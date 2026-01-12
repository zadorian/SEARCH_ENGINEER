"""
ALLDOM Bridge: JESTER (Implementation)

Direct integration with the JESTER Mapper module.
This file contains the actual logic for communicating with JESTER.
"""

import logging
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)

async def discover(domain: str, mode: str = "fast", **kwargs) -> List[Dict[str, Any]]:
    """
    Discover all URLs for domain using JESTER.
    """
    try:
        from modules.jester.MAPPER.mapper import Mapper

        results = []
        is_fast = (mode == "fast")
        
        async with Mapper() as mapper:
            async for r in mapper.map_domain(domain, fast=is_fast, **kwargs):
                # Convert DiscoveredURL to ALLDOM format
                data = r.to_dict()
                # Extract top-level keys
                url = data.pop("url")
                source = data.pop("source") 
                discovered_at = data.pop("discovered_at")
                
                results.append({
                    "url": url,
                    "source": source,
                    "discovered_at": discovered_at,
                    "metadata": data,
                    "scenario": "jester-scraped-url-node",
                })

        return results
    except ImportError:
        logger.warning("JESTER MAPPER not available")
        return []
    except Exception as e:
        logger.error(f"Jester bridge discover error: {e}")
        return []

async def subdomains(domain: str, **kwargs) -> List[str]:
    """
    Discover subdomains using JESTER.
    """
    try:
        from modules.jester.MAPPER.mapper import Mapper

        results = []
        async with Mapper() as mapper:
            async for sub in mapper.discover_subdomains(domain, **kwargs):
                results.append(sub)
        return results
    except Exception as e:
        logger.error(f"Jester bridge subdomains error: {e}")
        return []

async def sitemaps(domain: str, **kwargs) -> List[Dict[str, Any]]:
    """
    Parse sitemaps using JESTER.
    """
    try:
        from modules.jester.MAPPER.mapper import Mapper

        results = []
        async with Mapper() as mapper:
            async for r in mapper.map_domain(domain, sources=["sitemap"], **kwargs):
                 data = r.to_dict()
                 results.append({
                     "url": data["url"], 
                     "source": "sitemap",
                     "metadata": data,
                     "scenario": "jester-scraped-url-node"
                 })
        return results
    except Exception as e:
        logger.error(f"Jester bridge sitemaps error: {e}")
        return []

async def search_engines(domain: str, **kwargs) -> List[Dict[str, Any]]:
    """
    Discover via search engines using JESTER.
    """
    try:
        from modules.jester.MAPPER.mapper import Mapper
        
        results = []
        async with Mapper() as mapper:
            async for r in mapper.map_domain(domain, sources=["search_engines"], **kwargs):
                data = r.to_dict()
                results.append({
                    "url": data["url"],
                    "source": data["source"],
                    "metadata": data,
                    "scenario": "jester-scraped-url-node"
                })
        return results
    except Exception as e:
        logger.error(f"Jester bridge search_engines error: {e}")
        return []

async def firecrawl_map(domain: str, **kwargs) -> List[Dict[str, Any]]:
    """
    Discover via Firecrawl using JESTER.
    """
    try:
        from modules.jester.MAPPER.mapper import Mapper
        
        results = []
        async with Mapper() as mapper:
            async for r in mapper.map_domain(domain, sources=["firecrawl_map"], **kwargs):
                data = r.to_dict()
                results.append({
                    "url": data["url"],
                    "source": "firecrawl",
                    "metadata": data,
                    "scenario": "jester-scraped-url-node"
                })
        return results
    except Exception as e:
        logger.error(f"Jester bridge firecrawl error: {e}")
        return []

async def discover_stream(domain: str, mode: str = "fast", **kwargs) -> AsyncIterator[Dict]:
    """Streaming discovery using JESTER."""
    try:
        from modules.jester.MAPPER.mapper import Mapper

        is_fast = (mode == "fast")
        
        async with Mapper() as mapper:
            async for r in mapper.map_domain(domain, fast=is_fast, **kwargs):
                data = r.to_dict()
                url = data.pop("url")
                source = data.pop("source")
                
                yield {
                    "url": url,
                    "source": source,
                    "metadata": data,
                    "scenario": "jester-scraped-url-node"
                }
    except Exception as e:
        logger.error(f"Jester bridge stream error: {e}")
