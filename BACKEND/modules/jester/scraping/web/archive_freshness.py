"""
Archive Freshness Checker for DRILL

Before crawling a URL, check if we already have fresh data from:
- Common Crawl (CC)
- Wayback Machine (archive.org)

Configurable skip policies:
- always_skip: Never re-crawl if archived
- skip_if_recent: Skip if archived within X days
- never_skip: Always crawl but report freshness
- report_only: Just report freshness, let user decide

This integrates with LinkLater's existing Wayback support.
"""

import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
import re


class SkipPolicy(Enum):
    """Policy for skipping crawls based on archive freshness."""
    ALWAYS_SKIP = "always_skip"           # Never re-crawl if any archive exists
    SKIP_IF_RECENT = "skip_if_recent"     # Skip if archived within threshold
    NEVER_SKIP = "never_skip"             # Always crawl, but report freshness
    REPORT_ONLY = "report_only"           # Just report, user decides


@dataclass
class ArchiveFreshness:
    """Archive freshness data for a URL."""
    url: str

    # Common Crawl data
    cc_available: bool = False
    cc_last_crawl: Optional[datetime] = None
    cc_archive: Optional[str] = None  # e.g., "CC-MAIN-2024-10"
    cc_age_days: Optional[int] = None

    # Wayback Machine data
    wayback_available: bool = False
    wayback_last_snapshot: Optional[datetime] = None
    wayback_snapshot_url: Optional[str] = None
    wayback_age_days: Optional[int] = None

    # Combined verdict
    has_recent_archive: bool = False
    freshest_source: Optional[str] = None
    freshest_date: Optional[datetime] = None
    freshest_age_days: Optional[int] = None

    # Recommendation
    should_skip: bool = False
    skip_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "cc": {
                "available": self.cc_available,
                "last_crawl": self.cc_last_crawl.isoformat() if self.cc_last_crawl else None,
                "archive": self.cc_archive,
                "age_days": self.cc_age_days,
            },
            "wayback": {
                "available": self.wayback_available,
                "last_snapshot": self.wayback_last_snapshot.isoformat() if self.wayback_last_snapshot else None,
                "snapshot_url": self.wayback_snapshot_url,
                "age_days": self.wayback_age_days,
            },
            "freshest": {
                "source": self.freshest_source,
                "date": self.freshest_date.isoformat() if self.freshest_date else None,
                "age_days": self.freshest_age_days,
            },
            "should_skip": self.should_skip,
            "skip_reason": self.skip_reason,
        }


@dataclass
class FreshnessConfig:
    """Configuration for archive freshness checking."""
    skip_policy: SkipPolicy = SkipPolicy.SKIP_IF_RECENT
    recent_threshold_days: int = 90  # Consider "recent" if within this many days
    check_cc: bool = True
    check_wayback: bool = True
    timeout: int = 10  # HTTP timeout


class ArchiveFreshnessChecker:
    """
    Check if URLs have recent archive coverage before crawling.

    Integrates with LinkLater's existing Wayback and CC clients.
    """

    # CC Index API
    CC_INDEX_URL = "https://index.commoncrawl.org/CC-MAIN-2024-10-index"

    # Wayback CDX API
    WAYBACK_CDX_URL = "https://web.archive.org/cdx/search/cdx"

    def __init__(self, config: Optional[FreshnessConfig] = None):
        self.config = config or FreshnessConfig()

    async def check_freshness(
        self,
        url: str,
        config_override: Optional[FreshnessConfig] = None,
    ) -> ArchiveFreshness:
        """
        Check archive freshness for a URL.

        Args:
            url: URL to check
            config_override: Override default config for this check

        Returns:
            ArchiveFreshness with complete archive data and recommendation
        """
        config = config_override or self.config
        freshness = ArchiveFreshness(url=url)
        now = datetime.utcnow()

        # Check both archives in parallel
        tasks = []
        if config.check_cc:
            tasks.append(self._check_cc(url))
        if config.check_wayback:
            tasks.append(self._check_wayback(url))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process CC result
        if config.check_cc and len(results) > 0:
            if not isinstance(results[0], Exception) and results[0]:
                cc_data = results[0]
                freshness.cc_available = True
                freshness.cc_last_crawl = cc_data.get("timestamp")
                freshness.cc_archive = cc_data.get("archive")
                if freshness.cc_last_crawl:
                    freshness.cc_age_days = (now - freshness.cc_last_crawl).days

        # Process Wayback result
        wayback_idx = 1 if config.check_cc else 0
        if config.check_wayback and len(results) > wayback_idx:
            if not isinstance(results[wayback_idx], Exception) and results[wayback_idx]:
                wb_data = results[wayback_idx]
                freshness.wayback_available = True
                freshness.wayback_last_snapshot = wb_data.get("timestamp")
                freshness.wayback_snapshot_url = wb_data.get("snapshot_url")
                if freshness.wayback_last_snapshot:
                    freshness.wayback_age_days = (now - freshness.wayback_last_snapshot).days

        # Determine freshest archive
        candidates = []
        if freshness.cc_last_crawl:
            candidates.append(("cc", freshness.cc_last_crawl, freshness.cc_age_days))
        if freshness.wayback_last_snapshot:
            candidates.append(("wayback", freshness.wayback_last_snapshot, freshness.wayback_age_days))

        if candidates:
            # Sort by date descending (most recent first)
            candidates.sort(key=lambda x: x[1], reverse=True)
            freshness.freshest_source = candidates[0][0]
            freshness.freshest_date = candidates[0][1]
            freshness.freshest_age_days = candidates[0][2]
            freshness.has_recent_archive = freshness.freshest_age_days <= config.recent_threshold_days

        # Apply skip policy
        freshness = self._apply_policy(freshness, config)

        return freshness

    async def check_batch(
        self,
        urls: List[str],
        config_override: Optional[FreshnessConfig] = None,
        max_concurrent: int = 10,
    ) -> List[ArchiveFreshness]:
        """
        Check freshness for multiple URLs.

        Args:
            urls: URLs to check
            config_override: Override default config
            max_concurrent: Max concurrent checks

        Returns:
            List of ArchiveFreshness objects
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def check_with_limit(url: str) -> ArchiveFreshness:
            async with semaphore:
                return await self.check_freshness(url, config_override)

        return await asyncio.gather(*[check_with_limit(url) for url in urls])

    async def _check_cc(self, url: str) -> Optional[Dict[str, Any]]:
        """Check Common Crawl index for URL."""
        try:
            # Extract domain for CC query
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc

            # Try CC CDX API
            params = {
                "url": url,
                "output": "json",
                "limit": 1,
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.CC_INDEX_URL,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout),
                ) as resp:
                    if resp.status != 200:
                        return None

                    text = await resp.text()
                    if not text.strip():
                        return None

                    # Parse first line as JSON
                    import json
                    for line in text.strip().split('\n'):
                        if line.strip():
                            data = json.loads(line)
                            timestamp_str = data.get("timestamp", "")
                            if timestamp_str:
                                # Parse CC timestamp (YYYYMMDDhhmmss)
                                try:
                                    timestamp = datetime.strptime(timestamp_str[:14], "%Y%m%d%H%M%S")
                                    return {
                                        "timestamp": timestamp,
                                        "archive": data.get("filename", "").split('/')[0] if data.get("filename") else None,
                                    }
                                except ValueError:
                                    pass
                            break

        except Exception as e:
            print(f"[FreshnessChecker] CC check failed for {url}: {e}")

        return None

    async def _check_wayback(self, url: str) -> Optional[Dict[str, Any]]:
        """Check Wayback Machine for URL."""
        try:
            params = {
                "url": url,
                "output": "json",
                "limit": 1,
                "fl": "timestamp,original",
                "sort": "timestamp:desc",  # Most recent first
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.WAYBACK_CDX_URL,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout),
                ) as resp:
                    if resp.status != 200:
                        return None

                    text = await resp.text()
                    lines = text.strip().split('\n')

                    # Skip header line, get first result
                    for line in lines[1:]:  # Skip header
                        if not line.strip():
                            continue

                        parts = line.split()
                        if len(parts) >= 1:
                            timestamp_str = parts[0]
                            try:
                                # Parse Wayback timestamp (YYYYMMDDhhmmss)
                                timestamp = datetime.strptime(timestamp_str[:14], "%Y%m%d%H%M%S")
                                snapshot_url = f"https://web.archive.org/web/{timestamp_str}/{url}"
                                return {
                                    "timestamp": timestamp,
                                    "snapshot_url": snapshot_url,
                                }
                            except ValueError:
                                pass
                        break

        except Exception as e:
            print(f"[FreshnessChecker] Wayback check failed for {url}: {e}")

        return None

    def _apply_policy(
        self,
        freshness: ArchiveFreshness,
        config: FreshnessConfig,
    ) -> ArchiveFreshness:
        """Apply skip policy to freshness data."""

        if config.skip_policy == SkipPolicy.ALWAYS_SKIP:
            if freshness.cc_available or freshness.wayback_available:
                freshness.should_skip = True
                freshness.skip_reason = f"Archive exists ({freshness.freshest_source}, {freshness.freshest_age_days} days old)"

        elif config.skip_policy == SkipPolicy.SKIP_IF_RECENT:
            if freshness.has_recent_archive:
                freshness.should_skip = True
                freshness.skip_reason = f"Recent archive in {freshness.freshest_source} ({freshness.freshest_age_days} days old, threshold: {config.recent_threshold_days})"
            elif freshness.freshest_date:
                freshness.skip_reason = f"Archive exists but old ({freshness.freshest_age_days} days > {config.recent_threshold_days} threshold)"

        elif config.skip_policy == SkipPolicy.NEVER_SKIP:
            freshness.should_skip = False
            if freshness.freshest_date:
                freshness.skip_reason = f"Archive available in {freshness.freshest_source} ({freshness.freshest_age_days} days old) but skip disabled"

        elif config.skip_policy == SkipPolicy.REPORT_ONLY:
            freshness.should_skip = False
            if freshness.freshest_date:
                freshness.skip_reason = f"Archive: {freshness.freshest_source} ({freshness.freshest_age_days} days old) - User decision required"
            else:
                freshness.skip_reason = "No archive found - Crawl recommended"

        return freshness


class SmartCrawlDecider:
    """
    Integrates archive freshness into crawl decisions.

    Use this in DRILL crawler to decide whether to crawl each URL.
    """

    def __init__(
        self,
        skip_policy: SkipPolicy = SkipPolicy.SKIP_IF_RECENT,
        recent_threshold_days: int = 90,
    ):
        self.checker = ArchiveFreshnessChecker(
            FreshnessConfig(
                skip_policy=skip_policy,
                recent_threshold_days=recent_threshold_days,
            )
        )

        # Track decisions for reporting
        self.decisions: List[ArchiveFreshness] = []

    async def should_crawl(self, url: str) -> Tuple[bool, ArchiveFreshness]:
        """
        Decide if a URL should be crawled.

        Returns:
            Tuple of (should_crawl: bool, freshness_data: ArchiveFreshness)
        """
        freshness = await self.checker.check_freshness(url)
        self.decisions.append(freshness)

        # Invert should_skip for should_crawl
        return (not freshness.should_skip, freshness)

    async def filter_urls(
        self,
        urls: List[str],
        max_concurrent: int = 10,
    ) -> Tuple[List[str], List[ArchiveFreshness]]:
        """
        Filter a list of URLs, returning those that should be crawled.

        Returns:
            Tuple of (urls_to_crawl, all_freshness_data)
        """
        freshness_data = await self.checker.check_batch(urls, max_concurrent=max_concurrent)
        self.decisions.extend(freshness_data)

        urls_to_crawl = [
            f.url for f in freshness_data if not f.should_skip
        ]

        return urls_to_crawl, freshness_data

    def get_report(self) -> Dict[str, Any]:
        """Generate a report of all crawl decisions."""
        skipped = [d for d in self.decisions if d.should_skip]
        crawled = [d for d in self.decisions if not d.should_skip]

        return {
            "total_checked": len(self.decisions),
            "to_skip": len(skipped),
            "to_crawl": len(crawled),
            "skip_rate": f"{len(skipped)/len(self.decisions)*100:.1f}%" if self.decisions else "0%",
            "by_source": {
                "cc_available": sum(1 for d in self.decisions if d.cc_available),
                "wayback_available": sum(1 for d in self.decisions if d.wayback_available),
            },
            "skipped_urls": [
                {
                    "url": d.url,
                    "reason": d.skip_reason,
                    "archive_age_days": d.freshest_age_days,
                }
                for d in skipped[:50]  # Limit to first 50
            ],
            "stale_archives": [
                {
                    "url": d.url,
                    "archive": d.freshest_source,
                    "age_days": d.freshest_age_days,
                    "date": d.freshest_date.isoformat() if d.freshest_date else None,
                }
                for d in self.decisions
                if d.freshest_age_days and d.freshest_age_days > 365
            ][:50],
        }


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

async def check_url_freshness(url: str) -> ArchiveFreshness:
    """Quick freshness check for a single URL."""
    checker = ArchiveFreshnessChecker()
    return await checker.check_freshness(url)


async def filter_for_crawling(
    urls: List[str],
    recent_days: int = 90,
) -> Tuple[List[str], Dict[str, Any]]:
    """
    Filter URLs, skipping those with recent archives.

    Args:
        urls: URLs to filter
        recent_days: Skip if archived within this many days

    Returns:
        Tuple of (urls_to_crawl, report)
    """
    decider = SmartCrawlDecider(
        skip_policy=SkipPolicy.SKIP_IF_RECENT,
        recent_threshold_days=recent_days,
    )

    to_crawl, _ = await decider.filter_urls(urls)
    report = decider.get_report()

    return to_crawl, report


# ============================================================================
# CLI
# ============================================================================

async def main():
    """CLI for testing archive freshness checking."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Archive Freshness Checker")
    parser.add_argument("urls", nargs="+", help="URLs to check")
    parser.add_argument("--policy", choices=["always_skip", "skip_if_recent", "never_skip", "report_only"],
                        default="skip_if_recent", help="Skip policy")
    parser.add_argument("--threshold", type=int, default=90, help="Recent threshold in days")
    parser.add_argument("--output", help="Output JSON file")

    args = parser.parse_args()

    policy_map = {
        "always_skip": SkipPolicy.ALWAYS_SKIP,
        "skip_if_recent": SkipPolicy.SKIP_IF_RECENT,
        "never_skip": SkipPolicy.NEVER_SKIP,
        "report_only": SkipPolicy.REPORT_ONLY,
    }

    config = FreshnessConfig(
        skip_policy=policy_map[args.policy],
        recent_threshold_days=args.threshold,
    )

    checker = ArchiveFreshnessChecker(config)

    print(f"\n{'='*60}")
    print(f"Archive Freshness Check")
    print(f"Policy: {args.policy}, Threshold: {args.threshold} days")
    print(f"{'='*60}\n")

    results = []
    for url in args.urls:
        print(f"Checking: {url}")
        freshness = await checker.check_freshness(url)
        results.append(freshness.to_dict())

        print(f"  CC: {'✓' if freshness.cc_available else '✗'} ", end="")
        if freshness.cc_available:
            print(f"({freshness.cc_age_days} days old)")
        else:
            print()

        print(f"  Wayback: {'✓' if freshness.wayback_available else '✗'} ", end="")
        if freshness.wayback_available:
            print(f"({freshness.wayback_age_days} days old)")
        else:
            print()

        print(f"  Should skip: {freshness.should_skip}")
        print(f"  Reason: {freshness.skip_reason}")
        print()

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"Saved to: {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
