"""
exact_phrase_recall_runner_bing.py  ·  v2 ("max-recall+ streaming")
====================================
Automates the "max-recall" playbook for Bing Web Search using the
scraping-based `BingSearch` class with enhanced robustness and streaming.

Changes from v1:
* **Streaming Support**: Results are yielded progressively as queries complete
* **Enhanced Base Queries**: More filetype variations using correct operators
* **Retry Logic**: Robust handling of scraping failures and rate limits  
* **Iterative Exception Search**: Excludes found domains to discover more results
* **Thread Safety**: Parallel execution with proper locking
* **Smart Delays**: Randomized delays to mimic human behavior and avoid bans
* **Fixed Operators**: Removed unsupported `inurl:`, added `inbody:`

Features:
* Builds enhanced base queries (exact phrase, multiple filetypes, intitle, inbody).
* Adds optional `site:` OR-groups (chunked).
* Adds optional language/market targeting (via `mkt` parameter).
* Sweeps through specified filetype categories and extra extensions.
* Executes with retry logic and smart delays to avoid detection.
* Streams results progressively with optional parallel execution.
* Implements iterative exception search for maximum recall.

Note on Time Slicing:
The underlying `BingSearch` (scraper) does not currently support arbitrary
date range operators. Post-filtering can be added if scraper returns dates.

Example:
-------
```python
from exact_phrase_recall_runner_bing import ExactPhraseRecallRunnerBing, chunk_sites
# Adjust import path as needed if BingSearch is elsewhere
try:
    from brute.engines.bing import BingSearch
except ImportError:
    try:
        from search_engines.bing import BingSearch
    except ImportError:
        # Fallback if running from a different structure
        print("Warning: Could not import BingSearch from brute.engines.bing or search_engines.bing. Using placeholder.")
        class BingSearch: # Placeholder
            FILETYPE_LIBRARY = {"document": ["filetype:pdf", "filetype:doc"], "spreadsheet": ["filetype:xls"]}
            MARKET_CODES = {'us': 'en-US', 'de': 'de-DE'}
            def search(*args, **kwargs): return []

try:
    from shared_session import get_shared_session
    SHARED_SESSION = True
except ImportError:
    SHARED_SESSION = False



phrase = "my exact phrase"
# Example site groups (chunked)
sites  = ["*.de","*.fr","*.it","*.uk"]
site_groups = list(chunk_sites(sites))

# Example market codes for lang_groups
lang_groups = ["en-US", "de-DE", None] # None for default market

# Example filetypes
filetype_cats = ["document"]
extra_filetypes = ["ppt", "csv"] # No filetype: prefix needed

bing_client = BingSearch() # Assumes BingSearch can be initialized without params for scraping
runner = ExactPhraseRecallRunnerBing(
    phrase=phrase,
    bing=bing_client,
    site_groups=site_groups,
    lang_groups=lang_groups,
    filetype_categories=filetype_cats,
    extra_exts=extra_filetypes,
    max_results_per_query=50,
    use_parallel=True,
    exception_search_iterations=3
)

# For streaming results:
for hit in runner.run():
    process(hit)  # Process each result as it comes in

# For batch collection:
all_hits = list(runner.run())
print(f"Found {len(all_hits)} unique URLs from Bing.")
```
"""

from __future__ import annotations
import os

import logging
import time
import random
import threading
from typing import Dict, List, Optional, Iterable, Tuple
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# Self-contained Bing Search implementation
import os
import requests
from bs4 import BeautifulSoup
import urllib.parse

logger = logging.getLogger("bing_phrase_runner")

class BingSearch:
    """Bing Web Search implementation using API or web scraping"""
    
    FILETYPE_LIBRARY = {
        "document": ["filetype:pdf", "filetype:doc", "filetype:docx"],
        "spreadsheet": ["filetype:xls", "filetype:xlsx"],
        "presentation": ["filetype:ppt", "filetype:pptx"],
        "text": ["filetype:txt", "filetype:rtf"]
    }
    
    MARKET_CODES = {
        'us': 'en-US',
        'uk': 'en-GB', 
        'de': 'de-DE',
        'fr': 'fr-FR',
        'es': 'es-ES',
        'it': 'it-IT',
        'jp': 'ja-JP',
        'cn': 'zh-CN'
    }
    
    def __init__(self, api_key: str = None):
        # SCRAPING ONLY - NO API
        self.api_key = None  # NO API
        self.api_endpoint = None  # NO API
        self.custom_config = None  # NO API

        # Proxy pool integration
        try:
            from brute.infrastructure.proxy_pool import get_proxy_config_for_engine, record_proxy_result
            self._get_proxy = get_proxy_config_for_engine
            self._record_proxy = record_proxy_result
            self._proxy_enabled = True
            logger.info("Bing: Proxy pool enabled for SERP scraping")
        except ImportError:
            self._proxy_enabled = False
            self._get_proxy = None
            self._record_proxy = None

        # Headers for web scraping - rotate User-Agent to reduce fingerprinting
        self.user_agents = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15',
        ]
        self.headers = {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'max-age=0',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"'
        }

        # Keep-alive session reuse
        self.session = requests.Session()
        self.session.headers.update(self.headers)

        # Polite jitter settings
        try:
            self.page_delay_min = float(os.getenv('BING_PAGE_DELAY_MIN', '0.3'))
            self.page_delay_max = float(os.getenv('BING_PAGE_DELAY_MAX', '0.7'))
        except Exception:
            self.page_delay_min, self.page_delay_max = 0.3, 0.7
        
    def search(self, query: str, max_results: int = 50, mkt: str = 'en-US', **kwargs) -> List[Dict]:
        """
        Perform Bing search using MULTI-BACKEND (SerpAPI + BrightData + Scraping)
        
        Args:
            query: Search query
            max_results: Maximum number of results
            mkt: Market code (e.g., 'en-US')
            
        Returns:
            List of result dictionaries
        """
        # MULTI-BACKEND: Use SerpAPI + BrightData + Scraping together for max recall
        if os.getenv('USE_MULTI_BACKEND', 'true').lower() == 'true':
            try:
                from .multi_backend_integration import multi_backend_bing
                return multi_backend_bing(query, max_results, 
                                         native_search_func=self._search_scrape,
                                         mkt=mkt)
            except ImportError as e:
                logger.debug(f"Multi-backend not available: {e}")
            except Exception as e:
                logger.warning(f"Multi-backend failed, using scrape only: {e}")
        
        # Fallback to scrape only
        return self._search_scrape(query, max_results, mkt)
    # API METHOD REMOVED - SCRAPING ONLY!
    
    def _search_scrape(self, query: str, max_results: int, mkt: str) -> List[Dict]:
        """Fallback web scraping method"""
        results = []
        
        logger.info(f"Bing scraping starting for query: '{query}' with max_results: {max_results}")
        
        # Bing shows ~10 results per page
        pages_needed = (max_results + 9) // 10
        
        for page in range(min(pages_needed, 5)):  # Limit to 5 pages
            params = {
                'q': query,
                'first': page * 10 + 1
            }
            
            try:
                url = f"https://www.bing.com/search?{urllib.parse.urlencode(params)}"
                logger.debug(f"Bing scraping URL: {url}")
                # Rotate UA periodically
                if random.random() < 0.25:
                    self.session.headers['User-Agent'] = random.choice(self.user_agents)

                # Get proxy for this request
                proxy_config = None
                proxies = None
                if self._proxy_enabled and self._get_proxy:
                    proxy_config = self._get_proxy('bing')
                    if proxy_config:
                        proxies = proxy_config.get_proxy_dict()
                        logger.debug(f"Bing using proxy: {proxy_config.name}")

                response = self.session.get(url, timeout=30, proxies=proxies)
                logger.debug(f"Bing response status: {response.status_code}")

                # Record proxy result
                if proxy_config and self._record_proxy:
                    self._record_proxy(proxy_config, response.status_code < 500)

                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Find search results
                results_on_page = soup.find_all('li', class_='b_algo')
                logger.debug(f"Found {len(results_on_page)} results on page {page+1}")
                
                for result in results_on_page:
                    link_elem = result.find('h2')
                    if link_elem and link_elem.find('a'):
                        url = link_elem.find('a').get('href', '')
                        title = link_elem.get_text(strip=True)
                        
                        # Get snippet
                        snippet_elem = result.find('div', class_='b_caption')
                        snippet = ''
                        if snippet_elem:
                            p_elem = snippet_elem.find('p')
                            if p_elem:
                                snippet = p_elem.get_text(strip=True)
                        
                        results.append({
                            'url': url,
                            'title': title,
                            'snippet': snippet,
                            'source': 'bing'
                        })
                        
                        if len(results) >= max_results:
                            return results
                
            except Exception as e:
                logger.error(f"Bing scraping failed on page {page+1}: {e}", exc_info=True)
                break
                
            # Polite jitter between pages (configurable)
            time.sleep(random.uniform(self.page_delay_min, self.page_delay_max))
        
        logger.info(f"Bing scraping completed with {len(results)} results")

        # EXACT PHRASE FILTER - Only return results containing exact phrase
        if query.startswith('"') or '"' in query:
            import re as regex_module
            phrase_match = regex_module.search(r'"([^"]+)"', query)
            if phrase_match:
                phrase = phrase_match.group(1).lower()
                words = phrase.split()
                sep = r'[\s\-_./]*'
                pattern = sep.join([regex_module.escape(w) for w in words])
                rgx = regex_module.compile(pattern, regex_module.IGNORECASE)
                filtered = [r for r in results if rgx.search((r.get('title','') or '') + ' ' + (r.get('snippet','') or '') + ' ' + (r.get('url','') or ''))]
                logger.info(f"Bing exact phrase filter: {len(filtered)}/{len(results)} passed")
                results = filtered

        return results

# --------------------------------------------------------------------------- #
# Helper Functions
# --------------------------------------------------------------------------- #

def generate_bing_base_queries(phrase: str) -> Dict[str, str]:
    """Return enhanced base queries using correct Bing operators for maximum recall."""
    clean_phrase = phrase.strip('\'"')
    quoted = f'"{clean_phrase}"'
    return {
        "B1": quoted,
        "B2_pdf": f'{quoted} filetype:pdf',
        "B2_doc": f'{quoted} filetype:doc OR filetype:docx',
        "B2_xls": f'{quoted} filetype:xls OR filetype:xlsx',
        "B2_ppt": f'{quoted} filetype:ppt OR filetype:pptx',
        "B2_txt": f'{quoted} filetype:txt OR filetype:rtf',
        "B3": f'intitle:{quoted}',
        # "B4": f'inurl:{quoted}',  # Removed: not supported since 2007
        "B5": f'inbody:{quoted}',  # Added: supported for body text searches
    }

def build_site_block(sites: List[str]) -> str:
    """
    Converts a list of site patterns into a Bing OR-grouped site query string.
    Example: ["*.de", "example.com"] -> "(site:*.de OR site:example.com)"
    """
    if not sites:
        return ""
    # Ensure each site starts with "site:" correctly
    processed_sites = []
    for s in sites:
        s_clean = s.strip()
        if not s_clean.startswith("site:"):
            processed_sites.append(f"site:{s_clean}")
        else:
            processed_sites.append(s_clean)
    return "(" + " OR ".join(processed_sites) + ")" if processed_sites else ""

def chunk_sites(sites: Iterable[str], max_terms: int = 20) -> Iterable[List[str]]:
    """
    Yields sub-lists of sites to keep OR-groups within a reasonable length
    for Bing query limits (assuming around 20-30 terms is safe).
    """
    sites_list = list(sites)
    for i in range(0, len(sites_list), max_terms):
        yield sites_list[i : i + max_terms]


def retry_on_failure(max_retries: int = 3, delay: float = 2.0):
    """Simple retry decorator for scraping calls with exponential backoff."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        # Exponential backoff with jitter for scraping
                        wait_time = delay * (2 ** attempt) + random.uniform(0, 1)
                        if "captcha" in str(e).lower() or "blocked" in str(e).lower():
                            wait_time *= 3  # Longer wait for anti-bot measures
                        logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait_time:.1f}s...")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"All {max_retries + 1} attempts failed. Last error: {e}")
            raise last_exception
        return wrapper
    return decorator


# --------------------------------------------------------------------------- #
# Enhanced Runner Class with Streaming Support
# --------------------------------------------------------------------------- #
class ExactPhraseRecallRunnerBing:
    """
    Exhaustively combines base queries, site groups, language/market settings,
    and filetype filters, then executes them using the BingSearch client
    with streaming results and maximum recall features.
    """

    def __init__(
        self,
        phrase: str,
        bing: BingSearch,
        site_groups: Optional[List[List[str]]] = None,
        lang_groups: Optional[List[Optional[str]]] = None, # Expects market codes like "en-US", None for default
        filetype_categories: Optional[List[str]] = None,
        extra_exts: Optional[List[str]] = None, # Expected in plain format like "csv", not "filetype:csv"
        max_results_per_query: int = 50, # Max results for each individual call to bing.search()
        polite_delay: float = 1.0, # Base delay between search calls
        use_parallel: bool = True,
        max_workers: int = 20, # Increased for better performance
        exception_search_iterations: int = 3,
        time_slices: Optional[List[Dict[str, str]]] = None, # For post-filtering if dates available
    ):
        self.phrase = phrase.strip('\'"') # Ensure phrase is unquoted internally
        self.bing = bing
        
        # Site groups: Use provided, or default to [None] (no site filter)
        self.site_groups: List[List[str] | None] = site_groups if site_groups else [None]
        if None not in self.site_groups and site_groups is not None : # If user provided groups but not None explicitly
             self.site_groups.insert(0, None)

        # Language groups (market codes for Bing)
        self.lang_groups: List[Optional[str]] = lang_groups if lang_groups is not None else [None]
        if None not in self.lang_groups and lang_groups is not None: # Ensure a default run
            self.lang_groups.insert(0,None)

        self.max_results_per_query = max(1, min(max_results_per_query, 200)) # Bing pages ~10, API might differ
        self.polite_delay = polite_delay
        self.use_parallel = use_parallel
        self.max_workers = max_workers
        self.exception_search_iterations = exception_search_iterations
        self.time_slices = time_slices or []
        self._lock = threading.Lock()  # For thread-safe store updates
        self._store: Dict[str, Dict] = {}  # url -> result-dict

        # Prepare the pool of filetype extensions to iterate over
        self.ext_pool: List[str] = []
        if filetype_categories and hasattr(self.bing, 'FILETYPE_LIBRARY'):
            for cat in filetype_categories:
                # Get extensions like "filetype:pdf", "filetype:doc"
                ext_operators = self.bing.FILETYPE_LIBRARY.get(cat, [])
                self.ext_pool.extend(ext_operators)
        
        if extra_exts:
            for ext in extra_exts:
                clean_ext = ext.strip()
                # Ensure filetype: prefix
                if not clean_ext.startswith("filetype:"):
                    clean_ext = f"filetype:{clean_ext}"
                if clean_ext not in self.ext_pool:
                    self.ext_pool.append(clean_ext)
        
        # Remove duplicates from ext_pool just in case
        self.ext_pool = sorted(list(set(self.ext_pool)))
        logger.info(f"Effective extension pool for sweeping: {self.ext_pool}")

    def _add_and_get_new(self, batch: List[Dict]) -> List[Dict]:
        """Merge batch into store (thread-safe) and return only new unique hits added."""
        new_hits = []
        with self._lock:
            for hit in batch:
                url = hit.get("url")
                if url and url not in self._store:
                    # Apply time filtering if configured and data available
                    if self.time_slices and not self._passes_time_filter(hit):
                        continue
                    self._store[url] = hit
                    new_hits.append(hit)
        if new_hits:
            logger.debug(f"    -> Added and yielding {len(new_hits)} new unique URLs.")
        return new_hits

    def _passes_time_filter(self, hit: Dict) -> bool:
        """Check if hit passes time slice filters (if any configured)."""
        if not self.time_slices:
            return True
        
        # Extract date from hit (adjust field name based on your scraper's output)
        hit_date = hit.get('date') or hit.get('published_date') or hit.get('timestamp')
        if not hit_date:
            return True  # No date info, include by default
        
        # Simple filtering - can be enhanced based on date format
        for time_slice in self.time_slices:
            if 'after' in time_slice and hit_date < time_slice['after']:
                return False
            if 'before' in time_slice and hit_date > time_slice['before']:
                return False
        
        return True

    @retry_on_failure(max_retries=3, delay=2.0)
    def _execute_query(self, task: Tuple[str, str, Optional[str]]) -> List[Dict]:
        """Execute a single query with retry logic and smart delays."""
        tag, query, market_code = task
        
        # Add randomized delay to mimic human behavior
        delay_variation = random.uniform(0.5, 1.5)
        time.sleep(self.polite_delay * delay_variation)
        
        try:
            logger.info(f"[{tag}] Executing Bing Query: {query[:100]}...")
            
            batch_results = self.bing.search(
                query, 
                max_results=self.max_results_per_query,
                mkt=market_code
            )
            
            if batch_results:
                # Tag the results with metadata
                for res in batch_results:
                    res["found_by_query"] = query
                    res["source_tag"] = "B"  # Bing source tag
                    res["query_tag"] = tag
                    if market_code:
                        res["market_code"] = market_code
                
                logger.debug(f"[{tag}] Found {len(batch_results)} results")
                return batch_results
            else:
                logger.debug(f"[{tag}] No results returned")
                return []
                
        except Exception as e:
            logger.warning(f"[{tag}] Query failed: {e}")
            raise  # Let retry decorator handle it

    def _iter_queries(self) -> Iterable[Tuple[str, str, Optional[str]]]:
        """
        Generates all query permutations: (tag, query_string, market_code).
        Query string includes base query, site block, and one filetype operator.
        """
        base_queries = generate_bing_base_queries(self.phrase)
        
        # Include a None option in ext_pool to run queries without a filetype filter
        current_ext_options = [None] + self.ext_pool

        query_idx = 0
        for b_tag, base_q_template in base_queries.items():
            for sites in self.site_groups:
                site_block_str = build_site_block(sites) if sites else ""
                for lang_market_code in self.lang_groups:
                    for ext_operator in current_ext_options:
                        query_idx +=1
                        current_query_parts = [base_q_template]

                        if site_block_str:
                            current_query_parts.append(site_block_str)
                        
                        # Add extension, but avoid doubling up if base query already has it
                        if ext_operator:
                            if "filetype:" not in base_q_template or ext_operator not in base_q_template:
                                current_query_parts.append(ext_operator)

                        final_query_str = " ".join(filter(None, current_query_parts))
                        # Replace multiple spaces with a single space
                        final_query_str = ' '.join(final_query_str.split())

                        tag = f"{b_tag}-S{self.site_groups.index(sites) if sites else 'N'}" \
                              f"-L{self.lang_groups.index(lang_market_code) if lang_market_code else 'N'}" \
                              f"-E{self.ext_pool.index(ext_operator) if ext_operator else 'N'}_{query_idx}"
                        
                        yield tag, final_query_str, lang_market_code
    
    def run(self) -> Iterable[Dict]:
        """Runs all query permutations and yields unique results as they become available."""
        logger.info(f"Starting Bing Exact Phrase Recall run for: '{self.phrase}' (parallel={self.use_parallel}, streaming=True)")
        self._store.clear() # Clear any existing stored results
        
        tasks = list(self._iter_queries())
        logger.info(f"Prepared {len(tasks)} Bing query permutations with enhanced filtering...")

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

        logger.info(f"Finished main Bing run. Found {len(self._store)} unique URLs from {len(tasks)} permutations.")
        
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

        logger.info(f"Complete Bing run finished. Total unique URLs: {len(self._store)}")

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
        
        logger.info(f"Running Bing exception search excluding {len(found_domains)} previously found domains...")
        
        # Base phrase for exception search
        base_query = f'"{self.phrase}"'
        
        # Build exclusion list using -site: syntax
        all_domains = sorted(list(found_domains))
        exception_results = []
        
        # Split into chunks to handle query length limits
        max_domains_per_query = 20  # Conservative for Bing scraping
        
        for i in range(0, len(all_domains), max_domains_per_query):
            chunk_domains = all_domains[i:i + max_domains_per_query]
            chunk_exclusions = [f"-site:{domain}" for domain in chunk_domains]
            chunk_query = f"{base_query} {' '.join(chunk_exclusions)}"
            
            logger.info(f"Exception query chunk {i//max_domains_per_query + 1}: excluding {len(chunk_domains)} domains")
            chunk_results = self._run_single_exception_query(chunk_query, found_domains)
            exception_results.extend(chunk_results)
        
        logger.info(f"Exception search completed: found {len(exception_results)} new results from different domains")
        return exception_results
    
    @retry_on_failure(max_retries=2, delay=3.0)  # More conservative for exception search
    def _run_single_exception_query(self, exception_query: str, excluded_domains: set) -> List[Dict]:
        """Run a single exception query and filter results."""
        try:
            logger.debug(f"Exception query: {exception_query[:150]}...")
            
            # Reduced delay for parallel execution
            time.sleep(self.polite_delay * random.uniform(0.1, 0.2))
            
            hits_from_engine = self.bing.search(
                exception_query, 
                max_results=self.max_results_per_query
            )
            
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
            logger.warning(f"Exception search query failed: {exc}")
            raise  # Let retry decorator handle it

    def run_as_list(self) -> List[Dict]:
        """Convenience method to collect all streaming results into a list."""
        return list(self.run())

# --------------------------------------------------------------------------- #
# Main (Example Usage / Demo)
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s: %(message)s")
    logger.info("Starting Bing Exact Phrase Recall Runner Interactive Demo")

    # Get phrase from user input
    raw_phrase_to_search = input("Please enter the keyword or phrase for Bing search: ")
    PHRASE_TO_SEARCH = raw_phrase_to_search.strip().strip('\'"')

    if not PHRASE_TO_SEARCH:
        logger.error("No search phrase provided. Exiting demo.")
    else:
        logger.info(f"Searching Bing for: '{PHRASE_TO_SEARCH}'")
        # Example Site Groups (can be None to search globally)
        demo_sites = ["*.gov", "*.edu"]  # Smaller set for demo
        demo_site_groups = list(chunk_sites(demo_sites, max_terms=2))

        # Example Language/Market Groups (can be None for default)
        demo_lang_groups = ["en-US", None] # Reduced for demo

        # Example Filetype Categories and Extra Extensions
        demo_filetype_cats = ["document"] # From BingSearch.FILETYPE_LIBRARY keys
        demo_extra_exts = ["csv", "json"] # Plain format, no filetype: prefix

        try:
            logger.info("Initializing BingSearch client...")
            bing_search_client = BingSearch()
        except Exception as e:
            logger.error(f"Failed to initialize BingSearch: {e}", exc_info=True)
            bing_search_client = None

        if bing_search_client:
            logger.info("Initializing ExactPhraseRecallRunnerBing...")
            bing_runner = ExactPhraseRecallRunnerBing(
                phrase=PHRASE_TO_SEARCH,
                bing=bing_search_client,
                site_groups=demo_site_groups,
                lang_groups=demo_lang_groups,
                filetype_categories=demo_filetype_cats,
                extra_exts=demo_extra_exts,
                max_results_per_query=30,
                polite_delay=0.5,
                use_parallel=True,
                max_workers=20,
                exception_search_iterations=2  # Reduced for demo
            )

            logger.info("Starting streaming Bing runner...")
            results = []
            result_count = 0
            
            # Demonstrate streaming - process results as they come in
            for result in bing_runner.run():
                result_count += 1
                results.append(result)
                # Process each result immediately
                if result_count % 5 == 0:
                    print(f"Processed {result_count} results so far...")

            print(f"\n--- STREAMING BING DEMO COMPLETE ---")
            print(f"Found {len(results)} unique Bing URLs for phrase: '{PHRASE_TO_SEARCH}'")
            
            if results:
                print("\nSample of results:")
                for i, res_item in enumerate(results[:5], 1):
                    title = res_item.get('title', '[No Title]')
                    url = res_item.get('url', '[No URL]')
                    snippet = res_item.get('snippet', '[No Snippet]')
                    search_type = res_item.get('search_type', 'normal')
                    print(f"\n{i}. Title: {title}")
                    print(f"   URL: {url}")
                    print(f"   Type: {search_type}")
                    print(f"   Snippet: {snippet[:150]}...")
            else:
                print("No results found in this demo run.")
        else:
            logger.error("BingSearch client could not be initialized. Demo cannot run.")

    logger.info("Bing Exact Phrase Recall Runner Demo Finished.") 