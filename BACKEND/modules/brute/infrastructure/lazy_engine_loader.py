#!/usr/bin/env python3
"""
Lazy Engine Loader for Search Engineer

This module provides a centralized lazy loading system for search engines
to avoid the startup delays caused by importing all engines at module load time.

Features:
- Lazy imports: Engines are only imported when first accessed
- Caching: Once imported, engines are cached for reuse
- Thread-safe: Uses threading locks for safe concurrent access
- Maintains compatibility with existing AVAILABLE flags
- Provides both synchronous and asynchronous interfaces
"""

import sys
import threading
import importlib
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Callable, Union
from functools import wraps
import asyncio

logger = logging.getLogger(__name__)

# Get the project root
PROJECT_ROOT = Path(__file__).resolve().parent
SEARCH_ENGINES_PATH = PROJECT_ROOT / 'engines'

# Ensure engines is in the path
if str(SEARCH_ENGINES_PATH) not in sys.path:
    sys.path.insert(0, str(SEARCH_ENGINES_PATH))


class LazyEngineProxy:
    """
    A proxy object that lazily loads the actual engine class when first accessed.
    This allows us to maintain the same interface as direct imports while deferring
    the actual import until needed.
    """
    
    def __init__(self, module_name: str, class_name: str, fallback_class: Optional[type] = None):
        self.module_name = module_name
        self.class_name = class_name
        self.fallback_class = fallback_class
        self._instance = None
        self._load_error = None
        self._lock = threading.Lock()
    
    def _load(self):
        """Load the actual engine class if not already loaded."""
        if self._instance is None and self._load_error is None:
            with self._lock:
                # Double-check pattern
                if self._instance is None and self._load_error is None:
                    try:
                        module = importlib.import_module(self.module_name)
                        engine_class = getattr(module, self.class_name)
                        self._instance = engine_class()
                        logger.debug(f"Successfully loaded {self.class_name} from {self.module_name}")
                    except Exception as e:
                        self._load_error = e
                        logger.warning(f"Failed to load {self.class_name} from {self.module_name}: {e}")
                        if self.fallback_class:
                            self._instance = self.fallback_class()
    
    def __call__(self, *args, **kwargs):
        """Allow the proxy to be instantiated like a class."""
        self._load()
        if self._instance:
            # If the instance is a class, instantiate it
            if isinstance(self._instance, type):
                return self._instance(*args, **kwargs)
            # Otherwise return the instance itself
            return self._instance
        raise ImportError(f"Could not load {self.class_name}")
    
    def __getattr__(self, name):
        """Proxy attribute access to the loaded instance."""
        self._load()
        if self._instance:
            return getattr(self._instance, name)
        raise ImportError(f"Could not load {self.class_name}")
    
    @property
    def is_available(self):
        """Check if the engine can be loaded without actually loading it."""
        if self._instance is not None:
            return True
        if self._load_error is not None:
            return False
        
        # Try to import without creating instance
        try:
            importlib.import_module(self.module_name)
            return True
        except Exception:
            return False


class LazyEngineLoader:
    """
    Centralized lazy loader for all search engines.
    
    Usage:
        from lazy_engine_loader import LazyEngineLoader
        
        loader = LazyEngineLoader()
        
        # Check availability without loading
        if loader.is_available('google'):
            # Load and use engine
            GoogleSearch = loader.get_engine('google')
            engine = GoogleSearch()
            results = engine.search(query)
    """
    
    # Engine configuration mapping
    ENGINE_CONFIG = {
        'google': {
            'module': 'exact_phrase_recall_runner_google',
            'class': 'GoogleSearch'
        },
        'bing': {
            'module': 'exact_phrase_recall_runner_bing',
            'class': 'BingSearch'
        },
        'yandex': {
            'module': 'exact_phrase_recall_runner_yandex',
            'class': 'YandexSearch'
        },
        'duckduckgo': {
            'module': 'exact_phrase_recall_runner_duckduck',
            'class': 'MaxExactDuckDuckGo'
        },
        'yep': {
            'module': 'exact_phrase_recall_runner_yep',
            'class': 'YepScraper'
        },
        'brave': {
            'module': 'exact_phrase_recall_runner_brave',
            'class': 'BraveSearch'
        },
        'boardreader': {
            'module': 'exact_phrase_recall_runner_boardreader',
            'class': 'ExactPhraseRecallRunnerBoardreaderV2'
        },
        'exa': {
            'module': 'exact_phrase_recall_runner_exa',
            'class': 'ExactPhraseRecallRunnerExa'
        },
        'gdelt': {
            'module': 'exact_phrase_recall_runner_gdelt',
            'class': 'ExactPhraseRecallRunnerGDELT'
        },
        'grok': {
            'module': 'exact_phrase_recall_runner_grok_http',
            'class': 'ExactPhraseRecallRunnerGrok'
        },
        'publicwww': {
            'module': 'exact_phrase_recall_runner_publicwww',
            'class': 'PublicWWWSearch'
        },
        'socialsearcher': {
            'module': 'exact_phrase_recall_runner_socialsearcher',
            'class': 'ExactPhraseRecallRunnerSocialSearcher'
        },
        'newsapi': {
            'module': 'exact_phrase_recall_runner_newsapi',
            'class': 'ExactPhraseRecallRunnerNewsAPI'
        },
        'aleph': {
            'module': 'exact_phrase_recall_runner_aleph',
            'class': 'ExactPhraseRecallRunnerAleph'
        },
        'archiveorg': {
            'module': 'exact_phrase_recall_runner_archiveorg',
            'class': 'ExactPhraseRecallRunnerArchiveOrg'
        },
        'huggingface': {
            'module': 'exact_phrase_recall_runner_huggingface',
            'class': 'ExactPhraseRecallRunnerHuggingFace'
        },
        'wikileaks': {
            'module': 'exact_phrase_recall_runner_wikileaks',
            'class': 'ExactPhraseRecallRunnerWikiLeaks'
        }
    }
    
    def __init__(self):
        self._engines = {}
        self._proxies = {}
        self._lock = threading.Lock()
        self._availability_cache = {}
        
        # Create fallback class for unavailable engines
        self._create_fallback_class()
    
    def _create_fallback_class(self):
        """Create a fallback class for unavailable engines."""
        class FallbackEngine:
            def search(self, *args, **kwargs):
                return []
            
            async def search_async(self, *args, **kwargs):
                return []
        
        self.FallbackEngine = FallbackEngine
    
    def get_engine(self, engine_name: str) -> Union[type, Any]:
        """
        Get an engine by name. Returns a lazy proxy that will load the engine
        when first accessed.
        
        Args:
            engine_name: Name of the engine (e.g., 'google', 'bing')
            
        Returns:
            LazyEngineProxy that behaves like the engine class
        """
        if engine_name not in self.ENGINE_CONFIG:
            raise ValueError(f"Unknown engine: {engine_name}")
        
        if engine_name not in self._proxies:
            with self._lock:
                if engine_name not in self._proxies:
                    config = self.ENGINE_CONFIG[engine_name]
                    proxy = LazyEngineProxy(
                        config['module'],
                        config['class'],
                        self.FallbackEngine
                    )
                    self._proxies[engine_name] = proxy
        
        return self._proxies[engine_name]
    
    def is_available(self, engine_name: str) -> bool:
        """
        Check if an engine is available without loading it.
        
        Args:
            engine_name: Name of the engine
            
        Returns:
            True if the engine can be imported, False otherwise
        """
        if engine_name not in self.ENGINE_CONFIG:
            return False
        
        if engine_name in self._availability_cache:
            return self._availability_cache[engine_name]
        
        proxy = self.get_engine(engine_name)
        available = proxy.is_available
        self._availability_cache[engine_name] = available
        return available
    
    def get_all_engines(self) -> Dict[str, Any]:
        """
        Get all available engines as a dictionary.
        
        Returns:
            Dictionary mapping engine names to their classes
        """
        engines = {}
        for engine_name in self.ENGINE_CONFIG:
            if self.is_available(engine_name):
                engines[engine_name] = self.get_engine(engine_name)
        return engines
    
    def get_availability_flags(self) -> Dict[str, bool]:
        """
        Get availability flags for all engines.
        
        Returns:
            Dictionary mapping engine names to their availability status
        """
        return {
            engine_name: self.is_available(engine_name)
            for engine_name in self.ENGINE_CONFIG
        }
    
    async def preload_engines(self, engine_names: Optional[list] = None):
        """
        Asynchronously preload specified engines.
        
        Args:
            engine_names: List of engine names to preload. If None, preload all.
        """
        if engine_names is None:
            engine_names = list(self.ENGINE_CONFIG.keys())
        
        tasks = []
        for engine_name in engine_names:
            if engine_name in self.ENGINE_CONFIG:
                task = asyncio.create_task(self._preload_engine(engine_name))
                tasks.append(task)
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _preload_engine(self, engine_name: str):
        """Preload a single engine asynchronously."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.get_engine, engine_name)


# Global singleton instance
_loader_instance = None
_loader_lock = threading.Lock()


def get_loader() -> LazyEngineLoader:
    """Get the global LazyEngineLoader instance."""
    global _loader_instance
    if _loader_instance is None:
        with _loader_lock:
            if _loader_instance is None:
                _loader_instance = LazyEngineLoader()
    return _loader_instance


# Convenience functions for backward compatibility
def get_engine(engine_name: str) -> Any:
    """Get an engine by name using the global loader."""
    return get_loader().get_engine(engine_name)


def is_available(engine_name: str) -> bool:
    """Check if an engine is available using the global loader."""
    return get_loader().is_available(engine_name)


def get_availability_flags() -> Dict[str, bool]:
    """Get availability flags for all engines using the global loader."""
    return get_loader().get_availability_flags()


# Create module-level proxies for backward compatibility
# These can be imported directly like: from lazy_engine_loader import GoogleSearch, GOOGLE_AVAILABLE
def _create_module_proxies():
    """Create module-level proxies for all engines."""
    loader = get_loader()
    module = sys.modules[__name__]
    
    for engine_name, config in LazyEngineLoader.ENGINE_CONFIG.items():
        class_name = config['class']
        
        # Create the proxy
        proxy = loader.get_engine(engine_name)
        
        # Add to module
        setattr(module, class_name, proxy)
        
        # Create availability flag
        flag_name = f"{engine_name.upper()}_AVAILABLE"
        setattr(module, flag_name, loader.is_available(engine_name))


# Initialize module-level proxies
_create_module_proxies()


if __name__ == "__main__":
    # Test the lazy loader
    import time
    
    print("Testing LazyEngineLoader...")
    
    # Time the initialization
    start = time.time()
    loader = LazyEngineLoader()
    print(f"Loader initialization: {time.time() - start:.4f}s")
    
    # Check availability without loading
    start = time.time()
    print("\nChecking availability:")
    for engine in ['google', 'bing', 'yandex', 'duckduckgo']:
        available = loader.is_available(engine)
        print(f"  {engine}: {available}")
    print(f"Availability check: {time.time() - start:.4f}s")
    
    # Load an engine
    start = time.time()
    try:
        GoogleSearch = loader.get_engine('google')
        print(f"\nLoaded Google engine: {time.time() - start:.4f}s")
        
        # Try to use it
        engine = GoogleSearch()
        print(f"Google engine instance: {engine}")
    except Exception as e:
        print(f"Error loading Google: {e}")
    
    # Test module-level imports
    print("\nTesting module-level imports:")
    from lazy_engine_loader import GoogleSearch as GS, GOOGLE_AVAILABLE
    print(f"GOOGLE_AVAILABLE: {GOOGLE_AVAILABLE}")
    if GOOGLE_AVAILABLE:
        print(f"GoogleSearch: {GS}")