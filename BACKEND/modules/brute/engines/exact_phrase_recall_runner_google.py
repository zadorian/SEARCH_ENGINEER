"""Compatibility shim for old import style"""
try:
    from .google import GoogleSearch
except ImportError:
    from brute.engines.google import GoogleSearch

__all__ = ['GoogleSearch']
