"""
JESTER MAPPER - Linklater Archive Bridge
=========================================

Bridges MAPPER to Linklater's production-ready archive intelligence.

Instead of reimplementing CC Index queries, this module uses Linklater's
battle-tested CCIndexClient with:
    - 1-hour cache for CC index list (class-level)
    - Semaphore-based concurrency control
    - Proper error handling and retry logic

Usage:
    bridge = LinklaterArchiveBridge()
    async for url in bridge.discover_commoncrawl("example.com"):
        print(url.url, url.timestamp)
"""

import asyncio
import time
import logging
from typing import AsyncGenerator, Optional, Set, List

from ..models import DiscoveredURL

# Import Linklater's CC Index client
from BACKEND.modules.LINKLATER.archives.cc_index_client import CCIndexClient, CCIndexRecord

logger = logging.getLogger(__name__)


class LinklaterArchiveBridge:
    """
    Bridge between Linklater archive tools and MAPPER URL discovery.

    Features:
        - Uses CCIndexClient for multi-index CC queries
        - 1-hour cache for CC index list (class-level, shared)
        - Semaphore-based concurrency control
        - Converts CCIndexRecord → DiscoveredURL
    """

    # Class-level cache (shared across all instances)
    _index_cache: Optional[List[dict]] = None
    _index_cache_time: float = 0.0
    _CACHE_TTL: int = 3600  # 1 hour

    def __init__(
        self,
        max_indexes: int = 50,         # Query 50 indexes to cover 2+ years
        max_concurrent: int = 5,       # 5 concurrent index queries
        limit_per_index: int = 200,    # URLs per index
    ):
        """
        Initialize the Linklater bridge.

        Args:
            max_indexes: How many CC indexes to query (most recent first)
            max_concurrent: Max parallel index queries
            limit_per_index: Max URLs to retrieve from each index
        """
        self.max_indexes = max_indexes
        self.max_concurrent = max_concurrent
        self.limit_per_index = limit_per_index
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def discover_commoncrawl(
        self,
        domain: str,
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Discover URLs from Common Crawl using Linklater's CCIndexClient.

        Args:
            domain: Domain to search (e.g., "example.com")

        Yields:
            DiscoveredURL objects with archive metadata
        """
        logger.info(f"[linklater-cc] Starting CC discovery for: {domain}")

        # Get cached index list
        indexes = await self._get_cached_indexes()
        if not indexes:
            logger.error("[linklater-cc] Failed to get CC indexes")
            return

        # Take most recent indexes
        indexes_to_query = indexes[:self.max_indexes]
        logger.info(f"[linklater-cc] Querying {len(indexes_to_query)} indexes")

        seen: Set[str] = set()
        total_found = 0

        async def query_index(idx_info: dict) -> List[CCIndexRecord]:
            """Query single index with semaphore limit."""
            idx_id = idx_info.get("id", "unknown")
            async with self._semaphore:
                client = None
                try:
                    client = CCIndexClient(timeout=60)
                    # Use query_url() with wildcard pattern and match_type='exact'
                    # NOTE: matchType=domain breaks wildcards! Use 'exact' for wildcards.
                    url_pattern = f"*.{domain}/*"
                    records = await client.query_url(
                        url=url_pattern,
                        archive=idx_id,
                        match_type='exact',  # 'exact' means don't add matchType param
                        filter_status=[200, 301, 302],  # Valid responses
                        limit=self.limit_per_index
                    )
                    if records:
                        logger.debug(f"[linklater-cc] {idx_id}: {len(records)} URLs")
                    return records
                except Exception as e:
                    # 404 = no captures (normal), other errors logged at debug
                    error_str = str(e)
                    if "404" not in error_str:
                        logger.debug(f"[linklater-cc] {idx_id} error: {e}")
                    return []
                finally:
                    if client:
                        await client.close()

        # Query indexes in batches (double semaphore size for queue depth)
        batch_size = self.max_concurrent * 2
        for i in range(0, len(indexes_to_query), batch_size):
            batch = indexes_to_query[i:i + batch_size]
            tasks = [query_index(idx) for idx in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for idx_info, result in zip(batch, results):
                if isinstance(result, Exception):
                    continue

                idx_id = idx_info.get("id", "unknown")
                for record in result:
                    if record.url not in seen:
                        seen.add(record.url)
                        total_found += 1
                        yield self._convert_record(record, domain, idx_id)

        logger.info(f"[linklater-cc] Complete: {total_found} URLs from {len(indexes_to_query)} indexes")

    async def _get_cached_indexes(self) -> List[dict]:
        """
        Get CC index list with 1-hour caching.

        Cache is class-level, so it's shared across all instances.
        """
        now = time.time()
        cls = LinklaterArchiveBridge

        # Check cache
        if cls._index_cache and (now - cls._index_cache_time) < self._CACHE_TTL:
            logger.debug(f"[linklater-cc] Using cached index list ({len(cls._index_cache)} indexes)")
            return cls._index_cache

        # Fetch fresh
        try:
            client = CCIndexClient(timeout=30)
            try:
                indexes = await client.list_available_archives()
                if indexes:
                    cls._index_cache = indexes
                    cls._index_cache_time = now
                    logger.info(f"[linklater-cc] Cached {len(indexes)} CC indexes (1-hour TTL)")
                    return indexes
            finally:
                await client.close()
        except Exception as e:
            logger.error(f"[linklater-cc] Failed to fetch indexes: {e}")

        # Return stale cache if available
        if cls._index_cache:
            logger.warning("[linklater-cc] Using stale cache due to fetch failure")
            return cls._index_cache

        return []

    def _convert_record(
        self,
        record: CCIndexRecord,
        domain: str,
        archive_id: str
    ) -> DiscoveredURL:
        """
        Convert Linklater CCIndexRecord to MAPPER DiscoveredURL.

        Args:
            record: CC Index record from Linklater
            domain: Original domain queried
            archive_id: CC archive ID (e.g., "CC-MAIN-2024-10")

        Returns:
            DiscoveredURL with archive metadata populated
        """
        # Build Wayback-style view URL
        archive_url = None
        if record.timestamp:
            archive_url = f"https://web.archive.org/web/{record.timestamp}/{record.url}"

        return DiscoveredURL(
            url=record.url,
            source="commoncrawl",
            domain=domain,
            timestamp=record.timestamp,
            is_archived=True,
            archive_url=archive_url,
            archive_source=f"commoncrawl:{archive_id}",
            status_code=record.status if record.status else None,
            content_type=record.mime,
        )


# Convenience function for direct usage
async def discover_cc_urls(domain: str, max_indexes: int = 30) -> AsyncGenerator[DiscoveredURL, None]:
    """
    Convenience function to discover CC URLs.

    Usage:
        async for url in discover_cc_urls("example.com"):
            print(url.url)
    """
    bridge = LinklaterArchiveBridge(max_indexes=max_indexes)
    async for url in bridge.discover_commoncrawl(domain):
        yield url
