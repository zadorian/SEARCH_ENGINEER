#!/usr/bin/env python3
"""
EYE-D Phone Search Engine
Refactored to route aggregator outputs to specialized output formatters.
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
import re
from typing import Dict, Any, List, Union
from datetime import datetime

from dehashed_engine import DeHashedEngine
from osintindustries import OSINTIndustriesClient

# Import Output Handlers
from output.email import EmailOutputHandler
from output.phone import PhoneOutputHandler
from output.username import UsernameOutputHandler
from output.person_name import PersonNameOutputHandler
from output.company_name import CompanyNameOutputHandler
from output.password import PasswordOutputHandler
from output.domain_url import DomainUrlOutputHandler

# Optional: Reverse WHOIS
try:
    from modules.alldom.whoisxmlapi import reverse_whois_search
    WHOIS_AVAILABLE = True
except ImportError:
    WHOIS_AVAILABLE = False

class EyeDPhoneEngine:
    def __init__(self, phone: str):
        self.phone = phone
        self.normalized_phone = re.sub(r'[^\d]', '', phone)
        self.dehashed = DeHashedEngine(phone)
        self.osint = OSINTIndustriesClient()
        
        self.handlers = {
            'email': EmailOutputHandler(),
            'phone': PhoneOutputHandler(),
            'username': UsernameOutputHandler(),
            'person_name': PersonNameOutputHandler(),
            'company_name': CompanyNameOutputHandler(),
            'password': PasswordOutputHandler(),
            'domain_url': DomainUrlOutputHandler()
        }

    def _generate_id(self, node_type: str, value: str) -> str:
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
        print(f"📱 [Pipeline] Starting investigation for phone: {self.phone}")
        
        input_id = self._generate_id('phone', self.phone)
        
        agg_ids = {
            'dehashed': self._generate_aggregator_id("DeHashed"),
            'osint': self._generate_aggregator_id("OSINT Industries"),
            'whois': self._generate_aggregator_id("WHOIS")
        }

        self.handlers['phone'].process(
            self.phone, 
            {
                'is_input': True, 
                'input_id': None, 
                'aggregator_ids': list(agg_ids.values())
            }
        )

        tasks = [
            self._search_dehashed(input_id, agg_ids['dehashed']),
            self._search_osint_industries(input_id, agg_ids['osint'])
        ]
        if WHOIS_AVAILABLE:
            tasks.append(self._search_whois(input_id, agg_ids['whois']))

        await asyncio.gather(*tasks)
        print(f"✅ Investigation complete for {self.phone}")

    def _generate_aggregator_id(self, name: str) -> str:
        return hashlib.sha256(f"aggregator:{name}:{self.phone}:{datetime.now().strftime('%Y%m%d%H')}".encode()).hexdigest()[:16]

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
        h = self.handlers['phone']
        if h.es:
            try: h.es.index(index=h.es_index, id=agg_id, body=node)
            except: pass

    async def _search_dehashed(self, input_id: str, agg_id: str):
        print("  → Querying DeHashed...")
        await self._create_aggregator_node("DeHashed", agg_id, input_id)
        context = {'input_id': input_id, 'aggregator_id': agg_id, 'is_input': False}
        try:
            loop = asyncio.get_event_loop()
            custom_query = f"phone:{self.normalized_phone}"
            data = await loop.run_in_executor(None, lambda: self.dehashed.search(custom_query=custom_query))
            if data:
                for entry in data:
                    self._process_field(entry.get('email'), 'email', context, entry)
                    self._process_field(entry.get('phone'), 'phone', context, entry)
                    self._process_field(entry.get('username'), 'username', context, entry)
                    self._process_field(entry.get('password'), 'password', context, entry)
                    if entry.get('database_name'):
                        self._process_field(entry['database_name'], 'company_name', context, entry)
        except Exception as e:
            print(f"❌ DeHashed Error: {e}")

    async def _search_osint_industries(self, input_id: str, agg_id: str):
        print("  → Querying OSINT Industries...")
        await self._create_aggregator_node("OSINT Industries", agg_id, input_id)
        context = {'input_id': input_id, 'aggregator_id': agg_id, 'is_input': False}
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: self.osint.search_phone(self.phone))
            if data:
                for r in data:
                    raw = r.raw_data
                    self._process_field(r.email, 'email', context, raw)
                    self._process_field(r.phone, 'phone', context, raw)
                    self._process_field(r.username, 'username', context, raw)
                    if r.module == 'hibp' or r.category == 'Breach Data':
                        self._process_field(r.name, 'company_name', context, raw)
                    else:
                        self._process_field(r.name, 'person_name', context, raw)
        except Exception as e:
            print(f"❌ OSINT Industries Error: {e}")

    async def _search_whois(self, input_id: str, agg_id: str):
        print("  → Querying WHOIS...")
        await self._create_aggregator_node("WHOIS", agg_id, input_id)
        context = {'input_id': input_id, 'aggregator_id': agg_id, 'is_input': False}
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: whois_lookup(self.normalized_phone, query_type="telephone")) # Note: check if alldom supports this
            if data and data.get('domains'):
                for domain in data['domains']:
                    self._process_field(domain, 'domain_url', context, data)
        except Exception as e:
            print(f"❌ WHOIS Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        asyncio.run(EyeDPhoneEngine(sys.argv[1]).search_async())
    else:
        print("Usage: python3 phone.py <phone>")
