#!/usr/bin/env python3
"""
EYE-D Email Search Engine
Refactored to route aggregator outputs to specialized output formatters.
Creates provenance graph with aggregator_result nodes.
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

class EyeDEmailEngine:
    def __init__(self, email: str):
        self.email = email
        self.dehashed = DeHashedEngine(email)
        self.osint = OSINTIndustriesClient()
        
        # Initialize Handlers
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
        """Helper to handle both single values and lists of values"""
        if not value:
            return
            
        handler = self.handlers.get(handler_key)
        if not handler:
            return

        if isinstance(value, list):
            for item in value:
                if item and isinstance(item, str):
                    handler.process(item, context, raw_data)
        elif isinstance(value, str):
            handler.process(value, context, raw_data)

    async def search_async(self):
        print(f"📧 [Pipeline] Starting investigation for email: {self.email}")
        
        input_id = self._generate_id('email', self.email)
        
        # Pre-generate aggregator IDs for Input Node linkage
        agg_ids = {
            'dehashed': self._generate_aggregator_id("DeHashed"),
            'osint': self._generate_aggregator_id("OSINT Industries"),
            'whois': self._generate_aggregator_id("WHOIS")
        }
        
        # Create Input Node linked to all aggregators
        self.handlers['email'].process(
            self.email, 
            {
                'is_input': True, 
                'input_id': None, 
                'aggregator_ids': list(agg_ids.values())
            }
        )

        # Run Aggregators in Parallel
        tasks = [
            self._search_dehashed(input_id, agg_ids['dehashed']),
            self._search_osint_industries(input_id, agg_ids['osint'])
        ]
        if WHOIS_AVAILABLE:
            tasks.append(self._search_whois(input_id, agg_ids['whois']))

        await asyncio.gather(*tasks)
        print(f"✅ Investigation complete for {self.email}")

    def _generate_aggregator_id(self, name: str) -> str:
        return hashlib.sha256(f"aggregator:{name}:{self.email}:{datetime.now().strftime('%Y%m%d%H')}".encode()).hexdigest()[:16]

    async def _create_aggregator_node(self, name: str, agg_id: str, input_id: str):
        """Create a LOCATION class node for the aggregator result"""
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
        h = self.handlers['email']
        if h.es:
            try: h.es.index(index=h.es_index, id=agg_id, body=node)
            except: pass

    async def _search_dehashed(self, input_id: str, agg_id: str):
        print("  → Querying DeHashed...")
        await self._create_aggregator_node("DeHashed", agg_id, input_id)
        context = {'input_id': input_id, 'aggregator_id': agg_id, 'is_input': False}
        
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, self.dehashed.search)
            if data:
                for entry in data:
                    self._process_field(entry.get('email'), 'email', context, entry)
                    self._process_field(entry.get('phone'), 'phone', context, entry)
                    self._process_field(entry.get('username'), 'username', context, entry)
                    self._process_field(entry.get('password'), 'password', context, entry)
                    self._process_field(entry.get('hashed_password'), 'password', context, entry)
                    # DeHashed database names are technically Company/Source nodes
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
            data = await loop.run_in_executor(None, lambda: self.osint.search_email(self.email))
            if data:
                for r in data:
                    raw = r.raw_data
                    self._process_field(r.email, 'email', context, raw)
                    self._process_field(r.phone, 'phone', context, raw)
                    self._process_field(r.username, 'username', context, raw)
                    
                    # INTELLIGENT ROUTING: 
                    # If the name comes from HIBP, it's a Company (the breach site).
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
            data = await loop.run_in_executor(None, lambda: reverse_whois_search(self.email, "basicSearchTerms", search_type="historic"))
            if data and data.get('domains'):
                for domain in data['domains']:
                    self._process_field(domain, 'domain_url', context, data)
        except Exception as e:
            print(f"❌ WHOIS Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        asyncio.run(EyeDEmailEngine(sys.argv[1]).search_async())
    else:
        print("Usage: python3 email.py <email>")