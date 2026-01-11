"""
ALLDOM Bridge: Keyword Search

Search for keywords across domain content.
Operators: keyword:?domain, keyword:url?
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

SNIPPET_RADIUS = 120
MAX_RESULTS_PER_URL = 10


def _compile_keyword_pattern(keyword: str) -> re.Pattern:
    """Compile regex pattern for keyword matching."""
    term = (keyword or "").strip()
    if not term:
        raise ValueError("Keyword must not be empty.")
    
    if " " in term:
        # Multi-word phrase - exact match
        return re.compile(re.escape(term), re.IGNORECASE)
    
    # Single word - word boundary match
    escaped = re.escape(term)
    return re.compile(rf"\b{escaped}\b", re.IGNORECASE)


def _extract_snippet(content: str, match_span: Tuple[int, int]) -> str:
    """Extract snippet around keyword match."""
    start, end = match_span
    snippet_start = max(0, start - SNIPPET_RADIUS)
    snippet_end = min(len(content), end + SNIPPET_RADIUS)
    
    prefix = content[snippet_start:start]
    match = content[start:end]
    suffix = content[end:snippet_end]
    
    parts = []
    if snippet_start > 0:
        parts.append("...")
    parts.append(prefix)
    parts.append(f"<mark>{match}</mark>")
    parts.append(suffix)
    if snippet_end < len(content):
        parts.append("...")
    
    return " ".join("".join(parts).split())


async def search_keyword(
    keyword: str,
    target: str,
    target_type: str = "domain",
    max_pages: int = 50,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Search for keyword across domain or in specific URL (keyword:?domain, keyword:url?).
    
    Args:
        keyword: Keyword or phrase to search for
        target: Domain or URL to search
        target_type: 'domain' or 'url'
        max_pages: Max pages to search (domain mode only)
        **kwargs: Additional parameters
    
    Returns:
        List of matches with url, snippets, match_count
    """
    try:
        from modules.JESTER import Jester
        from modules.JESTER.MAPPER.mapper import JesterMapper
        
        # Compile keyword pattern
        keyword_pattern = _compile_keyword_pattern(keyword)
        
        # Determine URLs to search
        urls = []
        if target_type == "url":
            urls = [target]
        else:
            # Domain mode - discover URLs first
            mapper = JesterMapper()
            async for discovered in mapper.discover_stream(target, mode="fast"):
                urls.append(discovered.url)
                if len(urls) >= max_pages:
                    break
            
            if not urls:
                urls = [f"https://{target}"]
        
        # Scrape and search for keyword
        jester = Jester()
        results = []
        
        for url in urls[:max_pages]:
            result = await jester.scrape(url)
            if not result or not result.content:
                continue
            
            content = result.content
            
            # Find all keyword matches
            matches = list(keyword_pattern.finditer(content))
            if not matches:
                continue
            
            # Extract snippets
            snippets = []
            for match in matches[:MAX_RESULTS_PER_URL]:
                snippet = _extract_snippet(content, match.span())
                snippets.append(snippet)
            
            results.append({
                "url": url,
                "title": getattr(result, "title", None) or url,
                "keyword": keyword,
                "match_count": len(matches),
                "snippets": snippets,
                "source": "keyword_search",
                "metadata": {
                    "total_matches": len(matches),
                    "snippets_shown": len(snippets)
                }
            })
        
        await jester.close()
        return results
        
    except ImportError as e:
        logger.warning(f"Keyword search dependencies not available: {e}")
        return []
    except ValueError as e:
        logger.error(f"Invalid keyword: {e}")
        raise
    except Exception as e:
        logger.error(f"Keyword search error: {e}")
        return []


async def search_domain(keyword: str, domain: str, max_pages: int = 50, **kwargs) -> List[Dict[str, Any]]:
    """Search keyword across entire domain."""
    return await search_keyword(keyword, domain, "domain", max_pages, **kwargs)


async def search_url(keyword: str, url: str, **kwargs) -> List[Dict[str, Any]]:
    """Search keyword in specific URL."""
    return await search_keyword(keyword, url, "url", **kwargs)
