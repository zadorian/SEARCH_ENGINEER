"""
JESTER - The Unified Scraping System

JESTER is the ONLY scraping system. All 4 tiers are your own:
- JESTER_A: httpx direct (Python, fastest)
- JESTER_B: Colly Go crawler (static HTML, 500+ concurrent)
- JESTER_C: Rod Go crawler (JS rendering, ~100 concurrent)
- JESTER_D: Custom headless browser (Playwright hybrid)

External fallbacks (paid, NOT part of JESTER):
- Firecrawl: External API
- BrightData: Proxy API (last resort)

Usage:
    # Unified orchestrator
    from modules.jester import Jester
    jester = Jester()
    result = await jester.scrape("https://example.com")

    # Individual tiers
    from modules.jester import JesterA, JesterB, JesterC, JesterD
    from modules.jester import scrape_a, scrape_b, scrape_c, scrape_d
"""

# Import unified orchestrator
from modules.jester.scraper import (
    # Main class
    Jester,
    JesterMethod,
    JesterResult,
    JesterConfig,
    # Convenience functions
    scrape,
    scrape_batch,
    scrape_batch_optimized,
    get_jester,
    # Crawl mode
    crawl_domain,
    crawl_domain_full,
    crawl_batch,
    CrawlPage,
    CrawlConfig,
    DomainCrawlResult,
)

# Import individual tiers
from modules.jester.jester_a import (
    JesterA,
    JesterAResult,
    scrape_a,
    scrape_a_batch,
)

from modules.jester.jester_b import (
    JesterB,
    JesterBResult,
    scrape_b,
    scrape_b_batch,
    colly_available,
)

from modules.jester.jester_c import (
    JesterC,
    JesterCResult,
    scrape_c,
    scrape_c_batch,
    rod_available,
    ScreenshotRule,
    ScreenshotResult,
)

from modules.jester.jester_d import (
    JesterD,
    JesterDResult,
    scrape_d,
    scrape_d_batch,
    jester_d_available,
)

__all__ = [
    # Unified orchestrator
    "Jester",
    "JesterMethod",
    "JesterResult",
    "JesterConfig",
    "scrape",
    "scrape_batch",
    "scrape_batch_optimized",
    "get_jester",
    # Crawl mode
    "crawl_domain",
    "crawl_domain_full",
    "crawl_batch",
    "CrawlPage",
    "CrawlConfig",
    "DomainCrawlResult",
    # Tier A - httpx
    "JesterA",
    "JesterAResult",
    "scrape_a",
    "scrape_a_batch",
    # Tier B - Colly Go
    "JesterB",
    "JesterBResult",
    "scrape_b",
    "scrape_b_batch",
    "colly_available",
    # Tier C - Rod Go
    "JesterC",
    "JesterCResult",
    "scrape_c",
    "scrape_c_batch",
    "rod_available",
    "ScreenshotRule",
    "ScreenshotResult",
    # Tier D - Custom headless
    "JesterD",
    "JesterDResult",
    "scrape_d",
    "scrape_d_batch",
    "jester_d_available",
]
