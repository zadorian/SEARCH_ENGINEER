"""
Universal "Drill" Scraper
Implements the fallback chain: Live -> Firecrawl -> Archive (CC/Wayback).
"""

import asyncio
import aiohttp
import logging
import time
import random
import re
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from urllib.parse import urlparse

from .cc_first_scraper import CCFirstScraper, ScrapeResult
from .binary_extractor import BinaryTextExtractor
from .warc_parser import html_to_markdown

try:
    from submarine.rov.session_injector import SessionInjector
    AUTH_PLUGIN_AVAILABLE = True
except ImportError:
    AUTH_PLUGIN_AVAILABLE = False
    SessionInjector = None

try:
    from submarine.seekleech import SeekLeech
    SEEKLEECH_AVAILABLE = True
except ImportError:
    SEEKLEECH_AVAILABLE = False
    SeekLeech = None

logger = logging.getLogger(__name__)

try:
    from jester.scraper import Jester, JesterConfig, JesterMethod
    JESTER_AVAILABLE = True
except ImportError:
    JESTER_AVAILABLE = False
    Jester = None
    JesterConfig = None
    JesterMethod = None

@dataclass
class UniversalScrapeResult(ScrapeResult):
    """Extended result with drill-specific metadata."""
    drill_mode: str = "live"  # 'live', 'firecrawl', 'archive'
    jester_method: Optional[str] = None
    next_page_url: Optional[str] = None
    search_config: Optional[Dict] = None  # Populated by SeekLeech

class UniversalScraper:
    """
    Comprehensive scraper implementing the "Drill" strategy:
    1. Live Fetch (Fast, Parallel, Binary-aware)
    2. Firecrawl (Paid fallback for difficult live sites)
    3. Archive (Common Crawl / Wayback for offline content)
    4. Authenticated Deep Dive (via Jester Auth Plugin)
    5. Autonomous Search Discovery (via SeekLeech)
    """

    def __init__(
        self,
        firecrawl_key: Optional[str] = None,
        timeout: float = 10.0,
        max_concurrent: int = 50,
        convert_to_markdown: bool = True,
        use_jester: bool = True,
        jester_config: Optional["JesterConfig"] = None,
        auth_session_dir: Optional[str] = None,
        auto_detect_search: bool = False
    ):
        self.cc_scraper = CCFirstScraper(
            firecrawl_api_key=firecrawl_key,
            timeout=timeout,
            max_connections=max_concurrent,
            convert_to_markdown=convert_to_markdown
        )
        self.binary_extractor = BinaryTextExtractor()
        self.timeout = aiohttp.ClientTimeout(total=timeout, connect=5.0)
        self.session: Optional[aiohttp.ClientSession] = None
        self.convert_to_markdown = convert_to_markdown
        self.jester = None
        self.session_injector = None
        self.auto_detect_search = auto_detect_search
        self.seekleech = None

        if use_jester and JESTER_AVAILABLE:
            self.jester = Jester(jester_config or JesterConfig())
            
        if AUTH_PLUGIN_AVAILABLE:
            self.session_injector = SessionInjector(auth_session_dir)

        if SEEKLEECH_AVAILABLE and auto_detect_search:
            self.seekleech = SeekLeech()

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=self.timeout,
                headers=self.headers
            )
        return self.session

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
        await self.cc_scraper.close()
        if self.jester:
            await self.jester.close()
        if self.seekleech:
            await self.seekleech.close()

    def _maybe_convert_html(self, html: str, raw_html: bool) -> str:
        if raw_html or not self.convert_to_markdown:
            return html
        return html_to_markdown(html)

    def _looks_like_login_page(self, html: str) -> bool:
        if not html:
            return False
        if re.search(r'type=["\']password["\']', html, re.IGNORECASE):
            return bool(re.search(r'(log\s*in|sign\s*in|password|two-factor|mfa|otp)', html, re.IGNORECASE))
        return False

    def _resolve_jester_method(self, method: Optional[Any]) -> Optional["JesterMethod"]:
        if not method or not JESTER_AVAILABLE:
            return None
        if isinstance(method, JesterMethod):
            return method
        if isinstance(method, str):
            cleaned = method.strip().lower()
            mapping = {
                "a": JesterMethod.JESTER_A,
                "b": JesterMethod.JESTER_B,
                "c": JesterMethod.JESTER_C,
                "d": JesterMethod.JESTER_D,
                "jester_a": JesterMethod.JESTER_A,
                "jester_b": JesterMethod.JESTER_B,
                "jester_c": JesterMethod.JESTER_C,
                "jester_d": JesterMethod.JESTER_D,
                "firecrawl": JesterMethod.FIRECRAWL,
                "brightdata": JesterMethod.BRIGHTDATA,
            }
            return mapping.get(cleaned)
        return None
        
    def _detect_pagination(self, html: str, current_url: str) -> Optional[str]:
        """
        Heuristic to find the 'Next' page URL.
        Strategy:
        1. Look for <link rel="next"> (High confidence)
        2. Look for <a>Next</a> or <a>></a> near bottom
        3. Look for URL increment pattern (page=1 -> page=2)
        """
        # 1. SEO Rel=Next (Best)
        match = re.search(r'<link[^>]+rel=["\"]next["\"][^>]+href=["\"]([^"\"]+)["\"]', html, re.IGNORECASE)
        if match:
            return match.group(1)

        # 2. Heuristic Search
        # Reduce search space to the last 15% of the document to avoid navbars
        footer_zone = html[int(len(html)*0.85):]
        
        # Look for "Next" or "More" text in anchors
        next_match = re.search(r'<a[^>]+href=["\"]([^"\"]+)["\"][^>]*>\s*(?:Next|More|&gt;|»)\s*</a>', footer_zone, re.IGNORECASE)
        if next_match:
            return next_match.group(1)
            
        return None

    async def _fetch_live(
        self,
        url: str,
        raw_html: bool = False,
        jester_method: Optional[Any] = None,
    ) -> Optional[Tuple[str, str, int, Optional[str]]]:
        """
        Try to fetch URL live.
        Returns (content, content_source_type, status_code, jester_method) or None.
        """
        # 1. Check for Auth Session (Deep Dive / Librarian Mode)
        is_authenticated = False
        parsed = urlparse(url if "://" in url else f"https://{url}")
        domain = parsed.netloc or parsed.path.split("/")[0]
        
        if self.session_injector and self.session_injector.has_session(domain):
            is_authenticated = True
            logger.info(f"[Librarian] Authenticated session found for {domain}. Engaging stealth mode.")
            
            # Prefer Jester-D (Headless) for authenticated sessions that need JS-heavy flows
            if not jester_method and JESTER_AVAILABLE and JesterMethod:
                jester_method = JesterMethod.JESTER_D
            
            # Throttling for safety
            delay = random.uniform(3.0, 7.0)
            logger.info(f"[Librarian] Throttling for {delay:.2f}s...")
            await asyncio.sleep(delay)

        auth_cookies = None
        if is_authenticated and self.session_injector:
            cookie_records = self.session_injector.load_cookies(domain)
            if cookie_records:
                auth_cookies = {
                    cookie.get("name"): cookie.get("value")
                    for cookie in cookie_records
                    if cookie.get("name") and cookie.get("value") is not None
                }

        async def fetch_with_aiohttp(cookies: Optional[Dict[str, str]] = None):
            try:
                session = await self._get_session()
                async with session.get(
                    url,
                    allow_redirects=True,
                    ssl=False,
                    cookies=cookies,
                ) as response:
                    if response.status == 200:
                        content_type = response.headers.get('Content-Type', '').lower()

                        if self.binary_extractor.can_extract(content_type):
                            data = await response.read()
                            result = self.binary_extractor.extract_text(data, content_type)
                            if result.success:
                                return result.text, "live_binary", response.status, None

                        text = await response.text(errors='replace')

                        if is_authenticated and self._looks_like_login_page(text):
                            logger.info(f"[Librarian] Login page detected for {domain} (cookie fetch).")
                            return None

                        if 'text/html' in content_type:
                            converted = self._maybe_convert_html(text, raw_html)
                            return converted, "live_html", response.status, None

                        return text, "live_text", response.status, None

            except Exception as e:
                logger.debug(f"[UniversalScraper] Live fetch failed for {url}: {e}")
            return None

        did_cookie_attempt = False
        if is_authenticated and auth_cookies:
            cookie_hit = await fetch_with_aiohttp(auth_cookies)
            did_cookie_attempt = True
            if cookie_hit:
                return cookie_hit

        if self.jester:
            try:
                forced = self._resolve_jester_method(jester_method)
                
                # Note: Jester does not yet accept session injection; cookie-based fetch runs before this path.
                
                result = await self.jester.scrape(url, force_method=forced)
                if result and result.html:
                    if is_authenticated and self._looks_like_login_page(result.html):
                        logger.info(f"[Librarian] Login page detected for {domain} (jester).")
                        return None
                    html = self._maybe_convert_html(result.html, raw_html)
                    return html, "jester", result.status_code, result.method.value
            except Exception as e:
                logger.debug(f"[UniversalScraper] Jester fetch failed for {url}: {e}")

        # Fallback to standard request if Jester fails or is not used.
        fallback_cookies = None
        if is_authenticated and auth_cookies and not did_cookie_attempt:
            fallback_cookies = auth_cookies
        return await fetch_with_aiohttp(fallback_cookies)

        return None

    async def fetch_live_coverage(
        self,
        url: str,
        raw_html: bool = False,
        include_brightdata: bool = True,
        include_firecrawl: bool = False,
        fast_first: bool = False,
        max_bytes: Optional[int] = None,
    ) -> Optional[Tuple[str, str, int, Optional[str]]]:
        """
        Coverage-max live fetch:
        run all JESTER methods in parallel and return the strongest result.
        """
        if not self.jester or not JESTER_AVAILABLE:
            return await self._fetch_live(url, raw_html=raw_html)

        method_calls = [
            ("jester_a", self.jester.scrape_a),
            ("jester_b", self.jester.scrape_b),
            ("jester_c", self.jester.scrape_c),
            ("jester_d", self.jester.scrape_d),
        ]
        if include_firecrawl:
            method_calls.append(("firecrawl", self.jester.scrape_firecrawl))
        if include_brightdata:
            method_calls.append(("brightdata", self.jester.scrape_brightdata))

        async def run_method(name, func):
            try:
                result = await func(url)
                if result and result.html:
                    html = result.html
                    if max_bytes and max_bytes > 0:
                        html = html[:max_bytes]
                    html = self._maybe_convert_html(html, raw_html)
                    return html, "jester", result.status_code, result.method.value
            except Exception as e:
                logger.debug(f"[UniversalScraper] Jester {name} failed for {url}: {e}")
            return None

        tasks = [asyncio.create_task(run_method(name, func)) for name, func in method_calls]
        if fast_first:
            while tasks:
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    try:
                        item = task.result()
                    except Exception:
                        item = None
                    if isinstance(item, tuple) and item and item[0]:
                        for leftover in pending:
                            leftover.cancel()
                        return item
                tasks = list(pending)
        results = await asyncio.gather(*tasks, return_exceptions=True)

        best = None
        best_len = 0
        for item in results:
            if isinstance(item, tuple) and item and item[0]:
                content_len = len(item[0])
                if content_len > best_len:
                    best = item
                    best_len = content_len

        if best:
            return best

        return await self._fetch_live(url, raw_html=raw_html)

    async def scrape(
        self,
        url: str,
        allow_firecrawl: bool = True,
        allow_archive: bool = True,
        allow_live: bool = True,
        prefer_archive: bool = False,
        raw_html: bool = False,
        jester_method: Optional[Any] = None,
        auto_detect_search: bool = False
    ) -> UniversalScrapeResult:
        """
        Scrape a single URL using the Drill strategy.
        """
        start_time = time.time()
        
        # Decide if we should run SeekLeech (Search Discovery)
        # We only do this for live scrapes where we have high intent
        should_run_seekleech = (self.auto_detect_search or auto_detect_search) and self.seekleech

        # 1. Prefer Archive first (optional)
        if prefer_archive and allow_archive:
            archive_res = await self._fetch_archive(url, raw_html=raw_html)
            if archive_res:
                content, source_type, timestamp = archive_res
                latency = int((time.time() - start_time) * 1000)
                return UniversalScrapeResult(
                    url=url,
                    content=content,
                    source=source_type,
                    status=200,
                    timestamp=timestamp,
                    latency_ms=latency,
                    drill_mode="archive"
                )

        # 2. Try Live (JESTER A-D or aiohttp)
        if allow_live:
            live_res = await self._fetch_live(url, raw_html=raw_html, jester_method=jester_method)
            if live_res:
                content, source_type, status_code, jester_used = live_res
                latency = int((time.time() - start_time) * 1000)
                
                # Run SeekLeech if enabled
                search_config = None
                if should_run_seekleech:
                    try:
                        logger.info(f"📡 SeekLeech: Scanning {url} for search templates...")
                        # SeekLeech expects a dict with 'url' and 'domain'
                        domain = url.split("//")[-1].split("/")[0]
                        seek_res = await self.seekleech.mine({"url": url, "domain": domain})
                        if seek_res.status == "found":
                            search_config = seek_res.to_dict()
                            logger.info(f"🎯 SeekLeech: Found search template!")
                    except Exception as e:
                        logger.warning(f"SeekLeech failed: {e}")

                return UniversalScrapeResult(
                    url=url,
                    content=content,
                    source=source_type,
                    status=status_code or 200,
                    latency_ms=latency,
                    drill_mode="live",
                    jester_method=jester_used,
                    search_config=search_config
                )

        # 3. Try Firecrawl (paid accelerator) if allowed
        if allow_firecrawl:
            # 2. Try Firecrawl (via CCFirstScraper's helper which handles auth check)
            # Note: CCFirstScraper.fetch_from_firecrawl logs errors but returns None on fail
            fc_content = await self.cc_scraper.fetch_from_firecrawl(url)
            if fc_content:
                latency = int((time.time() - start_time) * 1000)
                return UniversalScrapeResult(
                    url=url,
                    content=fc_content,
                    source="firecrawl",
                    status=200,
                    latency_ms=latency,
                    drill_mode="firecrawl"
                )
        
        # 4. Try Archive (CC + Wayback racing)
        if not allow_archive:
            latency = int((time.time() - start_time) * 1000)
            return UniversalScrapeResult(
                url=url,
                content="",
                source="failed",
                status=0,
                latency_ms=latency,
                drill_mode="failed"
            )

        archive_res = await self._fetch_archive(url, raw_html=raw_html)
        content = None
        source = "failed"
        timestamp = None
        if archive_res:
            content, source, timestamp = archive_res

        latency = int((time.time() - start_time) * 1000)
        
        return UniversalScrapeResult(
            url=url,
            content=content or "",
            source=source,
            status=200 if content else 0,
            timestamp=timestamp,
            latency_ms=latency,
            drill_mode="archive" if content else "failed"
        )

    async def _fetch_archive(
        self,
        url: str,
        raw_html: bool = False,
    ) -> Optional[Tuple[str, str, Optional[str]]]:
        """Fetch from CC or Wayback (first available)."""
        # Manually trigger archive fetch from CCFirstScraper components
        cc_task = asyncio.create_task(self.cc_scraper._fetch_cc_full(url))
        wayback_task = asyncio.create_task(self.cc_scraper.fetch_from_wayback(url))

        pending = {cc_task, wayback_task}
        content = None
        source = None
        timestamp = None

        while pending and not content:
            done, pending = await asyncio.wait(
                pending,
                return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                try:
                    result = task.result()
                    if task == cc_task:
                        if result and result[0]:
                            content, loc = result
                            source = 'cc'
                            timestamp = loc.get('timestamp') if loc else None
                    else:
                        if result:
                            content = result
                            source = 'wayback'
                except Exception:
                    pass

            if content:
                for task in pending:
                    task.cancel()
                break

        if content and source:
            return content, source, timestamp

        return None

    async def batch_scrape(self, urls: List[str]) -> Dict[str, UniversalScrapeResult]:
        """Batch scrape multiple URLs in parallel."""
        tasks = [self.scrape(url) for url in urls]
        results = await asyncio.gather(*tasks)
        return {res.url: res for res in results}
