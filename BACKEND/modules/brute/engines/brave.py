"""
exact_phrase_recall_runner_brave.py  ·  v3 ("max-recall+ streaming")
=========================================================
Changes vs. v2
--------------
* **Streaming Support**: Results are yielded progressively as queries complete
* **Enhanced Base Queries**: More filetype variations using correct `filetype:` operator
* **Retry Logic**: Robust handling of rate limits and API failures
* **Iterative Exception Search**: Excludes found domains to discover more results
* **Thread Safety**: Parallel execution with proper locking
* **Fixed Operators**: Uses official Brave operators (`filetype:` not `ext:`)
* **Enhanced Error Handling**: Better recovery from API issues

Features
========
* **Global TLD list** identical to the Google/Yandex runners – use it when
  `site_groups` is not supplied.
* **File-type sweep** now covers every extension in `BraveSearch.FILETYPE_LIBRARY`
  *per category* **and** adds a separate sweep for standalone extensions you
  pass via `extra_exts`.
* **Language OR-fan-out** (`lang_groups=[None,"en","es"]`), because Brave's
  `search_lang` param is strict.
* **Adaptive pagination**: if `hits == max_results_per_query` and the API still
  reports `has_more`, the runner re-issues the query with `offset` bumped until
  Brave says no more.
* **Progressive streaming**: Results are yielded immediately as they become available.
* **Exception search**: Discovers additional results by excluding found domains.

Example
-------
```python
from exact_phrase_recall_runner_brave import ExactPhraseRecallRunnerBrave, chunk_sites
# BraveSearch is now self-contained in this file

try:
    from shared_session import get_shared_session
    SHARED_SESSION = True
except ImportError:
    SHARED_SESSION = False


runner = ExactPhraseRecallRunnerBrave(
    phrase="my exact phrase",
    brave=BraveSearch(),
    site_groups=None,            # ← use the global TLD list automatically
    filetype_categories=["document","spreadsheet"],
    extra_exts=["csv"],          # sweep CSV individually (no ext: prefix needed)
    lang_groups=[None,"es"],     # run each permutation in EN default + ES
    use_parallel=True,           # Enable parallel execution
    exception_search_iterations=3 # Run iterative exception search
)

# For streaming results:
for hit in runner.run():
    process(hit)  # Process each result as it comes in

# For batch collection:
all_hits = list(runner.run())
print(len(all_hits), "unique Brave URLs")
```
"""

from __future__ import annotations

import logging
import time
import threading
from typing import Dict, List, Optional, Iterable, Tuple
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests # Added import

# Self-contained Brave implementation
import os
from dotenv import load_dotenv
import json
import re

# Import configuration management
try:
    from .brave_config import get_brave_config
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False

# Check for shared session availability
try:
    from shared_session import get_shared_session
    SHARED_SESSION = True
except ImportError:
    SHARED_SESSION = False

# Self-contained base class
class SearchEngine:
    def __init__(self, name: str = "default", api_key: str = None):
        self.name = name
        self.api_key = api_key
        if SHARED_SESSION:
            self.session = get_shared_session(engine_name='BRAVE')
            logger.info("Using shared connection pool")
        else:
            self.session = requests.Session()
            # Configure session for better connection handling
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=2,  # Reduced from default
                pool_maxsize=3,      # Small pool size  
                max_retries=3,
                pool_block=True
            )
            self.session.mount('https://', adapter)
            self.session.mount('http://', adapter)

load_dotenv()

class BraveSearchError(Exception):
    """Custom exception for Brave Search errors"""
    pass

class BraveSearch(SearchEngine):
    """Brave Search API implementation with comprehensive operator support and enhanced location features"""
    
    FILETYPE_LIBRARY = {
        # Document formats
        'document': [
            'ext:pdf', 'ext:doc', 'ext:docx', 'ext:txt', 
            'ext:rtf', 'ext:odt', 'ext:html'
        ],
        
        # Spreadsheet formats  
        'spreadsheet': [
            'ext:xls', 'ext:xlsx', 'ext:ods'
        ],
        
        # Presentations
        'presentation': [
            'ext:ppt', 'ext:pptx'
        ]
    }

    def __init__(self, api_key=None, location_context=None):
        self.api_key = api_key or os.getenv("BRAVE_SEARCH_API_KEY") or os.getenv("BRAVE_API_KEY")
        if not self.api_key:
            raise ValueError("Brave API key is required")
        super().__init__(api_key=self.api_key, name="brave")
        
        # Load configuration
        self.config = get_brave_config() if CONFIG_AVAILABLE else None
        
        # Enhanced rate limiting with config
        rate_config = self.config.get_rate_limiting_config() if self.config else {}
        self.rate_limit_delay = rate_config.get('base_delay', 3.0)
        self.max_concurrent_requests = rate_config.get('max_concurrent', 2)
        self.adaptive_delay = rate_config.get('base_delay', 2.0)
        self.max_delay = rate_config.get('max_delay', 15.0)
        self.enable_adaptive = rate_config.get('enable_adaptive', True)
        self.respect_retry_after = rate_config.get('respect_retry_after', True)
        
        self.request_semaphore = threading.Semaphore(self.max_concurrent_requests)
        self.base_url = "https://api.search.brave.com/res/v1"
        
        # Base headers
        self.headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip", 
            "X-Subscription-Token": self.api_key,
            "User-Agent": "Search_Engineer/1.0 (Enhanced Brave Integration)"
        }
        
        # Location context for enhanced targeting
        self.location_context = location_context or {}
        self._update_location_headers()
        
        # Search enhancement defaults from config
        search_config = self.config.get_search_config() if self.config else {}
        self.default_params = {
            "freshness": search_config.get('freshness', 'all'),
            "text_decorations": "false",
            "search_lang": search_config.get('search_lang', 'en'),
            "safesearch": search_config.get('safesearch', 'moderate'),
            "spellcheck": "true" if search_config.get('enable_spellcheck', True) else "false"
        }
        
        # Add extra snippets if enabled
        if search_config.get('enable_extra_snippets', True):
            self.default_params['extra_snippets'] = 'true'
        
        logger.info(f"Initialized Enhanced Brave Search with config: {self.config.get_performance_mode() if self.config else 'default'}")

    def _update_location_headers(self):
        """Update headers with location context for enhanced targeting"""
        if self.location_context:
            # Add precise geolocation headers
            if 'latitude' in self.location_context and 'longitude' in self.location_context:
                self.headers['X-Loc-Lat'] = str(self.location_context['latitude'])
                self.headers['X-Loc-Long'] = str(self.location_context['longitude'])
            
            # Add timezone context
            if 'timezone' in self.location_context:
                self.headers['X-Loc-Timezone'] = self.location_context['timezone']
            
            # Add location context headers
            if 'city' in self.location_context:
                self.headers['X-Loc-City'] = self.location_context['city']
            if 'state' in self.location_context:
                self.headers['X-Loc-State'] = self.location_context['state']
            if 'country' in self.location_context:
                self.headers['X-Loc-Country'] = self.location_context['country']
    
    def set_location_context(self, latitude=None, longitude=None, timezone=None, 
                           city=None, state=None, country=None):
        """Set location context for enhanced search targeting"""
        self.location_context = {}
        if latitude is not None:
            self.location_context['latitude'] = latitude
        if longitude is not None:
            self.location_context['longitude'] = longitude
        if timezone:
            self.location_context['timezone'] = timezone
        if city:
            self.location_context['city'] = city
        if state:
            self.location_context['state'] = state
        if country:
            self.location_context['country'] = country
        
        self._update_location_headers()
        logger.info(f"Updated Brave location context: {self.location_context}")

    def set_search_preferences(self, safesearch="moderate", freshness="all", 
                             search_lang="en", spellcheck=True, units="metric"):
        """Configure search preferences for enhanced results"""
        self.default_params.update({
            "safesearch": safesearch,
            "freshness": freshness,
            "search_lang": search_lang,
            "spellcheck": "true" if spellcheck else "false",
            "units": units
        })
        logger.info(f"Updated Brave search preferences: {self.default_params}")
    
    def _log_complex_query(self, query: str):
        """Log complex queries that cause 422 errors for optimization"""
        logger.warning(f"Complex query detected (422 error): {query[:200]}...")
        # Could implement query simplification logic here in the future
        if len(query) > 1000:
            logger.warning(f"Query length: {len(query)} characters - consider simplification")
        if query.count('(') > 10 or query.count('OR') > 20:
            logger.warning("Query has many operators - consider breaking into multiple queries")
    
    def _optimize_rate_limiting(self, response):
        """Optimize rate limiting based on API response headers"""
        # Check for rate limit headers
        if 'X-RateLimit-Remaining' in response.headers:
            try:
                # Handle cases where the header might contain comma-separated values like "49, 0"
                remaining_str = response.headers.get('X-RateLimit-Remaining', '0')
                # Take the first number if there's a comma
                if ',' in remaining_str:
                    remaining_str = remaining_str.split(',')[0].strip()
                remaining = int(remaining_str)
                if remaining < 10:  # Less than 10 requests remaining
                    self.adaptive_delay = max(self.adaptive_delay, 2.0)
                    logger.info(f"Low rate limit remaining ({remaining}), increasing delay to {self.adaptive_delay}s")
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not parse X-RateLimit-Remaining header: {response.headers.get('X-RateLimit-Remaining')} - {e}")
        
        # Check for server load indicators
        if 'X-Response-Time' in response.headers:
            try:
                response_time_str = response.headers.get('X-Response-Time', '0')
                # Handle potential comma-separated values
                if ',' in response_time_str:
                    response_time_str = response_time_str.split(',')[0].strip()
                response_time = float(response_time_str)
                if response_time > 2000:  # Response took > 2 seconds
                    self.adaptive_delay = min(self.adaptive_delay * 1.1, 10.0)
                    logger.debug(f"Slow API response ({response_time}ms), adjusting delay to {self.adaptive_delay:.1f}s")
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not parse X-Response-Time header: {response.headers.get('X-Response-Time')} - {e}")

    def brave_base(self, query: str, max_results: int = 100, **kwargs) -> List[Dict]:
        """Execute enhanced Brave search with all available parameters and features."""
        logger.info("\nDEBUG: Enhanced Brave Search")
        logger.info(f"Query: {query}") # Log query as received
        print(f"\nSearching Brave API with enhanced features (max {max_results} results)...")
        
        all_results = []
        page = 0
        batch_size = 20  # Brave's max per request
        max_attempts = 10  # Try up to 10 pages
        
        # Determine if the original query was quoted for filtering later
        is_exact_search = query.startswith('"') and query.endswith('"')
        search_phrase_for_filter = query.strip('"').lower() if is_exact_search else None
        
        while len(all_results) < max_results and page < max_attempts:
            try:
                # Calculate offset with maximum of 9 (Brave API limitation)
                offset = min(page * batch_size, 9)
                
                # Merge default parameters with kwargs, giving priority to kwargs
                params = {
                    "q": query,
                    "count": batch_size,
                    "offset": offset,
                    **self.default_params,  # Use enhanced defaults
                    **kwargs  # User overrides
                }
                
                # Add result enhancement features
                if not params.get('extra_snippets'):
                    params['extra_snippets'] = 'true'  # Always get extra snippets
                
                # Add summary if requested or for complex queries
                if len(query.split()) > 5 and not params.get('summary'):
                    params['summary'] = 'true'
                
                # Add result filtering if specified
                if 'result_filter' not in params and is_exact_search:
                    params['result_filter'] = 'web'  # Focus on web results for exact searches
                
                # Use semaphore to limit concurrent requests
                with self.request_semaphore:
                    # Apply adaptive delay
                    time.sleep(self.adaptive_delay)
                    
                    response = self.session.get(
                        f"{self.base_url}/web/search",
                        headers=self.headers,
                        params=params,
                        timeout=60  # Increased timeout from 30s to 60s
                    )
                
                # Enhanced rate limiting with dynamic API response handling
                if response.status_code == 429:
                    # Check for Retry-After header if config allows
                    if self.respect_retry_after and response.headers.get('Retry-After'):
                        try:
                            retry_after = float(response.headers.get('Retry-After'))
                            wait_time = retry_after + 1  # Add 1s buffer
                            print(f"Rate limit hit on page {page+1}, API suggests waiting {retry_after}s (using {wait_time}s)")
                        except (ValueError, TypeError):
                            wait_time = self.rate_limit_delay * 3
                    else:
                        # Adaptive delay - increase delay on rate limits  
                        if self.enable_adaptive:
                            self.adaptive_delay = min(self.adaptive_delay * 2.0, self.max_delay)
                            wait_time = self.adaptive_delay
                            print(f"Rate limit hit on page {page+1}, using adaptive delay of {wait_time:.1f}s")
                        else:
                            wait_time = self.rate_limit_delay * 3
                            print(f"Rate limit hit on page {page+1}, using fixed delay of {wait_time:.1f}s")
                    
                    time.sleep(wait_time)
                    continue
                elif response.status_code == 422:
                    print(f"Query too complex (422 error) on page {page+1} - query optimization needed")
                    print(f"Query was: {query[:200]}..." if len(query) > 200 else f"Query was: {query}")
                    # Try to simplify query for future requests
                    self._log_complex_query(query)
                    break
                elif response.status_code == 400:
                    print(f"Bad request (400 error) on page {page+1} - invalid parameters")
                    print(f"Query: {query[:100]}...")
                    print(f"Params: {params}")
                    break
                elif response.status_code == 403:
                    print(f"Forbidden (403 error) - API key may be invalid or quota exceeded")
                    break
                elif response.status_code == 500:
                    print(f"Server error (500) on page {page+1} - retrying with backoff")
                    time.sleep(self.adaptive_delay * 2)  # Wait longer for server errors
                    continue
                elif response.status_code != 200:
                    print(f"API error on page {page+1}: {response.status_code}")
                    print(f"Error details: {response.text[:500]}...")
                    # Check if it's a temporary error worth retrying
                    if response.status_code >= 500:
                        time.sleep(self.adaptive_delay)
                        continue
                    else:
                        break
                
                # Optimize rate limiting based on response headers
                self._optimize_rate_limiting(response)
                    
                data = response.json()
                
                if 'web' in data and 'results' in data['web']:
                    items = data['web']['results']
                    
                    if not items:
                        print(f"\nNo more results available after page {page}")
                        break
                        
                    # Filter for exact phrase matches ONLY if user provided quotes
                    matches = []
                    if is_exact_search:
                        for item in items:
                            snippet_lower = item.get("description", "").lower()
                            url_text = item.get("url", "").lower()
                            title = item.get("title", "").lower()
                            # Stricter check for exact phrase
                            if search_phrase_for_filter in snippet_lower or \
                               search_phrase_for_filter in url_text or \
                               search_phrase_for_filter in title:
                                # Get snippet from description or extra_snippets
                                snippet = item.get("description", "")
                                
                                # If no description, try extra_snippets
                                if not snippet and item.get("extra_snippets"):
                                    extra_snippets = item.get("extra_snippets", [])
                                    if extra_snippets:
                                        snippet = " ".join(extra_snippets[:2])  # Join first 2 extra snippets
                                
                                matches.append({
                                    "url": item.get("url", ""),
                                    "title": item.get("title", ""),
                                    "snippet": snippet,
                                    "source": "brave"
                                })
                                # Debug logging for BR snippets
                                if not snippet:
                                    logger.info(f"BR API returned empty snippet for URL: {item.get('url', '')[:50]}...")
                        if matches:
                            all_results.extend(matches)
                            print(f"Found {len(matches)} exact phrase matches in batch {page+1}")
                    else:
                        # If not an exact search, add all results from the batch
                        for item in items:
                            # Get snippet from description or extra_snippets
                            snippet = item.get("description", "")
                            
                            # If no description, try extra_snippets
                            if not snippet and item.get("extra_snippets"):
                                extra_snippets = item.get("extra_snippets", [])
                                if extra_snippets:
                                    snippet = " ".join(extra_snippets[:2])  # Join first 2 extra snippets
                            
                            matches.append({
                                "url": item.get("url", ""),
                                "title": item.get("title", ""),
                                "snippet": snippet,
                                "source": "brave"
                            })
                            # Debug logging for BR snippets
                            if not snippet:
                                logger.info(f"BR API returned empty snippet for URL: {item.get('url', '')[:50]}...")
                        all_results.extend(matches)
                        print(f"Found {len(matches)} keyword results in batch {page+1}")
                    
                    if len(items) < batch_size:
                        print(f"\nReached end of available results on page {page+1}")
                        break
                        
                    page += 1
                    time.sleep(self.rate_limit_delay)
                    
                else:
                    print(f"\nNo results found in response on page {page+1}")
                    break
                
            except Exception as e:
                print(f"\nError during search on page {page+1}: {str(e)}")
                break
        
        print(f"\nTotal matches found via Brave: {len(all_results)}")
        if len(all_results) < max_results:
            print("Note: Fewer results than maximum requested - this appears to be all available results")
        
        return all_results[:max_results]

    def brave_inbody(self, keywords: List[str], max_results: int = 100) -> List[Dict]:
        """Search for all terms in page body"""
        query = 'inbody:' + ' '.join(keywords)
        return self.brave_base(query, max_results)

    def brave_intitle(self, keyword: str, max_results: int = 30) -> List[Dict]:
        """Search for keyword in page titles"""
        query = f'intitle:{keyword}'
        return self.brave_base(query, max_results)

    def brave_inurl(self, keywords: List[str], max_results: int = 100) -> List[Dict]:
        """Search for keywords in URLs"""
        query = 'inurl:' + ' '.join(keywords) 
        return self.brave_base(query, max_results)

    def brave_site(self, keyword: str, domain: str, max_results: int = 100) -> List[Dict]:
        """Search within specific domain"""
        query = f'{keyword} site:{domain}'
        return self.brave_base(query, max_results)

    def brave_filetype(self, keyword: str, filetype: str, max_results: int = 100) -> List[Dict]:
        """Search for files of specific type"""
        query = f'{keyword} ext:{filetype}'
        return self.brave_base(query, max_results)

    def brave_filetype_library(self, keyword: str, filetype_category: str, max_results: int = 100, additional_query: str = None) -> List[Dict]:
        """
        Search for files of a specific category using predefined filetype operators,
        optionally combined with additional query parts.
        """
        if filetype_category not in self.FILETYPE_LIBRARY:
            raise ValueError(f"Unknown filetype category: {filetype_category}. "
                           f"Available categories: {list(self.FILETYPE_LIBRARY.keys())}")
        
        all_results = []
        for ext in self.FILETYPE_LIBRARY[filetype_category]:
            query_parts = [keyword]
            if additional_query:
                 query_parts.append(additional_query)
            query_parts.append(ext) # ext already includes 'ext:'
            query = ' '.join(filter(None, query_parts))
            
            results = self.brave_base(query, max_results=max_results)
            all_results.extend(results)
            
            if len(all_results) >= max_results:
                break
                
        return all_results[:max_results]

    def brave_exclude(self, include_terms: List[str], exclude_terms: List[str], 
                     max_results: int = 100) -> List[Dict]:
        """Search with included and excluded terms"""
        includes = ' '.join(include_terms)
        excludes = ' '.join([f"-{term}" for term in exclude_terms])
        query = f'{includes} {excludes}'
        return self.brave_base(query, max_results)

    def brave_exact_phrase(self, phrase: str, max_results: int = 100) -> List[Dict]:
        """Search for exact phrase match (This method ensures quoting)"""
        query = f'"{phrase}"'
        return self.brave_base(query, max_results)

    def brave_search_with_autoprompt(self, query: str, max_results: int = 100) -> List[Dict]:
        """
        Search with Brave's autoprompt feature enabled
        
        Args:
            query (str): Search query
            max_results (int): Maximum number of results to return
            
        Returns:
            List[Dict]: Results with autoprompt optimization
            
        Raises:
            BraveSearchError: If API request fails
        """
        return self.brave_base(query, max_results, use_autoprompt=True)

    def brave_enhanced_search(self, query: str, max_results: int = 100, 
                            safesearch="moderate", freshness="all", 
                            result_filter=None, enable_summary=False,
                            enable_spellcheck=True, goggles_id=None) -> List[Dict]:
        """
        Enhanced Brave search with all advanced features
        
        Args:
            query: Search query
            max_results: Maximum results to return
            safesearch: Content filtering ("off", "moderate", "strict")
            freshness: Time filter ("pd" for past day, "pw" for past week, "pm" for past month, "py" for past year, "all")
            result_filter: Filter by result type ("discussions", "faq", "infobox", "news", "videos", "web", "locations")
            enable_summary: Enable result summaries
            enable_spellcheck: Enable automatic spell correction
            goggles_id: Custom search re-ranking with Brave Goggles
            
        Returns:
            List of enhanced search results
        """
        enhanced_params = {
            "safesearch": safesearch,
            "freshness": freshness,
            "spellcheck": "true" if enable_spellcheck else "false",
            "extra_snippets": "true",
        }
        
        if result_filter:
            enhanced_params["result_filter"] = result_filter
        
        if enable_summary:
            enhanced_params["summary"] = "true"
            
        if goggles_id:
            enhanced_params["goggles_id"] = goggles_id
        
        return self.brave_base(query, max_results, **enhanced_params)
    
    def brave_location_search(self, query: str, country=None, latitude=None, longitude=None,
                            city=None, state=None, timezone=None, units="metric", 
                            max_results: int = 100) -> List[Dict]:
        """
        Location-aware search with enhanced geographic targeting
        
        Args:
            query: Search query
            country: ISO country code (e.g., "US", "GB", "DE")
            latitude: Latitude for precise location
            longitude: Longitude for precise location
            city: City name for location context
            state: State/province for location context
            timezone: IANA timezone identifier
            units: Unit system ("metric" or "imperial")
            max_results: Maximum results to return
            
        Returns:
            List of location-targeted search results
        """
        # Set location context if provided
        if any([latitude, longitude, city, state, country, timezone]):
            self.set_location_context(
                latitude=latitude,
                longitude=longitude,
                timezone=timezone,
                city=city,
                state=state,
                country=country
            )
        
        location_params = {
            "units": units,
            "extra_snippets": "true"
        }
        
        if country:
            location_params["country"] = country.upper()
        
        return self.brave_base(query, max_results, **location_params)
    
    def brave_fresh_search(self, query: str, time_period="pd", max_results: int = 100) -> List[Dict]:
        """
        Search for fresh/recent results within specified time period
        
        Args:
            query: Search query
            time_period: Time filter ("pd"=past day, "pw"=past week, "pm"=past month, "py"=past year)
            max_results: Maximum results to return
            
        Returns:
            List of fresh search results
        """
        return self.brave_base(query, max_results, 
                             freshness=time_period, 
                             extra_snippets="true")
    
    def brave_safe_search(self, query: str, safety_level="strict", max_results: int = 100) -> List[Dict]:
        """
        Search with enhanced content safety filtering
        
        Args:
            query: Search query
            safety_level: Safety filter ("off", "moderate", "strict")
            max_results: Maximum results to return
            
        Returns:
            List of safety-filtered search results
        """
        return self.brave_base(query, max_results, 
                             safesearch=safety_level,
                             extra_snippets="true")
    
    def brave_news_search(self, query: str, max_results: int = 100) -> List[Dict]:
        """
        Search specifically for news results
        
        Args:
            query: Search query
            max_results: Maximum results to return
            
        Returns:
            List of news search results
        """
        return self.brave_base(query, max_results,
                             result_filter="news",
                             freshness="pw",  # Default to past week for news
                             extra_snippets="true")
    
    def brave_video_search(self, query: str, max_results: int = 100) -> List[Dict]:
        """
        Search specifically for video results
        
        Args:
            query: Search query
            max_results: Maximum results to return
            
        Returns:
            List of video search results
        """
        return self.brave_base(query, max_results,
                             result_filter="videos",
                             extra_snippets="true")

    def search(self, query: str, max_results: int = 100, **kwargs) -> List[Dict]:
        """
        Implement the abstract search method from SearchEngine.
        Respects user's original quoting and uses enhanced features by default.
        """
        # Use enhanced search as the default
        return self.brave_base(query, max_results, **kwargs)
    
    def discussions_search(self, query: str, max_results: int = 100, **kwargs) -> List[Dict]:
        """
        Search for discussions and forum content using Brave's discussions filter.
        
        Args:
            query: Search query
            max_results: Maximum number of results to return
            **kwargs: Additional search parameters
            
        Returns:
            List of search results focused on discussions/forums
        """
        logger.info(f"Starting Brave discussions search for: '{query}'")
        
        # Force discussions filter
        kwargs['result_filter'] = 'discussions'
        
        # Optimize other parameters for discussion content
        if 'extra_snippets' not in kwargs:
            kwargs['extra_snippets'] = 'true'  # Get more context for discussions
        
        if 'summary' not in kwargs:
            kwargs['summary'] = 'true'  # Helpful for discussion threads
        
        # Use base search with discussions filter
        results = self.brave_base(query, max_results, **kwargs)
        
        logger.info(f"Brave discussions search found {len(results)} results")
        return results


logger = logging.getLogger("brave_phrase_runner")

# --------------------------------------------------------------------------- #
# Global TLD list (same as Google & Yandex)
# --------------------------------------------------------------------------- #
GLOBAL_TLDS = [
    # Generic
    "*.com", "*.org", "*.net", "*.gov", "*.edu", "*.info", "*.biz", "*.ac", "*.ai", "*.io",
    # Europe
    "*.eu", "*.al", "*.ad", "*.at", "*.by", "*.be", "*.ba", "*.bg", "*.hr", "*.cz", "*.dk",
    "*.ee", "*.fo", "*.fi", "*.fr", "*.de", "*.gi", "*.gr", "*.hu", "*.is", "*.ie", "*.it",
    "*.lv", "*.li", "*.lt", "*.lu", "*.mk", "*.mt", "*.md", "*.mc", "*.me", "*.nl", "*.no",
    "*.pl", "*.pt", "*.ro", "*.ru", "*.sm", "*.rs", "*.sk", "*.si", "*.es", "*.se", "*.ch",
    "*.tr", "*.ua", "*.uk", "*.va", "*.cy",
    # South America
    "*.ar", "*.bo", "*.br", "*.cl", "*.co", "*.ec", "*.gf", "*.gy", "*.py", "*.pe", "*.sr", "*.uy", "*.ve",
    # Central Asia
    "*.kz", "*.kg", "*.tj", "*.tm", "*.uz",
    # Commonwealth / misc
    "*.ag", "*.bs", "*.bb", "*.bz", "*.bw", "*.bn", "*.cm", "*.dm", "*.fj", "*.gm", "*.gh",
    "*.gd", "*.jm", "*.ke", "*.ki", "*.ls", "*.mw", "*.mv", "*.mu", "*.mz", "*.na",
    "*.nr", "*.pk", "*.pg", "*.rw", "*.kn", "*.lc", "*.vc", "*.ws", "*.sc", "*.sl", "*.sb", "*.lk",
    "*.sz", "*.tz", "*.to", "*.tt", "*.tv", "*.ug", "*.vu", "*.zm", "*.zw",
    # Other large markets
    "*.ca", "*.mx", "*.au", "*.jp", "*.cn", "*.in", "*.kr", "*.za", "*.id", "*.ir", "*.sa", "*.ae", "*.ph", "*.hk", "*.tw", "*.nz", "*.eg", "*.il"
]

# Optimized TLD list for faster searches (top 20 most common)
OPTIMIZED_TLDS = [
    "*.com", "*.org", "*.net", "*.edu", "*.gov",  # Top generic
    "*.uk", "*.de", "*.fr", "*.ca", "*.au",      # Major English/European
    "*.jp", "*.cn", "*.in", "*.ru", "*.br",      # Large markets
    "*.io", "*.ai", "*.co", "*.info", "*.biz"     # Tech/business
]

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def generate_brave_base_queries(phrase: str) -> Dict[str, str]:
    """Return enhanced base queries using official Brave operators for maximum recall."""
    # Ensure phrase is quoted for exact match search
    if not phrase.startswith('"') or not phrase.endswith('"'):
        quote_char = '"'
        clean_phrase = phrase.strip(quote_char)
        quoted = f'"{clean_phrase}"'
    else:
        quoted = phrase
        
    return {
        "B1": quoted,
        "B2_pdf": f"{quoted} filetype:pdf",  # Fixed: use filetype: not ext:
        "B2_doc": f"{quoted} filetype:doc OR filetype:docx",
        "B2_xls": f"{quoted} filetype:xls OR filetype:xlsx",
        "B2_ppt": f"{quoted} filetype:ppt OR filetype:pptx",
        "B2_txt": f"{quoted} filetype:txt OR filetype:rtf",
        "B3": f"intitle:{quoted}",
        # "B4": f"inurl:{quoted}",  # Removed: not supported by Brave
        "B5": f"inbody:{quoted}",  # Added: supported by Brave for body text
    }


def build_site_block(sites: List[str]) -> str:
    """Turn ["*.edu","*.gov"] → ``(site:*.edu OR site:*.gov)``."""
    if not sites:
        return ""
    tokens = [s if s.strip().startswith("site:") else f"site:{s.strip()}" for s in sites]
    return "(" + " OR ".join(tokens) + ")"


def chunk_sites(sites: Iterable[str], max_terms: int = 30):
    """Yield sub-lists capped at ~30 to stay under Brave operator limits."""
    sites = list(sites)
    for i in range(0, len(sites), max_terms):
        yield sites[i:i + max_terms]


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
                        # Exponential backoff for rate limits
                        wait_time = delay * (2 ** attempt)
                        if "429" in str(e) or "rate limit" in str(e).lower():
                            wait_time *= 2  # Longer wait for rate limits
                        logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait_time:.1f}s...")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"All {max_retries + 1} attempts failed. Last error: {e}")
            raise last_exception
        return wrapper
    return decorator


# --------------------------------------------------------------------------- #
# Enhanced Runner with Streaming Support
# --------------------------------------------------------------------------- #
class ExactPhraseRecallRunnerBrave:
    """Exhaustively combines base × site × lang × ext, calls Brave, streams results with maximum recall."""

    def __init__(
        self,
        phrase: str,
        brave: "BraveSearch",
        site_groups: Optional[List[List[str]]] = None,
        filetype_categories: Optional[List[str]] = None,
        extra_exts: Optional[List[str]] = None,
        lang_groups: Optional[List[Optional[str]]] = None,
        max_results_per_query: int = 200,
        polite_delay: float = 2.0,  # Increased from 0.1s to 2.0s for better rate limiting
        use_parallel: bool = True,
        max_workers: int = 3,  # Reduced from 50 to 3 - very conservative for Brave API
        exception_search_iterations: int = 3,
    ):
        self.phrase = phrase.strip("\"")
        self.brave = brave
        # Use GLOBAL_TLDS (chunked) if site_groups is None or empty list
        # Reduce chunk size even further (3) to avoid 422 errors with complex queries
        # Apply performance mode optimizations from config
        # Check if we should use optimized TLDs for better performance
        use_optimized = os.getenv('BRAVE_USE_OPTIMIZED_TLDS', 'true').lower() == 'true'
        tld_list = OPTIMIZED_TLDS if use_optimized else GLOBAL_TLDS
        
        self.site_groups: List[List[str] | None] = site_groups if site_groups else list(chunk_sites(tld_list, max_terms=3))
        if not self.site_groups: self.site_groups = [None] # Ensure loop runs if TLD list also empty
        
        # Load performance settings from config if available
        try:
            import yaml
            with open('config.yaml', 'r') as f:
                config = yaml.safe_load(f)
                perf_config = config.get('performance', {})
                
                # Check which performance mode is enabled
                if perf_config.get('turbo', {}).get('enabled', False):
                    logger.info("🚀 TURBO MODE: Minimal permutations for sub-10s execution")
                    self.site_groups = [None]  # No site variations
                    self.lang_groups = [None]  # No language variations  
                elif perf_config.get('fast', {}).get('enabled', False):
                    logger.info("⚡ FAST MODE: Reduced permutations for 10-15s execution")
                    if perf_config['fast'].get('enable_site_variations', False) == False:
                        self.site_groups = [None]  # Skip site variations
                    if perf_config['fast'].get('enable_language_variations', False) == False:
                        self.lang_groups = [None]  # Skip language variations
                else:
                    # Default optimization: use top TLDs only
                    logger.info("📊 DEFAULT MODE: Using optimized TLD list (20 domains instead of 140+)")
        except Exception as e:
            logger.debug(f"Could not load performance config: {e}")
            pass  # Continue with default settings
        self.filetype_categories = filetype_categories or []
        self.extra_exts = extra_exts or []
        # Initialize lang_groups before performance mode overrides
        if not hasattr(self, 'lang_groups'):  # Only set if not already set by performance mode
            # Default: no language variations to reduce query count
            self.lang_groups: List[Optional[str]] = lang_groups if lang_groups is not None else [None]
        self.max_results = max(1, min(max_results_per_query, 200))
        # Environment overrides to tune at runtime without code changes
        try:
            env_delay = float(os.getenv('BRAVE_POLITE_DELAY', str(polite_delay)))
            env_use_parallel = os.getenv('BRAVE_USE_PARALLEL', 'true').lower() == 'true' if use_parallel is not None else use_parallel
            env_workers = int(os.getenv('BRAVE_MAX_WORKERS', str(max_workers)))
            env_iters = int(os.getenv('BRAVE_EXCEPTION_ITERS', str(exception_search_iterations)))
        except Exception:
            env_delay = polite_delay
            env_use_parallel = use_parallel
            env_workers = max_workers
            env_iters = exception_search_iterations

        self.delay = env_delay
        self.use_parallel = env_use_parallel
        self.max_workers = env_workers
        self.exception_search_iterations = env_iters
        self._lock = threading.Lock()  # For thread-safe store updates
        self.store: Dict[str, Dict] = {}

        self.ext_pool: List[str] = []
        if self.filetype_categories:
            if hasattr(BraveSearch, "FILETYPE_LIBRARY"): 
                for cat in self.filetype_categories:
                    self.ext_pool.extend(BraveSearch.FILETYPE_LIBRARY.get(cat, []))
            else:
                 logger.warning("BraveSearch class missing FILETYPE_LIBRARY, cannot expand filetype categories.")
        
        # Add extra extensions, ensuring they use filetype: prefix
        for ext in self.extra_exts:
            if isinstance(ext, str) and ext.strip():
                 clean_ext = ext.strip()
                 if not clean_ext.startswith("filetype:"):
                      clean_ext = f"filetype:{clean_ext}"
                 if clean_ext not in self.ext_pool:
                      self.ext_pool.append(clean_ext)

    # ............................................................. #
    def _add_and_get_new(self, hits: List[Dict]) -> List[Dict]:
        """Merge batch into store (thread-safe) and return only new unique hits added."""
        new_hits = []
        with self._lock:
            for h in hits:
                url = h.get("url")
                if url and url not in self.store:
                    self.store[url] = h
                    new_hits.append(h)
        if new_hits:
            logger.debug(f"    -> Added and yielding {len(new_hits)} new unique URLs.")
        return new_hits

    # ............................................................. #
    @retry_on_failure(max_retries=3, delay=1.0)
    def _search_full(self, query: str, lang: Optional[str]) -> List[Dict]:
        """Paginate until Brave indicates no more (honouring API 200-max) with retry logic."""
        all_hits: List[Dict] = []
        offset = 0
        # Brave uses count=20 per page, offset is 0, 1, 2... up to 9 (max 10 pages)
        max_offset = 9 
        results_per_page = 20

        logger.debug(f"    Starting pagination for query: {query[:100]}... (lang={lang}) Max results={self.max_results}")

        while len(all_hits) < self.max_results and offset <= max_offset:
            current_batch_max = min(results_per_page, self.max_results - len(all_hits))
            if current_batch_max <= 0: break
            
            params = {}
            if lang:
                params["search_lang"] = lang
            
            logger.debug(f"      Fetching offset {offset} (requesting {current_batch_max} more, total collected {len(all_hits)})..." )
            try:
                # --- Direct API Call Logic (mimicking brave.py's brave_base) --- 
                api_params = {
                    "q": query, 
                    "count": results_per_page, # Always request 20 per page
                    "offset": offset,
                    "text_decorations": "false", 
                    **params # Add lang if present
                }
                
                # Need to use the requests session from the BraveSearch instance if possible
                # Or reimplement request logic here
                if hasattr(self.brave, 'session') and hasattr(self.brave, 'headers'):
                     response = self.brave.session.get(
                         f"{self.brave.base_url}/web/search",
                         headers=self.brave.headers,
                         params=api_params,
                         timeout=60  # Increased timeout from 30s to 60s from 20s to 30s
                     )
                else: # Fallback if session/headers aren't accessible
                    logger.warning("Brave instance lacks session/headers, making direct request.")
                    # Define headers dict correctly
                    request_headers = {
                        "Accept": "application/json",
                        "X-Subscription-Token": self.brave.api_key if hasattr(self.brave, 'api_key') else ""
                    }
                    # Pass the defined headers dict to the function call with rate limiting
                    if hasattr(self.brave, 'request_semaphore'):
                        with self.brave.request_semaphore:
                            time.sleep(self.brave.adaptive_delay)
                            response = requests.get(
                                "https://api.search.brave.com/res/v1/web/search",
                                headers=request_headers,
                                params=api_params,
                                timeout=60  # Increased timeout from 30s to 60s
                            )
                    else:
                        # Fallback if semaphore not available
                        time.sleep(1.0)
                        response = requests.get(
                            "https://api.search.brave.com/res/v1/web/search",
                            headers=request_headers,
                            params=api_params,
                            timeout=60  # Increased timeout from 30s to 60s
                        )

                if response.status_code == 422:
                    logger.warning(f"Query too complex (422 error) - query: {query[:100]}...")
                    return []  # Return empty results for this query
                response.raise_for_status() # Raise HTTP errors
                data = response.json()
                batch = data.get('web', {}).get('results', [])
                # --- End Direct API Call Logic --- 

                if not batch:
                    logger.debug(f"      Offset {offset}: No more results returned by API.")
                    break
                
                # Add results from this batch (but don't add to global store here - let caller handle it)
                for hit in batch:
                    url = hit.get("url")
                    if url:
                        all_hits.append(hit)
                        if len(all_hits) >= self.max_results:
                             break
                
                logger.debug(f"      Offset {offset}: Collected {len(batch)} results from API.")
                
                if len(batch) < results_per_page:
                    logger.debug(f"      Offset {offset}: API returned less than requested, assuming end of results.")
                    break  # Brave says no more for this query
                    
            except requests.exceptions.HTTPError as http_err:
                # Handle specific HTTP errors like 429 Too Many Requests
                if http_err.response.status_code == 429:
                    logger.warning(f"    Brave API rate limit hit at offset {offset}. Will retry...")
                    raise  # Let retry decorator handle it
                else:
                    logger.warning(f"    Brave API HTTP error at offset {offset}: {http_err}")
                    raise  # Let retry decorator handle it
            except Exception as e:
                logger.error(f"    Error during Brave pagination at offset {offset}: {e}")
                raise  # Let retry decorator handle it
                
            # Increment offset for next page only if successful and didn't break
            offset += 1 
            time.sleep(self.delay)
            
        logger.debug(f"    Finished pagination for query. Collected {len(all_hits)} results for this query.")
        return all_hits # Return hits collected specifically for THIS query pagination

    # ............................................................. #
    def _execute_query(self, task: Tuple[str, str, Optional[str]]) -> List[Dict]:
        """Execute a single query with full error handling."""
        tag, query, lang = task
        try:
            lang_str = f" (lang={lang})" if lang else ""
            logger.info(f"[{tag}]{lang_str} {query[:100]}...")
            
            query_hits = self._search_full(query, lang)
            
            # Add metadata to hits
            for hit in query_hits:
                hit['found_by_query'] = query
                hit['query_tag'] = tag
                if lang:
                    hit['search_lang'] = lang
                    
            return query_hits
        except Exception as exc:
            logger.warning(f"Brave query [{tag}] failed: {exc}")
            return []

    # ............................................................. #
    def _iter_queries(self) -> Iterable[Tuple[str, str, Optional[str]]]:
        """Generate all query permutations (base × site × lang × ext)."""
        base_queries = generate_brave_base_queries(self.phrase)
        
        # Add base extensions (like filetype:pdf from B2_pdf)
        base_exts = []
        for query in base_queries.values():
            if " filetype:" in query:
                # Extract filetype: part
                parts = query.split(" filetype:")
                if len(parts) > 1:
                    ext_part = parts[1].split()[0]  # Get first word after filetype:
                    base_exts.append(f"filetype:{ext_part}")
        
        effective_ext_pool = [ext for ext in self.ext_pool if ext not in base_exts]
        # Include a None option for extensions to run base queries without extra filetypes
        ext_options = [None] + effective_ext_pool 

        # Ensure site_groups contains None if it's meant to run without site filters
        site_options = self.site_groups if None in self.site_groups else [None] + self.site_groups

        # Query deduplication - track seen queries
        seen_queries = set()
        count = 0
        dedupe_count = 0
        
        for b_idx, (b_tag, base_q) in enumerate(base_queries.items()):
            for s_idx, site_group in enumerate(site_options):
                site_block = build_site_block(site_group) if site_group else ""
                for l_idx, lang in enumerate(self.lang_groups):
                    for e_idx, ext in enumerate(ext_options):
                        query_parts = [base_q]
                        if site_block: 
                            query_parts.append(site_block)
                        if ext: 
                            query_parts.append(ext)
                        
                        final_query = " ".join(query_parts)
                        
                        # Create deduplication key (query + language)
                        dedupe_key = (final_query, lang)
                        
                        if dedupe_key not in seen_queries:
                            seen_queries.add(dedupe_key)
                            count += 1
                            tag = f"{b_tag}-S{s_idx}-L{l_idx}-E{e_idx}"
                            yield tag, final_query, lang
                        else:
                            dedupe_count += 1
        
        if dedupe_count > 0:
            logger.info(f"Query deduplication: {dedupe_count} duplicate queries eliminated, {count} unique queries remain")

    # ............................................................. #
    def run(self) -> Iterable[Dict]:
        """Runs all query permutations and yields unique results as they become available."""
        logger.info(f"Starting Brave Exact Phrase Recall run for: '{self.phrase}' (parallel={self.use_parallel}, streaming=True)")
        
        tasks = list(self._iter_queries())
        logger.info(f"Prepared {len(tasks)} Brave query permutations with enhanced filtering...")

        # Execute queries and stream results
        if self.use_parallel and len(tasks) > 1:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {executor.submit(self._execute_query, t): t for t in tasks}
                for future in as_completed(futures):
                    try:
                        batch = future.result()
                        if batch:
                            new_hits = self._add_and_get_new(batch)
                            for hit in new_hits:
                                yield hit  # Stream new unique hits immediately
                    except Exception as e:
                        logger.error(f"Query execution failed: {e}")
                        continue
        else:
            for t in tasks:
                try:
                    batch = self._execute_query(t)
                    if batch:
                        new_hits = self._add_and_get_new(batch)
                        for hit in new_hits:
                            yield hit
                except Exception as e:
                    logger.error(f"Query execution failed: {e}")
                    continue

        logger.info(f"Finished main Brave run. Found {len(self.store)} unique URLs from {len(tasks)} permutations.")
        
        # Run iterative exception search for maximum recall
        logger.info(f"Starting iterative exception search ({self.exception_search_iterations} iterations max)...")
        for iteration in range(self.exception_search_iterations):
            try:
                exception_hits = self.run_exception_search()
                new_exception_hits = self._add_and_get_new(exception_hits)
                
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

        logger.info(f"Complete Brave run finished. Total unique URLs: {len(self.store)}")

    # ............................................................. #
    def run_exception_search(self) -> List[Dict]:
        """
        Performs an exception search by excluding previously found domains
        to discover additional results. Uses conservative limits to avoid 422 errors.
        """
        if not self.store:
            logger.info("No previous results to exclude - skipping exception search")
            return []
        
        # Extract unique domains from all found URLs
        found_domains = set()
        domain_counts = {}  # Track how many results per domain
        for url in self.store.keys():
            try:
                domain = urlparse(url).netloc.lower()
                if domain:
                    found_domains.add(domain)
                    domain_counts[domain] = domain_counts.get(domain, 0) + 1
            except Exception:
                continue
        
        if not found_domains:
            logger.info("No valid domains found in previous results - skipping exception search")
            return []
        
        logger.info(f"Running Brave exception search with {len(found_domains)} previously found domains...")
        
        # Base phrase for exception search
        base_query = f'"{self.phrase}"'
        
        # Limit exclusions to avoid 422 errors
        MAX_EXCLUSIONS_PER_QUERY = 15  # Conservative limit for Brave
        
        exception_results = []
        
        if len(found_domains) <= MAX_EXCLUSIONS_PER_QUERY:
            # Can exclude all domains in one query
            all_domains = sorted(list(found_domains))
            exclusions = [f"-site:{domain}" for domain in all_domains]  # Use -site: syntax (shorter)
            full_exclusion_query = f"{base_query} {' '.join(exclusions)}"
            
            logger.info(f"Using single exception query excluding all {len(all_domains)} domains")
            exception_results.extend(self._run_single_exception_query(full_exclusion_query, found_domains))
        else:
            # Too many domains - use smart strategy
            logger.info(f"Too many domains ({len(found_domains)}) - using selective exclusion strategy")
            
            # Strategy 1: Exclude top domains by result count
            top_domains = sorted(domain_counts.keys(), 
                               key=lambda d: domain_counts[d], 
                               reverse=True)[:MAX_EXCLUSIONS_PER_QUERY]
            
            top_exclusions = [f"-site:{domain}" for domain in top_domains]
            top_query = f"{base_query} {' '.join(top_exclusions)}"
            
            logger.info(f"Exception query 1: excluding top {len(top_domains)} domains by frequency")
            exception_results.extend(self._run_single_exception_query(top_query, found_domains))
            
            # Strategy 2: If needed, try excluding a different set of domains
            if len(exception_results) < 20:  # If we didn't find many new results
                # Get less common domains
                remaining_domains = [d for d in found_domains if d not in top_domains]
                if len(remaining_domains) > 0:
                    # Take a sample of remaining domains
                    sample_size = min(MAX_EXCLUSIONS_PER_QUERY, len(remaining_domains))
                    sample_domains = remaining_domains[:sample_size]
                    
                    sample_exclusions = [f"-site:{domain}" for domain in sample_domains]
                    sample_query = f"{base_query} {' '.join(sample_exclusions)}"
                    
                    logger.info(f"Exception query 2: excluding {len(sample_domains)} additional domains")
                    additional_results = self._run_single_exception_query(sample_query, found_domains)
                    exception_results.extend(additional_results)
        
        logger.info(f"Exception search completed: found {len(exception_results)} new results from different domains")
        return exception_results
    
    def _run_single_exception_query(self, exception_query: str, excluded_domains: set) -> List[Dict]:
        """Run a single exception query and filter results."""
        try:
            # Safety check for query length
            if len(exception_query) > 1500:  # Conservative limit
                logger.warning(f"Exception query too long ({len(exception_query)} chars) - risk of 422 error, skipping")
                return []
                
            logger.debug(f"Exception query: {exception_query[:200]}..." if len(exception_query) > 200 else exception_query)
            
            hits_from_engine = self._search_full(exception_query, None)  # No lang restriction for broader search
            
            # Filter out any results that match previously found domains
            new_results = []
            if hits_from_engine:
                for hit in hits_from_engine:
                    url = hit.get("url", "")
                    if url:
                        try:
                            hit_domain = urlparse(url).netloc.lower()
                            # Only include if domain wasn't in our exclusion list
                            if hit_domain not in excluded_domains:
                                hit['found_by_query'] = exception_query
                                hit['search_type'] = 'exception'  # Mark as exception result
                                new_results.append(hit)
                            else:
                                logger.debug(f"Filtered out result from excluded domain: {hit_domain}")
                        except Exception:
                            continue
            
            return new_results
            
        except Exception as exc:
            error_msg = str(exc)
            if "422" in error_msg or "Unprocessable Entity" in error_msg:
                logger.warning(f"Brave API rejected exception query (422 error) - query too complex")
            else:
                logger.warning(f"Exception search query failed: {exc}")
            return []

    # ............................................................. #
    def run_as_list(self) -> List[Dict]:
        """Convenience method to collect all streaming results into a list."""
        return list(self.run())


# --------------------------------------------------------------------------- #
# Quick test
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s: %(message)s")

    PHRASE = "gulfstream lng"  # Example phrase
    SITES = ["*.edu", "*.gov", "*.mil"] # Example site groups
    SITE_GROUPS = list(chunk_sites(SITES))
    # Example file types
    FILE_CATS = ["document", "spreadsheet"] 
    EXTRA_EXTS = ["csv", "json"]  # No filetype: prefix needed
    LANGS = [None, "es", "ru"] # Add Russian and Spanish

    logger.info("Initializing BraveSearch...")
    try:
        bs = BraveSearch() # Assumes key in .env
    except Exception as e:
        logger.error(f"Failed to initialize BraveSearch: {e}", exc_info=True)
        exit()
        
    logger.info("Initializing ExactPhraseRecallRunnerBrave (v3)...")
    runner = ExactPhraseRecallRunnerBrave(
        phrase=PHRASE,
        brave=bs,
        site_groups=SITE_GROUPS,
        filetype_categories=FILE_CATS,
        extra_exts=EXTRA_EXTS,
        lang_groups=LANGS,
        max_results_per_query=200,
        use_parallel=True,
        max_workers=3,  # Conservative setting to prevent API timeouts
        exception_search_iterations=3
    )
    
    logger.info("Starting streaming Brave runner...")
    results = []
    result_count = 0
    
    # Demonstrate streaming - process results as they come in
    for result in runner.run():
        result_count += 1
        results.append(result)
        # Process each result immediately (e.g., save to database, display, etc.)
        if result_count % 10 == 0:
            print(f"Processed {result_count} results so far...")
    
    print(f"\n--- STREAMING BRAVE DEMO COMPLETE --- ")
    print(f"Found {len(results)} unique Brave URLs:")
    for i, h in enumerate(results[:10], 1):  # Show first 10 results
        title = h.get('title', '')
        snippet = h.get('description', h.get('snippet', '[No Snippet Available]'))
        url = h.get('url', '[No URL]')
        search_type = h.get('search_type', 'normal')
        print(f"\n--- Result {i} ---")
        print(f"Title: {title}")
        print(f"URL: {url}")
        print(f"Type: {search_type}")
        print(f"Snippet: {snippet}") 