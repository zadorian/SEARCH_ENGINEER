"""Compatibility shim for old import style"""
try:
    from .duckduckgo import MaxExactDuckDuckGo, DuckDuckGoFixed
except ImportError:
    from brute.engines.duckduckgo import MaxExactDuckDuckGo, DuckDuckGoFixed

__all__ = ['MaxExactDuckDuckGo', 'DuckDuckGoFixed']
