"""
ALLDOM Bridge: LINKLATER (Related Sites & Links)

Thin wrapper for all link-based discovery operations.
LINKLATER handles: backlinks, outlinks, similar content, related sites.
DELEGATES TO: modules.linklater.api.LinkLater
"""

import logging
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)

async def _get_api():
    """Lazy load LinkLater API."""
    try:
        from modules.linklater.api import get_linklater
        return get_linklater()
    except ImportError as e:
        logger.error(f"Failed to import LinkLater API: {e}")
        return None


async def backlinks(domain_or_url: str, mode: str = "fast", **kwargs) -> List[Dict[str, Any]]:
    """
    Get backlinks (bl? or ?bl).
    
    Modes:
    - fast (?bl): Domains only - 100ms
    - rich (bl?): Pages with anchors - 30-60s
    """
    linklater = await _get_api()
    if not linklater:
        return []
        
    try:
        # LinkLater.get_backlinks handles mode logic internally or via kwargs
        results = await linklater.get_backlinks(domain_or_url, limit=kwargs.get('limit', 100))
        # Convert LinkRecord objects to dicts if needed, though they might be compatible
        return [r if isinstance(r, dict) else r.__dict__ for r in results]
    except Exception as e:
        logger.error(f"Backlinks error: {e}")
        return []


async def backlinks_domains(domain_or_url: str, **kwargs) -> List[str]:
    """Get referring domains only (?bl !domain)."""
    # Just filter the rich results or use mode="domain" if LinkLater supports it
    results = await backlinks(domain_or_url, mode="fast", **kwargs)
    return [r.get("domain") or r.get("source_domain") for r in results if r.get("domain") or r.get("source_domain")]


async def outlinks(domain_or_url: str, **kwargs) -> List[Dict[str, Any]]:
    """
    Get outlinks (ol?).
    Extract all links from target.
    """
    linklater = await _get_api()
    if not linklater:
        return []

    try:
        results = await linklater.get_outlinks(domain_or_url, limit=kwargs.get('limit', 100))
        return [r if isinstance(r, dict) else r.__dict__ for r in results]
    except Exception as e:
        logger.error(f"Outlinks error: {e}")
        return []


async def outlinks_domains(domain_or_url: str, **kwargs) -> List[str]:
    """Get linked domains only (!ol:)."""
    results = await outlinks(domain_or_url, **kwargs)
    
    # Extract domains from results
    domains = set()
    for r in results:
        # LinkRecord usually has 'target_domain' or 'domain'
        d = r.get("target_domain") or r.get("domain")
        if d:
            domains.add(d)
    
    return list(domains)


async def similar(url: str, limit: int = 20, method: str = "exa", **kwargs) -> List[Dict[str, Any]]:
    """
    Find sites similar to target URL (similar:url).
    """
    # LinkLater doesn't have a direct 'similar' method exposed in the main class yet,
    # but the previous code imported it from 'discovery.similar_discovery'.
    # We should stick to that or assume LinkLater will have it. 
    # For now, let's keep the direct import but via the module path, 
    # OR if LinkLater API has it (it imports get_related_sites from Majestic).
    # The previous code used 'find_similar'.
    
    try:
        from modules.linklater.discovery.similar_discovery import find_similar
        
        results = await find_similar(url, limit=limit, prefer_method=method, **kwargs)
        
        return [
            {
                "url": r.url,
                "domain": r.domain,
                "title": r.title,
                "score": r.score,
                "source": r.source,
                "metadata": r.metadata
            }
            for r in results
        ]
    except Exception as e:
        logger.error(f"Similar content error: {e}")
        return []


async def similar_all(url: str, limit: int = 20, **kwargs) -> Dict[str, List[Dict]]:
    """Find similar sites using all methods."""
    try:
        from modules.linklater.discovery.similar_discovery import find_similar_all
        
        results = await find_similar_all(url, limit=limit, **kwargs)
        
        formatted = {}
        for method, sites in results.items():
            formatted[method] = [
                {
                    "url": s.url,
                    "domain": s.domain,
                    "title": s.title,
                    "score": s.score,
                    "source": s.source,
                    "metadata": s.metadata
                }
                for s in sites
            ]
        
        return formatted
    except Exception as e:
        logger.error(f"Similar all methods error: {e}")
        return {}


async def related_sites(domain_or_url: str, limit: int = 20, **kwargs) -> List[Dict[str, Any]]:
    """
    Alias for similar() - find related sites.
    """
    return await similar(domain_or_url, limit=limit, **kwargs)


# Streaming variants
async def backlinks_stream(domain_or_url: str, mode: str = "fast", **kwargs) -> AsyncIterator[Dict]:
    """Stream backlinks as they're discovered."""
    # LinkLater API doesn't expose streaming backlinks yet, so we fall back to batch
    results = await backlinks(domain_or_url, mode=mode, **kwargs)
    for result in results:
        yield result


async def outlinks_stream(domain_or_url: str, **kwargs) -> AsyncIterator[Dict]:
    """Stream outlinks as they're discovered."""
    results = await outlinks(domain_or_url, **kwargs)
    for result in results:
        yield result
