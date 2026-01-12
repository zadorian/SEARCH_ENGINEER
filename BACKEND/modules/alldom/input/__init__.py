# ALLDOM Input Engines
"""
Input engines for ALLDOM - search BY these entity types to find related domains.

Each engine has:
- code: Short engine identifier (e.g., 'ADD' for domain)
- name: Human-readable name
- _code: Legend code from codes.json
- search_async(): Async search method
- search(): Sync wrapper
"""

from .domain_url import AlldomDomainEngine
from .email import AlldomEmailEngine
from .phone import AlldomPhoneEngine
from .person_name import AlldomPersonNameEngine
from .company_name import AlldomCompanyNameEngine
from .ip import AlldomIpEngine

__all__ = [
    'AlldomDomainEngine',
    'AlldomEmailEngine',
    'AlldomPhoneEngine',
    'AlldomPersonNameEngine',
    'AlldomCompanyNameEngine',
    'AlldomIpEngine',
]
