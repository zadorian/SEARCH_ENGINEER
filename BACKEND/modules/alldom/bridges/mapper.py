"""
ALLDOM Bridge: MAPPER (JESTER)

Thin wrapper for URL discovery operations.
"""

import logging
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)


async def discover(domain: str, mode: str = "fast", **kwargs) -> List[Dict[str, Any]]:
    """
    Discover all URLs for domain (map!).

    Uses JESTER MAPPER with configurable depth:
    - fast: Quick sources only (<10s)
    - thorough: All sources (30-60s)
    """
    try:
        from modules.JESTER.MAPPER.mapper import JesterMapper

        mapper = JesterMapper()
        results = await mapper.discover(domain, mode=mode, **kwargs)

        return [
            {
                "url": r.url,
                "source": r.source,
                "discovered_at": r.discovered_at,
                "metadata": r.metadata,
            }
            for r in results
        ]
    except ImportError:
        logger.warning("JESTER MAPPER not available, using fallback")
        # Fallback to simpler discovery
        return await _fallback_discover(domain, **kwargs)
    except Exception as e:
        logger.error(f"Mapper discover error: {e}")
        return []


async def _fallback_discover(domain: str, **kwargs) -> List[Dict[str, Any]]:
    """Fallback URL discovery using basic methods."""
    results = []

    # Try sitemap
    try:
        sitemap_urls = await sitemaps(domain)
        results.extend(sitemap_urls)
    except Exception:
        pass

    # Try subdomains
    try:
        sub_results = await subdomains(domain)
        for sub in sub_results:
            results.append({"url": f"https://{sub}", "source": "subdomain"})
    except Exception:
        pass

    return results


async def subdomains(domain: str, **kwargs) -> List[str]:
    """
    Discover subdomains (sub!).
    """
    try:
        from modules.JESTER.MAPPER.mapper import JesterMapper

        mapper = JesterMapper()
        results = await mapper.discover_subdomains(domain, **kwargs)
        return results
    except ImportError:
        # Fallback to basic subdomain discovery
        try:
            from modules.alldom.sources.subdomain_discovery import SubdomainDiscovery
            sd = SubdomainDiscovery()
            results = []
            async for r in sd.discover_all(domain):
                results.append(r.subdomain)
            return results
        except Exception:
            pass
        return []
    except Exception as e:
        logger.error(f"Subdomain discovery error: {e}")
        return []


async def sitemaps(domain: str, **kwargs) -> List[Dict[str, Any]]:
    """
    Parse domain sitemaps (sitemap:).
    """
    try:
        from modules.JESTER.MAPPER.mapper import JesterMapper

        mapper = JesterMapper()
        results = await mapper.parse_sitemaps(domain, **kwargs)
        return [{"url": url, "source": "sitemap"} for url in results]
    except ImportError:
        # Fallback to basic sitemap parsing
        try:
            from modules.alldom.sources.sitemaps import SitemapParser
            parser = SitemapParser()
            results = []
            async for r in parser.parse_all(domain):
                results.append({"url": r.url, "source": "sitemap"})
            return results
        except Exception:
            pass
        return []
    except Exception as e:
        logger.error(f"Sitemap parsing error: {e}")
        return []


async def search_engines(domain: str, **kwargs) -> List[Dict[str, Any]]:
    """
    Discover URLs via search engines.
    """
    try:
        from modules.alldom.sources.search_engines import SearchEngineDiscovery
        se = SearchEngineDiscovery()
        results = []
        async for r in se.search_all(domain):
            results.append({"url": r.url, "source": r.source, "metadata": r.metadata})
        return results
    except Exception as e:
        logger.error(f"Search engine discovery error: {e}")
        return []


async def firecrawl_map(domain: str, **kwargs) -> List[Dict[str, Any]]:
    """
    Discover URLs via Firecrawl map endpoint.
    """
    try:
        from modules.alldom.sources.firecrawl_mapper import FirecrawlMapper
        fm = FirecrawlMapper()
        results = []
        async for r in fm.map_domain(domain):
            results.append({"url": r.url, "source": "firecrawl", "metadata": r.metadata})
        return results
    except Exception as e:
        logger.error(f"Firecrawl map error: {e}")
        return []


async def discover_stream(domain: str, mode: str = "fast", **kwargs) -> AsyncIterator[Dict]:
    """Streaming URL discovery."""
    try:
        from modules.JESTER.MAPPER.mapper import JesterMapper

        mapper = JesterMapper()
        async for result in mapper.discover_stream(domain, mode=mode, **kwargs):
            yield {
                "url": result.url,
                "source": result.source,
            }
    except Exception as e:
        logger.error(f"Mapper stream error: {e}")
