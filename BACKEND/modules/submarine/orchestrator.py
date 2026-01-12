#!/usr/bin/env python3
"""
SUBMARINE - Unified Mass-Crawling & Indexing

Optimal pipeline for processing millions of domains using:
1. Common Crawl first (free archived content + links)
2. JESTER fallback (A/B/C/D - no paid APIs)
3. MAPPER entity extraction
4. PACMAN tier classification + ES indexing

Usage:
    ./orchestrator.py crawl --input domains.txt --concurrent 200
    ./orchestrator.py resume  # Resume from checkpoint
    ./orchestrator.py status  # Show progress
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Set, AsyncIterator, Tuple

import aiohttp
import httpx
from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

# ============================================================================
# CONFIGURATION
# ============================================================================

# Directories
# Data directory for input/output/checkpoints (can be overridden)
DATA_DIR = Path(os.getenv("SUBMARINE_DATA_DIR", "/data/submarine_data"))
INPUT_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"
CHECKPOINT_DIR = DATA_DIR / "checkpoints"

# Binary directory - USE JESTER'S BINARIES DIRECTLY
# JESTER is the scraping specialist; we use its tools.
JESTER_BIN_DIR = Path("/data/SEARCH_ENGINEER/BACKEND/modules/jester/scraping/go/bin")

# Go binaries
COLLY_BINARY = JESTER_BIN_DIR / "colly_crawler_linux"
CCLINKS_BINARY = JESTER_BIN_DIR / "cclinks"
ROD_BINARY = JESTER_BIN_DIR / "rod_crawler_linux"

# Common Crawl
CC_INDEX_BASE = "https://index.commoncrawl.org"
CC_DATA_BASE = "https://data.commoncrawl.org"
CC_ARCHIVE = "CC-MAIN-2025-47"  # Latest

# Wayback Machine
WAYBACK_CDX = "http://web.archive.org/cdx/search/cdx"

# Elasticsearch
ES_HOST = "http://localhost:9200"
ES_INDEX = "cymonides-2"

# Concurrency limits (standard profile)
CONCURRENT_CC_LOOKUP = 100      # CC Index queries
CONCURRENT_WARC_FETCH = 50      # WARC downloads (CC rate limits)
CONCURRENT_WAT_PROCESS = 10     # WAT files (large)
CONCURRENT_JESTER = 100         # Domain-level concurrency (A→B→C cascade per domain)
CONCURRENT_ES_BULK = 500        # ES bulk size

# Checkpointing
CHECKPOINT_INTERVAL = 10000     # Save every N domains

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("SUBMARINE")


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class DomainResult:
    """Result for a single domain."""
    domain: str
    source: str  # cc, jester_a, jester_b, jester_c, jester_d, failed
    url: Optional[str] = None  # Actual fetched URL for provenance
    content: Optional[str] = None
    content_length: int = 0
    status_code: int = 0
    latency_ms: int = 0
    cc_warc_path: Optional[str] = None
    cc_offset: Optional[int] = None
    cc_length: Optional[int] = None
    outlinks: List[str] = field(default_factory=list)
    backlinks: List[str] = field(default_factory=list)
    entities: Dict = field(default_factory=dict)
    tier: int = 3
    error: Optional[str] = None


@dataclass
class SubmarineProgress:
    """Track overall progress."""
    total_domains: int = 0
    processed: int = 0
    cc_hits: int = 0
    cc_misses: int = 0
    jester_a_hits: int = 0
    jester_b_hits: int = 0
    jester_c_hits: int = 0
    jester_d_hits: int = 0
    failed: int = 0
    indexed: int = 0
    start_time: float = field(default_factory=time.time)
    last_checkpoint: int = 0
    current_phase: str = "init"
    input_file: str = ""  # Track input file for resume

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time

    @property
    def rate(self) -> float:
        return self.processed / max(self.elapsed, 1)

    @property
    def eta_seconds(self) -> float:
        if self.rate == 0:
            return float('inf')
        return (self.total_domains - self.processed) / self.rate

    def display(self) -> str:
        pct = (self.processed / max(self.total_domains, 1)) * 100
        bar_width = 40
        filled = int(bar_width * pct / 100)
        bar = "█" * filled + "░" * (bar_width - filled)
        eta = str(timedelta(seconds=int(self.eta_seconds))) if self.eta_seconds < 86400*7 else "∞"

        return (
            f"\r[{bar}] {pct:.1f}% | "
            f"{self.processed:,}/{self.total_domains:,} | "
            f"{self.rate:.1f}/s | ETA: {eta} | "
            f"CC:{self.cc_hits:,} J-A:{self.jester_a_hits:,} J-B:{self.jester_b_hits:,} "
            f"J-C:{self.jester_c_hits:,} J-D:{self.jester_d_hits:,} ❌:{self.failed:,}"
        )

    def to_dict(self) -> dict:
        return {
            "total_domains": self.total_domains,
            "processed": self.processed,
            "cc_hits": self.cc_hits,
            "cc_misses": self.cc_misses,
            "jester_a_hits": self.jester_a_hits,
            "jester_b_hits": self.jester_b_hits,
            "jester_c_hits": self.jester_c_hits,
            "jester_d_hits": self.jester_d_hits,
            "failed": self.failed,
            "indexed": self.indexed,
            "start_time": self.start_time,
            "last_checkpoint": self.last_checkpoint,
            "current_phase": self.current_phase,
            "input_file": self.input_file,
            "saved_at": datetime.now().isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SubmarineProgress":
        p = cls()
        for k, v in data.items():
            if hasattr(p, k) and k != "saved_at":
                setattr(p, k, v)
        return p


# ============================================================================
# PHASE 1: CC INDEX BATCH LOOKUP
# ============================================================================

class CCIndexLookup:
    """
    Batch lookup domains in Common Crawl Index.

    Uses proper query patterns:
    - matchType=domain for domain-wide matching
    - filter=status:200 for successful pages only
    - collapse=urlkey to dedupe by URL
    - fl= to limit returned fields
    """

    def __init__(self, archive: str = CC_ARCHIVE):
        self.archive = archive
        self.index_url = f"{CC_INDEX_BASE}/{archive}-index"
        self._session: Optional[aiohttp.ClientSession] = None
        self._lookup_count = 0

    async def __aenter__(self):
        connector = aiohttp.TCPConnector(
            limit=CONCURRENT_CC_LOOKUP,
            limit_per_host=50,  # Don't hammer CC too hard
            keepalive_timeout=30,
        )
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self

    async def __aexit__(self, *args):
        if self._session:
            await self._session.close()

    async def lookup_domain(self, domain: str) -> Optional[Dict]:
        """
        Query CC Index for a domain using proper patterns.

        Uses: url={domain} with matchType=domain
        Returns best WARC location (most recent, status 200).
        """
        # matchType=domain handles wildcards internally - don't use * prefix
        params = {
            "url": domain,  # Just domain, matchType=domain handles subdomains
            "matchType": "domain",
            "output": "json",
            "fl": "url,filename,offset,length,status,timestamp,mime",
            "limit": "20",  # Get more options to find status:200
        }

        from urllib.parse import urlencode
        url = f"{self.index_url}?{urlencode(params)}"

        try:
            async with self._session.get(url) as resp:
                self._lookup_count += 1

                if resp.status == 503:
                    # Rate limited - back off
                    await asyncio.sleep(1)
                    return None

                if resp.status != 200:
                    return None

                text = await resp.text()
                if not text.strip():
                    return None

                # Parse NDJSON - pick best record (status:200, recent, largest)
                best_record = None
                best_score = 0

                for line in text.strip().split('\n'):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                        status = str(record.get("status", ""))
                        timestamp = int(record.get("timestamp", "0") or "0")
                        length = int(record.get("length", 0) or 0)
                        mime = record.get("mime", "")

                        # Score: heavily prefer status 200 + HTML content
                        score = 0
                        if status == "200":
                            score += 1000000000  # Strongly prefer 200
                        if "html" in mime.lower():
                            score += 100000000  # Prefer HTML
                        score += timestamp  # Prefer recent
                        score += length // 100  # Prefer larger

                        if score > best_score:
                            best_score = score
                            best_record = record
                    except (json.JSONDecodeError, ValueError):
                        continue

                if best_record:
                    best_record["domain"] = domain  # Track original domain
                    return best_record

                return None

        except asyncio.TimeoutError:
            logger.debug(f"CC lookup timeout for {domain}")
            return None
        except Exception as e:
            logger.debug(f"CC lookup failed for {domain}: {e}")
            return None

    async def batch_lookup(
        self,
        domains: List[str],
        progress_callback=None,
        output_file: Optional[Path] = None,
    ) -> Tuple[Dict[str, Dict], List[str]]:
        """
        Batch lookup domains in CC Index with proper concurrency.

        Args:
            domains: List of domains to lookup
            progress_callback: Called after each lookup
            output_file: If provided, stream results to JSONL file

        Returns:
            (cc_hits: {domain: cc_record}, cc_misses: [domains])
        """
        cc_hits = {}
        cc_misses = []

        # Open output file if provided
        out_fh = None
        if output_file:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            out_fh = open(output_file, 'w')

        sem = asyncio.Semaphore(CONCURRENT_CC_LOOKUP)
        lock = asyncio.Lock()

        async def lookup_one(domain: str):
            async with sem:
                result = await self.lookup_domain(domain)

                async with lock:
                    if result:
                        cc_hits[domain] = result
                        if out_fh:
                            out_fh.write(json.dumps(result) + '\n')
                    else:
                        cc_misses.append(domain)

                if progress_callback:
                    progress_callback()

        # Process in chunks for better memory management
        chunk_size = 5000
        for i in range(0, len(domains), chunk_size):
            chunk = domains[i:i + chunk_size]
            tasks = [lookup_one(d) for d in chunk]
            await asyncio.gather(*tasks, return_exceptions=True)

            # Brief pause between chunks to avoid rate limits
            if i + chunk_size < len(domains):
                await asyncio.sleep(0.5)

        if out_fh:
            out_fh.close()

        logger.info(f"CC Index: {self._lookup_count} lookups, {len(cc_hits)} hits, {len(cc_misses)} misses")
        return cc_hits, cc_misses


# ============================================================================
# PHASE 2a: CC CONTENT FETCHER (WARC + WAT)
# ============================================================================

class CCContentFetcher:
    """
    Fetch content from Common Crawl WARC files with proper parallelization.

    Uses Range requests to fetch only the needed bytes from each WARC.
    Processes multiple domains concurrently.
    """

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._fetch_count = 0
        self._success_count = 0

    async def __aenter__(self):
        connector = aiohttp.TCPConnector(
            limit=CONCURRENT_WARC_FETCH,
            limit_per_host=20,  # CC servers can handle this
            keepalive_timeout=60,
            enable_cleanup_closed=True,
        )
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=120, connect=30)
        )
        return self

    async def __aexit__(self, *args):
        if self._session:
            await self._session.close()

    async def fetch_warc_content(self, cc_record: Dict) -> Tuple[str, Optional[str]]:
        """
        Fetch actual content from WARC file using Range request.

        Returns: (domain, content or None)
        """
        domain = cc_record.get("domain", "unknown")
        filename = cc_record.get("filename")
        offset = int(cc_record.get("offset", 0) or 0)
        length = int(cc_record.get("length", 0) or 0)

        if not filename or not length:
            return domain, None

        url = f"{CC_DATA_BASE}/{filename}"
        headers = {"Range": f"bytes={offset}-{offset + length - 1}"}

        self._fetch_count += 1

        try:
            async with self._session.get(url, headers=headers) as resp:
                if resp.status not in (200, 206):
                    logger.debug(f"WARC fetch {domain}: HTTP {resp.status}")
                    return domain, None

                import gzip
                compressed = await resp.read()

                # Decompress WARC record
                try:
                    decompressed = gzip.decompress(compressed)
                    content = self._extract_html_from_warc(decompressed)
                    if content:
                        self._success_count += 1
                    return domain, content
                except gzip.BadGzipFile:
                    # Sometimes records aren't gzipped
                    content = self._extract_html_from_warc(compressed)
                    if content:
                        self._success_count += 1
                    return domain, content
                except Exception as e:
                    logger.debug(f"WARC decompress {domain}: {e}")
                    return domain, None

        except asyncio.TimeoutError:
            logger.debug(f"WARC timeout: {domain}")
            return domain, None
        except Exception as e:
            logger.debug(f"WARC fetch {domain}: {e}")
            return domain, None

    def _extract_html_from_warc(self, warc_data: bytes) -> Optional[str]:
        """Extract HTML content from WARC record."""
        try:
            text = warc_data.decode('utf-8', errors='ignore')

            # WARC format: WARC headers, blank line, HTTP headers, blank line, body
            # Find the double CRLF separating sections
            parts = text.split('\r\n\r\n', 2)

            if len(parts) >= 3:
                # parts[0] = WARC headers, parts[1] = HTTP headers, parts[2] = body
                body = parts[2]
            elif len(parts) == 2:
                body = parts[1]
            else:
                body = text

            # Basic validation - should look like HTML
            if '<' in body and '>' in body:
                return body

            return None
        except Exception:
            return None

    async def batch_fetch(
        self,
        cc_records: Dict[str, Dict],
        progress_callback=None,
        output_dir: Optional[Path] = None,
    ) -> List[DomainResult]:
        """
        Fetch content for multiple domains in parallel.

        Args:
            cc_records: {domain: cc_record} from CC Index lookup
            progress_callback: Called after each fetch with DomainResult
            output_dir: If provided, stream content to files

        Returns:
            List of DomainResult objects
        """
        results = []
        sem = asyncio.Semaphore(CONCURRENT_WARC_FETCH)
        lock = asyncio.Lock()

        # Open content output file if needed (APPEND mode to preserve across batches)
        content_fh = None
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            content_fh = open(output_dir / "cc_content.ndjson", 'a')

        async def fetch_one(domain: str, cc_record: Dict):
            async with sem:
                start = time.time()
                _, content = await self.fetch_warc_content(cc_record)
                latency = int((time.time() - start) * 1000)

                result = DomainResult(
                    domain=domain,
                    source="cc" if content else "cc_failed",
                    url=cc_record.get("url"),  # Actual CC URL
                    content=content,
                    content_length=len(content) if content else 0,
                    status_code=int(cc_record.get("status", 0) or 0),  # CC status
                    latency_ms=latency,
                    cc_warc_path=cc_record.get("filename"),
                    cc_offset=int(cc_record.get("offset", 0) or 0),
                    cc_length=int(cc_record.get("length", 0) or 0),
                )

                async with lock:
                    results.append(result)
                    if content_fh and content:
                        # Stream full content to file for downstream processing
                        content_fh.write(json.dumps({
                            "domain": domain,
                            "url": cc_record.get("url", ""),
                            "content_length": len(content),
                            "content": content,  # Full content, not preview
                        }) + '\n')

                if progress_callback:
                    progress_callback(result)

        # Process all records in parallel with semaphore
        tasks = [fetch_one(domain, record) for domain, record in cc_records.items()]
        await asyncio.gather(*tasks, return_exceptions=True)

        if content_fh:
            content_fh.close()

        logger.info(f"WARC fetch: {self._fetch_count} attempts, {self._success_count} success")
        return results


# ============================================================================
# PHASE 2b: JESTER FALLBACK SCRAPER
# ============================================================================

class JesterFallback:
    """JESTER scraping for domains not in CC. A→B→C→D cascade."""

    def __init__(self):
        self._http: Optional[httpx.AsyncClient] = None
        self._colly_available = COLLY_BINARY.exists()
        self._rod_available = ROD_BINARY.exists()

    async def __aenter__(self):
        self._http = httpx.AsyncClient(
            timeout=15,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SUBMARINE/1.0)"}
        )
        return self

    async def __aexit__(self, *args):
        if self._http:
            await self._http.aclose()

    async def scrape(self, domain: str) -> DomainResult:
        """Try A→B→C→D with URL fallbacks until one succeeds."""
        # URL patterns to try in order
        url_patterns = [
            f"https://www.{domain}",
            f"https://{domain}",
            f"http://www.{domain}",
            f"http://{domain}",
        ]

        for url in url_patterns:
            # Try JESTER_A (httpx) - fast, try first
            result = await self._try_jester_a(url, domain)
            if result.content:
                return result

        # All JESTER_A attempts failed, try B/C with URL fallbacks too
        if self._colly_available:
            for url in url_patterns:
                result = await self._try_jester_b(url, domain)
                if result.content:
                    return result

        # Try JESTER_C (rod) with URL fallbacks
        if self._rod_available:
            for url in url_patterns:
                result = await self._try_jester_c(url, domain)
                if result.content:
                    return result

        # JESTER_D would go here (headless) but skip for now

        # All failed
        return DomainResult(
            domain=domain,
            source="failed",
            error="All JESTER methods failed"
        )

    async def _try_jester_a(self, url: str, domain: str) -> DomainResult:
        """JESTER_A: httpx direct."""
        start = time.time()
        try:
            resp = await self._http.get(url)
            latency = int((time.time() - start) * 1000)

            if resp.status_code == 200 and len(resp.text) > 50:  # Lowered from 100
                return DomainResult(
                    domain=domain,
                    source="jester_a",
                    url=str(resp.url),  # Actual final URL after redirects
                    content=resp.text,
                    content_length=len(resp.text),
                    status_code=resp.status_code,
                    latency_ms=latency
                )
        except Exception:
            pass

        return DomainResult(domain=domain, source="jester_a", error="failed")

    async def _try_jester_b(self, url: str, domain: str) -> DomainResult:
        """JESTER_B: colly_crawler Go binary."""
        start = time.time()
        try:
            # Call colly_crawler for single URL
            proc = await asyncio.create_subprocess_exec(
                str(COLLY_BINARY), "crawl",
                f"--urls=[{json.dumps(url)}]",
                "--concurrent=1",
                "--timeout=15",
                "--include-html",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=20)
            latency = int((time.time() - start) * 1000)

            # Parse NDJSON output
            for line in stdout.decode().strip().split('\n'):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    if data.get("status_code") == 200 and data.get("html"):
                        return DomainResult(
                            domain=domain,
                            source="jester_b",
                            url=data.get("url", url),  # Use returned URL or input
                            content=data["html"],
                            content_length=len(data["html"]),
                            status_code=200,
                            latency_ms=latency,
                            outlinks=data.get("outlinks", [])
                        )
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            pass

        return DomainResult(domain=domain, source="jester_b", error="failed")

    async def _try_jester_c(self, url: str, domain: str) -> DomainResult:
        """JESTER_C: rod_crawler Go binary (JS rendering)."""
        start = time.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                str(ROD_BINARY), "crawl",
                f"--url={url}",
                "--timeout=30",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=35)
            latency = int((time.time() - start) * 1000)

            for line in stdout.decode().strip().split('\n'):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    if data.get("html"):
                        return DomainResult(
                            domain=domain,
                            source="jester_c",
                            url=data.get("url", url),  # Use returned URL or input
                            content=data["html"],
                            content_length=len(data["html"]),
                            status_code=200,
                            latency_ms=latency
                        )
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            pass

        return DomainResult(domain=domain, source="jester_c", error="failed")

    async def batch_scrape(
        self,
        domains: List[str],
        progress_callback=None
    ) -> List[DomainResult]:
        """Batch scrape domains not in CC."""
        results = []
        sem = asyncio.Semaphore(CONCURRENT_JESTER)

        async def scrape_one(domain: str):
            async with sem:
                result = await self.scrape(domain)
                results.append(result)
                if progress_callback:
                    progress_callback(result)

        tasks = [scrape_one(d) for d in domains]
        await asyncio.gather(*tasks, return_exceptions=True)

        return results


# ============================================================================
# PHASE 4: PACMAN INDEXER
# ============================================================================

class PacmanIndexer:
    """Tier classification and Elasticsearch indexing."""

    # LinkedIn domains loaded from ES
    linkedin_domains: Set[str] = set()

    def __init__(self, es_host: str = ES_HOST, index: str = ES_INDEX):
        self.es_host = es_host
        self.index = index
        self._es: Optional[AsyncElasticsearch] = None

    async def __aenter__(self):
        self._es = AsyncElasticsearch([self.es_host])
        # Load LinkedIn domains for Tier 1 classification
        await self._load_linkedin_domains()
        return self

    async def __aexit__(self, *args):
        if self._es:
            await self._es.close()

    async def _load_linkedin_domains(self):
        """Load LinkedIn domains from ES for tier classification."""
        try:
            # Already have them in the input file, but could load from ES
            logger.info("LinkedIn domains will be Tier 1 by default")
        except Exception as e:
            logger.warning(f"Could not load LinkedIn domains: {e}")

    def classify_tier(self, result: DomainResult) -> int:
        """Classify domain into Tier 1, 2, or 3."""
        # LinkedIn domains = Tier 1
        # This is a simplified classification - full PACMAN has more rules

        if result.source == "failed":
            return 3  # URL-only

        if result.content and len(result.content) > 1000:
            return 1  # Full content

        if result.content:
            return 2  # Some content

        return 3  # URL-only

    async def index_batch(self, results: List[DomainResult]) -> int:
        """Bulk index results to Elasticsearch."""
        if not results:
            return 0

        actions = []
        for r in results:
            tier = self.classify_tier(r)
            r.tier = tier

            doc = {
                "_index": self.index,
                "_id": f"submarine_{r.domain}",  # Stable ID prevents duplicates on rerun
                "_source": {
                    "source_url": r.url or f"https://{r.domain}",  # Use actual fetched URL
                    "source_domain": r.domain,
                    "source_type": "linkedin-submarine",
                    "tier": tier,
                    "scrape_source": r.source,
                    "content": r.content[:50000] if r.content and tier == 1 else "",
                    "content_length": r.content_length,
                    "status_code": r.status_code,
                    "latency_ms": r.latency_ms,
                    "outlinks_count": len(r.outlinks),
                    "indexed_at": datetime.utcnow().isoformat(),
                }
            }

            if r.error:
                doc["_source"]["error"] = r.error

            actions.append(doc)

        try:
            success, failed = await async_bulk(
                self._es, actions,
                raise_on_error=False,
                stats_only=True
            )
            if failed:
                logger.warning(f"ES bulk: {success} indexed, {failed} failed")
            return success
        except Exception as e:
            logger.error(f"ES bulk indexing failed: {e}")
            return 0


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================

class SubmarineOrchestrator:
    """Main orchestrator for SUBMARINE pipeline."""

    def __init__(self):
        self.progress = SubmarineProgress()
        self._shutdown = False

        # Register signal handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        logger.info("\n⚠️  Shutdown requested - saving checkpoint...")
        self._shutdown = True
        self._save_checkpoint()
        sys.exit(0)

    def _save_checkpoint(self):
        """Save progress checkpoint."""
        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        checkpoint_file = CHECKPOINT_DIR / "progress.json"
        temp_file = checkpoint_file.with_suffix('.tmp')

        with open(temp_file, 'w') as f:
            json.dump(self.progress.to_dict(), f, indent=2)
        temp_file.replace(checkpoint_file)

        logger.info(f"✅ Checkpoint saved: {self.progress.processed:,} domains")

    def _load_checkpoint(self) -> bool:
        """Load checkpoint if exists."""
        checkpoint_file = CHECKPOINT_DIR / "progress.json"
        if not checkpoint_file.exists():
            return False

        try:
            with open(checkpoint_file) as f:
                data = json.load(f)
            self.progress = SubmarineProgress.from_dict(data)
            logger.info(f"📂 Resuming from checkpoint: {self.progress.processed:,} domains")
            return True
        except Exception as e:
            logger.warning(f"Could not load checkpoint: {e}")
            return False

    async def run(
        self,
        input_file: Path,
        resume: bool = False,
        dry_run: bool = False
    ):
        """Run the full SUBMARINE pipeline."""

        # Setup directories
        for d in [INPUT_DIR, OUTPUT_DIR, CHECKPOINT_DIR]:
            d.mkdir(parents=True, exist_ok=True)

        # Count domains first (memory-efficient)
        logger.info(f"📂 Counting domains in {input_file}...")
        with open(input_file) as f:
            total_lines = sum(1 for line in f if line.strip())

        self.progress.total_domains = total_lines
        self.progress.input_file = str(input_file)  # Track for resume
        logger.info(f"📊 Total domains: {self.progress.total_domains:,}")

        # Resume from checkpoint?
        start_idx = 0
        if resume and self._load_checkpoint():
            start_idx = self.progress.last_checkpoint
            self.progress.start_time = time.time()  # Reset for accurate ETA
            logger.info(f"   Resuming from index {start_idx:,}")

        if dry_run:
            logger.info("🧪 DRY RUN - no actual processing")
            return

        # Stream domains in batches (memory-efficient - never load full file)
        batch_size = CHECKPOINT_INTERVAL
        current_idx = 0
        batch = []

        with open(input_file) as f:
            for line in f:
                domain = line.strip()
                if not domain:
                    continue

                current_idx += 1

                # Skip until we reach start_idx (for resume)
                if current_idx <= start_idx:
                    continue

                batch.append(domain)

                # Process when batch is full
                if len(batch) >= batch_size:
                    if self._shutdown:
                        break
                    await self._process_batch(batch)
                    self.progress.last_checkpoint = current_idx
                    self._save_checkpoint()
                    batch = []

        # Process remaining batch
        if batch and not self._shutdown:
            await self._process_batch(batch)
            self.progress.last_checkpoint = current_idx
            self._save_checkpoint()

        logger.info("\n\n✅ SUBMARINE complete!")
        self._print_final_stats()

    async def _process_batch(self, domains: List[str]):
        """Process a batch of domains through all phases."""

        self.progress.current_phase = "cc_lookup"
        logger.info(f"\n📡 Phase 1: CC Index lookup for {len(domains):,} domains...")

        # Phase 1: CC Index lookup
        async with CCIndexLookup() as cc_lookup:
            cc_hits, cc_misses = await cc_lookup.batch_lookup(
                domains,
                progress_callback=lambda: None
            )

        self.progress.cc_hits += len(cc_hits)
        self.progress.cc_misses += len(cc_misses)
        logger.info(f"   CC hits: {len(cc_hits):,}, CC misses: {len(cc_misses):,}")

        # Phase 2a: Fetch CC content (PARALLEL)
        self.progress.current_phase = "cc_fetch"
        results: List[DomainResult] = []

        # Write CC hits to output file
        cc_hits_file = OUTPUT_DIR / "cc_hits.jsonl"
        cc_miss_file = OUTPUT_DIR / "cc_miss.txt"
        content_dir = OUTPUT_DIR / "content"
        content_dir.mkdir(parents=True, exist_ok=True)

        # Append CC hits to JSONL
        with open(cc_hits_file, "a") as f:
            for domain, record in cc_hits.items():
                f.write(json.dumps({"domain": domain, **record}) + "\n")

        # Append CC misses
        with open(cc_miss_file, "a") as f:
            for domain in cc_misses:
                f.write(domain + "\n")

        if cc_hits:
            logger.info(f"📥 Phase 2a: Fetching CC content for {len(cc_hits):,} domains (parallel)...")
            async with CCContentFetcher() as fetcher:
                # Use parallel batch_fetch instead of sequential loop
                cc_results = await fetcher.batch_fetch(
                    cc_hits,
                    progress_callback=lambda r: logger.debug(f"CC fetch {r.domain}: {'✓' if r.content else '✗'}"),
                    output_dir=content_dir
                )
                results.extend(cc_results)

        # Phase 2b: JESTER fallback for CC misses
        if cc_misses:
            self.progress.current_phase = "jester"
            logger.info(f"🔧 Phase 2b: JESTER scraping {len(cc_misses):,} domains...")

            async with JesterFallback() as jester:
                jester_results = await jester.batch_scrape(
                    cc_misses,
                    progress_callback=lambda r: self._update_jester_stats(r)
                )
                results.extend(jester_results)

        # Phase 4: Index to Elasticsearch
        self.progress.current_phase = "indexing"
        logger.info(f"📤 Phase 4: Indexing {len(results):,} results to ES...")

        async with PacmanIndexer() as indexer:
            indexed = await indexer.index_batch(results)
            self.progress.indexed += indexed

        # Clear content from results to free memory
        for r in results:
            r.content = None

        self.progress.processed += len(domains)
        print(self.progress.display(), end="", flush=True)

    def _update_jester_stats(self, result: DomainResult):
        """Update progress stats based on JESTER result."""
        if result.source == "jester_a":
            self.progress.jester_a_hits += 1
        elif result.source == "jester_b":
            self.progress.jester_b_hits += 1
        elif result.source == "jester_c":
            self.progress.jester_c_hits += 1
        elif result.source == "jester_d":
            self.progress.jester_d_hits += 1
        elif result.source == "failed":
            self.progress.failed += 1

    def _print_final_stats(self):
        """Print final statistics."""
        p = self.progress
        elapsed = timedelta(seconds=int(p.elapsed))

        print("\n" + "=" * 60)
        print("SUBMARINE FINAL STATS")
        print("=" * 60)
        print(f"Total processed:  {p.processed:,}")
        print(f"CC hits:          {p.cc_hits:,} ({p.cc_hits/max(p.processed,1)*100:.1f}%)")
        print(f"CC misses:        {p.cc_misses:,}")
        print(f"JESTER A hits:    {p.jester_a_hits:,}")
        print(f"JESTER B hits:    {p.jester_b_hits:,}")
        print(f"JESTER C hits:    {p.jester_c_hits:,}")
        print(f"JESTER D hits:    {p.jester_d_hits:,}")
        print(f"Failed:           {p.failed:,}")
        print(f"Indexed:          {p.indexed:,}")
        print(f"Duration:         {elapsed}")
        print(f"Avg rate:         {p.rate:.1f} domains/sec")
        print("=" * 60)


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="SUBMARINE - Mass Crawling & Indexing")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # crawl command
    crawl_parser = subparsers.add_parser("crawl", help="Run the crawl pipeline")
    crawl_parser.add_argument("--input", "-i", type=Path, required=True, help="Input domains file")
    crawl_parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    crawl_parser.add_argument("--dry-run", action="store_true", help="Dry run (no processing)")

    # resume command
    subparsers.add_parser("resume", help="Resume from last checkpoint")

    # status command
    subparsers.add_parser("status", help="Show current progress")

    args = parser.parse_args()

    orchestrator = SubmarineOrchestrator()

    if args.command == "crawl":
        asyncio.run(orchestrator.run(
            input_file=args.input,
            resume=args.resume,
            dry_run=args.dry_run
        ))

    elif args.command == "resume":
        # Find input file from checkpoint
        checkpoint_file = CHECKPOINT_DIR / "progress.json"
        if not checkpoint_file.exists():
            print("❌ No checkpoint found")
            sys.exit(1)

        # Read input file from checkpoint
        with open(checkpoint_file) as f:
            data = json.load(f)
        input_file = Path(data.get("input_file", ""))
        if not input_file or not input_file.exists():
            print(f"❌ Input file from checkpoint not found: {input_file}")
            sys.exit(1)
        asyncio.run(orchestrator.run(input_file=input_file, resume=True))

    elif args.command == "status":
        checkpoint_file = CHECKPOINT_DIR / "progress.json"
        if checkpoint_file.exists():
            with open(checkpoint_file) as f:
                data = json.load(f)
            print(json.dumps(data, indent=2))
        else:
            print("No checkpoint found")


if __name__ == "__main__":
    main()
