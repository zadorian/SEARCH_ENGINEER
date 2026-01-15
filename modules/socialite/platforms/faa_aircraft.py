#!/usr/bin/env python3
"""
FAA AIRCRAFT - FAA Aircraft Registry (N-Number) Scraper via Apify.

Actor: ii2e5GTophh9VtXHa
Cost: $0.005 per actor start + $0.005 per result
Source: https://registry.faa.gov/aircraftinquiry

Comprehensive FAA aircraft registration database scraping:
- Aircraft identification (N-Number, make, model, serial, year)
- Owner details (name, full address, county, country)
- Technical specs (engine, weight, category, class)
- Registration data (status, dates, certificates)
- Airworthiness info (certificate type, dates, type certificate)
- Location info (base location, city, state, country)
- Advanced data (Mode S codes, fractional ownership, dealer status)

Usage:
    from socialite.platforms.faa_aircraft import (
        search_aircraft,
        lookup_n_number,
        search_by_owner,
        FAARegistration
    )

    # Search by N-Number
    aircraft = lookup_n_number("N10253")

    # Search by state/county
    aircraft = search_aircraft(state="FL", county="CITRUS", max_items=50)

    # Search by owner
    aircraft = search_by_owner("SIPOS RICHARD", state="FL")

    # Search by make/model
    aircraft = search_aircraft(aircraft_make="Cessna", aircraft_model="172")
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
FAA_AIRCRAFT_ACTOR_ID = "ii2e5GTophh9VtXHa"

# US States
US_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC", "PR", "VI", "GU", "AS", "MP"
]

AIRCRAFT_CATEGORIES = [
    "Airplane",
    "Rotorcraft",
    "Glider",
    "Lighter Than Air",
    "Powered Parachute",
    "Weight-Shift Control",
]

AIRCRAFT_CLASSES = [
    "Fixed Wing Single-Engine",
    "Fixed Wing Multi-Engine",
    "Helicopter",
    "Gyroplane",
]

REGISTRATION_STATUSES = [
    "Valid",
    "Expired",
    "Pending",
    "Cancelled",
    "Revoked",
    "Suspended",
]

ENGINE_TYPES = [
    "Reciprocating",
    "Turbo-Prop",
    "Turbo-Fan",
    "Turbo-Jet",
    "Turbo-Shaft",
    "Electric",
    "None",
]


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class FAAOwner:
    """Aircraft registered owner information."""
    name: str = ""
    street: str = ""
    city: str = ""
    state: str = ""
    state_full: str = ""
    county: str = ""
    zip_code: str = ""
    country: str = ""
    country_full: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "FAAOwner":
        return cls(
            name=data.get("registeredOwnerName", "") or data.get("name", ""),
            street=data.get("registeredOwnerStreet", "") or data.get("street", ""),
            city=data.get("registeredOwnerCity", "") or data.get("city", ""),
            state=data.get("registeredOwnerState", "") or data.get("state", ""),
            state_full=data.get("registeredOwnerStateFull", "") or data.get("stateFull", ""),
            county=data.get("registeredOwnerCounty", "") or data.get("county", ""),
            zip_code=data.get("registeredOwnerZipCode", "") or data.get("zipCode", ""),
            country=data.get("registeredOwnerCountry", "") or data.get("country", "US"),
            country_full=data.get("registeredOwnerCountryFull", "") or data.get("countryFull", "UNITED STATES"),
            raw=data,
        )

    @property
    def full_address(self) -> str:
        parts = [self.street, f"{self.city}, {self.state} {self.zip_code}".strip()]
        return ", ".join(p for p in parts if p)


@dataclass
class FAAEngine:
    """Aircraft engine information."""
    manufacturer: str = ""
    model: str = ""
    count: int = 0
    engine_type: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "FAAEngine":
        return cls(
            manufacturer=data.get("engineManufacturer", ""),
            model=data.get("engineModel", ""),
            count=int(data.get("engineCount", 0) or 0),
            engine_type=data.get("engineType", ""),
            raw=data,
        )


@dataclass
class FAABaseLocation:
    """Aircraft base location."""
    location: str = ""
    city: str = ""
    state: str = ""
    country: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "FAABaseLocation":
        return cls(
            location=data.get("baseLocation", ""),
            city=data.get("baseCity", ""),
            state=data.get("baseState", ""),
            country=data.get("baseCountry", ""),
            raw=data,
        )


@dataclass
class FAARegistration:
    """
    Complete FAA aircraft registration data.

    Contains all fields from the FAA Aircraft Registry including:
    - Aircraft identification
    - Owner details
    - Technical specifications
    - Registration information
    - Airworthiness data
    - Location information
    - Advanced data (Mode S, fractional ownership, etc.)
    """
    # Aircraft Identification
    n_number: str = ""
    aircraft_make: str = ""
    aircraft_model: str = ""
    aircraft_serial_number: str = ""
    aircraft_year: Optional[int] = None

    # Classification
    aircraft_category: str = ""
    aircraft_class: str = ""
    aircraft_weight: Optional[int] = None

    # Registration
    registration_status: str = ""
    registration_date: Optional[str] = None
    registration_expiration_date: Optional[str] = None
    registration_type: str = ""
    last_action_date: Optional[str] = None
    last_action_type: str = ""

    # Airworthiness
    airworthiness_certificate: str = ""
    airworthiness_date: Optional[str] = None
    type_certificate: str = ""
    type_certificate_data_sheet: str = ""
    type_certificate_holder: str = ""

    # Engine
    engine: Optional[FAAEngine] = None

    # Owner
    owner: Optional[FAAOwner] = None

    # Base Location
    base_location: Optional[FAABaseLocation] = None

    # Advanced Data
    mode_s_code: str = ""
    mode_s_code_hex: str = ""
    fractional_ownership: Optional[str] = None
    dealer: Optional[str] = None

    # Kit information
    kit_manufacturer: Optional[str] = None
    kit_model: Optional[str] = None
    kit_serial_number: Optional[str] = None

    # Metadata
    scraped_timestamp: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "FAARegistration":
        """Create from Apify actor output."""
        # Parse owner
        owner = FAAOwner.from_apify(data) if data.get("registeredOwnerName") else None

        # Parse engine
        engine = FAAEngine.from_apify(data) if data.get("engineManufacturer") else None

        # Parse base location
        base_location = FAABaseLocation.from_apify(data) if data.get("baseLocation") else None

        # Parse year
        aircraft_year = None
        if data.get("aircraftYear"):
            try:
                aircraft_year = int(data["aircraftYear"])
            except (ValueError, TypeError):
                pass

        return cls(
            # Identification
            n_number=data.get("nNumber", ""),
            aircraft_make=data.get("aircraftMake", ""),
            aircraft_model=data.get("aircraftModel", ""),
            aircraft_serial_number=data.get("aircraftSerialNumber", ""),
            aircraft_year=aircraft_year,

            # Classification
            aircraft_category=data.get("aircraftCategory", ""),
            aircraft_class=data.get("aircraftClass", ""),
            aircraft_weight=int(data.get("aircraftWeight", 0) or 0) if data.get("aircraftWeight") else None,

            # Registration
            registration_status=data.get("registrationStatus", ""),
            registration_date=data.get("registrationDate"),
            registration_expiration_date=data.get("registrationExpirationDate"),
            registration_type=data.get("registrationType", ""),
            last_action_date=data.get("lastActionDate"),
            last_action_type=data.get("lastActionType", ""),

            # Airworthiness
            airworthiness_certificate=data.get("airworthinessCertificate", ""),
            airworthiness_date=data.get("airworthinessDate"),
            type_certificate=data.get("typeCertificate", ""),
            type_certificate_data_sheet=data.get("typeCertificateDataSheet", ""),
            type_certificate_holder=data.get("typeCertificateHolder", ""),

            # Components
            engine=engine,
            owner=owner,
            base_location=base_location,

            # Advanced
            mode_s_code=data.get("modeSCode", ""),
            mode_s_code_hex=data.get("modeSCodeHex", ""),
            fractional_ownership=data.get("fractionalOwnership"),
            dealer=data.get("dealer"),

            # Kit
            kit_manufacturer=data.get("kitManufacturer"),
            kit_model=data.get("kitModel"),
            kit_serial_number=data.get("kitSerialNumber"),

            # Metadata
            scraped_timestamp=data.get("scrapedTimestamp"),
            raw=data,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "n_number": self.n_number,
            "aircraft_make": self.aircraft_make,
            "aircraft_model": self.aircraft_model,
            "aircraft_serial_number": self.aircraft_serial_number,
            "aircraft_year": self.aircraft_year,
            "aircraft_category": self.aircraft_category,
            "aircraft_class": self.aircraft_class,
            "aircraft_weight": self.aircraft_weight,
            "registration_status": self.registration_status,
            "registration_date": self.registration_date,
            "registration_expiration_date": self.registration_expiration_date,
            "owner_name": self.owner.name if self.owner else "",
            "owner_city": self.owner.city if self.owner else "",
            "owner_state": self.owner.state if self.owner else "",
            "owner_county": self.owner.county if self.owner else "",
            "engine_manufacturer": self.engine.manufacturer if self.engine else "",
            "engine_type": self.engine.engine_type if self.engine else "",
            "engine_count": self.engine.count if self.engine else 0,
            "base_location": self.base_location.location if self.base_location else "",
            "mode_s_code_hex": self.mode_s_code_hex,
        }

    @property
    def full_n_number(self) -> str:
        """Get N-number with N prefix."""
        if self.n_number.upper().startswith("N"):
            return self.n_number.upper()
        return f"N{self.n_number.upper()}"

    @property
    def aircraft_description(self) -> str:
        """Get full aircraft description."""
        parts = []
        if self.aircraft_year:
            parts.append(str(self.aircraft_year))
        if self.aircraft_make:
            parts.append(self.aircraft_make)
        if self.aircraft_model:
            parts.append(self.aircraft_model)
        return " ".join(parts)


# =============================================================================
# I/O LEGEND CODES (for relationship mapping)
# =============================================================================

"""
FAA Aircraft Registry I/O Legend Codes:

INPUTS (what you can search by):
- n_number         : Aircraft N-Number (e.g., N10253)
- aircraft_make    : Manufacturer (e.g., Cessna, Boeing)
- aircraft_model   : Model (e.g., 172, 737)
- owner_name       : Owner name or company
- serial_number    : Aircraft serial number
- state            : US state code
- county           : County name
- year_from/to     : Year range filter
- aircraft_category: Category filter
- aircraft_class   : Class filter
- registration_status: Status filter

OUTPUTS (what you get):
- n_number                  : Aircraft tail number
- aircraft_make             : Manufacturer name
- aircraft_model            : Model designation
- aircraft_serial_number    : Manufacturer serial
- aircraft_year             : Year of manufacture
- aircraft_category         : Category (Airplane, Rotorcraft, etc.)
- aircraft_class            : Class (Fixed Wing Single-Engine, etc.)
- aircraft_weight           : Maximum weight in lbs
- registration_status       : Current status (Valid, Expired, etc.)
- registration_date         : Registration date
- registration_expiration   : Expiration date
- registration_type         : Type (Individual, Corporation, etc.)
- owner_name                : Registered owner name
- owner_address             : Full street address
- owner_city                : City
- owner_state               : State (abbreviated)
- owner_state_full          : State (full name)
- owner_county              : County
- owner_zip                 : ZIP code
- owner_country             : Country code
- owner_country_full        : Country name
- engine_manufacturer       : Engine manufacturer
- engine_model              : Engine model
- engine_count              : Number of engines
- engine_type               : Engine type (Reciprocating, Turbo-Fan, etc.)
- airworthiness_certificate : Certificate type
- airworthiness_date        : Airworthiness date
- type_certificate          : Type certificate
- type_certificate_holder   : TC holder
- base_location             : Base location string
- base_city                 : Base city
- base_state                : Base state
- base_country              : Base country
- mode_s_code               : Mode S transponder code (octal)
- mode_s_code_hex           : Mode S code (hexadecimal)
- fractional_ownership      : Fractional ownership status
- dealer                    : Dealer status
- kit_manufacturer          : Kit manufacturer (if applicable)
- kit_model                 : Kit model
- last_action_date          : Last action date
- last_action_type          : Last action type
- scraped_timestamp         : Data freshness timestamp

RELATIONSHIPS:
- owner_name        -> person_name (if individual)
- owner_name        -> company_name (if corporation)
- owner_address     -> address
- owner_state       -> jurisdiction (US state)
- n_number          -> asset_id (aircraft identifier)
- mode_s_code_hex   -> transponder_id (for ADS-B tracking)
- base_location     -> location
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


def search_aircraft(
    *,
    n_number: Optional[str] = None,
    aircraft_make: Optional[str] = None,
    aircraft_model: Optional[str] = None,
    owner_name: Optional[str] = None,
    serial_number: Optional[str] = None,
    aircraft_category: Optional[List[str]] = None,
    aircraft_class: Optional[List[str]] = None,
    registration_status: Optional[List[str]] = None,
    state: Optional[str] = None,
    county: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    max_items: int = 100,
) -> List[FAARegistration]:
    """
    Search FAA aircraft registry with comprehensive filters.

    Args:
        n_number: Aircraft N-Number (e.g., "N10253" or "10253")
        aircraft_make: Manufacturer (e.g., "Cessna", "Boeing")
        aircraft_model: Model (e.g., "172", "737")
        owner_name: Owner name or company
        serial_number: Aircraft serial number
        aircraft_category: Filter by categories (see AIRCRAFT_CATEGORIES)
        aircraft_class: Filter by classes (see AIRCRAFT_CLASSES)
        registration_status: Filter by status (see REGISTRATION_STATUSES)
        state: US state code (e.g., "FL", "TX")
        county: County name (e.g., "CITRUS")
        year_from: Minimum manufacture year
        year_to: Maximum manufacture year
        max_items: Maximum results (free users limited to 100)

    Returns:
        List of FAARegistration objects

    Examples:
        # By N-Number
        aircraft = search_aircraft(n_number="N10253")

        # By state/county
        aircraft = search_aircraft(state="FL", county="CITRUS", max_items=50)

        # By make/model
        aircraft = search_aircraft(aircraft_make="Cessna", aircraft_model="172")

        # By owner
        aircraft = search_aircraft(owner_name="John Smith", state="TX")

        # With filters
        aircraft = search_aircraft(
            state="CA",
            aircraft_category=["Airplane"],
            aircraft_class=["Fixed Wing Multi-Engine"],
            year_from=2000,
            max_items=200
        )
    """
    client = _get_client()

    # Build input
    run_input = {
        "maxItems": max_items,
    }

    if n_number:
        # Strip N prefix if present
        run_input["nNumber"] = n_number.upper().lstrip("N")
    if aircraft_make:
        run_input["aircraftMake"] = aircraft_make
    if aircraft_model:
        run_input["aircraftModel"] = aircraft_model
    if owner_name:
        run_input["ownerName"] = owner_name
    if serial_number:
        run_input["serialNumber"] = serial_number
    if aircraft_category:
        run_input["aircraftCategory"] = aircraft_category
    if aircraft_class:
        run_input["aircraftClass"] = aircraft_class
    if registration_status:
        run_input["registrationStatus"] = registration_status
    if state:
        run_input["state"] = state.upper()
    if county:
        run_input["county"] = county.upper()
    if year_from:
        run_input["yearFrom"] = year_from
    if year_to:
        run_input["yearTo"] = year_to

    try:
        logger.info(f"Searching FAA registry: {run_input}")
        run = client.actor(FAA_AIRCRAFT_ACTOR_ID).call(run_input=run_input)
        results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

        return [FAARegistration.from_apify(r) for r in results]
    except Exception as e:
        logger.error(f"FAA aircraft search failed: {e}")
        return []


def lookup_n_number(n_number: str) -> Optional[FAARegistration]:
    """
    Look up aircraft by N-Number.

    Args:
        n_number: Aircraft N-Number (e.g., "N10253" or "10253")

    Returns:
        FAARegistration or None

    Example:
        registration = lookup_n_number("N10253")
        if registration:
            print(f"Owner: {registration.owner.name}")
    """
    results = search_aircraft(n_number=n_number, max_items=1)
    return results[0] if results else None


def search_by_owner(
    owner_name: str,
    *,
    state: Optional[str] = None,
    max_items: int = 100,
) -> List[FAARegistration]:
    """
    Search FAA registry by owner name.

    Args:
        owner_name: Owner name or company to search
        state: Optional state filter (recommended for faster results)
        max_items: Maximum results

    Returns:
        List of FAARegistration objects

    Example:
        aircraft = search_by_owner("SIPOS RICHARD", state="FL")
    """
    return search_aircraft(
        owner_name=owner_name,
        state=state,
        max_items=max_items,
    )


def search_by_location(
    state: str,
    *,
    county: Optional[str] = None,
    max_items: int = 100,
) -> List[FAARegistration]:
    """
    Search FAA registry by state/county.

    Args:
        state: US state code (e.g., "FL", "TX")
        county: County name (e.g., "CITRUS")
        max_items: Maximum results

    Returns:
        List of FAARegistration objects

    Example:
        aircraft = search_by_location("FL", county="CITRUS", max_items=50)
    """
    return search_aircraft(
        state=state,
        county=county,
        max_items=max_items,
    )


def search_by_make_model(
    make: str,
    model: Optional[str] = None,
    *,
    state: Optional[str] = None,
    max_items: int = 100,
) -> List[FAARegistration]:
    """
    Search FAA registry by aircraft make/model.

    Args:
        make: Aircraft manufacturer (e.g., "Cessna", "Boeing")
        model: Aircraft model (optional)
        state: Optional state filter
        max_items: Maximum results

    Returns:
        List of FAARegistration objects

    Example:
        aircraft = search_by_make_model("Cessna", "172", state="CA")
    """
    return search_aircraft(
        aircraft_make=make,
        aircraft_model=model,
        state=state,
        max_items=max_items,
    )


def get_aircraft_stats(registrations: List[FAARegistration]) -> Dict[str, Any]:
    """
    Get statistics from a list of registrations.

    Args:
        registrations: List of FAARegistration objects

    Returns:
        Statistics dict with counts, top manufacturers, etc.
    """
    if not registrations:
        return {"count": 0}

    makes = {}
    models = {}
    years = []
    categories = {}
    classes = {}
    statuses = {}
    engine_types = {}
    owner_states = {}

    for reg in registrations:
        if reg.aircraft_make:
            makes[reg.aircraft_make] = makes.get(reg.aircraft_make, 0) + 1
        if reg.aircraft_model:
            key = f"{reg.aircraft_make} {reg.aircraft_model}".strip()
            models[key] = models.get(key, 0) + 1
        if reg.aircraft_year:
            years.append(reg.aircraft_year)
        if reg.aircraft_category:
            categories[reg.aircraft_category] = categories.get(reg.aircraft_category, 0) + 1
        if reg.aircraft_class:
            classes[reg.aircraft_class] = classes.get(reg.aircraft_class, 0) + 1
        if reg.registration_status:
            statuses[reg.registration_status] = statuses.get(reg.registration_status, 0) + 1
        if reg.engine and reg.engine.engine_type:
            engine_types[reg.engine.engine_type] = engine_types.get(reg.engine.engine_type, 0) + 1
        if reg.owner and reg.owner.state:
            owner_states[reg.owner.state] = owner_states.get(reg.owner.state, 0) + 1

    return {
        "count": len(registrations),
        "top_manufacturers": dict(sorted(makes.items(), key=lambda x: x[1], reverse=True)[:10]),
        "top_models": dict(sorted(models.items(), key=lambda x: x[1], reverse=True)[:10]),
        "year_range": {
            "min": min(years),
            "max": max(years),
            "avg": sum(years) // len(years)
        } if years else None,
        "categories": categories,
        "classes": classes,
        "statuses": statuses,
        "engine_types": engine_types,
        "owner_states": dict(sorted(owner_states.items(), key=lambda x: x[1], reverse=True)[:10]),
    }


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Data structures
    "FAARegistration",
    "FAAOwner",
    "FAAEngine",
    "FAABaseLocation",
    # Search functions
    "search_aircraft",
    "lookup_n_number",
    "search_by_owner",
    "search_by_location",
    "search_by_make_model",
    # Utilities
    "get_aircraft_stats",
    # Config
    "US_STATES",
    "AIRCRAFT_CATEGORIES",
    "AIRCRAFT_CLASSES",
    "REGISTRATION_STATUSES",
    "ENGINE_TYPES",
    "FAA_AIRCRAFT_ACTOR_ID",
]


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python faa_aircraft.py <n_number|state> [county] [max_items]")
        print("\nExamples:")
        print("  python faa_aircraft.py N10253           # Lookup by N-number")
        print("  python faa_aircraft.py FL               # All Florida aircraft")
        print("  python faa_aircraft.py FL CITRUS        # Citrus County, FL")
        print("  python faa_aircraft.py make:Cessna      # By manufacturer")
        print("  python faa_aircraft.py owner:Smith      # By owner name")
        sys.exit(1)

    query = sys.argv[1]
    max_items = 20

    if query.startswith("make:"):
        make = query[5:]
        print(f"✈️  Searching FAA by manufacturer: {make}")
        aircraft = search_by_make_model(make, max_items=max_items)
    elif query.startswith("owner:"):
        owner = query[6:]
        state = sys.argv[2] if len(sys.argv) > 2 else None
        print(f"✈️  Searching FAA by owner: {owner}")
        aircraft = search_by_owner(owner, state=state, max_items=max_items)
    elif query.startswith("N") or query.isdigit():
        print(f"✈️  Looking up N-Number: {query}")
        result = lookup_n_number(query)
        aircraft = [result] if result else []
    else:
        # State/county search
        state = query.upper()
        county = sys.argv[2].upper() if len(sys.argv) > 2 else None
        max_items = int(sys.argv[3]) if len(sys.argv) > 3 else max_items
        print(f"✈️  Searching FAA: {state}{' / ' + county if county else ''}")
        aircraft = search_by_location(state, county=county, max_items=max_items)

    print(f"\n📋 Found {len(aircraft)} aircraft")

    for i, ac in enumerate(aircraft[:10], 1):
        print(f"\n  {i}. {ac.full_n_number}")
        print(f"     {ac.aircraft_description}")
        print(f"     Category: {ac.aircraft_category} / {ac.aircraft_class}")
        print(f"     Status: {ac.registration_status}")
        if ac.owner:
            print(f"     Owner: {ac.owner.name}")
            print(f"     Location: {ac.owner.city}, {ac.owner.state} ({ac.owner.county})")
        if ac.engine:
            print(f"     Engine: {ac.engine.manufacturer} {ac.engine.model} ({ac.engine.engine_type})")

    if len(aircraft) > 10:
        print(f"\n  ... and {len(aircraft) - 10} more")

    # Show stats
    if aircraft:
        stats = get_aircraft_stats(aircraft)
        print(f"\n📊 Statistics:")
        print(f"   Total: {stats['count']}")
        if stats.get('top_manufacturers'):
            top = list(stats['top_manufacturers'].items())[0]
            print(f"   Top Manufacturer: {top[0]} ({top[1]})")
        if stats.get('year_range'):
            print(f"   Year Range: {stats['year_range']['min']} - {stats['year_range']['max']}")
        if stats.get('categories'):
            print(f"   Categories: {stats['categories']}")
