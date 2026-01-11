"""
Archive/Wayback resource metadata for ALLDOM.

Entity-centric: Returns url entities (snapshots).
"""

from .base import ResourceMetadata, StaticCapabilityResource, EntityCodes


class WaybackResource(StaticCapabilityResource):
    """
    Wayback Machine/Internet Archive capabilities.

    HAVE (accepts):
        - domain (6): Find snapshots for domain
        - url (5): Find snapshots for specific URL

    GET (provides):
        - url (5): Archived snapshot URLs

    Operations:
        - snapshots: List available snapshots
        - content: Fetch archived content
    """

    metadata = ResourceMetadata(
        name="wayback",
        accepts=[
            EntityCodes.DOMAIN,  # 6 - Domain snapshots
            EntityCodes.URL,     # 5 - URL snapshots
        ],
        provides=[
            EntityCodes.URL,     # 5 - Archived snapshot URLs
        ],
        description="Historical snapshots from Internet Archive Wayback Machine.",
        operations=["snapshots", "content"],
        default_operation="snapshots",
        friction="Free",
    )


class CommonCrawlResource(StaticCapabilityResource):
    """
    CommonCrawl archive search.

    HAVE (accepts):
        - domain (6): Search CC index for domain

    GET (provides):
        - url (5): Archived URLs from CommonCrawl

    Operations:
        - index: Search CC index
        - content: Fetch archived content from WARC
    """

    metadata = ResourceMetadata(
        name="commoncrawl",
        accepts=[
            EntityCodes.DOMAIN,  # 6 - Search domain in CC
        ],
        provides=[
            EntityCodes.URL,     # 5 - Archived URLs
        ],
        description="Search CommonCrawl index for archived pages.",
        operations=["index", "content"],
        default_operation="index",
        friction="Free",
    )
