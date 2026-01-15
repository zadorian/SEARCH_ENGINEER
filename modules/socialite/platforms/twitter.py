#!/usr/bin/env python3
"""
Twitter/X search functionality.

Provides URL generators for Twitter/X social media searches.
No scraping; complies with ToS by generating direct search URLs.
"""

from typing import Optional
from urllib.parse import quote


def _twitter_quote(query: str) -> str:
    """Quote a query for Twitter/X URLs"""
    return quote(query)


def twitter_search(query: str) -> str:
    """General Twitter/X search"""
    return f"https://x.com/search?q={_twitter_quote(query)}&f=live"


def twitter_from_user(username: str, query: str = "") -> str:
    """Tweets from a specific user (outgoing)"""
    search_query = f"from:{username}"
    if query:
        search_query += f" {query}"
    return f"https://x.com/search?q={_twitter_quote(search_query)}&f=live"


def twitter_to_user(username: str, query: str = "") -> str:
    """Tweets to a specific user (incoming/mentions)"""
    search_query = f"to:{username}"
    if query:
        search_query += f" {query}"
    return f"https://x.com/search?q={_twitter_quote(search_query)}&f=live"


def twitter_replies_from_user(username: str) -> str:
    """Replies from a specific user"""
    return f"https://x.com/search?q={_twitter_quote(f'from:{username} filter:replies')}&src=typed_query&f=live"


def twitter_followers(username: str) -> str:
    """User's followers list"""
    return f"https://x.com/{username}/followers"


def twitter_following(username: str) -> str:
    """User's following list"""
    return f"https://x.com/{username}/following"


def twitter_profile(username: str) -> str:
    """Direct link to user profile"""
    return f"https://x.com/{username}"


def twitter_from_user_date_range(username: str, since: str, until: str, query: str = "") -> str:
    """Tweets from a user within a date range (YYYY-MM-DD format)"""
    search_query = f"from:{username}"
    if query:
        search_query += f" {query}"
    search_query += f" since:{since} until:{until}"
    return f"https://x.com/search?q={_twitter_quote(search_query)}&src=typd&f=live"


def twitter_to_user_date_range(username: str, since: str, until: str, query: str = "") -> str:
    """Tweets to a user within a date range (YYYY-MM-DD format)"""
    search_query = f"to:{username}"
    if query:
        search_query += f" {query}"
    search_query += f" since:{since} until:{until}"
    return f"https://x.com/search?q={_twitter_quote(search_query)}&src=typd&f=live"


def twitter_outlinks(username: str, query: str = "") -> str:
    """Tweets from a user that contain links (outlinks)"""
    search_query = f"from:{username} filter:links"
    if query:
        search_query += f" {query}"
    return f"https://x.com/search?q={_twitter_quote(search_query)}&src=typed_query&f=live"


def twitter_historic_google(username: str, include_status: bool = False) -> str:
    """Search historic Twitter content via Google (includes deleted/archived tweets)"""
    if include_status:
        # Search for specific status updates (individual tweets)
        site_query = f"site:twitter.com/{username}/status/"
    else:
        # Search for all content from user's profile
        site_query = f"site:twitter.com/{username}"
    return f"https://www.google.com/search?q={quote(site_query)}"


def twitter_historic_google_with_query(username: str, query: str, include_status: bool = False) -> str:
    """Search historic Twitter content via Google with additional search terms"""
    if include_status:
        site_query = f"site:twitter.com/{username}/status/ {query}"
    else:
        site_query = f"site:twitter.com/{username} {query}"
    return f"https://www.google.com/search?q={quote(site_query)}"


def twitter_find_by_real_name(real_name: str) -> str:
    """Search for Twitter profiles by real name (returns potential usernames)"""
    # Search Twitter profiles for the real name
    search_query = f'site:twitter.com "{real_name}" -inurl:status'
    return f"https://www.google.com/search?q={quote(search_query)}"


def twitter_find_by_real_name_x(real_name: str) -> str:
    """Search for X.com profiles by real name using current domain"""
    # Search X.com profiles for the real name
    search_query = f'site:x.com "{real_name}" -inurl:status'
    return f"https://www.google.com/search?q={quote(search_query)}"


def twitter_find_verified(real_name: str) -> str:
    """Search for verified Twitter accounts by real name"""
    # Look for profiles with verification patterns
    search_query = f'site:twitter.com "{real_name}" ("verified account" OR "blue checkmark" OR "official")'
    return f"https://www.google.com/search?q={quote(search_query)}"


# Utility function
def extract_twitter_username(query: str) -> Optional[str]:
    """Try to extract a Twitter username from the query"""
    import re
    # Look for @username pattern
    match = re.search(r'@([A-Za-z0-9_]+)', query)
    if match:
        return match.group(1)
    # Look for u:username pattern
    match = re.search(r'u:([A-Za-z0-9_]+)', query)
    if match:
        return match.group(1)
    # Look for username:username pattern
    match = re.search(r'username:([A-Za-z0-9_]+)', query)
    if match:
        return match.group(1)
    # Look for common patterns like "username zadory" or just "zadory"
    words = query.split()
    if len(words) == 1 and re.match(r'^[A-Za-z0-9_]+$', words[0]):
        return words[0]
    return None
