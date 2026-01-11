#!/usr/bin/env python3
"""
Anchor Text Search - Find pages linked to with specific anchor text using Majestic.
Useful for finding pages that are described by your keyword, even if they don't mention it themselves.
"""

import sys
import os
import re
import logging
import requests
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

class AnchorSearcher:
    """Search for pages based on inbound anchor text using Majestic"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('MAJESTIC_API_KEY')
        self.base_url = "https://api.majestic.com/api/json"
        
        if not self.api_key:
            logger.warning("MAJESTIC_API_KEY not found. Anchor search will fail.")

    def parse_query(self, query: str) -> Tuple[str, str]:
        """Parse anchor: operator or domain"""
        # format: anchor:"phrase" site:domain.com
        # or just: domain.com "phrase"
        
        target_domain = None
        search_phrase = query
        
        # Extract site: if present
        site_match = re.search(r'site:([^\s]+)', query)
        if site_match:
            target_domain = site_match.group(1)
            search_phrase = query.replace(site_match.group(0), '').strip()
            
        # Extract anchor: if present
        anchor_match = re.search(r'anchor:(?:"([^"]+)"|([^ \n]+))', search_phrase)
        if anchor_match:
            # If explicit anchor: operator, use that as the phrase
            search_phrase = anchor_match.group(1) or anchor_match.group(2)
            
        return target_domain, search_phrase.strip('"')

    async def search(self, query: str, max_results: int = 50) -> Dict:
        target_domain, phrase = self.parse_query(query)
        
        if not self.api_key:
            return {'error': 'Majestic API key not configured'}
            
        if not target_domain:
            # If no domain specified, we can't easily search "all of Majestic" for anchor text
            # efficiently without a seed. 
            # Strategy: Require a domain, or use results from a previous search?
            # For CLI tool, let's require a domain or error out.
            return {'error': 'Target domain required (use site:domain.com)'}

        logger.info(f"Searching backlinks of {target_domain} for anchor text: '{phrase}'")
        
        results = []
        stats = {'processed_backlinks': 0, 'matches': 0}
        
        try:
            # Run synchronous API call in executor
            loop = asyncio.get_event_loop()
            backlinks = await loop.run_in_executor(
                None, 
                self._fetch_backlinks, 
                target_domain, 
                max_results * 5 # Fetch more to filter
            )
            
            stats['processed_backlinks'] = len(backlinks)
            
            for link in backlinks:
                anchor_text = link.get('AnchorText', '')
                target_url = link.get('TargetURL', '')
                
                if not anchor_text or not target_url:
                    continue
                    
                # Check if anchor text matches our phrase
                if phrase.lower() in anchor_text.lower():
                    stats['matches'] += 1
                    results.append({
                        'title': f"Linked via: '{anchor_text}'",
                        'url': target_url,
                        'snippet': f"Found via backlink from {link.get('SourceURL', 'unknown')}. TrustFlow: {link.get('SourceTrustFlow', 0)}",
                        'source': 'majestic',
                        'anchor_text': anchor_text,
                        'source_url': link.get('SourceURL'),
                        'trust_flow': link.get('SourceTrustFlow'),
                        'citation_flow': link.get('SourceCitationFlow')
                    })
                    
            # Sort by TrustFlow
            results.sort(key=lambda x: x.get('trust_flow', 0), reverse=True)
            
            return {
                'query': query,
                'target_domain': target_domain,
                'phrase': phrase,
                'results': results[:max_results],
                'stats': stats
            }
            
        except Exception as e:
            logger.error(f"Anchor search failed: {e}")
            return {'error': str(e)}

    def _fetch_backlinks(self, domain: str, limit: int) -> List[Dict]:
        """Fetch backlinks from Majestic"""
        params = {
            'app_api_key': self.api_key,
            'cmd': 'GetBackLinkData',
            'item': domain,
            'datasource': 'fresh',
            'Count': limit,
            'Mode': '0',
            'MaxSourceURLsPerRefDomain': '-1'
        }
        
        resp = requests.get(self.base_url, params=params)
        resp.raise_for_status()
        
        data = resp.json()
        if data.get('Code') != 'OK':
            raise Exception(f"Majestic API Error: {data.get('ErrorMessage')}")
            
        return data.get('DataTables', {}).get('BackLinks', {}).get('Data', [])

async def main():
    if len(sys.argv) < 2:
        print("Usage: python3 anchor.py \"site:example.com anchor:keyword\"")
        return
    
    query = sys.argv[1]
    searcher = AnchorSearcher()
    data = await searcher.search(query)
    
    if 'error' in data:
        print(f"Error: {data['error']}")
        return

    print(f"\nFound {len(data['results'])} results with anchor '{data['phrase']}' on {data['target_domain']}")
    for i, r in enumerate(data['results'][:10], 1):
        print(f"{i}. {r['url']}")
        print(f"   Anchor: {r['anchor_text']}")
        print(f"   From: {r['source_url']}")

if __name__ == "__main__":
    asyncio.run(main())