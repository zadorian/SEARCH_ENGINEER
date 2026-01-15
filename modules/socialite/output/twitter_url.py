"""
SOCIALITE Twitter/X URL Output Handler

Creates C1 graph nodes for Twitter/X URLs with proper embedded edges.
Pushes to cymonides-1 with VERIFIED/UNVERIFIED status.

Legend Code: 103 (twitter_url)
"""

import re
from typing import Optional

try:
    from .url_base import UrlOutputHandler
except ImportError:
    from url_base import UrlOutputHandler


class TwitterUrlOutputHandler(UrlOutputHandler):
    """
    Handles Twitter/X URL output with C1-compliant schema.

    Supported URL patterns:
    - twitter.com/username
    - x.com/username
    - twitter.com/username/status/123 (tweet)
    """

    @property
    def platform(self) -> str:
        return "twitter"

    @property
    def _code(self) -> int:
        return 103

    def extract_username(self, url: str) -> Optional[str]:
        """Extract username from Twitter/X URL."""
        patterns = [
            # Profile: twitter.com/username or x.com/username
            r'(?:twitter|x)\.com/([a-zA-Z0-9_]+)(?:[/?]|$)',
        ]

        url_lower = url.lower()

        # Filter out non-profile URLs
        exclude = ['i/', 'intent/', 'search', 'explore', 'home', 'notifications', 'messages', 'settings', 'tos', 'privacy']
        for ex in exclude:
            if f'/{ex}' in url_lower or url_lower.endswith(f'/{ex}'):
                return None

        # Handle status/tweet URLs - extract username before /status/
        status_match = re.search(r'(?:twitter|x)\.com/([a-zA-Z0-9_]+)/status/(\d+)', url, re.IGNORECASE)
        if status_match:
            return status_match.group(1)

        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                username = match.group(1)
                # Filter out reserved paths
                reserved = ['i', 'intent', 'search', 'explore', 'home', 'notifications', 'messages', 'settings', 'tos', 'privacy', 'about']
                if username.lower() not in reserved:
                    return username

        return None


__all__ = ['TwitterUrlOutputHandler']
