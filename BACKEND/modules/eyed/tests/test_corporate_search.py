#!/usr/bin/env python3
"""Test script for corporate searches"""

from __future__ import annotations

if __name__ != "__main__":
    import pytest

    pytest.skip("EYE-D test scripts are manual; run directly", allow_module_level=True)

import os
import json

# Set API keys
# Replaced by Corporella - /data/corporella/
# os.environ['OPENCORPORATES_API_KEY'] = 'UvjlNXuBiIeNymveADRR'
# Set `ALEPH_API_KEY` in the environment (or use Corporella at /data/corporella/).

# Replaced by Corporella - /data/corporella/
# print("Testing OpenCorporates API...")
# from opencorporates import OpenCorporatesAPI
# api = OpenCorporatesAPI()
# print(f"API key loaded: {api.api_key}")
# result = api.search_companies('sastre consulting ltd')
# if 'results' in result and 'companies' in result['results']:
#     companies = result['results']['companies']
#     print(f"\nFound {len(companies)} companies:")
#     for comp in companies[:3]:  # Show first 3
#         company = comp['company']
#         print(f"- {company['name']} ({company['jurisdiction_code']}) - {company.get('company_number', 'N/A')}")
# else:
#     print(f"Error or no results: {result}")

# Test OCCRP Aleph
print("Testing OCCRP Aleph API...")
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

print("\nNote: For company searches, use Corporella at /data/corporella/")
print("Aleph API is working!")
