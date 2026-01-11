#!/usr/bin/env python3
"""
DuckDuckGo Images Search - Image search via DuckDuckGo
"""

from typing import Any, Dict, List
from urllib.parse import quote
import logging
import requests
import re

logger = logging.getLogger(__name__)


class DuckDuckGoImagesSearch:
    """DuckDuckGo Image Search"""

    code = "DDI"
    name = "duckduckgo_images"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        })

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 25, **kwargs) -> List[Dict[str, Any]]:
        """
        Search for images using DuckDuckGo.

        Args:
            query: Search query
            max_results: Maximum number of results

        Returns:
            List of image results
        """
        results = []

        # Generate DDG image search URL
        encoded_query = quote(query)
        results.append({
            "title": f"DuckDuckGo Images: {query}",
            "url": f"https://duckduckgo.com/?q={encoded_query}&iax=images&ia=images",
            "snippet": f"Image search results for '{query}' on DuckDuckGo",
            "engine": self.name,
            "engine_code": self.code,
            "engine_badge": "DD",
            "search_engine": "duckduckgo",
            "source": "duckduckgo_images",
            "is_search_url": True,
        })

        # Try to get actual results via API
        try:
            api_results = self._fetch_image_results(query, max_results)
            results.extend(api_results)
        except Exception as e:
            logger.debug(f"DDG image API not available: {e}")

        return results[:max_results]

    def _fetch_image_results(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Attempt to fetch image results from DDG"""
        try:
            # Get vqd token
            vqd_url = f"https://duckduckgo.com/?q={quote(query)}"
            resp = self.session.get(vqd_url, timeout=10)

            # Extract vqd from response
            vqd_match = re.search(r'vqd="([^"]+)"', resp.text) or re.search(r"vqd=([^&]+)", resp.text)
            if not vqd_match:
                return []

            vqd = vqd_match.group(1)

            # Fetch images
            image_url = "https://duckduckgo.com/i.js"
            params = {
                "l": "us-en",
                "o": "json",
                "q": query,
                "vqd": vqd,
            }

            image_resp = self.session.get(image_url, params=params, timeout=10)
            data = image_resp.json()

            results = []
            for item in data.get("results", [])[:limit]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("image", ""),
                    "snippet": item.get("title", ""),
                    "thumbnail": item.get("thumbnail", ""),
                    "source_url": item.get("url", ""),
                    "width": item.get("width"),
                    "height": item.get("height"),
                    "source": item.get("source", "duckduckgo_images"),
                    "engine": self.name,
                    "engine_code": self.code,
                    "engine_badge": "DD",
                    "search_engine": "duckduckgo",
                })

            return results

        except Exception as e:
            logger.debug(f"DDG image fetch failed: {e}")
            return []

    def search_by_size(self, query: str, size: str = "medium", max_results: int = 25) -> List[Dict[str, Any]]:
        """
        Search with size filter.

        Args:
            query: Search query
            size: Size filter (small, medium, large, wallpaper)
            max_results: Maximum results

        Returns:
            List of image results
        """
        encoded_query = quote(query)
        size_param = {
            "small": "Small",
            "medium": "Medium",
            "large": "Large",
            "wallpaper": "Wallpaper",
        }.get(size, "")

        url = f"https://duckduckgo.com/?q={encoded_query}&iax=images&ia=images"
        if size_param:
            url += f"&iaf=size:{size_param}"

        return [{
            "title": f"DuckDuckGo Images ({size}): {query}",
            "url": url,
            "snippet": f"{size.capitalize()} image search for '{query}'",
            "engine": self.name,
            "engine_code": self.code,
            "engine_badge": "DD",
            "search_engine": "duckduckgo",
            "source": "duckduckgo_images",
            "is_search_url": True,
        }]


__all__ = ["DuckDuckGoImagesSearch"]
