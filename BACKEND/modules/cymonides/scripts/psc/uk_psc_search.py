#!/usr/bin/env python3
"""
UK PSC (Persons with Significant Control) Search
=================================================

Search and ingest UK PSC data from Companies House snapshot files.

Data source:
- http://download.companieshouse.gov.uk/en_pscdata.html
- JSONL format, one company per line

Usage:
    # Search
    python uk_psc_search.py --company "Barclays"
    python uk_psc_search.py --person "John Smith"
    python uk_psc_search.py --company-number "00102498"

    # Ingest
    python uk_psc_search.py --ingest /path/to/psc-snapshot.txt
"""

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Iterator
from datetime import datetime
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[6]
load_dotenv(PROJECT_ROOT / ".env")

from .psc_indices import PSCIndexManager


class UKPSCSearcher:
    """UK PSC data searcher and ingester."""

    # PSC kind to type mapping
    KIND_TO_TYPE = {
        "individual-person-with-significant-control": "person",
        "corporate-entity-person-with-significant-control": "company",
        "legal-person-person-with-significant-control": "company",
        "super-secure-person-with-significant-control": "redacted",
    }

    # Nature of control parsing
    CONTROL_PATTERNS = {
        "ownership-of-shares-25-to-50-percent": {"ownership_band": "25-50%"},
        "ownership-of-shares-50-to-75-percent": {"ownership_band": "50-75%"},
        "ownership-of-shares-75-to-100-percent": {"ownership_band": "75-100%"},
        "ownership-of-shares-more-than-25-percent": {"ownership_band": "more-than-25%"},
        "voting-rights-25-to-50-percent": {"voting_band": "25-50%"},
        "voting-rights-50-to-75-percent": {"voting_band": "50-75%"},
        "voting-rights-75-to-100-percent": {"voting_band": "75-100%"},
        "voting-rights-more-than-25-percent": {"voting_band": "more-than-25%"},
        "right-to-appoint-and-remove-directors": {"has_right_to_appoint_directors": True},
        "significant-influence-or-control": {"has_significant_influence": True},
    }

    def __init__(self):
        self.index_manager = PSCIndexManager()

    async def close(self):
        await self.index_manager.close()

    def parse_psc_record(self, raw: Dict) -> Optional[Dict[str, Any]]:
        """Parse a raw PSC JSONL record into structured format."""
        company_number = raw.get("company_number")
        data = raw.get("data", {})

        if not company_number or not data:
            return None

        kind = data.get("kind", "")
        psc_type = self.KIND_TO_TYPE.get(kind, "unknown")

        if psc_type == "unknown":
            return None

        record = {
            "company_number": company_number,
            "psc_kind": kind,
            "psc_type": psc_type,
            "psc_id": data.get("etag") or data.get("links", {}).get("self", "").split("/")[-1],
            "etag": data.get("etag"),
            "links": data.get("links"),
            "data_source": "uk_psc",
        }

        # Name
        name = data.get("name", "")
        if psc_type == "person":
            name_elements = data.get("name_elements", {})
            record["psc_name"] = name
            record["psc_forename"] = name_elements.get("forename")
            record["psc_surname"] = name_elements.get("surname")
            record["psc_name_normalized"] = name.upper().replace(",", " ").strip()

            # DOB (partial - month/year only for privacy)
            dob = data.get("date_of_birth", {})
            record["psc_dob_month"] = dob.get("month")
            record["psc_dob_year"] = dob.get("year")

            # Nationality & residence
            record["psc_nationality"] = data.get("nationality")
            record["psc_country_of_residence"] = data.get("country_of_residence")

        elif psc_type == "company":
            record["psc_name"] = name
            record["psc_name_normalized"] = name.upper()

            # Corporate identification (CRITICAL for cross-country routing)
            identification = data.get("identification", {})
            record["psc_corporate_reg_number"] = identification.get("registration_number")
            record["psc_corporate_jurisdiction"] = identification.get("country_registered")
            record["psc_corporate_legal_form"] = identification.get("legal_form")
            record["psc_corporate_legal_authority"] = identification.get("legal_authority")
            record["psc_corporate_place_registered"] = identification.get("place_registered")

        # Address
        address = data.get("address", {})
        if address:
            record["address_premises"] = address.get("premises")
            record["address_line_1"] = address.get("address_line_1")
            record["address_locality"] = address.get("locality")
            record["address_region"] = address.get("region")
            record["address_postal_code"] = address.get("postal_code")
            record["address_country"] = address.get("country")

            # Full address
            parts = [
                address.get("premises"),
                address.get("address_line_1"),
                address.get("address_line_2"),
                address.get("locality"),
                address.get("region"),
                address.get("postal_code"),
                address.get("country"),
            ]
            record["address_full"] = ", ".join(p for p in parts if p)

        # Nature of control
        natures = data.get("natures_of_control", [])
        record["natures_of_control"] = natures

        # Parse control bands
        for nature in natures:
            if nature in self.CONTROL_PATTERNS:
                record.update(self.CONTROL_PATTERNS[nature])

        # Dates
        record["notified_on"] = data.get("notified_on")
        record["ceased_on"] = data.get("ceased_on")

        return record

    def read_psc_snapshot(self, file_path: Path) -> Iterator[Dict]:
        """Read PSC snapshot JSONL file, yielding parsed records."""
        with open(file_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    raw = json.loads(line)
                    record = self.parse_psc_record(raw)
                    if record:
                        yield record
                except json.JSONDecodeError as e:
                    if line_num % 100000 == 0:
                        print(f"  Line {line_num}: JSON error - {e}")
                    continue

    async def ingest_snapshot(
        self,
        file_path: Path,
        batch_size: int = 1000,
        max_records: int = None,
    ) -> Dict[str, int]:
        """Ingest PSC snapshot file into Elasticsearch."""
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"PSC snapshot file not found: {file_path}")

        # Ensure indices exist
        await self.index_manager.create_indices()

        stats = {
            "total": 0,
            "persons": 0,
            "companies": 0,
            "foreign_corporates": 0,
            "errors": 0,
        }

        batch = []
        snapshot_date = datetime.now().strftime("%Y-%m-%d")

        print(f"Ingesting PSC data from: {file_path}")

        for record in self.read_psc_snapshot(file_path):
            record["snapshot_date"] = snapshot_date

            batch.append(record)
            stats["total"] += 1

            if record["psc_type"] == "person":
                stats["persons"] += 1
            elif record["psc_type"] == "company":
                stats["companies"] += 1
                if record.get("psc_corporate_jurisdiction"):
                    stats["foreign_corporates"] += 1

            if len(batch) >= batch_size:
                await self._index_batch(batch)
                batch = []

                if stats["total"] % 10000 == 0:
                    print(f"  Processed {stats['total']:,} records...")

            if max_records and stats["total"] >= max_records:
                break

        # Index remaining
        if batch:
            await self._index_batch(batch)

        print(f"\nIngestion complete:")
        print(f"  Total records: {stats['total']:,}")
        print(f"  Person PSCs: {stats['persons']:,}")
        print(f"  Corporate PSCs: {stats['companies']:,}")
        print(f"  Foreign corporates: {stats['foreign_corporates']:,}")

        return stats

    async def _index_batch(self, batch: List[Dict]):
        """Index a batch of PSC records."""
        for record in batch:
            try:
                await self.index_manager.index_psc_record(record)
            except Exception as e:
                print(f"  Error indexing record: {e}")

    # Search methods delegate to index manager
    async def search_by_company_number(self, company_number: str) -> List[Dict]:
        """Search PSCs by company number."""
        return await self.index_manager.search_pscs_by_company(company_number)

    async def search_by_person_name(self, person_name: str) -> List[Dict]:
        """Search companies where a person is PSC."""
        return await self.index_manager.search_companies_by_psc_person(person_name)

    async def search_foreign_by_country(self, country_code: str) -> Dict:
        """Search foreign corporate PSCs by country."""
        return await self.index_manager.search_foreign_corporate_pscs_by_country(country_code)


# CLI
async def main():
    import argparse

    parser = argparse.ArgumentParser(description="UK PSC Search and Ingest")
    parser.add_argument("--company", help="Search by company name")
    parser.add_argument("--company-number", help="Search by company number")
    parser.add_argument("--person", help="Search by person name")
    parser.add_argument("--country", help="Search foreign corporate PSCs by country code")
    parser.add_argument("--ingest", help="Path to PSC snapshot file to ingest")
    parser.add_argument("--max-records", type=int, help="Max records to ingest (for testing)")

    args = parser.parse_args()

    searcher = UKPSCSearcher()

    try:
        if args.ingest:
            stats = await searcher.ingest_snapshot(
                Path(args.ingest),
                max_records=args.max_records,
            )
            print(json.dumps(stats, indent=2))
        elif args.company_number:
            results = await searcher.search_by_company_number(args.company_number)
            print(json.dumps(results, indent=2, default=str))
        elif args.person:
            results = await searcher.search_by_person_name(args.person)
            print(json.dumps(results, indent=2, default=str))
        elif args.country:
            results = await searcher.search_foreign_by_country(args.country)
            print(json.dumps(results, indent=2, default=str))
        else:
            parser.print_help()
    finally:
        await searcher.close()


if __name__ == "__main__":
    asyncio.run(main())
