#!/usr/bin/env python3
"""
Instagram search functionality.

Provides URL generators for Instagram profiles and search.
No scraping; complies with ToS by generating direct profile URLs.
"""

from urllib.parse import quote_plus


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
