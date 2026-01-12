"""
JESTER_B - Colly Go Crawler

High-performance static HTML scraping using Go's Colly library.
500+ concurrent requests, much faster than Python for static sites.

Usage:
    from modules.jester.jester_b import JesterB

    scraper = JesterB()
    result = await scraper.scrape("https://example.com")

    # Batch scraping (SINGLE Go call - very efficient)
    results = await scraper.scrape_batch(["https://a.com", "https://b.com"])
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger("JESTER.B")

# Constants
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_CONCURRENT = 500
MIN_VALID_HTML_LENGTH = 100

# Go binary location
GO_BIN_DIR = Path(__file__).parent / "scraping" / "go" / "bin"
COLLY_CRAWLER_BIN = GO_BIN_DIR / "colly_crawler"


@dataclass
class OutlinkRecord:
    """External link found on the page."""
    url: str
    domain: str
    anchor_text: str
    is_nofollow: bool = False
    is_external: bool = True


@dataclass
class JesterBResult:
    """Result from JESTER_B (Colly) scrape."""
    url: str
    html: str
    status_code: int
    latency_ms: int
    content_length: int
    title: str = ""
    content: str = ""  # Text content (no HTML)
    outlinks: List[OutlinkRecord] = field(default_factory=list)
    internal_links: List[str] = field(default_factory=list)
    needs_js: bool = False
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.html and len(self.html) >= MIN_VALID_HTML_LENGTH and not self.error


class JesterB:
    """
    JESTER_B: High-performance Colly Go crawler.

    Uses Go's Colly library for 500+ concurrent static HTML requests.
    Much faster than Python httpx for bulk crawling.
    Cannot render JavaScript - use JESTER_C for JS-heavy sites.
    """

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        user_agent: Optional[str] = None,
        delay_ms: int = 0,
    ):
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.user_agent = user_agent
        self.delay_ms = delay_ms

        self._go_bridge = None
        self._available = None

    def _check_available(self) -> bool:
        """Check if Colly binary is available."""
        if self._available is None:
            import os
            self._available = COLLY_CRAWLER_BIN.exists() and os.access(COLLY_CRAWLER_BIN, os.X_OK)
            if self._available:
                logger.debug("Colly crawler binary available")
            else:
                logger.warning(f"Colly crawler not found at {COLLY_CRAWLER_BIN}")
        return self._available

    async def _ensure_init(self):
        """Initialize Go bridge if needed."""
        if self._go_bridge is None:
            if not self._check_available():
                raise RuntimeError(f"Colly crawler not available at {COLLY_CRAWLER_BIN}")

            # Import Go bridge
            try:
                from modules.jester.scraping.web.go_bridge import GoBridge
                self._go_bridge = GoBridge()
            except ImportError:
                from modules.jester.scraping.go_bridge import GoBridge
                self._go_bridge = GoBridge()

    @property
    def available(self) -> bool:
        """Check if JESTER_B is available."""
        return self._check_available()

    async def scrape(self, url: str) -> JesterBResult:
        """
        Scrape a single URL with Colly Go crawler.

        Args:
            url: URL to scrape

        Returns:
            JesterBResult with HTML content or error
        """
        await self._ensure_init()
        start = time.time()

        try:
            results, js_required = await self._go_bridge.crawl_static_html(
                [url],
                max_concurrent=1,
                timeout=self.timeout,
                delay_ms=self.delay_ms,
                user_agent=self.user_agent,
                detect_js_required=True,
            )
            latency = int((time.time() - start) * 1000)

            if results and len(results) > 0:
                r = results[0]

                # Convert outlinks
                outlinks = []
                for ol in (r.outlinks or []):
                    outlinks.append(OutlinkRecord(
                        url=ol.url,
                        domain=ol.domain,
                        anchor_text=ol.anchor_text,
                        is_nofollow=ol.is_nofollow,
                        is_external=ol.is_external,
                    ))

                return JesterBResult(
                    url=url,
                    html=r.html or "",
                    status_code=r.status_code,
                    latency_ms=latency,
                    content_length=len(r.html or ""),
                    title=r.title or "",
                    content=r.content or "",
                    outlinks=outlinks,
                    internal_links=r.internal_links or [],
                    needs_js=r.needs_js,
                    error=r.error if r.error else None,
                )

            return JesterBResult(
                url=url,
                html="",
                status_code=0,
                latency_ms=latency,
                content_length=0,
                error="No result from Colly"
            )

        except Exception as e:
            latency = int((time.time() - start) * 1000)
            return JesterBResult(
                url=url,
                html="",
                status_code=0,
                latency_ms=latency,
                content_length=0,
                error=str(e)
            )

    async def scrape_batch(self, urls: List[str]) -> List[JesterBResult]:
        """
        Scrape multiple URLs in a SINGLE Go call.

        This is the most efficient way to use JESTER_B - one Go process
        handles all URLs with 500+ concurrent connections.

        Args:
            urls: List of URLs to scrape

        Returns:
            List of JesterBResult for each URL
        """
        if not urls:
            return []

        await self._ensure_init()
        start = time.time()

        try:
            go_results, js_required = await self._go_bridge.crawl_static_html(
                urls,
                max_concurrent=self.max_concurrent,
                timeout=self.timeout,
                delay_ms=self.delay_ms,
                user_agent=self.user_agent,
                detect_js_required=True,
            )

            # Map results by URL
            result_map = {}
            for r in (go_results or []):
                outlinks = []
                for ol in (r.outlinks or []):
                    outlinks.append(OutlinkRecord(
                        url=ol.url,
                        domain=ol.domain,
                        anchor_text=ol.anchor_text,
                        is_nofollow=ol.is_nofollow,
                        is_external=ol.is_external,
                    ))

                result_map[r.url] = JesterBResult(
                    url=r.url,
                    html=r.html or "",
                    status_code=r.status_code,
                    latency_ms=r.latency_ms,
                    content_length=len(r.html or ""),
                    title=r.title or "",
                    content=r.content or "",
                    outlinks=outlinks,
                    internal_links=r.internal_links or [],
                    needs_js=r.needs_js,
                    error=r.error if r.error else None,
                )

            # Return in original order, with errors for missing URLs
            results = []
            for url in urls:
                if url in result_map:
                    results.append(result_map[url])
                else:
                    results.append(JesterBResult(
                        url=url,
                        html="",
                        status_code=0,
                        latency_ms=0,
                        content_length=0,
                        error="No result from Colly"
                    ))

            return results

        except Exception as e:
            logger.error(f"Batch JESTER_B failed: {e}")
            latency = int((time.time() - start) * 1000)
            return [
                JesterBResult(
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
async def scrape_b(url: str, **kwargs) -> JesterBResult:
    """Quick single-URL scrape with JESTER_B (Colly)."""
    scraper = JesterB(**kwargs)
    return await scraper.scrape(url)


async def scrape_b_batch(urls: List[str], **kwargs) -> List[JesterBResult]:
    """Quick batch scrape with JESTER_B (Colly)."""
    scraper = JesterB(**kwargs)
    return await scraper.scrape_batch(urls)


def colly_available() -> bool:
    """Check if Colly binary is available."""
    return JesterB().available


# CLI test
if __name__ == "__main__":
    import asyncio

    async def test():
        print("JESTER_B - Colly Go Crawler")
        print("=" * 50)

        scraper = JesterB()
        if not scraper.available:
            print("ERROR: Colly binary not available")
            print(f"Expected at: {COLLY_CRAWLER_BIN}")
            return

        url = "https://example.com"
        result = await scraper.scrape(url)

        print(f"URL: {result.url}")
        print(f"Status: {result.status_code}")
        print(f"Latency: {result.latency_ms}ms")
        print(f"Content length: {result.content_length}")
        print(f"Title: {result.title}")
        print(f"Needs JS: {result.needs_js}")
        print(f"Outlinks: {len(result.outlinks)}")
        print(f"Success: {result.success}")
        if result.error:
            print(f"Error: {result.error}")

    asyncio.run(test())
