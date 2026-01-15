"""
JESTER MAPPER - Sitemap Discovery (Optimized)
==============================================

Discover URLs from site-declared sources:
    - sitemap.xml (recursive, including sitemap indexes)
    - robots.txt (Disallow/Allow patterns, Sitemap directives)

Optimizations:
    - Accepts shared HTTP client for connection reuse
    - httpx with HTTP/2 support when available

Usage:
    discovery = SitemapDiscovery()
    async for url in discovery.discover_all("example.com"):
        print(url.url, url.source, url.priority)
"""

import asyncio
import logging
from typing import AsyncGenerator, Set, Optional, Any
from xml.etree import ElementTree

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    import aiohttp
    HTTPX_AVAILABLE = False

from ..models import DiscoveredURL
from ..config import TIMEOUTS

logger = logging.getLogger(__name__)

# XML namespaces for sitemaps
SITEMAP_NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "xhtml": "http://www.w3.org/1999/xhtml",
}


class SitemapDiscovery:
    """
    Sitemap and robots.txt-based URL discovery (optimized).

    Parses:
        - sitemap.xml and sitemap index files
        - robots.txt for Disallow patterns and Sitemap directives
    """

    async def _get_client(self, client: Optional[Any] = None):
        """Get a client - use provided or create temporary one."""
        if client is not None:
            return client, False
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

    async def discover_all(
        self,
        domain: str,
        client: Optional[Any] = None,
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Discover URLs from sitemaps and robots.txt.

        Args:
            domain: Domain to check
            client: Optional shared HTTP client

        Yields:
            DiscoveredURL objects
        """
        http_client, should_close = await self._get_client(client)
        seen: Set[str] = set()

        try:
            # First, check robots.txt for Sitemap directives
            sitemap_urls = await self._get_sitemap_urls_from_robots(http_client, domain)

            # Add default sitemap locations
            sitemap_urls.update([
                f"https://{domain}/sitemap.xml",
                f"https://{domain}/sitemap_index.xml",
                f"https://{domain}/sitemap-index.xml",
                f"https://{domain}/sitemaps/sitemap.xml",
            ])

            # Parse all sitemaps (handles recursion for sitemap indexes)
            for sitemap_url in sitemap_urls:
                async for url in self._parse_sitemap(http_client, sitemap_url, domain, seen):
                    yield url

            # Also parse robots.txt for Disallow patterns (discovers hidden paths)
            async for url in self._discover_from_robots(http_client, domain, seen):
                yield url

        finally:
            await self._close_client(http_client, should_close)

        logger.info(f"Sitemap discovery complete: {len(seen)} URLs")

    async def discover_sitemap(
        self,
        domain: str,
        client: Optional[Any] = None,
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Discover URLs from sitemap.xml only.

        Args:
            domain: Domain to check
            client: Optional shared HTTP client

        Yields:
            DiscoveredURL objects with priority/lastmod metadata
        """
        http_client, should_close = await self._get_client(client)
        seen: Set[str] = set()
        sitemap_url = f"https://{domain}/sitemap.xml"

        try:
            async for url in self._parse_sitemap(http_client, sitemap_url, domain, seen):
                yield url
        finally:
            await self._close_client(http_client, should_close)

    async def _parse_sitemap(
        self,
        client: Any,
        sitemap_url: str,
        domain: str,
        seen: Set[str],
        depth: int = 0,
        max_depth: int = 5,
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """Parse a sitemap (handles both regular sitemaps and sitemap indexes)."""
        if depth > max_depth:
            logger.warning(f"[sitemap] Max depth reached: {sitemap_url}")
            return

        if sitemap_url in seen:
            return

        seen.add(sitemap_url)
        logger.debug(f"[sitemap] Parsing: {sitemap_url}")

        try:
            if HTTPX_AVAILABLE:
                response = await client.get(sitemap_url)
                status = response.status_code
                content = response.text if status == 200 else None
            else:
                async with client.get(
                    sitemap_url,
                    timeout=aiohttp.ClientTimeout(total=TIMEOUTS.get("sitemap", 30))
                ) as response:
                    status = response.status
                    content = await response.text() if status == 200 else None

            if status != 200 or content is None:
                logger.debug(f"[sitemap] HTTP {status}: {sitemap_url}")
                return

            # Check if it's gzipped
            if sitemap_url.endswith(".gz"):
                import gzip
                if HTTPX_AVAILABLE:
                    content = gzip.decompress(response.content).decode("utf-8")
                else:
                    content = gzip.decompress(await response.read()).decode("utf-8")

            # Parse XML
            try:
                root = ElementTree.fromstring(content)
            except ElementTree.ParseError as e:
                logger.debug(f"[sitemap] XML parse error: {e}")
                return

            # Check if it's a sitemap index
            if root.tag.endswith("sitemapindex"):
                for sitemap in root.findall(".//sm:sitemap/sm:loc", SITEMAP_NS):
                    child_url = sitemap.text.strip() if sitemap.text else None
                    if child_url:
                        async for url in self._parse_sitemap(client, child_url, domain, seen, depth + 1, max_depth):
                            yield url
            else:
                # Regular sitemap - extract URLs
                for url_elem in root.findall(".//sm:url", SITEMAP_NS):
                    loc = url_elem.find("sm:loc", SITEMAP_NS)
                    priority = url_elem.find("sm:priority", SITEMAP_NS)
                    lastmod = url_elem.find("sm:lastmod", SITEMAP_NS)
                    changefreq = url_elem.find("sm:changefreq", SITEMAP_NS)

                    if loc is not None and loc.text:
                        url_str = loc.text.strip()
                        if url_str not in seen:
                            seen.add(url_str)
                            yield DiscoveredURL(
                                url=url_str,
                                source="sitemap",
                                domain=domain,
                                priority=float(priority.text) if priority is not None and priority.text else None,
                                lastmod=lastmod.text if lastmod is not None else None,
                                changefreq=changefreq.text if changefreq is not None else None,
                            )

                # Also check for alternate hreflang URLs
                for link in root.findall(".//xhtml:link[@rel='alternate']", SITEMAP_NS):
                    href = link.get("href")
                    if href and href not in seen:
                        seen.add(href)
                        yield DiscoveredURL(
                            url=href,
                            source="sitemap",
                            domain=domain,
                        )

        except asyncio.TimeoutError:
            logger.debug(f"[sitemap] Timeout: {sitemap_url}")
        except Exception as e:
            logger.debug(f"[sitemap] Error parsing {sitemap_url}: {e}")

    async def _get_sitemap_urls_from_robots(self, client: Any, domain: str) -> Set[str]:
        """Extract Sitemap directives from robots.txt."""
        sitemap_urls: Set[str] = set()
        robots_url = f"https://{domain}/robots.txt"

        try:
            if HTTPX_AVAILABLE:
                response = await client.get(robots_url)
                status = response.status_code
                content = response.text if status == 200 else None
            else:
                async with client.get(
                    robots_url,
                    timeout=aiohttp.ClientTimeout(total=TIMEOUTS.get("robots", 10))
                ) as response:
                    status = response.status
                    content = await response.text() if status == 200 else None

            if status != 200 or content is None:
                return sitemap_urls

            for line in content.split("\n"):
                line = line.strip()
                if line.lower().startswith("sitemap:"):
                    sitemap_url = line.split(":", 1)[1].strip()
                    if sitemap_url:
                        sitemap_urls.add(sitemap_url)

        except Exception as e:
            logger.debug(f"[robots] Error: {e}")

        return sitemap_urls

    async def _discover_from_robots(
        self,
        client: Any,
        domain: str,
        seen: Set[str],
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """Discover URLs from robots.txt Disallow/Allow patterns."""
        robots_url = f"https://{domain}/robots.txt"

        try:
            if HTTPX_AVAILABLE:
                response = await client.get(robots_url)
                status = response.status_code
                content = response.text if status == 200 else None
            else:
                async with client.get(
                    robots_url,
                    timeout=aiohttp.ClientTimeout(total=TIMEOUTS.get("robots", 10))
                ) as response:
                    status = response.status
                    content = await response.text() if status == 200 else None

            if status != 200 or content is None:
                return

            paths: Set[str] = set()
            for line in content.split("\n"):
                line = line.strip()
                if line.lower().startswith(("disallow:", "allow:")):
                    path = line.split(":", 1)[1].strip()
                    if path and path != "/":
                        path = path.replace("*", "").replace("$", "")
                        if path and not path.endswith("/"):
                            paths.add(path)

            for path in paths:
                url_str = f"https://{domain}{path}"
                if url_str not in seen:
                    seen.add(url_str)
                    yield DiscoveredURL(
                        url=url_str,
                        source="robots",
                        domain=domain,
                        path=path,
                    )

        except Exception as e:
            logger.debug(f"[robots] Error: {e}")
