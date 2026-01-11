#!/usr/bin/env python3
"""
EYE-D Keyword Search Engine (Generic)
"""

import asyncio
from typing import Dict, Any, List
from datetime import datetime
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import sibling engines for fallback strategies
try:
    from input.person_name import EyeDPersonEngine
    from input.username import EyeDUsernameEngine
except ImportError:
    try:
        from person_name import EyeDPersonEngine
        from username import EyeDUsernameEngine
    except ImportError:
        pass

class EyeDKeywordEngine:
    code = 'EDK'
    name = 'EYE-D Keyword'

    def __init__(self, keyword: str):
        self.keyword = keyword

    async def search_async(self) -> Dict[str, Any]:
        """
        Generic keyword search strategy:
        1. Assume it might be a Person Name
        2. Assume it might be a Username/Handle
        """
        print(f"🔎 Generic keyword search for: {self.keyword}")
        
        results = {
            'query': self.keyword,
            'query_type': 'EYE-D',
            'subtype': 'keyword',
            'results': [],
            'entities': [],
            'timestamp': datetime.now().isoformat()
        }

        # Strategy 1: Person Search
        print("  → Trying Person Search strategy...")
        try:
            person_engine = EyeDPersonEngine(self.keyword)
            person_results = await person_engine.search_async()
            if person_results.get('results'):
                results['results'].extend(person_results['results'])
                results['entities'].extend(person_results.get('entities', []))
        except Exception as e:
            print(f"Person strategy failed: {e}")

        # Strategy 2: Username Search
        print("  → Trying Username Search strategy...")
        try:
            username_engine = EyeDUsernameEngine(self.keyword)
            username_results = await username_engine.search_async()
            if username_results.get('results'):
                results['results'].extend(username_results['results'])
                results['entities'].extend(username_results.get('entities', []))
        except Exception as e:
            print(f"Username strategy failed: {e}")

        results['total_results'] = len(results['results'])
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

if __name__ == "__main__":
    if len(sys.argv) > 1:
        engine = EyeDKeywordEngine(sys.argv[1])
        print(engine.search())
    else:
        print("Usage: python keyword.py <term>")