"""
SUBMARINE Extraction Bridge

Wires SUBMARINE's WARC content to PACMAN extraction pipeline.
"""

from .pacman_bridge import extract_from_content, extract_from_results, PACMANExtractor

__all__ = ["extract_from_content", "extract_from_results", "PACMANExtractor"]
