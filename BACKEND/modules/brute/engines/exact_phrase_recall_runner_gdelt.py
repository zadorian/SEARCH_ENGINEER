"""Compatibility shim for old import style"""
try:
    from .gdelt import ExactPhraseRecallRunnerGDELT, EnhancedGDELTSearcher
except ImportError:
    from brute.engines.gdelt import ExactPhraseRecallRunnerGDELT, EnhancedGDELTSearcher

# Alias for compatibility
GDELTSearch = ExactPhraseRecallRunnerGDELT

__all__ = ['ExactPhraseRecallRunnerGDELT', 'EnhancedGDELTSearcher', 'GDELTSearch']
