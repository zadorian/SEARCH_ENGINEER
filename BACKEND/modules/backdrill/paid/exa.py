"""
Exa historical search for BACKDRILL.

Exa provides semantic search with date filtering:
- start_published_date: Filter content published after this date
- end_published_date: Filter content published before this date

This allows searching for historical content by publication date.
"""

import os
import aiohttp
from datetime import datetime
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

EXA_API = "https://api.exa.ai"
EXA_API_KEY = os.getenv("EXA_API_KEY")


class ExaHistorical:
    """
    Exa search client with historical date filtering.

    Exa's date parameters allow filtering by publication date:
    - start_published_date: ISO 8601 date (e.g., "2020-01-01")
    - end_published_date: ISO 8601 date

    Usage:
        exa = ExaHistorical()

        # Search with date range
        results = await exa.search(
            "company acquisition",
            start_date="2020-01-01",
            end_date="2023-12-31"
        )

        # Find similar pages from a time period
        similar = await exa.find_similar(
            "https://example.com/news/acquisition",
            start_date="2020-01-01"
        )
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ):
        self.api_key = api_key or EXA_API_KEY
        self._session = session
        self._own_session = session is None

        if not self.api_key:
            logger.warning("EXA_API_KEY not set - Exa will be unavailable")

    async def __aenter__(self):
        if self._own_session:
            self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._own_session and self._session:
            await self._session.close()

    async def _ensure_session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._own_session = True

    def _format_date(self, date_str: Optional[str]) -> Optional[str]:
        """Format date string to ISO 8601."""
        if not date_str:
            return None

        # Already in ISO format
        if 'T' in date_str:
            return date_str

        # Add time component
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.strftime("%Y-%m-%dT00:00:00.000Z")
        except:
            return date_str

    async def search(
        self,
        query: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        num_results: int = 10,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        use_autoprompt: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Search Exa with optional date filtering.

        Args:
            query: Search query
            start_date: Filter after this date (YYYY-MM-DD)
            end_date: Filter before this date (YYYY-MM-DD)
            num_results: Number of results
            include_domains: Only include these domains
            exclude_domains: Exclude these domains
            use_autoprompt: Let Exa enhance the query

        Returns:
            List of result dicts with url, title, published_date
        """
        if not self.api_key:
            return []

        await self._ensure_session()

        payload = {
            "query": query,
            "numResults": num_results,
            "useAutoprompt": use_autoprompt,
        }

        # Date filters
        if start_date:
            payload["startPublishedDate"] = self._format_date(start_date)
        if end_date:
            payload["endPublishedDate"] = self._format_date(end_date)

        # Domain filters
        if include_domains:
            payload["includeDomains"] = include_domains
        if exclude_domains:
            payload["excludeDomains"] = exclude_domains

        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        try:
            async with self._session.post(
                f"{EXA_API}/search",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    logger.debug(f"Exa search failed: {resp.status}")
                    return []

                data = await resp.json()
                results = []

                for item in data.get("results", []):
                    results.append({
                        "url": item.get("url"),
                        "title": item.get("title"),
                        "published_date": item.get("publishedDate"),
                        "score": item.get("score"),
                        "author": item.get("author"),
                    })

                return results

        except Exception as e:
            logger.error(f"Exa search failed: {e}")
            return []

    async def find_similar(
        self,
        url: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        num_results: int = 10,
        exclude_source_domain: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Find pages similar to a given URL.

        Args:
            url: Source URL to find similar content
            start_date: Filter after this date
            end_date: Filter before this date
            num_results: Number of results
            exclude_source_domain: Exclude results from source domain

        Returns:
            List of similar pages
        """
        if not self.api_key:
            return []

        await self._ensure_session()

        payload = {
            "url": url,
            "numResults": num_results,
            "excludeSourceDomain": exclude_source_domain,
        }

        if start_date:
            payload["startPublishedDate"] = self._format_date(start_date)
        if end_date:
            payload["endPublishedDate"] = self._format_date(end_date)

        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        try:
            async with self._session.post(
                f"{EXA_API}/findSimilar",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    return []

                data = await resp.json()
                results = []

                for item in data.get("results", []):
                    results.append({
                        "url": item.get("url"),
                        "title": item.get("title"),
                        "published_date": item.get("publishedDate"),
                        "score": item.get("score"),
                    })

                return results

        except Exception as e:
            logger.error(f"Exa find_similar failed: {e}")
            return []

    async def get_contents(
        self,
        urls: List[str],
        text_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Get content for a list of URLs.

        Args:
            urls: List of URLs to fetch content
            text_only: Return only text (no HTML)

        Returns:
            List of content dicts
        """
        if not self.api_key:
            return []

        await self._ensure_session()

        payload = {
            "ids": urls,  # Exa uses 'ids' but accepts URLs
            "text": text_only,
        }

        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        try:
            async with self._session.post(
                f"{EXA_API}/contents",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status != 200:
                    return []

                data = await resp.json()
                return data.get("results", [])

        except Exception as e:
            logger.error(f"Exa get_contents failed: {e}")
            return []

    async def search_with_content(
        self,
        query: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        num_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search and get content in one call.

        Convenience method that combines search + get_contents.
        """
        # First search
        search_results = await self.search(
            query,
            start_date=start_date,
            end_date=end_date,
            num_results=num_results,
        )

        if not search_results:
            return []

        # Get URLs
        urls = [r["url"] for r in search_results if r.get("url")]

        # Fetch content
        contents = await self.get_contents(urls)

        # Merge
        url_to_content = {c.get("url"): c for c in contents}

        for result in search_results:
            url = result.get("url")
            if url and url in url_to_content:
                result["content"] = url_to_content[url].get("text")

        return search_results
