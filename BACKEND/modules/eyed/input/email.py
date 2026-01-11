#!/usr/bin/env python3
"""
EYE-D Email Search Engine
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from unified_osint import UnifiedSearcher
    EYE_D_AVAILABLE = True
except ImportError:
    EYE_D_AVAILABLE = False

# Import WhoisXMLAPI for reverse WHOIS
try:
    from modules.alldom.whoisxmlapi import reverse_whois_search
    WHOISXML_AVAILABLE = True
except ImportError:
    WHOISXML_AVAILABLE = False

class EyeDEmailEngine:
    code = 'EDE'
    name = 'EYE-D Email'

    def __init__(self, email: str):
        self.email = email
        self.osint_client = UnifiedSearcher() if EYE_D_AVAILABLE else None

    async def search_async(self) -> Dict[str, Any]:
        print(f"📧 Searching for email: {self.email}")

        results = {
            'query': self.email,
            'query_type': 'EYE-D',
            'subtype': 'email',
            'results': [],
            'entities': [],
            'timestamp': datetime.now().isoformat()
        }

        if not self.osint_client:
            results['error'] = "EYE-D module not available"
            return results

        try:
            # Use UnifiedSearcher
            osint_results = self.osint_client.search(self.email)

            for source, data in osint_results.items():
                if data and not (isinstance(data, dict) and data.get('error')):
                    results['results'].append({
                        'source': source,
                        'data': data,
                        'entity_type': 'email',
                        'entity_value': self.email
                    })

            # Reverse WHOIS
            if WHOISXML_AVAILABLE:
                try:
                    print(f"🔍 Running reverse WHOIS for email: {self.email}")
                    whois_result = reverse_whois_search(self.email, "basicSearchTerms", search_type="historic")
                    if whois_result and whois_result.get('domains_count', 0) > 0:
                        results['results'].append({
                            'source': 'whoisxmlapi_reverse',
                            'data': whois_result,
                            'entity_type': 'email',
                            'entity_value': self.email,
                            'domains_found': whois_result.get('domains_count')
                        })
                except Exception as e:
                    print(f"⚠️ Reverse WHOIS failed: {e}")

            results['total_results'] = len(results['results'])
            print(f"✅ Found {results['total_results']} results for email {self.email}")

        except Exception as e:
            results['error'] = str(e)
            print(f"❌ Error searching email: {e}")

        return results

    def search(self) -> List[Dict[str, Any]]:
        """Sync wrapper for search."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            results = loop.run_until_complete(self.search_async())
            # Format for output
            web_results = []
            for i, r in enumerate(results.get('results', []), 1):
                data = r.get('data', {})
                snippet = str(data)[:300]
                if isinstance(data, dict):
                    snippet = ' | '.join([f"{k}: {str(v)[:80]}" for k, v in list(data.items())[:8]])
                
                web_results.append({
                    'url': f"https://dehashed.com/search?query={self.email}", # Generic link
                    'title': f"Email: {self.email} (from {r.get('source','unknown')})",
                    'snippet': snippet,
                    'engine': self.name,
                    'source': r.get('source','unknown').upper(),
                    'rank': i
                })
            return web_results
        finally:
            loop.close()