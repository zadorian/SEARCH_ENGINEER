"""
SUBMARINE Distributed Scraper

Architecture:
- SASTRE (primary): High concurrency (500+ threads), 20-core server
- LOCAL MAC (secondary): Rate limit evasion IP, lower concurrency

When sastre gets rate-limited on a domain, local Mac takes over.
ALL results stream to sastre Elasticsearch immediately.

Usage:
    # SASTRE (PRIMARY) - high concurrency, processes most domains
    python -m modules.SUBMARINE.distributed_scraper \
        --domains domains.txt \
        --concurrent 500 \
        --es-host localhost:9200

    # LOCAL MAC (SECONDARY) - rate limit evasion, lower concurrency
    # Takes domains that sastre couldn't scrape due to rate limits
    python -m modules.SUBMARINE.distributed_scraper \
        --domains rate_limited_domains.txt \
        --concurrent 50 \
        --es-host 176.9.2.153:9200

    # Or run both in parallel with chunks (sastre gets 90%, local gets 10%)
    # SASTRE:
    python -m modules.SUBMARINE.distributed_scraper \
        --domains domains.txt --chunk 0 --total-chunks 10 \
        --concurrent 500 --es-host localhost:9200
    # ... (chunks 1-8 also on sastre)

    # LOCAL (just 1 chunk for rate limit diversity):
    python -m modules.SUBMARINE.distributed_scraper \
        --domains domains.txt --chunk 9 --total-chunks 10 \
        --concurrent 50 --es-host 176.9.2.153:9200

Optional enrichment:
    --include-io            # Attach IO Matrix metadata (category, search template) from io-matrix
    --io-index io-matrix    # Override IO index name (default: io-matrix)
"""

import asyncio
import argparse
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import aiohttp
import logging
import sys
from urllib.parse import quote_plus

# Setup paths for SUBJECT and PACMAN imports
if "/data" not in sys.path:
    sys.path.insert(0, "/data")
if "/data/CLASSES" not in sys.path:
    sys.path.insert(0, "/data/CLASSES")
if "/data/SUBMARINE" not in sys.path:
    sys.path.insert(0, "/data/SUBMARINE")
# Setup paths for SEARCH_ENGINEER backend modules (JESTER/BACKDRILL/TORPEDO)
for backend_root in ("/data/SEARCH_ENGINEER/BACKEND", "/data/SEARCH_ENGINEER/nexus/BACKEND"):
    try:
        if backend_root not in sys.path and Path(backend_root).exists():
            sys.path.insert(0, backend_root)
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# Sastre ES endpoint
DEFAULT_ES_HOST = "176.9.2.153"
DEFAULT_ES_PORT = 9200
ES_INDEX = "submarine-scrapes"
DEFAULT_IO_INDEX = "io-matrix"


class SastreStreamer:
    """Stream scraped data to sastre Elasticsearch."""

    def __init__(self, es_host: str = DEFAULT_ES_HOST, es_port: int = DEFAULT_ES_PORT):
        self.es_url = f"http://{es_host}:{es_port}"
        self._session: Optional[aiohttp.ClientSession] = None
        self._buffer: List[Dict] = []
        self._buffer_size = 100  # Bulk index every 100 docs

    async def _ensure_session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession()

    async def _ensure_index(self):
        """Create index if not exists."""
        await self._ensure_session()
        try:
            async with self._session.head(f"{self.es_url}/{ES_INDEX}") as resp:
                if resp.status == 404:
                    mapping = {
                        "mappings": {
                            "properties": {
                                "url": {"type": "keyword"},
                                "domain": {"type": "keyword"},
                                "html": {"type": "text", "index": False},
                                "text": {"type": "text"},
                                "title": {"type": "text"},
                                "timestamp": {"type": "date"},
                                "source": {"type": "keyword"},
                                "scraper_ip": {"type": "keyword"},
                                "content_length": {"type": "integer"},
                                "status_code": {"type": "integer"},
                                "entities": {"type": "object", "enabled": False},
                                "scraped_at": {"type": "date"},
                                # Full extraction fields
                                "themes": {"type": "keyword"},
                                "phenomena": {"type": "keyword"},
                                "persons": {"type": "nested", "properties": {
                                    "name": {"type": "text"},
                                    "confidence": {"type": "float"},
                                }},
                                "companies": {"type": "nested", "properties": {
                                    "name": {"type": "text"},
                                    "confidence": {"type": "float"},
                                }},
                                "locations": {"type": "keyword"},
                                "industry": {"type": "keyword"},
                                "red_flags": {"type": "keyword"},
                                # SUBJECT detection fields
                                "professions": {"type": "nested", "properties": {
                                    "name": {"type": "keyword"},
                                    "confidence": {"type": "float"},
                                    "language": {"type": "keyword"},
                                    "matched_term": {"type": "text"},
                                }},
                                "titles": {"type": "nested", "properties": {
                                    "name": {"type": "keyword"},
                                    "confidence": {"type": "float"},
                                    "language": {"type": "keyword"},
                                    "matched_term": {"type": "text"},
                                }},
                                "industries": {"type": "nested", "properties": {
                                    "name": {"type": "keyword"},
                                    "confidence": {"type": "float"},
                                    "language": {"type": "keyword"},
                                    "matched_term": {"type": "text"},
                                }},
                                "outlinks": {"type": "nested", "properties": {
                                    "url": {"type": "keyword"},
                                    "text": {"type": "text"},
                                    "domain": {"type": "keyword"},
                                    "is_external": {"type": "boolean"},
                                }},
                                "outlinks_external": {"type": "nested", "properties": {
                                    "url": {"type": "keyword"},
                                    "text": {"type": "text"},
                                    "domain": {"type": "keyword"},
                                    "is_external": {"type": "boolean"},
                                }},
                                # IO Matrix enrichment
                                "site_category": {"type": "keyword"},
                                "io_source_id": {"type": "keyword"},
                                "io_source_domain": {"type": "keyword"},
                                "io_source_name": {"type": "text"},
                                "io_source_type": {"type": "keyword"},
                                "io_source_category": {"type": "keyword"},
                                "io_jurisdiction": {"type": "keyword"},
                                "io_jurisdictions": {"type": "keyword"},
                                "io_search_url": {"type": "keyword"},
                                "io": {"type": "object", "enabled": False},
                            }
                        }
                    }
                    async with self._session.put(
                        f"{self.es_url}/{ES_INDEX}",
                        json=mapping,
                        headers={"Content-Type": "application/json"}
                    ) as create_resp:
                        if create_resp.status in (200, 201):
                            logger.info(f"Created index {ES_INDEX}")
        except Exception as e:
            logger.warning(f"Index check failed: {e}")

    async def stream(self, doc: Dict[str, Any]):
        """Add doc to buffer, flush when full."""
        self._buffer.append(doc)
        if len(self._buffer) >= self._buffer_size:
            await self.flush()

    async def flush(self):
        """Bulk index buffered documents to sastre."""
        if not self._buffer:
            return

        await self._ensure_session()

        # Build bulk request body
        bulk_body = ""
        for doc in self._buffer:
            action = {"index": {"_index": ES_INDEX}}
            bulk_body += json.dumps(action) + "\n"
            bulk_body += json.dumps(doc) + "\n"

        try:
            async with self._session.post(
                f"{self.es_url}/_bulk",
                data=bulk_body,
                headers={"Content-Type": "application/x-ndjson"},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    errors = result.get("errors", False)
                    if errors:
                        logger.warning(f"Bulk index had errors")
                    else:
                        logger.info(f"Streamed {len(self._buffer)} docs to sastre")
                else:
                    logger.error(f"Bulk index failed: {resp.status}")
        except Exception as e:
            logger.error(f"Stream to sastre failed: {e}")

        self._buffer = []

    async def close(self):
        await self.flush()
        if self._session:
            await self._session.close()


class DistributedScraper:
    """
    Distributed scraper that runs locally or on sastre.
    Streams all results to sastre ES.
    """

    def __init__(
        self,
        es_host: str = DEFAULT_ES_HOST,
        es_port: int = DEFAULT_ES_PORT,
        use_jester: bool = True,
        use_backdrill: bool = True,
        concurrent: int = 100,
        include_io: bool = False,
        io_index: str = DEFAULT_IO_INDEX,
        io_es_host: Optional[str] = None,
        io_es_port: Optional[int] = None,
    ):
        self.streamer = SastreStreamer(es_host, es_port)
        self.use_jester = use_jester
        self.use_backdrill = use_backdrill
        self.concurrent = concurrent
        self._jester = None
        self._backdrill = None
        self.include_io = include_io
        self.io_index = io_index
        io_host = io_es_host or es_host
        io_port = io_es_port or es_port
        self.io_es_url = f"http://{io_host}:{io_port}"
        self._torpedo_searcher = None

        # Get local IP for tracking
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            self.scraper_ip = s.getsockname()[0]
            s.close()
        except:
            self.scraper_ip = "unknown"

    async def _get_jester(self):
        if self._jester is None and self.use_jester:
            try:
                from modules.JESTER import Jester
                self._jester = Jester()
            except ImportError:
                logger.debug("JESTER not available, will use httpx fallback")
                self._jester = None
        return self._jester

    async def _get_backdrill(self):
        if self._backdrill is None and self.use_backdrill:
            try:
                from modules.BACKDRILL import Backdrill
                self._backdrill = Backdrill(
                    enable_cc=True,
                    enable_wayback=True,
                    enable_memento=False,
                )
            except ImportError:
                logger.debug("BACKDRILL not available, will use httpx fallback")
                self._backdrill = None
        return self._backdrill

    def _normalize_domain(self, value: str) -> str:
        if not value:
            return ""
        value = value.strip().lower()
        value = value.replace("https://", "").replace("http://", "")
        value = value.split("/")[0]
        return value

    async def _io_lookup_source(self, domain: str) -> Optional[Dict[str, Any]]:
        """
        Lookup a domain in the IO Matrix Elasticsearch index (io-matrix).

        Returns the matching source doc (or None).
        """
        domain = self._normalize_domain(domain)
        if not domain:
            return None

        candidates = [domain]
        if domain.startswith("www."):
            candidates.append(domain[4:])

        queries = [{"term": {"domain": d}} for d in candidates if d]
        if not queries:
            return None

        await self.streamer._ensure_session()

        indices = [self.io_index] if self.io_index else []
        if DEFAULT_IO_INDEX not in indices:
            indices.append(DEFAULT_IO_INDEX)
        if "io-matrix-sources" not in indices:
            indices.append("io-matrix-sources")

        headers = {"Content-Type": "application/json"}
        timeout = aiohttp.ClientTimeout(total=5)

        for index in indices:
            for include_doc_type in (True, False):
                must_filters: List[Dict[str, Any]] = []
                if include_doc_type:
                    must_filters.append({"term": {"doc_type": "source"}})
                must_filters.append({"bool": {"should": queries, "minimum_should_match": 1}})

                es_query = {"query": {"bool": {"filter": must_filters}}, "size": 1}

                try:
                    async with self.streamer._session.post(
                        f"{self.io_es_url}/{index}/_search",
                        json=es_query,
                        headers=headers,
                        timeout=timeout,
                    ) as resp:
                        if resp.status == 404:
                            break
                        if resp.status != 200:
                            continue
                        data = await resp.json()
                except Exception:
                    continue

                hits = (data.get("hits") or {}).get("hits") or []
                if hits:
                    src = hits[0].get("_source")
                    if isinstance(src, dict):
                        return src

        return None

    def _apply_io_source(self, doc: Dict[str, Any], src: Dict[str, Any], domain: str) -> None:
        doc["site_category"] = src.get("category")
        doc["io_source_id"] = src.get("id")
        doc["io_source_domain"] = src.get("domain") or domain
        doc["io_source_name"] = src.get("name")
        doc["io_source_type"] = src.get("source_type") or src.get("type")
        doc["io_source_category"] = src.get("category")
        doc["io_jurisdiction"] = src.get("jurisdiction")
        doc["io_jurisdictions"] = src.get("jurisdictions") or []
        doc["io_search_url"] = src.get("search_url") or src.get("search_template")
        doc["io"] = src

    async def _attach_io(self, doc: Dict[str, Any], include_io: bool) -> None:
        if not include_io:
            return
        if "io" in doc:
            return
        domain = doc.get("domain") or self._normalize_domain(doc.get("url", ""))
        if not domain:
            return

        try:
            src = await self._io_lookup_source(domain)
            if not src:
                return
            self._apply_io_source(doc, src, domain)
        except Exception as e:
            logger.debug(f"IO enrichment failed for {domain}: {e}")

    async def _get_torpedo_searcher(self):
        if self._torpedo_searcher is None:
            try:
                from modules.TORPEDO.EXECUTION.base_searcher import BaseSearcher
                self._torpedo_searcher = BaseSearcher()
            except ImportError:
                self._torpedo_searcher = None
        return self._torpedo_searcher

    async def torpedo_search_site(
        self,
        domain: str,
        query: str,
        template: Optional[str] = None,
        scrape_method: Optional[str] = None,
        use_brightdata: bool = False,
        extract: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute a single-site TORPEDO search using a site search template.

        If template is not provided, resolves it via io-matrix source lookup.
        """
        domain_norm = self._normalize_domain(domain)

        src = None
        if not template:
            src = await self._io_lookup_source(domain_norm)
            template = (src or {}).get("search_url") or (src or {}).get("search_template")

        if not template or "{q}" not in template:
            return {
                "success": False,
                "domain": domain_norm,
                "query": query,
                "error": "No usable search template found (expected '{q}' in template).",
                "template": template,
                "io_source": src,
            }

        if not scrape_method and isinstance(src, dict):
            classification = src.get("classification") if isinstance(src.get("classification"), dict) else {}
            scrape_method = classification.get("scrape_method") or src.get("scrape_method")

        search_url = template.replace("{q}", quote_plus(query))

        searcher = await self._get_torpedo_searcher()
        if not searcher:
            return {
                "success": False,
                "domain": domain_norm,
                "query": query,
                "template": template,
                "search_url": search_url,
                "error": "TORPEDO execution not available (modules.TORPEDO not importable).",
                "io_source": src,
            }

        fetched = await searcher.fetch_url(
            search_url,
            scrape_method=scrape_method,
            use_brightdata=use_brightdata,
        )

        result: Dict[str, Any] = {
            "success": fetched.get("success", False),
            "domain": domain_norm,
            "query": query,
            "template": template,
            "search_url": search_url,
            "status_code": fetched.get("status_code"),
            "method_used": fetched.get("method_used"),
            "error": fetched.get("error"),
            "io_source": src,
            "html": fetched.get("html"),
        }

        if extract and fetched.get("html"):
            try:
                extraction = await self._extract_full(fetched["html"], "", search_url)
                result["extraction"] = extraction
            except Exception as e:
                result["extraction_error"] = str(e)

        return result

    async def scrape_domain(self, domain: str) -> Dict[str, Any]:
        """Scrape a single domain (homepage only), return doc for ES."""
        url = f"https://{domain}" if not domain.startswith("http") else domain

        result = {
            "url": url,
            "domain": domain.replace("https://", "").replace("http://", "").split("/")[0],
            "scraper_ip": self.scraper_ip,
            "scraped_at": datetime.utcnow().isoformat(),
        }

        # Try JESTER first (live scraping)
        if self.use_jester:
            try:
                jester = await self._get_jester()
                if jester:
                    jr = await jester.scrape(url)
                    if jr.html and len(jr.html) > 100:
                        # Run FULL extraction (persons, companies, industries, outlinks)
                        extraction = await self._extract_full(jr.html, jr.text, url)
                        result.update({
                            "html": jr.html,
                            "text": jr.text,
                            "title": jr.title,
                            "source": f"jester_{jr.method.value}",
                            "content_length": len(jr.html),
                            "status_code": jr.status_code,
                            "entities": extraction.get("entities", jr.entities or {}),
                            "persons": extraction.get("persons", []),
                            "companies": extraction.get("companies", []),
                            "titles": extraction.get("titles", []),
                            "professions": extraction.get("professions", []),
                            "industries": extraction.get("industries", []),
                            "industry": extraction.get("industry"),
                            "outlinks": extraction.get("outlinks", []),
                            "outlinks_external": extraction.get("outlinks_external", []),
                        })
                        await self._attach_io(result, include_io=self.include_io)
                        return result
            except Exception as e:
                logger.debug(f"JESTER failed for {domain}: {e}")

        # Fallback to BACKDRILL (archives)
        if self.use_backdrill:
            try:
                bd = await self._get_backdrill()
                if bd:
                    br = await bd.fetch(url)
                    if br.success:
                        # Run FULL extraction (persons, companies, industries, outlinks)
                        extraction = await self._extract_full(br.html, br.content, url)
                        result.update({
                            "html": br.html,
                            "text": br.content,
                            "source": br.source.value if br.source else "backdrill",
                            "content_length": len(br.html) if br.html else 0,
                            "status_code": br.status_code,
                            "timestamp": br.timestamp.isoformat() if br.timestamp else None,
                            "entities": extraction.get("entities", {}),
                            "persons": extraction.get("persons", []),
                            "companies": extraction.get("companies", []),
                            "titles": extraction.get("titles", []),
                            "professions": extraction.get("professions", []),
                            "industries": extraction.get("industries", []),
                            "industry": extraction.get("industry"),
                            "outlinks": extraction.get("outlinks", []),
                            "outlinks_external": extraction.get("outlinks_external", []),
                        })
                        await self._attach_io(result, include_io=self.include_io)
                        return result
            except Exception as e:
                logger.debug(f"BACKDRILL failed for {domain}: {e}")

        # Fallback to simple httpx (when JESTER/BACKDRILL unavailable)
        try:
            import httpx
            async with httpx.AsyncClient(
                timeout=15.0,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; SubmarineCrawler/1.0)"}
            ) as client:
                resp = await client.get(url)
                if resp.status_code == 200 and len(resp.text) > 100:
                    html = resp.text
                    # Extract text from HTML (simple)
                    import re
                    text = re.sub(r'<[^>]+>', ' ', html)
                    text = re.sub(r'\s+', ' ', text).strip()
                    # Extract title
                    title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.I)
                    title = title_match.group(1).strip() if title_match else None

                    # Run FULL extraction (persons, companies, industries, outlinks)
                    extraction = await self._extract_full(html, text[:100000], url)
                    result.update({
                        "html": html,
                        "text": text[:100000],  # Limit text size
                        "title": title,
                        "source": "httpx_direct",
                        "content_length": len(html),
                        "status_code": resp.status_code,
                        "entities": extraction.get("entities", {}),
                        "persons": extraction.get("persons", []),
                        "companies": extraction.get("companies", []),
                        "titles": extraction.get("titles", []),
                        "professions": extraction.get("professions", []),
                        "industries": extraction.get("industries", []),
                        "industry": extraction.get("industry"),
                        "outlinks": extraction.get("outlinks", []),
                        "outlinks_external": extraction.get("outlinks_external", []),
                    })
                    await self._attach_io(result, include_io=self.include_io)
                    return result
        except Exception as e:
            logger.debug(f"httpx fallback failed for {domain}: {e}")

        # Failed
        result["source"] = "failed"
        result["content_length"] = 0
        await self._attach_io(result, include_io=self.include_io)
        return result

    async def crawl_domain_full(
        self,
        domain: str,
        max_pages: int = 50,
        max_depth: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Crawl FULL domain (multiple pages) with FULL extraction.

        Extracts:
        - Entities (email, phone, LEI, IBAN, crypto, company numbers)
        - Themes (ownership analysis, sanctions, financial crime, etc.)
        - Phenomena (shell company, circular ownership, etc.)
        - Persons & Companies (if UniversalExtractor available)
        - Industry classification

        Streams each page to sastre as it's crawled.

        Args:
            domain: Domain to crawl
            max_pages: Max pages per domain (default 50)
            max_depth: Max crawl depth (default 3)

        Returns:
            List of docs (also streamed to ES)
        """
        from modules.JESTER.scraper import crawl_domain, DomainCrawlConfig

        url = f"https://{domain}" if not domain.startswith("http") else domain
        base_domain = domain.replace("https://", "").replace("http://", "").split("/")[0]
        io_src = None
        if self.include_io:
            io_src = await self._io_lookup_source(base_domain)

        config = DomainCrawlConfig(
            max_pages=max_pages,
            max_depth=max_depth,
            follow_outlinks=False,
            delay_between_pages=0.1,
        )

        docs = []

        try:
            async for page in crawl_domain(url, config):
                # Run FULL extraction (entities + themes + phenomena)
                extraction = await self._extract_full(page.html, page.text, page.url)

                doc = {
                    "url": page.url,
                    "domain": base_domain,
                    "html": page.html,
                    "text": page.text,
                    "title": page.title,
                    "source": f"jester_{page.method.value}" if hasattr(page, 'method') else "jester_crawl",
                    "content_length": len(page.html) if page.html else 0,
                    "status_code": page.status_code if hasattr(page, 'status_code') else 200,
                    "scraper_ip": self.scraper_ip,
                    "scraped_at": datetime.utcnow().isoformat(),
                    "depth": getattr(page, 'depth', 0),
                    "links_found": len(page.links) if hasattr(page, 'links') else 0,
                    # FULL EXTRACTION (UniversalExtractor / PACMAN)
                    "entities": extraction.get("entities", {}),
                    "themes": extraction.get("themes", []),
                    "phenomena": extraction.get("phenomena", []),
                    "persons": extraction.get("persons", []),
                    "companies": extraction.get("companies", []),
                    "locations": extraction.get("locations", []),
                    "industry": extraction.get("industry"),
                    "red_flags": extraction.get("red_flags", []),
                    # SUBJECT DETECTION (professions, titles, industries)
                    "professions": extraction.get("professions", []),
                    "titles": extraction.get("titles", []),
                    "industries": extraction.get("industries", []),
                    "outlinks": extraction.get("outlinks", []),
                    "outlinks_external": extraction.get("outlinks_external", []),
                }
                if io_src:
                    self._apply_io_source(doc, io_src, base_domain)

                # Stream to sastre immediately
                await self.streamer.stream(doc)
                docs.append(doc)

        except Exception as e:
            logger.error(f"Domain crawl failed for {domain}: {e}")
            # Try homepage fallback
            fallback = await self.scrape_domain(domain)
            if fallback.get("content_length", 0) > 0:
                await self.streamer.stream(fallback)
                docs.append(fallback)

        return docs

    async def _extract_full(self, html: str, text: str, url: str = "") -> Dict[str, Any]:
        """
        Run FULL extraction: entities + themes + phenomena + persons + companies + SUBJECT (profession/title/industry).

        Priority:
        1. UniversalExtractor (sastre, full embeddings)
        2. SUBJECT Detector (professions, titles, industries from synonyms.json)
        3. PACMAN regex (basic entity extraction)
        """
        result = {
            "entities": {},
            "themes": [],
            "phenomena": [],
            "persons": [],
            "companies": [],
            "locations": [],
            "industry": None,
            "red_flags": [],
            "professions": [],  # NEW: from SUBJECT
            "titles": [],       # NEW: from SUBJECT
            "industries": [],   # NEW: from SUBJECT (more granular)
            "outlinks": [],
            "outlinks_external": [],
        }

        if not html or len(html) < 100:
            return result

        content = text or html

        # 1. Try UniversalExtractor (full extraction with embeddings)
        try:
            try:
                from PACMAN.universal_extractor import UniversalExtractor
                extractor = UniversalExtractor()
                full_result = extractor.extract(content)
                result.update({
                    "entities": full_result.get("identifiers", {}),
                    "themes": full_result.get("themes", []),
                    "phenomena": full_result.get("phenomena", []),
                    "persons": full_result.get("persons", []),
                    "companies": full_result.get("companies", []),
                    "locations": full_result.get("locations", []),
                    "industry": full_result.get("industry"),
                    "red_flags": full_result.get("red_flags", []),
                })
            except ImportError:
                pass
        except Exception as e:
            logger.debug(f"UniversalExtractor failed: {e}")

        # 2. SUBJECT Detector - professions, titles, industries (multilingual)
        try:
            # Try sastre path first
            try:
                import sys
                if '/data/CLASSES' not in sys.path:
                    sys.path.insert(0, '/data/CLASSES')
                from SUBJECT.detector import classify_text

                subject_result = classify_text(content[:100000])  # Limit scan size

                # Merge detected professions
                if subject_result.get('professions'):
                    for p in subject_result['professions']:
                        if p['name'] not in [x.get('name') for x in result['professions']]:
                            result['professions'].append({
                                'name': p['name'],
                                'confidence': p['confidence'],
                                'language': p['language'],
                                'matched_term': p['matched_term'],
                            })

                # Merge detected titles
                if subject_result.get('titles'):
                    for t in subject_result['titles']:
                        if t['name'] not in [x.get('name') for x in result['titles']]:
                            result['titles'].append({
                                'name': t['name'],
                                'confidence': t['confidence'],
                                'language': t['language'],
                                'matched_term': t['matched_term'],
                            })

                # Merge detected industries
                if subject_result.get('industries'):
                    for i in subject_result['industries']:
                        if i['name'] not in [x.get('name') for x in result['industries']]:
                            result['industries'].append({
                                'name': i['name'],
                                'confidence': i['confidence'],
                                'language': i['language'],
                                'matched_term': i['matched_term'],
                            })

                # Set primary industry if not already set
                if not result['industry'] and subject_result.get('primary_industry'):
                    result['industry'] = subject_result['primary_industry']

            except ImportError:
                logger.debug("SUBJECT detector not available")
        except Exception as e:
            logger.debug(f"SUBJECT detection failed: {e}")

        # 3. PACMAN regex fallback (basic entities)
        if not result['entities']:
            try:
                from modules.JESTER.pacman import extract_async
                entities = await extract_async(html)
                result["entities"] = entities
            except ImportError:
                pass
            except Exception as e:
                logger.debug(f"PACMAN extraction failed: {e}")

        # 4. Identifier extraction (emails, phones, LEI, IBAN, crypto, etc.)
        try:
            import sys
            if "/data/PACMAN" not in sys.path:
                sys.path.insert(0, "/data/PACMAN")
            from patterns import ALL_PATTERNS
            
            identifiers = {}
            for name, pattern in ALL_PATTERNS.items():
                matches = pattern.findall(content[:100000])
                if matches:
                    # Handle tuple results from groups
                    if matches and isinstance(matches[0], tuple):
                        matches = [" ".join(filter(None, m)).strip() for m in matches]
                    # Deduplicate and limit
                    unique = list(set(m for m in matches if m))[:50]
                    if unique:
                        identifiers[name] = unique
            
            if identifiers:
                result["entities"] = identifiers
        except Exception as e:
            logger.debug(f"Identifier extraction failed: {e}")

        # 5. Outlinks extraction (extract all links from HTML)
        if html and url:
            try:
                import sys
                if "/data/SUBMARINE" not in sys.path:
                    sys.path.insert(0, "/data/SUBMARINE")
                from outlink_extractor import extract_outlinks
                all_links = extract_outlinks(html, url, max_links=100)
                result["outlinks"] = all_links
                result["outlinks_external"] = [l for l in all_links if l.get("is_external")]
            except Exception as e:
                logger.debug(f"Outlinks extraction failed: {e}")

        return result

    async def scrape_batch(
        self,
        domains: List[str],
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, int]:
        """
        Scrape domains (homepage only) and stream to sastre.

        Returns stats dict.
        """
        await self.streamer._ensure_index()

        sem = asyncio.Semaphore(self.concurrent)
        stats = {"total": len(domains), "success": 0, "failed": 0, "streamed": 0}

        async def process_one(domain: str, idx: int):
            async with sem:
                doc = await self.scrape_domain(domain)

                if doc.get("content_length", 0) > 0:
                    stats["success"] += 1
                else:
                    stats["failed"] += 1

                # Stream to sastre immediately
                await self.streamer.stream(doc)
                stats["streamed"] += 1

                if progress_callback and idx % 100 == 0:
                    progress_callback(idx, len(domains), stats)

        tasks = [process_one(d, i) for i, d in enumerate(domains)]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Final flush
        await self.streamer.flush()

        return stats

    async def crawl_batch_full(
        self,
        domains: List[str],
        max_pages_per_domain: int = 50,
        max_depth: int = 3,
        max_concurrent_domains: int = 10,
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, int]:
        """
        Crawl FULL domains (multiple pages each) with PACMAN extraction.

        Streams each page to sastre as it's crawled.

        Args:
            domains: List of domains to crawl
            max_pages_per_domain: Max pages to crawl per domain (default 50)
            max_depth: Max crawl depth (default 3)
            max_concurrent_domains: How many domains to crawl at once (default 10)
            progress_callback: Progress callback (domain_idx, total_domains, stats)

        Returns:
            Stats dict with total pages, success, failed
        """
        await self.streamer._ensure_index()

        sem = asyncio.Semaphore(max_concurrent_domains)
        stats = {
            "total_domains": len(domains),
            "domains_done": 0,
            "total_pages": 0,
            "success_pages": 0,
            "failed_domains": 0,
            "entities_extracted": 0,
        }

        async def crawl_one(domain: str, idx: int):
            async with sem:
                try:
                    docs = await self.crawl_domain_full(
                        domain,
                        max_pages=max_pages_per_domain,
                        max_depth=max_depth,
                    )
                    stats["total_pages"] += len(docs)
                    stats["success_pages"] += sum(1 for d in docs if d.get("content_length", 0) > 0)
                    stats["entities_extracted"] += sum(
                        len(d.get("entities", {})) for d in docs
                    )
                except Exception as e:
                    logger.error(f"Crawl failed for {domain}: {e}")
                    stats["failed_domains"] += 1

                stats["domains_done"] += 1

                if progress_callback and stats["domains_done"] % 10 == 0:
                    progress_callback(stats["domains_done"], len(domains), stats)

        tasks = [crawl_one(d, i) for i, d in enumerate(domains)]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Final flush
        await self.streamer.flush()

        return stats

    async def scrape_domain_full(
        self,
        domain: str,
        run_alldom: bool = True,
        alldom_depth: str = "full",
        include_io: bool = True,
    ) -> Dict[str, Any]:
        """
        Scrape a single domain with FULL intelligence extraction.
        
        By DEFAULT runs ALLDOM (unless run_alldom=False):
        - WHOIS, age, GA tracking, tech stack
        - URL mapping, subdomains, sitemaps
        - Backlinks, outlinks analysis
        - Plus standard extraction (persons, companies, identifiers, etc.)
        
        Args:
            domain: Target domain
            run_alldom: If True (default), run full ALLDOM suite
            alldom_depth: "fast" or "full" (default: full)
            
        Returns:
            Combined result with scrape data + ALLDOM intel
        """
        # First do standard scrape with extraction
        result = await self.scrape_domain(domain)
        await self._attach_io(result, include_io=include_io)
        
        # Then run ALLDOM if enabled
        if run_alldom:
            try:
                import sys
                if "/data/ALLDOM" not in sys.path:
                    sys.path.insert(0, "/data/ALLDOM")
                if "/data" not in sys.path:
                    sys.path.insert(0, "/data")
                
                from ALLDOM.alldom import AllDom
                
                ad = AllDom()
                alldom_results = await ad.scan(domain, depth=alldom_depth)
                
                # Merge ALLDOM results into result
                result["alldom"] = {}
                for op, res in alldom_results.items():
                    if res.success:
                        result["alldom"][op] = res.data
                    else:
                        result["alldom"][op] = {"error": res.error}
                
                # Extract specific fields for easier access
                if alldom_results.get("whois:") and alldom_results["whois:"].success:
                    result["whois"] = alldom_results["whois:"].data
                    
                if alldom_results.get("age!") and alldom_results["age!"].success:
                    result["domain_age"] = alldom_results["age!"].data
                    
                if alldom_results.get("tech!") and alldom_results["tech!"].success:
                    result["tech_stack"] = alldom_results["tech!"].data
                    
                if alldom_results.get("bl?") and alldom_results["bl?"].success:
                    result["backlinks"] = alldom_results["bl?"].data
                    
                if alldom_results.get("sub!") and alldom_results["sub!"].success:
                    result["subdomains"] = alldom_results["sub!"].data
                    
                if alldom_results.get("map!") and alldom_results["map!"].success:
                    result["discovered_urls"] = alldom_results["map!"].data
                    
            except ImportError as e:
                logger.debug(f"ALLDOM not available: {e}")
            except Exception as e:
                logger.warning(f"ALLDOM scan failed for {domain}: {e}")
                result["alldom_error"] = str(e)
        
        return result

    async def close(self):
        await self.streamer.close()
        if self._jester:
            await self._jester.close()
        if self._backdrill:
            await self._backdrill.close()
        if self._torpedo_searcher:
            try:
                await self._torpedo_searcher.close()
            except Exception:
                pass


# Backwards-compatible alias used by legacy scripts/tests.
SubmarineScraper = DistributedScraper


def load_domains(path: str, chunk: int = 0, total_chunks: int = 1) -> List[str]:
    """Load domains from file (txt or CSV with 'domain' column), return only this chunk."""
    import csv

    domains = []
    path = Path(path)

    if path.suffix.lower() == '.csv':
        # CSV file - look for 'domain' column
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                domain = row.get('domain') or row.get('Domain') or row.get('DOMAIN')
                if domain:
                    domain = domain.strip()
                    if domain and not domain.startswith('#'):
                        domains.append(domain)
    else:
        # Plain text file - one domain per line
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    domains.append(line)

    # Split into chunks
    if total_chunks > 1:
        chunk_size = len(domains) // total_chunks
        start = chunk * chunk_size
        end = start + chunk_size if chunk < total_chunks - 1 else len(domains)
        return domains[start:end]

    return domains


async def main():
    parser = argparse.ArgumentParser(description="Distributed scraper with sastre streaming")
    parser.add_argument("--domains", required=True, help="Path to domains file (or CSV with 'domain' column)")
    parser.add_argument("--chunk", type=int, default=0, help="Which chunk to process (0-indexed)")
    parser.add_argument("--total-chunks", type=int, default=1, help="Total number of chunks")
    parser.add_argument("--es-host", default=DEFAULT_ES_HOST, help="Elasticsearch host")
    parser.add_argument("--es-port", type=int, default=DEFAULT_ES_PORT, help="Elasticsearch port")
    parser.add_argument("--concurrent", type=int, default=100, help="Concurrent requests (homepage mode)")
    parser.add_argument("--jester-only", action="store_true", help="Only use JESTER (no archives)")
    parser.add_argument("--backdrill-only", action="store_true", help="Only use BACKDRILL (archives)")
    parser.add_argument("--include-io", action="store_true", help="Enrich docs with IO Matrix source metadata (io-matrix)")
    parser.add_argument("--io-index", default=DEFAULT_IO_INDEX, help="IO Matrix index name (default: io-matrix)")
    parser.add_argument("--io-es-host", help="IO Matrix Elasticsearch host (default: --es-host)")
    parser.add_argument("--io-es-port", type=int, help="IO Matrix Elasticsearch port (default: --es-port)")

    # Full domain crawling options
    parser.add_argument("--full-crawl", action="store_true", help="Crawl FULL domains (not just homepage)")
    parser.add_argument("--max-pages", type=int, default=50, help="Max pages per domain (full-crawl mode)")
    parser.add_argument("--max-depth", type=int, default=3, help="Max crawl depth (full-crawl mode)")
    parser.add_argument("--concurrent-domains", type=int, default=10, help="Concurrent domains (full-crawl mode)")

    args = parser.parse_args()

    # Load domains for this chunk
    domains = load_domains(args.domains, args.chunk, args.total_chunks)
    logger.info(f"Loaded {len(domains)} domains (chunk {args.chunk}/{args.total_chunks})")

    # Create scraper
    scraper = DistributedScraper(
        es_host=args.es_host,
        es_port=args.es_port,
        use_jester=not args.backdrill_only,
        use_backdrill=not args.jester_only,
        concurrent=args.concurrent,
        include_io=args.include_io,
        io_index=args.io_index,
        io_es_host=args.io_es_host,
        io_es_port=args.io_es_port,
    )

    start = time.time()

    if args.full_crawl:
        # FULL DOMAIN CRAWL with PACMAN extraction
        logger.info(f"Mode: FULL CRAWL (max {args.max_pages} pages/domain, depth {args.max_depth})")

        def progress_full(done, total, stats):
            pct = done / total * 100
            logger.info(
                f"Progress: {done}/{total} domains ({pct:.1f}%) - "
                f"Pages: {stats['total_pages']}, Entities: {stats['entities_extracted']}"
            )

        stats = await scraper.crawl_batch_full(
            domains,
            max_pages_per_domain=args.max_pages,
            max_depth=args.max_depth,
            max_concurrent_domains=args.concurrent_domains,
            progress_callback=progress_full,
        )

        elapsed = time.time() - start
        logger.info(f"Done in {elapsed:.1f}s")
        logger.info(f"Domains: {stats['domains_done']}/{stats['total_domains']}, Failed: {stats['failed_domains']}")
        logger.info(f"Total pages: {stats['total_pages']}, Success: {stats['success_pages']}")
        logger.info(f"Entities extracted: {stats['entities_extracted']}")
        logger.info(f"Speed: {stats['total_pages']/elapsed:.1f} pages/sec")

    else:
        # HOMEPAGE ONLY mode
        logger.info(f"Mode: HOMEPAGE ONLY (concurrent={args.concurrent})")

        def progress_homepage(idx, total, stats):
            pct = idx / total * 100
            logger.info(f"Progress: {idx}/{total} ({pct:.1f}%) - Success: {stats['success']}, Failed: {stats['failed']}")

        stats = await scraper.scrape_batch(domains, progress_callback=progress_homepage)

        elapsed = time.time() - start
        logger.info(f"Done in {elapsed:.1f}s")
        logger.info(f"Total: {stats['total']}, Success: {stats['success']}, Failed: {stats['failed']}")
        logger.info(f"Speed: {stats['total']/elapsed:.1f} domains/sec")
        logger.info(f"Streamed {stats['streamed']} docs to sastre")

    await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
