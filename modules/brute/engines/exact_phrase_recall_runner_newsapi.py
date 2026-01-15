try:
    from .newsapi import ExactPhraseRecallRunnerNewsAPI
except ImportError:
    from brute.engines.newsapi import ExactPhraseRecallRunnerNewsAPI
__all__ = ['ExactPhraseRecallRunnerNewsAPI']
