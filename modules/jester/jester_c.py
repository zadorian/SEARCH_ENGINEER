"""
JESTER_C - Rod Go JS Renderer

JS rendering for SPAs and dynamic sites using Go's Rod library.
~100 concurrent browser pages, faster than Python Playwright (~2x).

Usage:
    from modules.jester.jester_c import JesterC

    scraper = JesterC()
    result = await scraper.scrape("https://example.com")

    # Batch scraping with screenshots
    results, screenshots = await scraper.scrape_batch_with_screenshots(
        ["https://a.com", "https://b.com"],
        screenshot_dir="/tmp/screenshots"
    )
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

logger = logging.getLogger("JESTER.C")

# Constants
DEFAULT_TIMEOUT = 45
DEFAULT_MAX_CONCURRENT = 100
MIN_VALID_HTML_LENGTH = 100

# Go binary location
GO_BIN_DIR = Path(__file__).parent / "scraping" / "go" / "bin"
ROD_CRAWLER_BIN = GO_BIN_DIR / "rod_crawler"


@dataclass
class OutlinkRecord:
    """External link found on the page."""
    url: str
    domain: str
    anchor_text: str
    is_nofollow: bool = False
    is_external: bool = True


@dataclass
class ScreenshotResult:
    """Result of a screenshot operation."""
    url: str
    title: str = ""
    screenshot_path: str = ""
    rule_name: str = ""
    full_page: bool = False
    error: str = ""


@dataclass
class ScreenshotRule:
    """Rule for when to take screenshots."""
    name: str
    rule_type: str  # url_contains, url_regex, content_contains, content_min_length, title_contains, domain, always
    value: str = ""
    keywords: List[str] = field(default_factory=list)
    min_length: int = 0
    domains: List[str] = field(default_factory=list)
    full_page: bool = False
    quality: int = 90
    format: str = "png"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.rule_type,
            "value": self.value,
            "keywords": self.keywords,
            "min_length": self.min_length,
            "domains": self.domains,
            "full_page": self.full_page,
            "quality": self.quality,
            "format": self.format,
        }


@dataclass
class JesterCResult:
    """Result from jester_C (Rod) scrape."""
    url: str
    html: str
    status_code: int
    latency_ms: int
    content_length: int
    title: str = ""
    content: str = ""
    outlinks: List[OutlinkRecord] = field(default_factory=list)
    internal_links: List[str] = field(default_factory=list)
    screenshot_path: Optional[str] = None
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.html and len(self.html) >= MIN_VALID_HTML_LENGTH and not self.error

    @property
    def needs_js(self) -> bool:
        """Rod always renders JS."""
        return True


class JesterC:
    """
    JESTER_C: Rod Go JS renderer.

    Uses Go's Rod library for headless Chrome rendering.
    ~100 concurrent browser pages, faster than Python Playwright.
    Use this for SPAs, React/Vue/Angular sites, or pages requiring JS.
    """

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        include_html: bool = True,
    ):
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.include_html = include_html

        self._go_bridge = None
        self._available = None

    def _check_available(self) -> bool:
        """Check if Rod binary is available."""
        if self._available is None:
            import os
            self._available = ROD_CRAWLER_BIN.exists() and os.access(ROD_CRAWLER_BIN, os.X_OK)
            if self._available:
                logger.debug("Rod crawler binary available")
            else:
                logger.warning(f"Rod crawler not found at {ROD_CRAWLER_BIN}")
        return self._available

    async def _ensure_init(self):
        """Initialize Go bridge if needed."""
        if self._go_bridge is None:
            if not self._check_available():
                raise RuntimeError(f"Rod crawler not available at {ROD_CRAWLER_BIN}")

            try:
                from modules.jester.scraping.web.go_bridge import GoBridge
                self._go_bridge = GoBridge()
            except ImportError:
                from modules.jester.scraping.go_bridge import GoBridge
                self._go_bridge = GoBridge()

    @property
    def available(self) -> bool:
        """Check if JESTER_C is available."""
        return self._check_available()

    async def scrape(self, url: str) -> JesterCResult:
        """
        Scrape a single URL with Rod Go JS renderer.

        Args:
            url: URL to scrape

        Returns:
            JesterCResult with rendered HTML content or error
        """
        await self._ensure_init()
        start = time.time()

        try:
            results = await self._go_bridge.crawl_with_rod(
                [url],
                max_concurrent=1,
                timeout=self.timeout,
                include_html=self.include_html,
            )
            latency = int((time.time() - start) * 1000)

            if results and len(results) > 0:
                r = results[0]

                outlinks = []
                for ol in (r.outlinks or []):
                    outlinks.append(OutlinkRecord(
                        url=ol.url,
                        domain=ol.domain,
                        anchor_text=ol.anchor_text,
                        is_nofollow=ol.is_nofollow,
                        is_external=ol.is_external,
                    ))

                return JesterCResult(
                    url=url,
                    html=r.html or "",
                    status_code=r.status_code,
                    latency_ms=latency,
                    content_length=len(r.html or ""),
                    title=r.title or "",
                    content=r.content or "",
                    outlinks=outlinks,
                    internal_links=r.internal_links or [],
                    error=r.error if r.error else None,
                )

            return JesterCResult(
                url=url,
                html="",
                status_code=0,
                latency_ms=latency,
                content_length=0,
                error="No result from Rod"
            )

        except Exception as e:
            latency = int((time.time() - start) * 1000)
            return JesterCResult(
                url=url,
                html="",
                status_code=0,
                latency_ms=latency,
                content_length=0,
                error=str(e)
            )

    async def scrape_batch(self, urls: List[str]) -> List[JesterCResult]:
        """
        Scrape multiple URLs in a SINGLE Go call with JS rendering.

        Args:
            urls: List of URLs to scrape

        Returns:
            List of JesterCResult for each URL
        """
        if not urls:
            return []

        await self._ensure_init()
        start = time.time()

        try:
            go_results = await self._go_bridge.crawl_with_rod(
                urls,
                max_concurrent=self.max_concurrent,
                timeout=self.timeout,
                include_html=self.include_html,
            )

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

                result_map[r.url] = JesterCResult(
                    url=r.url,
                    html=r.html or "",
                    status_code=r.status_code,
                    latency_ms=r.latency_ms,
                    content_length=len(r.html or ""),
                    title=r.title or "",
                    content=r.content or "",
                    outlinks=outlinks,
                    internal_links=r.internal_links or [],
                    error=r.error if r.error else None,
                )

            results = []
            for url in urls:
                if url in result_map:
                    results.append(result_map[url])
                else:
                    results.append(JesterCResult(
                        url=url,
                        html="",
                        status_code=0,
                        latency_ms=0,
                        content_length=0,
                        error="No result from Rod"
                    ))

            return results

        except Exception as e:
            logger.error(f"Batch JESTER_C failed: {e}")
            latency = int((time.time() - start) * 1000)
            return [
                JesterCResult(
                    url=url,
                    html="",
                    status_code=0,
                    latency_ms=latency,
                    content_length=0,
                    error=str(e)
                )
                for url in urls
            ]

    async def screenshot(
        self,
        url: str,
        output_path: str,
        full_page: bool = False,
        quality: int = 90,
    ) -> ScreenshotResult:
        """
        Take a screenshot of a single URL.

        Args:
            url: URL to screenshot
            output_path: Where to save the screenshot
            full_page: Capture full scrollable page
            quality: JPEG quality (0-100)

        Returns:
            ScreenshotResult with path to saved screenshot
        """
        await self._ensure_init()

        try:
            result = await self._go_bridge.take_screenshot(
                url,
                output_path,
                full_page=full_page,
                quality=quality,
                timeout=self.timeout,
            )
            return ScreenshotResult(
                url=result.url,
                title=result.title,
                screenshot_path=result.screenshot_path,
                full_page=result.full_page,
                error=result.error,
            )
        except Exception as e:
            return ScreenshotResult(
                url=url,
                error=str(e),
            )

    async def scrape_batch_with_screenshots(
        self,
        urls: List[str],
        screenshot_dir: str,
        rules: Optional[List[ScreenshotRule]] = None,
        screenshot_all: bool = False,
    ) -> Tuple[List[JesterCResult], List[ScreenshotResult]]:
        """
        Scrape URLs with rule-based screenshot capture.

        Args:
            urls: List of URLs to scrape
            screenshot_dir: Directory to save screenshots
            rules: List of ScreenshotRule for when to capture
            screenshot_all: Screenshot every page

        Returns:
            Tuple of (crawl_results, screenshot_results)
        """
        if not urls:
            return [], []

        await self._ensure_init()

        try:
            go_rules = [r.to_dict() for r in rules] if rules else None

            # Import the dataclass from go_bridge
            from modules.jester.scraping.web.go_bridge import ScreenshotRule as GoScreenshotRule

            crawl_results_raw, screenshot_results_raw = await self._go_bridge.crawl_with_screenshots(
                urls,
                screenshot_dir,
                rules=[GoScreenshotRule(**r) for r in go_rules] if go_rules else None,
                screenshot_all=screenshot_all,
                max_concurrent=self.max_concurrent,
                timeout=self.timeout,
            )

            # Convert results
            crawl_results = []
            for r in crawl_results_raw:
                outlinks = []
                for ol in (r.outlinks or []):
                    outlinks.append(OutlinkRecord(
                        url=ol.url,
                        domain=ol.domain,
                        anchor_text=ol.anchor_text,
                        is_nofollow=ol.is_nofollow,
                        is_external=ol.is_external,
                    ))

                crawl_results.append(JesterCResult(
                    url=r.url,
                    html=r.html or "",
                    status_code=r.status_code,
                    latency_ms=r.latency_ms,
                    content_length=len(r.html or ""),
                    title=r.title or "",
                    content=r.content or "",
                    outlinks=outlinks,
                    internal_links=r.internal_links or [],
                    error=r.error if r.error else None,
                ))

            screenshot_results = []
            for s in screenshot_results_raw:
                screenshot_results.append(ScreenshotResult(
                    url=s.url,
                    title=s.title,
                    screenshot_path=s.screenshot_path,
                    rule_name=s.rule_name,
                    full_page=s.full_page,
                    error=s.error,
                ))

            return crawl_results, screenshot_results

        except Exception as e:
            logger.error(f"Batch with screenshots failed: {e}")
            return [], []


# Convenience functions
async def scrape_c(url: str, **kwargs) -> JesterCResult:
    """Quick single-URL scrape with JESTER_C (Rod)."""
    scraper = JesterC(**kwargs)
    return await scraper.scrape(url)


async def scrape_c_batch(urls: List[str], **kwargs) -> List[JesterCResult]:
    """Quick batch scrape with JESTER_C (Rod)."""
    scraper = JesterC(**kwargs)
    return await scraper.scrape_batch(urls)


async def screenshot_c(url: str, output_path: str, **kwargs) -> ScreenshotResult:
    """Quick screenshot with JESTER_C (Rod)."""
    scraper = JesterC(**kwargs)
    return await scraper.screenshot(url, output_path)


def rod_available() -> bool:
    """Check if Rod binary is available."""
    return JesterC().available


# CLI test
if __name__ == "__main__":
    import asyncio

    async def test():
        print("JESTER_C - Rod Go JS Renderer")
        print("=" * 50)

        scraper = JesterC()
        if not scraper.available:
            print("ERROR: Rod binary not available")
            print(f"Expected at: {ROD_CRAWLER_BIN}")
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
