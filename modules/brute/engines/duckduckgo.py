"""
Fixed DuckDuckGo implementation with better rate limit handling
"""

import logging
import os
import time
import random
from typing import List, Dict, Any, Optional
import requests
from bs4 import BeautifulSoup

try:
    from shared_session import get_shared_session
except ImportError:
    get_shared_session = None

# Proxy pool integration
try:
    from brute.infrastructure.proxy_pool import get_proxy_config_for_engine, record_proxy_result
    PROXY_POOL_AVAILABLE = True
except ImportError:
    PROXY_POOL_AVAILABLE = False
    get_proxy_config_for_engine = None
    record_proxy_result = None

logger = logging.getLogger(__name__)


class DuckDuckGoFixed:
    """Fixed DuckDuckGo implementation with rate limit handling and proxy support"""

    def __init__(self):
        self.session = None
        self.last_request_time = 0
        self.min_delay = 2.0  # Minimum 2 seconds between requests
        self.rate_limited = False
        self.rate_limit_expire = 0
        self._proxy_enabled = PROXY_POOL_AVAILABLE
        if self._proxy_enabled:
            logger.info("DuckDuckGo: Proxy pool enabled for SERP scraping")
        
    def _get_session(self):
        """Get or create session with proper headers"""
        if self.session is None:
            if get_shared_session:
                self.session = get_shared_session(engine_name='DUCKDUCK')
                logger.info("Using shared connection pool")
            else:
                self.session = requests.Session()
            
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0'
            })
        return self.session
    
    def _wait_if_needed(self):
        """Implement rate limiting"""
        current_time = time.time()
        
        # Check if we're rate limited
        if self.rate_limited and current_time < self.rate_limit_expire:
            wait_time = self.rate_limit_expire - current_time
            logger.info(f"Rate limited. Waiting {wait_time:.1f} seconds...")
            time.sleep(wait_time)
            self.rate_limited = False
        
        # Regular rate limiting
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_delay:
            wait_time = self.min_delay - time_since_last + random.uniform(0, 1)
            logger.debug(f"Rate limiting: waiting {wait_time:.1f} seconds")
            time.sleep(wait_time)
        
        self.last_request_time = time.time()
    
    def search(self, query: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Search DuckDuckGo with multi-backend support for max recall.
        
        Args:
            query: Search query  
            max_results: Maximum results to return
            
        Returns:
            List of search results
        """
        # MULTI-BACKEND: Use SerpAPI + BrightData + Native scraping
        if os.getenv('USE_MULTI_BACKEND', 'true').lower() == 'true':
            try:
                from .multi_backend_integration import multi_backend_duckduckgo
                return multi_backend_duckduckgo(query, max_results, 
                                                native_search_func=self._search_native)
            except ImportError as e:
                logger.debug(f"Multi-backend not available: {e}")
            except Exception as e:
                logger.warning(f"Multi-backend failed, using native: {e}")
        
        return self._search_native(query, max_results)
    
    def _search_native(self, query: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """Native DuckDuckGo scraping (used as one backend in multi-backend)."""
        results = []
        
        # Wait before making request
        self._wait_if_needed()
        
        try:
            session = self._get_session()

            # Get proxy for this request
            proxy_config = None
            proxies = None
            if self._proxy_enabled and get_proxy_config_for_engine:
                proxy_config = get_proxy_config_for_engine('duckduckgo')
                if proxy_config:
                    proxies = proxy_config.get_proxy_dict()
                    logger.debug(f"DuckDuckGo using proxy: {proxy_config.name}")

            # Try the HTML interface with form submission
            # First, get the search page to establish cookies
            home_resp = session.get('https://duckduckgo.com/', timeout=10, proxies=proxies)
            time.sleep(random.uniform(0.5, 1.0))

            # Now submit search
            search_data = {
                'q': query,
                'kl': 'us-en',
                'kp': '-2',  # Safe search off
                'kz': '-1',  # No instant answers
            }

            resp = session.post(
                'https://html.duckduckgo.com/html/',
                data=search_data,
                timeout=15,
                allow_redirects=True,
                proxies=proxies
            )

            # Record proxy result
            if proxy_config and record_proxy_result:
                record_proxy_result(proxy_config, resp.status_code < 500)

            logger.debug(f"DuckDuckGo response status: {resp.status_code}")
            
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                # Look for result containers
                # Try multiple selectors
                selectors = [
                    'div.result',
                    'div.results_links',
                    'div.result__body',
                    'div.links_main',
                    'h2.result__title',
                ]
                
                for selector in selectors:
                    containers = soup.select(selector)
                    if containers:
                        logger.debug(f"Found {len(containers)} results with selector: {selector}")
                        break
                else:
                    # No results found with selectors, try finding links directly
                    containers = []
                    all_links = soup.find_all('a', href=True)
                    
                    for link in all_links:
                        href = link.get('href', '')
                        # Filter results
                        if (href.startswith('http') and 
                            'duckduckgo.com' not in href and
                            'duck.co' not in href):
                            containers.append(link)
                
                # Process results
                seen_urls = set()
                
                for container in containers[:max_results]:
                    try:
                        # Extract URL
                        if hasattr(container, 'name') and container.name == 'a':
                            url = container.get('href', '')
                            title = container.get_text(strip=True)
                            snippet = ""
                        else:
                            # Look for link within container
                            link = container.find('a', class_=['result__a', 'result__url'])
                            if not link:
                                link = container.find('a', href=True)
                            
                            if not link:
                                continue
                                
                            url = link.get('href', '')
                            title = link.get_text(strip=True)
                            
                            # Find snippet
                            snippet_elem = container.find(['span', 'div'], class_=['result__snippet', 'snippet'])
                            if not snippet_elem:
                                snippet_elem = container.find('a', class_='result__snippet')
                            
                            snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                        
                        # Clean and validate URL
                        if url and url.startswith('http') and url not in seen_urls:
                            seen_urls.add(url)
                            results.append({
                                'url': url,
                                'title': title or url,
                                'snippet': snippet,
                                'source': 'duckduckgo'
                            })
                    
                    except Exception as e:
                        logger.debug(f"Error parsing result: {e}")
                        continue
                
                logger.info(f"Successfully extracted {len(results)} results")
                
            elif resp.status_code == 202:
                logger.warning("DuckDuckGo returned 202 - rate limited")
                self.rate_limited = True
                self.rate_limit_expire = time.time() + 60  # Wait 60 seconds
                
            elif resp.status_code == 403:
                logger.error("DuckDuckGo returned 403 - access forbidden")
                self.rate_limited = True
                self.rate_limit_expire = time.time() + 300  # Wait 5 minutes
                
            else:
                logger.warning(f"Unexpected status code: {resp.status_code}")
        
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")
        
        return results


# Global instance to maintain state between calls
_global_ddg = None


def search_duckduckgo_exact_phrase(phrase: str, max_results: int = 100, **kwargs) -> List[Dict[str, Any]]:
    """
    Search DuckDuckGo for exact phrase with rate limit handling
    
    Args:
        phrase: Search phrase
        max_results: Maximum results
        
    Returns:
        List of search results
    """
    global _global_ddg
    
    if _global_ddg is None:
        _global_ddg = DuckDuckGoFixed()
    
    # Add quotes for exact phrase search
    query = f'"{phrase}"'
    
    return _global_ddg.search(query, max_results)


# Create the class that matches the expected name in ENGINE_CONFIG
class MaxExactDuckDuckGo:
    """DuckDuckGo search engine for brute.py integration"""
    
    def __init__(self, phrase: str = None):
        self.phrase = phrase
        self.ddg = DuckDuckGoFixed()
        print("  - MaxExactDuckDuckGo Initialized")
    
    def search(self, query: str = None, max_results: int = 100) -> List[Dict[str, Any]]:
        """Search method matching expected interface"""
        if query is None:
            query = self.phrase
        return self.ddg.search(query, max_results)

class ExactPhraseRecallRunnerDuckDuckGo:
    """
    DuckDuckGo search runner with DD1-DD4 variations for max recall.
    DuckDuckGo supports: site:, filetype:, intitle:, inurl:, inbody:
    """

    def __init__(self, phrase: str = None, keyword: str = None,
                 max_results: int = 50, event_emitter=None,
                 use_parallel: bool = True, max_workers: int = 4):
        self.phrase = phrase or keyword
        self.keyword = keyword or phrase
        self.max_results = max_results
        self.event_emitter = event_emitter
        self.use_parallel = use_parallel
        self.max_workers = max_workers
        self.ddg = DuckDuckGoSearch()

    def _get_base_queries(self) -> dict:
        """Get DD1-DD4 query variations."""
        quoted = self.phrase if self.phrase.startswith('"') else f'"{self.phrase}"'
        return {
            "DD1_exact": quoted,
            "DD2_pdf": f"{quoted} filetype:pdf",
            "DD2_doc": f"{quoted} filetype:doc OR filetype:docx",
            "DD2_xls": f"{quoted} filetype:xls OR filetype:xlsx",
            "DD2_ppt": f"{quoted} filetype:ppt OR filetype:pptx",
            "DD3_intitle": f"intitle:{quoted}",
            "DD4_inurl": f"inurl:{quoted}",
        }

    def _search_query(self, tag_query):
        """Search a single query variation."""
        tag, query = tag_query
        try:
            results = self.ddg.search(query, max_results=self.max_results // 4)
            for r in results:
                r["_query_tag"] = tag
            return results
        except Exception as e:
            logging.warning(f"DDG query {tag} failed: {e}")
            return []

    def run(self):
        """Run all query variations with optional parallelism."""
        all_results = []
        seen_urls = set()
        queries = list(self._get_base_queries().items())

        if self.use_parallel:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                for results in executor.map(self._search_query, queries):
                    for r in results:
                        url = r.get("url", "")
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            all_results.append(r)
                            if self.event_emitter:
                                try:
                                    self.event_emitter(r)
                                except:
                                    pass
        else:
            for tag, query in queries:
                results = self._search_query((tag, query))
                for r in results:
                    url = r.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append(r)

        return all_results[:self.max_results]

    async def run_with_streaming(self):
        """Async streaming support."""
        for r in self.run():
            yield r
