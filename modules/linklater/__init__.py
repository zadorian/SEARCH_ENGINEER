"""
LinkLater - Unified Archive Intelligence & Link Graph System

MAIN ENTRY POINT: Use the unified API for all functionality.

Quick Start:
    from modules.linklater.api import linklater

    # Archive scraping (CC → Wayback → Firecrawl)
    result = await linklater.scrape_url("https://example.com/doc.pdf")

    # Entity extraction
    entities = linklater.extract_entities(text)

    # Backlinks (CC Graph + GlobalLinks)
    backlinks = await linklater.get_backlinks("example.com")

    # Keyword variations
    async for match in linklater.search_keyword_variations(["keyword"]):
        print(match)

ALL 150+ METHODS AVAILABLE VIA: linklater.method_name()
"""

# Unified API (The new standard)
from .api import LinkLater, linklater, get_linklater

__version__ = "2.0.0"
__all__ = [
    'LinkLater',
    'linklater',
    'get_linklater',
]