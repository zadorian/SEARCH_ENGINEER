"""
Firecrawl cached scraping for BACKDRILL.

Firecrawl provides fast web scraping with built-in caching.
Key parameter: maxAge (30 days = 2592000000ms)

This allows treating Firecrawl as a "cache layer" for recent content.
"""

import os
import aiohttp
from typing import Optional, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

FIRECRAWL_API = "https://api.firecrawl.dev/v1"
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")

# Default cache age: 30 days in milliseconds
DEFAULT_MAX_AGE_MS = 2592000000


class FirecrawlCache:
    """
    Firecrawl client with cache-first approach.

    Firecrawl's maxAge parameter allows fetching from their cache
    instead of re-scraping. This is useful for:
    - Recent content (within 30 days)
    - Faster responses (no live scrape needed)
    - Lower costs (cached requests are cheaper)

    Usage:
        fc = FirecrawlCache(max_age_ms=2592000000)  # 30 days

        # Fetch with cache
        result = await fc.fetch("https://example.com")

        # Force fresh scrape
        result = await fc.fetch("https://example.com", force_fresh=True)
    """

    def __init__(
        self,
        max_age_ms: int = DEFAULT_MAX_AGE_MS,
        api_key: Optional[str] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ):
        self.max_age_ms = max_age_ms
        self.api_key = api_key or FIRECRAWL_API_KEY
        self._session = session
        self._own_session = session is None

        if not self.api_key:
            logger.warning("FIRECRAWL_API_KEY not set - Firecrawl will be unavailable")

    async def __aenter__(self):
        if self._own_session:
            self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._own_session and self._session:
            await self._session.close()

    async def _ensure_session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._own_session = True

    async def fetch(
        self,
        url: str,
        force_fresh: bool = False,
        formats: Optional[list] = None,
    ):
        """
        Fetch URL content via Firecrawl.

        Uses maxAge to prefer cached content within the cache window.

        Args:
            url: Target URL
            force_fresh: If True, bypass cache and force fresh scrape
            formats: Content formats to return (default: ["markdown", "html"])

        Returns:
            BackdrillResult
        """
        from ..backdrill import BackdrillResult, ArchiveSource

        if not self.api_key:
            return BackdrillResult(url=url)

        await self._ensure_session()

        payload = {
            "url": url,
            "formats": formats or ["markdown", "html"],
        }

        # Use maxAge for cache-first approach (unless forcing fresh)
        if not force_fresh:
            payload["maxAge"] = self.max_age_ms

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with self._session.post(
                f"{FIRECRAWL_API}/scrape",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status != 200:
                    logger.debug(f"Firecrawl request failed: {resp.status}")
                    return BackdrillResult(url=url, status_code=resp.status)

                data = await resp.json()

                if not data.get("success"):
                    return BackdrillResult(url=url)

                result_data = data.get("data", {})

                return BackdrillResult(
                    url=url,
                    html=result_data.get("html"),
                    content=result_data.get("markdown"),
                    timestamp=datetime.now(),  # Firecrawl doesn't provide cache timestamp
                    source=ArchiveSource.FIRECRAWL_CACHE,
                    status_code=200,
                    mime_type="text/html",
                    metadata={
                        "cached": not force_fresh,
                        "max_age_ms": self.max_age_ms if not force_fresh else 0,
                        "title": result_data.get("metadata", {}).get("title"),
                        "description": result_data.get("metadata", {}).get("description"),
                    }
                )

        except Exception as e:
            logger.error(f"Firecrawl fetch failed for {url}: {e}")
            return BackdrillResult(url=url)

    async def crawl(
        self,
        url: str,
        max_pages: int = 10,
        include_paths: Optional[list] = None,
        exclude_paths: Optional[list] = None,
    ) -> Dict[str, Any]:
        """
        Crawl a site starting from URL.

        Note: This is an async job - returns job_id for polling.

        Args:
            url: Starting URL
            max_pages: Max pages to crawl
            include_paths: URL patterns to include
            exclude_paths: URL patterns to exclude

        Returns:
            Dict with job_id and status
        """
        if not self.api_key:
            return {"error": "No API key configured"}

        await self._ensure_session()

        payload = {
            "url": url,
            "limit": max_pages,
            "maxAge": self.max_age_ms,
        }

        if include_paths:
            payload["includePaths"] = include_paths
        if exclude_paths:
            payload["excludePaths"] = exclude_paths

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with self._session.post(
                f"{FIRECRAWL_API}/crawl",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                data = await resp.json()
                return {
                    "job_id": data.get("id"),
                    "status": data.get("status"),
                    "success": data.get("success"),
                }

        except Exception as e:
            logger.error(f"Firecrawl crawl failed: {e}")
            return {"error": str(e)}

    def get_cache_age_days(self) -> float:
        """Get current cache age setting in days."""
        return self.max_age_ms / (1000 * 60 * 60 * 24)

    def set_cache_age_days(self, days: float):
        """Set cache age in days."""
        self.max_age_ms = int(days * 24 * 60 * 60 * 1000)
