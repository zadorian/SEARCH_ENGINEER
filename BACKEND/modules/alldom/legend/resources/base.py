"""
Base metadata helpers for ALLDOM resources.

Entity-centric approach aligned with CYMONIDES ontology:
- accepts: Entity type codes you can search BY (what you HAVE)
- provides: Entity type codes you GET back (not operation types)
- operations: Available modes (current, history, reverse) as parameters
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Protocol, Any, runtime_checkable


# Entity type codes (aligned with codes.json and CYMONIDES)
class EntityCodes:
    """Core entity type codes - what you HAVE and what you GET."""
    EMAIL = 1
    PHONE = 2
    USERNAME = 3
    URL = 5
    DOMAIN = 6
    PERSON = 7
    IP_ADDRESS = 8
    ADDRESS = 11
    COMPANY_NAME = 13
    COMPANY_REG_ID = 14


@dataclass(frozen=True)
class ResourceMetadata:
    """
    Describes a resource's capabilities using entity-centric codes.

    Philosophy:
    - accepts: Entity type codes this resource can search BY
    - provides: Entity type codes this resource can RETURN
    - operations: Available modes (current/history/reverse/etc.)

    Operations are parameters, NOT separate output types.
    """

    name: str
    accepts: List[int]  # Entity type codes this resource accepts as INPUT
    provides: List[int]  # Entity type codes this resource RETURNS as OUTPUT
    description: str
    operations: List[str] = field(default_factory=list)  # Available modes
    default_operation: str = "current"
    friction: str = "Free"  # Free, Paywalled, Rate-Limited


@runtime_checkable
class CapabilityResource(Protocol):
    """Protocol for resources that can be invoked."""

    metadata: ResourceMetadata

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ...


class StaticCapabilityResource:
    """Base class for ALLDOM resources with metadata."""

    metadata: ResourceMetadata

    def __init_subclass__(cls) -> None:
        if not hasattr(cls, "metadata"):
            raise TypeError(f"{cls.__name__} must define ResourceMetadata")

    def accepts_input(self, entity_code: int) -> bool:
        """Check if resource accepts this entity type as input."""
        return entity_code in self.metadata.accepts

    def provides_output(self, entity_code: int) -> bool:
        """Check if resource can return this entity type."""
        return entity_code in self.metadata.provides

    def supports_operation(self, operation: str) -> bool:
        """Check if resource supports this operation mode."""
        return operation in self.metadata.operations

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the resource. Override in subclass."""
        raise NotImplementedError(
            f"{self.metadata.name} resource is metadata-only in the routing layer"
        )
