"""
DRILL Go Bridge - Call Go binaries for heavy lifting

Why Go for heavy operations:
- WAT file processing: Go is 10x faster than Python for parsing gzipped WAT files
- Link deduplication: Go's FarmHash + memory efficiency handles billions of links
- Concurrent I/O: Go's goroutines are much lighter than Python async
- HTTP crawling: Colly can do 500+ concurrent requests vs Python's ~50
- JS rendering: Rod can handle ~100 concurrent browser pages vs Python's ~50

This bridge lets DRILL use Go binaries for heavy lifting while keeping
Python for orchestration, configuration, and integration.

v1.5.0: Added colly_crawler for high-performance static HTML crawling.
v1.5.1: Added rod_crawler for JS rendering, moved binaries to linklater.
v1.5.2: Added screenshot capability with rules-based triggering.
"""

import asyncio
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional, Iterator, Tuple
from dataclasses import dataclass, field

# Path to DRILL Go binaries (in linklater module)
DRILL_GO_BIN = Path(__file__).parent / "go" / "bin"

# Binary paths
COLLY_CRAWLER_BIN = DRILL_GO_BIN / "colly_crawler"
ROD_CRAWLER_BIN = DRILL_GO_BIN / "rod_crawler"

# Legacy GlobalLinks binaries (for backward compatibility)
# Use GLOBALLINKS_BIN_PATH env var to override location
try:
    _DEFAULT_GLOBALLINKS = Path(__file__).resolve().parents[5] / "categorizer-filterer" / "globallinks" / "globallinks-with-outlinker" / "bin"
except IndexError:
    _DEFAULT_GLOBALLINKS = Path("/nonexistent")  # Will use GLOBALLINKS_BIN_PATH env var if needed
GLOBALLINKS_BIN = Path(os.getenv("GLOBALLINKS_BIN_PATH", str(_DEFAULT_GLOBALLINKS)))
OUTLINKER_BIN = GLOBALLINKS_BIN / "outlinker"
LINKSAPI_BIN = GLOBALLINKS_BIN / "linksapi"
STORELINKS_BIN = GLOBALLINKS_BIN / "storelinks"


def _check_binaries() -> Dict[str, bool]:
    """Check which Go binaries are available."""
    return {
        # DRILL binaries (in linklater)
        "colly_crawler": COLLY_CRAWLER_BIN.exists() and os.access(COLLY_CRAWLER_BIN, os.X_OK),
        "rod_crawler": ROD_CRAWLER_BIN.exists() and os.access(ROD_CRAWLER_BIN, os.X_OK),
        # Legacy GlobalLinks binaries
        "outlinker": OUTLINKER_BIN.exists() and os.access(OUTLINKER_BIN, os.X_OK),
        "linksapi": LINKSAPI_BIN.exists() and os.access(LINKSAPI_BIN, os.X_OK),
        "storelinks": STORELINKS_BIN.exists() and os.access(STORELINKS_BIN, os.X_OK),
    }


GO_AVAILABLE = _check_binaries()


@dataclass
class OutlinkerResult:
    """Result from outlinker extraction."""
    source_domain: str
    target_domain: str
    target_url: str
    anchor_text: str
    nofollow: bool
    source_url: str


@dataclass
class OutlinkRecord:
    """Outlink extracted by Colly crawler."""
    url: str
    domain: str
    anchor_text: str
    is_nofollow: bool
    is_external: bool


@dataclass
class CrawlResult:
    """Result from Colly crawler for a single URL."""
    url: str
    status_code: int = 0
    content_type: str = ""
    title: str = ""
    content: str = ""
    html: str = ""
    outlinks: List[OutlinkRecord] = field(default_factory=list)
    internal_links: List[str] = field(default_factory=list)
    needs_js: bool = False
    error: str = ""
    latency_ms: int = 0


@dataclass
class CrawlStats:
    """Statistics from a crawl operation."""
    total: int = 0
    success: int = 0
    failed: int = 0
    needs_js: int = 0
    total_time_ms: int = 0


@dataclass
class ScreenshotRule:
    """Rule for when to take screenshots during crawling."""
    name: str
    rule_type: str  # url_contains, url_regex, content_contains, content_min_length, title_contains, domain, always
    value: str = ""
    keywords: List[str] = field(default_factory=list)
    min_length: int = 0
    domains: List[str] = field(default_factory=list)
    full_page: bool = False
    quality: int = 90  # JPEG quality
    format: str = "png"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
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
class ScreenshotResult:
    """Result of a screenshot operation."""
    url: str
    title: str = ""
    screenshot_path: str = ""
    rule_name: str = ""
    full_page: bool = False
    error: str = ""

    @staticmethod
    def from_crawl_result(data: Dict[str, Any]) -> Optional['ScreenshotResult']:
        """Create ScreenshotResult from crawl result if screenshot was taken."""
        if data.get("screenshot_path"):
            return ScreenshotResult(
                url=data.get("url", ""),
                title=data.get("title", ""),
                screenshot_path=data.get("screenshot_path", ""),
                rule_name=data.get("screenshot_rule", ""),
            )
        return None


class GoBridge:
    """
    Bridge to GlobalLinks Go binaries.

    Provides Python interface to Go's high-performance link processing.
    """

    def __init__(self):
        self.available = GO_AVAILABLE

    def is_available(self, binary: str) -> bool:
        """Check if a Go binary is available."""
        return self.available.get(binary, False)

    # =========================================================================
    # OUTLINKER - Extract links from WAT files
    # =========================================================================

    async def extract_links_from_wat(
        self,
        wat_file: str,
        target_domain: Optional[str] = None,
        country_tlds: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        output_file: Optional[str] = None,
    ) -> List[OutlinkerResult]:
        """
        Extract links from a WAT file using Go's outlinker.

        This is MUCH faster than Python for large WAT files.

        Args:
            wat_file: Path to WAT.gz file
            target_domain: Filter to links TO this domain
            country_tlds: Filter to links TO these TLDs (e.g., [".ru", ".ky"])
            keywords: Filter to links with these keywords in anchor/URL
            output_file: Write results to this file

        Returns:
            List of OutlinkerResult objects
        """
        if not self.is_available("outlinker"):
            raise RuntimeError("outlinker binary not available")

        cmd = [str(OUTLINKER_BIN), "extract", wat_file]

        if target_domain:
            cmd.extend(["--target-domain", target_domain])

        if country_tlds:
            cmd.extend(["--country-tlds", ",".join(country_tlds)])

        if keywords:
            cmd.extend(["--keywords", ",".join(keywords)])

        if output_file:
            cmd.extend(["--output", output_file])
        else:
            cmd.append("--json")

        # Run Go binary
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"outlinker failed: {stderr.decode()}")

        # Parse JSON output
        results = []
        for line in stdout.decode().strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                results.append(OutlinkerResult(
                    source_domain=data.get("source_domain", ""),
                    target_domain=data.get("target_domain", ""),
                    target_url=data.get("target_url", ""),
                    anchor_text=data.get("anchor_text", ""),
                    nofollow=data.get("nofollow", False),
                    source_url=data.get("source_url", ""),
                ))
            except json.JSONDecodeError:
                continue

        return results

    async def search_links(
        self,
        domain: str,
        archive: str = "CC-MAIN-2024-10",
        max_results: int = 1000,
    ) -> List[OutlinkerResult]:
        """
        Search for links to a domain using outlinker search.

        Args:
            domain: Target domain to find links to
            archive: Common Crawl archive to search
            max_results: Maximum results to return

        Returns:
            List of OutlinkerResult objects
        """
        if not self.is_available("outlinker"):
            raise RuntimeError("outlinker binary not available")

        cmd = [
            str(OUTLINKER_BIN), "search",
            "--domain", domain,
            "--archive", archive,
            "--max", str(max_results),
            "--json",
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"outlinker search failed: {stderr.decode()}")

        results = []
        for line in stdout.decode().strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                results.append(OutlinkerResult(
                    source_domain=data.get("source_domain", ""),
                    target_domain=data.get("target_domain", ""),
                    target_url=data.get("target_url", ""),
                    anchor_text=data.get("anchor_text", ""),
                    nofollow=data.get("nofollow", False),
                    source_url=data.get("source_url", ""),
                ))
            except json.JSONDecodeError:
                continue

        return results

    # =========================================================================
    # LINKSAPI - Query the link database
    # =========================================================================

    async def query_backlinks(
        self,
        domain: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Query backlinks to a domain from the link database.

        Args:
            domain: Target domain
            limit: Maximum results

        Returns:
            List of backlink records
        """
        if not self.is_available("linksapi"):
            raise RuntimeError("linksapi binary not available")

        cmd = [
            str(LINKSAPI_BIN), "search",
            "--target", domain,
            "--limit", str(limit),
            "--json",
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            # linksapi might not be running, return empty
            return []

        results = []
        for line in stdout.decode().strip().split("\n"):
            if not line:
                continue
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        return results

    async def query_outlinks(
        self,
        domain: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Query outlinks from a domain.

        Args:
            domain: Source domain
            limit: Maximum results

        Returns:
            List of outlink records
        """
        if not self.is_available("linksapi"):
            raise RuntimeError("linksapi binary not available")

        cmd = [
            str(LINKSAPI_BIN), "search",
            "--source", domain,
            "--limit", str(limit),
            "--json",
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            return []

        results = []
        for line in stdout.decode().strip().split("\n"):
            if not line:
                continue
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        return results

    # =========================================================================
    # COLLY_CRAWLER - High-performance static HTML crawling
    # =========================================================================

    async def crawl_static_html(
        self,
        urls: List[str],
        max_concurrent: int = 500,
        timeout: int = 30,
        delay_ms: int = 0,
        user_agent: Optional[str] = None,
        country_tlds: Optional[List[str]] = None,
        url_keywords: Optional[List[str]] = None,
        detect_js_required: bool = True,
    ) -> Tuple[List[CrawlResult], List[str]]:
        """
        Crawl URLs using Go/Colly for high-speed static HTML crawling.

        This is MUCH faster than Python crawlers for static HTML:
        - Go: 500+ concurrent requests
        - Python: ~50 concurrent requests

        Args:
            urls: List of URLs to crawl
            max_concurrent: Max concurrent requests (default: 500)
            timeout: Request timeout in seconds (default: 30)
            delay_ms: Delay between requests in ms (default: 0)
            user_agent: Custom user agent
            country_tlds: Filter outlinks to these TLDs
            url_keywords: Filter outlinks containing these keywords
            detect_js_required: Detect pages needing JS rendering

        Returns:
            Tuple of (results, js_required_urls)
            - results: List of CrawlResult for successfully crawled pages
            - js_required_urls: List of URLs that need Playwright (JS rendering)
        """
        if not self.is_available("colly_crawler"):
            raise RuntimeError("colly_crawler binary not available")

        if not urls:
            return [], []

        # Create temp file for URL input
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(urls, f)
            url_file = f.name

        # Create temp file for output
        output_file = tempfile.mktemp(suffix='.ndjson')

        try:
            # Build command - subcommand FIRST, then flags
            cmd = [
                str(COLLY_CRAWLER_BIN),
                "crawl",  # Subcommand FIRST
                f"--urls={url_file}",
                f"--output={output_file}",
                f"--concurrent={max_concurrent}",
                f"--timeout={timeout}",
                f"--delay={delay_ms}",
                "--include-html",  # CRITICAL: Include raw HTML for Python link extraction
            ]

            if user_agent:
                cmd.append(f"--user-agent={user_agent}")

            # Run Go binary
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                raise RuntimeError(f"colly_crawler failed: {stderr.decode()}")

            # Parse results
            results = []
            js_required_urls = []

            with open(output_file, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)

                        # Parse outlinks
                        outlinks = []
                        for ol in data.get("outlinks", []) or []:
                            outlinks.append(OutlinkRecord(
                                url=ol.get("url", ""),
                                domain=ol.get("domain", ""),
                                anchor_text=ol.get("anchor_text", ""),
                                is_nofollow=ol.get("is_nofollow", False),
                                is_external=ol.get("is_external", True),
                            ))

                        result = CrawlResult(
                            url=data.get("url", ""),
                            status_code=data.get("status_code", 0),
                            content_type=data.get("content_type", ""),
                            title=data.get("title", ""),
                            content=data.get("content", ""),
                            html=data.get("html", ""),
                            outlinks=outlinks,
                            internal_links=data.get("internal_links", []) or [],
                            needs_js=data.get("needs_js", False),
                            error=data.get("error", ""),
                            latency_ms=data.get("latency_ms", 0),
                        )

                        results.append(result)

                        # Collect URLs needing JS
                        if result.needs_js and not result.error:
                            js_required_urls.append(result.url)

                    except json.JSONDecodeError:
                        continue

            return results, js_required_urls

        finally:
            # Cleanup temp files
            try:
                os.unlink(url_file)
            except Exception as e:

                print(f"[LINKLATER] Error: {e}")

                pass
            try:
                os.unlink(output_file)
            except Exception as e:

                print(f"[LINKLATER] Error: {e}")

                pass

    async def test_crawl(self, url: str) -> CrawlResult:
        """
        Test crawl a single URL using Colly.

        Args:
            url: URL to crawl

        Returns:
            CrawlResult for the URL
        """
        results, _ = await self.crawl_static_html([url], max_concurrent=1)
        if results:
            return results[0]
        return CrawlResult(url=url, error="No result returned")

    # =========================================================================
    # ROD_CRAWLER - JS-rendering crawler (medium path)
    # =========================================================================

    async def crawl_with_rod(
        self,
        urls: List[str],
        max_concurrent: int = 50,
        timeout: int = 30,
        include_html: bool = True,
    ) -> List[CrawlResult]:
        """
        Crawl URLs using Go/Rod for JS rendering.

        This is the "medium path" - faster than Python/Playwright (~2x)
        but slower than Colly (which can't render JS).

        Args:
            urls: List of URLs to crawl
            max_concurrent: Max concurrent browser pages (default: 50)
            timeout: Page load timeout in seconds (default: 30)
            include_html: Include raw HTML in results (default: True)

        Returns:
            List of CrawlResult (all with needs_js=True)
        """
        if not self.is_available("rod_crawler"):
            raise RuntimeError("rod_crawler binary not available")

        if not urls:
            return []

        # Create temp file for URL input
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(urls, f)
            url_file = f.name

        # Create temp file for output
        output_file = tempfile.mktemp(suffix='.ndjson')

        try:
            # Build command - FLAGS MUST COME BEFORE SUBCOMMAND for Go's flag package
            cmd = [
                str(ROD_CRAWLER_BIN),
                f"--urls={url_file}",
                f"--output={output_file}",
                f"--concurrent={max_concurrent}",
                f"--timeout={timeout}",
            ]
            if include_html:
                cmd.append("--include-html")
            cmd.append("crawl")  # Subcommand comes AFTER flags

            # Run Go binary
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                raise RuntimeError(f"rod_crawler failed: {stderr.decode()}")

            # Parse results
            results = []

            with open(output_file, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)

                        # Parse outlinks
                        outlinks = []
                        for ol in data.get("outlinks", []) or []:
                            outlinks.append(OutlinkRecord(
                                url=ol.get("url", ""),
                                domain=ol.get("domain", ""),
                                anchor_text=ol.get("anchor_text", ""),
                                is_nofollow=ol.get("is_nofollow", False),
                                is_external=ol.get("is_external", True),
                            ))

                        result = CrawlResult(
                            url=data.get("url", ""),
                            status_code=data.get("status_code", 0),
                            content_type=data.get("content_type", ""),
                            title=data.get("title", ""),
                            content=data.get("content", ""),
                            html=data.get("html", ""),
                            outlinks=outlinks,
                            internal_links=data.get("internal_links", []) or [],
                            needs_js=True,  # Rod always renders JS
                            error=data.get("error", ""),
                            latency_ms=data.get("latency_ms", 0),
                        )

                        results.append(result)

                    except json.JSONDecodeError:
                        continue

            return results

        finally:
            # Cleanup temp files
            try:
                os.unlink(url_file)
            except Exception as e:

                print(f"[LINKLATER] Error: {e}")

                pass
            try:
                os.unlink(output_file)
            except Exception as e:

                print(f"[LINKLATER] Error: {e}")

                pass

    async def test_crawl_js(self, url: str) -> CrawlResult:
        """
        Test crawl a single URL using Rod (with JS rendering).

        Args:
            url: URL to crawl

        Returns:
            CrawlResult for the URL
        """
        results = await self.crawl_with_rod([url], max_concurrent=1)
        if results:
            return results[0]
        return CrawlResult(url=url, error="No result returned", needs_js=True)

    # =========================================================================
    # SCREENSHOTS - Manual and rule-based screenshot capture
    # =========================================================================

    async def take_screenshot(
        self,
        url: str,
        output_path: str,
        full_page: bool = False,
        quality: int = 90,
        timeout: int = 30,
    ) -> ScreenshotResult:
        """
        Take a screenshot of a single URL (manual trigger).

        This is the "pull the trigger" function - capture any URL on demand.

        Args:
            url: URL to screenshot
            output_path: Where to save the screenshot (PNG or JPEG)
            full_page: Capture full scrollable page (default: False)
            quality: JPEG quality 0-100 (default: 90, ignored for PNG)
            timeout: Page load timeout seconds (default: 30)

        Returns:
            ScreenshotResult with path to saved screenshot
        """
        if not self.is_available("rod_crawler"):
            raise RuntimeError("rod_crawler binary not available")

        # Build command - FLAGS BEFORE SUBCOMMAND
        cmd = [
            str(ROD_CRAWLER_BIN),
            f"--timeout={timeout}",
            f"--screenshot-quality={quality}",
        ]

        if full_page:
            cmd.append("--full-page")

        # Subcommand and args AFTER flags
        cmd.extend(["screenshot", url, output_path])

        # Run Go binary
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            return ScreenshotResult(
                url=url,
                error=f"Screenshot failed: {stderr.decode()}",
            )

        # Parse result
        try:
            data = json.loads(stdout.decode())
            return ScreenshotResult(
                url=data.get("url", url),
                title=data.get("title", ""),
                screenshot_path=data.get("screenshot_path", output_path),
                full_page=data.get("full_page", full_page),
            )
        except json.JSONDecodeError:
            return ScreenshotResult(
                url=url,
                screenshot_path=output_path,
                full_page=full_page,
            )

    async def crawl_with_screenshots(
        self,
        urls: List[str],
        screenshot_dir: str,
        rules: Optional[List[ScreenshotRule]] = None,
        screenshot_all: bool = False,
        max_concurrent: int = 50,
        timeout: int = 30,
        full_page: bool = False,
        quality: int = 90,
    ) -> Tuple[List[CrawlResult], List[ScreenshotResult]]:
        """
        Crawl URLs with rule-based screenshot capture.

        Takes screenshots based on configurable rules:
        - url_contains: Keyword in URL
        - url_regex: Regex pattern in URL
        - content_contains: Keyword in page content
        - content_min_length: Minimum content length
        - title_contains: Keyword in page title
        - domain: Specific TLDs (e.g., .ru, .ky)
        - always: Screenshot every page

        Args:
            urls: List of URLs to crawl
            screenshot_dir: Directory to save screenshots
            rules: List of ScreenshotRule for when to capture
            screenshot_all: Screenshot every page (overrides rules)
            max_concurrent: Max concurrent browser pages
            timeout: Page load timeout seconds
            full_page: Default to full page screenshots
            quality: Default JPEG quality

        Returns:
            Tuple of (crawl_results, screenshot_results)
        """
        if not self.is_available("rod_crawler"):
            raise RuntimeError("rod_crawler binary not available")

        if not urls:
            return [], []

        # Create temp files
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(urls, f)
            url_file = f.name

        output_file = tempfile.mktemp(suffix='.ndjson')
        rules_file = None

        try:
            # Build command - FLAGS BEFORE SUBCOMMAND
            cmd = [
                str(ROD_CRAWLER_BIN),
                f"--urls={url_file}",
                f"--output={output_file}",
                f"--concurrent={max_concurrent}",
                f"--timeout={timeout}",
                f"--screenshot-dir={screenshot_dir}",
                f"--screenshot-quality={quality}",
            ]

            if full_page:
                cmd.append("--full-page")

            if screenshot_all:
                cmd.append("--screenshot-all")

            # Write rules to temp file if provided
            if rules and not screenshot_all:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                    json.dump([r.to_dict() for r in rules], f)
                    rules_file = f.name
                cmd.append(f"--screenshot-rules={rules_file}")

            # Subcommand AFTER flags
            cmd.append("crawl")

            # Run Go binary
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                raise RuntimeError(f"rod_crawler failed: {stderr.decode()}")

            # Parse results
            crawl_results = []
            screenshot_results = []

            with open(output_file, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)

                        # Parse outlinks
                        outlinks = []
                        for ol in data.get("outlinks", []) or []:
                            outlinks.append(OutlinkRecord(
                                url=ol.get("url", ""),
                                domain=ol.get("domain", ""),
                                anchor_text=ol.get("anchor_text", ""),
                                is_nofollow=ol.get("is_nofollow", False),
                                is_external=ol.get("is_external", True),
                            ))

                        result = CrawlResult(
                            url=data.get("url", ""),
                            status_code=data.get("status_code", 0),
                            content_type=data.get("content_type", ""),
                            title=data.get("title", ""),
                            content=data.get("content", ""),
                            html=data.get("html", ""),
                            outlinks=outlinks,
                            internal_links=data.get("internal_links", []) or [],
                            needs_js=True,
                            error=data.get("error", ""),
                            latency_ms=data.get("latency_ms", 0),
                        )
                        crawl_results.append(result)

                        # Check for screenshot
                        ss_result = ScreenshotResult.from_crawl_result(data)
                        if ss_result:
                            screenshot_results.append(ss_result)

                    except json.JSONDecodeError:
                        continue

            return crawl_results, screenshot_results

        finally:
            # Cleanup temp files
            for f in [url_file, output_file, rules_file]:
                if f:
                    try:
                        os.unlink(f)
                    except Exception as e:

                        print(f"[LINKLATER] Error: {e}")

                        pass


# Global bridge instance
_bridge: Optional[GoBridge] = None


def get_go_bridge() -> GoBridge:
    """Get the global Go bridge instance."""
    global _bridge
    if _bridge is None:
        _bridge = GoBridge()
    return _bridge


# Convenience functions
async def go_extract_links(wat_file: str, **kwargs) -> List[OutlinkerResult]:
    """Extract links from WAT file using Go."""
    return await get_go_bridge().extract_links_from_wat(wat_file, **kwargs)


async def go_search_links(domain: str, **kwargs) -> List[OutlinkerResult]:
    """Search for links to domain using Go."""
    return await get_go_bridge().search_links(domain, **kwargs)


async def go_query_backlinks(domain: str, **kwargs) -> List[Dict[str, Any]]:
    """Query backlinks using Go."""
    return await get_go_bridge().query_backlinks(domain, **kwargs)


async def go_crawl_static(urls: List[str], **kwargs) -> Tuple[List[CrawlResult], List[str]]:
    """Crawl URLs using Go/Colly for fast static HTML crawling."""
    return await get_go_bridge().crawl_static_html(urls, **kwargs)


async def go_test_crawl(url: str) -> CrawlResult:
    """Test crawl a single URL using Go/Colly."""
    return await get_go_bridge().test_crawl(url)


def go_available() -> Dict[str, bool]:
    """Check which Go binaries are available."""
    return get_go_bridge().available


def colly_available() -> bool:
    """Check if Colly crawler is available."""
    return get_go_bridge().is_available("colly_crawler")


def rod_available() -> bool:
    """Check if Rod JS crawler is available."""
    return get_go_bridge().is_available("rod_crawler")


async def go_crawl_js(urls: List[str], **kwargs) -> List[CrawlResult]:
    """Crawl URLs using Go/Rod for JS rendering."""
    return await get_go_bridge().crawl_with_rod(urls, **kwargs)


async def go_test_crawl_js(url: str) -> CrawlResult:
    """Test crawl a single URL using Go/Rod (with JS rendering)."""
    return await get_go_bridge().test_crawl_js(url)


# Screenshot convenience functions
async def go_screenshot(
    url: str,
    output_path: str,
    full_page: bool = False,
    quality: int = 90,
    timeout: int = 30,
) -> ScreenshotResult:
    """
    Take a screenshot of a URL (manual trigger).

    Example:
        result = await go_screenshot(
            "https://example.com",
            "/tmp/example.png",
            full_page=True,
        )
        print(f"Saved to: {result.screenshot_path}")
    """
    return await get_go_bridge().take_screenshot(
        url, output_path, full_page=full_page, quality=quality, timeout=timeout
    )


async def go_crawl_with_screenshots(
    urls: List[str],
    screenshot_dir: str,
    rules: Optional[List[ScreenshotRule]] = None,
    screenshot_all: bool = False,
    **kwargs,
) -> Tuple[List[CrawlResult], List[ScreenshotResult]]:
    """
    Crawl URLs with rule-based screenshot capture.

    Example:
        # Screenshot all pages
        results, screenshots = await go_crawl_with_screenshots(
            ["https://example.com", "https://test.com"],
            "/tmp/screenshots",
            screenshot_all=True,
        )

        # Screenshot based on rules
        rules = [
            ScreenshotRule(name="sanctions", rule_type="content_contains", keywords=["sanction", "OFAC"]),
            ScreenshotRule(name="russia", rule_type="domain", domains=[".ru", ".by"]),
            ScreenshotRule(name="long", rule_type="content_min_length", min_length=10000),
        ]
        results, screenshots = await go_crawl_with_screenshots(
            urls,
            "/tmp/screenshots",
            rules=rules,
        )
    """
    return await get_go_bridge().crawl_with_screenshots(
        urls, screenshot_dir, rules=rules, screenshot_all=screenshot_all, **kwargs
    )


def create_screenshot_rules(**kwargs) -> List[ScreenshotRule]:
    """
    Helper to create common screenshot rules.

    Args:
        url_keywords: Screenshot if URL contains any of these keywords
        content_keywords: Screenshot if content contains any of these keywords
        title_keywords: Screenshot if title contains any of these keywords
        domains: Screenshot if URL is on these TLDs (e.g., [".ru", ".ky"])
        min_content_length: Screenshot if content length >= this
        url_regex: Screenshot if URL matches this regex

    Example:
        rules = create_screenshot_rules(
            content_keywords=["sanction", "OFAC", "SDN"],
            domains=[".ru", ".by", ".kz"],
            min_content_length=10000,
        )
    """
    rules = []

    if "url_keywords" in kwargs:
        rules.append(ScreenshotRule(
            name="url_match",
            rule_type="url_contains",
            keywords=kwargs["url_keywords"],
        ))

    if "content_keywords" in kwargs:
        rules.append(ScreenshotRule(
            name="content_match",
            rule_type="content_contains",
            keywords=kwargs["content_keywords"],
        ))

    if "title_keywords" in kwargs:
        rules.append(ScreenshotRule(
            name="title_match",
            rule_type="title_contains",
            keywords=kwargs["title_keywords"],
        ))

    if "domains" in kwargs:
        rules.append(ScreenshotRule(
            name="domain_match",
            rule_type="domain",
            domains=kwargs["domains"],
        ))

    if "min_content_length" in kwargs:
        rules.append(ScreenshotRule(
            name="content_length",
            rule_type="content_min_length",
            min_length=kwargs["min_content_length"],
        ))

    if "url_regex" in kwargs:
        rules.append(ScreenshotRule(
            name="url_regex",
            rule_type="url_regex",
            value=kwargs["url_regex"],
        ))

    return rules


# CLI test
if __name__ == "__main__":
    print("DRILL Go Bridge")
    print("=" * 50)
    print()
    print("Go binaries available:")
    for binary, available in go_available().items():
        status = "✓" if available else "✗"
        print(f"  {status} {binary}")
    print()
    print(f"DRILL binaries: {DRILL_GO_BIN}")
    print(f"Legacy binaries: {GLOBALLINKS_BIN}")
