"""
LINKLATER (backlinks/outlinks) resource metadata for ALLDOM.

Entity-centric: Returns domain and url entities.
Operations (domains/pages) are modes, not output types.
"""

from .base import ResourceMetadata, StaticCapabilityResource, EntityCodes


class BacklinksResource(StaticCapabilityResource):
    """
    Backlink analysis via LINKLATER/Majestic/Ahrefs.

    HAVE (accepts):
        - domain (6): Get backlinks to domain
        - url (5): Get backlinks to specific page

    GET (provides):
        - domain (6): Source domains linking to target
        - url (5): Source URLs linking to target

    Operations:
        - domains: Domain-level backlinks
        - pages: Page-level backlinks
    """

    metadata = ResourceMetadata(
        name="backlinks",
        accepts=[
            EntityCodes.DOMAIN,  # 6 - Domain-level backlinks
            EntityCodes.URL,     # 5 - Page-level backlinks
        ],
        provides=[
            EntityCodes.DOMAIN,  # 6 - Source domains
            EntityCodes.URL,     # 5 - Source URLs
        ],
        description="Inbound link discovery, domain rating, anchor text analysis.",
        operations=["domains", "pages"],
        default_operation="domains",
        friction="Paywalled",
    )


class OutlinksResource(StaticCapabilityResource):
    """
    Outlink analysis via LINKLATER/scraping.

    HAVE (accepts):
        - domain (6): Get outlinks from domain
        - url (5): Get outlinks from specific page

    GET (provides):
        - domain (6): Target domains linked to
        - url (5): Target URLs linked to

    Operations:
        - domains: Domain-level outlinks
        - pages: Page-level outlinks
    """

    metadata = ResourceMetadata(
        name="outlinks",
        accepts=[
            EntityCodes.DOMAIN,  # 6 - Domain-level outlinks
            EntityCodes.URL,     # 5 - Page-level outlinks
        ],
        provides=[
            EntityCodes.DOMAIN,  # 6 - Target domains
            EntityCodes.URL,     # 5 - Target URLs
        ],
        description="Outbound link discovery from domain pages.",
        operations=["domains", "pages"],
        default_operation="domains",
        friction="Rate-Limited",
    )


class RelatedDomainsResource(StaticCapabilityResource):
    """
    Related/co-cited domain analysis via LINKLATER.

    HAVE (accepts):
        - domain (6): Find domains related to target

    GET (provides):
        - domain (6): Related/co-cited domains

    Operations:
        - cocited: Domains frequently cited together
        - similar: Similar content domains
        - tracker: Domains sharing tracking codes (GA/GTM)
    """

    metadata = ResourceMetadata(
        name="related_domains",
        accepts=[
            EntityCodes.DOMAIN,  # 6 - Find related to target
        ],
        provides=[
            EntityCodes.DOMAIN,  # 6 - Related domains
        ],
        description="Find domains frequently co-linked or co-cited with target.",
        operations=["cocited", "similar", "tracker"],
        default_operation="cocited",
        friction="Rate-Limited",
    )
