#!/usr/bin/env python3
import json
import re

print("Searching for edges in backup file...")

# Read the corrupted backup
with open('cache/graph_state_backup.json', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# Look for edges array anywhere in the file
print(f"File size: {len(content)} bytes")

# Try multiple patterns
patterns = [
    r'"edges":\s*\[(.*?)\],\s*"nodeIdCounter"',
    r'"edges":\s*\[(.*?)\],\s*"[^"]+":',
    r'"edges":\[(.*?)\],"'
]

for pattern in patterns:
    print(f"\nTrying pattern: {pattern[:30]}...")
    match = re.search(pattern, content, re.DOTALL)
    if match:
        edges_str = '[' + match.group(1) + ']'
        # Clean up incomplete entries
        edges_str = re.sub(r',\s*\{[^}]*$', '', edges_str)
        edges_str = re.sub(r',\s*$', '', edges_str)
        
        try:
            edges = json.loads(edges_str)
            print(f"✓ Found {len(edges)} edges!")
            
            if edges:
                # Update the current graph_state.json
                with open('cache/graph_state.json', 'r') as f:
                    current = json.load(f)
                
                current['edges'] = edges
                
                with open('cache/graph_state.json', 'w') as f:
                    json.dump(current, f)
                
                print(f"✓ Updated graph_state.json with {len(edges)} edges!")
                print("✓ Refresh browser and click FORCE LOAD!")
                
                # Show sample edges
                print("\nSample edges:")
                for edge in edges[:5]:
                    print(f"  {edge.get('from')} -> {edge.get('to')} ({edge.get('title', 'no title')})")
                
                break
        except Exception as e:
            print(f"Error parsing edges: {e}")
else:
    print("\nCould not find edges array in backup")
    
    # Try to find any edge-like structures
    edge_pattern = r'\{"from":\d+,"to":\d+[^}]+\}'
    edges_found = re.findall(edge_pattern, content)
    if edges_found:
        print(f"\nFound {len(edges_found)} individual edge objects")
        print("First few:")
        for edge_str in edges_found[:5]:
            print(f"  {edge_str}")