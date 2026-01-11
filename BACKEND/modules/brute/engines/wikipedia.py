#!/usr/bin/env python3
"""
Wikipedia search engine for encyclopedic content.
Searches 6M+ articles across multiple languages.
Free API with no authentication required.
"""

import os
import time
import json
import requests
from typing import List, Dict, Optional, Iterator
from urllib.parse import quote, urlencode
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

try:
    from shared_session import get_shared_session
    SHARED_SESSION = True
except ImportError:
    SHARED_SESSION = False


class ExactPhraseRecallRunnerWikipedia:
    """Search Wikipedia for encyclopedic articles."""
    
    def __init__(
        self,
        phrase: str,
        language: str = 'en',  # Wikipedia language code (en, es, fr, de, etc.)
        search_mode: str = 'text',  # 'text', 'title', 'nearmatch'
        include_redirects: bool = True,
        max_results_per_page: int = 50,
        max_pages: int = 10
    ):
        self.phrase = phrase
        self.language = language
        self.search_mode = search_mode
        self.include_redirects = include_redirects
        self.max_results_per_page = min(max_results_per_page, 500)  # API max is 500
        self.max_pages = max_pages
        self.base_url = f"https://{language}.wikipedia.org/w/api.php"
        
        # Use shared session if available
        if SHARED_SESSION:
            self.session = get_shared_session(engine_name='WIKIPEDIA')
        else:
            self.session = requests.Session()
            self.session.headers.update({
                'User-Agent': 'SearchEngine/1.0 (https://example.com/contact)'
            })
        
        print(f"  - ExactPhraseRecallRunnerWikipedia Initialized")
        print(f"    Language: {language}")
        print(f"    Search mode: {search_mode}")
    
    def _search_articles(self, offset: int = 0) -> Dict:
        """Search Wikipedia using the MediaWiki API."""
        # Build search string with quotes for exact phrase
        search_string = f'"{self.phrase}"'
        
        # Choose API action based on search mode
        if self.search_mode == 'title':
            # Use opensearch for title search
            params = {
                'action': 'opensearch',
                'search': self.phrase,  # No quotes for title search
                'limit': self.max_results_per_page,
                'format': 'json',
                'redirects': 'resolve' if self.include_redirects else 'return'
            }
        elif self.search_mode == 'nearmatch':
            # Use query for near match
            params = {
                'action': 'query',
                'list': 'search',
                'srsearch': f'nearmatch:{self.phrase}',
                'srlimit': self.max_results_per_page,
                'sroffset': offset,
                'format': 'json',
                'srprop': 'snippet|titlesnippet|size|wordcount|timestamp|redirecttitle'
            }
        else:  # 'text' - default full text search
            params = {
                'action': 'query',
                'list': 'search',
                'srsearch': search_string,
                'srlimit': self.max_results_per_page,
                'sroffset': offset,
                'srwhat': 'text',
                'format': 'json',
                'srprop': 'snippet|titlesnippet|size|wordcount|timestamp|redirecttitle|sectiontitle'
            }
        
        try:
            response = self.session.get(self.base_url, params=params, timeout=30)
            
            if response.status_code != 200:
                print(f"Wikipedia API error: {response.status_code}")
                return {'query': {'searchinfo': {'totalhits': 0}, 'search': []}}
            
            data = response.json()
            
            # Handle opensearch response format
            if self.search_mode == 'title' and 'query' not in data:
                # Convert opensearch format to standard format
                titles = data[1] if len(data) > 1 else []
                descriptions = data[2] if len(data) > 2 else []
                urls = data[3] if len(data) > 3 else []
                
                search_results = []
                for i, title in enumerate(titles):
                    result = {
                        'title': title,
                        'snippet': descriptions[i] if i < len(descriptions) else '',
                        'url': urls[i] if i < len(urls) else f"https://{self.language}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"
                    }
                    search_results.append(result)
                
                return {
                    'query': {
                        'searchinfo': {'totalhits': len(titles)},
                        'search': search_results
                    }
                }
            
            return data
            
        except Exception as e:
            print(f"Wikipedia search error: {e}")
            return {'query': {'searchinfo': {'totalhits': 0}, 'search': []}}
    
    def _get_page_extract(self, title: str) -> str:
        """Get the introduction extract of a Wikipedia page."""
        params = {
            'action': 'query',
            'prop': 'extracts',
            'exintro': True,
            'explaintext': True,
            'titles': title,
            'format': 'json',
            'exlimit': 1,
            'exchars': 300
        }
        
        try:
            response = self.session.get(self.base_url, params=params, timeout=10)
            data = response.json()
            
            pages = data.get('query', {}).get('pages', {})
            for page_id, page_data in pages.items():
                if page_id != '-1':  # -1 means page not found
                    return page_data.get('extract', '')
            
        except Exception as e:

            print(f"[BRUTE] Error: {e}")

            pass
        
        return ''
    
    def _clean_snippet(self, html_snippet: str) -> str:
        """Clean HTML from search snippets."""
        # Remove HTML tags
        import re
        clean = re.sub(r'<[^>]+>', '', html_snippet)
        # Remove multiple spaces
        clean = re.sub(r'\s+', ' ', clean)
        # Decode HTML entities
        clean = clean.replace('&quot;', '"').replace('&amp;', '&')
        clean = clean.replace('&lt;', '<').replace('&gt;', '>')
        return clean.strip()
    
    def _parse_search_result(self, result: Dict) -> Dict[str, str]:
        """Parse a search result into standard format."""
        # Get title
        title = result.get('title', 'Untitled')
        
        # Check for redirect
        redirect_title = result.get('redirecttitle')
        if redirect_title:
            title = f"{title} (redirect from: {redirect_title})"
        
        # Get section title if searching within sections
        section_title = result.get('sectiontitle')
        if section_title:
            title = f"{title} § {section_title}"
        
        # Get snippet
        snippet = result.get('snippet', '')
        if snippet:
            snippet = self._clean_snippet(snippet)
        
        # Add metadata to snippet
        snippet_parts = []
        
        if snippet:
            snippet_parts.append(snippet)
        
        # Add word count
        word_count = result.get('wordcount')
        if word_count:
            snippet_parts.append(f"Words: {word_count:,}")
        
        # Add size
        size = result.get('size')
        if size:
            kb_size = size / 1024
            snippet_parts.append(f"Size: {kb_size:.1f} KB")
        
        # Add timestamp
        timestamp = result.get('timestamp')
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                snippet_parts.append(f"Updated: {dt.strftime('%Y-%m-%d')}")
            except Exception as e:

                print(f"[BRUTE] Error: {e}")

                pass
        
        # If no snippet yet, try to get page extract
        if not snippet_parts or (len(snippet_parts) == 1 and not snippet_parts[0]):
            extract = self._get_page_extract(title)
            if extract:
                snippet_parts = [extract]
        
        final_snippet = " | ".join(snippet_parts) if snippet_parts else "Wikipedia article"
        
        # Build URL
        url = result.get('url')
        if not url:
            # Build Wikipedia URL
            page_title = title.split(' (redirect')[0].split(' § ')[0]  # Remove redirect/section info
            encoded_title = quote(page_title.replace(' ', '_'))
            url = f"https://{self.language}.wikipedia.org/wiki/{encoded_title}"
        
        return {
            'url': url,
            'title': title,
            'snippet': final_snippet,
            'source': 'wikipedia'
        }
    
    def search(self, max_results: int = 100) -> List[Dict[str, str]]:
        """Search Wikipedia for articles matching the phrase."""
        print(f"🔍 Searching Wikipedia ({self.language}) for: '{self.phrase}'")
        
        all_results = []
        
        try:
            for page in range(self.max_pages):
                if len(all_results) >= max_results:
                    break
                
                # Calculate offset
                offset = page * self.max_results_per_page
                
                # Search Wikipedia
                data = self._search_articles(offset)
                
                # Extract results based on response format
                if 'query' in data:
                    search_info = data['query'].get('searchinfo', {})
                    total_hits = search_info.get('totalhits', 0)
                    search_results = data['query'].get('search', [])
                else:
                    # Handle other response formats
                    search_results = []
                    total_hits = 0
                
                if not search_results:
                    break
                
                # Process each result
                for result in search_results:
                    if len(all_results) >= max_results:
                        break
                    
                    parsed = self._parse_search_result(result)
                    
                    # Verify phrase appears (case-insensitive)
                    phrase_lower = self.phrase.lower()
                    if (phrase_lower in parsed['title'].lower() or 
                        phrase_lower in parsed['snippet'].lower()):
                        all_results.append(parsed)
                
                print(f"  Page {page + 1}: Found {len(search_results)} articles (Total available: {total_hits:,})")
                
                # Check if we've seen all results
                if offset + len(search_results) >= total_hits:
                    break
                
                # Rate limiting - Wikipedia requests max 200/s but be polite
                if page < self.max_pages - 1:
                    time.sleep(0.5)
            
        except Exception as e:
            print(f"Wikipedia search error: {e}")
        
        print(f"✅ Found {len(all_results)} results from Wikipedia")
        return all_results[:max_results]
    
    def search_multiple_languages(self, languages: List[str], max_per_language: int = 20) -> List[Dict[str, str]]:
        """Search Wikipedia across multiple languages."""
        all_results = []
        
        for lang in languages:
            print(f"\nSearching Wikipedia ({lang})...")
            self.language = lang
            self.base_url = f"https://{lang}.wikipedia.org/w/api.php"
            
            results = self.search(max_results=max_per_language)
            
            # Add language tag to results
            for result in results:
                result['title'] = f"[{lang.upper()}] {result['title']}"
                all_results.append(result)
        
        return all_results
    
    def run(self) -> List[Dict[str, str]]:
        """Run the search - standard interface."""
        return self.search(max_results=self.max_results_per_page * self.max_pages)


# For backward compatibility
def search_wikipedia_exact_phrase(phrase: str, max_results: int = 100, **kwargs) -> List[Dict[str, str]]:
    """Search Wikipedia for exact phrase."""
    searcher = ExactPhraseRecallRunnerWikipedia(phrase, **kwargs)
    return searcher.search(max_results)


if __name__ == "__main__":
    # Test single language search
    searcher = ExactPhraseRecallRunnerWikipedia(
        "artificial intelligence",
        language='en',
        search_mode='text'
    )
    results = searcher.search(max_results=3)
    
    print("\n=== English Wikipedia Results ===")
    for i, result in enumerate(results, 1):
        print(f"\n{i}. {result['title']}")
        print(f"   URL: {result['url']}")
        print(f"   Info: {result['snippet'][:200]}...")
    
    # Test multi-language search
    print("\n=== Multi-language Search ===")
    results = searcher.search_multiple_languages(['en', 'es', 'fr'], max_per_language=2)
    
    for i, result in enumerate(results, 1):
        print(f"\n{i}. {result['title']}")
        print(f"   URL: {result['url']}")