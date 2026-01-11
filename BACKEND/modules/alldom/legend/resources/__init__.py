"""
Resource definitions for ALLDOM legend routing.

Entity-centric approach aligned with CYMONIDES ontology.
"""

from .base import ResourceMetadata, StaticCapabilityResource, CapabilityResource, EntityCodes
from .whois import WhoisResource
from .dns import DNSResource
from .linklater import BacklinksResource, OutlinksResource, RelatedDomainsResource
from .ip import IPLookupResource, IPLinkedDomainsResource
from .archive import WaybackResource, CommonCrawlResource

__all__ = [
    # Base
    "ResourceMetadata",
    "StaticCapabilityResource",
    "CapabilityResource",
    "EntityCodes",
    # WHOIS
    "WhoisResource",
    # DNS
    "DNSResource",
    # Links
    "BacklinksResource",
    "OutlinksResource",
    "RelatedDomainsResource",
    # IP
    "IPLookupResource",
    "IPLinkedDomainsResource",
    # Archive
    "WaybackResource",
    "CommonCrawlResource",
]
