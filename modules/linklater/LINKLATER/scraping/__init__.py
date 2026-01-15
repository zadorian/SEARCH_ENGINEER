"""
LINKLATER Scraping Module

Provides both historical (Wayback/Common Crawl) and current (live) scraping capabilities.

Usage:
    from modules.linklater.scraping import Drill, DrillConfig  # Web crawler
    from modules.linklater.scraping import TorCrawler          # Tor crawler
    from modules.linklater.scraping.historical import ArchiveScraper
"""

# Historical scraping (Wayback + Common Crawl)
try:
    from .historical import ArchiveScraper, CCIndexClient, WarcParser, BinaryExtractor
except ImportError:
    ArchiveScraper = CCIndexClient = WarcParser = BinaryExtractor = None

# Web scraping (DRILL crawler)
try:
    from .web import Drill, DrillConfig, CrawlStats, JSDetector
    Crawler = Drill  # Alias for backwards compatibility
except ImportError:
    Drill = DrillConfig = CrawlStats = JSDetector = Crawler = None

# Tor scraping (dark web)
try:
    from .tor import TorCrawler, AhmiaImporter, CrawlerConfig as TorConfig
except ImportError:
    TorCrawler = AhmiaImporter = TorConfig = None

__all__ = [
    # Historical
    "ArchiveScraper",
    "CCIndexClient",
    "WarcParser",
    "BinaryExtractor",
    # Web (DRILL)
    "Drill",
    "DrillConfig",
    "CrawlStats",
    "Crawler",  # Alias
    "JSDetector",
    # Tor
    "TorCrawler",
    "TorConfig",
    "AhmiaImporter",
]
