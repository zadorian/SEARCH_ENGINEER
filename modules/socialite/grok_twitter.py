"""
Grok Twitter Bridge - Use Grok for Twitter/X data.

Grok has native access to Twitter/X data, making it the preferred
method for Twitter searches and profile lookups.
"""

import os
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


async def search_twitter_via_grok(
    query: str,
    username: Optional[str] = None,
    search_type: str = "posts"
) -> Dict[str, Any]:
    """
    Search Twitter/X using Grok's native access.

    Args:
        query: Search query
        username: Optional username filter
        search_type: "posts", "users", or "all"

    Returns:
        Dict with search results
    """
    try:
        from modules.ai_qa.brain import brain_query

        # Build search prompt
        if username:
            prompt = f"Search Twitter/X for tweets from @{username} about: {query}"
        else:
            prompt = f"Search Twitter/X for: {query}"

        if search_type == "users":
            prompt = f"Find Twitter/X accounts matching: {query}"

        # Call Grok with search enabled
        result = brain_query(
            prompt,
            model="grok-4",
            search_enabled=True
        )

        return {
            "query": query,
            "username": username,
            "search_type": search_type,
            "response": result,
            "source": "grok"
        }

    except Exception as e:
        logger.error(f"Grok Twitter search error: {e}")
        return {
            "query": query,
            "error": str(e),
            "source": "grok"
        }


async def get_twitter_profile_via_grok(username: str) -> Dict[str, Any]:
    """
    Get Twitter/X profile info using Grok.

    Args:
        username: Twitter username (without @)

    Returns:
        Dict with profile information
    """
    try:
        from modules.ai_qa.brain import brain_query

        prompt = f"""Get comprehensive information about the Twitter/X account @{username}.
Include:
- Display name
- Bio/description
- Follower count
- Following count
- Account creation date (if known)
- Verified status
- Recent notable tweets or activity
- Any notable associations or organizations"""

        result = brain_query(
            prompt,
            model="grok-4",
            search_enabled=True
        )

        return {
            "username": username,
            "profile_url": f"https://x.com/{username}",
            "data": result,
            "source": "grok"
        }

    except Exception as e:
        logger.error(f"Grok profile lookup error: {e}")
        return {
            "username": username,
            "error": str(e),
            "source": "grok"
        }


async def analyze_twitter_user_via_grok(username: str) -> Dict[str, Any]:
    """
    Deep analysis of a Twitter/X user using Grok.

    Args:
        username: Twitter username

    Returns:
        Dict with analysis results
    """
    try:
        from modules.ai_qa.brain import brain_query

        prompt = f"""Analyze the Twitter/X account @{username}:

1. PROFILE SUMMARY
   - Who is this person/organization?
   - What do they primarily post about?

2. ENGAGEMENT ANALYSIS
   - How active are they?
   - What kind of engagement do their posts get?

3. NETWORK ANALYSIS
   - Who do they frequently interact with?
   - What communities are they part of?

4. SENTIMENT ANALYSIS
   - What is the general tone of their posts?
   - How do others respond to them?

5. RED FLAGS (if any)
   - Controversial content
   - Bot-like behavior
   - Inauthentic activity patterns"""

        result = brain_query(
            prompt,
            model="grok-4",
            search_enabled=True
        )

        return {
            "username": username,
            "analysis": result,
            "source": "grok"
        }

    except Exception as e:
        logger.error(f"Grok analysis error: {e}")
        return {
            "username": username,
            "error": str(e),
            "source": "grok"
        }


__all__ = [
    "search_twitter_via_grok",
    "get_twitter_profile_via_grok",
    "analyze_twitter_user_via_grok"
]
