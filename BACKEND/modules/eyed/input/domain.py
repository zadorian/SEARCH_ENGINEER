#!/usr/bin/env python3
"""
EYE-D Domain Input Handler
Thin wrapper around ALLDOM WHOIS functionality.
"""

from typing import List, Dict, Any
from modules.alldom.whoisxmlapi import whois_lookup

class EyeDDomainEngine:
    code = 'EDD'
    name = 'EYE-D Domain'

    def __init__(self, domain: str):
        self.domain = domain

    def search(self) -> List[Dict[str, Any]]:
        """Sync wrapper calling ALLDOM WHOIS."""
        try:
            # Call the central WHOIS implementation in ALLDOM
            history = whois_lookup(self.domain, query_type="domain")
            
            web_results = []
            count = history.get('count', 0)
            
            web_results.append({
                'url': f"https://whois.whoisxmlapi.com/lookup?q={self.domain}",
                'title': f"WHOIS History: {self.domain}",
                'snippet': f"Found {count} historical records.",
                'engine': self.name,
                'source': 'WHOISXML',
                'rank': 1
            })
            
            if history.get('records'):
                latest = history['records'][0]
                registrant = latest.get('registrantContact', {}).get('organization') or latest.get('registrantContact', {}).get('name')
                web_results.append({
                    'url': '#',
                    'title': f"Latest Registrant: {registrant or 'Unknown'}",
                    'snippet': f"Created: {latest.get('createdDate')}, Expires: {latest.get('expiresDate')}",
                    'engine': self.name,
                    'source': 'WHOISXML',
                    'rank': 2
                })

            return web_results
        except Exception as e:
            return [{'error': str(e)}]

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        engine = EyeDDomainEngine(sys.argv[1])
        print(engine.search())