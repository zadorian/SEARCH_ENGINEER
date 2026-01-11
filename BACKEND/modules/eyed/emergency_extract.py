#!/usr/bin/env python3
import json
import re

# Read the corrupted backup
with open('cache/graph_state_backup.json', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# Try to find where nodes array ends
nodes_match = re.search(r'"nodes":\s*\[(.*?)\],\s*"edges"', content, re.DOTALL)
if nodes_match:
    nodes_str = '[' + nodes_match.group(1) + ']'
    # Clean up any incomplete nodes at the end
    nodes_str = re.sub(r',\s*\{[^}]*$', '', nodes_str)
    
    try:
        nodes = json.loads(nodes_str)
        print(f"✓ Extracted {len(nodes)} nodes from backup!")
        
        # Create minimal valid graph state
        graph_state = {
            "nodes": nodes,
            "edges": [],  # We'll rebuild edges
            "nodeIdCounter": len(nodes) + 100,
            "valueToNodeMap": [],
            "breachConnections": [],
            "nodeSearchQueries": [],
            "activeQueryNodes": [],
            "autoShowQueries": False,
            "anchoredNodes": []
        }
        
        # Save it
        with open('cache/graph_state.json', 'w') as out:
            json.dump(graph_state, out)
            
        print("✓ Saved extracted nodes to graph_state.json!")
        print("✓ Your colored nodes are restored! Refresh browser!")
        
        # Show node type distribution
        types = {}
        for node in nodes:
            t = node.get('type', 'unknown')
            types[t] = types.get(t, 0) + 1
        print(f"\nNode types restored:")
        for t, count in types.items():
            print(f"  {t}: {count}")
            
    except Exception as e:
        print(f"Error parsing nodes: {e}")
else:
    print("Could not find nodes in backup file")