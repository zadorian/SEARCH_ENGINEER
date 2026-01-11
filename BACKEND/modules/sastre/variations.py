"""
SASTRE Free ORs - Automatic Entity Variation Expansion

Free ORs are query variations that expand reach without losing precision:
    "John Smith" → "J. Smith" OR "Smith, John" OR "JOHN SMITH"
    "Acme Holdings" → "Acme Holdings Ltd" OR "Acme Holdings Limited"
    "Иванов" → "Ivanov" OR "Iwanow"

These are FREE reach - no precision loss. Generate automatically when
entities are added to investigation.

INTEGRATION NOTE:
    For Entropy Logic (common vs unique names) and Likelihood-based
    categorization, use the central VarietyGenerator in query_compiler.py:

    from SASTRE.query_compiler import generate_useful_variety

    # Returns variations grouped by likelihood
    result = generate_useful_variety("John Smith", "person")
    # {"high_likelihood": [...], "medium_likelihood": [...], "experimental": [...]}
"""

import re
from typing import List, Dict, Set, Optional
from dataclasses import dataclass
import unicodedata


@dataclass
class VariationSet:
    """A set of variations for an entity."""
    original: str
    variations: List[str]
    entity_type: str  # person, company, domain, etc.
    locale: Optional[str] = None


class VariationGenerator:
    """
    Generate free OR variations for entities.

    These variations expand search reach without precision loss.
    """

    # Common company suffixes by region
    COMPANY_SUFFIXES = {
        # English
        'en': ['Ltd', 'Ltd.', 'Limited', 'Inc', 'Inc.', 'Incorporated',
               'Corp', 'Corp.', 'Corporation', 'LLC', 'L.L.C.', 'LLP', 'PLC', 'Plc'],
        # German
        'de': ['GmbH', 'AG', 'KG', 'OHG', 'e.K.', 'GmbH & Co. KG', 'mbH'],
        # French
        'fr': ['SA', 'S.A.', 'SARL', 'S.A.R.L.', 'SAS', 'S.A.S.', 'EURL'],
        # Spanish
        'es': ['S.A.', 'S.L.', 'S.L.U.', 'S.C.'],
        # Italian
        'it': ['S.p.A.', 'S.r.l.', 'S.a.s.'],
        # Dutch
        'nl': ['B.V.', 'N.V.', 'BV', 'NV'],
        # Hungarian
        'hu': ['Kft.', 'Zrt.', 'Bt.', 'Nyrt.', 'Kft', 'Zrt'],
        # Russian
        'ru': ['ООО', 'ОАО', 'ЗАО', 'АО', 'ПАО'],
        # Offshore
        'offshore': ['Ltd', 'Limited', 'Inc', 'Corp', 'SA', 'BV', 'NV'],
    }

    # Cyrillic to Latin transliteration (simplified)
    CYRILLIC_LATIN = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        # Ukrainian extras
        'і': 'i', 'ї': 'yi', 'є': 'ye', 'ґ': 'g',
    }

    # German alternative transliterations
    GERMAN_SPECIAL = {
        'ä': ['ae', 'a'], 'ö': ['oe', 'o'], 'ü': ['ue', 'u'],
        'Ä': ['Ae', 'A'], 'Ö': ['Oe', 'O'], 'Ü': ['Ue', 'U'],
        'ß': ['ss', 'sz'],
    }

    # Hungarian special characters
    HUNGARIAN_SPECIAL = {
        'á': ['a'], 'é': ['e'], 'í': ['i'], 'ó': ['o'], 'ö': ['o', 'oe'],
        'ő': ['o', 'oe'], 'ú': ['u'], 'ü': ['u', 'ue'], 'ű': ['u', 'ue'],
    }

    @classmethod
    def generate_person_variations(cls, name: str) -> List[str]:
        """
        Generate variations for a person name.

        Args:
            name: Person name (e.g., "John Smith")

        Returns:
            List of variations
        """
        variations = set()
        variations.add(name)

        # Normalize
        name_clean = name.strip()
        parts = name_clean.split()

        if len(parts) >= 2:
            first = parts[0]
            last = parts[-1]
            middle = parts[1:-1] if len(parts) > 2 else []

            # Basic variations
            variations.add(f"{last}, {first}")  # Smith, John
            variations.add(f"{first[0]}. {last}")  # J. Smith
            variations.add(f"{first[0]} {last}")  # J Smith
            variations.add(f"{last} {first}")  # Smith John

            # With middle names
            if middle:
                middle_initials = ' '.join(m[0] + '.' for m in middle)
                variations.add(f"{first} {middle_initials} {last}")
                variations.add(f"{first[0]}. {middle_initials} {last}")

            # Case variations
            variations.add(name_clean.upper())
            variations.add(name_clean.lower())
            variations.add(name_clean.title())

            # Hyphenated last names
            if '-' in last:
                parts_hyphen = last.split('-')
                variations.add(f"{first} {parts_hyphen[0]}")
                variations.add(f"{first} {parts_hyphen[-1]}")

        # Transliteration for non-ASCII
        if cls._has_cyrillic(name):
            variations.update(cls._transliterate_cyrillic(name))

        # German special chars
        if cls._has_german_special(name):
            variations.update(cls._expand_german(name))

        # Hungarian special chars
        if cls._has_hungarian_special(name):
            variations.update(cls._expand_hungarian(name))

        # Remove original to avoid duplicate
        return sorted(list(variations - {name}))

    @classmethod
    def generate_company_variations(
        cls,
        name: str,
        locale: Optional[str] = None
    ) -> List[str]:
        """
        Generate variations for a company name.

        Args:
            name: Company name (e.g., "Acme Holdings Ltd")
            locale: Optional locale hint (e.g., 'en', 'de')

        Returns:
            List of variations
        """
        variations = set()
        variations.add(name)

        name_clean = name.strip()

        # Strip known suffixes
        base_name, suffix = cls._split_company_suffix(name_clean)

        if base_name != name_clean:
            variations.add(base_name)

            # Add all regional suffix variations
            for region, suffixes in cls.COMPANY_SUFFIXES.items():
                if locale and region not in (locale, 'offshore'):
                    continue
                for s in suffixes:
                    variations.add(f"{base_name} {s}")
                    variations.add(f"{base_name}, {s}")

        # Case variations
        variations.add(name_clean.upper())
        variations.add(name_clean.lower())
        variations.add(name_clean.title())

        # "The X Company" variations
        if name_clean.lower().startswith('the '):
            without_the = name_clean[4:]
            variations.add(without_the)
            variations.add(without_the.title())

        # "&" vs "and"
        if '&' in name_clean:
            variations.add(name_clean.replace('&', 'and'))
            variations.add(name_clean.replace('&', ' and '))
        if ' and ' in name_clean.lower():
            variations.add(name_clean.replace(' and ', ' & '))
            variations.add(name_clean.replace(' And ', ' & '))

        # Punctuation variations
        variations.add(name_clean.replace('.', ''))
        variations.add(name_clean.replace(',', ''))

        # Transliteration for non-ASCII
        if cls._has_cyrillic(name):
            variations.update(cls._transliterate_cyrillic(name))

        if cls._has_german_special(name):
            variations.update(cls._expand_german(name))

        if cls._has_hungarian_special(name):
            variations.update(cls._expand_hungarian(name))

        return sorted(list(variations - {name}))

    @classmethod
    def generate_domain_variations(cls, domain: str) -> List[str]:
        """
        Generate variations for a domain name.

        Args:
            domain: Domain name (e.g., "example.com")

        Returns:
            List of variations
        """
        variations = set()
        domain_clean = domain.strip().lower()
        variations.add(domain_clean)

        # Remove www
        if domain_clean.startswith('www.'):
            variations.add(domain_clean[4:])
        else:
            variations.add(f"www.{domain_clean}")

        # TLD variations for common mistakes
        parts = domain_clean.rsplit('.', 1)
        if len(parts) == 2:
            base, tld = parts

            # Common TLD typos/alternatives
            tld_alts = {
                'com': ['co', 'org', 'net'],
                'co.uk': ['com', 'uk'],
                'de': ['com', 'at', 'ch'],
                'fr': ['com'],
            }
            for alt in tld_alts.get(tld, []):
                variations.add(f"{base}.{alt}")

        # Hyphen variations
        if '-' in parts[0]:
            variations.add(parts[0].replace('-', '') + '.' + parts[1] if len(parts) == 2 else parts[0].replace('-', ''))
        # Don't add hyphens randomly as it would be lossy

        return sorted(list(variations - {domain}))

    @classmethod
    def generate_email_variations(cls, email: str) -> List[str]:
        """
        Generate variations for an email address.

        Args:
            email: Email address

        Returns:
            List of variations
        """
        variations = set()
        email_clean = email.strip().lower()
        variations.add(email_clean)

        if '@' not in email_clean:
            return []

        local, domain = email_clean.rsplit('@', 1)

        # Common patterns
        # firstname.lastname -> firstnamelastname
        if '.' in local:
            variations.add(local.replace('.', '') + '@' + domain)
            variations.add(local.replace('.', '_') + '@' + domain)

        # firstname_lastname -> firstname.lastname
        if '_' in local:
            variations.add(local.replace('_', '.') + '@' + domain)
            variations.add(local.replace('_', '') + '@' + domain)

        # Domain variations
        domain_vars = cls.generate_domain_variations(domain)
        for dv in domain_vars:
            variations.add(f"{local}@{dv}")

        return sorted(list(variations - {email}))

    @classmethod
    def _split_company_suffix(cls, name: str) -> tuple:
        """Split company name from legal suffix."""
        all_suffixes = []
        for suffixes in cls.COMPANY_SUFFIXES.values():
            all_suffixes.extend(suffixes)

        # Sort by length descending to match longest first
        all_suffixes.sort(key=len, reverse=True)

        name_lower = name.lower()
        for suffix in all_suffixes:
            suffix_lower = suffix.lower()
            # Check with comma
            if name_lower.endswith(f', {suffix_lower}'):
                return name[:-len(suffix)-2].strip(), suffix
            # Check with space
            if name_lower.endswith(f' {suffix_lower}'):
                return name[:-len(suffix)-1].strip(), suffix
            # Check direct
            if name_lower.endswith(suffix_lower):
                return name[:-len(suffix)].strip(), suffix

        return name, ''

    @classmethod
    def _has_cyrillic(cls, text: str) -> bool:
        """Check if text contains Cyrillic characters."""
        return bool(re.search(r'[\u0400-\u04FF]', text))

    @classmethod
    def _transliterate_cyrillic(cls, text: str) -> Set[str]:
        """Transliterate Cyrillic to Latin."""
        variations = set()

        # Standard transliteration
        result = []
        for char in text.lower():
            if char in cls.CYRILLIC_LATIN:
                result.append(cls.CYRILLIC_LATIN[char])
            else:
                result.append(char)
        variations.add(''.join(result))
        variations.add(''.join(result).title())

        # German-style transliteration (common for Russian names in German docs)
        german_trans = {
            'ж': 'sch', 'ч': 'tsch', 'ш': 'sch', 'щ': 'schtsch',
            'х': 'ch', 'ц': 'z', 'я': 'ja', 'ю': 'ju', 'е': 'je',
        }
        result_de = []
        for char in text.lower():
            if char in german_trans:
                result_de.append(german_trans[char])
            elif char in cls.CYRILLIC_LATIN:
                result_de.append(cls.CYRILLIC_LATIN[char])
            else:
                result_de.append(char)
        variations.add(''.join(result_de))
        variations.add(''.join(result_de).title())

        return variations

    @classmethod
    def _has_german_special(cls, text: str) -> bool:
        """Check if text contains German special characters."""
        return bool(re.search(r'[äöüÄÖÜß]', text))

    @classmethod
    def _expand_german(cls, text: str) -> Set[str]:
        """Expand German special characters to ASCII alternatives."""
        variations = set()

        # Generate all combinations
        def expand(s: str, pos: int = 0) -> Set[str]:
            if pos >= len(s):
                return {s}

            char = s[pos]
            if char in cls.GERMAN_SPECIAL:
                results = set()
                for replacement in cls.GERMAN_SPECIAL[char]:
                    new_s = s[:pos] + replacement + s[pos+1:]
                    results.update(expand(new_s, pos + len(replacement)))
                return results
            else:
                return expand(s, pos + 1)

        variations.update(expand(text))
        return variations

    @classmethod
    def _has_hungarian_special(cls, text: str) -> bool:
        """Check if text contains Hungarian special characters."""
        return bool(re.search(r'[áéíóöőúüű]', text.lower()))

    @classmethod
    def _expand_hungarian(cls, text: str) -> Set[str]:
        """Expand Hungarian special characters to ASCII alternatives."""
        variations = set()

        # Simple replacement
        result = text.lower()
        for char, replacements in cls.HUNGARIAN_SPECIAL.items():
            result = result.replace(char, replacements[0])
        variations.add(result)
        variations.add(result.title())

        return variations


def generate_variations(
    value: str,
    entity_type: str = 'auto',
    locale: Optional[str] = None
) -> VariationSet:
    """
    Generate all variations for an entity value.

    Args:
        value: Entity value (name, domain, email, etc.)
        entity_type: Type hint ('person', 'company', 'domain', 'email', 'auto')
        locale: Optional locale hint

    Returns:
        VariationSet with all variations
    """
    # Auto-detect entity type
    if entity_type == 'auto':
        if '@' in value:
            entity_type = 'email'
        elif '.' in value and ' ' not in value:
            entity_type = 'domain'
        elif any(suffix in value for suffix in ['Ltd', 'Inc', 'Corp', 'GmbH', 'SA']):
            entity_type = 'company'
        else:
            entity_type = 'person'

    # Generate variations by type
    if entity_type == 'person':
        variations = VariationGenerator.generate_person_variations(value)
    elif entity_type == 'company':
        variations = VariationGenerator.generate_company_variations(value, locale)
    elif entity_type == 'domain':
        variations = VariationGenerator.generate_domain_variations(value)
    elif entity_type == 'email':
        variations = VariationGenerator.generate_email_variations(value)
    else:
        variations = []

    return VariationSet(
        original=value,
        variations=variations,
        entity_type=entity_type,
        locale=locale
    )


def expand_query_with_variations(query: str, entity_type: str = 'auto') -> str:
    """
    Expand a query with OR variations.

    Args:
        query: Original query (can be quoted)
        entity_type: Entity type hint

    Returns:
        Expanded query with ORs (e.g., "John Smith" OR "J. Smith" OR "Smith, John")
    """
    # Extract quoted term if present
    quoted_match = re.match(r'"([^"]+)"', query)
    if quoted_match:
        value = quoted_match.group(1)
    else:
        value = query.strip()

    var_set = generate_variations(value, entity_type)

    # Build OR query
    all_terms = [f'"{value}"'] + [f'"{v}"' for v in var_set.variations[:10]]  # Limit to prevent explosion
    return ' OR '.join(all_terms)


def generate_useful_variations(
    value: str,
    entity_type: str = 'auto',
    max_variations: int = 15,
) -> Dict[str, List[str]]:
    """
    Generate variations using the Principle of Useful Variety.

    This wraps the central VarietyGenerator from query_compiler.py,
    adding Entropy Logic:
    - Common names → Strict variations (few, high-precision)
    - Unique names → Broad variations (more experimental)

    Args:
        value: The value to generate variations for
        entity_type: "person", "company", "phone", "email", "domain", or "auto"
        max_variations: Maximum variations to return

    Returns:
        Dict with "high_likelihood", "medium_likelihood", "experimental" lists

    Example:
        # Common name "John Smith" - returns fewer, stricter variations
        result = generate_useful_variations("John Smith", "person")

        # Unique name "Elon Musk" - returns more experimental variations
        result = generate_useful_variations("Elon Musk", "person")
    """
    try:
        from .query_compiler import generate_useful_variety
        return generate_useful_variety(value, entity_type, max_variations)
    except ImportError:
        # Fallback if query_compiler not available
        var_set = generate_variations(value, entity_type)
        return {
            "high_likelihood": [value] + var_set.variations[:5],
            "medium_likelihood": var_set.variations[5:10],
            "experimental": var_set.variations[10:],
        }
