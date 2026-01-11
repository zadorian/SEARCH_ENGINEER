"""
ContactOut metadata.
"""

from .base import ResourceMetadata, StaticCapabilityResource


class ContactOutResource(StaticCapabilityResource):
    """LinkedIn-based enrichment for emails/phones/domains."""

    metadata = ResourceMetadata(
        name="contactout",
        accepts=[1, 2, 6, 7],
        provides=[188, 189],
        description="LinkedIn-driven contact enrichment (emails, phones, social/professional profiles).",
        friction="Paywalled",
    )
