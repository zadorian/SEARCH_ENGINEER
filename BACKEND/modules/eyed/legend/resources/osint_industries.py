"""
OSINT Industries metadata.
"""

from .base import ResourceMetadata, StaticCapabilityResource


class OSINTIndustriesResource(StaticCapabilityResource):
    """Linked social profiles + breach clustering from OSINT Industries."""

    metadata = ResourceMetadata(
        name="osint_industries",
        accepts=[1, 2, 6, 7],
        provides=[188, 190],
        description="Enriches person/email/phone/domain inputs with social profiles, identities, and breach context.",
        friction="Paywalled",
    )
