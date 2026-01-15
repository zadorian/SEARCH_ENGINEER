"""
LINKLATER Search Module

Keyword search across archives and Elasticsearch.

Main exports:
- keyword_search(): Unified search interface (async)
- KeywordVariations: Generate name variations for search
- HistoricalSearcher: WAT-based keyword search in CC archives

Usage:
    from modules.linklater.search import keyword_search, KeywordVariations

    # Unified search
    results = await keyword_search(
        domain="example.com",
        keywords=["CEO", "founder"],
        source="archives"  # or "elasticsearch", "both"
    )

    # Name variations
    variations = KeywordVariations()
    names = await variations.search("john smith")
"""

from typing import List, Dict, Any, Optional

# Re-export KeywordVariations from mapping module
try:
    from ..mapping.keyword_variations import KeywordVariations
except ImportError:
    KeywordVariations = None

# Re-export HistoricalSearcher from drill module
try:
    from ..scraping.web.historical_search import HistoricalSearcher
except ImportError:
    HistoricalSearcher = None


async def keyword_search(
    domain: str,
    keywords: List[str] = None,
    source: str = "archives",
    years: List[int] = None,
    max_results: int = 100,
) -> List[Dict[str, Any]]:
    """
    Unified keyword search across archives and indexed content.

    Args:
        domain: Target domain to search
        keywords: List of keywords to find (optional - returns all if None)
        source: "archives" (Wayback/CC), "elasticsearch", or "both"
        years: Specific years to search (default: recent years)
        max_results: Maximum number of results to return

    Returns:
        List of search results with URL, timestamp, and matched content

    Example:
        results = await keyword_search(
            domain="soax.com",
            keywords=["CEO", "founder"],
            source="archives",
            years=[2023, 2024]
        )
    """
    results = []

    if source in ("archives", "both"):
        # Use HistoricalSearcher for CC/Wayback archives
        if HistoricalSearcher:
            try:
                from ..archives.optimal_archive import OptimalArchiveSearcher
                searcher = OptimalArchiveSearcher(sources=["wayback", "cc"])
                async for result in searcher.search_keywords_streaming(
                    domain,
                    keywords=keywords,
                    years=years or [2024, 2023],
                    return_html=False
                ):
                    if result.get("type") != "status":
                        results.append({
                            "url": result.get("url"),
                            "timestamp": result.get("timestamp"),
                            "source": "archive",
                            "archive_url": f"https://web.archive.org/web/{result.get('timestamp')}/{result.get('url')}",
                        })
                        if len(results) >= max_results:
                            break
            except ImportError:
                pass

    if source in ("elasticsearch", "both"):
        # TODO: Add Elasticsearch search when cymonides_bridge is implemented
        pass

    return results


__all__ = [
    # Main interface
    "keyword_search",
    # Re-exports
    "KeywordVariations",
    "HistoricalSearcher",
]
