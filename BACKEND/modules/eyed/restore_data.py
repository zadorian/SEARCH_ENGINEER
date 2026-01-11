#!/usr/bin/env python3
import pickle
import json

# Load search cache
with open('cache/search_cache.pkl', 'rb') as f:
    search_cache = pickle.load(f)

# Create empty graph state
graph_state = {
    "nodes": [],
    "edges": [],
    "nodeIdCounter": 0,
    "valueToNodeMap": [],
    "breachConnections": [],
    "nodeSearchQueries": [],
    "activeQueryNodes": [],
    "autoShowQueries": False,
    "anchoredNodes": []
}

# Save clean graph state
with open('cache/graph_state.json', 'w') as f:
    json.dump(graph_state, f)

print("Graph state reset. Search cache preserved.")
print(f"Found {len(search_cache)} cached searches:")
for key in list(search_cache.keys())[:10]:
    data = search_cache[key]
    if 'results' in data and data['results']:
        print(f"  - {key}: {len(data['results'])} results")