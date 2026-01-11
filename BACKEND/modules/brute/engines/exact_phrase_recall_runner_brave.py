"""Compatibility shim for old import style"""
try:
    from .brave import BraveSearch, ExactPhraseRecallRunnerBrave
except ImportError:
    from brute.engines.brave import BraveSearch, ExactPhraseRecallRunnerBrave

__all__ = ['BraveSearch', 'ExactPhraseRecallRunnerBrave']
