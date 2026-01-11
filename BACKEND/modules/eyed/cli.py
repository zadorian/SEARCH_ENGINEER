#!/usr/bin/env python3
"""
OSINT Tools Main Entry Point
Automatically detects input type and routes to appropriate handler
Unified with IO Matrix spec.
"""

import re
import sys
import asyncio
import json
from typing import Dict, Any, Optional

# Import the unified searcher
try:
    try:
        from .unified_osint import UnifiedSearcher
    except ImportError:
        from unified_osint import UnifiedSearcher
except ImportError:
    print("Critical Error: Could not import unified_osint. Ensure you are running from the correct directory.")
    sys.exit(1)

# Import DeHashedEngine for direct fallbacks
try:
    try:
        from .dehashed_engine import DeHashedEngine
    except ImportError:
        from dehashed_engine import DeHashedEngine
except ImportError:
    DeHashedEngine = None # Will fail gracefully if needed


def detect_input_type(query: str) -> str:
    """
    Detect the type of input query based on patterns.
    Aligned with Master Matrix definitions.
    """
    
    query_lower = query.lower()

    # Email pattern (ID 1)
    if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', query):
        return "email"
    
    # IP address pattern (ID 130)
    if re.match(r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$', query):
        return "ip_address"
    
    # Phone pattern (ID 2)
    if re.match(r'^[\]?[(]?[0-9]{1,4}[)]?[-\s\.]?[(]?[0-9]{1,4}[)]?[-\s\.]?[0-9]{1,5}[-\s\.]?[0-9]{1,5}$', query):
        return "phone"
    
    # LinkedIn URL (ID 5)
    if "linkedin.com" in query_lower:
        return "linkedin_url"
    
    # Domain pattern (ID 6)
    if re.match(r'^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$', query_lower):
        return "domain"
    
    # VIN pattern (ID 118) - 17 chars, excludes I, O, Q
    if re.match(r'^[A-HJ-NPR-Z0-9]{17}$', query.upper()):
        return "vin"

    # Address pattern (ID 35/47) - Simple heuristic: Starts with number, contains street type
    if re.match(r'^\d+\s+[A-Za-z0-9\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Way|Place|Pl|Square|Sq)', query, re.IGNORECASE):
        return "address"

    # Vehicle Reg ID (ID 23) - Placeholder regex, country specific usually
    # Assume basic alphanumeric for now if explicitly tagged
    
    # If contains spaces, likely a person's name (ID 7)
    if ' ' in query and len(query.split()) <= 4 and not any(c.isdigit() for c in query):
        return "person_name"
    
    # Username pattern (ID 3)
    if re.match(r'^[a-zA-Z0-9_.-]{3,20}$', query) and '@' not in query:
        return "username"
    
    # Default to unknown
    return "unknown"

async def run_search_async(query: str, input_type: str) -> Dict[str, Any]:
    """Async search execution"""
    handler = UnifiedSearcher()
    
    # Map input_type to UnifiedSearcher method
    if input_type == "email":
        return await handler.search_email(query)
    elif input_type == "phone":
        return await handler.search_phone(query)
    elif input_type == "ip_address":
        return await handler.search_ip(query)
    elif input_type == "domain":
        return await handler.search_whois(query) # Maps to WHOIS/Domain search
    elif input_type == "username":
        return await handler.search_username(query)
    elif input_type == "linkedin_url":
        return await handler.search_linkedin(query)
    
    # Fallbacks for types not yet fully implemented in UnifiedSearcher
    # Direct routing to DeHashed for specific fields it supports
    elif input_type in ["vin", "password", "hashed_password", "person_name", "address", "license_plate", "social"]:
        if not DeHashedEngine:
             return {"error": "DeHashedEngine not available", "query": query}
        
        engine = DeHashedEngine()
        field_map = {
            "vin": "vin",
            "password": "password",
            "hashed_password": "hashed_password",
            "person_name": "name",
            "address": "address",
            "license_plate": "license_plate",
            "social": "username" # DeHashed often maps social to username field or general search
        }
        
        field = field_map.get(input_type, "name")
        # Special handling for name to ensure quotes
        search_term = f'"{query}"' if input_type == "person_name" and " " in query else query
        
        return {"results": engine.search(custom_query=f"{field}:{search_term}"), "subtype": input_type}
    
    else:
        return {
            "error": f"Input type '{input_type}' handler not found",
            "query": query,
            "detected_type": input_type
        }

def search(query: str, input_type: Optional[str] = None) -> Dict[str, Any]:
    """Synchronous wrapper for search"""
    if not input_type:
        input_type = detect_input_type(query)
    
    print(f"🔍 Detected input type: {input_type}")
    print(f"🔎 Searching for: {query}")
    
    return asyncio.run(run_search_async(query, input_type))

def main():
    """
    Command-line interface
    Supports standard arguments: <query> [type]
    OR single JSON argument: '{"query": "...", "type": "..."}'
    """
    if len(sys.argv) < 2:
        print("Usage: python cli.py <query> [type]")
        print("OR:    python cli.py '{\"query\": \"...\", \"type\": \"...\"}'")
        sys.exit(1)
    
    first_arg = sys.argv[1]
    query = None
    input_type = None

    # Check for JSON input
    if first_arg.strip().startswith('{'):
        try:
            data = json.loads(first_arg)
            # Handle standard Matrix input format
            # Matrix router sends: { inputs: { field: value }, entityType: ... }
            if 'inputs' in data:
                # Extract first value from inputs dict
                inputs = data.get('inputs', {})
                if inputs:
                    # Prefer specific keys if available
                    query = inputs.get('email') or inputs.get('phone') or inputs.get('domain') or inputs.get('username') or list(inputs.values())[0]
                
                input_type = data.get('entityType')
            else:
                # Direct simple JSON
                query = data.get('query') or data.get('q') or data.get('value')
                input_type = data.get('type') or data.get('input_type')
        except json.JSONDecodeError:
            # Fallback to standard args if JSON parse fails
            query = first_arg
            input_type = sys.argv[2] if len(sys.argv) > 2 else None
    else:
        # Standard arguments
        query = first_arg
        input_type = sys.argv[2] if len(sys.argv) > 2 else None

    if not query:
        print(json.dumps({"error": "No query provided"}))
        sys.exit(1)
    
    results = search(query, input_type)
    
    print(json.dumps(results, indent=2, default=str))

if __name__ == "__main__":
    main()
