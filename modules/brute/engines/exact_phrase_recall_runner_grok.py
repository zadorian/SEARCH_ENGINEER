try:
    from .grok import ExactPhraseRecallRunnerGrok
except ImportError:
    from brute.engines.grok import ExactPhraseRecallRunnerGrok
__all__ = ['ExactPhraseRecallRunnerGrok']
