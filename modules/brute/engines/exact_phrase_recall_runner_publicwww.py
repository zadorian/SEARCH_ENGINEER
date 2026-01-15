"""Compatibility shim for old import style"""
try:
    from .publicwww import PublicWWWAPIEngine
except ImportError:
    from brute.engines.publicwww import PublicWWWAPIEngine

# Alias for compatibility
PublicWWWSearch = PublicWWWAPIEngine

__all__ = ['PublicWWWAPIEngine', 'PublicWWWSearch']
