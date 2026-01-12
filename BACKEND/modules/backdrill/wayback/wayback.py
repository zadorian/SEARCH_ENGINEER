"""
Wayback Machine client for BACKDRILL.

Provides:
- CDX API queries (timestamps, availability)
- Content fetching (archived pages)
- Save Page Now API

Consolidated from:
- LINKLATER/archives/optimal_archive.py
- LINKLATER/scraping/cc_first_scraper.py (Wayback parts)
"""

import asyncio
import aiohttp
from datetime import datetime
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

CDX_API = "https://web.archive.org/cdx/search/cdx"
WAYBACK_URL = "https://web.archive.org/web"
SAVE_API = "https://web.archive.org/save"


class Wayback:
    """
    Wayback Machine client for BACKDRILL.

    Usage:
        wb = Wayback()

        # Check if URL is archived
        exists = await wb.exists("https://example.com")

        # Get all snapshots
        snapshots = await wb.list_snapshots("https://example.com")

        # Fetch content
        result = await wb.fetch("https://example.com")

        # Save a URL (Save Page Now)
        saved = await wb.save("https://example.com")
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

    # -------------------------------------------------------------------------
    # CDX API
    # -------------------------------------------------------------------------

    async def exists(
        self,
        url: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> bool:
        """Check if URL exists in Wayback Machine."""
        snapshots = await self.list_snapshots(url, start_date, end_date, limit=1)
        return len(snapshots) > 0

    async def list_snapshots(
        self,
        url: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
        collapse: str = "timestamp:8",  # One per day
    ) -> List[Dict[str, Any]]:
        """
        Get all Wayback snapshots for a URL via CDX API.

        Args:
            url: Target URL
            start_date: Filter from date (YYYY-MM-DD)
            end_date: Filter to date (YYYY-MM-DD)
            limit: Max snapshots to return
            collapse: Dedup field (timestamp:8 = one per day)

        Returns:
            List of snapshot dicts with timestamp, url, status, mime
        """
        await self._ensure_session()

        params = {
            "url": url,
            "output": "json",
            "fl": "timestamp,original,statuscode,mimetype,digest",
            "limit": limit,
            "filter": "!statuscode:[45]..",  # Exclude 4xx/5xx
        }

        if start_date:
            params["from"] = start_date.replace("-", "")
        if end_date:
            params["to"] = end_date.replace("-", "")
        if collapse:
            params["collapse"] = collapse

        try:
            async with self._session.get(
                CDX_API,
                params=params,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    return []

                data = await resp.json()

                # First row is headers
                if len(data) <= 1:
                    return []

                snapshots = []
                for row in data[1:]:
                    snapshots.append({
                        "timestamp": row[0],
                        "url": row[1],
                        "status": row[2],
                        "mime": row[3],
                        "digest": row[4] if len(row) > 4 else None,
                    })

                return snapshots

        except Exception as e:
            logger.error(f"CDX query failed for {url}: {e}")
            return []

    async def get_closest_snapshot(
        self,
        url: str,
        target_date: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get the snapshot closest to a target date.

        Args:
            url: Target URL
            target_date: Target date (YYYY-MM-DD or YYYYMMDDHHMMSS)

        Returns:
            Closest snapshot or None
        """
        await self._ensure_session()

        # Format timestamp
        ts = target_date.replace("-", "").replace(":", "").replace(" ", "")

        params = {
            "url": url,
            "timestamp": ts,
            "output": "json",
            "limit": 1,
        }

        try:
            async with self._session.get(
                f"{CDX_API}/closest",
                params=params,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    return None

                data = await resp.json()
                if data and "archived_snapshots" in data:
                    closest = data["archived_snapshots"].get("closest")
                    if closest and closest.get("available"):
                        return {
                            "timestamp": closest.get("timestamp"),
                            "url": closest.get("url"),
                            "status": closest.get("status"),
                        }

        except Exception as e:
            logger.debug(f"Closest snapshot query failed: {e}")

        return None

    # -------------------------------------------------------------------------
    # Content fetching
    # -------------------------------------------------------------------------

    async def fetch(
        self,
        url: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        timestamp: Optional[str] = None,
    ):
        """
        Fetch archived content from Wayback Machine.

        Returns a BackdrillResult.
        """
        from ..backdrill import BackdrillResult, ArchiveSource

        await self._ensure_session()

        # Get timestamp if not provided
        if not timestamp:
            snapshots = await self.list_snapshots(url, start_date, end_date, limit=1)
            if not snapshots:
                return BackdrillResult(url=url)
            timestamp = snapshots[0]["timestamp"]

        # Fetch archived page
        wb_url = f"{WAYBACK_URL}/{timestamp}id_/{url}"

        try:
            async with self._session.get(
                wb_url,
                timeout=aiohttp.ClientTimeout(total=30),
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    return BackdrillResult(url=url, status_code=resp.status)

                content = await resp.text()

                # Parse timestamp to datetime
                try:
                    ts_dt = datetime.strptime(timestamp, "%Y%m%d%H%M%S")
                except:
                    ts_dt = None

                return BackdrillResult(
                    url=url,
                    html=content,
                    timestamp=ts_dt,
                    source=ArchiveSource.WAYBACK_DATA,
                    status_code=resp.status,
                    mime_type=resp.headers.get("Content-Type"),
                    metadata={"wayback_url": str(resp.url)}
                )

        except Exception as e:
            logger.error(f"Wayback fetch failed for {url}: {e}")
            return BackdrillResult(url=url)

    async def fetch_raw(
        self,
        url: str,
        timestamp: str,
    ) -> Optional[bytes]:
        """
        Fetch raw bytes from Wayback (for binary files).

        Uses id_ modifier to get unmodified content.
        """
        await self._ensure_session()

        wb_url = f"{WAYBACK_URL}/{timestamp}id_/{url}"

        try:
            async with self._session.get(
                wb_url,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status == 200:
                    return await resp.read()
        except Exception as e:
            logger.debug(f"Raw fetch failed: {e}")

        return None

    # -------------------------------------------------------------------------
    # Save Page Now
    # -------------------------------------------------------------------------

    async def save(
        self,
        url: str,
        capture_all: bool = False,
        capture_outlinks: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Save a URL to Wayback Machine using Save Page Now API.

        Args:
            url: URL to archive
            capture_all: Capture all resources (images, CSS, JS)
            capture_outlinks: Also capture outlinks

        Returns:
            Dict with job_id and status, or None on failure
        """
        await self._ensure_session()

        params = {"url": url}
        if capture_all:
            params["capture_all"] = "1"
        if capture_outlinks:
            params["capture_outlinks"] = "1"

        try:
            async with self._session.post(
                SAVE_API,
                data=params,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status in (200, 201):
                    # Check for job_id in response
                    text = await resp.text()
                    return {
                        "status": "submitted",
                        "url": url,
                        "response": text[:500],
                    }
                else:
                    return {
                        "status": "failed",
                        "url": url,
                        "error": f"HTTP {resp.status}",
                    }

        except Exception as e:
            logger.error(f"Save Page Now failed for {url}: {e}")
            return None

    # -------------------------------------------------------------------------
    # Bulk operations
    # -------------------------------------------------------------------------

    async def fetch_batch(
        self,
        urls: List[str],
        concurrent: int = 10,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List:
        """
        Fetch multiple URLs concurrently.

        Args:
            urls: List of URLs
            concurrent: Max concurrent requests
            start_date: Filter from date
            end_date: Filter to date

        Returns:
            List of BackdrillResult objects
        """
        semaphore = asyncio.Semaphore(concurrent)

        async def fetch_one(url):
            async with semaphore:
                return await self.fetch(url, start_date, end_date)

        tasks = [fetch_one(url) for url in urls]
        return await asyncio.gather(*tasks)

    async def get_domain_snapshots(
        self,
        domain: str,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Get all snapshots for a domain (wildcard search).

        Returns unique URLs found in Wayback for the domain.
        """
        await self._ensure_session()

        params = {
            "url": f"*.{domain}/*",
            "matchType": "domain",
            "output": "json",
            "fl": "timestamp,original,statuscode",
            "collapse": "urlkey",
            "limit": limit,
        }

        try:
            async with self._session.get(
                CDX_API,
                params=params,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status != 200:
                    return []

                data = await resp.json()

                if len(data) <= 1:
                    return []

                results = []
                for row in data[1:]:
                    results.append({
                        "timestamp": row[0],
                        "url": row[1],
                        "status": row[2] if len(row) > 2 else None,
                    })

                return results

        except Exception as e:
            logger.error(f"Domain snapshot query failed for {domain}: {e}")
            return []
