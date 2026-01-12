#!/usr/bin/env python3
"""
PSC Index Manager
=================

Manages per-country Elasticsearch indices for PSC data.
Enables cross-jurisdiction searches like:
- "Find all German companies that are PSCs of UK companies"
- "Find UK properties owned by BVI companies"

Index Strategy:
- psc_gb: All UK PSC records (individual + corporate)
- psc_gb_corporate_by_country: Corporate PSCs grouped by foreign jurisdiction
- psc_property_owners_by_country: UK property owners by jurisdiction
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from elasticsearch import AsyncElasticsearch
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[6]
load_dotenv(PROJECT_ROOT / ".env")


class PSCIndexManager:
    """Manages PSC Elasticsearch indices with per-country routing."""

    # Index names
    INDEX_PSC_GB = "psc_gb"
    INDEX_PSC_CORPORATE_BY_COUNTRY = "psc_gb_corporate_by_country"
    INDEX_PROPERTY_OWNERS = "uk_land_registry_overseas"

    # Elasticsearch mapping for main PSC index
    PSC_GB_MAPPING = {
        "mappings": {
            "properties": {
                # Target company (the UK company with PSCs)
                "company_number": {"type": "keyword"},
                "company_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},

                # PSC identification
                "psc_id": {"type": "keyword"},
                "psc_kind": {"type": "keyword"},  # individual-person-with-significant-control, corporate-entity-*
                "psc_type": {"type": "keyword"},  # person, company

                # PSC name
                "psc_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "psc_name_normalized": {"type": "keyword"},

                # Individual PSC fields
                "psc_forename": {"type": "keyword"},
                "psc_surname": {"type": "keyword"},
                "psc_dob_month": {"type": "integer"},
                "psc_dob_year": {"type": "integer"},
                "psc_nationality": {"type": "keyword"},
                "psc_country_of_residence": {"type": "keyword"},

                # Corporate PSC fields (CRITICAL for cross-country routing)
                "psc_corporate_reg_number": {"type": "keyword"},
                "psc_corporate_jurisdiction": {"type": "keyword"},  # ISO 2-letter: DE, FR, BVI, etc.
                "psc_corporate_legal_form": {"type": "keyword"},
                "psc_corporate_legal_authority": {"type": "keyword"},
                "psc_corporate_place_registered": {"type": "keyword"},

                # Control nature
                "natures_of_control": {"type": "keyword"},  # Array: ownership-of-shares-25-to-50-percent, etc.
                "ownership_band": {"type": "keyword"},  # 25-50%, 50-75%, 75-100%, more-than-25%
                "voting_band": {"type": "keyword"},
                "has_right_to_appoint_directors": {"type": "boolean"},
                "has_significant_influence": {"type": "boolean"},

                # Address
                "address_full": {"type": "text"},
                "address_premises": {"type": "keyword"},
                "address_line_1": {"type": "text"},
                "address_locality": {"type": "keyword"},
                "address_region": {"type": "keyword"},
                "address_postal_code": {"type": "keyword"},
                "address_country": {"type": "keyword"},

                # Dates
                "notified_on": {"type": "date", "format": "yyyy-MM-dd||yyyy-MM||yyyy"},
                "ceased_on": {"type": "date", "format": "yyyy-MM-dd||yyyy-MM||yyyy"},
                "is_active": {"type": "boolean"},

                # Metadata
                "etag": {"type": "keyword"},
                "links": {"type": "object", "enabled": False},
                "snapshot_date": {"type": "date"},
                "indexed_at": {"type": "date"},
                "data_source": {"type": "keyword"},  # uk_psc, openownership
            }
        },
        "settings": {
            "number_of_shards": 3,
            "number_of_replicas": 1,
            "analysis": {
                "normalizer": {
                    "lowercase_normalizer": {
                        "type": "custom",
                        "filter": ["lowercase", "asciifolding"]
                    }
                }
            }
        }
    }

    # Mapping for corporate PSCs grouped by foreign jurisdiction
    PSC_CORPORATE_BY_COUNTRY_MAPPING = {
        "mappings": {
            "properties": {
                # UK company being controlled
                "uk_company_number": {"type": "keyword"},
                "uk_company_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},

                # Foreign corporate PSC
                "psc_corporate_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "psc_corporate_reg_number": {"type": "keyword"},
                "psc_corporate_jurisdiction": {"type": "keyword"},  # FILTERABLE by country
                "psc_corporate_country_code": {"type": "keyword"},  # ISO 2-letter
                "psc_corporate_legal_form": {"type": "keyword"},

                # Control
                "natures_of_control": {"type": "keyword"},
                "ownership_band": {"type": "keyword"},

                # Dates
                "notified_on": {"type": "date"},
                "ceased_on": {"type": "date"},
                "is_active": {"type": "boolean"},

                "indexed_at": {"type": "date"},
            }
        }
    }

    # Mapping for UK property owners by jurisdiction
    PROPERTY_OWNERS_BY_COUNTRY_MAPPING = {
        "mappings": {
            "properties": {
                # Property details
                "title_number": {"type": "keyword"},
                "property_address": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "locality": {"type": "keyword"},
                "district": {"type": "keyword"},
                "county": {"type": "keyword"},
                "postcode": {"type": "keyword"},
                "tenure": {"type": "keyword"},

                # Owner details (CRITICAL for jurisdiction routing)
                "owner_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "owner_country_code": {"type": "keyword"},  # FILTERABLE: BVI, JE, GG, IM, etc.
                "owner_country_name": {"type": "keyword"},
                "owner_registration_number": {"type": "keyword"},
                "owner_address": {"type": "text"},

                # Transaction
                "price_paid": {"type": "float"},
                "date_of_transfer": {"type": "date"},

                "indexed_at": {"type": "date"},
            }
        }
    }

    # Country code mappings for normalization
    COUNTRY_CODE_MAP = {
        # Common variations
        "BRITISH VIRGIN ISLANDS": "VG",
        "BVI": "VG",
        "VIRGIN ISLANDS, BRITISH": "VG",
        "JERSEY": "JE",
        "GUERNSEY": "GG",
        "ISLE OF MAN": "IM",
        "CAYMAN ISLANDS": "KY",
        "BERMUDA": "BM",
        "LUXEMBOURG": "LU",
        "NETHERLANDS": "NL",
        "IRELAND": "IE",
        "GERMANY": "DE",
        "FRANCE": "FR",
        "SWITZERLAND": "CH",
        "LIECHTENSTEIN": "LI",
        "MONACO": "MC",
        "CYPRUS": "CY",
        "MALTA": "MT",
        "GIBRALTAR": "GI",
        "UNITED STATES": "US",
        "USA": "US",
        "U.S.A.": "US",
        "HONG KONG": "HK",
        "SINGAPORE": "SG",
        "UNITED ARAB EMIRATES": "AE",
        "UAE": "AE",
        "MAURITIUS": "MU",
        "SEYCHELLES": "SC",
        "PANAMA": "PA",
        "DELAWARE": "US",  # State but often used
    }

    def __init__(self, es_host: str = None):
        self.es_host = es_host or os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
        self.es = None

    async def connect(self):
        """Connect to Elasticsearch."""
        if self.es is None:
            self.es = AsyncElasticsearch([self.es_host])
        return self.es

    async def close(self):
        """Close Elasticsearch connection."""
        if self.es:
            await self.es.close()
            self.es = None

    async def create_indices(self, force_recreate: bool = False):
        """Create all PSC indices."""
        await self.connect()

        indices = [
            (self.INDEX_PSC_GB, self.PSC_GB_MAPPING),
            (self.INDEX_PSC_CORPORATE_BY_COUNTRY, self.PSC_CORPORATE_BY_COUNTRY_MAPPING),
            (self.INDEX_PROPERTY_OWNERS, self.PROPERTY_OWNERS_BY_COUNTRY_MAPPING),
        ]

        for index_name, mapping in indices:
            exists = await self.es.indices.exists(index=index_name)

            if exists and force_recreate:
                await self.es.indices.delete(index=index_name)
                exists = False

            if not exists:
                await self.es.indices.create(index=index_name, body=mapping)
                print(f"Created index: {index_name}")
            else:
                print(f"Index already exists: {index_name}")

    def normalize_country_code(self, country: str) -> str:
        """Normalize country name to ISO 2-letter code."""
        if not country:
            return ""

        country_upper = country.upper().strip()

        # Direct match
        if len(country_upper) == 2:
            return country_upper

        # Lookup in mapping
        return self.COUNTRY_CODE_MAP.get(country_upper, country_upper[:2])

    async def index_psc_record(self, record: Dict[str, Any]) -> str:
        """Index a single PSC record. Returns doc ID."""
        await self.connect()

        # Normalize and enrich
        record["indexed_at"] = datetime.now().isoformat()
        record["is_active"] = record.get("ceased_on") is None

        # Normalize country codes
        if record.get("psc_corporate_jurisdiction"):
            record["psc_corporate_country_code"] = self.normalize_country_code(
                record["psc_corporate_jurisdiction"]
            )

        # Generate doc ID
        doc_id = f"{record.get('company_number', '')}_{record.get('psc_id', '')}"

        await self.es.index(
            index=self.INDEX_PSC_GB,
            id=doc_id,
            body=record,
        )

        # If corporate PSC, also index in by-country index
        if record.get("psc_type") == "company" and record.get("psc_corporate_jurisdiction"):
            await self.es.index(
                index=self.INDEX_PSC_CORPORATE_BY_COUNTRY,
                id=doc_id,
                body={
                    "uk_company_number": record.get("company_number"),
                    "uk_company_name": record.get("company_name"),
                    "psc_corporate_name": record.get("psc_name"),
                    "psc_corporate_reg_number": record.get("psc_corporate_reg_number"),
                    "psc_corporate_jurisdiction": record.get("psc_corporate_jurisdiction"),
                    "psc_corporate_country_code": record.get("psc_corporate_country_code"),
                    "psc_corporate_legal_form": record.get("psc_corporate_legal_form"),
                    "natures_of_control": record.get("natures_of_control"),
                    "ownership_band": record.get("ownership_band"),
                    "notified_on": record.get("notified_on"),
                    "ceased_on": record.get("ceased_on"),
                    "is_active": record["is_active"],
                    "indexed_at": record["indexed_at"],
                },
            )

        return doc_id

    async def search_pscs_by_company(self, company_number: str) -> List[Dict]:
        """Search PSCs for a company by company number."""
        await self.connect()

        result = await self.es.search(
            index=self.INDEX_PSC_GB,
            body={
                "query": {
                    "term": {"company_number": company_number}
                },
                "size": 100,
            }
        )

        return [hit["_source"] for hit in result["hits"]["hits"]]

    async def search_companies_by_psc_person(self, person_name: str) -> List[Dict]:
        """Find companies where a person is a PSC."""
        await self.connect()

        result = await self.es.search(
            index=self.INDEX_PSC_GB,
            body={
                "query": {
                    "bool": {
                        "must": [
                            {"match": {"psc_name": person_name}},
                            {"term": {"psc_type": "person"}},
                        ]
                    }
                },
                "size": 100,
            }
        )

        return [hit["_source"] for hit in result["hits"]["hits"]]

    async def search_foreign_corporate_pscs_by_country(
        self,
        country_code: str,
        active_only: bool = True
    ) -> Dict[str, Any]:
        """
        Find all foreign companies from a jurisdiction that are PSCs of UK companies.

        Example: Find all German (DE) companies that are PSCs of UK companies.
        This enables cross-country routing: DE companies → UK companies they control.
        """
        await self.connect()

        query = {
            "bool": {
                "must": [
                    {"term": {"psc_corporate_country_code": country_code.upper()}}
                ]
            }
        }

        if active_only:
            query["bool"]["must"].append({"term": {"is_active": True}})

        result = await self.es.search(
            index=self.INDEX_PSC_CORPORATE_BY_COUNTRY,
            body={
                "query": query,
                "size": 1000,
                "aggs": {
                    "by_legal_form": {"terms": {"field": "psc_corporate_legal_form", "size": 20}},
                    "by_uk_company": {"terms": {"field": "uk_company_name.keyword", "size": 100}},
                }
            }
        )

        return {
            "country_code": country_code.upper(),
            "total": result["hits"]["total"]["value"],
            "companies": [hit["_source"] for hit in result["hits"]["hits"]],
            "aggregations": result.get("aggregations", {}),
        }

    async def search_uk_properties_by_owner_country(
        self,
        country_code: str
    ) -> Dict[str, Any]:
        """
        Find UK properties owned by companies from a specific jurisdiction.

        Example: Find all UK properties owned by BVI (VG) companies.
        """
        await self.connect()

        result = await self.es.search(
            index=self.INDEX_PROPERTY_OWNERS,
            body={
                "query": {
                    "term": {"owner_country_code": country_code.upper()}
                },
                "size": 1000,
                "aggs": {
                    "by_county": {"terms": {"field": "county", "size": 50}},
                    "by_owner": {"terms": {"field": "owner_name.keyword", "size": 100}},
                    "total_value": {"sum": {"field": "price_paid"}},
                }
            }
        )

        return {
            "country_code": country_code.upper(),
            "total": result["hits"]["total"]["value"],
            "properties": [hit["_source"] for hit in result["hits"]["hits"]],
            "aggregations": result.get("aggregations", {}),
        }

    async def get_all_foreign_psc_jurisdictions(self) -> Dict[str, int]:
        """Get counts of foreign corporate PSCs by jurisdiction."""
        await self.connect()

        result = await self.es.search(
            index=self.INDEX_PSC_CORPORATE_BY_COUNTRY,
            body={
                "size": 0,
                "aggs": {
                    "by_jurisdiction": {
                        "terms": {"field": "psc_corporate_country_code", "size": 250}
                    }
                }
            }
        )

        buckets = result.get("aggregations", {}).get("by_jurisdiction", {}).get("buckets", [])
        return {b["key"]: b["doc_count"] for b in buckets}


# CLI for testing
async def main():
    import argparse

    parser = argparse.ArgumentParser(description="PSC Index Manager")
    parser.add_argument("--create", action="store_true", help="Create indices")
    parser.add_argument("--force", action="store_true", help="Force recreate indices")
    parser.add_argument("--search-company", help="Search PSCs by company number")
    parser.add_argument("--search-person", help="Search companies by PSC person name")
    parser.add_argument("--search-country", help="Search foreign PSCs by country code")
    parser.add_argument("--search-properties", help="Search UK properties by owner country")
    parser.add_argument("--list-jurisdictions", action="store_true", help="List all foreign PSC jurisdictions")

    args = parser.parse_args()

    manager = PSCIndexManager()

    try:
        if args.create:
            await manager.create_indices(force_recreate=args.force)
        elif args.search_company:
            results = await manager.search_pscs_by_company(args.search_company)
            print(json.dumps(results, indent=2, default=str))
        elif args.search_person:
            results = await manager.search_companies_by_psc_person(args.search_person)
            print(json.dumps(results, indent=2, default=str))
        elif args.search_country:
            results = await manager.search_foreign_corporate_pscs_by_country(args.search_country)
            print(json.dumps(results, indent=2, default=str))
        elif args.search_properties:
            results = await manager.search_uk_properties_by_owner_country(args.search_properties)
            print(json.dumps(results, indent=2, default=str))
        elif args.list_jurisdictions:
            results = await manager.get_all_foreign_psc_jurisdictions()
            print("Foreign PSC jurisdictions:")
            for code, count in sorted(results.items(), key=lambda x: -x[1]):
                print(f"  {code}: {count:,}")
        else:
            parser.print_help()
    finally:
        await manager.close()


if __name__ == "__main__":
    asyncio.run(main())
