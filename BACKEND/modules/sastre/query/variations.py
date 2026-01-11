"""
SASTRE Variations Generator - Free ORs for name/entity variations.

Generates search variations automatically:
- Name inversions (John Smith → Smith, John)
- Initials (J. Smith, J Smith)
- Common misspellings
- Transliterations
- Company suffix variations (Ltd, Limited, LLC)

INTEGRATION NOTE:
    For Entropy Logic (common vs unique names), Likelihood-based categorization,
    and Split-Segment Rule for phones, use the central VarietyGenerator:

    from SASTRE.query_compiler import (
        generate_useful_variety,  # Entropy-aware variations
        unified_search,           # Full search with variations
        VarietyGenerator,         # The class itself
    )

    # Example: Entropy Logic (common names get strict variations)
    result = generate_useful_variety("John Smith", "person")
    # {"high_likelihood": [...], "medium_likelihood": [...], "experimental": [...]}

    # Example: Phone Split-Segment Rule
    result = generate_useful_variety("+36301234567", "phone")
    # Includes tail segments for partial matching
"""

from dataclasses import dataclass
from typing import List, Set, Optional, Dict
import re


# =============================================================================
# VARIATION RULES
# =============================================================================

# Company suffix equivalents
COMPANY_SUFFIX_GROUPS = [
    ['ltd', 'ltd.', 'limited'],
    ['llc', 'l.l.c.', 'l.l.c'],
    ['inc', 'inc.', 'incorporated'],
    ['corp', 'corp.', 'corporation'],
    ['gmbh', 'g.m.b.h.', 'gesellschaft mit beschränkter haftung'],
    ['ag', 'a.g.', 'aktiengesellschaft'],
    ['sa', 's.a.', 'sociedad anónima', 'société anonyme'],
    ['bv', 'b.v.', 'besloten vennootschap'],
    ['nv', 'n.v.', 'naamloze vennootschap'],
    ['plc', 'p.l.c.', 'public limited company'],
    ['co', 'co.', 'company'],
    ['pty', 'pty.', 'proprietary'],
    ['pvt', 'pvt.', 'private'],
]

# Common name transliterations
NAME_TRANSLITERATIONS = {
    'john': ['jon', 'johan', 'johannes', 'ivan', 'ian', 'sean', 'juan'],
    'michael': ['mike', 'mikhail', 'michel', 'michele', 'miguel'],
    'robert': ['rob', 'bob', 'roberto', 'robert'],
    'william': ['will', 'bill', 'wilhelm', 'guillermo'],
    'james': ['jim', 'jamie', 'jaime', 'diego'],
    'richard': ['rick', 'dick', 'ricardo'],
    'david': ['dave', 'davide'],
    'alexander': ['alex', 'alexis', 'alejandro', 'alessandro'],
    'peter': ['pete', 'pedro', 'pierre', 'piotr'],
    'nicholas': ['nick', 'nicolas', 'nikolai', 'nikos'],
}


# =============================================================================
# VARIATION GENERATOR
# =============================================================================

class VariationGenerator:
    """
    Generates search variations for names and entities.

    Free ORs = automatic expansion of search terms to catch variations.
    """

    def __init__(self, include_transliterations: bool = True, max_variations: int = 20):
        self.include_transliterations = include_transliterations
        self.max_variations = max_variations

    def generate(self, value: str, entity_type: str = 'unknown') -> List[str]:
        """
        Generate variations for a value based on entity type.
        """
        if entity_type in ('person', 'p:'):
            return self.generate_person_variations(value)
        elif entity_type in ('company', 'c:', 'organization'):
            return self.generate_company_variations(value)
        elif entity_type in ('domain', 'd:'):
            return self.generate_domain_variations(value)
        else:
            # Generic - try both person and company rules
            variations = set()
            variations.add(value)
            variations.update(self.generate_person_variations(value))
            variations.update(self.generate_company_variations(value))
            return list(variations)[:self.max_variations]

    def generate_person_variations(self, name: str) -> List[str]:
        """
        Generate variations for a person name.

        Includes:
        - Original
        - Name inversion (First Last → Last, First)
        - Initial forms (F. Last, F Last)
        - All caps
        - All lower
        - Transliterations (optional)
        """
        variations: Set[str] = set()
        variations.add(name)

        # Normalize
        name_clean = name.strip()
        parts = name_clean.split()

        if len(parts) >= 2:
            first = parts[0]
            last = parts[-1]
            middle = parts[1:-1] if len(parts) > 2 else []

            # Basic name forms
            variations.add(f"{last}, {first}")  # Last, First
            variations.add(f"{first[0]}. {last}")  # F. Last
            variations.add(f"{first[0]} {last}")  # F Last
            variations.add(f"{first} {last[0]}.")  # First L.

            # With middle names/initials
            if middle:
                middle_str = ' '.join(middle)
                middle_initials = ' '.join([m[0] + '.' for m in middle])
                variations.add(f"{first} {middle_initials} {last}")
                variations.add(f"{first[0]}. {middle_initials} {last}")

            # Case variations
            variations.add(name_clean.upper())
            variations.add(name_clean.lower())
            variations.add(name_clean.title())

            # Transliterations
            if self.include_transliterations:
                first_lower = first.lower()
                if first_lower in NAME_TRANSLITERATIONS:
                    for alt_first in NAME_TRANSLITERATIONS[first_lower]:
                        variations.add(f"{alt_first.title()} {last}")
                        variations.add(f"{alt_first[0].upper()}. {last}")

        return list(variations)[:self.max_variations]

    def generate_company_variations(self, name: str) -> List[str]:
        """
        Generate variations for a company name.

        Includes:
        - Original
        - With/without suffix
        - Suffix equivalents (Ltd → Limited)
        - Punctuation variations
        - All caps
        """
        variations: Set[str] = set()
        variations.add(name)

        name_clean = name.strip()
        name_lower = name_clean.lower()

        # Find and handle suffix
        suffix_found = None
        base_name = name_clean

        for suffix_group in COMPANY_SUFFIX_GROUPS:
            for suffix in suffix_group:
                # Check if name ends with this suffix
                suffix_patterns = [
                    f' {suffix}$',
                    f' {suffix.upper()}$',
                    f' {suffix.title()}$',
                ]
                for pattern in suffix_patterns:
                    match = re.search(pattern, name_clean, re.IGNORECASE)
                    if match:
                        base_name = name_clean[:match.start()].strip()
                        suffix_found = suffix_group
                        break
                if suffix_found:
                    break
            if suffix_found:
                break

        # Add base name without suffix
        if base_name != name_clean:
            variations.add(base_name)

        # Add suffix equivalents
        if suffix_found:
            for equiv_suffix in suffix_found:
                variations.add(f"{base_name} {equiv_suffix}")
                variations.add(f"{base_name} {equiv_suffix.upper()}")
                variations.add(f"{base_name} {equiv_suffix.title()}")

        # Punctuation variations
        variations.add(name_clean.replace('.', ''))
        variations.add(name_clean.replace(',', ''))
        variations.add(name_clean.replace('&', 'and'))
        variations.add(name_clean.replace(' and ', ' & '))

        # Case variations
        variations.add(name_clean.upper())
        variations.add(name_clean.lower())
        variations.add(name_clean.title())

        # "The" variations
        if name_lower.startswith('the '):
            variations.add(name_clean[4:])  # Without "The"
        else:
            variations.add(f"The {name_clean}")  # With "The"

        return list(variations)[:self.max_variations]

    def generate_domain_variations(self, domain: str) -> List[str]:
        """
        Generate variations for a domain.

        Includes:
        - With/without www
        - Different TLDs (if root domain)
        """
        variations: Set[str] = set()
        variations.add(domain)

        domain_clean = domain.strip().lower()

        # Remove protocol if present
        domain_clean = re.sub(r'^https?://', '', domain_clean)
        domain_clean = domain_clean.rstrip('/')

        variations.add(domain_clean)

        # WWW variations
        if domain_clean.startswith('www.'):
            variations.add(domain_clean[4:])  # Without www
        else:
            variations.add(f'www.{domain_clean}')  # With www

        # TLD variations for common domains
        parts = domain_clean.split('.')
        if len(parts) >= 2:
            root = '.'.join(parts[:-1])
            tld = parts[-1]

            # Common TLD alternates
            tld_groups = [
                ['com', 'co', 'net', 'org'],
                ['uk', 'co.uk'],
                ['de', 'com.de'],
            ]

            for group in tld_groups:
                if tld in group:
                    for alt_tld in group:
                        variations.add(f'{root}.{alt_tld}')

        return list(variations)[:self.max_variations]


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def generate_name_variations(name: str, max_variations: int = 20) -> List[str]:
    """Generate person name variations."""
    return VariationGenerator(max_variations=max_variations).generate_person_variations(name)


def generate_company_variations(name: str, max_variations: int = 20) -> List[str]:
    """Generate company name variations."""
    return VariationGenerator(max_variations=max_variations).generate_company_variations(name)


def expand_free_ors(value: str, entity_type: str = 'unknown') -> str:
    """
    Expand a value into Free OR query syntax.

    Example:
        expand_free_ors("John Smith", "person")
        → '"John Smith" OR "Smith, John" OR "J. Smith" OR "J Smith"'
    """
    generator = VariationGenerator(max_variations=10)
    variations = generator.generate(value, entity_type)

    # Build OR query
    return ' OR '.join([f'"{v}"' for v in variations])


def generate_useful_variety(
    value: str,
    value_type: str = 'person',
    max_variations: int = 15,
) -> Dict[str, List[str]]:
    """
    Generate variations using the Principle of Useful Variety.

    Delegates to the central VarietyGenerator in query_compiler.py,
    which provides:
    - Entropy Logic (common names → strict, unique names → broad)
    - Likelihood-based categorization
    - Split-Segment Rule for phones

    Args:
        value: The value to generate variations for
        value_type: "person", "company", "phone", "email", "domain"
        max_variations: Maximum variations to return

    Returns:
        Dict with "high_likelihood", "medium_likelihood", "experimental" lists
    """
    try:
        from ..query_compiler import generate_useful_variety as central_variety
        return central_variety(value, value_type, max_variations)
    except ImportError:
        # Fallback to local generation
        generator = VariationGenerator(max_variations=max_variations)
        variations = generator.generate(value, value_type)
        return {
            "high_likelihood": variations[:5],
            "medium_likelihood": variations[5:10],
            "experimental": variations[10:],
        }
