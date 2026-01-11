"""
Descriptor for ALLDOM capabilities within the search system.

Entity-centric approach aligned with CYMONIDES ontology:
- accepts_inputs: Entity type codes you can search BY
- provides_outputs: Entity type codes you GET back
- operations: Available modes (current/history/reverse) as parameters
"""

from dataclasses import dataclass, field
from typing import Dict, List

from .input import DomainInput, EmailInput, PersonNameInput, PhoneInput, IpAddressInput
from .models import output_models
from .resources import (
    ResourceMetadata,
    EntityCodes,
    WhoisResource,
    DNSResource,
    BacklinksResource,
    OutlinksResource,
    RelatedDomainsResource,
    IPLookupResource,
    IPLinkedDomainsResource,
    WaybackResource,
    CommonCrawlResource,
)


@dataclass
class ModuleDescriptor:
    """
    Describes a module's capabilities for routing.

    Entity-centric design:
    - accepts_inputs: Entity type codes this module can search BY
    - provides_outputs: Entity type codes this module can RETURN
    - Operations are parameters, not separate codes
    """

    module_name: str
    display_name: str
    accepts_inputs: List[int]  # Entity type codes
    provides_outputs: List[int]  # Entity type codes
    friction: str
    description: str
    resource_registry: Dict[str, ResourceMetadata] = field(default_factory=dict)


class AllDomModule:
    """
    Convenience wrapper for introspecting ALLDOM's capabilities.
    Used by router/matrix tooling.

    Entity-centric: All inputs and outputs are entity types (not operations).
    """

    def __init__(self) -> None:
        self._resources = [
            WhoisResource(),
            DNSResource(),
            BacklinksResource(),
            OutlinksResource(),
            RelatedDomainsResource(),
            IPLookupResource(),
            IPLinkedDomainsResource(),
            WaybackResource(),
            CommonCrawlResource(),
        ]

    @property
    def descriptor(self) -> ModuleDescriptor:
        """
        Module descriptor with entity-centric codes.

        INPUT codes (what you can search BY):
            1  = email
            2  = phone
            5  = url
            6  = domain
            7  = person_name
            8  = ip_address
            13 = company_name

        OUTPUT codes (what you GET back):
            Same entity types - domain, person, company, email, address, etc.
        """
        return ModuleDescriptor(
            module_name="alldom_intelligence_platform",
            display_name="ALLDOM - Domain & Link Intelligence Platform",
            accepts_inputs=[
                EntityCodes.EMAIL,        # 1
                EntityCodes.PHONE,        # 2
                EntityCodes.URL,          # 5
                EntityCodes.DOMAIN,       # 6
                EntityCodes.PERSON,       # 7
                EntityCodes.IP_ADDRESS,   # 8
                EntityCodes.COMPANY_NAME, # 13
            ],
            provides_outputs=[
                EntityCodes.EMAIL,        # 1
                EntityCodes.PHONE,        # 2
                EntityCodes.URL,          # 5
                EntityCodes.DOMAIN,       # 6
                EntityCodes.PERSON,       # 7
                EntityCodes.IP_ADDRESS,   # 8
                EntityCodes.ADDRESS,      # 11
                EntityCodes.COMPANY_NAME, # 13
            ],
            friction="Mixed",
            description="WHOIS, DNS, backlinks, outlinks, IP lookup, and archive intelligence.",
            resource_registry={
                res.metadata.name: res.metadata for res in self._resources
            },
        )

    def supported_inputs(self) -> Dict[int, str]:
        """Map of entity type codes to input descriptions."""
        return {
            EntityCodes.EMAIL: "Email address - for reverse WHOIS, breach search",
            EntityCodes.PHONE: "Phone number - for carrier lookup, reverse search",
            EntityCodes.URL: "Full URL - for backlinks, archive search",
            EntityCodes.DOMAIN: "Domain name - for WHOIS, DNS, backlinks, archive",
            EntityCodes.PERSON: "Person name - for reverse WHOIS by registrant",
            EntityCodes.IP_ADDRESS: "IP address - for reverse DNS, geolocation, hosted domains",
            EntityCodes.COMPANY_NAME: "Company name - for reverse WHOIS by org",
        }

    def supported_outputs(self) -> Dict[int, str]:
        """Map of entity type codes to output descriptions."""
        return {
            EntityCodes.EMAIL: "Email entities - contact emails, registrant emails",
            EntityCodes.PHONE: "Phone entities - contact numbers",
            EntityCodes.URL: "URL entities - pages, archive snapshots",
            EntityCodes.DOMAIN: "Domain entities - related domains, backlink sources",
            EntityCodes.PERSON: "Person entities - registrant names",
            EntityCodes.IP_ADDRESS: "IP entities - resolved IPs, ASN data",
            EntityCodes.ADDRESS: "Address entities - registrant addresses",
            EntityCodes.COMPANY_NAME: "Company entities - registrant organizations",
        }

    def list_resources(self) -> List[ResourceMetadata]:
        """List all available resource metadata."""
        return [res.metadata for res in self._resources]

    def find_resources_for_input(self, entity_code: int) -> List[ResourceMetadata]:
        """Find resources that accept a given entity type as input."""
        return [
            res.metadata for res in self._resources
            if entity_code in res.metadata.accepts
        ]

    def find_resources_for_output(self, entity_code: int) -> List[ResourceMetadata]:
        """Find resources that can return a given entity type."""
        return [
            res.metadata for res in self._resources
            if entity_code in res.metadata.provides
        ]

    def find_resources_with_operation(self, operation: str) -> List[ResourceMetadata]:
        """Find resources that support a given operation mode."""
        return [
            res.metadata for res in self._resources
            if operation in res.metadata.operations
        ]


__all__ = ["AllDomModule", "ModuleDescriptor"]
