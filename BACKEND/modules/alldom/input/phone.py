#!/usr/bin/env python3
"""
ALLDOM Phone Input Handler
Finds domains associated with a phone number via Reverse WHOIS.
"""

import asyncio
from typing import Dict, Any, List

try:
    from modules.alldom.whoisxmlapi import whois_lookup
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parents[2]))
    from modules.alldom.whoisxmlapi import whois_lookup

class AlldomPhoneEngine:
    code = 'ADP'
    name = 'ALLDOM Phone'
    _code = 2  # Legend code: phone

    def __init__(self, phone: str):
        self.phone = phone

    async def search_async(self) -> Dict[str, Any]:
        """
        Find domains registered by this phone number.
        """
        print(f"📱 [ALLDOM] Reverse WHOIS for phone: {self.phone}")
        
        try:
            result = await asyncio.to_thread(whois_lookup, self.phone, query_type="phone")
            return result
        except Exception as e:
            return {"error": str(e), "query": self.phone}

    def search(self) -> List[Dict[str, Any]]:
        """Sync wrapper returning list of domains."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(self.search_async())
            domains = result.get('domains', [])
            
            formatted_results = []
            for d in domains:
                formatted_results.append({
                    'domain': d,
                    'source': 'reverse_whois',
                    'match_type': 'registrant_phone',
                    'match_value': self.phone
                })
            return formatted_results
        finally:
            loop.close()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        engine = AlldomPhoneEngine(sys.argv[1])
        print(engine.search())
    else:
        print("Usage: python phone.py <phone>")
