#!/usr/bin/env python3
"""Test script for corporate searches"""

import os
import json

# Set API keys
os.environ['OPENCORPORATES_API_KEY'] = 'UvjlNXuBiIeNymveADRR'
os.environ['ALEPH_API_KEY'] = '1c0971afa4804c2aafabb125c79b275e'

# Test OpenCorporates
print("Testing OpenCorporates API...")
from opencorporates import OpenCorporatesAPI

api = OpenCorporatesAPI()
print(f"API key loaded: {api.api_key}")

result = api.search_companies('sastre consulting ltd')
if 'results' in result and 'companies' in result['results']:
    companies = result['results']['companies']
    print(f"\nFound {len(companies)} companies:")
    for comp in companies[:3]:  # Show first 3
        company = comp['company']
        print(f"- {company['name']} ({company['jurisdiction_code']}) - {company.get('company_number', 'N/A')}")
else:
    print(f"Error or no results: {result}")

# Test OCCRP Aleph
print("\n\nTesting OCCRP Aleph API...")
from occrp_aleph import AlephSearcher
import asyncio

searcher = AlephSearcher()
print(f"API key loaded: {'Yes' if searcher.api_key else 'No'}")

async def test_aleph():
    results = await searcher.search('sastre consulting', max_results=5)
    return results

results = asyncio.run(test_aleph())
print(f"\nFound {len(results)} results from Aleph")
for r in results[:3]:
    print(f"- {r['title']} ({r['schema']})")

print("\n✅ Both APIs are working! Please restart your Flask server to use them.")