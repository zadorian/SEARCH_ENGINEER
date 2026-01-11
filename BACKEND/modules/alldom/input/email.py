#!/usr/bin/env python3
"""
ALLDOM Email Input Handler
Finds domains associated with an email address via Reverse WHOIS.
"""

import asyncio
from typing import Dict, Any, List

try:
    from modules.alldom.whoisxmlapi import whois_lookup
except ImportError:
    # Fallback for local testing or relative path issues
    import sys
    from pathlib import Path
    # Add module root to path
    sys.path.insert(0, str(Path(__file__).parents[2]))
    from modules.alldom.whoisxmlapi import whois_lookup

class AlldomEmailEngine:
    code = 'ADE'
    name = 'ALLDOM Email'

    def __init__(self, email: str):
        self.email = email

    async def search_async(self) -> Dict[str, Any]:
        """
        Find domains registered by this email.
        """
        print(f"📧 [ALLDOM] Reverse WHOIS for email: {self.email}")
        
        # whois_lookup is synchronous but makes network calls, so we wrap it
        try:
            result = await asyncio.to_thread(whois_lookup, self.email, query_type="email")
            return result
        except Exception as e:
            return {"error": str(e), "query": self.email}

    def search(self) -> List[Dict[str, Any]]:
        """Sync wrapper returning list of domains."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(self.search_async())
            domains = result.get('domains', [])
            
            # Format as list of result dicts
            formatted_results = []
            for d in domains:
                formatted_results.append({
                    'domain': d,
                    'source': 'reverse_whois',
                    'match_type': 'registrant_email',
                    'match_value': self.email
                })
            return formatted_results
        finally:
            loop.close()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        engine = AlldomEmailEngine(sys.argv[1])
        print(engine.search())
    else:
        print("Usage: python email.py <email>")
