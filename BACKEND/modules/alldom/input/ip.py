#!/usr/bin/env python3
"""
ALLDOM IP Input Handler
Finds domains associated with an IP address via Reverse IP/DNS.
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

# Legend codes from /data/SEARCH_ENGINEER/BACKEND/modules/input_output/matrix/codes.json
# 8 = ip_address

class AlldomIpEngine:
    code = 'ADI'
    name = 'ALLDOM IP'
    _code = 8

    def __init__(self, ip: str):
        self.ip = ip

    async def search_async(self) -> Dict[str, Any]:
        """
        Find domains hosted on this IP.
        """
        print(f"🌐 [ALLDOM] Reverse IP lookup for: {self.ip}")
        
        try:
            result = await asyncio.to_thread(whois_lookup, self.ip, query_type="ip")
            return result
        except Exception as e:
            return {"error": str(e), "query": self.ip}

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
                    'source': 'reverse_ip',
                    'match_type': 'hosted_ip',
                    'match_value': self.ip
                })
            return formatted_results
        finally:
            loop.close()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        engine = AlldomIpEngine(sys.argv[1])
        print(engine.search())
    else:
        print("Usage: python ip.py <ip_address>")
