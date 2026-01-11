"""
exact_phrase_recall_runner_baidu.py

Baidu search engine runner following the standard ExactPhraseRecallRunner pattern.
Supports all Baidu search operators.

Baidu Operators:
- "phrase": Exact phrase match (works for Chinese and Latin text)
- -term: Exclude term
- site:domain.com: Restrict to domain
- intitle:term: Term in page title
- inurl:term: Term in URL
- filetype:ext: Restrict by file type (pdf, doc, xls, ppt, etc.)
- OR / |: Logical OR
- (): Grouping
"""

import logging
import time
import requests
from typing import List, Dict, Optional, Iterator
from urllib.parse import quote, urlencode
from bs4 import BeautifulSoup
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

logger = logging.getLogger(__name__)


class BaiduScraper:
    """Baidu search scraper for individual queries."""
    
    def __init__(self):
        """Initialize Baidu scraper."""
        self.base_url = "https://www.baidu.com/s"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
    
    def build_url(self, query: str, offset: int = 0) -> str:
        """
        Build Baidu search URL.
        
        Args:
            query: Search query with operators
            offset: Page offset for pagination
            
        Returns:
            Complete search URL
        """
        params = {
            'wd': query,  # Baidu uses 'wd' for query parameter
            'pn': offset,  # Page number (0, 10, 20, ...)
            'rn': 50,     # Results per page (max 50)
            'ie': 'utf-8',
            'oe': 'utf-8'
        }
        
        url = f"{self.base_url}?{urlencode(params)}"
        logger.debug(f"Built Baidu URL: {url}")
        return url
    
    def extract_results(self, html: str, max_results: int = 50) -> List[Dict]:
        """
        Extract search results from Baidu HTML.
        
        Args:
            html: HTML content from Baidu
            max_results: Maximum number of results to extract
            
        Returns:
            List of search results
        """
        results = []
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Baidu result containers
            # Main results are in divs with class "result" or "c-container"
            result_containers = soup.find_all('div', class_=re.compile('result|c-container'))
            
            for container in result_containers[:max_results]:
                try:
                    result = {}
                    
                    # Extract URL - Baidu uses redirects
                    link_elem = container.find('a', href=True)
                    if link_elem:
                        # Baidu URLs are often redirects through baidu.com
                        baidu_url = link_elem.get('href', '')
                        if baidu_url:
                            result['url'] = baidu_url
                            # Try to extract real URL from data attributes if available
                            real_url = link_elem.get('data-landurl')
                            if real_url:
                                result['url'] = real_url
                    
                    # Extract title
                    title_elem = container.find(['h3', 'a'])
                    if title_elem:
                        # Remove HTML tags and clean up
                        title_text = title_elem.get_text(strip=True)
                        # Remove Baidu's added text
                        title_text = re.sub(r'_百度.*?$', '', title_text)
                        result['title'] = title_text
                    
                    # Extract snippet/description
                    # Baidu uses various classes for snippets
                    snippet_elem = container.find(class_=re.compile('c-abstract|content-right_8Zs40|c-span-last'))
                    if not snippet_elem:
                        # Try finding any text content
                        snippet_elem = container.find('span', class_=re.compile('content|abstract'))
                    
                    if snippet_elem:
                        result['snippet'] = snippet_elem.get_text(strip=True)
                    elif not snippet_elem:
                        # Fallback: get all text from container
                        all_text = container.get_text(strip=True)
                        # Remove title from text to get snippet
                        if result.get('title'):
                            snippet = all_text.replace(result['title'], '').strip()
                            result['snippet'] = snippet[:300]  # Limit length
                    
                    # Only add if we have URL and title
                    if result.get('url') and result.get('title'):
                        results.append(result)
                        
                except Exception as e:
                    logger.debug(f"Error extracting Baidu result: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error parsing Baidu results: {e}")
        
        return results
    
    def search(self, query: str, max_results: int = 50) -> List[Dict]:
        """
        Perform Baidu search.
        
        Args:
            query: Search query with operators
            max_results: Maximum results to return
            
        Returns:
            List of search results
        """
        all_results = []
        offset = 0
        
        while len(all_results) < max_results:
            try:
                url = self.build_url(query, offset)
                logger.info(f"Searching Baidu: {url}")
                
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                
                # Baidu returns GB2312/GBK encoded content sometimes
                # Let requests handle encoding detection
                html = response.text
                
                results = self.extract_results(html, max_results - len(all_results))
                
                if not results:
                    logger.info("No more Baidu results found")
                    break
                
                all_results.extend(results)
                logger.info(f"Found {len(results)} results on page")
                
                # Pagination
                offset += 10  # Baidu uses 10-result increments
                time.sleep(1)  # Rate limiting
                
            except requests.RequestException as e:
                logger.error(f"Error fetching Baidu results: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error in Baidu search: {e}")
                break
        
        return all_results[:max_results]


class ExactPhraseRecallRunnerBaidu:
    """
    Standard runner for Baidu search engine.
    Supports all Baidu operators and follows the ExactPhraseRecallRunner pattern.
    """
    
    def __init__(self,
                 phrase: str,
                 scraper=None,
                 site_groups: Optional[List[str]] = None,
                 filetype_groups: Optional[List[str]] = None,
                 exclude_terms: Optional[List[str]] = None,
                 intitle_terms: Optional[List[str]] = None,
                 inurl_terms: Optional[List[str]] = None,
                 max_results_per_query: int = 50,
                 use_parallel: bool = True,
                 max_workers: int = 3):
        """
        Initialize Baidu runner.
        
        Args:
            phrase: The search query (can include quotes for exact match)
            scraper: BaiduScraper instance
            site_groups: List of domains for site: operator
            filetype_groups: List of file extensions for filetype: operator
            exclude_terms: List of terms to exclude with -term
            intitle_terms: List of terms for intitle: operator
            inurl_terms: List of terms for inurl: operator
            max_results_per_query: Maximum results per query variation
            use_parallel: Enable parallel execution
            max_workers: Number of parallel workers
        """
        self.phrase = phrase
        self.scraper = scraper or BaiduScraper()
        self.site_groups = site_groups or []
        self.filetype_groups = filetype_groups or []
        self.exclude_terms = exclude_terms or []
        self.intitle_terms = intitle_terms or []
        self.inurl_terms = inurl_terms or []
        self.max_results_per_query = max_results_per_query
        self.use_parallel = use_parallel
        self.max_workers = max_workers
        
        # Thread safety
        self.result_lock = threading.Lock()
        self.seen_urls = set()
        self.results_found = False
        
        logger.info(f"BaiduRunner initialized: phrase='{phrase}'")
    
    def _build_query_variations(self) -> List[str]:
        """
        Build all query variations using Baidu operators.
        
        Returns:
            List of query strings with different operator combinations
        """
        variations = []
        
        # Base query (ensure quotes for exact phrase)
        base_query = self.phrase
        if ' ' in base_query and not (base_query.startswith('"') and base_query.endswith('"')):
            base_query = f'"{base_query}"'
        
        # Add exclusions to base
        if self.exclude_terms:
            exclusions = ' '.join([f'-{term}' for term in self.exclude_terms])
            base_query = f'{base_query} {exclusions}'
        
        # Plain query
        variations.append(base_query)
        
        # Site-specific queries
        for site in self.site_groups:
            variations.append(f'{base_query} site:{site}')
        
        # Filetype queries
        for filetype in self.filetype_groups:
            variations.append(f'{base_query} filetype:{filetype}')
            # Also combine with sites
            for site in self.site_groups[:3]:  # Limit combinations
                variations.append(f'{base_query} site:{site} filetype:{filetype}')
        
        # Title queries
        for term in self.intitle_terms:
            variations.append(f'{base_query} intitle:{term}')
        
        # URL queries
        for term in self.inurl_terms:
            variations.append(f'{base_query} inurl:{term}')
        
        # Combined operators (limited to avoid too many variations)
        if self.intitle_terms and self.site_groups:
            variations.append(f'{base_query} intitle:{self.intitle_terms[0]} site:{self.site_groups[0]}')
        
        if self.inurl_terms and self.filetype_groups:
            variations.append(f'{base_query} inurl:{self.inurl_terms[0]} filetype:{self.filetype_groups[0]}')
        
        return variations
    
    def _search_single_query(self, query: str) -> List[Dict]:
        """
        Execute search for a single query variation.
        
        Args:
            query: Query string with operators
            
        Returns:
            List of search results
        """
        try:
            logger.info(f"Searching Baidu with query: {query}")
            results = self.scraper.search(query, self.max_results_per_query)
            logger.info(f"Baidu query returned {len(results)} results")
            return results
        except Exception as e:
            logger.error(f"Error searching Baidu with query '{query}': {e}")
            return []
    
    def _deduplicate_result(self, result: Dict) -> Optional[Dict]:
        """
        Check if result is duplicate based on URL.
        
        Args:
            result: Search result dict
            
        Returns:
            Result if not duplicate, None otherwise
        """
        url = result.get('url', '')
        if not url:
            return None
        
        # Normalize Baidu redirect URLs
        url = url.replace('http://www.baidu.com/link?url=', '')
        url = url.replace('https://www.baidu.com/link?url=', '')
        
        with self.result_lock:
            if url in self.seen_urls:
                return None
            self.seen_urls.add(url)
        
        # Add source information
        result['engine'] = 'BA'
        result['engines'] = ['BA']
        result['source'] = 'Baidu'
        
        return result
    
    def run(self) -> Iterator[Dict]:
        """
        Execute search across all query variations and yield results.
        
        Yields:
            Search results as they become available
        """
        queries = self._build_query_variations()
        logger.info(f"Running Baidu search with {len(queries)} query variations")
        
        if self.use_parallel and len(queries) > 1:
            # Parallel execution
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit all queries
                future_to_query = {
                    executor.submit(self._search_single_query, query): query
                    for query in queries
                }
                
                # Process results as they complete
                for future in as_completed(future_to_query):
                    query = future_to_query[future]
                    try:
                        results = future.result()
                        
                        # Yield deduplicated results
                        for result in results:
                            clean_result = self._deduplicate_result(result)
                            if clean_result:
                                self.results_found = True
                                yield clean_result
                                
                    except Exception as e:
                        logger.error(f"Error processing query '{query}': {e}")
        else:
            # Sequential execution
            for query in queries:
                results = self._search_single_query(query)
                
                # Yield deduplicated results
                for result in results:
                    clean_result = self._deduplicate_result(result)
                    if clean_result:
                        self.results_found = True
                        yield clean_result
    
    def has_results(self) -> bool:
        """Check if any results were found."""
        return self.results_found


# Alias for compatibility
ExactPhraseRecallRunner = ExactPhraseRecallRunnerBaidu


def main():
    """Test the Baidu runner."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test Baidu Runner')
    parser.add_argument('query', help='Search query')
    parser.add_argument('--sites', nargs='+', help='Domains for site: operator')
    parser.add_argument('--filetypes', nargs='+', help='File types')
    parser.add_argument('--exclude', nargs='+', help='Terms to exclude')
    parser.add_argument('--intitle', nargs='+', help='Terms for intitle:')
    parser.add_argument('--inurl', nargs='+', help='Terms for inurl:')
    parser.add_argument('--limit', type=int, default=10, help='Max results')
    
    args = parser.parse_args()
    
    # Create runner
    runner = ExactPhraseRecallRunnerBaidu(
        phrase=args.query,
        site_groups=args.sites,
        filetype_groups=args.filetypes,
        exclude_terms=args.exclude,
        intitle_terms=args.intitle,
        inurl_terms=args.inurl,
        max_results_per_query=args.limit
    )
    
    print(f"Searching Baidu for: {args.query}")
    print("-" * 60)
    
    # Collect results
    results = list(runner.run())
    
    if results:
        for i, result in enumerate(results, 1):
            print(f"\n{i}. {result.get('title', 'No title')}")
            print(f"   URL: {result.get('url', 'No URL')}")
            if result.get('snippet'):
                print(f"   Snippet: {result['snippet'][:150]}...")
    else:
        print("No results found")
    
    print(f"\nTotal results: {len(results)}")


if __name__ == '__main__':
    main()