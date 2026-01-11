#!/usr/bin/env python3
"""
EYE-D Person Name Search Engine
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from unified_osint import UnifiedSearcher
    EYE_D_AVAILABLE = True
except ImportError:
    EYE_D_AVAILABLE = False

class EyeDPersonEngine:
    code = 'EDP'
    name = 'EYE-D Person'

    def __init__(self, person_name: str):
        self.person_name = person_name
        self.osint_client = UnifiedSearcher() if EYE_D_AVAILABLE else None

    async def search_async(self) -> Dict[str, Any]:
        print(f"👤 Searching for person: {self.person_name}")

        results = {
            'query': self.person_name,
            'query_type': 'EYE-D',
            'subtype': 'person',
            'results': [],
            'entities': [],
            'timestamp': datetime.now().isoformat()
        }

        if not self.osint_client:
            results['error'] = "EYE-D module not available"
            return results

        try:
            # Use UnifiedSearcher's search method
            osint_results = self.osint_client.search(self.person_name)

            # Process results
            for source, data in osint_results.items():
                if data and not (isinstance(data, dict) and data.get('error')):
                    result_entry = {
                        'source': source,
                        'data': data,
                        'entity_type': 'person',
                        'entity_value': self.person_name
                    }
                    results['results'].append(result_entry)

            results['total_results'] = len(results['results'])
            print(f"✅ Found {results['total_results']} results for person {self.person_name}")

        except Exception as e:
            results['error'] = str(e)
            print(f"❌ Error searching person: {e}")

        return results

    def search(self) -> List[Dict[str, Any]]:
        """Sync wrapper for search."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            results = loop.run_until_complete(self.search_async())
            return results.get('results', [])
        finally:
            loop.close()
