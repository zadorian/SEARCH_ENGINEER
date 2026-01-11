"""Compatibility shim for old import style"""
try:
    from .socialsearcher import SocialSearcher
except ImportError:
    from brute.engines.socialsearcher import SocialSearcher

# Alias for compatibility
SocialSearcherSearch = SocialSearcher

__all__ = ['SocialSearcher', 'SocialSearcherSearch']
