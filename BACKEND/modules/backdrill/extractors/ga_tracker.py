"""
Google Analytics tracker extraction for BACKDRILL.

Extract and track GA/GTM codes from archived content:
- UA-XXXXX-X (Universal Analytics)
- G-XXXXXXX (GA4)
- GTM-XXXXXX (Tag Manager)

Consolidated from:
- LINKLATER/mapping/ga_tracker.py
"""

import re
from typing import Dict, List, Optional, Any
import aiohttp
import logging

logger = logging.getLogger(__name__)

# Regex patterns
UA_PATTERN = r'UA-\d+-\d+'
GA4_PATTERN = r'G-[A-Z0-9]{7,}'
GTM_PATTERN = r'GTM-[A-Z0-9]+'


def extract_ga_codes(content: str) -> Dict[str, List[str]]:
    """
    Extract Google Analytics codes from HTML content.

    Args:
        content: HTML content to search

    Returns:
        Dict with keys 'ua', 'ga4', 'gtm' containing lists of codes
    """
    if not content:
        return {"ua": [], "ga4": [], "gtm": []}

    return {
        "ua": list(set(re.findall(UA_PATTERN, content))),
        "ga4": list(set(re.findall(GA4_PATTERN, content))),
        "gtm": list(set(re.findall(GTM_PATTERN, content))),
    }


def classify_ga_code(code: str) -> str:
    """Classify a GA code by type."""
    if code.startswith('UA-'):
        return 'universal_analytics'
    elif code.startswith('G-'):
        return 'ga4'
    elif code.startswith('GTM-'):
        return 'tag_manager'
    return 'unknown'


class GATracker:
    """
    Google Analytics code discovery and tracking.

    Three discovery modes:
    1. Forward: Domain → GA codes (current + historical)
    2. Reverse: GA code → All domains using it
    3. Network: Domain → GA codes → Related domains

    Usage:
        tracker = GATracker()

        # Extract codes from archived content
        codes = tracker.extract("https://example.com")

        # Reverse lookup (find domains sharing a GA code)
        domains = await tracker.reverse_lookup("UA-12345-1")

        # Find related domains via shared GA codes
        related = await tracker.find_related("example.com")
    """

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        self._session = session
        self._own_session = session is None

    async def __aenter__(self):
        if self._own_session:
            self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._own_session and self._session:
            await self._session.close()

    async def _ensure_session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._own_session = True

    def extract(self, content: str) -> Dict[str, List[str]]:
        """Extract GA codes from content (convenience wrapper)."""
        return extract_ga_codes(content)

    async def discover_codes(
        self,
        domain: str,
        from_date: str = "2012-01-01",
        to_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Discover all GA codes used by a domain (current + historical).

        Uses BACKDRILL to fetch archived versions and extract codes.

        Args:
            domain: Target domain
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)

        Returns:
            {
                'domain': str,
                'current_codes': {'ua': [], 'ga4': [], 'gtm': []},
                'historical_codes': {
                    'ua': {'UA-123': {'first_seen': '...', 'last_seen': '...'}},
                    ...
                },
                'timeline': [...]
            }
        """
        from ..backdrill import Backdrill

        result = {
            'domain': domain,
            'current_codes': {'ua': [], 'ga4': [], 'gtm': []},
            'historical_codes': {'ua': {}, 'ga4': {}, 'gtm': {}},
            'timeline': []
        }

        async with Backdrill() as bd:
            # Get snapshots
            snapshots = await bd.list_snapshots(f"https://{domain}")

            # Track code appearances
            code_dates = {'ua': {}, 'ga4': {}, 'gtm': {}}

            for snap in snapshots[:50]:  # Limit to avoid rate limits
                ts = snap.get('timestamp')
                if not ts:
                    continue

                # Fetch snapshot content
                content_result = await bd.fetch(
                    f"https://{domain}",
                    prefer_source=None,
                )

                if not content_result.success:
                    continue

                content = content_result.html or content_result.content or ""
                codes = extract_ga_codes(content)

                # Format date
                formatted_date = ts[:10] if len(ts) >= 10 else ts

                # Update tracking
                for code_type in ['ua', 'ga4', 'gtm']:
                    for code in codes[code_type]:
                        if code not in code_dates[code_type]:
                            code_dates[code_type][code] = {
                                'first_seen': formatted_date,
                                'last_seen': formatted_date
                            }
                        else:
                            code_dates[code_type][code]['last_seen'] = formatted_date

                # Add to timeline
                if any(codes.values()):
                    result['timeline'].append({
                        'date': formatted_date,
                        'ua': codes['ua'],
                        'ga4': codes['ga4'],
                        'gtm': codes['gtm']
                    })

            # Set most recent as current
            if result['timeline']:
                latest = result['timeline'][-1]
                result['current_codes'] = {
                    'ua': latest.get('ua', []),
                    'ga4': latest.get('ga4', []),
                    'gtm': latest.get('gtm', [])
                }

            result['historical_codes'] = code_dates

        return result

    async def reverse_lookup(
        self,
        ga_code: str,
        limit: int = 50,
    ) -> List[str]:
        """
        Find domains using a specific GA code.

        Note: This is an expensive operation requiring many archive lookups.
        Consider using pre-indexed data from Elasticsearch instead.

        Args:
            ga_code: GA code to search for (e.g., "UA-12345-1")
            limit: Max domains to check

        Returns:
            List of domains using this code
        """
        # For now, return empty - full reverse lookup requires
        # either a pre-built index or extensive archive scanning
        logger.warning(
            "GA reverse lookup not implemented in BACKDRILL. "
            "Use GATracker from LINKLATER for full functionality."
        )
        return []

    async def find_related(
        self,
        domain: str,
        max_per_code: int = 10,
    ) -> Dict[str, List[str]]:
        """
        Find domains related via shared GA codes.

        Args:
            domain: Target domain
            max_per_code: Max related domains per code

        Returns:
            Dict mapping GA codes to lists of related domains
        """
        # Discover codes from domain
        codes_result = await self.discover_codes(domain)

        # Collect all codes
        all_codes = set()
        for code_type in ['ua', 'ga4', 'gtm']:
            all_codes.update(codes_result['current_codes'][code_type])
            all_codes.update(codes_result['historical_codes'][code_type].keys())

        # For each code, do reverse lookup
        related = {}
        for code in all_codes:
            domains = await self.reverse_lookup(code, limit=max_per_code)
            if domains:
                related[code] = domains

        return related


# Convenience functions
async def discover_ga_codes(domain: str) -> Dict[str, Any]:
    """Discover GA codes from a domain."""
    async with GATracker() as tracker:
        return await tracker.discover_codes(domain)


async def find_related_via_ga(domain: str) -> Dict[str, List[str]]:
    """Find related domains via shared GA codes."""
    async with GATracker() as tracker:
        return await tracker.find_related(domain)
