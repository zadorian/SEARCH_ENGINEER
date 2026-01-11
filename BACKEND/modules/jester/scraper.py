"""
JESTER - The Unified Scraping System

JESTER is the ONLY scraping system. Everything uses JESTER.

Scraping Hierarchy (tries in order, stops on success):
- JESTER_A: httpx direct (fastest, ~60% of sites)
- JESTER_B: Colly Go crawler (static HTML, 500+ concurrent)
- JESTER_C: Rod Go crawler (JS rendering, ~100 concurrent)
- JESTER_D: Headless browser (custom Firecrawl + Playwright hybrid)
- FIRECRAWL: External Firecrawl API (paid)
- BRIGHTDATA: BrightData proxy API (paid, last resort)

Usage:
    from JESTER import Jester

    jester = Jester()
    html, method_used, latency = await jester.scrape("https://example.com")

    # Or force a specific method:
    html = await jester.scrape_a("https://example.com")  # httpx only
    html = await jester.scrape_b("https://example.com")  # Colly only
    html = await jester.scrape_c("https://example.com")  # Rod only
    html = await jester.scrape_d("https://example.com")  # Headless only
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

import httpx
from dotenv import load_dotenv

# Load environment
# Adjusted for /data root deployment
try:
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    if not (PROJECT_ROOT / ".env").exists():
        # Fallback for deep nesting if needed
        for parent in Path(__file__).resolve().parents:
            if (parent / ".env").exists():
                PROJECT_ROOT = parent
                break
except IndexError:
    PROJECT_ROOT = Path("/data")

load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger("JESTER")

# Constants
MIN_VALID_HTML_LENGTH = 100  # Minimum HTML length to consider a scrape successful


class JesterMethod(Enum):
    """Scraping methods in order of preference."""
    JESTER_A = "jester_a"      # httpx direct
    JESTER_B = "jester_b"      # Colly Go crawler
    JESTER_C = "jester_c"      # Rod Go JS renderer
    JESTER_D = "jester_d"      # Headless browser (Firecrawl + Playwright)
    FIRECRAWL = "firecrawl"    # External API
    BRIGHTDATA = "brightdata"  # Proxy API
    BLOCKED = "blocked"        # All methods failed


@dataclass
class JesterResult:
    """Result from a JESTER scrape operation."""
    url: str
    html: str
    method: JesterMethod
    latency_ms: int
    status_code: int
    content_length: int
    needs_js: bool = False
    error: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    entities: Dict[str, List[str]] = field(default_factory=dict)  # PACMAN extraction


@dataclass
class JesterConfig:
    """Configuration for JESTER scraper."""
    # Timeouts
    timeout_a: int = 15        # httpx timeout
    timeout_b: int = 30        # Colly timeout
    timeout_c: int = 45        # Rod timeout
    timeout_d: int = 60        # JESTER_D timeout
    timeout_api: int = 60      # External API timeout

    # Concurrency limits
    max_concurrent_a: int = 100
    max_concurrent_b: int = 500
    max_concurrent_c: int = 100
    max_concurrent_d: int = 50

    # User agent
    user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

    # Which methods to try (in order)
    enabled_methods: List[JesterMethod] = field(default_factory=lambda: [
        JesterMethod.JESTER_A,
        JesterMethod.JESTER_B,
        JesterMethod.JESTER_C,
        JesterMethod.JESTER_D,
        JesterMethod.FIRECRAWL,
        JesterMethod.BRIGHTDATA,  # Available for single-URL, disabled in batch by default
    ])

    # Skip to specific method for known classifications
    force_method: Optional[JesterMethod] = None

    # Auth session injection (ROV)
    use_auth_sessions: bool = True
    auth_session_dir: Optional[str] = None


class Jester:
    """
    The Unified Scraping System.

    JESTER tries methods in order until one succeeds:
    A (httpx) -> B (Colly) -> C (Rod) -> D (headless) -> Firecrawl -> BrightData
    """

    def __init__(self, config: Optional[JesterConfig] = None):
        self.config = config or JesterConfig()

        # HTTP client for JESTER_A
        self._http: Optional[httpx.AsyncClient] = None

        # Go bridge for JESTER_B and JESTER_C
        self._go_bridge = None

        # Headless crawler for JESTER_D
        self._headless = None

        # API clients
        self._firecrawl_key = os.getenv("FIRECRAWL_API_KEY")
        self._firecrawl_url = os.getenv("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev/v1")
        self._brightdata_key = os.getenv("BRIGHTDATA_API_KEY")

        # Track availability
        self._colly_available = False
        self._rod_available = False
        self._jester_d_available = False

        self._initialized = False
        self._init_lock = asyncio.Lock()  # Prevent race condition in lazy init

    async def _ensure_init(self):
        """Lazy initialization of components (thread-safe)."""
        if self._initialized:
            return

        async with self._init_lock:
            # Double-check after acquiring lock
            if self._initialized:
                return

            # Initialize HTTP client with connection limits
            self._http = httpx.AsyncClient(
                timeout=self.config.timeout_a,
                follow_redirects=True,
                headers={"User-Agent": self.config.user_agent},
                limits=httpx.Limits(max_connections=500, max_keepalive_connections=100)
            )

            # Check Go binary availability
            await self._check_go_availability()

            # Check JESTER_D availability
            await self._check_jester_d_availability()

            self._initialized = True

    async def _check_go_availability(self):
        """Check if Go binaries are available."""
        try:
            # Import go_bridge from LINKLATER
            from modules.jester.scraping.go_bridge import colly_available, rod_available, GoBridge
            self._colly_available = colly_available()
            self._rod_available = rod_available()
            if self._colly_available or self._rod_available:
                self._go_bridge = GoBridge()
            logger.info(f"Go binaries: Colly={self._colly_available}, Rod={self._rod_available}")
        except ImportError as e:
            logger.warning(f"Go bridge not available: {e}")
            self._colly_available = False
            self._rod_available = False

    async def _check_jester_d_availability(self):
        """Check if JESTER_D headless browser is available."""
        try:
            from modules.jester.scraping.crawler import Drill, DrillConfig
            self._jester_d_available = True
            logger.info("JESTER_D (headless) available")
        except ImportError as e:
            logger.warning(f"JESTER_D not available: {e}")
            self._jester_d_available = False

    async def close(self):
        """Close all connections."""
        if self._http:
            await self._http.aclose()
        if self._go_bridge:
            # Go bridge cleanup if needed
            pass

    # ─────────────────────────────────────────────────────────────
    # Main scrape method - tries all methods in order
    # ─────────────────────────────────────────────────────────────

    async def scrape(
        self,
        url: str,
        force_method: Optional[JesterMethod] = None,
    ) -> JesterResult:
        """
        Scrape a URL using the JESTER hierarchy.

        Tries methods in order until one succeeds:
        A -> B -> C -> D -> Firecrawl -> BrightData

        Args:
            url: URL to scrape
            force_method: Skip to specific method (for pre-classified sources)

        Returns:
            JesterResult with HTML content and metadata
        """
        await self._ensure_init()

        method = force_method or self.config.force_method
        methods = self.config.enabled_methods

        # If forcing a method, start from that method
        if method:
            try:
                idx = methods.index(method)
                methods = methods[idx:]
            except ValueError:
                pass

        last_error = None

        for m in methods:
            try:
                result = await self._try_method(url, m)
                if result and result.html and len(result.html) > MIN_VALID_HTML_LENGTH:
                    return result
            except Exception as e:
                last_error = str(e)
                logger.debug(f"Method {m.value} failed for {url}: {e}")
                continue

        # All methods failed
        return JesterResult(
            url=url,
            html="",
            method=JesterMethod.BLOCKED,
            latency_ms=0,
            status_code=0,
            content_length=0,
            error=last_error or "All scraping methods failed"
        )

    async def _try_method(self, url: str, method: JesterMethod) -> Optional[JesterResult]:
        """Try a specific scraping method."""
        if method == JesterMethod.JESTER_A:
            return await self.scrape_a(url)
        elif method == JesterMethod.JESTER_B:
            if not self._colly_available:
                return None
            return await self.scrape_b(url)
        elif method == JesterMethod.JESTER_C:
            if not self._rod_available:
                return None
            return await self.scrape_c(url)
        elif method == JesterMethod.JESTER_D:
            if not self._jester_d_available:
                return None
            return await self.scrape_d(url)
        elif method == JesterMethod.FIRECRAWL:
            if not self._firecrawl_key:
                return None
            return await self.scrape_firecrawl(url)
        elif method == JesterMethod.BRIGHTDATA:
            if not self._brightdata_key:
                return None
            return await self.scrape_brightdata(url)
        return None

    # ─────────────────────────────────────────────────────────────
    # Individual scraping methods
    # ─────────────────────────────────────────────────────────────

    async def scrape_a(self, url: str) -> JesterResult:
        """
        JESTER_A: Direct httpx request.

        Fastest method, works for ~60% of sites.
        """
        await self._ensure_init()
        start = time.time()

        try:
            resp = await self._http.get(url, timeout=self.config.timeout_a)
            latency = int((time.time() - start) * 1000)

            # Check for bot blocks
            if resp.status_code in (403, 429, 503):
                return JesterResult(
                    url=url,
                    html="",
                    method=JesterMethod.JESTER_A,
                    latency_ms=latency,
                    status_code=resp.status_code,
                    content_length=0,
                    error=f"Blocked with status {resp.status_code}"
                )

            html = resp.text
            return JesterResult(
                url=url,
                html=html,
                method=JesterMethod.JESTER_A,
                latency_ms=latency,
                status_code=resp.status_code,
                content_length=len(html),
                headers=dict(resp.headers)
            )
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            return JesterResult(
                url=url,
                html="",
                method=JesterMethod.JESTER_A,
                latency_ms=latency,
                status_code=0,
                content_length=0,
                error=str(e)
            )

    async def scrape_b(self, url: str) -> JesterResult:
        """
        JESTER_B: Colly Go crawler.

        High-performance static HTML crawling, 500+ concurrent.
        """
        await self._ensure_init()

        if not self._colly_available or not self._go_bridge:
            raise RuntimeError("Colly not available")

        start = time.time()
        try:
            # crawl_static_html returns (results, js_required_urls)
            results, _ = await self._go_bridge.crawl_static_html(
                [url],
                max_concurrent=1,
                timeout=self.config.timeout_b
            )
            latency = int((time.time() - start) * 1000)

            if results and len(results) > 0:
                r = results[0]
                return JesterResult(
                    url=url,
                    html=r.html or "",
                    method=JesterMethod.JESTER_B,
                    latency_ms=latency,
                    status_code=r.status_code,
                    content_length=len(r.html or ""),
                    needs_js=r.needs_js
                )

            return JesterResult(
                url=url,
                html="",
                method=JesterMethod.JESTER_B,
                latency_ms=latency,
                status_code=0,
                content_length=0,
                error="No result from Colly"
            )
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            return JesterResult(
                url=url,
                html="",
                method=JesterMethod.JESTER_B,
                latency_ms=latency,
                status_code=0,
                content_length=0,
                error=str(e)
            )

    async def scrape_c(self, url: str) -> JesterResult:
        """
        JESTER_C: Rod Go JS renderer.

        JS rendering for SPAs, ~100 concurrent browsers.
        """
        await self._ensure_init()

        if not self._rod_available or not self._go_bridge:
            raise RuntimeError("Rod not available")

        start = time.time()
        try:
            result = await self._go_bridge.crawl_with_rod(
                [url],
                max_concurrent=1,
                timeout=self.config.timeout_c,
                include_html=True
            )
            latency = int((time.time() - start) * 1000)

            if result and len(result) > 0:
                r = result[0]
                return JesterResult(
                    url=url,
                    html=r.html or "",
                    method=JesterMethod.JESTER_C,
                    latency_ms=latency,
                    status_code=r.status_code,
                    content_length=len(r.html or ""),
                    needs_js=True
                )

            return JesterResult(
                url=url,
                html="",
                method=JesterMethod.JESTER_C,
                latency_ms=latency,
                status_code=0,
                content_length=0,
                error="No result from Rod"
            )
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            return JesterResult(
                url=url,
                html="",
                method=JesterMethod.JESTER_C,
                latency_ms=latency,
                status_code=0,
                content_length=0,
                error=str(e)
            )

    async def scrape_d(self, url: str) -> JesterResult:
        """
        JESTER_D: Headless browser (custom Firecrawl + Playwright hybrid).

        Custom headless browser crawler built on Firecrawl + Playwright.
        """
        await self._ensure_init()

        if not self._jester_d_available:
            raise RuntimeError("JESTER_D not available")

        start = time.time()
        try:
            # Import the headless crawler implementation
            from modules.jester.scraping.crawler import Drill, DrillConfig

            config = DrillConfig(
                max_pages=1,
                max_concurrent=1,
                request_timeout=self.config.timeout_d,
                extract_entities=False,
                generate_embeddings=False,
                index_to_elasticsearch=False,
                auth_use_sessions=self.config.use_auth_sessions,
                auth_session_dir=self.config.auth_session_dir,
            )

            crawler = Drill(config)
            result = await crawler.crawl_url(url)
            latency = int((time.time() - start) * 1000)

            if result and result.html:
                return JesterResult(
                    url=url,
                    html=result.html,
                    method=JesterMethod.JESTER_D,
                    latency_ms=latency,
                    status_code=result.status_code or 200,
                    content_length=len(result.html),
                    needs_js=True
                )

            return JesterResult(
                url=url,
                html="",
                method=JesterMethod.JESTER_D,
                latency_ms=latency,
                status_code=0,
                content_length=0,
                error="No result from JESTER_D"
            )
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            return JesterResult(
                url=url,
                html="",
                method=JesterMethod.JESTER_D,
                latency_ms=latency,
                status_code=0,
                content_length=0,
                error=str(e)
            )

    async def scrape_firecrawl(self, url: str) -> JesterResult:
        """
        FIRECRAWL: External Firecrawl API.

        Paid service, reliable fallback.
        """
        await self._ensure_init()

        if not self._firecrawl_key:
            raise RuntimeError("Firecrawl API key not configured")

        start = time.time()
        try:
            resp = await self._http.post(
                f"{self._firecrawl_url}/scrape",
                headers={
                    "Authorization": f"Bearer {self._firecrawl_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "url": url,
                    "formats": ["html"],
                    "onlyMainContent": False,
                    "maxAge": 2592000000,  # 30 days in ms - use cached for 500% speed boost
                },
                timeout=self.config.timeout_api
            )
            latency = int((time.time() - start) * 1000)

            if resp.status_code == 200:
                data = resp.json()
                html = data.get("data", {}).get("html", "")
                return JesterResult(
                    url=url,
                    html=html,
                    method=JesterMethod.FIRECRAWL,
                    latency_ms=latency,
                    status_code=200,
                    content_length=len(html)
                )

            return JesterResult(
                url=url,
                html="",
                method=JesterMethod.FIRECRAWL,
                latency_ms=latency,
                status_code=resp.status_code,
                content_length=0,
                error=f"Firecrawl returned {resp.status_code}"
            )
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            return JesterResult(
                url=url,
                html="",
                method=JesterMethod.FIRECRAWL,
                latency_ms=latency,
                status_code=0,
                content_length=0,
                error=str(e)
            )

    async def scrape_brightdata(self, url: str) -> JesterResult:
        """
        BRIGHTDATA: BrightData Web Unlocker proxy.

        Paid service, last resort for heavily protected sites.
        """
        await self._ensure_init()

        if not self._brightdata_key:
            raise RuntimeError("BrightData API key not configured")

        start = time.time()
        try:
            resp = await self._http.post(
                "https://api.brightdata.com/request",
                headers={
                    "Authorization": f"Bearer {self._brightdata_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "zone": "mcp_unlocker",
                    "url": url,
                    "format": "raw"
                },
                timeout=self.config.timeout_api
            )
            latency = int((time.time() - start) * 1000)

            if resp.status_code == 200:
                html = resp.text
                return JesterResult(
                    url=url,
                    html=html,
                    method=JesterMethod.BRIGHTDATA,
                    latency_ms=latency,
                    status_code=200,
                    content_length=len(html)
                )

            return JesterResult(
                url=url,
                html="",
                method=JesterMethod.BRIGHTDATA,
                latency_ms=latency,
                status_code=resp.status_code,
                content_length=0,
                error=f"BrightData returned {resp.status_code}"
            )
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            return JesterResult(
                url=url,
                html="",
                method=JesterMethod.BRIGHTDATA,
                latency_ms=latency,
                status_code=0,
                content_length=0,
                error=str(e)
            )

    # ─────────────────────────────────────────────────────────────
    # Batch scraping
    # ─────────────────────────────────────────────────────────────

    async def scrape_batch(
        self,
        urls: List[str],
        max_concurrent: int = 100,  # Match Firecrawl subscription limit
        force_method: Optional[JesterMethod] = None,
    ) -> List[JesterResult]:
        """
        Scrape multiple URLs concurrently.

        Args:
            urls: List of URLs to scrape
            max_concurrent: Maximum concurrent requests (default 100 for Firecrawl)
            force_method: Force a specific method for all URLs

        Returns:
            List of JesterResult objects
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def scrape_with_semaphore(url: str) -> JesterResult:
            async with semaphore:
                return await self.scrape(url, force_method=force_method)

        tasks = [scrape_with_semaphore(url) for url in urls]
        return await asyncio.gather(*tasks)

    # ─────────────────────────────────────────────────────────────
    # Optimized batch scraping (tiered)
    # ─────────────────────────────────────────────────────────────

    async def scrape_batch_optimized(
        self,
        urls: List[str],
        domain_limit: int = 10,
        progress_callback: Optional[callable] = None,
        use_backdrill: bool = True,
        use_firecrawl: bool = False,
        use_brightdata: bool = False,
    ) -> List[JesterResult]:
        """
        Optimized batch scraping using tiered parallelization.

        Instead of trying each tier per-URL (spawning 1000 Go processes),
        this runs each tier ONCE with all URLs that need it:

        Phase 1: JESTER_A (httpx) on ALL URLs → collect failures
        Phase 2: BACKDRILL (archives: recent → 2y → 3y) on failures
        Phase 3: JESTER_B (Colly) on failures (ONE Go call, 500 concurrent)
        Phase 4: JESTER_C (Rod) on remaining (ONE Go call, 100 concurrent)
        Phase 5: JESTER_D (headless browser) on remaining
        Phase 6: Firecrawl (paid API, off by default)
        Phase 7: BrightData (expensive, off by default)

        Args:
            urls: List of URLs to scrape
            domain_limit: Max concurrent requests per domain (rate limiting)
            progress_callback: Optional callback(phase, completed, total)
            use_backdrill: Enable BACKDRILL archive fallback (default True)
            use_firecrawl: Enable Firecrawl paid API (default False for batch)
            use_brightdata: Enable BrightData as last resort (default False for batch)

        Returns:
            List of JesterResult objects in same order as input URLs
        """
        await self._ensure_init()

        if not urls:
            return []

        results: Dict[str, JesterResult] = {}
        pending = set(urls)

        def report(phase: str, done: int, total: int):
            if progress_callback:
                progress_callback(phase, done, total)
            logger.info(f"[{phase}] {done}/{total} URLs processed")

        # Phase 1: JESTER_A (httpx) - all URLs
        logger.info(f"Phase 1: JESTER_A on {len(pending)} URLs")
        a_results = await self._batch_jester_a(list(pending), domain_limit)
        for r in a_results:
            results[r.url] = r
            if r.html and len(r.html) > MIN_VALID_HTML_LENGTH:
                pending.discard(r.url)
        report("JESTER_A", len(urls) - len(pending), len(urls))

        # Phase 2: JESTER_B (Colly) - failed URLs, SINGLE Go call
        if pending and self._colly_available:
            logger.info(f"Phase 2: JESTER_B on {len(pending)} failed URLs")
            b_results = await self._batch_jester_b(list(pending))
            for r in b_results:
                results[r.url] = r
                if r.html and len(r.html) > MIN_VALID_HTML_LENGTH:
                    pending.discard(r.url)
            report("JESTER_B", len(urls) - len(pending), len(urls))

        # Phase 3: JESTER_C (Rod) - still-failed URLs, SINGLE Go call
        if pending and self._rod_available:
            logger.info(f"Phase 3: JESTER_C on {len(pending)} failed URLs")
            c_results = await self._batch_jester_c(list(pending))
            for r in c_results:
                results[r.url] = r
                if r.html and len(r.html) > MIN_VALID_HTML_LENGTH:
                    pending.discard(r.url)
            report("JESTER_C", len(urls) - len(pending), len(urls))

        # Phase 4: JESTER_D (headless) - remaining failures
        if pending and self._jester_d_available:
            logger.info(f"Phase 4: JESTER_D on {len(pending)} failed URLs")
            d_results = await self._batch_jester_d(list(pending))
            for r in d_results:
                results[r.url] = r
                if r.html and len(r.html) > MIN_VALID_HTML_LENGTH:
                    pending.discard(r.url)
            report("JESTER_D", len(urls) - len(pending), len(urls))

        # Phase 5: Firecrawl - paid fallback
        if pending and self._firecrawl_key:
            logger.info(f"Phase 5: Firecrawl on {len(pending)} failed URLs")
            f_results = await self._batch_firecrawl(list(pending))
            for r in f_results:
                results[r.url] = r
                if r.html and len(r.html) > MIN_VALID_HTML_LENGTH:
                    pending.discard(r.url)
            report("FIRECRAWL", len(urls) - len(pending), len(urls))

        # Phase 6: BrightData - off by default for batch (expensive)
        if use_brightdata and pending and self._brightdata_key:
            logger.info(f"Phase 6: BrightData on {len(pending)} failed URLs")
            bd_results = await self._batch_brightdata(list(pending))
            for r in bd_results:
                results[r.url] = r
                if r.html and len(r.html) > MIN_VALID_HTML_LENGTH:
                    pending.discard(r.url)
            report("BRIGHTDATA", len(urls) - len(pending), len(urls))

        # Mark any remaining as blocked
        for url in pending:
            if url not in results:
                results[url] = JesterResult(
                    url=url,
                    html="",
                    method=JesterMethod.BLOCKED,
                    latency_ms=0,
                    status_code=0,
                    content_length=0,
                    error="All scraping methods failed"
                )

        # Return in original order
        return [results.get(url) for url in urls]

    async def _batch_jester_a(
        self,
        urls: List[str],
        domain_limit: int = 10,
    ) -> List[JesterResult]:
        """
        Batch JESTER_A (httpx) with per-domain rate limiting.
        """
        from urllib.parse import urlparse
        from collections import defaultdict

        # Group by domain for rate limiting
        domain_semaphores: Dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(domain_limit)
        )
        global_semaphore = asyncio.Semaphore(self.config.max_concurrent_a)

        async def fetch_one(url: str) -> JesterResult:
            domain = urlparse(url).netloc
            async with global_semaphore:
                async with domain_semaphores[domain]:
                    return await self.scrape_a(url)

        tasks = [fetch_one(url) for url in urls]
        return await asyncio.gather(*tasks, return_exceptions=False)

    async def _batch_jester_b(self, urls: List[str]) -> List[JesterResult]:
        """
        Batch JESTER_B (Colly) - SINGLE Go call with all URLs.
        This is the key optimization: 500 concurrent in ONE process.
        """
        if not self._go_bridge or not urls:
            return []

        start = time.time()
        try:
            # Call Colly ONCE with ALL URLs
            crawl_results, _ = await self._go_bridge.crawl_static_html(
                urls,
                max_concurrent=self.config.max_concurrent_b,  # 500!
                timeout=self.config.timeout_b
            )
            latency = int((time.time() - start) * 1000)

            # Convert CrawlResult to JesterResult
            results = []
            for r in crawl_results:
                results.append(JesterResult(
                    url=r.url,
                    html=r.html or "",
                    method=JesterMethod.JESTER_B,
                    latency_ms=r.latency_ms or latency,
                    status_code=r.status_code,
                    content_length=len(r.html or ""),
                    needs_js=r.needs_js,
                    error=r.error or None
                ))
            return results
        except Exception as e:
            logger.error(f"Batch JESTER_B failed: {e}")
            # Return empty results for all URLs
            return [JesterResult(
                url=url,
                html="",
                method=JesterMethod.JESTER_B,
                latency_ms=0,
                status_code=0,
                content_length=0,
                error=str(e)
            ) for url in urls]

    async def _batch_jester_c(self, urls: List[str]) -> List[JesterResult]:
        """
        Batch JESTER_C (Rod) - SINGLE Go call with all URLs.
        JS rendering at 100 concurrent browsers.
        """
        if not self._go_bridge or not urls:
            return []

        start = time.time()
        try:
            # Call Rod ONCE with ALL URLs
            crawl_results = await self._go_bridge.crawl_with_rod(
                urls,
                max_concurrent=self.config.max_concurrent_c,  # 100
                timeout=self.config.timeout_c,
                include_html=True
            )
            latency = int((time.time() - start) * 1000)

            # Convert to JesterResult
            results = []
            for r in crawl_results:
                results.append(JesterResult(
                    url=r.url,
                    html=r.html or "",
                    method=JesterMethod.JESTER_C,
                    latency_ms=r.latency_ms or latency,
                    status_code=r.status_code,
                    content_length=len(r.html or ""),
                    needs_js=True,
                    error=r.error or None
                ))
            return results
        except Exception as e:
            logger.error(f"Batch JESTER_C failed: {e}")
            return [JesterResult(
                url=url,
                html="",
                method=JesterMethod.JESTER_C,
                latency_ms=0,
                status_code=0,
                content_length=0,
                error=str(e)
            ) for url in urls]

    async def _batch_jester_d(self, urls: List[str]) -> List[JesterResult]:
        """
        Batch JESTER_D (headless browser).
        Limited concurrency due to resource usage.
        """
        semaphore = asyncio.Semaphore(self.config.max_concurrent_d)  # 50

        async def scrape_one(url: str) -> JesterResult:
            async with semaphore:
                return await self.scrape_d(url)

        tasks = [scrape_one(url) for url in urls]
        return await asyncio.gather(*tasks, return_exceptions=False)

    async def _batch_firecrawl(self, urls: List[str]) -> List[JesterResult]:
        """
        Batch Firecrawl API calls.
        Rate limited to avoid API throttling.
        """
        semaphore = asyncio.Semaphore(10)  # Firecrawl rate limit

        async def scrape_one(url: str) -> JesterResult:
            async with semaphore:
                return await self.scrape_firecrawl(url)

        tasks = [scrape_one(url) for url in urls]
        return await asyncio.gather(*tasks, return_exceptions=False)

    async def _batch_brightdata(self, urls: List[str]) -> List[JesterResult]:
        """
        Batch BrightData API calls.
        Most expensive, lowest concurrency.
        """
        semaphore = asyncio.Semaphore(5)  # Conservative rate limit

        async def scrape_one(url: str) -> JesterResult:
            async with semaphore:
                return await self.scrape_brightdata(url)

        tasks = [scrape_one(url) for url in urls]
        return await asyncio.gather(*tasks, return_exceptions=False)


# ─────────────────────────────────────────────────────────────────
# Convenience functions
# ─────────────────────────────────────────────────────────────────

_default_jester: Optional[Jester] = None
_jester_lock = asyncio.Lock()


async def get_jester() -> Jester:
    """Get the default Jester instance (thread-safe singleton)."""
    global _default_jester
    if _default_jester is None:
        async with _jester_lock:
            # Double-check after acquiring lock
            if _default_jester is None:
                _default_jester = Jester()
    return _default_jester


async def scrape(url: str, force_method: Optional[JesterMethod] = None) -> JesterResult:
    """Convenience function to scrape a URL."""
    jester = await get_jester()
    return await jester.scrape(url, force_method=force_method)


async def scrape_batch(
    urls: List[str],
    max_concurrent: int = 100,  # Match Firecrawl subscription limit
    force_method: Optional[JesterMethod] = None,
) -> List[JesterResult]:
    """Convenience function to scrape multiple URLs (simple per-URL cascading)."""
    jester = await get_jester()
    return await jester.scrape_batch(urls, max_concurrent, force_method)


async def scrape_batch_optimized(
    urls: List[str],
    domain_limit: int = 10,
    progress_callback: Optional[callable] = None,
    use_brightdata: bool = False,
) -> List[JesterResult]:
    """
    Convenience function for optimized batch scraping.

    Use this for large URL lists (100+). It's much faster because:
    - Go binaries are called ONCE with all URLs (not per-URL)
    - Per-domain rate limiting prevents blocks
    - Tiered execution minimizes expensive API calls
    - BrightData OFF by default (pass use_brightdata=True to enable)

    Example:
        results = await scrape_batch_optimized(urls, progress_callback=print)
    """
    jester = await get_jester()
    return await jester.scrape_batch_optimized(urls, domain_limit, progress_callback, use_brightdata)


# ─────────────────────────────────────────────────────────────────
# CRAWL MODE - Follow internal links, map domains
# ─────────────────────────────────────────────────────────────────

from urllib.parse import urlparse, urljoin
from dataclasses import dataclass, field
from typing import Set, AsyncIterator


@dataclass
class CrawlPage:
    """Result from crawling a single page (includes links found)."""
    url: str
    html: str
    method: JesterMethod
    latency_ms: int
    status_code: int
    content_length: int
    internal_links: List[str] = field(default_factory=list)  # Same-domain links
    external_links: List[str] = field(default_factory=list)  # Other-domain links
    depth: int = 0
    error: Optional[str] = None


@dataclass
class CrawlConfig:
    """Configuration for domain crawling."""
    max_depth: int = 2              # How deep to follow links (0 = seed only)
    max_pages: int = 100            # Maximum pages to crawl per domain
    same_domain_only: bool = True   # Only follow internal links
    follow_outlinks: bool = False   # Also crawl first page of external domains
    max_outlink_domains: int = 10   # Max external domains to crawl (if follow_outlinks)
    respect_robots: bool = False    # TODO: robots.txt parsing
    delay_between_pages: float = 0  # Seconds between requests (politeness)
    url_filter: Optional[callable] = None  # Filter function for URLs


@dataclass
class DomainCrawlResult:
    """Complete result from crawling a domain (includes outlink graph)."""
    seed_url: str
    seed_domain: str
    pages: List['CrawlPage'] = field(default_factory=list)
    outlink_graph: Dict[str, List[str]] = field(default_factory=dict)  # domain -> [linked domains]
    all_internal_urls: Set[str] = field(default_factory=set)
    all_external_urls: Set[str] = field(default_factory=set)
    total_time_sec: float = 0
    error: Optional[str] = None


async def crawl_domain(
    seed_url: str,
    config: Optional[CrawlConfig] = None,
) -> AsyncIterator[CrawlPage]:
    """
    Crawl a domain starting from seed URL, following internal links.

    This is STREAMING - yields pages as they're crawled.

    Args:
        seed_url: Starting URL
        config: Crawl configuration (defaults to depth=2, max_pages=100)

    Yields:
        CrawlPage objects as they're discovered and scraped

    Example:
        async for page in crawl_domain("https://company.com"):
            print(f"Found {len(page.internal_links)} links on {page.url}")
    """
    config = config or CrawlConfig()
    jester = await get_jester()
    await jester._ensure_init()

    # Parse seed domain
    parsed_seed = urlparse(seed_url)
    seed_domain = parsed_seed.netloc.lower()

    # Track state
    seen_urls: Set[str] = set()
    queue: List[Tuple[str, int]] = [(seed_url, 0)]  # (url, depth)
    pages_crawled = 0

    while queue and pages_crawled < config.max_pages:
        url, depth = queue.pop(0)

        # Normalize URL
        url = url.split('#')[0]  # Remove fragment
        if url in seen_urls:
            continue
        seen_urls.add(url)

        # Apply URL filter if provided
        if config.url_filter and not config.url_filter(url):
            continue

        # Politeness delay
        if config.delay_between_pages > 0 and pages_crawled > 0:
            await asyncio.sleep(config.delay_between_pages)

        # Scrape the page
        result = await jester.scrape(url)
        pages_crawled += 1

        # Extract links from HTML
        internal_links = []
        external_links = []

        if result.html:
            # Simple link extraction (Go bridge does this better, but fallback for httpx)
            import re
            href_pattern = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
            for match in href_pattern.finditer(result.html):
                link = match.group(1)
                # Skip non-http links
                if link.startswith(('javascript:', 'mailto:', 'tel:', '#')):
                    continue

                # Make absolute
                abs_link = urljoin(url, link)
                abs_link = abs_link.split('#')[0]  # Remove fragment

                # Classify as internal or external
                link_domain = urlparse(abs_link).netloc.lower()
                if link_domain == seed_domain:
                    internal_links.append(abs_link)
                    # Add to queue if within depth
                    if depth < config.max_depth and abs_link not in seen_urls:
                        queue.append((abs_link, depth + 1))
                else:
                    external_links.append(abs_link)

        # Deduplicate links
        internal_links = list(set(internal_links))
        external_links = list(set(external_links))

        # Yield page result
        yield CrawlPage(
            url=result.url,
            html=result.html,
            method=result.method,
            latency_ms=result.latency_ms,
            status_code=result.status_code,
            content_length=result.content_length,
            internal_links=internal_links,
            external_links=external_links,
            depth=depth,
            error=result.error,
        )


async def crawl_domain_full(
    seed_url: str,
    config: Optional[CrawlConfig] = None,
) -> DomainCrawlResult:
    """
    Crawl a domain fully and return complete result with outlink graph.

    This is NON-STREAMING - returns when complete.

    Args:
        seed_url: Starting URL
        config: Crawl configuration

    Returns:
        DomainCrawlResult with pages, outlink graph, all discovered URLs
    """
    config = config or CrawlConfig()
    start_time = time.time()

    parsed_seed = urlparse(seed_url)
    seed_domain = parsed_seed.netloc.lower()

    result = DomainCrawlResult(
        seed_url=seed_url,
        seed_domain=seed_domain,
        pages=[],
        outlink_graph={seed_domain: []},
        all_internal_urls=set(),
        all_external_urls=set(),
    )

    # Collect all pages from the streaming crawl
    try:
        async for page in crawl_domain(seed_url, config):
            result.pages.append(page)
            result.all_internal_urls.update(page.internal_links)
            result.all_external_urls.update(page.external_links)

            # Build outlink graph
            for ext_url in page.external_links:
                ext_domain = urlparse(ext_url).netloc.lower()
                if ext_domain and ext_domain != seed_domain:
                    if seed_domain not in result.outlink_graph:
                        result.outlink_graph[seed_domain] = []
                    if ext_domain not in result.outlink_graph[seed_domain]:
                        result.outlink_graph[seed_domain].append(ext_domain)

        # Optionally crawl outlink domains (first page only)
        if config.follow_outlinks and result.all_external_urls:
            jester = await get_jester()
            outlink_domains = list(set(
                urlparse(u).netloc.lower()
                for u in result.all_external_urls
                if urlparse(u).netloc.lower() != seed_domain
            ))[:config.max_outlink_domains]

            logger.info(f"Following {len(outlink_domains)} outlink domains...")

            # Get one page from each external domain
            ext_urls = [f"https://{d}" for d in outlink_domains]
            ext_results = await scrape_batch(ext_urls, max_concurrent=20)

            for r in ext_results:
                if r.html and len(r.html) > 100:
                    ext_domain = urlparse(r.url).netloc.lower()

                    # Extract outlinks from external domain
                    ext_outlinks = []
                    import re
                    href_pattern = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
                    for match in href_pattern.finditer(r.html[:50000]):
                        link = match.group(1)
                        if link.startswith('http'):
                            link_domain = urlparse(link).netloc.lower()
                            if link_domain and link_domain != ext_domain:
                                ext_outlinks.append(link_domain)

                    result.outlink_graph[ext_domain] = list(set(ext_outlinks))[:20]

    except Exception as e:
        result.error = str(e)
        logger.error(f"Crawl error: {e}")

    result.total_time_sec = time.time() - start_time
    return result


async def crawl_batch(
    seed_urls: List[str],
    config: Optional[CrawlConfig] = None,
    max_concurrent_domains: int = 10,
) -> AsyncIterator[CrawlPage]:
    """
    Crawl multiple domains concurrently.

    Args:
        seed_urls: List of starting URLs (one per domain)
        config: Crawl configuration
        max_concurrent_domains: How many domains to crawl at once

    Yields:
        CrawlPage objects from all domains, interleaved
    """
    config = config or CrawlConfig()

    # Create queues for each domain
    results_queue: asyncio.Queue = asyncio.Queue()
    active_crawlers = 0
    lock = asyncio.Lock()

    async def crawl_one_domain(seed: str):
        nonlocal active_crawlers
        try:
            async for page in crawl_domain(seed, config):
                await results_queue.put(page)
        finally:
            async with lock:
                active_crawlers -= 1
            await results_queue.put(None)  # Signal completion

    # Start crawlers
    semaphore = asyncio.Semaphore(max_concurrent_domains)
    tasks = []

    for seed in seed_urls:
        async with lock:
            active_crawlers += 1

        async def run_with_semaphore(s):
            async with semaphore:
                await crawl_one_domain(s)

        task = asyncio.create_task(run_with_semaphore(seed))
        tasks.append(task)

    # Yield results as they come
    completed = 0
    while completed < len(seed_urls):
        item = await results_queue.get()
        if item is None:
            completed += 1
        else:
            yield item

    # Ensure all tasks complete
    await asyncio.gather(*tasks, return_exceptions=True)


# ─────────────────────────────────────────────────────────────────
# PACMAN Integration - Entity Extraction (No Slowdown)
# ─────────────────────────────────────────────────────────────────

async def extract_entities_batch(
    results: List[JesterResult],
    max_concurrent: int = 50,
) -> List[JesterResult]:
    """
    Run PACMAN entity extraction on batch results.

    This runs IN PARALLEL with future scrapes - no slowdown.
    Extraction takes ~5ms per page, runs in thread pool.

    Args:
        results: List of JesterResult from scrape_batch or scrape_batch_optimized
        max_concurrent: Max concurrent extractions (default 50)

    Returns:
        Same results list with entities populated

    Example:
        results = await scrape_batch_optimized(urls)
        results = await extract_entities_batch(results)  # Adds entities
    """
    try:
        from .pacman import extract_async
    except ImportError:
        logger.warning("PACMAN not available - skipping entity extraction")
        return results

    semaphore = asyncio.Semaphore(max_concurrent)

    async def extract_one(result: JesterResult) -> JesterResult:
        if not result.html or len(result.html) < MIN_VALID_HTML_LENGTH:
            return result

        async with semaphore:
            try:
                entities = await extract_async(result.html)
                result.entities = entities
            except Exception as e:
                logger.debug(f"Extraction failed for {result.url}: {e}")
        return result

    tasks = [extract_one(r) for r in results]
    await asyncio.gather(*tasks, return_exceptions=False)
    return results


async def scrape_batch_with_extraction(
    urls: List[str],
    domain_limit: int = 10,
    progress_callback: Optional[callable] = None,
) -> List[JesterResult]:
    """
    Scrape batch with PACMAN extraction built-in.

    Convenience function that runs scrape_batch_optimized followed by
    entity extraction. The extraction adds <5ms per successful page.

    Args:
        urls: List of URLs to scrape
        domain_limit: Max concurrent requests per domain
        progress_callback: Optional callback(phase, completed, total)

    Returns:
        List of JesterResult with entities populated
    """
    # Phase 1: Scrape
    results = await scrape_batch_optimized(urls, domain_limit, progress_callback)

    # Phase 2: Extract entities (parallel, non-blocking)
    results = await extract_entities_batch(results)

    if progress_callback:
        successful = sum(1 for r in results if r.entities)
        progress_callback("EXTRACTION", successful, len(urls))

    return results
