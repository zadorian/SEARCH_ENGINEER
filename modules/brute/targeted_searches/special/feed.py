#!/usr/bin/env python3
"""
Feed Search - Find RSS/Atom feeds for a specific domain or topic.
Supports feed: operator and intelligent fallbacks.
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
    from exact_phrase_recall_runner_brave import BraveSearch
    BRAVE_AVAILABLE = True
except ImportError:
    BRAVE_AVAILABLE = False

try:
    from exact_phrase_recall_runner_duckduck import MaxExactDuckDuckGo as DuckDuckGoSearch
    DUCKDUCKGO_AVAILABLE = True
except ImportError:
    DUCKDUCKGO_AVAILABLE = False

class FeedSearcher:
    """Search for RSS/Atom feeds"""
    
    def __init__(self):
        self.engines = {}
        if GOOGLE_AVAILABLE: self.engines['google'] = GoogleSearch()
        if BING_AVAILABLE: self.engines['bing'] = BingSearch()
        if BRAVE_AVAILABLE: self.engines['brave'] = BraveSearch()
        if DUCKDUCKGO_AVAILABLE: self.engines['duckduckgo'] = DuckDuckGoSearch()
        
    def parse_query(self, query: str) -> Tuple[str, str]:
        """Parse feed: operator"""
        match = re.search(r'feed:([^\s]+)', query, re.IGNORECASE)
        if match:
            target = match.group(1)
            return target, query.replace(match.group(0), '').strip()
        return '', query

    def generate_variations(self, target: str, keywords: str) -> List[Tuple[str, str]]:
        """Generate L1/L2/L3 variations"""
        variations = []
        
        # L1: Native Operator (rarely supported, but worth a try)
        l1_query = f"feed:{target} {keywords}".strip()
        variations.append((l1_query, 'L1'))
        
        # Determine if target is a domain or a topic
        is_domain = '.' in target and ' ' not in target
        
        if is_domain:
            # L2: Filetype Search on Domain
            l2_query_1 = f"site:{target} (filetype:rss OR filetype:xml OR filetype:atom) {keywords}".strip()
            variations.append((l2_query_1, 'L2'))
            
            # L3: InURL Search on Domain
            l3_query_1 = f"site:{target} (inurl:rss OR inurl:feed OR inurl:atom) {keywords}".strip()
            variations.append((l3_query_1, 'L3'))
            
            # L3: Broad Title Search
            l3_query_2 = f'site:{target} intitle:"rss feed" OR intitle:"atom feed" {keywords}'.strip()
            variations.append((l3_query_2, 'L3'))
            
        else:
            # Topic-based feed search
            # L2: Filetype Global
            l2_query_1 = f'"{target}" (filetype:rss OR filetype:xml OR filetype:atom) {keywords}'.strip()
            variations.append((l2_query_1, 'L2'))
            
            # L3: InURL Global
            l3_query_1 = f'"{target}" (inurl:rss OR inurl:feed OR inurl:atom) {keywords}'.strip()
            variations.append((l3_query_1, 'L3'))
            
        return variations

    async def search(self, query: str, max_results: int = 50) -> Dict:
        target, keywords = self.parse_query(query)
        
        # If no operator, assume the whole query is the target topic
        if not target:
            target = query
            keywords = ""
            
        print(f"\nFeed search detected: {target}")
        
        results_data = {
            'query': query,
            'target': target,
            'results': [],
            'stats': {}
        }
        
        seen_urls = set()
        tasks = []
        
        for engine_name, engine in self.engines.items():
            tasks.append(self._run_engine(engine_name, engine, target, keywords, max_results))
            
        outputs = await asyncio.gather(*tasks, return_exceptions=True)
        
        for output in outputs:
            if isinstance(output, tuple):
                eng_name, results = output
                valid_results = []
                for r in results:
                    if r['url'] not in seen_urls:
                        seen_urls.add(r['url'])
                        r['source'] = eng_name
                        valid_results.append(r)
                
                results_data['results'].extend(valid_results)
                results_data['stats'][eng_name] = len(valid_results)
                
        return results_data

    async def _run_engine(self, name, engine, target, keywords, max_results):
        variations = self.generate_variations(target, keywords)
        all_results = []
        limit = max(10, max_results // len(variations))
        
        for q, strat in variations:
            try:
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
        print("Usage: python3 feed.py \"feed:example.com\"")
        return
    
    query = sys.argv[1]
    searcher = FeedSearcher()
    data = await searcher.search(query)
    
    print(f"\nFound {len(data['results'])} results.")
    for i, r in enumerate(data['results'][:10], 1):
        print(f"{i}. [{r['source']} - {r.get('strategy', '?')}] {r.get('title')}")
        print(f"   {r.get('url')}")

if __name__ == "__main__":
    asyncio.run(main())
