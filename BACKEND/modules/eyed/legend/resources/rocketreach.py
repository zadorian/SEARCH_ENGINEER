"""
RocketReach metadata.
"""

from .base import ResourceMetadata, StaticCapabilityResource


class RocketReachResource(StaticCapabilityResource):
    """Contact enrichment for email/phone/name inputs."""

    metadata = ResourceMetadata(
        name="rocketreach",
        accepts=[1, 2, 6, 7],
        provides=[189, 190],
        description="Validates corporate emails/phones, titles, and linked companies via RocketReach.",
        friction="Paywalled",
    )
