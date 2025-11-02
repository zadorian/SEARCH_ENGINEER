#!/usr/bin/env python3
"""Quick test to see what Aleph returns for Sastre Consulting Ltd"""

import json
import sys
import os

# Set up environment
os.environ['ALEPH_CLI_PATH'] = '/Users/attic/Library/Mobile Documents/com~apple~CloudDocs/01_ACTIVE_PROJECTS/Development/0. WIKIMAN/01aleph.py'
os.environ['ALEPH_API_KEY'] = 'test-aleph-api-key'

sys.path.insert(0, '.')

from corporella import tool_aleph_search

# Test search
print("Searching for Sastre Consulting Ltd...\n")
result = tool_aleph_search("Sastre Consulting Ltd")

if result.get('ok'):
    # Pretty print the full entity structure
    print("\n=== FULL ENTITY STRUCTURE ===\n")
    entity = result.get('results', {}).get('entity', {})

    print(f"Schema: {entity.get('schema')}")
    print(f"\nProperties keys: {list(entity.get('properties', {}).keys())}")

    # Print all properties
    print("\n=== ALL PROPERTIES ===")
    for key, value in entity.get('properties', {}).items():
        print(f"\n{key}:")
        print(f"  Type: {type(value)}")
        if isinstance(value, list) and value:
            print(f"  Length: {len(value)}")
            if isinstance(value[0], dict):
                print(f"  First item type: dict")
                print(f"  First item keys: {list(value[0].keys()) if value[0] else 'empty'}")
                if 'schema' in value[0]:
                    print(f"  First item schema: {value[0].get('schema')}")
                    print(f"  First item properties: {value[0].get('properties', {})}")
            else:
                print(f"  Values: {value[:3]}..." if len(value) > 3 else f"  Values: {value}")
        elif isinstance(value, dict):
            print(f"  Keys: {list(value.keys())}")
        else:
            print(f"  Value: {value}")

    # Check for relationships
    print("\n=== RELATIONSHIPS ===")
    rels = result.get('results', {}).get('relationships', {})
    for rel_type, rel_list in rels.items():
        if rel_list:
            print(f"\n{rel_type}: {len(rel_list)} items")
            for item in rel_list[:2]:
                print(f"  - {item}")
else:
    print(f"Error: {result.get('error')}")
