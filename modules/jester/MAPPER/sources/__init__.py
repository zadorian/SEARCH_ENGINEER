"""
JESTER MAPPER - URL Discovery Sources
======================================

Each source module provides async generators that yield DiscoveredURL objects.

Sources:
    subdomains.py      - crt.sh, WhoisXML, Sublist3r, DNSDumpster
    firecrawl.py       - Firecrawl MAP + CRAWL
    search_engines.py  - Google, Bing, Brave, DDG, Yandex, Exa
    backdrill_bridge.py - Wayback, CommonCrawl, Memento via BACKDRILL (FREE)
    sitemaps.py        - sitemap.xml, robots.txt
    backlinks.py       - Majestic, Ahrefs, CC WebGraph
    elasticsearch_source.py - Query our ES indexes
"""

from .subdomains import SubdomainDiscovery
from .firecrawl import FirecrawlDiscovery
from .search_engines import SearchEngineDiscovery
from .backdrill_bridge import ArchiveDiscovery
from .sitemaps import SitemapDiscovery
from .backlinks import BacklinkDiscovery
from .elasticsearch_source import ElasticsearchDiscovery

__all__ = [
    "SubdomainDiscovery",
    "FirecrawlDiscovery",
    "SearchEngineDiscovery",
    "ArchiveDiscovery",
    "SitemapDiscovery",
    "BacklinkDiscovery",
    "ElasticsearchDiscovery",
]
