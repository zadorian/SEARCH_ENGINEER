"""
Entity Pattern Extraction - Regex patterns for company forms and structured data.

Extracts:
- Company names with legal forms (GmbH, Ltd, LLC, AG, S.A., etc.)
- Registration numbers (HRB, Companies House, etc.)
- Addresses
- Dates
- Financial figures
- People names with titles

Usage:
    from modules.cc_content.entity_patterns import EntityExtractor

    extractor = EntityExtractor()
    entities = extractor.extract_all(content)
    companies = extractor.extract_companies(content)
"""

import re
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field


@dataclass
class ExtractedEntity:
    """Extracted entity with metadata."""
    text: str
    type: str  # 'company', 'registration', 'person', 'address', 'date', 'amount'
    subtype: Optional[str] = None  # e.g., 'GmbH', 'Ltd', 'HRB'
    context: Optional[str] = None  # surrounding text
    confidence: float = 0.8
    jurisdiction: Optional[str] = None  # e.g., 'DE', 'UK', 'US'


# === COMPANY FORM PATTERNS BY JURISDICTION ===

COMPANY_FORMS = {
    # Germany
    'DE': [
        r'\b([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)*)\s+(GmbH|AG|KG|OHG|e\.?K\.?|GmbH\s*&\s*Co\.?\s*KG|UG(?:\s*\(haftungsbeschränkt\))?)\b',
        r'\b([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)*)\s+(Gesellschaft\s+mit\s+beschränkter\s+Haftung)\b',
        r'\b([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)*)\s+(Aktiengesellschaft)\b',
    ],
    # UK
    'UK': [
        r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(Ltd\.?|Limited|PLC|plc|LLP)\b',
        r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(Private\s+Limited\s+Company)\b',
    ],
    # US
    'US': [
        r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*),?\s+(LLC|Inc\.?|Corp\.?|Corporation|L\.?L\.?C\.?|Incorporated)\b',
        r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(Limited\s+Liability\s+Company)\b',
    ],
    # Netherlands
    'NL': [
        r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(B\.?V\.?|N\.?V\.?|C\.?V\.?)\b',
    ],
    # France
    'FR': [
        r'\b([A-Z][a-zéèêëàâäùûüôöîïç]+(?:\s+[A-Z][a-zéèêëàâäùûüôöîïç]+)*)\s+(S\.?A\.?R\.?L\.?|S\.?A\.?|S\.?A\.?S\.?|EURL)\b',
        r'\b([A-Z][a-zéèêëàâäùûüôöîïç]+(?:\s+[A-Z][a-zéèêëàâäùûüôöîïç]+)*)\s+(Société\s+Anonyme)\b',
    ],
    # Italy
    'IT': [
        r'\b([A-Z][a-zàèéìòù]+(?:\s+[A-Z][a-zàèéìòù]+)*)\s+(S\.?p\.?A\.?|S\.?r\.?l\.?|S\.?a\.?s\.?)\b',
    ],
    # Spain
    'ES': [
        r'\b([A-Z][a-záéíóúñ]+(?:\s+[A-Z][a-záéíóúñ]+)*)\s+(S\.?L\.?|S\.?A\.?|S\.?L\.?U\.?)\b',
    ],
    # Switzerland
    'CH': [
        r'\b([A-Z][a-zäöü]+(?:\s+[A-Z][a-zäöü]+)*)\s+(AG|GmbH|SA|Sàrl)\b',
    ],
    # Luxembourg
    'LU': [
        r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(S\.?à\.?r\.?l\.?|S\.?A\.?)\b',
    ],
    # Cyprus
    'CY': [
        r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(Ltd\.?|Limited)\b',
    ],
    # BVI/Cayman/Jersey (Offshore)
    'OFFSHORE': [
        r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(Ltd\.?|Limited|Inc\.?|Corp\.?)\b',
    ],
    # Hungary
    'HU': [
        r'\b([A-Z][a-záéíóöőúüű]+(?:\s+[A-Z][a-záéíóöőúüű]+)*)\s+(Kft\.?|Zrt\.?|Bt\.?|Nyrt\.?)\b',
    ],
    # Russia
    'RU': [
        r'\b([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)*)\s+(ООО|ОАО|ЗАО|ПАО|АО)\b',
        r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(OOO|OAO|ZAO|PAO)\b',  # Transliterated
    ],
    # Generic international
    'INTL': [
        r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(Holdings?|Group|International|Investments?)\b',
    ],
}

# === REGISTRATION NUMBER PATTERNS ===

REGISTRATION_PATTERNS = {
    'DE_HRB': r'\b(HRB?\s*\d{3,8})\b',  # German Handelsregister
    'DE_HRA': r'\b(HRA?\s*\d{3,8})\b',
    'UK_CH': r'\b(\d{8}|[A-Z]{2}\d{6})\b',  # UK Companies House (8 digits or 2 letters + 6 digits)
    'UK_SC': r'\b(SC\d{6})\b',  # Scottish companies
    'UK_NI': r'\b(NI\d{6})\b',  # Northern Ireland
    'US_EIN': r'\b(\d{2}-\d{7})\b',  # US Employer ID
    'NL_KVK': r'\b(KVK\s*\d{8})\b',  # Dutch Chamber of Commerce
    'FR_SIREN': r'\b(\d{3}\s*\d{3}\s*\d{3})\b',  # French SIREN (9 digits)
    'FR_SIRET': r'\b(\d{3}\s*\d{3}\s*\d{3}\s*\d{5})\b',  # French SIRET (14 digits)
    'CH_UID': r'\b(CHE-\d{3}\.\d{3}\.\d{3})\b',  # Swiss UID
    'LU_RCS': r'\b(B\s*\d{5,6})\b',  # Luxembourg RCS
    'CY_REG': r'\b(HE\s*\d{5,6})\b',  # Cyprus
    'HU_REG': r'\b(Cg\.\s*\d{2}-\d{2}-\d{6})\b',  # Hungarian company reg
}

# === PERSON PATTERNS ===

PERSON_PATTERNS = [
    # Title + Name
    r'\b((?:Mr\.?|Mrs\.?|Ms\.?|Dr\.?|Prof\.?|Sir|Dame|Lord|Lady)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b',
    # Name + Title suffix
    r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\s*,?\s*(CEO|CFO|COO|CTO|Chairman|Director|Managing\s+Director|MD|President|VP|Vice\s+President)\b',
    # German titles
    r'\b((?:Herr|Frau|Dr\.|Prof\.)\s+[A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+){1,3})\b',
]

# === DATE PATTERNS ===

DATE_PATTERNS = [
    r'\b(\d{1,2}[./]\d{1,2}[./]\d{2,4})\b',  # DD/MM/YYYY or DD.MM.YYYY
    r'\b(\d{4}-\d{2}-\d{2})\b',  # ISO format
    r'\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})\b',
    r'\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})\b',
    r'\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{4})\b',
]

# === FINANCIAL PATTERNS ===

FINANCIAL_PATTERNS = [
    # Currency amounts
    r'([$€£¥]\s*\d{1,3}(?:[,.\s]\d{3})*(?:[.,]\d{2})?(?:\s*(?:million|billion|m|bn|k|M|B))?)',
    r'(\d{1,3}(?:[,.\s]\d{3})*(?:[.,]\d{2})?\s*(?:USD|EUR|GBP|CHF|JPY))',
    r'(\d{1,3}(?:[,.\s]\d{3})*(?:[.,]\d{2})?\s*(?:dollars?|euros?|pounds?|francs?))',
    # Percentages
    r'(\d{1,3}(?:[.,]\d{1,2})?\s*%)',
]

# === ADDRESS PATTERNS ===

ADDRESS_PATTERNS = [
    # German addresses
    r'\b([A-ZÄÖÜ][a-zäöüß]+(?:straße|str\.|weg|platz|allee|ring|gasse)\s*\d+[a-z]?(?:\s*,\s*\d{5}\s+[A-ZÄÖÜ][a-zäöüß]+)?)\b',
    # UK postcodes
    r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})\b',
    # US ZIP
    r'\b(\d{5}(?:-\d{4})?)\b',
]


class EntityExtractor:
    """Extract entities from text using regex patterns."""

    def __init__(self, jurisdictions: Optional[List[str]] = None):
        """
        Initialize extractor.

        Args:
            jurisdictions: List of jurisdiction codes to use. If None, uses all.
        """
        self.jurisdictions = jurisdictions or list(COMPANY_FORMS.keys())
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compile regex patterns for performance."""
        self._company_patterns = {}
        for jur in self.jurisdictions:
            if jur in COMPANY_FORMS:
                self._company_patterns[jur] = [
                    re.compile(p, re.IGNORECASE | re.UNICODE)
                    for p in COMPANY_FORMS[jur]
                ]

        self._registration_patterns = {
            k: re.compile(v, re.IGNORECASE)
            for k, v in REGISTRATION_PATTERNS.items()
        }

        self._person_patterns = [
            re.compile(p, re.UNICODE) for p in PERSON_PATTERNS
        ]

        self._date_patterns = [
            re.compile(p, re.IGNORECASE) for p in DATE_PATTERNS
        ]

        self._financial_patterns = [
            re.compile(p, re.IGNORECASE | re.UNICODE) for p in FINANCIAL_PATTERNS
        ]

    def extract_companies(self, text: str) -> List[ExtractedEntity]:
        """Extract company names with legal forms."""
        entities = []
        seen: Set[str] = set()

        for jur, patterns in self._company_patterns.items():
            for pattern in patterns:
                for match in pattern.finditer(text):
                    full_match = match.group(0).strip()
                    if full_match.lower() in seen:
                        continue
                    seen.add(full_match.lower())

                    # Get surrounding context
                    start = max(0, match.start() - 50)
                    end = min(len(text), match.end() + 50)
                    context = text[start:end].replace('\n', ' ').strip()

                    # Determine subtype (legal form)
                    groups = match.groups()
                    subtype = groups[-1] if len(groups) > 1 else None

                    entities.append(ExtractedEntity(
                        text=full_match,
                        type='company',
                        subtype=subtype,
                        context=context,
                        jurisdiction=jur,
                        confidence=0.85 if subtype else 0.7
                    ))

        return entities

    def extract_registrations(self, text: str) -> List[ExtractedEntity]:
        """Extract registration numbers."""
        entities = []
        seen: Set[str] = set()

        for reg_type, pattern in self._registration_patterns.items():
            for match in pattern.finditer(text):
                reg_num = match.group(1).strip()
                if reg_num.lower() in seen:
                    continue
                seen.add(reg_num.lower())

                # Determine jurisdiction from pattern name
                jur = reg_type.split('_')[0]

                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end].replace('\n', ' ').strip()

                entities.append(ExtractedEntity(
                    text=reg_num,
                    type='registration',
                    subtype=reg_type,
                    context=context,
                    jurisdiction=jur,
                    confidence=0.9
                ))

        return entities

    def extract_persons(self, text: str) -> List[ExtractedEntity]:
        """Extract person names with titles."""
        entities = []
        seen: Set[str] = set()

        for pattern in self._person_patterns:
            for match in pattern.finditer(text):
                name = match.group(1).strip()
                if name.lower() in seen:
                    continue
                seen.add(name.lower())

                # Get role if captured
                groups = match.groups()
                role = groups[1] if len(groups) > 1 else None

                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end].replace('\n', ' ').strip()

                entities.append(ExtractedEntity(
                    text=name,
                    type='person',
                    subtype=role,
                    context=context,
                    confidence=0.75
                ))

        return entities

    def extract_dates(self, text: str) -> List[ExtractedEntity]:
        """Extract dates."""
        entities = []
        seen: Set[str] = set()

        for pattern in self._date_patterns:
            for match in pattern.finditer(text):
                date_str = match.group(1).strip()
                if date_str in seen:
                    continue
                seen.add(date_str)

                start = max(0, match.start() - 30)
                end = min(len(text), match.end() + 30)
                context = text[start:end].replace('\n', ' ').strip()

                entities.append(ExtractedEntity(
                    text=date_str,
                    type='date',
                    context=context,
                    confidence=0.9
                ))

        return entities

    def extract_financials(self, text: str) -> List[ExtractedEntity]:
        """Extract financial figures."""
        entities = []
        seen: Set[str] = set()

        for pattern in self._financial_patterns:
            for match in pattern.finditer(text):
                amount = match.group(1).strip()
                if amount in seen:
                    continue
                seen.add(amount)

                start = max(0, match.start() - 40)
                end = min(len(text), match.end() + 40)
                context = text[start:end].replace('\n', ' ').strip()

                entities.append(ExtractedEntity(
                    text=amount,
                    type='amount',
                    context=context,
                    confidence=0.85
                ))

        return entities

    def extract_all(self, text: str) -> Dict[str, List[ExtractedEntity]]:
        """Extract all entity types."""
        return {
            'companies': self.extract_companies(text),
            'registrations': self.extract_registrations(text),
            'persons': self.extract_persons(text),
            'dates': self.extract_dates(text),
            'financials': self.extract_financials(text),
        }

    def extract_with_custom_pattern(
        self,
        text: str,
        pattern: str,
        entity_type: str = 'custom',
        flags: int = re.IGNORECASE
    ) -> List[ExtractedEntity]:
        """
        Extract entities using a custom regex pattern.

        Args:
            text: Text to search
            pattern: Regex pattern (string)
            entity_type: Type label for extracted entities
            flags: Regex flags

        Returns:
            List of extracted entities
        """
        entities = []
        compiled = re.compile(pattern, flags)

        for match in compiled.finditer(text):
            full_match = match.group(0).strip()

            start = max(0, match.start() - 50)
            end = min(len(text), match.end() + 50)
            context = text[start:end].replace('\n', ' ').strip()

            entities.append(ExtractedEntity(
                text=full_match,
                type=entity_type,
                context=context,
                confidence=0.8
            ))

        return entities

    def to_dict(self, entities: List[ExtractedEntity]) -> List[Dict[str, Any]]:
        """Convert entities to dict format."""
        return [
            {
                'text': e.text,
                'type': e.type,
                'subtype': e.subtype,
                'context': e.context,
                'confidence': e.confidence,
                'jurisdiction': e.jurisdiction,
            }
            for e in entities
        ]


# Convenience functions
def extract_companies(text: str, jurisdictions: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Quick company extraction."""
    extractor = EntityExtractor(jurisdictions)
    entities = extractor.extract_companies(text)
    return extractor.to_dict(entities)


def extract_all_entities(text: str) -> Dict[str, List[Dict[str, Any]]]:
    """Quick full extraction."""
    extractor = EntityExtractor()
    result = extractor.extract_all(text)
    return {k: extractor.to_dict(v) for k, v in result.items()}


# CLI for testing
if __name__ == '__main__':
    import sys
    import json

    test_text = """
    Die Müller Holding GmbH & Co. KG (HRB 12345) mit Sitz in Frankfurt am Main,
    Hauptstraße 42, 60311 Frankfurt, wurde am 15. Januar 2020 gegründet.

    Der Geschäftsführer Dr. Hans Schmidt hat 25% der Anteile. Die Tochtergesellschaft
    Müller International Ltd. (Company Number 12345678) in London erwirtschaftete
    €50 million Umsatz in 2023.

    Smith & Partners LLC (EIN 12-3456789) aus Delaware ist ebenfalls beteiligt.
    Acme Corporation Inc. is the US parent company.

    Contact: Mrs. Jane Doe, CFO at jane.doe@mueller-holding.de
    """

    if len(sys.argv) > 1:
        # Read from file
        with open(sys.argv[1], 'r') as f:
            test_text = f.read()

    extractor = EntityExtractor()
    results = extractor.extract_all(test_text)

    print("=== EXTRACTED ENTITIES ===\n")
    for entity_type, entities in results.items():
        if entities:
            print(f"\n--- {entity_type.upper()} ({len(entities)}) ---")
            for e in entities:
                print(f"  • {e.text}")
                if e.subtype:
                    print(f"    Type: {e.subtype}")
                if e.jurisdiction:
                    print(f"    Jurisdiction: {e.jurisdiction}")
                print(f"    Context: ...{e.context}...")
                print()
