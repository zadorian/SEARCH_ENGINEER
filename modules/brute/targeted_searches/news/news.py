from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

BACKEND_DIR = Path(__file__).resolve().parents[4]
MODULES_DIR = BACKEND_DIR / "modules"
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

logger = logging.getLogger(__name__)

NEWS_BANGS_PATH = BACKEND_DIR / "domain_sources" / "bangs" / "categories" / "news_bangs.json"

try:
    from search_engines.newsapi import NewsAPIEngine
    NEWSAPI_AVAILABLE = True
except Exception:
    NEWSAPI_AVAILABLE = False
    NewsAPIEngine = None

try:
    from search_engines.gdelt import GDELTNewsEngine
    GDELT_AVAILABLE = True
except Exception:
    GDELT_AVAILABLE = False
    GDELTNewsEngine = None

try:
    from brute.engines.google_news_brightdata import fetch_google_news
    BRIGHTDATA_GNEWS_AVAILABLE = True
except ImportError:
    # Try alternate path if brute not directly importable
    try:
        from modules.brute.engines.google_news_brightdata import fetch_google_news
        BRIGHTDATA_GNEWS_AVAILABLE = True
    except ImportError:
        BRIGHTDATA_GNEWS_AVAILABLE = False
        fetch_google_news = None

# BrightData Archive - native cat{news}! support (17.5 PB cached web data)
try:
    from backdrill.brightdata import BrightDataArchive, search_by_category
    BRIGHTDATA_ARCHIVE_AVAILABLE = True
except ImportError:
    BRIGHTDATA_ARCHIVE_AVAILABLE = False
    BrightDataArchive = None
    search_by_category = None

try:
    from torpedo.torpedo import Torpedo
    TORPEDO_AVAILABLE = True
except Exception:
    TORPEDO_AVAILABLE = False
    Torpedo = None

# TORPEDO NewsSearcher - uses sources/news.json with extraction recipes + date filtering
try:
    from torpedo.EXECUTION.news_searcher import NewsSearcher as TorpedoNewsSearcher
    TORPEDO_NEWS_AVAILABLE = True
except Exception:
    TORPEDO_NEWS_AVAILABLE = False
    TorpedoNewsSearcher = None

_NEWS_BANGS_CACHE: Optional[List[Dict[str, Any]]] = None


def _load_news_bangs() -> List[Dict[str, Any]]:
    global _NEWS_BANGS_CACHE
    if _NEWS_BANGS_CACHE is not None:
        return _NEWS_BANGS_CACHE
    try:
        with NEWS_BANGS_PATH.open() as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            _NEWS_BANGS_CACHE = data.get("bangs", []) or []
        elif isinstance(data, list):
            _NEWS_BANGS_CACHE = data
        else:
            _NEWS_BANGS_CACHE = []
    except Exception as exc:
        logger.warning("Failed to load news bangs from %s: %s", NEWS_BANGS_PATH, exc)
        _NEWS_BANGS_CACHE = []
    return _NEWS_BANGS_CACHE


def _normalize_country(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    cleaned = code.strip().upper()
    return cleaned[:2] if cleaned else None


def _parse_date_range(query: str) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Parse date range operators from query.
    
    Supports:
    - 2024! -> year 2024
    - 2024-2025! -> date range
    - date:2024-01-01 -> start date
    - date:2024-01-01..2024-12-31 -> date range
    - from:2024-01-01 to:2024-12-31 -> date range
    
    Returns: (cleaned_query, date_from, date_to)
    """
    working = query
    date_from = None
    date_to = None
    
    # Year range: 2020-2024! (must check before single year)
    range_match = re.search(r'\b(\d{4})-(\d{4})!', working)
    if range_match:
        date_from = f"{range_match.group(1)}-01-01"
        date_to = f"{range_match.group(2)}-12-31"
        working = working.replace(range_match.group(0), " ")
    
    # Year operator: 2024! (single year)
    if not range_match:
        year_match = re.search(r'\b(\d{4})!(?!\d)', working)
        if year_match:
            year = year_match.group(1)
            date_from = f"{year}-01-01"
            date_to = f"{year}-12-31"
            working = working.replace(year_match.group(0), " ")
    
    # date:YYYY-MM-DD or date:YYYY-MM-DD..YYYY-MM-DD
    date_match = re.search(r'date:(\d{4}-\d{2}-\d{2})(?:\.\.(\d{4}-\d{2}-\d{2}))?', working)
    if date_match:
        date_from = date_match.group(1)
        date_to = date_match.group(2) or date_from
        working = working.replace(date_match.group(0), " ")
    
    # from:YYYY-MM-DD to:YYYY-MM-DD
    from_match = re.search(r'from:(\d{4}-\d{2}-\d{2})', working)
    to_match = re.search(r'to:(\d{4}-\d{2}-\d{2})', working)
    if from_match:
        date_from = from_match.group(1)
        working = working.replace(from_match.group(0), " ")
    if to_match:
        date_to = to_match.group(1)
        working = working.replace(to_match.group(0), " ")
    
    return working.strip(), date_from, date_to


def _parse_mode_and_country(
    query: str,
    mode: Optional[str],
    country: Optional[str],
) -> Tuple[str, Optional[str], str]:
    working = query or ""

    if mode is None:
        mode_match = re.search(r"\bmode\s*[:=]\s*(global|national)\b", working, re.IGNORECASE)
        if mode_match:
            mode = mode_match.group(1).lower()
            working = working.replace(mode_match.group(0), " ")

    if country is None:
        country_match = re.search(
            r"\b(?:loc|country|national)\s*[:=]\s*([a-z]{2})\b",
            working,
            re.IGNORECASE,
        )
        if country_match:
            country = country_match.group(1)
            working = working.replace(country_match.group(0), " ")

    country = _normalize_country(country)
    mode = (mode or "").strip().lower()

    if not mode:
        mode = "national" if country else "global"

    if mode not in {"global", "national"}:
        mode = "global"

    cleaned = " ".join(working.split())
    return cleaned, country, mode


def _extract_terms(query: str) -> List[str]:
    terms = re.findall(r"[a-zA-Z0-9]{3,}", query.lower())
    seen = set()
    ordered = []
    for term in terms:
        if term not in seen:
            seen.add(term)
            ordered.append(term)
    return ordered


def _matches_terms(text: str, terms: Iterable[str]) -> bool:
    lowered = (text or "").lower()
    return any(term in lowered for term in terms) if terms else True


def _normalize_url(base_url: str, href: str) -> Optional[str]:
    if not href:
        return None
    href = href.strip()
    if href.startswith("#"):
        return None
    if href.startswith("mailto:") or href.startswith("javascript:"):
        return None
    if href.startswith("//"):
        href = f"https:{href}"
    if not href.startswith("http"):
        href = urljoin(base_url, href)
    return href


def _extract_links_from_html(
    html: str,
    base_url: str,
    query_terms: List[str],
    source_label: str,
    max_results: int,
) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    selectors = [
        "article a",
        "h1 a",
        "h2 a",
        "h3 a",
        "h4 a",
        ".headline a",
        ".title a",
        ".story a",
        ".result a",
        ".search-result a",
        "[class*=\"result\"] a",
    ]
    candidates = soup.select(", ".join(selectors)) or soup.find_all("a", href=True)
    results: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for link in candidates:
        href = link.get("href")
        text = link.get_text(" ", strip=True)
        if not href or not text or len(text) < 12:
            continue
        if not _matches_terms(text, query_terms):
            continue
        normalized = _normalize_url(base_url, href)
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        results.append(
            {
                "title": text,
                "url": normalized,
                "snippet": f"{text} ({source_label})",
                "source": source_label,
                "engine": "torpedo_national",
            }
        )
        if len(results) >= max_results:
            break

    return results


def _country_sources(country: str, max_sources: int) -> List[Dict[str, Any]]:
    if not country:
        return []
    entries = _load_news_bangs()
    normalized = country.lower()
    filtered = [e for e in entries if str(e.get("country", "")).lower() == normalized]
    filtered.sort(key=lambda e: (bool(e.get("is_global")), e.get("domain", "")))
    seen_domains: set[str] = set()
    unique: List[Dict[str, Any]] = []
    for entry in filtered:
        domain = str(entry.get("domain", "")).lower()
        if not domain or domain in seen_domains:
            continue
        seen_domains.add(domain)
        unique.append(entry)
        if len(unique) >= max_sources:
            break
    return unique


def _build_search_url(template: str, query: str) -> Optional[str]:
    if not template:
        return None
    if "{q}" not in template and "{{{s}}}" not in template:
        return None
    encoded = quote_plus(query)
    return template.replace("{q}", encoded).replace("{{{s}}}", encoded)


async def _run_in_thread(func, *args):
    if hasattr(asyncio, "to_thread"):
        return await asyncio.to_thread(func, *args)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, func, *args)


class NewsSearcher:
    def __init__(
        self,
        *,
        max_sources: int = 25,
        max_results_per_source: int = 6,
        max_concurrent: int = 6,
    ) -> None:
        self.max_sources = max_sources
        self.max_results_per_source = max_results_per_source
        self.max_concurrent = max_concurrent
        self.newsapi = NewsAPIEngine() if NEWSAPI_AVAILABLE else None
        self.gdelt = GDELTNewsEngine() if GDELT_AVAILABLE else None

    async def search(
        self,
        query: str,
        max_results: int = 50,
        *,
        mode: Optional[str] = None,
        country: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search news sources.
        
        Args:
            query: Search query (can include date operators like 2024! or date:2024-01-01)
            max_results: Maximum results to return
            mode: 'global' or 'national'
            country: ISO-2 country code for national mode
            date_from: Start date (YYYY-MM-DD) - overrides query operators
            date_to: End date (YYYY-MM-DD) - overrides query operators
        """
        # Parse date operators from query if not explicitly provided
        query_after_date, parsed_from, parsed_to = _parse_date_range(query)
        date_from = date_from or parsed_from
        date_to = date_to or parsed_to
        
        clean_query, country_code, resolved_mode = _parse_mode_and_country(query_after_date, mode, country)

        if not clean_query:
            return {"results": [], "stats": {"mode": resolved_mode, "country": country_code}}

        if resolved_mode == "national" and not country_code:
            resolved_mode = "global"

        tasks: List[asyncio.Task] = []
        if resolved_mode == "global":
            tasks.append(asyncio.create_task(self._run_global(clean_query, max_results)))
        else:
            tasks.append(asyncio.create_task(self._run_national(
                clean_query, country_code, max_results,
                date_from=date_from, date_to=date_to
            )))

        results: List[Dict[str, Any]] = []
        seen_urls: set[str] = set()
        stats: Dict[str, Any] = {"mode": resolved_mode, "country": country_code, "engines": {}}

        for task in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(task, Exception):
                logger.warning("News search task failed: %s", task)
                continue
            engine_name = task.get("engine")
            items = task.get("results", [])
            stats["engines"][engine_name] = len(items)
            for item in items:
                url = item.get("url")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                results.append(item)
                if len(results) >= max_results:
                    break

        stats["total_results"] = len(results)
        return {"results": results[:max_results], "stats": stats}

    async def _run_global(self, query: str, max_results: int) -> Dict[str, Any]:
        tasks = []
        if self.newsapi:
            tasks.append(_run_in_thread(self.newsapi.search, query, max_results))
        if self.gdelt:
            tasks.append(_run_in_thread(self.gdelt.search, query, max_results))
        if BRIGHTDATA_GNEWS_AVAILABLE:
            tasks.append(asyncio.create_task(self._run_brightdata_variations(query, max_results)))
        # BrightData Archive - native cat{news}! support
        if BRIGHTDATA_ARCHIVE_AVAILABLE:
            tasks.append(asyncio.create_task(self._run_brightdata_archive(query, max_results)))

        results: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for task in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(task, Exception):
                logger.warning("Global news engine error: %s", task)
                continue
            # Handle list return (from _run_in_thread wrappers) vs dict return (from _run_brightdata_variations)
            items = []
            if isinstance(task, dict):
                items = task.get("results", [])
            elif isinstance(task, list):
                items = task
            
            for item in items:
                url = item.get("url")
                if not url or url in seen:
                    continue
                seen.add(url)
                results.append(item)
                if len(results) >= max_results:
                    break

        return {"engine": "global", "results": results}

    async def _run_brightdata_variations(self, query: str, max_results: int) -> Dict[str, Any]:
        """Run Google News search across major regions via Bright Data."""
        if not fetch_google_news:
            return {"engine": "google_news_brightdata", "results": []}
            
        # Major regions for Tier 1 coverage
        regions = ["US", "GB", "DE", "FR", "CA", "AU", "IN", "IT", "ES", "BR"]
        inputs = [{"keyword": query, "country": r, "language": ""} for r in regions]
        
        # Batch call using async trigger mode for stability with larger batches
        articles = await fetch_google_news(inputs, async_mode=True)
        
        # Limit results per region logic is handled by API returning top results, 
        # but we might want to ensure diversity if API returns flat list. 
        # For now return all and let dedup handle it.
        
        return {"engine": "google_news_brightdata", "results": articles}

    async def _run_brightdata_archive(self, query: str, max_results: int) -> Dict[str, Any]:
        """
        Search BrightData Archive with native cat{news}! support.

        Uses the 17.5 PB cached web data with category filtering.
        """
        if not search_by_category:
            return {"engine": "brightdata_archive", "results": []}

        try:
            # Extract domain if query looks like a domain search
            domains = None
            clean_query = query
            if "site:" in query.lower():
                import re
                match = re.search(r'site:([^\s]+)', query, re.IGNORECASE)
                if match:
                    domains = [match.group(1)]
                    clean_query = re.sub(r'site:[^\s]+', '', query).strip()

            # Use native category filter for news
            results = await search_by_category(
                category="news",
                domains=domains,
                limit=max_results,
            )

            return {"engine": "brightdata_archive", "results": results}

        except Exception as e:
            logger.warning(f"BrightData Archive news search failed: {e}")
            return {"engine": "brightdata_archive", "results": []}

    async def _run_national(
        self,
        query: str,
        country: Optional[str],
        max_results: int,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search national news sources with optional date filtering.
        
        Uses TORPEDO NewsSearcher with sources/news.json (recipes + date filtering subset).
        """
        if not country:
            return {"engine": "national", "results": []}
            
        results: List[Dict[str, Any]] = []
        seen: set[str] = set()

        # PRIMARY: Use TORPEDO NewsSearcher with date filtering
        if TORPEDO_NEWS_AVAILABLE:
            try:
                torpedo_news = TorpedoNewsSearcher()
                await torpedo_news.load_sources()

                # Map GB -> UK for consistency
                jur = country.upper()
                if jur == "GB":
                    jur = "UK"

                # Search with date filtering if provided
                data = await torpedo_news.search(
                    query=query,
                    jurisdiction=jur,
                    max_sources=self.max_sources,
                    extract=True,
                    date_from=date_from,
                    date_to=date_to,
                    date_filter_only=bool(date_from or date_to)  # Only use date-capable sources if date filter
                )

                # Process TORPEDO results - structured articles
                for source_result in data.get("results", []):
                    source_name = source_result.get("source", source_result.get("domain", ""))
                    domain = source_result.get("domain", "")

                    # Extract from recipe-based articles
                    for article in source_result.get("articles", []):
                        url = article.get("url", "")
                        if not url or url in seen:
                            continue
                        seen.add(url)

                        results.append({
                            "title": article.get("title", ""),
                            "url": url,
                            "snippet": article.get("snippet", ""),
                            "date": article.get("date", ""),
                            "source": source_name,
                            "domain": domain,
                            "engine": "torpedo_national",
                        })

                        if len(results) >= max_results:
                            break

                    # Fallback: extract from raw HTML if no recipe
                    if not source_result.get("articles") and source_result.get("html"):
                        html = source_result["html"]
                        search_url = source_result.get("search_url", f"https://{domain}")
                        query_terms = _extract_terms(query)

                        extracted = _extract_links_from_html(
                            html, search_url, query_terms,
                            source_name, self.max_results_per_source
                        )

                        for item in extracted:
                            url = item.get("url")
                            if not url or url in seen:
                                continue
                            seen.add(url)
                            item["domain"] = domain
                            results.append(item)

                            if len(results) >= max_results:
                                break

                    if len(results) >= max_results:
                        break

                logger.info(f"TORPEDO national news: {len(results)} results for {jur} (date_filter={bool(date_from or date_to)})")

            except Exception as e:
                logger.warning(f"TORPEDO NewsSearcher failed: {e}, falling back to legacy")

        # FALLBACK: Legacy bangs-based search if TORPEDO unavailable or failed
        if not results and TORPEDO_AVAILABLE:
            sources = _country_sources(country, self.max_sources)
            if sources:
                query_terms = _extract_terms(query)
                semaphore = asyncio.Semaphore(self.max_concurrent)
                torpedo = Torpedo()

                async def fetch(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
                    template = entry.get("url") or ""
                    search_url = _build_search_url(template, query)
                    if not search_url:
                        return []
                    source_label = entry.get("domain") or entry.get("site") or entry.get("description") or "news"
                    async with semaphore:
                        html, _, _ = await torpedo.scrape_url(search_url, scrape_method="direct")
                    if not html:
                        return []
                    return _extract_links_from_html(
                        html, search_url, query_terms,
                        str(source_label), self.max_results_per_source,
                    )

                try:
                    batches = await asyncio.gather(
                        *(fetch(entry) for entry in sources),
                        return_exceptions=True,
                    )
                finally:
                    await torpedo.close()

                for batch in batches:
                    if isinstance(batch, Exception):
                        logger.debug("Torpedo scrape error: %s", batch)
                        continue
                    for item in batch:
                        url = item.get("url")
                        if not url or url in seen:
                            continue
                        seen.add(url)
                        results.append(item)
                        if len(results) >= max_results:
                            break

        return {"engine": "national", "results": results}


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="News search (global or national).")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--mode", choices=["global", "national"], help="Force global or national mode")
    parser.add_argument("--country", help="ISO-2 country code (national mode)")
    parser.add_argument("--limit", type=int, default=50, help="Max results")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    return parser


async def main() -> None:
    parser = _build_cli_parser()
    args = parser.parse_args()

    searcher = NewsSearcher()
    data = await searcher.search(
        args.query,
        max_results=args.limit,
        mode=args.mode,
        country=args.country,
    )

    if args.json:
        print(json.dumps(data, indent=2))
        return

    stats = data.get("stats", {})
    print(f"\nMode: {stats.get('mode')} Country: {stats.get('country')}")
    print(f"Found {len(data.get('results', []))} results.\n")
    for idx, item in enumerate(data.get("results", [])[:10], 1):
        title = item.get("title") or "(no title)"
        print(f"{idx}. {title}")
        print(f"   {item.get('url')}")


async def search_news(
    query: str,
    country: Optional[str] = None,
    max_sites: int = 25,
    max_results: int = 50,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convenience function for news search.

    This is the public API for news_bridge.py and other callers.

    Args:
        query: Search query (can include date operators like 2024! or date:2024-01-01)
        country: ISO-2 country code (e.g., 'UK', 'DE')
        max_sites: Max news sites to search
        max_results: Max total results
        date_from: Start date (YYYY-MM-DD) - overrides query operators
        date_to: End date (YYYY-MM-DD) - overrides query operators

    Returns:
        Dict with 'articles', 'sites_searched', 'stats', 'total'
    
    Date Operators in Query:
        - 2024!                    -> articles from 2024
        - 2020-2024!               -> articles from 2020-2024
        - date:2024-01-01          -> articles from that date
        - date:2024-01-01..2024-12-31  -> articles in date range
        - from:2024-01-01 to:2024-06-30 -> explicit date range
    """
    searcher = NewsSearcher(max_sources=max_sites)

    # Determine mode based on country
    mode = "national" if country else "global"

    data = await searcher.search(
        query=query,
        max_results=max_results,
        mode=mode,
        country=country,
        date_from=date_from,
        date_to=date_to,
    )

    # Transform to expected format for news_bridge.py and GRID
    results = data.get("results", [])
    stats = data.get("stats", {})

    articles = []
    for item in results:
        articles.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("snippet", ""),
            "source": item.get("source", ""),
            "domain": item.get("domain", item.get("source", "")),
            "date": item.get("date", ""),
            "engine": item.get("engine", "torpedo_national"),
        })

    return {
        "articles": articles,
        "total": len(articles),
        "sites_searched": list(stats.get("engines", {}).keys()),
        "stats": stats,
    }


if __name__ == "__main__":
    asyncio.run(main())
