"""
SOCIALITE Instagram URL Output Handler

Creates C1 graph nodes for Instagram URLs with proper embedded edges.
Pushes to cymonides-1 with VERIFIED/UNVERIFIED status.

Legend Code: 102 (instagram_url)
"""

import re
from typing import Optional

try:
    from .url_base import UrlOutputHandler
except ImportError:
    from url_base import UrlOutputHandler


class InstagramUrlOutputHandler(UrlOutputHandler):
    """
    Handles Instagram URL output with C1-compliant schema.

    Supported URL patterns:
    - instagram.com/username
    - instagr.am/username
    - instagram.com/p/POSTID (post)
    - instagram.com/reel/REELID (reel)
    """

    @property
    def platform(self) -> str:
        return "instagram"

    @property
    def _code(self) -> int:
        return 102

    def extract_username(self, url: str) -> Optional[str]:
        """Extract username from Instagram URL."""
        patterns = [
            # Profile: instagram.com/username
            r'(?:instagram|instagr\.am)\.com/([a-zA-Z0-9_.]+)(?:[/?]|$)',
        ]

        url_lower = url.lower()

        # Filter out non-profile URLs
        exclude = ['p/', 'reel/', 'tv/', 'stories/', 'explore/', 'accounts/', 'about/', 'legal/']
        for ex in exclude:
            if ex in url_lower:
                # Return post/reel ID instead for those
                if ex in ['p/', 'reel/', 'tv/']:
                    match = re.search(rf'{ex}([a-zA-Z0-9_-]+)', url)
                    if match:
                        return f"post:{match.group(1)}"
                return None

        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                username = match.group(1)
                # Filter out reserved usernames
                reserved = ['explore', 'accounts', 'about', 'legal', 'api', 'developer']
                if username.lower() not in reserved:
                    return username

        return None


__all__ = ['InstagramUrlOutputHandler']
