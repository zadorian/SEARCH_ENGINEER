"""
JESTER MAPPER - Search Engine Discovery (Optimized)
====================================================

Discover URLs indexed by search engines using site: queries.

Optimizations:
    - Accepts shared HTTP client (no session-per-request)
    - Parallel market queries for Bing (4x faster)
    - httpx with HTTP/2 support when available

Sources:
    - Google Custom Search API
    - Bing via SerpAPI (parallel markets)
    - Brave Search API
    - DuckDuckGo (scraping)
    - Exa API (semantic search)

Usage:
    discovery = SearchEngineDiscovery()
    async for url in discovery.discover_all("example.com"):
        print(url.url, url.source)
"""

import asyncio
import logging
from typing import AsyncGenerator, Set, Optional, Any, List
from urllib.parse import unquote
import re

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    import aiohttp
    HTTPX_AVAILABLE = False

from ..models import DiscoveredURL
from ..config import (
    GOOGLE_API_KEY,
    GOOGLE_CSE_ID,
    SERPAPI_KEY,
    BRAVE_API_KEY,
    EXA_API_KEY,
    TIMEOUTS,
    RATE_LIMITS,
)

logger = logging.getLogger(__name__)


class SearchEngineDiscovery:
    """
    Search engine-based URL discovery (optimized).

    Uses site: operator to find indexed pages.
    Accepts shared HTTP client for connection reuse.
    """

    def __init__(self):
        self.google_key = GOOGLE_API_KEY
        self.google_cse = GOOGLE_CSE_ID
        self.serpapi_key = SERPAPI_KEY  # Bing via SerpAPI
        self.brave_key = BRAVE_API_KEY
        self.exa_key = EXA_API_KEY

    async def _get_client(self, client: Optional[Any] = None):
        """Get a client - use provided or create temporary one."""
        if client is not None:
            return client, False  # (client, should_close)

        # Create temporary client
        if HTTPX_AVAILABLE:
            return httpx.AsyncClient(http2=True, timeout=httpx.Timeout(30.0)), True
        else:
            return aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)), True

    async def _close_client(self, client: Any, should_close: bool):
        """Close client if we created it."""
        if should_close and client is not None:
            if HTTPX_AVAILABLE:
                await client.aclose()
            else:
                await client.close()

    async def _http_get(self, client: Any, url: str, params: dict = None, headers: dict = None):
        """Unified HTTP GET for both httpx and aiohttp."""
        if HTTPX_AVAILABLE:
            response = await client.get(url, params=params, headers=headers)
            # httpx: .json() is sync, not async
            return response.status_code, response.json() if response.status_code == 200 else None
        else:
            async with client.get(url, params=params, headers=headers) as response:
                return response.status, await response.json() if response.status == 200 else None

    async def _http_post(self, client: Any, url: str, data: dict = None, json_data: dict = None, headers: dict = None):
        """Unified HTTP POST for both httpx and aiohttp."""
        if HTTPX_AVAILABLE:
            if json_data:
                response = await client.post(url, json=json_data, headers=headers)
            else:
                response = await client.post(url, data=data, headers=headers)
            if response.status_code == 200:
                # httpx: .json() and .text are sync, not async
                content_type = response.headers.get("content-type", "")
                if "json" in content_type:
                    return response.status_code, response.json()
                else:
                    return response.status_code, response.text
            return response.status_code, None
        else:
            if json_data:
                async with client.post(url, json=json_data, headers=headers) as response:
                    if response.status == 200:
                        content_type = response.headers.get("content-type", "")
                        if "json" in content_type:
                            return response.status, await response.json()
                        else:
                            return response.status, await response.text()
                    return response.status, None
            else:
                async with client.post(url, data=data, headers=headers) as response:
                    if response.status == 200:
                        return response.status, await response.text()
                    return response.status, None

    async def discover_all(
        self,
        domain: str,
        max_per_engine: int = 200,
        client: Optional[Any] = None,
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Query all search engines in parallel.

        Args:
            domain: Domain to search
            max_per_engine: Maximum results per engine
            client: Optional shared HTTP client

        Yields:
            DiscoveredURL objects
        """
        seen: Set[str] = set()

        generators = [
            ("google", self.discover_google(domain, max_per_engine, client)),
            ("bing", self.discover_bing(domain, max_per_engine, client)),
            ("brave", self.discover_brave(domain, max_per_engine, client)),
            ("duckduckgo", self.discover_duckduckgo(domain, client)),
        ]

        queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()

        async def consume(name: str, gen):
            try:
                async for item in gen:
                    await queue.put(item)
            except Exception as exc:
                logger.error(f"Search engine '{name}' failed: {exc}")
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

        logger.info(f"Search engine discovery complete: {len(seen)} URLs")

    async def discover_google(
        self,
        domain: str,
        max_results: int = 200,
        client: Optional[Any] = None,
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Query Google Custom Search API.

        FREE tier: 100 queries/day, 10 results/query.
        PAID: $5 per 1000 queries.
        """
        if not self.google_key or not self.google_cse:
            logger.debug("[google] No API key or CSE ID - skipping")
            return

        logger.info(f"[google] Searching site:{domain}")

        http_client, should_close = await self._get_client(client)
        query = f"site:{domain}"
        count = 0
        start = 1

        try:
            while count < max_results:
                url = "https://www.googleapis.com/customsearch/v1"
                params = {
                    "key": self.google_key,
                    "cx": self.google_cse,
                    "q": query,
                    "start": start,
                    "num": 10,
                }

                try:
                    status, data = await self._http_get(http_client, url, params=params)

                    if status == 429:
                        logger.warning("[google] Rate limited")
                        break
                    if status != 200 or data is None:
                        logger.error(f"[google] HTTP {status}")
                        break

                    items = data.get("items", [])
                    if not items:
                        break

                    for item in items:
                        link = item.get("link")
                        if link:
                            count += 1
                            yield DiscoveredURL(
                                url=link,
                                source="google",
                                domain=domain,
                                title=item.get("title"),
                                description=item.get("snippet"),
                            )

                    next_page = data.get("queries", {}).get("nextPage")
                    if not next_page:
                        break

                    start += 10
                    await asyncio.sleep(1 / RATE_LIMITS.get("google", 1))

                except Exception as e:
                    logger.error(f"[google] Error: {e}")
                    break

        finally:
            await self._close_client(http_client, should_close)

        logger.info(f"[google] Found {count} URLs")

    async def discover_bing(
        self,
        domain: str,
        max_results: int = 200,
        client: Optional[Any] = None,
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Query Bing via SerpAPI with PARALLEL MARKET QUERIES.

        Searches all 4 markets simultaneously for 4x faster results.
        """
        if not self.serpapi_key:
            logger.debug("[bing] No SERPAPI_KEY - skipping")
            return

        logger.info(f"[bing] Searching site:{domain} via SerpAPI (parallel markets)")

        http_client, should_close = await self._get_client(client)
        markets = ["en-US", "en-GB", "de-DE", "fr-FR"]
        seen_urls: Set[str] = set()

        try:
            async def search_market(market: str) -> List[DiscoveredURL]:
                """Search a single market and return results."""
                results = []
                query = f"site:{domain}"
                first = 1
                page_size = 50
                market_max = max_results // len(markets)  # Divide quota among markets

                while len(results) < market_max:
                    url = "https://serpapi.com/search"
                    params = {
                        "api_key": self.serpapi_key,
                        "engine": "bing",
                        "q": query,
                        "first": first,
                        "count": page_size,
                        "mkt": market,
                        "safeSearch": "Off",
                    }

                    try:
                        status, data = await self._http_get(http_client, url, params=params)

                        if status == 401:
                            logger.error("[bing] Invalid SERPAPI_KEY")
                            return results
                        if status == 429:
                            logger.warning(f"[bing] Rate limited on {market}")
                            break
                        if status != 200 or data is None:
                            break

                        organic = data.get("organic_results", [])
                        if not organic:
                            break

                        for item in organic:
                            link = item.get("link") or item.get("url")
                            if link:
                                results.append(DiscoveredURL(
                                    url=link,
                                    source="bing",
                                    domain=domain,
                                    title=item.get("title"),
                                    description=item.get("snippet") or item.get("description"),
                                ))

                        first += page_size
                        await asyncio.sleep(0.1)

                    except Exception as e:
                        logger.error(f"[bing] Error on {market}: {e}")
                        break

                return results

            # Run ALL markets in parallel (4x faster)
            market_results = await asyncio.gather(
                *[search_market(m) for m in markets],
                return_exceptions=True
            )

            # Yield results, deduplicating across markets
            total_count = 0
            for result_set in market_results:
                if isinstance(result_set, Exception):
                    logger.error(f"[bing] Market failed: {result_set}")
                    continue

                for url_item in result_set:
                    if url_item.url not in seen_urls and total_count < max_results:
                        seen_urls.add(url_item.url)
                        total_count += 1
                        yield url_item

        finally:
            await self._close_client(http_client, should_close)

        logger.info(f"[bing] Found {len(seen_urls)} URLs via SerpAPI (parallel)")

    async def discover_brave(
        self,
        domain: str,
        max_results: int = 200,
        client: Optional[Any] = None,
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Query Brave Search API.

        FREE tier: 2000 queries/month.
        PAID: $3 per 1000 queries.
        """
        if not self.brave_key:
            logger.debug("[brave] No API key - skipping")
            return

        logger.info(f"[brave] Searching site:{domain}")

        http_client, should_close = await self._get_client(client)
        query = f"site:{domain}"
        count = 0
        offset = 0

        try:
            while count < max_results:
                url = "https://api.search.brave.com/res/v1/web/search"
                headers = {
                    "X-Subscription-Token": self.brave_key,
                    "Accept": "application/json",
                }
                params = {
                    "q": query,
                    "count": 20,
                    "offset": offset,
                }

                try:
                    status, data = await self._http_get(http_client, url, params=params, headers=headers)

                    if status == 429:
                        logger.warning("[brave] Rate limited")
                        break
                    if status != 200 or data is None:
                        logger.error(f"[brave] HTTP {status}")
                        break

                    results = data.get("web", {}).get("results", [])
                    if not results:
                        break

                    for result in results:
                        link = result.get("url")
                        if link:
                            count += 1
                            yield DiscoveredURL(
                                url=link,
                                source="brave",
                                domain=domain,
                                title=result.get("title"),
                                description=result.get("description"),
                            )

                    offset += 20
                    await asyncio.sleep(1 / RATE_LIMITS.get("brave", 5))

                except Exception as e:
                    logger.error(f"[brave] Error: {e}")
                    break

        finally:
            await self._close_client(http_client, should_close)

        logger.info(f"[brave] Found {count} URLs")

    async def discover_duckduckgo(
        self,
        domain: str,
        client: Optional[Any] = None,
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Query DuckDuckGo via HTML scraping.

        FREE - No API key required.
        Limited results (DDG limits site: queries).
        """
        logger.info(f"[duckduckgo] Searching site:{domain}")

        http_client, should_close = await self._get_client(client)

        try:
            url = "https://html.duckduckgo.com/html/"
            data = {"q": f"site:{domain}"}

            status, html = await self._http_post(http_client, url, data=data)

            if status != 200 or html is None:
                logger.error(f"[duckduckgo] HTTP {status}")
                return

            # Extract URLs from results
            pattern = r'class="result__url"[^>]*href="([^"]+)"'
            matches = re.findall(pattern, html)

            uddg_pattern = r'uddg=([^&"]+)'
            uddg_matches = re.findall(uddg_pattern, html)

            all_urls = set()
            for match in matches + uddg_matches:
                try:
                    url_str = unquote(match)
                    if domain in url_str:
                        all_urls.add(url_str)
                except Exception:
                    continue

            for url_str in all_urls:
                yield DiscoveredURL(
                    url=url_str,
                    source="duckduckgo",
                    domain=domain,
                )

            logger.info(f"[duckduckgo] Found {len(all_urls)} URLs")

        except Exception as e:
            logger.error(f"[duckduckgo] Error: {e}")

        finally:
            await self._close_client(http_client, should_close)

    async def discover_exa(
        self,
        domain: str,
        max_results: int = 100,
        client: Optional[Any] = None,
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Query Exa semantic search API.

        PAID - Requires EXA_API_KEY.
        Good for finding related content.
        """
        if not self.exa_key:
            logger.debug("[exa] No API key - skipping")
            return

        logger.info(f"[exa] Searching site:{domain}")

        http_client, should_close = await self._get_client(client)

        try:
            url = "https://api.exa.ai/search"
            headers = {
                "x-api-key": self.exa_key,
                "Content-Type": "application/json",
            }
            payload = {
                "query": f"site:{domain}",
                "numResults": min(max_results, 100),
                "type": "keyword",
            }

            status, data = await self._http_post(http_client, url, json_data=payload, headers=headers)

            if status != 200 or data is None:
                logger.error(f"[exa] HTTP {status}")
                return

            results = data.get("results", [])

            for result in results:
                link = result.get("url")
                if link:
                    yield DiscoveredURL(
                        url=link,
                        source="exa",
                        domain=domain,
                        title=result.get("title"),
                    )

            logger.info(f"[exa] Found {len(results)} URLs")

        except Exception as e:
            logger.error(f"[exa] Error: {e}")

        finally:
            await self._close_client(http_client, should_close)
