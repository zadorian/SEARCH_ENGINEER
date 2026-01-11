#!/usr/bin/env python3
"""
Brave Videos Search - Video-specific search using Brave Search API
"""

import os
from typing import Any, Dict, List
import logging

logger = logging.getLogger(__name__)

# Import main Brave search
try:
    from .brave import BraveSearch
    BRAVE_AVAILABLE = True
except ImportError:
    BRAVE_AVAILABLE = False
    logger.warning("Brave search not available")


class BraveVideosSearch:
    """Brave Video Search using the videos filter"""

    code = "BRV"
    name = "brave_videos"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("BRAVE_API_KEY")
        self._brave = None
        if BRAVE_AVAILABLE and self.api_key:
            self._brave = BraveSearch(api_key=self.api_key)

    def is_available(self) -> bool:
        return BRAVE_AVAILABLE and bool(self.api_key)

    def search(self, query: str, max_results: int = 25, **kwargs) -> List[Dict[str, Any]]:
        """
        Search for videos using Brave Search API.

        Args:
            query: Search query
            max_results: Maximum number of results

        Returns:
            List of video results
        """
        if not self._brave:
            logger.warning("Brave Videos not available - no API key or brave module")
            return []

        try:
            # Use Brave's video search method
            results = self._brave.brave_video_search(query, max_results=max_results)

            # Normalize results
            normalized = []
            for r in results:
                normalized.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("description", r.get("snippet", "")),
                    "thumbnail": r.get("thumbnail", {}).get("src", "") if isinstance(r.get("thumbnail"), dict) else r.get("thumbnail", ""),
                    "duration": r.get("video", {}).get("duration", "") if isinstance(r.get("video"), dict) else "",
                    "source": r.get("source", "brave_videos"),
                    "engine": self.name,
                    "engine_code": self.code,
                    "engine_badge": "BR",
                    "search_engine": "brave",
                })

            return normalized[:max_results]

        except Exception as e:
            logger.error(f"Brave video search error: {e}")
            return []


__all__ = ["BraveVideosSearch"]
