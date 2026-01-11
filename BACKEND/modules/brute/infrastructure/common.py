#!/usr/bin/env python3
"""
Common utilities for targeted_searches modules
Provides resource management, rate limiting, and concurrency helpers
"""

import asyncio
import aiohttp
import time
import threading
import logging
from typing import List, Dict, Any, Optional, Set
from contextlib import asynccontextmanager
import functools

logger = logging.getLogger(__name__)


class ResourceManager:
    """Simple context manager for any resource with cleanup"""
    def __init__(self, resource, cleanup_method='close'):
        self.resource = resource
        self.cleanup_method = cleanup_method
    
    def __enter__(self):
        return self.resource
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self.resource, self.cleanup_method):
            try:
                cleanup_func = getattr(self.resource, self.cleanup_method)
                cleanup_func()
            except Exception as e:
                logger.warning(f"Error during resource cleanup: {e}")


class SessionPool:
    """Manages a shared aiohttp session pool for all HTTP requests"""
    def __init__(self, connector_limit=100, timeout=30):
        self.connector_limit = connector_limit
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.connector = None
        self.session = None
        self._lock = asyncio.Lock()
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create the shared session"""
        async with self._lock:
            if not self.session or self.session.closed:
                self.connector = aiohttp.TCPConnector(
                    limit=self.connector_limit,
                    limit_per_host=30,
                    ttl_dns_cache=300
                )
                self.session = aiohttp.ClientSession(
                    connector=self.connector,
                    timeout=self.timeout
                )
            return self.session
    
    async def close(self):
        """Close the session and connector"""
        async with self._lock:
            if self.session and not self.session.closed:
                await self.session.close()
            if self.connector:
                await self.connector.close()
            self.session = None
            self.connector = None


class RateLimiter:
    """Rate limiter for API calls with concurrency control"""
    def __init__(self, max_concurrent=5, requests_per_second=10):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.rate_limit = requests_per_second
        self.last_request_time = 0
        self._lock = asyncio.Lock()
    
    async def acquire(self):
        """Acquire rate limit permission"""
        async with self.semaphore:
            async with self._lock:
                # Calculate required delay
                now = time.time()
                time_since_last = now - self.last_request_time
                min_interval = 1.0 / self.rate_limit
                
                if time_since_last < min_interval:
                    sleep_time = min_interval - time_since_last
                    await asyncio.sleep(sleep_time)
                
                self.last_request_time = time.time()
            
            # Yield while holding the semaphore
            try:
                yield
            finally:
                pass  # Semaphore released automatically


class TaskManager:
    """Manages async tasks with cancellation and timeout support"""
    def __init__(self, max_tasks=10):
        self.max_tasks = max_tasks
        self.tasks: List[asyncio.Task] = []
        self._lock = asyncio.Lock()
    
    async def run_tasks(self, coroutines: List, timeout: int = 300) -> List[Any]:
        """Run tasks with timeout and proper cleanup"""
        async with self._lock:
            try:
                # Create semaphore for task limiting
                sem = asyncio.Semaphore(self.max_tasks)
                
                async def run_with_sem(coro):
                    async with sem:
                        return await coro
                
                # Create tasks
                self.tasks = [asyncio.create_task(run_with_sem(coro)) for coro in coroutines]
                
                # Wait with timeout
                results = await asyncio.wait_for(
                    asyncio.gather(*self.tasks, return_exceptions=True),
                    timeout=timeout
                )
                
                # Filter out exceptions but log them
                clean_results = []
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(f"Task {i} failed: {result}")
                    else:
                        clean_results.append(result)
                
                return clean_results
                
            except asyncio.TimeoutError:
                logger.error(f"Task timeout after {timeout}s, cancelling all tasks")
                # Cancel all tasks
                for task in self.tasks:
                    if not task.done():
                        task.cancel()
                # Wait for cancellation
                await asyncio.gather(*self.tasks, return_exceptions=True)
                raise
            finally:
                self.tasks = []
    
    async def cancel_all(self):
        """Cancel all running tasks"""
        async with self._lock:
            for task in self.tasks:
                if not task.done():
                    task.cancel()
            if self.tasks:
                await asyncio.gather(*self.tasks, return_exceptions=True)
            self.tasks = []


class BoundedResultsBuffer:
    """Memory-bounded buffer for search results with deduplication"""
    def __init__(self, max_size=10000):
        self.max_size = max_size
        self.results: List[Dict[str, Any]] = []
        self.seen_urls: Set[str] = set()
        self._lock = threading.Lock()
    
    def add(self, result: Dict[str, Any]) -> bool:
        """Add a result if not duplicate and buffer not full"""
        with self._lock:
            # Check buffer size
            if len(self.results) >= self.max_size:
                # Remove oldest 10% of results
                remove_count = max(1, self.max_size // 10)
                removed = self.results[:remove_count]
                self.results = self.results[remove_count:]
                
                # Clean up seen_urls
                for r in removed:
                    url = r.get('url')
                    if url:
                        self.seen_urls.discard(url)
                
                logger.warning(f"Buffer full, removed {remove_count} oldest results")
            
            # Check for duplicate
            url = result.get('url')
            if not url:
                return False
                
            if url in self.seen_urls:
                return False
            
            # Add result
            self.seen_urls.add(url)
            self.results.append(result)
            return True
    
    def add_batch(self, results: List[Dict[str, Any]]) -> int:
        """Add multiple results, return count of added"""
        added = 0
        for result in results:
            if self.add(result):
                added += 1
        return added
    
    def get_all(self) -> List[Dict[str, Any]]:
        """Get all results"""
        with self._lock:
            return self.results.copy()
    
    def clear(self):
        """Clear the buffer"""
        with self._lock:
            self.results.clear()
            self.seen_urls.clear()
    
    @property
    def size(self) -> int:
        """Current buffer size"""
        with self._lock:
            return len(self.results)


# Decorators and context managers

def with_timeout(timeout: int = 30):
    """Decorator to add timeout to async functions"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
            except asyncio.TimeoutError:
                logger.error(f"{func.__name__} timed out after {timeout}s")
                return None
            except Exception as e:
                logger.error(f"{func.__name__} failed: {e}")
                raise
        return wrapper
    return decorator


@asynccontextmanager
async def safe_execute(operation_name: str, raise_errors: bool = False):
    """Context manager for safe execution with logging"""
    start_time = time.time()
    try:
        yield
    except asyncio.CancelledError:
        logger.warning(f"{operation_name} was cancelled")
        if raise_errors:
            raise
    except Exception as e:
        logger.error(f"{operation_name} failed: {e}")
        if raise_errors:
            raise
    finally:
        duration = time.time() - start_time
        if duration > 10:  # Log slow operations
            logger.warning(f"{operation_name} took {duration:.2f}s")
        else:
            logger.debug(f"{operation_name} took {duration:.2f}s")


# Global instances (can be imported by other modules)
_global_session_pool = None
_global_rate_limiter = None


def get_session_pool() -> SessionPool:
    """Get the global session pool instance"""
    global _global_session_pool
    if _global_session_pool is None:
        _global_session_pool = SessionPool()
    return _global_session_pool


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance"""
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = RateLimiter()
    return _global_rate_limiter


async def cleanup_global_resources():
    """Clean up all global resources"""
    global _global_session_pool, _global_rate_limiter
    
    if _global_session_pool:
        await _global_session_pool.close()
        _global_session_pool = None
    
    _global_rate_limiter = None
    logger.info("Global resources cleaned up")
