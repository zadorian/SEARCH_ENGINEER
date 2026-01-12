#!/usr/bin/env python3
"""
Facebook search functionality.

Provides URL generators for Facebook profiles and search.
No scraping; complies with ToS by generating direct URLs.
Facebook's search API is restricted, so we use Google for most searches.
"""

from urllib.parse import quote_plus, quote


def facebook_profile(username: str) -> str:
    """Direct link to Facebook profile"""
    return f"https://www.facebook.com/{username}"


def facebook_search(query: str) -> str:
    """Facebook search via Google (Facebook's search is locked down without auth)"""
    google_query = f"site:facebook.com {query}"
    return f"https://www.google.com/search?q={quote_plus(google_query)}"


def facebook_people(name: str) -> str:
    """Search Facebook for people with this name"""
    return f"https://www.facebook.com/search/people/?q={quote(name)}"


def facebook_pages(query: str) -> str:
    """Search Facebook pages"""
    return f"https://www.facebook.com/search/pages/?q={quote(query)}"


def facebook_groups(query: str) -> str:
    """Search Facebook groups"""
    return f"https://www.facebook.com/search/groups/?q={quote(query)}"
