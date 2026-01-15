#!/usr/bin/env python3
"""
EYE-D Company Name Search Engine
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
from typing import Dict, Any, List, Union
from datetime import datetime

# Import Output Handlers
from output.email import EmailOutputHandler
from output.phone import PhoneOutputHandler
from output.username import UsernameOutputHandler
from output.company_name import CompanyNameOutputHandler

# Import Aggregators
try:
    from rocketreach_client import RocketReachClient
except ImportError:
    RocketReachClient = None

try:
    from contactout_client import ContactOutClient
except ImportError:
    ContactOutClient = None

class EyeDCompanyNameEngine:
    def __init__(self, name: str):
        self.name = name
        self.rocketreach = RocketReachClient() if RocketReachClient else None
        self.contactout = ContactOutClient() if ContactOutClient else None
        
        self.handlers = {
            'email': EmailOutputHandler(),
            'phone': PhoneOutputHandler(),
            'username': UsernameOutputHandler(),
            'person': CompanyNameOutputHandler()
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
        print(f"👥 [Pipeline] Starting investigation for name: {self.name}")
        
        input_id = self._generate_id('person', self.name)
        
        agg_ids = {
            'rocketreach': self._generate_aggregator_id("RocketReach"),
            'contactout': self._generate_aggregator_id("ContactOut")
        }

        self.handlers['person'].process(
            self.name, 
            {
                'is_input': True, 
                'input_id': None, 
                'aggregator_ids': list(agg_ids.values())
            }
        )

        tasks = []
        if self.rocketreach: tasks.append(self._search_rocketreach(input_id, agg_ids['rocketreach']))
        if self.contactout: tasks.append(self._search_contactout(input_id, agg_ids['contactout']))

        await asyncio.gather(*tasks)
        print(f"✅ Investigation complete for {self.name}")

    def _generate_aggregator_id(self, name: str) -> str:
        return hashlib.sha256(f"aggregator:{name}:{self.name}:{datetime.now().strftime('%Y%m%d%H')}".encode()).hexdigest()[:16]

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
        h = self.handlers['person']
        if h.es:
            try: h.es.index(index=h.es_index, id=agg_id, body=node)
            except: pass

    async def _search_rocketreach(self, input_id: str, agg_id: str):
        print("  → Querying RocketReach...")
        await self._create_aggregator_node("RocketReach", agg_id, input_id)
        context = {'input_id': input_id, 'aggregator_id': agg_id, 'is_input': False}
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: self.rocketreach.search(name=self.name))
            if data:
                for entry in data:
                    if entry.get('emails'):
                        for e in entry['emails']:
                            self._process_field(e.get('email'), 'email', context, entry)
                    if entry.get('phones'):
                        for p in entry['phones']:
                            self._process_field(p.get('phone'), 'phone', context, entry)
        except Exception as e:
            print(f"❌ RocketReach Error: {e}")

    async def _search_contactout(self, input_id: str, agg_id: str):
        print("  → Querying ContactOut...")
        await self._create_aggregator_node("ContactOut", agg_id, input_id)
        context = {'input_id': input_id, 'aggregator_id': agg_id, 'is_input': False}
        try:
            loop = asyncio.get_event_loop()
            data, _ = await loop.run_in_executor(None, lambda: self.contactout.search_people(name=self.name))
            if data:
                for p in data:
                    raw = p.__dict__
                    if p.email:
                        self._process_field(p.email, 'email', context, raw)
                    if p.phone:
                        self._process_field(p.phone, 'phone', context, raw)
        except Exception as e:
            print(f"❌ ContactOut Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        asyncio.run(EyeDCompanyNameEngine(sys.argv[1]).search_async())
    else:
        print("Usage: python3 company_name.py <name>")
