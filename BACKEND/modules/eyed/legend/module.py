"""
Descriptor for EYE-D capabilities within Drill Search.
"""

from dataclasses import dataclass, field
from typing import Dict, List

from ..classifier import classify_eyed_query  # keeps existing exports reachable
from .input import DomainUrlInput, EmailInput, PersonNameInput, PhoneInput
from .models import output_models
from .resources import (
    ArchiveOrgResource,
    ContactOutResource,
    DeHashedResource,
    KasprResource,
    OSINTIndustriesResource,
    ResourceMetadata,
    RocketReachResource,
    WhoisXMLResource,
)


@dataclass
class ModuleDescriptor:
    module_name: str
    display_name: str
    accepts_inputs: List[int]
    provides_outputs: List[int]
    friction: str
    description: str
    resource_registry: Dict[str, ResourceMetadata] = field(default_factory=dict)


class EyeDModule:
    """
    Convenience wrapper so router/matrix tooling can introspect Eye-D's real capabilities.
    """

    def __init__(self) -> None:
        self._resources = [
            DeHashedResource(),
            OSINTIndustriesResource(),
            RocketReachResource(),
            ContactOutResource(),
            KasprResource(),
            WhoisXMLResource(),
            ArchiveOrgResource(),
        ]

    @property
    def descriptor(self) -> ModuleDescriptor:
        return ModuleDescriptor(
            module_name="eyed_osint_platform",
            display_name="EYE-D – OSINT Intelligence Platform",
            accepts_inputs=[1, 2, 6, 7],
            provides_outputs=[187, 188, 189, 190, 191, 192, 193, 195],
            friction="Paywalled",
            description="Breach discovery, contact enrichment, and domain intelligence used by Drill Search + MCP.",
            resource_registry={
                res.metadata.name: res.metadata for res in self._resources
            },
        )

    def supported_inputs(self) -> Dict[int, str]:
        return {
            1: EmailInput.__doc__.strip(),
            2: PhoneInput.__doc__.strip(),
            6: DomainUrlInput.__doc__.strip(),
            7: PersonNameInput.__doc__.strip(),
        }

    def supported_outputs(self) -> Dict[int, str]:
        return {
            187: output_models.BreachData.__doc__,
            188: output_models.SocialProfile.__doc__,
            189: output_models.PhoneRecord.__doc__,
            190: output_models.PersonIdentityGraph.__doc__,
            191: output_models.DomainBacklinks.__doc__,
            192: output_models.DomainWaybackSnapshots.__doc__,
            193: output_models.DomainDNSRecords.__doc__,
            195: output_models.WhoisHistoryEntry.__doc__,
        }

    def list_resources(self) -> List[ResourceMetadata]:
        return [res.metadata for res in self._resources]


__all__ = ["EyeDModule", "ModuleDescriptor", "classify_eyed_query"]
