"""
Entity-centric output models for ALLDOM.

Aligned with CYMONIDES ontology and I/O Matrix standard.
Operations (current/history/reverse) are metadata, NOT separate types.

Philosophy:
- OUTPUT = entity node_type + properties you GET
- Operation mode is a parameter, not a different output type
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


# =============================================================================
# ENTITY TYPE CODES (aligned with codes.json)
# =============================================================================

class EntityCode(Enum):
    """Core entity type codes - what you HAVE and what you GET."""
    EMAIL = 1
    PHONE = 2
    USERNAME = 3
    URL = 5
    DOMAIN = 6
    PERSON = 7
    IP_ADDRESS = 8
    ADDRESS = 11
    COMPANY_NAME = 13
    COMPANY_REG_ID = 14


# =============================================================================
# BASE OUTPUT MODEL
# =============================================================================

@dataclass
class EntityOutput:
    """Base class for all entity outputs."""

    entity_type: str  # node_type from CYMONIDES
    source: Optional[str] = None  # Where data came from (whois, dns, etc.)
    operation_mode: Optional[str] = None  # current, history, reverse, etc.
    confidence: float = 1.0
    extracted_at: Optional[datetime] = None
    raw_data: Optional[Dict[str, Any]] = None


# =============================================================================
# PERSON OUTPUT (code 7)
# =============================================================================

@dataclass
class PersonOutput(EntityOutput):
    """Person entity output - code 7."""

    entity_type: str = "person"

    # Core properties
    name: Optional[str] = None
    dob: Optional[datetime] = None
    nationality: Optional[str] = None
    country: Optional[str] = None

    # Contact info (creates edges)
    emails: List[str] = field(default_factory=list)
    phones: List[str] = field(default_factory=list)
    addresses: List[str] = field(default_factory=list)

    # Corporate relationships (creates edges)
    companies: List[Dict[str, Any]] = field(default_factory=list)  # company_name, role, dates

    # Social/online presence (creates edges)
    profiles: List[Dict[str, str]] = field(default_factory=list)  # platform, url


# =============================================================================
# COMPANY OUTPUT (code 13/14)
# =============================================================================

@dataclass
class CompanyOutput(EntityOutput):
    """Company entity output - codes 13, 14."""

    entity_type: str = "company"

    # Core identifiers
    name: Optional[str] = None
    registration_number: Optional[str] = None
    vat_number: Optional[str] = None
    lei: Optional[str] = None

    # Status and dates
    status: Optional[str] = None
    incorporation_date: Optional[datetime] = None
    dissolution_date: Optional[datetime] = None
    company_type: Optional[str] = None

    # Location
    country: Optional[str] = None
    jurisdiction: Optional[str] = None
    address: Optional[str] = None

    # Contact
    website: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None

    # Related entities (creates edges)
    officers: List[Dict[str, Any]] = field(default_factory=list)  # name, role, dates
    shareholders: List[Dict[str, Any]] = field(default_factory=list)
    beneficial_owners: List[Dict[str, Any]] = field(default_factory=list)
    parent_company: Optional[str] = None
    subsidiaries: List[str] = field(default_factory=list)


# =============================================================================
# DOMAIN OUTPUT (code 6)
# =============================================================================

@dataclass
class DomainOutput(EntityOutput):
    """Domain entity output - code 6."""

    entity_type: str = "domain"

    # Core identifier
    domain: Optional[str] = None

    # WHOIS data
    registrar: Optional[str] = None
    registrant: Optional[str] = None
    registrant_email: Optional[str] = None
    registrant_org: Optional[str] = None
    creation_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    updated_date: Optional[datetime] = None
    nameservers: List[str] = field(default_factory=list)
    status: List[str] = field(default_factory=list)
    privacy_protected: bool = False

    # DNS records
    dns_a: List[str] = field(default_factory=list)
    dns_aaaa: List[str] = field(default_factory=list)
    dns_mx: List[str] = field(default_factory=list)
    dns_ns: List[str] = field(default_factory=list)
    dns_txt: List[str] = field(default_factory=list)
    dns_cname: List[str] = field(default_factory=list)

    # Link intelligence (creates edges)
    backlinks: List[Dict[str, Any]] = field(default_factory=list)
    outlinks: List[Dict[str, Any]] = field(default_factory=list)
    subdomains: List[str] = field(default_factory=list)

    # Related entities
    linked_ips: List[str] = field(default_factory=list)
    related_domains: List[str] = field(default_factory=list)  # From WHOIS cluster/reverse


# =============================================================================
# IP ADDRESS OUTPUT (code 8)
# =============================================================================

@dataclass
class IpAddressOutput(EntityOutput):
    """IP address entity output - code 8."""

    entity_type: str = "ip_address"

    # Core identifier
    ip_address: Optional[str] = None
    version: int = 4  # 4 or 6

    # Reverse DNS
    hostname: Optional[str] = None
    ptr_record: Optional[str] = None

    # ASN/Network info
    asn: Optional[int] = None
    asn_org: Optional[str] = None
    asn_country: Optional[str] = None

    # Geolocation
    country: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # Related entities (creates edges)
    linked_domains: List[str] = field(default_factory=list)


# =============================================================================
# EMAIL OUTPUT (code 1)
# =============================================================================

@dataclass
class EmailOutput(EntityOutput):
    """Email entity output - code 1."""

    entity_type: str = "email"

    # Core identifier
    email: Optional[str] = None
    local_part: Optional[str] = None
    domain: Optional[str] = None

    # Validation
    valid: Optional[bool] = None
    disposable: Optional[bool] = None

    # Related entities (creates edges via reverse WHOIS, etc.)
    linked_domains: List[str] = field(default_factory=list)
    linked_persons: List[str] = field(default_factory=list)
    linked_companies: List[str] = field(default_factory=list)


# =============================================================================
# PHONE OUTPUT (code 2)
# =============================================================================

@dataclass
class PhoneOutput(EntityOutput):
    """Phone entity output - code 2."""

    entity_type: str = "phone"

    # Core identifier
    phone_number: Optional[str] = None
    country_code: Optional[str] = None
    national_number: Optional[str] = None

    # Carrier info
    carrier: Optional[str] = None
    line_type: Optional[str] = None  # mobile, landline, voip

    # Location
    location: Optional[str] = None
    country: Optional[str] = None

    # Related entities (creates edges)
    linked_persons: List[str] = field(default_factory=list)
    linked_companies: List[str] = field(default_factory=list)


# =============================================================================
# URL OUTPUT (code 5)
# =============================================================================

@dataclass
class UrlOutput(EntityOutput):
    """URL entity output - code 5."""

    entity_type: str = "url"

    # Core identifier
    url: Optional[str] = None
    domain: Optional[str] = None
    path: Optional[str] = None

    # Archive/historical
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    snapshots: List[Dict[str, Any]] = field(default_factory=list)  # timestamp, status

    # Link context
    anchor_text: Optional[str] = None
    source_url: Optional[str] = None  # Where this link was found

    # Related entities (creates edges)
    links_to: List[str] = field(default_factory=list)
    linked_from: List[str] = field(default_factory=list)


# =============================================================================
# ADDRESS OUTPUT (code 11)
# =============================================================================

@dataclass
class AddressOutput(EntityOutput):
    """Address entity output - code 11."""

    entity_type: str = "address"

    # Full address
    full_address: Optional[str] = None

    # Components
    street: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None

    # Related entities (creates edges)
    occupants: List[Dict[str, Any]] = field(default_factory=list)  # person/company, dates


# =============================================================================
# AGGREGATE RESPONSE MODELS
# =============================================================================

@dataclass
class AlldomResponse:
    """Standard response from ALLDOM operations."""

    success: bool = True
    operation: Optional[str] = None  # whois, dns, backlinks, etc.
    mode: Optional[str] = None  # current, history, reverse, etc.
    input_type: Optional[str] = None
    input_value: Optional[str] = None

    # Results as entity outputs
    entities: List[EntityOutput] = field(default_factory=list)

    # Edges discovered (relationships between entities)
    edges: List[Dict[str, Any]] = field(default_factory=list)

    # Metadata
    total_results: int = 0
    execution_time_ms: Optional[float] = None
    error: Optional[str] = None


__all__ = [
    # Enums
    "EntityCode",
    # Base
    "EntityOutput",
    # Entity outputs
    "PersonOutput",
    "CompanyOutput",
    "DomainOutput",
    "IpAddressOutput",
    "EmailOutput",
    "PhoneOutput",
    "UrlOutput",
    "AddressOutput",
    # Response
    "AlldomResponse",
]
