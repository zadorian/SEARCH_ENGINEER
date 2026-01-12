#!/usr/bin/env python3
"""
PSC Jurisdiction Router
=======================

Routes foreign companies extracted from PSC data to their respective country registries.

When a corporate PSC is found in UK data (e.g., a German GmbH controlling a UK Ltd),
this router:
1. Extracts the foreign jurisdiction
2. Routes to Torpedo for full company profile from that country's registry
3. Aggregates results for cross-country analysis

Usage:
    # Extract and route foreign companies from PSC data
    python jurisdiction_router.py --extract-from-pscs "12345678"

    # Route a specific foreign company to its registry
    python jurisdiction_router.py --route "Some GmbH" --jurisdiction DE
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[6]
load_dotenv(PROJECT_ROOT / ".env")

# Add BACKEND modules to path
sys.path.insert(0, str(PROJECT_ROOT / "BACKEND" / "modules"))

from .psc_indices import PSCIndexManager


class JurisdictionRouter:
    """Routes foreign companies to their country-specific registries."""

    # Jurisdiction to registry mapping (extends Torpedo)
    JURISDICTION_REGISTRIES = {
        # European
        "DE": {"name": "Germany", "registry": "handelsregister.de", "torpedo_supported": True},
        "FR": {"name": "France", "registry": "infogreffe.fr", "torpedo_supported": True},
        "NL": {"name": "Netherlands", "registry": "kvk.nl", "torpedo_supported": True},
        "BE": {"name": "Belgium", "registry": "kbo.be", "torpedo_supported": True},
        "LU": {"name": "Luxembourg", "registry": "rcsl.lu", "torpedo_supported": True},
        "CH": {"name": "Switzerland", "registry": "zefix.ch", "torpedo_supported": True},
        "AT": {"name": "Austria", "registry": "firmenbuch.at", "torpedo_supported": True},
        "IT": {"name": "Italy", "registry": "registroimprese.it", "torpedo_supported": True},
        "ES": {"name": "Spain", "registry": "rmc.es", "torpedo_supported": True},
        "IE": {"name": "Ireland", "registry": "cro.ie", "torpedo_supported": True},
        "CY": {"name": "Cyprus", "registry": "cybc.org.cy", "torpedo_supported": False},
        "MT": {"name": "Malta", "registry": "mbr.org.mt", "torpedo_supported": False},

        # Offshore
        "VG": {"name": "British Virgin Islands", "registry": "bvi.gov.vg", "torpedo_supported": False},
        "KY": {"name": "Cayman Islands", "registry": "ciregistry.gov.ky", "torpedo_supported": False},
        "BM": {"name": "Bermuda", "registry": "roc.bm", "torpedo_supported": False},
        "JE": {"name": "Jersey", "registry": "jerseyfsc.org", "torpedo_supported": False},
        "GG": {"name": "Guernsey", "registry": "guernseyregistry.com", "torpedo_supported": False},
        "IM": {"name": "Isle of Man", "registry": "gov.im", "torpedo_supported": False},
        "GI": {"name": "Gibraltar", "registry": "companieshouse.gi", "torpedo_supported": False},
        "PA": {"name": "Panama", "registry": "registro-publico.gob.pa", "torpedo_supported": False},
        "SC": {"name": "Seychelles", "registry": "sra.sc", "torpedo_supported": False},
        "MU": {"name": "Mauritius", "registry": "mns.mu", "torpedo_supported": False},

        # Asia/Middle East
        "HK": {"name": "Hong Kong", "registry": "cr.gov.hk", "torpedo_supported": False},
        "SG": {"name": "Singapore", "registry": "acra.gov.sg", "torpedo_supported": False},
        "AE": {"name": "UAE", "registry": "various", "torpedo_supported": False},

        # Americas
        "US": {"name": "United States", "registry": "various", "torpedo_supported": True},
    }

    # IO Matrix field codes
    FIELD_CODES = {
        "foreign_company_jurisdiction": 311,
        "foreign_company_reg_number": 312,
        "foreign_company_name": 313,
        "foreign_company_country_code": 314,
        "psc_foreign_companies_list": 327,
    }

    def __init__(self):
        self.psc_index = PSCIndexManager()
        self._torpedo = None

    async def close(self):
        await self.psc_index.close()
        if self._torpedo:
            await self._torpedo.close()

    async def _get_torpedo(self):
        """Lazy-load Torpedo."""
        if self._torpedo is None:
            from TORPEDO.torpedo import Torpedo
            self._torpedo = Torpedo()
            await self._torpedo.load_sources()
        return self._torpedo

    def get_registry_info(self, country_code: str) -> Optional[Dict]:
        """Get registry information for a country code."""
        return self.JURISDICTION_REGISTRIES.get(country_code.upper())

    async def extract_foreign_jurisdictions(
        self,
        company_number: str
    ) -> Dict[str, Any]:
        """
        Extract foreign company jurisdictions from PSC data for a UK company.

        Returns list of foreign companies with their jurisdictions for routing.
        """
        # Get PSCs for this company
        pscs = await self.psc_index.search_pscs_by_company(company_number)

        foreign_companies = []
        jurisdictions_found = set()

        for psc in pscs:
            if psc.get("psc_type") == "company" and psc.get("psc_corporate_jurisdiction"):
                jurisdiction = psc.get("psc_corporate_country_code") or psc.get("psc_corporate_jurisdiction")
                jurisdiction = self.psc_index.normalize_country_code(jurisdiction)

                foreign_company = {
                    "name": psc.get("psc_name"),
                    "reg_number": psc.get("psc_corporate_reg_number"),
                    "jurisdiction": jurisdiction,
                    "legal_form": psc.get("psc_corporate_legal_form"),
                    "natures_of_control": psc.get("natures_of_control", []),
                    "ownership_band": psc.get("ownership_band"),
                    "registry_info": self.get_registry_info(jurisdiction),
                }

                foreign_companies.append(foreign_company)
                jurisdictions_found.add(jurisdiction)

        return {
            "company_number": company_number,
            "foreign_companies": foreign_companies,
            "jurisdictions": list(jurisdictions_found),
            "total_foreign_pscs": len(foreign_companies),
            "field_codes": {
                "psc_foreign_companies_list": self.FIELD_CODES["psc_foreign_companies_list"],
            }
        }

    async def route_to_registry(
        self,
        company_name: str,
        jurisdiction: str,
        reg_number: str = None,
    ) -> Dict[str, Any]:
        """
        Route a foreign company to its registry via Torpedo.

        Returns full company profile from the foreign registry.
        """
        jurisdiction = jurisdiction.upper()
        registry_info = self.get_registry_info(jurisdiction)

        if not registry_info:
            return {
                "success": False,
                "error": f"Unknown jurisdiction: {jurisdiction}",
                "company_name": company_name,
            }

        if not registry_info.get("torpedo_supported"):
            return {
                "success": False,
                "error": f"Jurisdiction {jurisdiction} ({registry_info['name']}) not yet supported by Torpedo",
                "registry": registry_info["registry"],
                "company_name": company_name,
                "recommendation": "Manual search required",
            }

        # Route via Torpedo
        torpedo = await self._get_torpedo()

        result = await torpedo.fetch_profile(
            query=company_name,
            jurisdiction=jurisdiction,
        )

        if result.get("success"):
            return {
                "success": True,
                "company_name": company_name,
                "jurisdiction": jurisdiction,
                "registry": registry_info["registry"],
                "profile": result.get("profile", {}),
                "source": result.get("source", {}),
            }
        else:
            return {
                "success": False,
                "error": result.get("error"),
                "company_name": company_name,
                "jurisdiction": jurisdiction,
            }

    async def enrich_foreign_pscs(
        self,
        company_number: str,
        max_enrichments: int = 5,
    ) -> Dict[str, Any]:
        """
        Extract foreign PSCs and enrich them via their respective registries.

        This is the full cross-country routing pipeline:
        UK Company → PSC Data → Foreign Companies → Foreign Registries → Full Profiles
        """
        # Step 1: Extract foreign jurisdictions
        extraction = await self.extract_foreign_jurisdictions(company_number)

        if not extraction["foreign_companies"]:
            return {
                "company_number": company_number,
                "message": "No foreign corporate PSCs found",
                "enriched": [],
            }

        # Step 2: Route to registries
        enriched = []
        errors = []

        for i, foreign in enumerate(extraction["foreign_companies"][:max_enrichments]):
            registry_info = foreign.get("registry_info", {})

            if registry_info.get("torpedo_supported"):
                print(f"  Enriching: {foreign['name']} ({foreign['jurisdiction']})")

                profile_result = await self.route_to_registry(
                    company_name=foreign["name"],
                    jurisdiction=foreign["jurisdiction"],
                    reg_number=foreign.get("reg_number"),
                )

                if profile_result.get("success"):
                    enriched.append({
                        **foreign,
                        "enriched_profile": profile_result.get("profile", {}),
                    })
                else:
                    errors.append({
                        "company": foreign["name"],
                        "error": profile_result.get("error"),
                    })
            else:
                errors.append({
                    "company": foreign["name"],
                    "error": f"Registry not supported: {foreign['jurisdiction']}",
                })

        return {
            "company_number": company_number,
            "total_foreign_pscs": len(extraction["foreign_companies"]),
            "enriched_count": len(enriched),
            "enriched": enriched,
            "errors": errors,
            "jurisdictions": extraction["jurisdictions"],
        }

    async def aggregate_by_jurisdiction(
        self,
        jurisdiction: str,
    ) -> Dict[str, Any]:
        """
        Get all foreign corporate PSCs from a specific jurisdiction.

        Example: "Find all German companies that are PSCs of UK companies"
        """
        result = await self.psc_index.search_foreign_corporate_pscs_by_country(
            jurisdiction
        )

        # Add registry info
        result["registry_info"] = self.get_registry_info(jurisdiction)

        return result


# CLI
async def main():
    import argparse

    parser = argparse.ArgumentParser(description="PSC Jurisdiction Router")
    parser.add_argument("--extract-from-pscs", help="Extract foreign jurisdictions from PSC data for a UK company number")
    parser.add_argument("--route", help="Company name to route to foreign registry")
    parser.add_argument("--jurisdiction", help="Jurisdiction code (DE, FR, VG, etc.)")
    parser.add_argument("--enrich", help="Enrich foreign PSCs for a UK company number")
    parser.add_argument("--aggregate", help="Aggregate PSCs by jurisdiction code")
    parser.add_argument("--list-registries", action="store_true", help="List supported registries")

    args = parser.parse_args()

    router = JurisdictionRouter()

    try:
        if args.list_registries:
            print("Supported Jurisdictions:")
            for code, info in sorted(router.JURISDICTION_REGISTRIES.items()):
                status = "Torpedo" if info["torpedo_supported"] else "Manual"
                print(f"  {code}: {info['name']} ({info['registry']}) [{status}]")

        elif args.extract_from_pscs:
            result = await router.extract_foreign_jurisdictions(args.extract_from_pscs)
            print(json.dumps(result, indent=2, default=str))

        elif args.route and args.jurisdiction:
            result = await router.route_to_registry(args.route, args.jurisdiction)
            print(json.dumps(result, indent=2, default=str))

        elif args.enrich:
            result = await router.enrich_foreign_pscs(args.enrich)
            print(json.dumps(result, indent=2, default=str))

        elif args.aggregate:
            result = await router.aggregate_by_jurisdiction(args.aggregate)
            print(json.dumps(result, indent=2, default=str))

        else:
            parser.print_help()

    finally:
        await router.close()


if __name__ == "__main__":
    asyncio.run(main())
