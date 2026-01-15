"""
SocialSearcher - Social media search via API.

Searches across Reddit, YouTube, and other platforms using external APIs.
"""

import os
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# SocialSearcher.com API key (if available)
SOCIALSEARCHER_API_KEY = os.getenv("SOCIALSEARCHER_API_KEY", "")


class SocialSearcher:
    """Search social media platforms via API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or SOCIALSEARCHER_API_KEY
        self.base_url = "https://api.social-searcher.com/v2"

    def search(
        self,
        query: str,
        content_type: str = "all",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search social media platforms.

        Args:
            query: Search query string
            content_type: Platform type - "reddit", "youtube", "twitter", "all"
            limit: Maximum results to return

        Returns:
            List of search results with platform, text, url, author, date
        """
        if not self.api_key:
            logger.warning("SocialSearcher API key not configured - returning empty results")
            return []

        # Build search URL based on content type
        platform_map = {
            "reddit": "reddit",
            "youtube": "youtube",
            "twitter": "twitter",
            "all": "web"
        }

        try:
            import httpx

            network = platform_map.get(content_type, "web")
            params = {
                "q": query,
                "network": network,
                "limit": min(limit, 100),
                "key": self.api_key
            }

            response = httpx.get(
                f"{self.base_url}/search",
                params=params,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                return self._parse_results(data.get("posts", []))
            else:
                logger.error(f"SocialSearcher API error: {response.status_code}")
                return []

        except ImportError:
            logger.error("httpx not installed")
            return []
        except Exception as e:
            logger.error(f"SocialSearcher error: {e}")
            return []

    def _parse_results(self, posts: List[Dict]) -> List[Dict[str, Any]]:
        """Parse API response into standardized format."""
        results = []
        for post in posts:
            results.append({
                "platform": post.get("network", "unknown"),
                "text": post.get("text", ""),
                "url": post.get("url", ""),
                "author": post.get("user", {}).get("name", ""),
                "username": post.get("user", {}).get("screen_name", ""),
                "date": post.get("posted", ""),
                "likes": post.get("favorites", 0),
                "shares": post.get("shares", 0)
            })
        return results


__all__ = ["SocialSearcher"]
