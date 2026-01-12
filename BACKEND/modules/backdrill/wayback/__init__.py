"""
Wayback Machine submodule for BACKDRILL.

Provides:
- CDX API queries (timestamps, availability)
- Content fetching (archived pages)
- Save Page Now API

SOURCE FILES:
- wayback.py ← LINKLATER/archives/optimal_archive.py (WaybackClient parts)
- wayback.py ← SUBMARINE/sastre_submarine.py WaybackFetcher class
"""

from .wayback import Wayback

__all__ = ["Wayback"]
