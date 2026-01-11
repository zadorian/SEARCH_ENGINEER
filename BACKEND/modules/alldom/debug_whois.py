#!/usr/bin/env python3
"""Debug WHOIS data to see what we're actually getting"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import whois
import json

# Test with a known name
test_name = "John Smith"
print(f"Testing reverse WHOIS for: {test_name}")

# Step 1: Reverse WHOIS
results = whois.reverse_whois_search(test_name, 'basicSearchTerms')
print(f"\nFound {results.get('domains_count', 0)} domains")

if results.get('domains') and len(results['domains']) > 0:
    # Take first domain
    test_domain = results['domains'][0]
    print(f"\nTesting with domain: {test_domain}")
    
    # Step 2: Get WHOIS history
    history = whois.get_whois_history(test_domain)
    print(f"Got {len(history) if history else 0} history records")
    
    if history and len(history) > 0:
        record = history[0]
        
        # Check what's in the record
        print("\n=== RECORD STRUCTURE ===")
        print(f"Type: {type(record)}")
        print(f"Keys: {list(record.keys()) if isinstance(record, dict) else 'NOT A DICT'}")
        
        # Check for contact fields
        print("\n=== CONTACT FIELDS ===")
        for contact_type in ['registrantContact', 'administrativeContact', 'technicalContact', 'billingContact']:
            if record.get(contact_type):
                print(f"\n{contact_type} found!")
                contact = record[contact_type]
                for k, v in contact.items():
                    if v and 'REDACTED' not in str(v).upper():
                        print(f"  {k}: {v}")
            else:
                print(f"\n{contact_type}: NOT FOUND")
        
        # Check text fields
        print("\n=== TEXT FIELDS ===")
        print(f"rawText: {len(record.get('rawText', ''))} chars")
        print(f"cleanText: {len(record.get('cleanText', ''))} chars")
        
        if record.get('rawText'):
            print("\nrawText preview:")
            print(record['rawText'][:500])
        
        if record.get('cleanText'):
            print("\ncleanText preview:")
            print(record['cleanText'][:500])
        
        # Save full record
        with open('debug_whois_record.json', 'w') as f:
            json.dump(record, f, indent=2)
        print("\n\nFull record saved to debug_whois_record.json")
    else:
        print("\nNO HISTORY RECORDS RETURNED!")
else:
    print("\nNO DOMAINS FOUND!")