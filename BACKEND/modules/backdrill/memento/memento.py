"""
Memento TimeMap client for BACKDRILL.

Access 40+ web archives via the Memento protocol.

Consolidated from:
- DATA/archives/archive_browser.py

Supported archives:
- Internet Archive (archive.org)
- Archive.today / Archive.is
- Perma.cc
- UK Web Archive (webarchive.org.uk)
- Portuguese Web Archive (arquivo.pt)
- Croatian Web Archive
- Australian Web Archive (webarchive.nla.gov.au)
- Library of Congress (webarchive.loc.gov)
- Stanford Web Archive
- Icelandic Web Archive
- Norwegian Web Archive
- And 30+ more...
"""

import asyncio
import aiohttp
import re
from datetime import datetime
from typing import Optional, List, Dict, Any, Set
from urllib.parse import urlparse, quote
import logging

logger = logging.getLogger(__name__)

# Memento TimeMap aggregator
MEMENTO_AGGREGATOR = "http://timetravel.mementoweb.org/timemap/json"

# Known archive patterns for source identification
ARCHIVE_PATTERNS = {
    "archive.org": "Internet Archive",
    "web.archive.org": "Internet Archive",
    "archive.today": "Archive.today",
    "archive.is": "Archive.today",
    "archive.ph": "Archive.today",
    "archive.md": "Archive.today",
    "perma.cc": "Perma.cc",
    "webarchive.org.uk": "UK Web Archive",
    "arquivo.pt": "Portuguese Web Archive",
    "haw.nsk.hr": "Croatian Web Archive",
    "webarchive.nla.gov.au": "Australian Web Archive",
    "webarchive.loc.gov": "Library of Congress",
    "swap.stanford.edu": "Stanford Web Archive",
    "vefsafn.is": "Icelandic Web Archive",
    "webarchive.proni.gov.uk": "Northern Ireland Web Archive",
    "webarchive.nationalarchives.gov.uk": "UK National Archives",
    "web.archive.org.au": "Pandora (Australia)",
    "webarchive.bnf.fr": "French Web Archive (BnF)",
    "nukrobi2.nuk.uni-lj.si": "Slovenian Web Archive",
    "wayback.archive-it.org": "Archive-It",
    "screenshots.com": "Screenshots.com",
}


class Memento:
    """
    Memento TimeMap client for accessing 40+ web archives.

    The Memento protocol provides a standardized way to discover
    archived versions of web resources across multiple archives.

    Usage:
        m = Memento()

        # Get all snapshots from all archives
        snapshots = await m.list_snapshots("https://example.com")

        # Fetch from best available archive
        result = await m.fetch("https://example.com")

        # Get archives that have this URL
        archives = await m.get_archives("https://example.com")
    """

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        self._session = session
        self._own_session = session is None

    async def __aenter__(self):
        if self._own_session:
            self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        if self._own_session and self._session:
            await self._session.close()
            self._session = None

    async def _ensure_session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._own_session = True

    def _identify_archive(self, url: str) -> str:
        """Identify which archive a memento URL belongs to."""
        for pattern, name in ARCHIVE_PATTERNS.items():
            if pattern in url:
                return name
        return "Unknown Archive"

    def _parse_timestamp(self, ts: str) -> Optional[datetime]:
        """Parse various timestamp formats."""
        formats = [
            "%Y%m%d%H%M%S",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
            "%a, %d %b %Y %H:%M:%S %Z",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(ts, fmt)
            except:
                continue
        return None

    async def list_snapshots(
        self,
        url: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get all available snapshots from all archives via Memento TimeMap.

        Args:
            url: Target URL
            start_date: Filter from date (YYYY-MM-DD) - client-side filter
            end_date: Filter to date (YYYY-MM-DD) - client-side filter

        Returns:
            List of snapshot dicts with timestamp, memento_url, archive
        """
        await self._ensure_session()

        encoded_url = quote(url, safe='')
        timemap_url = f"{MEMENTO_AGGREGATOR}/{encoded_url}"

        try:
            async with self._session.get(
                timemap_url,
                timeout=aiohttp.ClientTimeout(total=60),
                headers={"Accept": "application/json"}
            ) as resp:
                if resp.status != 200:
                    logger.debug(f"TimeMap request failed: {resp.status}")
                    return []

                data = await resp.json()

                # Parse mementos
                mementos = data.get("mementos", {})
                snapshots = []

                # Parse date filters
                start_dt = None
                end_dt = None
                if start_date:
                    try:
                        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                    except:
                        pass
                if end_date:
                    try:
                        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                    except:
                        pass

                # Get list of mementos
                memento_list = mementos.get("list", [])
                if not memento_list and "first" in mementos:
                    # Some responses use first/last/prev/next instead of list
                    memento_list = [mementos.get("first")]
                    if "last" in mementos:
                        memento_list.append(mementos["last"])

                for m in memento_list:
                    if not m:
                        continue

                    memento_url = m.get("uri")
                    timestamp_str = m.get("datetime")

                    if not memento_url:
                        continue

                    # Parse timestamp
                    ts_dt = self._parse_timestamp(timestamp_str) if timestamp_str else None

                    # Apply date filters
                    if ts_dt:
                        if start_dt and ts_dt < start_dt:
                            continue
                        if end_dt and ts_dt > end_dt:
                            continue

                    archive = self._identify_archive(memento_url)

                    snapshots.append({
                        "timestamp": timestamp_str,
                        "datetime": ts_dt,
                        "memento_url": memento_url,
                        "archive": archive,
                        "original_url": url,
                    })

                # Sort by timestamp (newest first)
                snapshots.sort(
                    key=lambda x: x.get("datetime") or datetime.min,
                    reverse=True
                )

                return snapshots

        except Exception as e:
            logger.error(f"Memento TimeMap query failed for {url}: {e}")
            return []

    async def get_archives(self, url: str) -> List[str]:
        """
        Get list of archives that have snapshots of this URL.

        Returns list of archive names.
        """
        snapshots = await self.list_snapshots(url)
        archives: Set[str] = set()
        for snap in snapshots:
            archives.add(snap.get("archive", "Unknown"))
        return list(archives)

    async def fetch(
        self,
        url: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        prefer_archive: Optional[str] = None,
    ):
        """
        Fetch content from the best available archive.

        Tries archives in order of preference:
        1. Preferred archive (if specified)
        2. Internet Archive (most reliable)
        3. Any other available archive

        Returns a BackdrillResult.
        """
        from ..backdrill import BackdrillResult, ArchiveSource

        await self._ensure_session()

        snapshots = await self.list_snapshots(url, start_date, end_date)

        if not snapshots:
            return BackdrillResult(url=url)

        # Sort by preference
        def sort_key(snap):
            archive = snap.get("archive", "")
            if prefer_archive and prefer_archive.lower() in archive.lower():
                return (0, snap.get("datetime") or datetime.min)
            if "Internet Archive" in archive:
                return (1, snap.get("datetime") or datetime.min)
            if "Archive.today" in archive:
                return (2, snap.get("datetime") or datetime.min)
            return (3, snap.get("datetime") or datetime.min)

        snapshots.sort(key=sort_key, reverse=True)

        # Try to fetch from best snapshot
        for snap in snapshots[:5]:  # Try top 5
            memento_url = snap.get("memento_url")
            if not memento_url:
                continue

            try:
                async with self._session.get(
                    memento_url,
                    timeout=aiohttp.ClientTimeout(total=30),
                    allow_redirects=True,
                ) as resp:
                    if resp.status == 200:
                        content = await resp.text()

                        return BackdrillResult(
                            url=url,
                            html=content,
                            timestamp=snap.get("datetime"),
                            source=ArchiveSource.MEMENTO,
                            status_code=resp.status,
                            mime_type=resp.headers.get("Content-Type"),
                            metadata={
                                "archive": snap.get("archive"),
                                "memento_url": memento_url,
                            }
                        )

            except Exception as e:
                logger.debug(f"Memento fetch failed from {snap.get('archive')}: {e}")
                continue

        return BackdrillResult(url=url)

    async def fetch_from_archive(
        self,
        url: str,
        archive_name: str,
    ):
        """
        Fetch from a specific archive.

        Args:
            url: Target URL
            archive_name: Archive name (e.g., "Internet Archive", "Archive.today")

        Returns a BackdrillResult.
        """
        from ..backdrill import BackdrillResult

        snapshots = await self.list_snapshots(url)

        # Filter to specific archive
        archive_snaps = [
            s for s in snapshots
            if archive_name.lower() in s.get("archive", "").lower()
        ]

        if not archive_snaps:
            return BackdrillResult(url=url)

        # Get newest from this archive
        snap = archive_snaps[0]
        return await self.fetch(url, prefer_archive=archive_name)

    async def compare_archives(
        self,
        url: str,
    ) -> Dict[str, Any]:
        """
        Compare availability across different archives.

        Returns summary of what each archive has.
        """
        snapshots = await self.list_snapshots(url)

        by_archive: Dict[str, List] = {}
        for snap in snapshots:
            archive = snap.get("archive", "Unknown")
            if archive not in by_archive:
                by_archive[archive] = []
            by_archive[archive].append(snap)

        summary = {
            "url": url,
            "total_snapshots": len(snapshots),
            "archives": {},
        }

        for archive, snaps in by_archive.items():
            dates = [s.get("datetime") for s in snaps if s.get("datetime")]
            summary["archives"][archive] = {
                "count": len(snaps),
                "oldest": min(dates).isoformat() if dates else None,
                "newest": max(dates).isoformat() if dates else None,
            }

        return summary
