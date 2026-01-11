#!/usr/bin/env python3
"""Test script to debug ExactPhraseRecallRunner"""

import os
import sys
from pathlib import Path

# Set up environment
os.environ['GOOGLE_API_KEY'] = 'AIzaSyBEqsmskKDyXqIOPl26Gf0QdA4pVwM-M2s'
os.environ['GOOGLE_SEARCH_ENGINE_ID'] = '3224c9c84183240de'

# Import the modules
sys.path.insert(0, str(Path(__file__).parent))
from exact_phrase_recall_runner import ExactPhraseRecallRunner, chunk_sites

# Import the real GoogleSearch from server
from server import GoogleSearch

# Test the runner
def main():
    print("🚀 Testing ExactPhraseRecallRunner...")
    
    # Simple test with minimal configuration
    SITES = [".com", ".org", ".net"]
    site_groups = list(chunk_sites(SITES, max_terms=2))
    
    print(f"📊 Site groups: {site_groups}")
    
    google = GoogleSearch()
    runner = ExactPhraseRecallRunner(
        phrase="test",
        google=google,
        site_groups=site_groups,
        time_slices=[{}],  # No time filter
        max_results_per_query=10,
        use_parallel=False  # Disable parallel for easier debugging
    )
    
    print("\n🚀 Running exhaustive search...")
    results = runner.run()
    
    print(f"\n📊 FINAL RESULTS:")
    print(f"   Total results: {len(results)}")
    print(f"   Store size: {len(runner._store)}")
    
    if results:
        print(f"\n📋 Sample results:")
        for i, result in enumerate(results[:3]):
            print(f"   {i+1}. {result.get('url', 'NO URL')}")
            print(f"      Title: {result.get('title', 'NO TITLE')}")
    else:
        print("❌ No results returned!")
        if runner._store:
            print(f"\n📊 But store has {len(runner._store)} items!")
            print("📋 Store contents:")
            for url, data in list(runner._store.items())[:3]:
                print(f"   - {url}: {data.get('title', 'NO TITLE')}")

if __name__ == "__main__":
    main()