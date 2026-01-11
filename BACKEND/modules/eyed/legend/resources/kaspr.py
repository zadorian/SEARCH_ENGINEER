"""
Kaspr metadata.
"""

from .base import ResourceMetadata, StaticCapabilityResource


class KasprResource(StaticCapabilityResource):
    """Kaspr LinkedIn enrichment."""

    metadata = ResourceMetadata(
        name="kaspr",
        accepts=[7],
        provides=[188],
        description="Deep LinkedIn profile intelligence (employment history, social URLs).",
        friction="Paywalled",
    )
