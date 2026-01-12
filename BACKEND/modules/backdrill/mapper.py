"""
BACKDRILL Mapper - Unified URL discovery for domains via archive sources.

Maps all URLs belonging to a domain across:
- Wayback Machine CDX API
- CommonCrawl Index API
- Memento TimeMap (40+ archives)

Usage:
    from modules.backdrill.mapper import BackdrillMapper

    mapper = BackdrillMapper()

    # Get all archived URLs for a domain
    urls = await mapper.map_domain("example.com")

    # Get URLs with filters
    urls = await mapper.map_domain(
        "example.com",
        start_date="2020-01-01",
        end_date="2024-12-31",
        mime_filter="text/html",
    )

    # Stream results as they arrive
    async for url in mapper.map_domain_stream("example.com"):
        print(url.url, url.source, url.timestamp)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, AsyncGenerator, Set
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class MappedURL:
    """A URL discovered from archives."""
    url: str
    domain: str
    source: str  # wayback, commoncrawl, memento
    timestamp: Optional[str] = None
    status_code: Optional[int] = None
    mime_type: Optional[str] = None
    content_length: Optional[int] = None
    digest: Optional[str] = None

    # Archive-specific
    archive_url: Optional[str] = None  # Direct link to archived version
    warc_file: Optional[str] = None  # CommonCrawl WARC location
    archive_name: Optional[str] = None  # Memento archive name

    # Metadata
    discovered_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class DomainMap:
    """Complete URL map for a domain."""
    domain: str
    urls: List[MappedURL]

    # Stats
    total_urls: int = 0
    unique_urls: int = 0
    by_source: Dict[str, int] = field(default_factory=dict)
    by_year: Dict[str, int] = field(default_factory=dict)

    # Date range
    earliest: Optional[str] = None
    latest: Optional[str] = None

    # Timing
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None


class BackdrillMapper:
    """
    Unified URL mapper using archive sources.

    Discovers all archived URLs for a domain by querying:
    1. Wayback Machine CDX API (fastest, most comprehensive for recent)
    2. CommonCrawl Index API (massive historical coverage)
    3. Memento TimeMap (40+ archives, optional)
    """

    def __init__(
        self,
        enable_wayback: bool = True,
        enable_commoncrawl: bool = True,
        enable_memento: bool = False,  # Off by default (slow)
    ):
        self.enable_wayback = enable_wayback
        self.enable_commoncrawl = enable_commoncrawl
        self.enable_memento = enable_memento

        # Lazy-loaded clients
        self._wayback = None
        self._cc = None
        self._memento = None

    async def _ensure_clients(self):
        """Lazy-load archive clients."""
        if self.enable_wayback and self._wayback is None:
            from .wayback import Wayback
            self._wayback = Wayback()

        if self.enable_commoncrawl and self._cc is None:
            from .commoncrawl import CCIndex
            self._cc = CCIndex()

        if self.enable_memento and self._memento is None:
            from .memento import Memento
            self._memento = Memento()

    async def close(self):
        """Close all clients."""
        if self._wayback:
            await self._wayback.close()
        if self._cc:
            await self._cc.close()
        if self._memento:
            await self._memento.close()

    async def __aenter__(self):
        await self._ensure_clients()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def _normalize_domain(self, domain: str) -> str:
        """Normalize domain for querying."""
        domain = domain.lower().strip()
        domain = domain.lstrip("www.")
        # Remove protocol if present
        if "://" in domain:
            domain = urlparse(domain).netloc
        return domain

    async def map_domain(
        self,
        domain: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        mime_filter: Optional[str] = None,
        status_filter: Optional[int] = 200,
        limit_per_source: int = 10000,
        dedupe: bool = True,
    ) -> DomainMap:
        """
        Map all URLs for a domain from archive sources.

        Args:
            domain: Target domain (e.g., "example.com")
            start_date: Optional start date (YYYY-MM-DD)
            end_date: Optional end date (YYYY-MM-DD)
            mime_filter: Filter by MIME type (e.g., "text/html")
            status_filter: Filter by HTTP status (default: 200)
            limit_per_source: Max URLs per source
            dedupe: Deduplicate URLs across sources

        Returns:
            DomainMap with all discovered URLs
        """
        await self._ensure_clients()
        domain = self._normalize_domain(domain)

        start_time = datetime.utcnow()
        all_urls: List[MappedURL] = []
        seen_urls: Set[str] = set()
        by_source: Dict[str, int] = {}
        by_year: Dict[str, int] = {}

        # Run all sources in parallel
        tasks = []

        if self.enable_wayback and self._wayback:
            tasks.append(self._map_wayback(
                domain, start_date, end_date, mime_filter, status_filter, limit_per_source
            ))

        if self.enable_commoncrawl and self._cc:
            tasks.append(self._map_commoncrawl(
                domain, start_date, end_date, mime_filter, status_filter, limit_per_source
            ))

        if self.enable_memento and self._memento:
            tasks.append(self._map_memento(domain, limit_per_source))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Combine results
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Source error: {result}")
                continue

            for url in result:
                # Dedupe
                if dedupe and url.url in seen_urls:
                    continue
                seen_urls.add(url.url)

                all_urls.append(url)

                # Stats
                by_source[url.source] = by_source.get(url.source, 0) + 1

                if url.timestamp:
                    year = url.timestamp[:4] if len(url.timestamp) >= 4 else "unknown"
                    by_year[year] = by_year.get(year, 0) + 1

        # Build result
        end_time = datetime.utcnow()

        # Find date range
        timestamps = [u.timestamp for u in all_urls if u.timestamp]
        earliest = min(timestamps) if timestamps else None
        latest = max(timestamps) if timestamps else None

        return DomainMap(
            domain=domain,
            urls=all_urls,
            total_urls=len(all_urls),
            unique_urls=len(seen_urls),
            by_source=by_source,
            by_year=dict(sorted(by_year.items())),
            earliest=earliest,
            latest=latest,
            started_at=start_time.isoformat(),
            completed_at=end_time.isoformat(),
            duration_ms=int((end_time - start_time).total_seconds() * 1000),
        )

    async def map_domain_stream(
        self,
        domain: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        mime_filter: Optional[str] = None,
        status_filter: Optional[int] = 200,
        limit_per_source: int = 10000,
        dedupe: bool = True,
    ) -> AsyncGenerator[MappedURL, None]:
        """
        Stream URLs as they're discovered from archive sources.

        Yields results as each source returns them (parallel streaming).
        """
        await self._ensure_clients()
        domain = self._normalize_domain(domain)
        seen_urls: Set[str] = set()

        # Create async generators for each source
        generators = []

        if self.enable_wayback and self._wayback:
            generators.append(("wayback", self._stream_wayback(
                domain, start_date, end_date, mime_filter, status_filter, limit_per_source
            )))

        if self.enable_commoncrawl and self._cc:
            generators.append(("commoncrawl", self._stream_commoncrawl(
                domain, start_date, end_date, mime_filter, status_filter, limit_per_source
            )))

        if self.enable_memento and self._memento:
            generators.append(("memento", self._stream_memento(domain, limit_per_source)))

        # Merge streams
        queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()

        async def consume(name: str, gen):
            try:
                async for url in gen:
                    await queue.put(url)
            except Exception as e:
                logger.error(f"Stream error from {name}: {e}")
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

                if dedupe:
                    if item.url in seen_urls:
                        continue
                    seen_urls.add(item.url)

                yield item
        finally:
            for task in tasks:
                task.cancel()

    # -------------------------------------------------------------------------
    # Source-specific mappers
    # -------------------------------------------------------------------------

    async def _map_wayback(
        self,
        domain: str,
        start_date: Optional[str],
        end_date: Optional[str],
        mime_filter: Optional[str],
        status_filter: Optional[int],
        limit: int,
    ) -> List[MappedURL]:
        """Map URLs from Wayback Machine CDX API."""
        urls = []
        async for url in self._stream_wayback(
            domain, start_date, end_date, mime_filter, status_filter, limit
        ):
            urls.append(url)
        return urls

    async def _stream_wayback(
        self,
        domain: str,
        start_date: Optional[str],
        end_date: Optional[str],
        mime_filter: Optional[str],
        status_filter: Optional[int],
        limit: int,
    ) -> AsyncGenerator[MappedURL, None]:
        """Stream URLs from Wayback Machine."""
        try:
            results = await self._wayback.cdx_search(
                url=f"{domain}/*",
                start_date=start_date,
                end_date=end_date,
                mime_type=mime_filter,
                status_code=status_filter,
                limit=limit,
                collapse="urlkey",  # Dedupe by URL
            )

            for r in results:
                timestamp = r.get("timestamp", "")
                archive_url = f"https://web.archive.org/web/{timestamp}/{r.get('url')}"

                yield MappedURL(
                    url=r.get("url", ""),
                    domain=domain,
                    source="wayback",
                    timestamp=timestamp,
                    status_code=int(r.get("statuscode", 0)) if r.get("statuscode") else None,
                    mime_type=r.get("mimetype"),
                    content_length=int(r.get("length", 0)) if r.get("length") else None,
                    digest=r.get("digest"),
                    archive_url=archive_url,
                )

        except Exception as e:
            logger.error(f"Wayback mapping error for {domain}: {e}")

    async def _map_commoncrawl(
        self,
        domain: str,
        start_date: Optional[str],
        end_date: Optional[str],
        mime_filter: Optional[str],
        status_filter: Optional[int],
        limit: int,
    ) -> List[MappedURL]:
        """Map URLs from CommonCrawl Index."""
        urls = []
        async for url in self._stream_commoncrawl(
            domain, start_date, end_date, mime_filter, status_filter, limit
        ):
            urls.append(url)
        return urls

    async def _stream_commoncrawl(
        self,
        domain: str,
        start_date: Optional[str],
        end_date: Optional[str],
        mime_filter: Optional[str],
        status_filter: Optional[int],
        limit: int,
    ) -> AsyncGenerator[MappedURL, None]:
        """Stream URLs from CommonCrawl Index."""
        try:
            results = await self._cc.search(
                url=f"{domain}/*",
                limit=limit,
            )

            for r in results:
                # Filter by date if specified
                timestamp = r.get("timestamp", "")
                if start_date and timestamp < start_date.replace("-", ""):
                    continue
                if end_date and timestamp > end_date.replace("-", ""):
                    continue

                # Filter by mime
                if mime_filter and r.get("mime") != mime_filter:
                    continue

                # Filter by status
                status = int(r.get("status", 0)) if r.get("status") else None
                if status_filter and status != status_filter:
                    continue

                yield MappedURL(
                    url=r.get("url", ""),
                    domain=domain,
                    source="commoncrawl",
                    timestamp=timestamp,
                    status_code=status,
                    mime_type=r.get("mime"),
                    content_length=int(r.get("length", 0)) if r.get("length") else None,
                    digest=r.get("digest"),
                    warc_file=r.get("filename"),
                )

        except Exception as e:
            logger.error(f"CommonCrawl mapping error for {domain}: {e}")

    async def _map_memento(
        self,
        domain: str,
        limit: int,
    ) -> List[MappedURL]:
        """Map URLs from Memento TimeMap."""
        urls = []
        async for url in self._stream_memento(domain, limit):
            urls.append(url)
        return urls

    async def _stream_memento(
        self,
        domain: str,
        limit: int,
    ) -> AsyncGenerator[MappedURL, None]:
        """Stream URLs from Memento TimeMap (40+ archives)."""
        try:
            results = await self._memento.timemap(f"https://{domain}/")

            count = 0
            for r in results:
                if count >= limit:
                    break

                yield MappedURL(
                    url=r.get("original") or f"https://{domain}/",
                    domain=domain,
                    source="memento",
                    timestamp=r.get("datetime"),
                    archive_url=r.get("uri"),
                    archive_name=r.get("archive"),
                )
                count += 1

        except Exception as e:
            logger.error(f"Memento mapping error for {domain}: {e}")

    # -------------------------------------------------------------------------
    # Convenience methods
    # -------------------------------------------------------------------------

    async def get_url_count(self, domain: str) -> Dict[str, int]:
        """Quick count of URLs per source (no full fetch)."""
        await self._ensure_clients()
        domain = self._normalize_domain(domain)

        counts = {}

        if self.enable_wayback and self._wayback:
            try:
                count = await self._wayback.count_urls(domain)
                counts["wayback"] = count
            except:
                counts["wayback"] = 0

        if self.enable_commoncrawl and self._cc:
            try:
                count = await self._cc.count_urls(domain)
                counts["commoncrawl"] = count
            except:
                counts["commoncrawl"] = 0

        counts["total"] = sum(counts.values())
        return counts

    async def get_snapshots(
        self,
        url: str,
        limit: int = 100,
    ) -> List[MappedURL]:
        """Get all snapshots/versions of a specific URL."""
        await self._ensure_clients()

        snapshots = []

        if self.enable_wayback and self._wayback:
            try:
                results = await self._wayback.cdx_search(url=url, limit=limit)
                for r in results:
                    timestamp = r.get("timestamp", "")
                    snapshots.append(MappedURL(
                        url=url,
                        domain=urlparse(url).netloc,
                        source="wayback",
                        timestamp=timestamp,
                        status_code=int(r.get("statuscode", 0)) if r.get("statuscode") else None,
                        archive_url=f"https://web.archive.org/web/{timestamp}/{url}",
                    ))
            except Exception as e:
                logger.error(f"Wayback snapshots error: {e}")

        # Sort by timestamp
        snapshots.sort(key=lambda x: x.timestamp or "", reverse=True)
        return snapshots


# Convenience function
async def map_domain(domain: str, **kwargs) -> DomainMap:
    """Quick domain mapping."""
    async with BackdrillMapper() as mapper:
        return await mapper.map_domain(domain, **kwargs)


__all__ = [
    "BackdrillMapper",
    "MappedURL",
    "DomainMap",
    "map_domain",
]
