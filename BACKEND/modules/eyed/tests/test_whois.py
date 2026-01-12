#!/usr/bin/env python3
"""Test WHOIS functionality"""

from __future__ import annotations

if __name__ != "__main__":
    import pytest

    pytest.skip("EYE-D test scripts are manual; run directly", allow_module_level=True)

import requests
import json

# Test the WHOIS API endpoint
url = "http://localhost:5000/api/whois"

test_queries = [
    {"query": "John Doe", "type": "name"},
    {"query": "example@gmail.com", "type": "email"},
    {"query": "+1234567890", "type": "phone"},
    {"query": "example.com", "type": "domain"}
]

for test in test_queries:
    print(f"\nTesting: {test['query']} (type: {test['type']})")
    try:
        response = requests.post(url, json=test)
        print(f"Status: {response.status_code}")
        
        if response.ok:
            data = response.json()
            if 'error' in data:
                print(f"Error: {data['error']}")
            else:
                print(f"Results: {len(data.get('results', []))} found")
                if data.get('results'):
                    print(f"First result type: {data['results'][0].get('type', 'unknown')}")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Exception: {e}")
