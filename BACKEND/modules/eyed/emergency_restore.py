#!/usr/bin/env python3
import pickle
import json

# Load search cache
with open('cache/search_cache.pkl', 'rb') as f:
    search_cache = pickle.load(f)

# Count total results
total_results = 0
all_nodes = {}
all_edges = {}
node_id_counter = 0

# Process each cached search
for key, data in search_cache.items():
    if 'results' in data and data['results']:
        print(f"\nProcessing {key}: {len(data['results'])} results")
        
        for breach in data['results']:
            # Process emails
            if 'email' in breach and breach['email']:
                for email in breach['email']:
                    node_key = f"email_{email}"
                    if node_key not in all_nodes:
                        all_nodes[node_key] = {
                            "id": node_id_counter,
                            "label": email,
                            "type": "email",
                            "color": {"background": "#000000", "border": "#00CED1"},
                            "data": {
                                "value": email,
                                "breach": breach.get('database_name', 'Unknown'),
                                "breachData": breach
                            },
                            "font": {"multi": "html", "size": 12}
                        }
                        node_id_counter += 1
                        total_results += 1

# Create graph state with recovered nodes
graph_state = {
    "nodes": list(all_nodes.values()),
    "edges": [],
    "nodeIdCounter": node_id_counter,
    "valueToNodeMap": [[k, v["id"]] for k, v in all_nodes.items()],
    "breachConnections": [],
    "nodeSearchQueries": [],
    "activeQueryNodes": [],
    "autoShowQueries": False,
    "anchoredNodes": []
}

# Save graph state
with open('cache/graph_state.json', 'w') as f:
    json.dump(graph_state, f)

print(f"\n✓ RESTORED {len(all_nodes)} nodes from cache!")
print("Refresh your browser now - your data is back!")