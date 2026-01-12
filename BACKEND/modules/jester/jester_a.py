"""
JESTER_A - Direct HTTP Scraper (httpx)

The fastest scraping tier. Works for ~60% of sites.
No JS rendering, just direct HTTP requests.

Usage:
    from modules.jester.jester_a import JesterA

    scraper = JesterA()
    result = await scraper.scrape("https://example.com")

    # Batch scraping
    results = await scraper.scrape_batch(["https://a.com", "https://b.com"])
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("JESTER.A")

# Constants
DEFAULT_TIMEOUT = 15
DEFAULT_MAX_CONCURRENT = 100
MIN_VALID_HTML_LENGTH = 100
DEFAULT_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


@dataclass
class JesterAResult:
    """Result from JESTER_A scrape."""
    url: str
    html: str
    status_code: int
    latency_ms: int
    content_length: int
    error: Optional[str] = None
    headers: Dict[str, str] = None

    def __post_init__(self):
        if self.headers is None:
            self.headers = {}

    @property
    def success(self) -> bool:
        return self.html and len(self.html) >= MIN_VALID_HTML_LENGTH and not self.error


class JesterA:
    """
    JESTER_A: Direct HTTP scraper using httpx.

    Fastest tier - no JS rendering, pure HTTP requests.
    Good for static sites, APIs, simple pages.
    """

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        user_agent: str = DEFAULT_USER_AGENT,
        follow_redirects: bool = True,
    ):
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.user_agent = user_agent
        self.follow_redirects = follow_redirects

        self._client: Optional[httpx.AsyncClient] = None
        self._semaphore: Optional[asyncio.Semaphore] = None

    async def _ensure_init(self):
        """Initialize HTTP client if needed."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": self.user_agent},
                follow_redirects=self.follow_redirects,
                timeout=httpx.Timeout(self.timeout),
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

    async def scrape(self, url: str) -> JesterAResult:
        """
        Scrape a single URL with direct HTTP request.

        Args:
            url: URL to scrape

        Returns:
            JesterAResult with HTML content or error
        """
        await self._ensure_init()
        start = time.time()

        try:
            async with self._semaphore:
                resp = await self._client.get(url)
                latency = int((time.time() - start) * 1000)

                # Check for bot blocks
                if resp.status_code in (403, 429, 503):
                    return JesterAResult(
                        url=url,
                        html="",
                        status_code=resp.status_code,
                        latency_ms=latency,
                        content_length=0,
                        error=f"Blocked with status {resp.status_code}"
                    )

                html = resp.text
                return JesterAResult(
                    url=url,
                    html=html,
                    status_code=resp.status_code,
                    latency_ms=latency,
                    content_length=len(html),
                    headers=dict(resp.headers)
                )

        except httpx.TimeoutException:
            latency = int((time.time() - start) * 1000)
            return JesterAResult(
                url=url,
                html="",
                status_code=0,
                latency_ms=latency,
                content_length=0,
                error="Timeout"
            )
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            return JesterAResult(
                url=url,
                html="",
                status_code=0,
                latency_ms=latency,
                content_length=0,
                error=str(e)
            )

    async def scrape_batch(
        self,
        urls: List[str],
        rate_limit_per_domain: int = 10,
    ) -> List[JesterAResult]:
        """
        Scrape multiple URLs concurrently with per-domain rate limiting.

        Args:
            urls: List of URLs to scrape
            rate_limit_per_domain: Max concurrent requests per domain

        Returns:
            List of JesterAResult for each URL
        """
        await self._ensure_init()

        # Group by domain for rate limiting
        domain_semaphores: Dict[str, asyncio.Semaphore] = {}

        def get_domain(url: str) -> str:
            try:
                return urlparse(url).netloc
            except:
                return url

        async def scrape_with_domain_limit(url: str) -> JesterAResult:
            domain = get_domain(url)
            if domain not in domain_semaphores:
                domain_semaphores[domain] = asyncio.Semaphore(rate_limit_per_domain)

            async with domain_semaphores[domain]:
                return await self.scrape(url)

        tasks = [scrape_with_domain_limit(url) for url in urls]
        return await asyncio.gather(*tasks)


# Convenience function
async def scrape_a(url: str, **kwargs) -> JesterAResult:
    """Quick single-URL scrape with JESTER_A."""
    async with JesterA(**kwargs) as scraper:
        return await scraper.scrape(url)


async def scrape_a_batch(urls: List[str], **kwargs) -> List[JesterAResult]:
    """Quick batch scrape with JESTER_A."""
    async with JesterA(**kwargs) as scraper:
        return await scraper.scrape_batch(urls)


# CLI test
if __name__ == "__main__":
    async def test():
        print("JESTER_A - Direct HTTP Scraper")
        print("=" * 50)

        url = "https://example.com"
        result = await scrape_a(url)

        print(f"URL: {result.url}")
        print(f"Status: {result.status_code}")
        print(f"Latency: {result.latency_ms}ms")
        print(f"Content length: {result.content_length}")
        print(f"Success: {result.success}")
        if result.error:
            print(f"Error: {result.error}")

    asyncio.run(test())
