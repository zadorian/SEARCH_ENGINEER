#!/usr/bin/env python3
"""
BruteSearchOptimal - Production-grade brute search with intelligent routing.

This is the OPTIMAL version of brute search that integrates:
1. QueryRouter - Multi-axis analysis for intelligent engine selection (10-15 vs 65)
2. CascadeExecutor - 3-wave execution for progressive streaming
3. ResultRanker - Confidence scoring for quality ranking

Performance targets:
- First results in 10-15 seconds (vs 120+ seconds baseline)
- 87% faster searches through intelligent routing
- Same maximum recall through exhaustive eventual search
- Professional UX with progress streaming

Usage:
    from brute.infrastructure.brute_optimal import BruteSearchOptimal

    brute = BruteSearchOptimal(performance_mode='balanced')
    results = brute.search("climate change research")

    # Or streaming:
    for wave, results in brute.search_streaming("climate change"):
        process_results(results)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generator, Iterator, List, Optional, Tuple

# Import components
import sys
from pathlib import Path

# Ensure cymonides is importable
CYMONIDES_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CYMONIDES_ROOT))

try:
    from brute.routing.query_router import QueryRouter, EngineRecommendation
    from brute.routing.axis_analyzer import SubjectType
    from brute.execution.cascade_executor import (
        CascadeExecutor, WavePhase, ExecutionResult, WaveResult
    )
    from brute.ranking.result_ranker import ResultRanker, RankedResult
except ImportError:
    from ..routing.query_router import QueryRouter, EngineRecommendation
    from ..routing.axis_analyzer import SubjectType
    from ..execution.cascade_executor import (
        CascadeExecutor, WavePhase, ExecutionResult, WaveResult
    )
    from ..ranking.result_ranker import ResultRanker, RankedResult

logger = logging.getLogger(__name__)


@dataclass
class SearchProgress:
    """Progress update during search."""
    wave: WavePhase
    engines_completed: int
    engines_total: int
    results_so_far: int
    elapsed_ms: float
    message: str


@dataclass
class OptimalSearchResult:
    """Complete search result with metadata."""
    query: str
    results: List[RankedResult]
    total_results: int
    unique_urls: int

    # Routing metadata
    engines_selected: List[str]
    engines_succeeded: List[str]
    engines_failed: List[str]
    query_intent: str
    query_complexity: float

    # Timing
    total_time_ms: float
    routing_time_ms: float
    execution_time_ms: float
    ranking_time_ms: float

    # Wave breakdown
    wave_results: List[WaveResult] = field(default_factory=list)


# Progress callback type
ProgressCallback = Callable[[SearchProgress], None]


class BruteSearchOptimal:
    """
    Production-grade brute search with intelligent optimization.

    Combines query routing, cascade execution, and result ranking
    for optimal performance while maintaining maximum recall.
    """

    def __init__(
        self,
        engine_registry: Optional[Dict[str, Any]] = None,
        performance_mode: str = 'balanced',
        max_results_per_engine: int = 100,
        max_engines: int = 15,
        deduplicate: bool = True,
        progress_callback: Optional[ProgressCallback] = None
    ):
        """
        Initialize optimal brute search.

        Args:
            engine_registry: Dict mapping engine codes to runner classes
            performance_mode: 'speed', 'balanced', or 'comprehensive'
            max_results_per_engine: Max results per engine (default 100)
            max_engines: Max engines to use per query (default 15)
            deduplicate: Whether to deduplicate by URL (default True)
            progress_callback: Optional callback for progress updates
        """
        self.performance_mode = performance_mode
        self.max_results_per_engine = max_results_per_engine
        self.deduplicate = deduplicate
        self.progress_callback = progress_callback

        # Initialize components
        self.router = QueryRouter(
            max_engines=max_engines,
            performance_mode=performance_mode
        )
        self.ranker = ResultRanker()

        # Engine registry - use provided or load default
        self.engine_registry = engine_registry or self._load_default_registry()

        # Engine tiers from router
        self.engine_tiers = {
            code: tag.tier
            for code, tag in self.router.ENGINE_TAGS.items()
        }

        logger.info(
            "BruteSearchOptimal initialized: mode=%s, max_engines=%d, registry=%d engines",
            performance_mode, max_engines, len(self.engine_registry)
        )

    def _load_default_registry(self) -> Dict[str, Any]:
        """Load default engine registry from brute.py ENGINE_CONFIG."""
        registry = {}

        try:
            # Import from brute.py
            from brute.infrastructure.brute import ENGINE_CONFIG

            for code, config in ENGINE_CONFIG.items():
                if config.get('disabled'):
                    continue

                # Try to load the runner class
                try:
                    module_name = config.get('module', '')
                    class_name = config.get('class', '')

                    if module_name and class_name:
                        # Dynamic import
                        import importlib
                        module = importlib.import_module(f"engines.{module_name}")
                        runner_class = getattr(module, class_name)
                        registry[code] = runner_class
                except Exception as exc:
                    logger.debug("Could not load engine %s: %s", code, exc)

        except ImportError as exc:
            logger.warning("Could not import ENGINE_CONFIG: %s", exc)

        return registry

    def search(
        self,
        query: str,
        engines: Optional[List[str]] = None,
        stop_after_wave: Optional[WavePhase] = None
    ) -> OptimalSearchResult:
        """
        Execute optimal brute search.

        Args:
            query: Search query
            engines: Optional explicit engine list (bypasses router)
            stop_after_wave: Optional wave to stop after (for speed mode)

        Returns:
            OptimalSearchResult with ranked results and metadata
        """
        start_time = time.time()

        # Phase 1: Query Routing
        route_start = time.time()
        if engines:
            # Use provided engines
            selected_engines = engines
            recommendation = None
            query_intent = 'explicit'
            query_complexity = 0.0
        else:
            # Use router
            recommendation = self.router.route(query)
            selected_engines = recommendation.recommended_engines
            query_intent = recommendation.query_analysis.detected_intent
            query_complexity = recommendation.query_analysis.complexity_score

        routing_time = (time.time() - route_start) * 1000

        logger.info(
            "Query routed: '%s' -> %d engines in %.0fms",
            query[:50], len(selected_engines), routing_time
        )

        # Phase 2: Cascade Execution
        exec_start = time.time()

        # Create executor with progress wrapper
        def exec_progress(wave, completed, total, results):
            if self.progress_callback:
                self.progress_callback(SearchProgress(
                    wave=wave,
                    engines_completed=completed,
                    engines_total=total,
                    results_so_far=len(results),
                    elapsed_ms=(time.time() - start_time) * 1000,
                    message=f"{wave.name}: {completed}/{total} engines"
                ))

        executor = CascadeExecutor(
            engine_registry=self.engine_registry,
            max_results_per_engine=self.max_results_per_engine,
            deduplicate=self.deduplicate,
            progress_callback=exec_progress
        )

        execution_result = executor.execute(
            query=query,
            engines=selected_engines,
            engine_tiers=self.engine_tiers,
            stop_after_wave=stop_after_wave
        )

        execution_time = (time.time() - exec_start) * 1000

        # Phase 3: Result Ranking
        rank_start = time.time()
        ranked_results = self.ranker.rank(
            execution_result.all_results,
            query,
            self.engine_tiers
        )
        ranking_time = (time.time() - rank_start) * 1000

        total_time = (time.time() - start_time) * 1000

        logger.info(
            "Search complete: %d results, %d unique, %.1fs total",
            len(ranked_results), execution_result.unique_urls, total_time / 1000
        )

        return OptimalSearchResult(
            query=query,
            results=ranked_results,
            total_results=len(ranked_results),
            unique_urls=execution_result.unique_urls,
            engines_selected=selected_engines,
            engines_succeeded=execution_result.engines_succeeded,
            engines_failed=execution_result.engines_failed,
            query_intent=query_intent,
            query_complexity=query_complexity,
            total_time_ms=total_time,
            routing_time_ms=routing_time,
            execution_time_ms=execution_time,
            ranking_time_ms=ranking_time,
            wave_results=execution_result.wave_results
        )

    def search_streaming(
        self,
        query: str,
        engines: Optional[List[str]] = None
    ) -> Generator[Tuple[WavePhase, List[RankedResult]], None, None]:
        """
        Execute search with streaming results.

        Yields ranked results as each wave completes for progressive UX.

        Args:
            query: Search query
            engines: Optional explicit engine list

        Yields:
            Tuple of (wave_phase, ranked_results_from_wave)
        """
        # Route query
        if engines:
            selected_engines = engines
        else:
            recommendation = self.router.route(query)
            selected_engines = recommendation.recommended_engines

        # Create executor
        executor = CascadeExecutor(
            engine_registry=self.engine_registry,
            max_results_per_engine=self.max_results_per_engine,
            deduplicate=self.deduplicate
        )

        # Stream results
        all_results: List[Dict[str, Any]] = []

        for wave, wave_results in executor.execute_streaming(
            query, selected_engines, self.engine_tiers
        ):
            if wave == WavePhase.COMPLETE:
                break

            # Accumulate and rank all results so far
            all_results.extend(wave_results)
            ranked = self.ranker.rank(wave_results, query, self.engine_tiers)

            logger.info(
                "Streaming %s: %d new results, %d total",
                wave.name, len(wave_results), len(all_results)
            )

            yield (wave, ranked)

    def get_route_preview(self, query: str) -> Dict[str, Any]:
        """
        Preview how a query would be routed without executing.

        Useful for debugging and UX (show user which engines will be used).

        Args:
            query: Search query

        Returns:
            Dict with routing details
        """
        recommendation = self.router.route(query)
        analysis = recommendation.query_analysis

        return {
            'query': query,
            'intent': analysis.detected_intent,
            'complexity': analysis.complexity_score,
            'engines': recommendation.recommended_engines,
            'engine_count': len(recommendation.recommended_engines),
            'estimated_time_ms': recommendation.estimated_time_ms,
            'tier_breakdown': recommendation.tier_breakdown,
            'explanation': recommendation.explanation,
            'axis_analysis': {
                'subjects': [s.name for s in analysis.axis_analysis.subject_types],
                'location': analysis.axis_analysis.location_context.name,
                'operators': [o.name for o in analysis.axis_analysis.operators],
                'temporal': analysis.axis_analysis.temporal_context.name,
            }
        }


# Convenience function
def brute_search_optimal(
    query: str,
    performance_mode: str = 'balanced',
    progress_callback: Optional[ProgressCallback] = None
) -> OptimalSearchResult:
    """
    Quick function for optimal brute search.

    Args:
        query: Search query
        performance_mode: 'speed', 'balanced', or 'comprehensive'
        progress_callback: Optional progress callback

    Returns:
        OptimalSearchResult
    """
    brute = BruteSearchOptimal(
        performance_mode=performance_mode,
        progress_callback=progress_callback
    )
    return brute.search(query)


if __name__ == '__main__':
    # Demo optimal brute search
    print("BruteSearchOptimal - Demo")
    print("=" * 70)

    # Create mock engine registry for demo
    class MockRunner:
        def __init__(self, phrase, max_results=100):
            self.phrase = phrase
            self.max_results = max_results
            self.engine_name = "MockEngine"

        def run(self):
            import random
            time.sleep(random.uniform(0.05, 0.2))
            for i in range(min(5, self.max_results)):
                yield {
                    'url': f'https://example{i}.com/{self.phrase.replace(" ", "-")}',
                    'title': f'Result {i} for {self.phrase}',
                    'snippet': f'This is about {self.phrase}...',
                }

    # Build mock registry
    registry = {code: MockRunner for code in [
        'GO', 'BI', 'DD', 'BR', 'YA', 'SE', 'AX', 'PM', 'EX', 'WP',
        'NA', 'GR', 'GD', 'LG', 'HF', 'AL', 'AA', 'GU', 'OL', 'SS'
    ]}

    # Progress callback
    def on_progress(p: SearchProgress):
        print(f"  ⏳ {p.message} - {p.results_so_far} results ({p.elapsed_ms:.0f}ms)")

    # Create optimal brute search
    brute = BruteSearchOptimal(
        engine_registry=registry,
        performance_mode='balanced',
        max_engines=12,
        progress_callback=on_progress
    )

    # Test queries
    test_queries = [
        "climate change effects",
        "machine learning research papers 2024",
        "site:github.com python async",
        "latest news Ukraine",
    ]

    for query in test_queries:
        print(f"\n{'─'*70}")
        print(f"Query: '{query}'")

        # Preview routing
        preview = brute.get_route_preview(query)
        print(f"\nRouting Preview:")
        print(f"  Intent: {preview['intent']}")
        print(f"  Engines: {preview['engine_count']} - {', '.join(preview['engines'][:8])}...")
        print(f"  Estimated: {preview['estimated_time_ms']}ms")

        # Execute search
        print(f"\nExecuting:")
        result = brute.search(query)

        print(f"\nResults:")
        print(f"  Total: {result.total_results}")
        print(f"  Unique URLs: {result.unique_urls}")
        print(f"  Engines: {len(result.engines_succeeded)} succeeded, {len(result.engines_failed)} failed")
        print(f"  Time: {result.total_time_ms:.0f}ms (route: {result.routing_time_ms:.0f}ms, "
              f"exec: {result.execution_time_ms:.0f}ms, rank: {result.ranking_time_ms:.0f}ms)")

        if result.results:
            print(f"\nTop 3 Results:")
            for r in result.results[:3]:
                print(f"  #{r.rank} [{r.confidence_score:.1f}] {r.title[:40]}...")
