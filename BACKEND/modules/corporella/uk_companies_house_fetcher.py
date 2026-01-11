"""
UK Companies House API Fetcher
Standalone function to fetch company data when user clicks "Fetch from UK Companies House" button
"""

from companies_house_api import CompaniesHouseAPI
from typing import Dict, Any, Optional
import os

def fetch_uk_company(company_number: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch complete UK company data from Companies House

    Args:
        company_number: UK company registration number (e.g., "08804411")
        api_key: Optional Companies House API key (or from CH_API_KEY env var)

    Returns:
        {
            "ok": True/False,
            "source": "companies_house",
            "company_number": str,
            "details": {...},       # Company details
            "officers": [...],      # List of officers
            "psc": [...],          # Beneficial owners
            "filing_history": [...] # Recent filings
        }
    """
    try:
        # Initialize API client
        ch = CompaniesHouseAPI(api_key)

        if not ch.ch_api_key:
            return {
                "ok": False,
                "source": "companies_house",
                "error": "No API key provided. Set CH_API_KEY environment variable or pass api_key parameter."
            }

        # Fetch all data in parallel (well, sequentially for now, but could parallelize)
        details = ch.get_company_details(company_number)
        officers = ch.get_company_officers(company_number)
        psc = ch.get_psc_data(company_number)
        filing_history = ch.get_filing_history(company_number)

        if not details:
            return {
                "ok": False,
                "source": "companies_house",
                "error": f"Company {company_number} not found or API error"
            }

        return {
            "ok": True,
            "source": "companies_house",
            "company_number": company_number,
            "details": details,
            "officers": officers,
            "psc": psc,  # Persons with Significant Control (beneficial owners)
            "filing_history": filing_history,
            "timestamp": details.get('date_of_creation'),
            # Flatten key fields for easy access
            "company_name": details.get('company_name'),
            "company_status": details.get('company_status'),
            "company_type": details.get('type'),
            "jurisdiction": "GB",
            "registered_office_address": details.get('registered_office_address'),
            "sic_codes": details.get('sic_codes', [])
        }

    except Exception as e:
        return {
            "ok": False,
            "source": "companies_house",
            "error": str(e)
        }


# Example usage
if __name__ == "__main__":
    import json

    # Test with Revolut Ltd
    print("Testing UK Companies House API with Revolut Ltd...")
    result = fetch_uk_company("08804411")

    if result["ok"]:
        print("\n✅ SUCCESS")
        print(f"Company: {result['company_name']}")
        print(f"Status: {result['company_status']}")
        print(f"Type: {result['company_type']}")
        print(f"Officers: {len(result['officers'])}")
        print(f"PSC (Beneficial Owners): {len(result['psc'])}")
        print(f"Filing History: {len(result['filing_history'])}")

        print("\nFull Response:")
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"\n❌ ERROR: {result['error']}")
