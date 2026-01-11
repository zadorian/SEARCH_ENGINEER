"""
Output models for ALLDOM legend routing.
"""

from .output_models import *

__all__ = [
    # WHOIS
    "WhoisRecord",
    "WhoisHistoryEntry",
    "WhoisClusterResult",
    "WhoisDiscoveryResponse",
    # DNS
    "DNSRecord",
    "DomainDNSRecords",
    # Links
    "Backlink",
    "DomainBacklinks",
    "Outlink",
    "DomainOutlinks",
    # IP
    "IPLookupResult",
    # Reverse
    "ReverseEmailResult",
    "ReversePhoneResult",
    # Person
    "PersonCorporateRoles",
    # SSL
    "SSLCertificate",
    # Archive
    "WaybackSnapshot",
    "DomainWaybackSnapshots",
]
