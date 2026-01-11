#!/usr/bin/env python3
import json

# Read the corrupted file
with open('cache/graph_state_backup.json', 'rb') as f:
    data = f.read()

# Try to extract valid JSON
for end_pos in range(len(data)-1, len(data)-50000, -1):
    try:
        # Try different end patterns
        test_data = data[:end_pos]
        if test_data.endswith(b'}'):
            test_data += b']}'  # Complete the structure
        elif test_data.endswith(b'}]'):
            test_data += b'}'
        elif test_data.endswith(b'"'):
            test_data += b'}]}'
            
        parsed = json.loads(test_data.decode('utf-8', errors='ignore'))
        
        # Check if we got valid data
        if 'nodes' in parsed and len(parsed['nodes']) > 0:
            print(f"✓ Successfully extracted {len(parsed['nodes'])} nodes!")
            print(f"✓ Found {len(parsed.get('edges', []))} edges!")
            
            # Save the recovered data
            with open('cache/graph_state_recovered.json', 'w') as out:
                json.dump(parsed, out)
            
            print("\nRecovered graph saved to graph_state_recovered.json")
            print("Copy it to graph_state.json to restore!")
            break
            
    except Exception as e:
        continue
else:
    print("Could not recover the JSON. Check browser localStorage!")