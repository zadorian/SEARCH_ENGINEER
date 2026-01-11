#!/usr/bin/env python3
"""Test the actual server flow"""

import os
import json

# Set up environment
os.environ['GOOGLE_API_KEY'] = 'AIzaSyBEqsmskKDyXqIOPl26Gf0QdA4pVwM-M2s'
os.environ['GOOGLE_SEARCH_ENGINE_ID'] = '3224c9c84183240de'

# Now import server components
from server import app, GoogleSearch, ExactPhraseRecallRunner, chunk_sites

def test_exhaustive_search():
    """Test the exhaustive search endpoint"""
    print("🚀 Testing exhaustive search endpoint...")
    
    with app.test_client() as client:
        # Simulate the request from frontend
        response = client.post('/api/google/search', 
            json={
                'query': 'test',
                'run_mode': 'exhaustive',
                'max_results': 10
            }
        )
        
        print(f"📊 Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.get_json()
            print(f"✅ Success: {data.get('success', False)}")
            print(f"📊 Total URLs: {data.get('total_urls', 0)}")
            print(f"📊 URLs in response: {len(data.get('urls', []))}")
            print(f"📊 Results in response: {len(data.get('results', []))}")
            
            if data.get('urls'):
                print(f"\n📋 Sample URLs:")
                for i, url in enumerate(data['urls'][:5]):
                    print(f"   {i+1}. {url}")
            else:
                print("❌ No URLs in response!")
                
            if data.get('results'):
                print(f"\n📋 Sample results:")
                for i, result in enumerate(data['results'][:3]):
                    print(f"   {i+1}. {result.get('url', 'NO URL')}")
                    print(f"      Title: {result.get('title', 'NO TITLE')}")
        else:
            print(f"❌ Error response: {response.status_code}")
            print(f"📊 Response data: {response.get_data(as_text=True)}")

if __name__ == "__main__":
    test_exhaustive_search()