"""
Proxy Pool Manager for BRUTE Searches and BACKDRILL
====================================================

Rotates between:
1. Apify residential proxies (good for SERP scraping)
2. Brightdata proxies (when zone credentials are configured)
3. Direct connection (server IP - use sparingly for rate-limited APIs)

Usage:
    from brute.infrastructure.proxy_pool import ProxyPool, get_proxy_for_engine

    # Get a proxy for a specific engine
    proxy = get_proxy_for_engine('google')  # Returns dict like {'http': '...', 'https': '...'}

    # Or use the pool directly
    pool = ProxyPool()
    proxy = pool.get_next()  # Round-robin rotation
    proxy = pool.get_random()  # Random selection
"""

import os
import random
import threading
import time
import logging
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

logger = logging.getLogger(__name__)


class ProxyType(Enum):
    APIFY_RESIDENTIAL = "apify_residential"
    APIFY_DATACENTER = "apify_datacenter"
    BRIGHTDATA_RESIDENTIAL = "brightdata_residential"
    BRIGHTDATA_DATACENTER = "brightdata_datacenter"
    FREE_HTTP = "free_http"  # Free public proxies
    FREE_SOCKS = "free_socks"
    DIRECT = "direct"


@dataclass
class ProxyConfig:
    """Configuration for a single proxy."""
    name: str
    proxy_type: ProxyType
    url: Optional[str] = None  # Full proxy URL (http://user:pass@host:port)
    weight: float = 1.0  # Higher weight = more likely to be selected
    enabled: bool = True

    # Rate limiting
    requests_per_minute: int = 60
    last_request_time: float = 0
    request_count: int = 0

    # Health tracking
    success_count: int = 0
    failure_count: int = 0
    last_failure_time: float = 0
    consecutive_failures: int = 0

    def get_proxy_dict(self) -> Optional[Dict[str, str]]:
        """Return proxy dict for requests library."""
        if self.url is None:
            return None  # Direct connection
        return {
            'http': self.url,
            'https': self.url
        }

    def record_success(self):
        """Record a successful request."""
        self.success_count += 1
        self.consecutive_failures = 0
        self.last_request_time = time.time()
        self.request_count += 1

    def record_failure(self):
        """Record a failed request."""
        self.failure_count += 1
        self.consecutive_failures += 1
        self.last_failure_time = time.time()

        # Disable proxy after 5 consecutive failures
        if self.consecutive_failures >= 5:
            logger.warning(f"Disabling proxy {self.name} after {self.consecutive_failures} failures")
            self.enabled = False

    def is_rate_limited(self) -> bool:
        """Check if we should wait before using this proxy."""
        if self.requests_per_minute <= 0:
            return False

        now = time.time()
        # Reset counter every minute
        if now - self.last_request_time > 60:
            self.request_count = 0
            return False

        return self.request_count >= self.requests_per_minute

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 1.0
        return self.success_count / total


class ProxyPool:
    """
    Manages a pool of proxies with rotation, health checking, and rate limiting.
    """

    def __init__(self, load_from_env: bool = True):
        self.proxies: List[ProxyConfig] = []
        self._lock = threading.Lock()
        self._round_robin_index = 0

        # Engine-specific proxy preferences
        # Some engines work better with certain proxy types
        self.engine_preferences: Dict[str, List[ProxyType]] = {
            # SERP engines - use residential proxies
            'google': [ProxyType.APIFY_RESIDENTIAL, ProxyType.BRIGHTDATA_RESIDENTIAL],
            'bing': [ProxyType.APIFY_RESIDENTIAL, ProxyType.BRIGHTDATA_RESIDENTIAL],
            'brave': [ProxyType.APIFY_DATACENTER, ProxyType.DIRECT],  # Brave API works with datacenter
            'duckduckgo': [ProxyType.APIFY_RESIDENTIAL, ProxyType.BRIGHTDATA_RESIDENTIAL],
            'yandex': [ProxyType.APIFY_RESIDENTIAL],  # Already configured for Russia
            'baidu': [ProxyType.APIFY_RESIDENTIAL, ProxyType.BRIGHTDATA_RESIDENTIAL],
            'qwant': [ProxyType.APIFY_RESIDENTIAL, ProxyType.DIRECT],

            # Archive/Wayback - mix to avoid rate limits
            'wayback': [ProxyType.APIFY_DATACENTER, ProxyType.DIRECT, ProxyType.APIFY_RESIDENTIAL],
            'commoncrawl': [ProxyType.DIRECT, ProxyType.APIFY_DATACENTER],
            'memento': [ProxyType.APIFY_DATACENTER, ProxyType.DIRECT],

            # APIs with keys - direct is fine
            'newsapi': [ProxyType.DIRECT],
            'serpapi': [ProxyType.DIRECT],
            'pubmed': [ProxyType.DIRECT],
            'arxiv': [ProxyType.DIRECT],
            'crossref': [ProxyType.DIRECT],
            'openalex': [ProxyType.DIRECT],

            # Default fallback
            'default': [ProxyType.APIFY_RESIDENTIAL, ProxyType.DIRECT],
        }

        if load_from_env:
            self._load_from_env()

    def _load_from_env(self):
        """Load proxy configurations from environment variables."""

        # Always add direct connection option
        self.proxies.append(ProxyConfig(
            name="direct",
            proxy_type=ProxyType.DIRECT,
            url=None,
            weight=0.3,  # Lower weight - prefer proxies for scraping
            requests_per_minute=30,  # Be conservative with server IP
        ))

        # Apify Residential Proxy
        apify_host = os.getenv('APIFY_PROXY_HOST', 'proxy.apify.com')
        apify_port = os.getenv('APIFY_PROXY_PORT', '8000')
        apify_username = os.getenv('APIFY_PROXY_USERNAME')
        apify_password = os.getenv('APIFY_PROXY_PASSWORD')

        if apify_password:
            # Generic residential proxy (no country restriction)
            generic_username = "groups-RESIDENTIAL"
            apify_url = f"http://{generic_username}:{apify_password}@{apify_host}:{apify_port}"
            self.proxies.append(ProxyConfig(
                name="apify_residential",
                proxy_type=ProxyType.APIFY_RESIDENTIAL,
                url=apify_url,
                weight=1.0,
                requests_per_minute=120,
            ))
            logger.info("Loaded Apify residential proxy")

            # Datacenter proxy (BUYPROXIES94952 group)
            dc_username = "groups-BUYPROXIES94952"
            apify_dc_url = f"http://{dc_username}:{apify_password}@{apify_host}:{apify_port}"
            self.proxies.append(ProxyConfig(
                name="apify_datacenter",
                proxy_type=ProxyType.APIFY_DATACENTER,
                url=apify_dc_url,
                weight=0.8,
                requests_per_minute=200,
            ))
            logger.info("Loaded Apify datacenter proxy (BUYPROXIES94952)")

        # Yandex-specific proxy (Russia IP) - use residential with country-ru
        if apify_password:
            yandex_username = "groups-RESIDENTIAL,country-ru"
            yandex_url = f"http://{yandex_username}:{apify_password}@{apify_host}:{apify_port}"
            self.proxies.append(ProxyConfig(
                name="apify_yandex",
                proxy_type=ProxyType.APIFY_RESIDENTIAL,
                url=yandex_url,
                weight=0.5,  # Only use for Yandex
                requests_per_minute=60,
            ))
            logger.info("Loaded Yandex-specific proxy (Russia)")

        # Brightdata Proxy
        # Note: Brightdata needs zone credentials, not just API key
        # Format: brd-customer-{CUSTOMER_ID}-zone-{ZONE_NAME}:{ZONE_PASSWORD}@brd.superproxy.io:{PORT}
        brightdata_username = os.getenv('BRIGHTDATA_PROXY_USERNAME')
        brightdata_password = os.getenv('BRIGHTDATA_PROXY_PASSWORD')
        brightdata_host = os.getenv('BRIGHTDATA_PROXY_HOST', 'brd.superproxy.io')
        brightdata_port = os.getenv('BRIGHTDATA_PROXY_PORT', '22225')

        if brightdata_username and brightdata_password:
            brightdata_url = f"http://{brightdata_username}:{brightdata_password}@{brightdata_host}:{brightdata_port}"
            self.proxies.append(ProxyConfig(
                name="brightdata_residential",
                proxy_type=ProxyType.BRIGHTDATA_RESIDENTIAL,
                url=brightdata_url,
                weight=1.0,
                requests_per_minute=100,
            ))
            logger.info("Loaded Brightdata residential proxy")
        else:
            logger.info("Brightdata proxy not configured (needs BRIGHTDATA_PROXY_USERNAME and BRIGHTDATA_PROXY_PASSWORD)")

        logger.info(f"Proxy pool initialized with {len(self.proxies)} proxies: {[p.name for p in self.proxies]}")

    def load_free_proxies(self, max_proxies: int = 20, run_actor: bool = False) -> int:
        """
        Load free proxies from Apify proxy scraper's last dataset.

        Args:
            max_proxies: Maximum free proxies to add
            run_actor: If True, run the actor first (slow). If False, use last dataset.

        Returns number of proxies added.
        """
        added = 0
        apify_token = os.getenv('APIFY_API_TOKEN') or os.getenv('APIFY_TOKEN')

        if not apify_token:
            logger.warning("No APIFY_API_TOKEN - cannot fetch free proxies")
            return 0

        try:
            import urllib.request
            import json

            actor_id = "mstephen190~proxy-scraper"

            if run_actor:
                # Run actor synchronously (slow - 60-120s)
                url = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items?token={apify_token}"
                data = json.dumps({
                    "testProxies": True,
                    "testTimeout": 3000,
                    "maxProxies": max_proxies * 3,
                }).encode()
                req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
                logger.info("Running proxy scraper actor (this takes ~60s)...")
                resp = urllib.request.urlopen(req, timeout=180)
            else:
                # Get last dataset (fast)
                url = f"https://api.apify.com/v2/acts/{actor_id}/runs/last/dataset/items?token={apify_token}"
                logger.info("Fetching free proxies from last run...")
                resp = urllib.request.urlopen(url, timeout=15)

            proxies_data = json.loads(resp.read().decode())
            logger.info(f"Got {len(proxies_data)} proxies from Apify")

            # Add working proxies
            # Filter for anonymous/elite proxies first (avoid transparent proxies)
            prioritized = sorted(proxies_data, key=lambda x: 0 if x.get('anonymity', '') in ('elite proxy', 'anonymous') else 1)

            for i, p in enumerate(prioritized):
                if added >= max_proxies:
                    break

                # Skip if tested and not working
                if 'working' in p and not p['working']:
                    continue

                # Skip transparent proxies (reveal your IP)
                if p.get('anonymity', '').lower() == 'transparent':
                    continue

                # Support both formats: 'ip'/'host' and 'port'
                ip = p.get('host') or p.get('ip', '')
                port = str(p.get('port', ''))
                protocol = p.get('protocol', 'http').lower()

                if not ip or not port:
                    # Try 'full' format like '1.2.3.4:8080'
                    full = p.get('full', '')
                    if ':' in full:
                        ip, port = full.rsplit(':', 1)
                    else:
                        continue

                proxy_url = f"{protocol}://{ip}:{port}"
                proxy_type = ProxyType.FREE_SOCKS if 'socks' in protocol else ProxyType.FREE_HTTP
                country = p.get('country', 'XX')[:2] if p.get('country') else 'XX'

                self.proxies.append(ProxyConfig(
                    name=f"free_{added}_{country}",
                    proxy_type=proxy_type,
                    url=proxy_url,
                    weight=0.2,  # Lower weight than paid proxies
                    requests_per_minute=15,  # Conservative rate limit
                ))
                added += 1

            logger.info(f"Added {added} free proxies to pool")

        except Exception as e:
            logger.warning(f"Failed to load free proxies: {e}")

        return added

    def add_proxy(self, config: ProxyConfig):
        """Add a proxy to the pool."""
        with self._lock:
            self.proxies.append(config)

    def get_available_proxies(self, proxy_types: Optional[List[ProxyType]] = None, exclude_special: bool = True) -> List[ProxyConfig]:
        """Get list of available (enabled, not rate-limited) proxies.

        Args:
            proxy_types: Filter by proxy types
            exclude_special: Exclude special-purpose proxies (yandex, etc.) from general pool
        """
        available = []
        for proxy in self.proxies:
            if not proxy.enabled:
                continue
            if proxy.is_rate_limited():
                continue
            if proxy_types and proxy.proxy_type not in proxy_types:
                continue
            # Exclude special-purpose proxies from general pool
            if exclude_special and proxy.name in ('apify_yandex',):
                continue
            available.append(proxy)
        return available

    def get_next(self, proxy_types: Optional[List[ProxyType]] = None) -> Optional[ProxyConfig]:
        """Get next proxy using round-robin rotation."""
        available = self.get_available_proxies(proxy_types)
        if not available:
            # Fallback to any enabled proxy
            available = [p for p in self.proxies if p.enabled]
        if not available:
            return None

        with self._lock:
            self._round_robin_index = (self._round_robin_index + 1) % len(available)
            return available[self._round_robin_index]

    def get_random(self, proxy_types: Optional[List[ProxyType]] = None) -> Optional[ProxyConfig]:
        """Get a random proxy, weighted by success rate and configured weight."""
        available = self.get_available_proxies(proxy_types)
        if not available:
            available = [p for p in self.proxies if p.enabled]
        if not available:
            return None

        # Calculate weighted probabilities
        weights = [p.weight * p.success_rate for p in available]
        total_weight = sum(weights)
        if total_weight == 0:
            return random.choice(available)

        # Weighted random selection
        r = random.uniform(0, total_weight)
        cumulative = 0
        for proxy, weight in zip(available, weights):
            cumulative += weight
            if r <= cumulative:
                return proxy

        return available[-1]

    def get_for_engine(self, engine_code: str) -> Optional[ProxyConfig]:
        """Get the best proxy for a specific engine."""
        engine_code = engine_code.lower()

        # Get preferred proxy types for this engine
        preferred_types = self.engine_preferences.get(
            engine_code,
            self.engine_preferences['default']
        )

        # Special case for Yandex - use Russia proxy
        if engine_code == 'yandex':
            for proxy in self.proxies:
                if proxy.name == 'apify_yandex' and proxy.enabled:
                    return proxy

        # Try to get a proxy of the preferred type
        return self.get_random(preferred_types)

    def get_stats(self) -> Dict:
        """Get statistics about the proxy pool."""
        return {
            'total_proxies': len(self.proxies),
            'enabled_proxies': len([p for p in self.proxies if p.enabled]),
            'proxies': [
                {
                    'name': p.name,
                    'type': p.proxy_type.value,
                    'enabled': p.enabled,
                    'success_rate': round(p.success_rate, 2),
                    'requests': p.success_count + p.failure_count,
                    'consecutive_failures': p.consecutive_failures,
                }
                for p in self.proxies
            ]
        }


# Global pool instance
_global_pool: Optional[ProxyPool] = None
_pool_lock = threading.Lock()


def get_pool() -> ProxyPool:
    """Get or create the global proxy pool."""
    global _global_pool
    if _global_pool is None:
        with _pool_lock:
            if _global_pool is None:
                _global_pool = ProxyPool()
    return _global_pool


def get_proxy_for_engine(engine_code: str) -> Optional[Dict[str, str]]:
    """
    Convenience function to get proxy dict for an engine.

    Usage:
        proxies = get_proxy_for_engine('google')
        response = requests.get(url, proxies=proxies)
    """
    pool = get_pool()
    config = pool.get_for_engine(engine_code)
    if config:
        return config.get_proxy_dict()
    return None


def get_proxy_config_for_engine(engine_code: str) -> Optional[ProxyConfig]:
    """Get the ProxyConfig object for tracking success/failure."""
    pool = get_pool()
    return pool.get_for_engine(engine_code)


def record_proxy_result(proxy_config: Optional[ProxyConfig], success: bool):
    """Record the result of a request using a proxy."""
    if proxy_config:
        if success:
            proxy_config.record_success()
        else:
            proxy_config.record_failure()


# Async support
class AsyncProxyPool:
    """Async wrapper for proxy pool with aiohttp support."""

    def __init__(self, pool: Optional[ProxyPool] = None):
        self.pool = pool or get_pool()

    def get_connector_kwargs(self, engine_code: str) -> Dict:
        """
        Get kwargs for aiohttp.ClientSession with proxy.

        Usage:
            async with aiohttp.ClientSession(**pool.get_connector_kwargs('google')) as session:
                async with session.get(url) as response:
                    ...
        """
        config = self.pool.get_for_engine(engine_code)
        if config and config.url:
            return {'proxy': config.url}
        return {}

    def get_request_kwargs(self, engine_code: str) -> Dict:
        """
        Get kwargs for individual aiohttp request with proxy.

        Usage:
            async with session.get(url, **pool.get_request_kwargs('google')) as response:
                ...
        """
        return self.get_connector_kwargs(engine_code)


def get_async_pool() -> AsyncProxyPool:
    """Get async proxy pool wrapper."""
    return AsyncProxyPool(get_pool())


if __name__ == '__main__':
    # Test the proxy pool
    from dotenv import load_dotenv
    load_dotenv('/data/SEARCH_ENGINEER/.env')

    pool = ProxyPool()
    print("\n=== Proxy Pool Stats ===")
    stats = pool.get_stats()
    print(f"Total proxies: {stats['total_proxies']}")
    print(f"Enabled: {stats['enabled_proxies']}")

    print("\n=== Configured Proxies ===")
    for p in stats['proxies']:
        print(f"  {p['name']}: {p['type']} (enabled={p['enabled']})")

    print("\n=== Engine Proxy Selection ===")
    test_engines = ['google', 'bing', 'yandex', 'wayback', 'newsapi', 'default']
    for engine in test_engines:
        config = pool.get_for_engine(engine)
        proxy_dict = config.get_proxy_dict() if config else None
        proxy_name = config.name if config else "None"
        print(f"  {engine}: {proxy_name}")
