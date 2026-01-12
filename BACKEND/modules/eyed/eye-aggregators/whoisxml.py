"""
WhoisXML metadata for Eye-D.
"""

from .base import ResourceMetadata, StaticCapabilityResource


class WhoisXMLResource(StaticCapabilityResource):
    """WHOIS history and DNS records via WhoisXML APIs."""

    metadata = ResourceMetadata(
        name="whoisxmlapi",
        accepts=[1, 2, 6],
        provides=[193, 195],
        description="Reverse WHOIS, historical WHOIS snapshots, and DNS answers.",
        friction="Paywalled",
    )
