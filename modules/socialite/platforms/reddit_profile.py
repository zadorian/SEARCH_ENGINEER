#!/usr/bin/env python3
"""
REDDIT PROFILE - Reddit User Profile Scraper via Apify.

Actor: ILMCNaVwoOZyWEsrk
Scrapes Reddit user profiles, posts, and comments.

Usage:
    from socialite.platforms.reddit_profile import (
        scrape_user,
        scrape_users,
        RedditUser,
        RedditPost,
    )

    # Scrape single user
    user = scrape_user("spez")

    # Scrape from URL
    user = scrape_user("https://www.reddit.com/user/spez")
"""

import os
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_TOKEN")
REDDIT_PROFILE_ACTOR_ID = "ILMCNaVwoOZyWEsrk"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class RedditPost:
    """Reddit post or comment."""
    # Post identification
    id: str = ""
    url: str = ""
    permalink: str = ""

    # Content
    title: str = ""
    selftext: str = ""
    subreddit: str = ""

    # Author
    author: str = ""

    # Engagement
    score: int = 0
    upvote_ratio: float = 0.0
    num_comments: int = 0

    # Media
    is_video: bool = False
    thumbnail: str = ""
    media_url: str = ""

    # Metadata
    created_utc: Optional[int] = None
    over_18: bool = False

    # Awards
    awards: List[Dict[str, Any]] = field(default_factory=list)

    # Raw
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "RedditPost":
        """Create from Apify actor output."""
        return cls(
            id=data.get("id", "") or data.get("name", ""),
            url=data.get("url", ""),
            permalink=data.get("permalink", ""),
            title=data.get("title", ""),
            selftext=data.get("selftext", "") or data.get("body", ""),
            subreddit=data.get("subreddit", "") or data.get("subreddit_name_prefixed", ""),
            author=data.get("author", ""),
            score=int(data.get("score", 0) or 0),
            upvote_ratio=float(data.get("upvote_ratio", 0.0) or 0.0),
            num_comments=int(data.get("num_comments", 0) or 0),
            is_video=data.get("is_video", False),
            thumbnail=data.get("thumbnail", ""),
            media_url=data.get("url_overridden_by_dest", "") or data.get("media_url", ""),
            created_utc=int(data.get("created_utc", 0)) if data.get("created_utc") else None,
            over_18=data.get("over_18", False),
            awards=data.get("all_awardings", []) or data.get("awards", []) or [],
            raw=data,
        )

    @property
    def created_datetime(self) -> Optional[datetime]:
        """Convert created_utc to datetime."""
        if self.created_utc:
            return datetime.utcfromtimestamp(self.created_utc)
        return None

    @property
    def full_url(self) -> str:
        """Get full Reddit URL."""
        if self.url and self.url.startswith("http"):
            return self.url
        if self.permalink:
            return f"https://www.reddit.com{self.permalink}"
        return ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "selftext": self.selftext[:500] if self.selftext else "",
            "subreddit": self.subreddit,
            "author": self.author,
            "score": self.score,
            "num_comments": self.num_comments,
            "url": self.full_url,
            "is_video": self.is_video,
            "created_utc": self.created_utc,
            "over_18": self.over_18,
        }


@dataclass
class RedditUser:
    """Reddit user profile."""
    # User identification
    username: str = ""
    user_url: str = ""

    # Posts and comments
    posts: List[RedditPost] = field(default_factory=list)

    # Statistics (derived from posts)
    total_posts: int = 0
    total_score: int = 0
    most_active_subreddits: List[str] = field(default_factory=list)

    # Raw
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_posts(cls, username: str, posts: List[RedditPost]) -> "RedditUser":
        """Create from list of posts."""
        # Calculate statistics
        total_score = sum(p.score for p in posts)

        # Find most active subreddits
        subreddit_counts = {}
        for post in posts:
            if post.subreddit:
                sr = post.subreddit.replace("r/", "")
                subreddit_counts[sr] = subreddit_counts.get(sr, 0) + 1

        most_active = sorted(subreddit_counts.keys(), key=lambda x: subreddit_counts[x], reverse=True)[:10]

        return cls(
            username=username,
            user_url=f"https://www.reddit.com/user/{username}",
            posts=posts,
            total_posts=len(posts),
            total_score=total_score,
            most_active_subreddits=most_active,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "username": self.username,
            "user_url": self.user_url,
            "total_posts": self.total_posts,
            "total_score": self.total_score,
            "most_active_subreddits": self.most_active_subreddits,
            "posts_sample": [p.to_dict() for p in self.posts[:5]],
        }


# =============================================================================
# I/O LEGEND CODES
# =============================================================================

"""
Reddit Profile Scraper I/O Legend:

INPUTS:
- startUrls         : Reddit user URLs (e.g., "https://www.reddit.com/user/spez")
- maxItems          : Maximum posts to return
- skipUserPosts     : Skip user posts (comments only)
- debugMode         : Enable debug output

OUTPUTS:
- title             : Post title
- selftext          : Post body text
- subreddit         : Subreddit name
- author            : Post author username
- score             : Post score (upvotes - downvotes)
- upvote_ratio      : Ratio of upvotes
- num_comments      : Number of comments
- created_utc       : Unix timestamp of creation
- url               : Post/media URL
- is_video          : Whether post is a video
- over_18           : NSFW flag
- all_awardings     : Awards received

RELATIONSHIPS:
- author          -> person_username (Reddit)
- subreddit       -> community
- url             -> social_profile (Reddit)
"""


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


def _normalize_user_url(user_input: str) -> str:
    """Convert username or URL to proper Reddit user URL."""
    if user_input.startswith("http"):
        return user_input
    # Remove leading u/ or /u/ if present
    username = user_input.lstrip("/").lstrip("u/").lstrip("user/")
    return f"https://www.reddit.com/user/{username}"


def scrape_user(
    user: str,
    *,
    max_items: int = 50,
    skip_posts: bool = False,
    debug: bool = False,
) -> Optional[RedditUser]:
    """
    Scrape a Reddit user's profile and posts.

    Args:
        user: Reddit username or user URL
        max_items: Maximum posts to return
        skip_posts: Only get comments (skip posts)
        debug: Enable debug mode

    Returns:
        RedditUser or None

    Example:
        user = scrape_user("spez")
        if user:
            print(f"{user.username}: {user.total_posts} posts, {user.total_score} total score")
    """
    results = scrape_users([user], max_items=max_items, skip_posts=skip_posts, debug=debug)
    return results[0] if results else None


def scrape_users(
    users: List[str],
    *,
    max_items: int = 50,
    skip_posts: bool = False,
    debug: bool = False,
) -> List[RedditUser]:
    """
    Scrape multiple Reddit user profiles.

    Args:
        users: List of Reddit usernames or URLs
        max_items: Maximum posts per user
        skip_posts: Only get comments
        debug: Enable debug mode

    Returns:
        List of RedditUser objects

    Example:
        users = scrape_users(["spez", "kn0thing"])
    """
    client = _get_client()

    # Normalize URLs
    start_urls = [_normalize_user_url(u) for u in users]

    run_input = {
        "startUrls": start_urls,
        "maxItems": max_items,
        "skipUserPosts": skip_posts,
        "debugMode": debug,
    }

    try:
        logger.info(f"Scraping {len(users)} Reddit users")
        run = client.actor(REDDIT_PROFILE_ACTOR_ID).call(run_input=run_input)
        results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

        # Group posts by author
        posts_by_user = {}
        for item in results:
            author = item.get("author", "unknown")
            if author not in posts_by_user:
                posts_by_user[author] = []
            posts_by_user[author].append(RedditPost.from_apify(item))

        # Create RedditUser objects
        reddit_users = []
        for username, posts in posts_by_user.items():
            reddit_users.append(RedditUser.from_posts(username, posts))

        return reddit_users
    except Exception as e:
        logger.error(f"Reddit user scrape failed: {e}")
        return []


def get_user_posts(
    username: str,
    max_items: int = 50,
) -> List[RedditPost]:
    """
    Get posts from a Reddit user.

    Args:
        username: Reddit username
        max_items: Maximum posts

    Returns:
        List of RedditPost objects
    """
    user = scrape_user(username, max_items=max_items)
    return user.posts if user else []


def get_user_stats(username: str) -> Dict[str, Any]:
    """
    Get statistics for a Reddit user.

    Args:
        username: Reddit username

    Returns:
        Dict with user statistics
    """
    user = scrape_user(username, max_items=100)
    if not user:
        return {"username": username, "error": "User not found"}

    return {
        "username": user.username,
        "url": user.user_url,
        "total_posts": user.total_posts,
        "total_score": user.total_score,
        "avg_score": user.total_score // user.total_posts if user.total_posts > 0 else 0,
        "most_active_subreddits": user.most_active_subreddits,
        "posts_with_video": sum(1 for p in user.posts if p.is_video),
        "nsfw_posts": sum(1 for p in user.posts if p.over_18),
    }


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Data structures
    "RedditUser",
    "RedditPost",
    # Scraping functions
    "scrape_user",
    "scrape_users",
    "get_user_posts",
    "get_user_stats",
    # Config
    "REDDIT_PROFILE_ACTOR_ID",
]


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python reddit_profile.py <username_or_url> [max_items]")
        print("\nExamples:")
        print("  python reddit_profile.py spez")
        print("  python reddit_profile.py https://www.reddit.com/user/spez")
        print("  python reddit_profile.py spez 100")
        sys.exit(1)

    user_input = sys.argv[1]
    max_items = int(sys.argv[2]) if len(sys.argv) > 2 else 50

    print(f"🔍 Scraping Reddit user: {user_input}")
    print(f"   Max items: {max_items}")

    user = scrape_user(user_input, max_items=max_items)

    if user:
        print(f"\n📋 u/{user.username}")
        print(f"   URL: {user.user_url}")
        print(f"   Total Posts: {user.total_posts}")
        print(f"   Total Score: {user.total_score:,}")
        if user.most_active_subreddits:
            print(f"   Most Active Subreddits: {', '.join(user.most_active_subreddits[:5])}")

        if user.posts:
            print(f"\n   Recent Posts ({len(user.posts)}):")
            for i, post in enumerate(user.posts[:5], 1):
                title = post.title[:60] + "..." if len(post.title) > 60 else post.title
                print(f"     {i}. [{post.subreddit}] {title}")
                print(f"        Score: {post.score}, Comments: {post.num_comments}")
    else:
        print("❌ User not found")
