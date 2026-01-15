#!/usr/bin/env python3
"""
PSC Data Bridge
===============

Unified bridge for ingesting PSC data from multiple sources:
1. UK PSC snapshot (Companies House JSONL)
2. OpenOwnership BODS data
3. UK Land Registry Overseas Ownership

Provides IO Matrix integration:
- Field codes 281-327 for PSC data
- Field codes 311-327 for cross-country routing
- Integration with Torpedo for foreign registry lookups

Usage:
    # Ingest UK PSC data
    python psc_bridge.py --ingest-uk /path/to/psc-snapshot.txt

    # Ingest property ownership data
    python psc_bridge.py --ingest-property /path/to/overseas-ownership.csv

    # Run cross-country analysis
    python psc_bridge.py --analyze-foreign DE

    # Export for IO Matrix
    python psc_bridge.py --export-routes
"""

import asyncio
import json
import csv
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[6]
load_dotenv(PROJECT_ROOT / ".env")

from .psc_indices import PSCIndexManager
from .uk_psc_search import UKPSCSearcher
from .jurisdiction_router import JurisdictionRouter


class PSCDataBridge:
    """Unified bridge for PSC data ingestion and IO Matrix integration."""

    # IO Matrix field codes for PSC data
    IO_FIELD_CODES = {
        # PSC records
        "psc_records": 281,
        "psc_person_name": 282,
        "psc_person_dob_month": 283,
        "psc_person_dob_year": 284,
        "psc_person_nationality": 285,
        "psc_person_country_of_residence": 286,
        "psc_corporate_name": 287,
        "psc_corporate_reg_number": 288,
        "psc_corporate_jurisdiction": 289,
        "psc_corporate_legal_form": 290,
        "psc_corporate_legal_authority": 291,
        "psc_corporate_place_registered": 292,
        "psc_natures_of_control": 293,
        "psc_ownership_band": 294,
        "psc_voting_band": 295,
        "psc_right_to_appoint_directors": 296,
        "psc_significant_influence": 297,
        "psc_address_full": 298,
        "psc_address_premises": 299,
        "psc_address_locality": 300,
        "psc_address_region": 301,
        "psc_address_postal_code": 302,
        "psc_address_country": 303,
        "psc_notified_date": 304,
        "psc_ceased_date": 305,
        "psc_is_active": 306,
        "psc_data_source": 307,
        "psc_snapshot_date": 308,
        "psc_etag": 309,
        "psc_links": 310,
        # Cross-country routing
        "foreign_company_jurisdiction": 311,
        "foreign_company_reg_number": 312,
        "foreign_company_name": 313,
        "foreign_company_country_code": 314,
        # Property ownership
        "property_owner_jurisdiction": 315,
        "property_owner_company_reg": 316,
        "property_owner_country_code": 317,
        "property_title_number": 318,
        "property_address": 319,
        "property_price_paid": 320,
        "property_transfer_date": 321,
        # OpenOwnership BODS
        "oo_statement_id": 322,
        "oo_statement_type": 323,
        "oo_publication_date": 324,
        "oo_interested_party": 325,
        "oo_interest_level": 326,
        # Lists
        "psc_foreign_companies_list": 327,
    }

    def __init__(self):
        self.index_manager = PSCIndexManager()
        self.searcher = UKPSCSearcher()
        self.router = JurisdictionRouter()

    async def close(self):
        """Close all connections."""
        await self.index_manager.close()
        await self.searcher.close()
        await self.router.close()

    # =========================================================================
    # INGESTION METHODS
    # =========================================================================

    async def ingest_uk_psc(
        self,
        snapshot_path: Path,
        batch_size: int = 1000,
        max_records: int = None
    ) -> Dict[str, Any]:
        """
        Ingest UK PSC snapshot from Companies House.

        File format: JSONL, one company per line
        Source: http://download.companieshouse.gov.uk/en_pscdata.html
        """
        return await self.searcher.ingest_snapshot(
            snapshot_path,
            batch_size=batch_size,
            max_records=max_records
        )

    async def ingest_property_ownership(
        self,
        csv_path: Path,
        max_records: int = None
    ) -> Dict[str, int]:
        """
        Ingest UK Land Registry overseas ownership data.

        File format: CSV with columns:
        - Title Number, Property Address, County, District
        - Owner Name, Owner Country, Owner Address
        - Price Paid, Date of Transfer
        """
        csv_path = Path(csv_path)
        if not csv_path.exists():
            raise FileNotFoundError(f"Property file not found: {csv_path}")

        await self.index_manager.create_indices()

        stats = {"total": 0, "indexed": 0, "errors": 0}

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                stats["total"] += 1

                try:
                    record = {
                        "title_number": row.get("Title Number", "").strip(),
                        "property_address": row.get("Property Address", "").strip(),
                        "locality": row.get("Locality", "").strip(),
                        "district": row.get("District", "").strip(),
                        "county": row.get("County", "").strip(),
                        "postcode": row.get("Postcode", "").strip(),
                        "tenure": row.get("Tenure", "").strip(),
                        "owner_name": row.get("Owner Name", "").strip(),
                        "owner_country_name": row.get("Owner Country", "").strip(),
                        "owner_registration_number": row.get("Owner Reg Number", "").strip(),
                        "owner_address": row.get("Owner Address", "").strip(),
                        "indexed_at": datetime.now().isoformat(),
                    }

                    # Normalize country code
                    record["owner_country_code"] = self.index_manager.normalize_country_code(
                        record["owner_country_name"]
                    )

                    # Parse price
                    price_str = row.get("Price Paid", "").strip().replace(",", "")
                    if price_str:
                        try:
                            record["price_paid"] = float(price_str)
                        except ValueError:
                            pass

                    # Parse date
                    date_str = row.get("Date of Transfer", "").strip()
                    if date_str:
                        record["date_of_transfer"] = date_str

                    await self.index_manager.es.index(
                        index=self.index_manager.INDEX_PROPERTY_OWNERS,
                        id=record["title_number"],
                        body=record
                    )
                    stats["indexed"] += 1

                except Exception as e:
                    stats["errors"] += 1
                    if stats["errors"] <= 10:
                        print(f"  Error: {e}")

                if stats["total"] % 10000 == 0:
                    print(f"  Processed {stats['total']:,} properties...")

                if max_records and stats["total"] >= max_records:
                    break

        print(f"\nProperty ingestion complete:")
        print(f"  Total: {stats['total']:,}")
        print(f"  Indexed: {stats['indexed']:,}")
        print(f"  Errors: {stats['errors']:,}")

        return stats

    # =========================================================================
    # ANALYSIS METHODS
    # =========================================================================

    async def analyze_foreign_jurisdictions(self) -> Dict[str, Any]:
        """Get overview of foreign corporate PSCs by jurisdiction."""
        jurisdictions = await self.index_manager.get_all_foreign_psc_jurisdictions()

        # Add registry info for each
        enriched = {}
        for code, count in jurisdictions.items():
            registry = self.router.get_registry_info(code)
            enriched[code] = {
                "count": count,
                "name": registry["name"] if registry else "Unknown",
                "registry": registry["registry"] if registry else None,
                "torpedo_supported": registry["torpedo_supported"] if registry else False,
            }

        return {
            "total_foreign_pscs": sum(jurisdictions.values()),
            "jurisdictions_count": len(jurisdictions),
            "by_jurisdiction": enriched,
        }

    async def analyze_jurisdiction(self, country_code: str) -> Dict[str, Any]:
        """Detailed analysis of foreign PSCs from a specific jurisdiction."""
        # Get PSC data
        psc_data = await self.index_manager.search_foreign_corporate_pscs_by_country(
            country_code
        )

        # Get property data
        property_data = await self.index_manager.search_uk_properties_by_owner_country(
            country_code
        )

        # Get registry info
        registry_info = self.router.get_registry_info(country_code)

        return {
            "jurisdiction": country_code.upper(),
            "registry_info": registry_info,
            "psc_analysis": {
                "total_companies": psc_data["total"],
                "sample": psc_data["companies"][:10],
                "by_legal_form": psc_data.get("aggregations", {}).get("by_legal_form", {}),
            },
            "property_analysis": {
                "total_properties": property_data["total"],
                "sample": property_data["properties"][:10],
                "total_value": property_data.get("aggregations", {}).get("total_value", {}),
                "by_county": property_data.get("aggregations", {}).get("by_county", {}),
            },
        }

    # =========================================================================
    # IO MATRIX INTEGRATION
    # =========================================================================

    def export_io_routes(self) -> List[Dict]:
        """Export PSC routes for IO Matrix rules.json."""
        routes = [
            {
                "id": "UK_PSC_FROM_COMPANY",
                "label": "Get PSCs for UK company",
                "requires_any": [14],  # company_id (company_number)
                "returns": [281, 282, 287, 289, 293, 294],
                "resources": [{
                    "type": "module",
                    "import": "CYMONIDES.scripts.psc.uk_psc_search.UKPSCSearcher",
                    "method": "search_by_company_number"
                }]
            },
            {
                "id": "UK_PSC_FROM_PERSON",
                "label": "Find companies where person is PSC",
                "requires_any": [7],  # person_name
                "returns": [13, 14, 293, 294],
                "resources": [{
                    "type": "module",
                    "import": "CYMONIDES.scripts.psc.uk_psc_search.UKPSCSearcher",
                    "method": "search_by_person_name"
                }]
            },
            {
                "id": "FOREIGN_COMPANY_JURISDICTION_EXTRACT",
                "label": "Extract foreign company jurisdictions from PSC",
                "requires_any": [14],  # company_id
                "returns": [311, 312, 313, 314, 327],
                "resources": [{
                    "type": "module",
                    "import": "CYMONIDES.scripts.psc.jurisdiction_router.JurisdictionRouter",
                    "method": "extract_foreign_jurisdictions"
                }]
            },
            {
                "id": "PSC_BY_COUNTRY_GB",
                "label": "Find UK companies with PSCs from jurisdiction",
                "requires_any": [314],  # foreign_company_country_code
                "returns": [13, 14, 287, 288, 289, 293],
                "resources": [{
                    "type": "module",
                    "import": "CYMONIDES.scripts.psc.psc_indices.PSCIndexManager",
                    "method": "search_foreign_corporate_pscs_by_country"
                }]
            },
            {
                "id": "UK_PROPERTY_BY_OWNER_COUNTRY",
                "label": "Find UK properties by owner jurisdiction",
                "requires_any": [317],  # property_owner_country_code
                "returns": [318, 319, 320, 321, 156],
                "resources": [{
                    "type": "module",
                    "import": "CYMONIDES.scripts.psc.psc_indices.PSCIndexManager",
                    "method": "search_uk_properties_by_owner_country"
                }]
            },
            {
                "id": "ROUTE_FOREIGN_COMPANY_TO_REGISTRY",
                "label": "Route foreign company to home registry (via Torpedo)",
                "requires_any": [287, 311],  # psc_corporate_name or foreign_company_jurisdiction
                "returns": [13, 14, 37, 38, 39, 40],  # company profile fields
                "resources": [{
                    "type": "module",
                    "import": "CYMONIDES.scripts.psc.jurisdiction_router.JurisdictionRouter",
                    "method": "route_to_registry"
                }]
            },
        ]

        return routes

    def get_field_mapping(self) -> Dict[int, str]:
        """Get IO Matrix field code mapping."""
        return {v: k for k, v in self.IO_FIELD_CODES.items()}


# CLI
async def main():
    import argparse

    parser = argparse.ArgumentParser(description="PSC Data Bridge")
    parser.add_argument("--ingest-uk", help="Path to UK PSC snapshot (JSONL)")
    parser.add_argument("--ingest-property", help="Path to UK property ownership CSV")
    parser.add_argument("--max-records", type=int, help="Max records to ingest")
    parser.add_argument("--analyze-foreign", help="Analyze foreign PSCs from jurisdiction (e.g., DE, BVI)")
    parser.add_argument("--analyze-all", action="store_true", help="Analyze all foreign jurisdictions")
    parser.add_argument("--export-routes", action="store_true", help="Export IO Matrix routes")
    parser.add_argument("--create-indices", action="store_true", help="Create Elasticsearch indices")

    args = parser.parse_args()

    bridge = PSCDataBridge()

    try:
        if args.create_indices:
            await bridge.index_manager.connect()
            await bridge.index_manager.create_indices()
            print("Indices created successfully")

        elif args.ingest_uk:
            stats = await bridge.ingest_uk_psc(
                Path(args.ingest_uk),
                max_records=args.max_records
            )
            print(json.dumps(stats, indent=2))

        elif args.ingest_property:
            stats = await bridge.ingest_property_ownership(
                Path(args.ingest_property),
                max_records=args.max_records
            )
            print(json.dumps(stats, indent=2))

        elif args.analyze_foreign:
            result = await bridge.analyze_jurisdiction(args.analyze_foreign)
            print(json.dumps(result, indent=2, default=str))

        elif args.analyze_all:
            result = await bridge.analyze_foreign_jurisdictions()
            print(json.dumps(result, indent=2))

        elif args.export_routes:
            routes = bridge.export_io_routes()
            print(json.dumps(routes, indent=2))

        else:
            parser.print_help()

    finally:
        await bridge.close()


if __name__ == "__main__":
    asyncio.run(main())
