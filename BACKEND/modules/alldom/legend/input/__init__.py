"""
Input dataclasses for ALLDOM legend routing.

These define the structured inputs that ALLDOM accepts and routes
to appropriate bridges (WHOIS, DNS, backlinks, etc.).

Entity type codes (from codes.json):
- 1: email
- 2: phone
- 6: domain
- 7: person_name
- 8: ip_address
"""

from .email import EmailInput
from .phone import PhoneInput
from .domain import DomainInput, DomainUrlInput  # DomainUrlInput for backward compat
from .person_name import PersonNameInput
from .ip_address import IpAddressInput

__all__ = [
    "EmailInput",       # code 1
    "PhoneInput",       # code 2
    "DomainInput",      # code 6
    "DomainUrlInput",   # code 6 (backward compat alias)
    "PersonNameInput",  # code 7
    "IpAddressInput",   # code 8
]
