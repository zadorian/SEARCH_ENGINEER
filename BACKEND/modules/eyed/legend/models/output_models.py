"""
Legend-aligned output dataclasses for EYE-D.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class BreachRecord:
    """Legend 187: person_email_breaches entry."""

    source: str
    breach: str
    breached_at: Optional[datetime]
    compromised_fields: List[str] = field(default_factory=list)
    password_exposed: bool = False
    raw: Optional[Dict] = None


@dataclass
class BreachData:
    """Legend 187: person_email_breaches aggregate."""

    identifier: str
    total_breaches: int
    breaches: List[BreachRecord] = field(default_factory=list)
    sensitive_data_exposed: List[str] = field(default_factory=list)


@dataclass
class SocialProfile:
    """Legend 188: person_social_profiles."""

    platform: str
    username: str
    url: str
    followers: Optional[int] = None
    verified: bool = False
    raw: Optional[Dict] = None


@dataclass
class PhoneRecord:
    """Legend 189: person_phone_records."""

    phone_number: str
    carrier: Optional[str]
    location: Optional[str]
    line_type: Optional[str]
    associated_emails: List[str] = field(default_factory=list)
    associated_names: List[str] = field(default_factory=list)


@dataclass
class PersonIdentityGraph:
    """Legend 190: person_identity_graph."""

    seed_identifier: str
    linked_emails: List[str] = field(default_factory=list)
    linked_domains: List[str] = field(default_factory=list)
    linked_orgs: List[str] = field(default_factory=list)
    social_profiles: List[SocialProfile] = field(default_factory=list)


@dataclass
class Backlink:
    """Legend 191: domain_backlinks entry."""

    source_url: str
    target_url: str
    anchor_text: Optional[str]
    first_seen: Optional[datetime]
    last_seen: Optional[datetime]
    domain_authority: Optional[float]


@dataclass
class DomainBacklinks:
    """Legend 191: domain_backlinks aggregate."""

    domain: str
    backlinks: List[Backlink] = field(default_factory=list)
    total_backlinks: int = 0
    unique_domains: int = 0


@dataclass
class WaybackSnapshot:
    """Legend 192: domain_wayback_snapshots entry."""

    timestamp: datetime
    url: str
    status: str


@dataclass
class DomainWaybackSnapshots:
    """Legend 192: domain_wayback_snapshots aggregate."""

    domain: str
    snapshots: List[WaybackSnapshot] = field(default_factory=list)


@dataclass
class DNSRecord:
    """Legend 193: domain_dns_records entry."""

    record_type: str
    value: str
    ttl: Optional[int] = None
    last_seen: Optional[datetime] = None


@dataclass
class DomainDNSRecords:
    """Legend 193: domain_dns_records aggregate."""

    domain: str
    records: List[DNSRecord] = field(default_factory=list)


@dataclass
class WhoisHistoryEntry:
    """Legend 195: domain_whois_history entry."""

    observed_at: datetime
    registrar: Optional[str]
    registrant: Optional[str]
    registrant_email: Optional[str]
    name_servers: List[str] = field(default_factory=list)
    raw: Optional[Dict] = None


@dataclass
class SSLCertificate:
    """Legend 196: domain_ssl_certificates entry."""

    fingerprint: str
    issuer: str
    subject: str
    not_before: Optional[datetime]
    not_after: Optional[datetime]
    alternative_names: List[str] = field(default_factory=list)


@dataclass
class UrlTimeline:
    """Legend 197: domain_url_timelines entry."""

    url: str
    live: bool
    http_status: Optional[int]
    first_seen: Optional[datetime]
    last_seen: Optional[datetime]
    discovery_sources: List[str] = field(default_factory=list)
    archive_count: int = 0


@dataclass
class DomainTimeline:
    """Legend 197: domain_url_timelines aggregate."""

    domain: str
    urls: List[UrlTimeline] = field(default_factory=list)


@dataclass
class KeywordHit:
    """Legend 198: domain_keyword_hits entry."""

    url: str
    keyword: str
    first_seen: Optional[datetime]
    last_seen: Optional[datetime]
    total_occurrences: int
    sample_excerpt: Optional[str] = None


@dataclass
class DomainKeywordResults:
    """Legend 198: domain_keyword_hits aggregate."""

    domain: str
    keywords: List[str]
    hits: List[KeywordHit] = field(default_factory=list)
    urls_scanned: int = 0
    urls_with_hits: int = 0


__all__ = [
    "BreachRecord",
    "BreachData",
    "SocialProfile",
    "PhoneRecord",
    "PersonIdentityGraph",
    "Backlink",
    "DomainBacklinks",
    "WaybackSnapshot",
    "DomainWaybackSnapshots",
    "DNSRecord",
    "DomainDNSRecords",
    "WhoisHistoryEntry",
    "SSLCertificate",
    "UrlTimeline",
    "DomainTimeline",
    "KeywordHit",
    "DomainKeywordResults",
]
