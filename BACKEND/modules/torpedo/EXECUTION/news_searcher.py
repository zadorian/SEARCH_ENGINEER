"""
NewsSearcher - News Source Searcher

Searches news sources by jurisdiction using templates from sources/news.json.

Usage:
    from TORPEDO.news_searcher import NewsSearcher

    news = NewsSearcher()
    await news.load_sources()

    # Search UK news
    results = await news.search("Brexit", "UK")

    # Get available jurisdictions
    jurs = news.get_jurisdictions()
"""

import json
import logging
import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional
from urllib.parse import quote_plus

from .base_searcher import BaseSearcher
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime, date
import re

# Import pagination helper
from ..PROCESSING.pagination_detector import PaginationDetector

logger = logging.getLogger("Torpedo.NewsSearcher")

from ..paths import news_sources_path as _default_news_sources_path

DEFAULT_NEWS_SOURCES_PATH = _default_news_sources_path()


class NewsSearcher(BaseSearcher):
    """News Source Searcher - searches news outlets by jurisdiction."""

    def __init__(self):
        super().__init__()
        self.sources: Dict[str, List[Dict[str, Any]]] = {}  # jurisdiction -> sources
        self.loaded = False
        self.paginator = PaginationDetector()  # For building next page URLs

    async def load_sources(self, sources_path: Optional[str | Path] = None) -> int:
        """
        Load news sources from sources/news.json.

        Returns: Number of sources loaded.
        """
        if self.loaded:
            return sum(len(s) for s in self.sources.values())

        count = 0

        path = Path(sources_path) if sources_path else DEFAULT_NEWS_SOURCES_PATH

        if not path.exists():
            logger.error(f"Missing news sources file: {path}")
            return 0

        try:
            logger.info(f"Loading from {path}")
            with open(path) as f:
                data = json.load(f)

            for jur, sources in data.items():
                if not isinstance(sources, list):
                    continue

                if jur == "GB":
                    jur = "UK"

                if jur not in self.sources:
                    self.sources[jur] = []

                for source in sources:
                    template = source.get("search_template")
                    if template and "{q}" in template:
                        self.sources[jur].append({
                            "id": source.get("id"),
                            "domain": source.get("domain"),
                            "name": source.get("name", source.get("domain")),
                            "search_template": template,
                            "reliability": source.get("reliability", 0.5),
                            "type": source.get("type", "news_outlet"),
                            "category": source.get("category", "news"),
                            "region": source.get("region"),
                            "scrape_method": source.get("scrape_method"),
                            "search_recipe": source.get("search_recipe"),  # CSS selectors
                            "date_filtering": source.get("date_filtering"),  # Date params
                            "pagination": source.get("pagination"),  # Pagination config from PROCESSOR
                            "needs_js": source.get("needs_js", False)
                        })
                        count += 1

            self.loaded = True
            total = sum(len(s) for s in self.sources.values())
            logger.info(f"Loaded {total} news sources across {len(self.sources)} jurisdictions")
            return total

        except Exception as e:
            logger.error(f"Failed to load news sources: {e}")
            return 0

    def get_jurisdictions(self) -> List[str]:
        """Get list of available jurisdictions."""
        return sorted(self.sources.keys())

    def get_sources_for_jurisdiction(self, jurisdiction: str) -> List[Dict[str, Any]]:
        """Get all news sources for a jurisdiction."""
        if jurisdiction == "GB":
            jurisdiction = "UK"
        return self.sources.get(jurisdiction.upper(), [])

    def _extract_with_recipe(
        self,
        html: str,
        recipe: Dict[str, str],
        base_url: str = ""
    ) -> List[Dict[str, Any]]:
        """Extract search results from HTML using a recipe."""
        soup = BeautifulSoup(html, 'html.parser')
        results = []

        container_sel = recipe.get("container", "article")
        title_sel = recipe.get("title", "a")
        url_sel = recipe.get("url", "a[href]")
        snippet_sel = recipe.get("snippet", "p")
        date_sel = recipe.get("date")

        containers = soup.select(container_sel)

        for container in containers:
            result = {}

            # Extract title (use separator to preserve spaces between inline elements)
            title_el = container.select_one(title_sel)
            if title_el:
                result["title"] = title_el.get_text(separator=' ', strip=True)

            # Extract URL
            url_el = container.select_one(url_sel)
            if url_el:
                href = url_el.get("href", "")
                if href and not href.startswith("http"):
                    if base_url:
                        href = urljoin(base_url, href)
                result["url"] = href

            # Extract snippet (use separator to preserve spaces)
            snippet_el = container.select_one(snippet_sel)
            if snippet_el:
                result["snippet"] = snippet_el.get_text(separator=' ', strip=True)

            # Extract date
            if date_sel:
                date_el = container.select_one(date_sel)
                if date_el:
                    result["date"] = date_el.get("datetime") or date_el.get_text(strip=True)

            # Only add if we have meaningful data (URL required, title optional but must exist)
            if result.get("url") and result.get("title"):
                results.append(result)

        return results

    def _build_date_url(
        self,
        source: Dict[str, Any],
        query: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> str:
        """Build search URL with date parameters if supported."""
        date_config = source.get("date_filtering")

        if date_config and date_config.get("supported") and (date_from or date_to):
            # Use date template if available
            template = date_config.get("template_date", source.get("search_template"))
            url = template.replace("{q}", quote_plus(query))

            # Format dates according to source requirements
            date_format = date_config.get("date_format", "YYYY-MM-DD")

            if date_from:
                formatted_from = self._format_date(date_from, date_format)
                url = url.replace("{date_from}", formatted_from)

            if date_to:
                formatted_to = self._format_date(date_to, date_format)
                url = url.replace("{date_to}", formatted_to)

            return url

        # Fallback to regular template
        return source.get("search_template", "").replace("{q}", quote_plus(query))

    def _format_date(self, date_str: str, target_format: str) -> str:
        """Format date string to target format."""
        try:
            # Parse input (assume YYYY-MM-DD)
            d = datetime.strptime(date_str, "%Y-%m-%d")

            if target_format == "YYYY-MM-DD":
                return d.strftime("%Y-%m-%d")
            elif target_format == "DD-MM-YYYY":
                return d.strftime("%d-%m-%Y")
            elif target_format == "DD.MM.YYYY":
                return d.strftime("%d.%m.%Y")
            elif target_format == "DD/MM/YYYY":
                return d.strftime("%d/%m/%Y")
            elif target_format == "YYYYMMDD":
                return d.strftime("%Y%m%d")
            elif target_format == "timestamp":
                return str(int(d.timestamp()))
            else:
                return date_str
        except:
            return date_str

    async def search(
        self,
        query: str,
        jurisdiction: str,
        max_sources: int = 5,
        max_pages: int = 1,  # NEW: Max pages to fetch per source (pagination)
        use_brightdata: bool = False,
        min_reliability: float = 0.0,
        extract: bool = True,
        # Filters
        source_type: Optional[str] = None,  # e.g., "business", "sports", "tabloid"
        region: Optional[str] = None,  # e.g., "Catalonia", "Bavaria"
        # Date filters
        date_from: Optional[str] = None,  # YYYY-MM-DD
        date_to: Optional[str] = None,  # YYYY-MM-DD
        date_filter_only: bool = False,  # Only use sources with date filtering
        # Scrape method filter
        scrape_method_filter: Optional[str] = None,  # e.g., "firecrawl" - only use sources with this method
        require_recipe: bool = False,  # Only use sources with extraction recipes
        limit: Optional[int] = None,  # Alias for max_sources (CLI compatibility)
    ) -> Dict[str, Any]:
        """
        Search news sources for a jurisdiction with filtering and pagination.

        Args:
            query: Search term
            jurisdiction: 2-letter jurisdiction code (e.g., "UK", "DE")
            max_sources: Maximum number of sources to query
            max_pages: Maximum pages to fetch per source (pagination, default 1)
            use_brightdata: Use BrightData proxy for blocked sites
            min_reliability: Minimum reliability score (0.0-1.0)
            extract: If True, extract structured results using recipe
            source_type: Filter by source type (business, sports, tabloid, etc)
            region: Filter by region within jurisdiction
            date_from: Start date for date-filtered search (YYYY-MM-DD)
            date_to: End date for date-filtered search (YYYY-MM-DD)
            date_filter_only: If True, only query sources that support date filtering
            scrape_method_filter: Only use sources with this scrape method (e.g., "firecrawl")
            require_recipe: If True, only use sources with extraction recipes

        Returns:
            {
                "jurisdiction": str,
                "query": str,
                "sources_queried": int,
                "total_articles": int,
                "pages_fetched": int,
                "filters_applied": {...},
                "results": [{source, domain, articles: [...], pages_fetched: int, ...}],
                "errors": []
            }
        """
        if limit is not None:
            max_sources = limit

        if not self.loaded:
            await self.load_sources()

        if jurisdiction == "GB":
            jurisdiction = "UK"

        sources = self.get_sources_for_jurisdiction(jurisdiction)

        # Apply filters
        filters_applied = {}

        # Filter by reliability
        if min_reliability > 0:
            sources = [s for s in sources if s.get("reliability", 0) >= min_reliability]
            filters_applied["min_reliability"] = min_reliability

        # Filter by source type
        if source_type:
            sources = [s for s in sources if s.get("type", "").lower() == source_type.lower()]
            filters_applied["type"] = source_type

        # Filter by region
        if region:
            sources = [s for s in sources if region.lower() in (s.get("region", "") or "").lower()]
            filters_applied["region"] = region

        # Filter by date support
        if date_filter_only or (date_from or date_to):
            date_capable = [s for s in sources if (s.get("date_filtering") or {}).get("supported")]
            if date_capable:
                sources = date_capable
                filters_applied["date_capable"] = True
            if date_from:
                filters_applied["date_from"] = date_from
            if date_to:
                filters_applied["date_to"] = date_to

        # Filter by scrape method (e.g., only firecrawl sources)
        if scrape_method_filter:
            sources = [s for s in sources if (s.get("scrape_method") or "").lower() == scrape_method_filter.lower()]
            filters_applied["scrape_method"] = scrape_method_filter

        # Filter to only sources with extraction recipes
        if require_recipe:
            sources = [s for s in sources if s.get("search_recipe")]
            filters_applied["require_recipe"] = True

        # Sort by reliability (highest first)
        sources = sorted(sources, key=lambda x: x.get("reliability", 0), reverse=True)

        if not sources:
            return {
                "jurisdiction": jurisdiction,
                "query": query,
                "sources_queried": 0,
                "total_articles": 0,
                "filters_applied": filters_applied,
                "results": [],
                "errors": [f"No news sources found for jurisdiction: {jurisdiction} with applied filters"]
            }

        # Limit sources
        sources_to_query = sources[:max_sources]

        # Execute searches in parallel with pagination support
        async def search_source(source: Dict[str, Any]) -> Dict[str, Any]:
            # Build URL (with date params if applicable)
            search_url = self._build_date_url(source, query, date_from, date_to)

            # Use pre-classified scrape_method if available
            scrape_method = source.get("scrape_method")
            pagination_config = source.get("pagination")

            all_articles = []
            pages_fetched = 0
            current_url = search_url
            seen_urls = set()  # Dedup articles by URL

            # Fetch up to max_pages
            for page_num in range(1, max_pages + 1):
                response = await self.fetch_url(
                    current_url,
                    scrape_method=scrape_method,
                    use_brightdata=use_brightdata
                )

                if not response["success"]:
                    if page_num == 1:
                        # First page failed - return error
                        return {
                            "source": source["name"],
                            "domain": source["domain"],
                            "type": source.get("type", "news_outlet"),
                            "region": source.get("region"),
                            "search_url": search_url,
                            "reliability": source.get("reliability", 0.5),
                            "success": False,
                            "method_used": response.get("method_used"),
                            "error": response["error"],
                            "articles": [],
                            "pages_fetched": 0
                        }
                    # Later page failed - return what we have
                    break

                pages_fetched += 1

                # Extract articles from this page
                if response["html"] and extract:
                    recipe = source.get("search_recipe")
                    if recipe:
                        page_articles = self._extract_with_recipe(
                            response["html"],
                            recipe,
                            base_url=f"https://{source['domain']}"
                        )
                        # Dedup by URL
                        for article in page_articles:
                            url = article.get("url", "")
                            if url and url not in seen_urls:
                                seen_urls.add(url)
                                all_articles.append(article)

                # Check if we should fetch more pages
                if page_num >= max_pages:
                    break

                if not pagination_config:
                    break  # No pagination config - only first page

                # Build next page URL
                next_url = self.paginator.get_next_page_url(
                    search_url,
                    pagination_config,
                    current_page=page_num
                )

                if not next_url:
                    break  # No more pages

                current_url = next_url

                # Small delay between pages to be polite
                await asyncio.sleep(0.5)

            result = {
                "source": source["name"],
                "domain": source["domain"],
                "type": source.get("type", "news_outlet"),
                "region": source.get("region"),
                "search_url": search_url,
                "reliability": source.get("reliability", 0.5),
                "success": True,
                "method_used": response.get("method_used"),
                "error": None,
                "articles": all_articles,
                "pages_fetched": pages_fetched
            }

            return result

        tasks = [search_source(s) for s in sources_to_query]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        final_results = []
        errors = []
        total_articles = 0
        total_pages = 0

        for r in results:
            if isinstance(r, Exception):
                errors.append(str(r))
            else:
                final_results.append(r)
                total_articles += len(r.get("articles", []))
                total_pages += r.get("pages_fetched", 1)

        return {
            "jurisdiction": jurisdiction,
            "query": query,
            "sources_queried": len(sources_to_query),
            "total_articles": total_articles,
            "total_pages_fetched": total_pages,
            "filters_applied": filters_applied,
            "results": final_results,
            "errors": errors
        }

    async def search_global(
        self,
        query: str,
        max_sources: int = 10,
        top_jurisdictions: List[str] = None
    ) -> Dict[str, Any]:
        """
        Search across multiple jurisdictions.

        Args:
            query: Search term
            max_sources: Total max sources across all jurisdictions
            top_jurisdictions: Priority jurisdictions (default: UK, US, DE, FR)

        Returns combined results.
        """
        if not self.loaded:
            await self.load_sources()

        if top_jurisdictions is None:
            top_jurisdictions = ["UK", "US", "DE", "FR", "GLOBAL"]

        all_results = []
        errors = []
        sources_per_jur = max(1, max_sources // len(top_jurisdictions))

        for jur in top_jurisdictions:
            result = await self.search(query, jur, max_sources=sources_per_jur)
            all_results.extend(result["results"])
            errors.extend(result["errors"])

        return {
            "query": query,
            "jurisdictions": top_jurisdictions,
            "sources_queried": len(all_results),
            "results": all_results,
            "errors": errors
        }
