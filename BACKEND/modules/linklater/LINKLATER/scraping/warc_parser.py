"""
WARC Parser - DEPRECATED: Import from core instead.

This file is kept for backwards compatibility.
New code should import from: LINKLATER.core.parsers
"""

# Re-export from canonical location
from ..core.parsers import WARCParser, html_to_markdown

__all__ = ["WARCParser", "html_to_markdown"]
