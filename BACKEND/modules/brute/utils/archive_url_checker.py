#!/usr/bin/env python3
"""
Archive URL Checker - Validates and processes URLs from Archive.org and other archives
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, quote
import requests
from datetime import datetime

logger = logging.getLogger(__name__)


def process_archive_results(results: List[Dict], verify: bool = False, timeout: int = 5) -> List[Dict]:
    """
    Process and optionally verify Archive.org results.

    Args:
        results: List of archive search results
        verify: Whether to verify URLs are accessible (slower)
        timeout: Request timeout for verification

    Returns:
        List of processed results with availability status
    """
    processed = []

    for result in results:
        url = result.get("url", "")

        # Add metadata
        processed_result = {
            **result,
            "is_archive": is_archive_url(url),
            "archive_type": get_archive_type(url),
            "original_url": extract_original_url(url) if is_archive_url(url) else url,
        }

        # Optionally verify availability
        if verify:
            processed_result["is_available"] = check_url_available(url, timeout)
        else:
            processed_result["is_available"] = None

        processed.append(processed_result)

    return processed


def is_archive_url(url: str) -> bool:
    """Check if URL is from an archive service"""
    archive_domains = [
        "web.archive.org",
        "archive.org",
        "archive.is",
        "archive.today",
        "archive.ph",
        "archive.md",
        "webcache.googleusercontent.com",
        "cachedview.com",
    ]

    try:
        parsed = urlparse(url)
        return any(domain in parsed.netloc for domain in archive_domains)
    except Exception:
        return False


def get_archive_type(url: str) -> Optional[str]:
    """Determine the type of archive"""
    try:
        parsed = urlparse(url)
        if "web.archive.org" in parsed.netloc:
            return "wayback_machine"
        elif "archive.org" in parsed.netloc:
            return "internet_archive"
        elif any(d in parsed.netloc for d in ["archive.is", "archive.today", "archive.ph", "archive.md"]):
            return "archive_today"
        elif "webcache.googleusercontent.com" in parsed.netloc:
            return "google_cache"
        return None
    except Exception:
        return None


def extract_original_url(archive_url: str) -> Optional[str]:
    """Extract the original URL from an archive URL"""
    try:
        parsed = urlparse(archive_url)

        # Wayback Machine format: /web/TIMESTAMP/URL
        if "web.archive.org" in parsed.netloc:
            path_parts = parsed.path.split("/")
            if len(path_parts) >= 4 and path_parts[1] == "web":
                # Find the URL part (after timestamp)
                url_start_idx = 3
                original = "/".join(path_parts[url_start_idx:])
                if not original.startswith("http"):
                    original = "http://" + original
                return original

        # Archive.is format: URL is in the path
        if any(d in parsed.netloc for d in ["archive.is", "archive.today", "archive.ph", "archive.md"]):
            # Format is typically /{id}/{original_url}
            path_parts = parsed.path.strip("/").split("/", 1)
            if len(path_parts) >= 2:
                return path_parts[1]

        return None

    except Exception:
        return None


def check_url_available(url: str, timeout: int = 5) -> bool:
    """Check if a URL is accessible"""
    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        return response.status_code < 400
    except Exception:
        return False


def get_wayback_url(url: str, timestamp: str = None) -> str:
    """
    Generate a Wayback Machine URL.

    Args:
        url: Original URL to archive
        timestamp: Optional timestamp (YYYYMMDDHHMMSS format)

    Returns:
        Wayback Machine URL
    """
    if timestamp:
        return f"https://web.archive.org/web/{timestamp}/{url}"
    return f"https://web.archive.org/web/*/{url}"


def get_archive_today_url(url: str) -> str:
    """Generate an Archive.today URL"""
    return f"https://archive.today/{quote(url)}"


async def check_wayback_availability(url: str) -> Dict[str, Any]:
    """
    Check if a URL is available in the Wayback Machine.

    Args:
        url: URL to check

    Returns:
        Dict with availability information
    """
    api_url = f"https://archive.org/wayback/available?url={quote(url)}"

    try:
        response = requests.get(api_url, timeout=10)
        data = response.json()

        snapshots = data.get("archived_snapshots", {})
        closest = snapshots.get("closest", {})

        if closest:
            return {
                "available": True,
                "url": closest.get("url"),
                "timestamp": closest.get("timestamp"),
                "status": closest.get("status"),
            }
        else:
            return {
                "available": False,
                "url": None,
                "timestamp": None,
                "status": None,
            }

    except Exception as e:
        logger.error(f"Wayback availability check failed: {e}")
        return {
            "available": False,
            "error": str(e),
        }


def generate_archive_search_urls(query: str) -> List[Dict[str, str]]:
    """
    Generate search URLs for various archive services.

    Args:
        query: Search query or URL

    Returns:
        List of archive search URLs
    """
    encoded = quote(query)

    return [
        {
            "title": f"Wayback Machine: {query}",
            "url": f"https://web.archive.org/web/*/{query}",
            "description": "Search the Internet Archive's Wayback Machine",
            "archive_type": "wayback_machine",
        },
        {
            "title": f"Archive.org Search: {query}",
            "url": f"https://archive.org/search.php?query={encoded}",
            "description": "Search all Internet Archive collections",
            "archive_type": "internet_archive",
        },
        {
            "title": f"Archive.today: {query}",
            "url": f"https://archive.today/{query}",
            "description": "Search Archive.today snapshots",
            "archive_type": "archive_today",
        },
        {
            "title": f"Google Cache: {query}",
            "url": f"https://webcache.googleusercontent.com/search?q=cache:{query}",
            "description": "Google's cached version",
            "archive_type": "google_cache",
        },
    ]


__all__ = [
    "process_archive_results",
    "is_archive_url",
    "get_archive_type",
    "extract_original_url",
    "check_url_available",
    "get_wayback_url",
    "get_archive_today_url",
    "check_wayback_availability",
    "generate_archive_search_urls",
]
