"""
exact_phrase_recall_runner_exa.py  ·  v2 ("max-recall+ streaming + exact phrase enforcement")
====================================
Automates exact phrase searches for Exa with streaming support and maximum recall.

Changes from v1:
* **Streaming Support**: Results are yielded progressively as queries complete
* **Enhanced Exact Phrase Variations**: Categories and languages for more targeted exact searches  
* **Retry Logic**: Robust handling of API failures and rate limits
* **Iterative Exception Search**: Excludes found domains to discover more results
* **Thread Safety**: Parallel execution with proper locking
* **Improved Time Slices**: Better date handling with custom ranges
* **Exact Phrase Enforcement**: Maintains exact_only=True default for true exact phrase matching

Features:
* Uses functions from `search_engines.exa.py`.
* BY DEFAULT: Only performs exact phrase matching (exa_exact, exa_site) with enhanced variations.
* OPTIONAL: Set exact_only=False to include neural and news searches for broader recall.
* Handles exact phrase matching across site groups, categories, languages, and time slices.
* Converts time slices to Exa-compatible date parameters with enhanced support.
* Streams results progressively with optional parallel execution.
* Implements iterative exception search for maximum recall.
* Augments results with comprehensive metadata for downstream processing.

Fixed: Previously included neural and news searches by default, which don't
enforce exact phrase matching. Now exact_only=True by default for true exact phrase searches
with enhanced variations for maximum recall while maintaining exactness.
"""

from __future__ import annotations

try:
    from shared_session import get_shared_session
    SHARED_SESSION = True
except ImportError:
    SHARED_SESSION = False


import logging
import time
import threading
from typing import Dict, List, Optional, Iterable, Any, Tuple
from datetime import datetime, timedelta
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Use built-in Exa implementation instead of external module
# The external search_engines.exa module is not available, so we'll use the exa package directly
try:
    from exa_py import Exa
    EXA_AVAILABLE = True
except ImportError:
    print("WARNING: exa_py package not available. Install with: pip install exa_py")
    EXA_AVAILABLE = False

logger = logging.getLogger("exa_phrase_runner")

# Implement the missing Exa functions using exa_py
def exa_exact(phrase: str, **kwargs) -> List[Dict]:
    """Exact phrase search using Exa API with ENFORCED exact matching."""
    if not EXA_AVAILABLE:
        return []
    
    try:
        exa = Exa(api_key=os.getenv('EXA_API_KEY'))
        # Use search with exact phrase - ensure quotes are present
        query = f'"{phrase}"' if not (phrase.startswith('"') and phrase.endswith('"')) else phrase
        
        # ENFORCED exact phrase matching parameters
        search_params = {
            'query': query,
            'type': 'keyword',  # FORCE keyword search for exact phrase matching
            'use_autoprompt': False,  # DISABLE autoprompt for exact matching
            'num_results': kwargs.get('num_results', 10),
            'text': True,  # Always get text content
            'highlights': {
                "num_sentences": kwargs.get('highlight_sentences', 5), 
                "highlights_per_url": kwargs.get('highlights_per_url', 5)
            }
        }
        
        logger.debug(f"[EXA EXACT] Enforcing exact phrase search for: {query}")
        
        # Add domain filtering if provided
        if kwargs.get('include_domains'):
            search_params['include_domains'] = kwargs['include_domains']
        if kwargs.get('exclude_domains'):
            search_params['exclude_domains'] = kwargs['exclude_domains']
        
        # Add category filtering if supported
        if kwargs.get('category'):
            search_params['category'] = kwargs['category']
            
        # Add language preference if supported
        if kwargs.get('language'):
            search_params['language'] = kwargs['language']
        
        results = exa.search_and_contents(**search_params)
        
        # Convert to expected format
        output = []
        logger.debug(f"[EXA] Processing {len(results.results)} results")
        for i, result in enumerate(results.results):
            # Use highlights if available, otherwise use text
            snippet = ''
            if hasattr(result, 'highlights') and result.highlights:
                # Join highlights with ellipsis, ensuring they're strings
                highlights = [str(h) for h in result.highlights if h]
                snippet = ' ... '.join(highlights)
            elif hasattr(result, 'text') and result.text:
                # Use first 300 characters of text content
                snippet = str(result.text)[:300]
                # Add ellipsis if truncated
                if len(str(result.text)) > 300:
                    snippet += '...'
            
            logger.debug(f"[EXA] Result {i}: URL={result.url}, Title={result.title[:50] if result.title else 'N/A'}..., Snippet length={len(snippet)}")
            if not snippet:
                logger.warning(f"[EXA] Empty snippet for {result.url}. Has highlights: {hasattr(result, 'highlights')}, Has text: {hasattr(result, 'text')}")
                if hasattr(result, 'highlights'):
                    logger.debug(f"[EXA] Highlights type: {type(result.highlights)}, Content: {result.highlights}")
                if hasattr(result, 'text'):
                    logger.debug(f"[EXA] Text length: {len(result.text) if result.text else 0}")
            
            output.append({
                'url': result.url,
                'title': result.title,
                'snippet': snippet,
                'published_date': result.published_date if hasattr(result, 'published_date') else None,
                'author': result.author if hasattr(result, 'author') else None,
                'score': result.score if hasattr(result, 'score') else None,
                'image': result.image if hasattr(result, 'image') else None,
                'id': result.id if hasattr(result, 'id') else None
            })
        return output
    except Exception as e:
        logger.error(f"Exa exact search failed: {e}")
        return []

def exa_site(phrase: str, domains: List[str] = None, **kwargs) -> List[Dict]:
    """Site-specific exact phrase search using Exa API with ENFORCED exact matching."""
    if not EXA_AVAILABLE:
        return []
    
    try:
        exa = Exa(api_key=os.getenv('EXA_API_KEY'))
        # Use search with exact phrase - ensure quotes are present
        query = f'"{phrase}"' if not (phrase.startswith('"') and phrase.endswith('"')) else phrase
        
        # ENFORCED exact phrase matching parameters
        search_params = {
            'query': query,
            'type': 'keyword',  # FORCE keyword search for exact phrase matching
            'use_autoprompt': False,  # DISABLE autoprompt for exact matching
            'num_results': kwargs.get('num_results', 10),
            'text': True,  # Always get text content
            'highlights': {
                "num_sentences": kwargs.get('highlight_sentences', 5), 
                "highlights_per_url": kwargs.get('highlights_per_url', 5)
            }
        }
        
        logger.debug(f"[EXA SITE] Enforcing exact phrase search for: {query} on domains: {domains}")
        
        # Add domain filtering
        if domains:
            search_params['include_domains'] = domains
        if kwargs.get('exclude_domains'):
            search_params['exclude_domains'] = kwargs['exclude_domains']
        
        # Add category filtering if supported
        if kwargs.get('category'):
            search_params['category'] = kwargs['category']
            
        # Add language preference if supported
        if kwargs.get('language'):
            search_params['language'] = kwargs['language']
        
        results = exa.search_and_contents(**search_params)
        
        # Convert to expected format
        output = []
        logger.debug(f"[EXA] Processing {len(results.results)} results")
        for i, result in enumerate(results.results):
            # Use highlights if available, otherwise use text
            snippet = ''
            if hasattr(result, 'highlights') and result.highlights:
                # Join highlights with ellipsis, ensuring they're strings
                highlights = [str(h) for h in result.highlights if h]
                snippet = ' ... '.join(highlights)
            elif hasattr(result, 'text') and result.text:
                # Use first 300 characters of text content
                snippet = str(result.text)[:300]
                # Add ellipsis if truncated
                if len(str(result.text)) > 300:
                    snippet += '...'
            
            logger.debug(f"[EXA] Result {i}: URL={result.url}, Title={result.title[:50] if result.title else 'N/A'}..., Snippet length={len(snippet)}")
            if not snippet:
                logger.warning(f"[EXA] Empty snippet for {result.url}. Has highlights: {hasattr(result, 'highlights')}, Has text: {hasattr(result, 'text')}")
                if hasattr(result, 'highlights'):
                    logger.debug(f"[EXA] Highlights type: {type(result.highlights)}, Content: {result.highlights}")
                if hasattr(result, 'text'):
                    logger.debug(f"[EXA] Text length: {len(result.text) if result.text else 0}")
            
            output.append({
                'url': result.url,
                'title': result.title,
                'snippet': snippet,
                'published_date': result.published_date if hasattr(result, 'published_date') else None,
                'author': result.author if hasattr(result, 'author') else None,
                'score': result.score if hasattr(result, 'score') else None,
                'image': result.image if hasattr(result, 'image') else None,
                'id': result.id if hasattr(result, 'id') else None
            })
        return output
    except Exception as e:
        logger.error(f"Exa site search failed: {e}")
        return []

def neural_search_with_filter(search_phrase: str, filter_phrase: str, **kwargs) -> List[Dict]:
    """Neural search using Exa API."""
    if not EXA_AVAILABLE:
        return []
    
    try:
        exa = Exa(api_key=os.getenv('EXA_API_KEY'))
        # Enhanced neural search with hybrid filtering parameters
        search_params = {
            'query': search_phrase,
            'type': kwargs.get('search_type', 'auto'),  # auto intelligently combines neural + keyword
            'num_results': kwargs.get('num_results', 10),
            'text': True,  # Always get text content
            'highlights': {
                "num_sentences": kwargs.get('highlight_sentences', 5), 
                "highlights_per_url": kwargs.get('highlights_per_url', 5)
            },
            'context': kwargs.get('context', True)  # LLM-ready formatting
        }
        
        # Add neural→keyword filtering parameters from API docs
        if kwargs.get('include_text'):
            search_params['include_text'] = kwargs['include_text']  # Must contain these phrases (up to 5 words)
        if kwargs.get('exclude_text'):
            search_params['exclude_text'] = kwargs['exclude_text']  # Must NOT contain these phrases
            
        # Add user location for geographic relevance  
        if kwargs.get('user_location'):
            search_params['user_location'] = kwargs['user_location']
        
        # Add domain filtering if provided
        if kwargs.get('include_domains'):
            search_params['include_domains'] = kwargs['include_domains']
        if kwargs.get('exclude_domains'):
            search_params['exclude_domains'] = kwargs['exclude_domains']
        
        # Add category filtering if supported
        if kwargs.get('category'):
            search_params['category'] = kwargs['category']
            
        # Add language preference if supported
        if kwargs.get('language'):
            search_params['language'] = kwargs['language']
        
        results = exa.search_and_contents(**search_params)
        
        # Convert to expected format
        output = []
        logger.debug(f"[EXA] Processing {len(results.results)} results")
        for i, result in enumerate(results.results):
            # Use highlights if available, otherwise use text
            snippet = ''
            if hasattr(result, 'highlights') and result.highlights:
                # Join highlights with ellipsis, ensuring they're strings
                highlights = [str(h) for h in result.highlights if h]
                snippet = ' ... '.join(highlights)
            elif hasattr(result, 'text') and result.text:
                # Use first 300 characters of text content
                snippet = str(result.text)[:300]
                # Add ellipsis if truncated
                if len(str(result.text)) > 300:
                    snippet += '...'
            
            logger.debug(f"[EXA] Result {i}: URL={result.url}, Title={result.title[:50] if result.title else 'N/A'}..., Snippet length={len(snippet)}")
            if not snippet:
                logger.warning(f"[EXA] Empty snippet for {result.url}. Has highlights: {hasattr(result, 'highlights')}, Has text: {hasattr(result, 'text')}")
                if hasattr(result, 'highlights'):
                    logger.debug(f"[EXA] Highlights type: {type(result.highlights)}, Content: {result.highlights}")
                if hasattr(result, 'text'):
                    logger.debug(f"[EXA] Text length: {len(result.text) if result.text else 0}")
            
            output.append({
                'url': result.url,
                'title': result.title,
                'snippet': snippet,
                'published_date': result.published_date if hasattr(result, 'published_date') else None,
                'author': result.author if hasattr(result, 'author') else None,
                'score': result.score if hasattr(result, 'score') else None,
                'image': result.image if hasattr(result, 'image') else None,
                'id': result.id if hasattr(result, 'id') else None
            })
        return output
    except Exception as e:
        logger.error(f"Exa neural search failed: {e}")
        return []


def exa_hybrid_neural_keyword(phrase: str, **kwargs) -> List[Dict]:
    """
    Hybrid neural→keyword search strategy:
    1. Use type='auto' for intelligent neural + keyword combination
    2. Filter results using includeText/excludeText for precision
    3. Return LLM-ready formatted results with context
    """
    if not EXA_AVAILABLE:
        return []
    
    try:
        exa = Exa(api_key=os.getenv('EXA_API_KEY'))
        
        # Extract exact phrases from the search phrase for filtering
        import re
        quoted_phrases = re.findall(r'"([^"]*)"', phrase)
        
        search_params = {
            'query': phrase,
            'type': 'auto',  # Intelligently combines neural + keyword
            'num_results': kwargs.get('num_results', 25),
            'text': True,
            'highlights': {
                "num_sentences": kwargs.get('highlight_sentences', 3), 
                "highlights_per_url": kwargs.get('highlights_per_url', 3),
                "query": phrase  # Focus highlights on our search phrase
            }
        }
        
        # Add keyword filtering if we found quoted phrases
        if quoted_phrases and not kwargs.get('include_text'):
            search_params['include_text'] = quoted_phrases[:1]  # Use first quoted phrase as filter
            logger.debug(f"[EXA HYBRID] Auto-filtering for quoted phrases: {quoted_phrases[:1]}")
        
        # Add additional filtering parameters from kwargs
        if kwargs.get('include_text'):
            search_params['include_text'] = kwargs['include_text']
        if kwargs.get('exclude_text'):
            search_params['exclude_text'] = kwargs['exclude_text']
        if kwargs.get('category'):
            search_params['category'] = kwargs['category']
        if kwargs.get('user_location'):
            search_params['user_location'] = kwargs['user_location']
            
        # Domain filtering
        if kwargs.get('include_domains'):
            search_params['include_domains'] = kwargs['include_domains']
        if kwargs.get('exclude_domains'):
            search_params['exclude_domains'] = kwargs['exclude_domains']
            
        # Date filtering
        if kwargs.get('start_published_date'):
            search_params['start_published_date'] = kwargs['start_published_date']
        if kwargs.get('end_published_date'):
            search_params['end_published_date'] = kwargs['end_published_date']
        
        logger.debug(f"[EXA HYBRID] Neural→keyword search with auto-routing: {phrase}")
        results = exa.search_and_contents(**search_params)
        
        # Convert to expected format
        output = []
        for result in results.results:
            # Use highlights if available, otherwise use text snippet
            snippet = ''
            if hasattr(result, 'highlights') and result.highlights:
                highlights = [str(h) for h in result.highlights if h]
                snippet = ' ... '.join(highlights)
            elif hasattr(result, 'text') and result.text:
                snippet = str(result.text)[:400]
                if len(str(result.text)) > 400:
                    snippet += '...'
            
            output.append({
                'title': result.title or 'No Title',
                'url': result.url,
                'snippet': snippet,
                'source': 'exa_hybrid',
                'rank': len(output) + 1,
                'score': result.score or 0.0,
                'published_date': result.published_date,
                'author': result.author,
                'highlights': result.highlights or [],
                'context_formatted': hasattr(results, 'context') and results.context,
                'search_type': 'hybrid_neural_keyword',
                'exa_id': result.id if hasattr(result, 'id') else None
            })
        
        logger.info(f"[EXA HYBRID] Found {len(output)} results with auto neural→keyword routing")
        return output
        
    except Exception as e:
        logger.error(f"Exa hybrid neural→keyword search failed: {e}")
        return []


def exa_news_search(phrase: str, **kwargs) -> List[Dict]:
    """News search using Exa API."""
    if not EXA_AVAILABLE:
        return []
    
    try:
        exa = Exa(api_key=os.getenv('EXA_API_KEY'))
        query = f'"{phrase}"'  # Ensure exact phrase
        # CRITICAL: Use search_and_contents for news
        results = exa.search_and_contents(
            query, 
            type="keyword",  # News uses keyword search
            category="news",
            use_autoprompt=False,
            num_results=kwargs.get('num_results', 10),
            text=True,
            highlights={"num_sentences": 5, "highlights_per_url": 5}
        )
        
        # Convert to expected format
        output = []
        logger.debug(f"[EXA] Processing {len(results.results)} results")
        for i, result in enumerate(results.results):
            # Use highlights if available, otherwise use text
            snippet = ''
            if hasattr(result, 'highlights') and result.highlights:
                # Join highlights with ellipsis, ensuring they're strings
                highlights = [str(h) for h in result.highlights if h]
                snippet = ' ... '.join(highlights)
            elif hasattr(result, 'text') and result.text:
                # Use first 300 characters of text content
                snippet = str(result.text)[:300]
                # Add ellipsis if truncated
                if len(str(result.text)) > 300:
                    snippet += '...'
            
            logger.debug(f"[EXA] Result {i}: URL={result.url}, Title={result.title[:50] if result.title else 'N/A'}..., Snippet length={len(snippet)}")
            if not snippet:
                logger.warning(f"[EXA] Empty snippet for {result.url}. Has highlights: {hasattr(result, 'highlights')}, Has text: {hasattr(result, 'text')}")
                if hasattr(result, 'highlights'):
                    logger.debug(f"[EXA] Highlights type: {type(result.highlights)}, Content: {result.highlights}")
                if hasattr(result, 'text'):
                    logger.debug(f"[EXA] Text length: {len(result.text) if result.text else 0}")
            
            output.append({
                'url': result.url,
                'title': result.title,
                'snippet': snippet,
                'published_date': result.published_date if hasattr(result, 'published_date') else None,
                'author': result.author if hasattr(result, 'author') else None,
                'score': result.score if hasattr(result, 'score') else None,
                'image': result.image if hasattr(result, 'image') else None,
                'id': result.id if hasattr(result, 'id') else None
            })
        return output
    except Exception as e:
        logger.error(f"Exa news search failed: {e}")
        return []

# Helper to chunk site lists (if needed, similar to other runners)
def chunk_sites(sites: Iterable[str], max_terms: int = 10) -> Iterable[List[str]]:
    """Yield sub-lists of sites. Exa's include_domains limit is assumed to be around 10."""
    sites_list = list(sites)
    for i in range(0, len(sites_list), max_terms):
        yield sites_list[i : i + max_terms]

def slice_to_exa_date_params(slice_dict: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Enhanced conversion of time_slice dict into Exa-compatible date parameters.
    Supports both relative times and custom start/end dates.
    """
    if not slice_dict:
        return {}

    params: Dict[str, Any] = {}
    now = datetime.now()
    end_date_str = now.strftime('%Y-%m-%d')
    start_date = None

    # Support direct start/end date specification
    if 'start' in slice_dict:
        params['start_published_date'] = slice_dict['start']
        if 'end' in slice_dict:
            params['end_published_date'] = slice_dict['end']
        return params
    
    if 'end' in slice_dict:
        params['end_published_date'] = slice_dict['end']

    # Existing relative date logic
    if 'last_days' in slice_dict:
        days = slice_dict['last_days']
        start_date = now - timedelta(days=days)
        params['days_back'] = days # Specifically for exa_news_search if it prefers this
    elif 'last_weeks' in slice_dict:
        start_date = now - timedelta(weeks=slice_dict['last_weeks'])
    elif 'last_months' in slice_dict:
        # Approximate months as 30 days for timedelta
        start_date = now - timedelta(days=slice_dict['last_months'] * 30)
    elif 'last_years' in slice_dict:
        # Approximate years as 365 days
        start_date = now - timedelta(days=slice_dict['last_years'] * 365)

    if start_date:
        params['start_published_date'] = start_date.strftime('%Y-%m-%d')
        if 'end' not in slice_dict:  # Only set end if not explicitly provided
            params['end_published_date'] = end_date_str
    
    return params


def retry_on_failure(max_retries: int = 3, delay: float = 2.0):
    """Simple retry decorator for API calls with exponential backoff."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        # Exponential backoff for API calls
                        wait_time = delay * (2 ** attempt)
                        if "rate limit" in str(e).lower() or "429" in str(e):
                            wait_time *= 2  # Longer wait for rate limits
                        logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait_time:.1f}s...")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"All {max_retries + 1} attempts failed. Last error: {e}")
            raise last_exception
        return wrapper
    return decorator


class ExactPhraseRecallRunnerExa:
    """
    Orchestrates exact phrase searches across Exa's capabilities for maximum recall with streaming.
    
    By default, only performs exact phrase searches (exa_exact, exa_site) with enhanced variations.
    Set exact_only=False to include neural and news searches for broader recall.
    """

    def __init__(
        self,
        phrase: str,
        site_groups: Optional[List[List[str] | None]] = None,
        time_slices: Optional[List[Optional[Dict[str, Any]]]] = None,
        category_groups: Optional[List[Optional[str]]] = None,  # NEW: For targeted exact searches
        language_groups: Optional[List[Optional[str]]] = None,  # NEW: For language-specific exact searches
        max_results_per_query: int = 30, # Exa default might be lower, adjust based on API behavior
        polite_delay: float = 0.2, # Reduced delay - parallel execution provides natural spacing
        use_parallel: bool = True,
        max_workers: int = 20,
        exact_only: bool = True,  # Control whether to include non-exact searches
        exception_search_iterations: int = 3,  # NEW: For iterative exception search
    ):
        self.phrase = phrase.strip('\'"') # Ensure phrase is unquoted internally
        
        # Site groups: Use provided, or default to [None] (no site filter for global search type)
        self.site_groups: List[List[str] | None] = site_groups if site_groups else [None]
        if None not in self.site_groups and site_groups is not None:
             self.site_groups.insert(0, None) # Ensure a global run if specific sites are given

        # Time slices: Use provided, or default to [{}] (no time filter)
        self.time_slices: List[Optional[Dict[str, Any]]] = time_slices if time_slices is not None else [{}]
        if {} not in self.time_slices and None not in self.time_slices and time_slices is not None :
             self.time_slices.insert(0,{}) # Ensure a run without time filters

        # NEW: Category and language groups for enhanced exact search variations
        self.category_groups: List[Optional[str]] = category_groups or [None]  # e.g., ["news_article", "research_paper", "company"]
        self.language_groups: List[Optional[str]] = language_groups or [None]  # e.g., ["en", "es", "fr"]

        # Environment overrides for runtime tuning
        try:
            env_max = int(os.getenv('EXA_MAX_RESULTS_PER_QUERY', str(max_results_per_query)))
            env_delay = float(os.getenv('EXA_POLITE_DELAY', str(polite_delay)))
            env_parallel = os.getenv('EXA_USE_PARALLEL', 'true').lower() == 'true' if use_parallel is not None else use_parallel
            env_workers = int(os.getenv('EXA_MAX_WORKERS', str(max_workers)))
        except Exception:
            env_max = max_results_per_query
            env_delay = polite_delay
            env_parallel = use_parallel
            env_workers = max_workers

        self.max_results_per_query = env_max
        self.polite_delay = env_delay
        self.use_parallel = env_parallel
        self.max_workers = env_workers
        self.exact_only = exact_only  # Store exact_only setting
        self.exception_search_iterations = exception_search_iterations
        self._lock = threading.Lock()  # NEW: For thread-safe store updates
        self._store: Dict[str, Dict] = {}  # url -> result-dict

        if not os.getenv('EXA_API_KEY'):
            logger.error("EXA_API_KEY environment variable not set. Exa searches will fail.")
        
        # Initialize Exa client with proper configuration
        if EXA_AVAILABLE:
            self.exa = Exa(api_key=os.getenv('EXA_API_KEY'))
            logger.info("EXA client initialized with text/highlights enabled")
        else:
            self.exa = None

    def _add_and_get_new(self, batch: Optional[List[Dict]], effective_query_str: str) -> List[Dict]:
        """Merge batch into store (thread-safe) and return only new unique hits added."""
        if not batch:
            return []
        
        new_hits = []
        with self._lock:
            for hit in batch:
                url = hit.get("url")
                if url and isinstance(url, str) and url not in self._store:
                    # Ensure 'snippet' field exists, using highlights if necessary
                    if 'snippet' not in hit or not hit['snippet']:
                        highlights = hit.get('highlights', [])
                        if highlights:
                            hit['snippet'] = highlights[0] if isinstance(highlights[0], str) else str(highlights[0])
                        else:
                            # Try to get snippet from text content if available
                            text_content = hit.get('text', '')
                            hit['snippet'] = text_content[:300] if text_content else ""
                    
                    hit['found_by_query'] = effective_query_str
                    self._store[url] = hit
                    new_hits.append(hit)
        
        if new_hits:
            logger.debug(f"    -> Added and yielding {len(new_hits)} new unique URLs for: {effective_query_str}")
        return new_hits

    @retry_on_failure(max_retries=3, delay=1.0)
    def _execute_task(self, task_tuple: Tuple[Any, Dict[str, Any], str]) -> Tuple[List[Dict], str]:
        """Execute a single Exa task with retry logic."""
        func_or_str, params, tag = task_tuple
        try:
            if func_or_str == "neural":
                # Use hybrid neural→keyword search with intelligent filtering
                res = exa_hybrid_neural_keyword(self.phrase, **params)
            else:
                res = func_or_str(self.phrase, **params)
            return res or [], tag
        except Exception as exc:
            logger.warning(f"Exa task failed ({tag}): {exc}")
            raise  # Let retry decorator handle it

    def run(self) -> Iterable[Dict]:
        """Runs all query permutations and yields unique results as they become available."""
        search_type = "exact phrase" if self.exact_only else "comprehensive (exact + neural + news)"
        logger.info(f"Starting Exa {search_type} search for phrase: '{self.phrase}' (parallel={self.use_parallel}, streaming=True)")
        self._store.clear()

        tasks = []  # list of (callable, args, kwargs, tag)

        # Build enhanced exact phrase search tasks with category and language variations
        for sites_list in self.site_groups:
            for slice_config in self.time_slices:
                for category in self.category_groups:
                    for language in self.language_groups:
                        time_params = slice_to_exa_date_params(slice_config)
                        kw_api_params = {"max_results": self.max_results_per_query, **time_params}
                        kw_api_params.pop('days_back', None)
                        
                        # Add category filter if specified
                        if category:
                            kw_api_params["category"] = category
                        
                        # Add language filter if specified
                        if language:
                            kw_api_params["language"] = language

                        if sites_list:
                            func = exa_site
                            kw_api_params["domains"] = sites_list
                            tag = f"exa_site(exact) domains:{','.join(sites_list[:3])}{'...' if len(sites_list) > 3 else ''} cat:{category} lang:{language} {time_params}"
                        else:
                            func = exa_exact
                            tag = f"exa_exact cat:{category} lang:{language} {time_params}"

                        tasks.append((func, kw_api_params, tag))

        # Only include neural and news searches if exact_only=False
        if not self.exact_only:
            logger.info("Including neural and news searches (exact_only=False) - WARNING: May include non-exact matches")
            
            # Build neural tasks
            for slice_config in self.time_slices:
                for language in self.language_groups:
                    time_params = slice_to_exa_date_params(slice_config)
                    api_params = {"max_results": self.max_results_per_query, **time_params}
                    api_params.pop('days_back', None)
                    if language:
                        api_params["language"] = language
                    tag = f"exa_neural_filter lang:{language} {time_params} [NON-EXACT]"
                    tasks.append(("neural", api_params, tag))  # mark with string to identify

            # Build news tasks
            for slice_config in self.time_slices:
                for language in self.language_groups:
                    time_params = slice_to_exa_date_params(slice_config)
                    api_params = {"max_results": self.max_results_per_query, **time_params}
                    if language:
                        api_params["language"] = language
                    tag = f"exa_news lang:{language} {time_params} [NON-EXACT]"
                    tasks.append((exa_news_search, api_params, tag))
        else:
            logger.info("Exact phrase mode - excluding neural and news searches (exact_only=True)")

        logger.info(f"Prepared {len(tasks)} Exa query tasks for {search_type} search with enhanced variations...")

        # Execute tasks and stream results
        if self.use_parallel and len(tasks) > 1:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {executor.submit(self._execute_task, t): t for t in tasks}
                for future in as_completed(futures):
                    try:
                        batch, tag = future.result()
                        new_hits = self._add_and_get_new(batch, tag)
                        for hit in new_hits:
                            yield hit  # Stream new unique hits immediately
                    except Exception as e:
                        logger.error(f"Task execution failed: {e}")
                        continue
        else:
            for t in tasks:
                try:
                    batch, tag = self._execute_task(t)
                    new_hits = self._add_and_get_new(batch, tag)
                    for hit in new_hits:
                        yield hit
                    time.sleep(self.polite_delay)
                except Exception as e:
                    logger.error(f"Task execution failed: {e}")
                    continue

        logger.info(f"Finished main Exa {search_type} search. Found {len(self._store)} unique URLs from {len(tasks)} tasks.")
        
        # Run iterative exception search for maximum recall
        logger.info(f"Starting iterative exception search ({self.exception_search_iterations} iterations max)...")
        for iteration in range(self.exception_search_iterations):
            try:
                exception_hits = self.run_exception_search()
                new_exception_hits = self._add_and_get_new(exception_hits, f"exception_search_iter_{iteration + 1}")
                
                if new_exception_hits:
                    logger.info(f"Exception search iteration {iteration + 1}: Found {len(new_exception_hits)} new results")
                    for hit in new_exception_hits:
                        hit['search_type'] = 'exception'
                        hit['exception_iteration'] = iteration + 1
                        yield hit
                else:
                    logger.info(f"Exception search iteration {iteration + 1}: No new results, stopping")
                    break
            except Exception as e:
                logger.error(f"Exception search iteration {iteration + 1} failed: {e}")
                break

        logger.info(f"Complete Exa {search_type} search finished. Total unique URLs: {len(self._store)}")

    def run_exception_search(self) -> List[Dict]:
        """
        Performs an exception search by excluding ALL previously found domains
        to discover additional results that might have been missed.
        """
        if not self._store:
            logger.info("No previous results to exclude - skipping exception search")
            return []
        
        # Extract unique domains from all found URLs
        found_domains = set()
        for url in self._store.keys():
            try:
                domain = urlparse(url).netloc.lower()
                if domain:
                    found_domains.add(domain)
            except Exception:
                continue
        
        if not found_domains:
            logger.info("No valid domains found in previous results - skipping exception search")
            return []
        
        logger.info(f"Running Exa exception search excluding {len(found_domains)} previously found domains...")
        
        all_domains = list(found_domains)
        exception_results = []
        
        # Split into chunks to respect Exa's domain limit (~10 domains per query)
        max_domains_per_query = 10
        
        for i in range(0, len(all_domains), max_domains_per_query):
            chunk_domains = all_domains[i:i + max_domains_per_query]
            
            try:
                logger.info(f"Exception query chunk {i//max_domains_per_query + 1}: excluding {len(chunk_domains)} domains")
                
                # Use exact search with domain exclusions to maintain exact phrase enforcement
                params = {
                    "num_results": self.max_results_per_query, 
                    "exclude_domains": chunk_domains
                }
                
                hits = exa_exact(self.phrase, **params)
                
                # Filter results to ensure they're from truly different domains
                filtered_hits = []
                for hit in hits or []:
                    url = hit.get("url", "")
                    if url:
                        try:
                            hit_domain = urlparse(url).netloc.lower()
                            if hit_domain not in found_domains:
                                hit['found_by_query'] = f"exception_exclude_{len(chunk_domains)}_domains"
                                hit['search_type'] = 'exception'
                                filtered_hits.append(hit)
                        except Exception:
                            continue
                
                exception_results.extend(filtered_hits)
                
            except Exception as e:
                logger.warning(f"Exception chunk {i//max_domains_per_query + 1} failed: {e}")
                continue
        
        logger.info(f"Exception search completed: found {len(exception_results)} new results from different domains")
        return exception_results

    def run_as_list(self) -> List[Dict]:
        """Convenience method to collect all streaming results into a list."""
        return list(self.run())

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    
    # --- Configuration for Demo ---
    # Ensure EXA_API_KEY is set in your environment variables or .env file
    # load_dotenv() # If you have a .env file and python-dotenv installed

    if not os.getenv('EXA_API_KEY'):
        print("DEMO ERROR: EXA_API_KEY not found. Please set it in your environment.")
    else:
        PHRASE_TO_SEARCH = input("Enter the exact phrase to search with Exa: ").strip()
        if not PHRASE_TO_SEARCH:
            logger.error("No search phrase provided for Exa demo. Exiting.")
            exit()

        # Ask user for search mode
        print("\nSearch Mode Options:")
        print("1. Exact phrase only (exa_exact + exa_site with enhanced variations) - DEFAULT")
        print("2. Comprehensive (exact + neural + news searches) - WARNING: May include non-exact matches")
        mode_choice = input("Choose mode (1 or 2, default=1): ").strip()
        
        exact_only = True  # Default to exact phrase mode
        if mode_choice == "2":
            exact_only = False
            print("Selected: Comprehensive mode (includes neural and news searches - may include non-exact matches)")
        else:
            print("Selected: Exact phrase mode only with enhanced variations")

        logger.info(f"Starting Enhanced Exa Recall Runner demo for phrase: '{PHRASE_TO_SEARCH}' (exact_only={exact_only})")

        # Example Site Groups (Set to None for global search by default)
        demo_site_groups = None # Default to global search

        # Enhanced Time Slices with custom date support
        demo_time_slices = [
            {},  # No time filter
            {'last_days': 90},
            {'last_years': 1},
            {'start': '2024-01-01', 'end': '2024-12-31'}  # Custom date range
        ]

        # NEW: Example categories for targeted exact searches
        demo_categories = [None, "news_article", "research_paper"]  # None for all categories
        
        # NEW: Example languages for language-specific exact searches  
        demo_languages = [None, "en"]  # None for all languages, "en" for English

        runner = ExactPhraseRecallRunnerExa(
            phrase=PHRASE_TO_SEARCH,
            site_groups=demo_site_groups,
            time_slices=demo_time_slices,
            category_groups=demo_categories,  # NEW
            language_groups=demo_languages,   # NEW
            max_results_per_query=10, # Keep low for demo
            polite_delay=0.5,
            use_parallel=True,
            max_workers=20,
            exact_only=exact_only,
            exception_search_iterations=2  # Reduced for demo
        )

        logger.info("Starting streaming Exa runner...")
        results = []
        result_count = 0
        
        # Demonstrate streaming - process results as they come in
        for result in runner.run():
            result_count += 1
            results.append(result)
            # Process each result immediately
            if result_count % 5 == 0:
                print(f"Processed {result_count} results so far...")

        search_mode = "EXACT PHRASE" if exact_only else "COMPREHENSIVE"
        print(f"\n--- STREAMING EXA {search_mode} DEMO COMPLETE ---")
        print(f"Found {len(results)} unique URLs from Exa for phrase: '{PHRASE_TO_SEARCH}'")
        
        if results:
            print("\nSample of results:")
            for i, res_item in enumerate(results[:5], 1): # Print first 5
                title = res_item.get('title', '[No Title]')
                url = res_item.get('url', '[No URL]')
                snippet = res_item.get('snippet', '[No Snippet]')
                found_by = res_item.get('found_by_query', '[Unknown Query]')
                search_type = res_item.get('search_type', 'normal')
                print(f"\n{i}. Title: {title}")
                print(f"   URL: {url}")
                print(f"   Type: {search_type}")
                print(f"   Snippet: {snippet[:100]}...")
                print(f"   Found By: {found_by}")
        else:
            print("No results found in this Exa demo run.") 