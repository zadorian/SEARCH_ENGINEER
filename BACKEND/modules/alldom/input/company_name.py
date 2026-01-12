#!/usr/bin/env python3
"""
ALLDOM Company Name Input Handler
Finds domains associated with a company name via Reverse WHOIS.
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

class AlldomCompanyNameEngine:
    code = 'ADC'
    name = 'ALLDOM Company Name'
    _code = 13  # Legend code: company_name

    def __init__(self, company_name: str):
        self.company_name = company_name

    async def search_async(self) -> Dict[str, Any]:
        """
        Find domains registered by this company.
        """
        print(f"🏢 [ALLDOM] Reverse WHOIS for company: {self.company_name}")
        
        try:
            result = await asyncio.to_thread(whois_lookup, self.company_name, query_type="terms")
            return result
        except Exception as e:
            return {"error": str(e), "query": self.company_name}

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
                    'match_type': 'registrant_org',
                    'match_value': self.company_name
                })
            return formatted_results
        finally:
            loop.close()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        engine = AlldomCompanyNameEngine(sys.argv[1])
        print(engine.search())
    else:
        print("Usage: python company_name.py <company>")
