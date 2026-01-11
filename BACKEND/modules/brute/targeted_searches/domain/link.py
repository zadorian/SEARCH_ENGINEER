#!/usr/bin/env python3
"""
Link Search - Find pages that link to a specific URL or domain.
Supports link: operator and intelligent fallbacks.
"""

import sys
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import logging
from datetime import datetime
import os
import asyncio
import json
from urllib.parse import urlparse

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import search engines from engines directory
sys.path.insert(0, str(Path(__file__).parent.parent / 'engines'))

# Set up logger
logger = logging.getLogger(__name__)

# Import search engines
try:
    from exact_phrase_recall_runner_google import GoogleSearch
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

try:
    from exact_phrase_recall_runner_bing import BingSearch
    BING_AVAILABLE = True
except ImportError:
    BING_AVAILABLE = False

try:
    from exact_phrase_recall_runner_yandex import YandexSearch
    YANDEX_AVAILABLE = True
except ImportError:
    YANDEX_AVAILABLE = False

try:
    from exact_phrase_recall_runner_brave import BraveSearch
    BRAVE_AVAILABLE = True
except ImportError:
    BRAVE_AVAILABLE = False

try:
    from exact_phrase_recall_runner_duckduck import MaxExactDuckDuckGo as DuckDuckGoSearch
    DUCKDUCKGO_AVAILABLE = True
except ImportError:
    DUCKDUCKGO_AVAILABLE = False

class LinkSearcher:
    """Search for pages linking to a specific URL"""
    
    def __init__(self):
        self.engines = {}
        if GOOGLE_AVAILABLE: self.engines['google'] = GoogleSearch()
        if BING_AVAILABLE: self.engines['bing'] = BingSearch()
        if YANDEX_AVAILABLE: self.engines['yandex'] = YandexSearch()
        if BRAVE_AVAILABLE: self.engines['brave'] = BraveSearch()
        if DUCKDUCKGO_AVAILABLE: self.engines['duckduckgo'] = DuckDuckGoSearch()
        
    def parse_query(self, query: str) -> Tuple[str, str]:
        """Parse link: operator"""
        match = re.search(r'link:([^\s]+)', query, re.IGNORECASE)
        if match:
            target_url = match.group(1)
            return target_url, query.replace(match.group(0), '').strip()
        
        # Implicit mode: if query looks like a URL/domain and no other operators
        if '.' in query and ' ' not in query and not ':' in query:
            return query, ''
            
        return '', query

    def normalize_url(self, url: str) -> str:
        """Strip protocol and www for broader matching"""
        url = url.lower()
        url = re.sub(r'^https?://', '', url)
        url = re.sub(r'^www\.', '', url)
        return url.strip('/')

    def generate_variations(self, target_url: str, keywords: str) -> List[Tuple[str, str]]:
        """Generate L1/L2/L3 variations"""
        variations = []
        clean_url = self.normalize_url(target_url)
        
        # L1: Native Operator
        # Note: Google's link: operator is deprecated/weak, but Bing's is decent
        l1_query = f"link:{target_url} {keywords}".strip()
        variations.append((l1_query, 'L1'))
        
        # L2: Content/URL Mention (The real "link" search nowadays)
        # Searching for the domain string finds mentions and unlinked citations
        l2_query_1 = f'"{clean_url}" -site:{clean_url} {keywords}'.strip()
        variations.append((l2_query_1, 'L2'))
        
        # L2: InURL (Links might pass parameters with the URL)
        l2_query_2 = f'inurl:"{clean_url}" -site:{clean_url} {keywords}'.strip()
        variations.append((l2_query_2, 'L2'))
        
        # L3: Broad Domain Search (Brute)
        # Search for just the domain name part
        try:
            domain = clean_url.split('/')[0]
            if domain != clean_url:
                l3_query = f'"{domain}" -site:{domain} {keywords}'.strip()
                variations.append((l3_query, 'L3'))
        except Exception as e:

            print(f"[BRUTE] Error: {e}")

            pass
            
        return variations

    async def search(self, query: str, max_results: int = 50) -> Dict:
        target_url, keywords = self.parse_query(query)
        
        if not target_url:
            print("No target URL found in query (use link:example.com)")
            return {'error': 'No target URL found'}
            
        print(f"\nLink search detected: {target_url}")
        
        results_data = {
            'query': query,
            'target_url': target_url,
            'results': [],
            'stats': {}
        }
        
        seen_urls = set()
        # Exclude the target site itself from results
        target_domain = self.normalize_url(target_url).split('/')[0]
        
        tasks = []
        for engine_name, engine in self.engines.items():
            tasks.append(self._run_engine(engine_name, engine, target_url, keywords, max_results))
            
        outputs = await asyncio.gather(*tasks, return_exceptions=True)
        
        for output in outputs:
            if isinstance(output, tuple):
                eng_name, results = output
                valid_results = []
                for r in results:
                    # Filter out self-links
                    res_domain = self.normalize_url(r['url']).split('/')[0]
                    if target_domain in res_domain:
                        continue
                        
                    if r['url'] not in seen_urls:
                        seen_urls.add(r['url'])
                        r['source'] = eng_name
                        valid_results.append(r)
                
                results_data['results'].extend(valid_results)
                results_data['stats'][eng_name] = len(valid_results)
                
        return results_data

    async def _run_engine(self, name, engine, target_url, keywords, max_results):
        variations = self.generate_variations(target_url, keywords)
        all_results = []
        limit = max(10, max_results // len(variations))
        
        for q, strat in variations:
            try:
                # Run sync search in executor
                loop = asyncio.get_event_loop()
                res = await loop.run_in_executor(None, engine.search, q, limit)
                if res:
                    for r in res:
                        r['strategy'] = strat
                        r['query'] = q
                    all_results.extend(res)
            except Exception as e:
                logger.warning(f"{name} error on {q}: {e}")
                
        return name, all_results

async def main():
    if len(sys.argv) < 2:
        print("Usage: python3 link.py \"link:example.com\"")
        return
    
    query = sys.argv[1]
    searcher = LinkSearcher()
    data = await searcher.search(query)
    
    print(f"\nFound {len(data['results'])} results.")
    for i, r in enumerate(data['results'][:10], 1):
        print(f"{i}. [{r['source']}] {r.get('title')}")
        print(f"   {r.get('url')}")
        print(f"   {r.get('snippet')[:100]}...")

if __name__ == "__main__":
    asyncio.run(main())
