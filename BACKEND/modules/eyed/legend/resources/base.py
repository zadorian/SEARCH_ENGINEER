"""
Base metadata helpers for EYE-D resources.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Protocol, Any, runtime_checkable


@dataclass(frozen=True)
class ResourceMetadata:
    name: str
    accepts: List[int]
    provides: List[int]
    description: str
    friction: str = "Paywalled"


@runtime_checkable
class CapabilityResource(Protocol):
    metadata: ResourceMetadata

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ...


class StaticCapabilityResource:
    metadata: ResourceMetadata

    def __init_subclass__(cls) -> None:
        if not hasattr(cls, "metadata"):
            raise TypeError(f"{cls.__name__} must define ResourceMetadata")

    def accepts_input(self, legend_code: int) -> bool:
        return legend_code in self.metadata.accepts

    def provides_output(self, legend_code: int) -> bool:
        return legend_code in self.metadata.provides

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError(
            f"{self.metadata.name} resource is metadata-only in the routing layer"
        )
