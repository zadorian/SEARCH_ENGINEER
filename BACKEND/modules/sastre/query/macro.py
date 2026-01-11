"""
SASTRE MACRO Language - Investigation query language.

MACRO bridges INTENT and EXECUTION:

SYNTAX:
    [subject] => [location_operator] => [intent_operator]

SUBJECT:
    "John Smith"              # Exact match
    "John Smith"~             # With variations (Free ORs)
    ("John" AND "Smith")      # Boolean

LOCATION OPERATORS (!):
    !cyprus_registry          # Specific source
    !CY                       # Jurisdiction (expands to all CY sources)
    !corporate                # Category (all corporate registries)
    !*                        # All sources (brute)

INTENT OPERATORS:
    => entities?              # EXTRACT: Find entities at location
    => verify!                # VERIFY: Confirm subject at location
    => *                      # TRACE: Find all locations for subject
    => discover!              # DISCOVER: Explore unknown
    => officers?              # Specific extraction
    => shareholders?
    => connections?

MODIFIERS:
    [2020-2023]               # Temporal filter
    [filetype:pdf]            # Format filter
    [news]                    # Genre filter

EXAMPLES:
    "John Smith"~ => !CY => entities?
        # Find John Smith (with variations) in Cyprus, extract entities

    "Acme Corp" => !* => officers?
        # Find Acme Corp everywhere, get officers

    !companieshouse.gov.uk => entities? [2023]
        # Extract all entities from Companies House, 2023 only
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import re


# =============================================================================
# PARSED MACRO
# =============================================================================

@dataclass
class ParsedMacro:
    """A parsed MACRO expression."""
    raw: str

    # Components
    subject: Optional[str] = None
    subject_with_variations: bool = False
    subject_boolean: Optional[str] = None

    location_operator: Optional[str] = None
    location_type: str = "unknown"  # source, jurisdiction, category, brute

    intent_operator: Optional[str] = None
    intent_type: str = "discover"  # extract, verify, trace, discover

    # Modifiers
    temporal_filter: Optional[str] = None
    format_filter: Optional[str] = None
    genre_filter: Optional[str] = None

    # Derived
    jurisdictions: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    extraction_type: Optional[str] = None  # entities, officers, shareholders, etc.


# =============================================================================
# LOCATION MAPPINGS
# =============================================================================

# Jurisdiction to sources mapping
JURISDICTION_SOURCES = {
    'cy': ['companies.gov.cy', 'cysec.gov.cy', 'opencorporates.com/jurisdictions/cy'],
    'uk': ['companieshouse.gov.uk', 'fca.org.uk', 'opencorporates.com/jurisdictions/gb'],
    'us': ['sec.gov', 'opencorporates.com/jurisdictions/us'],
    'de': ['handelsregister.de', 'bundesanzeiger.de', 'opencorporates.com/jurisdictions/de'],
    'vg': ['bvifsc.vg', 'opencorporates.com/jurisdictions/vg'],
    'ky': ['ciregistry.gov.ky', 'opencorporates.com/jurisdictions/ky'],
    'ch': ['zefix.ch', 'finma.ch', 'opencorporates.com/jurisdictions/ch'],
    'nl': ['kvk.nl', 'opencorporates.com/jurisdictions/nl'],
    'ie': ['cro.ie', 'opencorporates.com/jurisdictions/ie'],
    'lu': ['lbr.lu', 'opencorporates.com/jurisdictions/lu'],
    'pa': ['registro-publico.gob.pa', 'opencorporates.com/jurisdictions/pa'],
    'sg': ['acra.gov.sg', 'opencorporates.com/jurisdictions/sg'],
    'hk': ['cr.gov.hk', 'opencorporates.com/jurisdictions/hk'],
}

# Category to sources mapping
CATEGORY_SOURCES = {
    'corporate': list(set(s for sources in JURISDICTION_SOURCES.values() for s in sources)),
    'news': ['reuters.com', 'bloomberg.com', 'ft.com', 'wsj.com', 'bbc.com'],
    'social': ['linkedin.com', 'twitter.com', 'facebook.com', 'instagram.com'],
    'legal': ['courtlistener.com', 'pacer.gov', 'casetext.com'],
    'offshore': ['icij.org', 'offshoreleaks.icij.org', 'occrp.org'],
    'sanctions': ['sanctionssearch.ofac.treas.gov', 'opensanctions.org'],
    'breach': ['haveibeenpwned.com', 'dehashed.com'],
}


# =============================================================================
# MACRO PARSER
# =============================================================================

class MacroParser:
    """
    Parses MACRO expressions into structured components.
    """

    # Regex patterns
    SUBJECT_PATTERN = r'^"([^"]+)"(~)?'
    BOOLEAN_PATTERN = r'^\(([^)]+)\)'
    LOCATION_PATTERN = r'=>\s*!(\S+)'
    INTENT_PATTERN = r'=>\s*(\w+[?!*])'
    TEMPORAL_PATTERN = r'\[(\d{4}(?:-\d{4})?)\]'
    FORMAT_PATTERN = r'\[filetype:(\w+)\]'
    GENRE_PATTERN = r'\[(news|legal|social|corporate|offshore)\]'

    def parse(self, macro: str) -> ParsedMacro:
        """Parse a MACRO expression."""
        result = ParsedMacro(raw=macro)

        # Parse subject
        subject_match = re.match(self.SUBJECT_PATTERN, macro)
        if subject_match:
            result.subject = subject_match.group(1)
            result.subject_with_variations = subject_match.group(2) == '~'
        else:
            boolean_match = re.match(self.BOOLEAN_PATTERN, macro)
            if boolean_match:
                result.subject_boolean = boolean_match.group(1)

        # Parse location operator
        location_match = re.search(self.LOCATION_PATTERN, macro)
        if location_match:
            location = location_match.group(1)
            result.location_operator = location
            result.location_type, result.jurisdictions, result.sources = self._resolve_location(location)

        # Parse intent operator
        intent_match = re.search(self.INTENT_PATTERN, macro)
        if intent_match:
            intent = intent_match.group(1)
            result.intent_operator = intent
            result.intent_type = self._resolve_intent(intent)
            result.extraction_type = self._resolve_extraction(intent)

        # Parse modifiers
        temporal_match = re.search(self.TEMPORAL_PATTERN, macro)
        if temporal_match:
            result.temporal_filter = temporal_match.group(1)

        format_match = re.search(self.FORMAT_PATTERN, macro)
        if format_match:
            result.format_filter = format_match.group(1)

        genre_match = re.search(self.GENRE_PATTERN, macro)
        if genre_match:
            result.genre_filter = genre_match.group(1)

        return result

    def _resolve_location(self, location: str) -> tuple:
        """Resolve location operator to type, jurisdictions, and sources."""
        location_lower = location.lower()

        # Check if it's a wildcard
        if location == '*':
            return 'brute', [], []

        # Check if it's a jurisdiction
        if location_lower in JURISDICTION_SOURCES:
            return 'jurisdiction', [location_lower], JURISDICTION_SOURCES[location_lower]

        # Check if it's a category
        if location_lower in CATEGORY_SOURCES:
            return 'category', [], CATEGORY_SOURCES[location_lower]

        # Check if it's a specific source (contains domain-like pattern)
        if '.' in location or '_registry' in location_lower:
            # Try to extract jurisdiction from registry name
            for jur in JURISDICTION_SOURCES:
                if jur in location_lower:
                    return 'source', [jur], [location]
            return 'source', [], [location]

        # Unknown - treat as category
        return 'unknown', [], []

    def _resolve_intent(self, intent: str) -> str:
        """Resolve intent operator to intent type."""
        intent_lower = intent.lower()

        if intent_lower.endswith('?'):
            # Question = extraction
            return 'extract'
        elif intent_lower.endswith('!'):
            if 'verify' in intent_lower:
                return 'verify'
            elif 'discover' in intent_lower:
                return 'discover'
        elif intent_lower == '*':
            return 'trace'

        return 'discover'

    def _resolve_extraction(self, intent: str) -> Optional[str]:
        """Resolve extraction type from intent."""
        intent_lower = intent.lower().rstrip('?!')

        extraction_types = {
            'entities': 'entities',
            'officers': 'officers',
            'directors': 'officers',
            'shareholders': 'shareholders',
            'owners': 'shareholders',
            'connections': 'connections',
            'backlinks': 'backlinks',
            'profiles': 'profiles',
            'locations': 'locations',
            'data': 'data',
        }

        return extraction_types.get(intent_lower)

    def to_query_string(self, parsed: ParsedMacro, variations: List[str] = None) -> str:
        """Convert parsed MACRO to executable query string."""
        parts = []

        # Subject component
        if parsed.subject:
            if parsed.subject_with_variations and variations:
                subject_parts = [f'"{v}"' for v in variations]
                parts.append(f'({" OR ".join(subject_parts)})')
            else:
                parts.append(f'"{parsed.subject}"')
        elif parsed.subject_boolean:
            parts.append(f'({parsed.subject_boolean})')

        # Location component
        if parsed.sources:
            source_parts = [f'site:{s}' for s in parsed.sources[:5]]
            parts.append(f'({" OR ".join(source_parts)})')
        elif parsed.location_type == 'brute':
            pass  # No location restriction

        # Temporal filter
        if parsed.temporal_filter:
            if '-' in parsed.temporal_filter:
                parts.append(parsed.temporal_filter)
            else:
                parts.append(parsed.temporal_filter)

        # Format filter
        if parsed.format_filter:
            parts.append(f'filetype:{parsed.format_filter}')

        return ' '.join(parts)

    def to_io_rules(self, parsed: ParsedMacro) -> List[str]:
        """Map parsed MACRO to IO Matrix rule IDs."""
        rules = []

        # Map extraction type to modules
        extraction_to_module = {
            'entities': ['corporella', 'eye-d', 'linklater'],
            'officers': ['corporella', 'torpedo'],
            'shareholders': ['corporella'],
            'profiles': ['eye-d'],
            'backlinks': ['linklater'],
            'connections': ['corporella', 'eye-d'],
        }

        if parsed.extraction_type:
            rules.extend(extraction_to_module.get(parsed.extraction_type, ['brute']))

        # Add jurisdiction-specific rules
        for jur in parsed.jurisdictions:
            rules.append(f'{jur}_registry')

        return list(set(rules))


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def parse_macro(macro: str) -> ParsedMacro:
    """Parse a MACRO expression."""
    return MacroParser().parse(macro)


def macro_to_query_string(macro: str, variations: List[str] = None) -> str:
    """Convert MACRO to query string."""
    parser = MacroParser()
    parsed = parser.parse(macro)
    return parser.to_query_string(parsed, variations)


def build_macro(
    subject: str = None,
    with_variations: bool = False,
    location: str = None,
    intent: str = None,
    temporal: str = None,
) -> str:
    """Build a MACRO expression from components."""
    parts = []

    # Subject
    if subject:
        if with_variations:
            parts.append(f'"{subject}"~')
        else:
            parts.append(f'"{subject}"')

    # Location
    if location:
        parts.append(f'=> !{location}')

    # Intent
    if intent:
        parts.append(f'=> {intent}')

    # Temporal
    if temporal:
        parts.append(f'[{temporal}]')

    return ' '.join(parts)
