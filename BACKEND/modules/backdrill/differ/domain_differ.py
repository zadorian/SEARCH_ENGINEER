"""
Domain Version Comparison - Track how a domain changed over time.

Provides:
- Domain-level change tracking (new pages, removed pages, modified pages)
- Page version comparison (content diffs between timestamps)
- Change timeline for investigation (when did X appear/disappear?)

Usage:
    from modules.backdrill.differ import DomainDiffer

    differ = DomainDiffer()

    # Get domain evolution over time
    evolution = await differ.domain_evolution("example.com")

    # Compare two time periods
    changes = await differ.compare_periods(
        "example.com",
        period1="2020-01-01",
        period2="2024-01-01"
    )

    # Track specific page changes
    page_history = await differ.page_history("https://example.com/about")

    # Find when content appeared/disappeared
    appearance = await differ.find_content_change(
        "example.com",
        search_text="John Smith",
        change_type="appeared"  # or "disappeared"
    )
"""

import asyncio
import difflib
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Set, Tuple
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class PageVersion:
    """A single version of a page."""
    url: str
    timestamp: str  # YYYYMMDDHHMMSS
    source: str  # wayback, commoncrawl, memento
    content_hash: Optional[str] = None
    title: Optional[str] = None
    content_length: Optional[int] = None
    status_code: Optional[int] = None
    archive_url: Optional[str] = None


@dataclass
class PageChange:
    """A change between two versions of a page."""
    url: str
    change_type: str  # "modified", "title_changed", "major_change", "minor_change"
    from_timestamp: str
    to_timestamp: str
    from_hash: Optional[str] = None
    to_hash: Optional[str] = None
    similarity: float = 0.0
    diff_summary: Optional[str] = None
    added_lines: int = 0
    removed_lines: int = 0


@dataclass
class DomainChange:
    """A change at the domain level."""
    change_type: str  # "page_added", "page_removed", "page_modified"
    url: str
    timestamp: str
    details: Optional[str] = None


@dataclass
class DomainEvolution:
    """Complete evolution of a domain over time."""
    domain: str

    # URL counts by period
    periods: List[Dict[str, Any]] = field(default_factory=list)

    # Changes detected
    pages_added: List[DomainChange] = field(default_factory=list)
    pages_removed: List[DomainChange] = field(default_factory=list)
    pages_modified: List[DomainChange] = field(default_factory=list)

    # Stats
    total_unique_urls: int = 0
    earliest_snapshot: Optional[str] = None
    latest_snapshot: Optional[str] = None

    # Timing
    analyzed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class PeriodComparison:
    """Comparison between two time periods."""
    domain: str
    period1: str
    period2: str

    # URLs in each period
    urls_period1: Set[str] = field(default_factory=set)
    urls_period2: Set[str] = field(default_factory=set)

    # Differences
    urls_added: Set[str] = field(default_factory=set)  # In period2 but not period1
    urls_removed: Set[str] = field(default_factory=set)  # In period1 but not period2
    urls_common: Set[str] = field(default_factory=set)  # In both periods

    # Content changes (for common URLs)
    content_changed: List[PageChange] = field(default_factory=list)


@dataclass
class PageHistory:
    """Complete history of a single page."""
    url: str
    versions: List[PageVersion] = field(default_factory=list)
    changes: List[PageChange] = field(default_factory=list)

    # Stats
    total_versions: int = 0
    unique_versions: int = 0  # By content hash
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None


@dataclass
class ContentAppearance:
    """When specific content appeared or disappeared."""
    search_text: str
    domain: str
    change_type: str  # "appeared" or "disappeared"

    # The page and timestamp where change occurred
    url: Optional[str] = None
    timestamp: Optional[str] = None

    # Context
    surrounding_text: Optional[str] = None
    found: bool = False


class DomainDiffer:
    """
    Track how a domain changed over time.

    Uses BackdrillMapper for URL discovery and Backdrill for content fetching.
    """

    def __init__(
        self,
        enable_content_fetch: bool = True,
        max_concurrent: int = 10,
    ):
        self.enable_content_fetch = enable_content_fetch
        self.max_concurrent = max_concurrent

        # Lazy-loaded
        self._mapper = None
        self._backdrill = None

    async def _ensure_clients(self):
        """Lazy-load mapper and backdrill."""
        if self._mapper is None:
            from ..mapper import BackdrillMapper
            self._mapper = BackdrillMapper()
            await self._mapper._ensure_clients()

        if self._backdrill is None and self.enable_content_fetch:
            from ..backdrill import Backdrill
            self._backdrill = Backdrill()

    async def close(self):
        """Close all clients."""
        if self._mapper:
            await self._mapper.close()
        if self._backdrill:
            await self._backdrill.close()

    async def __aenter__(self):
        await self._ensure_clients()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def _normalize_domain(self, domain: str) -> str:
        """Normalize domain for comparison."""
        domain = domain.lower().strip()
        domain = domain.lstrip("www.")
        if "://" in domain:
            from urllib.parse import urlparse
            domain = urlparse(domain).netloc
        return domain

    def _timestamp_to_year(self, ts: str) -> str:
        """Extract year from timestamp."""
        if ts and len(ts) >= 4:
            return ts[:4]
        return "unknown"

    def _content_hash(self, content: str) -> str:
        """Hash content for comparison."""
        # Normalize whitespace for comparison
        normalized = re.sub(r'\s+', ' ', content.strip())
        return hashlib.md5(normalized.encode()).hexdigest()[:16]

    def _extract_text(self, html: str) -> str:
        """Extract visible text from HTML."""
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Remove script/style
            for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()

            return soup.get_text(separator=' ', strip=True)
        except:
            return html

    async def domain_evolution(
        self,
        domain: str,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
    ) -> DomainEvolution:
        """
        Analyze how a domain evolved over time.

        Groups URLs by year and tracks additions/removals.

        Args:
            domain: Target domain
            start_year: Optional start year filter
            end_year: Optional end year filter

        Returns:
            DomainEvolution with change timeline
        """
        await self._ensure_clients()
        domain = self._normalize_domain(domain)

        # Get all mapped URLs
        domain_map = await self._mapper.map_domain(domain, dedupe=False)

        # Group by year
        urls_by_year: Dict[str, Set[str]] = {}

        for mapped_url in domain_map.urls:
            year = self._timestamp_to_year(mapped_url.timestamp or "")
            if year == "unknown":
                continue

            # Apply year filters
            if start_year and int(year) < start_year:
                continue
            if end_year and int(year) > end_year:
                continue

            if year not in urls_by_year:
                urls_by_year[year] = set()
            urls_by_year[year].add(mapped_url.url)

        # Build periods
        periods = []
        sorted_years = sorted(urls_by_year.keys())

        for year in sorted_years:
            periods.append({
                "year": year,
                "url_count": len(urls_by_year[year]),
                "urls": list(urls_by_year[year])[:100],  # Sample
            })

        # Detect changes between consecutive years
        pages_added = []
        pages_removed = []

        prev_year = None
        prev_urls = set()

        for year in sorted_years:
            current_urls = urls_by_year[year]

            if prev_year:
                # URLs that appeared
                for url in current_urls - prev_urls:
                    pages_added.append(DomainChange(
                        change_type="page_added",
                        url=url,
                        timestamp=year,
                        details=f"First seen in {year} (not in {prev_year})",
                    ))

                # URLs that disappeared
                for url in prev_urls - current_urls:
                    pages_removed.append(DomainChange(
                        change_type="page_removed",
                        url=url,
                        timestamp=year,
                        details=f"Not seen in {year} (was in {prev_year})",
                    ))

            prev_year = year
            prev_urls = current_urls

        # Collect all unique URLs
        all_urls = set()
        for urls in urls_by_year.values():
            all_urls.update(urls)

        return DomainEvolution(
            domain=domain,
            periods=periods,
            pages_added=pages_added[:500],  # Limit output size
            pages_removed=pages_removed[:500],
            total_unique_urls=len(all_urls),
            earliest_snapshot=domain_map.earliest,
            latest_snapshot=domain_map.latest,
        )

    async def compare_periods(
        self,
        domain: str,
        period1: str,
        period2: str,
        fetch_content: bool = False,
    ) -> PeriodComparison:
        """
        Compare two time periods for a domain.

        Args:
            domain: Target domain
            period1: First date (YYYY-MM-DD or YYYY)
            period2: Second date (YYYY-MM-DD or YYYY)
            fetch_content: If True, compare content of common URLs

        Returns:
            PeriodComparison with URL diffs
        """
        await self._ensure_clients()
        domain = self._normalize_domain(domain)

        # Normalize period format
        p1_start = period1.replace("-", "")
        p2_start = period2.replace("-", "")

        # Determine period ranges (year or specific date)
        if len(p1_start) == 4:
            p1_end = p1_start + "1231"
            p1_start = p1_start + "0101"
        else:
            p1_end = p1_start

        if len(p2_start) == 4:
            p2_end = p2_start + "1231"
            p2_start = p2_start + "0101"
        else:
            p2_end = p2_start

        # Get URLs for each period
        map1 = await self._mapper.map_domain(
            domain,
            start_date=f"{p1_start[:4]}-{p1_start[4:6] if len(p1_start) > 4 else '01'}-{p1_start[6:8] if len(p1_start) > 6 else '01'}",
            end_date=f"{p1_end[:4]}-{p1_end[4:6] if len(p1_end) > 4 else '12'}-{p1_end[6:8] if len(p1_end) > 6 else '31'}",
        )

        map2 = await self._mapper.map_domain(
            domain,
            start_date=f"{p2_start[:4]}-{p2_start[4:6] if len(p2_start) > 4 else '01'}-{p2_start[6:8] if len(p2_start) > 6 else '01'}",
            end_date=f"{p2_end[:4]}-{p2_end[4:6] if len(p2_end) > 4 else '12'}-{p2_end[6:8] if len(p2_end) > 6 else '31'}",
        )

        urls1 = {u.url for u in map1.urls}
        urls2 = {u.url for u in map2.urls}

        result = PeriodComparison(
            domain=domain,
            period1=period1,
            period2=period2,
            urls_period1=urls1,
            urls_period2=urls2,
            urls_added=urls2 - urls1,
            urls_removed=urls1 - urls2,
            urls_common=urls1 & urls2,
        )

        # Optionally compare content of common URLs
        if fetch_content and self._backdrill and result.urls_common:
            # Sample common URLs for content comparison
            sample_urls = list(result.urls_common)[:20]

            for url in sample_urls:
                try:
                    change = await self._compare_url_versions(url, period1, period2)
                    if change and change.similarity < 0.95:  # Significant change
                        result.content_changed.append(change)
                except Exception as e:
                    logger.warning(f"Failed to compare {url}: {e}")

        return result

    async def _compare_url_versions(
        self,
        url: str,
        ts1: str,
        ts2: str,
    ) -> Optional[PageChange]:
        """Compare two versions of a URL."""
        if not self._backdrill:
            return None

        # Fetch both versions
        # Note: Need to construct archive URLs with timestamps
        ts1_norm = ts1.replace("-", "")
        ts2_norm = ts2.replace("-", "")

        try:
            # Use wayback URLs directly
            url1 = f"https://web.archive.org/web/{ts1_norm}/{url}"
            url2 = f"https://web.archive.org/web/{ts2_norm}/{url}"

            result1 = await self._backdrill.fetch(url1)
            result2 = await self._backdrill.fetch(url2)

            content1 = self._extract_text(result1.html or result1.content or "")
            content2 = self._extract_text(result2.html or result2.content or "")

            if not content1 or not content2:
                return None

            # Calculate similarity
            similarity = difflib.SequenceMatcher(None, content1, content2).ratio()

            # Generate diff stats
            lines1 = content1.splitlines()
            lines2 = content2.splitlines()
            diff = list(difflib.unified_diff(lines1, lines2, n=0))

            added = sum(1 for line in diff if line.startswith('+') and not line.startswith('+++'))
            removed = sum(1 for line in diff if line.startswith('-') and not line.startswith('---'))

            # Determine change type
            if similarity > 0.99:
                change_type = "identical"
            elif similarity > 0.9:
                change_type = "minor_change"
            elif similarity > 0.5:
                change_type = "modified"
            else:
                change_type = "major_change"

            return PageChange(
                url=url,
                change_type=change_type,
                from_timestamp=ts1,
                to_timestamp=ts2,
                from_hash=self._content_hash(content1),
                to_hash=self._content_hash(content2),
                similarity=similarity,
                added_lines=added,
                removed_lines=removed,
            )

        except Exception as e:
            logger.error(f"Error comparing {url}: {e}")
            return None

    async def page_history(
        self,
        url: str,
        max_versions: int = 50,
        fetch_content: bool = False,
    ) -> PageHistory:
        """
        Get complete history of a single page.

        Args:
            url: Target URL
            max_versions: Max versions to retrieve
            fetch_content: If True, fetch and hash content

        Returns:
            PageHistory with all versions and changes
        """
        await self._ensure_clients()

        # Get all snapshots
        snapshots = await self._mapper.get_snapshots(url, limit=max_versions)

        versions = []
        for snap in snapshots:
            version = PageVersion(
                url=snap.url,
                timestamp=snap.timestamp or "",
                source=snap.source,
                status_code=snap.status_code,
                archive_url=snap.archive_url,
            )
            versions.append(version)

        # Sort by timestamp (oldest first)
        versions.sort(key=lambda v: v.timestamp)

        # Detect changes between consecutive versions
        changes = []
        prev_version = None

        for version in versions:
            if prev_version and version.content_hash and prev_version.content_hash:
                if version.content_hash != prev_version.content_hash:
                    changes.append(PageChange(
                        url=url,
                        change_type="modified",
                        from_timestamp=prev_version.timestamp,
                        to_timestamp=version.timestamp,
                        from_hash=prev_version.content_hash,
                        to_hash=version.content_hash,
                    ))
            prev_version = version

        # Count unique versions
        unique_hashes = {v.content_hash for v in versions if v.content_hash}

        return PageHistory(
            url=url,
            versions=versions,
            changes=changes,
            total_versions=len(versions),
            unique_versions=len(unique_hashes) if unique_hashes else len(versions),
            first_seen=versions[0].timestamp if versions else None,
            last_seen=versions[-1].timestamp if versions else None,
        )

    async def find_content_change(
        self,
        domain: str,
        search_text: str,
        change_type: str = "appeared",
        max_pages: int = 100,
    ) -> ContentAppearance:
        """
        Find when specific content appeared or disappeared from a domain.

        Args:
            domain: Target domain
            search_text: Text to search for
            change_type: "appeared" or "disappeared"
            max_pages: Max pages to check

        Returns:
            ContentAppearance with location and timestamp
        """
        await self._ensure_clients()
        domain = self._normalize_domain(domain)

        if not self._backdrill:
            return ContentAppearance(
                search_text=search_text,
                domain=domain,
                change_type=change_type,
                found=False,
            )

        # Get domain URLs
        domain_map = await self._mapper.map_domain(domain, limit_per_source=max_pages)

        # Group URLs by timestamp
        url_timestamps: Dict[str, List[str]] = {}
        for mapped_url in domain_map.urls:
            ts = mapped_url.timestamp
            if ts:
                if ts not in url_timestamps:
                    url_timestamps[ts] = []
                url_timestamps[ts].append(mapped_url.url)

        # Sort timestamps
        sorted_ts = sorted(url_timestamps.keys())

        # Search through time
        search_lower = search_text.lower()
        found_in: Dict[str, bool] = {}  # timestamp -> found

        # Sample timestamps (can't check everything)
        sample_ts = sorted_ts[::max(1, len(sorted_ts) // 20)]  # ~20 samples

        for ts in sample_ts:
            urls = url_timestamps[ts][:5]  # Sample URLs per timestamp

            for url in urls:
                try:
                    archive_url = f"https://web.archive.org/web/{ts}/{url}"
                    result = await self._backdrill.fetch(archive_url)
                    content = (result.html or result.content or "").lower()

                    if search_lower in content:
                        found_in[ts] = True

                        if change_type == "appeared":
                            # Found it - check if it's the first appearance
                            # by checking previous timestamp
                            idx = sorted_ts.index(ts)
                            if idx == 0 or not found_in.get(sorted_ts[idx-1], False):
                                # Extract surrounding context
                                pos = content.find(search_lower)
                                start = max(0, pos - 100)
                                end = min(len(content), pos + len(search_text) + 100)

                                return ContentAppearance(
                                    search_text=search_text,
                                    domain=domain,
                                    change_type="appeared",
                                    url=url,
                                    timestamp=ts,
                                    surrounding_text=content[start:end],
                                    found=True,
                                )
                        break
                    else:
                        found_in[ts] = False

                        if change_type == "disappeared":
                            # Not found - check if it was in previous timestamp
                            idx = sample_ts.index(ts)
                            if idx > 0 and found_in.get(sample_ts[idx-1], False):
                                return ContentAppearance(
                                    search_text=search_text,
                                    domain=domain,
                                    change_type="disappeared",
                                    url=url,
                                    timestamp=ts,
                                    found=True,
                                )

                except Exception as e:
                    logger.debug(f"Error checking {url} at {ts}: {e}")
                    continue

        return ContentAppearance(
            search_text=search_text,
            domain=domain,
            change_type=change_type,
            found=False,
        )

    async def get_domain_snapshot(
        self,
        domain: str,
        target_date: str,
    ) -> Dict[str, Any]:
        """
        Get a snapshot of what a domain looked like at a specific date.

        Args:
            domain: Target domain
            target_date: Date (YYYY-MM-DD)

        Returns:
            Dictionary with URLs, page counts, sample content
        """
        await self._ensure_clients()
        domain = self._normalize_domain(domain)

        # Get URLs around the target date
        date_parts = target_date.split("-")
        year = date_parts[0]

        domain_map = await self._mapper.map_domain(
            domain,
            start_date=f"{year}-01-01",
            end_date=f"{year}-12-31",
        )

        # Filter to closest to target date
        target_ts = target_date.replace("-", "")

        closest_urls = []
        for mapped_url in domain_map.urls:
            ts = mapped_url.timestamp or ""
            if ts.startswith(target_ts[:6]):  # Same month
                closest_urls.append(mapped_url)

        return {
            "domain": domain,
            "target_date": target_date,
            "urls_found": len(closest_urls),
            "urls": [u.url for u in closest_urls[:100]],
            "sources": list({u.source for u in closest_urls}),
        }


# Convenience functions
async def compare_domain_periods(
    domain: str,
    period1: str,
    period2: str,
) -> PeriodComparison:
    """Quick comparison between two periods."""
    async with DomainDiffer() as differ:
        return await differ.compare_periods(domain, period1, period2)


async def get_domain_evolution(domain: str) -> DomainEvolution:
    """Quick domain evolution analysis."""
    async with DomainDiffer() as differ:
        return await differ.domain_evolution(domain)


__all__ = [
    "DomainDiffer",
    "PageVersion",
    "PageChange",
    "DomainChange",
    "DomainEvolution",
    "PeriodComparison",
    "PageHistory",
    "ContentAppearance",
    "compare_domain_periods",
    "get_domain_evolution",
]
