"""
JESTER_D - Custom Headless Browser (Playwright Hybrid)

Your own headless browser crawler built on Crawlee + Playwright.
The most capable tier - handles auth, complex JS, anti-bot measures.
~50 concurrent browser pages, slower but more powerful than Rod.

Usage:
    from modules.jester.jester_d import JesterD

    scraper = JesterD()
    result = await scraper.scrape("https://example.com")

    # With auth session
    scraper = JesterD(use_auth_sessions=True)
    result = await scraper.scrape("https://protected-site.com")
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger("JESTER.D")

# Constants
DEFAULT_TIMEOUT = 60
DEFAULT_MAX_CONCURRENT = 50
MIN_VALID_HTML_LENGTH = 100


@dataclass
class JesterDResult:
    """Result from jester_D (headless) scrape."""
    url: str
    html: str
    status_code: int
    latency_ms: int
    content_length: int
    title: str = ""
    content: str = ""
    entities: Dict[str, List[str]] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.html and len(self.html) >= MIN_VALID_HTML_LENGTH and not self.error

    @property
    def needs_js(self) -> bool:
        """JESTER_D always uses JS rendering."""
        return True


class JesterD:
    """
    JESTER_D: Custom headless browser crawler.

    Built on Crawlee + Playwright. The most capable scraping tier:
    - Full JavaScript execution
    - Cookie/session handling
    - Anti-bot bypass capabilities
    - Auth session injection (ROV)
    - Entity extraction integration

    Use when JESTER_A/B/C fail or for sites requiring authentication.
    """

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        use_auth_sessions: bool = True,
        auth_session_dir: Optional[str] = None,
        extract_entities: bool = False,
    ):
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.use_auth_sessions = use_auth_sessions
        self.auth_session_dir = auth_session_dir
        self.extract_entities = extract_entities

        self._available = None
        self._crawler_class = None

    def _check_available(self) -> bool:
        """Check if JESTER_D dependencies are available."""
        if self._available is None:
            try:
                from modules.jester.scraping.crawler import Drill, DrillConfig, CRAWLEE_AVAILABLE
                self._available = CRAWLEE_AVAILABLE
                self._crawler_class = (Drill, DrillConfig)
                if self._available:
                    logger.debug("JESTER_D (Crawlee/Playwright) available")
                else:
                    logger.warning("JESTER_D: Crawlee not installed")
            except ImportError as e:
                logger.warning(f"JESTER_D not available: {e}")
                self._available = False
        return self._available

    @property
    def available(self) -> bool:
        """Check if JESTER_D is available."""
        return self._check_available()

    async def scrape(self, url: str) -> JesterDResult:
        """
        Scrape a single URL with custom headless browser.

        Args:
            url: URL to scrape

        Returns:
            JesterDResult with rendered HTML content or error
        """
        if not self._check_available():
            return JesterDResult(
                url=url,
                html="",
                status_code=0,
                latency_ms=0,
                content_length=0,
                error="JESTER_D not available (Crawlee not installed)"
            )

        Drill, DrillConfig = self._crawler_class
        start = time.time()

        try:
            config = DrillConfig(
                max_pages=1,
                max_concurrent=1,
                request_timeout=self.timeout,
                extract_entities=self.extract_entities,
                generate_embeddings=False,
                index_to_elasticsearch=False,
                auth_use_sessions=self.use_auth_sessions,
                auth_session_dir=self.auth_session_dir,
            )

            crawler = Drill(config)
            result = await crawler.crawl_url(url)
            latency = int((time.time() - start) * 1000)

            if result and result.html:
                return JesterDResult(
                    url=url,
                    html=result.html,
                    status_code=result.status_code or 200,
                    latency_ms=latency,
                    content_length=len(result.html),
                    title=getattr(result, 'title', '') or '',
                    content=getattr(result, 'content', '') or '',
                    entities=getattr(result, 'entities', {}) or {},
                )

            return JesterDResult(
                url=url,
                html="",
                status_code=0,
                latency_ms=latency,
                content_length=0,
                error="No result from jester_D"
            )

        except Exception as e:
            latency = int((time.time() - start) * 1000)
            logger.error(f"JESTER_D scrape failed: {e}")
            return JesterDResult(
                url=url,
                html="",
                status_code=0,
                latency_ms=latency,
                content_length=0,
                error=str(e)
            )

    async def scrape_batch(self, urls: List[str]) -> List[JesterDResult]:
        """
        Scrape multiple URLs with headless browser.

        Note: JESTER_D batch is sequential by URL but uses
        concurrent page handling internally.

        Args:
            urls: List of URLs to scrape

        Returns:
            List of JesterDResult for each URL
        """
        if not urls:
            return []

        if not self._check_available():
            return [
                JesterDResult(
                    url=url,
                    html="",
                    status_code=0,
                    latency_ms=0,
                    content_length=0,
                    error="JESTER_D not available"
                )
                for url in urls
            ]

        Drill, DrillConfig = self._crawler_class
        start = time.time()

        try:
            config = DrillConfig(
                max_pages=len(urls),
                max_concurrent=min(self.max_concurrent, len(urls)),
                request_timeout=self.timeout,
                extract_entities=self.extract_entities,
                generate_embeddings=False,
                index_to_elasticsearch=False,
                auth_use_sessions=self.use_auth_sessions,
                auth_session_dir=self.auth_session_dir,
            )

            crawler = Drill(config)

            # Use batch crawl if available, otherwise sequential
            if hasattr(crawler, 'crawl_urls'):
                go_results = await crawler.crawl_urls(urls)
            else:
                # Sequential fallback
                go_results = []
                for url in urls:
                    result = await crawler.crawl_url(url)
                    go_results.append(result)

            results = []
            for i, url in enumerate(urls):
                if i < len(go_results) and go_results[i]:
                    r = go_results[i]
                    results.append(JesterDResult(
                        url=url,
                        html=r.html or "",
                        status_code=r.status_code or 200,
                        latency_ms=getattr(r, 'latency_ms', 0) or 0,
                        content_length=len(r.html or ""),
                        title=getattr(r, 'title', '') or '',
                        content=getattr(r, 'content', '') or '',
                        entities=getattr(r, 'entities', {}) or {},
                    ))
                else:
                    results.append(JesterDResult(
                        url=url,
                        html="",
                        status_code=0,
                        latency_ms=0,
                        content_length=0,
                        error="No result from jester_D"
                    ))

            return results

        except Exception as e:
            latency = int((time.time() - start) * 1000)
            logger.error(f"Batch JESTER_D failed: {e}")
            return [
                JesterDResult(
                    url=url,
                    html="",
                    status_code=0,
                    latency_ms=latency,
                    content_length=0,
                    error=str(e)
                )
                for url in urls
            ]


# Convenience functions
async def scrape_d(url: str, **kwargs) -> JesterDResult:
    """Quick single-URL scrape with JESTER_D (headless)."""
    scraper = JesterD(**kwargs)
    return await scraper.scrape(url)


async def scrape_d_batch(urls: List[str], **kwargs) -> List[JesterDResult]:
    """Quick batch scrape with JESTER_D (headless)."""
    scraper = JesterD(**kwargs)
    return await scraper.scrape_batch(urls)


def jester_d_available() -> bool:
    """Check if JESTER_D is available."""
    return JesterD().available


# CLI test
if __name__ == "__main__":
    import asyncio

    async def test():
        print("JESTER_D - Custom Headless Browser")
        print("=" * 50)

        scraper = JesterD()
        if not scraper.available:
            print("ERROR: JESTER_D not available")
            print("Install Crawlee: pip install crawlee[playwright]")
            return

        url = "https://example.com"
        result = await scraper.scrape(url)

        print(f"URL: {result.url}")
        print(f"Status: {result.status_code}")
        print(f"Latency: {result.latency_ms}ms")
        print(f"Content length: {result.content_length}")
        print(f"Title: {result.title}")
        print(f"Needs JS: {result.needs_js}")
        print(f"Success: {result.success}")
        if result.error:
            print(f"Error: {result.error}")

    asyncio.run(test())
