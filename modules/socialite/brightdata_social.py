"""
SOCIALITE BrightData Social - Facebook data collection via BrightData SDK.

Provides structured data collection for Facebook:
- Profiles
- Posts (by profile, group, or URL)
- Comments
- Reels
- Events

Uses BrightData's official Python SDK for reliable data collection.
"""

import os
import sys
import logging
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Add python-libs to path for BrightData SDK
python_libs = Path("/data/python-libs")
if python_libs.exists() and str(python_libs) not in sys.path:
    sys.path.insert(0, str(python_libs))

# Try to import BrightData SDK
try:
    from brightdata import BrightDataClient
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False
    BrightDataClient = None


# =============================================================================
# CONFIGURATION
# =============================================================================

def _get_api_token() -> Optional[str]:
    """Get BrightData API token from environment."""
    return os.getenv("BRIGHTDATA_API_TOKEN") or os.getenv("BRIGHTDATA_API_KEY")


def brightdata_sdk_available() -> bool:
    """Check if BrightData SDK is installed."""
    return SDK_AVAILABLE


def brightdata_facebook_available() -> bool:
    """Check if BrightData Facebook collection is available."""
    return SDK_AVAILABLE and bool(_get_api_token())


def get_brightdata_client():
    """
    Get async BrightData client.

    Usage:
        async with get_brightdata_client() as client:
            result = await client.crawler.facebook.posts(url=url)
    """
    if not SDK_AVAILABLE:
        raise ImportError("BrightData SDK not installed. Run: pip install brightdata")
    token = _get_api_token()
    if not token:
        raise ValueError("BRIGHTDATA_API_TOKEN environment variable not set")
    return BrightDataClient(api_token=token)


def get_brightdata_sync_client():
    """Get synchronous BrightData client wrapper."""
    return get_brightdata_client()


# Facebook Dataset IDs
FACEBOOK_DATASETS = {
    "posts_by_profile": "gd_l1vikqnt5poorcr2ej",
    "posts_by_group": "gd_lyclm1871i4mcmrxo9",
    "post_by_url": "gd_l1vikqnt3k3b2o4r93",
    "comments": "gd_l1vikqo02w8gnjmz79",
    "reels": "gd_lyclr31z0cz99xy823",
    "profile": "gd_l1vikqo9l31x7pkxr0",
    "profiles": "gd_l1vikqo9l31x7pkxr0",
    "event": "gd_l1vikr8t0r0l9c5s12",
    "events": "gd_l1vikr8t0r0l9c5s12",
}


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class FacebookPost:
    """Facebook post data."""
    post_url: str
    post_id: str = ""
    author_name: str = ""
    author_url: str = ""
    content: str = ""
    posted_at: Optional[datetime] = None
    likes: int = 0
    comments: int = 0
    shares: int = 0
    views: int = 0
    media_urls: List[str] = field(default_factory=list)
    hashtags: List[str] = field(default_factory=list)
    is_video: bool = False
    is_reel: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "FacebookPost":
        posted = data.get("posted_at", data.get("timestamp", data.get("date")))
        if isinstance(posted, str):
            try:
                posted = datetime.fromisoformat(posted.replace("Z", "+00:00"))
            except:
                posted = None

        return cls(
            post_url=data.get("url", data.get("post_url", "")),
            post_id=data.get("post_id", data.get("id", "")),
            author_name=data.get("author_name", data.get("author", "")),
            author_url=data.get("author_url", data.get("author_profile", "")),
            content=data.get("content", data.get("text", data.get("message", ""))),
            posted_at=posted,
            likes=data.get("likes", data.get("like_count", 0)),
            comments=data.get("comments", data.get("comment_count", 0)),
            shares=data.get("shares", data.get("share_count", 0)),
            views=data.get("views", data.get("view_count", 0)),
            media_urls=data.get("media_urls", data.get("media", [])),
            hashtags=data.get("hashtags", []),
            is_video=data.get("is_video", False),
            is_reel=data.get("is_reel", False),
            raw=data,
        )


@dataclass
class FacebookComment:
    """Facebook comment data."""
    comment_id: str = ""
    post_url: str = ""
    author_name: str = ""
    author_url: str = ""
    content: str = ""
    posted_at: Optional[datetime] = None
    likes: int = 0
    replies: int = 0
    is_reply: bool = False
    parent_comment_id: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "FacebookComment":
        posted = data.get("posted_at", data.get("timestamp"))
        if isinstance(posted, str):
            try:
                posted = datetime.fromisoformat(posted.replace("Z", "+00:00"))
            except:
                posted = None

        return cls(
            comment_id=data.get("comment_id", data.get("id", "")),
            post_url=data.get("post_url", ""),
            author_name=data.get("author_name", data.get("author", "")),
            author_url=data.get("author_url", ""),
            content=data.get("content", data.get("text", "")),
            posted_at=posted,
            likes=data.get("likes", 0),
            replies=data.get("replies", data.get("reply_count", 0)),
            is_reply=data.get("is_reply", False),
            parent_comment_id=data.get("parent_comment_id", ""),
            raw=data,
        )


@dataclass
class FacebookReel:
    """Facebook reel data."""
    reel_url: str
    reel_id: str = ""
    author_name: str = ""
    author_url: str = ""
    caption: str = ""
    posted_at: Optional[datetime] = None
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    duration_seconds: int = 0
    thumbnail_url: str = ""
    video_url: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "FacebookReel":
        posted = data.get("posted_at", data.get("timestamp"))
        if isinstance(posted, str):
            try:
                posted = datetime.fromisoformat(posted.replace("Z", "+00:00"))
            except:
                posted = None

        return cls(
            reel_url=data.get("url", data.get("reel_url", "")),
            reel_id=data.get("reel_id", data.get("id", "")),
            author_name=data.get("author_name", data.get("author", "")),
            author_url=data.get("author_url", ""),
            caption=data.get("caption", data.get("text", "")),
            posted_at=posted,
            views=data.get("views", data.get("view_count", 0)),
            likes=data.get("likes", 0),
            comments=data.get("comments", 0),
            shares=data.get("shares", 0),
            duration_seconds=data.get("duration", data.get("duration_seconds", 0)),
            thumbnail_url=data.get("thumbnail", data.get("thumbnail_url", "")),
            video_url=data.get("video_url", ""),
            raw=data,
        )


@dataclass
class FacebookGroupPost(FacebookPost):
    """Facebook group post with additional group context."""
    group_name: str = ""
    group_url: str = ""
    group_id: str = ""


@dataclass
class FacebookProfile:
    """Facebook profile data."""
    profile_url: str
    user_id: str = ""
    name: str = ""
    username: str = ""
    bio: str = ""
    location: str = ""
    work: str = ""
    education: str = ""
    relationship_status: str = ""
    profile_image: str = ""
    cover_image: str = ""
    friends: int = 0
    followers: int = 0
    following: int = 0
    verified: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "FacebookProfile":
        return cls(
            profile_url=data.get("url", data.get("profile_url", "")),
            user_id=data.get("user_id", data.get("id", "")),
            name=data.get("name", ""),
            username=data.get("username", ""),
            bio=data.get("bio", data.get("about", "")),
            location=data.get("location", data.get("current_city", "")),
            work=data.get("work", data.get("employer", "")),
            education=data.get("education", ""),
            relationship_status=data.get("relationship_status", ""),
            profile_image=data.get("profile_image", data.get("avatar", "")),
            cover_image=data.get("cover_image", data.get("cover", "")),
            friends=data.get("friends", data.get("friend_count", 0)),
            followers=data.get("followers", data.get("follower_count", 0)),
            following=data.get("following", 0),
            verified=data.get("verified", False),
            raw=data,
        )


@dataclass
class FacebookEvent:
    """Facebook event data."""
    event_url: str
    event_id: str = ""
    name: str = ""
    description: str = ""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    location: str = ""
    organizer_name: str = ""
    organizer_url: str = ""
    attending: int = 0
    interested: int = 0
    cover_image: str = ""
    is_online: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "FacebookEvent":
        def parse_time(val):
            if isinstance(val, str):
                try:
                    return datetime.fromisoformat(val.replace("Z", "+00:00"))
                except:
                    return None
            return val

        return cls(
            event_url=data.get("url", data.get("event_url", "")),
            event_id=data.get("event_id", data.get("id", "")),
            name=data.get("name", data.get("title", "")),
            description=data.get("description", ""),
            start_time=parse_time(data.get("start_time")),
            end_time=parse_time(data.get("end_time")),
            location=data.get("location", data.get("venue", "")),
            organizer_name=data.get("organizer_name", data.get("host", "")),
            organizer_url=data.get("organizer_url", ""),
            attending=data.get("attending", data.get("going_count", 0)),
            interested=data.get("interested", data.get("interested_count", 0)),
            cover_image=data.get("cover_image", data.get("cover", "")),
            is_online=data.get("is_online", False),
            raw=data,
        )


# =============================================================================
# FACEBOOK API CLIENT
# =============================================================================

class FacebookAPI:
    """
    Facebook data collection API using BrightData SDK.

    Usage:
        async with FacebookAPI() as fb:
            posts = await fb.posts_by_profile("https://facebook.com/user")
            profile = await fb.profile("https://facebook.com/user")
    """

    def __init__(self, timeout: int = 180):
        self.timeout = timeout
        self._client = None

    @property
    def available(self) -> bool:
        return brightdata_facebook_available()

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

    def _extract_data(self, result) -> List[Dict]:
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

    async def posts_by_profile(
        self,
        profile_url: str,
        limit: int = 20,
    ) -> List[FacebookPost]:
        """Get posts from a Facebook profile."""
        result = await self._client.crawler.facebook.posts_by_profile(
            url=profile_url,
            limit=limit,
            timeout=self.timeout,
        )
        data = self._extract_data(result)
        return [FacebookPost.from_api(d) for d in data]

    async def posts_by_group(
        self,
        group_url: str,
        limit: int = 20,
    ) -> List[FacebookGroupPost]:
        """Get posts from a Facebook group."""
        result = await self._client.crawler.facebook.posts_by_group(
            url=group_url,
            limit=limit,
            timeout=self.timeout,
        )
        data = self._extract_data(result)
        posts = []
        for d in data:
            post = FacebookGroupPost.from_api(d)
            post.group_url = group_url
            posts.append(post)
        return posts

    async def post(self, post_url: str) -> Optional[FacebookPost]:
        """Get a single post by URL."""
        result = await self._client.crawler.facebook.post(
            url=post_url,
            timeout=self.timeout,
        )
        data = self._extract_data(result)
        return FacebookPost.from_api(data[0]) if data else None

    async def comments(
        self,
        post_url: str,
        limit: int = 50,
    ) -> List[FacebookComment]:
        """Get comments on a post."""
        result = await self._client.crawler.facebook.comments(
            url=post_url,
            limit=limit,
            timeout=self.timeout,
        )
        data = self._extract_data(result)
        comments = [FacebookComment.from_api(d) for d in data]
        for c in comments:
            c.post_url = post_url
        return comments

    async def reels(
        self,
        profile_url: str,
        limit: int = 10,
    ) -> List[FacebookReel]:
        """Get reels from a profile."""
        result = await self._client.crawler.facebook.reels(
            url=profile_url,
            limit=limit,
            timeout=self.timeout,
        )
        data = self._extract_data(result)
        return [FacebookReel.from_api(d) for d in data]

    async def profile(self, profile_url: str) -> Optional[FacebookProfile]:
        """Get profile data."""
        result = await self._client.crawler.facebook.profile(
            url=profile_url,
            timeout=self.timeout,
        )
        data = self._extract_data(result)
        return FacebookProfile.from_api(data[0]) if data else None

    async def profiles(self, profile_urls: List[str]) -> List[FacebookProfile]:
        """Get multiple profiles."""
        profiles = []
        for url in profile_urls:
            try:
                p = await self.profile(url)
                if p:
                    profiles.append(p)
            except Exception as e:
                logger.error(f"Failed to get profile {url}: {e}")
        return profiles

    async def event(self, event_url: str) -> Optional[FacebookEvent]:
        """Get event data."""
        result = await self._client.crawler.facebook.event(
            url=event_url,
            timeout=self.timeout,
        )
        data = self._extract_data(result)
        return FacebookEvent.from_api(data[0]) if data else None

    async def events(self, event_urls: List[str]) -> List[FacebookEvent]:
        """Get multiple events."""
        events = []
        for url in event_urls:
            try:
                e = await self.event(url)
                if e:
                    events.append(e)
            except Exception as e:
                logger.error(f"Failed to get event {url}: {e}")
        return events


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def facebook_posts_by_profile(
    profile_url: str,
    limit: int = 20,
    timeout: int = 180,
) -> List[FacebookPost]:
    """Get posts from a Facebook profile."""
    async with FacebookAPI(timeout=timeout) as fb:
        return await fb.posts_by_profile(profile_url, limit)


async def facebook_posts_by_group(
    group_url: str,
    limit: int = 20,
    timeout: int = 180,
) -> List[FacebookGroupPost]:
    """Get posts from a Facebook group."""
    async with FacebookAPI(timeout=timeout) as fb:
        return await fb.posts_by_group(group_url, limit)


async def facebook_post(
    post_url: str,
    timeout: int = 180,
) -> Optional[FacebookPost]:
    """Get a single post by URL."""
    async with FacebookAPI(timeout=timeout) as fb:
        return await fb.post(post_url)


async def facebook_comments(
    post_url: str,
    limit: int = 50,
    timeout: int = 180,
) -> List[FacebookComment]:
    """Get comments on a post."""
    async with FacebookAPI(timeout=timeout) as fb:
        return await fb.comments(post_url, limit)


async def facebook_reels(
    profile_url: str,
    limit: int = 10,
    timeout: int = 180,
) -> List[FacebookReel]:
    """Get reels from a profile."""
    async with FacebookAPI(timeout=timeout) as fb:
        return await fb.reels(profile_url, limit)


async def facebook_profile(
    profile_url: str,
    timeout: int = 180,
) -> Optional[FacebookProfile]:
    """Get profile data."""
    async with FacebookAPI(timeout=timeout) as fb:
        return await fb.profile(profile_url)


async def facebook_profiles(
    profile_urls: List[str],
    timeout: int = 180,
) -> List[FacebookProfile]:
    """Get multiple profiles."""
    async with FacebookAPI(timeout=timeout) as fb:
        return await fb.profiles(profile_urls)


async def facebook_event(
    event_url: str,
    timeout: int = 180,
) -> Optional[FacebookEvent]:
    """Get event data."""
    async with FacebookAPI(timeout=timeout) as fb:
        return await fb.event(event_url)


async def facebook_events(
    event_urls: List[str],
    timeout: int = 180,
) -> List[FacebookEvent]:
    """Get multiple events."""
    async with FacebookAPI(timeout=timeout) as fb:
        return await fb.events(event_urls)


async def facebook_posts_by_username(
    username: str,
    limit: int = 20,
    timeout: int = 180,
) -> List[FacebookPost]:
    """Get posts from a Facebook user by username."""
    profile_url = f"https://www.facebook.com/{username}"
    return await facebook_posts_by_profile(profile_url, limit, timeout)


__all__ = [
    # SDK availability
    "brightdata_sdk_available",
    "brightdata_facebook_available",
    "get_brightdata_client",
    "get_brightdata_sync_client",
    # Dataset IDs
    "FACEBOOK_DATASETS",
    # Data structures
    "FacebookPost",
    "FacebookComment",
    "FacebookReel",
    "FacebookGroupPost",
    "FacebookProfile",
    "FacebookEvent",
    # API client
    "FacebookAPI",
    # Convenience functions
    "facebook_posts_by_profile",
    "facebook_posts_by_group",
    "facebook_post",
    "facebook_comments",
    "facebook_reels",
    "facebook_profile",
    "facebook_profiles",
    "facebook_event",
    "facebook_events",
    "facebook_posts_by_username",
]
