"""
SOCIALITE Facebook URL Output Handler

Creates C1 graph nodes for Facebook URLs with proper embedded edges.
Pushes to cymonides-1 with VERIFIED/UNVERIFIED status.

Legend Code: 101 (facebook_url)
"""

import re
from typing import Optional

try:
    from .url_base import UrlOutputHandler
except ImportError:
    from url_base import UrlOutputHandler


class FacebookUrlOutputHandler(UrlOutputHandler):
    """
    Handles Facebook URL output with C1-compliant schema.

    Supported URL patterns:
    - facebook.com/username
    - facebook.com/profile.php?id=12345
    - facebook.com/people/Name/12345
    - fb.com/username
    """

    @property
    def platform(self) -> str:
        return "facebook"

    @property
    def _code(self) -> int:
        return 101

    def extract_username(self, url: str) -> Optional[str]:
        """Extract username or ID from Facebook URL."""
        patterns = [
            # Profile with username: facebook.com/johndoe
            r'(?:facebook|fb)\.com/([a-zA-Z0-9_.]+)(?:[/?]|$)',
            # Profile.php with ID: facebook.com/profile.php?id=12345
            r'profile\.php\?id=(\d+)',
            # People page: facebook.com/people/Name/12345
            r'/people/[^/]+/(\d+)',
            # Pages: facebook.com/pages/Name/12345
            r'/pages/[^/]+/(\d+)',
        ]

        url_lower = url.lower()

        # Filter out non-profile URLs
        exclude = ['watch', 'groups', 'events', 'marketplace', 'gaming', 'help', 'about', 'legal']
        for ex in exclude:
            if f'/{ex}' in url_lower or f'{ex}.' in url_lower:
                return None

        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                return match.group(1)

        return None


__all__ = ['FacebookUrlOutputHandler']
