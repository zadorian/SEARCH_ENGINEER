#!/usr/bin/env python3
"""
YaCy Decentralized P2P Search Engine
=====================================

Connects to local YaCy freeworld instance for federated P2P search.
- Port 8090: Freeworld network (main public YaCy P2P network)
- Searches across all connected peers globally

The freeworld network is the main YaCy public network with thousands of peers.
"""
from __future__ import annotations

import os
import logging
from typing import Any, Dict, List
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger(__name__)

try:
    from .engines import BaseEngine
except ImportError:
    try:
        from brute.engines.engines import BaseEngine
    except ImportError:
        class BaseEngine:
            code: str = 'ENG'
            name: str = 'BaseEngine'
            def search(self, query: str, max_results: int = 10, **kwargs):
                return []

# YaCy freeworld instance (main public P2P network)
YACY_FREEWORLD_URL = os.getenv("YACY_FREEWORLD_URL", "http://localhost:8090")


class YaCyEngine(BaseEngine):
    """YaCy decentralized P2P search engine - connects to freeworld network."""
    code = 'YC'
    name = 'YaCy'

    def __init__(self):
        self._available = None

    def is_available(self) -> bool:
        """Check if YaCy freeworld instance is running."""
        if self._available is not None:
            return self._available
        try:
            with httpx.Client(timeout=5) as client:
                resp = client.get(f"{YACY_FREEWORLD_URL}/Status.html")
                self._available = resp.status_code == 200
        except Exception:
            self._available = False
        return self._available

    def search(self, query: str, max_results: int = 50, **kwargs) -> List[Dict[str, Any]]:
        """
        Search YaCy freeworld P2P network.

        Args:
            query: Search query
            max_results: Maximum results to return

        Returns:
            List of search results with url, title, snippet
        """
        if not self.is_available():
            logger.warning("YaCy freeworld not available at %s", YACY_FREEWORLD_URL)
            return []

        results = []

        try:
            # YaCy search API with global resource (includes all peers)
            params = {
                "query": query,
                "resource": "global",  # Search across all connected peers
                "count": max_results,
                "contentdom": "text",
                "verify": "false",
            }

            with httpx.Client(timeout=30) as client:
                resp = client.get(
                    f"{YACY_FREEWORLD_URL}/yacysearch.json",
                    params=params
                )

                if resp.status_code != 200:
                    logger.warning("YaCy search failed: %s", resp.status_code)
                    return []

                data = resp.json()

                # Parse YaCy response format
                channels = data.get("channels", [])
                for channel in channels:
                    items = channel.get("items", [])
                    for item in items:
                        url = item.get("link", "")
                        if not url:
                            continue

                        results.append({
                            "url": url,
                            "title": item.get("title", ""),
                            "snippet": item.get("description", ""),
                            "source": "yacy",
                            "engine": self.code,
                            "yacy_host": item.get("host", ""),
                            "yacy_size": item.get("size", 0),
                        })

                        if len(results) >= max_results:
                            break

            logger.info("YaCy freeworld: %d results for '%s'", len(results), query)

        except httpx.TimeoutException:
            logger.warning("YaCy search timeout for '%s'", query)
        except Exception as e:
            logger.error("YaCy search error: %s", e)

        return results


__all__ = ['YaCyEngine']
