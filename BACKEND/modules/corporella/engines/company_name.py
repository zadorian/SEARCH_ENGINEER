#!/usr/bin/env python3
"""
Corporella Company Name Search Engine
"""

import requests
import json
from typing import Dict, Any, List

class CorporellaCompanyNameEngine:
    code = 'CCN'
    name = 'Corporella Company Name'

    def __init__(self, company_name: str):
        self.company_name = company_name
        self.occrp_api_key = "d130af08b5ab43b3825d99e7c92a1b5a"  # Should use env var in prod
        self.occrp_base_url = "https://aleph.occrp.org/api/2/"

    def search(self) -> List[Dict[str, Any]]:
        """Search OCCRP Aleph database for company information."""
        try:
            params = {
                'q': self.company_name,
                'filter:schema': 'Company',
                'limit': 10,
                'api_key': self.occrp_api_key
            }
            
            headers = {
                'Authorization': f'ApiKey {self.occrp_api_key}'
            }
            
            response = requests.get(
                f"{self.occrp_base_url}search",
                params=params,
                headers=headers
            )
            
            response.raise_for_status()
            data = response.json()
            
            # Format as list of dicts for consistency
            results = []
            for item in data.get('results', []):
                results.append({
                    'source': 'occrp_aleph',
                    'data': item,
                    'entity_type': 'company',
                    'entity_value': item.get('name', self.company_name)
                })
            
            return results
            
        except requests.exceptions.RequestException as e:
            return [{'error': str(e)}]

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        engine = CorporellaCompanyNameEngine(sys.argv[1])
        print(engine.search())
    else:
        print("Usage: python company_name.py <name>")
