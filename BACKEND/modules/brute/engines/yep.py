#!/usr/bin/env python3
from __future__ import annotations

from typing import Any, Dict, List

try:
    from .engines import BaseEngine
except ImportError:
    from brute.engines.engines import BaseEngine

# Try to import YepExactPhraseRecallRunner, fallback to stub
try:
    from .object.exact_phrase.yep import YepExactPhraseRecallRunner
except ImportError:
    YepExactPhraseRecallRunner = None


class YepEngine(BaseEngine):
    code = 'YEP'
    name = 'Yep'

    def __init__(self):
        self._runner_cls = YepExactPhraseRecallRunner

    def is_available(self) -> bool:
        return self._runner_cls is not None

    def search(self, query: str, max_results: int = 10, **kwargs) -> List[Dict[str, Any]]:
        if not self._runner_cls:
            return []
        try:
            runner = self._runner_cls(
                phrase=query,
                max_results_per_query=max_results,
            )
            res = list(runner.run())[:max_results]
        except Exception:
            res = []
        for r in res:
            r['engine'] = self.name
            r['source'] = 'yep'
        return res
__all__ = ['YepEngine']
