"""Compatibility shim for old import style"""
try:
    from .grok import ExactPhraseRecallRunnerGrok
except ImportError:
    from brute.engines.grok import ExactPhraseRecallRunnerGrok

# Alias for compatibility
GrokSearch = ExactPhraseRecallRunnerGrok

__all__ = ['ExactPhraseRecallRunnerGrok', 'GrokSearch']
