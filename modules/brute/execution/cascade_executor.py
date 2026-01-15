#!/usr/bin/env python3
"""
Cascade Executor - 3-Wave execution for progressive result streaming.

Architecture:
- Wave 1: Lightning + Fast engines (30s) - First results in 10-15s
- Wave 2: Standard engines (60s) - Additional depth
- Wave 3: Slow + Very Slow engines (120s) - Maximum recall

Results stream progressively as each wave completes, providing
excellent UX while maximizing total recall.
"""
from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, Iterator, List, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)


class WavePhase(Enum):
    """Execution wave phases."""
    WAVE_1 = auto()  # Lightning + Fast (30s)
    WAVE_2 = auto()  # Standard (60s)
    WAVE_3 = auto()  # Slow + Very Slow (120s)
    COMPLETE = auto()


@dataclass
class EngineResult:
    """Result from a single engine execution."""
    engine_code: str
    engine_name: str
    results: List[Dict[str, Any]]
    success: bool
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    result_count: int = 0
    tier: str = "unknown"


@dataclass
class WaveResult:
    """Result from a single wave of execution."""
    wave: WavePhase
    engine_results: List[EngineResult] = field(default_factory=list)
    total_results: int = 0
    successful_engines: int = 0
    failed_engines: int = 0
    execution_time_ms: float = 0.0


@dataclass
class ExecutionResult:
    """Complete execution result across all waves."""
    query: str
    wave_results: List[WaveResult] = field(default_factory=list)
    all_results: List[Dict[str, Any]] = field(default_factory=list)
    total_results: int = 0
    unique_urls: int = 0
    total_execution_time_ms: float = 0.0
    engines_succeeded: List[str] = field(default_factory=list)
    engines_failed: List[str] = field(default_factory=list)


# Progress callback type
ProgressCallback = Callable[[WavePhase, int, int, List[Dict[str, Any]]], None]


class CascadeExecutor:
    """
    3-Wave Cascade Executor for progressive result streaming.

    Executes search engines in 3 waves based on performance tiers,
    streaming results progressively for excellent UX while ensuring
    maximum recall through exhaustive search.
    """

    # Wave composition: which tiers go in which wave
    WAVE_COMPOSITION = {
        WavePhase.WAVE_1: ['lightning', 'fast'],  # 30s timeout
        WavePhase.WAVE_2: ['standard'],           # 60s timeout
        WavePhase.WAVE_3: ['slow', 'very_slow'],  # 120s timeout
    }

    # Timeouts per wave (milliseconds)
    WAVE_TIMEOUTS = {
        WavePhase.WAVE_1: 30000,   # 30 seconds
        WavePhase.WAVE_2: 60000,   # 60 seconds
        WavePhase.WAVE_3: 120000,  # 120 seconds
    }

    # Max parallel executions per wave
    WAVE_PARALLELISM = {
        WavePhase.WAVE_1: 10,  # Fast engines can run many in parallel
        WavePhase.WAVE_2: 6,   # Moderate parallelism
        WavePhase.WAVE_3: 3,   # Slow engines run fewer in parallel
    }

    def __init__(
        self,
        engine_registry: Dict[str, Any],
        max_results_per_engine: int = 100,
        deduplicate: bool = True,
        progress_callback: Optional[ProgressCallback] = None
    ):
        """
        Initialize cascade executor.

        Args:
            engine_registry: Dict mapping engine codes to runner classes
            max_results_per_engine: Max results to fetch from each engine
            deduplicate: Whether to deduplicate results by URL
            progress_callback: Optional callback for progress updates
        """
        self.engine_registry = engine_registry
        self.max_results_per_engine = max_results_per_engine
        self.deduplicate = deduplicate
        self.progress_callback = progress_callback
        self._seen_urls: Set[str] = set()

    def execute(
        self,
        query: str,
        engines: List[str],
        engine_tiers: Dict[str, str],
        stop_after_wave: Optional[WavePhase] = None
    ) -> ExecutionResult:
        """
        Execute search across engines using 3-wave cascade.

        Args:
            query: Search query
            engines: List of engine codes to execute
            engine_tiers: Dict mapping engine codes to tier names
            stop_after_wave: Optional wave to stop after (for speed mode)

        Returns:
            ExecutionResult with all results and metadata
        """
        start_time = time.time()
        self._seen_urls.clear()

        result = ExecutionResult(query=query)

        # Group engines by wave
        wave_engines = self._group_engines_by_wave(engines, engine_tiers)

        # Execute each wave
        for wave in [WavePhase.WAVE_1, WavePhase.WAVE_2, WavePhase.WAVE_3]:
            wave_engine_list = wave_engines.get(wave, [])

            if not wave_engine_list:
                continue

            logger.info(
                "Executing %s with %d engines: %s",
                wave.name, len(wave_engine_list), wave_engine_list
            )

            wave_result = self._execute_wave(
                query, wave_engine_list, wave, engine_tiers
            )

            result.wave_results.append(wave_result)
            result.all_results.extend(
                r for er in wave_result.engine_results for r in er.results
            )
            result.engines_succeeded.extend(
                er.engine_code for er in wave_result.engine_results if er.success
            )
            result.engines_failed.extend(
                er.engine_code for er in wave_result.engine_results if not er.success
            )

            # Call progress callback
            if self.progress_callback:
                self.progress_callback(
                    wave,
                    len(result.engines_succeeded),
                    len(engines),
                    result.all_results[-wave_result.total_results:]
                )

            # Stop early if requested
            if stop_after_wave and wave == stop_after_wave:
                logger.info("Stopping after %s as requested", wave.name)
                break

        # Finalize
        result.total_results = len(result.all_results)
        result.unique_urls = len(self._seen_urls)
        result.total_execution_time_ms = (time.time() - start_time) * 1000

        logger.info(
            "Cascade complete: %d results from %d engines in %.1fs",
            result.total_results,
            len(result.engines_succeeded),
            result.total_execution_time_ms / 1000
        )

        return result

    def execute_streaming(
        self,
        query: str,
        engines: List[str],
        engine_tiers: Dict[str, str]
    ) -> Iterator[Tuple[WavePhase, List[Dict[str, Any]]]]:
        """
        Execute search with streaming results.

        Yields results as each wave completes.

        Args:
            query: Search query
            engines: List of engine codes
            engine_tiers: Dict mapping codes to tiers

        Yields:
            Tuple of (wave_phase, results_list)
        """
        self._seen_urls.clear()
        wave_engines = self._group_engines_by_wave(engines, engine_tiers)

        for wave in [WavePhase.WAVE_1, WavePhase.WAVE_2, WavePhase.WAVE_3]:
            wave_engine_list = wave_engines.get(wave, [])
            if not wave_engine_list:
                continue

            wave_result = self._execute_wave(
                query, wave_engine_list, wave, engine_tiers
            )

            results = [r for er in wave_result.engine_results for r in er.results]
            yield (wave, results)

        yield (WavePhase.COMPLETE, [])

    def _group_engines_by_wave(
        self,
        engines: List[str],
        engine_tiers: Dict[str, str]
    ) -> Dict[WavePhase, List[str]]:
        """Group engines into waves based on their tiers."""
        wave_engines: Dict[WavePhase, List[str]] = {
            WavePhase.WAVE_1: [],
            WavePhase.WAVE_2: [],
            WavePhase.WAVE_3: [],
        }

        for code in engines:
            tier = engine_tiers.get(code, 'fast')

            for wave, tiers in self.WAVE_COMPOSITION.items():
                if tier in tiers:
                    wave_engines[wave].append(code)
                    break
            else:
                # Default to Wave 1 if tier unknown
                wave_engines[WavePhase.WAVE_1].append(code)

        return wave_engines

    def _execute_wave(
        self,
        query: str,
        engines: List[str],
        wave: WavePhase,
        engine_tiers: Dict[str, str]
    ) -> WaveResult:
        """Execute a single wave of engines in parallel."""
        start_time = time.time()
        timeout_sec = self.WAVE_TIMEOUTS[wave] / 1000
        max_workers = min(self.WAVE_PARALLELISM[wave], len(engines))

        wave_result = WaveResult(wave=wave)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all engine tasks
            future_to_engine = {
                executor.submit(
                    self._execute_single_engine,
                    query,
                    code,
                    engine_tiers.get(code, 'unknown')
                ): code
                for code in engines
            }

            # Collect results with timeout
            for future in as_completed(future_to_engine, timeout=timeout_sec):
                code = future_to_engine[future]
                try:
                    engine_result = future.result(timeout=5)
                    wave_result.engine_results.append(engine_result)

                    if engine_result.success:
                        wave_result.successful_engines += 1
                        wave_result.total_results += engine_result.result_count
                    else:
                        wave_result.failed_engines += 1

                except TimeoutError:
                    logger.warning("%s timed out in %s", code, wave.name)
                    wave_result.engine_results.append(EngineResult(
                        engine_code=code,
                        engine_name=code,
                        results=[],
                        success=False,
                        error="Timeout",
                        tier=engine_tiers.get(code, 'unknown')
                    ))
                    wave_result.failed_engines += 1

                except Exception as exc:
                    logger.error("%s failed in %s: %s", code, wave.name, exc)
                    wave_result.engine_results.append(EngineResult(
                        engine_code=code,
                        engine_name=code,
                        results=[],
                        success=False,
                        error=str(exc),
                        tier=engine_tiers.get(code, 'unknown')
                    ))
                    wave_result.failed_engines += 1

        wave_result.execution_time_ms = (time.time() - start_time) * 1000

        logger.info(
            "%s complete: %d/%d engines, %d results in %.1fs",
            wave.name,
            wave_result.successful_engines,
            len(engines),
            wave_result.total_results,
            wave_result.execution_time_ms / 1000
        )

        return wave_result

    def _execute_single_engine(
        self,
        query: str,
        engine_code: str,
        tier: str
    ) -> EngineResult:
        """Execute a single engine and return results."""
        start_time = time.time()

        try:
            # Get engine runner from registry
            runner_class = self.engine_registry.get(engine_code)
            if not runner_class:
                return EngineResult(
                    engine_code=engine_code,
                    engine_name=engine_code,
                    results=[],
                    success=False,
                    error=f"Engine {engine_code} not found in registry",
                    tier=tier
                )

            # Instantiate runner
            runner = runner_class(
                phrase=query,
                max_results=self.max_results_per_engine
            )

            # Execute and collect results
            results: List[Dict[str, Any]] = []
            for result in runner.run():
                # Deduplicate by URL
                url = result.get('url', '')
                if self.deduplicate and url:
                    if url in self._seen_urls:
                        continue
                    self._seen_urls.add(url)

                # Enrich with engine metadata
                result.setdefault('engine', engine_code)
                result.setdefault('engine_code', engine_code)
                result.setdefault('tier', tier)

                results.append(result)

            execution_time = (time.time() - start_time) * 1000

            return EngineResult(
                engine_code=engine_code,
                engine_name=getattr(runner, 'engine_name', engine_code),
                results=results,
                success=True,
                execution_time_ms=execution_time,
                result_count=len(results),
                tier=tier
            )

        except Exception as exc:
            logger.error("Engine %s failed: %s", engine_code, exc, exc_info=True)
            return EngineResult(
                engine_code=engine_code,
                engine_name=engine_code,
                results=[],
                success=False,
                error=str(exc),
                execution_time_ms=(time.time() - start_time) * 1000,
                tier=tier
            )


class AsyncCascadeExecutor:
    """
    Async version of CascadeExecutor for use with async frameworks.

    Same 3-wave pattern but uses asyncio for better integration
    with async web frameworks like FastAPI.
    """

    def __init__(
        self,
        engine_registry: Dict[str, Any],
        max_results_per_engine: int = 100,
        deduplicate: bool = True
    ):
        self.engine_registry = engine_registry
        self.max_results_per_engine = max_results_per_engine
        self.deduplicate = deduplicate
        self._seen_urls: Set[str] = set()

    async def execute_streaming(
        self,
        query: str,
        engines: List[str],
        engine_tiers: Dict[str, str]
    ):
        """
        Async generator yielding results as waves complete.

        Usage:
            async for wave, results in executor.execute_streaming(query, engines, tiers):
                yield results  # Stream to client
        """
        self._seen_urls.clear()

        # Use sync executor in thread pool for now
        # (most engines are sync anyway)
        loop = asyncio.get_event_loop()
        sync_executor = CascadeExecutor(
            self.engine_registry,
            self.max_results_per_engine,
            self.deduplicate
        )

        for wave, results in sync_executor.execute_streaming(query, engines, engine_tiers):
            yield (wave, results)
            await asyncio.sleep(0)  # Yield control to event loop


# Convenience function
def create_cascade_executor(
    engine_registry: Dict[str, Any],
    progress_callback: Optional[ProgressCallback] = None
) -> CascadeExecutor:
    """Create a cascade executor with standard settings."""
    return CascadeExecutor(
        engine_registry=engine_registry,
        max_results_per_engine=100,
        deduplicate=True,
        progress_callback=progress_callback
    )


if __name__ == '__main__':
    # Demo with mock engines
    print("Cascade Executor - Demo")
    print("=" * 60)

    # Mock engine registry
    class MockRunner:
        def __init__(self, phrase, max_results=100):
            self.phrase = phrase
            self.max_results = max_results
            self.engine_name = "MockEngine"

        def run(self):
            import random
            time.sleep(random.uniform(0.1, 0.5))
            for i in range(min(10, self.max_results)):
                yield {
                    'url': f'https://example.com/{i}',
                    'title': f'Result {i} for {self.phrase}',
                    'snippet': f'This is result {i}...'
                }

    registry = {
        'GO': MockRunner,
        'BI': MockRunner,
        'DD': MockRunner,
        'BR': MockRunner,
        'YA': MockRunner,
        'SE': MockRunner,
        'AX': MockRunner,
        'PM': MockRunner,
        'LG': MockRunner,
        'HF': MockRunner,
    }

    tiers = {
        'GO': 'standard',
        'BI': 'lightning',
        'DD': 'lightning',
        'BR': 'lightning',
        'YA': 'fast',
        'SE': 'fast',
        'AX': 'standard',
        'PM': 'standard',
        'LG': 'very_slow',
        'HF': 'very_slow',
    }

    def progress(wave, completed, total, results):
        print(f"  Progress: {wave.name} - {completed}/{total} engines, {len(results)} new results")

    executor = CascadeExecutor(registry, progress_callback=progress)

    print("\nExecuting search for 'machine learning'...")
    result = executor.execute(
        "machine learning",
        list(registry.keys()),
        tiers
    )

    print(f"\nResults:")
    print(f"  Total results: {result.total_results}")
    print(f"  Unique URLs: {result.unique_urls}")
    print(f"  Execution time: {result.total_execution_time_ms:.0f}ms")
    print(f"  Succeeded: {result.engines_succeeded}")
    print(f"  Failed: {result.engines_failed}")

    print("\nWave breakdown:")
    for wr in result.wave_results:
        print(f"  {wr.wave.name}: {wr.successful_engines} engines, {wr.total_results} results, {wr.execution_time_ms:.0f}ms")
