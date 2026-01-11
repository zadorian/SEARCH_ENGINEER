"""
Legend-aligned ALLDOM exports for the search system.

ALLDOM handles:
- WHOIS (current, history, reverse, clustering)
- DNS resolution
- Backlinks and outlinks (via LINKLATER bridge)
- IP address lookups
- Archive/Wayback queries

Input types (entity codes from codes.json):
- 1: email
- 2: phone
- 6: domain
- 7: person_name
- 8: ip_address
"""

from .input import (
    EmailInput,
    PhoneInput,
    DomainInput,
    DomainUrlInput,  # backward compat alias
    PersonNameInput,
    IpAddressInput,
)
from .module import AllDomModule, ModuleDescriptor
from . import models, resources

__all__ = [
    # Input types (named by entity code)
    "EmailInput",       # code 1
    "PhoneInput",       # code 2
    "DomainInput",      # code 6
    "DomainUrlInput",   # code 6 (backward compat)
    "PersonNameInput",  # code 7
    "IpAddressInput",   # code 8
    # Module
    "AllDomModule",
    "ModuleDescriptor",
    # Submodules
    "models",
    "resources",
]
