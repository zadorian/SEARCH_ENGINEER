"""
PACMAN Patterns - Centralized regex patterns

Usage:
    from PACMAN.patterns import ALL_PATTERNS
    from PACMAN.patterns.company_numbers import UK_CRN
    from PACMAN.patterns.identifiers import LEI, IBAN
"""

from .identifiers import ALL_IDENTIFIERS, LEI, IBAN, SWIFT, VAT, IMO, MMSI, ISIN, DUNS
from .company_numbers import ALL_COMPANY_NUMBERS, EUROPE_PATTERNS, US_PATTERNS
from .contacts import ALL_CONTACTS, EMAIL, PHONE_INTL
from .crypto import ALL_CRYPTO, BTC_LEGACY, BTC_BECH32, ETH
from .names import PERSON_NAME, COMPANY_NAME, NAME_EXCLUSIONS, COMPANY_SUFFIXES

# All patterns combined for fast iteration
ALL_PATTERNS = {
    **ALL_IDENTIFIERS,
    **ALL_COMPANY_NUMBERS,
    **ALL_CONTACTS,
    **ALL_CRYPTO,
}

__all__ = [
    'ALL_PATTERNS', 'ALL_IDENTIFIERS', 'ALL_COMPANY_NUMBERS', 
    'ALL_CONTACTS', 'ALL_CRYPTO',
    'LEI', 'IBAN', 'SWIFT', 'VAT', 'IMO', 'MMSI', 'ISIN', 'DUNS',
    'EMAIL', 'PHONE_INTL',
    'BTC_LEGACY', 'BTC_BECH32', 'ETH',
    'PERSON_NAME', 'COMPANY_NAME', 'NAME_EXCLUSIONS', 'COMPANY_SUFFIXES',
]
