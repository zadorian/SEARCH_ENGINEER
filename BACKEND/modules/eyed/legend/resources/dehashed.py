"""
DeHashed capability metadata for Drill Search's Eye-D integration.
"""

from .base import ResourceMetadata, StaticCapabilityResource


class DeHashedResource(StaticCapabilityResource):
    """
    Breach data pulled from DeHashed (email/phone/domain/username).

    Backed by the collectors in `OSINT_tools/unified_osint.py` when executed
    inside Drill Search, and by the standalone Eye-D MCP server when running externally.
    """

    metadata = ResourceMetadata(
        name="dehashed",
        accepts=[1, 2, 6, 7],
        provides=[187],
        description="Credential breach history, exposed fields, passwords, and related identifiers.",
        friction="Paywalled",
    )
