"""
Common Crawl Configuration - Centralized CC Index Management

Provides dynamic fetching of the latest CC archive with caching.
All modules should import from here instead of hardcoding CC-MAIN-* strings.

Usage:
    from linklater.cc_config import get_latest_archive, CC_INDEX_BASE

    archive = await get_latest_archive()  # Returns "CC-MAIN-2025-47" (latest)
    # or
    archive = get_latest_archive_sync()   # Blocking version
"""

import asyncio
import time
import logging
from typing import Optional, List, Dict
from functools import lru_cache

import httpx

logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

CC_INDEX_BASE = "https://index.commoncrawl.org"
CC_DATA_BASE = "https://data.commoncrawl.org"
CC_COLLINFO_URL = f"{CC_INDEX_BASE}/collinfo.json"

# Default fallback if API is unavailable
DEFAULT_ARCHIVE = "CC-MAIN-2025-47"

# Cache settings
_CACHE_TTL_SECONDS = 3600  # 1 hour
_cached_latest_archive: Optional[str] = None
_cache_timestamp: float = 0.0
_archive_list_cache: Optional[List[Dict]] = None


# ============================================================================
# Async Functions
# ============================================================================

async def fetch_available_archives(timeout: int = 10) -> List[Dict]:
    """
    Fetch list of available CC archives from collinfo.json.

    Returns:
        List of archive metadata dicts, sorted by recency (newest first)

    Example response:
        [
            {"id": "CC-MAIN-2025-47", "name": "November 2025", ...},
            {"id": "CC-MAIN-2025-43", "name": "October 2025", ...},
            ...
        ]
    """
    global _archive_list_cache, _cache_timestamp

    # Return cached if fresh
    if _archive_list_cache and (time.time() - _cache_timestamp) < _CACHE_TTL_SECONDS:
        return _archive_list_cache

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(CC_COLLINFO_URL)
            response.raise_for_status()
            archives = response.json()

            # Cache the result
            _archive_list_cache = archives
            _cache_timestamp = time.time()

            logger.debug(f"Fetched {len(archives)} CC archives, latest: {archives[0]['id'] if archives else 'none'}")
            return archives

    except Exception as e:
        logger.warning(f"Failed to fetch CC archives: {e}, using cached/default")
        if _archive_list_cache:
            return _archive_list_cache
        return []


async def get_latest_archive(timeout: int = 10) -> str:
    """
    Get the latest available CC archive ID.

    Returns:
        Archive ID like "CC-MAIN-2025-47"

    Uses caching to avoid repeated API calls. Falls back to DEFAULT_ARCHIVE
    if the API is unavailable.

    Example:
        archive = await get_latest_archive()
        # Returns: "CC-MAIN-2025-47"
    """
    global _cached_latest_archive, _cache_timestamp

    # Return cached if fresh
    if _cached_latest_archive and (time.time() - _cache_timestamp) < _CACHE_TTL_SECONDS:
        return _cached_latest_archive

    archives = await fetch_available_archives(timeout)

    if archives:
        _cached_latest_archive = archives[0]["id"]
        return _cached_latest_archive

    logger.warning(f"No archives available, using default: {DEFAULT_ARCHIVE}")
    return DEFAULT_ARCHIVE


async def get_recent_archives(count: int = 5, timeout: int = 10) -> List[str]:
    """
    Get the N most recent CC archive IDs.

    Args:
        count: Number of archives to return
        timeout: Request timeout

    Returns:
        List of archive IDs like ["CC-MAIN-2025-47", "CC-MAIN-2025-43", ...]
    """
    archives = await fetch_available_archives(timeout)
    return [a["id"] for a in archives[:count]]


# ============================================================================
# Sync Functions (for non-async contexts)
# ============================================================================

def get_latest_archive_sync(timeout: int = 10) -> str:
    """
    Synchronous version of get_latest_archive().

    For use in non-async contexts. Creates event loop if needed.

    Returns:
        Archive ID like "CC-MAIN-2025-47"
    """
    global _cached_latest_archive, _cache_timestamp

    # Return cached if fresh
    if _cached_latest_archive and (time.time() - _cache_timestamp) < _CACHE_TTL_SECONDS:
        return _cached_latest_archive

    try:
        # Try to use existing event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Can't run sync in running loop, return cached/default
            return _cached_latest_archive or DEFAULT_ARCHIVE
        return loop.run_until_complete(get_latest_archive(timeout))
    except RuntimeError:
        # No event loop, create one
        return asyncio.run(get_latest_archive(timeout))


def get_default_archive() -> str:
    """
    Get default archive without API call.

    Use this when you need a fallback and don't want to make network requests.

    Returns:
        DEFAULT_ARCHIVE constant
    """
    return _cached_latest_archive or DEFAULT_ARCHIVE


# ============================================================================
# URL Builders
# ============================================================================

def build_index_url(archive: Optional[str] = None) -> str:
    """
    Build CC Index API URL for an archive.

    Args:
        archive: Archive ID (uses latest if None)

    Returns:
        URL like "https://index.commoncrawl.org/CC-MAIN-2025-47-index"
    """
    arch = archive or get_default_archive()
    return f"{CC_INDEX_BASE}/{arch}-index"


def build_data_url(path: str) -> str:
    """
    Build CC Data URL for a file path.

    Args:
        path: File path like "crawl-data/CC-MAIN-2025-47/..."

    Returns:
        Full URL like "https://data.commoncrawl.org/crawl-data/..."
    """
    if path.startswith("http"):
        return path
    return f"{CC_DATA_BASE}/{path.lstrip('/')}"


# ============================================================================
# Cache Management
# ============================================================================

def clear_cache():
    """Clear all cached archive data."""
    global _cached_latest_archive, _cache_timestamp, _archive_list_cache
    _cached_latest_archive = None
    _cache_timestamp = 0.0
    _archive_list_cache = None
    logger.debug("CC config cache cleared")


def set_cache_ttl(seconds: int):
    """Set cache TTL in seconds."""
    global _CACHE_TTL_SECONDS
    _CACHE_TTL_SECONDS = seconds


# ============================================================================
# Initialization
# ============================================================================

# Try to pre-populate cache on import (non-blocking)
def _init_cache():
    """Attempt to initialize cache in background."""
    try:
        loop = asyncio.get_event_loop()
        if not loop.is_running():
            # Don't block on import, just set default
            pass
    except RuntimeError:
        pass

_init_cache()
