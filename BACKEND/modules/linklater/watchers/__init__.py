"""
LINKLATER Watchers Module

Haiku-based extraction pipeline for watcher surveillance nodes.
"""

from .watcher_extraction import (
    check_source_against_watchers,
    check_source_against_watchers_batch,
    process_watchers_batch,
)

__all__ = [
    "check_source_against_watchers",
    "check_source_against_watchers_batch",
    "process_watchers_batch",
]
