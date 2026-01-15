"""Bing engine shim"""
try:
    from .bing import ExactPhraseRecallRunnerBing, BingSearch
except ImportError:
    from brute.engines.bing import ExactPhraseRecallRunnerBing, BingSearch
__all__ = ['ExactPhraseRecallRunnerBing', 'BingSearch']
