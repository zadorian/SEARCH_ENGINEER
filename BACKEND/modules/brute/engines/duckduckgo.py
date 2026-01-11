"""
Fixed DuckDuckGo implementation with better rate limit handling
"""

import logging
import time
import random
from typing import List, Dict, Any, Optional
import requests
from bs4 import BeautifulSoup

try:
    from shared_session import get_shared_session
except ImportError:
    get_shared_session = None

logger = logging.getLogger(__name__)


class DuckDuckGoFixed:
    """Fixed DuckDuckGo implementation with rate limit handling"""
    
    def __init__(self):
        self.session = None
        self.last_request_time = 0
        self.min_delay = 2.0  # Minimum 2 seconds between requests
        self.rate_limited = False
        self.rate_limit_expire = 0
        
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
        Search DuckDuckGo with proper rate limit handling
        
        Args:
            query: Search query  
            max_results: Maximum results to return
            
        Returns:
            List of search results
        """
        results = []
        
        # Wait before making request
        self._wait_if_needed()
        
        try:
            session = self._get_session()
            
            # Try the HTML interface with form submission
            # First, get the search page to establish cookies
            home_resp = session.get('https://duckduckgo.com/', timeout=10)
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
                allow_redirects=True
            )
            
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