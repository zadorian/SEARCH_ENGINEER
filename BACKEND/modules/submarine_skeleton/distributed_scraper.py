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
from urllib.parse import quote_plus

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
            from modules.JESTER import Jester
            self._jester = Jester()
        return self._jester

    async def _get_backdrill(self):
        if self._backdrill is None and self.use_backdrill:
            from modules.BACKDRILL import Backdrill
            self._backdrill = Backdrill(
                enable_cc=True,
                enable_wayback=True,
                enable_memento=False,
            )
        return self._backdrill

    def _normalize_domain(self, value: str) -> str:
        if not value:
            return ""
        value = value.strip().lower()
        value = value.replace("https://", "").replace("http://", "")
        value = value.split("/")[0]
        return value

    async def _io_lookup_source(self, domain: str) -> Optional[Dict[str, Any]]:
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
    ) -> Dict[str, Any]:
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

        return {
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

    async def scrape_domain(self, domain: str) -> Dict[str, Any]:
        """Scrape a single domain, return doc for ES."""
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
                jr = await jester.scrape(url)
                if jr.html and len(jr.html) > 100:
                    result.update({
                        "html": jr.html,
                        "text": jr.text,
                        "title": jr.title,
                        "source": f"jester_{jr.method.value}",
                        "content_length": len(jr.html),
                        "status_code": jr.status_code,
                        "entities": jr.entities or {},
                    })
                    await self._attach_io(result, include_io=self.include_io)
                    return result
            except Exception as e:
                logger.debug(f"JESTER failed for {domain}: {e}")

        # Fallback to BACKDRILL (archives)
        if self.use_backdrill:
            try:
                bd = await self._get_backdrill()
                br = await bd.fetch(url)
                if br.success:
                    result.update({
                        "html": br.html,
                        "text": br.content,
                        "source": br.source.value if br.source else "backdrill",
                        "content_length": len(br.html) if br.html else 0,
                        "status_code": br.status_code,
                        "timestamp": br.timestamp.isoformat() if br.timestamp else None,
                    })
                    await self._attach_io(result, include_io=self.include_io)
                    return result
            except Exception as e:
                logger.debug(f"BACKDRILL failed for {domain}: {e}")

        # Failed
        result["source"] = "failed"
        result["content_length"] = 0
        await self._attach_io(result, include_io=self.include_io)
        return result

    async def scrape_batch(
        self,
        domains: List[str],
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, int]:
        """
        Scrape domains and stream to sastre.

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


def load_domains(path: str, chunk: int = 0, total_chunks: int = 1) -> List[str]:
    """Load domains from file, return only this chunk."""
    domains = []
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                domains.append(line)

    # Split into chunks
    chunk_size = len(domains) // total_chunks
    start = chunk * chunk_size
    end = start + chunk_size if chunk < total_chunks - 1 else len(domains)

    return domains[start:end]


async def main():
    parser = argparse.ArgumentParser(description="Distributed scraper with sastre streaming")
    parser.add_argument("--domains", required=True, help="Path to domains file")
    parser.add_argument("--chunk", type=int, default=0, help="Which chunk to process (0-indexed)")
    parser.add_argument("--total-chunks", type=int, default=1, help="Total number of chunks")
    parser.add_argument("--es-host", default=DEFAULT_ES_HOST, help="Elasticsearch host")
    parser.add_argument("--es-port", type=int, default=DEFAULT_ES_PORT, help="Elasticsearch port")
    parser.add_argument("--concurrent", type=int, default=100, help="Concurrent requests")
    parser.add_argument("--jester-only", action="store_true", help="Only use JESTER (no archives)")
    parser.add_argument("--backdrill-only", action="store_true", help="Only use BACKDRILL (archives)")
    parser.add_argument("--include-io", action="store_true", help="Enrich docs with IO Matrix source metadata (io-matrix)")
    parser.add_argument("--io-index", default=DEFAULT_IO_INDEX, help="IO Matrix index name (default: io-matrix)")
    parser.add_argument("--io-es-host", help="IO Matrix Elasticsearch host (default: --es-host)")
    parser.add_argument("--io-es-port", type=int, help="IO Matrix Elasticsearch port (default: --es-port)")
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

    def progress(idx, total, stats):
        pct = idx / total * 100
        logger.info(f"Progress: {idx}/{total} ({pct:.1f}%) - Success: {stats['success']}, Failed: {stats['failed']}")

    # Run
    start = time.time()
    stats = await scraper.scrape_batch(domains, progress_callback=progress)
    elapsed = time.time() - start

    logger.info(f"Done in {elapsed:.1f}s")
    logger.info(f"Total: {stats['total']}, Success: {stats['success']}, Failed: {stats['failed']}")
    logger.info(f"Speed: {stats['total']/elapsed:.1f} domains/sec")
    logger.info(f"Streamed {stats['streamed']} docs to sastre")

    await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
