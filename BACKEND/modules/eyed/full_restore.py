#!/usr/bin/env python3
import pickle
import json
from collections import defaultdict

# Node color mapping
NODE_COLORS = {
    'email': '#00CED1',      # Dark Turquoise
    'username': '#FFD700',   # Gold
    'password': '#FF6347',   # Tomato Red
    'hashed_password': '#FF4500',  # Orange Red
    'ip_address': '#9370DB',  # Medium Purple
    'phone': '#32CD32',      # Lime Green
    'name': '#4682B4',       # Steel Blue
    'address': '#DAA520',    # Goldenrod
    'domain': '#FF1493',     # Deep Pink
    'company': '#4B0082',    # Indigo
    'social': '#00CED1',     # Dark Turquoise
    'url': '#708090',        # Slate Gray
    'vin': '#8B4513',        # Saddle Brown
    'database_name': '#2F4F4F'  # Dark Slate Gray
}

# Load search cache
with open('cache/search_cache.pkl', 'rb') as f:
    search_cache = pickle.load(f)

# Create structures
all_nodes = {}
all_edges = {}
node_id_counter = 0
breach_to_nodes = defaultdict(list)  # Track which nodes belong to which breach

# Process each cached search
for key, data in search_cache.items():
    if 'results' in data and data['results']:
        print(f"\nProcessing {key}: {len(data['results'])} results")
        
        for breach in data['results']:
            breach_name = breach.get('database_name', 'Unknown')
            
            # Process all data types in the breach
            for data_type, values in breach.items():
                if data_type in ['id', 'database_name'] or not values:
                    continue
                    
                if isinstance(values, list):
                    for value in values:
                        if not value:
                            continue
                            
                        # Determine node type
                        if data_type == 'email':
                            node_type = 'email'
                        elif data_type == 'username':
                            node_type = 'username'
                        elif data_type == 'password':
                            node_type = 'password'
                        elif data_type == 'hashed_password':
                            node_type = 'hashed_password'
                        elif data_type == 'ip_address':
                            node_type = 'ip_address'
                        elif data_type == 'phone':
                            node_type = 'phone'
                        elif data_type == 'name':
                            node_type = 'name'
                        elif data_type == 'address':
                            node_type = 'address'
                        elif data_type == 'domain':
                            node_type = 'domain'
                        elif data_type == 'company':
                            node_type = 'company'
                        elif data_type == 'social':
                            node_type = 'social'
                        elif data_type == 'url':
                            node_type = 'url'
                        elif data_type == 'vin':
                            node_type = 'vin'
                        elif data_type == 'dob':
                            node_type = 'name'  # DOB usually goes with name
                        else:
                            node_type = 'email'  # Default
                        
                        node_key = f"{node_type}_{value}"
                        
                        if node_key not in all_nodes:
                            color = NODE_COLORS.get(node_type, '#00CED1')
                            
                            # Truncate label for hashes
                            label = value
                            if node_type == 'hashed_password' and len(value) > 20:
                                label = value[:8] + '...' + value[-8:]
                            
                            all_nodes[node_key] = {
                                "id": node_id_counter,
                                "label": label,
                                "type": node_type,
                                "color": {
                                    "background": "#000000",
                                    "border": color,
                                    "highlight": {
                                        "background": "#1a1a1a",
                                        "border": color
                                    }
                                },
                                "borderWidth": 2,
                                "borderWidthSelected": 3,
                                "data": {
                                    "value": value,
                                    "label": label,
                                    "breach": breach_name,
                                    "breachData": breach
                                },
                                "font": {
                                    "multi": "html",
                                    "size": 12,
                                    "color": "#FFFFFF"
                                },
                                "shape": "box",
                                "size": 25
                            }
                            
                            breach_to_nodes[breach_name].append(node_id_counter)
                            node_id_counter += 1

# Create edges between nodes from the same breach
edge_id = 0
for breach_name, node_ids in breach_to_nodes.items():
    if len(node_ids) > 1:
        # Connect all nodes from the same breach
        for i in range(len(node_ids)):
            for j in range(i + 1, len(node_ids)):
                edge_key = f"edge_{node_ids[i]}_{node_ids[j]}"
                if edge_key not in all_edges:
                    all_edges[edge_key] = {
                        "id": edge_key,
                        "from": node_ids[i],
                        "to": node_ids[j],
                        "title": f"Same breach: {breach_name}",
                        "color": {
                            "color": "#666666",
                            "highlight": "#ff0000"
                        },
                        "width": 2,
                        "arrows": {
                            "to": {"enabled": False}
                        }
                    }
                    edge_id += 1

print(f"\n✓ Created {len(all_nodes)} nodes with proper types and colors")
print(f"✓ Created {len(all_edges)} edges connecting nodes from same breaches")

# Create graph state
graph_state = {
    "nodes": list(all_nodes.values()),
    "edges": list(all_edges.values()),
    "nodeIdCounter": node_id_counter,
    "valueToNodeMap": [[k, v["id"]] for k, v in all_nodes.items()],
    "breachConnections": [[breach, nodes] for breach, nodes in breach_to_nodes.items()],
    "nodeSearchQueries": [],
    "activeQueryNodes": [],
    "autoShowQueries": False,
    "anchoredNodes": []
}

# Save graph state
with open('cache/graph_state.json', 'w') as f:
    json.dump(graph_state, f)

print(f"\n✅ FULL RESTORE COMPLETE!")
print(f"Nodes by type:")
type_counts = defaultdict(int)
for node in all_nodes.values():
    type_counts[node['type']] += 1
for node_type, count in sorted(type_counts.items()):
    color = NODE_COLORS.get(node_type, '#00CED1')
    print(f"  {node_type}: {count} nodes (color: {color})")
print("\nRefresh your browser - your graph is fully restored with colors and connections!")