#!/usr/bin/env python3
"""
Example of migrating proximity.py to use lazy loading.

This shows how to convert an existing search type module to use the new
lazy loading system with minimal changes.
"""

import sys
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Literal
import logging
from datetime import datetime
import os
import asyncio
import json
from urllib.parse import urlparse
import traceback
import inspect
from functools import partial
import requests

# Get the correct path to your project's root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# CHANGED: Replace all the individual try/except imports with a single import
from engine_imports import *

# The rest of the imports remain the same
logger = logging.getLogger(__name__)

# Import brain for gap filling
try:
    from brain import predict_gap_fillers
    AI_BRAIN_AVAILABLE = True
except ImportError:
    AI_BRAIN_AVAILABLE = False
    logger.warning("Brain module not found, gap filling will be disabled")
    async def predict_gap_fillers(*args, **kwargs):
        return []

# Import inurl search functionality
try:
    from master_search import SearchEngines, URLCleaner, DomainChecker
    INURL_AVAILABLE = True
    logger.info("inURL search module loaded successfully")
except ImportError as e:
    INURL_AVAILABLE = False
    logger.warning(f"inURL search module not available: {e}")
    # Create fallback classes
    class SearchEngines:
        def search_wayback(self, query, limit): return []
        def search_common_crawl(self, query, limit): return []
    class URLCleaner:
        @staticmethod
        def clean_url(url): return url
    class DomainChecker:
        @staticmethod
        def check_domain_batch(domains): return {}

# CHANGED: Custom imports that need special handling
# Archive.org with enhanced proximity support
class ArchiveOrgSearch:
    """Archive.org search with full-text proximity using Lucene ~N operator"""
    def __init__(self):
        # Use lazy loading to get the base class
        if ARCHIVEORG_AVAILABLE:
            base_class = get_engine('archiveorg')
            self.base = base_class()
        else:
            self.base = None
        
    def search(self, query, max_results=10):
        """Search using Archive.org's proximity support"""
        if not self.base:
            return []
        
        # Convert our proximity format to Archive.org's Lucene syntax
        # Archive.org uses "term1 term2"~N for proximity
        if ' * ' in query:
            # Simple wildcard - Archive.org supports this directly
            return self.base.search(query, max_results)
        
        # Check if it's already in Lucene proximity format
        if '~' in query and query.count('"') >= 2:
            # Already formatted for Archive.org proximity
            return self.base.search(query, max_results)
        
        # Try to extract terms for proximity formatting
        import re
        # Look for patterns like: "term1" "term2" or term1 term2
        terms = re.findall(r'"([^"]+)"|([^\s"]+)', query)
        terms = [t[0] or t[1] for t in terms if t[0] or t[1]]
        
        if len(terms) >= 2:
            # Default to proximity of 10 words if not specified
            proximity_query = f'"{" ".join(terms)}"~10'
            results = self.base.search(proximity_query, max_results)
            if results:
                return results
        
        # Fallback to regular search
        return self.base.search(query, max_results)
    
    async def search_async(self, query, max_results=10):
        """Async wrapper for proximity search"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.search, query, max_results)

# Simple wrapper classes for engines without proximity support
class NewsAPISearch:
    """NewsAPI for phrase searches"""
    def __init__(self, api_key='YOUR_NEWSAPI_KEY'):
        self.api_key = api_key

    def search(self, query, max_results=10):
        url = "https://newsapi.org/v2/everything"
        params = {'q': query, 'apiKey': self.api_key, 'pageSize': max_results}
        response = requests.get(url, params=params)
        if response.status_code == 200:
            articles = response.json().get('articles', [])
            return [{'url': a['url'], 'title': a['title'], 'snippet': a['description']} for a in articles]
        return []

class AlephSearch:
    """Aleph OCRP for proximity/wildcards"""
    def search(self, query, max_results=10):
        # Assume API endpoint; use query_string syntax
        url = "https://aleph.occrp.org/api/2/entities"  # May require auth
        params = {'filter:q': query, 'limit': max_results}
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json().get('results', [])
            return [{'url': d.get('links', {}).get('self', ''), 'title': d['name'], 'snippet': d.get('snippet', '')} for d in data]
        return []

class XSearch:
    """X (Twitter) search using Grok tools"""
    async def search_async(self, query, max_results=10):
        # Use x_keyword_search for exact/phrase
        from xai_tools import x_keyword_search  # Assume tool access
        results = await x_keyword_search(query=query, limit=max_results)
        return [{'url': r['link'], 'title': r['user'], 'snippet': r['text']} for r in results]

# Define proximity types
ProximityMode = Literal["at_least", "exactly", "fewer_than", "wildcard"]

class ProximitySyntaxError(ValueError):
    pass

class ProximitySearcher:
    """
    Standardized Searcher class for proximity searches.
    This class is designed to be imported and used by main.py.
    """
    PROXIMITY_REGEX = re.compile(r'^(.*)\s+(\d+<|<s*\d+|~\d+|\*\s*(?:\d+)?)\s+(.*)$', re.IGNORECASE)
    OPERATOR_REGEX = re.compile(r'(\d+<)|(<\s*(\d+))|(~(\d+))|(\*\s*(?:(\d+))?)')

    def __init__(self, additional_args: List[str] = None):
        self.additional_args = additional_args or []
        self.engines = self._initialize_engines()

    def _initialize_engines(self) -> Dict:
        """CHANGED: Now uses lazy loading through EngineManager"""
        engine_manager = EngineManager()
        
        # Define which engines we want to use
        engine_names = [
            'google', 'bing', 'yandex', 'duckduckgo', 'brave',
            'yep', 'boardreader', 'exa', 'gdelt', 'grok',
            'publicwww', 'socialsearcher'
        ]
        
        # Get engine instances (only loads them when accessed)
        engines = engine_manager.get_engines(engine_names)
        
        # Add custom engines
        engines['archive'] = ArchiveOrgSearch()
        engines['newsapi'] = NewsAPISearch()
        engines['aleph'] = AlephSearch()
        engines['x'] = XSearch()
        
        return engines

    # The rest of the class remains exactly the same...
    def parse_query(self, query: str) -> Tuple[str, str, int, ProximityMode]:
        """Parse proximity or wildcard operators"""
        # First, check for wildcards like "term1 *3 term2"
        operators = self.parse_wildcards(query)
        if operators:
            parts = query.replace('"', '').split()
            for i, count in operators.items():
                if i > 0 and i < len(parts) - 1:
                    term1 = parts[i-1].strip()
                    term2 = parts[i+1].strip()
                    return term1, term2, count, 'exactly'  # Treat as exactly N words

        # Fall back to proximity regex
        match = self.PROXIMITY_REGEX.match(query.strip())
        if not match:
            raise ProximitySyntaxError("Invalid query. Use 'term1 OP term2' or 'term1 *N term2'.")

        term1 = match.group(1).strip().strip('"')
        operator_part = match.group(2).strip()
        term2 = match.group(3).strip().strip('"')

        op_match = self.OPERATOR_REGEX.match(operator_part)
        if not op_match:
            raise ProximitySyntaxError(f"Invalid operator: {operator_part}")

        if op_match.group(1):  # N<
            distance = int(op_match.group(1)[:-1])
            mode = "at_least"
        elif op_match.group(2):  # <N
            distance = int(op_match.group(3))
            mode = "fewer_than"
        elif op_match.group(4):  # ~N
            distance = int(op_match.group(5))
            mode = "exactly"
        elif op_match.group(6):  # *N or *
            mode = "wildcard"
            distance = int(op_match.group(7)) if op_match.group(7) else 1
        else:
            raise ProximitySyntaxError(f"Unknown operator: {operator_part}")

        if distance <= 0:
            raise ProximitySyntaxError("Distance must be positive.")

        logger.info(f"Parsed query: term1='{term1}', term2='{term2}', distance={distance}, mode='{mode}'")
        return term1, term2, distance, mode

    # ... rest of the methods remain the same ...
    # (I'm not copying all methods to save space, but they would remain unchanged)

# Keep the main block for direct testing if needed
if __name__ == "__main__":
    async def main_test():
        searcher = ProximitySearcher()
        print("\n=== Proximity/Wildcard Search (Lazy Loading Test) ===")
        print("Syntax: term1 OP term2 (OP: N<, <N, ~N, *N, *, **, ***)")
        print("Type 'exit' to end.")

        while True:
            try:
                query = input("\nQuery: ").strip()
                if query.lower() in ['exit', 'quit']:
                    break
                if not query:
                    continue

                # Test lazy loading - engines will only load when used
                print("Searching... (engines will load on first use)")
                results_data = await searcher.search(query)

                if 'error' in results_data:
                    print(f"Error: {results_data['error']}")
                    continue

                print(f"\nFound {results_data['total_unique_results']} results.")

                for i, result in enumerate(results_data['results'][:20], 1):
                    print(f"\n{i}. {result.get('title', 'No Title')} [{', '.join(result.get('source_engines', []))}]")
                    print(f"   URL: {result.get('url', 'N/A')}")
                    snippet = result.get('snippet', '')[:250] + '...' if len(result.get('snippet', '')) > 250 else result.get('snippet', '')
                    print(f"   Snippet: {snippet}")

            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {str(e)}")
                traceback.print_exc()

    asyncio.run(main_test())