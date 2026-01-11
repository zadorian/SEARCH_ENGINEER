#!/usr/bin/env python3
"""
DuckDuckGo Videos Search - Video search via DuckDuckGo
"""

import os
from typing import Any, Dict, List
from urllib.parse import quote
import logging
import requests

logger = logging.getLogger(__name__)


class DuckDuckGoVideosSearch:
    """DuckDuckGo Video Search"""

    code = "DDV"
    name = "duckduckgo_videos"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        })

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 25, **kwargs) -> List[Dict[str, Any]]:
        """
        Search for videos using DuckDuckGo.

        Args:
            query: Search query
            max_results: Maximum number of results

        Returns:
            List of video results (as clickable search URLs)
        """
        results = []

        # Generate DDG video search URLs
        encoded_query = quote(query)

        # Main video search
        results.append({
            "title": f"DuckDuckGo Videos: {query}",
            "url": f"https://duckduckgo.com/?q={encoded_query}&iax=videos&ia=videos",
            "snippet": f"Video search results for '{query}' on DuckDuckGo",
            "engine": self.name,
            "engine_code": self.code,
            "engine_badge": "DD",
            "search_engine": "duckduckgo",
            "source": "duckduckgo_videos",
            "is_search_url": True,
        })

        # Try to get actual results via API
        try:
            api_results = self._fetch_video_results(query, max_results)
            results.extend(api_results)
        except Exception as e:
            logger.debug(f"DDG video API not available: {e}")

        return results[:max_results]

    def _fetch_video_results(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Attempt to fetch video results from DDG API"""
        # DDG doesn't have a public video API, but we can try the vqd-based approach
        try:
            # Get vqd token
            vqd_url = f"https://duckduckgo.com/?q={quote(query)}"
            resp = self.session.get(vqd_url, timeout=10)

            # Extract vqd from response
            import re
            vqd_match = re.search(r'vqd="([^"]+)"', resp.text) or re.search(r"vqd=([^&]+)", resp.text)
            if not vqd_match:
                return []

            vqd = vqd_match.group(1)

            # Fetch videos
            video_url = "https://duckduckgo.com/v.js"
            params = {
                "l": "us-en",
                "o": "json",
                "q": query,
                "vqd": vqd,
            }

            video_resp = self.session.get(video_url, params=params, timeout=10)
            data = video_resp.json()

            results = []
            for item in data.get("results", [])[:limit]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("content", item.get("url", "")),
                    "snippet": item.get("description", ""),
                    "thumbnail": item.get("images", {}).get("medium", ""),
                    "duration": item.get("duration", ""),
                    "source": item.get("provider", "duckduckgo_videos"),
                    "engine": self.name,
                    "engine_code": self.code,
                    "engine_badge": "DD",
                    "search_engine": "duckduckgo",
                })

            return results

        except Exception as e:
            logger.debug(f"DDG video fetch failed: {e}")
            return []


__all__ = ["DuckDuckGoVideosSearch"]
