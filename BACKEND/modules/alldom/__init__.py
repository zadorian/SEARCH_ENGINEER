"""
ALLDOM Bridges - Thin wrappers to underlying modules.

Each bridge imports from its target module and exposes a consistent interface.
"""

from .bridges import linklater
from .bridges import backdrill
from .bridges import mapper
from .bridges import eyed
from .bridges import macros
from .bridges import entities
from .bridges import exif

__all__ = [
    "linklater",
    "backdrill",
    "mapper",
    "eyed",
    "macros",
    "entities",
    "exif",
]
