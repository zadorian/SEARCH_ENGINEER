#!/usr/bin/env python3
"""Test MCP server functions directly"""
import sys
import os

os.environ['ALEPH_CLI_PATH'] = '/Users/attic/Library/Mobile Documents/com~apple~CloudDocs/01_ACTIVE_PROJECTS/Development/0. WIKIMAN/01aleph.py'
os.environ['ALEPH_API_KEY'] = 'test-aleph-api-key'
os.environ['OPEN_CORPORATES_API_TOKEN'] = 'test-opencorporates-token'

sys.path.insert(0, '.')

from corporella import tool_parallel_search

print("Testing parallel_search through direct import (same way MCP server does)...")
result = tool_parallel_search("Sastre Consulting Ltd")

if result.get('ok'):
    print("\n=== RESULT ===")
    print(f"Officers found: {len(result.get('officers_data', []))}")
    print(f"OpenCorporates companies: {result.get('sources', {}).get('opencorporates', {}).get('companies_found')}")
    print(f"Aleph entities: {result.get('sources', {}).get('aleph', {}).get('entities_found')}")

    print("\n=== OFFICERS DATA ===")
    for officer in result.get('officers_data', []):
        print(f"- {officer.get('name')} ({officer.get('source')})")

    print("\n=== REPORT PREVIEW ===")
    report = result.get('report', '')
    lines = report.split('\n')
    for line in lines[15:35]:  # Show officers section
        print(line)
else:
    print(f"ERROR: {result.get('error')}")
