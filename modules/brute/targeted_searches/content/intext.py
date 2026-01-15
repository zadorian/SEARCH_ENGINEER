#!/usr/bin/env python3
"""
InText Search - Search for terms specifically within the body text of pages.
Supports intext: and inbody: operators.
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

class InTextSearcher:
    """Search for terms within page body text using intext/inbody operators"""
    
    ENGINE_OPERATORS = {
        'google': {'intext': 'intext:', 'allintext': 'allintext:'},
        'bing': {'intext': 'inbody:', 'allintext': 'inbody:'}, # Bing prefers inbody:
        'yandex': {'intext': 'intext:', 'allintext': 'intext:'}, # Yandex is flexible
        'brave': {'intext': 'inbody:', 'allintext': 'inbody:'},
        'duckduckgo': {'intext': 'intext:', 'allintext': 'intext:'}
    }
    
    def __init__(self):
        self.engines = {}
        if GOOGLE_AVAILABLE: self.engines['google'] = GoogleSearch()
        if BING_AVAILABLE: self.engines['bing'] = BingSearch()
        if YANDEX_AVAILABLE: self.engines['yandex'] = YandexSearch()
        if BRAVE_AVAILABLE: self.engines['brave'] = BraveSearch()
        if DUCKDUCKGO_AVAILABLE: self.engines['duckduckgo'] = DuckDuckGoSearch()
        
    def parse_query(self, query: str) -> Tuple[str, str, str]:
        """Parse intext operators"""
        # Check for intext: or inbody:
        match = re.search(r'(?:intext|inbody):([^\s]+)', query, re.IGNORECASE)
        if match:
            term = match.group(1)
            keywords = re.sub(r'(?:intext|inbody):[^\s]+\s*', '', query, flags=re.IGNORECASE).strip()
            return 'intext', term, keywords
            
        match_all = re.search(r'(?:allintext|allinbody):(.+)', query, re.IGNORECASE)
        if match_all:
            term = match_all.group(1).strip()
            return 'allintext', term, ''
            
        return 'none', '', query

    def generate_variations(self, operator: str, term: str, keywords: str, engine: str) -> List[Tuple[str, str]]:
        """Generate L1/L2/L3 variations"""
        variations = []
        ops = self.ENGINE_OPERATORS.get(engine, self.ENGINE_OPERATORS['google'])
        
        # L1: Native Operator
        native_op = ops.get(operator, 'intext:')
        l1_query = f"{native_op}{term} {keywords}".strip()
        variations.append((l1_query, 'L1'))
        
        # L2: Fallback to Intitle (Correlation)
        # If text is important, it might be in the title too
        l2_query = f"intitle:{term} {keywords}".strip()
        variations.append((l2_query, 'L2'))
        
        # L3: Broad Match + Filter
        # Just search for the term as a mandatory keyword
        l3_query = f'"{term}" {keywords}'.strip()
        variations.append((l3_query, 'L3'))
        
        return variations

    async def search(self, query: str, max_results: int = 50) -> Dict:
        operator, term, keywords = self.parse_query(query)
        
        if operator == 'none':
            # Treat whole query as intext if no operator provided (implicit mode)
            term = query
            keywords = ""
            operator = 'intext'
            
        print(f"\nInText search detected: {term}")
        
        results_data = {
            'query': query,
            'term': term,
            'results': [],
            'stats': {}
        }
        
        seen_urls = set()
        tasks = []
        
        for engine_name, engine in self.engines.items():
            tasks.append(self._run_engine(engine_name, engine, operator, term, keywords, max_results))
            
        outputs = await asyncio.gather(*tasks, return_exceptions=True)
        
        for output in outputs:
            if isinstance(output, tuple):
                eng_name, results = output
                valid_results = []
                for r in results:
                    # L3 Filtering: Snippet must contain term
                    strategy = r.get('strategy', 'L1')
                    if strategy == 'L3':
                        snippet = r.get('snippet', '').lower()
                        if term.lower() not in snippet:
                            continue
                            
                    if r['url'] not in seen_urls:
                        seen_urls.add(r['url'])
                        r['source'] = eng_name
                        valid_results.append(r)
                
                results_data['results'].extend(valid_results)
                results_data['stats'][eng_name] = len(valid_results)
                
        return results_data

    async def _run_engine(self, name, engine, operator, term, keywords, max_results):
        variations = self.generate_variations(operator, term, keywords, name)
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
        print("Usage: python3 intext.py \"intext:keyword\"")
        return
    
    query = sys.argv[1]
    searcher = InTextSearcher()
    data = await searcher.search(query)
    
    print(f"\nFound {len(data['results'])} results.")
    for i, r in enumerate(data['results'][:10], 1):
        print(f"{i}. [{r['source']}] {r.get('title')}")
        print(f"   {r.get('url')}")
        print(f"   {r.get('snippet')[:100]}...")

if __name__ == "__main__":
    asyncio.run(main())
