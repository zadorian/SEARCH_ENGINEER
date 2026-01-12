"""
DEEP DIVE - WARC Content Fetcher

Wraps the ccwarc_linux Go binary for fast WARC fetching.
Takes dive plans and executes them efficiently.
"""

from .diver import DeepDiver, DiveResult

__all__ = ["DeepDiver", "DiveResult"]
