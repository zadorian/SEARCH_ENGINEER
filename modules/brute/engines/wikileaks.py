"""WikiLeaks targeted search orchestrator."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional

try:
    from TOOLS.SEARCH_ENGINES.legacy.wikileaks import ExactPhraseRecallRunnerWikiLeaks
except Exception:
    ExactPhraseRecallRunnerWikiLeaks = None


class WikiLeaksTargetedConfig:
    document_types: Optional[List[str]] = None
    date_ranges: Optional[List[Dict[str, Any]]] = None
    max_results_per_query: int = 50
    polite_delay: float = 1.5
    use_parallel: bool = True
    max_workers: int = 3
    exception_iterations: int = 2


class WikiLeaksTargetedSearch:
    """Targeted WikiLeaks search mirroring the legacy runner behaviour."""

    operator_type = "news"
    engine_name = "wikileaks"
    engine_code = "WL"

    def __init__(self, config: Optional[WikiLeaksTargetedConfig] = None) -> None:
        if ExactPhraseRecallRunnerWikiLeaks is None:
            raise RuntimeError("WikiLeaks runner unavailable")
        self.config = config or WikiLeaksTargetedConfig()
        self._seen_urls: set[str] = set()

    def reset(self) -> None:
        self._seen_urls.clear()

    async def search(
        self,
        query: str,
        *,
        level: Optional[str] = None,
        max_results: Optional[int] = None,
        document_types: Optional[List[str]] = None,
        date_ranges: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        runner = ExactPhraseRecallRunnerWikiLeaks(
            phrase=query,
            document_types=document_types or self.config.document_types,
            date_ranges=date_ranges or self.config.date_ranges,
            max_results_per_query=self.config.max_results_per_query,
            polite_delay=self.config.polite_delay,
            use_parallel=self.config.use_parallel,
            max_workers=self.config.max_workers,
            exception_search_iterations=self.config.exception_iterations,
        )

        loop = asyncio.get_running_loop()
        results: List[Dict[str, Any]] = await loop.run_in_executor(None, runner.run_as_list)

        level_label = (level or "L1").upper()
        limit = max_results if max_results is not None else len(results)
        yielded = 0

        for item in results:
            if yielded >= limit:
                break
            url = item.get("url")
            if not url or url in self._seen_urls:
                continue
            self._seen_urls.add(url)
            item.setdefault("engine", self.engine_name)
            item.setdefault("engine_code", self.engine_code)
            item.setdefault("source", item.get("source") or self.engine_name)
            item.setdefault("targeted_search", self.operator_type)
            item.setdefault("search_level", level_label)
            yield item
            yielded += 1


__all__ = [
    "WikiLeaksTargetedConfig",
    "WikiLeaksTargetedSearch",
]
