"""
SOCIALITE LinkedIn URL Output Handler

Creates C1 graph nodes for LinkedIn URLs with proper embedded edges.
Pushes to cymonides-1 with VERIFIED/UNVERIFIED status.

Legend Code: 105 (linkedin_url)
"""

import re
from typing import Optional

try:
    from .url_base import UrlOutputHandler
except ImportError:
    from url_base import UrlOutputHandler


class PersonLinkedInUrlOutputHandler(UrlOutputHandler):
    """
    Handles LinkedIn person profile URL output with C1-compliant schema.

    Supported URL patterns:
    - linkedin.com/in/username
    - linkedin.com/pub/name/xx/xxx/xxx
    """

    @property
    def platform(self) -> str:
        return "linkedin"

    @property
    def _code(self) -> int:
        return 105

    def extract_username(self, url: str) -> Optional[str]:
        """Extract username/slug from LinkedIn URL."""
        patterns = [
            r'linkedin\.com/in/([a-zA-Z0-9_-]+)',
            r'linkedin\.com/pub/([^/]+)',
        ]

        url_lower = url.lower()

        exclude = ['/company/', '/jobs/', '/school/', '/groups/', '/pulse/', '/learning/', '/sales/', '/talent/']
        for ex in exclude:
            if ex in url_lower:
                return None

        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                return match.group(1)

        return None


class CompanyLinkedInUrlOutputHandler(UrlOutputHandler):
    """Handles LinkedIn company URL output with C1-compliant schema."""

    @property
    def platform(self) -> str:
        return "linkedin"

    @property
    def _code(self) -> int:
        return 105

    def extract_username(self, url: str) -> Optional[str]:
        """Extract company slug from LinkedIn URL."""
        pattern = r'linkedin\.com/company/([a-zA-Z0-9_-]+)'
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return f"company:{match.group(1)}"
        return None


__all__ = ['PersonLinkedInUrlOutputHandler', 'CompanyLinkedInUrlOutputHandler']
