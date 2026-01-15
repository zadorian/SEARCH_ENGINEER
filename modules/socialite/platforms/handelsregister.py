#!/usr/bin/env python3
"""
HANDELSREGISTER - German Commercial Registry via Apify.

Actor: CZBHNvjaWtrEw9O9R (radeance/handelsregister-api)
Cost: Pay-per-result pricing

Scrapes the German Handelsregister (Commercial Register):
- Company basic data (name, status, legal form)
- Register court and number
- Representatives/directors
- Address information
- Document links

Usage:
    from socialite.platforms.handelsregister import (
        search_company,
        search_by_register,
        search_keyword,
        HandelsregisterCompany
    )

    # By company name/identifier
    company = search_company("BMW AG")

    # By register number
    company = search_by_register("HRB 42243", court="München")

    # Keyword search
    results = search_keyword("Volkswagen", max_results=10)
"""

import os
import logging
from typing import Optional, List, Dict, Any, Literal
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_TOKEN")
HANDELSREGISTER_ACTOR_ID = "CZBHNvjaWtrEw9O9R"

REGISTER_TYPES = ["HRA", "HRB", "GnR", "PR", "VR", "GsR"]  # HRA=partnerships, HRB=corporations, GnR=cooperatives, PR=partnerships, VR=associations, GsR=partnerships

REGISTER_COURTS = [
    "all", "aachen", "altenburg", "amberg", "ansbach", "apolda", "arnsberg", "arnstadt",
    "arnstadt zweigstelle ilmenau", "aschaffenburg", "augsburg", "aurich", "bad hersfeld",
    "bad homburg v.d.h.", "bad kreuznach", "bad oeynhausen", "bad salzungen", "bamberg",
    "bayreuth", "berlin (charlottenburg)", "bielefeld", "bochum", "bonn", "braunschweig",
    "bremen", "chemnitz", "coburg", "coesfeld", "cottbus", "darmstadt", "deggendorf",
    "dortmund", "dresden", "duisburg", "düren", "düsseldorf", "eisenach", "erfurt",
    "eschwege", "essen", "flensburg", "frankfurt am main", "frankfurt/oder", "freiburg",
    "friedberg", "fritzlar", "fulda", "fürth", "gelsenkirchen", "gera", "gießen", "gotha",
    "göttingen", "greiz", "gütersloh", "hagen", "hamburg", "hamm", "hanau", "hannover",
    "heilbad heiligenstadt", "hildburghausen", "hildesheim", "hof", "homburg", "ingolstadt",
    "iserlohn", "jena", "kaiserslautern", "kassel", "kempten (allgäu)", "kiel", "kleve",
    "koblenz", "köln", "königstein", "korbach", "krefeld", "landau", "landshut", "langenfeld",
    "lebach", "leipzig", "lemgo", "limburg", "lübeck", "ludwigshafen a.rhein (ludwigshafen)",
    "lüneburg", "mainz", "mannheim", "marburg", "meiningen", "memmingen", "merzig",
    "mönchengladbach", "montabaur", "mühlhausen", "münchen", "münster", "neubrandenburg",
    "neunkirchen", "neuruppin", "neuss", "nordhausen", "nürnberg", "offenbach am main",
    "oldenburg (oldenburg)", "osnabrück", "ottweiler", "paderborn", "passau", "pinneberg",
    "pößneck", "pößneck zweigstelle bad lobenstein", "potsdam", "recklinghausen", "regensburg",
    "rostock", "rudolstadt", "saarbrücken", "saarlouis", "schweinfurt", "schwerin", "siegburg",
    "siegen", "sömmerda", "sondershausen", "sonneberg", "stadthagen", "stadtroda", "steinfurt",
    "stendal", "st. ingbert (st ingbert)", "stralsund", "straubing", "stuttgart",
    "st. wendel (st wendel)", "suhl", "tostedt", "traunstein", "ulm", "völklingen", "walsrode",
    "weiden i. d. opf.", "weimar", "wetzlar", "wiesbaden", "wittlich", "wuppertal", "würzburg",
    "zweibrücken"
]

DOCUMENT_TYPES = ["current_printout", "chronological_printout", "historical_printout", "structured_content"]


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class HandelsregisterRepresentative:
    """Company representative/director."""
    name: str = ""
    role: str = ""
    birth_date: Optional[str] = None
    location: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "HandelsregisterRepresentative":
        return cls(
            name=data.get("name", "") or data.get("fullName", ""),
            role=data.get("role", "") or data.get("position", ""),
            birth_date=data.get("birthDate"),
            location=data.get("location", "") or data.get("city", ""),
            raw=data,
        )


@dataclass
class HandelsregisterAddress:
    """Company address."""
    street: str = ""
    postal_code: str = ""
    city: str = ""
    country: str = "Germany"
    full_address: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "HandelsregisterAddress":
        street = data.get("street", "") or data.get("streetAddress", "")
        postal = data.get("postalCode", "") or data.get("zipCode", "")
        city = data.get("city", "") or data.get("locality", "")

        full = data.get("fullAddress", "")
        if not full and (street or postal or city):
            parts = [p for p in [street, f"{postal} {city}".strip()] if p]
            full = ", ".join(parts)

        return cls(
            street=street,
            postal_code=postal,
            city=city,
            country=data.get("country", "Germany"),
            full_address=full,
            raw=data,
        )


@dataclass
class HandelsregisterCompany:
    """German company from Handelsregister."""
    name: str = ""
    legal_form: str = ""
    status: str = ""
    register_type: str = ""  # HRA, HRB, etc.
    register_number: str = ""
    register_court: str = ""
    registration_date: Optional[str] = None
    purpose: str = ""
    capital: str = ""
    address: Optional[HandelsregisterAddress] = None
    representatives: List[HandelsregisterRepresentative] = field(default_factory=list)
    documents: List[Dict[str, str]] = field(default_factory=list)
    url: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "HandelsregisterCompany":
        """Create from Apify actor output."""
        # Parse address
        address = None
        if data.get("address"):
            addr_data = data["address"]
            if isinstance(addr_data, str):
                address = HandelsregisterAddress(full_address=addr_data)
            else:
                address = HandelsregisterAddress.from_apify(addr_data)

        # Parse representatives
        reps = []
        for rep_data in data.get("representatives", []) or data.get("directors", []) or []:
            if isinstance(rep_data, dict):
                reps.append(HandelsregisterRepresentative.from_apify(rep_data))
            elif isinstance(rep_data, str):
                reps.append(HandelsregisterRepresentative(name=rep_data))

        # Parse documents
        docs = []
        for doc in data.get("documents", []) or []:
            if isinstance(doc, dict):
                docs.append({
                    "title": doc.get("title", "") or doc.get("name", ""),
                    "url": doc.get("url", "") or doc.get("link", ""),
                    "date": doc.get("date", ""),
                })
            elif isinstance(doc, str):
                docs.append({"title": doc, "url": "", "date": ""})

        return cls(
            name=data.get("name", "") or data.get("companyName", ""),
            legal_form=data.get("legalForm", "") or data.get("rechtsform", ""),
            status=data.get("status", "") or data.get("state", "active"),
            register_type=data.get("registerType", "") or data.get("registerArt", ""),
            register_number=data.get("registerNumber", "") or data.get("registerNummer", ""),
            register_court=data.get("registerCourt", "") or data.get("amtsgericht", ""),
            registration_date=data.get("registrationDate") or data.get("eingetragen"),
            purpose=data.get("purpose", "") or data.get("gegenstand", ""),
            capital=data.get("capital", "") or data.get("stammkapital", ""),
            address=address,
            representatives=reps,
            documents=docs,
            url=data.get("url", "") or data.get("handelsregisterUrl", ""),
            raw=data,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "legal_form": self.legal_form,
            "status": self.status,
            "register_type": self.register_type,
            "register_number": self.register_number,
            "register_court": self.register_court,
            "registration_date": self.registration_date,
            "purpose": self.purpose,
            "capital": self.capital,
            "address": self.address.full_address if self.address else None,
            "representatives": [{"name": r.name, "role": r.role} for r in self.representatives],
            "documents_count": len(self.documents),
            "url": self.url,
        }

    @property
    def full_register_id(self) -> str:
        """Get full register identifier (e.g., 'HRB 42243 München')."""
        parts = [self.register_type, self.register_number]
        if self.register_court:
            parts.append(self.register_court)
        return " ".join(p for p in parts if p)


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
    identifier: str,
    *,
    deep_search: bool = True,
    include_representatives: bool = True,
    include_address: bool = True,
    include_documents: bool = False,
) -> Optional[HandelsregisterCompany]:
    """
    Search for a company by name or identifier.

    Args:
        identifier: Company name, register number, or other identifier
        deep_search: Enable comprehensive search (slower but more results)
        include_representatives: Include director/representative information
        include_address: Include address details
        include_documents: Include document links

    Returns:
        HandelsregisterCompany object or None

    Example:
        company = search_company("BMW AG")
        company = search_company("HRB 42243")
    """
    client = _get_client()

    run_input = {
        "identifier": identifier,
        "deepSearch": deep_search,
        "includeRepresentatives": include_representatives,
        "includeAddress": include_address,
        "includeDocuments": include_documents,
        "proxy": {
            "useApifyProxy": True,
        },
    }

    try:
        logger.info(f"Searching Handelsregister for: {identifier}")
        run = client.actor(HANDELSREGISTER_ACTOR_ID).call(run_input=run_input)
        results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

        if results:
            return HandelsregisterCompany.from_apify(results[0])
        return None
    except Exception as e:
        logger.error(f"Handelsregister search failed: {e}")
        return None


def search_by_register(
    register_number: str,
    *,
    register_type: Optional[str] = None,
    court: Optional[str] = None,
    include_representatives: bool = True,
    include_address: bool = True,
    include_documents: bool = False,
) -> Optional[HandelsregisterCompany]:
    """
    Search by register number.

    Args:
        register_number: The register number (e.g., "42243")
        register_type: Register type (HRA, HRB, GnR, PR, VR)
        court: Register court name (e.g., "München", "Berlin Charlottenburg")
        include_representatives: Include director information
        include_address: Include address details
        include_documents: Include document links

    Returns:
        HandelsregisterCompany object or None

    Example:
        company = search_by_register("42243", register_type="HRB", court="München")
    """
    client = _get_client()

    run_input = {
        "registerNumber": register_number,
        "includeRepresentatives": include_representatives,
        "includeAddress": include_address,
        "includeDocuments": include_documents,
        "proxy": {
            "useApifyProxy": True,
        },
    }

    if register_type:
        run_input["registerType"] = register_type
    if court:
        run_input["registerCourt"] = court

    try:
        logger.info(f"Searching Handelsregister by register: {register_type or ''} {register_number} {court or ''}")
        run = client.actor(HANDELSREGISTER_ACTOR_ID).call(run_input=run_input)
        results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

        if results:
            return HandelsregisterCompany.from_apify(results[0])
        return None
    except Exception as e:
        logger.error(f"Handelsregister register search failed: {e}")
        return None


def search_keyword(
    keyword: str,
    *,
    max_results: int = 10,
    deep_search: bool = False,
    include_representatives: bool = False,
    include_address: bool = True,
) -> List[HandelsregisterCompany]:
    """
    Search for companies by keyword.

    Args:
        keyword: Search keyword
        max_results: Maximum results to return
        deep_search: Enable comprehensive search per result
        include_representatives: Include director information
        include_address: Include address details

    Returns:
        List of HandelsregisterCompany objects

    Example:
        companies = search_keyword("Volkswagen", max_results=20)
    """
    client = _get_client()

    run_input = {
        "keyword": keyword,
        "maxResults": max_results,
        "deepSearch": deep_search,
        "includeRepresentatives": include_representatives,
        "includeAddress": include_address,
        "includeDocuments": False,
        "proxy": {
            "useApifyProxy": True,
        },
    }

    try:
        logger.info(f"Searching Handelsregister keyword: {keyword}")
        run = client.actor(HANDELSREGISTER_ACTOR_ID).call(run_input=run_input)
        results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

        return [HandelsregisterCompany.from_apify(r) for r in results]
    except Exception as e:
        logger.error(f"Handelsregister keyword search failed: {e}")
        return []


def get_company_documents(
    identifier: str,
) -> List[Dict[str, str]]:
    """
    Get documents for a company.

    Args:
        identifier: Company name or register number

    Returns:
        List of document dictionaries with title, url, date
    """
    company = search_company(identifier, include_documents=True)
    if company:
        return company.documents
    return []


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Data structures
    "HandelsregisterCompany",
    "HandelsregisterRepresentative",
    "HandelsregisterAddress",
    # Functions
    "search_company",
    "search_by_register",
    "search_keyword",
    "get_company_documents",
    # Config
    "REGISTER_TYPES",
    "HANDELSREGISTER_ACTOR_ID",
]


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python handelsregister.py <company_name_or_register>")
        print("\nExamples:")
        print("  python handelsregister.py 'BMW AG'")
        print("  python handelsregister.py 'HRB 42243'")
        print("  python handelsregister.py keyword:Volkswagen")
        sys.exit(1)

    query = sys.argv[1]

    print(f"🇩🇪 Searching German Handelsregister: {query}")

    if query.startswith("keyword:"):
        keyword = query[8:]
        companies = search_keyword(keyword, max_results=10)
        print(f"\n📋 Found {len(companies)} companies")
        for c in companies[:10]:
            print(f"\n  {c.name}")
            print(f"    {c.full_register_id}")
            if c.address:
                print(f"    📍 {c.address.full_address}")
    else:
        company = search_company(query, include_documents=True)
        if company:
            print(f"\n🏢 {company.name}")
            print(f"   Legal Form: {company.legal_form}")
            print(f"   Status: {company.status}")
            print(f"   Register: {company.full_register_id}")
            if company.address:
                print(f"   Address: {company.address.full_address}")
            if company.capital:
                print(f"   Capital: {company.capital}")
            if company.representatives:
                print(f"\n   👤 Representatives ({len(company.representatives)}):")
                for rep in company.representatives[:5]:
                    print(f"      - {rep.name} ({rep.role})")
            if company.documents:
                print(f"\n   📄 Documents ({len(company.documents)}):")
                for doc in company.documents[:3]:
                    print(f"      - {doc['title']}")
        else:
            print("   No results found")
