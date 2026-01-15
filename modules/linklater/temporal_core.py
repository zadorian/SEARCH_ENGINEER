"""
LinkLater Temporal Analysis - URL Timeline Intelligence

Tracks temporal metadata for URLs:
- First-seen dates from Wayback Machine and Common Crawl
- Last-seen dates from archives
- Live/dead status detection
- Archive history enrichment

Based on AllDom temporal capabilities, integrated into LinkLater.
"""

import aiohttp
import asyncio
import json
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime
import logging
from urllib.parse import quote

logger = logging.getLogger(__name__)


@dataclass
class URLTimeline:
    """
    Complete temporal information for a URL

    Tracks discovery sources, archive history, and live status
    """
    url: str
    is_live: bool = False
    live_status_code: Optional[int] = None

    # Archive history
    first_seen_wayback: Optional[str] = None  # ISO timestamp
    last_seen_wayback: Optional[str] = None   # ISO timestamp
    first_seen_commoncrawl: Optional[str] = None
    last_seen_commoncrawl: Optional[str] = None
    # Memento (aggregates multiple archives; optional/fallback)
    first_seen_memento: Optional[str] = None
    last_seen_memento: Optional[str] = None

    # Discovery sources
    sources: Set[str] = field(default_factory=set)
    discovered_at: float = 0.0

    # Metadata
    title: Optional[str] = None
    description: Optional[str] = None

    def get_first_seen(self) -> Optional[str]:
        """Get earliest first-seen date across all archives"""
        dates = [d for d in [self.first_seen_wayback, self.first_seen_commoncrawl, self.first_seen_memento] if d]
        return min(dates) if dates else None

    def get_last_archived(self) -> Optional[str]:
        """Get most recent archive date"""
        dates = [d for d in [self.last_seen_wayback, self.last_seen_commoncrawl, self.last_seen_memento] if d]
        return max(dates) if dates else None

    def age_days(self) -> Optional[int]:
        """Get age in days since first-seen"""
        first_seen = self.get_first_seen()
        if not first_seen:
            return None
        try:
            dt = datetime.fromisoformat(first_seen.replace('Z', '+00:00'))
            age = (datetime.now(dt.tzinfo) - dt).days
            return age
        except Exception as e:
            return None

    def to_dict(self) -> dict:
        """Convert to dictionary (for JSON serialization)"""
        data = asdict(self)
        # Convert set to list
        data['sources'] = list(self.sources)
        # Add computed fields
        data['first_seen'] = self.get_first_seen()
        data['last_archived'] = self.get_last_archived()
        data['age_days'] = self.age_days()
        return data

    def format_display(self) -> str:
        """Format for human-readable display"""
        if self.is_live:
            first_seen = self.get_first_seen()
            if first_seen:
                try:
                    dt = datetime.fromisoformat(first_seen.replace('Z', '+00:00'))
                    return f"{self.url} [LIVE] (first seen: {dt.strftime('%d %b %Y')})"
                except Exception as e:
                    return f"{self.url} [LIVE]"
            return f"{self.url} [LIVE]"
        else:
            last_archived = self.get_last_archived()
            if last_archived:
                try:
                    dt = datetime.fromisoformat(last_archived.replace('Z', '+00:00'))
                    archive_source = []
                    if self.last_seen_wayback == last_archived:
                        archive_source.append('Wayback')
                    if self.last_seen_commoncrawl == last_archived:
                        archive_source.append('CommonCrawl')
                    sources_str = '/'.join(archive_source)
                    return f"{self.url} [DEAD] (last seen: {dt.strftime('%d %b %Y')} via {sources_str})"
                except Exception as e:
                    return f"{self.url} [DEAD]"
            return f"{self.url} [DEAD]"


class TemporalAnalyzer:
    """
    URL temporal analysis and enrichment

    Provides:
    - Live/dead status checking
    - Archive history enrichment
    - First-seen/last-seen date tracking
    """

    def __init__(self, timeout: int = 30):
        """
        Initialize temporal analyzer

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout

    async def check_url_live(self, url: str, timeout: int = 10) -> tuple[bool, Optional[int]]:
        """
        Check if a URL is still live

        Args:
            url: URL to check
            timeout: Request timeout in seconds

        Returns:
            Tuple of (is_live, status_code)
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(
                    url,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    allow_redirects=True
                ) as response:
                    return (True, response.status)
        except Exception as e:
            return (False, None)

    async def check_urls_live_batch(
        self,
        urls: List[str],
        max_concurrent: int = 50
    ) -> Dict[str, tuple[bool, Optional[int]]]:
        """
        Check live status for multiple URLs in parallel

        Args:
            urls: List of URLs to check
            max_concurrent: Max concurrent requests

        Returns:
            Dict mapping URL -> (is_live, status_code)
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        results = {}

        async def check_one(url: str):
            async with semaphore:
                is_live, status = await self.check_url_live(url)
                results[url] = (is_live, status)

        tasks = [check_one(url) for url in urls]
        await asyncio.gather(*tasks, return_exceptions=True)

        return results

    async def enrich_wayback_history(
        self,
        url: str
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Get first-seen and last-seen dates from Wayback Machine

        Args:
            url: URL to query

        Returns:
            Tuple of (first_seen, last_seen) ISO timestamps
        """
        try:
            async with aiohttp.ClientSession() as session:
                cdx_url = "https://web.archive.org/cdx/search/cdx"
                params = {
                    'url': url,
                    'output': 'json',
                    'limit': -1,  # All snapshots
                    'fl': 'timestamp',
                    'filter': 'statuscode:200',
                    'collapse': 'timestamp:8'  # Daily granularity
                }

                async with session.get(
                    cdx_url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if len(data) > 1:
                            # Skip header row
                            timestamps = [row[0] for row in data[1:]]
                            if timestamps:
                                # Convert to ISO format
                                first_raw = min(timestamps)
                                last_raw = max(timestamps)

                                first_dt = datetime.strptime(first_raw, '%Y%m%d%H%M%S')
                                last_dt = datetime.strptime(last_raw, '%Y%m%d%H%M%S')

                                return (
                                    first_dt.isoformat() + 'Z',
                                    last_dt.isoformat() + 'Z'
                                )
        except Exception as e:
            logger.debug(f"Wayback enrichment failed for {url}: {e}")

        return (None, None)

    async def enrich_commoncrawl_history(
        self,
        url: str,
        archive: str = "CC-MAIN-2024-10"
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Get first-seen and last-seen dates from Common Crawl

        Args:
            url: URL to query
            archive: CC archive to query (default: latest)

        Returns:
            Tuple of (first_seen, last_seen) ISO timestamps
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Get index API endpoint
                indexes_url = "https://index.commoncrawl.org/collinfo.json"
                async with session.get(
                    indexes_url,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        indexes = await response.json()
                        if not indexes:
                            return (None, None)

                        # Use specified archive or latest
                        cdx_api = None
                        for idx in indexes:
                            if archive == "latest" or idx['id'] == archive:
                                cdx_api = idx['cdx-api']
                                break

                        if not cdx_api:
                            return (None, None)

                        # Query index
                        params = {
                            'url': url,
                            'output': 'json',
                            'limit': -1  # All captures
                        }

                        async with session.get(
                            cdx_api,
                            params=params,
                            timeout=aiohttp.ClientTimeout(total=self.timeout)
                        ) as cdx_resp:
                            if cdx_resp.status == 200:
                                text = await cdx_resp.text()
                                if text.strip():
                                    timestamps = []
                                    for line in text.strip().split('\n'):
                                        try:
                                            entry = json.loads(line)
                                            timestamp_raw = entry.get('timestamp', '')
                                            if timestamp_raw:
                                                timestamps.append(timestamp_raw)
                                        except json.JSONDecodeError:
                                            continue

                                    if timestamps:
                                        first_raw = min(timestamps)
                                        last_raw = max(timestamps)

                                        first_dt = datetime.strptime(first_raw, '%Y%m%d%H%M%S')
                                        last_dt = datetime.strptime(last_raw, '%Y%m%d%H%M%S')

                                        return (
                                            first_dt.isoformat() + 'Z',
                                            last_dt.isoformat() + 'Z'
                                        )
        except Exception as e:
            logger.debug(f"Common Crawl enrichment failed for {url}: {e}")

        return (None, None)

    async def enrich_memento_history(self, url: str) -> tuple[Optional[str], Optional[str]]:
        """
        Get first/last memento datetimes (aggregated across archives via Memento).

        This is best-effort *supplemental* signal; it can be slower/less reliable than Wayback CDX.
        """
        try:
            api_url = f"https://timetravel.mementoweb.org/api/json/{quote(url, safe='')}"
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    api_url,
                    timeout=aiohttp.ClientTimeout(total=min(self.timeout, 20))
                ) as response:
                    if response.status != 200:
                        return (None, None)
                    data = await response.json()
                    mem = (data or {}).get("mementos") or {}
                    first_dt = ((mem.get("first") or {}).get("datetime") or "").strip()
                    last_dt = ((mem.get("last") or {}).get("datetime") or "").strip()

                    def to_iso(dt_str: str) -> Optional[str]:
                        if not dt_str:
                            return None
                        try:
                            parsed = datetime.strptime(dt_str, "%a, %d %b %Y %H:%M:%S GMT")
                            return parsed.isoformat() + "Z"
                        except Exception:
                            try:
                                parsed2 = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                                return parsed2.isoformat().replace("+00:00", "Z")
                            except Exception:
                                return None

                    return (to_iso(first_dt), to_iso(last_dt))
        except Exception as e:
            logger.debug(f"Memento enrichment failed for {url}: {e}")
            return (None, None)

    async def get_url_timeline(
        self,
        url: str,
        check_live: bool = True,
        enrich_wayback: bool = True,
        enrich_commoncrawl: bool = True,
        enrich_memento: bool = True,
        cc_archive: str = "latest"
    ) -> URLTimeline:
        """
        Get complete temporal timeline for a URL

        Args:
            url: URL to analyze
            check_live: Check if URL is still live
            enrich_wayback: Enrich with Wayback history
            enrich_commoncrawl: Enrich with CC history
            cc_archive: CC archive to query

        Returns:
            URLTimeline object with complete temporal data
        """
        timeline = URLTimeline(url=url, discovered_at=asyncio.get_event_loop().time())

        # Check live status
        if check_live:
            is_live, status = await self.check_url_live(url)
            timeline.is_live = is_live
            timeline.live_status_code = status

        # Enrich with archive history (parallel)
        tasks = []
        if enrich_wayback:
            tasks.append(self.enrich_wayback_history(url))
        if enrich_commoncrawl:
            tasks.append(self.enrich_commoncrawl_history(url, cc_archive))
        if enrich_memento:
            tasks.append(self.enrich_memento_history(url))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        idx = 0
        if enrich_wayback and idx < len(results):
            if not isinstance(results[idx], Exception):
                first_wb, last_wb = results[idx]
                timeline.first_seen_wayback = first_wb
                timeline.last_seen_wayback = last_wb
            idx += 1

        if enrich_commoncrawl and idx < len(results):
            if not isinstance(results[idx], Exception):
                first_cc, last_cc = results[idx]
                timeline.first_seen_commoncrawl = first_cc
                timeline.last_seen_commoncrawl = last_cc
            idx += 1

        if enrich_memento and idx < len(results):
            if not isinstance(results[idx], Exception):
                first_m, last_m = results[idx]
                timeline.first_seen_memento = first_m
                timeline.last_seen_memento = last_m

        return timeline

    async def get_url_timelines_batch(
        self,
        urls: List[str],
        check_live: bool = True,
        enrich_wayback: bool = True,
        enrich_commoncrawl: bool = True,
        enrich_memento: bool = True,
        cc_archive: str = "latest",
        max_concurrent: int = 10
    ) -> Dict[str, URLTimeline]:
        """
        Get temporal timelines for multiple URLs in parallel

        Args:
            urls: List of URLs to analyze
            check_live: Check if URLs are still live
            enrich_wayback: Enrich with Wayback history
            enrich_commoncrawl: Enrich with CC history
            cc_archive: CC archive to query
            max_concurrent: Max concurrent requests

        Returns:
            Dict mapping URL -> URLTimeline
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        results = {}

        async def analyze_one(url: str):
            async with semaphore:
                timeline = await self.get_url_timeline(
                    url=url,
                    check_live=check_live,
                    enrich_wayback=enrich_wayback,
                    enrich_commoncrawl=enrich_commoncrawl,
                    enrich_memento=enrich_memento,
                    cc_archive=cc_archive
                )
                results[url] = timeline

        tasks = [analyze_one(url) for url in urls]
        await asyncio.gather(*tasks, return_exceptions=True)

        return results
