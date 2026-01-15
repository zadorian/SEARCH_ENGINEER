"""
BrightData Archive Engine - Search 17.5 PB of cached web data.

SASTRE Operators (native support):
  lang{de}!     → language_whitelist: ['deu']
  -lang{de}!    → language_blacklist: ['deu']
  geo{fr}!      → ip_country_whitelist: ['fr']
  -geo{fr}!     → ip_country_blacklist: ['fr']
  cat{news}!    → category_whitelist: ['news']
  -cat{news}!   → category_blacklist: ['news']
  date{2023}!   → min_date/max_date (flexible parsing)

Unlike CC/Wayback, BrightData supports native NOT searches via blacklist filters.

Usage:
    from brute.engines.brightdata_archive import BrightDataArchiveEngine

    engine = BrightDataArchiveEngine()
    results = await engine.search("query", domains=["example.com"])
    results = await engine.search("query", languages=["de"], countries_exclude=["us"])
"""

import asyncio
import logging
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

# Import from backdrill module
try:
    from backdrill.brightdata import BrightDataArchive, convert_lang_code
    AVAILABLE = True
except ImportError as e:
    logger.warning(f"BrightData Archive not available: {e}")
    AVAILABLE = False
    BrightDataArchive = None
    convert_lang_code = lambda x: x

# Engine code for BRUTE registry
ENGINE_CODE = "BD"
ENGINE_NAME = "BrightData Archive"


class BrightDataArchiveEngine:
    """
    BrightData Archive search engine wrapper for BRUTE.

    Features:
    - Native lang{}/geo{}/cat{}/date{} operator support
    - Native NOT support via blacklist filters (-lang{}, -geo{}, -cat{})
    - 17.5 PB cached web data (larger than CC + Wayback combined)
    - Async search with polling
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self._client = None

    async def _get_client(self) -> Optional[BrightDataArchive]:
        """Get or create BrightData client."""
        if not AVAILABLE:
            return None
        if self._client is None:
            self._client = BrightDataArchive(api_key=self.api_key)
        return self._client

    async def search(
        self,
        query: str = None,
        domains: Optional[List[str]] = None,
        url: Optional[str] = None,
        # Date filters
        date: Optional[str] = None,  # Flexible: "2023", "2020-2023", "01 2023"
        min_date: Optional[str] = None,
        max_date: Optional[str] = None,
        max_age: Optional[str] = None,
        # Language filters (native NOT via blacklist)
        languages: Optional[List[str]] = None,
        languages_exclude: Optional[List[str]] = None,
        # Geo filters (native NOT via blacklist)
        countries: Optional[List[str]] = None,
        countries_exclude: Optional[List[str]] = None,
        # Category filters (native NOT via blacklist)
        categories: Optional[List[str]] = None,
        categories_exclude: Optional[List[str]] = None,
        # Path/domain pattern filters
        path_pattern: Optional[str] = None,
        path_exclude: Optional[str] = None,
        domain_pattern: Optional[str] = None,
        domain_exclude_pattern: Optional[str] = None,
        # Boolean filters
        has_captcha: Optional[bool] = None,
        robots_blocked: Optional[bool] = None,
        # Limits
        max_results: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Search BrightData Archive.

        Args:
            query: Search query (used to extract domain if not provided)
            domains: List of domains to search
            url: Specific URL to search
            date: Flexible date format (e.g., "2023", "2020-2023")
            languages: ISO 639-1 codes (auto-converted to 639-3)
            languages_exclude: Languages to exclude (native NOT)
            countries: Country codes to include
            countries_exclude: Countries to exclude (native NOT)
            categories: Categories to include
            categories_exclude: Categories to exclude (native NOT)
            max_results: Maximum results to return

        Returns:
            List of result dicts with url, title, timestamp, etc.
        """
        client = await self._get_client()
        if not client:
            logger.warning("BrightData client not available")
            return []

        try:
            result = await client.search(
                domains=domains,
                url=url,
                date=date,
                min_date=min_date,
                max_date=max_date,
                max_age=max_age,
                languages=languages,
                languages_exclude=languages_exclude,
                countries=countries,
                countries_exclude=countries_exclude,
                categories=categories,
                categories_exclude=categories_exclude,
                path_pattern=path_pattern,
                path_exclude=path_exclude,
                domain_pattern=domain_pattern,
                domain_exclude_pattern=domain_exclude_pattern,
                has_captcha=has_captcha,
                robots_blocked=robots_blocked,
                limit=max_results,
            )

            if "error" in result:
                logger.error(f"BrightData search error: {result['error']}")
                return []

            search_id = result.get("search_id")
            if not search_id:
                return []

            # Poll for results
            for _ in range(30):  # Max 60 seconds
                await asyncio.sleep(2)
                status = await client.get_search_status(search_id)

                if status.get("ready"):
                    # Return metadata about results (actual content via dump)
                    return [{
                        "source": "brightdata_archive",
                        "search_id": search_id,
                        "files_count": status.get("files_count", 0),
                        "total_size": status.get("total_size", 0),
                        "filters_applied": {
                            "languages": languages,
                            "languages_exclude": languages_exclude,
                            "countries": countries,
                            "countries_exclude": countries_exclude,
                            "categories": categories,
                            "categories_exclude": categories_exclude,
                        }
                    }]

                if "error" in status:
                    logger.error(f"BrightData status error: {status['error']}")
                    break

            await client.close()
            return []

        except Exception as e:
            logger.error(f"BrightData search failed: {e}")
            return []

    async def search_with_not(
        self,
        query: str,
        domains: Optional[List[str]] = None,
        exclude_languages: Optional[List[str]] = None,
        exclude_countries: Optional[List[str]] = None,
        exclude_categories: Optional[List[str]] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Search with native NOT support via blacklist filters.

        Unlike CC/Wayback which require post-filtering, BrightData
        handles exclusions natively at the API level.

        Args:
            query: Search query
            exclude_languages: -lang{}! operator
            exclude_countries: -geo{}! operator
            exclude_categories: -cat{}! operator
        """
        return await self.search(
            query=query,
            domains=domains,
            languages_exclude=exclude_languages,
            countries_exclude=exclude_countries,
            categories_exclude=exclude_categories,
            **kwargs
        )

    async def close(self):
        """Close the client connection."""
        if self._client:
            await self._client.close()
            self._client = None


# Convenience function for quick searches
async def search_brightdata(
    domains: List[str],
    date: Optional[str] = None,
    languages: Optional[List[str]] = None,
    countries: Optional[List[str]] = None,
    max_results: int = 100,
) -> List[Dict[str, Any]]:
    """Quick search function."""
    engine = BrightDataArchiveEngine()
    try:
        return await engine.search(
            domains=domains,
            date=date,
            languages=languages,
            countries=countries,
            max_results=max_results,
        )
    finally:
        await engine.close()
