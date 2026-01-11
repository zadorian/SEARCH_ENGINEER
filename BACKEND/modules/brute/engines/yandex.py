"""
exact_phrase_recall_runner_yandex.py

Automates the "max-recall" playbook for **Yandex Web Search** (via your
`YandexSearch` class or SerpApi wrapper).

Features
========
* Builds expanded base queries (phrase, multiple filetypes, title, URL).
* Adds optional ``site:`` OR-groups (chunked to ≤30 terms to stay under the
  32-operator limit, just like Google).
* Adds optional ``date:`` slices ( >YYYYMMDD / <YYYYMMDD ) for fast binary or
  annual partitioning.
* Executes every permutation with retry logic, streams results progressively.
* Implements iterative exception search for maximum recall.
* De-dupes on URL and yields results as they become available.

Yandex operator notes (2025-04):
--------------------------------
* Exact phrase ⇒ **"..."**
* File type ⇒ **mime:pdf**, **mime:doc**, etc.
* Title search ⇒ **title:"..."**  (supported in XML API & front-end)
* URL search ⇒ **url:"..."** (enabled for maximum recall)
* Date filter ⇒ **date:>YYYYMMDD** / **date:<YYYYMMDD**
* OR    ⇒ **|** (pipe) with spaces around the symbol
* Domain exclusion ⇒ **-domain:example.com**

Example
-------
```python
from exact_phrase_recall_runner_yandex import ExactPhraseRecallRunnerYandex, chunk_sites
# YandexSearch is now self-contained in this file 

try:
    from shared_session import get_shared_session
    SHARED_SESSION = True
except ImportError:
    SHARED_SESSION = False


phrase      = "my exact phrase"
site_groups = list(chunk_sites(["*.ru", "*.de", "*.fr", "*.it"]))
time_slices = [  # binary split example
    {"after": "2021"}, # Note: Runner expects YYYY, converts to YYYY0101
    {"before": "2021"},
]

y = YandexSearch() # Assumes keys in .env
runner = ExactPhraseRecallRunnerYandex(
    phrase=phrase,
    yandex=y,
    site_groups=site_groups,
    time_slices=time_slices,
    max_results_per_query=100,
)

# For streaming results:
for hit in runner.run():
    process(hit)  # Process each result as it comes in

# For batch collection:
all_hits = list(runner.run())
print(len(all_hits), "unique URLs from Yandex")
"""

from __future__ import annotations

import logging
import time
import threading
from typing import Iterable, List, Dict, Optional, Union, Tuple
from itertools import chain
from concurrent.futures import ThreadPoolExecutor, as_completed

# Self-contained Yandex implementation
import os
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
from urllib.parse import urlparse
from dotenv import load_dotenv
from requests import exceptions, get
import requests
import traceback

# Self-contained base class
class SearchEngine:
    def __init__(self, name: str = "default", api_key: str = None):
        self.name = name
        self.api_key = api_key

load_dotenv()

class YandexSearch(SearchEngine):
    """Yandex search engine implementation with comprehensive operator support"""
    
    FILETYPE_LIBRARY = {
        # Document formats
        'document': [
            'mime:pdf', 'mime:doc', 'mime:docx', 'mime:txt', 'mime:rtf', 
            'mime:odt', 'mime:html'
        ],
        
        # Spreadsheet formats
        'spreadsheet': [
            'mime:xls', 'mime:xlsx', 'mime:ods', 'mime:csv'
        ],
        
        # Presentations
        'presentation': [
            'mime:ppt', 'mime:pptx', 'mime:odp'
        ],
        
        # PDF only
        'pdf': ['mime:pdf']
    }
    
    def __init__(self, api_key=None, folder_id=None):
        """Initialize Yandex search with API key and folder ID from environment if not provided."""
        self.api_key = api_key or os.getenv("YANDEX_API_KEY")
        if not self.api_key:
            logger.warning("No Yandex API key provided. Some functionality may be limited.")
        
        self.folderid = folder_id or os.getenv("YANDEX_FOLDER_ID") or "b1ggt7mo1kudnbu4ol9b"
        
        super().__init__(api_key=self.api_key, name="yandex")
        self.rate_limit_delay = 1.0 # Seconds between requests to avoid rate limiting
    
    def search(self, query: str, max_results: int = 30) -> List[Dict]:
        """
        Standard search method (base implementation for SearchEngine)
        
        Args:
            query (str): Search query
            max_results (int): Maximum number of results to return
            
        Returns:
            List[Dict]: Search results
        """
        return self.yandex_base(query, max_results)
    
    def yandex_base(self, query: str, max_results: int = 30) -> List[Dict]:
        """
        Base search method that handles API calls and pagination
        
        Args:
            query (str): Search query
            max_results (int): Maximum number of results to return
            
        Returns:
            List[Dict]: Search results with url, title, and snippet
        """
        print(f"\nExecuting Yandex search for: {query}")
        url = "https://yandex.com/search/xml"
        
        all_results = []
        page = 0
        results_per_page = min(30, max_results)  # Yandex limits to 30 per request
        
        while len(all_results) < max_results and page < 10:  # Limit to 10 pages max
            print(f"Fetching page {page+1} of Yandex results...")
            
            params = {
                "folderid": self.folderid,
                "apikey": self.api_key,
                "query": query,
                "l10n": "en",
                "sortby": "rlv",  # Sort by relevance
                "filter": "none",  # Disable duplicate filtering
                "maxpassages": "1",  # Limit to 1 passage per result
                "page": str(page),  # Page number (0-based)
            }

            try:
                # Add delay to avoid rate limiting
                if page > 0:
                    time.sleep(self.rate_limit_delay)
                
                response = get(url, params=params, timeout=10)
                response.raise_for_status()
                
                root = ET.fromstring(response.content)
                
                # Check for API errors
                error = root.find('.//error')
                if error is not None:
                    error_code = error.get('code', 'Unknown')
                    error_text = error.text if error.text else "API Error"
                    if error_code == '55':
                        logger.warning(f"Yandex rate limit exceeded, waiting before retry...")
                        time.sleep(2.0)  # Wait longer for rate limit
                        continue
                    else:
                        logger.error(f"Yandex API error {error_code}: {error_text}")
                        break
                
                # Extract results using the WORKING method
                results_from_page = []
                for group in root.iter('group'):
                    titles, urls, passages = (
                        group.iter('title'),
                        group.iter('url'),
                        group.iter('passage')
                    )
                    for title, url, passage in zip(titles, urls, passages):
                        results_from_page.append({
                            "title": ''.join(list(title.itertext())),
                            "url": ''.join(list(url.itertext())),
                            "snippet": ''.join(list(passage.itertext())),
                            "passage": ''.join(list(passage.itertext())),  # For compatibility
                            "source": "yandex"
                        })
                
                if not results_from_page:
                    # No more results
                    print(f"No more results found on page {page+1}.")
                    break
                
                all_results.extend(results_from_page)
                print(f"Retrieved {len(results_from_page)} results from page {page+1}")
                page += 1
                
                if len(results_from_page) < results_per_page:
                    # Last page of results
                    print("Reached the end of results according to Yandex.")
                    break
                
            except exceptions.RequestException as e:
                logger.error(f"HTTP Error during Yandex search on page {page}: {str(e)}")
                break
            except ET.ParseError as e:
                logger.error(f"XML Parsing Error during Yandex search on page {page}: {str(e)}")
                logger.error(f"Response content: {response.text[:500]}...")
                break
            except Exception as e:
                logger.error(f"Unexpected Error during Yandex search on page {page}: {str(e)}")
                traceback.print_exc()
                break
                
        print(f"Total Yandex results: {len(all_results)}")
        return all_results[:max_results]
    
    def yandex_exact_phrase(self, phrase: str, max_results: int = 30) -> List[Dict]:
        """
        Search for exact phrase match
        
        Args:
            phrase (str): Exact phrase to search for
            max_results (int): Maximum number of results to return
            
        Returns:
            List[Dict]: Results containing exact phrase
        """
        # Official Yandex documentation (2024) specifies double quotes for exact phrase
        # Older sources referenced square brackets; align to current docs.
        # If phrase already contains quotes, avoid double quoting.
        clean = phrase.strip('"')
        formatted_query = f'"{clean}"'
        return self.yandex_base(formatted_query, max_results)
    
    def yandex_title(self, keyword: str, max_results: int = 30) -> List[Dict]:
        """
        Search for keyword in page titles
        Handles exact phrases if keyword is quoted.
        """
        keyword_cleaned = keyword.strip()
        if keyword_cleaned.startswith('"') and keyword_cleaned.endswith('"'):
            # Use Yandex exact phrase syntax [ ] within title: operator
            # Note: Based on web testing, title:"phrase" also seems to work for XML API, 
            # using quotes for consistency with other engines unless issues arise.
            phrase = keyword_cleaned.strip('"')
            formatted_query = f'title:"{phrase}"'
        else:
            # Standard title search for single keyword
            formatted_query = f'title:{keyword_cleaned}'
        return self.yandex_base(formatted_query, max_results)
    
    def yandex_url(self, keyword: str, max_results: int = 30) -> List[Dict]:
        """
        Search for keyword in URLs
        
        Args:
            keyword (str): Keyword to search for in URLs
            max_results (int): Maximum number of results to return
            
        Returns:
            List[Dict]: Results with keyword in URL
        """
        formatted_query = f'inurl:{keyword}'
        return self.yandex_base(formatted_query, max_results)
    
    def yandex_site(self, domain: str, keyword: Optional[str] = None, max_results: int = 30) -> List[Dict]:
        """
        Search within a specific site
        
        Args:
            domain (str): Domain to search within
            keyword (Optional[str]): Keyword to search for (if None, returns all pages from domain)
            max_results (int): Maximum number of results to return
            
        Returns:
            List[Dict]: Results from specified site
        """
        if keyword:
            formatted_query = f'{keyword} site:{domain}'
        else:
            formatted_query = f'site:{domain}'
        return self.yandex_base(formatted_query, max_results)
    
    def yandex_filetype(self, keyword: str, filetype: str, max_results: int = 30) -> List[Dict]:
        """
        Search for specific file types
        
        Args:
            keyword (str): Keyword to search for
            filetype (str): File type to search for (pdf, doc, etc.)
            max_results (int): Maximum number of results to return
            
        Returns:
            List[Dict]: Results of specified file type
        """
        formatted_query = f'{keyword} mime:{filetype}'
        return self.yandex_base(formatted_query, max_results)
    
    def yandex_filetype_library(self, keyword: str, filetype_category: str, max_results: int = 30, additional_query: str = None) -> List[Dict]:
        """
        Search for files of a specific category using predefined filetype operators
        
        Args:
            keyword (str): Keyword to search for
            filetype_category (str): Category from FILETYPE_LIBRARY
            max_results (int): Maximum number of results to return
            additional_query (str, optional): Additional query string to include
            
        Returns:
            List[Dict]: Results of files in specified category
        """
        if filetype_category not in self.FILETYPE_LIBRARY:
            raise ValueError(f"Unknown filetype category: {filetype_category}. "
                             f"Available categories: {list(self.FILETYPE_LIBRARY.keys())}")
        
        all_results = []
        results_per_filetype = max_results // len(self.FILETYPE_LIBRARY[filetype_category])
        
        for mime_type in self.FILETYPE_LIBRARY[filetype_category]:
            # Construct query
            query_parts = [keyword]
            if additional_query:
                query_parts.append(additional_query)
            query_parts.append(mime_type)
            formatted_query = ' '.join(query_parts)
            
            # Execute search
            results = self.yandex_base(formatted_query, results_per_filetype)
            all_results.extend(results)
            
            if len(all_results) >= max_results:
                break
                
        return all_results[:max_results]
    
    def yandex_date_range(self, keyword: str, start_date: Optional[str] = None, 
                          end_date: Optional[str] = None, max_results: int = 30) -> List[Dict]:
        """
        Search for results within specific date range
        
        Args:
            keyword (str): Keyword to search for
            start_date (Optional[str]): Start date in format YYYYMMDD
            end_date (Optional[str]): End date in format YYYYMMDD
            max_results (int): Maximum number of results to return
            
        Returns:
            List[Dict]: Results within specified date range
        """
        query_parts = [keyword]
        
        if start_date:
            query_parts.append(f'date:>{start_date}')
        
        if end_date:
            query_parts.append(f'date:<{end_date}')
            
        if start_date and end_date:
            # Replace individual date constraints with range
            query_parts = [keyword, f'date:{start_date}..{end_date}']
            
        formatted_query = ' '.join(query_parts)
        return self.yandex_base(formatted_query, max_results)
    
    def yandex_language(self, keyword: str, language: str, max_results: int = 30) -> List[Dict]:
        """
        Search for results in specific language
        
        Args:
            keyword (str): Keyword to search for
            language (str): Language code (en, ru, fr, de, etc.)
            max_results (int): Maximum number of results to return
            
        Returns:
            List[Dict]: Results in specified language
        """
        formatted_query = f'{keyword} lang:{language}'
        return self.yandex_base(formatted_query, max_results)
    
    def yandex_exclude(self, keyword: str, excluded_terms: List[str], max_results: int = 30) -> List[Dict]:
        """
        Search with excluded terms
        
        Args:
            keyword (str): Keyword to search for
            excluded_terms (List[str]): Terms to exclude from results
            max_results (int): Maximum number of results to return
            
        Returns:
            List[Dict]: Results excluding specified terms
        """
        query_parts = [keyword]
        for term in excluded_terms:
            query_parts.append(f'-{term}')
            
        formatted_query = ' '.join(query_parts)
        return self.yandex_base(formatted_query, max_results)
    
    def yandex_or(self, terms: List[str], max_results: int = 30) -> List[Dict]:
        """
        Search for any of the specified terms (OR operator)
        
        Args:
            terms (List[str]): List of search terms
            max_results (int): Maximum number of results to return
            
        Returns:
            List[Dict]: Results containing any of the specified terms
        """
        formatted_query = ' | '.join(terms)
        return self.yandex_base(formatted_query, max_results)
    
    def yandex_same_sentence(self, terms: List[str], max_results: int = 30) -> List[Dict]:
        """
        Search for terms appearing in the same sentence
        
        Args:
            terms (List[str]): List of terms to find in same sentence
            max_results (int): Maximum number of results to return
            
        Returns:
            List[Dict]: Results with terms in same sentence
        """
        formatted_query = ' & '.join(terms)
        return self.yandex_base(formatted_query, max_results)
    
    def yandex_same_document(self, terms: List[str], max_results: int = 30) -> List[Dict]:
        """
        Search for terms appearing in the same document
        
        Args:
            terms (List[str]): List of terms to find in same document
            max_results (int): Maximum number of results to return
            
        Returns:
            List[Dict]: Results with terms in same document
        """
        formatted_query = ' && '.join(terms)
        return self.yandex_base(formatted_query, max_results)
    
    def yandex_indom(self, keyword: str, domains: List[str], max_results: int = 30) -> List[Dict]:
        """
        Search for keyword within specific domains
        
        Args:
            keyword (str): Keyword to search for
            domains (List[str]): List of domains to search within
            max_results (int): Maximum number of results to return
            
        Returns:
            List[Dict]: Results from specified domains
        """
        all_results = []
        results_per_domain = max_results // len(domains)
        
        for domain in domains:
            formatted_query = f'{keyword} site:{domain}'
            results = self.yandex_base(formatted_query, results_per_domain)
            all_results.extend(results)
            
            if len(all_results) >= max_results:
                break
                
        return all_results[:max_results]
    
    def search_pdf_documents(self, query: str, max_results: int = 30) -> List[Dict]:
        """
        Search for PDF documents related to the query
        
        Args:
            query (str): Search query
            max_results (int): Maximum number of results to return
            
        Returns:
            List[Dict]: PDF document results
        """
        return self.yandex_filetype(query, "pdf", max_results)


logger = logging.getLogger("yandex_phrase_runner") # Corrected logger name

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def generate_yandex_base_queries(phrase: str) -> Dict[str, str]:
    """Return expanded base queries for maximum recall using Yandex operators."""
    clean_phrase = phrase.strip('"')  # Ensure no outer quotes
    quoted = f'"{clean_phrase}"'

    queries = {
        "Y1_exact": quoted,
        "Y2_pdf": f"{quoted} mime:pdf",
        "Y2_doc": f"{quoted} (mime:doc | mime:docx)",
        "Y2_xls": f"{quoted} (mime:xls | mime:xlsx)",
        "Y2_ppt": f"{quoted} (mime:ppt | mime:pptx)",
        "Y2_txt": f"{quoted} (mime:txt | mime:rtf)",
        "Y3_title": f"title:{quoted}",
        "Y4_url": f"url:{quoted}",  # Enabled for maximum recall
    }
    return queries


def build_site_block(tlds: list[str]) -> str:
    """
    Convert ['ru', '.de', '*.fr'] → 'domain:ru | domain:de | domain:fr'
    """
    if not tlds: # Handle empty list case
        return ""
    cleaned = []
    for tld in tlds:
        tld = str(tld).strip() # Ensure string and remove whitespace
        tld = tld.lstrip("*.")            # remove leading *., .
        # No need for the .startswith(".") check after lstrip
        if tld:
            cleaned.append(f"domain:{tld}")
    # Yandex uses pipe | for OR, no surrounding parentheses needed based on examples
    return " | ".join(cleaned) if cleaned else ""


def build_time_block(after: Optional[str] = None, before: Optional[str] = None) -> str:
    """Return a Yandex ``date:`` filter string with enhanced date handling."""
    parts: List[str] = []
    # Enhanced to handle both YYYY and YYYYMMDD formats
    if after and isinstance(after, str):
        after = after.replace('-', '')  # Remove dashes
        if len(after) == 4: 
            after += '0101'  # Year-only → Jan 1
        elif len(after) >= 8:
            after = after[:8]  # Truncate to YYYYMMDD if longer
        if len(after) == 8:
            parts.append(f"date:>{after}")
    if before and isinstance(before, str):
        before = before.replace('-', '')
        if len(before) == 4:
            before += '0101'
        elif len(before) >= 8:
            before = before[:8]
        if len(before) == 8:
            parts.append(f"date:<{before}")
    return " ".join(parts)


def chunk_sites(sites: Iterable[str], max_terms: int = 30) -> Iterable[List[str]]:
    """Yield sub-lists so each OR-group stays within ~30 terms."""
    sites = list(sites)
    for i in range(0, len(sites), max_terms):
        yield sites[i:i + max_terms]


def retry_on_failure(max_retries: int = 3, delay: float = 2.0):
    """Simple retry decorator for API calls."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                        time.sleep(delay)
                    else:
                        logger.error(f"All {max_retries + 1} attempts failed. Last error: {e}")
            raise last_exception
        return wrapper
    return decorator


# --------------------------------------------------------------------------- #
# Enhanced Runner with Streaming Support
# --------------------------------------------------------------------------- #
class ExactPhraseRecallRunnerYandex:
    """Exhaustively combine base × site × time, hit Yandex, stream results with maximum recall."""

    def __init__(
        self,
        phrase: str,
        yandex: "YandexSearch",
        site_groups: Optional[List[List[str]]] = None,
        time_slices: Optional[List[Dict[str, Union[str, None]]]] = None,
        max_results_per_query: int = 100,
        use_parallel: bool = True,
        max_workers: int = 20,
        exception_search_iterations: int = 3,
    ):
        self.phrase = phrase.strip('\"') # Ensure outer quotes are stripped, leave brackets if any were internal
        self.yandex = yandex
        
        # Ensure site_groups always allows for a run without domain filters
        # if specific domain groups are provided.
        if site_groups:
             # If None is not already present, add it to the list
             if None not in site_groups:
                  self.site_groups: List[List[str] | None] = [None] + site_groups
             else:
                  self.site_groups: List[List[str] | None] = site_groups # Use as is if None already included
        else:
             self.site_groups: List[List[str] | None] = [None] # Default to only no filter

        # Ensure time_slices always allows for a run without date filters
        # if specific time slices are provided.
        if time_slices:
            # Check if an empty dict (representing no filter) is present
            has_no_filter = any(not d for d in time_slices if isinstance(d, dict))
            if not has_no_filter:
                 self.time_slices: List[Dict[str, Union[str, None]]] = [{}] + time_slices
            else:
                 self.time_slices: List[Dict[str, Union[str, None]]] = time_slices # Use as is
        else:
            self.time_slices: List[Dict[str, Union[str, None]]] = [{}] # Default to only no filter
            
        self.max_results_per_query = max_results_per_query
        self.use_parallel = use_parallel
        self.max_workers = max_workers
        self.exception_search_iterations = exception_search_iterations
        self._lock = threading.Lock()  # For thread-safe store updates
        self._store: Dict[str, Dict] = {} # url -> result dict

    # ............................................................. #
    def _add_and_get_new(self, batch: List[Dict]) -> List[Dict]:
        """Merge batch into store (thread-safe) and return only new unique hits added."""
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
    def _execute_query(self, task: Tuple[str, str]) -> List[Dict]:
        """Execute a single query with retry logic."""
        query, tag = task
        try:
            hits_from_engine = self.yandex.search(query=query, max_results=self.max_results_per_query)
            augmented_hits = []
            if hits_from_engine:
                for hit in hits_from_engine:
                    hit['found_by_query'] = query
                    hit['query_tag'] = tag
                    augmented_hits.append(hit)
            return augmented_hits
        except Exception as exc:
            logger.warning(f"Yandex query failed ({query}): {exc}")
            raise  # Re-raise for retry mechanism

    # ............................................................. #
    def run(self) -> Iterable[Dict]:
        """Runs all query permutations and yields unique results as they become available."""
        logger.info(f"Starting Yandex Exact Phrase Recall run for: '{self.phrase}' (parallel={self.use_parallel}, streaming=True)")
        bases = generate_yandex_base_queries(self.phrase)

        tasks = []  # (query, tag)
        for tag, base_query in bases.items():
            for sites in self.site_groups:
                site_block = build_site_block(sites) if sites else ""
                for slice_ in self.time_slices:
                    time_block = build_time_block(slice_.get("after"), slice_.get("before"))
                    parts = [base_query, site_block, time_block]
                    query = " ".join(filter(None, parts))
                    tasks.append((query, tag))

        logger.info(f"Prepared {len(tasks)} Yandex query permutations with enhanced filtering...")

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

        logger.info(f"Finished main Yandex run. Found {len(self._store)} unique URLs from {len(tasks)} permutations.")
        
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

        logger.info(f"Complete Yandex run finished. Total unique URLs: {len(self._store)}")

    # ............................................................. #
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
                from urllib.parse import urlparse
                domain = urlparse(url).netloc.lower()
                if domain:
                    found_domains.add(domain)
            except Exception:
                continue
        
        if not found_domains:
            logger.info("No valid domains found in previous results - skipping exception search")
            return []
        
        logger.info(f"Running Yandex exception search excluding {len(found_domains)} previously found domains...")
        
        # Base phrase for exception search
        base_query = f'"{self.phrase}"'
        
        # Build exclusion list - exclude ALL domains
        all_domains = sorted(list(found_domains))
        exclusions = [f"-domain:{domain}" for domain in all_domains]
        
        # Check if we can fit all exclusions in one query (Yandex ~2048 char limit)
        full_exclusion_query = f"{base_query} {' '.join(exclusions)}"
        
        exception_results = []
        
        if len(full_exclusion_query) <= 2000:  # Safe margin under Yandex's limit
            # Single query with all exclusions
            logger.info(f"Using single exception query excluding all {len(all_domains)} domains")
            exception_results.extend(self._run_single_exception_query(full_exclusion_query, found_domains))
        else:
            # Split into multiple queries if needed
            logger.info(f"Query too long - splitting into multiple exception queries to exclude all {len(all_domains)} domains")
            
            # Calculate how many domains we can exclude per query
            avg_domain_length = sum(len(domain) for domain in all_domains) / len(all_domains)
            max_domains_per_query = int((2000 - len(base_query) - 50) / (avg_domain_length + 9))  # 9 = "-domain:" + space
            max_domains_per_query = max(10, max_domains_per_query)  # At least 10 domains per query
            
            # Split domains into chunks
            for i in range(0, len(all_domains), max_domains_per_query):
                chunk_domains = all_domains[i:i + max_domains_per_query]
                chunk_exclusions = [f"-domain:{domain}" for domain in chunk_domains]
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
            
            hits_from_engine = self.yandex.search(query=exception_query, max_results=self.max_results_per_query)
            
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
# Main (quick manual test)
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s: %(message)s")

    PHRASE = "gulfstream lng"  # Example phrase
    SITES = ["*.ru", "*.de", "*.fr", "*.it"] # Example TLDs - will be cleaned by new build_site_block
    SITE_GROUPS = list(chunk_sites(SITES))
    # SITE_GROUPS = [None] # <-- Run without site filters for testing
    TIME_SLICES = [
        {}, # No time filter
        {"after": "2021"}, # After 2021 (runner converts to YYYY0101)
        {"before": "2021"} # Before 2021 (runner converts to YYYY0101)
    ]
    # TIME_SLICES = [{}] # <-- Run without time filters for testing

    logger.info("Initializing YandexSearch...")
    # IMPORTANT: Ensure the *real* YandexSearch is imported and API key is set
    # The try-except block attempts to import search_engines.yandex
    try:
        ys = YandexSearch() # Assumes keys are in .env or passed if needed
    except Exception as e:
        logger.error(f"Failed to initialize YandexSearch: {e}", exc_info=True)
        exit()

    logger.info("Initializing ExactPhraseRecallRunnerYandex...")
    runner = ExactPhraseRecallRunnerYandex(
        phrase=PHRASE,
        yandex=ys,
        site_groups=SITE_GROUPS, # Use original site groups (now using domain:)
        time_slices=TIME_SLICES, # Use original time slices
        max_results_per_query=50, 
        use_parallel=True,
        max_workers=20,
        exception_search_iterations=3
    )
    
    logger.info("Starting streaming Yandex runner...")
    results = []
    result_count = 0
    
    # Demonstrate streaming - process results as they come in
    for result in runner.run():
        result_count += 1
        results.append(result)
        # Process each result immediately (e.g., save to database, display, etc.)
        if result_count % 10 == 0:
            print(f"Processed {result_count} results so far...")
    
    print(f"\n--- STREAMING YANDEX DEMO COMPLETE --- ")
    print(f"Found {len(results)} unique Yandex URLs:")
    for i, h in enumerate(results[:10], 1):  # Show first 10 results
        title = h.get('title','[No Title]')
        url = h.get('url', '[No URL]')
        # Yandex might use 'headline' or 'passage' or 'snippet' - check API response if needed
        snippet = h.get('snippet', h.get('description', h.get('passage', '[No Snippet]')))
        search_type = h.get('search_type', 'normal')
        print(f"\n{i}. Title: {title}")
        print(f"   URL: {url}")
        print(f"   Type: {search_type}")
        print(f"   Snippet: {snippet}") 