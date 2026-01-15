"""
DRILL - Deep Recursive Investigation Link Locator

A high-performance web crawler integrated into LinkLater.
Combines Crawlee framework with Firecrawl optimizations and LinkLater's
11 URL discovery sources for maximum recall investigation crawling.

Enhanced with:
- GlobalLinks intelligence for smarter crawling
- Go-inspired link processing for speed (ported from GlobalLinks Go architecture)
- Archive freshness checking (CC + Wayback) to avoid re-crawling
- Relevance scoring for link prioritization
- HYBRID CRAWLING: Go/Colly fast path (500+ concurrent) + Python/Playwright slow path

Usage:
    from modules.linklater.drill import Drill, DrillConfig

    # Basic crawl
    drill = Drill()
    await drill.crawl("example.com", max_pages=1000)

    # With discovery sources
    await drill.discover_and_crawl("example.com", include_subdomains=True)

    # HYBRID CRAWLING (NEW in v1.5.0)
    # Go/Colly crawls static HTML (90% of pages) at 500+ concurrent
    # Playwright handles JS-heavy pages (10%) at 50 concurrent
    config = DrillConfig(
        use_hybrid_crawler=True,      # Enable Go fast path
        go_crawler_concurrent=500,    # Go concurrency
        force_playwright_domains=["facebook.com", "linkedin.com"],
    )
    drill = Drill(config)
    stats = await drill.crawl("target.com")
    print(f"Go crawled: {stats.pages_go_crawled}, Playwright: {stats.pages_playwright}")

    # JS detection for manual use
    from modules.linklater.drill import detect_js_requirement, needs_playwright
    if needs_playwright(html, url):
        # Use Playwright
    else:
        # Use static HTTP

    # With GlobalLinks pre-flight intelligence
    from modules.linklater.drill import crawl_with_intel
    intel, stats = await crawl_with_intel("target.com")
    print(f"Categories: {intel.categories}")
    print(f"Anchor keywords: {intel.anchor_keywords}")

    # Link pipeline (extract → enrich → index → query)
    from modules.linklater.drill import DrillLinkPipeline
    pipeline = DrillLinkPipeline()
    await pipeline.extract_and_index("target.com", "CC-MAIN-2024-10")
    results = await pipeline.query_links(target_tlds=[".ru", ".ky"])

    # Go-style link processing with relevance scoring
    from modules.linklater.drill import extract_links_from_html, calculate_relevance_score
    links = extract_links_from_html(html, source_url, country_tlds=[".ru", ".cy"])
    for link in links:
        score = calculate_relevance_score(link.target)
        print(f"{link.target.url} - score: {score}")

    # Archive freshness checking
    from modules.linklater.drill import ArchiveFreshnessChecker, SkipPolicy
    checker = ArchiveFreshnessChecker()
    freshness = await checker.check_freshness("https://example.com")
    print(f"CC: {freshness.cc_latest_date}, Wayback: {freshness.wayback_latest_date}")

    # UNIFIED SCREENSHOT TRIGGERING (NEW in v1.5.3)
    # Screenshots work regardless of which crawler (Colly/Rod/Playwright) fetched content.
    # Content is checked against rules in Python, then matching URLs dispatch to Rod.
    from modules.linklater.drill import ScreenshotRule
    from pathlib import Path
    config = DrillConfig(
        screenshot_dir=Path("/tmp/screenshots"),
        screenshot_rules=[
            ScreenshotRule(name="sensitive_keywords", rule_type="content_contains",
                           keywords=["confidential", "secret", "offshore"]),
            ScreenshotRule(name="tax_havens", rule_type="domain",
                           domains=[".ky", ".bvi", ".vg", ".pa"]),
            ScreenshotRule(name="long_content", rule_type="content_min_length",
                           min_length=5000),
        ],
        screenshot_full_page=True,  # Full page screenshots
    )
    drill = Drill(config)
    stats = await drill.crawl("target.com")
    print(f"Screenshots: {stats.screenshots_taken} taken (of {stats.screenshots_triggered} triggered)")
    print(f"Rules matched: {stats.screenshot_rules_matched}")
"""

from .crawler import Drill, DrillConfig, CrawlStats, CrawlUrlResult

# JESTER aliases (Drill = JESTER_D in the unified JESTER scraping system)
# Use `from jester import Jester` for the unified interface
# These aliases exist for backward compatibility
JesterD = Drill
JesterDConfig = DrillConfig
from .extractors import (
    EntityExtractor,
    ExtractedEntities,
    extract_entities,
    extract_and_store_entities,
    batch_extract_and_store,
)
from .embedder import DrillEmbedder
from .indexer import DrillIndexer
from .discovery import DrillDiscovery

# GlobalLinks intelligence (makes DRILL smarter)
from .globallinks_intel import (
    GlobalLinksIntelligence,
    GlobalLinksEnhancedCrawler,
    DomainIntelligence,
    get_domain_intelligence,
    crawl_with_intel,
)

# Link pipeline (extract → enrich → index)
from .linkpipeline import (
    DrillLinkPipeline,
    EnrichedLink,
)

# Archive freshness (skip if CC/Wayback has recent data)
from .archive_freshness import (
    ArchiveFreshnessChecker,
    ArchiveFreshness,
    FreshnessConfig,
    SkipPolicy,
    SmartCrawlDecider,
    check_url_freshness,
    filter_for_crawling,
)

# Go binaries bridge (call Go for heavy lifting)
from .go_bridge import (
    GoBridge,
    OutlinkerResult,
    OutlinkRecord,
    CrawlResult as GoCrawlResult,
    CrawlStats as GoCrawlStats,
    get_go_bridge,
    go_extract_links,
    go_search_links,
    go_query_backlinks,
    go_crawl_static,
    go_test_crawl,
    go_available,
    colly_available,
    # Rod (JS rendering - medium path)
    rod_available,
    go_crawl_js,
    go_test_crawl_js,
    # Screenshots (rule-based and manual)
    ScreenshotRule,
    ScreenshotResult,
    go_screenshot,
    go_crawl_with_screenshots,
    create_screenshot_rules,
)

# JS detection for hybrid crawling
from .js_detector import (
    JSDetector,
    JSDetectionResult,
    DomainJSRules,
    detect_js_requirement,
    needs_playwright,
)

# Go-inspired link processing (port of GlobalLinks Go patterns)
from .link_processor import (
    # Core types
    URLRecord,
    LinkRecord,
    ScoringConfig,
    DomainCache,
    StreamingLinkParser,
    # Functions
    build_url_record,
    verify_url_quality,
    calculate_relevance_score,
    extract_links_from_html,
    get_domain_from_url,
    fast_hash,
    link_hash,
    page_hash,
    stream_gzip_lines,
    stream_wat_pages,
    get_cache_stats,
    # Validation helpers
    is_valid_host,
    is_valid_domain,
    is_ignored_domain,
    is_ignored_tld,
    is_ignored_extension,
    clean_query,
)

__all__ = [
    # Core crawler (JESTER_D in the unified JESTER system)
    "Drill",
    "DrillConfig",
    "JesterD",        # Alias for Drill
    "JesterDConfig",  # Alias for DrillConfig
    "CrawlStats",
    "CrawlUrlResult",
    "EntityExtractor",
    "ExtractedEntities",
    "extract_entities",
    "extract_and_store_entities",
    "batch_extract_and_store",
    "DrillEmbedder",
    "DrillIndexer",
    "DrillDiscovery",
    # GlobalLinks intelligence
    "GlobalLinksIntelligence",
    "GlobalLinksEnhancedCrawler",
    "DomainIntelligence",
    "get_domain_intelligence",
    "crawl_with_intel",
    # Link pipeline
    "DrillLinkPipeline",
    "EnrichedLink",
    # Archive freshness
    "ArchiveFreshnessChecker",
    "ArchiveFreshness",
    "FreshnessConfig",
    "SkipPolicy",
    "SmartCrawlDecider",
    "check_url_freshness",
    "filter_for_crawling",
    # Go-inspired link processing
    "URLRecord",
    "LinkRecord",
    "ScoringConfig",
    "DomainCache",
    "StreamingLinkParser",
    "build_url_record",
    "verify_url_quality",
    "calculate_relevance_score",
    "extract_links_from_html",
    "get_domain_from_url",
    "fast_hash",
    "link_hash",
    "page_hash",
    "stream_gzip_lines",
    "stream_wat_pages",
    "get_cache_stats",
    "is_valid_host",
    "is_valid_domain",
    "is_ignored_domain",
    "is_ignored_tld",
    "is_ignored_extension",
    "clean_query",
    # Go binaries bridge
    "GoBridge",
    "OutlinkerResult",
    "OutlinkRecord",
    "GoCrawlResult",
    "GoCrawlStats",
    "get_go_bridge",
    "go_extract_links",
    "go_search_links",
    "go_query_backlinks",
    "go_crawl_static",
    "go_test_crawl",
    "go_available",
    "colly_available",
    # Rod (JS rendering)
    "rod_available",
    "go_crawl_js",
    "go_test_crawl_js",
    # Screenshots
    "ScreenshotRule",
    "ScreenshotResult",
    "go_screenshot",
    "go_crawl_with_screenshots",
    "create_screenshot_rules",
    # JS detection
    "JSDetector",
    "JSDetectionResult",
    "DomainJSRules",
    "detect_js_requirement",
    "needs_playwright",
]

__version__ = "1.5.3"  # Screenshots: UNIFIED triggers work regardless of crawler (Colly/Rod/Playwright)
