#!/usr/bin/env python3
"""
Parallel Execution Framework for Search Engineer
Provides efficient concurrent execution of search engines with proper error handling,
progress tracking, and result aggregation.
"""

import asyncio
import time
import logging
from typing import List, Dict, Any, Optional, Callable, Union, Tuple
from concurrent.futures import ThreadPoolExecutor, Future
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
import threading
from collections import defaultdict

logger = logging.getLogger(__name__)


class EngineStatus(Enum):
    """Status of a search engine execution"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class EngineResult:
    """Result from a single engine execution"""
    engine_name: str
    status: EngineStatus
    results: List[Dict[str, Any]]
    execution_time: float
    error: Optional[Exception] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class ProgressTracker:
    """Track progress of parallel executions"""
    
    def __init__(self, callback: Optional[Callable] = None):
        self.callback = callback
        self.engines: Dict[str, EngineStatus] = {}
        self.start_times: Dict[str, float] = {}
        self.lock = threading.Lock()
    
    def register_engine(self, engine_name: str):
        """Register an engine for tracking"""
        with self.lock:
            self.engines[engine_name] = EngineStatus.PENDING
            self._notify()
    
    def update_status(self, engine_name: str, status: EngineStatus):
        """Update engine status"""
        with self.lock:
            self.engines[engine_name] = status
            if status == EngineStatus.RUNNING:
                self.start_times[engine_name] = time.time()
            self._notify()
    
    def get_progress(self) -> Dict[str, Any]:
        """Get current progress snapshot"""
        with self.lock:
            total = len(self.engines)
            completed = sum(1 for s in self.engines.values() 
                          if s in [EngineStatus.COMPLETED, EngineStatus.FAILED, 
                                  EngineStatus.TIMEOUT, EngineStatus.CANCELLED])
            
            return {
                'total': total,
                'completed': completed,
                'percentage': (completed / total * 100) if total > 0 else 0,
                'engines': dict(self.engines),
                'running_time': {
                    name: time.time() - start_time 
                    for name, start_time in self.start_times.items()
                    if self.engines.get(name) == EngineStatus.RUNNING
                }
            }
    
    def _notify(self):
        """Notify callback of progress update"""
        if self.callback:
            try:
                self.callback(self.get_progress())
            except Exception as e:
                logger.error(f"Progress callback error: {e}")


class ParallelExecutor:
    """
    Main parallel execution framework for search engines
    Handles both sync and async engines with unified interface
    """
    
    def __init__(self, 
                 max_workers: int = 10,
                 timeout: float = 30.0,
                 progress_callback: Optional[Callable] = None):
        """
        Initialize the parallel executor
        
        Args:
            max_workers: Maximum number of concurrent workers
            timeout: Global timeout for all searches
            progress_callback: Optional callback for progress updates
        """
        self.max_workers = max_workers
        self.timeout = timeout
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.progress_tracker = ProgressTracker(progress_callback)
        self._semaphore = asyncio.Semaphore(max_workers)
    
    async def execute_searches(self,
                             engines: List[Tuple[str, Union[Callable, Any]]],
                             query: str,
                             max_results: int = 10,
                             engine_timeout: Optional[float] = None,
                             **kwargs) -> Dict[str, EngineResult]:
        """
        Execute searches across multiple engines in parallel
        
        Args:
            engines: List of (name, engine_instance) tuples
            query: Search query
            max_results: Maximum results per engine
            engine_timeout: Timeout per engine (uses global timeout if None)
            **kwargs: Additional arguments passed to search methods
            
        Returns:
            Dictionary mapping engine names to EngineResult objects
        """
        if engine_timeout is None:
            engine_timeout = self.timeout
        
        # Register all engines
        for name, _ in engines:
            self.progress_tracker.register_engine(name)
        
        # Create tasks for all engines
        tasks = []
        for name, engine in engines:
            task = asyncio.create_task(
                self._execute_single_engine(
                    name, engine, query, max_results, engine_timeout, **kwargs
                ),
                name=name
            )
            tasks.append(task)
        
        # Execute all tasks with global timeout
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self.timeout
            )
        except asyncio.TimeoutError:
            # Cancel remaining tasks
            for task in tasks:
                if not task.done():
                    task.cancel()
                    self.progress_tracker.update_status(
                        task.get_name(), EngineStatus.TIMEOUT
                    )
            
            # Gather results including cancelled ones
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        final_results = {}
        for (name, _), result in zip(engines, results):
            if isinstance(result, EngineResult):
                final_results[name] = result
            elif isinstance(result, asyncio.CancelledError):
                final_results[name] = EngineResult(
                    engine_name=name,
                    status=EngineStatus.CANCELLED,
                    results=[],
                    execution_time=0,
                    error=result
                )
            elif isinstance(result, Exception):
                final_results[name] = EngineResult(
                    engine_name=name,
                    status=EngineStatus.FAILED,
                    results=[],
                    execution_time=0,
                    error=result
                )
        
        return final_results
    
    async def _execute_single_engine(self,
                                   name: str,
                                   engine: Any,
                                   query: str,
                                   max_results: int,
                                   timeout: float,
                                   **kwargs) -> EngineResult:
        """Execute a single engine search"""
        start_time = time.time()
        
        try:
            # Acquire semaphore to limit concurrency
            async with self._semaphore:
                self.progress_tracker.update_status(name, EngineStatus.RUNNING)
                
                # Detect if engine has async search method
                search_method = getattr(engine, 'search', None)
                if search_method is None:
                    raise AttributeError(f"Engine {name} has no search method")
                
                # Execute search with timeout
                if asyncio.iscoroutinefunction(search_method):
                    # Async engine
                    results = await asyncio.wait_for(
                        search_method(query, max_results, **kwargs),
                        timeout=timeout
                    )
                else:
                    # Sync engine - run in executor
                    loop = asyncio.get_event_loop()
                    results = await asyncio.wait_for(
                        loop.run_in_executor(
                            self.executor,
                            search_method,
                            query,
                            max_results,
                            kwargs
                        ),
                        timeout=timeout
                    )
                
                # Success
                execution_time = time.time() - start_time
                self.progress_tracker.update_status(name, EngineStatus.COMPLETED)
                
                return EngineResult(
                    engine_name=name,
                    status=EngineStatus.COMPLETED,
                    results=results if isinstance(results, list) else [],
                    execution_time=execution_time,
                    metadata={'query': query, 'max_results': max_results}
                )
                
        except asyncio.TimeoutError:
            self.progress_tracker.update_status(name, EngineStatus.TIMEOUT)
            return EngineResult(
                engine_name=name,
                status=EngineStatus.TIMEOUT,
                results=[],
                execution_time=time.time() - start_time,
                error=TimeoutError(f"Engine {name} timed out after {timeout}s")
            )
            
        except Exception as e:
            self.progress_tracker.update_status(name, EngineStatus.FAILED)
            logger.error(f"Engine {name} failed: {e}")
            return EngineResult(
                engine_name=name,
                status=EngineStatus.FAILED,
                results=[],
                execution_time=time.time() - start_time,
                error=e
            )
    
    def shutdown(self):
        """Shutdown the executor"""
        self.executor.shutdown(wait=True)


class SearchOrchestrator:
    """
    High-level orchestrator for parallel search execution
    Provides additional features like result merging, deduplication, and ranking
    """
    
    def __init__(self, executor: Optional[ParallelExecutor] = None):
        """
        Initialize the orchestrator
        
        Args:
            executor: ParallelExecutor instance (creates default if None)
        """
        self.executor = executor or ParallelExecutor()
    
    async def search(self,
                    engines: List[Tuple[str, Any]],
                    query: str,
                    max_results_per_engine: int = 10,
                    deduplicate: bool = True,
                    merge_strategy: str = 'interleave',
                    **kwargs) -> Dict[str, Any]:
        """
        Orchestrate parallel search with result processing
        
        Args:
            engines: List of (name, engine) tuples
            query: Search query
            max_results_per_engine: Max results from each engine
            deduplicate: Whether to remove duplicate URLs
            merge_strategy: How to merge results ('interleave', 'append', 'ranked')
            **kwargs: Additional arguments for engines
            
        Returns:
            Dictionary with:
                - results: Merged search results
                - engine_results: Individual engine results
                - statistics: Execution statistics
        """
        # Execute searches in parallel
        engine_results = await self.executor.execute_searches(
            engines, query, max_results_per_engine, **kwargs
        )
        
        # Merge results based on strategy
        merged_results = self._merge_results(
            engine_results, deduplicate, merge_strategy
        )
        
        # Calculate statistics
        statistics = self._calculate_statistics(engine_results)
        
        return {
            'query': query,
            'results': merged_results,
            'engine_results': engine_results,
            'statistics': statistics
        }
    
    def _merge_results(self,
                      engine_results: Dict[str, EngineResult],
                      deduplicate: bool,
                      strategy: str) -> List[Dict[str, Any]]:
        """Merge results from multiple engines"""
        if strategy == 'interleave':
            return self._merge_interleave(engine_results, deduplicate)
        elif strategy == 'append':
            return self._merge_append(engine_results, deduplicate)
        elif strategy == 'ranked':
            return self._merge_ranked(engine_results, deduplicate)
        else:
            raise ValueError(f"Unknown merge strategy: {strategy}")
    
    def _merge_interleave(self,
                         engine_results: Dict[str, EngineResult],
                         deduplicate: bool) -> List[Dict[str, Any]]:
        """Interleave results from different engines"""
        # Get successful results
        result_lists = []
        for engine_result in engine_results.values():
            if engine_result.status == EngineStatus.COMPLETED:
                result_lists.append(engine_result.results)
        
        if not result_lists:
            return []
        
        # Interleave results
        merged = []
        seen_urls = set()
        max_len = max(len(results) for results in result_lists)
        
        for i in range(max_len):
            for results in result_lists:
                if i < len(results):
                    result = results[i]
                    url = result.get('url', '')
                    
                    if deduplicate and url in seen_urls:
                        continue
                    
                    if deduplicate:
                        seen_urls.add(url)
                    
                    # Add engine source
                    result['search_engine'] = result.get('source', 'unknown')
                    merged.append(result)
        
        return merged
    
    def _merge_append(self,
                     engine_results: Dict[str, EngineResult],
                     deduplicate: bool) -> List[Dict[str, Any]]:
        """Append results from each engine sequentially"""
        merged = []
        seen_urls = set()
        
        for engine_name, engine_result in engine_results.items():
            if engine_result.status == EngineStatus.COMPLETED:
                for result in engine_result.results:
                    url = result.get('url', '')
                    
                    if deduplicate and url in seen_urls:
                        continue
                    
                    if deduplicate:
                        seen_urls.add(url)
                    
                    result['search_engine'] = engine_name
                    merged.append(result)
        
        return merged
    
    def _merge_ranked(self,
                     engine_results: Dict[str, EngineResult],
                     deduplicate: bool) -> List[Dict[str, Any]]:
        """Merge results with ranking based on multiple engine agreement"""
        url_scores = defaultdict(lambda: {'score': 0, 'results': [], 'engines': []})
        
        # Calculate scores based on position and engine count
        for engine_name, engine_result in engine_results.items():
            if engine_result.status == EngineStatus.COMPLETED:
                for position, result in enumerate(engine_result.results):
                    url = result.get('url', '')
                    if url:
                        # Score based on inverse position (higher position = higher score)
                        score = 1.0 / (position + 1)
                        url_scores[url]['score'] += score
                        url_scores[url]['results'].append(result)
                        url_scores[url]['engines'].append(engine_name)
        
        # Sort by score and create merged results
        sorted_urls = sorted(url_scores.items(), 
                           key=lambda x: (len(x[1]['engines']), x[1]['score']), 
                           reverse=True)
        
        merged = []
        for url, data in sorted_urls:
            # Use the first result as base
            result = data['results'][0].copy()
            result['search_engines'] = data['engines']
            result['combined_score'] = data['score']
            result['engine_count'] = len(data['engines'])
            merged.append(result)
        
        return merged
    
    def _calculate_statistics(self, 
                            engine_results: Dict[str, EngineResult]) -> Dict[str, Any]:
        """Calculate execution statistics"""
        stats = {
            'total_engines': len(engine_results),
            'successful_engines': 0,
            'failed_engines': 0,
            'timeout_engines': 0,
            'total_results': 0,
            'total_execution_time': 0,
            'engine_details': {}
        }
        
        for name, result in engine_results.items():
            stats['engine_details'][name] = {
                'status': result.status.value,
                'result_count': len(result.results),
                'execution_time': result.execution_time,
                'error': str(result.error) if result.error else None
            }
            
            if result.status == EngineStatus.COMPLETED:
                stats['successful_engines'] += 1
                stats['total_results'] += len(result.results)
            elif result.status == EngineStatus.FAILED:
                stats['failed_engines'] += 1
            elif result.status == EngineStatus.TIMEOUT:
                stats['timeout_engines'] += 1
            
            stats['total_execution_time'] = max(
                stats['total_execution_time'], 
                result.execution_time
            )
        
        stats['success_rate'] = (
            stats['successful_engines'] / stats['total_engines'] * 100
            if stats['total_engines'] > 0 else 0
        )
        
        return stats


# Convenience function for simple parallel search
async def parallel_search(engines: List[Tuple[str, Any]],
                        query: str,
                        max_results: int = 10,
                        timeout: float = 30.0,
                        progress_callback: Optional[Callable] = None,
                        **kwargs) -> Dict[str, Any]:
    """
    Simple function to perform parallel search
    
    Args:
        engines: List of (name, engine) tuples
        query: Search query
        max_results: Maximum results per engine
        timeout: Search timeout
        progress_callback: Optional progress callback
        **kwargs: Additional search parameters
        
    Returns:
        Search results dictionary
    """
    orchestrator = SearchOrchestrator(
        ParallelExecutor(timeout=timeout, progress_callback=progress_callback)
    )
    
    try:
        return await orchestrator.search(
            engines, query, max_results, **kwargs
        )
    finally:
        orchestrator.executor.shutdown()


# Example usage in existing search types
if __name__ == "__main__":
    # Example of how to integrate with existing code
    import asyncio
    
    async def example_usage():
        # Mock engines for demonstration
        class MockEngine:
            def __init__(self, name, delay=1):
                self.name = name
                self.delay = delay
            
            async def search(self, query, max_results, **kwargs):
                await asyncio.sleep(self.delay)
                return [
                    {'url': f'https://example{i}.com', 
                     'title': f'{self.name} Result {i}',
                     'snippet': f'Result from {self.name}'}
                    for i in range(max_results)
                ]
        
        # Progress callback
        def on_progress(progress):
            print(f"Progress: {progress['completed']}/{progress['total']} "
                  f"({progress['percentage']:.1f}%)")
        
        # Create engines
        engines = [
            ('Google', MockEngine('Google', 2)),
            ('Bing', MockEngine('Bing', 1.5)),
            ('DuckDuckGo', MockEngine('DuckDuckGo', 1)),
        ]
        
        # Execute parallel search
        results = await parallel_search(
            engines,
            query="test query",
            max_results=5,
            timeout=10,
            progress_callback=on_progress
        )
        
        print(f"\nTotal results: {len(results['results'])}")
        print(f"Statistics: {results['statistics']}")
    
    # Run example
    asyncio.run(example_usage())