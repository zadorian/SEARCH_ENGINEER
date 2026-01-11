#!/usr/bin/env python3
"""Test WHOIS contact data extraction"""

from __future__ import annotations

if __name__ != "__main__":
    import pytest

    pytest.skip("EYE-D test scripts are manual; run directly", allow_module_level=True)

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import whois
import json

# Test reverse WHOIS for a name
print("Testing contact data extraction...")
try:
    result = whois.reverse_whois_search("John Smith", "basicSearchTerms")
    if result['domains']:
        domain = result['domains'][0]
        print(f"\nGetting WHOIS history for {domain}...")
        history = whois.get_whois_history(domain)
        if history:
            record = history[0]
            
            # Check registrant contact
            if 'registrantContact' in record:
                print("\nRegistrant Contact:")
                print(json.dumps(record['registrantContact'], indent=2))
            
            # Check administrative contact
            if 'administrativeContact' in record:
                print("\nAdministrative Contact:")
                print(json.dumps(record['administrativeContact'], indent=2))
                
            # Check cleanText
            if 'cleanText' in record:
                print("\nClean Text (first 1000 chars):")
                print(record['cleanText'][:1000])
                
            # Check rawText length
            print(f"\nRaw text length: {len(record.get('rawText', ''))}")
            print(f"Clean text length: {len(record.get('cleanText', ''))}")
                        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
