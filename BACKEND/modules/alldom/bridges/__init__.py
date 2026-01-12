"""
ALLDOM Bridges - Thin wrappers to underlying modules.

Each bridge imports from its target module and exposes a consistent interface.
"""

from . import linklater
from . import backdrill
from . import mapper
from . import eyed
from . import macros
from . import entities
from . import exif
# from . import whois  # Native WHOIS (moved from EYE-D Jan 2026)

# New operator bridges (Jan 2026)
from . import ga
from . import keyword
from . import ai_qa

__all__ = [
    "linklater",  # Handles backlinks, outlinks, similar content
    "backdrill",
    "mapper",
    "eyed",        # DNS only (WHOIS moved to native)
    "macros",
    "entities",
    "exif",
    # "whois",       # Native WHOIS - current, historic, reverse, clustering
    "ga",
    "keyword",
    "ai_qa",
]
