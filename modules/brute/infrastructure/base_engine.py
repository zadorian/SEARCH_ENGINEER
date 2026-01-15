#!/usr/bin/env python3
"""
Base search engine class with common functionality
Provides resource management, rate limiting, and error handling
"""

import asyncio
import aiohttp
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union
from contextlib import asynccontextmanager

from brute.infrastructure.common import (
    get_session_pool, get_rate_limiter, BoundedResultsBuffer,
    with_timeout, safe_execute
)
from brute.infrastructure.settings import get_settings
from brute.infrastructure.config import Config

logger = logging.getLogger(__name__)


class BaseSearchEngine(ABC):
    """Abstract base class for all search engines"""
    
    def __init__(self, engine_code: str, engine_name: str):
        self.engine_code = engine_code
        self.engine_name = engine_name
        self.settings = get_settings()
        self.session_pool = get_session_pool()
        self.rate_limiter = get_rate_limiter()
        self.results_buffer = BoundedResultsBuffer(self.settings.MAX_BUFFER_SIZE)
        
        # Get API key if needed
        self.api_key = Config.get_api_key(engine_code)
        
        # Engine-specific settings
        self.max_retries = self.settings.MAX_RETRIES
        self.retry_delay = self.settings.RETRY_DELAY
        self.timeout = self.settings.REQUEST_TIMEOUT
    
    @abstractmethod
    async def _search_impl(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Implementation of the actual search logic.
        Must be overridden by subclasses.
        
        Args:
            query: Search query
            **kwargs: Additional engine-specific parameters
            
        Returns:
            List of raw search results
        """
        pass
    
    async def search(self, query: str, max_results: Optional[int] = None, **kwargs) -> List[Dict[str, Any]]:
        """
        Public search method with error handling and resource management
        
        Args:
            query: Search query
            max_results: Maximum number of results to return
            **kwargs: Additional engine-specific parameters
            
        Returns:
            List of processed search results
        """
        max_results = max_results or self.settings.MAX_RESULTS_PER_ENGINE
        
        async with safe_execute(f"{self.engine_name} search"):
            try:
                # Apply rate limiting
                async with self.rate_limiter.acquire():
                    # Get results with retry logic
                    results = await self._search_with_retry(query, **kwargs)
                    
                    # Process and limit results
                    processed = []
                    for i, result in enumerate(results[:max_results]):
                        # Add standard fields
                        result['source'] = self.engine_code
                        result['engine'] = self.engine_name
                        result['rank'] = i + 1
                        
                        # Validate result
                        if self._validate_result(result):
                            processed.append(result)
                    
                    logger.info(f"{self.engine_name}: Found {len(processed)} results")
                    return processed
                    
            except Exception as e:
                logger.error(f"{self.engine_name} search failed: {e}")
                return []
    
    async def _search_with_retry(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """Execute search with retry logic"""
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                # Add timeout to search
                return await asyncio.wait_for(
                    self._search_impl(query, **kwargs),
                    timeout=self.timeout
                )
            except asyncio.TimeoutError:
                last_error = f"Timeout after {self.timeout}s"
                logger.warning(f"{self.engine_name} attempt {attempt + 1} timed out")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"{self.engine_name} attempt {attempt + 1} failed: {e}")
            
            # Wait before retry with exponential backoff
            if attempt < self.max_retries - 1:
                delay = self.retry_delay * (self.settings.RETRY_BACKOFF ** attempt)
                await asyncio.sleep(delay)
        
        raise Exception(f"{self.engine_name} failed after {self.max_retries} attempts: {last_error}")
    
    def _validate_result(self, result: Dict[str, Any]) -> bool:
        """Validate a search result has required fields"""
        required_fields = ['url', 'title']
        for field in required_fields:
            if field not in result or not result[field]:
                return False
        return True
    
    @asynccontextmanager
    async def _get_session(self):
        """Get aiohttp session from pool"""
        session = await self.session_pool.get_session()
        yield session
        # Session is managed by pool, don't close here
    
    async def _make_request(self, url: str, method: str = 'GET', **kwargs) -> Union[Dict, str]:
        """Make HTTP request with session from pool"""
        async with self._get_session() as session:
            async with session.request(method, url, **kwargs) as response:
                response.raise_for_status()
                
                # Return JSON or text based on content type
                content_type = response.headers.get('Content-Type', '')
                if 'application/json' in content_type:
                    return await response.json()
                else:
                    return await response.text()


class SyncSearchEngineAdapter(BaseSearchEngine):
    """Adapter for synchronous search engines to work with async interface"""
    
    def __init__(self, engine_code: str, engine_name: str, sync_engine: Any):
        super().__init__(engine_code, engine_name)
        self.sync_engine = sync_engine
    
    @abstractmethod
    def _sync_search(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """Synchronous search implementation to be overridden"""
        pass
    
    async def _search_impl(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """Convert sync search to async"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._sync_search,
            query,
            kwargs
        )


class MultiEngineSearchOrchestrator:
    """Orchestrates searches across multiple engines"""
    
    def __init__(self, engines: List[BaseSearchEngine]):
        self.engines = engines
        self.settings = get_settings()
        self.results_buffer = BoundedResultsBuffer()
    
    async def search_all(self, query: str, max_results_per_engine: Optional[int] = None) -> Dict[str, Any]:
        """
        Search across all engines in parallel
        
        Args:
            query: Search query
            max_results_per_engine: Max results from each engine
            
        Returns:
            Dictionary with results and statistics
        """
        max_results = max_results_per_engine or self.settings.MAX_RESULTS_PER_ENGINE
        
        # Create search tasks
        tasks = []
        for engine in self.engines:
            task = asyncio.create_task(
                engine.search(query, max_results),
                name=engine.engine_name
            )
            tasks.append(task)
        
        # Execute with timeout
        try:
            all_results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self.settings.GLOBAL_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.error("Global search timeout reached")
            # Cancel remaining tasks
            for task in tasks:
                if not task.done():
                    task.cancel()
            all_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        combined_results = []
        statistics = {
            'engines_used': [],
            'engine_stats': {},
            'total_results': 0,
            'unique_urls': 0,
            'errors': []
        }
        
        for engine, result in zip(self.engines, all_results):
            if isinstance(result, Exception):
                statistics['errors'].append(f"{engine.engine_name}: {str(result)}")
                statistics['engine_stats'][engine.engine_name] = {'error': str(result)}
            else:
                # Add to combined results with deduplication
                unique_count = 0
                for res in result:
                    if self.results_buffer.add(res):
                        combined_results.append(res)
                        unique_count += 1
                
                statistics['engines_used'].append(engine.engine_name)
                statistics['engine_stats'][engine.engine_name] = {
                    'results': len(result),
                    'unique': unique_count
                }
        
        statistics['total_results'] = len(combined_results)
        statistics['unique_urls'] = self.results_buffer.size
        
        return {
            'query': query,
            'results': combined_results,
            'statistics': statistics
        }


# Example implementation for a specific engine
class ExampleGoogleEngine(BaseSearchEngine):
    """Example implementation for Google search"""
    
    def __init__(self):
        super().__init__('GO', 'Google')
        self.base_url = 'https://www.googleapis.com/customsearch/v1'
        self.cse_id = Config.GOOGLE_CSE_ID
    
    async def _search_impl(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """Implement Google Custom Search API"""
        if not self.api_key or not self.cse_id:
            raise ValueError("Google API key or CSE ID not configured")
        
        params = {
            'key': self.api_key,
            'cx': self.cse_id,
            'q': query,
            'num': 10  # Max per request
        }
        
        results = []
        
        # Make request
        data = await self._make_request(self.base_url, params=params)
        
        # Parse results
        for item in data.get('items', []):
            result = {
                'url': item.get('link'),
                'title': item.get('title'),
                'snippet': item.get('snippet', ''),
                'displayLink': item.get('displayLink', '')
            }
            results.append(result)
        
        return results