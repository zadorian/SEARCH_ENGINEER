"""
Archive.org metadata.
"""

from .base import ResourceMetadata, StaticCapabilityResource


class ArchiveOrgResource(StaticCapabilityResource):
    """Wayback Machine snapshot collector."""

    metadata = ResourceMetadata(
        name="archive_org",
        accepts=[6],
        provides=[192],
        description="Wayback/Archive.today timelines for discovered URLs.",
        friction="Open",
    )
