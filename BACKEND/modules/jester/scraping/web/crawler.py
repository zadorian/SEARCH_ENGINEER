"""
DRILL Crawler

Main crawler implementation using Crawlee with Firecrawl optimizations.
Integrates discovery, extraction, embedding, and indexing into a single pipeline.

Key optimizations from Firecrawl:
- Sitemap-first discovery
- Intelligent rate limiting
- robots.txt respect
- Content type filtering
- Deduplication
"""

import asyncio
import hashlib
import os
import re
import time
from uuid import uuid4
from typing import List, Dict, Any, Optional, Set, Callable, AsyncGenerator, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse, urljoin
from pathlib import Path

# Crawlee imports
try:
    from crawlee import PlaywrightCrawler, BeautifulSoupCrawler
    from crawlee.crawlers import BasicCrawler
    from crawlee.http_clients import CurlHttpClient
    from crawlee.storages import RequestQueue
    CRAWLEE_AVAILABLE = True
except ImportError:
    CRAWLEE_AVAILABLE = False

# Fallback: Use aiohttp for basic crawling if Crawlee not available
import aiohttp

# Local imports
from .extractors import EntityExtractor, ExtractedEntities
from .embedder import DrillEmbedder, FASTEMBED_AVAILABLE
from .indexer import DrillIndexer, PageDocument
from .discovery import DrillDiscovery, DiscoveryResult
from ..universal_scraper import UniversalScraper
from ...core.storage import MemoryStorage, SQLiteStorage, RedisStorage, StorageBackend, QueueItem
from ...extraction.universal_extractor import UniversalExtractor
from .cc_offline_sniper import CCIndexOfflineLookup

# Go bridge for hybrid crawling
from .go_bridge import GoBridge, CrawlResult as GoCrawlResult, colly_available, rod_available, ScreenshotRule, ScreenshotResult

# Go-inspired link processing (ported from GlobalLinks)
from .link_processor import (
    StreamingLinkParser,
    ScoringConfig,
    extract_links_from_html,
    build_url_record,
    verify_url_quality,
    calculate_relevance_score,
    get_domain_from_url,
    page_hash,
    get_cache_stats,
)

try:
    from SUBMARINE.rov.session_injector import SessionInjector
    AUTH_PLUGIN_AVAILABLE = True
except ImportError:
    AUTH_PLUGIN_AVAILABLE = False
    SessionInjector = None


@dataclass
class DrillConfig:
    """Configuration for DRILL crawler."""
    # Crawl settings
    max_pages: int = 1000
    max_depth: int = 10
    max_pages_per_depth: Optional[List[int]] = None
    max_concurrent: int = 50  # Can go higher, but 50 is safe for most targets
    request_timeout: int = 30
    delay_between_requests: float = 0.1  # Minimal courtesy delay

    # Discovery settings
    use_sitemap_first: bool = True  # Firecrawl optimization
    discover_subdomains: bool = True
    discover_archives: bool = True

    # Content settings
    allowed_content_types: Set[str] = field(default_factory=lambda: {
        'text/html', 'application/xhtml+xml'
    })
    skip_extensions: Set[str] = field(default_factory=lambda: {
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
        '.zip', '.rar', '.tar', '.gz', '.7z',
        '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico',
        '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv',
        '.css', '.js', '.json', '.xml', '.rss',
        '.woff', '.woff2', '.ttf', '.eot',
    })

    # Extraction settings
    extract_entities: bool = True
    generate_embeddings: bool = True
    index_to_elasticsearch: bool = True

    # Rate limiting
    # NOTE: robots.txt is IGNORED by default - this is investigation crawling,
    # not search engine indexing. We're not publishing, we're investigating.
    respect_robots_txt: bool = False
    default_crawl_delay: float = 0.5  # Courtesy delay only

    # Archive freshness settings (CC + Wayback)
    # Policy: "always_skip", "skip_if_recent", "never_skip", "report_only"
    archive_skip_policy: str = "skip_if_recent"
    archive_recent_threshold_days: int = 90  # Skip if archived within X days
    check_cc_freshness: bool = True          # Check Common Crawl
    check_wayback_freshness: bool = True     # Check Wayback Machine

    # Output
    output_dir: Optional[Path] = None
    save_html: bool = False  # Save raw HTML

    # Project context
    project_id: Optional[str] = None
    mission_id: Optional[str] = None
    mission_budget: Optional[int] = None

    # Persistent queue / storage
    # storage_backend: memory | sqlite | redis
    storage_backend: str = "memory"
    storage_path: str = "crawler_storage.db"
    redis_url: Optional[str] = None
    redis_namespace: str = "drill"
    redis_use_bloom: bool = False
    use_persistent_queue: Optional[bool] = None
    resume_state: bool = True
    state_save_interval: int = 50

    # Go-inspired link processing (ported from GlobalLinks)
    use_optimized_link_extraction: bool = True  # Use Go-style link processor
    link_scoring_keywords: List[str] = field(default_factory=list)  # Keywords for relevance scoring
    country_tld_filter: List[str] = field(default_factory=list)  # E.g., [".ru", ".ky", ".cy"]
    min_link_relevance_score: int = 10  # Minimum score to include link

    # HYBRID CRAWLING (Go/Colly fast path + Python/Playwright slow path)
    # When enabled, static HTML pages are crawled with Go/Colly (500+ concurrent)
    # and JS-heavy pages fall back to Python/Playwright (50 concurrent)
    use_hybrid_crawler: bool = True              # Enable Go fast path when available
    go_crawler_concurrent: int = 500             # Go concurrency (can go to 1000+)
    force_playwright_domains: List[str] = field(default_factory=list)  # Always use Playwright for these
    js_detection_aggressive: bool = False        # Aggressive = more Colly, Conservative = more Playwright

    # UNIFIED SCREENSHOT TRIGGERING
    # Screenshots work regardless of which crawler (Colly, Rod, Playwright) fetched content.
    # Content is checked against rules in Python, then matching URLs are dispatched to Rod.
    screenshot_rules: List['ScreenshotRule'] = field(default_factory=list)  # Rules for when to screenshot
    screenshot_dir: Optional[Path] = None        # Directory to save screenshots
    screenshot_all: bool = False                 # Screenshot everything (overrides rules)
    screenshot_full_page: bool = False           # Default to full page screenshots
    screenshot_quality: int = 90                 # JPEG quality (0-100)

    # Universal scraper (JESTER A-D + archive) for persistent queue mode
    use_universal_scraper: bool = False
    universal_use_jester: bool = True
    jester_method: Optional[str] = None  # A, B, C, D, firecrawl, brightdata

    # Auth session injection (ROV)
    auth_use_sessions: bool = True
    auth_session_dir: Optional[str] = None
    auth_login_detection: bool = True

    # Tripwire routing (UniversalExtractor)
    enable_tripwire_routing: bool = False
    tripwire_priority_boost: int = 5
    tripwire_trigger_on: List[str] = field(default_factory=lambda: [
        "red_flag_entities",
        "red_flag_themes",
        "phenomena",
    ])

    # Yield telemetry (kill low-yield branches)
    enable_yield_telemetry: bool = False
    yield_min_ratio: float = 0.01
    yield_min_samples: int = 25
    yield_drop_mode: str = "skip"  # skip | deprioritize

    # CC Offline Sniper preference
    cc_offline_sniper_enabled: bool = False
    cc_offline_archive: str = "CC-MAIN-2024-10"
    cc_offline_recent_days: int = 30
    cc_offline_limit: int = 200
    cc_offline_max_concurrent: int = 8

    # Sprint vs Marathon queue bias (persistent queue mode)
    sprint_priority_score_threshold: int = 50
    sprint_queue_ratio: float = 0.5  # Fraction of dequeues biased to sprint queue
    sprint_priority_patterns: List[str] = field(default_factory=lambda: [
        r"/(investor|investors|investor-relations|ir)\b",
        r"/(annual|report|reports|financials?|filings?|sec|10-k|10q|20-f|prospectus)\b",
        r"/(team|leadership|management|board)\b",
        r"/(about|company|overview)\b",
        r"/(press|news|media|blog)\b",
        r"/(governance|compliance|ethics|policy|legal|privacy|terms)\b",
    ])

    # Fractal Hunger (mission spawning)
    enable_fractal_hunger: bool = False
    fractal_budget_ratio: float = 0.2
    fractal_max_spawns: int = 25
    fractal_max_spawns_per_page: int = 3
    fractal_spawn_keywords: List[str] = field(default_factory=lambda: [
        "subsidiary",
        "affiliate",
        "parent",
        "holding",
        "holdings",
        "group",
        "portfolio",
        "investor",
        "partner",
        "acquisition",
    ])
    fractal_min_relevance_score: int = 60
    fractal_trigger_min_entities: int = 5
    fractal_trigger_on_tripwire: bool = True


@dataclass
class CrawlStats:
    """Statistics for a crawl session."""
    domain: str
    pages_crawled: int = 0
    pages_failed: int = 0
    pages_skipped_archive: int = 0  # Skipped due to archive freshness
    entities_extracted: int = 0
    urls_discovered: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    # Archive freshness data
    archive_freshness_report: Optional[Dict[str, Any]] = None

    # Link processing stats (Go-style)
    links_extracted: int = 0
    links_filtered: int = 0
    high_relevance_links: int = 0  # Links with score > 50
    domain_cache_stats: Optional[Dict[str, Any]] = None

    # Hybrid crawling stats (Go/Colly + Go/Rod + Python/Playwright)
    pages_go_crawled: int = 0       # Crawled with Go/Colly (fast path - static HTML)
    pages_rod_crawled: int = 0      # Crawled with Go/Rod (medium path - JS rendering)
    pages_playwright: int = 0       # Crawled with Playwright (slow path - fallback)
    go_crawler_time_ms: int = 0     # Time spent in Go/Colly crawler
    rod_crawler_time_ms: int = 0    # Time spent in Go/Rod crawler

    # Screenshot stats (unified triggering)
    screenshots_taken: int = 0       # Total screenshots captured
    screenshots_triggered: int = 0   # Pages that matched rules (queued)
    screenshots_failed: int = 0      # Screenshot failures
    screenshot_rules_matched: Dict[str, int] = field(default_factory=dict)  # Rule name -> count

    @property
    def duration_seconds(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0

    @property
    def pages_per_second(self) -> float:
        if self.duration_seconds > 0:
            return self.pages_crawled / self.duration_seconds
        return 0

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "domain": self.domain,
            "pages_crawled": self.pages_crawled,
            "pages_failed": self.pages_failed,
            "pages_skipped_archive": self.pages_skipped_archive,
            "entities_extracted": self.entities_extracted,
            "urls_discovered": self.urls_discovered,
            "duration_seconds": round(self.duration_seconds, 2),
            "pages_per_second": round(self.pages_per_second, 2),
            # Link processing stats
            "links_extracted": self.links_extracted,
            "links_filtered": self.links_filtered,
            "high_relevance_links": self.high_relevance_links,
            # Hybrid crawling stats
            "pages_go_crawled": self.pages_go_crawled,
            "pages_rod_crawled": self.pages_rod_crawled,
            "pages_playwright": self.pages_playwright,
            "go_crawler_time_ms": self.go_crawler_time_ms,
            "rod_crawler_time_ms": self.rod_crawler_time_ms,
            # Screenshot stats
            "screenshots_taken": self.screenshots_taken,
            "screenshots_triggered": self.screenshots_triggered,
            "screenshots_failed": self.screenshots_failed,
        }
        if self.archive_freshness_report:
            result["archive_freshness"] = self.archive_freshness_report
        if self.domain_cache_stats:
            result["domain_cache"] = self.domain_cache_stats
        if self.screenshot_rules_matched:
            result["screenshot_rules_matched"] = self.screenshot_rules_matched
        return result


@dataclass
class CrawlUrlResult:
    """Result of a single URL fetch (used by JESTER_D)."""
    url: str
    html: str
    status_code: int = 0
    content_type: str = "text/html"


class Drill:
    """
    DRILL - Deep Recursive Investigation Link Locator

    Main crawler class integrating Crawlee with LinkLater's capabilities.
    """

    def __init__(self, config: Optional[DrillConfig] = None):
        """
        Initialize DRILL crawler.

        Args:
            config: Crawler configuration (uses defaults if not provided)
        """
        self.config = config or DrillConfig()

        # Components
        self.discovery = DrillDiscovery(
            timeout=self.config.request_timeout,
            max_concurrent=self.config.max_concurrent,
        )
        self.extractor = EntityExtractor()

        # Lazy-loaded components
        self._embedder: Optional[DrillEmbedder] = None
        self._indexer: Optional[DrillIndexer] = None
        self._freshness_checker = None
        self._link_parser: Optional[StreamingLinkParser] = None
        self._go_bridge: Optional[GoBridge] = None
        self._storage: Optional[StorageBackend] = None
        self._universal_scraper: Optional[UniversalScraper] = None
        self._tripwire_extractor: Optional[UniversalExtractor] = None
        self._session_injector: Optional[SessionInjector] = None

        # Link scoring config
        self._scoring_config = ScoringConfig(
            target_keywords=self.config.link_scoring_keywords,
        )
        self._sprint_patterns = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.config.sprint_priority_patterns
        ]
        ratio = min(max(self.config.sprint_queue_ratio, 0.0), 1.0)
        self._sprint_bias_mod = 10
        self._sprint_bias_high = int(round(ratio * self._sprint_bias_mod))
        self._sprint_bias_index = 0

        if self.config.auth_use_sessions and AUTH_PLUGIN_AVAILABLE:
            self._session_injector = SessionInjector(self.config.auth_session_dir)

        # State
        self.visited_urls: Set[str] = set()
        self.page_hashes: Set[str] = set()  # Go-style hash deduplication
        self.stats = CrawlStats(domain="")
        self.archive_freshness_data: List[Any] = []  # Store freshness info for reporting
        self._yield_stats: Dict[str, Dict[str, int]] = {}
        self._low_yield_domains: Set[str] = set()
        self._pages_since_save: int = 0
        self._root_mission_id = self.config.mission_id or f"mission-{uuid4().hex[:8]}"
        self._mission_budgets: Dict[str, int] = {
            self._root_mission_id: self.config.mission_budget or self.config.max_pages
        }
        self._mission_counts: Dict[str, int] = {}
        self._depth_counts: Dict[int, int] = {}
        self._spawned_missions: Set[str] = set()
        self._spawn_count = 0
        self.mission_launcher = None

        # Screenshot queue (unified triggering)
        # Pages matching rules are queued here, then dispatched to Rod at end of crawl
        self._screenshot_queue: List[Dict[str, Any]] = []  # [{url, title, content_preview, rule_name}]
        self._screenshotted_urls: Set[str] = set()  # Track what's been captured
        self._cc_offline_recent_urls: Set[str] = set()

    @property
    def embedder(self) -> Optional[DrillEmbedder]:
        """Lazy load embedder."""
        if self._embedder is None and FASTEMBED_AVAILABLE and self.config.generate_embeddings:
            self._embedder = DrillEmbedder()
        return self._embedder

    @property
    def indexer(self) -> Optional[DrillIndexer]:
        """Lazy load indexer."""
        if self._indexer is None and self.config.index_to_elasticsearch:
            self._indexer = DrillIndexer()
            self._indexer.ensure_indices()
        return self._indexer

    @property
    def freshness_checker(self):
        """Lazy load archive freshness checker."""
        if self._freshness_checker is None:
            try:
                from .archive_freshness import SmartCrawlDecider, SkipPolicy

                policy_map = {
                    "always_skip": SkipPolicy.ALWAYS_SKIP,
                    "skip_if_recent": SkipPolicy.SKIP_IF_RECENT,
                    "never_skip": SkipPolicy.NEVER_SKIP,
                    "report_only": SkipPolicy.REPORT_ONLY,
                }
                policy = policy_map.get(self.config.archive_skip_policy, SkipPolicy.SKIP_IF_RECENT)

                self._freshness_checker = SmartCrawlDecider(
                    skip_policy=policy,
                    recent_threshold_days=self.config.archive_recent_threshold_days,
                )
            except ImportError:
                pass
        return self._freshness_checker

    @property
    def link_parser(self) -> StreamingLinkParser:
        """Lazy load Go-style link parser."""
        if self._link_parser is None:
            self._link_parser = StreamingLinkParser(
                country_tlds=self.config.country_tld_filter,
                url_keywords=self.config.link_scoring_keywords,
                include_internal=True,  # We want internal links for crawling
            )
        return self._link_parser

    @property
    def go_bridge(self) -> Optional[GoBridge]:
        """Lazy load Go bridge for hybrid crawling."""
        if self._go_bridge is None and self.config.use_hybrid_crawler and colly_available():
            self._go_bridge = GoBridge()
        return self._go_bridge

    @property
    def storage(self) -> StorageBackend:
        """Lazy load storage backend (memory/sqlite/redis)."""
        if self._storage is None:
            backend = (self.config.storage_backend or "memory").lower()
            if backend == "sqlite":
                self._storage = SQLiteStorage(self.config.storage_path)
            elif backend == "redis":
                redis_url = self.config.redis_url or "redis://localhost:6379/0"
                self._storage = RedisStorage(
                    redis_url=redis_url,
                    namespace=self.config.redis_namespace,
                    use_bloom=self.config.redis_use_bloom,
                )
            else:
                self._storage = MemoryStorage()
        return self._storage

    @property
    def universal_scraper(self) -> UniversalScraper:
        """Lazy load universal scraper for persistent queue mode."""
        if self._universal_scraper is None:
            self._universal_scraper = UniversalScraper(
                timeout=self.config.request_timeout,
                max_concurrent=self.config.max_concurrent,
                convert_to_markdown=False,
                use_jester=self.config.universal_use_jester,
            )
        return self._universal_scraper

    @property
    def tripwire_extractor(self) -> Optional[UniversalExtractor]:
        """Lazy load universal extractor for tripwire routing."""
        if not self.config.enable_tripwire_routing:
            return None
        if self._tripwire_extractor is None:
            try:
                self._tripwire_extractor = UniversalExtractor()
            except Exception as e:
                print(f"[DRILL] Tripwire extractor unavailable: {e}")
                self._tripwire_extractor = None
        return self._tripwire_extractor

    def _persistent_queue_enabled(self) -> bool:
        if self.config.use_persistent_queue is not None:
            return self.config.use_persistent_queue
        return (self.config.storage_backend or "memory").lower() in {"sqlite", "redis"}

    def _should_use_hybrid(self) -> bool:
        """Check if hybrid crawling should be used."""
        return (
            self.config.use_hybrid_crawler
            and self.go_bridge is not None
            and self.go_bridge.is_available("colly_crawler")
        )

    def _should_screenshot(self) -> bool:
        """Check if screenshots are enabled."""
        return (
            (self.config.screenshot_all or self.config.screenshot_rules)
            and self.config.screenshot_dir is not None
            and rod_available()
        )

    def _get_auth_cookies(self, domain: str) -> Optional[List[Dict[str, Any]]]:
        if not self._session_injector:
            return None
        if not self._session_injector.has_session(domain):
            return None
        return self._session_injector.load_cookies(domain)

    def _looks_like_login_page(self, html: str) -> bool:
        if not html:
            return False
        if re.search(r'type=["\']password["\']', html, re.IGNORECASE):
            return bool(re.search(r'(log\s*in|sign\s*in|password|two-factor|mfa|otp)', html, re.IGNORECASE))
        return False

    async def _fetch_html_with_cookies(
        self,
        url: str,
        cookies: List[Dict[str, Any]],
    ) -> Optional[Tuple[str, int]]:
        cookie_map = {
            cookie.get("name"): cookie.get("value")
            for cookie in cookies
            if cookie.get("name") and cookie.get("value") is not None
        }
        if not cookie_map:
            return None

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=self.config.request_timeout),
                    headers={'User-Agent': 'DRILL/1.0 (investigation crawler)'},
                    cookies=cookie_map,
                    ssl=False,
                ) as response:
                    if response.status != 200:
                        return None
                    html = await response.text(errors='replace')
                    return html, response.status
            except Exception:
                return None

    async def _fetch_html_playwright(
        self,
        url: str,
        auth_cookies: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Tuple[str, int]]:
        if not CRAWLEE_AVAILABLE:
            return None

        html_result: Dict[str, Any] = {"html": "", "status": 0}

        async def page_handler(context):
            request = context.request
            page = context.page if hasattr(context, 'page') else None
            if not page:
                return

            if auth_cookies and not request.user_data.get("auth_injected"):
                try:
                    await page.context.add_cookies(auth_cookies)
                    request.user_data["auth_injected"] = True
                    await page.goto(url, wait_until="domcontentloaded")
                except Exception:
                    pass

            html_result["html"] = await page.content()
            if context.http_response:
                html_result["status"] = context.http_response.status
            else:
                html_result["status"] = 200

        crawler = PlaywrightCrawler(
            max_requests_per_crawl=1,
            max_concurrency=1,
            request_handler=page_handler,
        )

        try:
            await crawler.run([url])
        except Exception:
            return None

        if html_result["html"]:
            return html_result["html"], html_result["status"]
        return None

    def _check_screenshot_trigger(
        self,
        url: str,
        title: str,
        content: str,
    ) -> Optional[str]:
        """
        Check if page content triggers a screenshot rule.

        This is the UNIFIED trigger check - works regardless of which crawler
        (Colly, Rod, or Playwright) fetched the content.

        Returns:
            Rule name if triggered, None otherwise
        """
        if not self._should_screenshot():
            return None

        # Screenshot-all overrides rules
        if self.config.screenshot_all:
            return "always"

        # Check each rule
        for rule in self.config.screenshot_rules:
            matched = False

            if rule.rule_type == "always":
                matched = True

            elif rule.rule_type == "url_contains":
                if rule.value and rule.value.lower() in url.lower():
                    matched = True
                elif rule.keywords:
                    matched = any(kw.lower() in url.lower() for kw in rule.keywords)

            elif rule.rule_type == "url_regex":
                if rule.value:
                    try:
                        if re.search(rule.value, url, re.IGNORECASE):
                            matched = True
                    except re.error:
                        pass

            elif rule.rule_type == "content_contains":
                content_lower = content.lower()
                if rule.value and rule.value.lower() in content_lower:
                    matched = True
                elif rule.keywords:
                    matched = any(kw.lower() in content_lower for kw in rule.keywords)

            elif rule.rule_type == "content_min_length":
                if len(content) >= rule.min_length:
                    matched = True

            elif rule.rule_type == "title_contains":
                title_lower = title.lower()
                if rule.value and rule.value.lower() in title_lower:
                    matched = True
                elif rule.keywords:
                    matched = any(kw.lower() in title_lower for kw in rule.keywords)

            elif rule.rule_type == "domain":
                parsed = urlparse(url)
                domain = parsed.netloc.lower()
                if rule.domains:
                    matched = any(d.lower() in domain for d in rule.domains)

            if matched:
                return rule.name

        return None

    def _queue_screenshot(
        self,
        url: str,
        title: str,
        content: str,
        rule_name: str,
    ):
        """Queue a URL for screenshot capture."""
        if url in self._screenshotted_urls:
            return

        self._screenshot_queue.append({
            "url": url,
            "title": title,
            "content_preview": content[:500],  # For debugging
            "rule_name": rule_name,
        })
        self.stats.screenshots_triggered += 1

        # Track which rules are triggering
        if rule_name not in self.stats.screenshot_rules_matched:
            self.stats.screenshot_rules_matched[rule_name] = 0
        self.stats.screenshot_rules_matched[rule_name] += 1

    async def _dispatch_screenshots(self):
        """
        Dispatch queued URLs to Rod for screenshot capture.

        Called at the end of crawl to batch-capture all triggered screenshots.
        """
        if not self._screenshot_queue:
            return

        if not rod_available():
            print(f"[DRILL] Screenshots: Rod not available, skipping {len(self._screenshot_queue)} screenshots")
            return

        print(f"[DRILL] Screenshots: Capturing {len(self._screenshot_queue)} pages...")

        # Ensure screenshot dir exists
        screenshot_dir = Path(self.config.screenshot_dir)
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        # Get or create Go bridge
        bridge = self._go_bridge or GoBridge()

        for item in self._screenshot_queue:
            url = item["url"]
            if url in self._screenshotted_urls:
                continue

            try:
                # Generate filename from URL
                parsed = urlparse(url)
                safe_domain = parsed.netloc.replace(".", "_")
                safe_path = parsed.path.replace("/", "_")[:50]
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                filename = f"{safe_domain}{safe_path}_{timestamp}.png"
                output_path = str(screenshot_dir / filename)

                # Take screenshot via Rod
                result = await bridge.take_screenshot(
                    url=url,
                    output_path=output_path,
                    full_page=self.config.screenshot_full_page,
                    quality=self.config.screenshot_quality,
                    timeout=30,
                )

                if result.error:
                    print(f"[DRILL] Screenshot failed for {url}: {result.error}")
                    self.stats.screenshots_failed += 1
                else:
                    self.stats.screenshots_taken += 1
                    self._screenshotted_urls.add(url)

            except Exception as e:
                print(f"[DRILL] Screenshot error for {url}: {e}")
                self.stats.screenshots_failed += 1

        print(f"[DRILL] Screenshots: {self.stats.screenshots_taken} captured, {self.stats.screenshots_failed} failed")

    @staticmethod
    def _parse_cc_timestamp(timestamp: Optional[str]) -> Optional[datetime]:
        if not timestamp:
            return None
        try:
            return datetime.strptime(timestamp, "%Y%m%d%H%M%S")
        except ValueError:
            return None

    async def _prime_cc_offline(self, domain: str) -> None:
        if not self.config.cc_offline_sniper_enabled:
            return

        self._cc_offline_recent_urls.clear()
        client = CCIndexOfflineLookup(self.config.cc_offline_archive)

        try:
            if hasattr(client, "lookup_domain_async"):
                results = await client.lookup_domain_async(
                    domain,
                    limit=self.config.cc_offline_limit,
                    max_concurrent=self.config.cc_offline_max_concurrent,
                )
            else:
                loop = asyncio.get_running_loop()
                results = await loop.run_in_executor(
                    None, lambda: client.lookup_domain(domain, limit=self.config.cc_offline_limit)
                )
        except Exception as e:
            print(f"[DRILL] CC Offline Sniper failed: {e}")
            return

        now = datetime.utcnow()
        for item in results or []:
            url = item.get("url")
            ts = self._parse_cc_timestamp(item.get("timestamp"))
            if not url or not ts:
                continue
            if (now - ts).days <= self.config.cc_offline_recent_days:
                self._cc_offline_recent_urls.add(url.lower())

    def _should_prefer_archive(self, url: str) -> bool:
        if not self.config.cc_offline_sniper_enabled:
            return False
        return url.lower() in self._cc_offline_recent_urls

    def _evaluate_tripwire(self, content: str, entities: ExtractedEntities) -> Dict[str, Any]:
        extractor = self.tripwire_extractor
        if not extractor:
            return {"triggered": False, "signals": {}, "summary": {}}

        entity_payload: List[Dict[str, Any]] = []
        for company in entities.companies:
            entity_payload.append({"type": "company", "value": company, "confidence": 0.7})
        for person in entities.persons:
            entity_payload.append({"type": "person", "value": person, "confidence": 0.7})
        for email in entities.emails:
            entity_payload.append({"type": "email", "value": email, "confidence": 0.6})
        for phone in entities.phones:
            entity_payload.append({"type": "phone", "value": phone, "confidence": 0.6})

        result = extractor.extract(content, entities=entity_payload)
        signals = {}
        for key in self.config.tripwire_trigger_on:
            value = getattr(result, key, None)
            if value:
                signals[key] = value

        return {
            "triggered": bool(signals),
            "signals": signals,
            "summary": {key: len(value) for key, value in signals.items()},
            "has_red_flag_entity": result.has_red_flag_entity,
        }

    def _update_yield(self, domain: str, entity_count: int) -> None:
        stats = self._yield_stats.setdefault(domain, {"pages": 0, "entities": 0})
        stats["pages"] += 1
        stats["entities"] += entity_count

        if not self.config.enable_yield_telemetry:
            return
        if stats["pages"] < self.config.yield_min_samples:
            return

        ratio = stats["entities"] / max(stats["pages"], 1)
        if ratio < self.config.yield_min_ratio:
            self._low_yield_domains.add(domain)

    def _yield_decision(self, domain: str) -> Tuple[bool, int]:
        if not self.config.enable_yield_telemetry:
            return False, 0
        if domain not in self._low_yield_domains:
            return False, 0
        if self.config.yield_drop_mode == "deprioritize":
            return False, -1
        return True, 0

    async def _load_state(self, domain: str) -> bool:
        if not self._persistent_queue_enabled():
            return False
        if not self.config.resume_state:
            await self.storage.clear()
            return False

        state = await self.storage.load_state()
        if not state or state.get("domain") != domain:
            await self.storage.clear()
            return False

        self.page_hashes = set(state.get("page_hashes", []))
        self._yield_stats = state.get("yield_stats", {}) or {}
        self._low_yield_domains = set(state.get("low_yield_domains", []))
        self.stats.pages_crawled = state.get("pages_crawled", 0)
        self.stats.pages_failed = state.get("pages_failed", 0)
        self.stats.pages_skipped_archive = state.get("pages_skipped_archive", 0)
        self.stats.entities_extracted = state.get("entities_extracted", 0)
        self.stats.urls_discovered = state.get("urls_discovered", 0)
        return True

    async def _save_state(self, domain: str) -> None:
        state = {
            "domain": domain,
            "page_hashes": list(self.page_hashes),
            "yield_stats": self._yield_stats,
            "low_yield_domains": list(self._low_yield_domains),
            "pages_crawled": self.stats.pages_crawled,
            "pages_failed": self.stats.pages_failed,
            "pages_skipped_archive": self.stats.pages_skipped_archive,
            "entities_extracted": self.stats.entities_extracted,
            "urls_discovered": self.stats.urls_discovered,
        }
        await self.storage.save_state(state)

    async def _maybe_save_state(self, domain: str, force: bool = False) -> None:
        if not self._persistent_queue_enabled():
            return
        self._pages_since_save += 1
        if force or self._pages_since_save >= self.config.state_save_interval:
            await self._save_state(domain)
            self._pages_since_save = 0

    async def _fetch_html(
        self,
        url: str,
        prefer_archive: bool = False,
    ) -> Optional[Tuple[str, int, str]]:
        if self.config.use_universal_scraper or self._persistent_queue_enabled():
            result = await self.universal_scraper.scrape(
                url=url,
                allow_firecrawl=True,
                allow_archive=True,
                allow_live=True,
                prefer_archive=prefer_archive,
                raw_html=True,
                jester_method=self.config.jester_method,
            )
            if result and result.content:
                return result.content, result.status or 0, result.source
            return None

        # Fallback to simple live fetch
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=self.config.request_timeout),
                    headers={'User-Agent': 'DRILL/1.0 (investigation crawler)'}
                ) as response:
                    if response.status != 200:
                        return None
                    html = await response.text()
                    return html, response.status, "live"
            except Exception:
                return None

    async def crawl(
        self,
        domain: str,
        seed_urls: Optional[List[str]] = None,
        on_page: Optional[Callable[[PageDocument], None]] = None,
        seed_plan: Optional[Dict[str, List[str]]] = None,
        lane_budgets: Optional[Dict[str, int]] = None,
    ) -> CrawlStats:
        """
        Crawl a domain with full pipeline.

        Args:
            domain: Target domain (e.g., "example.com")
            seed_urls: Optional starting URLs (discovered automatically if not provided)
            on_page: Optional callback for each crawled page
            seed_plan: Optional lane -> seed URLs mapping (sprint/marathon/archive)
            lane_budgets: Optional lane budgets (max pages per lane)

        Returns:
            CrawlStats with crawl results
        """
        # Clean domain
        domain = domain.lower().strip()
        if domain.startswith(('http://', 'https://')):
            domain = urlparse(domain).netloc

        self.stats = CrawlStats(domain=domain)
        self.stats.start_time = datetime.utcnow()
        self.visited_urls.clear()
        self._screenshot_queue.clear()
        self._screenshotted_urls.clear()
        self.page_hashes.clear()
        self._yield_stats.clear()
        self._low_yield_domains.clear()
        self._pages_since_save = 0
        self._cc_offline_recent_urls.clear()
        self._mission_counts.clear()
        self._depth_counts.clear()
        self._spawned_missions.clear()
        self._spawn_count = 0
        self._root_mission_id = self.config.mission_id or f"mission-{uuid4().hex[:8]}"
        self._mission_budgets = {
            self._root_mission_id: self.config.mission_budget or self.config.max_pages
        }

        # Phase 1: Discovery (Firecrawl optimization - sitemap first)
        if seed_plan:
            urls_to_crawl = []
            for lane, urls in seed_plan.items():
                if not urls:
                    continue
                urls_to_crawl.extend(urls)
            self.stats.urls_discovered = len(urls_to_crawl)
        elif seed_urls:
            urls_to_crawl = list(seed_urls)
            self.stats.urls_discovered = len(urls_to_crawl)
        elif self.config.use_sitemap_first:
            print(f"[DRILL] Discovering URLs for {domain}...")
            discovery_result = await self.discovery.discover(
                domain,
                include_subdomains=self.config.discover_subdomains,
                include_archives=self.config.discover_archives,
            )
            urls_to_crawl = self.discovery.get_crawl_seeds(discovery_result)
            self.stats.urls_discovered = discovery_result.total_urls
            print(f"[DRILL] Discovered {self.stats.urls_discovered} URLs from {len(discovery_result.urls_by_source)} sources")
        else:
            urls_to_crawl = [f"https://{domain}"]
            self.stats.urls_discovered = 1

        # Phase 1.5: Archive freshness check (skip URLs with recent CC/Wayback)
        if self.freshness_checker and self.config.archive_skip_policy != "never_skip":
            print(f"[DRILL] Checking archive freshness for {len(urls_to_crawl)} URLs...")
            urls_to_crawl, freshness_data = await self.freshness_checker.filter_urls(
                urls_to_crawl[:100],  # Check first 100 to avoid rate limits
                max_concurrent=5,
            )
            self.stats.pages_skipped_archive = len(freshness_data) - len(urls_to_crawl)
            self.stats.archive_freshness_report = self.freshness_checker.get_report()

            if self.stats.pages_skipped_archive > 0:
                print(f"[DRILL] Skipped {self.stats.pages_skipped_archive} URLs with recent archives")
                print(f"[DRILL] {len(urls_to_crawl)} URLs remain to crawl")

        # Phase 1.8: CC Offline Sniper cache (optional)
        if self._persistent_queue_enabled():
            await self._prime_cc_offline(domain)

        # Phase 1.9: Persistent queue resume (optional)
        if self._persistent_queue_enabled():
            await self._load_state(domain)
            if await self.storage.queue_size() == 0:
                if seed_plan:
                    await self._enqueue_seed_plan(seed_plan, lane_budgets)
                else:
                    for url in urls_to_crawl[:self.config.max_pages]:
                        await self.storage.enqueue(
                            url,
                            0,
                            mission_id=self._root_mission_id,
                            mission_budget=self._mission_budgets[self._root_mission_id],
                        )

        # Phase 2: Crawl (HYBRID: Go/Colly fast path + Python slow path)
        if self._persistent_queue_enabled():
            await self._crawl_with_storage_queue(domain, on_page)
        elif self._should_use_hybrid():
            # HYBRID MODE: Go/Colly for static HTML, Playwright for JS
            print(f"[DRILL] Using HYBRID mode (Go/Colly + Playwright)")
            await self._crawl_hybrid(domain, urls_to_crawl, on_page)
        elif CRAWLEE_AVAILABLE:
            # Python-only mode with Crawlee
            await self._crawl_with_crawlee(domain, urls_to_crawl, on_page)
        else:
            # Python-only mode with aiohttp
            await self._crawl_with_aiohttp(domain, urls_to_crawl, on_page)

        # Phase 3: Screenshots (UNIFIED - dispatch all triggered screenshots to Rod)
        # This happens AFTER crawling, so content from ANY crawler triggers screenshots
        if self._screenshot_queue:
            await self._dispatch_screenshots()

        self.stats.end_time = datetime.utcnow()
        if self._persistent_queue_enabled():
            await self._maybe_save_state(domain, force=True)

        # Capture domain cache stats (Go-style optimization tracking)
        if self.config.use_optimized_link_extraction:
            self.stats.domain_cache_stats = get_cache_stats()

        print(f"[DRILL] Completed: {self.stats.pages_crawled} pages in {self.stats.duration_seconds:.1f}s")
        if self.stats.pages_go_crawled > 0 or self.stats.pages_rod_crawled > 0 or self.stats.pages_playwright > 0:
            print(f"[DRILL] Hybrid: {self.stats.pages_go_crawled} Colly (fast), {self.stats.pages_rod_crawled} Rod (medium), {self.stats.pages_playwright} Playwright (slow)")
            print(f"[DRILL] Go timings: {self.stats.go_crawler_time_ms}ms Colly, {self.stats.rod_crawler_time_ms}ms Rod")
        if self.stats.links_extracted > 0:
            print(f"[DRILL] Links: {self.stats.links_extracted} extracted, {self.stats.links_filtered} filtered, {self.stats.high_relevance_links} high-relevance")
        if self.stats.domain_cache_stats:
            print(f"[DRILL] Domain cache: {self.stats.domain_cache_stats.get('hit_rate', 'N/A')} hit rate")
        if self.stats.screenshots_triggered > 0:
            print(f"[DRILL] Screenshots: {self.stats.screenshots_taken} taken, {self.stats.screenshots_failed} failed (of {self.stats.screenshots_triggered} triggered)")
        return self.stats

    async def _crawl_hybrid(
        self,
        domain: str,
        seed_urls: List[str],
        on_page: Optional[Callable[[PageDocument], None]],
    ):
        """
        Hybrid crawling with 3 tiers:
          - Fast path: Go/Colly for static HTML (~500 concurrent)
          - Medium path: Go/Rod for JS rendering (~100 concurrent)
          - Slow path: Python/Playwright fallback (~50 concurrent)

        This provides 5-10x speedup for typical investigation targets where
        ~90% of pages are static HTML, and 2x speedup for JS pages via Rod.
        """
        import time

        # Filter URLs that should always go to Playwright
        colly_urls = []
        playwright_urls = []

        for url in seed_urls:
            parsed = urlparse(url)
            domain_check = parsed.netloc.lower()

            # Check force_playwright_domains
            force_playwright = any(
                d in domain_check for d in self.config.force_playwright_domains
            )

            if force_playwright:
                playwright_urls.append(url)
            else:
                colly_urls.append(url)

        # Phase 2a: Fast path - Go/Colly for potentially static pages
        js_required_urls = []
        if colly_urls and self.go_bridge:
            print(f"[DRILL] Go/Colly fast path: {len(colly_urls)} URLs")
            start_time = time.time()

            try:
                go_results, js_required = await self.go_bridge.crawl_static_html(
                    colly_urls,
                    max_concurrent=self.config.go_crawler_concurrent,
                    timeout=self.config.request_timeout,
                    country_tlds=self.config.country_tld_filter or None,
                    url_keywords=self.config.link_scoring_keywords or None,
                    detect_js_required=True,
                )

                self.stats.go_crawler_time_ms = int((time.time() - start_time) * 1000)

                # Process Go results
                for result in go_results:
                    if result.error:
                        self.stats.pages_failed += 1
                        continue

                    if result.needs_js:
                        js_required_urls.append(result.url)
                        continue

                    # Process successful static page
                    # Pass HTML to _process_page (it extracts content internally)
                    doc = await self._process_page(result.url, domain, result.html)
                    if doc:
                        self.stats.pages_crawled += 1
                        self.stats.pages_go_crawled += 1
                        self.stats.entities_extracted += doc.entity_count if hasattr(doc, 'entity_count') else 0
                        if on_page:
                            on_page(doc)

            except Exception as e:
                print(f"[DRILL] Go/Colly failed: {e}, falling back to Playwright")
                js_required_urls = colly_urls

        # Add JS-required URLs to queue for JS rendering
        js_urls_to_process = playwright_urls + js_required_urls

        # Phase 2b: Medium path - Go/Rod for JS rendering (if available)
        rod_failed_urls = []
        if js_urls_to_process and rod_available():
            print(f"[DRILL] Go/Rod medium path: {len(js_urls_to_process)} URLs")
            start_time = time.time()

            try:
                rod_results = await self.go_bridge.crawl_with_rod(
                    js_urls_to_process,
                    max_concurrent=100,  # Rod handles ~100 concurrent browser pages
                    timeout=self.config.request_timeout,
                )

                self.stats.rod_crawler_time_ms = int((time.time() - start_time) * 1000)

                # Process Rod results
                for result in rod_results:
                    if result.error:
                        # Rod failed for this URL - queue for Playwright fallback
                        rod_failed_urls.append(result.url)
                        continue

                    # Process successful JS-rendered page
                    doc = await self._process_page(result.url, domain, result.html)
                    if doc:
                        self.stats.pages_crawled += 1
                        self.stats.pages_rod_crawled += 1
                        self.stats.entities_extracted += doc.entity_count if hasattr(doc, 'entity_count') else 0
                        if on_page:
                            on_page(doc)

            except Exception as e:
                print(f"[DRILL] Go/Rod failed: {e}, falling back to Playwright")
                rod_failed_urls = js_urls_to_process
        else:
            # Rod not available, all JS URLs go to Playwright
            rod_failed_urls = js_urls_to_process

        # Phase 2c: Slow path - Playwright for pages that need it or as fallback
        if rod_failed_urls:
            print(f"[DRILL] Playwright slow path: {len(rod_failed_urls)} URLs")

            if CRAWLEE_AVAILABLE:
                await self._crawl_with_crawlee(domain, rod_failed_urls, on_page, track_playwright=True)
            else:
                await self._crawl_with_aiohttp(domain, rod_failed_urls, on_page, track_playwright=True)

    async def _crawl_with_crawlee(
        self,
        domain: str,
        seed_urls: List[str],
        on_page: Optional[Callable[[PageDocument], None]],
        track_playwright: bool = False,
    ):
        """Crawl using Crawlee (preferred method).

        Args:
            track_playwright: If True, increment pages_playwright stat (for hybrid mode)
        """

        async def page_handler(context):
            """Handle each crawled page."""
            request = context.request
            response = context.http_response
            page = context.page if hasattr(context, 'page') else None

            url = request.url
            if self._should_skip_url(url):
                return

            if url in self.visited_urls:
                return

            self.visited_urls.add(url)

            try:
                # Get HTML content
                if page:  # Playwright
                    html = await page.content()
                else:  # BeautifulSoup
                    html = response.text

                # Process page
                doc = await self._process_page(url, domain, html)

                if doc:
                    self.stats.pages_crawled += 1
                    self.stats.entities_extracted += doc.entity_count if hasattr(doc, 'entity_count') else 0

                    # Track Playwright usage in hybrid mode
                    if track_playwright:
                        self.stats.pages_playwright += 1

                    if on_page:
                        on_page(doc)

                    # Enqueue discovered internal links
                    if hasattr(context, 'enqueue_links'):
                        await context.enqueue_links()

            except Exception as e:
                self.stats.pages_failed += 1
                print(f"[DRILL] Failed to process {url}: {e}")

            # Apply rate limit
            if self.config.delay_between_requests > 0:
                await asyncio.sleep(self.config.delay_between_requests)

        # Create crawler
        crawler = BeautifulSoupCrawler(
            max_requests_per_crawl=self.config.max_pages,
            max_concurrency=self.config.max_concurrent,
            request_handler=page_handler,
        )

        # Run crawler
        await crawler.run(seed_urls[:self.config.max_pages])

    async def _crawl_with_aiohttp(
        self,
        domain: str,
        seed_urls: List[str],
        on_page: Optional[Callable[[PageDocument], None]],
        track_playwright: bool = False,
    ):
        """Fallback crawl using aiohttp (when Crawlee not available).

        Args:
            track_playwright: If True, increment pages_playwright stat (for hybrid mode)
        """
        semaphore = asyncio.Semaphore(self.config.max_concurrent)
        queue = asyncio.Queue()

        # Add seed URLs to queue
        for url in seed_urls[:self.config.max_pages]:
            await queue.put((url, 0))  # (url, depth)

        async with aiohttp.ClientSession() as session:
            while not queue.empty() and self.stats.pages_crawled < self.config.max_pages:
                url, depth = await queue.get()

                if url in self.visited_urls:
                    continue

                if depth > self.config.max_depth:
                    continue

                depth_budget = None
                if self.config.max_pages_per_depth:
                    if depth < len(self.config.max_pages_per_depth):
                        depth_budget = self.config.max_pages_per_depth[depth]
                    else:
                        depth_budget = self.config.max_pages_per_depth[-1]
                if depth_budget is not None and depth_budget >= 0:
                    if self._depth_counts.get(depth, 0) >= depth_budget:
                        continue

                if self._should_skip_url(url):
                    continue

                self.visited_urls.add(url)

                async with semaphore:
                    try:
                        async with session.get(
                            url,
                            timeout=aiohttp.ClientTimeout(total=self.config.request_timeout),
                            headers={'User-Agent': 'DRILL/1.0 (investigation crawler)'}
                        ) as response:
                            if response.status != 200:
                                self.stats.pages_failed += 1
                                continue

                            content_type = response.headers.get('Content-Type', '')
                            if not any(ct in content_type for ct in self.config.allowed_content_types):
                                continue

                            html = await response.text()

                            # Process page
                            doc = await self._process_page(url, domain, html)

                            if doc:
                                self.stats.pages_crawled += 1
                                self.stats.entities_extracted += len(doc.companies) + len(doc.persons) + len(doc.emails) + len(doc.phones)
                                self._depth_counts[depth] = self._depth_counts.get(depth, 0) + 1

                                # Track Playwright usage in hybrid mode
                                if track_playwright:
                                    self.stats.pages_playwright += 1

                                if on_page:
                                    on_page(doc)

                                # Add internal links to queue
                                for link in (doc.internal_links or []):
                                    if link not in self.visited_urls:
                                        await queue.put((link, depth + 1))

                    except Exception as e:
                        self.stats.pages_failed += 1

                    # Rate limit
                    if self.config.delay_between_requests > 0:
                        await asyncio.sleep(self.config.delay_between_requests)

    async def _crawl_with_storage_queue(
        self,
        domain: str,
        on_page: Optional[Callable[[PageDocument], None]],
    ):
        """
        Crawl using the persistent storage queue.
        """
        semaphore = asyncio.Semaphore(self.config.max_concurrent)
        tasks: Set[asyncio.Task] = set()

        async def process_url(item: QueueItem):
            async with semaphore:
                url = item.url
                depth = item.depth
                mission_id = item.mission_id or self._root_mission_id
                mission_budget = item.mission_budget
                if mission_budget is None:
                    mission_budget = self._mission_budgets.get(mission_id, self.config.max_pages)
                self._mission_budgets.setdefault(mission_id, mission_budget)

                if self._mission_counts.get(mission_id, 0) >= mission_budget:
                    return

                if self.stats.pages_crawled >= self.config.max_pages:
                    return

                if depth > self.config.max_depth:
                    return

                depth_budget = None
                if self.config.max_pages_per_depth:
                    if depth < len(self.config.max_pages_per_depth):
                        depth_budget = self.config.max_pages_per_depth[depth]
                    else:
                        depth_budget = self.config.max_pages_per_depth[-1]
                if depth_budget is not None and depth_budget >= 0:
                    if self._depth_counts.get(depth, 0) >= depth_budget:
                        return

                if await self.storage.is_visited(url):
                    return

                if self._should_skip_url(url):
                    return

                await self.storage.mark_visited(url, time.time())
                self.visited_urls.add(url)

                prefer_archive = self._should_prefer_archive(url)
                fetched = await self._fetch_html(url, prefer_archive=prefer_archive)
                if not fetched:
                    self.stats.pages_failed += 1
                    return

                html, status_code, source = fetched
                doc = await self._process_page(url, domain, html)
                if not doc:
                    return

                doc.status_code = status_code or doc.status_code
                if hasattr(doc, "__dict__"):
                    doc.__dict__["fetch_source"] = source
                    doc.__dict__["mission_id"] = mission_id
                    doc.__dict__["crawl_depth"] = depth

                entity_count = len(doc.companies) + len(doc.persons) + len(doc.emails) + len(doc.phones)
                self.stats.pages_crawled += 1
                self.stats.entities_extracted += entity_count
                self._depth_counts[depth] = self._depth_counts.get(depth, 0) + 1

                if on_page:
                    on_page(doc)

                parsed_domain = urlparse(url).netloc
                self._update_yield(parsed_domain, entity_count)
                await self._maybe_save_state(domain)

                tripwire_triggered = False
                if hasattr(doc, "__dict__"):
                    tripwire_triggered = bool(doc.__dict__.get("tripwire_triggered"))

                self._mission_counts[mission_id] = self._mission_counts.get(mission_id, 0) + 1

                await self._enqueue_links_from_doc(
                    doc,
                    depth + 1,
                    parsed_domain,
                    tripwire_triggered,
                    mission_id,
                    mission_budget,
                )
                await self._maybe_spawn_mission(
                    doc,
                    mission_id,
                    mission_budget,
                    parsed_domain,
                    tripwire_triggered,
                    entity_count,
                )

                if self.config.delay_between_requests > 0:
                    await asyncio.sleep(self.config.delay_between_requests)

        while self.stats.pages_crawled < self.config.max_pages:
            while len(tasks) < self.config.max_concurrent:
                prefer_priority = self._next_dequeue_preference()
                item = await self.storage.dequeue(prefer_priority=prefer_priority)
                if not item:
                    break
                if isinstance(item, tuple):
                    queue_item = QueueItem(url=item[0], depth=item[1])
                else:
                    queue_item = item
                tasks.add(asyncio.create_task(process_url(queue_item)))

            if not tasks:
                break

            done, tasks = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

            # Clean up completed tasks
            for task in done:
                if task.exception():
                    self.stats.pages_failed += 1

    async def _enqueue_links_from_doc(
        self,
        doc: PageDocument,
        next_depth: int,
        source_domain: str,
        tripwire_triggered: bool,
        mission_id: Optional[str] = None,
        mission_budget: Optional[int] = None,
    ) -> None:
        if next_depth > self.config.max_depth:
            return

        links = doc.internal_links or []
        if not links:
            return

        skip, yield_priority = self._yield_decision(source_domain)
        if skip and not tripwire_triggered:
            return

        priority = 0
        if tripwire_triggered:
            priority += self.config.tripwire_priority_boost
        elif yield_priority < 0:
            priority = yield_priority

        scored_map: Dict[str, int] = {}
        if hasattr(doc, "__dict__"):
            for item in doc.__dict__.get("scored_links", []) or []:
                url = item.get("url")
                if url:
                    scored_map[url] = int(item.get("relevance_score", 0))

        added = 0
        for link in links:
            if link in self.visited_urls:
                continue
            score = scored_map.get(link, 0)
            link_priority = priority
            if self._is_sprint_link(link, score):
                link_priority = max(link_priority, 1)
            await self.storage.enqueue(
                link,
                next_depth,
                priority=link_priority,
                mission_id=mission_id,
                mission_budget=mission_budget,
            )
            added += 1

    async def _enqueue_seed_plan(
        self,
        seed_plan: Dict[str, List[str]],
        lane_budgets: Optional[Dict[str, int]] = None,
    ) -> None:
        lane_priority = {
            "sprint": 1,
            "marathon": 0,
            "archive": -1,
        }
        added = 0
        seen: Set[str] = set()

        for lane in ("sprint", "marathon", "archive"):
            urls = seed_plan.get(lane, []) if seed_plan else []
            if not urls:
                continue

            lane_budget = None
            if lane_budgets:
                lane_budget = lane_budgets.get(lane)
            if lane_budget is None:
                lane_budget = self.config.max_pages

            mission_id = f"{self._root_mission_id}:{lane}"
            self._mission_budgets[mission_id] = int(lane_budget)

            for url in urls:
                if not url:
                    continue
                normalized = url.lower().strip()
                if normalized in seen:
                    continue
                seen.add(normalized)
                await self.storage.enqueue(
                    url,
                    0,
                    priority=lane_priority.get(lane, 0),
                    mission_id=mission_id,
                    mission_budget=int(lane_budget),
                )
                added += 1

        if added:
            self.stats.urls_discovered = max(self.stats.urls_discovered, added)

    async def _maybe_spawn_mission(
        self,
        doc: PageDocument,
        parent_mission_id: str,
        parent_budget: int,
        source_domain: str,
        tripwire_triggered: bool,
        entity_count: int,
    ) -> None:
        if not self.config.enable_fractal_hunger:
            return
        if self._spawn_count >= self.config.fractal_max_spawns:
            return
        if self.config.fractal_trigger_on_tripwire:
            if not tripwire_triggered and entity_count < self.config.fractal_trigger_min_entities:
                return
        else:
            if entity_count < self.config.fractal_trigger_min_entities:
                return

        scored_links = []
        if hasattr(doc, "__dict__"):
            scored_links = doc.__dict__.get("scored_links", []) or []

        spawn_keywords = [kw.lower() for kw in self.config.fractal_spawn_keywords]
        candidates: List[Tuple[str, str, Optional[str], int]] = []

        for link in scored_links:
            target_domain = (link.get("domain") or "").lower()
            if not target_domain or target_domain == source_domain:
                continue
            anchor_text = (link.get("anchor_text") or "").lower()
            score = int(link.get("relevance_score", 0))
            if score < self.config.fractal_min_relevance_score and not any(
                kw in anchor_text for kw in spawn_keywords
            ):
                continue
            candidates.append((target_domain, link.get("url") or "", link.get("anchor_text"), score))

        if not candidates and tripwire_triggered:
            for outlink in (doc.outlinks or [])[: self.config.fractal_max_spawns_per_page]:
                parsed = urlparse(outlink)
                target_domain = parsed.netloc.lower()
                if not target_domain or target_domain == source_domain:
                    continue
                candidates.append((target_domain, outlink, None, 0))

        if not candidates:
            return

        spawned = 0
        for target_domain, target_url, anchor_text, score in candidates:
            if self._spawn_count >= self.config.fractal_max_spawns:
                break
            if spawned >= self.config.fractal_max_spawns_per_page:
                break
            if target_domain in self._spawned_missions:
                continue

            child_budget = max(1, int(parent_budget * self.config.fractal_budget_ratio))
            child_mission_id = f"{parent_mission_id}-{uuid4().hex[:6]}"
            self._mission_budgets[child_mission_id] = child_budget
            self._spawned_missions.add(target_domain)
            self._spawn_count += 1
            spawned += 1

            seed_url = target_url or f"https://{target_domain}"
            if self.mission_launcher and hasattr(self.mission_launcher, "spawn_mission"):
                await self.mission_launcher.spawn_mission(
                    seed_domain=target_domain,
                    seed_url=seed_url,
                    parent_mission_id=parent_mission_id,
                    budget_pages=child_budget,
                    reason=anchor_text or "fractal_spawn",
                )
            else:
                await self.storage.enqueue(
                    seed_url,
                    0,
                    priority=1,
                    mission_id=child_mission_id,
                    mission_budget=child_budget,
                )

    async def crawl_url(self, url: str) -> CrawlUrlResult:
        """
        Fetch a single URL (used by JESTER_D).
        """
        parsed = urlparse(url if "://" in url else f"https://{url}")
        domain = parsed.netloc or parsed.path.split("/")[0]
        auth_cookies = None
        if self.config.auth_use_sessions:
            auth_cookies = self._get_auth_cookies(domain)

        if auth_cookies:
            playwright_result = await self._fetch_html_playwright(url, auth_cookies)
            if playwright_result:
                html, status_code = playwright_result
                if not (self.config.auth_login_detection and self._looks_like_login_page(html)):
                    return CrawlUrlResult(url=url, html=html, status_code=status_code)
                print(f"[DRILL] Auth session still returned login page for {domain} (Playwright).")

            cookie_result = await self._fetch_html_with_cookies(url, auth_cookies)
            if cookie_result:
                html, status_code = cookie_result
                if not (self.config.auth_login_detection and self._looks_like_login_page(html)):
                    return CrawlUrlResult(url=url, html=html, status_code=status_code)
                print(f"[DRILL] Auth session still returned login page for {domain} (cookies).")

        prefer_archive = self._should_prefer_archive(url)
        fetched = await self._fetch_html(url, prefer_archive=prefer_archive)
        if not fetched:
            return CrawlUrlResult(url=url, html="", status_code=0)
        html, status_code, _source = fetched
        return CrawlUrlResult(url=url, html=html, status_code=status_code)

    async def _process_page(
        self,
        url: str,
        domain: str,
        html: str,
    ) -> Optional[PageDocument]:
        """
        Process a single crawled page.

        Pipeline:
        1. Extract entities
        2. Extract links using Go-style processing (if enabled)
        3. Generate embeddings
        4. Index to Elasticsearch
        """
        # Extract title
        title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else url

        # Extract entities
        entities = ExtractedEntities(url=url)
        if self.config.extract_entities:
            entities = self.extractor.extract(html, url)

        # Strip HTML for content
        content = self.extractor._strip_html(html)

        # Extract links using Go-style processing (if enabled)
        outlinks = entities.outlinks
        internal_links = entities.internal_links
        scored_links = []

        if self.config.use_optimized_link_extraction:
            go_outlinks, go_internal, scored_links = self._extract_scored_links(
                html, url, domain
            )
            # Use Go-style links if we got results
            if go_outlinks or go_internal:
                outlinks = go_outlinks
                internal_links = go_internal

        # Create document
        doc = PageDocument(
            url=url,
            domain=domain,
            title=title,
            content=content[:50000],  # Limit content size
            html_raw=html if self.config.save_html else None,
            companies=entities.companies,
            persons=entities.persons,
            emails=entities.emails,
            phones=entities.phones,
            outlinks=outlinks,
            internal_links=internal_links,
            keywords_found=entities.keywords_found,
            project_id=self.config.project_id,
        )

        # Tripwire routing (UniversalExtractor)
        if self.tripwire_extractor and self.config.enable_tripwire_routing:
            try:
                tripwire_result = self._evaluate_tripwire(content, entities)
                if hasattr(doc, '__dict__'):
                    doc.__dict__['tripwire'] = tripwire_result
                    doc.__dict__['tripwire_triggered'] = tripwire_result.get("triggered", False)
            except Exception as e:
                print(f"[DRILL] Tripwire evaluation failed for {url}: {e}")

        # Store scored links for later analysis
        if scored_links and hasattr(doc, '__dict__'):
            doc.__dict__['scored_links'] = scored_links

        # Generate embedding
        if self.embedder and self.config.generate_embeddings:
            # Embed title + first part of content
            embed_text = f"{title}. {content[:1000]}"
            doc.content_embedding = self.embedder.embed(embed_text)

        # Index to Elasticsearch
        if self.indexer and self.config.index_to_elasticsearch:
            try:
                self.indexer.index_page(doc)

                # Also index entities separately
                for company in doc.companies[:50]:  # Limit per page
                    self.indexer.index_entity(
                        entity_type="company",
                        entity_value=company,
                        source_url=url,
                        source_domain=domain,
                        project_id=self.config.project_id,
                    )

                for person in doc.persons[:50]:
                    self.indexer.index_entity(
                        entity_type="person",
                        entity_value=person,
                        source_url=url,
                        source_domain=domain,
                        project_id=self.config.project_id,
                    )

                for email in doc.emails[:20]:
                    self.indexer.index_entity(
                        entity_type="email",
                        entity_value=email,
                        source_url=url,
                        source_domain=domain,
                        project_id=self.config.project_id,
                    )

                for phone in doc.phones[:20]:
                    self.indexer.index_entity(
                        entity_type="phone",
                        entity_value=phone,
                        source_url=url,
                        source_domain=domain,
                        project_id=self.config.project_id,
                    )

                # Index outlinks for graph
                parsed_url = urlparse(url)
                for outlink in doc.outlinks[:100]:
                    parsed_outlink = urlparse(outlink)
                    self.indexer.index_link(
                        source_url=url,
                        source_domain=domain,
                        target_url=outlink,
                        target_domain=parsed_outlink.netloc,
                        link_type="outlink",
                        project_id=self.config.project_id,
                    )

            except Exception as e:
                print(f"[DRILL] Indexing error for {url}: {e}")

        # UNIFIED SCREENSHOT TRIGGER
        # Check if this page matches screenshot rules, regardless of which crawler fetched it
        rule_name = self._check_screenshot_trigger(url, title, content)
        if rule_name:
            self._queue_screenshot(url, title, content, rule_name)

        return doc

    def _should_skip_url(self, url: str) -> bool:
        """
        Check if URL should be skipped using Go-style validation.

        Uses optimized link processor validation for speed.
        """
        # Use Go-style URL validation if enabled
        if self.config.use_optimized_link_extraction:
            record = build_url_record(url)
            if not record:
                return True
            if not verify_url_quality(record):
                return True

            # Check for hash-based deduplication (Go pattern)
            url_hash = page_hash(record.host, record.path, record.query)
            if url_hash in self.page_hashes:
                return True
            self.page_hashes.add(url_hash)

            # Skip by extension (using link_processor's is_ignored_extension)
            from .link_processor import is_ignored_extension
            if is_ignored_extension(record.path):
                return True

        else:
            # Fallback to original validation
            parsed = urlparse(url)

            # Skip non-http(s)
            if parsed.scheme not in ('http', 'https'):
                return True

            # Skip by extension
            path_lower = parsed.path.lower()
            for ext in self.config.skip_extensions:
                if path_lower.endswith(ext):
                    return True

        # Skip common non-content paths (applies to both modes)
        skip_patterns = [
            '/wp-admin/', '/wp-includes/', '/wp-content/plugins/',
            '/admin/', '/login', '/logout', '/register',
            '/cart', '/checkout', '/account',
            '/cdn-cgi/', '/api/', '/_next/',
        ]
        path_lower = urlparse(url).path.lower()
        for pattern in skip_patterns:
            if pattern in path_lower:
                return True

        return False

    def _extract_scored_links(
        self,
        html: str,
        source_url: str,
        source_domain: str,
    ) -> Tuple[List[str], List[str], List[Dict[str, Any]]]:
        """
        Extract links using Go-style processing with relevance scoring.

        Returns:
            Tuple of (outlinks, internal_links, scored_links)
        """
        outlinks = []
        internal_links = []
        scored_links = []

        if not self.config.use_optimized_link_extraction:
            # Fallback to basic extraction
            return outlinks, internal_links, scored_links

        # Use Go-style link extraction
        links = extract_links_from_html(
            html,
            source_url,
            country_tlds=self.config.country_tld_filter,
            url_keywords=self.config.link_scoring_keywords,
            include_internal=True,
        )

        for link in links:
            self.stats.links_extracted += 1

            # Calculate relevance score
            score = calculate_relevance_score(link.target, self._scoring_config)

            # Track high-relevance links
            if score >= 50:
                self.stats.high_relevance_links += 1

            # Filter by minimum score
            if score < self.config.min_link_relevance_score:
                self.stats.links_filtered += 1
                continue

            target_url = link.target.to_full_url()
            target_domain = link.target.domain

            # Separate internal vs external
            if target_domain == source_domain:
                internal_links.append(target_url)
            else:
                outlinks.append(target_url)

            # Store scored link info
            scored_links.append({
                "url": target_url,
                "domain": target_domain,
                "anchor_text": link.anchor_text,
                "nofollow": link.nofollow,
                "relevance_score": score,
            })

        return outlinks, internal_links, scored_links

    def _is_sprint_link(self, url: str, score: int) -> bool:
        if score >= self.config.sprint_priority_score_threshold:
            return True
        for pattern in self._sprint_patterns:
            if pattern.search(url):
                return True
        return False

    def _next_dequeue_preference(self) -> int:
        if self._sprint_bias_high <= 0:
            return 0
        if self._sprint_bias_high >= self._sprint_bias_mod:
            return 1
        prefer_high = self._sprint_bias_index < self._sprint_bias_high
        self._sprint_bias_index = (self._sprint_bias_index + 1) % self._sprint_bias_mod
        return 1 if prefer_high else 0

    async def discover_and_crawl(
        self,
        domain: str,
        on_page: Optional[Callable[[PageDocument], None]] = None,
    ) -> CrawlStats:
        """
        Full discovery + crawl pipeline.

        Convenience method that runs discovery first, then crawls.
        """
        return await self.crawl(domain, on_page=on_page)

    async def crawl_with_external_seeds(
        self,
        domain: str,
        external_seeds: List[str],
        merge_with_discovery: bool = True,
        on_page: Optional[Callable[[PageDocument], None]] = None,
    ) -> CrawlStats:
        """
        Crawl using external discovery results as seeds.

        This enables the Discovery → Crawler seeding pipeline:
        1. Use unified_discovery_engine.py to find subdomains/URLs
        2. Feed those results here as external seeds
        3. Optionally merge with internal discovery (sitemap, etc.)

        Args:
            domain: Target domain
            external_seeds: URLs from external discovery (e.g., unified discovery engine)
            merge_with_discovery: If True, also run internal discovery and merge seeds
            on_page: Optional callback for each crawled page

        Returns:
            CrawlStats with crawl results
        """
        all_seeds = []
        seen = set()

        # Add external seeds first (they have priority)
        for seed in external_seeds:
            normalized = seed.lower().strip()
            if normalized not in seen:
                all_seeds.append(seed)
                seen.add(normalized)

        print(f"[DRILL] External seeds: {len(external_seeds)}")

        # Optionally merge with internal discovery
        if merge_with_discovery and self.config.use_sitemap_first:
            print(f"[DRILL] Running internal discovery for {domain}...")
            discovery_result = await self.discovery.discover(
                domain,
                include_subdomains=self.config.discover_subdomains,
                include_archives=self.config.discover_archives,
            )
            internal_seeds = self.discovery.get_crawl_seeds(discovery_result)

            for seed in internal_seeds:
                normalized = seed.lower().strip()
                if normalized not in seen:
                    all_seeds.append(seed)
                    seen.add(normalized)

            print(f"[DRILL] Internal seeds: {len(internal_seeds)} → Total: {len(all_seeds)}")

        return await self.crawl(domain, seed_urls=all_seeds, on_page=on_page)

    @staticmethod
    def subdomains_to_seeds(subdomains: List[str]) -> List[str]:
        """
        Convert subdomain list to seed URLs.

        Args:
            subdomains: List of subdomains (e.g., ["api.example.com", "www.example.com"])

        Returns:
            List of seed URLs (https root URLs for each subdomain)
        """
        seeds = []
        for subdomain in subdomains:
            subdomain = subdomain.lower().strip()
            if not subdomain.startswith(('http://', 'https://')):
                # Default to HTTPS root
                seeds.append(f"https://{subdomain}/")
            else:
                seeds.append(subdomain)
        return seeds

    @staticmethod
    def discovery_results_to_seeds(
        domains: List[str] = None,
        urls: List[str] = None,
        backlinks: List[str] = None,
    ) -> List[str]:
        """
        Convert unified discovery results to crawler seeds.

        Accepts various discovery outputs and merges them into a prioritized seed list.

        Args:
            domains: Discovered domains (converted to https root URLs)
            urls: Specific URLs to crawl
            backlinks: Backlink domains (converted to https root URLs)

        Returns:
            Deduplicated list of seed URLs, prioritized by:
            1. Specific URLs
            2. Discovered domains
            3. Backlink domains
        """
        seeds = []
        seen = set()

        # Add specific URLs first
        if urls:
            for url in urls:
                if url.lower() not in seen:
                    seeds.append(url)
                    seen.add(url.lower())

        # Add domains as root URLs
        if domains:
            for domain in domains:
                domain = domain.lower().strip()
                root_url = f"https://{domain}/"
                if root_url not in seen:
                    seeds.append(root_url)
                    seen.add(root_url)

        # Add backlinks as root URLs (lower priority)
        if backlinks:
            for domain in backlinks:
                domain = domain.lower().strip()
                root_url = f"https://{domain}/"
                if root_url not in seen:
                    seeds.append(root_url)
                    seen.add(root_url)

        return seeds


# ============================================================================
# CLI INTERFACE
# ============================================================================

async def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="DRILL - Deep Recursive Investigation Link Locator")
    parser.add_argument("domain", help="Domain to crawl (e.g., example.com)")
    parser.add_argument("--max-pages", type=int, default=100, help="Maximum pages to crawl")
    parser.add_argument("--max-concurrent", type=int, default=5, help="Concurrent requests")
    parser.add_argument("--no-discovery", action="store_true", help="Skip URL discovery phase")
    parser.add_argument("--no-index", action="store_true", help="Don't index to Elasticsearch")
    parser.add_argument("--no-embed", action="store_true", help="Don't generate embeddings")
    parser.add_argument("--output", type=str, help="Output directory for results")
    parser.add_argument("--project-id", type=str, help="Project ID for organizing results")

    args = parser.parse_args()

    config = DrillConfig(
        max_pages=args.max_pages,
        max_concurrent=args.max_concurrent,
        use_sitemap_first=not args.no_discovery,
        index_to_elasticsearch=not args.no_index,
        generate_embeddings=not args.no_embed,
        output_dir=Path(args.output) if args.output else None,
        project_id=args.project_id,
    )

    drill = Drill(config)

    print(f"\n{'='*60}")
    print(f"DRILL - Crawling {args.domain}")
    print(f"{'='*60}\n")

    stats = await drill.crawl(args.domain)

    print(f"\n{'='*60}")
    print("CRAWL COMPLETE")
    print(f"{'='*60}")
    print(f"Pages crawled: {stats.pages_crawled}")
    print(f"Pages failed: {stats.pages_failed}")
    print(f"Entities extracted: {stats.entities_extracted}")
    print(f"URLs discovered: {stats.urls_discovered}")
    print(f"Duration: {stats.duration_seconds:.1f}s")
    print(f"Speed: {stats.pages_per_second:.1f} pages/sec")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
