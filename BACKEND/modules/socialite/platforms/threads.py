#!/usr/bin/env python3
"""
Threads (Meta) search functionality.

Provides URL generators for Threads profiles (Meta's Twitter alternative).
No scraping; complies with ToS by generating direct profile URLs.
"""


def threads_profile(username: str) -> str:
    """Direct link to Threads profile"""
    return f"https://www.threads.net/@{username}"
