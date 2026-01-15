"""
JESTER MAPPER - Firecrawl Discovery (Optimized)
================================================

Discover URLs using Firecrawl's MAP and CRAWL endpoints.

- MAP: Fast site mapping (up to 100K URLs)
- CRAWL: Deep recursive crawl (100-parallel concurrency)

Optimizations:
    - Accepts shared HTTP client for connection reuse
    - httpx with HTTP/2 support when available

Usage:
    discovery = FirecrawlDiscovery()
    async for url in discovery.map_domain("example.com"):
        print(url.url, url.source)
"""

import asyncio
import logging
import re
from typing import AsyncGenerator, Set, Dict, Any, Optional, List
from urllib.parse import urljoin, urlparse

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    import aiohttp
    HTTPX_AVAILABLE = False

# Regex patterns to extract ALL asset URLs from HTML
ASSET_PATTERNS = [
    # Images
    re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'<img[^>]+srcset=["\']([^"\']+)["\']', re.IGNORECASE),
    # CSS
    re.compile(r'<link[^>]+href=["\']([^"\']+)["\']', re.IGNORECASE),
    # JavaScript
    re.compile(r'<script[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE),
    # Media
    re.compile(r'<source[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'<video[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'<audio[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE),
    # Embeds
    re.compile(r'<embed[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'<object[^>]+data=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'<iframe[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE),
    # Background images in style
    re.compile(r'url\(["\']?([^"\')\s]+)["\']?\)', re.IGNORECASE),
    # Data attributes
    re.compile(r'data-src=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'data-background=["\']([^"\']+)["\']', re.IGNORECASE),
]

def extract_assets_from_html(html: str, base_url: str) -> List[str]:
    """Extract ALL asset URLs (images, CSS, JS, media) from HTML."""
    assets = set()
    for pattern in ASSET_PATTERNS:
        for match in pattern.findall(html):
            # Handle srcset (comma-separated)
            if ',' in match and 'srcset' in pattern.pattern:
                for part in match.split(','):
                    url = part.strip().split()[0]  # Remove size descriptor
                    if url:
                        assets.add(url)
            else:
                assets.add(match)

    # Resolve relative URLs
    resolved = set()
    for url in assets:
        if not url.startswith(('http://', 'https://', 'data:', 'javascript:', '#', 'mailto:')):
            url = urljoin(base_url, url)
        if url.startswith(('http://', 'https://')):
            resolved.add(url)

    return list(resolved)

from ..models import DiscoveredURL
from ..config import (
    FIRECRAWL_API_KEY,
    FIRECRAWL_BASE_URL,
    FIRECRAWL_MAP_CONFIG,
    FIRECRAWL_CRAWL_CONFIG,
    TIMEOUTS,
)

logger = logging.getLogger(__name__)


class FirecrawlDiscovery:
    """
    Firecrawl-based URL discovery (optimized).

    Uses the Firecrawl v2 API:
    - MAP endpoint: Fast sitemap-style discovery (up to 100K URLs)
    - CRAWL endpoint: Deep recursive crawl with 100-parallel concurrency
    """

    def __init__(self):
        self.api_key = FIRECRAWL_API_KEY
        self.base_url = FIRECRAWL_BASE_URL
        self.map_config = FIRECRAWL_MAP_CONFIG
        self.crawl_config = FIRECRAWL_CRAWL_CONFIG

    async def _get_client(self, client: Optional[Any] = None):
        """Get a client - use provided or create temporary one."""
        if client is not None:
            return client, False
        if HTTPX_AVAILABLE:
            return httpx.AsyncClient(http2=True, timeout=httpx.Timeout(300.0)), True
        else:
            return aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)), True

    async def _close_client(self, client: Any, should_close: bool):
        """Close client if we created it."""
        if should_close and client is not None:
            if HTTPX_AVAILABLE:
                await client.aclose()
            else:
                await client.close()

    def _is_same_domain(self, url: str, domain: str) -> bool:
        """Check if URL belongs to the target domain."""
        try:
            parsed = urlparse(url)
            host = parsed.netloc.lower()
            domain = domain.lower()
            return host == domain or host.endswith(f".{domain}")
        except Exception:
            return False

    async def discover_all(
        self,
        domain: str,
        deep: bool = False,
        client: Optional[Any] = None,
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Discover URLs using Firecrawl.

        Args:
            domain: Domain to map
            deep: If True, also run deep CRAWL after MAP
            client: Optional shared HTTP client

        Yields:
            DiscoveredURL objects
        """
        seen: Set[str] = set()

        # Phase 1: MAP (fast)
        async for url in self.map_domain(domain, client=client):
            if url.url not in seen:
                seen.add(url.url)
                yield url

        # Phase 2: CRAWL (optional, slow but thorough)
        if deep:
            async for url in self.crawl_domain(domain, client=client):
                if url.url not in seen:
                    seen.add(url.url)
                    yield url

    async def map_domain(
        self,
        domain: str,
        client: Optional[Any] = None,
        include_subdomains: bool = True,
        search: Optional[str] = None,
        limit: int = 100000,
        sitemap_mode: str = "include",  # "only", "include", "skip"
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Call Firecrawl MAP endpoint for fast URL discovery.

        Returns up to 100K URLs from sitemap + light crawling.
        Uses Firecrawl v2 API.
        """
        if not self.api_key:
            logger.warning("[firecrawl_map] No API key - skipping")
            return

        logger.info(f"[firecrawl_map] Mapping domain: {domain}")

        http_client, should_close = await self._get_client(client)
        # Force v2 endpoint for map
        url = f"{self.base_url.replace('/v1', '/v2')}/map"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        # Start with default config but override with explicit args
        payload = {
            "url": f"https://{domain}",
            "includeSubdomains": include_subdomains,
            "limit": limit,
            "sitemap": sitemap_mode,
        }
        
        if search:
            payload["search"] = search

        # Merge any extra config that might be in self.map_config but not explicit args
        # (Be careful not to overwrite our explicit args with stale config defaults)
        for k, v in self.map_config.items():
            if k not in payload:
                payload[k] = v

        try:
            if HTTPX_AVAILABLE:
                response = await http_client.post(url, json=payload, headers=headers)
                status = response.status_code
                if status == 200:
                    data = response.json()
                else:
                    error = response.text
                    logger.error(f"[firecrawl_map] HTTP {status}: {error}")
                    return
            else:
                async with http_client.post(
                    url, json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=TIMEOUTS.get("firecrawl_map", 300))
                ) as response:
                    status = response.status
                    if status == 200:
                        data = await response.json()
                    else:
                        error = await response.text()
                        logger.error(f"[firecrawl_map] HTTP {status}: {error}")
                        return

            if status == 402:
                logger.error("[firecrawl_map] Insufficient credits")
                return

            if not data.get("success"):
                logger.error(f"[firecrawl_map] Failed: {data.get('error')}")
                return

            links = data.get("links", [])
            logger.info(f"[firecrawl_map] Found {len(links)} URLs")

            for link_obj in links:
                if isinstance(link_obj, dict):
                    url_str = link_obj.get("url")
                    title = link_obj.get("title")
                    description = link_obj.get("description")
                else:
                    url_str = link_obj
                    title = None
                    description = None

                if url_str and self._is_same_domain(url_str, domain):
                    yield DiscoveredURL(
                        url=url_str,
                        source="firecrawl_map",
                        domain=domain,
                        title=title,
                        description=description,
                    )

        except asyncio.TimeoutError:
            logger.error("[firecrawl_map] Timeout (5 min)")
        except Exception as e:
            logger.error(f"[firecrawl_map] Error: {e}")
        finally:
            await self._close_client(http_client, should_close)

    async def crawl_domain(
        self,
        domain: str,
        client: Optional[Any] = None,
        include_subdomains: bool = True,
        limit: int = 50000,
        max_depth: Optional[int] = None,
        allow_external_links: bool = False,
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Call Firecrawl CRAWL endpoint for deep recursive discovery.

        Uses 100-parallel concurrency to crawl all pages and extract links.
        Uses Firecrawl v2 API.
        """
        if not self.api_key:
            logger.warning("[firecrawl_crawl] No API key - skipping")
            return

        logger.info(f"[firecrawl_crawl] Starting deep crawl: {domain}")

        http_client, should_close = await self._get_client(client)
        # Force v2 endpoint for crawl
        url = f"{self.base_url.replace('/v1', '/v2')}/crawl"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "url": f"https://{domain}",
            "allowSubdomains": include_subdomains,
            "limit": limit,
            "allowExternalLinks": allow_external_links,
            "crawlEntireDomain": True, # Always true for discovery mode
        }
        
        if max_depth is not None:
            payload["maxDiscoveryDepth"] = max_depth

        # Merge scrapeOptions from config if present (e.g. maxConcurrency)
        # But ensure we don't overwrite our logic
        base_config = self.crawl_config.copy()
        if "scrapeOptions" in base_config:
            payload["scrapeOptions"] = base_config.pop("scrapeOptions")
        
        # Merge remaining base config keys if they don't conflict
        for k, v in base_config.items():
            if k not in payload:
                payload[k] = v

        try:
            if HTTPX_AVAILABLE:
                response = await http_client.post(url, json=payload, headers=headers)
                status = response.status_code
                if status == 200:
                    data = response.json()
                else:
                    error = response.text
                    logger.error(f"[firecrawl_crawl] HTTP {status}: {error}")
                    return
            else:
                async with http_client.post(
                    url, json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    status = response.status
                    if status == 200:
                        data = await response.json()
                    else:
                        error = await response.text()
                        logger.error(f"[firecrawl_crawl] HTTP {status}: {error}")
                        return

            if status == 402:
                logger.error("[firecrawl_crawl] Insufficient credits")
                return

            if not data.get("success"):
                logger.error(f"[firecrawl_crawl] Failed: {data.get('error')}")
                return

            job_id = data.get("id")
            logger.info(f"[firecrawl_crawl] Job started: {job_id}")

            # Poll for results
            async for discovered_url in self._poll_crawl_status(http_client, job_id, headers, domain):
                yield discovered_url

        except asyncio.TimeoutError:
            logger.error("[firecrawl_crawl] Timeout starting job")
        except Exception as e:
            logger.error(f"[firecrawl_crawl] Error: {e}")
        finally:
            await self._close_client(http_client, should_close)

    async def _poll_crawl_status(
        self,
        client: Any,
        job_id: str,
        headers: Dict[str, str],
        domain: str,
        poll_interval: int = 5,
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """Poll Firecrawl crawl status and yield discovered URLs."""
        url = f"{self.base_url}/crawl/{job_id}"
        seen_urls: Set[str] = set()
        max_polls = TIMEOUTS.get("firecrawl_crawl", 600) // poll_interval

        for poll_count in range(max_polls):
            try:
                if HTTPX_AVAILABLE:
                    response = await client.get(url, headers=headers)
                    status = response.status_code
                    data = response.json() if status == 200 else None
                else:
                    async with client.get(
                        url, headers=headers,
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        status = response.status
                        data = await response.json() if status == 200 else None

                if status != 200 or data is None:
                    logger.error(f"[firecrawl_crawl] Poll error: HTTP {status}")
                    break

                crawl_status = data.get("status")

                # Extract URLs from results
                if "data" in data:
                    for page_data in data["data"]:
                        metadata = page_data.get("metadata", {})
                        page_url = metadata.get("sourceURL") or metadata.get("url")

                        if page_url and self._is_same_domain(page_url, domain):
                            if page_url not in seen_urls:
                                seen_urls.add(page_url)
                                yield DiscoveredURL(
                                    url=page_url,
                                    source="firecrawl_crawl",
                                    domain=domain,
                                    title=metadata.get("title"),
                                )

                        # Extract links from page
                        links = page_data.get("links", [])
                        for link_obj in links:
                            if isinstance(link_obj, dict):
                                link_url = link_obj.get("url")
                            else:
                                link_url = link_obj

                            if not link_url:
                                continue

                            if not link_url.startswith(("http://", "https://")):
                                link_url = urljoin(page_url, link_url)

                            if self._is_same_domain(link_url, domain):
                                if link_url not in seen_urls:
                                    seen_urls.add(link_url)
                                    yield DiscoveredURL(
                                        url=link_url,
                                        source="firecrawl_crawl",
                                        domain=domain,
                                        parent_url=page_url,
                                    )

                        # Extract ALL assets from HTML (images, CSS, JS, media)
                        html_content = page_data.get("html") or page_data.get("rawHtml")
                        if html_content and page_url:
                            for asset_url in extract_assets_from_html(html_content, page_url):
                                if self._is_same_domain(asset_url, domain):
                                    if asset_url not in seen_urls:
                                        seen_urls.add(asset_url)
                                        yield DiscoveredURL(
                                            url=asset_url,
                                            source="firecrawl_crawl",
                                            domain=domain,
                                            parent_url=page_url,
                                        )

                if crawl_status == "completed":
                    logger.info(f"[firecrawl_crawl] Complete: {len(seen_urls)} URLs")
                    break
                elif crawl_status == "failed":
                    logger.error(f"[firecrawl_crawl] Job failed: {data.get('error')}")
                    break
                else:
                    logger.debug(f"[firecrawl_crawl] Status: {crawl_status} ({len(seen_urls)} URLs)")
                    await asyncio.sleep(poll_interval)

            except Exception as e:
                logger.error(f"[firecrawl_crawl] Poll error: {e}")
                break
