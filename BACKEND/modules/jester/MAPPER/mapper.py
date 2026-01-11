"""
JESTER MAPPER - Unified Domain URL Discovery (Optimized)
=========================================================

The single source of truth for discovering ALL URLs related to a domain.
Consolidates 17+ discovery methods with high-performance async execution.

Performance Optimizations:
    - Shared httpx client with HTTP/2 multiplexing
    - Connection pooling (100 concurrent, 10 per host)
    - In-memory dedup for small jobs, batch SQLite for large
    - Bounded priority queue (fast sources first)
    - Adaptive rate limiting per API
    - DNS pre-caching

Two Modes:
    THOROUGH (default) - All sources, fast ones stream first
    FAST - Only quick sources (<10s each)

Usage:
    from JESTER.MAPPER import Mapper

    async def example():
        async with Mapper() as mapper:  # Context manager for cleanup

            # THOROUGH (default) - all sources, fast results stream first
            async for url in mapper.map_domain("example.com"):
                print(url.url)

            # FAST - only quick sources
            async for url in mapper.map_domain("example.com", fast=True):
                print(url.url)

Source Categories:
    SUBDOMAINS  - crt.sh, WhoisXML, Sublist3r, DNSDumpster
    FIRECRAWL   - MAP (fast) + CRAWL (deep, 100-parallel)
    SEARCH      - Google, Bing, Brave, DuckDuckGo, Exa (site: queries)
    ARCHIVES    - Wayback CDX, Common Crawl Index
    SITEMAPS    - sitemap.xml parsing
    BACKLINKS   - Majestic, CC WebGraph
    ELASTIC     - Our indexed crawled_pages, io index
"""

import asyncio
import heapq
import logging
import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import AsyncGenerator, Set, List, Optional, Dict, Any, Tuple

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    import aiohttp
    HTTPX_AVAILABLE = False

from urllib.parse import urlparse

from .models import DiscoveredURL, MappingResult
from .config import (
    SOURCE_PRIORITY,
    ALL_SOURCES,
    FAST_SOURCES,
    SLOW_SOURCES,
    THOROUGH_SOURCES,
    FREE_SOURCES,
    TIMEOUTS,
)

# Source modules
from .sources.subdomains import SubdomainDiscovery
from .sources.firecrawl import FirecrawlDiscovery
from .sources.search_engines import SearchEngineDiscovery
from .sources.archives import ArchiveDiscovery
from .sources.sitemaps import SitemapDiscovery
from .sources.backlinks import BacklinkDiscovery
from .sources.elasticsearch_source import ElasticsearchDiscovery

logger = logging.getLogger(__name__)


# =============================================================================
# PRIORITY QUEUE ITEM
# =============================================================================

@dataclass(order=True)
class PriorityItem:
    """Wrapper for priority queue - fast sources (priority=1) processed first."""
    priority: int
    url: DiscoveredURL = field(compare=False)


# =============================================================================
# RESULT CACHE
# =============================================================================

class ResultCache:
    """Cache domain results for 5 minutes to avoid duplicate work."""

    def __init__(self, ttl_seconds: int = 300):
        self._cache: Dict[str, Tuple[datetime, List[DiscoveredURL]]] = {}
        self._ttl = timedelta(seconds=ttl_seconds)

    def get(self, domain: str, fast: bool) -> Optional[List[DiscoveredURL]]:
        key = f"{domain}:{'fast' if fast else 'thorough'}"
        if key in self._cache:
            timestamp, results = self._cache[key]
            if datetime.now() - timestamp < self._ttl:
                logger.info(f"[MAPPER] Cache hit for {domain}")
                return results
            del self._cache[key]
        return None

    def set(self, domain: str, fast: bool, results: List[DiscoveredURL]):
        key = f"{domain}:{'fast' if fast else 'thorough'}"
        self._cache[key] = (datetime.now(), results)


# =============================================================================
# ADAPTIVE RATE LIMITER
# =============================================================================

class AdaptiveRateLimiter:
    """Back off when we see 429s, speed up when successful."""

    def __init__(self, base_delay: float = 0.1, max_delay: float = 10.0):
        self.delays: Dict[str, float] = {}
        self.base_delay = base_delay
        self.max_delay = max_delay

    async def wait(self, source: str):
        delay = self.delays.get(source, self.base_delay)
        if delay > 0.01:
            await asyncio.sleep(delay)

    def success(self, source: str):
        current = self.delays.get(source, self.base_delay)
        self.delays[source] = max(current * 0.9, 0.05)

    def rate_limited(self, source: str):
        current = self.delays.get(source, self.base_delay)
        self.delays[source] = min(current * 2, self.max_delay)
        logger.warning(f"[{source}] Rate limited, backing off to {self.delays[source]:.2f}s")


class Mapper:
    """
    Unified domain URL discovery orchestrator (Optimized).

    Coordinates all discovery sources in parallel with:
    - Shared HTTP client with connection pooling
    - Priority queue for fast-first streaming
    - Adaptive rate limiting
    - In-memory or batch SQLite deduplication
    """

    # Class-level cache shared across instances
    _result_cache = ResultCache()
    _rate_limiter = AdaptiveRateLimiter()

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize the Mapper.

        Args:
            cache_dir: Optional directory for SQLite deduplication cache
        """
        self.cache_dir = cache_dir or Path(tempfile.gettempdir()) / "jester_mapper"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # HTTP client (created lazily)
        self._client: Optional[Any] = None

        # Semaphores for API rate limiting
        self._semaphores = {
            "google": asyncio.Semaphore(2),
            "bing": asyncio.Semaphore(3),
            "brave": asyncio.Semaphore(3),
            "serpapi": asyncio.Semaphore(5),
            "firecrawl": asyncio.Semaphore(5),
            "default": asyncio.Semaphore(10),
        }

        # Initialize source modules (they will receive client later)
        self.subdomain_discovery = SubdomainDiscovery()
        self.firecrawl_discovery = FirecrawlDiscovery()
        self.search_discovery = SearchEngineDiscovery()
        self.archive_discovery = ArchiveDiscovery()
        self.sitemap_discovery = SitemapDiscovery()
        self.backlink_discovery = BacklinkDiscovery()
        self.es_discovery = ElasticsearchDiscovery()

        # Map source names to discovery functions
        self._source_map = {
            # Subdomains
            "crt.sh": self.subdomain_discovery.discover_crtsh,
            "whoisxml": self.subdomain_discovery.discover_whoisxml,
            "sublist3r": self.subdomain_discovery.discover_sublist3r,
            "dnsdumpster": self.subdomain_discovery.discover_dnsdumpster,
            "subdomains": self.subdomain_discovery.discover_all,

            # Firecrawl
            "firecrawl_map": self.firecrawl_discovery.map_domain,
            "firecrawl_crawl": self.firecrawl_discovery.crawl_domain,
            "firecrawl": self.firecrawl_discovery.discover_all,

            # Search engines
            "google": self.search_discovery.discover_google,
            "bing": self.search_discovery.discover_bing,
            "brave": self.search_discovery.discover_brave,
            "duckduckgo": self.search_discovery.discover_duckduckgo,
            "exa": self.search_discovery.discover_exa,
            "search_engines": self.search_discovery.discover_all,

            # Archives
            "wayback": self.archive_discovery.discover_wayback,
            "commoncrawl": self.archive_discovery.discover_commoncrawl,
            "archives": self.archive_discovery.discover_all,

            # Sitemaps
            "sitemap": self.sitemap_discovery.discover_sitemap,
            "sitemaps": self.sitemap_discovery.discover_all,

            # Backlinks (Majestic + CC WebGraph only)
            "majestic": self.backlink_discovery.discover_majestic,
            "cc_webgraph": self.backlink_discovery.discover_cc_webgraph,
            "backlinks": self.backlink_discovery.discover_all,

            # Elasticsearch
            "elasticsearch": self.es_discovery.discover_all,
        }

    async def __aenter__(self):
        """Context manager entry - create HTTP client."""
        await self._get_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close HTTP client."""
        await self.close()

    async def _get_client(self):
        """Get or create the shared HTTP client."""
        if self._client is None:
            if HTTPX_AVAILABLE:
                # httpx with HTTP/2 multiplexing
                self._client = httpx.AsyncClient(
                    http2=True,
                    limits=httpx.Limits(
                        max_connections=100,
                        max_keepalive_connections=50,
                    ),
                    timeout=httpx.Timeout(60.0),
                    follow_redirects=True,
                )
                logger.debug("[MAPPER] Created httpx client with HTTP/2")
            else:
                # Fallback to aiohttp
                connector = aiohttp.TCPConnector(
                    limit=100,
                    limit_per_host=10,
                    ttl_dns_cache=300,
                    keepalive_timeout=30,
                )
                self._client = aiohttp.ClientSession(
                    connector=connector,
                    timeout=aiohttp.ClientTimeout(total=60),
                )
                logger.debug("[MAPPER] Created aiohttp client")
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose() if HTTPX_AVAILABLE else await self._client.close()
            self._client = None

    async def _precache_dns(self):
        """Pre-resolve API hostnames to eliminate DNS latency."""
        hosts = [
            "crt.sh", "api.firecrawl.dev", "serpapi.com",
            "api.search.brave.com", "web.archive.org",
            "index.commoncrawl.org", "api.majestic.com",
        ]
        loop = asyncio.get_event_loop()
        await asyncio.gather(*[
            loop.getaddrinfo(host, 443)
            for host in hosts
        ], return_exceptions=True)

    async def _verify_url_exists(self, url: str, client: Any) -> Tuple[bool, Optional[int]]:
        """
        Check if a URL currently exists (quick HEAD request).

        Returns:
            (exists: bool, status_code: Optional[int])
            - (True, 200) - URL exists
            - (False, 404) - URL doesn't exist
            - (None, None) - Couldn't verify (timeout, error)
        """
        try:
            if HTTPX_AVAILABLE:
                response = await client.head(url, follow_redirects=True, timeout=5.0)
                status = response.status_code
            else:
                async with client.head(url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    status = response.status

            exists = status in (200, 201, 202, 301, 302, 303, 307, 308)
            return exists, status
        except Exception:
            return None, None

    async def _verify_and_filter_url(
        self,
        item: DiscoveredURL,
        client: Any,
        archive_mode: str,
        verify_archives: bool,
    ) -> Optional[DiscoveredURL]:
        """
        Verify URL existence and apply archive_mode filtering.

        Returns:
            - DiscoveredURL (possibly with updated current_exists fields) if it passes filter
            - None if it should be filtered out
        """
        import time

        # Non-archived URLs: always pass through (they're from live sources)
        if not item.is_archived:
            # For current_only mode, non-archived URLs are assumed current
            if archive_mode == "archived_only":
                return None  # archived_only wants only dead URLs
            return item

        # Archived URL - needs verification if enabled
        if verify_archives:
            exists, status = await self._verify_url_exists(item.url, client)
            item.current_exists = exists
            item.current_status = status
            item.current_checked_at = time.time()

        # Apply archive_mode filter
        if archive_mode == "current_only":
            # Only return if URL currently exists
            if item.current_exists is True:
                return item
            elif item.current_exists is None and not verify_archives:
                # If not verifying, assume archived URLs might not exist
                return None
            return None

        elif archive_mode == "archived_only":
            # Only return if URL doesn't exist anymore
            if item.current_exists is False:
                return item
            elif item.current_exists is None:
                # Unknown - include it (conservative for archived_only)
                return item
            return None

        else:  # "both"
            return item

    async def map_domain(
        self,
        domain: str,
        sources: Optional[List[str]] = None,
        fast: bool = False,
        free_only: bool = False,
        include_subdomains: bool = True,
        max_urls: Optional[int] = None,
        archive_mode: str = "both",
        verify_archives: bool = True,
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Discover all URLs for a domain.

        This is the main entry point. It coordinates all discovery sources
        in parallel and yields URLs as they're discovered.

        Args:
            domain: Target domain (e.g., "example.com")
            sources: Specific sources to use (default: all)
            fast: Use only fast sources (<10s each)
            free_only: Use only free sources (no API keys)
            include_subdomains: Also discover subdomains
            max_urls: Stop after this many URLs (default: unlimited)
            archive_mode: "both" (default), "current_only", "archived_only"
                - both: Return all URLs (current + archived)
                - current_only: Only URLs that currently exist (200 OK)
                - archived_only: Only URLs that no longer exist (404/gone)
            verify_archives: Check if archive-discovered URLs currently exist (default: True)
                Even with archive_mode="current_only", archives are used for discovery,
                then verification confirms which URLs still exist.

        Yields:
            DiscoveredURL objects as they're discovered (fast sources first)

        Example:
            async for url in mapper.map_domain("example.com"):
                print(f"{url.source}: {url.url}")

            # Only current pages (but use archives to discover hidden URLs)
            async for url in mapper.map_domain("example.com", archive_mode="current_only"):
                print(f"Live: {url.url}")

            # Only dead pages (historical only)
            async for url in mapper.map_domain("example.com", archive_mode="archived_only"):
                print(f"Dead: {url.url} -> Archive: {url.archive_url}")
        """
        # Normalize domain
        domain = self._normalize_domain(domain)
        logger.info(f"[MAPPER] Starting discovery for: {domain}")

        # Check result cache (5-minute TTL)
        cached = self._result_cache.get(domain, fast)
        if cached:
            logger.info(f"[MAPPER] Returning {len(cached)} cached results")
            for url in cached:
                yield url
            return

        # Determine which sources to use
        if sources:
            active_sources = sources
        elif fast:
            active_sources = FAST_SOURCES
        elif free_only:
            active_sources = FREE_SOURCES
        else:
            active_sources = THOROUGH_SOURCES  # Default: ALL sources

        # Maybe skip subdomains
        if not include_subdomains:
            active_sources = [s for s in active_sources if s not in ["subdomains", "crt.sh", "whoisxml", "sublist3r", "dnsdumpster"]]

        logger.info(f"[MAPPER] Using {len(active_sources)} sources: {active_sources}")

        # Pre-cache DNS for all API hosts
        await self._precache_dns()

        # Ensure we have a client
        client = await self._get_client()

        # In-memory dedup set (fast for typical jobs <50K URLs)
        seen: Set[str] = set()

        # For large jobs, batch SQLite writes
        BATCH_SIZE = 100
        pending_batch: List[str] = []
        db_conn: Optional[sqlite3.Connection] = None

        url_count = 0
        collected_urls: List[DiscoveredURL] = []  # For caching

        try:
            # Create generators for each active source
            generators = []
            for source_name in active_sources:
                if source_name in self._source_map:
                    gen_func = self._source_map[source_name]
                    priority = SOURCE_PRIORITY.get(source_name, 10)
                    # Pass client to source if it accepts it
                    generators.append((source_name, priority, gen_func(domain)))

            if not generators:
                logger.warning("[MAPPER] No valid sources configured")
                return

            # Bounded priority queue - prevents memory explosion
            queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=1000)
            sentinel = object()
            sentinel_priority = 999

            async def consume(name: str, priority: int, gen):
                """Consume a generator and push items to the priority queue."""
                source_count = 0
                try:
                    async for item in gen:
                        if item is not None:
                            # Wrap in PriorityItem for fast-first streaming
                            await queue.put(PriorityItem(priority=priority, url=item))
                            source_count += 1
                            # Adaptive rate limiting
                            self._rate_limiter.success(name)
                except Exception as e:
                    if "429" in str(e) or "rate" in str(e).lower():
                        self._rate_limiter.rate_limited(name)
                    logger.error(f"[MAPPER] Source '{name}' failed: {e}")
                finally:
                    logger.info(f"[MAPPER] Source '{name}' complete: {source_count} URLs")
                    await queue.put(PriorityItem(priority=sentinel_priority, url=sentinel))

            # Start all consumers in parallel
            tasks = [
                asyncio.create_task(consume(name, priority, gen))
                for name, priority, gen in generators
            ]

            # Yield items as they arrive (fast sources first due to priority)
            completed = 0
            try:
                while completed < len(tasks):
                    priority_item = await queue.get()

                    if priority_item.url is sentinel:
                        completed += 1
                        continue

                    item = priority_item.url

                    # Fast in-memory dedup
                    if item.url in seen:
                        continue
                    seen.add(item.url)

                    # Switch to SQLite for large jobs
                    if len(seen) > 10000 and db_conn is None:
                        db_path = self.cache_dir / f"mapper_{domain.replace('.', '_')}.db"
                        db_conn = sqlite3.connect(str(db_path))
                        db_conn.execute("CREATE TABLE IF NOT EXISTS seen_urls (url TEXT PRIMARY KEY)")
                        # Bulk insert existing seen URLs
                        db_conn.executemany(
                            "INSERT OR IGNORE INTO seen_urls (url) VALUES (?)",
                            [(u,) for u in seen]
                        )
                        db_conn.commit()
                        logger.info(f"[MAPPER] Switched to SQLite dedup at {len(seen)} URLs")

                    # Batch SQLite writes (if active)
                    if db_conn is not None:
                        pending_batch.append(item.url)
                        if len(pending_batch) >= BATCH_SIZE:
                            db_conn.executemany(
                                "INSERT OR IGNORE INTO seen_urls (url) VALUES (?)",
                                [(u,) for u in pending_batch]
                            )
                            db_conn.commit()
                            pending_batch.clear()

                    # Verify and filter based on archive_mode
                    filtered_item = await self._verify_and_filter_url(
                        item, client, archive_mode, verify_archives
                    )
                    if filtered_item is None:
                        continue  # Filtered out by archive_mode

                    url_count += 1
                    collected_urls.append(filtered_item)
                    yield filtered_item

                    # Check max_urls limit
                    if max_urls and url_count >= max_urls:
                        logger.info(f"[MAPPER] Reached max_urls limit: {max_urls}")
                        break

            finally:
                # Cancel remaining tasks
                for task in tasks:
                    task.cancel()

                # Flush any pending batch
                if db_conn is not None and pending_batch:
                    db_conn.executemany(
                        "INSERT OR IGNORE INTO seen_urls (url) VALUES (?)",
                        [(u,) for u in pending_batch]
                    )
                    db_conn.commit()

        finally:
            if db_conn is not None:
                db_conn.close()

        # Cache results for 5 minutes
        self._result_cache.set(domain, fast, collected_urls)
        logger.info(f"[MAPPER] Discovery complete: {url_count} unique URLs")

    async def map_domain_with_stats(
        self,
        domain: str,
        sources: Optional[List[str]] = None,
        fast: bool = False,
        free_only: bool = False,
        include_subdomains: bool = True,
        max_urls: Optional[int] = None,
    ) -> MappingResult:
        """
        Discover URLs and return comprehensive statistics.

        Same as map_domain() but collects all results into a MappingResult
        object with statistics about sources used, timing, etc.

        Args:
            domain: Target domain
            sources: Specific sources to use
            fast: Use only fast sources
            free_only: Use only free sources
            include_subdomains: Also discover subdomains
            max_urls: Maximum URLs to return

        Returns:
            MappingResult with urls list and statistics

        Example:
            result = await mapper.map_domain_with_stats("example.com")
            print(f"Found {result.total_urls} URLs in {result.duration_seconds:.1f}s")
            for source, count in result.urls_by_source.items():
                print(f"  {source}: {count}")
        """
        start_time = datetime.now()

        urls: List[DiscoveredURL] = []
        urls_by_source: Dict[str, int] = {}

        async for url in self.map_domain(
            domain=domain,
            sources=sources,
            fast=fast,
            free_only=free_only,
            include_subdomains=include_subdomains,
            max_urls=max_urls,
        ):
            urls.append(url)
            urls_by_source[url.source] = urls_by_source.get(url.source, 0) + 1

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        return MappingResult(
            domain=domain,
            urls=urls,
            total_urls=len(urls),
            sources_used=list(urls_by_source.keys()),
            urls_by_source=urls_by_source,
            started_at=start_time,
            completed_at=end_time,
            duration_seconds=duration,
        )

    async def discover_subdomains(
        self,
        domain: str,
        sources: Optional[List[str]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Discover only subdomains (not full URLs).

        Args:
            domain: Target domain
            sources: Subdomain sources to use

        Yields:
            Subdomain strings (e.g., "api.example.com")
        """
        subdomain_sources = sources or ["crtsh", "whoisxml", "sublist3r", "dnsdumpster"]
        seen: Set[str] = set()

        async for url in self.map_domain(domain, sources=subdomain_sources):
            subdomain = url.subdomain or self._extract_subdomain(url.url, domain)
            if subdomain and subdomain not in seen:
                seen.add(subdomain)
                yield subdomain

    async def quick_map(
        self,
        domain: str,
        timeout: int = 30,
    ) -> List[DiscoveredURL]:
        """
        Quick mapping with timeout.

        Returns whatever URLs are discovered within the timeout.

        Args:
            domain: Target domain
            timeout: Maximum seconds to wait

        Returns:
            List of discovered URLs
        """
        urls: List[DiscoveredURL] = []

        async def collect():
            async for url in self.map_domain(domain, fast=True):
                urls.append(url)

        try:
            await asyncio.wait_for(collect(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.info(f"[MAPPER] Quick map timeout after {timeout}s, returning {len(urls)} URLs")

        return urls

    def _normalize_domain(self, domain: str) -> str:
        """
        Normalize a domain string.

        Handles:
            - URLs (extracts domain)
            - Protocol prefixes
            - Trailing slashes
            - www prefix (optional removal)

        Args:
            domain: Input domain or URL

        Returns:
            Normalized domain string
        """
        # Handle full URLs
        if "://" in domain:
            parsed = urlparse(domain)
            domain = parsed.netloc or parsed.path

        # Remove protocol if present without ://
        for prefix in ["http:", "https:", "//"]:
            if domain.startswith(prefix):
                domain = domain[len(prefix):]

        # Remove trailing slash and path
        domain = domain.split("/")[0]

        # Remove port
        domain = domain.split(":")[0]

        # Lowercase
        domain = domain.lower().strip()

        return domain

    def _extract_subdomain(self, url: str, base_domain: str) -> Optional[str]:
        """
        Extract subdomain from a URL.

        Args:
            url: Full URL
            base_domain: Base domain

        Returns:
            Subdomain or None
        """
        try:
            parsed = urlparse(url)
            host = parsed.netloc or parsed.path.split("/")[0]
            host = host.split(":")[0].lower()

            if host == base_domain:
                return None

            if host.endswith(f".{base_domain}"):
                return host

            return None
        except Exception:
            return None

    @staticmethod
    def get_available_sources() -> Dict[str, List[str]]:
        """
        Get list of available sources by category.

        Returns:
            Dict mapping category names to source lists
        """
        return {
            "subdomains": ["crtsh", "whoisxml", "sublist3r", "dnsdumpster"],
            "firecrawl": ["firecrawl_map", "firecrawl_crawl"],
            "search_engines": ["google", "bing", "brave", "duckduckgo", "exa"],
            "archives": ["wayback", "commoncrawl"],
            "sitemaps": ["sitemap"],
            "backlinks": ["majestic", "cc_webgraph"],
            "elasticsearch": ["elasticsearch"],
        }

    @staticmethod
    def get_source_info(source: str) -> Dict[str, Any]:
        """
        Get information about a specific source.

        Args:
            source: Source name

        Returns:
            Dict with source metadata
        """
        source_info = {
            "crtsh": {
                "name": "Certificate Transparency (crt.sh)",
                "type": "subdomain",
                "cost": "free",
                "speed": "fast",
                "description": "Finds subdomains from SSL certificate logs",
            },
            "whoisxml": {
                "name": "WhoisXML API",
                "type": "subdomain",
                "cost": "paid",
                "speed": "fast",
                "description": "Commercial subdomain enumeration API",
            },
            "sublist3r": {
                "name": "Sublist3r",
                "type": "subdomain",
                "cost": "free",
                "speed": "medium",
                "description": "Multi-source subdomain aggregator",
            },
            "firecrawl_map": {
                "name": "Firecrawl MAP",
                "type": "crawl",
                "cost": "paid",
                "speed": "fast",
                "description": "Fast site mapping, up to 100K URLs",
            },
            "firecrawl_crawl": {
                "name": "Firecrawl CRAWL",
                "type": "crawl",
                "cost": "paid",
                "speed": "slow",
                "description": "Deep 100-parallel recursive crawl",
            },
            "wayback": {
                "name": "Wayback Machine CDX",
                "type": "archive",
                "cost": "free",
                "speed": "medium",
                "description": "Internet Archive's historical URL index",
            },
            "commoncrawl": {
                "name": "Common Crawl Index",
                "type": "archive",
                "cost": "free",
                "speed": "slow",
                "description": "Petabyte-scale web archive index",
            },
            "google": {
                "name": "Google Custom Search",
                "type": "search",
                "cost": "limited_free",
                "speed": "fast",
                "description": "Google-indexed pages via site: query",
            },
            "bing": {
                "name": "Bing Search API",
                "type": "search",
                "cost": "limited_free",
                "speed": "fast",
                "description": "Bing-indexed pages via site: query",
            },
            "brave": {
                "name": "Brave Search API",
                "type": "search",
                "cost": "limited_free",
                "speed": "fast",
                "description": "Brave-indexed pages via site: query",
            },
            "majestic": {
                "name": "Majestic",
                "type": "backlink",
                "cost": "paid",
                "speed": "fast",
                "description": "Backlinks with Trust/Citation Flow metrics",
            },
            "cc_webgraph": {
                "name": "CC WebGraph (ES)",
                "type": "backlink",
                "cost": "free",
                "speed": "fast",
                "description": "90M domains, 166M edges in local ES",
            },
            "sitemap": {
                "name": "Sitemap Parser",
                "type": "sitemap",
                "cost": "free",
                "speed": "fast",
                "description": "Parse sitemap.xml and robots.txt",
            },
            "elasticsearch": {
                "name": "Local Elasticsearch",
                "type": "elasticsearch",
                "cost": "free",
                "speed": "fast",
                "description": "Query our indexed crawled pages",
            },
        }
        return source_info.get(source, {"name": source, "type": "unknown"})


# Convenience function for quick usage
async def map_domain(
    domain: str,
    fast: bool = False,
    free_only: bool = False,
) -> AsyncGenerator[DiscoveredURL, None]:
    """
    Quick function to map a domain.

    Usage:
        from JESTER.MAPPER import map_domain

        async for url in map_domain("example.com"):
            print(url.url)
    """
    mapper = Mapper()
    async for url in mapper.map_domain(domain, fast=fast, free_only=free_only):
        yield url
