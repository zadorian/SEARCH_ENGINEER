"""
LINKLATER - Minimal init for CLI usage on sastre.
"""
# Minimal imports for CLI usage
from .scraping.cc_first_scraper import CCFirstScraper, ScrapeResult
from .enrichment.entity_patterns import EntityExtractor, ExtractedEntity

__all__ = ["CCFirstScraper", "ScrapeResult", "EntityExtractor", "ExtractedEntity"]
