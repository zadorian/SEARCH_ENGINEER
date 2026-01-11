#!/usr/bin/env python3
"""
FCA Register API Client
=======================

UK Financial Conduct Authority Register API integration.
Supports lookup by:
- Firm Reference Number (FRN)
- Company name search
- Individual (person) search by name

Returns:
- Authorisation status
- Permissions and licences
- Authorised individuals
- Disciplinary history and fines
- Appointed representatives

Usage:
    from BACKEND.modules.EYE_D.regulatory.fca_api import FCAClient

    client = FCAClient()
    firm = await client.search_firm("Barclays")
    individuals = await client.search_individual("John Smith")
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import httpx
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parents[5]
load_dotenv(PROJECT_ROOT / ".env")


class FCAClient:
    """UK FCA Register API Client."""

    BASE_URL = "https://register.fca.org.uk/services"

    # Field code mapping for IO Matrix
    FIELD_CODES = {
        "fca_frn": 328,
        "fca_firm_name": 329,
        "fca_status": 330,
        "fca_business_type": 331,
        "fca_status_effective_date": 332,
        "fca_permissions": 333,
        "fca_requirements": 334,
        "fca_individuals": 335,
        "fca_appointed_representatives": 336,
        "fca_address": 337,
        "fca_passport": 338,
        "fca_regulators": 339,
        "fca_waivers": 340,
        "fca_exclusions": 341,
        "fca_disciplinary_history": 342,
        "fca_fines": 343,
        "fca_exceptional_info": 344,
        "fca_individual_name": 345,
        "fca_individual_irn": 346,
        "fca_individual_status": 347,
        "fca_individual_controlled_functions": 348,
        "fca_individual_firm_history": 349,
    }

    def __init__(self, api_key: str = None, auth_email: str = None):
        self.api_key = api_key or os.getenv("FCA_API_KEY")
        self.auth_email = auth_email or os.getenv("FCA_AUTH_EMAIL")
        self.http = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        await self.http.aclose()

    def _headers(self) -> Dict[str, str]:
        return {
            "x-auth-email": self.auth_email or "",
            "x-auth-key": self.api_key or "",
            "Content-Type": "application/json",
            "User-Agent": "DrillSearch-FCA/1.0",
        }

    def has_credentials(self) -> bool:
        return bool(self.api_key and self.auth_email)

    # ─────────────────────────────────────────────────────────────
    # Firm Lookup
    # ─────────────────────────────────────────────────────────────

    async def get_firm_by_frn(self, frn: str) -> Dict[str, Any]:
        """Get firm details by FRN (Firm Reference Number)."""
        if not self.has_credentials():
            return {"success": False, "error": "Missing FCA_API_KEY and FCA_AUTH_EMAIL"}

        endpoint = f"{self.BASE_URL}/V0.1/Firm/{frn}"

        try:
            resp = await self.http.get(endpoint, headers=self._headers())

            if resp.status_code == 401:
                return {"success": False, "error": "Unauthorised: Invalid API key or email"}
            if resp.status_code == 404:
                return {"success": False, "error": "Firm not found"}

            resp.raise_for_status()
            data = resp.json()

            # Parse the response
            records = data.get("Data", [])
            if not records:
                return {"success": False, "error": "No firm data returned"}

            firm = records[0]
            return {
                "success": True,
                "frn": frn,
                "firm": self._parse_firm(firm),
                "raw": firm,
            }

        except httpx.HTTPError as e:
            return {"success": False, "error": f"HTTP error: {e}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def search_firm(self, query: str, limit: int = 20) -> Dict[str, Any]:
        """Search for firms by name."""
        if not self.has_credentials():
            return {"success": False, "error": "Missing FCA_API_KEY and FCA_AUTH_EMAIL"}

        # FCA search endpoint
        endpoint = f"{self.BASE_URL}/V0.1/Search"
        params = {
            "q": query,
            "type": "firm",
            "pageSize": limit,
        }

        try:
            resp = await self.http.get(endpoint, headers=self._headers(), params=params)
            resp.raise_for_status()
            data = resp.json()

            records = data.get("Data", [])
            firms = []

            for record in records:
                frn = record.get("FRN") or record.get("Firm Reference Number")
                if frn:
                    # Get full firm details
                    firm_data = await self.get_firm_by_frn(str(frn))
                    if firm_data.get("success"):
                        firms.append(firm_data["firm"])
                    else:
                        # Just use search result data
                        firms.append({
                            "frn": frn,
                            "name": record.get("Organisation Name") or record.get("Name"),
                            "status": record.get("Status"),
                        })

            return {
                "success": True,
                "query": query,
                "count": len(firms),
                "firms": firms,
            }

        except httpx.HTTPError as e:
            return {"success": False, "error": f"HTTP error: {e}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _parse_firm(self, firm: Dict) -> Dict[str, Any]:
        """Parse firm data into structured format."""
        return {
            "frn": firm.get("FRN") or firm.get("Firm Reference Number"),
            "name": firm.get("Organisation Name"),
            "status": firm.get("Status"),
            "business_type": firm.get("Business Type"),
            "status_effective_date": firm.get("Status Effective Date"),
            # Related endpoints (URLs for further data)
            "endpoints": {
                "individuals": firm.get("Individuals"),
                "permissions": firm.get("Permissions"),
                "requirements": firm.get("Requirements"),
                "passport": firm.get("Passport"),
                "regulators": firm.get("Regulators"),
                "appointed_representatives": firm.get("Appointed Representative"),
                "address": firm.get("Address"),
                "waivers": firm.get("Waivers"),
                "exclusions": firm.get("Exclusions"),
                "disciplinary_history": firm.get("DisciplinaryHistory"),
            },
            "exceptional_info": firm.get("Exceptional Info Details", []),
        }

    # ─────────────────────────────────────────────────────────────
    # Firm Details (Permissions, Individuals, Fines)
    # ─────────────────────────────────────────────────────────────

    async def get_firm_permissions(self, frn: str) -> Dict[str, Any]:
        """Get firm's regulatory permissions (licences)."""
        endpoint = f"{self.BASE_URL}/V0.1/Firm/{frn}/Permissions"

        try:
            resp = await self.http.get(endpoint, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()

            permissions = data.get("Data", [])
            return {
                "success": True,
                "frn": frn,
                "permissions": [
                    {
                        "permission": p.get("Permission"),
                        "investment_type": p.get("Investment Type"),
                        "customer_type": p.get("Customer Type"),
                        "status": p.get("Status"),
                        "effective_date": p.get("Effective Date"),
                    }
                    for p in permissions
                ],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_firm_individuals(self, frn: str) -> Dict[str, Any]:
        """Get authorised individuals at a firm."""
        endpoint = f"{self.BASE_URL}/V0.1/Firm/{frn}/Individuals"

        try:
            resp = await self.http.get(endpoint, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()

            individuals = data.get("Data", [])
            return {
                "success": True,
                "frn": frn,
                "individuals": [
                    {
                        "name": ind.get("Name") or ind.get("Full Name"),
                        "irn": ind.get("IRN") or ind.get("Individual Reference Number"),
                        "status": ind.get("Status"),
                        "controlled_functions": ind.get("Controlled Functions", []),
                        "effective_date": ind.get("Effective Date"),
                    }
                    for ind in individuals
                ],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_firm_disciplinary_history(self, frn: str) -> Dict[str, Any]:
        """Get disciplinary actions and fines for a firm."""
        endpoint = f"{self.BASE_URL}/V0.1/Firm/{frn}/DisciplinaryHistory"

        try:
            resp = await self.http.get(endpoint, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()

            actions = data.get("Data", [])
            fines = []
            other_actions = []

            for action in actions:
                action_parsed = {
                    "action_type": action.get("Action Type"),
                    "action_date": action.get("Action Date"),
                    "description": action.get("Description"),
                    "fine_amount": action.get("Fine Amount"),
                    "currency": action.get("Currency", "GBP"),
                    "link": action.get("Link"),
                }

                if action.get("Fine Amount"):
                    fines.append(action_parsed)
                else:
                    other_actions.append(action_parsed)

            return {
                "success": True,
                "frn": frn,
                "has_disciplinary_history": len(actions) > 0,
                "fines": fines,
                "fines_total": sum(float(f.get("fine_amount", 0) or 0) for f in fines),
                "other_actions": other_actions,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_full_firm_profile(self, frn: str) -> Dict[str, Any]:
        """Get complete firm profile with all details."""
        # Fetch all in parallel
        firm_task = self.get_firm_by_frn(frn)
        permissions_task = self.get_firm_permissions(frn)
        individuals_task = self.get_firm_individuals(frn)
        disciplinary_task = self.get_firm_disciplinary_history(frn)

        firm, permissions, individuals, disciplinary = await asyncio.gather(
            firm_task, permissions_task, individuals_task, disciplinary_task,
            return_exceptions=True
        )

        # Handle exceptions
        if isinstance(firm, Exception):
            firm = {"success": False, "error": str(firm)}
        if isinstance(permissions, Exception):
            permissions = {"success": False, "error": str(permissions)}
        if isinstance(individuals, Exception):
            individuals = {"success": False, "error": str(individuals)}
        if isinstance(disciplinary, Exception):
            disciplinary = {"success": False, "error": str(disciplinary)}

        return {
            "success": firm.get("success", False),
            "frn": frn,
            "firm": firm.get("firm") if firm.get("success") else None,
            "permissions": permissions.get("permissions", []) if permissions.get("success") else [],
            "individuals": individuals.get("individuals", []) if individuals.get("success") else [],
            "disciplinary": disciplinary if disciplinary.get("success") else {},
            "errors": {
                k: v.get("error") for k, v in {
                    "firm": firm, "permissions": permissions,
                    "individuals": individuals, "disciplinary": disciplinary
                }.items() if not v.get("success")
            },
        }

    # ─────────────────────────────────────────────────────────────
    # Individual Lookup
    # ─────────────────────────────────────────────────────────────

    async def search_individual(self, name: str, limit: int = 20) -> Dict[str, Any]:
        """Search for authorised individuals by name."""
        if not self.has_credentials():
            return {"success": False, "error": "Missing FCA_API_KEY and FCA_AUTH_EMAIL"}

        endpoint = f"{self.BASE_URL}/V0.1/Search"
        params = {
            "q": name,
            "type": "individual",
            "pageSize": limit,
        }

        try:
            resp = await self.http.get(endpoint, headers=self._headers(), params=params)
            resp.raise_for_status()
            data = resp.json()

            records = data.get("Data", [])
            individuals = []

            for record in records:
                individuals.append({
                    "name": record.get("Name") or record.get("Full Name"),
                    "irn": record.get("IRN") or record.get("Individual Reference Number"),
                    "status": record.get("Status"),
                    "current_firm": record.get("Current Employer") or record.get("Firm Name"),
                    "current_frn": record.get("FRN") or record.get("Firm Reference Number"),
                })

            return {
                "success": True,
                "query": name,
                "count": len(individuals),
                "individuals": individuals,
            }

        except httpx.HTTPError as e:
            return {"success": False, "error": f"HTTP error: {e}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_individual_by_irn(self, irn: str) -> Dict[str, Any]:
        """Get individual details by IRN (Individual Reference Number)."""
        if not self.has_credentials():
            return {"success": False, "error": "Missing FCA_API_KEY and FCA_AUTH_EMAIL"}

        endpoint = f"{self.BASE_URL}/V0.1/Individual/{irn}"

        try:
            resp = await self.http.get(endpoint, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()

            records = data.get("Data", [])
            if not records:
                return {"success": False, "error": "Individual not found"}

            ind = records[0]
            return {
                "success": True,
                "irn": irn,
                "individual": {
                    "name": ind.get("Name") or ind.get("Full Name"),
                    "status": ind.get("Status"),
                    "controlled_functions": ind.get("Controlled Functions", []),
                    "current_firm": ind.get("Current Employer"),
                    "current_frn": ind.get("FRN"),
                    "firm_history": ind.get("Previous Firms", []),
                },
            }

        except Exception as e:
            return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────
# CLI Interface
# ─────────────────────────────────────────────────────────────

async def main():
    import argparse

    parser = argparse.ArgumentParser(description="FCA Register API Client")
    parser.add_argument("--frn", help="Firm Reference Number")
    parser.add_argument("--firm-name", help="Search firms by name")
    parser.add_argument("--person-name", help="Search individuals by name")
    parser.add_argument("--irn", help="Individual Reference Number")
    parser.add_argument("--full", action="store_true", help="Get full profile (permissions, individuals, fines)")
    parser.add_argument("--output", choices=["json", "table"], default="table")

    args = parser.parse_args()

    client = FCAClient()

    try:
        if args.frn:
            if args.full:
                result = await client.get_full_firm_profile(args.frn)
            else:
                result = await client.get_firm_by_frn(args.frn)
        elif args.firm_name:
            result = await client.search_firm(args.firm_name)
        elif args.person_name:
            result = await client.search_individual(args.person_name)
        elif args.irn:
            result = await client.get_individual_by_irn(args.irn)
        else:
            parser.print_help()
            return

        if args.output == "json":
            print(json.dumps(result, indent=2, default=str))
        else:
            # Pretty print
            if result.get("success"):
                print(json.dumps(result, indent=2, default=str))
            else:
                print(f"Error: {result.get('error')}")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
