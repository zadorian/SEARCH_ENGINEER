#!/usr/bin/env python3
"""
Threads (Meta) profile scraping via Apify.

Uses Apify actor kJdK90pa2hhYYrCK5 for Threads profile data extraction.
"""

import os
from typing import Optional, List, Dict, Any
from apify_client import ApifyClient


APIFY_TOKEN = os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_TOKEN")
THREADS_ACTOR_ID = "kJdK90pa2hhYYrCK5"


def get_client() -> ApifyClient:
    """Get Apify client with API token."""
    if not APIFY_TOKEN:
        raise ValueError("APIFY_API_TOKEN or APIFY_TOKEN environment variable required")
    return ApifyClient(APIFY_TOKEN)


def threads_profile_url(username: str) -> str:
    """Direct link to Threads profile."""
    username = username.lstrip("@")
    return f"https://www.threads.net/@{username}"


def scrape_profile(username: str) -> Dict[str, Any]:
    """
    Scrape a single Threads profile.

    Args:
        username: Threads username (with or without @)

    Returns:
        Profile data dict with bio, followers, posts, etc.
    """
    username = username.lstrip("@")
    client = get_client()

    run_input = {"usernames": [username]}
    run = client.actor(THREADS_ACTOR_ID).call(run_input=run_input)

    results = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    return results[0] if results else {}


def scrape_profiles(usernames: List[str]) -> List[Dict[str, Any]]:
    """
    Scrape multiple Threads profiles.

    Args:
        usernames: List of Threads usernames

    Returns:
        List of profile data dicts
    """
    usernames = [u.lstrip("@") for u in usernames]
    client = get_client()

    run_input = {"usernames": usernames}
    run = client.actor(THREADS_ACTOR_ID).call(run_input=run_input)

    return list(client.dataset(run["defaultDatasetId"]).iterate_items())


def scrape_profile_posts(username: str, max_posts: int = 20) -> Dict[str, Any]:
    """
    Scrape profile with posts.

    Args:
        username: Threads username
        max_posts: Maximum number of posts to retrieve

    Returns:
        Profile data with posts array
    """
    username = username.lstrip("@")
    client = get_client()

    run_input = {
        "usernames": [username],
        "maxPosts": max_posts
    }
    run = client.actor(THREADS_ACTOR_ID).call(run_input=run_input)

    results = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    return results[0] if results else {}


# Convenience aliases
get_profile = scrape_profile
get_profiles = scrape_profiles


__all__ = [
    "threads_profile_url",
    "scrape_profile",
    "scrape_profiles",
    "scrape_profile_posts",
    "get_profile",
    "get_profiles",
]


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python threads.py <username> [username2 ...]")
        sys.exit(1)

    usernames = sys.argv[1:]

    if len(usernames) == 1:
        result = scrape_profile(usernames[0])
    else:
        result = scrape_profiles(usernames)

    print(json.dumps(result, indent=2, default=str))
