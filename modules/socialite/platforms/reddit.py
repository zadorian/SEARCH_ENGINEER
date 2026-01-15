#!/usr/bin/env python3
"""
REDDIT - User scraping via Apify.

Actor: cgizCCmpI9tsJFexd
Cost: $0.004 per result (~$4 per 1,000)

Scrapes Reddit user data:
- Posts (submissions)
- Comments
- Profile metadata
- Karma scores
- Media links

Usage:
    posts = scrape_user_posts("Mark_Ruffalo", limit=100)
    comments = scrape_user_comments("spez", sort="top", time="year")
    profile = scrape_user_profile("GovSchwarzenegger")
"""

import os
import logging
from typing import Optional, List, Dict, Any, Literal
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_TOKEN")
REDDIT_ACTOR_ID = "cgizCCmpI9tsJFexd"

SCRAPE_TYPES = ["posts", "comments", "profile"]
SORT_OPTIONS = ["new", "top", "hot"]
TIME_OPTIONS = ["hour", "day", "week", "month", "year", "all"]


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class RedditPost:
    """Reddit post/submission."""
    post_id: str = ""
    title: str = ""
    selftext: str = ""
    author: str = ""
    subreddit: str = ""
    subreddit_subscribers: int = 0
    score: int = 0
    upvote_ratio: float = 0.0
    num_comments: int = 0
    created_utc: Optional[datetime] = None
    url: str = ""
    permalink: str = ""
    is_video: bool = False
    is_self: bool = False
    over_18: bool = False
    stickied: bool = False
    awards: List[str] = field(default_factory=list)
    media_url: str = ""
    thumbnail: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "RedditPost":
        """Create from Apify actor output."""
        created = None
        if data.get("created_utc"):
            try:
                created = datetime.utcfromtimestamp(data["created_utc"])
            except (ValueError, TypeError):
                pass

        return cls(
            post_id=data.get("id", "") or data.get("name", ""),
            title=data.get("title", ""),
            selftext=data.get("selftext", ""),
            author=data.get("author", ""),
            subreddit=data.get("subreddit", ""),
            subreddit_subscribers=data.get("subreddit_subscribers", 0) or 0,
            score=data.get("score", 0) or 0,
            upvote_ratio=data.get("upvote_ratio", 0.0) or 0.0,
            num_comments=data.get("num_comments", 0) or 0,
            created_utc=created,
            url=data.get("url", ""),
            permalink=data.get("permalink", ""),
            is_video=data.get("is_video", False),
            is_self=data.get("is_self", False),
            over_18=data.get("over_18", False),
            stickied=data.get("stickied", False),
            awards=[a.get("name", "") for a in data.get("all_awardings", [])] if data.get("all_awardings") else [],
            media_url=data.get("url_overridden_by_dest", "") or data.get("media_url", ""),
            thumbnail=data.get("thumbnail", ""),
            raw=data,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "post_id": self.post_id,
            "title": self.title,
            "author": self.author,
            "subreddit": self.subreddit,
            "score": self.score,
            "upvote_ratio": self.upvote_ratio,
            "num_comments": self.num_comments,
            "created_utc": self.created_utc.isoformat() if self.created_utc else None,
            "url": self.url,
            "is_video": self.is_video,
            "over_18": self.over_18,
        }


@dataclass
class RedditComment:
    """Reddit comment."""
    comment_id: str = ""
    body: str = ""
    author: str = ""
    subreddit: str = ""
    score: int = 0
    created_utc: Optional[datetime] = None
    permalink: str = ""
    link_title: str = ""
    link_id: str = ""
    parent_id: str = ""
    controversiality: int = 0
    is_submitter: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "RedditComment":
        """Create from Apify actor output."""
        created = None
        if data.get("created_utc"):
            try:
                created = datetime.utcfromtimestamp(data["created_utc"])
            except (ValueError, TypeError):
                pass

        return cls(
            comment_id=data.get("id", "") or data.get("name", ""),
            body=data.get("body", ""),
            author=data.get("author", ""),
            subreddit=data.get("subreddit", ""),
            score=data.get("score", 0) or 0,
            created_utc=created,
            permalink=data.get("permalink", ""),
            link_title=data.get("link_title", ""),
            link_id=data.get("link_id", ""),
            parent_id=data.get("parent_id", ""),
            controversiality=data.get("controversiality", 0) or 0,
            is_submitter=data.get("is_submitter", False),
            raw=data,
        )


@dataclass
class RedditProfile:
    """Reddit user profile."""
    username: str = ""
    user_id: str = ""
    created_utc: Optional[datetime] = None
    link_karma: int = 0
    comment_karma: int = 0
    total_karma: int = 0
    is_gold: bool = False
    is_mod: bool = False
    verified: bool = False
    has_verified_email: bool = False
    icon_img: str = ""
    banner_img: str = ""
    description: str = ""
    subreddit_subscribers: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "RedditProfile":
        """Create from Apify actor output."""
        created = None
        if data.get("created_utc"):
            try:
                created = datetime.utcfromtimestamp(data["created_utc"])
            except (ValueError, TypeError):
                pass

        return cls(
            username=data.get("name", "") or data.get("username", ""),
            user_id=data.get("id", ""),
            created_utc=created,
            link_karma=data.get("link_karma", 0) or 0,
            comment_karma=data.get("comment_karma", 0) or 0,
            total_karma=data.get("total_karma", 0) or data.get("link_karma", 0) + data.get("comment_karma", 0),
            is_gold=data.get("is_gold", False),
            is_mod=data.get("is_mod", False),
            verified=data.get("verified", False),
            has_verified_email=data.get("has_verified_email", False),
            icon_img=data.get("icon_img", "") or data.get("snoovatar_img", ""),
            banner_img=data.get("subreddit", {}).get("banner_img", "") if data.get("subreddit") else "",
            description=data.get("subreddit", {}).get("public_description", "") if data.get("subreddit") else "",
            subreddit_subscribers=data.get("subreddit", {}).get("subscribers", 0) if data.get("subreddit") else 0,
            raw=data,
        )


# =============================================================================
# SCRAPING FUNCTIONS
# =============================================================================

def _get_client():
    """Get Apify client."""
    if not APIFY_TOKEN:
        raise ValueError("APIFY_API_TOKEN or APIFY_TOKEN environment variable required")
    try:
        from apify_client import ApifyClient
        return ApifyClient(APIFY_TOKEN)
    except ImportError:
        raise ImportError("apify-client not installed. Run: pip install apify-client")


def _normalize_username(user: str) -> str:
    """Normalize username to URL format."""
    if user.startswith("http"):
        return user
    if user.startswith("u/"):
        user = user[2:]
    if user.startswith("/u/"):
        user = user[3:]
    return f"https://www.reddit.com/user/{user}"


def scrape_user_posts(
    username: str,
    *,
    limit: int = 100,
    sort: Literal["new", "top", "hot"] = "new",
    time: Literal["hour", "day", "week", "month", "year", "all"] = "all",
) -> List[RedditPost]:
    """
    Scrape a Reddit user's posts/submissions.

    Args:
        username: Reddit username or profile URL
        limit: Maximum posts to fetch (default 100)
        sort: Sort order (new, top, hot)
        time: Time filter (hour, day, week, month, year, all)

    Returns:
        List of RedditPost objects

    Example:
        posts = scrape_user_posts("Mark_Ruffalo", limit=50)
        posts = scrape_user_posts("spez", sort="top", time="year")
    """
    client = _get_client()

    run_input = {
        "user": _normalize_username(username),
        "scrapeType": "posts",
        "limit": str(limit),
        "sort": sort,
        "time": time,
        "proxy": {
            "useApifyProxy": True,
            "apifyProxyGroups": ["RESIDENTIAL"],
        },
        "maxRetries": 3,
        "timeout": 10,
    }

    try:
        run = client.actor(REDDIT_ACTOR_ID).call(run_input=run_input)
        results = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        return [RedditPost.from_apify(r) for r in results]
    except Exception as e:
        logger.error(f"Reddit posts scrape failed: {e}")
        return []


def scrape_user_comments(
    username: str,
    *,
    limit: int = 100,
    sort: Literal["new", "top", "hot"] = "new",
    time: Literal["hour", "day", "week", "month", "year", "all"] = "all",
) -> List[RedditComment]:
    """
    Scrape a Reddit user's comments.

    Args:
        username: Reddit username or profile URL
        limit: Maximum comments to fetch
        sort: Sort order
        time: Time filter

    Returns:
        List of RedditComment objects
    """
    client = _get_client()

    run_input = {
        "user": _normalize_username(username),
        "scrapeType": "comments",
        "limit": str(limit),
        "sort": sort,
        "time": time,
        "proxy": {
            "useApifyProxy": True,
            "apifyProxyGroups": ["RESIDENTIAL"],
        },
        "maxRetries": 3,
        "timeout": 10,
    }

    try:
        run = client.actor(REDDIT_ACTOR_ID).call(run_input=run_input)
        results = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        return [RedditComment.from_apify(r) for r in results]
    except Exception as e:
        logger.error(f"Reddit comments scrape failed: {e}")
        return []


def scrape_user_profile(username: str) -> Optional[RedditProfile]:
    """
    Scrape a Reddit user's profile metadata.

    Args:
        username: Reddit username or profile URL

    Returns:
        RedditProfile object or None
    """
    client = _get_client()

    run_input = {
        "user": _normalize_username(username),
        "scrapeType": "profile",
        "limit": "1",
        "proxy": {
            "useApifyProxy": True,
            "apifyProxyGroups": ["RESIDENTIAL"],
        },
        "maxRetries": 3,
        "timeout": 10,
    }

    try:
        run = client.actor(REDDIT_ACTOR_ID).call(run_input=run_input)
        results = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        if results:
            return RedditProfile.from_apify(results[0])
        return None
    except Exception as e:
        logger.error(f"Reddit profile scrape failed: {e}")
        return None


def scrape_user_full(
    username: str,
    *,
    posts_limit: int = 100,
    comments_limit: int = 100,
) -> Dict[str, Any]:
    """
    Scrape complete user data: profile, posts, and comments.

    Args:
        username: Reddit username
        posts_limit: Max posts
        comments_limit: Max comments

    Returns:
        Dict with profile, posts, comments
    """
    return {
        "profile": scrape_user_profile(username),
        "posts": scrape_user_posts(username, limit=posts_limit),
        "comments": scrape_user_comments(username, limit=comments_limit),
    }


# =============================================================================
# ANALYSIS HELPERS
# =============================================================================

def get_user_subreddits(username: str, limit: int = 100) -> Dict[str, int]:
    """
    Get subreddits a user is active in.

    Returns:
        Dict mapping subreddit -> post/comment count
    """
    posts = scrape_user_posts(username, limit=limit)
    comments = scrape_user_comments(username, limit=limit)

    subreddits: Dict[str, int] = {}
    for post in posts:
        subreddits[post.subreddit] = subreddits.get(post.subreddit, 0) + 1
    for comment in comments:
        subreddits[comment.subreddit] = subreddits.get(comment.subreddit, 0) + 1

    return dict(sorted(subreddits.items(), key=lambda x: x[1], reverse=True))


def get_user_top_posts(username: str, limit: int = 10) -> List[RedditPost]:
    """Get user's top posts by score."""
    posts = scrape_user_posts(username, sort="top", time="all", limit=limit)
    return sorted(posts, key=lambda p: p.score, reverse=True)[:limit]


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Data structures
    "RedditPost",
    "RedditComment",
    "RedditProfile",
    # Scraping functions
    "scrape_user_posts",
    "scrape_user_comments",
    "scrape_user_profile",
    "scrape_user_full",
    # Analysis
    "get_user_subreddits",
    "get_user_top_posts",
    # Config
    "SCRAPE_TYPES",
    "SORT_OPTIONS",
    "TIME_OPTIONS",
]


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python reddit.py <username> [type] [limit]")
        print("\nTypes: posts, comments, profile, full")
        print("\nExamples:")
        print("  python reddit.py Mark_Ruffalo")
        print("  python reddit.py spez posts 50")
        print("  python reddit.py GovSchwarzenegger full")
        sys.exit(1)

    username = sys.argv[1]
    scrape_type = sys.argv[2] if len(sys.argv) > 2 else "posts"
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 50

    print(f"📱 Scraping Reddit user: {username}")

    if scrape_type == "profile":
        profile = scrape_user_profile(username)
        if profile:
            print(f"\n👤 {profile.username}")
            print(f"   Karma: {profile.total_karma:,} (link: {profile.link_karma:,}, comment: {profile.comment_karma:,})")
            if profile.created_utc:
                print(f"   Created: {profile.created_utc.strftime('%Y-%m-%d')}")
    elif scrape_type == "comments":
        comments = scrape_user_comments(username, limit=limit)
        print(f"\n💬 Found {len(comments)} comments")
        for c in comments[:5]:
            print(f"\n  r/{c.subreddit} ({c.score} pts)")
            print(f"  {c.body[:100]}...")
    elif scrape_type == "full":
        data = scrape_user_full(username, posts_limit=limit, comments_limit=limit)
        print(f"\n📊 Full profile scraped:")
        print(f"   Posts: {len(data['posts'])}")
        print(f"   Comments: {len(data['comments'])}")
    else:  # posts
        posts = scrape_user_posts(username, limit=limit)
        print(f"\n📝 Found {len(posts)} posts")
        for p in posts[:5]:
            print(f"\n  r/{p.subreddit} ({p.score} pts, {p.num_comments} comments)")
            print(f"  {p.title[:80]}")
