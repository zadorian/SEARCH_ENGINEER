"""Yandex engine shim"""
try:
    from .yandex import ExactPhraseRecallRunnerYandex, YandexSearch
except ImportError:
    from brute.engines.yandex import ExactPhraseRecallRunnerYandex, YandexSearch
__all__ = ['ExactPhraseRecallRunnerYandex', 'YandexSearch']
