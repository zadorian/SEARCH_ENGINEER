"""
Historical analysis tools for BACKDRILL.

- Timeline builder: build a timeline of all versions
- Version differ: compare two snapshots
- Change scanner: detect content changes over time
"""

import difflib
from datetime import datetime
from typing import List, Dict, Any, Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from ..backdrill import Backdrill

logger = logging.getLogger(__name__)


async def build_timeline(
    bd: "Backdrill",
    url: str,
    max_snapshots: int = 50,
) -> List[Dict[str, Any]]:
    """
    Build a timeline of all archived versions of a URL.

    Aggregates snapshots from all available archives and
    orders them chronologically.

    Args:
        bd: Backdrill instance
        url: Target URL
        max_snapshots: Maximum snapshots to include

    Returns:
        List of {timestamp, source, url, digest} dicts
    """
    snapshots = await bd.list_snapshots(url)

    # Limit and format
    timeline = []
    seen_digests = set()

    for snap in snapshots[:max_snapshots]:
        # Skip duplicates by digest if available
        digest = snap.get("digest")
        if digest and digest in seen_digests:
            continue
        if digest:
            seen_digests.add(digest)

        timeline.append({
            "timestamp": snap.get("timestamp"),
            "source": snap.get("source"),
            "url": snap.get("url") or url,
            "status": snap.get("status"),
            "mime": snap.get("mime"),
            "digest": digest,
        })

    # Sort by timestamp (oldest first for timeline)
    timeline.sort(key=lambda x: x.get("timestamp") or "")

    return timeline


async def diff_versions(
    bd: "Backdrill",
    url: str,
    ts1: str,
    ts2: str,
    context_lines: int = 3,
) -> Dict[str, Any]:
    """
    Compare two archived versions of a URL.

    Args:
        bd: Backdrill instance
        url: Target URL
        ts1: First timestamp (YYYYMMDDHHMMSS format)
        ts2: Second timestamp
        context_lines: Number of context lines in diff

    Returns:
        {
            "url": str,
            "ts1": str,
            "ts2": str,
            "diff": str,  # Unified diff
            "added_lines": int,
            "removed_lines": int,
            "changed": bool,
        }
    """
    from ..backdrill import ArchiveSource

    # Fetch both versions
    result1 = await bd.fetch(url, prefer_source=ArchiveSource.WAYBACK_DATA)
    result2 = await bd.fetch(url, prefer_source=ArchiveSource.WAYBACK_DATA)

    content1 = result1.html or result1.content or ""
    content2 = result2.html or result2.content or ""

    # Generate diff
    lines1 = content1.splitlines(keepends=True)
    lines2 = content2.splitlines(keepends=True)

    diff = list(difflib.unified_diff(
        lines1,
        lines2,
        fromfile=f"{url} @ {ts1}",
        tofile=f"{url} @ {ts2}",
        n=context_lines,
    ))

    # Count changes
    added = sum(1 for line in diff if line.startswith('+') and not line.startswith('+++'))
    removed = sum(1 for line in diff if line.startswith('-') and not line.startswith('---'))

    return {
        "url": url,
        "ts1": ts1,
        "ts2": ts2,
        "diff": "".join(diff),
        "added_lines": added,
        "removed_lines": removed,
        "changed": len(diff) > 0,
    }


async def detect_changes(
    bd: "Backdrill",
    url: str,
    max_snapshots: int = 20,
) -> List[Dict[str, Any]]:
    """
    Detect significant content changes over time.

    Compares consecutive snapshots and identifies when
    major changes occurred.

    Args:
        bd: Backdrill instance
        url: Target URL
        max_snapshots: Max snapshots to analyze

    Returns:
        List of {timestamp, change_type, summary} for each change
    """
    timeline = await build_timeline(bd, url, max_snapshots=max_snapshots)

    if len(timeline) < 2:
        return []

    changes = []
    prev_digest = None

    for snap in timeline:
        digest = snap.get("digest")

        if prev_digest and digest and digest != prev_digest:
            changes.append({
                "timestamp": snap.get("timestamp"),
                "source": snap.get("source"),
                "change_type": "content_changed",
                "previous_digest": prev_digest,
                "new_digest": digest,
            })

        prev_digest = digest

    return changes


async def find_first_appearance(
    bd: "Backdrill",
    url: str,
    search_text: str,
) -> Optional[Dict[str, Any]]:
    """
    Find the first snapshot containing specific text.

    Useful for finding when something was first mentioned.

    Args:
        bd: Backdrill instance
        url: Target URL
        search_text: Text to search for

    Returns:
        Snapshot dict or None if not found
    """
    timeline = await build_timeline(bd, url, max_snapshots=100)

    for snap in timeline:
        # Fetch content
        ts = snap.get("timestamp")
        if not ts:
            continue

        result = await bd.fetch(url)
        content = result.html or result.content or ""

        if search_text.lower() in content.lower():
            return {
                "timestamp": ts,
                "source": snap.get("source"),
                "url": url,
                "found": True,
            }

    return None


async def find_last_appearance(
    bd: "Backdrill",
    url: str,
    search_text: str,
) -> Optional[Dict[str, Any]]:
    """
    Find the last snapshot containing specific text.

    Useful for finding when something was removed.

    Args:
        bd: Backdrill instance
        url: Target URL
        search_text: Text to search for

    Returns:
        Snapshot dict or None if not found
    """
    timeline = await build_timeline(bd, url, max_snapshots=100)

    # Reverse to search newest first
    last_found = None

    for snap in reversed(timeline):
        ts = snap.get("timestamp")
        if not ts:
            continue

        result = await bd.fetch(url)
        content = result.html or result.content or ""

        if search_text.lower() in content.lower():
            last_found = {
                "timestamp": ts,
                "source": snap.get("source"),
                "url": url,
                "found": True,
            }
            break

    return last_found


def compute_similarity(text1: str, text2: str) -> float:
    """
    Compute similarity ratio between two texts.

    Returns a value between 0.0 (completely different) and 1.0 (identical).
    """
    if not text1 or not text2:
        return 0.0

    return difflib.SequenceMatcher(None, text1, text2).ratio()
