#!/usr/bin/env python3
"""
Instagram platform support for Socialite.

Provides:
- URL generators for profiles, channels, tagged photos
- BrightData API integration for structured data collection (profiles, posts, comments, reels)

URL Generators (no auth required):
    instagram_profile(username) -> profile URL
    instagram_channel(username) -> reels/channel URL
    instagram_tagged(username) -> tagged photos URL
    instagram_search(query) -> Google site search

BrightData Data Collection (requires BRIGHTDATA_API_TOKEN):
    collect_profile(profile_url) -> dict
    collect_posts(post_urls) -> list[dict]
    collect_comments(post_url) -> list[dict]
    collect_reels(reel_urls) -> list[dict]

    # Typed wrapper
    InstagramDataCollector - async context manager
"""

from urllib.parse import quote_plus
from typing import Optional, Any, Union
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


# =============================================================================
# URL GENERATORS (no auth required)
# =============================================================================

def instagram_profile(username: str) -> str:
    """Direct link to Instagram profile"""
    return f"https://www.instagram.com/{username}/"


def instagram_channel(username: str) -> str:
    """Instagram channel/reels view"""
    return f"https://www.instagram.com/{username}/channel/"


def instagram_tagged(username: str) -> str:
    """Photos where user is tagged"""
    return f"https://www.instagram.com/{username}/tagged/"


def instagram_analysis(username: str) -> str:
    """Instagram profile analyzer tool (third-party)"""
    return f"https://toolzu.com/profile-analyzer/instagram/?username={username}"


def instagram_search(query: str) -> str:
    """Instagram search via Google (Instagram's search requires authentication)"""
    google_query = f"site:instagram.com {query}"
    return f"https://www.google.com/search?q={quote_plus(google_query)}"


# =============================================================================
# BRIGHTDATA INTEGRATION
# =============================================================================

# Add python-libs to path
python_libs = Path("/data/python-libs")
if python_libs.exists() and str(python_libs) not in sys.path:
    sys.path.insert(0, str(python_libs))

try:
    from brightdata import BrightDataClient
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False
    BrightDataClient = None


def _get_api_token() -> Optional[str]:
    """Get BrightData API token."""
    return os.getenv("BRIGHTDATA_API_TOKEN") or os.getenv("BRIGHTDATA_API_KEY")


def is_data_collection_available() -> bool:
    """Check if BrightData data collection is available."""
    return SDK_AVAILABLE and bool(_get_api_token())


# Dataset IDs (for reference)
INSTAGRAM_DATASETS = {
    "profiles": "gd_l1vikfch901nx3by4",
    "posts": "gd_lk5ns7kz21pck8jpis",
    "comments": "gd_ltppn085pokosxh13",
    "reels": "gd_lyclm20il4r5helnj",
}


# =============================================================================
# DATA COLLECTION FUNCTIONS
# =============================================================================

async def collect_profile(profile_url: str, timeout: int = 240) -> Optional[dict]:
    """
    Collect profile data from an Instagram profile URL.

    Args:
        profile_url: Instagram profile URL (e.g., "https://instagram.com/username")
        timeout: Maximum wait time in seconds

    Returns:
        Profile dict with: username, full_name, biography, follower_count, following_count,
        post_count, is_verified, is_business, etc.
    """
    if not is_data_collection_available():
        logger.warning("BrightData not available for Instagram data collection")
        return None

    try:
        async with BrightDataClient(api_token=_get_api_token()) as client:
            result = await client.crawler.instagram.profiles(url=profile_url, timeout=timeout)
            if result and hasattr(result, 'data'):
                data = result.data
                return data[0] if isinstance(data, list) else data
            return None
    except Exception as e:
        logger.error(f"Failed to collect Instagram profile: {e}")
        return None


async def collect_posts(
    post_urls: Union[str, list[str]],
    timeout: int = 240
) -> list[dict]:
    """
    Collect post data from Instagram post URLs.

    Args:
        post_urls: Single post URL or list of URLs
        timeout: Maximum wait time in seconds

    Returns:
        List of post dicts with: post_id, caption, like_count, comment_count,
        media_type, taken_at, etc.
    """
    if not is_data_collection_available():
        logger.warning("BrightData not available for Instagram data collection")
        return []

    urls = [post_urls] if isinstance(post_urls, str) else post_urls

    try:
        async with BrightDataClient(api_token=_get_api_token()) as client:
            result = await client.crawler.instagram.posts(url=urls, timeout=timeout)
            if result and hasattr(result, 'data'):
                data = result.data
                return data if isinstance(data, list) else [data]
            return []
    except Exception as e:
        logger.error(f"Failed to collect Instagram posts: {e}")
        return []


async def collect_comments(
    post_url: str,
    timeout: int = 240
) -> list[dict]:
    """
    Collect comments from an Instagram post.

    Args:
        post_url: Instagram post URL
        timeout: Maximum wait time in seconds

    Returns:
        List of comment dicts with: comment_id, text, user, like_count, created_at, etc.
    """
    if not is_data_collection_available():
        logger.warning("BrightData not available for Instagram data collection")
        return []

    try:
        async with BrightDataClient(api_token=_get_api_token()) as client:
            result = await client.crawler.instagram.comments(url=post_url, timeout=timeout)
            if result and hasattr(result, 'data'):
                data = result.data
                return data if isinstance(data, list) else [data]
            return []
    except Exception as e:
        logger.error(f"Failed to collect Instagram comments: {e}")
        return []


async def collect_reels(
    reel_urls: Union[str, list[str]],
    timeout: int = 240
) -> list[dict]:
    """
    Collect reel data from Instagram reel URLs.

    Args:
        reel_urls: Single reel URL or list of URLs
        timeout: Maximum wait time in seconds

    Returns:
        List of reel dicts with: post_id, caption, like_count, view_count,
        play_count, audio, etc.
    """
    if not is_data_collection_available():
        logger.warning("BrightData not available for Instagram data collection")
        return []

    urls = [reel_urls] if isinstance(reel_urls, str) else reel_urls

    try:
        async with BrightDataClient(api_token=_get_api_token()) as client:
            result = await client.crawler.instagram.reels(url=urls, timeout=timeout)
            if result and hasattr(result, 'data'):
                data = result.data
                return data if isinstance(data, list) else [data]
            return []
    except Exception as e:
        logger.error(f"Failed to collect Instagram reels: {e}")
        return []


# =============================================================================
# TYPED DATA COLLECTOR
# =============================================================================

class InstagramDataCollector:
    """
    Instagram data collector using BrightData SDK.

    Usage:
        async with InstagramDataCollector() as ig:
            profile = await ig.profile("https://instagram.com/username")
            posts = await ig.posts([post_url1, post_url2])
            comments = await ig.comments(post_url)
            reels = await ig.reels([reel_url1])
    """

    def __init__(self, timeout: int = 240):
        self.timeout = timeout
        self._client: Optional[Any] = None

    @property
    def available(self) -> bool:
        return is_data_collection_available()

    async def __aenter__(self):
        if not SDK_AVAILABLE:
            raise RuntimeError("BrightData SDK not installed")
        token = _get_api_token()
        if not token:
            raise RuntimeError("BRIGHTDATA_API_TOKEN not configured")
        self._client = BrightDataClient(api_token=token)
        await self._client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.__aexit__(exc_type, exc_val, exc_tb)

    def _extract_data(self, result) -> list[dict]:
        """Extract data from ScrapeResult."""
        if result is None:
            return []
        if hasattr(result, 'data'):
            data = result.data
            if isinstance(data, list):
                return data
            elif data is not None:
                return [data]
        return []

    async def profile(self, profile_url: str) -> Optional[dict]:
        """Collect profile data."""
        result = await self._client.crawler.instagram.profiles(
            url=profile_url, timeout=self.timeout
        )
        data = self._extract_data(result)
        return data[0] if data else None

    async def posts(self, post_urls: Union[str, list[str]]) -> list[dict]:
        """Collect post data."""
        urls = [post_urls] if isinstance(post_urls, str) else post_urls
        result = await self._client.crawler.instagram.posts(
            url=urls, timeout=self.timeout
        )
        return self._extract_data(result)

    async def comments(self, post_url: str) -> list[dict]:
        """Collect comments from post."""
        result = await self._client.crawler.instagram.comments(
            url=post_url, timeout=self.timeout
        )
        return self._extract_data(result)

    async def reels(self, reel_urls: Union[str, list[str]]) -> list[dict]:
        """Collect reel data."""
        urls = [reel_urls] if isinstance(reel_urls, str) else reel_urls
        result = await self._client.crawler.instagram.reels(
            url=urls, timeout=self.timeout
        )
        return self._extract_data(result)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # URL generators
    "instagram_profile",
    "instagram_channel",
    "instagram_tagged",
    "instagram_analysis",
    "instagram_search",
    # Data collection
    "is_data_collection_available",
    "collect_profile",
    "collect_posts",
    "collect_comments",
    "collect_reels",
    # Typed collector
    "InstagramDataCollector",
    # Dataset IDs
    "INSTAGRAM_DATASETS",
]
