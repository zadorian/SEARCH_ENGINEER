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

# Group by breach
breaches = {}
for node in nodes:
    if 'data' in node and 'breach' in node['data']:
        breach = node['data']['breach']
        if breach not in breaches:
            breaches[breach] = []
        breaches[breach].append(node['id'])

# Calculate simple connections (hub pattern, limited to breaches with <= 50 nodes)
total_connections = 0
connected_breaches = 0
for breach, node_ids in breaches.items():
    if len(node_ids) >= 2 and len(node_ids) <= 50:
        # Hub pattern: n-1 connections
        connections = len(node_ids) - 1
        total_connections += connections
        connected_breaches += 1
        print(f"{breach}: {len(node_ids)} nodes -> {connections} connections")

print(f"\nTotal: {total_connections} connections from {connected_breaches} breaches")
print(f"Skipped large breaches: ApexSMS ({len(breaches.get('ApexSMS', []))} nodes), Apollo ({len(breaches.get('Apollo', []))} nodes)")
