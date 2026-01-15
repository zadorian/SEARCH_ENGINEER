"""
JESTER MAPPER - Unified Domain URL Discovery
=============================================

The single source of truth for discovering ALL URLs belonging to a domain.

Usage:
    from jester.MAPPER import Mapper

    mapper = Mapper()

    # Full discovery (all 20+ sources)
    async for url in mapper.map_domain("example.com"):
        print(url.url, url.source)

    # Fast discovery (high-priority sources only)
    async for url in mapper.map_domain("example.com", fast=True):
        print(url.url)

    # Free sources only (no paid APIs)
    async for url in mapper.map_domain("example.com", free_only=True):
        print(url.url)

    # Specific sources
    async for url in mapper.map_domain("example.com", sources=["firecrawl", "wayback"]):
        print(url.url)

Sources:
    SUBDOMAINS:
        - crt.sh (Certificate Transparency)
        - WhoisXML (subdomain API)
        - Sublist3r (multi-source aggregator)
        - DNSDumpster (DNS recon)

    CRAWLING:
        - Firecrawl MAP (up to 100K URLs)
        - Firecrawl CRAWL (100-parallel recursive)

    SEARCH ENGINES:
        - Google site:
        - Bing site:
        - Brave site:
        - DuckDuckGo site:
        - Yandex site:
        - Exa site:

    ARCHIVES:
        - Wayback CDX (Internet Archive)
        - Common Crawl Index

    STRUCTURE:
        - sitemap.xml (recursive)
        - robots.txt

    BACKLINKS:
        - Majestic
        - CC WebGraph (90M domains, 166M edges)

    LOCAL:
        - Elasticsearch (our indexed data)

    FINGERPRINTING:
        - Google Analytics code sharing
"""

from .models import DiscoveredURL, MappingResult
from .mapper import Mapper, map_domain

__all__ = ["Mapper", "DiscoveredURL", "MappingResult", "map_domain"]
