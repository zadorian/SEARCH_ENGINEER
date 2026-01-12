"""
LINKLATER Temporal Module

URL timeline intelligence - tracks first-seen/last-seen dates from archives.

Main exports:
- URLTimeline: Dataclass for URL temporal metadata
- TemporalAnalyzer: Analyze URL timelines from Wayback/CC

Usage:
    from modules.LINKLATER.temporal import URLTimeline, TemporalAnalyzer

    # Get timeline for a URL
    analyzer = TemporalAnalyzer()
    timeline = await analyzer.get_url_timeline("https://example.com")

    print(f"First seen: {timeline.get_first_seen()}")
    print(f"Last archived: {timeline.get_last_archived()}")
    print(f"Age in days: {timeline.age_days()}")
"""

# Re-export from temporal_core.py (canonical location)
try:
    from ..temporal_core import (
        URLTimeline,
        TemporalAnalyzer,
    )
except ImportError as e:
    # Graceful fallback if some components missing
    URLTimeline = None
    TemporalAnalyzer = None

__all__ = [
    "URLTimeline",
    "TemporalAnalyzer",
]
