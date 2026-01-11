"""Compatibility shim for old import style"""
try:
    from .exa import ExactPhraseRecallRunnerExa
except ImportError:
    from brute.engines.exa import ExactPhraseRecallRunnerExa

# Alias for compatibility
ExaSearch = ExactPhraseRecallRunnerExa

__all__ = ['ExactPhraseRecallRunnerExa', 'ExaSearch']
