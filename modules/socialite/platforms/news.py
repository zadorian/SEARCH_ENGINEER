#!/usr/bin/env python3
"""
News platform integrations via Apify.

Provides scraping for:
- Bloomberg
- Reuters
- Financial Times
- WSJ
- Generic news articles

Uses Apify actors for paywall bypass and structured extraction.
"""

import os
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


# =============================================================================
# APIFY CONFIGURATION
# =============================================================================

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_TOKEN")

# News-specific Apify actors
NEWS_ACTORS = {
    "bloomberg": "KIZXeJ0LsBt6YYeLi",
    "google_news": "KIe0dFDnUt4mqQyVI",
    "reuters": "anchor/reuters-scraper",
    "generic": "apify/web-scraper",
}

# Google News time filters
GOOGLE_NEWS_TIME_FILTERS = [
    "Past hour",
    "Past 24 hours",
    "Past week",
    "Past month",
    "Past year",
    "Recent",  # alias for Recent
]

# Google News languages
GOOGLE_NEWS_LANGUAGES = [
    "English", "Spanish", "French", "German", "Italian", "Portuguese",
    "Russian", "Chinese", "Japanese", "Korean", "Arabic", "Hindi",
]

# Google News countries
GOOGLE_NEWS_COUNTRIES = [
    "Any", "United States", "United Kingdom", "Canada", "Australia",
    "Germany", "France", "Spain", "Italy", "Brazil", "India", "Japan",
]


def _get_apify_client():
    """Get Apify client."""
    if not APIFY_TOKEN:
        raise ValueError("APIFY_API_TOKEN or APIFY_TOKEN environment variable required")
    try:
        from apify_client import ApifyClient
        return ApifyClient(APIFY_TOKEN)
    except ImportError:
        raise ImportError("apify-client not installed. Run: pip install apify-client")


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class NewsArticle:
    """Structured news article data."""
    url: str
    title: str = ""
    content: str = ""
    author: str = ""
    authors: List[str] = field(default_factory=list)
    published_date: Optional[datetime] = None
    source: str = ""
    summary: str = ""
    tags: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    images: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
        """Parse various date formats."""
        if not date_str:
            return None
        for fmt in [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%B %d, %Y",
            "%b %d, %Y",
        ]:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None


# =============================================================================
# BLOOMBERG
# =============================================================================

def scrape_bloomberg(url: str) -> NewsArticle:
    """
    Scrape a Bloomberg news article.

    Args:
        url: Bloomberg article URL (e.g., https://www.bloomberg.com/news/articles/...)

    Returns:
        NewsArticle with extracted data
    """
    client = _get_apify_client()

    run_input = {"url": url}
    run = client.actor(NEWS_ACTORS["bloomberg"]).call(run_input=run_input)

    results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

    if not results:
        logger.warning(f"No results for Bloomberg URL: {url}")
        return NewsArticle(url=url, source="Bloomberg")

    data = results[0]

    return NewsArticle(
        url=data.get("url", url),
        title=data.get("title", "") or data.get("headline", ""),
        content=data.get("content", "") or data.get("body", "") or data.get("text", ""),
        author=data.get("author", ""),
        authors=data.get("authors", []) or [],
        published_date=NewsArticle._parse_date(
            data.get("publishedAt") or data.get("date") or data.get("published_time")
        ),
        source="Bloomberg",
        summary=data.get("summary", "") or data.get("abstract", "") or data.get("description", ""),
        tags=data.get("tags", []) or data.get("keywords", []) or [],
        entities=data.get("entities", []) or data.get("people", []) + data.get("companies", []),
        images=data.get("images", []) or ([data.get("image")] if data.get("image") else []),
        raw=data,
    )


def scrape_bloomberg_batch(urls: List[str]) -> List[NewsArticle]:
    """
    Scrape multiple Bloomberg articles.

    Args:
        urls: List of Bloomberg article URLs

    Returns:
        List of NewsArticle objects
    """
    articles = []
    for url in urls:
        try:
            article = scrape_bloomberg(url)
            articles.append(article)
        except Exception as e:
            logger.error(f"Failed to scrape Bloomberg {url}: {e}")
            articles.append(NewsArticle(url=url, source="Bloomberg"))
    return articles


# =============================================================================
# GOOGLE NEWS
# =============================================================================

@dataclass
class GoogleNewsArticle:
    """Google News article data."""
    url: str
    title: str = ""
    snippet: str = ""
    source: str = ""
    source_url: str = ""
    published_date: Optional[datetime] = None
    published_ago: str = ""
    thumbnail: str = ""
    keyword: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "GoogleNewsArticle":
        """Create from Apify API response."""
        return cls(
            url=data.get("link", "") or data.get("url", ""),
            title=data.get("title", ""),
            snippet=data.get("snippet", "") or data.get("description", ""),
            source=data.get("source", "") or data.get("publisher", ""),
            source_url=data.get("source_url", ""),
            published_date=NewsArticle._parse_date(data.get("date") or data.get("published_date")),
            published_ago=data.get("time", "") or data.get("published_ago", ""),
            thumbnail=data.get("thumbnail", "") or data.get("image", ""),
            keyword=data.get("keyword", ""),
            raw=data,
        )


def scrape_google_news(
    keyword: str,
    *,
    time_filter: str = "Recent",
    language: str = "English",
    country: str = "Any",
    max_items: int = 30,
) -> List[GoogleNewsArticle]:
    """
    Scrape Google News for articles matching a keyword.

    Args:
        keyword: Search keyword/topic (e.g., "Technology", "Climate Change")
        time_filter: Time filter - "Past hour", "Past 24 hours", "Past week",
                     "Past month", "Past year", "Recent"
        language: Language - "English", "Spanish", "French", etc.
        country: Country filter - "Any", "United States", "United Kingdom", etc.
        max_items: Maximum articles to return (default 30)

    Returns:
        List of GoogleNewsArticle objects
    """
    client = _get_apify_client()

    # Normalize time filter
    time_map = {
        "recent": "Recent",
        "hour": "Past hour",
        "24h": "Past 24 hours",
        "day": "Past 24 hours",
        "week": "Past week",
        "month": "Past month",
        "year": "Past year",
    }
    normalized_time = time_map.get(time_filter.lower(), time_filter)

    run_input = {
        "keyword": keyword,
        "time_filter": normalized_time,
        "language": language,
        "country": country if country != "Any" else "Any",
        "maxitems": max_items,
    }

    run = client.actor(NEWS_ACTORS["google_news"]).call(run_input=run_input)
    results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

    return [GoogleNewsArticle.from_api(r) for r in results]


def search_news(
    query: str,
    *,
    time_filter: str = "Past week",
    language: str = "English",
    country: str = "Any",
    max_results: int = 30,
) -> List[Dict[str, Any]]:
    """
    Search Google News and return simplified results.

    Args:
        query: Search query
        time_filter: Time filter
        language: Language
        country: Country
        max_results: Max results

    Returns:
        List of article dicts
    """
    articles = scrape_google_news(
        keyword=query,
        time_filter=time_filter,
        language=language,
        country=country,
        max_items=max_results,
    )

    return [
        {
            "url": a.url,
            "title": a.title,
            "snippet": a.snippet,
            "source": a.source,
            "published_ago": a.published_ago,
            "thumbnail": a.thumbnail,
        }
        for a in articles
    ]


def get_trending_news(
    topic: str = "Headlines",
    country: str = "United States",
    max_items: int = 20,
) -> List[GoogleNewsArticle]:
    """
    Get trending news for a topic.

    Args:
        topic: Topic category (e.g., "Headlines", "Technology", "Business")
        country: Country
        max_items: Max articles

    Returns:
        List of GoogleNewsArticle objects
    """
    return scrape_google_news(
        keyword=topic,
        time_filter="Recent",
        language="English",
        country=country,
        max_items=max_items,
    )


# =============================================================================
# GENERIC NEWS SCRAPER
# =============================================================================

def scrape_news_url(url: str) -> NewsArticle:
    """
    Generic news article scraper.
    Attempts to extract article content from any news URL.

    Args:
        url: News article URL

    Returns:
        NewsArticle with extracted data
    """
    # Detect source and use specialized scraper if available
    url_lower = url.lower()

    if "bloomberg.com" in url_lower:
        return scrape_bloomberg(url)

    # Fall back to generic scraper
    client = _get_apify_client()

    run_input = {
        "startUrls": [{"url": url}],
        "pageFunction": """
        async function pageFunction(context) {
            const { $, request } = context;

            // Try multiple selectors for article content
            const selectors = {
                title: ['h1', 'article h1', '.headline', '.title', '[itemprop="headline"]'],
                content: ['article', '.article-body', '.story-body', '.post-content', '[itemprop="articleBody"]'],
                author: ['.author', '.byline', '[rel="author"]', '[itemprop="author"]'],
                date: ['time', '[datetime]', '.date', '.published', '[itemprop="datePublished"]'],
            };

            const getText = (sels) => {
                for (const sel of sels) {
                    const el = $(sel).first();
                    if (el.length) return el.text().trim();
                }
                return '';
            };

            return {
                url: request.url,
                title: getText(selectors.title) || $('title').text(),
                content: getText(selectors.content) || $('body').text().substring(0, 10000),
                author: getText(selectors.author),
                date: $('time').attr('datetime') || getText(selectors.date),
            };
        }
        """,
    }

    run = client.actor(NEWS_ACTORS["generic"]).call(run_input=run_input)
    results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

    if not results:
        return NewsArticle(url=url)

    data = results[0]

    # Try to detect source from URL
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.replace("www.", "")
    source = domain.split(".")[0].title()

    return NewsArticle(
        url=data.get("url", url),
        title=data.get("title", ""),
        content=data.get("content", ""),
        author=data.get("author", ""),
        published_date=NewsArticle._parse_date(data.get("date")),
        source=source,
        raw=data,
    )


# =============================================================================
# URL GENERATORS
# =============================================================================

def bloomberg_url(slug: str) -> str:
    """Generate Bloomberg article URL from slug."""
    if slug.startswith("http"):
        return slug
    return f"https://www.bloomberg.com/news/articles/{slug}"


def bloomberg_search_url(query: str) -> str:
    """Generate Bloomberg search URL."""
    from urllib.parse import quote_plus
    return f"https://www.bloomberg.com/search?query={quote_plus(query)}"


def reuters_search_url(query: str) -> str:
    """Generate Reuters search URL."""
    from urllib.parse import quote_plus
    return f"https://www.reuters.com/site-search/?query={quote_plus(query)}"


def ft_search_url(query: str) -> str:
    """Generate Financial Times search URL."""
    from urllib.parse import quote_plus
    return f"https://www.ft.com/search?q={quote_plus(query)}"


def wsj_search_url(query: str) -> str:
    """Generate Wall Street Journal search URL."""
    from urllib.parse import quote_plus
    return f"https://www.wsj.com/search?query={quote_plus(query)}"


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_bloomberg_article(url: str) -> Dict[str, Any]:
    """
    Get Bloomberg article as dict.
    Convenience wrapper for scrape_bloomberg.
    """
    article = scrape_bloomberg(url)
    return {
        "url": article.url,
        "title": article.title,
        "content": article.content,
        "author": article.author,
        "authors": article.authors,
        "published_date": article.published_date.isoformat() if article.published_date else None,
        "source": article.source,
        "summary": article.summary,
        "tags": article.tags,
        "entities": article.entities,
    }


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Data structures
    "NewsArticle",
    "GoogleNewsArticle",

    # Bloomberg
    "scrape_bloomberg",
    "scrape_bloomberg_batch",
    "bloomberg_url",
    "bloomberg_search_url",
    "get_bloomberg_article",

    # Google News
    "scrape_google_news",
    "search_news",
    "get_trending_news",
    "GOOGLE_NEWS_TIME_FILTERS",
    "GOOGLE_NEWS_LANGUAGES",
    "GOOGLE_NEWS_COUNTRIES",

    # Generic
    "scrape_news_url",

    # URL generators
    "reuters_search_url",
    "ft_search_url",
    "wsj_search_url",
]


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python news.py <url>")
        print("\nExamples:")
        print("  python news.py https://www.bloomberg.com/news/articles/2025-02-02/...")
        sys.exit(1)

    url = sys.argv[1]
    article = scrape_news_url(url)

    print(json.dumps({
        "url": article.url,
        "title": article.title,
        "content": article.content[:500] + "..." if len(article.content) > 500 else article.content,
        "author": article.author,
        "date": article.published_date.isoformat() if article.published_date else None,
        "source": article.source,
        "summary": article.summary,
    }, indent=2))
