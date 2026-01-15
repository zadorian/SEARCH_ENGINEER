#!/usr/bin/env python3
"""
Bloomberg news platform integration.

Provides:
- Article scraping via Apify (actor KIZXeJ0LsBt6YYeLi)
- URL generation for articles and search
- Entity extraction from articles

This module bridges to news.py for core functionality.
"""

from typing import Optional, List, Dict, Any
from urllib.parse import quote_plus


# Bridge imports from news.py
from .news import (
    NewsArticle,
    scrape_bloomberg as scrape_article,
    scrape_bloomberg_batch as scrape_articles,
    bloomberg_url,
    bloomberg_search_url,
    get_bloomberg_article,
)


# =============================================================================
# URL GENERATORS
# =============================================================================

def bloomberg_profile_url(ticker: str) -> str:
    """Generate Bloomberg company profile URL from ticker."""
    return f"https://www.bloomberg.com/quote/{ticker.upper()}"


def bloomberg_markets_url() -> str:
    """Bloomberg markets overview."""
    return "https://www.bloomberg.com/markets"


def bloomberg_news_url(category: str = "markets") -> str:
    """Bloomberg news by category."""
    valid = ["markets", "technology", "politics", "wealth", "pursuits", "opinion"]
    if category.lower() not in valid:
        category = "markets"
    return f"https://www.bloomberg.com/{category.lower()}"


def bloomberg_company_news_url(company: str) -> str:
    """Search Bloomberg for company news."""
    return bloomberg_search_url(company)


def bloomberg_person_news_url(name: str) -> str:
    """Search Bloomberg for person news."""
    return bloomberg_search_url(f'"{name}"')


# =============================================================================
# SCRAPING
# =============================================================================

def scrape_bloomberg_article(url: str) -> NewsArticle:
    """
    Scrape a Bloomberg article.

    Args:
        url: Bloomberg article URL

    Returns:
        NewsArticle object with extracted content
    """
    return scrape_article(url)


def scrape_bloomberg_articles(urls: List[str]) -> List[NewsArticle]:
    """
    Scrape multiple Bloomberg articles.

    Args:
        urls: List of Bloomberg URLs

    Returns:
        List of NewsArticle objects
    """
    return scrape_articles(urls)


def extract_entities(article: NewsArticle) -> Dict[str, List[str]]:
    """
    Extract named entities from a Bloomberg article.

    Args:
        article: NewsArticle object

    Returns:
        Dict with 'companies', 'people', 'locations' lists
    """
    entities = {
        "companies": [],
        "people": [],
        "locations": [],
        "tags": article.tags,
    }

    # If raw data has entity info, use it
    if article.raw:
        entities["companies"] = article.raw.get("companies", []) or []
        entities["people"] = article.raw.get("people", []) or []
        entities["locations"] = article.raw.get("locations", []) or []

    return entities


# =============================================================================
# SEARCH RESULTS FORMAT
# =============================================================================

def bloomberg_results(
    query: str,
    *,
    search_type: str = "all",
) -> List[Dict[str, Any]]:
    """
    Generate Bloomberg search result links.

    Args:
        query: Search term
        search_type: "all", "news", "video", "audio"

    Returns:
        List of result dicts in standard format
    """
    results = [
        {
            "title": f"Bloomberg Search: {query}",
            "url": bloomberg_search_url(query),
            "source": "bloomberg",
            "search_engine": "bloomberg",
            "engine_code": "BBG",
            "engine_badge": "BBG",
            "metadata": {
                "type": "search",
                "query": query,
                "search_type": search_type,
            },
        }
    ]

    # Add specialized searches
    if search_type == "all" or search_type == "news":
        results.append({
            "title": f"Bloomberg News: {query}",
            "url": f"https://www.bloomberg.com/search?query={quote_plus(query)}&type=news",
            "source": "bloomberg",
            "search_engine": "bloomberg",
            "engine_code": "BBG",
            "engine_badge": "BBG",
            "metadata": {"type": "news_search"},
        })

    return results


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Data structures
    "NewsArticle",

    # URLs
    "bloomberg_url",
    "bloomberg_search_url",
    "bloomberg_profile_url",
    "bloomberg_markets_url",
    "bloomberg_news_url",
    "bloomberg_company_news_url",
    "bloomberg_person_news_url",

    # Scraping
    "scrape_bloomberg_article",
    "scrape_bloomberg_articles",
    "get_bloomberg_article",
    "extract_entities",

    # Results
    "bloomberg_results",
]


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python bloomberg.py <url|search_query>")
        sys.exit(1)

    arg = sys.argv[1]

    if arg.startswith("http"):
        # Scrape article
        article = scrape_bloomberg_article(arg)
        print(json.dumps({
            "url": article.url,
            "title": article.title,
            "author": article.author,
            "date": article.published_date.isoformat() if article.published_date else None,
            "summary": article.summary,
            "content_preview": article.content[:500] if article.content else "",
            "entities": extract_entities(article),
        }, indent=2))
    else:
        # Generate search URL
        print(f"Search URL: {bloomberg_search_url(arg)}")
        print(f"Company profile: {bloomberg_profile_url(arg)}")
