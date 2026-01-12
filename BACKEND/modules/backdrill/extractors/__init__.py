"""
Content extractors for BACKDRILL.

Specialized extractors for archived content:
- GA Tracker: Google Analytics code extraction (UA, GA4, GTM)

SOURCE FILES:
- ga_tracker.py ← LINKLATER/mapping/ga_tracker.py
"""

from .ga_tracker import extract_ga_codes, GATracker

__all__ = ["extract_ga_codes", "GATracker"]
