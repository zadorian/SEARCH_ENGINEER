"""
SASTRE Surprising AND Detector - Find unexpected co-occurrences.

"Surprising AND" = When two entities appear together unexpectedly.

Examples:
- "John Smith" AND "Offshore Trust" - Person + offshore structure
- "Acme Corp" AND "Sanctions List" - Company + sanctions
- "CEO Name" AND "Competitor" - Executive + competitor company
- "Politician" AND "Shell Company" - Public figure + opacity

These become investigation priorities because they suggest:
1. Hidden relationships
2. Potential conflicts of interest
3. Undisclosed connections
4. Red flags

The surprise factor comes from:
- Low expected co-occurrence in normal contexts
- High significance when co-occurrence does occur
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Tuple
from enum import Enum
import re


# =============================================================================
# SURPRISE CATEGORIES
# =============================================================================

class SurpriseCategory(Enum):
    """Categories of surprising co-occurrences."""
    RED_FLAG = "red_flag"              # Sanctions, fraud, criminal
    CONFLICT = "conflict"              # Competitor, conflict of interest
    OPACITY = "opacity"                # Offshore, anonymous, shell
    POLITICAL = "political"            # Government, political connections
    FINANCIAL = "financial"            # Large amounts, unusual transactions
    PERSONAL = "personal"              # Family, hidden relationships
    LEGAL = "legal"                    # Lawsuits, investigations
    MEDIA = "media"                    # Negative press, controversies


class SurpriseLevel(Enum):
    """How surprising the co-occurrence is."""
    EXTREMELY = "extremely"    # Very unexpected, high priority
    VERY = "very"              # Notable surprise
    MODERATELY = "moderately"  # Worth investigating
    SLIGHTLY = "slightly"      # Interesting but not urgent


# =============================================================================
# SURPRISING AND
# =============================================================================

@dataclass
class SurprisingAnd:
    """A surprising co-occurrence of entities."""
    entity_a: str
    entity_b: str
    category: SurpriseCategory
    surprise_level: SurpriseLevel
    reason: str
    source: str               # Where the co-occurrence was found
    context: str              # Surrounding text
    investigation_priority: float  # 0.0 - 1.0
    suggested_queries: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# CO-OCCURRENCE RULES
# =============================================================================

# Patterns that make co-occurrences surprising
SURPRISE_PATTERNS = {
    'red_flag': {
        'terms': [
            'sanctions', 'sanctioned', 'ofac', 'sdn list',
            'fraud', 'fraudulent', 'indicted', 'convicted',
            'money laundering', 'aml', 'bribery', 'corruption',
            'criminal', 'arrest', 'prosecution', 'extradition',
            'terrorist', 'terrorism', 'financing',
        ],
        'significance': 1.0,
        'description': 'Connection to sanctions, fraud, or criminal activity',
    },
    'opacity': {
        'terms': [
            'offshore', 'shell company', 'nominee', 'bearer shares',
            'bvi', 'cayman', 'panama', 'seychelles',
            'trust', 'foundation', 'anonymous',
            'beneficial owner', 'ubo',
        ],
        'significance': 0.8,
        'description': 'Connection to offshore or opaque structures',
    },
    'political': {
        'terms': [
            'pep', 'politically exposed',
            'minister', 'senator', 'congressman', 'mp',
            'government', 'state-owned', 'public official',
            'campaign', 'donation', 'lobbyist', 'lobbying',
        ],
        'significance': 0.7,
        'description': 'Connection to political figures or government',
    },
    'conflict': {
        'terms': [
            'competitor', 'rival', 'conflict of interest',
            'insider', 'self-dealing', 'related party',
            'undisclosed', 'hidden interest',
        ],
        'significance': 0.75,
        'description': 'Potential conflict of interest',
    },
    'legal': {
        'terms': [
            'lawsuit', 'litigation', 'sued', 'defendant',
            'investigation', 'subpoena', 'deposition',
            'settlement', 'judgment', 'verdict',
            'sec', 'doj', 'fbi', 'fca', 'sfo',
        ],
        'significance': 0.7,
        'description': 'Connection to legal proceedings',
    },
    'financial': {
        'terms': [
            'million', 'billion', 'wire transfer',
            'unusual transaction', 'suspicious activity',
            'tax haven', 'tax evasion', 'unreported',
            'debt', 'bankruptcy', 'insolvent',
        ],
        'significance': 0.6,
        'description': 'Significant financial activity',
    },
}

# Entity type combinations that are inherently surprising
SURPRISING_COMBINATIONS = [
    ('person', 'offshore', 0.7, SurpriseCategory.OPACITY),
    ('executive', 'competitor', 0.8, SurpriseCategory.CONFLICT),
    ('politician', 'company', 0.6, SurpriseCategory.POLITICAL),
    ('public_figure', 'shell_company', 0.9, SurpriseCategory.RED_FLAG),
    ('company', 'sanctions', 1.0, SurpriseCategory.RED_FLAG),
    ('person', 'lawsuit', 0.5, SurpriseCategory.LEGAL),
]


# =============================================================================
# SURPRISING AND DETECTOR
# =============================================================================

class SurprisingAndDetector:
    """
    Detects surprising co-occurrences of entities.

    Scans text for:
    1. Known entities appearing with red flag terms
    2. Entity pairs that shouldn't normally co-occur
    3. Context that elevates significance
    """

    def __init__(self):
        self.surprise_patterns = SURPRISE_PATTERNS
        self.surprising_combinations = SURPRISING_COMBINATIONS

    def detect(
        self,
        text: str,
        known_entities: List[Dict[str, Any]] = None,
        sources: List[Dict[str, Any]] = None
    ) -> List[SurprisingAnd]:
        """
        Detect surprising ANDs in text.

        Args:
            text: Text to analyze
            known_entities: List of known entities with names and types
            sources: Source documents (each with 'content' and 'url'/'source_id')
        """
        surprises = []

        # Build entity name set for fast lookup
        entity_names = set()
        entity_types = {}
        if known_entities:
            for e in known_entities:
                name = e.get('name', e.get('display_name', ''))
                if name:
                    entity_names.add(name.lower())
                    entity_types[name.lower()] = e.get('type', 'unknown')

        # 1. Check main text for pattern matches
        text_surprises = self._detect_in_text(text, entity_names, entity_types, 'narrative')
        surprises.extend(text_surprises)

        # 2. Check each source document
        if sources:
            for source in sources:
                content = source.get('content', '')
                source_id = source.get('url', source.get('source_id', 'unknown'))
                source_surprises = self._detect_in_text(
                    content, entity_names, entity_types, source_id
                )
                surprises.extend(source_surprises)

        # 3. Detect entity-entity surprising combinations
        if known_entities and len(known_entities) > 1:
            combo_surprises = self._detect_entity_combinations(known_entities, text)
            surprises.extend(combo_surprises)

        # Deduplicate and sort by priority
        surprises = self._deduplicate(surprises)
        surprises.sort(key=lambda s: -s.investigation_priority)

        return surprises

    def _detect_in_text(
        self,
        text: str,
        entity_names: Set[str],
        entity_types: Dict[str, str],
        source: str
    ) -> List[SurprisingAnd]:
        """Detect surprising patterns in text."""
        surprises = []
        text_lower = text.lower()

        # For each entity, check if surprise patterns appear nearby
        for entity_name in entity_names:
            # Find entity in text
            entity_positions = self._find_positions(text_lower, entity_name)

            for pos in entity_positions:
                # Get context window (500 chars around entity)
                context_start = max(0, pos - 250)
                context_end = min(len(text), pos + len(entity_name) + 250)
                context = text[context_start:context_end]
                context_lower = context.lower()

                # Check each surprise pattern category
                for category, pattern_info in self.surprise_patterns.items():
                    for term in pattern_info['terms']:
                        if term in context_lower:
                            # Found surprising co-occurrence!
                            surprise_level = self._calculate_surprise_level(
                                pattern_info['significance'],
                                entity_types.get(entity_name, 'unknown'),
                                term
                            )

                            surprises.append(SurprisingAnd(
                                entity_a=entity_name,
                                entity_b=term,
                                category=SurpriseCategory[category.upper()],
                                surprise_level=surprise_level,
                                reason=pattern_info['description'],
                                source=source,
                                context=context,
                                investigation_priority=pattern_info['significance'],
                                suggested_queries=self._generate_follow_up_queries(
                                    entity_name, term, category
                                ),
                            ))

        return surprises

    def _detect_entity_combinations(
        self,
        entities: List[Dict[str, Any]],
        text: str
    ) -> List[SurprisingAnd]:
        """Detect surprising combinations of entities appearing together."""
        surprises = []
        text_lower = text.lower()

        # Check all entity pairs
        for i, entity_a in enumerate(entities):
            name_a = entity_a.get('name', entity_a.get('display_name', ''))
            type_a = entity_a.get('type', 'unknown')

            for entity_b in entities[i+1:]:
                name_b = entity_b.get('name', entity_b.get('display_name', ''))
                type_b = entity_b.get('type', 'unknown')

                # Check if both appear in text
                if name_a.lower() in text_lower and name_b.lower() in text_lower:
                    # Check if this combination is surprising
                    for combo in self.surprising_combinations:
                        combo_type_a, combo_type_b, significance, category = combo

                        if (type_a == combo_type_a and type_b == combo_type_b) or \
                           (type_a == combo_type_b and type_b == combo_type_a):

                            # Find context where they co-occur
                            context = self._find_co_occurrence_context(
                                text, name_a, name_b
                            )

                            surprises.append(SurprisingAnd(
                                entity_a=name_a,
                                entity_b=name_b,
                                category=category,
                                surprise_level=self._significance_to_level(significance),
                                reason=f"Unexpected co-occurrence: {type_a} + {type_b}",
                                source='entity_analysis',
                                context=context,
                                investigation_priority=significance,
                                suggested_queries=[
                                    f'"{name_a}" AND "{name_b}"',
                                    f'"{name_a}" "{name_b}" relationship',
                                ],
                            ))

        return surprises

    def _find_positions(self, text: str, term: str) -> List[int]:
        """Find all positions of a term in text."""
        positions = []
        start = 0
        while True:
            pos = text.find(term.lower(), start)
            if pos == -1:
                break
            positions.append(pos)
            start = pos + 1
        return positions

    def _find_co_occurrence_context(
        self,
        text: str,
        name_a: str,
        name_b: str
    ) -> str:
        """Find text context where two names co-occur closest."""
        text_lower = text.lower()
        pos_a = text_lower.find(name_a.lower())
        pos_b = text_lower.find(name_b.lower())

        if pos_a == -1 or pos_b == -1:
            return ""

        # Get context around the midpoint between them
        min_pos = min(pos_a, pos_b)
        max_pos = max(pos_a, pos_b) + max(len(name_a), len(name_b))

        context_start = max(0, min_pos - 100)
        context_end = min(len(text), max_pos + 100)

        return text[context_start:context_end]

    def _calculate_surprise_level(
        self,
        base_significance: float,
        entity_type: str,
        term: str
    ) -> SurpriseLevel:
        """Calculate how surprising this co-occurrence is."""
        # Adjust for entity type
        type_multiplier = {
            'person': 1.0,
            'company': 0.9,
            'public_figure': 1.2,
            'politician': 1.3,
            'executive': 1.1,
        }.get(entity_type, 1.0)

        adjusted = base_significance * type_multiplier

        if adjusted >= 0.9:
            return SurpriseLevel.EXTREMELY
        elif adjusted >= 0.7:
            return SurpriseLevel.VERY
        elif adjusted >= 0.5:
            return SurpriseLevel.MODERATELY
        else:
            return SurpriseLevel.SLIGHTLY

    def _significance_to_level(self, significance: float) -> SurpriseLevel:
        """Convert significance score to surprise level."""
        if significance >= 0.9:
            return SurpriseLevel.EXTREMELY
        elif significance >= 0.7:
            return SurpriseLevel.VERY
        elif significance >= 0.5:
            return SurpriseLevel.MODERATELY
        else:
            return SurpriseLevel.SLIGHTLY

    def _generate_follow_up_queries(
        self,
        entity: str,
        term: str,
        category: str
    ) -> List[str]:
        """Generate follow-up queries for a surprising AND."""
        queries = [
            f'"{entity}" AND "{term}"',
            f'"{entity}" {term}',
        ]

        # Add category-specific queries
        if category == 'red_flag':
            queries.extend([
                f'"{entity}" sanctions OFAC',
                f'"{entity}" fraud investigation',
            ])
        elif category == 'opacity':
            queries.extend([
                f'"{entity}" offshore BVI Cayman Panama',
                f'"{entity}" beneficial owner',
            ])
        elif category == 'political':
            queries.extend([
                f'"{entity}" politically exposed person PEP',
                f'"{entity}" government connection',
            ])
        elif category == 'legal':
            queries.extend([
                f'"{entity}" lawsuit litigation',
                f'"{entity}" defendant plaintiff',
            ])

        return queries

    def _deduplicate(
        self,
        surprises: List[SurprisingAnd]
    ) -> List[SurprisingAnd]:
        """Remove duplicate surprising ANDs."""
        seen = set()
        unique = []

        for s in surprises:
            key = (
                s.entity_a.lower(),
                s.entity_b.lower(),
                s.category.value
            )
            # Also check reverse
            key_rev = (
                s.entity_b.lower(),
                s.entity_a.lower(),
                s.category.value
            )

            if key not in seen and key_rev not in seen:
                seen.add(key)
                unique.append(s)

        return unique


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def detect_surprising_ands(
    text: str,
    known_entities: List[Dict[str, Any]] = None,
    sources: List[Dict[str, Any]] = None
) -> List[SurprisingAnd]:
    """Detect surprising co-occurrences in text."""
    return SurprisingAndDetector().detect(text, known_entities, sources)
