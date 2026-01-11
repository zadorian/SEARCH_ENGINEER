"""Compatibility shim for old import style"""
try:
    from .bing import BingSearch
except ImportError:
    from brute.engines.bing import BingSearch

__all__ = ['BingSearch']
