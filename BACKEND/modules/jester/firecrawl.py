"""
Firecrawl - External Firecrawl API

External paid API fallback (NOT part of JESTER).
Use when JESTER A/B/C/D all fail.

Usage:
    from modules.jester.firecrawl import Firecrawl, scrape_firecrawl

    scraper = Firecrawl()
    result = await scraper.scrape("https://example.com")

Requires:
    FIRECRAWL_API_KEY environment variable
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

logger = logging.getLogger("FIRECRAWL")

# Constants
DEFAULT_TIMEOUT = 60
DEFAULT_MAX_CONCURRENT = 10  # Firecrawl rate limits
MIN_VALID_HTML_LENGTH = 100
DEFAULT_BASE_URL = "https://api.firecrawl.dev/v1"


@dataclass
class FirecrawlResult:
    """Result from Firecrawl API scrape."""
    url: str
    html: str
    status_code: int
    latency_ms: int
    content_length: int
    markdown: str = ""
    metadata: Dict = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    @property
    def success(self) -> bool:
        return self.html and len(self.html) >= MIN_VALID_HTML_LENGTH and not self.error


class Firecrawl:
    """
    Firecrawl API wrapper.

    External paid service for scraping. Reliable fallback when
    JESTER A/B/C/D fail. Handles JavaScript, bypasses some anti-bot.

    Requires FIRECRAWL_API_KEY environment variable.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        use_cache: bool = True,
    ):
        self.api_key = api_key or os.getenv("FIRECRAWL_API_KEY")
        self.base_url = base_url
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.use_cache = use_cache

        self._client: Optional[httpx.AsyncClient] = None
        self._semaphore: Optional[asyncio.Semaphore] = None

    @property
    def available(self) -> bool:
        """Check if Firecrawl API key is configured."""
        return bool(self.api_key)

    async def _ensure_init(self):
        """Initialize HTTP client if needed."""
        if self._client is None:
            if not self.api_key:
                raise RuntimeError("FIRECRAWL_API_KEY not configured")

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
        formats: List[str] = None,
        only_main_content: bool = False,
    ) -> FirecrawlResult:
        """
        Scrape a single URL with Firecrawl API.

        Args:
            url: URL to scrape
            formats: Output formats (default: ["html"])
            only_main_content: Extract only main content (default: False)

        Returns:
            FirecrawlResult with HTML content or error
        """
        await self._ensure_init()
        start = time.time()

        if formats is None:
            formats = ["html"]

        try:
            async with self._semaphore:
                payload = {
                    "url": url,
                    "formats": formats,
                    "onlyMainContent": only_main_content,
                }

                # Use cache for faster responses (30 days)
                if self.use_cache:
                    payload["maxAge"] = 2592000000  # 30 days in ms

                resp = await self._client.post(
                    f"{self.base_url}/scrape",
                    json=payload,
                )
                latency = int((time.time() - start) * 1000)

                if resp.status_code == 200:
                    data = resp.json()
                    result_data = data.get("data", {})

                    html = result_data.get("html", "")
                    markdown = result_data.get("markdown", "")
                    metadata = result_data.get("metadata", {})

                    return FirecrawlResult(
                        url=url,
                        html=html,
                        status_code=200,
                        latency_ms=latency,
                        content_length=len(html),
                        markdown=markdown,
                        metadata=metadata,
                    )

                # Handle errors
                error_msg = f"Firecrawl returned {resp.status_code}"
                try:
                    error_data = resp.json()
                    if "error" in error_data:
                        error_msg = error_data["error"]
                except:
                    pass

                return FirecrawlResult(
                    url=url,
                    html="",
                    status_code=resp.status_code,
                    latency_ms=latency,
                    content_length=0,
                    error=error_msg,
                )

        except httpx.TimeoutException:
            latency = int((time.time() - start) * 1000)
            return FirecrawlResult(
                url=url,
                html="",
                status_code=0,
                latency_ms=latency,
                content_length=0,
                error="Timeout",
            )
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            return FirecrawlResult(
                url=url,
                html="",
                status_code=0,
                latency_ms=latency,
                content_length=0,
                error=str(e),
            )

    async def scrape_batch(self, urls: List[str]) -> List[FirecrawlResult]:
        """
        Scrape multiple URLs with Firecrawl API.

        Rate limited to avoid API throttling.

        Args:
            urls: List of URLs to scrape

        Returns:
            List of FirecrawlResult for each URL
        """
        if not urls:
            return []

        await self._ensure_init()

        tasks = [self.scrape(url) for url in urls]
        return await asyncio.gather(*tasks)

    async def crawl(
        self,
        url: str,
        max_depth: int = 2,
        max_pages: int = 10,
        formats: List[str] = None,
    ) -> List[FirecrawlResult]:
        """
        Crawl a website starting from URL (Firecrawl's crawl endpoint).

        Args:
            url: Starting URL
            max_depth: Maximum crawl depth
            max_pages: Maximum pages to crawl
            formats: Output formats

        Returns:
            List of FirecrawlResult for crawled pages
        """
        await self._ensure_init()

        if formats is None:
            formats = ["html"]

        try:
            # Start crawl job
            resp = await self._client.post(
                f"{self.base_url}/crawl",
                json={
                    "url": url,
                    "maxDepth": max_depth,
                    "limit": max_pages,
                    "scrapeOptions": {
                        "formats": formats,
                    },
                },
            )

            if resp.status_code != 200:
                return [FirecrawlResult(
                    url=url,
                    html="",
                    status_code=resp.status_code,
                    latency_ms=0,
                    content_length=0,
                    error=f"Crawl start failed: {resp.status_code}",
                )]

            data = resp.json()
            job_id = data.get("id")

            if not job_id:
                return [FirecrawlResult(
                    url=url,
                    html="",
                    status_code=0,
                    latency_ms=0,
                    content_length=0,
                    error="No job ID returned",
                )]

            # Poll for completion
            results = []
            while True:
                await asyncio.sleep(2)  # Poll every 2 seconds

                status_resp = await self._client.get(f"{self.base_url}/crawl/{job_id}")
                status_data = status_resp.json()

                status = status_data.get("status")
                if status == "completed":
                    for page in status_data.get("data", []):
                        results.append(FirecrawlResult(
                            url=page.get("url", url),
                            html=page.get("html", ""),
                            status_code=200,
                            latency_ms=0,
                            content_length=len(page.get("html", "")),
                            markdown=page.get("markdown", ""),
                            metadata=page.get("metadata", {}),
                        ))
                    break
                elif status == "failed":
                    return [FirecrawlResult(
                        url=url,
                        html="",
                        status_code=0,
                        latency_ms=0,
                        content_length=0,
                        error=status_data.get("error", "Crawl failed"),
                    )]

            return results

        except Exception as e:
            return [FirecrawlResult(
                url=url,
                html="",
                status_code=0,
                latency_ms=0,
                content_length=0,
                error=str(e),
            )]


# Convenience functions
async def scrape_firecrawl(url: str, **kwargs) -> FirecrawlResult:
    """Quick single-URL scrape with Firecrawl."""
    async with Firecrawl(**kwargs) as scraper:
        return await scraper.scrape(url)


async def scrape_firecrawl_batch(urls: List[str], **kwargs) -> List[FirecrawlResult]:
    """Quick batch scrape with Firecrawl."""
    async with Firecrawl(**kwargs) as scraper:
        return await scraper.scrape_batch(urls)


def firecrawl_available() -> bool:
    """Check if Firecrawl API key is configured."""
    return bool(os.getenv("FIRECRAWL_API_KEY"))


# CLI test
if __name__ == "__main__":
    async def test():
        print("Firecrawl - External API")
        print("=" * 50)

        if not firecrawl_available():
            print("ERROR: FIRECRAWL_API_KEY not set")
            return

        url = "https://example.com"
        result = await scrape_firecrawl(url)

        print(f"URL: {result.url}")
        print(f"Status: {result.status_code}")
        print(f"Latency: {result.latency_ms}ms")
        print(f"Content length: {result.content_length}")
        print(f"Success: {result.success}")
        if result.error:
            print(f"Error: {result.error}")

    asyncio.run(test())
