"""
exact_phrase_recall_runner.py

Automates the "max-recall" playbook for Google Custom Search:

 1. Builds the four base queries (Q1–Q4).
 2. Adds optional site-group partitions (≤32 OR terms each).
 3. Adds optional time-slice partitions (before:/after: operators).
 4. Executes every permutation via the GoogleSearch class you already have.
 5. Dedupes results on URL and returns a single list.

Usage::

    from exact_phrase_recall_runner import ExactPhraseRecallRunner, chunk_sites
    # Adjust import path as needed if GoogleSearch is elsewhere
    try:
        from search_engines.google import GoogleSearch 
    except ImportError:
        # Fallback if running from a different structure
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent))
        from search_engines.google import GoogleSearch 

try:
    from shared_session import get_shared_session
    SHARED_SESSION = True
except ImportError:
    SHARED_SESSION = False


    phrase = "my exact phrase"
    sites  = ["*.de","*.fr","*.it","*.uk"]
    site_groups = list(chunk_sites(sites))
    time_slices = [{"after":"2021"}, {"before":"2021"}]

    google = GoogleSearch()
    runner = ExactPhraseRecallRunner(phrase, google,
                                     site_groups=site_groups,
                                     time_slices=time_slices)
    
    # For streaming results:
    for hit in runner.run():
        process(hit)  # Process each result as it comes in
    
    # For batch collection:
    hits = list(runner.run())

"""

import logging
import time
import json
import asyncio
import time
from typing import List, Dict, Optional, Iterable, Union, Tuple
from itertools import chain
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Self-contained Google Custom Search implementation
import os
import requests
from urllib.parse import quote_plus
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize logger early since GoogleSearch uses it
logger = logging.getLogger("exact_phrase_runner")

class GoogleSearch:
    """Google Custom Search API implementation"""
    
    def __init__(self, api_key: str = None, cse_id: str = None):
        self.api_key = api_key or os.getenv('GOOGLE_API_KEY', '')
        self.cse_id = cse_id or os.getenv('GOOGLE_CSE_ID', '') or os.getenv('GOOGLE_CX', '')
        self.base_url = "https://www.googleapis.com/customsearch/v1"
        
        # Keep-alive HTTP session for faster pagination
        try:
            import requests
            self.session = requests.Session()
            self.session.headers.update({
                'Accept-Encoding': 'br, gzip, deflate',
                'User-Agent': 'SearchEngineer/1.0 (+https://localhost)'
            })
        except Exception:
            self.session = None

        # Lightweight in-process cache (feature: speed up repeated queries)
        self._cache: dict = {}
        try:
            self.cache_ttl = int(os.getenv('GOOGLE_CSE_CACHE_TTL', '300'))  # seconds
        except Exception:
            self.cache_ttl = 300

        # Configurable inter-page delay (default faster but safe)
        try:
            self.page_delay = float(os.getenv('GOOGLE_CSE_PAGE_DELAY', '0.5'))
        except Exception:
            self.page_delay = 0.5
        
        if not self.api_key or not self.cse_id:
            logger.warning("Google API key or CSE ID not configured. Search will not work.")

        # Optional Redis L2 cache
        self.redis = None
        try:
            import redis  # type: ignore
            redis_url = os.getenv('REDIS_URL') or os.getenv('CACHE_REDIS_URL')
            if redis_url:
                self.redis = redis.Redis.from_url(redis_url, decode_responses=True)
                # Probe connection
                self.redis.ping()
                logger.info("Google CSE: Redis L2 cache enabled")
        except Exception as e:
            self.redis = None
            logger.debug(f"Redis cache not available: {e}")

        # Scrape fallback breaker
        self._scrape_fail_streak = 0
        self._scrape_block_until = 0.0
    
    def google_base(self, query: str, max_results: int = 100, date_restrict: str = None, 
                    lr: str = None, gl: str = None, cr: str = None, hl: str = None, **kwargs) -> Tuple[List[Dict], Optional[int]]:
        """
        Perform Google Custom Search with advanced language and location filtering
        
        Args:
            query: Search query
            max_results: Maximum number of results to return
            date_restrict: Date restriction (e.g., 'd1' for past day, 'm1' for past month)
            lr: Language restrict - filter by document language (e.g., 'lang_en', 'lang_es', 'lang_en|lang_fr')
            gl: Geolocation - country code for location-specific results (e.g., 'us', 'uk', 'fr')
            cr: Country restrict - restrict to specific countries (e.g., 'countryUS', 'countryUK')
            hl: Interface language - language for the search interface (e.g., 'en', 'es', 'fr')
            
        Returns:
            Tuple of (results list, estimated total count)
        """
        if not self.api_key or not self.cse_id:
            logger.error("Google API credentials not configured")
            # Optional fallback to scraping if explicitly enabled
            if os.getenv('USE_GOOGLE_SCRAPE_FALLBACK', 'false').lower() == 'true':
                logger.warning("Falling back to conservative Google scraping (credentials missing)")
                return self._search_scrape(query, max_results), None
            return [], None
            
        results = []
        total_results_estimate = None
        
        # Cache key and lookup
        cache_key = (query, max_results, date_restrict)
        now_ts = time.time()
        cached = self._cache.get(cache_key)
        if cached:
            cached_time, cached_payload = cached
            if now_ts - cached_time <= self.cache_ttl:
                return cached_payload

        # Check Redis L2 cache
        if self.redis is not None:
            try:
                rkey = f"google:{hash((query, max_results, date_restrict))}"
                rdata = self.redis.get(rkey)
                if rdata:
                    payload = json.loads(rdata)
                    return (payload.get('results', []), payload.get('total', None))
            except Exception:
                pass
        
        # Google CSE returns max 10 results per request, max 100 total
        num_pages = min(10, (max_results + 9) // 10)

        # Optional async parallel pagination for speed
        if os.getenv('GOOGLE_CSE_ASYNC', 'false').lower() == 'true':
            try:
                payload = asyncio.run(self._google_base_async(query, max_results, date_restrict, num_pages, lr, gl, cr, hl))
                # Merge async payload
                page_results, total_est = payload
                results.extend(page_results)
                total_results_estimate = total_est
            except Exception as e:
                logger.warning(f"Async Google fetch failed, falling back to sync: {e}")
                # fall back to sync loop below

        if not results:
            for page in range(num_pages):
                start_index = page * 10 + 1
                params = {
                    'key': self.api_key,
                    'cx': self.cse_id,
                    'q': query,
                    'start': start_index,
                    'num': min(10, max_results - len(results))
                }
                if date_restrict:
                    params['dateRestrict'] = date_restrict
                # Add language and location parameters
                if lr:
                    params['lr'] = lr  # Language restrict (e.g., 'lang_en', 'lang_es|lang_fr')
                if gl:
                    params['gl'] = gl  # Geolocation (e.g., 'us', 'uk', 'fr')
                if cr:
                    params['cr'] = cr  # Country restrict (e.g., 'countryUS', 'countryGB')
                if hl:
                    params['hl'] = hl  # Host language for UI (e.g., 'en', 'es')
                try:
                    if self.session is not None:
                        response = self.session.get(self.base_url, params=params, timeout=30)
                    else:
                        import requests
                        response = requests.get(self.base_url, params=params, timeout=30)
                    response.raise_for_status()
                    data = response.json()
                    if page == 0 and 'searchInformation' in data:
                        total_results_estimate = int(data['searchInformation'].get('totalResults', 0))
                    if 'items' in data:
                        for item in data['items']:
                            results.append({
                                'url': item.get('link', ''),
                                'title': item.get('title', ''),
                                'snippet': item.get('snippet', ''),
                                'source': 'google'
                            })
                            if len(results) >= max_results:
                                break
                    if 'items' not in data or len(data['items']) < 10:
                        break
                    if 'error' in data:
                        raise Exception(str(data['error']))
                except Exception as e:
                    err = str(e).lower()
                    logger.error(f"Google CSE error: {e}")
                    if os.getenv('USE_GOOGLE_SCRAPE_FALLBACK', 'false').lower() == 'true' and (
                        '429' in err or 'quota' in err or 'rate' in err or 'daily' in err or 'limit' in err or 'credentials not configured' in err
                    ):
                        if time.time() < self._scrape_block_until or self._scrape_fail_streak >= 3:
                            logger.warning("Scrape fallback temporarily blocked by circuit breaker")
                        else:
                            remaining = max_results - len(results)
                            if remaining > 0:
                                logger.warning("Falling back to conservative Google scraping for remaining results")
                                scraped = self._search_scrape(query, remaining)
                                if scraped:
                                    self._scrape_fail_streak = 0
                                    results.extend(scraped)
                                else:
                                    self._scrape_fail_streak += 1
                                    if self._scrape_fail_streak >= 3:
                                        self._scrape_block_until = time.time() + 300
                    break
                if page < num_pages - 1 and self.page_delay > 0:
                    time.sleep(self.page_delay)
                
        payload = (results, total_results_estimate)
        # Store in cache
        try:
            self._cache[cache_key] = (now_ts, payload)
        except Exception:
            pass
        # Store in Redis L2
        if self.redis is not None:
            try:
                rkey = f"google:{hash((query, max_results, date_restrict))}"
                self.redis.setex(rkey, self.cache_ttl, json.dumps({'results': results, 'total': total_results_estimate}))
            except Exception:
                pass
        return payload

    async def _google_base_async(self, query: str, max_results: int, date_restrict: Optional[str], num_pages: int, 
                                  lr: Optional[str] = None, gl: Optional[str] = None, 
                                  cr: Optional[str] = None, hl: Optional[str] = None) -> Tuple[List[Dict], Optional[int]]:
        """Parallel page fetching with httpx.AsyncClient (optional)."""
        try:
            import httpx  # type: ignore
        except Exception:
            # httpx not available
            return [], None

        per_page = 10
        pages = min(num_pages, (max_results + per_page - 1) // per_page)

        async def fetch_page(client: httpx.AsyncClient, page_index: int):
            start_index = page_index * per_page + 1
            params = {
                'key': self.api_key,
                'cx': self.cse_id,
                'q': query,
                'start': start_index,
                'num': per_page
            }
            if date_restrict:
                params['dateRestrict'] = date_restrict
            # Add language and location parameters for async requests
            if lr:
                params['lr'] = lr
            if gl:
                params['gl'] = gl
            if cr:
                params['cr'] = cr
            if hl:
                params['hl'] = hl
            r = await client.get(self.base_url, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            return page_index, data

        results: List[Dict] = []
        total_results_estimate: Optional[int] = None
        async with httpx.AsyncClient(headers={'Accept-Encoding': 'br, gzip, deflate'}, http2=True) as client:
            tasks = [fetch_page(client, i) for i in range(pages)]
            for coro in asyncio.as_completed(tasks):
                try:
                    page_idx, data = await coro
                    if page_idx == 0 and 'searchInformation' in data:
                        total_results_estimate = int(data['searchInformation'].get('totalResults', 0))
                    items = data.get('items') or []
                    for item in items:
                        results.append({
                            'url': item.get('link', ''),
                            'title': item.get('title', ''),
                            'snippet': item.get('snippet', ''),
                            'source': 'google'
                        })
                        if len(results) >= max_results:
                            break
                except Exception as e:
                    # If any page fails, continue; sync path can backfill if needed
                    logger.debug(f"Async page fetch failed: {e}")
        return results[:max_results], total_results_estimate

    def _search_scrape(self, query: str, max_results: int = 10) -> List[Dict]:
        """Conservative Google scraping fallback (single-page, best-effort).
        Disabled by default; enable with USE_GOOGLE_SCRAPE_FALLBACK=true.
        """
        results: List[Dict] = []
        try:
            import requests
            from bs4 import BeautifulSoup
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
            }
            params = {
                'q': query,
                'num': min(10, max(1, max_results)),
                'hl': 'en'
            }
            sess = self.session or requests.Session()
            resp = sess.get('https://www.google.com/search', params=params, headers=headers, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            # Try modern selector first
            for a in soup.select('div.yuRUbf > a'):
                href = a.get('href')
                title_el = a.select_one('h3')
                title = title_el.get_text(strip=True) if title_el else href
                if href:
                    results.append({'url': href, 'title': title, 'snippet': ''})
                    if len(results) >= max_results:
                        break
            # Fallback selector
            if len(results) < max_results:
                for a in soup.select('a'):
                    href = a.get('href', '')
                    if href.startswith('http') and 'google.' not in href:
                        text = a.get_text(strip=True)
                        if href and text:
                            results.append({'url': href, 'title': text, 'snippet': ''})
                            if len(results) >= max_results:
                                break
        except Exception as e:
            logger.warning(f"Google scrape fallback failed: {e}")
        return results
    
    def search(self, query: str, max_results: int = 100, **kwargs) -> List[Dict]:
        """
        Simplified search method for compatibility with filetype.py
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            List of result dictionaries
        """
        results, _ = self.google_base(query, max_results)
        return results
    
    def search_language(self, query: str, language_codes: Union[str, List[str]], 
                       max_results: int = 100, geolocation: Optional[str] = None) -> List[Dict]:
        """
        Search with language filtering using Google's lr parameter
        
        Args:
            query: Search query
            language_codes: Language code(s) - can be single 'en' or list ['en', 'es']
            max_results: Maximum number of results
            geolocation: Optional country code for geographic filtering (e.g., 'us', 'uk')
            
        Returns:
            List of result dictionaries filtered by language
            
        Examples:
            search_language("python tutorial", "en")  # English only
            search_language("python tutorial", ["en", "es"])  # English or Spanish
            search_language("python tutorial", "en", geolocation="us")  # English from US
        """
        # Format language codes for lr parameter
        if isinstance(language_codes, str):
            lr_param = f"lang_{language_codes}"
        else:
            # Multiple languages: lang_en|lang_es|lang_fr
            lr_param = "|".join([f"lang_{code}" for code in language_codes])
        
        # Call google_base with language restriction
        results, _ = self.google_base(
            query=query,
            max_results=max_results,
            lr=lr_param,
            gl=geolocation  # Optional geographic location
        )
        
        # Add language metadata to results
        for result in results:
            result['language_filter'] = language_codes
            if geolocation:
                result['geolocation'] = geolocation
        
        return results
    
    def search_country(self, query: str, country_code: str, 
                      max_results: int = 100, language: Optional[str] = None) -> List[Dict]:
        """
        Search restricted to specific country using cr parameter
        
        Args:
            query: Search query  
            country_code: 2-letter country code (e.g., 'US', 'GB', 'FR')
            max_results: Maximum number of results
            language: Optional language code to combine with country filtering
            
        Returns:
            List of result dictionaries from specified country
            
        Examples:
            search_country("news", "US")  # US results only
            search_country("news", "GB", language="en")  # UK English results
        """
        # Format country code for cr parameter
        cr_param = f"country{country_code.upper()}"
        
        # Optional language restriction
        lr_param = f"lang_{language}" if language else None
        
        # Call google_base with country restriction
        results, _ = self.google_base(
            query=query,
            max_results=max_results,
            cr=cr_param,
            lr=lr_param,
            gl=country_code.lower()  # Also set geolocation
        )
        
        # Add country metadata to results
        for result in results:
            result['country_filter'] = country_code
            if language:
                result['language_filter'] = language
        
        return results

# --------------------------------------------------------------------------- #
# Helper builders
# --------------------------------------------------------------------------- #

def generate_base_queries(phrase: str) -> Dict[str, str]:
    """Return expanded base queries for maximum recall."""
    # Ensure phrase itself isn't double-quoted coming in
    clean_phrase = phrase.strip('"')
    quoted = f'"{clean_phrase}"'
    return {
        # Base Q1: Exact phrase
        "Q1": quoted,
        # Base Q2: Exact phrase + various filetypes for document recall
        "Q2_pdf": f'{quoted} filetype:pdf',
        "Q2_doc": f'{quoted} (filetype:doc OR filetype:docx)',
        "Q2_xls": f'{quoted} (filetype:xls OR filetype:xlsx)',
        "Q2_ppt": f'{quoted} (filetype:ppt OR filetype:pptx)',
        "Q2_txt": f'{quoted} (filetype:txt OR filetype:rtf)',
        # Base Q3: Allintitle exact phrase (Google handles quoting within operator)
        "Q3": f'allintitle:{quoted}',
        # Base Q4: Allinurl exact phrase (Google handles quoting within operator)
        "Q4": f'allinurl:{quoted}', 
        # Base Q5: Allintext exact phrase for body text emphasis
        "Q5": f'allintext:{quoted}',
    }


def build_site_block(sites: list[str]) -> str:
    """
    ".de"  -> "site:*.de"
    "example.com" -> "site:example.com"
    """
    clean = []
    for s in sites:
        s = s.strip()
        if not s:
            continue
        if s.startswith("*.") or s.startswith("site:"):
            # already in correct form
            clean.append(s if s.startswith("site:") else f"site:{s}")
        elif s.startswith("."):
            clean.append(f"site:*{s}")            # .de   => site:*.de
        else:
            clean.append(f"site:{s}")             # foo.com => site:foo.com
    # Return joined string WITHOUT surrounding parentheses
    return " OR ".join(clean) if clean else ""


def chunk_sites(sites: Iterable[str], max_terms: int = 30) -> Iterable[List[str]]:
    """Yield sub-lists that respect Google's 32-OR limit (30 ⇒ safe margin)."""
    sites = list(sites)
    for i in range(0, len(sites), max_terms):
        yield sites[i:i + max_terms]


# --- Enhanced dateRestrict Helper --- 
def slice_to_date_restrict(slice_: dict[str, Union[str, int]]) -> Optional[str]:
    """Map time slice to Google's dateRestrict parameter format."""
    if not slice_: # Handles empty dict case {} -> no filter
        return None
    
    # Prioritize smaller units if multiple are present (e.g., days over weeks)
    if 'last_days' in slice_:
        try: return f"d{int(slice_['last_days'])}"
        except (ValueError, TypeError): pass
    if 'last_weeks' in slice_:
        try: return f"w{int(slice_['last_weeks'])}"
        except (ValueError, TypeError): pass
    if 'last_months' in slice_:
        try: return f"m{int(slice_['last_months'])}"
        except (ValueError, TypeError): pass
    if 'last_years' in slice_:
        try: return f"y{int(slice_['last_years'])}"
        except (ValueError, TypeError): pass
    
    # Support for after/before syntax (converted to dateRestrict approximation)
    if 'after' in slice_:
        try:
            year = int(slice_['after'])
            current_year = time.localtime().tm_year
            years_back = current_year - year
            if years_back > 0:
                return f"y{years_back}"
        except (ValueError, TypeError): pass
    if 'before' in slice_:
        # before: queries are harder to map to dateRestrict, skip for now
        logger.debug(f"'before' queries not supported in dateRestrict format: {slice_}")
        return None
    
    logger.warning(f"Unknown key in time slice for dateRestrict: {slice_}. No filter applied.")
    return None            # unknown key or invalid value ⇒ no filter


def retry_on_failure(max_retries: int = 3, delay: float = 2.0):
    """Enhanced retry decorator for API calls with 429 error handling."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        # Enhanced backoff for Google 429 errors
                        error_str = str(e).lower()
                        if "429" in error_str or "too many requests" in error_str or "rate limit" in error_str:
                            # Exponential backoff for rate limiting
                            backoff_delay = delay * (3 ** attempt)  # More aggressive backoff
                            logger.warning(f"Google rate limit hit (attempt {attempt + 1}): {e}. Backing off for {backoff_delay:.1f}s...")
                            time.sleep(backoff_delay)
                        else:
                            # Standard delay for other errors
                            logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                            time.sleep(delay)
                    else:
                        logger.error(f"All {max_retries + 1} attempts failed for Google query. Last error: {e}")
            raise last_exception
        return wrapper
    return decorator


# --------------------------------------------------------------------------- #
# Enhanced Runner with Streaming Support
# --------------------------------------------------------------------------- #
class ExactPhraseRecallRunner:
    """Exhaustively combines base-query × site-block × time-slice, hits Google, and streams results."""

    def __init__(
        self,
        phrase: str,
        google: "GoogleSearch",
        site_groups: Optional[List[List[str]]] = None,
        time_slices: Optional[List[Dict[str, Union[str, None]]]] = None,
        max_results_per_query: int = 100, # Max per individual API call
        use_parallel: bool = True,
        max_workers: int = 20,  # Standard 20 workers
        exception_search_iterations: int = 3,
    ):
        self.phrase = phrase.strip('"') # Ensure phrase is unquoted internally
        self.google = google
        # If site_groups is provided (not None and not empty), it uses that list.
        # If site_groups is None or empty, it defaults to [None].
        self.site_groups: List[List[str] | None] = site_groups if site_groups else [None]
        # If time_slices is provided (not None and not empty), it uses that list.
        # If time_slices is None or empty, it defaults to [{}].
        self.time_slices: List[Dict[str, Union[str, None]]] = time_slices if time_slices else [{}]
        # Respect the user's requested max_results_per_query
        # Note: Google's actual API limit is 10 per page, but we can paginate
        self.max_results_per_query = max(1, max_results_per_query)
        self.use_parallel = use_parallel
        self.max_workers = max_workers
        self.exception_search_iterations = exception_search_iterations
        self._lock = threading.Lock()
        self._store: Dict[str, Dict] = {}  # url → result-dict

    # ............................................................. #
    def _add_and_get_new(self, batch: List[Dict]) -> List[Dict]:
        """Add batch to store and return only the new unique hits added."""
        new_hits = []
        with self._lock:
            for hit in batch:
                url = hit.get("url")
                if url and url not in self._store:
                    self._store[url] = hit
                    new_hits.append(hit)
        if new_hits:
            logger.debug(f"    -> Added and yielding {len(new_hits)} new unique URLs.")
        return new_hits

    # ............................................................. #
    @retry_on_failure(max_retries=3, delay=2.0)
    def _execute_query(self, tag_query_dr: Tuple[str, str, Optional[str]]) -> List[Dict]:
        """Execute a single query with retry logic."""
        tag, query_str, date_restrict = tag_query_dr
        try:
            # Check if google_base supports date_restrict parameter
            kwargs = {'max_results': self.max_results_per_query}
            if date_restrict:
                kwargs['date_restrict'] = date_restrict
            
            hits_from_engine, estimated_count = self.google.google_base(
                query_str,
                **kwargs
            )
            
            if estimated_count is not None and estimated_count == 0:
                logger.debug(f"[{tag}] Estimated 0 results for: {query_str} (date_restrict={date_restrict})")
                    
            augmented_hits = []
            if hits_from_engine:
                for hit in hits_from_engine:
                    hit['found_by_query'] = query_str
                    hit['query_tag'] = tag
                    if date_restrict:
                        hit['date_restrict'] = date_restrict
                    augmented_hits.append(hit)
            return augmented_hits
        except Exception as exc:
            logger.warning(f"[{tag}] Query failed: {exc} (date_restrict={date_restrict})")
            raise  # Re-raise for retry mechanism

    # ............................................................. #
    def run(self) -> Iterable[Dict]:
        """Runs all query permutations and yields unique results as they become available."""
        logger.info(f"Starting Google Exact Phrase Recall run for: '{self.phrase}' (parallel={self.use_parallel}, streaming=True)")
        bases = generate_base_queries(self.phrase)

        # Build list of all query permutations with date restrictions
        permutations: List[Tuple[str, str, Optional[str]]] = []  # (tag, query_str, date_restrict)
        for tag, base_query in bases.items():
            for sites in self.site_groups:
                site_block = build_site_block(sites) if sites else ""
                for _slice in self.time_slices:
                    parts = [base_query, site_block]
                    query_str = " ".join(filter(None, parts))
                    date_restrict = slice_to_date_restrict(_slice)
                    permutations.append((tag, query_str, date_restrict))

        logger.info(f"Prepared {len(permutations)} Google query permutations with time filtering...")

        # Execute queries and stream results
        if self.use_parallel and len(permutations) > 1:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {executor.submit(self._execute_query, p): p for p in permutations}
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
            for p in permutations:
                try:
                    batch = self._execute_query(p)
                    if batch:
                        new_hits = self._add_and_get_new(batch)
                        for hit in new_hits:
                            yield hit
                except Exception as e:
                    logger.error(f"Query execution failed: {e}")
                    continue

        logger.info(f"Finished main Google run. Found {len(self._store)} unique URLs from {len(permutations)} permutations.")
        
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

        logger.info(f"Complete Google run finished. Total unique URLs: {len(self._store)}")

    # ............................................................. #
    def run_exception_search(self) -> List[Dict]:
        """
        Performs an exception search by excluding ALL previously found domains
        to discover additional results that might have been missed.
        Returns results that should be tagged as 'G-ex' (Google Exception).
        """
        if not self._store:
            logger.info("No previous results to exclude - skipping exception search")
            return []
        
        # Extract unique domains from all found URLs
        found_domains = set()
        for url in self._store.keys():
            try:
                from urllib.parse import urlparse
                domain = urlparse(url).netloc.lower()
                if domain:
                    found_domains.add(domain)
            except Exception:
                continue
        
        if not found_domains:
            logger.info("No valid domains found in previous results - skipping exception search")
            return []
        
        logger.info(f"Running Google exception search excluding ALL {len(found_domains)} previously found domains...")
        
        # Base phrase for exception search
        base_query = f'"{self.phrase}"'
        
        # Build exclusion list - exclude ALL domains, no arbitrary limit
        all_domains = sorted(list(found_domains))
        exclusions = [f"-site:{domain}" for domain in all_domains]
        
        # Check if we can fit all exclusions in one query (Google's ~2048 char limit)
        full_exclusion_query = f"{base_query} {' '.join(exclusions)}"
        
        exception_results = []
        
        if len(full_exclusion_query) <= 2000:  # Safe margin under Google's limit
            # Single query with all exclusions
            logger.info(f"Using single exception query excluding all {len(all_domains)} domains")
            exception_results.extend(self._run_single_exception_query(full_exclusion_query, all_domains))
        else:
            # Split into multiple queries if needed
            logger.info(f"Query too long - splitting into multiple exception queries to exclude all {len(all_domains)} domains")
            
            # Calculate how many domains we can exclude per query
            avg_domain_length = sum(len(domain) for domain in all_domains) / len(all_domains)
            max_domains_per_query = int((2000 - len(base_query) - 50) / (avg_domain_length + 7))  # 7 = "-site:" + space
            max_domains_per_query = max(10, max_domains_per_query)  # At least 10 domains per query
            
            # Split domains into chunks
            for i in range(0, len(all_domains), max_domains_per_query):
                chunk_domains = all_domains[i:i + max_domains_per_query]
                chunk_exclusions = [f"-site:{domain}" for domain in chunk_domains]
                chunk_query = f"{base_query} {' '.join(chunk_exclusions)}"
                
                logger.info(f"Exception query chunk {i//max_domains_per_query + 1}: excluding {len(chunk_domains)} domains")
                chunk_results = self._run_single_exception_query(chunk_query, found_domains)
                exception_results.extend(chunk_results)
        
        logger.info(f"Exception search completed: found {len(exception_results)} new results from different domains")
        return exception_results
    
    def _run_single_exception_query(self, exception_query: str, excluded_domains: set) -> List[Dict]:
        """Run a single exception query and filter results."""
        try:
            logger.debug(f"Exception query: {exception_query[:200]}..." if len(exception_query) > 200 else exception_query)
            
            hits_from_engine, estimated_count = self.google.google_base(
                exception_query,
                max_results=self.max_results_per_query
            )
            
            if estimated_count is not None and estimated_count == 0:
                logger.debug(f"Exception search estimated 0 results")
                return []
            
            # Filter out any results that match previously found domains
            new_results = []
            if hits_from_engine:
                for hit in hits_from_engine:
                    url = hit.get("url", "")
                    if url:
                        try:
                            from urllib.parse import urlparse
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
            logger.warning(f"Exception search query failed: {exc}")
            return []

    # ............................................................. #
    def run_as_list(self) -> List[Dict]:
        """Convenience method to collect all streaming results into a list."""
        return list(self.run())


# --------------------------------------------------------------------------- #
# Quick demo
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    # Configure logging for the demo
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s: %(message)s")

    PHRASE = "gulfstream lng"  # Example phrase
    # Example site groups (chunked) - TLDs without *. prefix
    SITES = [
        # Generic TLDs 
        ".com", ".org", ".net", ".gov", ".edu", ".info", ".biz", ".ac", ".ai", ".io",
        # European ccTLDs 
        ".eu", ".al", ".ad", ".at", ".by", ".be", ".ba", ".bg", ".hr", ".cz", ".dk", 
        ".ee", ".fo", ".fi", ".fr", ".de", ".gi", ".gr", ".hu", ".is", ".ie", ".it", 
        ".lv", ".li", ".lt", ".lu", ".mk", ".mt", ".md", ".mc", ".me", ".nl", ".no", 
        ".pl", ".pt", ".ro", ".ru", ".sm", ".rs", ".sk", ".si", ".es", ".se", ".ch", 
        ".tr", ".ua", ".uk", ".va", ".cy",
        # South American ccTLDs
        ".ar", ".bo", ".br", ".cl", ".co", ".ec", ".fk", ".gf", ".gy", ".py", ".pe", 
        ".sr", ".uy", ".ve",
        # Central Asian ccTLDs
        ".kz", ".kg", ".tj", ".tm", ".uz",
        # Commonwealth ccTLDs (Selected)
        ".ag", ".bs", ".bb", ".bz", ".bw", ".bn", ".cm", ".dm", ".fj", ".gm", ".gh",
        ".gd", ".jm", ".ke", ".ki", ".ls", ".mw", ".mv", ".mu", ".mz", ".na",
        ".nr", ".pk", ".pg", ".rw", ".kn", ".lc", ".vc", ".ws", ".sc", ".sl", ".sb", ".lk",
        ".sz", ".tz", ".to", ".tt", ".tv", ".ug", ".vu", ".zm", ".zw",
        # Other potentially relevant TLDs
        ".ca", ".mx", ".au", ".jp", ".cn", ".in", ".kr", ".za", ".id", ".ir", ".sa", ".ae", ".ph", ".hk", ".tw", ".nz", ".eg", ".il"
    ]
    SITES = sorted(list(set(SITES)))
    print(f"DEBUG: Total unique TLDs defined: {len(SITES)}")
    # Chunk into smaller groups (max 5 per OR block)
    SITE_GROUPS = list(chunk_sites(SITES, max_terms=5)) 
    print(f"DEBUG: Chunked into {len(SITE_GROUPS)} site groups (max 5 TLDs each).")
    
    # Define time slices using the new format for dateRestrict
    TIME_SLICES = [
        {'last_years': 25},   # ~Roughly since ~2000 (adjust year count as needed)
        {'last_years': 15},   # ~Roughly since ~2010
        {'last_years':  4},   # ~Roughly since ~2021 (adjust as needed)
        {'last_months': 6},   # Example: Last 6 months
        {'last_days': 30},    # Example: Last 30 days
        {}                    # no date filter (important to include)
    ]
    print(f"DEBUG: Defined {len(TIME_SLICES)} time slices for dateRestrict: {TIME_SLICES}")

    logger.info("Initializing GoogleSearch...")
    try:
        g = GoogleSearch() # Assumes API keys are in .env
    except Exception as e:
         logger.error(f"Failed to initialize GoogleSearch: {e}", exc_info=True)
         exit()
         
    logger.info("Initializing ExactPhraseRecallRunner...")
    runner = ExactPhraseRecallRunner(
        phrase=PHRASE,
        google=g,
        site_groups=SITE_GROUPS, # Pass the list of site lists
        time_slices=TIME_SLICES,
        max_results_per_query=100, # Fetch up to 100 per API call
        use_parallel=True,
        max_workers=5,  # Reduced from 20 to prevent rate limiting
        exception_search_iterations=3
    )
    
    logger.info("Starting streaming runner...")
    results = []
    result_count = 0
    
    # Demonstrate streaming - process results as they come in
    for result in runner.run():
        result_count += 1
        results.append(result)
        # Process each result immediately (e.g., save to database, display, etc.)
        if result_count % 10 == 0:
            print(f"Processed {result_count} results so far...")
    
    print(f"\n--- STREAMING DEMO COMPLETE --- ")
    print(f"Found {len(results)} unique Google URLs:")
    for i, r in enumerate(results[:10], 1):  # Show first 10 results
        title = r.get('title','[No Title]')
        url = r.get('url', r.get('link', '[No URL]')) # Google often uses 'link'
        snippet = r.get('snippet', '[No Snippet]')
        search_type = r.get('search_type', 'normal')
        print(f"\n{i}. Title: {title}")
        print(f"   URL: {url}")
        print(f"   Type: {search_type}")
        print(f"   Snippet: {snippet}") 