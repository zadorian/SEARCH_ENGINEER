#!/usr/bin/env python3
"""
ALLDOM Domain URL Search Engine
Parallel execution of WHOIS and DNS.
Refactored for C-1 Provenance Graph.
"""

import sys
import os
from pathlib import Path

# PREVENT STDLIB SHADOWING
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir in sys.path:
    sys.path.remove(script_dir)

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import uuid
import hashlib
from typing import Dict, Any, List, Union
from datetime import datetime
from urllib.parse import urlparse

# Import Output Handlers
from output.domain_url import DomainUrlOutputHandler
from output.ip_address import IpAddressOutputHandler
from output.dns_record import DnsRecordOutputHandler
from output.email import EmailOutputHandler
from output.phone import PhoneOutputHandler
from output.person_name import PersonNameOutputHandler
from output.company_name import CompanyNameOutputHandler
from output.address import AddressOutputHandler

# Import Aggregators
try:
    from modules.alldom.whoisxmlapi import whois_lookup, extract_entities_from_records
    WHOIS_AVAILABLE = True
except ImportError:
    WHOIS_AVAILABLE = False

class AlldomDomainEngine:
    def __init__(self, target: str):
        self.target = target
        self.domain, self.is_url = self._normalize_input(target)
        
        self.handlers = {
            'domain_url': DomainUrlOutputHandler(),
            'ip_address': IpAddressOutputHandler(),
            'dns_record': DnsRecordOutputHandler(),
            'email': EmailOutputHandler(),
            'phone': PhoneOutputHandler(),
            'person': PersonNameOutputHandler(),
            'company': CompanyNameOutputHandler(),
            'address': AddressOutputHandler()
        }

    def _normalize_input(self, input_string: str):
        input_string = input_string.lower().strip()
        if input_string.startswith(('http://', 'https://')):
            parsed = urlparse(input_string)
            return parsed.netloc if parsed.netloc else parsed.path, True
        return input_string.replace('www.', ''), False

    def _generate_id(self, node_type: str, value: str) -> str:
        raw = f"{node_type}:{str(value).lower().strip()}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]

    def _generate_aggregator_id(self, name: str) -> str:
        return hashlib.sha256(f"aggregator:{name}:{self.domain}:{datetime.now().strftime('%Y%m%d%H')}".encode()).hexdigest()[:16]

    async def _create_aggregator_node(self, name: str, agg_id: str, input_id: str):
        node = {
            "id": agg_id,
            "node_class": "LOCATION",
            "type": "aggregator_result",
            "canonicalValue": f"{name.lower()}_result_{agg_id}",
            "label": f"{name} Domain Scan",
            "value": agg_id,
            "embedded_edges": [],
            "metadata": {"aggregator": name, "timestamp": datetime.utcnow().isoformat()},
            "createdAt": datetime.utcnow().isoformat()
        }
        h = self.handlers['domain_url']
        if h.es:
            try: h.es.index(index=h.es_index, id=agg_id, body=node)
            except: pass

    async def search_async(self):
        print(f"🌐 [Alldom] Starting investigation for domain: {self.domain}")
        
        input_id = self._generate_id('domain', self.domain)
        
        agg_ids = {
            'whois': self._generate_aggregator_id("WHOISXML"),
            'dns': self._generate_aggregator_id("DNS_Lookup")
        }

        # Create Input Node
        self.handlers['domain_url'].process(
            self.domain, 
            {
                'is_input': True, 
                'input_id': None, 
                'aggregator_ids': list(agg_ids.values())
            }
        )

        # Run Parallel Tasks
        tasks = [
            self._search_whois(input_id, agg_ids['whois']),
            self._search_dns(input_id, agg_ids['dns'])
        ]

        await asyncio.gather(*tasks)
        print(f"✅ Alldom Investigation complete for {self.domain}")

    async def _search_whois(self, input_id: str, agg_id: str):
        print("  → Querying WHOIS...")
        await self._create_aggregator_node("WHOISXML", agg_id, input_id)
        context = {
            'input_id': input_id,
            'aggregator_id': agg_id,
            'is_input': False,
            'source_domain': self.domain
        }

        if WHOIS_AVAILABLE:
            try:
                loop = asyncio.get_event_loop()
                data = await loop.run_in_executor(None, lambda: whois_lookup(self.domain, query_type="domain"))
                if data:
                    # Route main domain
                    self.handlers['domain_url'].process(self.domain, context, data)

                    # Extract entities from WHOIS records
                    records = data.get('records', [])
                    if records:
                        entities = extract_entities_from_records(records)
                        print(f"  → Extracted {len(entities)} entities from WHOIS")

                        # Route each entity to appropriate handler
                        for entity in entities:
                            entity_type = entity.get('type')
                            entity_value = entity.get('value')

                            if not entity_value:
                                continue

                            entity_context = {
                                **context,
                                'metadata': {
                                    'role': entity.get('role'),
                                    'source': entity.get('source', 'whois')
                                }
                            }

                            handler = self.handlers.get(entity_type)
                            if handler:
                                handler.process(entity_value, entity_context, entity)

            except Exception as e:
                print(f"❌ WHOIS Error: {e}")

    async def _search_dns(self, input_id: str, agg_id: str):
        # Placeholder for DNS tasks
        print("  → Querying DNS (Stub)...")
        await self._create_aggregator_node("DNS_Lookup", agg_id, input_id)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        asyncio.run(AlldomDomainEngine(sys.argv[1]).search_async())
    else:
        print("Usage: python3 domain_url.py <domain>")