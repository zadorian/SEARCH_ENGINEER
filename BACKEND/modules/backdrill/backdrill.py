"""
BACKDRILL - Unified Archive Search Orchestrator

Single entry point for all archive operations:
- CommonCrawl (index, data, WAT)
- Wayback Machine (CDX, content, Save Page Now)
- Memento (40+ archives via TimeMap)
- Elasticsearch (WDC, webgraph, domains, cc_pdfs)
- Paid APIs (Firecrawl cache, Exa time filtering)

Racing: First source to return valid data wins.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class ArchiveSource(Enum):
    """Archive data sources in priority order."""
    COMMONCRAWL_INDEX = "cc_index"
    COMMONCRAWL_DATA = "cc_data"
    COMMONCRAWL_WAT = "cc_wat"
    WAYBACK_CDX = "wb_cdx"
    WAYBACK_DATA = "wb_data"
    MEMENTO = "memento"
    ELASTIC_WDC = "es_wdc"
    ELASTIC_WEBGRAPH = "es_webgraph"
    ELASTIC_DOMAINS = "es_domains"
    ELASTIC_CC_PDFS = "es_cc_pdfs"
    FIRECRAWL_CACHE = "firecrawl"
    EXA_HISTORICAL = "exa"


@dataclass
class BackdrillResult:
    """Result from archive fetch."""
    url: str
    content: Optional[str] = None
    html: Optional[str] = None
    timestamp: Optional[datetime] = None
    source: Optional[ArchiveSource] = None
    status_code: Optional[int] = None
    mime_type: Optional[str] = None
    digest: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.content is not None or self.html is not None


@dataclass
class BackdrillStats:
    """Statistics from a batch operation."""
    total: int = 0
    success: int = 0
    failed: int = 0
    by_source: Dict[str, int] = field(default_factory=dict)
    duration_ms: float = 0


class Backdrill:
    """
    Unified archive search interface.

    Usage:
        bd = Backdrill()

        # Single URL fetch (races all sources)
        result = await bd.fetch("https://example.com")

        # Batch fetch with concurrency
        results = await bd.fetch_batch(urls, concurrent=50)

        # Check existence without fetching content
        exists = await bd.exists("https://example.com")

        # Get all snapshots/timestamps
        snapshots = await bd.list_snapshots("https://example.com")

        # Date-range search
        results = await bd.fetch("https://example.com",
                                 start_date="2020-01-01",
                                 end_date="2023-12-31")
    """

    def __init__(
        self,
        enable_cc: bool = True,
        enable_wayback: bool = True,
        enable_memento: bool = True,
        enable_elastic: bool = True,
        enable_paid: bool = False,  # Opt-in for paid APIs
        es_host: str = "http://localhost:9200",
        firecrawl_max_age_ms: int = 2592000000,  # 30 days
    ):
        self.enable_cc = enable_cc
        self.enable_wayback = enable_wayback
        self.enable_memento = enable_memento
        self.enable_elastic = enable_elastic
        self.enable_paid = enable_paid
        self.es_host = es_host
        self.firecrawl_max_age_ms = firecrawl_max_age_ms

        # Lazy-load submodules
        self._cc = None
        self._wayback = None
        self._memento = None
        self._elastic = None
        self._firecrawl = None
        self._exa = None

    @property
    def cc(self):
        """CommonCrawl Index interface."""
        if self._cc is None:
            from .commoncrawl import CCIndex
            self._cc = CCIndex()
        return self._cc

    @property
    def cc_warc(self):
        """CommonCrawl WARC fetcher (wraps ccwarc_linux)."""
        if not hasattr(self, '_cc_warc') or self._cc_warc is None:
            from .commoncrawl import CCWARCFetcher
            self._cc_warc = CCWARCFetcher()
        return self._cc_warc

    @property
    def cc_links(self):
        """CommonCrawl WAT link extractor (wraps cclinks_linux)."""
        if not hasattr(self, '_cc_links') or self._cc_links is None:
            from .commoncrawl import CCLinksExtractor
            self._cc_links = CCLinksExtractor()
        return self._cc_links

    @property
    def wayback(self):
        """Wayback Machine interface."""
        if self._wayback is None:
            from .wayback import Wayback
            self._wayback = Wayback()
        return self._wayback

    @property
    def memento(self):
        """Memento TimeMap interface (40+ archives)."""
        if self._memento is None:
            from .memento import Memento
            self._memento = Memento()
        return self._memento

    @property
    def elastic(self):
        """Elasticsearch index bridges."""
        if self._elastic is None:
            from .c3_bridge import C3Bridge
            self._elastic = C3Bridge(host=self.es_host)
        return self._elastic

    @property
    def firecrawl(self):
        """Firecrawl cached scraping."""
        if self._firecrawl is None:
            from .paid.firecrawl import FirecrawlCache
            self._firecrawl = FirecrawlCache(max_age_ms=self.firecrawl_max_age_ms)
        return self._firecrawl

    @property
    def exa(self):
        """Exa historical search."""
        if self._exa is None:
            from .paid.exa import ExaHistorical
            self._exa = ExaHistorical()
        return self._exa

    @property
    def optimal(self):
        """High-performance keyword searcher."""
        if not hasattr(self, '_optimal') or self._optimal is None:
            from .optimal_archive import OptimalArchiveSearcher
            self._optimal = OptimalArchiveSearcher()
        return self._optimal

    async def search_keywords_streaming(
        self,
        url: str,
        keywords: Optional[List[str]] = None,
        years: Optional[List[int]] = None,
        direction: str = "backwards",
        return_html: bool = False,
        fast_first: bool = False,
    ):
        """Stream archive search results using OptimalArchiveSearcher."""
        async for result in self.optimal.search_keywords_streaming(
            url=url,
            keywords=keywords,
            years=years,
            direction=direction,
            return_html=return_html,
            fast_first=fast_first,
        ):
            yield result

    async def fetch(
        self,
        url: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        prefer_source: Optional[ArchiveSource] = None,
        timeout: float = 30.0,
    ) -> BackdrillResult:
        """
        Fetch archived content for a URL.

        Races multiple sources, returns first successful result.

        Args:
            url: Target URL
            start_date: Optional date filter (YYYY-MM-DD)
            end_date: Optional date filter (YYYY-MM-DD)
            prefer_source: Skip racing, use specific source
            timeout: Max wait time in seconds

        Returns:
            BackdrillResult with content and metadata
        """
        if prefer_source:
            return await self._fetch_from_source(url, prefer_source, start_date, end_date)

        # Race all enabled sources (wrap as tasks for Python 3.11+)
        tasks = []

        if self.enable_wayback:
            tasks.append(asyncio.create_task(self._fetch_wayback(url, start_date, end_date)))

        if self.enable_cc:
            tasks.append(asyncio.create_task(self._fetch_cc(url, start_date, end_date)))

        if self.enable_memento:
            tasks.append(asyncio.create_task(self._fetch_memento(url, start_date, end_date)))

        if self.enable_paid:
            tasks.append(asyncio.create_task(self._fetch_firecrawl(url)))

        if not tasks:
            return BackdrillResult(url=url)

        # Run all sources in parallel, return first successful
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout
            )

            # Return first successful result
            for result in results:
                if isinstance(result, BackdrillResult) and result.success:
                    return result

        except asyncio.TimeoutError:
            logger.debug(f"Timeout fetching {url}")
        except Exception as e:
            logger.debug(f"Error fetching {url}: {e}")

        return BackdrillResult(url=url)

    async def fetch_batch(
        self,
        urls: List[str],
        concurrent: int = 50,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[BackdrillResult]:
        """
        Fetch multiple URLs concurrently.

        Args:
            urls: List of URLs to fetch
            concurrent: Max concurrent requests
            start_date: Optional date filter
            end_date: Optional date filter

        Returns:
            List of BackdrillResult objects
        """
        semaphore = asyncio.Semaphore(concurrent)

        async def fetch_one(url: str) -> BackdrillResult:
            async with semaphore:
                return await self.fetch(url, start_date, end_date)

        tasks = [fetch_one(url) for url in urls]
        return await asyncio.gather(*tasks)

    async def fetch_batch_cc(
        self,
        domains: List[str],
        threads: int = 50,
        archive: Optional[str] = None,
    ) -> List[BackdrillResult]:
        """
        High-performance batch fetch from CommonCrawl using Go binary.

        Uses ccwarc_linux with 50+ concurrent threads for maximum speed.
        ONLY works on sastre server where Go binary exists.

        Args:
            domains: List of domains to fetch
            threads: Concurrent threads (default 50)
            archive: CC archive to use (default: latest)

        Returns:
            List of BackdrillResult objects with HTML content
        """
        import tempfile
        from pathlib import Path

        if not self.cc_warc.available:
            logger.warning("ccwarc binary not available - falling back to slow fetch")
            return await self.fetch_batch([f"https://{d}" for d in domains])

        results = []

        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "cc_results.ndjson"

            # Use Go binary batch mode (50+ threads)
            raw_results = await self.cc_warc.batch_fetch(
                domains,
                output_file,
                threads=threads,
            )

            for r in raw_results:
                url = r.get('url', '')
                results.append(BackdrillResult(
                    url=url,
                    html=r.get('html'),
                    content=r.get('text'),
                    timestamp=r.get('timestamp'),
                    source=ArchiveSource.COMMONCRAWL_DATA,
                    status_code=int(r.get('status', 200)) if r.get('status') else None,
                    mime_type=r.get('mime'),
                    digest=r.get('digest'),
                ))

        logger.info(f"CC batch fetch: {len(results)}/{len(domains)} domains")
        return results

    async def exists(
        self,
        url: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> bool:
        """
        Check if URL exists in any archive (no content fetch).

        Fast check using index APIs only.
        """
        tasks = []

        if self.enable_wayback:
            tasks.append(self.wayback.exists(url, start_date, end_date))

        if self.enable_cc:
            tasks.append(self.cc.exists(url, start_date, end_date))

        if not tasks:
            return False

        # Return True if any source has it
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return any(r is True for r in results)

    async def list_snapshots(
        self,
        url: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get all available snapshots/timestamps for a URL.

        Returns list of {timestamp, source, url} dicts.
        """
        all_snapshots = []
        tasks = []

        if self.enable_wayback:
            tasks.append(("wayback", self.wayback.list_snapshots(url, start_date, end_date)))

        if self.enable_cc:
            tasks.append(("cc", self.cc.list_snapshots(url, start_date, end_date)))

        if self.enable_memento:
            tasks.append(("memento", self.memento.list_snapshots(url)))

        for source_name, task in tasks:
            try:
                snapshots = await task
                for snap in snapshots:
                    snap["source"] = source_name
                    all_snapshots.append(snap)
            except Exception as e:
                logger.warning(f"Failed to get snapshots from {source_name}: {e}")

        # Sort by timestamp
        all_snapshots.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return all_snapshots

    # -------------------------------------------------------------------------
    # Internal fetch methods
    # -------------------------------------------------------------------------

    async def _fetch_wayback(
        self,
        url: str,
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> BackdrillResult:
        """Fetch from Wayback Machine."""
        try:
            return await self.wayback.fetch(url, start_date, end_date)
        except Exception as e:
            logger.debug(f"Wayback fetch failed for {url}: {e}")
            return BackdrillResult(url=url)

    async def _fetch_cc(
        self,
        url: str,
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> BackdrillResult:
        """Fetch from CommonCrawl using Go binary (ccwarc_linux)."""
        try:
            # Use Go binary for content fetching (50+ threads)
            if self.cc_warc.available:
                result = await self.cc_warc.fetch_single(url)
                if result and result.get('html'):
                    return BackdrillResult(
                        url=url,
                        html=result.get('html'),
                        content=result.get('text'),
                        timestamp=result.get('timestamp'),
                        source=ArchiveSource.COMMONCRAWL_DATA,
                        status_code=int(result.get('status', 200)),
                        mime_type=result.get('mime'),
                        digest=result.get('digest'),
                    )

            # Fallback: Try CC Index lookup + WARC fetch
            records = await self.cc.lookup_url(url, limit=1)
            if not records:
                return BackdrillResult(url=url)

            # TODO: Fetch WARC content from record
            # For now, return metadata only
            record = records[0]
            return BackdrillResult(
                url=url,
                source=ArchiveSource.COMMONCRAWL_INDEX,
                timestamp=record.get('timestamp'),
                status_code=int(record.get('status', 200)) if record.get('status') else None,
                mime_type=record.get('mime'),
                digest=record.get('digest'),
                metadata={'warc_file': record.get('warc_filename')},
            )
        except Exception as e:
            logger.debug(f"CommonCrawl fetch failed for {url}: {e}")
            return BackdrillResult(url=url)

    async def _fetch_memento(
        self,
        url: str,
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> BackdrillResult:
        """Fetch from Memento TimeMap (40+ archives)."""
        try:
            return await self.memento.fetch(url, start_date, end_date)
        except Exception as e:
            logger.debug(f"Memento fetch failed for {url}: {e}")
            return BackdrillResult(url=url)

    async def _fetch_firecrawl(self, url: str) -> BackdrillResult:
        """Fetch from Firecrawl cache."""
        try:
            return await self.firecrawl.fetch(url)
        except Exception as e:
            logger.debug(f"Firecrawl fetch failed for {url}: {e}")
            return BackdrillResult(url=url)

    async def _fetch_from_source(
        self,
        url: str,
        source: ArchiveSource,
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> BackdrillResult:
        """Fetch from a specific source."""
        if source == ArchiveSource.WAYBACK_DATA:
            return await self._fetch_wayback(url, start_date, end_date)
        elif source in (ArchiveSource.COMMONCRAWL_DATA, ArchiveSource.COMMONCRAWL_INDEX):
            return await self._fetch_cc(url, start_date, end_date)
        elif source == ArchiveSource.MEMENTO:
            return await self._fetch_memento(url, start_date, end_date)
        elif source == ArchiveSource.FIRECRAWL_CACHE:
            return await self._fetch_firecrawl(url)
        else:
            return BackdrillResult(url=url)

    # -------------------------------------------------------------------------
    # Elasticsearch index queries
    # -------------------------------------------------------------------------

    async def search_wdc_orgs(self, query: str, limit: int = 100) -> List[Dict]:
        """Search WDC organization entities (9.6M docs, 2023)."""
        return await self.elastic.search_wdc_orgs(query, limit)

    async def search_wdc_persons(self, query: str, limit: int = 100) -> List[Dict]:
        """Search WDC person entities (6.8M docs, 2023)."""
        return await self.elastic.search_wdc_persons(query, limit)

    async def search_webgraph(self, domain: str, limit: int = 100) -> List[Dict]:
        """Search CC web graph edges (421M edges, 2024)."""
        return await self.elastic.search_webgraph(domain, limit)

    async def search_domains(self, query: str, limit: int = 100) -> List[Dict]:
        """Search unified domains index (180M domains)."""
        return await self.elastic.search_domains(query, limit)

    async def search_cc_pdfs(self, query: str, jurisdiction: str = None, limit: int = 100) -> List[Dict]:
        """Search CC PDF collection (67K+ PDFs, 2025)."""
        return await self.elastic.search_cc_pdfs(query, jurisdiction, limit)

    # -------------------------------------------------------------------------
    # Specialized extractors
    # -------------------------------------------------------------------------

    async def extract_ga_codes(self, url: str) -> Dict[str, List[str]]:
        """
        Extract Google Analytics tracking codes from archived content.

        Returns:
            {
                "ua": ["UA-123456-1"],
                "ga4": ["G-XXXXXXX"],
                "gtm": ["GTM-XXXXXX"]
            }
        """
        from .extractors.ga_tracker import extract_ga_codes

        result = await self.fetch(url)
        if not result.success:
            return {"ua": [], "ga4": [], "gtm": []}

        return extract_ga_codes(result.html or result.content)

    async def find_domains_by_ga(self, ga_code: str) -> List[str]:
        """
        Reverse lookup: find all domains using a GA code.

        Searches archived content for domains sharing the same
        UA-XXXXX, G-XXXXXXX, or GTM-XXXXXX code.
        """
        from .extractors.ga_tracker import GATracker
        tracker = GATracker()
        return await tracker.reverse_lookup(ga_code)

    # -------------------------------------------------------------------------
    # Differ tools (timeline, version comparison)
    # -------------------------------------------------------------------------

    async def build_timeline(self, url: str) -> List[Dict]:
        """
        Build a timeline of all archived versions of a URL.

        Returns list of {timestamp, source, changes} dicts.
        """
        from .differ import build_timeline
        return await build_timeline(self, url)

    async def diff_versions(self, url: str, ts1: str, ts2: str) -> Dict:
        """
        Diff two archived versions of a URL.

        Args:
            url: Target URL
            ts1: First timestamp (YYYYMMDDHHMMSS)
            ts2: Second timestamp

        Returns:
            Diff result with added/removed content
        """
        from .differ import diff_versions
        return await diff_versions(self, url, ts1, ts2)

    async def close(self):
        """Clean up resources."""
        if self._cc:
            await self._cc.close()
        if self._wayback:
            await self._wayback.close()
        if self._memento:
            await self._memento.close()
