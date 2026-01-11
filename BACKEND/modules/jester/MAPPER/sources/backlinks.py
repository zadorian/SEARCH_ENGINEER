"""
JESTER MAPPER - Backlink Discovery (Optimized)
===============================================

Discover URLs by finding pages that link TO the target domain.

Sources:
    - Majestic API (Trust/Citation Flow metrics)
    - CC WebGraph (Common Crawl link graph, 90M domains)

Optimizations:
    - Accepts shared HTTP client for connection reuse
    - httpx with HTTP/2 support when available

Usage:
    discovery = BacklinkDiscovery()
    async for url in discovery.discover_all("example.com"):
        print(url.url, url.source, url.trust_flow)
"""

import asyncio
import logging
from typing import AsyncGenerator, Set, Optional, Any

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    import aiohttp
    HTTPX_AVAILABLE = False

from ..models import DiscoveredURL
from ..config import (
    MAJESTIC_API_KEY,
    ES_HOST,
    ES_INDEX_WEBGRAPH,
    TIMEOUTS,
)

logger = logging.getLogger(__name__)


class BacklinkDiscovery:
    """
    Backlink-based URL discovery (optimized).

    Finds pages that link TO the target domain, which:
    1. Reveals important pages on the target (pages others link to)
    2. Finds related domains in the same space
    3. Provides trust/authority metrics
    """

    def __init__(self):
        self.majestic_key = MAJESTIC_API_KEY
        self.es_host = ES_HOST
        self.es_index = ES_INDEX_WEBGRAPH

    async def _get_client(self, client: Optional[Any] = None):
        """Get a client - use provided or create temporary one."""
        if client is not None:
            return client, False
        if HTTPX_AVAILABLE:
            return httpx.AsyncClient(http2=True, timeout=httpx.Timeout(60.0)), True
        else:
            return aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)), True

    async def _close_client(self, client: Any, should_close: bool):
        """Close client if we created it."""
        if should_close and client is not None:
            if HTTPX_AVAILABLE:
                await client.aclose()
            else:
                await client.close()

    async def discover_all(
        self,
        domain: str,
        client: Optional[Any] = None,
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Query all backlink sources in parallel.

        Args:
            domain: Target domain
            client: Optional shared HTTP client

        Yields:
            DiscoveredURL objects with backlink metadata
        """
        seen: Set[str] = set()

        generators = [
            ("majestic", self.discover_majestic(domain, client=client)),
            ("cc_webgraph", self.discover_cc_webgraph(domain, client=client)),
        ]

        queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()

        async def consume(name: str, gen):
            try:
                async for item in gen:
                    await queue.put(item)
            except Exception as exc:
                logger.error(f"Backlink source '{name}' failed: {exc}")
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

        logger.info(f"Backlink discovery complete: {len(seen)} URLs")

    async def discover_majestic(
        self,
        domain: str,
        max_results: int = 1000,
        client: Optional[Any] = None,
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Query Majestic API for backlinks.

        PAID - Requires MAJESTIC_API_KEY.
        Returns Trust Flow and Citation Flow metrics.
        """
        if not self.majestic_key:
            logger.debug("[majestic] No API key - skipping")
            return

        logger.info(f"[majestic] Finding backlinks to: {domain}")

        http_client, should_close = await self._get_client(client)
        url = "https://api.majestic.com/api/json"
        params = {
            "app_api_key": self.majestic_key,
            "cmd": "GetBackLinkData",
            "item": domain,
            "Count": max_results,
            "datasource": "fresh",
            "Mode": 0,
        }

        try:
            if HTTPX_AVAILABLE:
                response = await http_client.get(url, params=params)
                status = response.status_code
                data = response.json() if status == 200 else None
            else:
                async with http_client.get(
                    url, params=params,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    status = response.status
                    data = await response.json() if status == 200 else None

            if status != 200 or data is None:
                logger.error(f"[majestic] HTTP {status}")
                return

            if data.get("Code") != "OK":
                logger.error(f"[majestic] API error: {data.get('ErrorMessage')}")
                return

            tables = data.get("DataTables", {})
            backlinks = tables.get("BackLinks", {}).get("Data", [])

            count = 0
            for bl in backlinks:
                source_url = bl.get("SourceURL")
                if source_url:
                    count += 1
                    yield DiscoveredURL(
                        url=source_url,
                        source="majestic",
                        domain=domain,
                        trust_flow=bl.get("SourceTrustFlow"),
                        citation_flow=bl.get("SourceCitationFlow"),
                        raw={
                            "anchor_text": bl.get("AnchorText"),
                            "target_url": bl.get("TargetURL"),
                            "first_seen": bl.get("FirstIndexedDate"),
                            "last_seen": bl.get("LastSeenDate"),
                        },
                    )

            logger.info(f"[majestic] Found {count} backlinks")

        except Exception as e:
            logger.error(f"[majestic] Error: {e}")
        finally:
            await self._close_client(http_client, should_close)

    async def discover_cc_webgraph(
        self,
        domain: str,
        max_results: int = 1000,
        client: Optional[Any] = None,
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Query CC WebGraph from Elasticsearch.

        FREE - Uses our indexed Common Crawl web graph.
        90M domains, 166M+ edges.
        """
        logger.info(f"[cc_webgraph] Finding referring domains for: {domain}")

        http_client, should_close = await self._get_client(client)
        query = {
            "query": {
                "term": {"target_domain.keyword": domain}
            },
            "size": max_results,
            "_source": ["source_domain", "source_url", "harmonic_rank", "page_rank"],
        }

        try:
            if HTTPX_AVAILABLE:
                response = await http_client.post(
                    f"{self.es_host}/{self.es_index}/_search",
                    json=query,
                    headers={"Content-Type": "application/json"},
                )
                status = response.status_code
                data = response.json() if status == 200 else None
            else:
                async with http_client.post(
                    f"{self.es_host}/{self.es_index}/_search",
                    json=query,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    status = response.status
                    data = await response.json() if status == 200 else None

            if status != 200 or data is None:
                logger.debug(f"[cc_webgraph] ES error: HTTP {status}")
                return

            hits = data.get("hits", {}).get("hits", [])

            count = 0
            for hit in hits:
                source = hit.get("_source", {})
                source_domain = source.get("source_domain")
                source_url = source.get("source_url")

                url_str = source_url or f"https://{source_domain}"

                if url_str:
                    count += 1
                    yield DiscoveredURL(
                        url=url_str,
                        source="cc_webgraph",
                        domain=domain,
                        raw={
                            "source_domain": source_domain,
                            "harmonic_rank": source.get("harmonic_rank"),
                            "page_rank": source.get("page_rank"),
                        },
                    )

            logger.info(f"[cc_webgraph] Found {count} referring domains")

        except Exception as e:
            logger.debug(f"[cc_webgraph] Error: {e}")
        finally:
            await self._close_client(http_client, should_close)
