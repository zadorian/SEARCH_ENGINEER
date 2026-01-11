#!/usr/bin/env python3
"""
Adapter to integrate parallel execution with existing search types
Provides drop-in replacement for sequential search execution
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Callable, Tuple
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from brute.infrastructure.parallel_executor import (
    ParallelExecutor, SearchOrchestrator, EngineStatus
)

logger = logging.getLogger(__name__)


class ParallelSearchAdapter:
    """
    Adapter to make existing search types use parallel execution
    Drop-in replacement for sequential execution
    """
    
    def __init__(self, timeout: float = 30.0, max_workers: int = 10):
        """
        Initialize the adapter
        
        Args:
            timeout: Global timeout for searches
            max_workers: Maximum concurrent workers
        """
        self.orchestrator = SearchOrchestrator(
            ParallelExecutor(max_workers=max_workers, timeout=timeout)
        )
        self._engine_cache = {}
    
    def register_engines(self, engines: Dict[str, Any]):
        """
        Register available search engines
        
        Args:
            engines: Dictionary mapping engine names to instances
        """
        self._engine_cache.update(engines)
    
    async def search_all_engines(self,
                               query: str,
                               max_results: int = 10,
                               engines: Optional[List[str]] = None,
                               progress_callback: Optional[Callable] = None,
                               **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """
        Search across all available engines in parallel
        
        Args:
            query: Search query
            max_results: Maximum results per engine
            engines: List of engine names to use (None = all)
            progress_callback: Optional progress callback
            **kwargs: Additional search parameters
            
        Returns:
            Dictionary mapping engine names to result lists
        """
        # Determine which engines to use
        if engines is None:
            engines_to_use = list(self._engine_cache.items())
        else:
            engines_to_use = [
                (name, self._engine_cache[name]) 
                for name in engines 
                if name in self._engine_cache
            ]
        
        if not engines_to_use:
            logger.warning("No engines available for search")
            return {}
        
        # Update orchestrator with progress callback if provided
        if progress_callback:
            self.orchestrator.executor.progress_tracker.callback = progress_callback
        
        # Execute parallel search
        results = await self.orchestrator.search(
            engines_to_use,
            query=query,
            max_results_per_engine=max_results,
            deduplicate=False,  # Keep original results per engine
            merge_strategy='append',
            **kwargs
        )
        
        # Convert to expected format
        engine_results = {}
        for engine_name, engine_result in results['engine_results'].items():
            if engine_result.status == EngineStatus.COMPLETED:
                engine_results[engine_name] = engine_result.results
            else:
                engine_results[engine_name] = []
                if engine_result.error:
                    logger.error(f"{engine_name} search failed: {engine_result.error}")
        
        return engine_results
    
    def search_all_engines_sync(self,
                              query: str,
                              max_results: int = 10,
                              engines: Optional[List[str]] = None,
                              **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """
        Synchronous wrapper for parallel search
        
        Args:
            query: Search query
            max_results: Maximum results per engine
            engines: List of engine names to use
            **kwargs: Additional search parameters
            
        Returns:
            Dictionary mapping engine names to result lists
        """
        # Create new event loop if needed
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is already running, create a new one in thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.search_all_engines(query, max_results, engines, **kwargs)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.search_all_engines(query, max_results, engines, **kwargs)
                )
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(
                self.search_all_engines(query, max_results, engines, **kwargs)
            )


# Global adapter instance
_global_adapter = None


def get_parallel_adapter(timeout: float = 30.0, max_workers: int = 10) -> ParallelSearchAdapter:
    """Get or create global parallel adapter instance"""
    global _global_adapter
    if _global_adapter is None:
        _global_adapter = ParallelSearchAdapter(timeout=timeout, max_workers=max_workers)
    return _global_adapter


# Drop-in replacement functions for existing code
def parallel_search_engines(engines: Dict[str, Any],
                          query: str,
                          max_results: int = 10,
                          progress_callback: Optional[Callable] = None,
                          **kwargs) -> Dict[str, List[Dict[str, Any]]]:
    """
    Drop-in replacement for sequential engine search
    
    Example usage to replace existing code:
    
    # Old sequential code:
    results = []
    if GOOGLE_AVAILABLE:
        results.extend(GoogleSearch().search(query))  # 2s
    if BING_AVAILABLE:
        results.extend(BingSearch().search(query))    # 2s
    if YANDEX_AVAILABLE:
        results.extend(YandexSearch().search(query))  # 2s
    
    # New parallel code:
    engines = {}
    if GOOGLE_AVAILABLE:
        engines['google'] = GoogleSearch()
    if BING_AVAILABLE:
        engines['bing'] = BingSearch()
    if YANDEX_AVAILABLE:
        engines['yandex'] = YandexSearch()
    
    results = parallel_search_engines(engines, query, max_results)
    """
    adapter = get_parallel_adapter()
    adapter.register_engines(engines)
    return adapter.search_all_engines_sync(
        query, max_results, progress_callback=progress_callback, **kwargs
    )


# Integration helper for existing search type classes
class ParallelSearchMixin:
    """
    Mixin to add parallel search capability to existing search classes
    
    Example usage:
    
    class YourSearchType(ParallelSearchMixin):
        def __init__(self):
            self.setup_engines()
        
        def setup_engines(self):
            self.engines = {}
            if GOOGLE_AVAILABLE:
                self.engines['google'] = GoogleSearch()
            if BING_AVAILABLE:
                self.engines['bing'] = BingSearch()
        
        def search(self, query, max_results=10):
            # Use parallel search automatically
            return self.parallel_search(query, max_results)
    """
    
    def __init__(self):
        self.engines = {}
        self._parallel_adapter = None
    
    @property
    def parallel_adapter(self):
        """Lazy initialization of parallel adapter"""
        if self._parallel_adapter is None:
            self._parallel_adapter = ParallelSearchAdapter()
            if hasattr(self, 'engines'):
                self._parallel_adapter.register_engines(self.engines)
        return self._parallel_adapter
    
    def parallel_search(self,
                       query: str,
                       max_results: int = 10,
                       engines: Optional[List[str]] = None,
                       progress_callback: Optional[Callable] = None,
                       **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """Execute parallel search across registered engines"""
        return self.parallel_adapter.search_all_engines_sync(
            query, max_results, engines, progress_callback, **kwargs
        )
    
    async def parallel_search_async(self,
                                  query: str,
                                  max_results: int = 10,
                                  engines: Optional[List[str]] = None,
                                  progress_callback: Optional[Callable] = None,
                                  **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """Async version of parallel search"""
        return await self.parallel_adapter.search_all_engines(
            query, max_results, engines, progress_callback, **kwargs
        )


# Example refactored search function
async def example_parallel_site_search(sites: List[str], 
                                     query: str,
                                     max_results: int = 100) -> Dict[str, List[str]]:
    """
    Example of how to refactor existing site search to use parallel execution
    
    This replaces sequential execution with parallel execution
    """
    from brute.infrastructure.engine_imports import (
        GOOGLE_AVAILABLE, GoogleSearch,
        BING_AVAILABLE, BingSearch,
        YANDEX_AVAILABLE, YandexSearch,
        BRAVE_AVAILABLE, BraveSearch,
        DUCKDUCKGO_AVAILABLE, DuckDuckGoSearch
    )
    
    # Build site queries
    site_queries = [f"site:{site} {query}" for site in sites]
    full_query = " OR ".join(site_queries)
    
    # Setup engines
    engines = []
    if GOOGLE_AVAILABLE:
        engines.append(('google', GoogleSearch()))
    if BING_AVAILABLE:
        engines.append(('bing', BingSearch()))
    if YANDEX_AVAILABLE:
        engines.append(('yandex', YandexSearch()))
    if BRAVE_AVAILABLE:
        engines.append(('brave', BraveSearch()))
    if DUCKDUCKGO_AVAILABLE:
        engines.append(('duckduckgo', DuckDuckGoSearch()))
    
    # Execute parallel search
    orchestrator = SearchOrchestrator()
    results = await orchestrator.search(
        engines,
        query=full_query,
        max_results_per_engine=max_results,
        deduplicate=True,
        merge_strategy='ranked'
    )
    
    # Extract URLs by engine
    urls_by_engine = {}
    for result in results['results']:
        engines_list = result.get('search_engines', [result.get('search_engine', 'unknown')])
        for engine in engines_list:
            if engine not in urls_by_engine:
                urls_by_engine[engine] = []
            urls_by_engine[engine].append(result['url'])
    
    return urls_by_engine