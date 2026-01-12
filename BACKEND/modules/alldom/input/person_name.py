#!/usr/bin/env python3
"""
ALLDOM Person Name Input Handler
Finds domains associated with a person's name via Reverse WHOIS.
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

class AlldomPersonNameEngine:
    code = 'ADN'
    name = 'ALLDOM Person Name'
    _code = 7  # Legend code: person_name

    def __init__(self, person_name: str):
        self.person_name = person_name

    async def search_async(self) -> Dict[str, Any]:
        """
        Find domains registered by this person.
        """
        print(f"👤 [ALLDOM] Reverse WHOIS for person: {self.person_name}")
        
        try:
            result = await asyncio.to_thread(whois_lookup, self.person_name, query_type="terms")
            return result
        except Exception as e:
            return {"error": str(e), "query": self.person_name}

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
                    'match_type': 'registrant_name',
                    'match_value': self.person_name
                })
            return formatted_results
        finally:
            loop.close()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        engine = AlldomPersonNameEngine(sys.argv[1])
        print(engine.search())
    else:
        print("Usage: python person_name.py <name>")
