#!/usr/bin/env python3
"""Test WHOIS data extraction"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import whois
import json

# Test reverse WHOIS for a name
print("Testing reverse WHOIS for 'John Smith'...")
try:
    result = whois.reverse_whois_search("John Smith", "basicSearchTerms")
    print(f"Found {result['domains_count']} domains")
    if result['domains']:
        print(f"First few domains: {result['domains'][:3]}")
        
        # Get details for first domain
        if result['domains']:
            domain = result['domains'][0]
            print(f"\nGetting WHOIS history for {domain}...")
            history = whois.get_whois_history(domain)
            if history:
                record = history[0]
                print("\nRecord keys:", list(record.keys()))
                
                # Check for raw text
                if 'rawText' in record:
                    print("\nRaw text preview (first 500 chars):")
                    print(record['rawText'][:500])
                    
                    # Extract some data manually
                    raw_text = record['rawText']
                    import re
                    
                    # Find emails
                    emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', raw_text)
                    print(f"\nEmails found: {emails[:5]}")
                    
                    # Find registrant info
                    registrant_match = re.search(r'Registrant Name:\s*(.+)', raw_text)
                    if registrant_match:
                        print(f"Registrant Name: {registrant_match.group(1)}")
                    
                    # Find addresses
                    street_match = re.search(r'Registrant Street:\s*(.+)', raw_text)
                    if street_match:
                        print(f"Registrant Street: {street_match.group(1)}")
                        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()