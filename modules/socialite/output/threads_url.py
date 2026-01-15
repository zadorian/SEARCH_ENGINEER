"""
SOCIALITE Threads URL Output Handler

Creates C1 graph nodes for Threads URLs with proper embedded edges.
Pushes to cymonides-1 with VERIFIED/UNVERIFIED status.

Legend Code: 104 (threads_url)
"""

import re
from typing import Optional

try:
    from .url_base import UrlOutputHandler
except ImportError:
    from url_base import UrlOutputHandler


class ThreadsUrlOutputHandler(UrlOutputHandler):
    """
    Handles Threads URL output with C1-compliant schema.

    Supported URL patterns:
    - threads.net/@username
    - threads.net/username
    """

    @property
    def platform(self) -> str:
        return "threads"

    @property
    def _code(self) -> int:
        return 104

    def extract_username(self, url: str) -> Optional[str]:
        """Extract username from Threads URL."""
        patterns = [
            # Profile with @: threads.net/@username
            r'threads\.net/@([a-zA-Z0-9_.]+)',
            # Profile without @: threads.net/username
            r'threads\.net/([a-zA-Z0-9_.]+)(?:[/?]|$)',
        ]

        url_lower = url.lower()

        # Filter out non-profile URLs
        exclude = ['post/', 'search', 'explore', 'settings', 'about', 'legal']
        for ex in exclude:
            if f'/{ex}' in url_lower:
                return None

        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                username = match.group(1)
                # Filter out reserved usernames
                reserved = ['search', 'explore', 'settings', 'about', 'legal']
                if username.lower() not in reserved:
                    return username

        return None


__all__ = ['ThreadsUrlOutputHandler']
