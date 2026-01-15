#!/usr/bin/env python3
"""
Engine Imports - Single import module for all search engines
Replace all try/except import blocks with: from engine_imports import *
"""

from .lazy_engine_loader import (
    get_engine,
    is_available,
    get_available_engines,
    get_all_availability_flags,
    EngineManager
)

# Import all engine classes and availability flags dynamically
from .lazy_engine_loader import LazyEngineLoader, _loader

# Create module-level variables for all engines
for engine_name, (module_name, class_name, flag_name) in LazyEngineLoader.ENGINE_CONFIG.items():
    # Set the engine class
    locals()[class_name] = _loader.get_engine_class(engine_name)
    
    # Set the availability flag (will be evaluated lazily)
    locals()[flag_name] = property(lambda self, e=engine_name: _loader.is_available(e))

# Fix the availability flags to be actual booleans, not properties
for engine_name, (_, _, flag_name) in LazyEngineLoader.ENGINE_CONFIG.items():
    # Override with actual boolean values
    exec(f"{flag_name} = is_available('{engine_name}')")

# Special handling for DuckDuckGo alias
if 'MaxExactDuckDuckGo' in locals():
    DuckDuckGoSearch = locals()['MaxExactDuckDuckGo']

# Export all symbols
__all__ = [
    # Functions
    'get_engine',
    'is_available', 
    'get_available_engines',
    'get_all_availability_flags',
    'EngineManager',
    
    # Engine classes
    'GoogleSearch',
    'BingSearch',
    'YandexSearch',
    'DuckDuckGoSearch',
    'MaxExactDuckDuckGo',
    'YepScraper',
    'YepSearch',
    'BraveSearch',
    'BoardReaderSearch',
    'ExaSearch',
    'GDELTSearch',
    'GrokSearch',
    'PublicWWWSearch',
    'SocialSearcherSearch',
    'AlephSearch',
    'ArchiveOrgSearch',
    'HuggingFaceSearch',
    'NewsAPISearch',
    
    # Availability flags
    'GOOGLE_AVAILABLE',
    'BING_AVAILABLE',
    'YANDEX_AVAILABLE',
    'DUCKDUCKGO_AVAILABLE',
    'YEP_AVAILABLE',
    'BRAVE_AVAILABLE',
    'BOARDREADER_AVAILABLE',
    'EXA_AVAILABLE',
    'GDELT_AVAILABLE',
    'GROK_AVAILABLE',
    'PUBLICWWW_AVAILABLE',
    'SOCIALSEARCHER_AVAILABLE',
    'ALEPH_AVAILABLE',
    'ARCHIVEORG_AVAILABLE',
    'HUGGINGFACE_AVAILABLE',
    'NEWSAPI_AVAILABLE',
]

# Add YepSearch alias for compatibility
if 'YepScraper' in locals():
    YepSearch = locals()['YepScraper']