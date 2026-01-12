"""
BrightData - External BrightData Web Unlocker API

External paid proxy API (NOT part of JESTER). LAST RESORT - most expensive.
Use only when everything else fails.

Usage:
    from modules.jester.brightdata import BrightData, scrape_brightdata

    scraper = BrightData()
    result = await scraper.scrape("https://example.com")

Requires:
    BRIGHTDATA_API_KEY environment variable
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional, List, Dict
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Load environment
load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")

logger = logging.getLogger("BRIGHTDATA")

# Constants
DEFAULT_TIMEOUT = 60
DEFAULT_MAX_CONCURRENT = 5  # Conservative - BrightData is expensive
MIN_VALID_HTML_LENGTH = 100
DEFAULT_ZONE = "mcp_unlocker"


@dataclass
class BrightDataResult:
    """Result from BrightData API scrape."""
    url: str
    html: str
    status_code: int
    latency_ms: int
    content_length: int
    headers: Dict = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.headers is None:
            self.headers = {}

    @property
    def success(self) -> bool:
        return self.html and len(self.html) >= MIN_VALID_HTML_LENGTH and not self.error


class BrightData:
    """
    BrightData Web Unlocker API wrapper.

    External paid proxy service. LAST RESORT for heavily protected sites.
    Most expensive option - use only when JESTER A/B/C/D and Firecrawl fail.

    Features:
    - Residential/datacenter proxy rotation
    - Anti-bot bypass
    - CAPTCHA solving
    - JavaScript rendering

    Requires BRIGHTDATA_API_KEY environment variable.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        zone: str = DEFAULT_ZONE,
        timeout: int = DEFAULT_TIMEOUT,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        country: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("BRIGHTDATA_API_KEY")
        self.zone = zone
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.country = country  # Optional country for geo-targeting

        self._client: Optional[httpx.AsyncClient] = None
        self._semaphore: Optional[asyncio.Semaphore] = None

    @property
    def available(self) -> bool:
        """Check if BrightData API key is configured."""
        return bool(self.api_key)

    async def _ensure_init(self):
        """Initialize HTTP client if needed."""
        if self._client is None:
            if not self.api_key:
                raise RuntimeError("BRIGHTDATA_API_KEY not configured")

            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_concurrent)

    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        await self._ensure_init()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def scrape(
        self,
        url: str,
        render_js: bool = True,
        wait_for: Optional[str] = None,
    ) -> BrightDataResult:
        """
        Scrape a single URL with BrightData Web Unlocker.

        Args:
            url: URL to scrape
            render_js: Enable JavaScript rendering (default: True)
            wait_for: CSS selector to wait for before returning

        Returns:
            BrightDataResult with HTML content or error
        """
        await self._ensure_init()
        start = time.time()

        try:
            async with self._semaphore:
                payload = {
                    "zone": self.zone,
                    "url": url,
                    "format": "raw",
                }

                if render_js:
                    payload["render_js"] = True

                if wait_for:
                    payload["wait_for"] = wait_for

                if self.country:
                    payload["country"] = self.country

                resp = await self._client.post(
                    "https://api.brightdata.com/request",
                    json=payload,
                )
                latency = int((time.time() - start) * 1000)

                if resp.status_code == 200:
                    html = resp.text
                    return BrightDataResult(
                        url=url,
                        html=html,
                        status_code=200,
                        latency_ms=latency,
                        content_length=len(html),
                        headers=dict(resp.headers),
                    )

                # Handle errors
                error_msg = f"BrightData returned {resp.status_code}"
                try:
                    error_data = resp.json()
                    if "error" in error_data:
                        error_msg = error_data["error"]
                    elif "message" in error_data:
                        error_msg = error_data["message"]
                except:
                    pass

                return BrightDataResult(
                    url=url,
                    html="",
                    status_code=resp.status_code,
                    latency_ms=latency,
                    content_length=0,
                    error=error_msg,
                )

        except httpx.TimeoutException:
            latency = int((time.time() - start) * 1000)
            return BrightDataResult(
                url=url,
                html="",
                status_code=0,
                latency_ms=latency,
                content_length=0,
                error="Timeout",
            )
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            return BrightDataResult(
                url=url,
                html="",
                status_code=0,
                latency_ms=latency,
                content_length=0,
                error=str(e),
            )

    async def scrape_batch(self, urls: List[str]) -> List[BrightDataResult]:
        """
        Scrape multiple URLs with BrightData.

        EXPENSIVE - use sparingly. Conservative rate limiting.

        Args:
            urls: List of URLs to scrape

        Returns:
            List of BrightDataResult for each URL
        """
        if not urls:
            return []

        await self._ensure_init()

        # Very conservative - BrightData is expensive
        tasks = [self.scrape(url) for url in urls]
        return await asyncio.gather(*tasks)

    async def scrape_with_screenshot(
        self,
        url: str,
        screenshot_path: str,
        full_page: bool = False,
    ) -> BrightDataResult:
        """
        Scrape URL and take screenshot with BrightData.

        Args:
            url: URL to scrape
            screenshot_path: Where to save screenshot
            full_page: Capture full page (default: False)

        Returns:
            BrightDataResult with HTML (screenshot saved to path)
        """
        await self._ensure_init()
        start = time.time()

        try:
            async with self._semaphore:
                payload = {
                    "zone": self.zone,
                    "url": url,
                    "format": "raw",
                    "render_js": True,
                    "screenshot": True,
                    "screenshot_full_page": full_page,
                }

                if self.country:
                    payload["country"] = self.country

                resp = await self._client.post(
                    "https://api.brightdata.com/request",
                    json=payload,
                )
                latency = int((time.time() - start) * 1000)

                if resp.status_code == 200:
                    # Response may contain both HTML and screenshot
                    content_type = resp.headers.get("content-type", "")

                    if "image" in content_type:
                        # Pure screenshot response
                        with open(screenshot_path, "wb") as f:
                            f.write(resp.content)
                        return BrightDataResult(
                            url=url,
                            html="",
                            status_code=200,
                            latency_ms=latency,
                            content_length=0,
                        )

                    # HTML response with screenshot in header or separate
                    html = resp.text
                    return BrightDataResult(
                        url=url,
                        html=html,
                        status_code=200,
                        latency_ms=latency,
                        content_length=len(html),
                        headers=dict(resp.headers),
                    )

                return BrightDataResult(
                    url=url,
                    html="",
                    status_code=resp.status_code,
                    latency_ms=latency,
                    content_length=0,
                    error=f"BrightData returned {resp.status_code}",
                )

        except Exception as e:
            latency = int((time.time() - start) * 1000)
            return BrightDataResult(
                url=url,
                html="",
                status_code=0,
                latency_ms=latency,
                content_length=0,
                error=str(e),
            )


# Convenience functions
async def scrape_brightdata(url: str, **kwargs) -> BrightDataResult:
    """Quick single-URL scrape with BrightData (EXPENSIVE)."""
    async with BrightData(**kwargs) as scraper:
        return await scraper.scrape(url)


async def scrape_brightdata_batch(urls: List[str], **kwargs) -> List[BrightDataResult]:
    """Quick batch scrape with BrightData (VERY EXPENSIVE)."""
    async with BrightData(**kwargs) as scraper:
        return await scraper.scrape_batch(urls)


def brightdata_available() -> bool:
    """Check if BrightData API key is configured."""
    return bool(os.getenv("BRIGHTDATA_API_KEY"))


# CLI test
if __name__ == "__main__":
    async def test():
        print("BrightData - External Proxy API")
        print("=" * 50)
        print("WARNING: This is EXPENSIVE - use sparingly!")
        print()

        if not brightdata_available():
            print("ERROR: BRIGHTDATA_API_KEY not set")
            return

        url = "https://example.com"
        result = await scrape_brightdata(url)

        print(f"URL: {result.url}")
        print(f"Status: {result.status_code}")
        print(f"Latency: {result.latency_ms}ms")
        print(f"Content length: {result.content_length}")
        print(f"Success: {result.success}")
        if result.error:
            print(f"Error: {result.error}")

    asyncio.run(test())
