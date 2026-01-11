"""
Optimized NewsAPI implementation with parallel variation processing
"""

import sys
from pathlib import Path
import requests
from typing import Dict, List, Iterable, Set
import time
import random
import tenacity
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import os

class ExactPhraseRecallRunnerNewsAPI:
    def __init__(self, phrase: str, api_key: str = None, start_date: str = None, end_date: str = None):
        self.phrase = phrase
        self.api_key = api_key or os.getenv("NEWSAPI_KEY", "") or os.getenv("NEWS_API_KEY", "")
        self.start_date = start_date  # Optional: YYYY-MM-DD format
        self.end_date = end_date  # Optional: YYYY-MM-DD format
        self.base_url = "https://newsapi.org/v2"
        
        # Try to use shared session if available
        try:
            from shared_session import get_shared_session
            self.session = get_shared_session(engine_name='NewsAPI')
            print("NewsAPI: Using shared connection pool")
        except ImportError:
            self.session = requests.Session()
            
        print("  - ExactPhraseRecallRunnerNewsAPI Initialized")
    
    def query_newsapi_parallel(self, query: str, max_results: int = 100) -> List[Dict]:
        """Parallel version of NewsAPI search"""
        print(f"NewsAPI: Starting search for query: '{query}'")
        print(f"NewsAPI: API key present: {bool(self.api_key)}")
        
        # Generate variations
        variations = [
            {"endpoint": "everything", "searchIn": "title,description", "sortBy": "relevancy"},
            {"endpoint": "everything", "searchIn": "title,description", "sortBy": "popularity"},
            {"endpoint": "everything", "searchIn": "title,description", "language": "en"},
        ]
        
        # Date range - only if explicitly provided
        start_date = datetime.strptime(self.start_date, "%Y-%m-%d") if self.start_date else None
        end_date = datetime.strptime(self.end_date, "%Y-%m-%d") if self.end_date else None
        
        collected_urls = set()
        results = []
        lock = threading.Lock()
        search_phrase = query.strip('"').lower()
        print(f"NewsAPI: Looking for phrase: '{search_phrase}'")
        
        def fetch_variation(var):
            """Fetch results for a single variation"""
            params = {
                "q": query,
                "apiKey": self.api_key,
                "pageSize": min(100, max_results),
            }
            if start_date:
                params["from"] = start_date.strftime("%Y-%m-%d")
            if end_date:
                params["to"] = end_date.strftime("%Y-%m-%d")
            params.update(var)
            
            try:
                url = f"{self.base_url}/{var['endpoint']}"
                print(f"NewsAPI: Fetching {url} with params: {var}")
                response = self._fetch_with_retries(url, params=params)
                data = response.json()
                
                # Check for API errors
                if data.get("status") == "error":
                    error_msg = data.get('message', 'Unknown error')
                    error_code = data.get('code', 'Unknown')
                    print(f"NewsAPI ERROR: {error_msg} (Code: {error_code})")
                    print(f"NewsAPI Full Response: {data}")
                    return []
                
                articles = data.get("articles", [])
                total_results = data.get("totalResults", 0)
                print(f"NewsAPI: Variation {var} returned {len(articles)} articles (total available: {total_results})")
                
                local_results = []
                matched_count = 0
                for article in articles:
                    title = article.get("title", "").lower()
                    desc = article.get("description", "").lower()
                    url_ = article.get("url", "")
                    source_name = article.get("source", {}).get("name", "")
                    
                    # Log matching logic
                    title_match = search_phrase in title
                    desc_match = search_phrase in desc
                    
                    if url_ and (title_match or desc_match):
                        matched_count += 1
                        snippet = f"[{source_name}] {article.get('title', '')}"
                        if article.get('description'):
                            snippet += f" - {article.get('description')}"
                        
                        local_results.append({
                            "url": url_,
                            "title": article.get('title', ''),
                            "snippet": snippet,
                            "found_by_query": query,
                            "source": source_name,
                            "published": article.get('publishedAt', '')
                        })
                
                print(f"NewsAPI: Matched {matched_count}/{len(articles)} articles for variation {var}")
                return local_results
                
            except Exception as e:
                print(f"NewsAPI error for variation {var}: {e}")
                import traceback
                traceback.print_exc()
                return []
        
        # Run variations in parallel - increased workers for better performance
        with ThreadPoolExecutor(max_workers=min(len(variations), 8)) as executor:
            futures = {executor.submit(fetch_variation, var): var for var in variations}
            
            for future in as_completed(futures):
                var_results = future.result()
                
                with lock:
                    for result in var_results:
                        if result['url'] not in collected_urls:
                            collected_urls.add(result['url'])
                            results.append(result)
                            
                            if len(results) >= max_results:
                                executor.shutdown(wait=False)
                                print(f"NewsAPI: Reached max results limit ({max_results}), returning {len(results)} results")
                                return results[:max_results]
        
        print(f"NewsAPI: Search complete, returning {len(results)} unique results")
        return results[:max_results]
    
    @tenacity.retry(
        wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
        stop=tenacity.stop_after_attempt(3),
        retry=tenacity.retry_if_exception_type(requests.RequestException)
    )
    def _fetch_with_retries(self, url: str, **kwargs) -> requests.Response:
        """Fetch URL with retry logic"""
        try:
            response = self.session.get(url, **kwargs)
            print(f"NewsAPI Response Status: {response.status_code}")
            
            if response.status_code == 429:
                # Reduced rate limit sleep
                time.sleep(0.2 + random.random() * 0.2)
                raise requests.RequestException("Rate limited")
            
            if response.status_code != 200:
                print(f"NewsAPI HTTP Error: {response.status_code} - {response.text[:200]}")
            
            response.raise_for_status()
            return response
        except Exception as e:
            print(f"NewsAPI Request Error: {type(e).__name__}: {e}")
            raise
    
    def search(self, query: str = None, max_results: int = 100) -> List[Dict]:
        """Main search method for brute.py compatibility"""
        if query is None:
            query = self.phrase
        return self.query_newsapi_parallel(query, max_results)