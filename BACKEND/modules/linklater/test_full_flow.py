#!/usr/bin/env python3
from __future__ import annotations

if __name__ != "__main__":
    import pytest

    pytest.skip("LINKLATER test scripts are manual/integration; run directly", allow_module_level=True)

import asyncio
import json
import sys
sys.path.insert(0, '/data/CLASSES')
sys.path.insert(0, '/data/CLASSES/NEXUS')

from nexus_bridge import NexusBridge
from c1_bridge import C1Bridge

async def test_full_flow():
    # 1. Run CLINK discovery
    print('=== Running CLINK Discovery ===')
    nexus = NexusBridge()
    entities = [
        {'value': 'Satya Nadella', 'type': 'person'},
        {'value': 'Microsoft', 'type': 'company'}
    ]
    
    results = await nexus.discover_related(entities, min_matches=2)
    sites = results.get('related_sites', [])
    print(f'Found {len(sites)} related sites')
    await nexus.close()
    
    # 2. Index to Cymonides-1
    print('\n=== Indexing to Cymonides-1 ===')
    c1 = C1Bridge(project_id='linklater-test')
    stats = c1.index_clink_results(results)
    
    print(f'Index: {stats["index"]}')
    print(f'Entities indexed: {stats["entities_indexed"]}')
    print(f'Sources indexed: {stats["sources_indexed"]}')
    print(f'Total nodes: {stats["total_nodes"]}')
    
    # 3. Show index stats
    print('\n=== Index Stats ===')
    print(json.dumps(c1.get_stats(), indent=2))
    
    # 4. Search for a node
    print('\n=== Search Results ===')
    nodes = c1.search_nodes('Satya', node_class='entity', limit=3)
    for node in nodes:
        print(f'{node["label"]} ({node["type"]})')
        edges = node.get('embedded_edges', [])
        print(f'  Edges: {len(edges)}')
        for edge in edges[:3]:
            print(f'    - {edge["relation"]} -> {edge["target_label"][:40]}')

asyncio.run(test_full_flow())
