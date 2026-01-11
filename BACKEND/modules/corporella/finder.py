#!/usr/bin/env python3
"""
Component 1: Finder
Search for companies based on various criteria
"""

import os
import requests
from typing import Dict, List, Optional, Any
from functools import lru_cache
from pathlib import Path

# Load environment variables from project root .env
from dotenv import load_dotenv
project_root = Path(__file__).parent.parent
load_dotenv(project_root / ".env")


class CompanyFinder:
    """Search for companies by name, officer, LEI, etc."""

    def __init__(self):
        self.oc_api_key = os.getenv("OPENCORPORATES_API_KEY") or os.getenv("OPEN_CORPORATES_API_TOKEN")
        self.oc_base_url = "https://api.opencorporates.com/v0.4"

    def search_by_name(
        self,
        name: str,
        jurisdiction: Optional[str] = None,
        per_page: int = 10
    ) -> Dict[str, Any]:
        """
        Search OpenCorporates by company name

        Args:
            name: Company name to search
            jurisdiction: ISO country code (e.g., "us_ca", "gb")
            per_page: Results per page (max 100)

        Returns:
            {
                "ok": True/False,
                "companies": [...],
                "total_count": int,
                "source": "opencorporates"
            }
        """
        params = {
            "q": name,
            "per_page": per_page
        }

        if jurisdiction:
            params["jurisdiction_code"] = jurisdiction

        if self.oc_api_key:
            params["api_token"] = self.oc_api_key

        try:
            response = requests.get(
                f"{self.oc_base_url}/companies/search",
                params=params,
                timeout=30
            )

            # Retry without token if authentication fails
            if response.status_code == 401 and params.get("api_token"):
                params.pop("api_token")
                response = requests.get(
                    f"{self.oc_base_url}/companies/search",
                    params=params,
                    timeout=30
                )

            response.raise_for_status()
            data = response.json()

            companies = []
            for item in data.get("results", {}).get("companies", []):
                company = item.get("company", {})
                companies.append({
                    "name": company.get("name"),
                    "company_number": company.get("company_number"),
                    "jurisdiction_code": company.get("jurisdiction_code"),
                    "incorporation_date": company.get("incorporation_date"),
                    "current_status": company.get("current_status"),
                    "company_type": company.get("company_type"),
                    "registered_address": company.get("registered_address_in_full"),
                    "registry_url": company.get("registry_url"),
                    "opencorporates_url": company.get("opencorporates_url"),
                    "source": "opencorporates"
                })

            return {
                "ok": True,
                "companies": companies,
                "total_count": data.get("results", {}).get("total_count", 0),
                "source": "opencorporates"
            }

        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "companies": [],
                "total_count": 0,
                "source": "opencorporates"
            }

    def search_by_officer(
        self,
        officer_name: str,
        per_page: int = 10
    ) -> Dict[str, Any]:
        """
        Search OpenCorporates for companies where person is officer/director

        Args:
            officer_name: Name of person to search
            per_page: Results per page

        Returns:
            {
                "ok": True/False,
                "officers": [...],
                "total_count": int,
                "source": "opencorporates"
            }
        """
        params = {
            "q": officer_name,
            "per_page": per_page
        }

        if self.oc_api_key:
            params["api_token"] = self.oc_api_key

        try:
            response = requests.get(
                f"{self.oc_base_url}/officers/search",
                params=params,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            officers = []
            for item in data.get("results", {}).get("officers", []):
                officer = item.get("officer", {})
                company = officer.get("company", {})

                officers.append({
                    "officer_name": officer.get("name"),
                    "position": officer.get("position"),
                    "start_date": officer.get("start_date"),
                    "end_date": officer.get("end_date"),
                    "company_name": company.get("name"),
                    "company_number": company.get("company_number"),
                    "jurisdiction_code": company.get("jurisdiction_code"),
                    "opencorporates_url": officer.get("opencorporates_url"),
                    "source": "opencorporates"
                })

            return {
                "ok": True,
                "officers": officers,
                "total_count": data.get("results", {}).get("total_count", 0),
                "source": "opencorporates"
            }

        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "officers": [],
                "total_count": 0,
                "source": "opencorporates"
            }

    @lru_cache(maxsize=128)
    def get_company_details(
        self,
        jurisdiction_code: str,
        company_number: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed company record including officers and filings

        Args:
            jurisdiction_code: e.g., "us_ca", "gb"
            company_number: Company registration number

        Returns:
            Detailed company data or None
        """
        if not jurisdiction_code or not company_number:
            return None

        if self.oc_api_key:
            params = {"api_token": self.oc_api_key}
        else:
            params = {}

        try:
            url = f"{self.oc_base_url}/companies/{jurisdiction_code}/{company_number}"
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            company = data.get("results", {}).get("company", {})

            return {
                "ok": True,
                "company": company,
                "source": "opencorporates"
            }

        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "source": "opencorporates"
            }


# Simple usage example
if __name__ == "__main__":
    finder = CompanyFinder()

    # Search by name
    print("=== Search by Name: Apple Inc ===")
    results = finder.search_by_name("Apple Inc", jurisdiction="us_ca")

    if results["ok"]:
        print(f"Found {results['total_count']} companies")
        for company in results['companies'][:3]:
            print(f"  - {company['name']} ({company['jurisdiction_code']})")
            print(f"    Number: {company['company_number']}")
            print(f"    Status: {company['current_status']}")
    else:
        print(f"Error: {results['error']}")

    # Search by officer
    print("\n=== Search by Officer: Tim Cook ===")
    officer_results = finder.search_by_officer("Tim Cook")

    if officer_results["ok"]:
        print(f"Found {officer_results['total_count']} officer records")
        for officer in officer_results['officers'][:3]:
            print(f"  - {officer['officer_name']} at {officer['company_name']}")
            print(f"    Position: {officer['position']}")
    else:
        print(f"Error: {officer_results['error']}")
