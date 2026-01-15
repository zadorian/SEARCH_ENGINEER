#!/usr/bin/env python3
"""
Google Images Search - Image search via Google Custom Search API or URL generation
"""

import os
from typing import Any, Dict, List
from urllib.parse import quote
import logging
import requests

logger = logging.getLogger(__name__)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID") or os.getenv("GOOGLE_SEARCH_ENGINE_ID")


class GoogleImagesSearch:
    """Google Image Search"""

    code = "GI"
    name = "google_images"

    def __init__(self, api_key: str = None, cse_id: str = None):
        self.api_key = api_key or GOOGLE_API_KEY
        self.cse_id = cse_id or GOOGLE_CSE_ID

    def is_available(self) -> bool:
        return bool(self.api_key and self.cse_id)

    def search(self, query: str, max_results: int = 25, **kwargs) -> List[Dict[str, Any]]:
        """
        Search for images using Google.

        Args:
            query: Search query
            max_results: Maximum number of results

        Returns:
            List of image results
        """
        results = []

        # Always add direct search URL
        encoded_query = quote(query)
        results.append({
            "title": f"Google Images: {query}",
            "url": f"https://www.google.com/search?q={encoded_query}&tbm=isch",
            "snippet": f"Image search results for '{query}' on Google",
            "engine": self.name,
            "engine_code": self.code,
            "engine_badge": "GO",
            "search_engine": "google",
            "source": "google_images",
            "is_search_url": True,
        })

        # If API available, fetch actual results
        if self.api_key and self.cse_id:
            try:
                api_results = self._fetch_api_results(query, max_results)
                results.extend(api_results)
            except Exception as e:
                logger.debug(f"Google Images API error: {e}")

        return results[:max_results]

    def _fetch_api_results(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Fetch image results from Google Custom Search API"""
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": self.api_key,
            "cx": self.cse_id,
            "q": query,
            "searchType": "image",
            "num": min(limit, 10),  # API max is 10 per request
        }

        try:
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            logger.error(f"Google Images API error: {e}")
            return []

        results = []
        for item in data.get("items", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "thumbnail": item.get("image", {}).get("thumbnailLink", ""),
                "context_url": item.get("image", {}).get("contextLink", ""),
                "width": item.get("image", {}).get("width"),
                "height": item.get("image", {}).get("height"),
                "engine": self.name,
                "engine_code": self.code,
                "engine_badge": "GO",
                "search_engine": "google",
                "source": "google_images",
            })

        return results

    def search_by_type(self, query: str, image_type: str = "photo", max_results: int = 25) -> List[Dict[str, Any]]:
        """
        Search with image type filter.

        Args:
            query: Search query
            image_type: Type filter (photo, face, clipart, lineart, animated)
            max_results: Maximum results

        Returns:
            List of filtered image results
        """
        encoded_query = quote(query)
        type_param = {
            "photo": "photo",
            "face": "face",
            "clipart": "clipart",
            "lineart": "lineart",
            "animated": "animated",
        }.get(image_type, "")

        url = f"https://www.google.com/search?q={encoded_query}&tbm=isch"
        if type_param:
            url += f"&tbs=itp:{type_param}"

        return [{
            "title": f"Google Images ({image_type}): {query}",
            "url": url,
            "snippet": f"{image_type.capitalize()} image search for '{query}'",
            "engine": self.name,
            "engine_code": self.code,
            "engine_badge": "GO",
            "search_engine": "google",
            "source": "google_images",
            "is_search_url": True,
        }]


__all__ = ["GoogleImagesSearch"]
