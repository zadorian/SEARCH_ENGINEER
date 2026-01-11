#!/usr/bin/env python3
"""
TORPEDO ← JESTER Bridge

Re-exports JESTER's scraping system for TORPEDO processors/executors.

PROCESSING tests which method works for each source and saves to JSON.
EXECUTION uses the pre-classified method to scrape without re-testing.

Usage in TORPEDO:
    from TORPEDO.jester_bridge import TorpedoScraper, ScrapeMethod, ScrapeResult

    scraper = TorpedoScraper()
    result = await scraper.scrape("https://example.com")

    # Force specific method (from classification):
    result = await scraper.scrape(url, force_method=ScrapeMethod.JESTER_C)

    # Batch scraping:
    results = await scraper.scrape_batch(urls, max_concurrent=20)

SOURCE: Bridge to modules.JESTER (not a reimplementation)
"""

# Import from real JESTER (support both `modules.JESTER` and top-level `JESTER`)
try:
    from modules.JESTER import (
        Jester,
        JesterConfig,
        JesterMethod,
        JesterResult,
        scrape,
        scrape_batch,
        get_jester,
    )
except ImportError:
    from JESTER import (  # type: ignore[no-redef]
        Jester,
        JesterConfig,
        JesterMethod,
        JesterResult,
        scrape,
        scrape_batch,
        get_jester,
    )

# Re-export with TORPEDO-friendly names for backward compatibility
TorpedoScraper = Jester
ScrapeMethod = JesterMethod
ScrapeResult = JesterResult
ScraperConfig = JesterConfig

__all__ = [
    # TORPEDO names (backward compat)
    "TorpedoScraper",
    "ScrapeMethod",
    "ScrapeResult",
    "ScraperConfig",
    # JESTER names (preferred)
    "Jester",
    "JesterMethod",
    "JesterResult",
    "JesterConfig",
    # Convenience functions
    "scrape",
    "scrape_batch",
    "get_jester",
]
