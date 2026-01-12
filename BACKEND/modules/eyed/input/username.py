#!/usr/bin/env python3
"""
EYE-D Username Search Engine
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

from dehashed_engine import DeHashedEngine
from sherlock_integration import SherlockIntegration

# Import Output Handlers
from output.email import EmailOutputHandler
from output.phone import PhoneOutputHandler
from output.username import UsernameOutputHandler
from output.person_name import PersonNameOutputHandler
from output.password import PasswordOutputHandler
from output.url import UrlOutputHandler

class EyeDUsernameEngine:
    def __init__(self, username: str):
        self.username = username
        self.dehashed = DeHashedEngine(username)
        
        self.handlers = {
            'email': EmailOutputHandler(),
            'phone': PhoneOutputHandler(),
            'username': UsernameOutputHandler(),
            'person': PersonNameOutputHandler(),
            'password': PasswordOutputHandler(),
            'url': UrlOutputHandler()
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
        print(f"👤 [Pipeline] Starting investigation for username: {self.username}")
        
        input_id = self._generate_id('username', self.username)
        
        agg_ids = {
            'dehashed': self._generate_aggregator_id("DeHashed"),
            'sherlock': self._generate_aggregator_id("Sherlock")
        }

        self.handlers['username'].process(
            self.username, 
            {
                'is_input': True, 
                'input_id': None, 
                'aggregator_ids': list(agg_ids.values())
            }
        )

        tasks = [
            self._search_dehashed(input_id, agg_ids['dehashed']),
            self._search_sherlock(input_id, agg_ids['sherlock'])
        ]

        await asyncio.gather(*tasks)
        print(f"✅ Investigation complete for {self.username}")

    def _generate_aggregator_id(self, name: str) -> str:
        return hashlib.sha256(f"aggregator:{name}:{self.username}:{datetime.now().strftime('%Y%m%d%H')}".encode()).hexdigest()[:16]

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
        h = self.handlers['username']
        if h.es:
            try: h.es.index(index=h.es_index, id=agg_id, body=node)
            except: pass

    async def _search_dehashed(self, input_id: str, agg_id: str):
        print("  → Querying DeHashed...")
        await self._create_aggregator_node("DeHashed", agg_id, input_id)
        context = {'input_id': input_id, 'aggregator_id': agg_id, 'is_input': False}
        try:
            loop = asyncio.get_event_loop()
            custom_query = f"username:{self.username}"
            data = await loop.run_in_executor(None, lambda: self.dehashed.search(custom_query=custom_query))
            if data:
                for entry in data:
                    self._process_field(entry.get('email'), 'email', context, entry)
                    self._process_field(entry.get('phone'), 'phone', context, entry)
                    self._process_field(entry.get('username'), 'username', context, entry)
                    self._process_field(entry.get('password'), 'password', context, entry)
        except Exception as e:
            print(f"❌ DeHashed Error: {e}")

    async def _search_sherlock(self, input_id: str, agg_id: str):
        print("  → Querying Sherlock...")
        await self._create_aggregator_node("Sherlock", agg_id, input_id)
        context = {'input_id': input_id, 'aggregator_id': agg_id, 'is_input': False}
        try:
            async with SherlockIntegration() as sherlock:
                data = await sherlock.check_username(self.username)
                if data:
                    for hit in data:
                        if hit.get('url'): self.handlers['url'].process(hit['url'], context, hit)
        except Exception as e:
            print(f"❌ Sherlock Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        asyncio.run(EyeDUsernameEngine(sys.argv[1]).search_async())
    else:
        print("Usage: python3 username.py <username>")