"""
LINKLATER Core - Shared Utilities

Centralized utilities used across web, tor, and historical scrapers.

Consolidates duplicate code:
- WARCParser: WARC record parsing (was in 2 locations)
- StorageBackend: Pluggable crawler state storage
- html_to_markdown: HTML to markdown conversion

Usage:
    from modules.linklater.core import WARCParser, html_to_markdown
    from modules.linklater.core.storage import MemoryStorage, SQLiteStorage
"""

from .parsers import WARCParser, html_to_markdown
from .storage import (
    StorageBackend,
    MemoryStorage,
    SQLiteStorage,
    RedisStorage,
)

__all__ = [
    # Parsers
    "WARCParser",
    "html_to_markdown",
    # Storage
    "StorageBackend",
    "MemoryStorage",
    "SQLiteStorage",
    "RedisStorage",
]
