#!/usr/bin/env python3
from __future__ import annotations

if __name__ != "__main__":
    import pytest

    pytest.skip("EYE-D test scripts are manual; run directly", allow_module_level=True)

import json

# Load the graph state
with open('cache/graph_state.json', 'r') as f:
    data = json.load(f)

nodes = data.get('nodes', [])
print(f"Total nodes: {len(nodes)}")

# Group by breach
breaches = {}
for node in nodes:
    if 'data' in node and 'breach' in node['data']:
        breach = node['data']['breach']
        if breach not in breaches:
            breaches[breach] = []
        breaches[breach].append(node['id'])

print(f"\nBreaches found: {len(breaches)}")
print("\nNodes per breach:")
for breach, node_ids in sorted(breaches.items(), key=lambda x: len(x[1]), reverse=True)[:10]:
    print(f"  {breach}: {len(node_ids)} nodes")

# Calculate how many connections would be created
total_connections = 0
for breach, node_ids in breaches.items():
    if len(node_ids) >= 2:
        # Star pattern in connectBreachNodes creates n*(n-1)/2 edges
        connections = len(node_ids) * (len(node_ids) - 1) // 2
        total_connections += connections

print(f"\nTotal connections that will be created: {total_connections}")
