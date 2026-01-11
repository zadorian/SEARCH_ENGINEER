#!/usr/bin/env python3
"""
Brute Force Search Tool - MEMORY OPTIMIZED VERSION
Runs all search engines at maximum recall with disk-based streaming
Prevents memory exhaustion by processing results incrementally
"""

import asyncio
import json
import sys
import time
import logging
import threading
import argparse
from pathlib import Path
from typing import Dict, List, Set, Optional, Any, Iterator, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import queue
import importlib
import os

# Add parent directory to path for direct execution and imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
import psutil  # For memory monitoring
import sqlite3  # For disk-based deduplication
import tempfile  # For temporary storage
import mmap  # For memory-mapped files
import gc  # For garbage collection
from functools import lru_cache  # For caching
import re # For highlighting

# Import snippet enrichment
try:
    from snippet_enrichment import SnippetEnricher
    ENRICHMENT_AVAILABLE = True
except ImportError:
    ENRICHMENT_AVAILABLE = False
    print("Warning: Snippet enrichment not available")

# Load environment variables
load_dotenv()

# Module imports are handled properly through package structure

# Import config
try:
    from brute.infrastructure.config import Config
except ImportError:
    from config import Config
# Query expansion temporarily disabled - moved to query_expansion subfolder
# from brute.infrastructure.query_expansion.query_expander import QueryExpander

# Import snippet aggregator for intelligent snippet merging
try:
    from brute.infrastructure.snippet_aggregator import SnippetAggregator
except ImportError:
    from infrastructure.snippet_aggregator import SnippetAggregator

# Import for rate limiting
from collections import defaultdict
import random

# Import for database storage
try:
    from brute.infrastructure.result_storage_with_relationships import ResultStorage
except ImportError:
    try:
        from infrastructure.result_storage_with_relationships import ResultStorage
    except ImportError:
        ResultStorage = None

try:
    from brute.infrastructure.checkpoint_manager import CheckpointManager
    from brute.infrastructure.progress_monitor import ProgressMonitor
except ImportError:
    try:
        from infrastructure.checkpoint_manager import CheckpointManager
        from infrastructure.progress_monitor import ProgressMonitor
    except ImportError:
        CheckpointManager = None
        ProgressMonitor = None

# Import for exact phrase filtering
try:
    from brute.scraper.phrase_matcher import PhraseMatcher
except ImportError:
    try:
        from scraper.phrase_matcher import PhraseMatcher
    except ImportError:
        PhraseMatcher = None

try:
    from brute.filtering.core.filter_manager import FilterManager
except ImportError:
    try:
        from filtering.core.filter_manager import FilterManager
    except ImportError:
        FilterManager = None

# Import for entity graph integration
try:
    from brute.infrastructure.entity_graph_storage import EntityGraphStorage
except ImportError:
    try:
        from infrastructure.entity_graph_storage import EntityGraphStorage
    except ImportError:
        EntityGraphStorage = None

try:
    from brute.infrastructure.storage_bridge import StorageBridge
except ImportError:
    try:
        from infrastructure.storage_bridge import StorageBridge
    except ImportError:
        StorageBridge = None

# Import for immediate categorization
try:
    from brute.categorizer.categorizer import categorize_url_basic, extract_domain
except ImportError:
    try:
        from categorizer.categorizer import categorize_url_basic, extract_domain
    except ImportError:
        categorize_url_basic = None
        extract_domain = None

# Import CascadeExecutor for optional 3-wave architecture
try:
    from brute.execution.cascade_executor import CascadeExecutor, WavePhase
    CASCADE_EXECUTOR_AVAILABLE = True
except ImportError:
    try:
        from execution.cascade_executor import CascadeExecutor, WavePhase
        CASCADE_EXECUTOR_AVAILABLE = True
    except ImportError:
        CASCADE_EXECUTOR_AVAILABLE = False

# Import EngineAnalytics for per-engine performance tracking
try:
    from brute.execution.engine_analytics import EngineAnalyticsCollector
    ANALYTICS_AVAILABLE = True
except ImportError:
    try:
        from execution.engine_analytics import EngineAnalyticsCollector
        ANALYTICS_AVAILABLE = True
    except ImportError:
        ANALYTICS_AVAILABLE = False

# Import EngineHealthMonitor for circuit breaker pattern
try:
    from brute.infrastructure.engine_health_monitor import EngineHealthMonitor, EngineStatus
    HEALTH_MONITOR_AVAILABLE = True
except ImportError:
    try:
        from infrastructure.engine_health_monitor import EngineHealthMonitor, EngineStatus
        HEALTH_MONITOR_AVAILABLE = True
    except ImportError:
        HEALTH_MONITOR_AVAILABLE = False

# Configure logging from environment
log_level = os.getenv('LOG_LEVEL', 'INFO')
log_file = os.getenv('LOG_FILE', 'brutesearch.log')

logging.basicConfig(
    level=getattr(logging, log_level.upper(), logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ] if os.getenv('ENABLE_DEBUG_MODE', 'false').lower() == 'true' else [logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Engine performance categories for smart timeout management
ENGINE_PERFORMANCE = {
    'fast': ['GO', 'BI', 'BR', 'EX', 'DD', 'YA', 'SS', 'OA', 'CR', 'OL', 'PM', 'AX', 'SE', 'WP', 'BK', 'YO'],     # 30 second timeout - Yandex & SocialSearcher moved to fast tier, You.com added
    'medium': ['GD', 'AL', 'PW', 'GR', 'NA', 'HF', 'GU', 'W', 'NT', 'JS', 'MU', 'SG', 'AA', 'LG', 'BA', 'QW'],   # 60 second timeout - Academic scraping engines, book repos, Baidu, Qwant
    'slow': ['AR', 'YE']      # 120 second timeout - Only truly slow engines (BO removed - disabled stub)
}

# Factory functions for creating engine clients
def create_google_client():
    """Create GoogleSearch instance"""
    from brute.engines.google import GoogleSearch
    return GoogleSearch()

def create_bing_client():
    """Create BingSearch instance"""
    from brute.engines.bing import BingSearch
    return BingSearch()

def create_brave_client():
    """Create BraveSearch instance"""
    from brute.engines.brave import BraveSearch
    return BraveSearch()

def create_yandex_client():
    """Create YandexSearch instance"""
    from brute.engines.yandex import YandexSearch
    return YandexSearch()

def create_yep_scraper():
    """Create YepScraper instance"""
    from brute.engines.yep import YepScraper
    return YepScraper()

def create_archiveorg_client():
    """Create ArchiveOrgSearch instance"""
    from brute.engines.archiveorg import ArchiveOrgSearch
    return ArchiveOrgSearch()

def create_qwant_scraper():
    """Create QwantScraper instance"""
    from brute.engines.qwant_scraper import QwantScraper
    return QwantScraper()

def create_baidu_scraper():
    """Create BaiduScraper instance"""
    from brute.engines.baidu import BaiduScraper
    return BaiduScraper()

# Engine configuration with two-letter codes
ENGINE_CONFIG = {
    'GO': {
        'name': 'Google',
        'module': 'engines.exact_phrase_recall_runner_google',
        'class': 'ExactPhraseRecallRunner',
        'supports_streaming': True,
        'init_kwargs': lambda: {
            'google': create_google_client(),
            'exception_search_iterations': 3,  # Enable exception search for MAXIMUM RECALL
            'use_parallel': True,  # Enable parallel execution for MAXIMUM RECALL
            'max_results_per_query': 100  # MAXIMUM RECALL - get all available results
        }
    },
    'BI': {
        'name': 'Bing',
        'module': 'engines.exact_phrase_recall_runner_bing',
        'class': 'ExactPhraseRecallRunnerBing',
        'engine_class': 'BingSearch',
        'supports_streaming': True,
        'init_kwargs': lambda: {'bing': create_bing_client()}
    },
    # AB removed - file doesn't exist
    'YA': {
        'name': 'Yandex',
        'module': 'engines.exact_phrase_recall_runner_yandex',
        'class': 'ExactPhraseRecallRunnerYandex',
        'supports_streaming': True,
        'init_kwargs': lambda: {'yandex': create_yandex_client()}
    },
    'DD': {
        'name': 'DuckDuckGo',
        'module': 'engines.exact_phrase_recall_runner_duckduck',
        'class': 'MaxExactDuckDuckGo',
        'supports_streaming': False
    },
    'BR': {
        'name': 'Brave',
        'module': 'engines.exact_phrase_recall_runner_brave',
        'class': 'ExactPhraseRecallRunnerBrave',
        'supports_streaming': True,
        'init_kwargs': lambda: {'brave': create_brave_client()}
    },
    'YE': {
        'name': 'Yep',
        'module': 'engines.exact_phrase_recall_runner_yep',
        'class': 'YepExactPhraseRecallRunner',
        'engine_class': 'YepScraper',
        'supports_streaming': True,
        'init_kwargs': lambda: {'scraper': create_yep_scraper()}
    },
    'QW': {
        'name': 'Qwant',
        'module': 'engines.exact_phrase_recall_runner_qwant',
        'class': 'ExactPhraseRecallRunnerQwant',
        'engine_class': 'QwantScraper',
        'supports_streaming': True,
        'init_kwargs': lambda: {
            'scraper': create_qwant_scraper(),
            'locale_groups': None,  # Use default locale for brute.py
            'search_type': 'web',
            'max_results_per_query': 200  # MAXIMUM RECALL
        }
    },
    'AR': {
        'name': 'Archive.org',
        'module': 'engines.exact_phrase_recall_runner_archiveorg',
        'class': 'ExactPhraseRecallRunnerArchiveOrg',
        'supports_streaming': False,
        'init_kwargs': lambda: {'archiveorg_client': create_archiveorg_client()}
    },
    'EX': {
        'name': 'Exa',
        'module': 'engines.exact_phrase_recall_runner_exa',
        'class': 'ExactPhraseRecallRunnerExa',
        'supports_streaming': True,
        # API settings used for exact phrase (not reflected in query syntax)
        'api_settings': 'keyword, no autoprompt'
    },
    'GD': {
        'name': 'GDELT',
        'module': 'engines.exact_phrase_recall_runner_gdelt',
        'class': 'ExactPhraseRecallRunnerGDELT',
        'supports_streaming': False
    },
    'GR': {
        'name': 'Grok',
        'module': 'engines.exact_phrase_recall_runner_grok_http',
        'class': 'ExactPhraseRecallRunnerGrok',
        'supports_streaming': False
    },
    'NA': {
        'name': 'NewsAPI',
        'module': 'engines.exact_phrase_recall_runner_newsapi',
        'class': 'ExactPhraseRecallRunnerNewsAPI',
        'supports_streaming': False
    },
    'PW': {
        'name': 'PublicWWW',
        'module': 'engines.exact_phrase_recall_runner_publicwww',
        'class': 'PublicWWWSearch',
        'supports_streaming': False
    },
    'SS': {
        'name': 'SocialSearcher',
        'module': 'engines.exact_phrase_recall_runner_socialsearcher',
        'class': 'ExactPhraseRecallRunnerSocialSearcher',
        'supports_streaming': True
    },
    'BO': {
        'name': 'BoardReader',
        'module': 'engines.exact_phrase_recall_runner_boardreader',
        'class': 'ExactPhraseRecallRunnerBoardreaderV2',
        'supports_streaming': False,
        'disabled': True,  # STUB: Engine not implemented - module doesn't exist
        'status': 'STUB_NEEDS_IMPLEMENTATION',
        'notes': 'BoardReader forum search aggregator - requires implementation'
    },
    'AL': {
        'name': 'Aleph',
        'module': 'engines.exact_phrase_recall_runner_aleph',
        'class': 'ExactPhraseRecallRunnerAleph',
        'supports_streaming': False
    },
    'HF': {
        'name': 'HuggingFace',
        'module': 'engines.exact_phrase_recall_runner_huggingface_fixed',
        'class': 'MaxExactHuggingFace',
        'supports_streaming': True
    },
    'W': {
        'name': 'WikiLeaks',
        'module': 'engines.exact_phrase_recall_runner_wikileaks',
        'class': 'ExactPhraseRecallRunnerWikiLeaks',
        'supports_streaming': True
    },
    'OA': {
        'name': 'OpenAlex',
        'module': 'engines.exact_phrase_recall_runner_openalex',
        'class': 'ExactPhraseRecallRunnerOpenAlex',
        'supports_streaming': True
    },
    'GU': {
        'name': 'Gutenberg',
        'module': 'engines.exact_phrase_recall_runner_gutenberg',
        'class': 'ExactPhraseRecallRunnerGutenberg',
        'supports_streaming': False
    },
    'CR': {
        'name': 'Crossref',
        'module': 'engines.exact_phrase_recall_runner_crossref',
        'class': 'ExactPhraseRecallRunnerCrossref',
        'supports_streaming': True
    },
    'OL': {
        'name': 'OpenLibrary',
        'module': 'engines.exact_phrase_recall_runner_openlibrary',
        'class': 'ExactPhraseRecallRunnerOpenLibrary',
        'supports_streaming': True
    },
    'PM': {
        'name': 'PubMed',
        'module': 'engines.exact_phrase_recall_runner_pubmed',
        'class': 'ExactPhraseRecallRunnerPubMed',
        'supports_streaming': True
    },
    'AX': {
        'name': 'arXiv',
        'module': 'engines.exact_phrase_recall_runner_arxiv',
        'class': 'ExactPhraseRecallRunnerArxiv',
        'supports_streaming': True
    },
    'SE': {
        'name': 'SemanticScholar',
        'module': 'engines.exact_phrase_recall_runner_semantic_scholar',
        'class': 'ExactPhraseRecallRunnerSemanticScholar',
        'supports_streaming': True
    },
    'WP': {
        'name': 'Wikipedia',
        'module': 'engines.exact_phrase_recall_runner_wikipedia',
        'class': 'ExactPhraseRecallRunnerWikipedia',
        'supports_streaming': True
    },
    'NT': {
        'name': 'Nature',
        'module': 'engines.exact_phrase_recall_runner_nature',
        'class': 'ExactPhraseRecallRunnerNature',
        'supports_streaming': False
    },
    'JS': {
        'name': 'JSTOR',
        'module': 'engines.exact_phrase_recall_runner_jstor',
        'class': 'ExactPhraseRecallRunnerJSTOR',
        'supports_streaming': False
    },
    'MU': {
        'name': 'ProjectMUSE',
        'module': 'engines.exact_phrase_recall_runner_muse',
        'class': 'ExactPhraseRecallRunnerMUSE',
        'supports_streaming': False
    },
    'SG': {
        'name': 'SAGEJournals',
        'module': 'engines.exact_phrase_recall_runner_sage',
        'class': 'ExactPhraseRecallRunnerSAGE',
        'supports_streaming': False
    },
    'BK': {
        'name': 'Books',
        'module': 'brute.targeted_searches.special.book',
        'class': 'BookSearchRunner',
        'supports_streaming': True,
        'is_local': True  # Mark as local search to skip API rate limiting
    },
    'AA': {
        'name': 'AnnasArchive',
        'module': 'engines.exact_phrase_recall_runner_annas_archive',
        'class': 'ExactPhraseRecallRunnerAnnasArchive',
        'supports_streaming': True,
        'init_kwargs': lambda: {'is_academic': True}  # Search both books and journals
    },
    'LG': {
        'name': 'LibGen',
        'module': 'engines.exact_phrase_recall_runner_libgen',
        'class': 'ExactPhraseRecallRunnerLibGen',
        'supports_streaming': True
    },
    'BA': {
        'name': 'Baidu',
        'module': 'engines.exact_phrase_recall_runner_baidu',
        'class': 'ExactPhraseRecallRunnerBaidu',
        'engine_class': 'BaiduScraper',
        'supports_streaming': True,
        'init_kwargs': lambda: {
            'scraper': create_baidu_scraper(),
            'max_results_per_query': 200  # MAXIMUM RECALL
        }
    },
    'YO': {
        'name': 'You.com',
        'module': 'engines.exact_phrase_recall_runner_you',
        'class': 'ExactPhraseRecallRunnerYou',
        'supports_streaming': True,
        'init_kwargs': lambda: {
            'max_results_per_query': 100  # You.com paginates at 20 per request
        }
    },
    'BS': {
        'name': 'BareSearch',
        'module': 'engines.exact_phrase_recall_runner_baresearch',
        'class': 'ExactPhraseRecallRunnerBareSearch',
        'supports_streaming': False,
        'init_kwargs': lambda: {}
    },
    'SP': {
        'name': 'Startpage',
        'module': 'engines.exact_phrase_recall_runner_startpage',
        'class': 'ExactPhraseRecallRunnerStartpage',
        'supports_streaming': False,
        'init_kwargs': lambda: {}
    },
    # === LOCAL CORPUS ENGINES ===
    'CY': {
        'name': 'CYMONIDES',
        'module': 'engines.cymonides',
        'class': 'CymonidesRunner',
        'supports_streaming': True,
        'is_local': True,  # No API rate limiting needed
        'init_kwargs': lambda: {
            'max_results_per_query': 500  # Local ES can handle high volume
        }
    }
}


# Prefer unified thin engine wrappers when available. Keys are existing engine codes.
WRAPPER_ENGINE_MAP = {
    # Core web
    'GO': ('engines.google', 'GoogleEngine'),
    'BI': ('engines.bing', 'BingEngine'),
    'BR': ('engines.brave', 'BraveEngine'),
    'YA': ('engines.yandex', 'YandexEngine'),
    'DD': ('engines.duckduckgo', 'DuckDuckGoEngine'),
    'QW': ('engines.qwant', 'QwantEngine'),
    'EX': ('engines.exa', 'ExaEngine'),
    # News/feeds
    'NA': ('engines.newsapi', 'NewsAPIEngine'),
    'GD': ('engines.gdelt', 'GDELTEngine'),
    # Utilities/special
    'PW': ('engines.publicwww', 'PublicWWWEngine'),
    'BO': ('engines.boardreader', 'BoardReaderEngine'),
    # Archive/alt
    'AR': ('engines.archiveorg', 'ArchiveOrgEngine'),
    'BA': ('engines.baidu', 'BaiduEngine'),
    'YE': ('engines.yep', 'YepEngine'),
    # Academic/data
    'AB': ('engines.azure_bing', 'AzureBingEngine'),
    'GR': ('engines.grok', 'GrokEngine'),
    'W': ('engines.wikileaks', 'WikiLeaksEngine'),
    'OA': ('engines.openalex', 'OpenAlexEngine'),
    'GU': ('engines.gutenberg', 'GutenbergEngine'),
    'CR': ('engines.crossref', 'CrossrefEngine'),
    'OL': ('engines.openlibrary', 'OpenLibraryEngine'),
    'PM': ('engines.pubmed', 'PubMedEngine'),
    'AX': ('engines.arxiv', 'ArxivEngine'),
    'SE': ('engines.semanticscholar', 'SemanticScholarEngine'),
    'WP': ('engines.wikipedia', 'WikipediaEngine'),
    'NT': ('engines.nature', 'NatureEngine'),
    'JS': ('engines.jstor', 'JSTOREngine'),
    'MU': ('engines.muse', 'ProjectMUSEEngine'),
    'SG': ('engines.sage', 'SAGEJournalsEngine'),
    # Local corpus
    'CY': ('engines.cymonides', 'CymonidesEngine'),
}

# Reasonable max results per engine when using wrappers
WRAPPER_ENGINE_MAX = {
    'GO': 100,
    'BI': 100,
    'BR': 100,
    'YA': 100,
    'DD': 500,
    'QW': 200,
    'EX': 100,
    'NA': 100,
    'GD': 200,
    'PW': 200,
    'BO': 100,
    'AR': 100,
    'BA': 200,
    'YE': 100,
    'AB': 100,
    'GR': 100,
    'W': 200,
    'OA': 200,
    'GU': 200,
    'CR': 200,
    'OL': 200,
    'PM': 100,
    'AX': 200,
    'SE': 200,
    'WP': 200,
    'NT': 50,
    'JS': 50,
    'MU': 50,
    'SG': 50,
    # Local corpus (no rate limit - local ES)
    'CY': 500,
}


# Import AdaptiveRateLimiter from shared module
try:
    from brute.infrastructure.rate_limiter import AdaptiveRateLimiter
except ImportError:
    try:
        from infrastructure.rate_limiter import AdaptiveRateLimiter
    except ImportError:
        AdaptiveRateLimiter = None

# Removed inline AdaptiveRateLimiter class definition to avoid duplication


class PriorityResultQueue:
    """Priority queue for processing results based on engine quality and speed"""
    
    def __init__(self):
        self._queue = queue.PriorityQueue()
        self._engine_priorities = {
            # Tier 1 - Highest quality, fastest (BRAVE AND EXA ARE FAST!)
            'GO': 1, 'BI': 1, 'BR': 1, 'EX': 1, 'YA': 1, 'DD': 2, 'SS': 2,
            # Tier 2 - Good quality, moderate speed
            'GR': 3, 'HF': 3, 'GD': 3, 'AL': 3, 'PW': 3, 'QW': 3,
            # Tier 3 - Specialized sources  
            'W': 4, 'BO': 4, 'NA': 4,
            # Tier 4 - Academic/specialized
            'OA': 5, 'CR': 5, 'OL': 5, 'PM': 5,
            'AX': 5, 'SE': 5, 'WP': 5, 'BK': 5,
            'GU': 5, 'NT': 5, 'JS': 5, 'MU': 5,
            'SG': 5, 'AA': 5, 'LG': 5, 'BA': 5,
            # Tier 5 - Slow/limited
            'AR': 6, 'YE': 6
        }
        self._result_count = 0
        self._lock = threading.Lock()
    
    def put(self, result: Dict[str, Any], engine_code: str):
        """Add result with priority based on engine quality"""
        priority = self._engine_priorities.get(engine_code, 9)
        # Use negative count for FIFO within same priority
        with self._lock:
            self._result_count += 1
            # Priority tuple: (engine_priority, order_received, result, engine)
            self._queue.put((priority, self._result_count, result, engine_code))
    
    def get(self, timeout: float = None) -> Tuple[Dict[str, Any], str]:
        """Get highest priority result"""
        try:
            priority, order, result, engine = self._queue.get(timeout=timeout)
            return result, engine
        except queue.Empty:
            return None, None
    
    def qsize(self) -> int:
        """Get approximate queue size"""
        return self._queue.qsize()
    
    def empty(self) -> bool:
        """Check if queue is empty"""
        return self._queue.empty()


class ResultDeduplicator:
    """Thread-safe deduplicator for search results with snippet aggregation"""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._seen_urls: Set[str] = set()
        self._results: Dict[str, Dict[str, Any]] = {}
        self._snippet_aggregator = SnippetAggregator()
        
    def add_result(self, url: str, title: str, snippet: str, source: str) -> Dict[str, Any]:
        """Add a result and return the deduplicated entry"""
        with self._lock:
            # Add to snippet aggregator
            self._snippet_aggregator.add_result({
                'url': url,
                'title': title,
                'snippet': snippet,
                'source': source
            })
            
            if url not in self._seen_urls:
                # New URL
                self._seen_urls.add(url)
                result = {
                    'url': url,
                    'title': title,
                    'sources': [source],
                    'snippets': {source: snippet},
                    'first_seen': datetime.now().isoformat(),
                    'source_count': 1,
                    'aggregated_snippet': snippet  # Will be updated later
                }
                self._results[url] = result
                return {'action': 'new', 'result': result}
            else:
                # Existing URL - add source and snippet
                result = self._results[url]
                if source not in result['sources']:
                    result['sources'].append(source)
                    result['source_count'] += 1
                result['snippets'][source] = snippet
                
                # Update aggregated snippet
                result['aggregated_snippet'] = self._snippet_aggregator.aggregate_snippets(url)
                
                # Select best title (longest or most informative)
                titles = list(self._snippet_aggregator.url_titles.get(url, set()))
                if titles:
                    result['title'] = max(titles, key=lambda t: len(t))
                
                return {'action': 'update', 'result': result}


class JSONStreamWriter:
    """Handles streaming JSON output"""
    
    def __init__(self, output_file: str):
        self.output_file = output_file
        self._lock = threading.Lock()
        self._first_write = True
        
        # Initialize JSON file
        with open(output_file, 'w') as f:
            f.write('{\n  "search_started": "' + datetime.now().isoformat() + '",\n')
            f.write('  "results": [\n')
    
    def write_result(self, result: Dict[str, Any], action: str):
        """MEMORY OPTIMIZED: Immediate streaming write to minimize RAM usage"""
        with self._lock:
            # MEMORY OPTIMIZATION: Write immediately instead of buffering
            # This prevents memory buildup during large searches
            with open(self.output_file, 'r+') as f:
                f.seek(0, 2)  # Go to end
                current_pos = f.tell()
                
                if not self._first_write:
                    # Go to end and back up before closing ]
                    # Find the closing ] and position before it
                    f.seek(max(0, current_pos - 10))
                    tail = f.read()
                    close_pos = tail.rfind('\n  ]\n}')
                    if close_pos != -1:
                        f.seek(current_pos - 10 + close_pos)
                    else:
                        # Only fallback seek if we aren't sure where we are, but don't do it blindly
                        # If we can't find the closing tag, better to just append than corrupt
                        logger.warning("Could not find closing JSON tag to overwrite, appending instead")
                        f.seek(0, 2) 
                
                # Write the new result
                if not self._first_write:
                    f.write(',\n')
                else:
                    self._first_write = False
                
                # Compact JSON for speed and memory
                json.dump(result, f, separators=(',', ':'))
                f.write('\n  ]\n}')
                f.flush()  # Force immediate write
    
    def _flush_buffer(self):
        """Legacy buffer flush method - no longer used in streaming mode"""
        # MEMORY OPTIMIZATION: This method is no longer used
        # Results are now written immediately to minimize memory usage
        pass
    
    def finalize(self, stats: Dict[str, Any]):
        """Finalize the JSON file with statistics"""
        with self._lock:
            # MEMORY OPTIMIZED: Direct file modification for minimal memory usage
            with open(self.output_file, 'r+') as f:
                f.seek(0, 2)  # Go to end
                current_pos = f.tell()
                
                # Find and replace the closing structure
                f.seek(max(0, current_pos - 10))
                tail = f.read()
                close_pos = tail.rfind('\n  ]\n}')
                
                if close_pos != -1:
                    # Position at the start of the closing structure
                    f.seek(current_pos - 10 + close_pos)
                    f.write('\n  ],\n')
                    f.write('  "search_completed": "' + datetime.now().isoformat() + '",\n')
                    f.write('  "statistics": ')
                    json.dump(stats, f, separators=(',', ':'))
                    f.write('\n}')
                    f.truncate()  # Remove any extra content


class ConnectionPoolManager:
    """Global connection pool for HTTP performance optimization"""
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'session'):
            self.session = requests.Session()
            
            # SPEED OPTIMIZATION: Connection pooling with retry strategy
            retry_strategy = Retry(
                total=3,
                backoff_factor=0.1,
                status_forcelist=[429, 500, 502, 503, 504],
            )
            
            adapter = HTTPAdapter(
                pool_connections=200,  # DOUBLED for maximum speed!
                pool_maxsize=400,      # DOUBLED for maximum concurrency!
                max_retries=retry_strategy,
                pool_block=False
            )
            
            self.session.mount("http://", adapter)
            self.session.mount("https://", adapter)
            
            # Keep connections alive
            self.session.headers.update({
                'Connection': 'keep-alive',
                'Keep-Alive': 'timeout=30, max=100'
            })
            
            logger.info("🚀 Connection pool initialized: 500 connections per pool")
    
    def get_session(self):
        return self.session


class MemoryMonitor:
    """Monitor memory usage and prevent exhaustion"""
    
    def __init__(self, max_memory_mb: int = None):
        self.process = psutil.Process()
        # Default to 80% of available memory
        total_memory = psutil.virtual_memory().total / (1024 * 1024)  # Convert to MB
        self.max_memory_mb = max_memory_mb or int(total_memory * 0.8)
        self.initial_memory = self.get_memory_usage()
        logger.info(f"Memory monitor initialized: Max {self.max_memory_mb}MB, Current {self.initial_memory}MB")
    
    def get_memory_usage(self) -> float:
        """Get current memory usage in MB"""
        return self.process.memory_info().rss / (1024 * 1024)
    
    def check_memory(self) -> tuple[bool, float]:
        """Check if memory usage is safe. Returns (is_safe, current_usage)"""
        current = self.get_memory_usage()
        is_safe = current < self.max_memory_mb
        
        # Progressive warnings and throttling
        percentage = (current / self.max_memory_mb) * 100
        if percentage > 90:
            logger.error(f"CRITICAL: Memory at {percentage:.1f}% ({current:.1f}MB / {self.max_memory_mb}MB)")
        elif percentage > 80:
            logger.warning(f"HIGH: Memory at {percentage:.1f}% ({current:.1f}MB / {self.max_memory_mb}MB)")
        elif percentage > 70:
            logger.info(f"MODERATE: Memory at {percentage:.1f}% ({current:.1f}MB / {self.max_memory_mb}MB)")
        
        return is_safe, current
    
    def get_throttle_delay(self) -> float:
        """Get progressive throttle delay based on memory usage"""
        current = self.get_memory_usage()
        percentage = (current / self.max_memory_mb) * 100
        
        if percentage > 90:
            return 2.0  # 2 second delay
        elif percentage > 80:
            return 1.0  # 1 second delay
        elif percentage > 70:
            return 0.5  # 500ms delay
        elif percentage > 60:
            return 0.1  # 100ms delay
        else:
            return 0  # No delay
    
    def wait_for_memory(self, target_mb: float = None):
        """Wait until memory usage drops below target"""
        target = target_mb or (self.max_memory_mb * 0.7)  # 70% of max
        wait_count = 0
        while True:
            is_safe, current = self.check_memory()
            if current < target:
                break
            logger.warning(f"Memory high: {current:.1f}MB / {self.max_memory_mb}MB. Waiting... (attempt {wait_count + 1})")
            
            # Aggressive memory cleanup
            gc.collect()  # Force garbage collection
            gc.collect()  # Run twice for better cleanup
            
            # Emergency brake: if memory is critically high (90%+), pause longer
            if current > (self.max_memory_mb * 0.9):
                logger.error(f"CRITICAL MEMORY USAGE: {current:.1f}MB - implementing emergency pause")
                time.sleep(10)  # Longer pause for critical memory
            else:
                time.sleep(2)
            
            wait_count += 1
            # Safety valve: if we've waited too long, reduce max memory threshold
            if wait_count > 10:
                self.max_memory_mb = int(self.max_memory_mb * 0.9)
                logger.warning(f"Reducing memory threshold to {self.max_memory_mb}MB due to persistent high usage")
                wait_count = 0


class DiskDeduplicator:
    """Disk-based deduplication using SQLite to minimize memory usage"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or tempfile.mktemp(suffix='.db')
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._lock = threading.Lock()
        self._init_db()
        logger.info(f"Disk deduplicator initialized at {self.db_path}")
    
    def _init_db(self):
        """Initialize the deduplication database"""
        with self._lock:
            cursor = self.conn.cursor()
            
            # Enable WAL mode for better concurrency
            cursor.execute('PRAGMA journal_mode=WAL')
            cursor.execute('PRAGMA synchronous=NORMAL')  # Faster writes
            cursor.execute('PRAGMA cache_size=10000')  # Larger cache
            cursor.execute('PRAGMA temp_store=MEMORY')  # Use memory for temp tables
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS seen_urls (
                    url TEXT PRIMARY KEY,
                    title TEXT,
                    snippet TEXT,
                    sources TEXT,
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    scraped_content TEXT,
                    scraped_at TIMESTAMP,
                    content_metadata TEXT
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_url ON seen_urls(url)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_scraped_at ON seen_urls(scraped_at)')
            
            # Add scraped content columns to existing tables if they don't exist
            self._migrate_schema()
            
            self.conn.commit()
    
    def _migrate_schema(self):
        """Add scraped content columns to existing databases"""
        try:
            cursor = self.conn.cursor()
            # Check if columns exist
            cursor.execute("PRAGMA table_info(seen_urls)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'scraped_content' not in columns:
                cursor.execute("ALTER TABLE seen_urls ADD COLUMN scraped_content TEXT")
            if 'scraped_at' not in columns:
                cursor.execute("ALTER TABLE seen_urls ADD COLUMN scraped_at TIMESTAMP")
            if 'content_metadata' not in columns:
                cursor.execute("ALTER TABLE seen_urls ADD COLUMN content_metadata TEXT")
                
        except Exception as e:
            logger.warning(f"DiskDeduplicator schema migration warning: {e}")
    
    def add_url(self, url: str, title: str, snippet: str, source: str, metadata: dict = None) -> tuple[bool, list]:
        """Add URL and return (is_new, existing_sources)"""
        logger.debug(f"DEBUG: add_url called with URL: {url[:50]}..., source: {source}")
        normalized_url = self._normalize_url(url)
        
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('SELECT sources, content_metadata FROM seen_urls WHERE url = ?', (normalized_url,))
            result = cursor.fetchone()
            
            if result:
                # URL exists, update sources
                existing_sources = result[0].split('+')
                if source not in existing_sources:
                    existing_sources.append(source)
                    
                    # Merge metadata if provided
                    if metadata:
                        try:
                            existing_metadata = json.loads(result[1]) if result[1] else {}
                            # Merge new metadata, preserving existing non-null values
                            for key, value in metadata.items():
                                if value is not None and (key not in existing_metadata or existing_metadata[key] is None):
                                    existing_metadata[key] = value
                            metadata_json = json.dumps(existing_metadata)
                        except Exception as e:
                            metadata_json = json.dumps(metadata) if metadata else None
                    else:
                        metadata_json = result[1]
                    
                    cursor.execute('UPDATE seen_urls SET sources = ?, content_metadata = ? WHERE url = ?',
                                 ('+'.join(existing_sources), metadata_json, normalized_url))
                    self.conn.commit()
                return False, existing_sources
            else:
                # New URL
                metadata_json = json.dumps(metadata) if metadata else None
                logger.debug(f"DEBUG: Inserting new URL: {normalized_url[:50]}...")
                cursor.execute('INSERT INTO seen_urls (url, title, snippet, sources, content_metadata) VALUES (?, ?, ?, ?, ?)',
                             (normalized_url, title, snippet, source, metadata_json))
                self.conn.commit()
                logger.debug(f"DEBUG: Successfully inserted and committed URL")
                return True, [source]
    
    def _normalize_url(self, url: str) -> str:
        """Normalize URL for deduplication"""
        url = url.lower().strip()
        url = url.replace('http://', '').replace('https://', '')
        url = url.replace('www.', '')
        if url.endswith('/'):
            url = url[:-1]
        return url
    
    def get_stats(self) -> dict:
        """Get deduplication statistics"""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM seen_urls')
            unique_count = cursor.fetchone()[0]
            return {'unique_urls': unique_count}
    
    def get_all_results(self) -> list:
        """Get all seen URLs as a list of result dicts for compatibility"""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('SELECT url, title, snippet, sources, scraped_content, scraped_at FROM seen_urls')
            results = []
            for row in cursor.fetchall():
                url, title, snippet, sources, scraped_content, scraped_at = row
                result = {
                    'url': url,
                    'title': title,
                    'snippet': snippet,
                    'sources': sources.split('+') if sources else []
                }
                # Add scraped content if available
                if scraped_content:
                    result['scraped_content'] = scraped_content
                    result['scraped_at'] = scraped_at
                results.append(result)
            return results
    
    def update_scraped_content(self, url: str, content: str, title: str = None, metadata: dict = None) -> bool:
        """
        Update scraped content for a URL
        
        Args:
            url: The URL to update
            content: The scraped markdown content
            title: Optional title from scraping
            metadata: Optional metadata from scraping
            
        Returns:
            True if updated, False if URL not found
        """
        normalized_url = self._normalize_url(url)
        
        with self._lock:
            cursor = self.conn.cursor()
            
            # Check if URL exists
            cursor.execute('SELECT url FROM seen_urls WHERE url = ?', (normalized_url,))
            if not cursor.fetchone():
                return False
            
            # Prepare content metadata
            content_meta = {
                'title': title,
                'content_length': len(content) if content else 0,
                'metadata': metadata or {},
                'scraping_source': 'firecrawl',
                'scraped_timestamp': datetime.now().isoformat()
            }
            
            # Update the record
            cursor.execute('''
                UPDATE seen_urls 
                SET scraped_content = ?, 
                    scraped_at = CURRENT_TIMESTAMP, 
                    content_metadata = ?
                WHERE url = ?
            ''', (content, json.dumps(content_meta), normalized_url))
            
            self.conn.commit()
            return True
    
    def get_scraped_content(self, url: str) -> Optional[dict]:
        """
        Get scraped content for a URL
        
        Args:
            url: The URL to retrieve content for
            
        Returns:
            Dict with scraped content data or None if not found
        """
        normalized_url = self._normalize_url(url)
        
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT scraped_content, scraped_at, content_metadata, title, snippet
                FROM seen_urls 
                WHERE url = ? AND scraped_content IS NOT NULL
            ''', (normalized_url,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            content, scraped_at, content_metadata, title, snippet = row
            
            # Parse metadata
            try:
                content_meta = json.loads(content_metadata) if content_metadata else {}
            except json.JSONDecodeError:
                content_meta = {}
            
            return {
                'url': url,
                'content': content,
                'scraped_at': scraped_at,
                'title': content_meta.get('title', title),
                'content_length': len(content) if content else 0,
                'metadata': content_meta.get('metadata', {}),
                'scraping_source': content_meta.get('scraping_source', 'unknown'),
                'snippet': snippet
            }
    
    def get_scraped_urls(self) -> List[str]:
        """Get list of all URLs that have been scraped"""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT url FROM seen_urls 
                WHERE scraped_content IS NOT NULL 
                ORDER BY scraped_at DESC
            ''')
            return [row[0] for row in cursor.fetchall()]
    
    def get_scraping_statistics(self) -> dict:
        """Get statistics about scraped content"""
        with self._lock:
            cursor = self.conn.cursor()
            
            # Total URLs
            cursor.execute('SELECT COUNT(*) FROM seen_urls')
            total_urls = cursor.fetchone()[0]
            
            # Scraped URLs
            cursor.execute('SELECT COUNT(*) FROM seen_urls WHERE scraped_content IS NOT NULL')
            scraped_urls = cursor.fetchone()[0]
            
            # Content sizes
            cursor.execute('SELECT LENGTH(scraped_content) FROM seen_urls WHERE scraped_content IS NOT NULL')
            content_sizes = [row[0] for row in cursor.fetchall()]
            
            total_content_size = sum(content_sizes)
            average_content_size = total_content_size / len(content_sizes) if content_sizes else 0
            
            return {
                'total_urls': total_urls,
                'scraped_urls': scraped_urls,
                'scraping_percentage': (scraped_urls / total_urls * 100) if total_urls > 0 else 0,
                'total_content_size': total_content_size,
                'average_content_size': int(average_content_size),
                'content_size_range': {
                    'min': min(content_sizes) if content_sizes else 0,
                    'max': max(content_sizes) if content_sizes else 0
                }
            }
    
    def cleanup(self):
        """Clean up database"""
        self.conn.close()
        if os.path.exists(self.db_path) and self.db_path.startswith(tempfile.gettempdir()):
            os.unlink(self.db_path)


# SQL Storage Verification Functions
def is_huggingface_result(result):
    """
    Detect if result is from HuggingFace engine or domain.
    
    Args:
        result: Search result dictionary
        
    Returns:
        bool: True if result is from HuggingFace
    """
    # Check engine code
    if result.get('engine') == 'HF':
        return True
    
    # Check if HF is in sources
    sources = result.get('sources', [])
    if isinstance(sources, str):
        sources = sources.split('+') if '+' in sources else [sources]
    if 'HF' in sources:
        return True
    
    # Check domain patterns for HuggingFace
    url = result.get('url', '')
    hf_domains = [
        'huggingface.co',
        'hf.co', 
        'huggingface.com'
    ]
    
    for domain in hf_domains:
        if domain in url.lower():
            return True
    
    return False

def extract_domain(url):
    """
    Extract domain from URL for site: search.
    
    Args:
        url: Full URL
        
    Returns:
        str: Domain name
    """
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc.lower()
    except Exception:
        # Fallback: basic string extraction
        if '//' in url:
            domain_part = url.split('//')[1].split('/')[0]
            return domain_part.lower()
        return url

async def verify_site_search(domain, query, engines=['BR', 'GO', 'BI']):
    """
    Verify if domain contains exact phrase using site: search.
    
    Args:
        domain: Domain to search within
        query: Exact phrase to search for
        engines: List of engines to try in order
        
    Returns:
        bool: True if exact phrase found on domain
    """
    import asyncio
    
    site_query = f'site:{domain} "{query}"'
    
    for engine_code in engines:
        try:
            # Import the appropriate engine
            if engine_code == 'BR':
                from brute.engines.brave import BraveSearch
                engine = BraveSearch()
            elif engine_code == 'GO':
                from brute.engines.google import GoogleSearch
                engine = GoogleSearch()
            elif engine_code == 'BI':
                from brute.engines.bing import BingSearch
                engine = BingSearch()
            else:
                continue
            
            # Perform single search
            results = list(engine.search(site_query, max_results=1))
            
            if results and len(results) > 0:
                logger.info(f"✅ SITE VERIFICATION: {domain} contains '{query}' (via {engine_code})")
                return True
                
        except Exception as e:
            logger.warning(f"⚠️ SITE VERIFICATION: {engine_code} failed for {domain}: {e}")
            continue
    
    logger.info(f"❌ SITE VERIFICATION: {domain} does NOT contain '{query}'")
    return False

class BruteSearchEngine:
    """Main search orchestrator"""
    
    def __init__(self, keyword: str, output_file: str = None, 
                 engines: Optional[List[str]] = None, max_workers: int = None,
                 checkpoint_id: Optional[str] = None, event_emitter=None, return_results: bool = False):
        self.keyword = keyword
        self.event_emitter = event_emitter  # For WebSocket events
        self._search_start_time = None
        self.return_results = return_results
        self.final_results = [] if return_results else None
        
        # Initialize checkpoint manager
        self.checkpoint_id = checkpoint_id or f"search_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.checkpoint_manager = CheckpointManager(self.checkpoint_id)
        
        # Initialize progress monitor
        self.progress_monitor = ProgressMonitor()
        self.enable_progress_monitor = os.getenv('ENABLE_PROGRESS_MONITOR', 'true').lower() == 'true'
        
        # Use environment variables for defaults
        default_output_dir = os.getenv('DEFAULT_OUTPUT_DIR', './results')
        Path(default_output_dir).mkdir(exist_ok=True)
        
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = os.path.join(default_output_dir, f'search_{timestamp}.json')
        
        self.output_file = output_file
        
        # Categorization setup
        self.categorization_queue = []
        self.categorized_results = {}
        self.categorization_batch_size = 50
        self._categorizer_lock = threading.Lock()
        
        # Domain categorization cache for performance
        self.domain_cache = {}
        self.cache_hits = 0
        self.cache_misses = 0
        print("🧠 Domain categorization cache initialized")
        
        # Scraping setup (for first 200 results) - ONLY if enabled
        self.enable_scraping = os.getenv('ENABLE_SCRAPING', 'false').lower() == 'true'
        self.scraping_queue = []
        self.scraped_urls = set()
        self.scraping_batch_size = 50
        self.max_scrape_results = 200
        self._scraper_lock = threading.Lock()
        self._scraper = None  # Lazy load
        
        if self.enable_scraping:
            print("🔍 Automatic scraping ENABLED (set ENABLE_SCRAPING=false to disable)")
        else:
            print("🚫 Automatic scraping DISABLED (set ENABLE_SCRAPING=true to enable)")
        
        # Database storage setup
        self.db_storage = None
        self.entity_storage = None
        self.storage_bridge = None
        self.enable_db_storage = os.getenv('ENABLE_DB_STORAGE', 'false').lower() == 'true' # Disabled by default to reduce file clutter
        self.enable_entity_extraction = os.getenv('ENABLE_ENTITY_EXTRACTION', 'true').lower() == 'true'
        
        if self.enable_db_storage:
            try:
                # Create database named after query
                db_name = f"search_{self.keyword.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                db_path = os.path.join(default_output_dir, db_name)
                self.db_storage = ResultStorage(db_path)
                logger.info(f"SQLite database initialized: {db_path}")
                
                # Initialize entity storage if entity extraction is enabled
                if self.enable_entity_extraction:
                    try:
                        # Use the same path but with entity_ prefix for graph storage
                        entity_db_name = f"entity_{self.keyword.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                        entity_db_path = os.path.join(default_output_dir, entity_db_name)
                        self.entity_storage = EntityGraphStorage(entity_db_path)
                        logger.info(f"Entity graph storage initialized: {entity_db_path}")
                        print("🧠 Entity extraction ENABLED (set ENABLE_ENTITY_EXTRACTION=false to disable)")
                    except Exception as e:
                        logger.error(f"Failed to initialize entity storage: {e}")
                        self.entity_storage = None
                        print("⚠️  Entity extraction DISABLED due to initialization error")
                else:
                    print("🚫 Entity extraction DISABLED (set ENABLE_ENTITY_EXTRACTION=true to enable)")
                
                # ALWAYS initialize storage_bridge when db_storage is enabled
                # This ensures real-time storage works regardless of entity extraction status
                try:
                    # Create WebSocket callback for graph updates
                    async def graph_update_callback(search_id, update_type, data):
                        """Send graph updates via WebSocket if available"""
                        if self.event_emitter:
                            try:
                                await self.event_emitter('graph_update', {
                                    'update_type': update_type,
                                    'search_id': search_id,
                                    **data
                                })
                            except Exception as e:
                                logger.warning(f"Failed to emit graph update: {e}")
                    
                    self.storage_bridge = StorageBridge(
                        result_storage=self.db_storage,
                        entity_storage=self.entity_storage,  # Can be None if entity extraction disabled
                        auto_extract=self.enable_entity_extraction,  # Only extract entities if enabled
                        graph_update_callback=graph_update_callback
                    )
                    logger.info("🗃️  Storage bridge initialized - real-time database storage ENABLED")
                except Exception as e:
                    logger.error(f"Failed to initialize storage bridge: {e}")
                    self.storage_bridge = None
                    print("⚠️  Storage bridge DISABLED due to initialization error")
                    
            except Exception as e:
                logger.error(f"Failed to initialize database: {e}")
                self.db_storage = None
        # Prioritize fastest engines first for better perceived performance
        if engines:
            self.engines = engines
        else:
            # Speed-optimized order: fast engines first, slow engines last
            fast_engines = ['GO', 'BI', 'BR', 'EX', 'DD', 'YA', 'SS']  # Fast APIs - Brave and Exa ARE fast!
            medium_engines = ['GR', 'HF', 'GD', 'AL', 'PW', 'BO', 'W', 'QW']  # Moderate complexity
            slow_engines = ['AR', 'YE', 'NA']  # Heavy processing/delays
            self.engines = fast_engines + medium_engines + slow_engines
        
        # MAXIMUM SPEED: Use ALL available workers!
        default_workers = min(len(self.engines), int(os.getenv('MAX_CONCURRENT_ENGINES', '64')))
        self.max_workers = max_workers or default_workers
        
        # SPEED MODE: Use configured workers or auto-scale based on engines  
        if max_workers is None:
            # MAXIMUM PERFORMANCE: Use as many workers as we have engines!
            cpu_count = psutil.cpu_count()
            # ENHANCED PARALLELIZATION: More workers for better I/O overlap
            # 3 workers per engine allows for network I/O wait overlap
            optimal_workers = min(len(self.engines) * 3, cpu_count * 4, 32)  # Cap at 32 to prevent thread explosion
            self.max_workers = optimal_workers
        else:
            self.max_workers = max_workers  # Respect user configuration
        logger.info(f"Speed-optimized mode: Using {self.max_workers} concurrent workers (CPUs: {psutil.cpu_count()})")
        
        # Initialize global connection pool for HTTP performance
        self.connection_pool = ConnectionPoolManager()
        
        # Initialize ADAPTIVE rate limiter - learns optimal rates in real-time!
        self.rate_limiter = AdaptiveRateLimiter()

        # Initialize ENGINE HEALTH MONITOR - circuit breaker for failing engines
        self.health_monitor = None
        self.enable_health_monitor = os.getenv('ENABLE_HEALTH_MONITOR', 'true').lower() == 'true'
        if self.enable_health_monitor and HEALTH_MONITOR_AVAILABLE:
            try:
                self.health_monitor = EngineHealthMonitor()
                # Register all engines for monitoring
                for engine_code in self.engines:
                    if engine_code in ENGINE_CONFIG:
                        self.health_monitor.register_engine(
                            engine_code,
                            ENGINE_CONFIG[engine_code].get('name', engine_code)
                        )
                logger.info(f"EngineHealthMonitor initialized - {len(self.engines)} engines registered")
            except Exception as e:
                logger.warning(f"Failed to initialize EngineHealthMonitor: {e}")
                self.health_monitor = None

        # Initialize priority result queue for optimal result processing
        self.priority_queue = PriorityResultQueue()
        logger.info("Priority queue initialized for quality-based result processing")
        
        # MEMORY OPTIMIZATION: Use disk-based deduplication
        # TEMPORARY: Using NoOp deduplicator to test streaming
        class NoOpDeduper:
            def add_url(self, url, title, snippet, source, metadata=None): return True, [source]
            def get_all_results(self): return []
            def get_stats(self): return {'unique_urls': 0, 'duplicate_urls': 0}
            def cleanup(self): pass
        
        self.deduplicator = DiskDeduplicator()
        
        # MEMORY OPTIMIZATION: Initialize memory monitor
        max_memory_mb = int(os.getenv('MAX_MEMORY_MB', '0')) or None
        self.memory_monitor = MemoryMonitor(max_memory_mb)
        
        # Initialize the FilterManager (replaces primitive exact phrase filtering)
        self.filter_manager = FilterManager()
        self.enable_exact_phrase_filter = True  # For compatibility with stats display
        self.force_exact_phrase = False  # Force exact phrase matching even without quotes
        logger.info("FilterManager initialized - sophisticated filtering enabled")
        
        # Initialize snippet enricher for post-processing
        # DISABLED by default to prevent automatic Firecrawl API calls
        self.enable_snippet_enrichment = os.getenv('ENABLE_SNIPPET_ENRICHMENT', 'false').lower() == 'true'
        self.enricher = None
        if self.enable_snippet_enrichment and ENRICHMENT_AVAILABLE:
            try:
                # Create post-processing enricher that prioritizes Firecrawl
                self.enricher = SnippetEnricher.create_post_processing_enricher()
                logger.info("Snippet enrichment enabled for post-processing (Firecrawl priority)")
            except Exception as e:
                logger.warning(f"Failed to initialize snippet enricher: {e}")
                self.enricher = None
        
        # Initialize filetype validator for filetype-specific filtering
        self.filetype_validator = None
        self.detected_filetype = None
        self.filetype_extensions = []
        try:
            from brute.infrastructure.filetype_url_validator import FiletypeURLValidator
            self.filetype_validator = FiletypeURLValidator()
            # Detect if this is a filetype search
            self._detect_filetype_search()
            if self.detected_filetype:
                logger.info(f"Filetype search detected: {self.detected_filetype} - Extensions: {self.filetype_extensions}")
        except ImportError:
            logger.debug("FiletypeURLValidator not available")
        
        self.json_writer = JSONStreamWriter(output_file)
        self.result_queue = queue.Queue(maxsize=100)  # Limit queue size
        self.filtered_out_queue = queue.Queue(maxsize=100) # New queue for filtered results
        self._stop_processing = False
        
        # Thread safety for statistics
        self.stats_lock = threading.Lock()
        
        # Statistics
        self.stats = {
            'total_results': 0,
            'unique_urls': 0,
            'filtered_results': 0,  # Count of filtered-out results
            'results_per_engine': {code: 0 for code in self.engines},
            'raw_results_per_engine': {code: 0 for code in self.engines},  # Raw counts before deduplication
            'filtered_per_engine': {code: 0 for code in self.engines},  # Filtered-out per engine
            'errors_per_engine': {code: 0 for code in self.engines},
            'engine_status': {code: 'pending' for code in self.engines},
            'start_time': datetime.now().isoformat(),
            'queries_expanded': [],
            'duplicate_rate': 0,
            'results_per_second': 0,
            'api_calls_made': 0,
            'filter_data': {
                'filetypes': defaultdict(int),
                'languages': defaultdict(int),
                'countries': defaultdict(int),
                'dates': defaultdict(int),
            }
        }

        # All results storage (JSON only, not Elasticsearch)
        self.all_results_list = []  # All passed results for JSON export
        self.filtered_results_list = []  # Filtered-out results for JSON export
        
        # Query expansion support - temporarily disabled
        self.enable_expansion = False  # Config.ENABLE_QUERY_EXPANSION
        # if self.enable_expansion:
        #     self.query_expander = QueryExpander(enable_aggressive=True)

        # CascadeExecutor mode - optional 3-wave architecture for cleaner execution
        self.use_cascade_executor = os.getenv('USE_CASCADE_EXECUTOR', 'false').lower() == 'true'
        self.cascade_executor = None
        if self.use_cascade_executor and CASCADE_EXECUTOR_AVAILABLE:
            try:
                # Build engine registry mapping engine codes to runner factories
                engine_registry = self._build_engine_registry()
                self.cascade_executor = CascadeExecutor(
                    engine_registry=engine_registry,
                    max_results_per_engine=100,
                    deduplicate=True,
                    progress_callback=self._cascade_progress_callback
                )
                logger.info("CascadeExecutor initialized - 3-wave architecture enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize CascadeExecutor: {e}")
                self.cascade_executor = None

        # ENGINE ANALYTICS: Per-engine performance tracking for self-improvement
        self.analytics_collector = None
        self.enable_analytics = os.getenv('ENABLE_ANALYTICS', 'true').lower() == 'true'
        if self.enable_analytics and ANALYTICS_AVAILABLE:
            try:
                self.analytics_collector = EngineAnalyticsCollector(
                    query=keyword,
                    search_id=self.checkpoint_id
                )
                logger.info("EngineAnalyticsCollector initialized - per-engine tracking enabled")
                print("📊 Engine analytics ENABLED - tracking per-engine performance")
            except Exception as e:
                logger.warning(f"Failed to initialize EngineAnalyticsCollector: {e}")
                self.analytics_collector = None
    
    async def emit_event(self, event_type: str, data: dict):
        """Emit event to WebSocket if connected"""
        if self.event_emitter:
            try:
                await self.event_emitter(event_type, data)
            except Exception as e:
                logger.warning(f"Failed to emit event {event_type}: {e}")
    
    def emit_event_sync(self, event_type: str, data: dict):
        """Emit event synchronously"""
        if self.event_emitter:
            try:
                # Just call it directly since it's now sync
                self.event_emitter(event_type, data)
            except Exception as e:
                logger.warning(f"Failed to emit sync event {event_type}: {e}")

    def _build_engine_registry(self) -> Dict[str, Any]:
        """
        Build engine registry for CascadeExecutor.
        Maps engine codes to runner classes that accept (phrase, max_results).
        """
        registry = {}

        # Create wrapper classes that adapt existing runners to CascadeExecutor interface
        for code in self.engines:
            if code not in ENGINE_CONFIG:
                continue
            config = ENGINE_CONFIG[code]

            # Create a factory closure that captures the code
            def make_runner_class(engine_code):
                class EngineRunner:
                    def __init__(self, phrase: str, max_results: int = 100):
                        self.phrase = phrase
                        self.max_results = max_results
                        self.engine_name = ENGINE_CONFIG[engine_code]['name']
                        self.engine_code = engine_code

                    def run(self):
                        """Run engine and yield results"""
                        try:
                            # Get factory function
                            factory_name = ENGINE_CONFIG[engine_code].get('factory')
                            if not factory_name or factory_name not in globals():
                                return

                            factory = globals()[factory_name]
                            client = factory()

                            # Run search with max results
                            results = client.search(self.phrase, max_results=self.max_results)

                            for result in results[:self.max_results]:
                                yield result
                        except Exception as e:
                            logger.warning(f"Engine {engine_code} failed: {e}")
                            return

                return EngineRunner

            registry[code] = make_runner_class(code)

        return registry

    def _cascade_progress_callback(self, wave, completed: int, total: int, results: List):
        """Progress callback for CascadeExecutor"""
        wave_name = wave.name if hasattr(wave, 'name') else str(wave)
        print(f"🌊 {wave_name}: {completed}/{total} engines complete, {len(results)} new results")

        # Emit WebSocket event for progress
        self.emit_event_sync('cascade_progress', {
            'wave': wave_name,
            'completed_engines': completed,
            'total_engines': total,
            'new_results': len(results)
        })

    def emit_engine_status(self, engine_code: str, status: str, results_count: int = 0):
        """Helper to emit engine status update synchronously"""
        with self.stats_lock:
            raw_count = self.stats.get('raw_results_per_engine', {}).get(engine_code, 0)
        
        self.emit_event_sync('engine_status', {
            'engine': engine_code,
            'status': status,
            'results': results_count,
            'raw_results': raw_count  # Include raw count before deduplication
        })
    
    def get_category_stats(self):
        """Get category statistics for results"""
        if not hasattr(self, 'categorized_results'):
            return {}
        
        stats = {}
        for category in self.categorized_results.values():
            # categorized_results stores categories as strings, not dicts
            if isinstance(category, str):
                stats[category] = stats.get(category, 0) + 1
            else:
                # Fallback for dict format if it exists
                cat_name = category.get('category', 'miscellaneous') if isinstance(category, dict) else 'miscellaneous'
                stats[cat_name] = stats.get(cat_name, 0) + 1
        
        return stats

    
    def _cached_categorize(self, url: str, title: str, snippet: str):
        """
        Cached domain categorization to improve performance.
        Caches results by domain to avoid repeated categorization of same domains.
        """
        try:
            domain = extract_domain(url)
            
            # Check cache first
            if domain in self.domain_cache:
                self.cache_hits += 1
                cached_result = self.domain_cache[domain].copy()
                return cached_result
            
            # Cache miss - perform categorization
            self.cache_misses += 1
            category_result = categorize_url_basic(url, title, snippet)
            
            # Cache domain-based results (not URL-specific ones)
            if (category_result['category'] != 'needs_gpt_classification' and 
                len(self.domain_cache) < 5000):  # Limit cache size
                self.domain_cache[domain] = category_result.copy()
            
            # Print cache statistics periodically
            total_calls = self.cache_hits + self.cache_misses
            if total_calls % 100 == 0:  # Every 100 calls
                hit_rate = (self.cache_hits / total_calls) * 100
                print(f"📊 Categorization cache: {len(self.domain_cache)} domains cached, "
                      f"{hit_rate:.1f}% hit rate ({self.cache_hits}/{total_calls})")
            
            return category_result
            
        except Exception as e:
            logger.warning(f"Cached categorization failed for {url}: {e}")
            # Fallback to direct categorization
            return categorize_url_basic(url, title, snippet)
    
    def _load_engine(self, engine_code: str):
        """Dynamically load a search engine"""
        config = ENGINE_CONFIG.get(engine_code)
        if not config:
            logger.error(f"Unknown engine code: {engine_code}")
            return None, None
        try:
            # Import the runner module
            module = importlib.import_module(config['module'])
            runner_class = getattr(module, config['class'])
            
            # Get API key for this engine
            api_key = Config.get_api_key(engine_code)
            
            # For engines that need a base engine instance
            if 'engine_class' in config and config['engine_class']:
                # The engine class is now embedded in the runner module itself
                engine_class = getattr(module, config['engine_class'])
                
                # Initialize engine with API key if available
                try:
                    if api_key:
                        engine_instance = engine_class(api_key=api_key)
                    else:
                        engine_instance = engine_class()
                    return runner_class, engine_instance
                except Exception as e:
                    logger.warning(f"Failed to initialize {config['engine_class']}, trying without instance: {e}")
                    return runner_class, None
            else:
                return runner_class, None
                
        except Exception as e:
            logger.error(f"Failed to load engine {engine_code}: {e}")
            return None, None
    
    def _run_engine(self, engine_code: str) -> Iterator[Dict[str, Any]]:
        """Run a single search engine and yield results with L1/L2/L3 expansion"""
        engine_name = ENGINE_CONFIG.get(engine_code, {}).get('name', engine_code)
        logger.info(f"Starting search with {engine_name} [{engine_code}]")
        
        # Generate query variations (L1/L2/L3)
        # Handle force exact phrase at the engine level too
        base_query = self.keyword
        if self.force_exact_phrase and not (base_query.startswith('"') and base_query.endswith('"')):
            base_query = f'"{base_query}"'
            
        queries_to_run = [base_query]
        
        # Filetype Expansion
        import re
        ft_match = re.search(r'filetype:(\w+)', self.keyword)
        if ft_match:
            ext = ft_match.group(1)
            base = self.keyword.replace(f'filetype:{ext}', '').strip()
            if base:
                # L2: inurl:.ext (Tricks)
                queries_to_run.append(f'{base} inurl:.{ext}')
                logger.info(f"L2 Expansion [{engine_code}]: Added inurl:.{ext}")
        
        # Site Expansion
        site_match = re.search(r'site:([\w\.-]+)', self.keyword)
        if site_match:
            domain = site_match.group(1)
            # Check if it looks like a domain (has dot, no wildcard)
            if '.' in domain and '*' not in domain and not domain.startswith('.'):
                 base = self.keyword.replace(f'site:{domain}', '').strip()
                 if base:
                     # L2: inurl:domain (Tricks)
                     queries_to_run.append(f'{base} inurl:{domain}')
                     logger.info(f"L2 Expansion [{engine_code}]: Added inurl:{domain}")

        # Remove duplicates
        queries_to_run = list(dict.fromkeys(queries_to_run))
        
        # Engine execution starts
        with self.stats_lock:
            self.stats['engine_status'][engine_code] = 'running'
        self.emit_engine_status(engine_code, 'running')
        
        # STREAMING: Show engine starting
        print(f"\n🔍 [{engine_code}] {engine_name} starting ({len(queries_to_run)} variations)...")
        
        try:
            # Apply rate limiting before starting
            self.rate_limiter.wait_if_needed(engine_code)
            
            all_results_count = 0
            
            # Iterate through all query variations
            for query_idx, current_query in enumerate(queries_to_run):
                if query_idx > 0:
                    # Small delay between variations
                    time.sleep(random.uniform(0.5, 1.5))
                
                # Try unified wrapper engine first
                results = None
                used_wrapper = False
                try:
                    wrapper_spec = WRAPPER_ENGINE_MAP.get(engine_code)
                    if wrapper_spec:
                        mod_name, cls_name = wrapper_spec
                        mod = importlib.import_module(mod_name)
                        cls = getattr(mod, cls_name)
                        wrapper_engine = cls()
                        max_res = WRAPPER_ENGINE_MAX.get(engine_code, 100)
                        # Pass the current variation
                        results = wrapper_engine.search(current_query.strip('"'), max_results=max_res) or []
                        used_wrapper = True
                except Exception as e:
                    logger.debug(f"Wrapper engine failed for {engine_code}: {e}")

                if not used_wrapper:
                    runner_class, engine_instance = self._load_engine(engine_code)
                    if not runner_class:
                        continue # Skip to next if load fails
                    
                    # Initialize runner with unified approach
                    config = ENGINE_CONFIG.get(engine_code, {})
                    
                    # Build kwargs from config
                    kwargs = {}
                    if 'init_kwargs' in config and callable(config['init_kwargs']):
                        kwargs = config['init_kwargs']()
                    
                    # Add phrase parameter - USE CURRENT VARIATION
                    kwargs.setdefault('phrase', current_query.strip('"'))
                    
                    # Add API key if available and not already in kwargs
                    api_key = Config.get_api_key(engine_code)
                    if api_key and 'api_key' not in kwargs:
                        if engine_code not in ['GO', 'BI', 'BR', 'YA', 'AR', 'YE', 'EX']:
                            kwargs['api_key'] = api_key
                    
                    # Special handling for SocialSearcher - it doesn't accept 'phrase' parameter
                    if engine_code == 'SS' and 'phrase' in kwargs:
                        del kwargs['phrase']
                    
                    # Create runner instance
                    
                    # Special handling for Google - it expects positional arguments
                    if engine_code == 'GO':
                        # ExactPhraseRecallRunner expects (phrase, google, site_groups=None, ...)
                        phrase = kwargs.pop('phrase', current_query.strip('"'))
                        google_client = kwargs.pop('google')
                        runner = runner_class(phrase, google_client, **kwargs)
                    else:
                        runner = runner_class(**kwargs)
                    
                    # Determine how to execute the search
                    if engine_code == 'DD':
                        clean_phrase = current_query.strip('"')
                        results = runner.search(clean_phrase, max_results=500)
                    elif engine_code == 'BO':
                        results = runner.run_sync()
                    elif hasattr(runner, 'run'):
                        # Standard run() method
                        run_method = getattr(runner, 'run')
                        if asyncio.iscoroutinefunction(run_method):
                            try:
                                loop = asyncio.get_running_loop()
                                import concurrent.futures
                                with concurrent.futures.ThreadPoolExecutor() as executor:
                                    future = executor.submit(asyncio.run, runner.run())
                                    results = future.result()
                            except RuntimeError:
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                try:
                                    results = loop.run_until_complete(runner.run())
                                finally:
                                    loop.close()
                        else:
                            raw_results = runner.run()
                            if engine_code == 'GO' and hasattr(raw_results, '__iter__') and not isinstance(raw_results, (list, tuple)):
                                results = []
                                for result in raw_results:
                                    results.append(result)
                            elif hasattr(raw_results, '__iter__') and not isinstance(raw_results, (list, tuple)):
                                results = list(raw_results)
                            else:
                                results = raw_results
                    elif hasattr(runner, 'search'):
                        # Fallback to search() method - USE CURRENT VARIATION
                        # Don't strip quotes if we are forcing exact phrase, unless the engine explicitly can't handle them
                        # Archive.org and others need the quotes for exact search
                        if self.force_exact_phrase or (current_query.startswith('"') and current_query.endswith('"')):
                            results = runner.search(current_query)
                        else:
                            results = runner.search(current_query.strip('"'))
                    else:
                        logger.error(f"Runner for {engine_code} has no run() or search() method")
                        results = []
                
                # Ensure results is a list
                if results is None:
                    results = []
                elif not isinstance(results, list):
                    results = list(results) if hasattr(results, '__iter__') else []
                
                # Initialize result processing counter for this variation
                processed_count = 0
                
                # Process results through the FilterManager
                # TEMPORARILY DISABLED FOR DEBUGGING
                use_filter_manager = True  # Enable FilterManager for proper filtering
                
                if use_filter_manager:
                    try:
                        # Determine the actual search type for proper filtering
                        if self.detected_filetype:
                            actual_search_type = 'filetype'
                        elif (current_query.startswith('"') and current_query.endswith('"')) or self.force_exact_phrase:
                            actual_search_type = 'exact_phrase'
                        else:
                            actual_search_type = 'brute'
                        
                        # Update context with current query
                        context = {
                            'query': current_query, # Use current variation
                            'search_type': actual_search_type,
                            'is_exact_phrase': (current_query.startswith('"') and current_query.endswith('"')) or self.force_exact_phrase,
                            'exact_phrase': current_query.strip('"') if current_query.startswith('"') and current_query.endswith('"') else current_query,
                            'filetype': self.detected_filetype,
                            'filetype_extensions': self.filetype_extensions,
                            'enable_exact_phrase_filter': self.enable_exact_phrase_filter,
                            'force_exact_phrase': self.force_exact_phrase
                        }
                        
                        # Run the async process_results method
                        try:
                            loop = asyncio.get_running_loop()
                            import concurrent.futures
                            with concurrent.futures.ThreadPoolExecutor() as executor:
                                future = executor.submit(asyncio.run, 
                                    self.filter_manager.process_results(results, search_type=actual_search_type, query_context=context))
                                processed_data = future.result()
                        except RuntimeError:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            try:
                                processed_data = loop.run_until_complete(
                                    self.filter_manager.process_results(results, search_type=actual_search_type, query_context=context))
                            finally:
                                loop.close()
                        
                        passed_results = processed_data.get('primary', []) + processed_data.get('secondary', [])
                        filtered_results = processed_data.get('filtered', [])
                        
                        all_processed_urls = {r.get('url') or r.get('link') for r in passed_results + filtered_results if r.get('url') or r.get('link')}
                        unprocessed_results = [r for r in results if (r.get('url') or r.get('link')) and (r.get('url') or r.get('link')) not in all_processed_urls]
                        
                        if unprocessed_results:
                            for ur in unprocessed_results:
                                ur['filter_reason'] = 'Not processed by FilterManager'
                            filtered_results.extend(unprocessed_results)

                    except Exception as filter_exc:
                        logger.error(f"FilterManager failed for {engine_code}: {filter_exc}")
                        passed_results = results
                        filtered_results = []
                else:
                    passed_results = results
                    filtered_results = []
                
                # Track raw results count (before deduplication)
                with self.stats_lock:
                    self.stats['raw_results_per_engine'][engine_code] += len(passed_results)
                
                # Handle passed results
                for result in passed_results:
                    if url := result.get('url'):
                        processed_count += 1
                        all_results_count += 1
                        
                        self.stats['total_results'] += 1
                        self.stats['results_per_engine'][engine_code] += 1
                        
                        is_safe, current_mem = self.memory_monitor.check_memory()
                        if not is_safe:
                            logger.warning(f"Memory high ({current_mem:.1f}MB), pausing result processing...")
                            self.memory_monitor.wait_for_memory()
                        
                        # Extract metadata from result
                        metadata = {
                            'author': result.get('author'),
                            'published_date': result.get('published_date'),
                            'score': result.get('score'),
                            'image': result.get('image'),
                            'category': result.get('category'),
                            'attributes': result.get('attributes', {})
                        }
                        
                        is_new, sources = self.deduplicator.add_url(url, result.get('title', ''), result.get('snippet', ''), engine_code, metadata)

                        # Build query_variant tag: ENGINE_CODE:exact_query_sent
                        # For engines that use API settings instead of query syntax, append [settings]
                        # e.g., EX:"query" [type=keyword,use_autoprompt=false]
                        engine_config = ENGINE_CONFIG.get(engine_code, {})
                        api_settings = engine_config.get('api_settings', '')
                        if api_settings:
                            query_variant = f"{engine_code}:{current_query} [{api_settings}]"
                        else:
                            query_variant = f"{engine_code}:{current_query}"

                        # REAL-TIME STORAGE
                        if self.storage_bridge and self.enable_db_storage:
                            storage_result = {
                                'url': url,
                                'title': result.get('title', ''),
                                'snippet': result.get('snippet', ''),
                                'sources': sources,
                                'engine': engine_code,
                                'query_variant': query_variant,
                                'rank': result.get('rank', 0),
                                'score': result.get('score', 0.0),
                                'timestamp': datetime.now().isoformat(),
                                'attributes': result.get('attributes', {})
                            }
                            
                            for key in ['author', 'published_date', 'image', 'category']:
                                if key in result and result[key] is not None:
                                    storage_result[key] = result[key]
                            
                            if self.storage_bridge and self.enable_db_storage:
                                try:
                                    self.storage_bridge.result_storage.store_search_results(
                                        query=self.keyword,
                                        results=[storage_result],
                                        project_id=self.checkpoint_id
                                    )
                                except Exception as e:
                                    logger.error(f"⚠️ DB STORAGE ERROR (Non-fatal): {e}")
                        
                        if is_new:
                            self.stats['unique_urls'] += 1
                            action = 'new'
                        else:
                            action = 'duplicate'
                        
                        attributes = result.get('attributes', {})

                        result_data = {
                            'url': url,
                            'title': result.get('title', ''),
                            'snippet': result.get('snippet', ''),
                            'sources': sources,
                            'engine': engine_code,
                            'query_variant': query_variant,
                            'timestamp': datetime.now().isoformat(),
                            'attributes': attributes,
                            'is_duplicate': action == 'duplicate'
                        }

                        # Store all passed results to JSON list
                        self.all_results_list.append(result_data)

                        if engine_code == 'BR':
                            logger.info(f"BR result - URL: {url[:50]}... Title: {result.get('title', '')[:50]}... Snippet: '{result.get('snippet', '')[:100]}...'")
                        
                        try:
                            self.priority_queue.put((result_data, action), engine_code)
                        except Exception as pq_err:
                            logger.warning(f"Priority queue put failed ({pq_err}); falling back to FIFO queue")
                            self.result_queue.put((result_data, action), timeout=30)
                        
                        yield result

                # Handle filtered results - store to JSON (NOT Elasticsearch)
                for filtered_result in filtered_results:
                    filter_reason = filtered_result.get('filter_reason', 'unknown')
                    url = filtered_result.get('url') or filtered_result.get('link', '')

                    # Build query_variant for filtered result
                    engine_config = ENGINE_CONFIG.get(engine_code, {})
                    api_settings = engine_config.get('api_settings', '')
                    if api_settings:
                        query_variant = f"{engine_code}:{current_query} [{api_settings}]"
                    else:
                        query_variant = f"{engine_code}:{current_query}"

                    filtered_data = {
                        'url': url,
                        'title': filtered_result.get('title', ''),
                        'snippet': filtered_result.get('snippet', ''),
                        'engine': engine_code,
                        'query_variant': query_variant,
                        'filter_reason': filter_reason,
                        'timestamp': datetime.now().isoformat(),
                        'attributes': filtered_result.get('attributes', {})
                    }
                    self.filtered_results_list.append(filtered_data)

                    # Update stats
                    with self.stats_lock:
                        self.stats['filtered_results'] += 1
                        self.stats['filtered_per_engine'][engine_code] = self.stats['filtered_per_engine'].get(engine_code, 0) + 1

            # End of variations loop
            logger.info(f"DEBUG: {engine_code} completed - Processed {all_results_count} results from all variations")
            with self.stats_lock:
                self.stats['engine_status'][engine_code] = 'completed'
                results_count = self.stats['results_per_engine'][engine_code]
            self.emit_engine_status(engine_code, 'completed', results_count)
            
            # Report success for rate limiting
            self.rate_limiter.report_success(engine_code)
            
            # STREAMING: Show engine completion
            count = self.stats['results_per_engine'][engine_code]
            print(f"✅ [{engine_code}] {engine_name} completed: {count} results")
            self.checkpoint_manager.mark_engine_completed(engine_code)
            
        except Exception as e:
            engine_name = ENGINE_CONFIG.get(engine_code, {}).get('name', engine_code)
            logger.error(f"❌ {engine_name} [{engine_code}] failed: {e}")
            with self.stats_lock:
                self.stats['errors_per_engine'][engine_code] += 1
                self.stats['engine_status'][engine_code] = 'error'
                results_count = self.stats['results_per_engine'][engine_code]
            self.emit_engine_status(engine_code, 'failed', results_count)
            
            # Report error for rate limiting (exponential backoff)
            self.rate_limiter.report_error(engine_code)
            
            # STREAMING: Show engine failure
            print(f"❌ [{engine_code}] {engine_name} failed: {str(e)[:100]}")
            
            # Save checkpoint for failed engine
            self.checkpoint_manager.mark_engine_failed(engine_code, str(e)[:100])
    
    def _result_writer_thread(self):
        """MEMORY OPTIMIZED: Process results in batches with memory monitoring"""
        batch = []
        batch_size = 50  # Process 50 results at a time
        last_flush = time.time()
        
        # Prefer draining priority queue so high-priority engines surface first
        while not self._stop_processing or not self.result_queue.empty() or not self.priority_queue.empty():
            try:
                # Try priority queue first (result, action)
                result_tuple, engine_code = self.priority_queue.get(timeout=0.05)
                if result_tuple:
                    result, action = result_tuple
                else:
                    # Fallback to FIFO queue if no priority item
                    result, action = self.result_queue.get(timeout=0.1)
                
                if self.return_results and result:
                    self.final_results.append(result)
                    continue

                batch.append((result, action))
                
                # Flush batch when it reaches size limit or every 5 seconds
                if len(batch) >= batch_size or (time.time() - last_flush) > 5:
                    self._flush_batch(batch)
                    batch = []
                    last_flush = time.time()
                
                # Immediate categorization for new results
                if action == 'new':
                    try:
                        category_result = self._cached_categorize(
                            result['url'], 
                            result['title'], 
                            result.get('aggregated_snippet', '')
                        )
                        category = category_result['category']
                        
                        # Only queue for GPT if basic categorization couldn't determine category
                        if category == 'needs_gpt_classification':
                            with self._categorizer_lock:
                                self.categorization_queue.append({
                                    'url': result['url'],
                                    'title': result['title'],
                                    'description': result.get('aggregated_snippet', ''),
                                    'query': self.keyword
                                })
                        else:
                            # Store the categorized result immediately
                            self.categorized_results[result['url']] = category
                    except Exception as e:
                        logger.warning(f"Immediate categorization failed for {result['url']}: {e}")
                        # Fallback to GPT queue
                        with self._categorizer_lock:
                            self.categorization_queue.append({
                                'url': result['url'],
                                'title': result['title'],
                                'description': result.get('aggregated_snippet', ''),
                                'query': self.keyword
                            })
                    
                    # Add to scraping queue for first 200 results - ONLY if enabled
                    # if self.enable_scraping and len(self.scraped_urls) + len(self.scraping_queue) < self.max_scrape_results:
                    #     with self._scraper_lock:
                    #         self.scraping_queue.append({
                    #             'url': result['url'],
                    #             'title': result['title']
                    #         })
                
                # STREAMING DISPLAY: Show results immediately as they arrive
                # Format: [ENGINE(S)] Title - URL
                sources = '+'.join(result['sources'])
                title = result['title'][:80] + '...' if len(result['title']) > 80 else result['title']
                url = result['url']
                
                # Check if already categorized
                category = self.categorized_results.get(url, '')
                category_prefix = f"[{category.upper()}] " if category else ""
                
                if action == 'new':
                    # New unique result
                    print(f"{category_prefix}[{sources}] ✓ {title}")
                    print(f"          {url}")
                    # Show snippet preview (first 120 chars)
                    snippet = result.get('aggregated_snippet', result.get('snippets', {}).get(result['sources'][0], ''))
                    if snippet:
                        preview = snippet[:120] + '...' if len(snippet) > 120 else snippet
                        print(f"          \"{preview}\"")
                else:
                    # Duplicate found by another engine
                    print(f"{category_prefix}[{sources}] ↗ Found again by {result['sources'][-1]}")
                
                # Check if we should run categorization
                if len(self.categorization_queue) >= self.categorization_batch_size:
                    # Run categorization in a separate thread to avoid blocking
                    threading.Thread(target=self._run_categorization_sync, daemon=True).start()
                
                # Check if we should run scraping - ONLY if enabled
                # if self.enable_scraping and len(self.scraping_queue) >= self.scraping_batch_size:
                #     # Run scraping in a separate thread
                #     threading.Thread(target=self._run_scraping_sync, daemon=True).start()
                
                # Show running totals and memory status every 25 results
                if self.stats['total_results'] % 25 == 0:
                    unique = self.stats['unique_urls']
                    total = self.stats['total_results']
                    is_safe, current_mem = self.memory_monitor.check_memory()
                    mem_pct = (current_mem / self.memory_monitor.max_memory_mb) * 100
                    mem_status = "🟢" if mem_pct < 70 else "🟡" if mem_pct < 85 else "🔴"
                    print(f"\n📊 Progress: {unique} unique URLs from {total} total results")
                    print(f"💾 Memory: {mem_status} {current_mem:.1f}MB ({mem_pct:.1f}% of {self.memory_monitor.max_memory_mb}MB limit)\n")
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error writing result: {e}")
        
        # Final flush of any remaining items
        if batch:
            self._flush_batch(batch)

    def _filtered_writer_thread(self):
        """Processes filtered-out results and sends them to the frontend."""
        while not self._stop_processing or not self.filtered_out_queue.empty():
            try:
                result = self.filtered_out_queue.get(timeout=0.1)
                self.emit_event_sync('filtered', {'result': result})
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error sending filtered result: {e}")

    def _filtered_writer_thread(self):
        """Processes filtered-out results and sends them to the frontend."""
        while not self._stop_processing or not self.filtered_out_queue.empty():
            try:
                result = self.filtered_out_queue.get(timeout=0.1)
                self.emit_event_sync('filtered', {'result': result})
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error sending filtered result: {e}")
    
    def _flush_batch(self, batch: List[tuple]):
        """Process and write a batch of results"""
        if not batch:
            return
        
        logger.info(f"Flushing batch of {len(batch)} results")

        # If returning results, just append to the list
        if self.return_results:
            for result, _ in batch:
                self.final_results.append(result)
            return

        # Original file writing logic
        for result, action in batch:
            try:
                # Write to JSON file
                self.json_writer.write_result(result, action)
                
                # Immediate categorization for new results
                if action == 'new':
                    try:
                        category_result = self._cached_categorize(
                            result['url'], 
                            result['title'], 
                            result.get('snippet', '')
                        )
                        category = category_result['category']
                        
                        # Only queue for GPT if basic categorization couldn't determine category
                        if category == 'needs_gpt_classification':
                            with self._categorizer_lock:
                                self.categorization_queue.append({
                                    'url': result['url'],
                                    'title': result['title'],
                                    'description': result.get('snippet', ''),
                                    'query': self.keyword
                                })
                        else:
                            # Store the categorized result immediately
                            self.categorized_results[result['url']] = category
                    except Exception as e:
                        logger.warning(f"Immediate categorization failed for {result['url']}: {e}")
                        # Fallback to GPT queue
                        with self._categorizer_lock:
                            self.categorization_queue.append({
                                'url': result['url'],
                                'title': result['title'],
                                'description': result.get('snippet', ''),
                                'query': self.keyword
                            })
                    
                    # Add to scraping queue for first 200 results - ONLY if enabled
                    # if self.enable_scraping and len(self.scraped_urls) + len(self.scraping_queue) < self.max_scrape_results:
                    #     with self._scraper_lock:
                    #         self.scraping_queue.append({
                    #             'url': result['url'],
                    #             'title': result['title']
                    #         })
                
                # STREAMING DISPLAY: Show results immediately
                sources = '+'.join(result['sources'])
                title = result['title'][:80] + '...' if len(result['title']) > 80 else result['title']
                url = result['url']
                
                # Check if already categorized
                category = self.categorized_results.get(url, '')
                if category:
                    print(f"[{category}] [{sources}] ✓ {title}")
                else:
                    print(f"[{sources}] ✓ {title}")
                print(f"          {url}")
                
                # Show snippet preview if available
                snippet = result.get('snippet', '')
                if snippet:
                    preview = snippet[:120] + '...' if len(snippet) > 120 else snippet
                    print(f"          \"{preview}\"")
                print()  # Blank line for readability
                
                # Update filter data aggregates
                attributes = result.get('attributes', {})
                if filetype := attributes.get('filetype'):
                    self.stats['filter_data']['filetypes'][filetype.lower()] += 1
                if lang := attributes.get('language'):
                    self.stats['filter_data']['languages'][lang] += 1
                if country := attributes.get('country'):
                    self.stats['filter_data']['countries'][country] += 1
                
                # WEBSOCKET STREAMING: Emit result to frontend for BOTH new and duplicate results
                # Always emit results so frontend can see ALL engines that found it
                
                # Immediate categorization for each result
                try:
                    category_result = self._cached_categorize(
                        result['url'], 
                        result['title'], 
                        result.get('snippet', '')
                    )
                    category = category_result['category']
                    attributes = category_result.get('attributes', {})
                    
                    # Only queue for GPT if basic categorization couldn't determine category
                    if category == 'needs_gpt_classification':
                        # Add to categorization queue for GPT processing
                        if action == 'new' or url not in self.categorized_results:
                            with self._categorizer_lock:
                                self.categorization_queue.append({
                                    'url': result['url'],
                                    'title': result['title'],
                                    'description': result.get('snippet', ''),
                                    'query': self.keyword
                                })
                    else:
                        # Store the categorized result immediately
                        self.categorized_results[url] = category
                        print(f"📂 Immediate category for {url[:60]}: {category}")
                
                except Exception as e:
                    logger.warning(f"Immediate categorization failed for {url}: {e}")
                    category = 'miscellaneous'
                    attributes = {}

                self.emit_event_sync('result', {
                    'result': {
                        'url': result['url'],
                        'title': result['title'],
                        'snippet': result.get('snippet', ''),
                        'description': result.get('snippet', ''),  # Keep for compatibility
                        'engine': result['sources'][0] if result.get('sources') else 'unknown', # Send first engine for display
                        'sources': result.get('sources', []),  # Send all sources
                        'query': self.keyword, # Add the query text
                        'category': category,  # Use immediate categorization result
                        'attributes': {**result.get('attributes', {}), **attributes},  # Merge existing and new attributes
                        'is_duplicate': action == 'duplicate'  # Let frontend know if this is an update
                    },
                    'total': self.stats['unique_urls']
                })
                
            except Exception as e:
                logger.error(f"Error processing result in batch: {e}")
        
        # Check if we should run categorization
        if len(self.categorization_queue) >= self.categorization_batch_size:
            threading.Thread(target=self._run_categorization_sync, daemon=True).start()
        
        # Check if we should run scraping - ONLY if enabled
        # DISABLED: Auto-scraping causing unauthorized Firecrawl API calls
        # if self.enable_scraping and len(self.scraping_queue) >= self.scraping_batch_size:
        #     threading.Thread(target=self._run_scraping_sync, daemon=True).start()
        
        # Clear some memory
        gc.collect()
    
    def remove_from_sql_database(self, url, search_id):
        """
        Remove a specific result from the SQL database.
        
        Args:
            url: URL to remove
            search_id: Search ID for the database
        """
        if not self.storage_bridge:
            return False
            
        try:
            # Use storage bridge to remove result
            if hasattr(self.storage_bridge, 'remove_result'):
                return self.storage_bridge.remove_result(url, search_id)
            else:
                # Fallback: direct SQL removal
                if self.db_storage:
                    return self.db_storage.remove_result(url, search_id)
            return False
        except Exception as e:
            logger.error(f"Failed to remove {url} from SQL: {e}")
            return False
    
    async def verify_filtered_results(self, filtered_results, original_query):
        """
        Verify filtered results using site: searches and HuggingFace handling.
        
        Args:
            filtered_results: List of filtered result dictionaries
            original_query: Original search query
            
        Returns:
            List of results verified for removal from SQL
        """
        verified_to_remove = []
        
        logger.info(f"🔍 VERIFICATION: Starting verification of {len(filtered_results)} filtered results")
        
        for i, result in enumerate(filtered_results):
            url = result.get('url', '')
            if not url:
                continue
                
            # HuggingFace handling: Simple removal without site: search
            if is_huggingface_result(result):
                verified_to_remove.append(result)
                logger.info(f"🤖 HF REMOVAL: {url[:50]}... (HuggingFace filtered result)")
                continue
            
            # For all other domains: Verify with site: search
            try:
                domain = extract_domain(url)
                if not domain:
                    verified_to_remove.append(result)  # Remove if can't extract domain
                    continue
                
                logger.info(f"🔍 VERIFICATION ({i+1}/{len(filtered_results)}): Checking {domain}")
                
                # Verify if domain actually contains the exact phrase
                has_exact_phrase = await verify_site_search(domain, original_query)
                
                if not has_exact_phrase:
                    # No exact phrase found - safe to remove
                    verified_to_remove.append(result)
                    logger.info(f"❌ VERIFIED REMOVAL: {url[:50]}... (no exact phrase found)")
                else:
                    # Exact phrase found - this was a false positive, keep in SQL
                    logger.info(f"✅ VERIFIED KEEP: {url[:50]}... (exact phrase confirmed)")
                    
            except Exception as e:
                logger.warning(f"⚠️ VERIFICATION ERROR for {url[:50]}...: {e}")
                # On error, be conservative and keep the result
                continue
        
        logger.info(f"🎯 VERIFICATION COMPLETE: {len(verified_to_remove)} results verified for removal")
        return verified_to_remove
    
    async def run_post_search_verification(self):
        """
        Run post-search verification to clean up SQL database.
        This should be called after the main search completes.
        """
        if not self.storage_bridge or not self.enable_db_storage:
            logger.info("⚠️ POST-VERIFICATION: Skipped (storage not enabled)")
            return
        
        logger.info("🧹 POST-VERIFICATION: Starting SQL cleanup process")
        
        try:
            # Get filtered results from the deduplicator or storage
            # For now, we'll need to track filtered results during the search
            # This is a placeholder - we'll need to modify the search process to collect these
            
            # TODO: Implement filtered results collection during search
            # For now, this is a framework for the verification system
            
            logger.info("🧹 POST-VERIFICATION: Framework ready (filtered results collection needed)")
            
        except Exception as e:
            logger.error(f"❌ POST-VERIFICATION FAILED: {e}")
    
    def _process_engine_result(self, engine_code, result):
        """Process a single result from an engine in round-robin fashion"""
        if not result or not result.get('url'):
            return
        
        url = result.get('url')
        
        # Update stats
        with self.stats_lock:
            self.stats['total_results'] += 1
            self.stats['results_per_engine'][engine_code] = \
                self.stats['results_per_engine'].get(engine_code, 0) + 1
        
        # Check memory every 10 results for efficiency
        if self.stats['total_results'] % 10 == 0:
            is_safe, current_mem = self.memory_monitor.check_memory()
            if not is_safe:
                logger.warning(f"Memory high ({current_mem:.1f}MB), pausing...")
                self.memory_monitor.wait_for_memory()
            else:
                # Apply progressive throttling based on memory usage
                throttle_delay = self.memory_monitor.get_throttle_delay()
                if throttle_delay > 0:
                    time.sleep(throttle_delay)
        
        # Extract metadata
        metadata = {
            'author': result.get('author'),
            'published_date': result.get('published_date'),
            'score': result.get('score'),
            'image': result.get('image'),
            'category': result.get('category'),
            'attributes': result.get('attributes', {})
        }
        
        # Deduplication
        is_new, sources = self.deduplicator.add_url(
            url, 
            result.get('title', ''), 
            result.get('snippet', ''),
            engine_code,
            metadata
        )
        
        if is_new:
            with self.stats_lock:
                self.stats['unique_urls'] += 1
        
        # Real-time storage if enabled
        if self.storage_bridge and self.enable_db_storage:
            try:
                storage_result = {
                    'url': url,
                    'title': result.get('title', ''),
                    'snippet': result.get('snippet', ''),
                    'sources': sources,
                    'engine': engine_code,
                    'rank': result.get('rank', 0),
                    'score': result.get('score', 0.0),
                    'timestamp': datetime.now().isoformat(),
                    'attributes': result.get('attributes', {})
                }
                
                # Add metadata if present
                for key in ['author', 'published_date', 'image', 'category']:
                    if key in result and result[key] is not None:
                        storage_result[key] = result[key]
                
                # Safe storage call
                stored_count = self.storage_bridge.result_storage.store_search_results(
                    query=self.keyword,
                    results=[storage_result],  # Wrap single result in list
                    project_id=self.checkpoint_id
                )

                if stored_count > 0:
                    logger.debug(f"✅ Stored result: {url[:50]}...")
            except Exception as e:
                logger.error(f"⚠️ DB STORAGE ERROR (Non-fatal): {e}")
                # Continue processing - JSON export is the priority
        
        # Queue for writing
        result_data = {
            'url': url,
            'title': result.get('title', ''),
            'snippet': result.get('snippet', ''),
            'sources': sources,  # List of all engines that found this URL
                    'engine': engine_code,
                    'timestamp': datetime.now().isoformat(),
                    'attributes': result.get('attributes', {})
        }
        
        action = 'new' if is_new else 'duplicate'
        
        try:
            self.result_queue.put((result_data, action), timeout=5)
        except queue.Full:
            logger.warning(f"Result queue full, skipping result from {engine_code}")
    
    def search(self):
        """Run the search across all engines"""
        self._search_start_time = time.time()
        
        print(f"\nStarting brute force search for: '{self.keyword}'")
        print(f"Output file: {self.output_file}")
        print(f"Engines: {', '.join([ENGINE_CONFIG[e]['name'] for e in self.engines])}")
        print(f"Max concurrent workers: {self.max_workers}")
        
        # Emit search started event (sync)
        self.emit_event_sync('status', {
            'status': 'started',
            'query': self.keyword,
            'engines': self.engines,
            'progress': 0
        })
        
        # Check if resuming from checkpoint
        resume_info = self.checkpoint_manager.get_resume_info()
        if resume_info.get('query'):
            print(f"\n📂 Resuming from checkpoint: {self.checkpoint_id}")
            print(self.checkpoint_manager.get_progress_summary())
            
            # Filter engines to only uncompleted ones
            self.engines = [e for e in self.engines 
                          if self.checkpoint_manager.should_resume_engine(e)]
            print(f"Remaining engines: {', '.join(self.engines)}")
        
        # Update checkpoint with search info
        self.checkpoint_manager.update_query_info(self.keyword, self.engines)
        
        # Query expansion if enabled - temporarily disabled
        # if self.enable_expansion:
        #     print("\nQuery Expansion ENABLED - Generating variations...")
        #     variations = self.query_expander.expand(self.keyword)
        #     print(f"Generated {len(variations)} query variations")
        #     self.stats['queries_expanded'] = [v.query for v in variations[:5]]  # Track first 5
        #     print("First 5 variations:")
        #     for i, var in enumerate(variations[:5]):
        #         print(f"  {i+1}. {var.query}")
        
        print()
        
        # Start result writer thread
        writer_thread = threading.Thread(target=self._result_writer_thread)
        writer_thread.start()

        # Start filtered results writer thread
        filtered_writer_thread = threading.Thread(target=self._filtered_writer_thread)
        filtered_writer_thread.start()
        
        # SMART TIERED PROCESSING - STAGGERED FOR CONTINUOUS STREAMING
        # Engines start in tiers but staggered within each tier for constant results
        
        # Group engines by performance tier
        fast_engines = [e for e in self.engines if e in ENGINE_PERFORMANCE['fast']]
        medium_engines = [e for e in self.engines if e in ENGINE_PERFORMANCE['medium']]
        slow_engines = [e for e in self.engines if e in ENGINE_PERFORMANCE['slow']]
        
        # EVENT-DRIVEN COLLECTION: Single unified queue for all results
        # Replaces round-robin polling for 20-30% speed improvement
        unified_results_queue = queue.Queue(maxsize=2000)  # Single queue for all engines
        completion_events = {engine: threading.Event() for engine in self.engines}  # Track completion per engine
        completed_engines = set()
        engine_result_counts = {e: 0 for e in self.engines}  # Track results per engine

        def engine_worker(engine_code, initial_delay=0):
            """Worker that runs engine and pushes results to unified queue"""
            engine_results_buffer = []  # Buffer for analytics
            error_info = None

            try:
                # Apply staggered delay for continuous streaming
                if initial_delay > 0:
                    time.sleep(initial_delay)

                # ANALYTICS: Mark engine start
                if self.analytics_collector:
                    self.analytics_collector.start_engine(
                        engine_code,
                        ENGINE_CONFIG.get(engine_code, {}).get('name', engine_code)
                    )

                print(f"🚀 Starting {ENGINE_CONFIG[engine_code]['name']} [{engine_code}]")

                # Run the existing streaming engine method
                for result in self._run_streaming_engine(engine_code):
                    if self._stop_processing:
                        break

                    # Buffer result for analytics
                    engine_results_buffer.append(result)

                    # Add result to unified queue with exponential backoff
                    for retry in range(3):
                        try:
                            unified_results_queue.put((engine_code, result), timeout=10)
                            break
                        except queue.Full:
                            if retry == 2:
                                logger.warning(f"Unified queue full, dropping result from {engine_code}")
                            else:
                                # Exponential backoff: 0.5s, 1s, 2s
                                backoff_delay = 0.5 * (2 ** retry)
                                time.sleep(backoff_delay)

                print(f"✅ [{engine_code}] {ENGINE_CONFIG[engine_code]['name']} completed")

            except Exception as e:
                logger.error(f"Engine {engine_code} failed: {e}")
                print(f"❌ [{engine_code}] {ENGINE_CONFIG[engine_code]['name']} failed: {str(e)[:100]}")
                error_info = str(e)
                # Classify error type
                error_type = 'other'
                error_str = str(e).lower()
                if 'timeout' in error_str:
                    error_type = 'timeout'
                elif 'rate' in error_str or '429' in error_str:
                    error_type = 'rate_limit'
                elif 'connection' in error_str or 'network' in error_str:
                    error_type = 'network'
                elif 'parse' in error_str or 'json' in error_str:
                    error_type = 'parse'

                # ANALYTICS: Record failure
                if self.analytics_collector:
                    self.analytics_collector.record_failure(
                        engine_code,
                        error=str(e),
                        error_type=error_type,
                        rate_limited=('429' in error_str or 'rate' in error_str)
                    )
            finally:
                # ANALYTICS: Record engine results (success case)
                if self.analytics_collector and not error_info:
                    self.analytics_collector.record_engine(
                        engine_code,
                        results=engine_results_buffer,
                        success=True
                    )

                # Signal completion via event (no sentinel needed)
                completion_events[engine_code].set()
        
        # Start engines in smart tiers with staggering for continuous results
        print(f"\n🎯 SMART TIERED PROCESSING - CONTINUOUS STREAMING")
        print(f"Tier 1 (0-1s stagger): {', '.join(fast_engines) if fast_engines else 'None'}")
        print(f"Tier 2 (1.5-3s stagger): {', '.join(medium_engines) if medium_engines else 'None'}")
        print(f"Tier 3 (3.5-6s stagger): {', '.join(slow_engines) if slow_engines else 'None'}")
        print("Engines staggered for continuous result streaming!\n")
        
        threads = []
        engine_start_times = {}
        
        # TIER 1: Fast engines with micro-staggering (0-1 second spread)
        if fast_engines:
            print(f"🚀 Starting Tier 1 (Fast engines)...")
            for i, engine_code in enumerate(fast_engines):
                # Stagger by 0.2 seconds within tier 1
                delay = i * 0.2
                engine_start_times[engine_code] = delay
                t = threading.Thread(
                    target=engine_worker,
                    args=(engine_code, delay),  # Event-driven: no per-engine queue
                    daemon=True
                )
                t.start()
                threads.append(t)
                if delay > 0:
                    print(f"  [{engine_code}] {ENGINE_CONFIG[engine_code]['name']} - starting in {delay:.1f}s")
                else:
                    print(f"  [{engine_code}] {ENGINE_CONFIG[engine_code]['name']} - starting now")
        
        # TIER 2: Medium engines starting at 1.5 seconds with staggering
        if medium_engines:
            base_delay = 1.5
            for i, engine_code in enumerate(medium_engines):
                # Stagger by 0.25 seconds within tier 2
                delay = base_delay + (i * 0.25)
                engine_start_times[engine_code] = delay
                t = threading.Thread(
                    target=engine_worker,
                    args=(engine_code, delay),  # Event-driven: no per-engine queue
                    daemon=True
                )
                t.start()
                threads.append(t)
                print(f"  [{engine_code}] {ENGINE_CONFIG[engine_code]['name']} - starting in {delay:.1f}s")

        # TIER 3: Slow engines starting at 3.5 seconds with staggering
        if slow_engines:
            base_delay = 3.5
            for i, engine_code in enumerate(slow_engines):
                # Stagger by 0.5 seconds within tier 3
                delay = base_delay + (i * 0.5)
                engine_start_times[engine_code] = delay
                t = threading.Thread(
                    target=engine_worker,
                    args=(engine_code, delay),  # Event-driven: no per-engine queue
                    daemon=True
                )
                t.start()
                threads.append(t)
                print(f"  [{engine_code}] {ENGINE_CONFIG[engine_code]['name']} - starting in {delay:.1f}s")
        
        # EVENT-DRIVEN COLLECTION: Single unified queue consumer
        # Replaces round-robin polling for 20-30% speed improvement
        # Instead of polling each queue with timeout, we block on unified queue
        active_engines = set(self.engines)
        results_processed = 0
        last_progress_time = time.time()

        print("\n📊 Processing results with EVENT-DRIVEN collection...")
        print("Legend: [ENGINE:count] where ✓ = completed\n")

        # Process results from unified queue until all engines complete
        while active_engines:
            try:
                # Block on unified queue with short timeout
                # This is ~40x more efficient than polling 40 queues individually
                item = unified_results_queue.get(timeout=0.1)

                # Unpack result: (engine_code, result)
                engine_code, result = item
                self._process_engine_result(engine_code, result)

                results_processed += 1
                engine_result_counts[engine_code] += 1

                # Show progress every 50 results or every second
                current_time = time.time()
                if results_processed % 50 == 0 or (current_time - last_progress_time) > 1.0:
                    # Build compact status showing all engines
                    status_parts = []
                    for e in self.engines:
                        count = engine_result_counts[e]
                        if e in active_engines:
                            status_parts.append(f"{e}:{count}")
                        else:
                            status_parts.append(f"{e}:✓{count}")

                    print(f"📈 Total: {results_processed} | {' '.join(status_parts)}")
                    last_progress_time = current_time

            except queue.Empty:
                # Check for completed engines via their events
                for engine_code in list(active_engines):
                    if completion_events[engine_code].is_set():
                        active_engines.remove(engine_code)
                        count = engine_result_counts[engine_code]
                        print(f"\n✅ [{engine_code}] completed with {count} results")
                        self.checkpoint_manager.mark_engine_completed(engine_code)

            except Exception as e:
                logger.error(f"Error processing result: {e}")

        # Drain any remaining items in the unified queue
        drained = 0
        while True:
            try:
                item = unified_results_queue.get_nowait()
                engine_code, result = item
                self._process_engine_result(engine_code, result)
                results_processed += 1
                engine_result_counts[engine_code] += 1
                drained += 1
            except queue.Empty:
                break

        if drained > 0:
            logger.info(f"Drained {drained} remaining results from unified queue")

        # All engines completed
        print(f"\n✨ All engines completed! Total results processed: {results_processed}")
        print(f"Results per engine: {dict(engine_result_counts)}")
        
        # Stop writer thread
        self._stop_processing = True
        writer_thread.join()
        filtered_writer_thread.join()
        
        # Calculate final statistics
        start_time = datetime.fromisoformat(self.stats['start_time'])
        elapsed_time = (datetime.now() - start_time).total_seconds()
        self.stats['elapsed_time_seconds'] = elapsed_time
        self.stats['results_per_second'] = round(self.stats['total_results'] / elapsed_time, 2) if elapsed_time > 0 else 0
        if self.stats['total_results'] > 0:
            self.stats['duplicate_rate'] = round((self.stats['total_results'] - self.stats['unique_urls']) / self.stats['total_results'] * 100, 2)
        
        # Add filter statistics
        if self.enable_exact_phrase_filter and 'filtered_results' in self.stats:
            total_before_filter = self.stats['total_results'] + self.stats['filtered_results']
            self.stats['filter_rate'] = round(self.stats['filtered_results'] / total_before_filter * 100, 2) if total_before_filter > 0 else 0
            logger.info(f"Exact phrase filter removed {self.stats['filtered_results']} results ({self.stats['filter_rate']}%)")
        
        # Enrich results with missing snippets - Always run if enricher is available
        if self.enricher and self.enable_snippet_enrichment:
            print("\n🔍 Starting snippet enrichment phase...")
            enriched_count = self._enrich_missing_snippets()
            if enriched_count > 0:
                print(f"🎯 Total enriched: {enriched_count} results with better snippets")
                self.stats['enriched_results'] = enriched_count
            else:
                print("ℹ️  No snippets needed enrichment or enrichment failed")
        
        # Finalize JSON with statistics
        self.json_writer.finalize(self.stats)
        
        # Store results in database
        if self.db_storage:
            try:
                print("\n💾 Using disk-based deduplication - results tracked efficiently...")
                stats = self.deduplicator.get_stats()
                print(f"Total unique URLs: {stats['unique_urls']}")
                
                # Note: In the memory-optimized version, results are processed incrementally
                # and stored in the deduplicator's SQLite database to minimize memory usage
                
            except Exception as e:
                logger.error(f"Failed to get deduplication stats: {e}")
                print(f"⚠️  Database stats failed: {str(e)[:100]}")
        
        # Extract entities and populate graph storage
        logger.info(f"DEBUG: Search completed with {self.stats['total_results']} total results, {self.stats['unique_urls']} unique URLs")
        if self.storage_bridge and self.deduplicator:
            try:
                print("\n🧠 Extracting entities and populating graph...")
                logger.info("DEBUG: Entering entity extraction phase")
                
                # Get all results from deduplicator for entity extraction
                results_for_extraction = []
                
                # DEBUG: Check deduplicator stats before extraction
                dedup_stats = self.deduplicator.get_stats()
                logger.info(f"DEBUG: Deduplicator stats before extraction: {dedup_stats}")
                
                # Query the deduplicator's SQLite database for all results
                cursor = self.deduplicator.conn.execute("""
                    SELECT url, title, snippet, sources, content_metadata 
                    FROM seen_urls 
                    ORDER BY first_seen DESC
                """)
                
                row_count = 0
                
                for row in cursor.fetchall():
                    row_count += 1
                    # Unpack tuple - indices match SELECT statement
                    url, title, snippet, sources_str, content_metadata = row
                    
                    # Convert sources back to list
                    sources = sources_str.split('+') if sources_str else []
                    result = {
                        'url': url,
                        'title': title or '',
                        'snippet': snippet or '',
                        'sources': sources,
                        'engine': sources[0] if sources else 'unknown'
                    }
                    
                    # Add metadata if available
                    if content_metadata:
                        try:
                            metadata = json.loads(content_metadata)
                            if metadata:
                                # Add metadata fields directly to result
                                for key in ['author', 'published_date', 'score', 'image', 'category']:
                                    if key in metadata and metadata[key] is not None:
                                        result[key] = metadata[key]
                                # Add attributes if present
                                if 'attributes' in metadata:
                                    result['attributes'] = metadata['attributes']
                        except Exception as e:
                            logger.warning(f"Failed to parse metadata for {url}: {e}")
                    
                    results_for_extraction.append(result)
                
                logger.info(f"DEBUG: Extraction phase found {row_count} rows in seen_urls table")
                logger.info(f"DEBUG: Built {len(results_for_extraction)} results for extraction")
                
                # Process results through storage bridge
                if results_for_extraction:
                    logger.info("DEBUG: Calling storage_bridge.process_search_results with data")
                    entity_counts = self.storage_bridge.process_search_results(
                        search_id=self.checkpoint_id,
                        query=self.keyword,
                        results=results_for_extraction,
                        project_id=f"search_{self.checkpoint_id}"
                    )
                else:
                    logger.warning("DEBUG: No results found for extraction - storage bridge not called")
                    entity_counts = {}  # Set empty dict to prevent errors
                    
                # Display entity extraction statistics if available
                if entity_counts:
                    total_entities = sum(count for key, count in entity_counts.items() 
                                       if key not in ['results_stored', 'urls', 'query_edges'])
                    
                    if total_entities > 0:
                        print(f"✅ Extracted {total_entities} entities:")
                        for entity_type, count in entity_counts.items():
                            if count > 0 and entity_type not in ['results_stored', 'urls', 'query_edges']:
                                print(f"   - {entity_type}: {count}")
                        print(f"   - URLs: {entity_counts.get('urls', 0)}")
                        print(f"   - Query connections: {entity_counts.get('query_edges', 0)}")
                        
                        # Store entity stats for reporting
                        self.stats['entity_extraction'] = entity_counts
                    else:
                        print("🔍 No entities extracted from search results")
                else:
                    print("⚠️  No results available for entity extraction")
                    
            except Exception as e:
                logger.error(f"Entity extraction failed: {e}")
                print(f"⚠️  Entity extraction failed: {str(e)[:100]}")
        
        # Enhanced summary with health status
        print(f"\n{'='*60}")
        print("Search completed!")
        print(f"Total results found: {self.stats['total_results']}")
        print(f"Unique URLs: {self.stats['unique_urls']}")
        print(f"Duplicate rate: {self.stats['duplicate_rate']}%")
        
        # Print filter statistics if enabled
        if 'filtered_results' in self.stats and self.stats['filtered_results'] > 0:
            filter_msg = f"Filtered out: {self.stats['filtered_results']} ({self.stats.get('filter_rate', 0)}%)"
            if self.enable_exact_phrase_filter:
                filter_msg += " - exact phrase"
            if self.detected_filetype:
                filter_msg += f" - filetype:{self.detected_filetype}"
            print(filter_msg)
        
        print(f"Results per second: {self.stats['results_per_second']}")
        print(f"Total time: {elapsed_time:.2f} seconds")
        
        # Emit completion event (sync)
        self.emit_event_sync('completed', {
            'total_results': self.stats['total_results'],
            'duration': elapsed_time,
            'engines_used': [e for e in self.engines if self.stats['engine_status'][e] == 'completed'],
            'categories': self.get_category_stats() if hasattr(self, 'categorized_results') else {}
        })
        
        # Engine health status
        working_engines = sum(1 for status in self.stats['engine_status'].values() 
                             if status == 'completed')
        total_engines = len(self.engines)
        health_pct = (working_engines / total_engines) * 100
        
        print(f"\nEngine Health: {working_engines}/{total_engines} engines working ({health_pct:.1f}%)")
        
        print(f"\nResults per engine:")
        # Thread-safe iteration over stats
        with self.stats_lock:
            results_per_engine = dict(self.stats['results_per_engine'])
            engine_status = dict(self.stats['engine_status'])
        
        for code, count in results_per_engine.items():
            status = engine_status[code]
            status_icon = "✅" if status == 'completed' else "⚠️" if status == 'timeout' else "❌"
            print(f"  {status_icon} [{code}] {ENGINE_CONFIG[code]['name']}: {count} results ({status})")
        
        if health_pct < 70:
            print(f"\n⚠️  Warning: {100-health_pct:.1f}% of engines failed. Consider checking API keys and network connectivity.")
        
        print(f"\nResults saved to: {self.output_file}")

        # ENGINE ANALYTICS: Print detailed per-engine analytics
        if self.analytics_collector:
            try:
                print("\n")  # Extra spacing before analytics
                self.analytics_collector.print_summary()
                self.analytics_collector.save_to_db()

                # Store analytics in stats for JSON export
                self.stats['engine_analytics'] = self.analytics_collector.to_dict()
                logger.info("Engine analytics saved to database and included in stats")
            except Exception as e:
                logger.error(f"Failed to output engine analytics: {e}")
                print(f"⚠️  Analytics output failed: {str(e)[:100]}")

        # SAVE ALL RESULTS TO JSON (including filtered results)
        self._save_results_json()

        # Run dual indexing if enabled (BEFORE cleanup)
        if os.getenv('ENABLE_INDEXING', 'true').lower() == 'true':
            self._run_dual_indexing()
        
        # Run post-search verification to clean up filtered results from SQL database
        if self.enable_exact_phrase_filter and self.storage_bridge and self.enable_db_storage:
            try:
                # Get filtered results from deduplicator's filtered_results table
                filtered_results = []
                if hasattr(self.deduplicator, 'conn'):
                    cursor = self.deduplicator.conn.execute("""
                        SELECT url, title, snippet, sources, content_metadata 
                        FROM filtered_results 
                        ORDER BY filtered_at DESC
                    """)
                    
                    for row in cursor.fetchall():
                        url, title, snippet, sources_str, content_metadata = row
                        sources = sources_str.split('+') if sources_str else []
                        result = {
                            'url': url,
                            'title': title or '',
                            'snippet': snippet or '',
                            'sources': sources,
                            'engine': sources[0] if sources else 'unknown'
                        }
                        filtered_results.append(result)
                
                if filtered_results:
                    logger.info(f"🧹 POST-VERIFICATION: Processing {len(filtered_results)} filtered results")
                    
                    # Run verification process
                    import asyncio
                    # Create new event loop for thread
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        verified_to_remove = loop.run_until_complete(self.verify_filtered_results(filtered_results, self.keyword))
                    finally:
                        loop.close()
                    
                    # Remove verified results from SQL database
                    removed_count = 0
                    for result in verified_to_remove:
                        url = result.get('url', '')
                        if url and self.storage_bridge.remove_result_from_sql(url, self.checkpoint_id):
                            removed_count += 1
                    
                    logger.info(f"🎯 POST-VERIFICATION: Removed {removed_count}/{len(filtered_results)} filtered results from SQL")
                    print(f"🧹 Cleaned up {removed_count} filtered results from SQL database")
                else:
                    logger.info("🧹 POST-VERIFICATION: No filtered results to verify")
                    
            except Exception as e:
                logger.error(f"❌ POST-VERIFICATION FAILED: {e}")
                print(f"⚠️  SQL cleanup failed: {str(e)[:100]}")
        
        # Clean up checkpoint on successful completion
        self.checkpoint_manager.cleanup()
        print("✅ Checkpoint cleaned up")
        
        # Clean up disk deduplicator
        self.deduplicator.cleanup()
        print("✅ Disk deduplicator cleaned up")

        if self.return_results:
            return self.final_results
    
    def _get_engine_timeout(self, engine_code: str) -> int:
        """Get timeout for engine based on performance category - OPTIMIZED FOR STREAMING"""
        # Aggressive timeouts for faster streaming response
        for category, engines in ENGINE_PERFORMANCE.items():
            if engine_code in engines:
                if category == 'fast':
                    return 15  # Reduced from 30s for faster feedback
                elif category == 'medium': 
                    return 30  # Reduced from 60s
                else:  # slow
                    return 45  # Reduced from 120s to prevent long hangs
        return 15  # Aggressive default timeout

    def _run_categorization_sync(self):
        """Synchronous wrapper to run async categorization"""
        import asyncio
        try:
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._process_categorization_batch())
        finally:
            loop.close()
    
    def _init_scraper(self):
        """Initialize ScrapeR if not already done"""
        if self._scraper is None:
            try:
                from brute.scraper.scraper import scraper
                # Get Firecrawl API key from environment
                api_key = os.getenv('FIRECRAWL_API_KEY')
                if api_key:
                    self._scraper = ScrapeR(api_key=api_key, max_results=self.max_scrape_results)
                    logger.info("ScrapeR initialized (but automatic scraping is DISABLED)")
                else:
                    logger.warning("FIRECRAWL_API_KEY not found - scraping disabled")
            except Exception as e:
                logger.error(f"Failed to initialize ScrapeR: {e}")
                self._scraper = False
    
    def _run_scraping_sync(self):
        """Synchronous wrapper to run async scraping"""
        # import asyncio
        # try:
        #     # Create a new event loop for this thread
        #     loop = asyncio.new_event_loop()
        #     asyncio.set_event_loop(loop)
        #     loop.run_until_complete(self._process_scraping_batch())
        # finally:
        #     loop.close()
        pass
    
    async def _process_scraping_batch(self):
        """Process a batch of URLs for scraping"""
        with self._scraper_lock:
            if len(self.scraping_queue) < self.scraping_batch_size:
                return  # Wait for more results
            
            # Take a batch
            batch = self.scraping_queue[:self.scraping_batch_size]
            self.scraping_queue = self.scraping_queue[self.scraping_batch_size:]
        
        # Initialize scraper if needed
        self._init_scraper()
        if not self._scraper or self._scraper is False:
            return
        
        try:
            print(f"\n🌐 Scraping batch of {len(batch)} URLs...")
            
            # Prepare URLs
            urls = [item['url'] for item in batch]
            
            # Use ScrapeR's batch scraping
            scraped_results = await self._scraper._scrape_urls(urls)
            
            # Update scraped URLs set
            for url in scraped_results:
                self.scraped_urls.add(url)
            
            print(f"✅ Scraped {len(scraped_results)} URLs successfully")
            
            # Store scraped content in results (for later indexing)
            for item in batch:
                if item['url'] in scraped_results:
                    scrape_result = scraped_results[item['url']]
                    if item['url'] in self.deduplicator._results:
                        self.deduplicator._results[item['url']]['scraped_content'] = scrape_result.markdown
            
        except Exception as e:
            logger.error(f"Scraping failed: {e}")
            print(f"⚠️  Scraping failed: {str(e)[:100]}")
    
    async def _process_categorization_batch(self):
        """Process a batch of results for categorization"""
        with self._categorizer_lock:
            if len(self.categorization_queue) < self.categorization_batch_size:
                return  # Wait for more results
            
            # Take a batch
            batch = self.categorization_queue[:self.categorization_batch_size]
            self.categorization_queue = self.categorization_queue[self.categorization_batch_size:]
        
        try:
            # Import categorizer
            from brute.categorizer.categorizer import categorize_results
            
            print(f"\n📂 Categorizing batch of {len(batch)} results...")
            
            # Run categorization
            categorized = await categorize_results(batch)
            
            # Update results with categories
            for result in categorized:
                url = result['url']
                # Handle both 'category' (singular) and 'categories' (plural) for backward compatibility
                if 'category' in result:
                    category = result['category']
                elif 'categories' in result:
                    categories = result['categories']
                    category = categories[0] if categories and isinstance(categories, list) else 'uncategorized'
                else:
                    category = 'uncategorized'
                
                self.categorized_results[url] = category
                
                # Display categorized result
                if url in self.deduplicator._results:
                    sources = '+'.join(self.deduplicator._results[url]['sources'])
                    title = self.deduplicator._results[url]['title'][:60] + '...'
                    category = self.categorized_results[url]
                    print(f"  [{category.upper()}] [{sources}] {title}")
            
            print(f"✅ Categorization complete\n")
            
        except Exception as e:
            logger.error(f"Categorization failed: {e}")
            print(f"⚠️  Categorization failed: {str(e)[:100]}")
    
    def _run_streaming_engine(self, engine_code: str):
        """Generator wrapper that yields results from engine with timeout and health monitoring"""
        import signal
        import threading

        # CIRCUIT BREAKER CHECK: Skip engine if health monitor says it's down
        if self.health_monitor and not self.health_monitor.should_allow_request(engine_code):
            engine_name = ENGINE_CONFIG.get(engine_code, {}).get('name', engine_code)
            status = self.health_monitor.get_engine_status(engine_code)
            logger.warning(f"⚡ {engine_name} [{engine_code}] skipped - circuit breaker OPEN ({status.value})")
            with self.stats_lock:
                self.stats['engine_status'][engine_code] = 'circuit_open'
            return  # Skip this engine entirely

        def timeout_handler():
            engine_name = ENGINE_CONFIG.get(engine_code, {}).get('name', engine_code)
            logger.warning(f"⚠️ {engine_name} [{engine_code}] timed out - continuing with other engines")
            with self.stats_lock:
                self.stats['engine_status'][engine_code] = 'timeout'
                results_count = self.stats['results_per_engine'][engine_code]
            self.emit_engine_status(engine_code, 'failed', results_count)
            # Record timeout in health monitor
            if self.health_monitor:
                self.health_monitor.record_request_failure(engine_code, start_time, 'timeout', 'Engine timed out')

        timeout_seconds = self._get_engine_timeout(engine_code)
        timer = threading.Timer(timeout_seconds, timeout_handler)
        timer.start()

        # Record request start in health monitor
        start_time = time.time()
        if self.health_monitor:
            self.health_monitor.record_request_start(engine_code)

        result_count = 0
        try:
            # Yield each result from the engine generator
            for result in self._run_engine(engine_code):
                result_count += 1
                yield result  # Pass results through for round-robin processing

            # Record success in health monitor
            if self.health_monitor:
                self.health_monitor.record_request_success(engine_code, start_time, result_count)

        except Exception as e:
            engine_name = ENGINE_CONFIG.get(engine_code, {}).get('name', engine_code)
            logger.error(f"❌ {engine_name} [{engine_code}] failed: {e}")
            with self.stats_lock:
                self.stats['engine_status'][engine_code] = 'error'
            # Record failure in health monitor
            if self.health_monitor:
                self.health_monitor.record_request_failure(engine_code, start_time, 'error', str(e))
        finally:
            timer.cancel()
    
    def _enrich_missing_snippets(self):
        """Enrich results that have missing or empty snippets"""
        if not self.enricher:
            return 0
            
        print("\n🔍 Checking for results with missing/poor snippets (< 20 chars)...")
        
        # Get all results from the deduplicator
        try:
            # Query results directly from SQLite
            conn = self.deduplicator.conn
            cursor = conn.cursor()
            
            # Find results with empty or placeholder snippets - more aggressive detection
            cursor.execute("""
                SELECT url, title, snippet, sources 
                FROM seen_urls 
                WHERE snippet IS NULL 
                   OR snippet = '' 
                   OR snippet LIKE '%Found on domain%'
                   OR snippet LIKE '%Page at%'
                   OR snippet LIKE '%No snippet available%'
                   OR snippet LIKE '%Click to view%'
                   OR LENGTH(TRIM(snippet)) < 20  -- Lowered from 50
                LIMIT 500  -- Increased from 100
            """)
            
            results_to_enrich = cursor.fetchall()
            
            if not results_to_enrich:
                logger.info("No results need snippet enrichment")
                return 0
            
            print(f"📌 Found {len(results_to_enrich)} results with missing/poor snippets (will enrich up to 500)")
            logger.info(f"Starting snippet enrichment for {len(results_to_enrich)} results")
            
            # Extract URLs for batch enrichment
            urls_to_enrich = [row[0] for row in results_to_enrich]
            
            # Run async enrichment in sync context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # Enrich in batches
                enrichment_data = loop.run_until_complete(
                    self.enricher.enrich(urls_to_enrich)
                )
                
                # Update results with enriched snippets
                enriched_count = 0
                for row in results_to_enrich:
                    url = row[0]
                    if url in enrichment_data and enrichment_data[url]:
                        enriched = enrichment_data[url]
                        if enriched.get('snippet') and len(enriched['snippet']) > len(row[2] or ''):
                            # Update the database with enriched snippet
                            cursor.execute("""
                                UPDATE seen_urls 
                                SET snippet = ?, title = ?
                                WHERE url = ?
                            """, (enriched['snippet'], enriched.get('title', row[1]), url))
                            enriched_count += 1
                            
                            # Skip updating in-memory results to avoid dictionary iteration errors
                            # The enriched data is already saved to the database
                            # if url in self.categorized_results:
                            #     self.categorized_results[url]['snippet'] = enriched['snippet']
                            #     self.categorized_results[url]['title'] = enriched.get('title', row[1])
                            #     self.categorized_results[url]['enriched'] = True
                
                conn.commit()
                
                if enriched_count > 0:
                    print(f"✅ Successfully enriched {enriched_count}/{len(results_to_enrich)} snippets")
                    logger.info(f"Snippet enrichment complete: {enriched_count} enriched, {len(results_to_enrich) - enriched_count} skipped")
                else:
                    print(f"ℹ️  No snippets could be enriched (0/{len(results_to_enrich)})")
                    
                return enriched_count
                
            finally:
                loop.close()
                
        except Exception as e:
            logger.error(f"Error enriching missing snippets: {e}")
            return 0

    def _save_results_json(self):
        """Save all search results (passed and filtered) to a JSON file in project root /results folder"""
        try:
            # Use project root /results folder
            results_dir = Path(__file__).parent.parent.parent.parent / 'results'
            results_dir.mkdir(exist_ok=True)

            # Create filename: query + date + time
            query_slug = self.keyword.replace('"', '').replace(' ', '_').replace('/', '_').replace(':', '_')[:50]
            date_str = datetime.now().strftime('%Y-%m-%d')
            time_str = datetime.now().strftime('%H-%M-%S')
            results_file = results_dir / f'{query_slug}_{date_str}_{time_str}.json'

            # Build comprehensive results object
            results_data = {
                'search_id': getattr(self, 'search_id', f'search_{int(time.time()*1000)}'),
                'query': self.keyword,
                'timestamp': datetime.now().isoformat(),
                'stats': {
                    'total_passed': len(self.all_results_list),
                    'total_filtered': len(self.filtered_results_list),
                    'unique_urls': self.stats.get('unique_urls', 0),
                    'engines_used': list(self.engines),
                    'filtered_per_engine': dict(self.stats.get('filtered_per_engine', {}))
                },
                'passed_results': self.all_results_list,
                'filtered_results': self.filtered_results_list
            }

            # Save to JSON file
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(results_data, f, indent=2, ensure_ascii=False)

            print(f"\n📊 All results saved to: {results_file}")
            print(f"   - Passed results: {len(self.all_results_list)}")
            print(f"   - Filtered results: {len(self.filtered_results_list)}")
            logger.info(f"Results JSON saved: {results_file}")

        except Exception as e:
            logger.error(f"Failed to save results JSON: {e}")
            print(f"⚠️  Failed to save results JSON: {str(e)[:100]}")

    def _run_dual_indexing(self):
        """Run Whoosh and vector indexing on all search results"""
        print("\n" + "="*80)
        print("Running dual indexing (Whoosh + Vector embeddings)...")
        print("="*80)
        
        try:
            # Prepare data for indexing
            query_name = self.keyword.replace('"', '').replace(' ', '_')[:50]  # Sanitize query for filename
            index_timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            
            # Initialize Whoosh indexer
            whoosh_index_dir = f"indices/whoosh/{query_name}_{index_timestamp}"
            from modules.brute.infrastructure.whoosh_indexer import Whooshindexer
            whoosh_indexer = Whooshindexer(index_dir=whoosh_index_dir)
            
            # Prepare files for Whoosh indexing
            files_to_index = []
            file_entities_map = {}
            file_id_map = {}
            
            # Create temporary directory for content files
            temp_dir = f"temp_index/{query_name}_{index_timestamp}"
            os.makedirs(temp_dir, exist_ok=True)
            
            # Collect all results from deduplicator database
            all_results = []
            with self.deduplicator._lock:
                cursor = self.deduplicator.conn.cursor()
                cursor.execute('SELECT url, title, snippet, sources FROM seen_urls')
                for row in cursor.fetchall():
                    url, title, snippet, sources = row
                    result = {
                        'url': url,
                        'title': title or 'No title',
                        'sources': sources.split('+') if sources else [],
                        'aggregated_snippet': snippet or '',
                        'scraped_content': '',  # Not stored in DiskDeduplicator
                        'category': self.categorized_results.get(url, ''),
                        'attributes': {}
                    }
                    all_results.append(result)
            
            for i, result in enumerate(all_results):
                # Create a temporary file for each result
                filename = f"{i:04d}_{result['url'].replace('://', '_').replace('/', '_')[:100]}.txt"
                filepath = os.path.join(temp_dir, filename)
                
                # Combine all available content
                content_parts = []
                content_parts.append(f"Title: {result.get('title', 'No title')}")
                content_parts.append(f"URL: {result['url']}")
                content_parts.append(f"Engines: {','.join(result.get('sources', []))}")
                
                if result.get('aggregated_snippet'):
                    content_parts.append(f"\nSnippet:\n{result['aggregated_snippet']}")
                
                if result.get('scraped_content'):
                    content_parts.append(f"\nScraped Content:\n{result['scraped_content']}")
                
                if result.get('category'):
                    content_parts.append(f"\nCategory: {result['category']}")
                    if result.get('attributes'):
                        content_parts.append(f"Attributes: {json.dumps(result['attributes'])}")
                
                # Write content to file
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(content_parts))
                
                # Add to indexing list
                files_to_index.append((filepath, result['url'], self.keyword))
                
                # Extract entities for Whoosh (simplified)
                entities = {
                    "entities": {
                        "people": [],
                        "companies": [],
                        "emails": [],
                        "phones": []
                    }
                }
                file_entities_map[filepath] = entities
                file_id_map[filepath] = f"file_{i:04d}"
            
            # Index with Whoosh
            print(f"\nIndexing {len(files_to_index)} results with Whoosh...")
            whoosh_indexer.index_files(files_to_index, file_entities_map, file_id_map)
            
            # Vector indexing (skip if no valid OpenAI API key)
            openai_key = os.getenv('OPENAI_API_KEY')
            if not openai_key or openai_key.startswith('your-api-key'):
                print(f"\n⚠️  Skipping vector embeddings: Invalid or placeholder OpenAI API key")
                print(f"   Set a valid OPENAI_API_KEY in .env to enable vector indexing")
            else:
                print(f"\nCreating vector embeddings...")
                vector_store_name = f"{query_name}_{index_timestamp}"
                
                # Prepare documents for vector embedding
                documents = []
                for result in all_results:
                    # Combine all text for embedding
                    text_parts = [
                        result.get('title', ''),
                        result.get('aggregated_snippet', ''),
                        result.get('scraped_content', '')[:5000] if result.get('scraped_content') else ''
                    ]
                    full_text = ' '.join(filter(None, text_parts))
                    
                    if full_text.strip():
                        documents.append({
                            'url': result['url'],
                            'text': full_text,
                            'metadata': {
                                'title': result.get('title', ''),
                                'engines': ','.join(result.get('sources', [])),
                                'category': result.get('category', ''),
                                'query': self.keyword
                            }
                        })
                
                if documents:
                    # Create vector embeddings using OpenAI
                    from openai import OpenAI
                    client = OpenAI()
                    
                    print(f"Creating embeddings for {len(documents)} documents...")
                    embeddings = []
                    
                    # Process in batches of 20
                    for i in range(0, len(documents), 20):
                        batch = documents[i:i+20]
                        texts = [doc['text'][:8000] for doc in batch]  # Limit text length
                        
                        response = client.embeddings.create(
                            input=texts,
                            model="text-embedding-3-small"
                        )
                        
                        for j, embedding in enumerate(response.data):
                            embeddings.append({
                                'embedding': embedding.embedding,
                                'metadata': batch[j]['metadata'],
                                'url': batch[j]['url']
                            })
                        
                        print(f"  Processed {min(i+20, len(documents))}/{len(documents)} documents")
                    
                    # Save embeddings to a simple JSON file (in production, use a proper vector DB)
                    vector_file = f"indices/vectors/{vector_store_name}.json"
                    os.makedirs(os.path.dirname(vector_file), exist_ok=True)
                    
                    with open(vector_file, 'w', encoding='utf-8') as f:
                        json.dump({
                            'query': self.keyword,
                            'created_at': datetime.utcnow().isoformat(),
                            'num_documents': len(embeddings),
                            'embeddings': embeddings
                        }, f)
                    
                    print(f"\n✓ Vector embeddings saved to: {vector_file}")
                else:
                    print(f"\n⚠️  No documents to embed")
            
            print(f"\n✓ Whoosh index created at: {whoosh_index_dir}")
            
            # Clean up temporary files
            import shutil
            shutil.rmtree(temp_dir)
            
            print(f"\n✓ Whoosh index created at: {whoosh_index_dir}")
            print(f"✓ Dual indexing complete!")
            
        except Exception as e:
            print(f"\n✗ Error during dual indexing: {str(e)}")
            import traceback
            traceback.print_exc()


    def _detect_filetype_search(self):
        """Detect if this is a filetype search and extract target extensions"""
        import re
        
        # Check for filetype: or ext: operators
        filetype_match = re.search(r'filetype:(\w+)', self.keyword, re.IGNORECASE)
        if filetype_match:
            self.detected_filetype = filetype_match.group(1).lower()
            self.filetype_extensions = [self.detected_filetype]
            return
            
        ext_match = re.search(r'ext:(\w+)', self.keyword, re.IGNORECASE)
        if ext_match:
            self.detected_filetype = ext_match.group(1).lower()
            self.filetype_extensions = [self.detected_filetype]
            return
            
        # Check for macro operators (word!)
        words = self.keyword.split()
        for word in words:
            if word.endswith('!'):
                candidate = word[:-1].lower()
                # Check known filetype macros
                if candidate in ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx']:
                    self.detected_filetype = candidate
                    self.filetype_extensions = [candidate]
                    return
                elif candidate == 'document':
                    self.detected_filetype = 'document'
                    self.filetype_extensions = ['pdf', 'doc', 'docx', 'odt', 'rtf', 'txt']
                    return
                elif candidate == 'spreadsheet':
                    self.detected_filetype = 'spreadsheet'
                    self.filetype_extensions = ['xls', 'xlsx', 'csv', 'ods']
                    return
                elif candidate == 'presentation':
                    self.detected_filetype = 'presentation'
                    self.filetype_extensions = ['ppt', 'pptx', 'odp']
                    return
                elif candidate == 'code':
                    self.detected_filetype = 'code'
                    self.filetype_extensions = ['py', 'js', 'java', 'cpp', 'c', 'cs', 'rb', 'go', 'rs', 'swift']
                    return


def main():
    """
    CYMONIDES Brute Search CLI - Maximum Recall Search Engine

    Features:
    - 40+ search engines in parallel
    - Event-driven result streaming
    - Circuit breaker for failing engines
    - Hash-based O(N) deduplication with source aggregation
    - Adaptive rate limiting
    - SQLite disk-based storage for unlimited results
    """
    parser = argparse.ArgumentParser(
        description='CYMONIDES Brute Search - Maximum recall across 40+ search engines',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python brute.py "Glencore mining corruption"
  python brute.py "site:sec.gov 10-K filings" --tier fast
  python brute.py "filetype:pdf annual report" -e GO BI BR EX
  python brute.py "John Smith" --no-dedup --raw
  python brute.py --health          # Show engine health status
  python brute.py --list-engines    # List all available engines

Environment Variables:
  ENABLE_HEALTH_MONITOR=true    Enable circuit breaker (default: true)
  USE_CASCADE_EXECUTOR=true     Use 3-wave execution architecture
  ENABLE_INDEXING=true          Enable Whoosh/vector indexing
  MAX_WORKERS=10                Max parallel engine threads
        '''
    )

    # Positional argument
    parser.add_argument('keyword', nargs='?', help='Search keyword or phrase (supports operators)')

    # Output options
    parser.add_argument('-o', '--output', default=None,
                       help='Output JSON file (default: auto-generated in results/)')
    parser.add_argument('--format', choices=['json', 'csv', 'jsonl'], default='json',
                       help='Output format (default: json)')

    # Engine selection
    parser.add_argument('-e', '--engines', nargs='+', metavar='CODE',
                       help='Specific engine codes (e.g., GO BI BR EX)')
    parser.add_argument('--tier', choices=['fast', 'medium', 'slow', 'all'], default='all',
                       help='Engine tier to use (default: all)')
    parser.add_argument('--exclude', nargs='+', metavar='CODE',
                       help='Engine codes to exclude')

    # Performance tuning
    parser.add_argument('-w', '--workers', type=int, default=None,
                       help='Max parallel workers (default: from .env or 10)')
    parser.add_argument('--timeout', type=int, default=None,
                       help='Per-engine timeout in seconds (default: varies by tier)')

    # Deduplication & filtering
    parser.add_argument('--no-dedup', action='store_true',
                       help='Disable deduplication (show all results)')
    parser.add_argument('--raw', action='store_true',
                       help='Raw mode: no filtering, no dedup, maximum output')
    parser.add_argument('--exact-phrase', action='store_true',
                       help='Enable exact phrase matching filter')

    # Optimization flags
    parser.add_argument('--cascade', action='store_true',
                       help='Use CascadeExecutor 3-wave architecture')
    parser.add_argument('--no-health-monitor', action='store_true',
                       help='Disable circuit breaker health monitoring')

    # Debug & info
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Verbose logging (DEBUG level)')
    parser.add_argument('-q', '--quiet', action='store_true',
                       help='Quiet mode (errors only)')

    # Special commands
    parser.add_argument('--check-config', action='store_true',
                       help='Check configuration status and exit')
    parser.add_argument('--list-engines', action='store_true',
                       help='List available search engines and exit')
    parser.add_argument('--health', action='store_true',
                       help='Show engine health status and exit')
    parser.add_argument('--resume', type=str, metavar='CHECKPOINT_ID',
                       help='Resume from a previous checkpoint')

    args = parser.parse_args()

    # Handle special commands
    if args.check_config:
        Config.print_config_status()
        print("\n" + "="*60)
        print("OPTIMIZATION STATUS")
        print("="*60)
        print(f"  Health Monitor: {'Available' if HEALTH_MONITOR_AVAILABLE else 'Not Available'}")
        print(f"  Cascade Executor: {'Available' if CASCADE_EXECUTOR_AVAILABLE else 'Not Available'}")
        print(f"  Rate Limiter: Available")
        print(f"  Hash Deduplication: Available (O(N) complexity)")
        sys.exit(0)

    if args.list_engines:
        print("\n" + "="*60)
        print("AVAILABLE SEARCH ENGINES")
        print("="*60)

        # Group by performance tier
        for tier_name, tier_codes in ENGINE_PERFORMANCE.items():
            print(f"\n[{tier_name.upper()}] ({len(tier_codes)} engines)")
            print("-" * 40)
            for code in tier_codes:
                if code in ENGINE_CONFIG:
                    name = ENGINE_CONFIG[code].get('name', code)
                    print(f"  [{code:3}] {name}")

        print(f"\nTotal: {len(ENGINE_CONFIG)} engines")
        print("\nUsage: python brute.py \"query\" -e GO BI BR EX")
        sys.exit(0)

    if args.health:
        print("\n" + "="*60)
        print("ENGINE HEALTH STATUS")
        print("="*60)
        if HEALTH_MONITOR_AVAILABLE:
            monitor = EngineHealthMonitor()
            # Register all engines
            for code in ENGINE_CONFIG:
                monitor.register_engine(code, ENGINE_CONFIG[code].get('name', code))

            print("\nAll engines registered. Run a search to see health data.")
            print("Health data persists across sessions.")

            # Try to load existing health data
            try:
                health_file = os.path.join(os.path.dirname(__file__), 'engine_health.json')
                if os.path.exists(health_file):
                    with open(health_file, 'r') as f:
                        health_data = json.load(f)
                    print(f"\nLoaded health data from: {health_file}")
                    for code, data in health_data.items():
                        status = data.get('status', 'unknown')
                        success_rate = data.get('success_rate', 0)
                        print(f"  [{code}] {status} ({success_rate:.0%} success)")
            except Exception as e:

                print(f"[BRUTE] Error: {e}")

                pass
        else:
            print("Health monitor not available.")
        sys.exit(0)

    # Require keyword for search
    if not args.keyword:
        parser.error("Keyword is required unless using --check-config, --list-engines, or --health")

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.quiet:
        logging.getLogger().setLevel(logging.ERROR)

    # Build engine list
    engines = args.engines
    if not engines:
        # Use tier-based selection
        if args.tier == 'all':
            engines = list(ENGINE_CONFIG.keys())
        else:
            engines = ENGINE_PERFORMANCE.get(args.tier, [])

    # Apply exclusions
    if args.exclude:
        engines = [e for e in engines if e not in args.exclude]

    # Validate engine codes
    invalid = [e for e in engines if e not in ENGINE_CONFIG]
    if invalid:
        print(f"Error: Invalid engine codes: {', '.join(invalid)}")
        print(f"Valid codes: {', '.join(ENGINE_CONFIG.keys())}")
        sys.exit(1)

    # Set environment variables based on flags
    if args.cascade:
        os.environ['USE_CASCADE_EXECUTOR'] = 'true'
    if args.no_health_monitor:
        os.environ['ENABLE_HEALTH_MONITOR'] = 'false'

    # Print banner
    print("\n" + "="*60)
    print("🔥 CYMONIDES BRUTE SEARCH - MAXIMUM RECALL")
    print("="*60)
    print(f"Query: {args.keyword}")
    print(f"Engines: {len(engines)} ({args.tier} tier)")
    print(f"Optimizations: Health Monitor={'ON' if not args.no_health_monitor else 'OFF'}, "
          f"Cascade={'ON' if args.cascade else 'OFF'}")
    if args.raw:
        print("Mode: RAW (no dedup, no filter)")
    elif args.no_dedup:
        print("Mode: No deduplication")
    print("="*60 + "\n")

    # Create searcher
    searcher = BruteSearchEngine(
        keyword=args.keyword,
        output_file=args.output,
        engines=engines,
        max_workers=args.workers,
        checkpoint_id=args.resume
    )

    # Apply raw mode settings
    if args.raw:
        searcher.enable_exact_phrase_filter = False
        # Note: Dedup is handled at collection level

    if args.exact_phrase:
        searcher.enable_exact_phrase_filter = True
        searcher.force_exact_phrase = True

    try:
        results = searcher.search()

        # Final summary
        print("\n" + "="*60)
        print("✅ SEARCH COMPLETE")
        print("="*60)
        if hasattr(searcher, 'stats'):
            print(f"Total results: {searcher.stats.get('total_results', 0)}")
            print(f"Unique URLs: {searcher.stats.get('unique_urls', 0)}")
            print(f"Duplicate rate: {searcher.stats.get('duplicate_rate', 0)}%")

            # Show source aggregation stats
            if hasattr(searcher, 'deduplicator'):
                all_results = searcher.deduplicator.get_all_results()
                multi_source = sum(1 for r in all_results if len(r.get('sources', [])) > 1)
                if multi_source:
                    print(f"Multi-engine results: {multi_source} ({multi_source*100//len(all_results)}%)")

    except KeyboardInterrupt:
        print("\n\n⚠️  Search interrupted by user")
        if hasattr(searcher, 'checkpoint_manager'):
            searcher.checkpoint_manager.save_checkpoint()
            print(f"Progress saved. Resume with: python brute.py --resume {searcher.checkpoint_id} \"{args.keyword}\"")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
