#!/usr/bin/env python3
"""
Brave Images Search - Image search using Brave Search API
"""

import os
from typing import Any, Dict, List
from urllib.parse import quote
import logging
import requests

logger = logging.getLogger(__name__)

BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")


class BraveImagesSearch:
    """Brave Image Search using the images endpoint"""

    code = "BRI"
    name = "brave_images"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or BRAVE_API_KEY
        self.base_url = "https://api.search.brave.com/res/v1/images/search"

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 25, **kwargs) -> List[Dict[str, Any]]:
        """
        Search for images using Brave Search API.

        Args:
            query: Search query
            max_results: Maximum number of results

        Returns:
            List of image results
        """
        results = []

        # Add direct search URL
        encoded_query = quote(query)
        results.append({
            "title": f"Brave Images: {query}",
            "url": f"https://search.brave.com/images?q={encoded_query}",
            "snippet": f"Image search results for '{query}' on Brave",
            "engine": self.name,
            "engine_code": self.code,
            "engine_badge": "BR",
            "search_engine": "brave",
            "source": "brave_images",
            "is_search_url": True,
        })

        # If API key available, fetch actual results
        if self.api_key:
            try:
                api_results = self._fetch_api_results(query, max_results)
                results.extend(api_results)
            except Exception as e:
                logger.debug(f"Brave Images API error: {e}")

        return results[:max_results]

    def _fetch_api_results(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Fetch image results from Brave Images API"""
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key,
        }
        params = {
            "q": query,
            "count": min(limit, 100),
        }

        try:
            r = requests.get(self.base_url, headers=headers, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            logger.error(f"Brave Images API error: {e}")
            return []

        results = []
        for item in data.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description", ""),
                "thumbnail": item.get("thumbnail", {}).get("src", "") if isinstance(item.get("thumbnail"), dict) else item.get("thumbnail", ""),
                "source_url": item.get("source", ""),
                "width": item.get("properties", {}).get("width"),
                "height": item.get("properties", {}).get("height"),
                "engine": self.name,
                "engine_code": self.code,
                "engine_badge": "BR",
                "search_engine": "brave",
                "source": "brave_images",
            })

        return results

    def search_safe(self, query: str, safe_search: str = "moderate", max_results: int = 25) -> List[Dict[str, Any]]:
        """
        Search with safe search filter.

        Args:
            query: Search query
            safe_search: Safety level (off, moderate, strict)
            max_results: Maximum results

        Returns:
            List of image results
        """
        if not self.api_key:
            return self.search(query, max_results)

        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key,
        }
        params = {
            "q": query,
            "count": min(max_results, 100),
            "safesearch": safe_search,
        }

        try:
            r = requests.get(self.base_url, headers=headers, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()

            results = []
            for item in data.get("results", []):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("description", ""),
                    "thumbnail": item.get("thumbnail", {}).get("src", ""),
                    "engine": self.name,
                    "engine_code": self.code,
                    "engine_badge": "BR",
                    "search_engine": "brave",
                    "source": "brave_images",
                })

            return results

        except Exception as e:
            logger.error(f"Brave Images search error: {e}")
            return self.search(query, max_results)


__all__ = ["BraveImagesSearch"]
