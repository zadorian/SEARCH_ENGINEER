"""
SASTRE Parallel Executor

True concurrent execution of parallel operator branches.
Adapted from brute's ParallelExecutor pattern.

ALIGNS WITH: Abacus System - "Parallel operators run concurrently"
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


@dataclass
class ParallelStepResult:
    """Result of a single parallel step execution."""
    step_id: str
    status: StepStatus
    result: Any
    execution_time: float
    error: Optional[Exception] = None


@dataclass
class ParallelExecutionResult:
    """Aggregated result of parallel execution."""
    results: Dict[str, ParallelStepResult]
    successful: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    total_time: float = 0.0
    partial_success: bool = False


class ProgressTracker:
    """Track progress of parallel execution."""

    def __init__(self, callback: Optional[Callable[[str, StepStatus], None]] = None):
        self._statuses: Dict[str, StepStatus] = {}
        self._callback = callback

    def register(self, step_id: str):
        self._statuses[step_id] = StepStatus.PENDING
        if self._callback:
            self._callback(step_id, StepStatus.PENDING)

    def update(self, step_id: str, status: StepStatus):
        self._statuses[step_id] = status
        if self._callback:
            self._callback(step_id, status)

    def get_status(self, step_id: str) -> StepStatus:
        return self._statuses.get(step_id, StepStatus.PENDING)

    def get_all_statuses(self) -> Dict[str, StepStatus]:
        return self._statuses.copy()


class RateLimiter:
    """Token bucket rate limiter for API calls."""

    def __init__(self, rate: float, burst: int = 1):
        self.rate = rate
        self.burst = burst
        self._tokens = float(burst)
        self._last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.time()
            elapsed = now - self._last_update
            self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
            self._last_update = now

            if self._tokens < 1:
                wait_time = (1 - self._tokens) / self.rate
                await asyncio.sleep(wait_time)
                self._tokens = 0
            else:
                self._tokens -= 1


class SastreParallelExecutor:
    """
    Execute multiple operations concurrently with proper resource management.

    Features:
    - Semaphore-based concurrency limiting
    - Per-step timeout handling
    - Progress tracking
    - Rate limiting (optional)
    - Error isolation (one failure doesn't stop others)
    """

    def __init__(
        self,
        max_concurrent: int = 10,
        timeout: float = 60.0,
        progress_callback: Optional[Callable[[str, StepStatus], None]] = None,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._timeout = timeout
        self._progress = ProgressTracker(progress_callback)
        self._rate_limiter = rate_limiter
        self._max_concurrent = max_concurrent

    async def execute_parallel(
        self,
        steps: List[Tuple[str, Callable[[], Coroutine]]],
        return_exceptions: bool = True,
        fail_fast: bool = False,
    ) -> ParallelExecutionResult:
        """
        Execute multiple steps concurrently.

        Args:
            steps: List of (step_id, coroutine_factory) tuples
            return_exceptions: If True, continue on errors. If False, raise on first error.
            fail_fast: If True, cancel remaining on first failure.

        Returns:
            ParallelExecutionResult with all results
        """
        start_time = time.time()
        tasks: List[asyncio.Task] = []

        for step_id, coro_factory in steps:
            self._progress.register(step_id)
            task = asyncio.create_task(
                self._execute_with_semaphore(step_id, coro_factory),
                name=step_id,
            )
            tasks.append(task)

        # Execute all with global timeout
        try:
            if fail_fast:
                done, pending = await asyncio.wait(
                    tasks,
                    timeout=self._timeout,
                    return_when=asyncio.FIRST_EXCEPTION,
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                results = list(done) + list(pending)
            else:
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=return_exceptions),
                    timeout=self._timeout,
                )
        except asyncio.TimeoutError:
            # Cancel remaining and collect partial results
            for task in tasks:
                if not task.done():
                    task.cancel()
            results = await asyncio.gather(*tasks, return_exceptions=True)

        return self._build_result(steps, results, time.time() - start_time)

    async def _execute_with_semaphore(
        self,
        step_id: str,
        coro_factory: Callable[[], Coroutine],
    ) -> ParallelStepResult:
        """Execute single step with concurrency control."""
        async with self._semaphore:
            if self._rate_limiter:
                await self._rate_limiter.acquire()

            self._progress.update(step_id, StepStatus.RUNNING)
            start = time.time()

            try:
                result = await coro_factory()
                self._progress.update(step_id, StepStatus.COMPLETED)
                return ParallelStepResult(
                    step_id=step_id,
                    status=StepStatus.COMPLETED,
                    result=result,
                    execution_time=time.time() - start,
                )
            except asyncio.CancelledError:
                self._progress.update(step_id, StepStatus.CANCELLED)
                return ParallelStepResult(
                    step_id=step_id,
                    status=StepStatus.CANCELLED,
                    result=None,
                    execution_time=time.time() - start,
                )
            except Exception as e:
                self._progress.update(step_id, StepStatus.FAILED)
                logger.error(f"[ParallelExecutor] Step {step_id} failed: {e}")
                return ParallelStepResult(
                    step_id=step_id,
                    status=StepStatus.FAILED,
                    result=None,
                    execution_time=time.time() - start,
                    error=e,
                )

    def _build_result(
        self,
        steps: List[Tuple[str, Callable]],
        results: List[Any],
        total_time: float,
    ) -> ParallelExecutionResult:
        """Build aggregated result from individual step results."""
        result_dict: Dict[str, ParallelStepResult] = {}
        successful: List[str] = []
        failed: List[str] = []

        for i, (step_id, _) in enumerate(steps):
            if i >= len(results):
                continue

            r = results[i]
            if isinstance(r, ParallelStepResult):
                result_dict[step_id] = r
                if r.status == StepStatus.COMPLETED:
                    successful.append(step_id)
                else:
                    failed.append(step_id)
            elif isinstance(r, Exception):
                result_dict[step_id] = ParallelStepResult(
                    step_id=step_id,
                    status=StepStatus.FAILED,
                    result=None,
                    execution_time=0,
                    error=r,
                )
                failed.append(step_id)
            else:
                # Raw result (shouldn't happen with proper coroutine factories)
                result_dict[step_id] = ParallelStepResult(
                    step_id=step_id,
                    status=StepStatus.COMPLETED,
                    result=r,
                    execution_time=0,
                )
                successful.append(step_id)

        return ParallelExecutionResult(
            results=result_dict,
            successful=successful,
            failed=failed,
            total_time=total_time,
            partial_success=len(successful) > 0 and len(failed) > 0,
        )


class ParallelResultMerger:
    """Merge results from parallel execution branches."""

    @staticmethod
    def merge_entity_results(
        results: List[Dict[str, Any]],
        strategy: str = "union",
    ) -> Dict[str, Any]:
        """
        Merge entity extraction results.

        Strategies:
        - 'union': Combine all entities, deduplicate by value
        - 'intersection': Only entities found in ALL branches
        - 'ranked': Weight by frequency across branches
        """
        if strategy == "union":
            all_entities = []
            seen = set()
            for result in results:
                for entity in result.get("entities", []):
                    key = (entity.get("type"), entity.get("value"))
                    if key not in seen:
                        seen.add(key)
                        all_entities.append(entity)
            return {"entities": all_entities, "merge_strategy": "union"}

        elif strategy == "ranked":
            from collections import defaultdict

            entity_counts: Dict[tuple, int] = defaultdict(int)
            entity_data: Dict[tuple, dict] = {}
            for result in results:
                for entity in result.get("entities", []):
                    key = (entity.get("type"), entity.get("value"))
                    entity_counts[key] += 1
                    entity_data[key] = entity

            ranked = sorted(
                entity_data.items(),
                key=lambda x: entity_counts[x[0]],
                reverse=True,
            )
            return {
                "entities": [e for _, e in ranked],
                "merge_strategy": "ranked",
                "frequencies": dict(entity_counts),
            }

        elif strategy == "intersection":
            if not results:
                return {"entities": [], "merge_strategy": "intersection"}

            # Start with first result's entities
            common = set()
            for entity in results[0].get("entities", []):
                common.add((entity.get("type"), entity.get("value")))

            # Intersect with subsequent results
            for result in results[1:]:
                result_keys = set()
                for entity in result.get("entities", []):
                    result_keys.add((entity.get("type"), entity.get("value")))
                common &= result_keys

            # Rebuild entity list from first result
            entities = [
                e
                for e in results[0].get("entities", [])
                if (e.get("type"), e.get("value")) in common
            ]
            return {"entities": entities, "merge_strategy": "intersection"}

        return {"entities": [], "merge_strategy": "unknown"}


# Convenience function
async def execute_parallel_steps(
    steps: List[Tuple[str, Callable[[], Coroutine]]],
    max_concurrent: int = 10,
    timeout: float = 60.0,
) -> ParallelExecutionResult:
    """Quick parallel execution without instantiating executor."""
    executor = SastreParallelExecutor(
        max_concurrent=max_concurrent,
        timeout=timeout,
    )
    return await executor.execute_parallel(steps)
