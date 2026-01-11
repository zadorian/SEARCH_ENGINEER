#!/usr/bin/env python3
"""
EYE-D Phone Search Engine
"""

import asyncio
import re
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

try:
    from modules.alldom.whoisxmlapi import reverse_whois_search
    WHOISXML_AVAILABLE = True
except ImportError:
    WHOISXML_AVAILABLE = False

class EyeDPhoneEngine:
    code = 'EDP2'
    name = 'EYE-D Phone'

    def __init__(self, phone: str):
        self.phone = phone
        self.osint_client = UnifiedSearcher() if EYE_D_AVAILABLE else None

    async def search_async(self) -> Dict[str, Any]:
        print(f"📱 Searching for phone: {self.phone}")

        results = {
            'query': self.phone,
            'query_type': 'EYE-D',
            'subtype': 'phone',
            'results': [],
            'entities': [],
            'timestamp': datetime.now().isoformat()
        }

        if not self.osint_client:
            results['error'] = "EYE-D module not available"
            return results

        try:
            normalized_phone = re.sub(r'[^\d+]', '', self.phone)
            osint_results = self.osint_client.search(normalized_phone)

            for source, data in osint_results.items():
                if data and not (isinstance(data, dict) and data.get('error')):
                    results['results'].append({
                        'source': source,
                        'data': data,
                        'entity_type': 'phone',
                        'entity_value': self.phone
                    })

            # Reverse WHOIS
            if WHOISXML_AVAILABLE:
                try:
                    clean_number = re.sub(r'\D', '', self.phone)
                    print(f"🔍 Running reverse WHOIS for phone: {clean_number}")
                    whois_result = reverse_whois_search(clean_number, "basicSearchTerms", search_field="telephone", search_type="historic")
                    if whois_result and whois_result.get('domains_count', 0) > 0:
                        results['results'].append({
                            'source': 'whoisxmlapi_reverse',
                            'data': whois_result,
                            'entity_type': 'phone',
                            'entity_value': self.phone
                        })
                except Exception as e:
                    print(f"⚠️ Reverse WHOIS failed: {e}")

            results['total_results'] = len(results['results'])
            print(f"✅ Found {results['total_results']} results for phone {self.phone}")

        except Exception as e:
            results['error'] = str(e)
            print(f"❌ Error searching phone: {e}")

        return results

    def search(self) -> List[Dict[str, Any]]:
        """Sync wrapper for search."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            results = loop.run_until_complete(self.search_async())
            web_results = []
            for i, r in enumerate(results.get('results', []), 1):
                data = r.get('data', {})
                snippet = str(data)[:300]
                if isinstance(data, dict):
                    snippet = ' | '.join([f"{k}: {str(v)[:80]}" for k, v in list(data.items())[:8]])
                
                web_results.append({
                    'url': f"https://truecaller.com/search/{self.phone.replace('+','%2B')}",
                    'title': f"Phone: {self.phone} (from {r.get('source','unknown')})",
                    'snippet': snippet,
                    'engine': self.name,
                    'source': r.get('source','unknown').upper(),
                    'rank': i
                })
            return web_results
        finally:
            loop.close()