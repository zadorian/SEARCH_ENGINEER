#!/usr/bin/env python3
"""
Test entity extraction service directly from CLI
"""

import json
import subprocess
import sys

def test_entity_extraction():
    """Test the entity extraction service"""
    
    test_content = """
    # Test Document
    
    John Smith, CEO of TechCorp, can be reached at john.smith@techcorp.com.
    The company is located at 123 Innovation Drive, Suite 500, San Francisco, CA 94105.
    Phone: (555) 123-4567
    """
    
    request = {
        "content": test_content,
        "command": "extract"
    }
    
    try:
        # Run the entity extraction service
        process = subprocess.Popen(
            ['python3', 'entity_extraction_service.py'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Send input and get output
        stdout, stderr = process.communicate(input=json.dumps(request))
        
        if stderr:
            print("STDERR:", stderr)
        
        if stdout:
            print("STDOUT:", stdout)
            try:
                result = json.loads(stdout)
                print("\nParsed Result:")
                print(json.dumps(result, indent=2))
            except json.JSONDecodeError as e:
                print(f"Failed to parse output: {e}")
        
    except Exception as e:
        print(f"Error running service: {e}")

if __name__ == "__main__":
    test_entity_extraction()