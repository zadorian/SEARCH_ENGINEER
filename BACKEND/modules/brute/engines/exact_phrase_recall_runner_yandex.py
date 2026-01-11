"""Compatibility shim for old import style"""
try:
    from .yandex import YandexSearch
except ImportError:
    from brute.engines.yandex import YandexSearch

__all__ = ['YandexSearch']
