"""
ModernEngineAdapter - Bridges modern engines to legacy ExactPhraseRecallRunner interface.

Modern engines use:
    engine.search(query: str, max_results: int, **kwargs) -> List[Dict]

Legacy pattern expects:
    runner = Runner(phrase=query, max_results=100, ...)
    for result in runner.run():
        yield result

This adapter allows modern engines to work with brute.py's ENGINE_CONFIG without
requiring architectural changes to either system.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Iterator, List, Optional, Type, Callable

logger = logging.getLogger(__name__)


class ModernEngineAdapter:
    """
    Adapter that wraps a modern search engine instance to provide the legacy
    ExactPhraseRecallRunner interface expected by brute.py.

    Usage:
        # Direct instantiation
        engine = SemanticScholarEngine()
        adapter = ModernEngineAdapter(engine, phrase="climate change")
        for result in adapter.run():
            process(result)

        # Via factory function
        AdaptedRunner = create_adapted_runner(SemanticScholarEngine)
        runner = AdaptedRunner(phrase="climate change", max_results=100)
        for result in runner.run():
            process(result)
    """

    def __init__(
        self,
        engine: Any,
        phrase: str,
        max_results: int = 100,
        streaming_batch_size: int = 20,
        **search_kwargs: Any
    ):
        """
        Initialize adapter with a modern engine instance.

        Args:
            engine: Modern engine instance with search(query, max_results, **kwargs) method
            phrase: Search query/phrase
            max_results: Maximum results to return
            streaming_batch_size: Yield results in batches of this size for streaming
            **search_kwargs: Additional kwargs to pass to engine.search()
        """
        self.engine = engine
        self.phrase = phrase
        self.max_results = max_results
        self.streaming_batch_size = streaming_batch_size
        self.search_kwargs = search_kwargs

        # Cache engine metadata
        self.engine_name = getattr(engine, 'name', engine.__class__.__name__)
        self.engine_code = getattr(engine, 'code', 'UN')  # Unknown if not specified

        logger.debug(
            "ModernEngineAdapter initialized: engine=%s, phrase=%s, max_results=%d",
            self.engine_name, phrase[:50], max_results
        )

    def run(self) -> Iterator[Dict[str, Any]]:
        """
        Execute search and yield results in the legacy streaming pattern.

        This method wraps the modern List[Dict] return into an Iterator[Dict]
        pattern, yielding results in batches to support streaming UX.

        Yields:
            Dict with search result data
        """
        start_time = time.time()
        total_yielded = 0

        try:
            # Call modern engine's search method
            results = self.engine.search(
                self.phrase,
                max_results=self.max_results,
                **self.search_kwargs
            )

            # Handle various return types
            if results is None:
                results = []
            elif not isinstance(results, list):
                # If engine returns iterator/generator, consume it
                results = list(results)

            logger.debug(
                "ModernEngineAdapter: %s returned %d results in %.2fs",
                self.engine_name, len(results), time.time() - start_time
            )

            # Yield results with streaming batch pattern
            batch: List[Dict[str, Any]] = []

            for result in results:
                if total_yielded >= self.max_results:
                    break

                # Ensure standard metadata is present
                enriched = self._enrich_result(result)
                batch.append(enriched)

                # Yield batch when full (enables streaming UX)
                if len(batch) >= self.streaming_batch_size:
                    for item in batch:
                        yield item
                        total_yielded += 1
                    batch = []

            # Yield remaining results
            for item in batch:
                if total_yielded >= self.max_results:
                    break
                yield item
                total_yielded += 1

        except Exception as exc:
            logger.error(
                "ModernEngineAdapter: %s search failed: %s",
                self.engine_name, exc, exc_info=True
            )
            # Don't re-raise - return empty results to allow other engines to continue
            return

        logger.debug(
            "ModernEngineAdapter: %s yielded %d results total",
            self.engine_name, total_yielded
        )

    def _enrich_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ensure result has standard metadata fields for brute.py compatibility.

        Args:
            result: Raw result from modern engine

        Returns:
            Enriched result with guaranteed standard fields
        """
        # Don't mutate original
        enriched = dict(result)

        # Ensure required fields exist
        enriched.setdefault('url', '')
        enriched.setdefault('title', 'Untitled')
        enriched.setdefault('snippet', '')

        # Add engine metadata if not present
        enriched.setdefault('engine', self.engine_name)
        enriched.setdefault('engine_code', self.engine_code)
        enriched.setdefault('engine_badge', self.engine_code)
        enriched.setdefault('source', self.engine_name.lower().replace(' ', '_'))

        return enriched


def create_adapted_runner(
    engine_class: Type[Any],
    engine_config: Optional[Dict[str, Any]] = None,
    engine_factory: Optional[Callable[[], Any]] = None
) -> Type[ModernEngineAdapter]:
    """
    Factory function that creates an adapted runner class for a modern engine.

    This allows seamless integration with ENGINE_CONFIG in brute.py by creating
    a class that matches the legacy ExactPhraseRecallRunner signature.

    Args:
        engine_class: Modern engine class (e.g., SemanticScholarEngine)
        engine_config: Optional config dict to pass to engine constructor
        engine_factory: Optional factory function to create engine instance

    Returns:
        Class that can be used as drop-in replacement for legacy runners

    Usage:
        # In ENGINE_CONFIG:
        'SE': {
            'name': 'SemanticScholar',
            'module': 'adapters.modern_engine_adapter',
            'class': 'create_adapted_runner',
            'class_factory': lambda: create_adapted_runner(SemanticScholarEngine),
            'supports_streaming': True
        }

        # Or create class directly:
        AdaptedSemanticScholar = create_adapted_runner(SemanticScholarEngine)
        runner = AdaptedSemanticScholar(phrase="query", max_results=100)
    """

    class AdaptedRunner(ModernEngineAdapter):
        """Dynamically created adapter class for a specific engine."""

        # Class-level engine reference for introspection
        _engine_class = engine_class
        _engine_config = engine_config or {}
        _engine_factory = engine_factory

        def __init__(
            self,
            phrase: str,
            max_results: int = 100,
            **kwargs: Any
        ):
            # Create engine instance
            if self._engine_factory:
                engine = self._engine_factory()
            elif self._engine_config:
                engine = engine_class(**self._engine_config)
            else:
                engine = engine_class()

            # Initialize adapter
            super().__init__(
                engine=engine,
                phrase=phrase,
                max_results=max_results,
                **kwargs
            )

    # Set class name for debugging
    AdaptedRunner.__name__ = f"Adapted{engine_class.__name__}"
    AdaptedRunner.__qualname__ = f"Adapted{engine_class.__name__}"

    return AdaptedRunner


# Pre-built adapted runners for convenience
# These can be imported directly into ENGINE_CONFIG

def _lazy_import_engines():
    """Lazy import to avoid circular dependencies."""
    from ..engines.semanticscholar import SemanticScholarEngine
    from ..engines.arxiv import ArxivEngine
    from ..engines.pubmed import PubMedEngine
    from ..engines.crossref import CrossrefEngine  # Note: Crossref, not CrossRef
    from ..engines.openalex import OpenAlexEngine
    from ..engines.gutenberg import GutenbergEngine
    from ..engines.annas_archive import AnnasArchiveEngine
    from ..engines.libgen import LibGenEngine
    from ..engines.jstor import JSTOREngine
    from ..engines.socialsearcher import SocialSearcher  # Note: SocialSearcher, not SocialSearcherEngine

    return {
        'SemanticScholarEngine': SemanticScholarEngine,
        'ArxivEngine': ArxivEngine,
        'PubMedEngine': PubMedEngine,
        'CrossrefEngine': CrossrefEngine,
        'OpenAlexEngine': OpenAlexEngine,
        'GutenbergEngine': GutenbergEngine,
        'AnnasArchiveEngine': AnnasArchiveEngine,
        'LibGenEngine': LibGenEngine,
        'JSTOREngine': JSTOREngine,
        'SocialSearcher': SocialSearcher,
    }


def get_adapted_engine(engine_name: str) -> Type[ModernEngineAdapter]:
    """
    Get pre-built adapted runner for a named engine.

    Args:
        engine_name: Name of engine (e.g., 'SemanticScholarEngine')

    Returns:
        Adapted runner class

    Example:
        AdaptedSS = get_adapted_engine('SemanticScholarEngine')
        runner = AdaptedSS(phrase="query")
    """
    engines = _lazy_import_engines()
    if engine_name not in engines:
        available = ', '.join(engines.keys())
        raise ValueError(f"Unknown engine: {engine_name}. Available: {available}")

    return create_adapted_runner(engines[engine_name])


__all__ = [
    'ModernEngineAdapter',
    'create_adapted_runner',
    'get_adapted_engine',
]
