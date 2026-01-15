#!/usr/bin/env python3
"""
Shared Session Pool - HTTP connection pooling for all search engines
Reduces connection overhead and improves performance

Now with integrated proxy rotation support for SERP scraping.
"""

import os
import time
import threading
import logging
from typing import Dict, Optional, Any, Union, Tuple
from functools import wraps
import warnings
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

# Primary HTTP library
import requests

# Proxy pool integration
try:
    from .proxy_pool import get_pool, get_proxy_config_for_engine, record_proxy_result, ProxyConfig
    PROXY_POOL_AVAILABLE = True
except ImportError:
    PROXY_POOL_AVAILABLE = False
    ProxyConfig = None

# Optional async support
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

logger = logging.getLogger(__name__)


class SessionPoolConfig:
    """Configuration for session pooling"""
    
    # Connection pool settings
    POOL_CONNECTIONS = int(os.environ.get('SESSION_POOL_CONNECTIONS', '20'))
    POOL_MAXSIZE = int(os.environ.get('SESSION_POOL_MAXSIZE', '100'))
    POOL_BLOCK = bool(os.environ.get('SESSION_POOL_BLOCK', 'True'))
    
    # Timeout settings (in seconds)
    CONNECT_TIMEOUT = float(os.environ.get('SESSION_CONNECT_TIMEOUT', '10'))
    READ_TIMEOUT = float(os.environ.get('SESSION_READ_TIMEOUT', '30'))
    
    # Retry configuration
    RETRY_TOTAL = int(os.environ.get('SESSION_RETRY_TOTAL', '3'))
    RETRY_BACKOFF_FACTOR = float(os.environ.get('SESSION_RETRY_BACKOFF_FACTOR', '0.3'))
    RETRY_STATUS_FORCELIST = [413, 429, 500, 502, 503, 504]
    
    # Session lifecycle
    SESSION_MAX_AGE = int(os.environ.get('SESSION_MAX_AGE', '3600'))  # 1 hour
    
    # Performance categories with different timeouts
    PERFORMANCE_TIMEOUTS = {
        'fast': (5, 30),    # (connect, read) for fast engines like Google
        'medium': (10, 60),  # for medium speed engines
        'slow': (15, 120),  # for slow engines or complex queries
        'default': (10, 30)
    }


class SharedSession:
    """Thread-safe session with connection pooling"""
    
    def __init__(self, engine_name: str, config: SessionPoolConfig = None):
        self.engine_name = engine_name
        self.config = config or SessionPoolConfig()
        self.session = None
        self.created_at = 0
        self.lock = threading.RLock()
        self._request_count = 0
        self._last_health_check = 0
        
    def get_session(self, performance_category: str = 'default') -> requests.Session:
        """Get or create a session with appropriate timeouts"""
        with self.lock:
            # Check if session needs to be refreshed
            if self._should_refresh_session():
                self._close_session()
                
            if self.session is None:
                self.session = self._create_session(performance_category)
                self.created_at = time.time()
                
            return self.session
    
    def _should_refresh_session(self) -> bool:
        """Check if session should be refreshed"""
        if self.session is None:
            return False
            
        # Check age
        age = time.time() - self.created_at
        if age > self.config.SESSION_MAX_AGE:
            logger.info(f"Session for {self.engine_name} exceeded max age ({age:.1f}s)")
            return True
            
        # Check health periodically
        if time.time() - self._last_health_check > 300:  # Every 5 minutes
            self._last_health_check = time.time()
            if not self._is_session_healthy():
                logger.warning(f"Session for {self.engine_name} failed health check")
                return True
                
        return False
    
    def _is_session_healthy(self) -> bool:
        """Basic health check for the session"""
        try:
            # Try a simple HEAD request to a reliable endpoint
            response = self.session.head('https://www.google.com', timeout=5)
            return response.status_code < 500
        except Exception as e:
            return False
    
    def _create_session(self, performance_category: str) -> requests.Session:
        """Create a new session with connection pooling"""
        session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=self.config.RETRY_TOTAL,
            backoff_factor=self.config.RETRY_BACKOFF_FACTOR,
            status_forcelist=self.config.RETRY_STATUS_FORCELIST,
            allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"]
        )
        
        # Configure connection pooling
        adapter = HTTPAdapter(
            pool_connections=self.config.POOL_CONNECTIONS,
            pool_maxsize=self.config.POOL_MAXSIZE,
            pool_block=self.config.POOL_BLOCK,
            max_retries=retry_strategy
        )
        
        # Mount adapter for both HTTP and HTTPS
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Set default headers
        session.headers.update({
            'User-Agent': f'Search_Engineer/{self.engine_name} (Session-Pooled)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # Set default timeout based on performance category
        connect_timeout, read_timeout = self.config.PERFORMANCE_TIMEOUTS.get(
            performance_category, 
            self.config.PERFORMANCE_TIMEOUTS['default']
        )
        
        # Store timeout as session default (can be overridden per request)
        session.timeout = (connect_timeout, read_timeout)
        
        logger.info(f"Created new session for {self.engine_name} with {performance_category} timeouts: {session.timeout}")
        return session
    
    def _close_session(self):
        """Close the current session"""
        if self.session:
            try:
                self.session.close()
            except Exception as e:
                logger.error(f"Error closing session for {self.engine_name}: {e}")
            finally:
                self.session = None
    
    def get(self, url: str, **kwargs) -> requests.Response:
        """Perform GET request with session"""
        return self._request('GET', url, **kwargs)
    
    def post(self, url: str, **kwargs) -> requests.Response:
        """Perform POST request with session"""
        return self._request('POST', url, **kwargs)
    
    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Perform request with automatic session management and proxy rotation"""
        perf_category = kwargs.pop('performance_category', 'default')
        use_proxy = kwargs.pop('use_proxy', True)  # Default to using proxy
        session = self.get_session(perf_category)

        # Use session timeout if not specified
        if 'timeout' not in kwargs and hasattr(session, 'timeout'):
            kwargs['timeout'] = session.timeout

        # Inject proxy if available and requested
        proxy_config = None
        if use_proxy and PROXY_POOL_AVAILABLE and 'proxies' not in kwargs:
            proxy_config = get_proxy_config_for_engine(self.engine_name)
            if proxy_config:
                proxy_dict = proxy_config.get_proxy_dict()
                if proxy_dict:
                    kwargs['proxies'] = proxy_dict
                    logger.debug(f"Using proxy {proxy_config.name} for {self.engine_name}")

        self._request_count += 1

        # Make request and track proxy health
        try:
            response = session.request(method, url, **kwargs)
            if proxy_config:
                # Record success if status < 500
                record_proxy_result(proxy_config, response.status_code < 500)
            return response
        except Exception as e:
            if proxy_config:
                record_proxy_result(proxy_config, False)
            raise


class SessionPoolManager:
    """Manages sessions for all search engines"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.sessions: Dict[str, SharedSession] = {}
            self.config = SessionPoolConfig()
            self._initialized = True
            logger.info("SessionPoolManager initialized")
    
    def get_session(self, engine_name: str, performance_category: str = 'default') -> SharedSession:
        """Get or create a shared session for an engine"""
        if engine_name not in self.sessions:
            with self._lock:
                if engine_name not in self.sessions:
                    self.sessions[engine_name] = SharedSession(engine_name, self.config)
                    
        return self.sessions[engine_name]
    
    def get_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all sessions"""
        stats = {}
        for engine_name, session in self.sessions.items():
            with session.lock:
                stats[engine_name] = {
                    'created_at': session.created_at,
                    'age': time.time() - session.created_at if session.created_at else 0,
                    'request_count': session._request_count,
                    'active': session.session is not None
                }
        return stats
    
    def close_all(self):
        """Close all sessions"""
        for session in self.sessions.values():
            session._close_session()
        self.sessions.clear()
        logger.info("All sessions closed")


# Global session pool manager
_pool_manager = SessionPoolManager()


# Convenience functions for easy integration
def get_shared_session(engine_name: str, performance_category: str = 'default') -> requests.Session:
    """Get a shared session for an engine"""
    shared = _pool_manager.get_session(engine_name, performance_category)
    return shared.get_session(performance_category)


def get(url: str, engine_name: str = 'default', performance_category: str = 'default', use_proxy: bool = True, **kwargs) -> requests.Response:
    """Drop-in replacement for requests.get with session pooling and proxy rotation"""
    shared = _pool_manager.get_session(engine_name, performance_category)
    return shared.get(url, performance_category=performance_category, use_proxy=use_proxy, **kwargs)


def post(url: str, engine_name: str = 'default', performance_category: str = 'default', use_proxy: bool = True, **kwargs) -> requests.Response:
    """Drop-in replacement for requests.post with session pooling and proxy rotation"""
    shared = _pool_manager.get_session(engine_name, performance_category)
    return shared.post(url, performance_category=performance_category, use_proxy=use_proxy, **kwargs)


# Proxy-aware convenience function for SERP scraping
def get_with_proxy(url: str, engine_name: str, **kwargs) -> requests.Response:
    """
    GET request with automatic proxy rotation based on engine type.

    Usage:
        from brute.infrastructure.shared_session import get_with_proxy
        response = get_with_proxy("https://www.bing.com/search?q=test", "bing")
    """
    return get(url, engine_name=engine_name, use_proxy=True, **kwargs)


def get_pool_stats() -> Dict[str, Dict[str, Any]]:
    """Get statistics for all pooled sessions"""
    return _pool_manager.get_stats()


def close_all_sessions():
    """Close all pooled sessions"""
    _pool_manager.close_all()


# Async support (optional)
if AIOHTTP_AVAILABLE:
    class AsyncSessionPool:
        """Async session pool using aiohttp"""
        
        def __init__(self):
            self.sessions: Dict[str, aiohttp.ClientSession] = {}
            self.config = SessionPoolConfig()
            self._lock = threading.Lock()
            
        async def get_session(self, engine_name: str) -> aiohttp.ClientSession:
            """Get or create an async session"""
            if engine_name not in self.sessions:
                connector = aiohttp.TCPConnector(
                    limit=self.config.POOL_MAXSIZE,
                    limit_per_host=self.config.POOL_CONNECTIONS,
                    ttl_dns_cache=300
                )
                
                timeout = aiohttp.ClientTimeout(
                    total=None,
                    connect=self.config.CONNECT_TIMEOUT,
                    sock_read=self.config.READ_TIMEOUT
                )
                
                self.sessions[engine_name] = aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout,
                    headers={
                        'User-Agent': f'Search_Engineer/{engine_name} (Async-Session-Pooled)'
                    }
                )
                
            return self.sessions[engine_name]
        
        async def close_all(self):
            """Close all async sessions"""
            for session in self.sessions.values():
                await session.close()
            self.sessions.clear()
    
    # Global async pool
    _async_pool = AsyncSessionPool()
    
    async def get_async_session(engine_name: str) -> aiohttp.ClientSession:
        """Get an async session for an engine"""
        return await _async_pool.get_session(engine_name)


# Backward compatibility
class ConnectionPoolManager:
    """Backward compatibility wrapper"""
    
    def __init__(self):
        logger.info("ConnectionPoolManager is deprecated, using SessionPoolManager")
        
    @staticmethod
    def get_instance():
        return _pool_manager
    
    def get_session(self, engine_code: str) -> requests.Session:
        return get_shared_session(engine_code)


# Performance monitoring decorator
def with_session_pool(engine_name: str, performance_category: str = 'default'):
    """Decorator to add session pooling to a function"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Inject session into kwargs if not present
            if 'session' not in kwargs:
                kwargs['session'] = get_shared_session(engine_name, performance_category)
            return func(*args, **kwargs)
        return wrapper
    return decorator


if __name__ == "__main__":
    # Test the session pooling
    import time
    
    print("Testing session pooling...")
    
    # Test basic functionality
    start = time.time()
    response1 = get('https://httpbin.org/get', engine_name='test', performance_category='fast')
    time1 = time.time() - start
    print(f"First request: {time1:.3f}s")
    
    # Second request should be faster (reused connection)
    start = time.time()
    response2 = get('https://httpbin.org/get', engine_name='test', performance_category='fast')
    time2 = time.time() - start
    print(f"Second request: {time2:.3f}s (should be faster)")
    
    # Show stats
    print("\nSession stats:")
    stats = get_pool_stats()
    for engine, stat in stats.items():
        print(f"  {engine}: {stat}")
    
    # Clean up
    close_all_sessions()
    print("\nAll sessions closed")