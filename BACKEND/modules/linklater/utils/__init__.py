"""
LINKLATER Utilities

Common utility functions used across modules.
"""

from typing import Optional
from urllib.parse import urlparse, urljoin

def normalize_url(url: str) -> str:
    """Normalize URL for consistent comparison."""
    parsed = urlparse(url)
    # Remove trailing slashes, lowercase host
    host = parsed.netloc.lower()
    path = parsed.path.rstrip('/') or '/'
    return f"{parsed.scheme}://{host}{path}"


def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    parsed = urlparse(url)
    return parsed.netloc.lower()


def is_js_heavy(html: str) -> bool:
    """
    Detect if page is JS-heavy (needs browser rendering).

    Returns True if page has minimal content but heavy JS.
    """
    if not html:
        return False

    # Quick heuristics
    text_len = len(html)
    script_count = html.lower().count('<script')

    # If many scripts but little visible content
    if script_count > 5 and text_len < 5000:
        return True

    # React/Vue/Angular markers
    js_markers = ['__NEXT_DATA__', 'window.__INITIAL_STATE__', 'ng-app']
    for marker in js_markers:
        if marker in html:
            return True

    return False


__all__ = [
    "normalize_url",
    "extract_domain",
    "is_js_heavy",
]
