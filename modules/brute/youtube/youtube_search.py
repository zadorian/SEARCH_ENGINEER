#!/usr/bin/env python3
"""
YouTube Search Engine - Video and Comment search via YouTube Data API v3
"""

import os
from typing import Any, Dict, List, Optional
import requests
import logging

logger = logging.getLogger(__name__)

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY") or os.getenv("GOOGLE_API_KEY")


class YouTubeSearch:
    """YouTube video and comment search using Data API v3"""

    code = "YT"
    name = "youtube"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or YOUTUBE_API_KEY
        self.api_base = "https://www.googleapis.com/youtube/v3"

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 25, **kwargs) -> List[Dict[str, Any]]:
        """
        Search for videos on YouTube.

        Args:
            query: Search query
            max_results: Maximum number of results (default 25, max 50)

        Returns:
            List of video results with metadata
        """
        if not self.api_key:
            logger.warning("YouTube API key not configured")
            return []

        videos = self._search_videos(query, max_results)

        # Optionally fetch top comments from first video
        if videos and kwargs.get('include_comments', True):
            try:
                first_url = videos[0].get("url", "")
                vid = first_url.split("v=")[-1] if "v=" in first_url else None
                if vid:
                    comments = self._fetch_top_comments(vid, limit=min(5, max_results // 5))
                    videos.extend(comments)
            except Exception as e:
                logger.debug(f"Could not fetch comments: {e}")

        return videos[:max_results]

    def _search_videos(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Search for videos"""
        url = f"{self.api_base}/search"
        params = {
            "key": self.api_key,
            "q": query,
            "part": "snippet",
            "type": "video",
            "maxResults": max(1, min(limit, 50)),
        }

        try:
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            logger.error(f"YouTube API error: {e}")
            return []

        results = []
        for item in data.get("items", []):
            vid = (item.get("id") or {}).get("videoId")
            snippet = item.get("snippet") or {}

            if not vid:
                continue

            results.append({
                "title": snippet.get("title", ""),
                "url": f"https://www.youtube.com/watch?v={vid}",
                "snippet": snippet.get("description", ""),
                "thumbnail": snippet.get("thumbnails", {}).get("medium", {}).get("url", ""),
                "channel": snippet.get("channelTitle", ""),
                "published": snippet.get("publishedAt", ""),
                "engine": self.name,
                "engine_code": self.code,
                "engine_badge": "YT",
                "search_engine": "youtube",
                "source": "youtube",
                "video_id": vid,
            })

        return results

    def _fetch_top_comments(self, video_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Fetch top comments for a video"""
        url = f"{self.api_base}/commentThreads"
        params = {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": max(1, min(limit, 50)),
            "key": self.api_key,
            "textFormat": "plainText",
        }

        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception:
            return []

        results = []
        for item in data.get("items", []):
            comment_snippet = (
                (item.get("snippet") or {})
                .get("topLevelComment", {})
                .get("snippet", {})
            )
            text = comment_snippet.get("textDisplay", "")
            author = comment_snippet.get("authorDisplayName", "YouTube user")

            results.append({
                "title": f"Comment by {author}: {text[:70]}..." if len(text) > 70 else f"Comment by {author}: {text}",
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "snippet": text,
                "author": author,
                "engine": self.name,
                "engine_code": self.code,
                "source": "youtube_comment",
            })

        return results

    def search_channel(self, channel_id: str, query: str = "", max_results: int = 25) -> List[Dict[str, Any]]:
        """Search within a specific channel"""
        if not self.api_key:
            return []

        url = f"{self.api_base}/search"
        params = {
            "key": self.api_key,
            "channelId": channel_id,
            "part": "snippet",
            "type": "video",
            "maxResults": max(1, min(max_results, 50)),
        }
        if query:
            params["q"] = query

        try:
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            logger.error(f"YouTube channel search error: {e}")
            return []

        return self._parse_video_results(data)

    def _parse_video_results(self, data: Dict) -> List[Dict[str, Any]]:
        """Parse video results from API response"""
        results = []
        for item in data.get("items", []):
            vid = (item.get("id") or {}).get("videoId")
            snippet = item.get("snippet") or {}

            if not vid:
                continue

            results.append({
                "title": snippet.get("title", ""),
                "url": f"https://www.youtube.com/watch?v={vid}",
                "snippet": snippet.get("description", ""),
                "engine": self.name,
                "engine_code": self.code,
                "source": "youtube",
            })

        return results


# Alias for backward compatibility
YouTubeEngine = YouTubeSearch

__all__ = ["YouTubeSearch", "YouTubeEngine"]
