#!/usr/bin/env python3
"""
Corporella Company ID Search Engine
"""

import requests
import json
from typing import Dict, Any, List

class CorporellaCompanyIdEngine:
    code = 'CCI'
    name = 'Corporella Company ID'

    def __init__(self, company_id: str):
        self.company_id = company_id
        self.occrp_api_key = "d130af08b5ab43b3825d99e7c92a1b5a"  # Should use env var in prod
        self.occrp_base_url = "https://aleph.occrp.org/api/2/"

    def search(self) -> List[Dict[str, Any]]:
        """Search OCCRP Aleph database by Company ID (Registration Number)."""
        try:
            # Aleph indexes registration numbers, so 'q' works.
            # We can also filter by schema 'Company' to be precise.
            params = {
                'q': self.company_id,
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
            
            results = []
            for item in data.get('results', []):
                # Verify if ID matches (fuzzy check)
                reg_num = item.get('properties', {}).get('registrationNumber', [])
                if reg_num and self.company_id in reg_num:
                    confidence = 'high'
                else:
                    confidence = 'medium' # Aleph fuzzy matching

                results.append({
                    'source': 'occrp_aleph',
                    'data': item,
                    'entity_type': 'company_id',
                    'entity_value': self.company_id,
                    'confidence': confidence
                })
            
            return results
            
        except requests.exceptions.RequestException as e:
            return [{'error': str(e)}]

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        engine = CorporellaCompanyIdEngine(sys.argv[1])
        print(engine.search())
    else:
        print("Usage: python company_id.py <id>")
