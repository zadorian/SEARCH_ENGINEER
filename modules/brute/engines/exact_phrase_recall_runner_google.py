"""Compatibility shim - exports ExactPhraseRecallRunner from google.py"""
try:
    from .google import ExactPhraseRecallRunner, GoogleSearch
except ImportError:
    from brute.engines.google import ExactPhraseRecallRunner, GoogleSearch

__all__ = ['ExactPhraseRecallRunner', 'GoogleSearch']
