"""
exact_phrase_recall_runner_serdavos.py  ·  v1 ("dark web search integration")
=======================================================
Integrates SerDavos (The Onion Knight) dark web crawling and search into Brute.

Features:
* **Dark Web Discovery**: Search multiple onion search engines (Ahmia, etc.)
* **Streaming Support**: Results are yielded progressively as they're discovered
* **Tor Integration**: Seamless Tor proxy connectivity
* **Elasticsearch Storage**: Crawled pages indexed for future searches
* **Discovery Graph**: Track search-to-domain relationships

Changes from standard engines:
* Wraps SerDavos MCP server tools for dark web access
* Converts onion URLs to results compatible with Brute
* Handles Tor connectivity and error recovery
* Supports both clearnet (Ahmia) and Tor searches
"""

from __future__ import annotations

import sys
import logging
import time
from typing import Dict, List, Optional, Any, Iterator
from pathlib import Path
from datetime import datetime

# Add LINKLATER to path for SerDavos imports
try:
    # Try multiple paths for LINKLATER (local vs server)
    linklater_paths = [
        Path(__file__).parent.parent.parent.parent / "LINKLATER",  # Relative from brute
        Path("/data/LINKLATER"),  # Server absolute path
        Path(__file__).parent.parent.parent / "LINKLATER",  # Another relative attempt
    ]

    linklater_found = False
    for linklater_path in linklater_paths:
        if linklater_path.exists() and str(linklater_path) not in sys.path:
            sys.path.insert(0, str(linklater_path))
            linklater_found = True
            break

    if not linklater_found:
        # Try without adding path - maybe it's already in PYTHONPATH
        pass

    # Import directly from linklater.scraping.tor
    try:
        from scraping.tor import (
            AhmiaDiscovery,
            OnionSearchDiscovery,
            ONION_SEARCH_ENGINES,
        )
    except ImportError:
        # Try with modules prefix
        from modules.linklater.scraping.tor import (
            AhmiaDiscovery,
            OnionSearchDiscovery,
            ONION_SEARCH_ENGINES,
        )

    SERDAVOS_AVAILABLE = True
except ImportError as e:
    logging.warning(f"SerDavos not available: {e}")
    SERDAVOS_AVAILABLE = False

from .engines import StreamingEngine

logger = logging.getLogger("serdavos_engine")


class SerDavosEngine(StreamingEngine):
    """
    Dark web search engine powered by SerDavos (The Onion Knight)

    Searches onion sites using multiple engines:
    - Ahmia (clearnet access, no Tor needed)
    - OnionLand Search (via Tor)
    - Torch (via Tor)
    - Not Evil (via Tor)
    - And more...
    """

    code = 'DW'  # Dark Web
    name = 'SerDavos (Dark Web)'

    def __init__(self, use_tor: bool = True, engines: Optional[List[str]] = None):
        """
        Initialize SerDavos engine

        Args:
            use_tor: Whether to use Tor proxy for onion searches (Ahmia works without)
            engines: List of engine names to use (defaults to all available)
        """
        self.use_tor = use_tor
        self.engines = engines or list(ONION_SEARCH_ENGINES.keys()) if (SERDAVOS_AVAILABLE and ONION_SEARCH_ENGINES) else ['ahmia']
        self.tor_proxy = None

        # Simplified: Don't check Tor connectivity at init, handle at search time
        # Ahmia works without Tor, so we can always fall back to that

    def is_available(self) -> bool:
        """Check if SerDavos is available"""
        return SERDAVOS_AVAILABLE

    def search(self, query: str, max_results: int = 50, **kwargs) -> List[Dict[str, Any]]:
        """
        Execute dark web search (batch mode)

        Args:
            query: Search query string
            max_results: Maximum number of results to return (per engine)
            **kwargs: Additional parameters

        Returns:
            List of result dicts with url, title, snippet
        """
        results = list(self.search_stream(query, max_results, **kwargs))
        return results

    def search_stream(self, query: str, max_results: int = 50, **kwargs) -> Iterator[Dict[str, Any]]:
        """
        Stream dark web search results as they're discovered

        Yields:
            Dict with result data (url, title, snippet, engine, timestamp)
        """
        if not self.is_available():
            logger.warning("SerDavos not available, skipping dark web search")
            return

        logger.info(f"[SerDavos] Starting dark web search for: {query}")
        logger.info(f"[SerDavos] Using engines: {self.engines}")

        seen_urls = set()

        # Always try Ahmia first (clearnet, no Tor needed)
        if 'ahmia' in self.engines:
            try:
                ahmia = AhmiaDiscovery()
                logger.info(f"[SerDavos/Ahmia] Searching...")

                for result in ahmia.search(query, limit=max_results):
                    url = result.get('url', '')

                    if url and url not in seen_urls:
                        seen_urls.add(url)

                        yield {
                            'url': url,
                            'title': result.get('title', url),
                            'snippet': result.get('description', ''),
                            'engine': 'SerDavos/Ahmia',
                            'engine_code': 'DW',
                            'timestamp': datetime.utcnow().isoformat(),
                            'metadata': {
                                'source': 'dark_web',
                                'discovery_method': 'ahmia',
                                'onion_url': url.endswith('.onion')
                            }
                        }

                logger.info(f"[SerDavos/Ahmia] Found {len(seen_urls)} results")

            except Exception as e:
                logger.error(f"[SerDavos/Ahmia] Error: {e}")

        # Try other engines if Tor is available
        if self.use_tor and ONION_SEARCH_ENGINES:
            # Default Tor proxy
            tor_proxy = "socks5://127.0.0.1:9050"

            for engine_name in self.engines:
                if engine_name == 'ahmia':
                    continue  # Already did Ahmia

                if engine_name not in ONION_SEARCH_ENGINES:
                    logger.warning(f"[SerDavos] Unknown engine: {engine_name}")
                    continue

                try:
                    logger.info(f"[SerDavos/{engine_name}] Searching via Tor...")

                    discovery = OnionSearchDiscovery(
                        engine=engine_name,
                        proxy=tor_proxy
                    )

                    for result in discovery.search(query, limit=max_results):
                        url = result.get('url', '')

                        if url and url not in seen_urls:
                            seen_urls.add(url)

                            yield {
                                'url': url,
                                'title': result.get('title', url),
                                'snippet': result.get('description', ''),
                                'engine': f'SerDavos/{engine_name}',
                                'engine_code': 'DW',
                                'timestamp': datetime.utcnow().isoformat(),
                                'metadata': {
                                    'source': 'dark_web',
                                    'discovery_method': engine_name,
                                    'onion_url': url.endswith('.onion'),
                                    'via_tor': True
                                }
                            }

                    logger.info(f"[SerDavos/{engine_name}] Total unique results: {len(seen_urls)}")

                except Exception as e:
                    logger.error(f"[SerDavos/{engine_name}] Error: {e}")
                    continue

        logger.info(f"[SerDavos] Search complete. Total unique results: {len(seen_urls)}")

    def get_search_url(self, query: str) -> Optional[str]:
        """Generate a URL for manual search (Ahmia clearnet)"""
        return f"https://ahmia.fi/search/?q={query}"


# Create default instance
serdavos_engine = SerDavosEngine() if SERDAVOS_AVAILABLE else None


def search_dark_web(query: str, max_results: int = 50, **kwargs) -> List[Dict[str, Any]]:
    """
    Convenience function for dark web search

    Args:
        query: Search query
        max_results: Maximum results per engine
        **kwargs: Additional parameters

    Returns:
        List of results
    """
    if serdavos_engine is None:
        logger.warning("SerDavos not available")
        return []

    return serdavos_engine.search(query, max_results, **kwargs)


__all__ = ['SerDavosEngine', 'serdavos_engine', 'search_dark_web']
