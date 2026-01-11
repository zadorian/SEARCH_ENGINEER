"""
Input dataclasses exposed for EYE-D.
"""

from .email import EmailInput
from .phone import PhoneInput
from .domain_url import DomainUrlInput
from .person_name import PersonNameInput

__all__ = [
    "EmailInput",
    "PhoneInput",
    "DomainUrlInput",
    "PersonNameInput",
]
