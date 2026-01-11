"""
IP address resource metadata for ALLDOM.

Entity-centric: Returns ip_address and domain entities.
"""

from .base import ResourceMetadata, StaticCapabilityResource, EntityCodes


class IPLookupResource(StaticCapabilityResource):
    """
    IP address geolocation and ASN lookup.

    HAVE (accepts):
        - ip_address (8): IP to look up

    GET (provides):
        - ip_address (8): Enriched IP data (ASN, geo, etc.)
        - domain (6): Reverse DNS hostname

    Operations:
        - current: Basic lookup
        - reverse_dns: Reverse DNS resolution
        - geolocation: Geolocation data
        - asn: ASN/network information
    """

    metadata = ResourceMetadata(
        name="ip_lookup",
        accepts=[
            EntityCodes.IP_ADDRESS,  # 8 - IP to look up
        ],
        provides=[
            EntityCodes.IP_ADDRESS,  # 8 - Enriched IP data
            EntityCodes.DOMAIN,      # 6 - Reverse DNS hostname
        ],
        description="Reverse DNS, geolocation, ASN, and linked domain discovery.",
        operations=["current", "reverse_dns", "geolocation", "asn"],
        default_operation="current",
        friction="Free",
    )


class IPLinkedDomainsResource(StaticCapabilityResource):
    """
    Find domains hosted on same IP.

    HAVE (accepts):
        - ip_address (8): IP to search

    GET (provides):
        - domain (6): Domains hosted on this IP

    Operations:
        - current: Currently hosted domains
        - history: Historically hosted domains
    """

    metadata = ResourceMetadata(
        name="ip_linked_domains",
        accepts=[
            EntityCodes.IP_ADDRESS,  # 8 - IP to search
        ],
        provides=[
            EntityCodes.DOMAIN,      # 6 - Hosted domains
        ],
        description="Discover domains sharing the same IP address.",
        operations=["current", "history"],
        default_operation="current",
        friction="Paywalled",
    )
