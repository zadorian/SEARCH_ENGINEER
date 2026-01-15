"""
JESTER MAPPER - Archive Discovery (via BACKDRILL)
==================================================

Discover historical URLs from web archives using BACKDRILL:
    - Wayback Machine CDX API (Internet Archive)
    - Common Crawl Index API
    - Memento TimeMap (40+ archives)

FREE - No API keys required.

SOURCE: Bridge to modules.backdrill (not a reimplementation)

Usage:
    discovery = ArchiveDiscovery()
    async for url in discovery.discover_all("example.com"):
        print(url.url, url.source, url.timestamp)
"""

import asyncio
import logging
from typing import AsyncGenerator, Set, Optional, List

from ..models import DiscoveredURL

logger = logging.getLogger(__name__)

# Import BACKDRILL
try:
    from modules.backdrill import Backdrill
    from modules.backdrill.wayback import Wayback
    from modules.backdrill.commoncrawl import CCIndex
    from modules.backdrill.memento import Memento
    BACKDRILL_AVAILABLE = True
except ImportError:
    BACKDRILL_AVAILABLE = False
    logger.warning("BACKDRILL not available - archive discovery disabled")


class ArchiveDiscovery:
    """
    Web archive-based URL discovery via BACKDRILL.

    Sources (all FREE):
        1. Wayback Machine CDX API - Internet Archive's index
        2. Common Crawl Index API - CC's petabyte-scale archive
        3. Memento TimeMap - 40+ web archives
    """

    def __init__(self):
        self._backdrill: Optional[Backdrill] = None
        self._wayback: Optional[Wayback] = None
        self._cc: Optional[CCIndex] = None
        self._memento: Optional[Memento] = None

    async def _ensure_init(self):
        """Lazy initialization of BACKDRILL clients."""
        if not BACKDRILL_AVAILABLE:
            return

        if self._wayback is None:
            self._wayback = Wayback()
        if self._cc is None:
            self._cc = CCIndex()

    async def close(self):
        """Close connections."""
        if self._wayback:
            await self._wayback.close()
        if self._cc:
            await self._cc.close()
        if self._memento:
            await self._memento.close()

    async def discover_all(
        self,
        domain: str,
        include_memento: bool = False,
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Query all archive sources in parallel.

        Args:
            domain: Domain to search
            include_memento: Include 40+ Memento archives (slower but more comprehensive)

        Yields:
            DiscoveredURL objects with timestamps
        """
        if not BACKDRILL_AVAILABLE:
            logger.error("BACKDRILL not available")
            return

        await self._ensure_init()
        seen: Set[str] = set()

        generators = [
            ("wayback", self.discover_wayback(domain)),
            ("commoncrawl", self.discover_commoncrawl(domain)),
        ]

        if include_memento:
            generators.append(("memento", self.discover_memento(domain)))

        queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()

        async def consume(name: str, gen):
            try:
                async for item in gen:
                    await queue.put(item)
            except Exception as exc:
                logger.error(f"Archive source '{name}' failed: {exc}")
            finally:
                await queue.put(sentinel)

        tasks = [asyncio.create_task(consume(name, gen)) for name, gen in generators]

        completed = 0
        try:
            while completed < len(tasks):
                item = await queue.get()
                if item is sentinel:
                    completed += 1
                    continue
                if item is not None and item.url not in seen:
                    seen.add(item.url)
                    yield item
        finally:
            for task in tasks:
                task.cancel()

        logger.info(f"Archive discovery complete: {len(seen)} unique URLs")

    async def discover_wayback(
        self,
        domain: str,
        limit: int = 10000,
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Query Wayback Machine CDX API via BACKDRILL.

        FREE - No API key required.
        """
        if not BACKDRILL_AVAILABLE or not self._wayback:
            return

        logger.info(f"[wayback] Searching archives for: {domain}")

        try:
            results = await self._wayback.cdx_search(
                url=f"{domain}/*",
                limit=limit,
                collapse="urlkey",
            )

            count = 0
            for r in results:
                count += 1
                archive_url = f"https://web.archive.org/web/{r.get('timestamp')}/{r.get('url')}"

                yield DiscoveredURL(
                    url=r.get("url"),
                    source="wayback",
                    domain=domain,
                    timestamp=r.get("timestamp"),
                    is_archived=True,
                    archive_url=archive_url,
                    archive_source="wayback",
                    status_code=r.get("status_code"),
                    content_type=r.get("mimetype"),
                )

            logger.info(f"[wayback] Found {count} archived URLs")

        except Exception as e:
            logger.error(f"[wayback] Error: {e}")

    async def discover_commoncrawl(
        self,
        domain: str,
        limit: int = 5000,
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Query Common Crawl Index API via BACKDRILL.

        FREE - No API key required.
        """
        if not BACKDRILL_AVAILABLE or not self._cc:
            return

        logger.info(f"[commoncrawl] Searching CC index for: {domain}")

        try:
            results = await self._cc.search(
                url=f"{domain}/*",
                limit=limit,
            )

            count = 0
            for r in results:
                count += 1

                yield DiscoveredURL(
                    url=r.get("url"),
                    source="commoncrawl",
                    domain=domain,
                    timestamp=r.get("timestamp"),
                    is_archived=True,
                    archive_url=None,  # CC doesn't have direct view URLs
                    archive_source="commoncrawl",
                    status_code=r.get("status"),
                    content_type=r.get("mime"),
                )

            logger.info(f"[commoncrawl] Found {count} archived URLs")

        except Exception as e:
            logger.error(f"[commoncrawl] Error: {e}")

    async def discover_memento(
        self,
        domain: str,
        limit: int = 1000,
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Query Memento TimeMap for 40+ web archives via BACKDRILL.

        FREE - No API key required. Slower but most comprehensive.
        """
        if not BACKDRILL_AVAILABLE:
            return

        if self._memento is None:
            self._memento = Memento()

        logger.info(f"[memento] Searching 40+ archives for: {domain}")

        try:
            results = await self._memento.timemap(f"https://{domain}/")

            count = 0
            for r in results[:limit]:
                count += 1

                yield DiscoveredURL(
                    url=r.get("original") or f"https://{domain}/",
                    source="memento",
                    domain=domain,
                    timestamp=r.get("datetime"),
                    is_archived=True,
                    archive_url=r.get("uri"),
                    archive_source=r.get("archive"),
                )

            logger.info(f"[memento] Found {count} archived snapshots")

        except Exception as e:
            logger.error(f"[memento] Error: {e}")
