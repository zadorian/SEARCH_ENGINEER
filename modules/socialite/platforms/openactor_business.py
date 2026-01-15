#!/usr/bin/env python3
"""
OPENACTOR BUSINESS - Business Entity Search via Apify.

Actor: h3OriIkWaInEm8g9q
Searches company registries in UK, US, Australia, and Canada.

Sources:
- UK: Companies House
- US: SEC
- Australia: ASIC
- Canada: Corporations Canada

Usage:
    from socialite.platforms.openactor_business import (
        search_company,
        lookup_registration,
        BusinessEntity,
    )

    # Search by company name
    results = search_company("Apple Inc", countries=["US"])

    # Lookup by registration number
    entity = lookup_registration("00445790", country="GB")
"""

import os
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_TOKEN")
OPENACTOR_BUSINESS_ACTOR_ID = "h3OriIkWaInEm8g9q"

# Supported countries
SUPPORTED_COUNTRIES = ["GB", "US", "AU", "CA"]

COUNTRY_SOURCES = {
    "GB": "UK Companies House",
    "US": "SEC EDGAR",
    "AU": "ASIC",
    "CA": "Corporations Canada",
}


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class BusinessAddress:
    """Business registered address."""
    address_line_1: str = ""
    address_line_2: str = ""
    city: str = ""
    region: str = ""
    postal_code: str = ""
    country: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "BusinessAddress":
        if not data:
            return cls()
        if isinstance(data, str):
            return cls(address_line_1=data, raw={"raw_string": data})
        return cls(
            address_line_1=data.get("addressLine1", "") or data.get("line1", "") or data.get("street", ""),
            address_line_2=data.get("addressLine2", "") or data.get("line2", ""),
            city=data.get("city", "") or data.get("locality", ""),
            region=data.get("region", "") or data.get("state", "") or data.get("county", ""),
            postal_code=data.get("postalCode", "") or data.get("postCode", "") or data.get("zipCode", ""),
            country=data.get("country", ""),
            raw=data,
        )

    @property
    def full_address(self) -> str:
        parts = [self.address_line_1, self.address_line_2, self.city, self.region, self.postal_code, self.country]
        return ", ".join(p for p in parts if p)


@dataclass
class BusinessDirector:
    """Company director/officer."""
    name: str = ""
    role: str = ""
    appointed_date: str = ""
    resigned_date: str = ""
    nationality: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "BusinessDirector":
        return cls(
            name=data.get("name", "") or data.get("fullName", ""),
            role=data.get("role", "") or data.get("position", "") or data.get("officerRole", ""),
            appointed_date=data.get("appointedDate", "") or data.get("appointedOn", ""),
            resigned_date=data.get("resignedDate", "") or data.get("resignedOn", ""),
            nationality=data.get("nationality", ""),
            raw=data,
        )


@dataclass
class BusinessFiling:
    """Company filing/document."""
    type: str = ""
    date: str = ""
    description: str = ""
    url: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "BusinessFiling":
        return cls(
            type=data.get("type", "") or data.get("filingType", "") or data.get("category", ""),
            date=data.get("date", "") or data.get("filingDate", ""),
            description=data.get("description", "") or data.get("title", ""),
            url=data.get("url", "") or data.get("link", ""),
            raw=data,
        )


@dataclass
class BusinessEntity:
    """
    Complete business entity data.

    Contains company information from UK, US, AU, or CA registries.
    """
    # Identification
    entity_name: str = ""
    registration_number: str = ""
    country: str = ""
    status: str = ""

    # Details
    company_type: str = ""
    incorporation_date: str = ""
    dissolution_date: str = ""

    # Address
    registered_address: Optional[BusinessAddress] = None

    # People
    directors: List[BusinessDirector] = field(default_factory=list)

    # Classification
    sic_codes: List[str] = field(default_factory=list)

    # Filings
    filings: List[BusinessFiling] = field(default_factory=list)

    # Firmographics
    firmographics: Dict[str, Any] = field(default_factory=dict)

    # Search results (if from search)
    search_results_top10: List[Dict[str, Any]] = field(default_factory=list)

    # Diagnostics
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    # Source
    source: str = ""

    # Raw data
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "BusinessEntity":
        """Create from Apify actor output."""
        # Parse address
        address_data = data.get("registeredAddress") or data.get("address")
        address = BusinessAddress.from_apify(address_data) if address_data else None

        # Parse directors
        directors_data = data.get("directors") or data.get("officers") or []
        directors = [BusinessDirector.from_apify(d) for d in directors_data]

        # Parse filings
        filings_data = data.get("filings") or data.get("documents") or []
        filings = [BusinessFiling.from_apify(f) for f in filings_data]

        # Parse SIC codes
        sic_codes = data.get("sicCodes") or data.get("sic_codes") or []
        if isinstance(sic_codes, dict):
            sic_codes = list(sic_codes.values())

        country = data.get("country", "")

        return cls(
            entity_name=data.get("entityName") or data.get("companyName") or data.get("name", ""),
            registration_number=data.get("registrationNumber") or data.get("companyNumber") or data.get("cik", ""),
            country=country,
            status=data.get("status") or data.get("companyStatus", ""),
            company_type=data.get("companyType") or data.get("type", ""),
            incorporation_date=data.get("incorporationDate") or data.get("dateOfCreation", ""),
            dissolution_date=data.get("dissolutionDate") or data.get("dateOfCessation", ""),
            registered_address=address,
            directors=directors,
            sic_codes=sic_codes,
            filings=filings,
            firmographics=data.get("firmographics") or {},
            search_results_top10=data.get("searchResultsTop10") or [],
            diagnostics=data.get("diagnostics") or {},
            source=COUNTRY_SOURCES.get(country, country),
            raw=data,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "entity_name": self.entity_name,
            "registration_number": self.registration_number,
            "country": self.country,
            "status": self.status,
            "company_type": self.company_type,
            "incorporation_date": self.incorporation_date,
            "registered_address": self.registered_address.full_address if self.registered_address else "",
            "directors": [{"name": d.name, "role": d.role} for d in self.directors[:5]],
            "sic_codes": self.sic_codes,
            "filings_count": len(self.filings),
            "source": self.source,
        }


# =============================================================================
# I/O LEGEND CODES
# =============================================================================

"""
OpenActor Business Entity Search I/O Legend:

INPUTS:
- entityName         : Company name to search
- registrationNumber : Company registration/CIK number
- countryCodes       : List of countries ["GB", "US", "AU", "CA"]

OUTPUTS:
- entityName           : Official company name
- registrationNumber   : Registration/company number
- country              : Country code
- status               : Company status (Active, Dissolved, etc.)
- registeredAddress    : Official registered address
- directors            : List of directors/officers
- sicCodes             : Industry classification codes
- filings              : Company filings/documents
- firmographics        : Additional company data
- searchResultsTop10   : Top 10 search results (if search)
- diagnostics          : Search diagnostics info

RELATIONSHIPS:
- entity_name        -> company_name
- registration_number -> company_id
- country            -> jurisdiction
- directors.name     -> person_name
- registered_address -> address
- sic_codes          -> industry_codes
"""


# =============================================================================
# SCRAPING FUNCTIONS
# =============================================================================

def _get_client():
    """Get Apify client."""
    if not APIFY_TOKEN:
        raise ValueError("APIFY_API_TOKEN or APIFY_TOKEN environment variable required")
    try:
        from apify_client import ApifyClient
        return ApifyClient(APIFY_TOKEN)
    except ImportError:
        raise ImportError("apify-client not installed. Run: pip install apify-client")


def search_company(
    entity_name: str,
    *,
    countries: Optional[List[str]] = None,
    max_items: int = 10,
) -> List[BusinessEntity]:
    """
    Search for a company by name across registries.

    Args:
        entity_name: Company name to search
        countries: List of country codes ["GB", "US", "AU", "CA"]
                  Defaults to all supported countries
        max_items: Maximum results

    Returns:
        List of BusinessEntity objects

    Example:
        results = search_company("Apple Inc", countries=["US"])
        for company in results:
            print(f"{company.entity_name} ({company.registration_number})")
    """
    client = _get_client()

    if countries is None:
        countries = SUPPORTED_COUNTRIES

    # Validate countries
    invalid = [c for c in countries if c not in SUPPORTED_COUNTRIES]
    if invalid:
        logger.warning(f"Unsupported countries ignored: {invalid}")
        countries = [c for c in countries if c in SUPPORTED_COUNTRIES]

    run_input = {
        "entityName": entity_name,
        "countryCodes": countries,
    }

    try:
        logger.info(f"Searching business registries: {entity_name} in {countries}")
        run = client.actor(OPENACTOR_BUSINESS_ACTOR_ID).call(run_input=run_input)
        results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

        return [BusinessEntity.from_apify(r) for r in results[:max_items]]
    except Exception as e:
        logger.error(f"Business entity search failed: {e}")
        return []


def lookup_registration(
    registration_number: str,
    *,
    country: str = "GB",
) -> Optional[BusinessEntity]:
    """
    Look up a company by registration number.

    Args:
        registration_number: Company registration number
        country: Country code (GB, US, AU, CA)

    Returns:
        BusinessEntity or None

    Example:
        entity = lookup_registration("00445790", country="GB")
        if entity:
            print(f"{entity.entity_name} - {entity.status}")
    """
    client = _get_client()

    if country not in SUPPORTED_COUNTRIES:
        logger.error(f"Unsupported country: {country}")
        return None

    run_input = {
        "registrationNumber": registration_number,
        "countryCodes": [country],
    }

    try:
        logger.info(f"Looking up registration: {registration_number} in {country}")
        run = client.actor(OPENACTOR_BUSINESS_ACTOR_ID).call(run_input=run_input)
        results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

        return BusinessEntity.from_apify(results[0]) if results else None
    except Exception as e:
        logger.error(f"Registration lookup failed: {e}")
        return None


def search_uk_company(entity_name: str) -> List[BusinessEntity]:
    """Search UK Companies House."""
    return search_company(entity_name, countries=["GB"])


def search_us_company(entity_name: str) -> List[BusinessEntity]:
    """Search US SEC."""
    return search_company(entity_name, countries=["US"])


def search_au_company(entity_name: str) -> List[BusinessEntity]:
    """Search Australian ASIC."""
    return search_company(entity_name, countries=["AU"])


def search_ca_company(entity_name: str) -> List[BusinessEntity]:
    """Search Canadian Corporations."""
    return search_company(entity_name, countries=["CA"])


def search_all_registries(entity_name: str) -> List[BusinessEntity]:
    """
    Search all supported registries.

    Args:
        entity_name: Company name to search

    Returns:
        Combined results from UK, US, AU, CA
    """
    return search_company(entity_name, countries=SUPPORTED_COUNTRIES)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Data structures
    "BusinessEntity",
    "BusinessAddress",
    "BusinessDirector",
    "BusinessFiling",
    # Search functions
    "search_company",
    "lookup_registration",
    "search_uk_company",
    "search_us_company",
    "search_au_company",
    "search_ca_company",
    "search_all_registries",
    # Config
    "SUPPORTED_COUNTRIES",
    "COUNTRY_SOURCES",
    "OPENACTOR_BUSINESS_ACTOR_ID",
]


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python openactor_business.py <company_name> [country_codes]")
        print("\nExamples:")
        print("  python openactor_business.py 'Apple Inc' US")
        print("  python openactor_business.py 'Barclays' GB")
        print("  python openactor_business.py 'Shell' GB,US,AU,CA")
        print("\nSupported countries:", SUPPORTED_COUNTRIES)
        sys.exit(1)

    company = sys.argv[1]
    countries = sys.argv[2].upper().split(",") if len(sys.argv) > 2 else None

    print(f"🔍 Searching business registries: {company}")
    if countries:
        print(f"   Countries: {countries}")

    results = search_company(company, countries=countries)

    print(f"\n📋 Found {len(results)} results")

    for i, entity in enumerate(results[:10], 1):
        print(f"\n  {i}. {entity.entity_name}")
        print(f"     Registration: {entity.registration_number}")
        print(f"     Country: {entity.country} ({entity.source})")
        print(f"     Status: {entity.status}")
        if entity.registered_address:
            print(f"     Address: {entity.registered_address.full_address}")
        if entity.directors:
            print(f"     Directors: {len(entity.directors)}")
            for d in entity.directors[:3]:
                print(f"       - {d.name} ({d.role})")
        if entity.sic_codes:
            print(f"     SIC Codes: {entity.sic_codes[:5]}")
