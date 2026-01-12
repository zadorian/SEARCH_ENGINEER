#!/usr/bin/env python3
"""
EYE-D Domain URL Search Engine
Executes WHOIS lookup and formats for C-1.
"""

import sys
import os
from pathlib import Path

# PREVENT STDLIB SHADOWING
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir in sys.path:
    sys.path.remove(script_dir)

# Add parent directory to path to find modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import uuid
import hashlib
from typing import Dict, Any, List, Union
from datetime import datetime

from output.domain_url import DomainUrlOutputHandler

# Import WHOIS lookup
try:
    from whoisxmlapi import whois_lookup
    WHOIS_AVAILABLE = True
except ImportError:
    try:
        from modules.alldom.whoisxmlapi import whois_lookup
        WHOIS_AVAILABLE = True
    except ImportError:
        WHOIS_AVAILABLE = False

class EyeDDomainEngine:
    def __init__(self, domain: str):
        self.domain = domain
        self.handlers = {
            'domain_url': DomainUrlOutputHandler()
        }

    def _generate_id(self, node_type: str, value: str) -> str:
        # Node type is 'domain' internally, but IO code is 'domain_url'
        raw = f"{node_type}:{str(value).lower().strip()}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]

    def _process_field(self, value: Union[str, List[str]], handler_key: str, context: Dict, raw_data: Dict):
        if not value: return
        handler = self.handlers.get(handler_key)
        if not handler: return

        if isinstance(value, list):
            for item in value:
                if item and isinstance(item, str):
                    handler.process(item, context, raw_data)
        elif isinstance(value, str):
            handler.process(value, context, raw_data)

    async def search_async(self):
        print(f"🌐 [Pipeline] Searching Domain: {self.domain}")
        
        # Internal node type is 'domain'
        input_id = self._generate_id('domain', self.domain)
        
        agg_ids = {
            'whois': self._generate_aggregator_id("WHOIS")
        }

        # Use 'domain_url' handler
        self.handlers['domain_url'].process(
            self.domain, 
            {
                'is_input': True, 
                'input_id': None, 
                'aggregator_ids': list(agg_ids.values())
            }
        )

        tasks = []
        if WHOIS_AVAILABLE:
            tasks.append(self._search_whois(input_id, agg_ids['whois']))

        await asyncio.gather(*tasks)
        print(f"✅ Investigation complete for {self.domain}")

    def _generate_aggregator_id(self, name: str) -> str:
        return hashlib.sha256(f"aggregator:{name}:{self.domain}:{datetime.now().strftime('%Y%m%d%H')}".encode()).hexdigest()[:16]

    async def _create_aggregator_node(self, name: str, agg_id: str, input_id: str):
        node = {
            "id": agg_id,
            "node_class": "LOCATION",
            "type": "aggregator_result",
            "canonicalValue": f"{name.lower()}_result_{agg_id}",
            "label": f"{name} Search Result",
            "value": agg_id,
            "embedded_edges": [],
            "metadata": {"aggregator": name, "timestamp": datetime.utcnow().isoformat()},
            "createdAt": datetime.utcnow().isoformat()
        }
        h = self.handlers['domain_url']
        if h.es:
            try: h.es.index(index=h.es_index, id=agg_id, body=node)
            except: pass

    async def _search_whois(self, input_id: str, agg_id: str):
        print("  → Querying WHOIS...")
        await self._create_aggregator_node("WHOIS", agg_id, input_id)
        context = {'input_id': input_id, 'aggregator_id': agg_id, 'is_input': False}
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: whois_lookup(self.domain, query_type="domain"))
            if data and data.get('domains'):
                for domain in data['domains']:
                    # Route to 'domain_url' handler
                    self._process_field(domain, 'domain_url', context, data)
        except Exception as e:
            print(f"❌ WHOIS Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        asyncio.run(EyeDDomainEngine(sys.argv[1]).search_async())
    else:
        print("Usage: python3 domain_url.py <domain>")
