"""
CC-First Scraper - Comprehensive Archive Content Source

Multi-source archive scraper with fallback chain:
1. Common Crawl (free, fast, bulk archives)
2. Wayback Machine (free, comprehensive, historical)
3. Firecrawl (paid, live content, final fallback)

Performance optimizations:
- Parallel CC + Wayback racing (first wins for speed)
- LRU caching for repeated domain patterns
- Connection pooling with keep-alive
- Aggressive timeouts with fallback to next source

Expected performance:
- ~85% of URLs found in CC + Wayback combined (free)
- CC/Wayback fetch: 100-300ms vs Firecrawl: 2-5s
- 100 URLs: ~8s with racing vs ~50s with Firecrawl only

Usage:
    scraper = CCFirstScraper(firecrawl_api_key="...")
    content, source = await scraper.get_content("https://example.com")

    # Batch processing with high concurrency
    results = await scraper.batch_scrape(urls, max_concurrent=50)
"""

import os
import asyncio
import aiohttp
import json
import time
from typing import Optional, Tuple, List, Dict, Any
from urllib.parse import quote, urlparse
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv
from collections import OrderedDict

from .warc_parser import WARCParser, html_to_markdown
from .binary_extractor import BinaryTextExtractor

# Centralized CC config
from ..cc_config import CC_INDEX_BASE, CC_DATA_BASE, get_default_archive

# Centralized logging
from ..config import get_logger
logger = get_logger(__name__)

# Entity extraction integration
try:
    from ..enrichment.entity_patterns import EntityExtractor, ExtractedEntity
    ENTITY_EXTRACTOR_AVAILABLE = True
except ImportError:
    ENTITY_EXTRACTOR_AVAILABLE = False
    EntityExtractor = None


class LRUCache:
    """Simple LRU cache for index lookups."""
    def __init__(self, maxsize: int = 2000):
        self.cache: OrderedDict = OrderedDict()
        self.maxsize = maxsize

    def get(self, key: str) -> Optional[Dict]:
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        return None

    def set(self, key: str, value: Dict):
        if key in self.cache:
            self.cache.move_to_end(key)
        else:
            if len(self.cache) >= self.maxsize:
                self.cache.popitem(last=False)
        self.cache[key] = value

# Load environment
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(PROJECT_ROOT / '.env')


@dataclass
class ScrapeResult:
    """Result of a scrape operation."""
    url: str
    content: str
    source: str  # 'cc', 'wayback', 'firecrawl', 'failed'
    timestamp: Optional[str] = None
    status: int = 200
    error: Optional[str] = None
    latency_ms: int = 0
    # Entity extraction results (populated when extract_entities=True)
    entities: Optional[Dict[str, List[Any]]] = None  # companies, persons, dates, etc.


@dataclass
class ScrapeStats:
    """Statistics for scraping session."""
    cc_hits: int = 0
    wayback_hits: int = 0
    firecrawl_hits: int = 0
    failures: int = 0
    cache_hits: int = 0
    total_time: float = 0.0

    @property
    def archive_hit_rate(self) -> float:
        """Combined CC + Wayback hit rate (free sources)."""
        total = self.cc_hits + self.wayback_hits + self.firecrawl_hits + self.failures
        return ((self.cc_hits + self.wayback_hits) / total * 100) if total > 0 else 0.0

    @property
    def total_success_rate(self) -> float:
        """Total success rate across all sources."""
        total = self.cc_hits + self.wayback_hits + self.firecrawl_hits + self.failures
        success = self.cc_hits + self.wayback_hits + self.firecrawl_hits
        return (success / total * 100) if total > 0 else 0.0


class CCFirstScraper:
    """
    Content scraper that tries Common Crawl first, Firecrawl as fallback.

    Benefits:
    - CC is free (no API costs)
    - CC has no rate limits (archived data)
    - CC is faster (~100-300ms vs 2-5s)
    - Historical versions available

    Speed Optimizations:
    - LRU cache for CC index lookups (avoid repeated queries)
    - Connection pooling with keep-alive
    - Aggressive timeouts with quick fallback
    - High concurrency batch processing
    """

    # CC constants now imported from centralized cc_config.py
    # No longer hardcoded here - uses dynamic fetching with caching

    # Shared cache across instances - increased from 5K to 50K for better hit rate
    _index_cache = LRUCache(maxsize=50000)

    def __init__(
        self,
        firecrawl_api_key: Optional[str] = None,
        cc_collection: Optional[str] = None,
        timeout: float = 15.0,  # Faster timeout (was 30)
        index_timeout: float = 5.0,  # Fast index lookup timeout
        convert_to_markdown: bool = True,
        cc_only: bool = False,
        max_connections: int = 100,  # Connection pooling
        extract_binary: bool = True,  # Extract text from PDFs/DOCX/etc
        extract_entities: bool = False,  # Auto-extract entities from scraped content
    ):
        """
        Initialize CC-First scraper.

        Args:
            firecrawl_api_key: API key for Firecrawl fallback. If None, loads from env.
            cc_collection: CC Index collection (e.g., 'CC-MAIN-2025-47')
            timeout: Request timeout in seconds
            index_timeout: Timeout for index lookups (faster)
            convert_to_markdown: Convert HTML to markdown
            cc_only: If True, skip Firecrawl fallback entirely (free CC-only mode)
            max_connections: Max concurrent connections for pooling
            extract_binary: Extract text from binary files (PDF, DOCX, etc)
            extract_entities: Auto-extract entities (companies, persons, etc) from content
        """
        self.firecrawl_key = firecrawl_api_key or os.getenv('FIRECRAWL_API_KEY')
        self.cc_collection = cc_collection or get_default_archive()
        self.cc_index_url = f"{CC_INDEX_BASE}/{self.cc_collection}-index"
        self.timeout = aiohttp.ClientTimeout(total=timeout, connect=5.0)
        self.index_timeout = aiohttp.ClientTimeout(total=index_timeout, connect=3.0)
        self.convert_to_markdown = convert_to_markdown
        self.cc_only = cc_only
        self.extract_binary = extract_binary
        self.stats = ScrapeStats()
        self._session: Optional[aiohttp.ClientSession] = None
        self._connector = aiohttp.TCPConnector(
            limit=max_connections,
            limit_per_host=30,
            keepalive_timeout=30,
            enable_cleanup_closed=True,
        )

        # Initialize binary extractor if enabled
        if self.extract_binary:
            self.binary_extractor = BinaryTextExtractor()
        else:
            self.binary_extractor = None

        # Initialize entity extractor if enabled
        self.extract_entities = extract_entities
        if self.extract_entities and ENTITY_EXTRACTOR_AVAILABLE:
            self.entity_extractor = EntityExtractor()
        else:
            self.entity_extractor = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with connection pooling."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=self.timeout,
                connector=self._connector,
            )
        return self._session

    async def close(self):
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def check_cc_index(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Check if URL exists in Common Crawl Index with caching.

        Args:
            url: URL to check

        Returns:
            Dict with WARC location info if found, None otherwise.
            Keys: filename, offset, length, status, timestamp
        """
        # Check cache first
        cache_key = f"cc:{url}"
        cached = self._index_cache.get(cache_key)
        if cached is not None:
            self.stats.cache_hits += 1
            return cached if cached != '__NOT_FOUND__' else None

        session = await self._get_session()
        encoded_url = quote(url, safe='')
        index_url = f"{self.cc_index_url}?url={encoded_url}&output=json&limit=1"

        try:
            async with session.get(index_url, timeout=self.index_timeout) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    if text.strip():
                        # CDX returns JSONL (one JSON per line)
                        first_line = text.strip().split('\n')[0]
                        result = json.loads(first_line)
                        self._index_cache.set(cache_key, result)
                        return result
                    else:
                        # Cache the miss to avoid repeated lookups
                        self._index_cache.set(cache_key, '__NOT_FOUND__')
        except asyncio.TimeoutError:
            pass  # Quick timeout, fall through to fallback
        except Exception as e:
            pass  # Fail silently, fall through to fallback

        return None

    async def fetch_from_cc(self, location: Dict[str, Any]) -> Optional[str]:
        """
        Fetch content from Common Crawl WARC file using range request.
        Handles both HTML and binary files (PDF, DOCX, etc).

        Args:
            location: Dict from check_cc_index with filename, offset, length

        Returns:
            Text content (HTML/markdown or extracted from binary) or None if fetch fails
        """
        session = await self._get_session()

        warc_url = f"{CC_DATA_BASE}/{location['filename']}"
        offset = int(location['offset'])
        length = int(location['length'])

        headers = {'Range': f'bytes={offset}-{offset + length - 1}'}

        try:
            async with session.get(warc_url, headers=headers) as resp:
                if resp.status in (200, 206):  # 206 = Partial Content
                    raw_data = await resp.read()

                    # First, try to extract binary content and check MIME type
                    binary_content, content_type = WARCParser.extract_binary(raw_data)

                    # Check if it's a binary file that we can extract text from
                    if (
                        binary_content
                        and content_type
                        and self.binary_extractor
                        and self.binary_extractor.can_extract(content_type)
                    ):
                        # Extract text from binary file (PDF, DOCX, etc)
                        result = self.binary_extractor.extract_text(
                            binary_content, content_type
                        )
                        if result.success and result.text:
                            logger.info(f"Extracted {result.char_count} chars from {result.file_type}")
                            return result.text

                    # Fallback to HTML extraction
                    html = WARCParser.extract_html(raw_data)

                    if html:
                        if self.convert_to_markdown:
                            return html_to_markdown(html)
                        return html
        except asyncio.TimeoutError:
            logger.warning("Timeout fetching WARC")
        except Exception as e:
            logger.warning(f"Error fetching WARC: {e}")

        return None

    async def fetch_from_wayback(self, url: str) -> Optional[str]:
        """
        Fetch content from Wayback Machine archives.
        Handles both HTML and binary files (PDF, DOCX, etc).

        Args:
            url: URL to fetch from archives

        Returns:
            Text content (HTML/markdown or extracted from binary) or None if fetch fails
        """
        session = await self._get_session()

        # Try Wayback's availability API to find snapshots
        wayback_api = f"https://archive.org/wayback/available?url={quote(url)}"

        try:
            async with session.get(wayback_api, timeout=self.index_timeout) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    archived_snapshots = data.get('archived_snapshots', {})
                    closest = archived_snapshots.get('closest', {})

                    if closest and closest.get('available'):
                        # Get the archived URL
                        snapshot_url = closest['url']

                        # Modify URL to get raw content (id_ flag prevents Wayback banner injection)
                        if 'id_' not in snapshot_url:
                            snapshot_url = snapshot_url.replace('/web/', '/web/') + 'id_/' if not snapshot_url.endswith('/') else snapshot_url.replace('/web/', '/web/') + 'id_'
                            # Actually, simpler: insert id_ before the URL
                            parts = snapshot_url.split('/')
                            if len(parts) >= 5:  # https://web.archive.org/web/TIMESTAMP/URL
                                # Insert id_ after timestamp
                                parts.insert(5, 'id_')
                                snapshot_url = '/'.join(parts)

                        # Fetch the archived content
                        async with session.get(snapshot_url, timeout=self.timeout) as archive_resp:
                            if archive_resp.status == 200:
                                # Check Content-Type header to see if it's binary
                                content_type = archive_resp.headers.get('Content-Type', '').split(';')[0].strip()

                                # Handle binary files
                                if (
                                    content_type
                                    and self.binary_extractor
                                    and self.binary_extractor.can_extract(content_type)
                                ):
                                    binary_data = await archive_resp.read()
                                    result = self.binary_extractor.extract_text(binary_data, content_type)
                                    if result.success and result.text:
                                        logger.info(f"Wayback: Extracted {result.char_count} chars from {result.file_type}")
                                        return result.text

                                # Handle HTML/text
                                text = await archive_resp.text(errors='ignore')

                                # Remove Wayback toolbar/banner if present
                                if '<!-- BEGIN WAYBACK TOOLBAR INSERT -->' in text:
                                    # Remove toolbar
                                    text = text.split('<!-- END WAYBACK TOOLBAR INSERT -->')[1] if '<!-- END WAYBACK TOOLBAR INSERT -->' in text else text

                                if self.convert_to_markdown:
                                    return html_to_markdown(text)
                                return text

        except asyncio.TimeoutError:
            logger.warning(f"Wayback: Timeout fetching {url}")
        except Exception as e:
            logger.warning(f"Wayback: Error fetching {url}: {e}")

        return None

    async def fetch_from_firecrawl(self, url: str) -> Optional[str]:
        """
        Fallback: Fetch content using Firecrawl API.

        Args:
            url: URL to scrape

        Returns:
            Markdown content or None if fetch fails
        """
        if not self.firecrawl_key:
            logger.warning("No Firecrawl API key configured")
            return None

        session = await self._get_session()

        try:
            async with session.post(
                'https://api.firecrawl.dev/v1/scrape',
                headers={
                    'Authorization': f'Bearer {self.firecrawl_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'url': url,
                    'formats': ['markdown']
                }
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('success'):
                        return data.get('data', {}).get('markdown', '')
                else:
                    error_text = await resp.text()
                    logger.warning(f"Firecrawl error {resp.status}: {error_text[:200]}")
        except asyncio.TimeoutError:
            logger.warning(f"Firecrawl timeout for {url}")
        except Exception as e:
            logger.warning(f"Firecrawl error: {e}")

        return None

    def _extract_entities_from_content(self, content: str) -> Optional[Dict[str, List[Any]]]:
        """
        Extract entities from content if entity extractor is enabled.

        Args:
            content: Text content to extract entities from

        Returns:
            Dict with entity lists by type, or None if extraction disabled/failed
        """
        if not self.entity_extractor or not content:
            return None

        try:
            result = self.entity_extractor.extract_all(content)
            # Convert ExtractedEntity objects to dicts for serialization
            return {
                entity_type: self.entity_extractor.to_dict(entities)
                for entity_type, entities in result.items()
                if entities  # Only include non-empty lists
            }
        except Exception as e:
            logger.warning(f"Entity extraction error: {e}")
            return None

    async def _fetch_cc_full(self, url: str) -> Tuple[Optional[str], Optional[Dict]]:
        """Full CC fetch: index lookup + WARC download. Returns (content, location)."""
        cc_location = await self.check_cc_index(url)
        if cc_location:
            content = await self.fetch_from_cc(cc_location)
            if content:
                return content, cc_location
        return None, None

    async def get_content(self, url: str) -> ScrapeResult:
        """
        Get content for URL using PARALLEL RACING strategy:
        - CC and Wayback start simultaneously
        - First successful response wins
        - Firecrawl as final fallback (paid)

        This is faster than sequential fallback:
        - Sequential: CC timeout (5s) + Wayback fetch = 5-10s for archive miss
        - Parallel: max(CC, Wayback) = 2-5s (whoever wins first)

        Automatically handles binary files (PDF/DOCX/XLSX/PPTX) with text extraction.

        Args:
            url: URL to scrape

        Returns:
            ScrapeResult with content and source indicator ('cc', 'wayback', 'firecrawl', or 'failed')
        """
        start_time = time.time()

        # PARALLEL RACING: Start CC and Wayback simultaneously
        # First successful response wins - no waiting for slow sources
        if not self.cc_only:
            # Create tasks for parallel execution
            cc_task = asyncio.create_task(self._fetch_cc_full(url))
            wayback_task = asyncio.create_task(self.fetch_from_wayback(url))

            # Wait for FIRST to complete successfully
            pending = {cc_task, wayback_task}
            content = None
            source = None
            cc_location = None

            while pending and not content:
                done, pending = await asyncio.wait(
                    pending,
                    return_when=asyncio.FIRST_COMPLETED
                )

                for task in done:
                    try:
                        result = task.result()
                        if task == cc_task:
                            # CC returns (content, location) tuple
                            if result and result[0]:
                                content, cc_location = result
                                source = 'cc'
                        else:
                            # Wayback returns content directly
                            if result:
                                content = result
                                source = 'wayback'
                    except Exception:
                        pass  # Task failed, try next

                # If we got content, cancel pending tasks
                if content:
                    for task in pending:
                        task.cancel()
                    break

            # Return if archive hit
            if content and source:
                if source == 'cc':
                    self.stats.cc_hits += 1
                else:
                    self.stats.wayback_hits += 1

                latency = int((time.time() - start_time) * 1000)
                entities = self._extract_entities_from_content(content)
                return ScrapeResult(
                    url=url,
                    content=content,
                    source=source,
                    timestamp=cc_location.get('timestamp') if cc_location else None,
                    status=int(cc_location.get('status', 200)) if cc_location else 200,
                    latency_ms=latency,
                    entities=entities
                )

            # Fallback to Firecrawl (paid)
            content = await self.fetch_from_firecrawl(url)
            if content:
                self.stats.firecrawl_hits += 1
                latency = int((time.time() - start_time) * 1000)
                entities = self._extract_entities_from_content(content)
                return ScrapeResult(
                    url=url,
                    content=content,
                    source='firecrawl',
                    status=200,
                    latency_ms=latency,
                    entities=entities
                )
            error_msg = 'CC, Wayback, and Firecrawl all failed'

        else:
            # cc_only mode: Sequential CC-only fetch
            cc_location = await self.check_cc_index(url)
            if cc_location:
                content = await self.fetch_from_cc(cc_location)
                if content:
                    self.stats.cc_hits += 1
                    latency = int((time.time() - start_time) * 1000)
                    entities = self._extract_entities_from_content(content)
                    return ScrapeResult(
                        url=url,
                        content=content,
                        source='cc',
                        timestamp=cc_location.get('timestamp'),
                        status=int(cc_location.get('status', 200)),
                        latency_ms=latency,
                        entities=entities
                    )
            error_msg = 'Not found in Common Crawl (cc_only mode)'

        # Failed
        self.stats.failures += 1
        latency = int((time.time() - start_time) * 1000)
        return ScrapeResult(
            url=url,
            content='',
            source='not_in_cc' if self.cc_only else 'failed',
            status=0,
            error=error_msg,
            latency_ms=latency
        )

    async def batch_scrape(
        self,
        urls: List[str],
        max_concurrent: int = 50,  # Increased from 20 for speed
        progress_callback: Optional[callable] = None
    ) -> Dict[str, ScrapeResult]:
        """
        Scrape multiple URLs with CC-first strategy.

        Args:
            urls: List of URLs to scrape
            max_concurrent: Maximum concurrent requests
            progress_callback: Optional callback(completed, total, url, source)

        Returns:
            Dict mapping URL to ScrapeResult
        """
        start_time = time.time()
        semaphore = asyncio.Semaphore(max_concurrent)
        results: Dict[str, ScrapeResult] = {}
        completed = 0

        async def fetch_one(url: str) -> Tuple[str, ScrapeResult]:
            nonlocal completed
            async with semaphore:
                result = await self.get_content(url)
                completed += 1
                if progress_callback:
                    progress_callback(completed, len(urls), url, result.source)
                return url, result

        # Run all fetches concurrently
        tasks = [fetch_one(url) for url in urls]
        task_results = await asyncio.gather(*tasks, return_exceptions=True)

        for item in task_results:
            if isinstance(item, Exception):
                logger.warning(f"Task exception: {item}")
                continue
            url, result = item
            results[url] = result

        self.stats.total_time = time.time() - start_time
        return results

    def get_stats(self) -> Dict[str, Any]:
        """Get scraping statistics."""
        total = self.stats.cc_hits + self.stats.wayback_hits + self.stats.firecrawl_hits + self.stats.failures
        return {
            'cc_hits': self.stats.cc_hits,
            'wayback_hits': self.stats.wayback_hits,
            'firecrawl_hits': self.stats.firecrawl_hits,
            'failures': self.stats.failures,
            'cache_hits': self.stats.cache_hits,
            'archive_hit_rate': f"{self.stats.archive_hit_rate:.1f}%",
            'total_success_rate': f"{self.stats.total_success_rate:.1f}%",
            'total_urls': total,
            'total_time': f"{self.stats.total_time:.2f}s",
            'avg_latency_ms': f"{(self.stats.total_time * 1000 / total):.0f}" if total > 0 else "0",
        }

    def reset_stats(self):
        """Reset statistics."""
        self.stats = ScrapeStats()
        # Note: Don't clear the class-level _index_cache to preserve across resets


# Convenience function for quick scraping
async def scrape_url(url: str, firecrawl_key: Optional[str] = None) -> ScrapeResult:
    """Quick single URL scrape."""
    scraper = CCFirstScraper(firecrawl_api_key=firecrawl_key)
    try:
        return await scraper.get_content(url)
    finally:
        await scraper.close()


async def scrape_urls(urls: List[str], firecrawl_key: Optional[str] = None) -> Dict[str, ScrapeResult]:
    """Quick batch URL scrape."""
    scraper = CCFirstScraper(firecrawl_api_key=firecrawl_key)
    try:
        return await scraper.batch_scrape(urls)
    finally:
        await scraper.close()


async def scrape_with_entities(url: str, firecrawl_key: Optional[str] = None) -> ScrapeResult:
    """
    Scrape URL and automatically extract entities (companies, persons, dates, etc).

    Args:
        url: URL to scrape
        firecrawl_key: Optional Firecrawl API key

    Returns:
        ScrapeResult with entities field populated
    """
    scraper = CCFirstScraper(firecrawl_api_key=firecrawl_key, extract_entities=True)
    try:
        return await scraper.get_content(url)
    finally:
        await scraper.close()


async def scrape_urls_with_entities(
    urls: List[str],
    firecrawl_key: Optional[str] = None,
    max_concurrent: int = 50
) -> Dict[str, ScrapeResult]:
    """
    Batch scrape URLs with automatic entity extraction.

    Args:
        urls: List of URLs to scrape
        firecrawl_key: Optional Firecrawl API key
        max_concurrent: Max concurrent requests

    Returns:
        Dict mapping URL to ScrapeResult with entities populated
    """
    scraper = CCFirstScraper(firecrawl_api_key=firecrawl_key, extract_entities=True)
    try:
        return await scraper.batch_scrape(urls, max_concurrent=max_concurrent)
    finally:
        await scraper.close()


# CLI for testing
if __name__ == '__main__':
    import sys

    async def main():
        if len(sys.argv) < 2:
            print("Usage: python cc_first_scraper.py <url> [url2] [url3] ...")
            print("\nExample:")
            print("  python cc_first_scraper.py https://example.com")
            return

        urls = sys.argv[1:]
        scraper = CCFirstScraper()

        try:
            if len(urls) == 1:
                result = await scraper.get_content(urls[0])
                print(f"\nSource: {result.source}")
                print(f"Status: {result.status}")
                print(f"Timestamp: {result.timestamp}")
                print(f"\nContent ({len(result.content)} chars):")
                print("-" * 50)
                print(result.content[:2000] if result.content else "(empty)")
            else:
                def progress(done, total, url, source):
                    print(f"[{done}/{total}] {source}: {url[:60]}...")

                results = await scraper.batch_scrape(urls, progress_callback=progress)

                print("\n" + "=" * 50)
                print("RESULTS")
                print("=" * 50)
                for url, result in results.items():
                    print(f"\n{result.source.upper()}: {url}")
                    print(f"  Status: {result.status}, Length: {len(result.content)}")

            print("\n" + "=" * 50)
            print("STATS")
            print("=" * 50)
            for k, v in scraper.get_stats().items():
                print(f"  {k}: {v}")

        finally:
            await scraper.close()

    asyncio.run(main())
