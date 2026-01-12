#!/usr/bin/env python3
"""
EYE-D Person LinkedIn URL Search Engine
Parallel execution of RocketReach, ContactOut, Kaspr.
"""

import asyncio
import sys
import re
from pathlib import Path
from typing import Dict, Any, List

# Add parent directory to path to find modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from input.base_engine import BaseEyeDEngine
from output_handler import extract_data_from_json, generate_graph_export

# Import enrichment clients if available
try:
    from rocketreach_client import RocketReachClient
except ImportError:
    RocketReachClient = None

try:
    from contactout_client import ContactOutClient
except ImportError:
    ContactOutClient = None

try:
    from kaspr_client import KasprClient
except ImportError:
    KasprClient = None

class EyeDPersonLinkedinEngine(BaseEyeDEngine):
    code = 'EDPL'
    name = 'EYE-D Person LinkedIn'

    def __init__(self, linkedin_url: str):
        # Output to 'person_linkedin_url' folder
        super().__init__('person_linkedin_url')
        self.linkedin_url = linkedin_url
        
        self.rocketreach = RocketReachClient() if RocketReachClient else None
        self.contactout = ContactOutClient() if ContactOutClient else None
        self.kaspr = KasprClient() if KasprClient else None

    async def search_async(self) -> Dict[str, Any]:
        print(f"💼 [Parallel] Searching Person LinkedIn: {self.linkedin_url}")
        
        # Define tasks
        tasks = []
        if self.rocketreach:
            tasks.append(self._search_rocketreach())
        if self.contactout:
            tasks.append(self._search_contactout())
        if self.kaspr:
            tasks.append(self._search_kaspr())

        # Execute parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Aggregate
        aggregated_data = {
            'query': self.linkedin_url,
            'results_by_source': {},
            'results': []
        }

        # Add direct LinkedIn reference
        aggregated_data['results'].append({
            'source': 'input',
            'data': {'linkedin_url': self.linkedin_url},
            'entity_type': 'linkedin',
            'entity_value': self.linkedin_url
        })

        for res in results:
            if isinstance(res, dict) and 'source' in res:
                source = res['source']
                data = res.get('data')
                
                if data:
                    aggregated_data['results_by_source'][source] = data

        # Extract entities and build graph
        extracted = extract_data_from_json(aggregated_data)
        
        # Extract name if available for better graph root
        primary_label = self.linkedin_url
        if extracted.get('names'):
            primary_label = extracted['names'][0].get('value', self.linkedin_url)
            
        graph = generate_graph_export(extracted, primary_label)
        
        # Construct Final Output
        final_output = {
            "input": self.linkedin_url,
            "input_type": "person_linkedin_url",
            "graph": graph, # C-1 Nodes and Edges
            "extracted_entities": extracted,
            "raw_data": aggregated_data
        }

        # Save to output/linkedin/
        saved_path = self.save_output(self.linkedin_url, final_output)
        return final_output

    async def _search_rocketreach(self):
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: self.rocketreach.lookup_linkedin(self.linkedin_url))
            return {'source': 'rocketreach', 'data': data}
        except Exception as e:
            print(f"❌ RocketReach Error: {e}")
            return {'source': 'rocketreach', 'data': {}, 'error': str(e)}

    async def _search_contactout(self):
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: self.contactout.enrich_linkedin(self.linkedin_url))
            return {'source': 'contactout', 'data': data}
        except Exception as e:
            print(f"❌ ContactOut Error: {e}")
            return {'source': 'contactout', 'data': {}, 'error': str(e)}

    async def _search_kaspr(self):
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: self.kaspr.enrich_linkedin(self.linkedin_url))
            return {'source': 'kaspr', 'data': data}
        except Exception as e:
            print(f"❌ Kaspr Error: {e}")
            return {'source': 'kaspr', 'data': {}, 'error': str(e)}

    def search(self):
        """Sync entry point"""
        return asyncio.run(self.search_async())

if __name__ == "__main__":
    if len(sys.argv) > 1:
        url_arg = sys.argv[1]
        engine = EyeDPersonLinkedinEngine(url_arg)
        engine.search()
    else:
        print("Usage: python3 person_linkedin_url.py <linkedin_url>")
