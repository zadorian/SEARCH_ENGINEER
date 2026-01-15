#!/usr/bin/env python3
"""
IP Search - Search for pages related to a specific IP address.
Supports ip: operator and intelligent fallbacks.
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

class IPSearcher:
    """Search for pages related to an IP address"""
    
    def __init__(self):
        self.engines = {}
        if GOOGLE_AVAILABLE: self.engines['google'] = GoogleSearch()
        if BING_AVAILABLE: self.engines['bing'] = BingSearch()
        if YANDEX_AVAILABLE: self.engines['yandex'] = YandexSearch()
        if BRAVE_AVAILABLE: self.engines['brave'] = BraveSearch()
        if DUCKDUCKGO_AVAILABLE: self.engines['duckduckgo'] = DuckDuckGoSearch()
        
    def parse_query(self, query: str) -> Tuple[str, str]:
        """Parse ip: operator"""
        match = re.search(r'ip:([^\s]+)', query, re.IGNORECASE)
        if match:
            target_ip = match.group(1)
            return target_ip, query.replace(match.group(0), '').strip()
        
        # Implicit mode: check if query looks like an IP
        # Simple IPv4 regex
        ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        match_ip = re.search(ip_pattern, query)
        if match_ip:
            return match_ip.group(0), query.replace(match_ip.group(0), '').strip()
            
        return '', query

    def generate_variations(self, target_ip: str, keywords: str) -> List[Tuple[str, str]]:
        """Generate L1/L2/L3 variations"""
        variations = []
        
        # L1: Native Operator
        l1_query = f"ip:{target_ip} {keywords}".strip()
        variations.append((l1_query, 'L1'))
        
        # L2: InURL (IPs in URLs are common for dev/staging sites)
        l2_query = f'inurl:{target_ip} {keywords}'.strip()
        variations.append((l2_query, 'L2'))
        
        # L3: Broad IP Search (Brute)
        # Just search for the IP string. Useful for finding logs, reports, or lists containing the IP.
        l3_query = f'"{target_ip}" {keywords}'.strip()
        variations.append((l3_query, 'L3'))
            
        return variations

    async def search(self, query: str, max_results: int = 50) -> Dict:
        target_ip, keywords = self.parse_query(query)
        
        if not target_ip:
            print("No target IP found in query (use ip:1.2.3.4)")
            return {'error': 'No target IP found'}
            
        print(f"\nIP search detected: {target_ip}")
        
        results_data = {
            'query': query,
            'target_ip': target_ip,
            'results': [],
            'stats': {}
        }
        
        seen_urls = set()
        tasks = []
        
        for engine_name, engine in self.engines.items():
            tasks.append(self._run_engine(engine_name, engine, target_ip, keywords, max_results))
            
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

    async def _run_engine(self, name, engine, target_ip, keywords, max_results):
        variations = self.generate_variations(target_ip, keywords)
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
        print("Usage: python3 ip.py \"ip:1.1.1.1\"")
        return
    
    query = sys.argv[1]
    searcher = IPSearcher()
    data = await searcher.search(query)
    
    print(f"\nFound {len(data['results'])} results.")
    for i, r in enumerate(data['results'][:10], 1):
        print(f"{i}. [{r['source']}] {r.get('title')}")
        print(f"   {r.get('url')}")
        print(f"   {r.get('snippet')[:100]}...")

if __name__ == "__main__":
    asyncio.run(main())
