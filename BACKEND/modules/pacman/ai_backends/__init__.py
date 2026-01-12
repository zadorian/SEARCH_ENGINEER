"""
PACMAN Backends
Entity extraction backends (AI and rule-based)
"""

from .base import (
    ExtractionBackend,
    ExtractedEntity,
    EntityType,
    BackendRegistry
)

# Import all backends to trigger auto-registration
from . import regex
from . import gliner
from . import haiku
from . import gpt
from . import gemini


def get_backend(name: str) -> ExtractionBackend:
    """Get a specific backend by name."""
    return BackendRegistry.get(name)


def list_backends() -> list:
    """List all registered backends."""
    return list(BackendRegistry.all_backends().keys())


def available_backends() -> list:
    """List backends that are currently available."""
    return BackendRegistry.available()


__all__ = [
    'ExtractionBackend',
    'ExtractedEntity',
    'EntityType',
    'BackendRegistry',
    'get_backend',
    'list_backends',
    'available_backends',
]
