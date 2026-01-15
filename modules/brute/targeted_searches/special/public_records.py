#!/usr/bin/env python3
"""
Public Records Search - Search for FOI requests, government transparency data, and public records.
Supports foi: and records: operators.
"""

import sys
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import logging
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

class PublicRecordsSearcher:
    """Search for public records and FOI requests"""
    
    # Known FOI/Transparency portals
    FOI_DOMAINS = [
        'whatdotheyknow.com',   # UK
        'muckrock.com',         # US
        'asktheeu.org',         # EU
        'foia.gov',             # US
        'righttoknow.org.au',   # Australia
        'transparency.org',     # Global
        'fragdenstaat.de',      # Germany
        'madada.fr',            # France
        'dostip.bg',            # Bulgaria
        'informio.sk'           # Slovakia
    ]
    
    def __init__(self):
        self.engines = {}
        if GOOGLE_AVAILABLE: self.engines['google'] = GoogleSearch()
        if BING_AVAILABLE: self.engines['bing'] = BingSearch()
        if BRAVE_AVAILABLE: self.engines['brave'] = BraveSearch()
        if DUCKDUCKGO_AVAILABLE: self.engines['duckduckgo'] = DuckDuckGoSearch()
        
    def parse_query(self, query: str) -> Tuple[str, str]:
        """Parse foi: or records: operator"""
        match = re.search(r'(?:foi|records):([^\s]+)', query, re.IGNORECASE)
        if match:
            target = match.group(1)
            return target, query.replace(match.group(0), '').strip()
        return '', query

    def generate_variations(self, topic: str, keywords: str) -> List[Tuple[str, str]]:
        """Generate L1/L2/L3 variations"""
        variations = []
        
        # L1: Site Search on known FOI portals
        site_parts = [f"site:{d}" for d in self.FOI_DOMAINS[:5]] # Top 5
        l1_query_1 = f"({' OR '.join(site_parts)}) {topic} {keywords}".strip()
        variations.append((l1_query_1, 'L1'))
        
        # L2: Keywords (Tricks)
        foi_terms = '("freedom of information" OR "public records" OR "right to know" OR "access to information")'
        l2_query = f'{foi_terms} "{topic}" {keywords}'.strip()
        variations.append((l2_query, 'L2'))
        
        # L3: Government Domain Documents (Brute)
        gov_sites = '(site:.gov OR site:.govt OR site:.gov.uk OR site:.europa.eu)'
        doc_types = '(filetype:pdf OR filetype:doc OR filetype:docx OR filetype:xls)'
        l3_query = f'{gov_sites} {doc_types} "{topic}" {keywords}'.strip()
        variations.append((l3_query, 'L3'))
            
        return variations

    async def search(self, query: str, max_results: int = 50) -> Dict:
        topic, keywords = self.parse_query(query)
        
        if not topic:
            # If no operator, assume the whole query is the topic if script called directly
            topic = query
            keywords = ""
            
        print(f"\nPublic Records search detected: {topic}")
        
        results_data = {
            'query': query,
            'topic': topic,
            'results': [],
            'stats': {}
        }
        
        seen_urls = set()
        tasks = []
        
        for engine_name, engine in self.engines.items():
            tasks.append(self._run_engine(engine_name, engine, topic, keywords, max_results))
            
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

    async def _run_engine(self, name, engine, topic, keywords, max_results):
        variations = self.generate_variations(topic, keywords)
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
        print("Usage: python3 public_records.py \"foi:ufo\"")
        return
    
    query = sys.argv[1]
    searcher = PublicRecordsSearcher()
    data = await searcher.search(query)
    
    print(f"\nFound {len(data['results'])} results.")
    for i, r in enumerate(data['results'][:10], 1):
        print(f"{i}. [{r['source']} - {r.get('strategy', '?')}] {r.get('title')}")
        print(f"   {r.get('url')}")

if __name__ == "__main__":
    asyncio.run(main())
