#!/usr/bin/env python3
"""
DeHashed Engine for DRILL_SEARCH
Implements advanced search capabilities strictly following DeHashed V2 API documentation.
"""

import os
import requests
import json
from typing import Dict, Any, Optional, List

class DeHashedEngine:
    """
    DeHashed Search Engine Wrapper (V2 API)
    """
    
    BASE_URL = "https://api.dehashed.com/v2/search"
    
    VALID_FIELDS = [
        "name", "email", "username", "ip_address", "password", "hashed_password",
        "vin", "license_plate", "address", "phone", "social", "cryptocurrency_address", "domain"
    ]
    
    def __init__(self, query: str = None, event_emitter=None, api_key: str = None, email: str = None):
        self.query = query
        self.event_emitter = event_emitter
        # API credentials: V2 API primarily uses the API Key in the header.
        # Legacy email/key auth might not be needed for V2 if just the key works, 
        # but we'll keep the env var read for compatibility with how secrets are stored.
        self.api_key = api_key or os.getenv("DEHASHED_API_KEY")
        
        if not self.api_key:
            print("Warning: DEHASHED_API_KEY not found in environment variables.")

    def build_query(self, 
                    term: str, 
                    field: str = None, 
                    use_regex: bool = False, 
                    use_wildcard: bool = False,
                    database_name: str = None) -> str:
        """
        Constructs a DeHashed compliant query string string for the 'query' parameter.
        
        Args:
            term: The search term.
            field: Specific field to search.
            use_regex: Boolean to enable regex search (logic for splitting email).
            use_wildcard: Boolean to enable wildcard search (logic for splitting email).
            database_name: Optional specific data origin to target.
            
        Returns:
            Formatted query string.
        """
        query_parts = []
        
        if field and field not in self.VALID_FIELDS:
            print(f"Warning: '{field}' is not a standard DeHashed field. Valid fields: {', '.join(self.VALID_FIELDS)}")

        # "Regexing/Wildcarding Emails requires that you split the query into email and domain."
        if field == "email" and (use_regex or use_wildcard):
            if "@" in term:
                try:
                    user_part, domain_part = term.split("@", 1)
                    # Construct complex query for email with regex/wildcard
                    query_parts.append(f"email:{user_part}")
                    query_parts.append(f"domain:{domain_part}")
                except ValueError:
                    query_parts.append(f"email:{term}")
            else:
                 query_parts.append(f"email:{term}")
        else:
            if field:
                # Quote terms with spaces if not already quoted
                if " " in term and not term.startswith('"') and not term.endswith('"'):
                    term = f'"{term}"'
                query_parts.append(f"{field}:{term}")
            else:
                # Global search or auto-detection
                query_parts.append(term)
                
        if database_name:
            query_parts.append(f"database_name={database_name}")
            
        return "&".join(query_parts)

    def search(self, 
               custom_query: str = None, 
               page: int = 1, 
               size: int = 100, 
               wildcard: bool = False, 
               regex: bool = False, 
               de_dupe: bool = False) -> Dict[str, Any]:
        """
        Execute the search against DeHashed V2 API.
        
        Args:
            custom_query: Override the instance query with a new one.
            page: Page number (max depth 10,000).
            size: Number of results per page (max 10,000).
            wildcard: Enable wildcard search.
            regex: Enable regex search.
            de_dupe: Enable deduplication.
            
        Returns:
            Dictionary containing search results.
        """
        if not self.api_key:
            return {"error": "Missing API Key"}

        search_query = custom_query or self.query
        if not search_query:
            return {"error": "No query provided"}

        if self.event_emitter:
            self.event_emitter('entity_progress', {
                'type': 'search_start',
                'message': f'🔍 Searching DeHashed (V2) for: {search_query}',
                'source': 'DeHashed'
            })

        try:
            headers = {
                "Content-Type": "application/json",
                "DeHashed-Api-Key": self.api_key,
                "Accept": "application/json" 
            }
            
            payload = {
                "query": search_query,
                "page": page,
                "size": size,
                "wildcard": wildcard,
                "regex": regex,
                "de_dupe": de_dupe
            }
            
            # Using POST request as per V2 docs
            response = requests.post(
                self.BASE_URL,
                json=payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                entries = data.get("entries", [])
                
                # If entries is None, it returns as null in JSON, so default to empty list
                if entries is None:
                    entries = []

                if self.event_emitter:
                    self.event_emitter('entity_progress', {
                        'type': 'source_complete',
                        'message': f'✅ DeHashed found {len(entries)} records',
                        'source': 'DeHashed',
                        'count': len(entries)
                    })
                
                return entries
            else:
                error_msg = f"DeHashed API Error: {response.status_code} - {response.text}"
                print(error_msg)
                return {"error": error_msg}
                
        except Exception as e:
            print(f"DeHashed Exception: {e}")
            return {"error": str(e)}

# Helper for direct execution/testing
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        q = sys.argv[1]
        de = DeHashedEngine()
        # Example default usage
        print(json.dumps(de.search(custom_query=q, size=5), indent=2))
    else:
        print("Usage: python dehashed_engine.py <query>")