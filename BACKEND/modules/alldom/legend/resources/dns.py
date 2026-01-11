"""
DNS resource metadata for ALLDOM.

Entity-centric: Returns domain and ip_address entities.
"""

from .base import ResourceMetadata, StaticCapabilityResource, EntityCodes


class DNSResource(StaticCapabilityResource):
    """
    DNS lookup and resolution capabilities.

    HAVE (accepts):
        - domain (6): Forward DNS lookup
        - ip_address (8): Reverse DNS lookup

    GET (provides):
        - domain (6): CNAME, NS targets
        - ip_address (8): A, AAAA records

    Operations:
        - current: Get current DNS records
        - history: Get historical DNS (requires SecurityTrails)
    """

    metadata = ResourceMetadata(
        name="dns",
        accepts=[
            EntityCodes.DOMAIN,      # 6 - Forward lookup
            EntityCodes.IP_ADDRESS,  # 8 - Reverse lookup
        ],
        provides=[
            EntityCodes.DOMAIN,      # 6 - CNAME, NS targets
            EntityCodes.IP_ADDRESS,  # 8 - A, AAAA records
        ],
        description="DNS A, AAAA, MX, NS, TXT, CNAME record resolution.",
        operations=["current", "history"],
        default_operation="current",
        friction="Free",
    )
