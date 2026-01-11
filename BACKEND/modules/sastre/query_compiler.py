#!/usr/bin/env python3
"""
SASTRE Query Compiler

The agent is a translator, not a programmer.
Fluent in the language, ignorant of the machinery.

Integrates:
- IntentTranslator (natural language → syntax)
- Variators from query_lab (name/company/location variations)
- Operator reference (all SASTRE operators)
- K-U aware query generation
"""

import re
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging

# Import canonical types from contracts
from .contracts import KUQuadrant, Intent
from .budget_enforcer import QueryEconomist, TokenCandidate

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS AND TYPES
# =============================================================================

class EntityType(Enum):
    PERSON = "person"
    COMPANY = "company"
    LOCATION = "location"
    PHONE = "phone"
    EMAIL = "email"
    DOMAIN = "domain"
    ASSET = "asset"
    DOCUMENT = "document"
    SOURCE = "source"


# =============================================================================
# INVESTIGATION STATE
# =============================================================================

@dataclass
class Entity:
    """An entity in the investigation."""
    id: str
    name: str
    entity_type: EntityType
    variations: List[str] = field(default_factory=list)
    anchors: Dict[str, Any] = field(default_factory=dict)
    sources: List[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_hashtag(self) -> str:
        """Convert to hashtag syntax."""
        return f"#{self.id}"


@dataclass
class QueryContext:
    """Current investigation context."""
    current_focus: str = ""
    entities: Dict[str, Entity] = field(default_factory=dict)
    sources: Dict[str, Any] = field(default_factory=dict)
    narrative: str = ""
    priority_concepts: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    ku_quadrant: Optional[KUQuadrant] = None
    profile: Optional["EntityProfile"] = None


# =============================================================================
# QUERY GENERATION STRATEGY (Architecture Refactor)
# =============================================================================
#
# Strategy Pattern for unified query generation.
# All query generators implement this interface.
# =============================================================================

class QueryGenerationStrategy(ABC):
    """
    Abstract base class for query generation strategies.

    All query generation approaches (triangulation, environment-aware,
    dimension-based) implement this interface for unified orchestration.

    Strategies can be:
    - TriangulationStrategy: Slot-filling with anchor + intersections
    - EnvironmentAwareStrategy: Targets specific document types (decorator)
    - KUAwareStrategy: Adjusts queries based on K-U quadrant (decorator)
    """

    @abstractmethod
    def generate(self, context: QueryContext) -> List["QueryResult"]:
        """
        Generate queries based on context.

        Args:
            context: QueryContext with profile, entities, K-U quadrant

        Returns:
            List of QueryResult objects with tier, quality score
        """
        pass

    @abstractmethod
    def get_tier_distribution(self) -> Dict[str, int]:
        """
        Return expected query count per tier.

        Returns:
            Dict mapping tier names (T1-T5) to expected counts
        """
        pass

    def get_strategy_name(self) -> str:
        """Return human-readable strategy name."""
        return self.__class__.__name__


class StrategyDecorator(QueryGenerationStrategy):
    """
    Base decorator for wrapping strategies with additional behavior.

    Decorators can add:
    - Environment-specific queries
    - K-U quadrant filtering
    - Domain constraints
    """

    def __init__(self, base_strategy: QueryGenerationStrategy):
        self.base_strategy = base_strategy

    def generate(self, context: QueryContext) -> List["QueryResult"]:
        """Default: delegate to base strategy."""
        return self.base_strategy.generate(context)

    def get_tier_distribution(self) -> Dict[str, int]:
        """Default: delegate to base strategy."""
        return self.base_strategy.get_tier_distribution()


class EnvironmentAwareStrategy(StrategyDecorator):
    """
    Decorator that adds environment-specific queries.

    PHILOSOPHY: "Query for the TEXTUAL ENVIRONMENT where answers appear."

    Environments map to document types and search patterns:
    - corporate_filing: SEC filings, company accounts, annual reports
    - news: Press releases, news articles
    - court_record: Litigation, court judgments
    - registry: Director appointments, company registrations
    - sanctions: OFAC/EU/UN sanctions lists
    """

    # Map environments to search patterns
    ENVIRONMENT_PATTERNS = {
        "corporate_filing": [
            ("annual report", "filetype:pdf"),
            ("10-K OR 10-Q", "site:sec.gov"),
            ("company accounts", "site:companieshouse.gov.uk"),
            ("financial statements", "filetype:pdf"),
        ],
        "news": [
            ("news", "site:reuters.com OR site:bloomberg.com OR site:wsj.com"),
            ("press release", ""),
            ("announcement", ""),
        ],
        "court_record": [
            ("court", "case OR lawsuit OR judgment"),
            ("litigation", "defendant OR plaintiff"),
            ("vs OR versus", "court OR judge"),
        ],
        "registry": [
            ("director", "appointed OR resigned OR registered"),
            ("officer", "registration OR incorporation"),
            ("beneficial owner", ""),
        ],
        "sanctions": [
            ("sanctions", "OFAC OR EU OR UN"),
            ("designated", "blocked OR prohibited"),
            ("SDN list", ""),
        ],
    }

    def __init__(
        self,
        base_strategy: QueryGenerationStrategy,
        environment: str,
        domains: Optional[List[str]] = None
    ):
        super().__init__(base_strategy)
        self.environment = environment
        self.domains = domains or []

    def generate(self, context: QueryContext) -> List["QueryResult"]:
        """Generate base queries + environment-specific queries."""
        # Get base queries
        base_queries = self.base_strategy.generate(context)

        # Add environment queries
        env_queries = self._generate_environment_queries(context)

        # Merge (environment queries as T3 priority)
        return base_queries + env_queries

    def get_tier_distribution(self) -> Dict[str, int]:
        """Base distribution + environment queries."""
        dist = self.base_strategy.get_tier_distribution()
        patterns = self.ENVIRONMENT_PATTERNS.get(self.environment, [])
        dist["T3"] = dist.get("T3", 0) + len(patterns)
        return dist

    def _generate_environment_queries(
        self,
        context: QueryContext
    ) -> List["QueryResult"]:
        """Generate queries targeting the document environment."""
        queries = []

        # Get anchor from context profile
        anchor = ""
        if context and context.profile:
            # Create triangulator to get anchor
            triangulator = EntityTriangulator(context.profile)
            anchor = triangulator.anchor

        patterns = self.ENVIRONMENT_PATTERNS.get(self.environment, [])

        for pattern_name, pattern_extra in patterns:
            query_parts = []

            if anchor:
                query_parts.append(anchor)

            query_parts.append(f'"{pattern_name}"')

            if pattern_extra:
                query_parts.append(f"({pattern_extra})")

            # Add domain constraints
            if self.domains:
                domain_or = " OR ".join(f"site:{d}" for d in self.domains[:3])
                query_parts.append(f"({domain_or})")

            queries.append(QueryResult(
                q=" ".join(query_parts),
                tier="T3",
                src=f"environment:{self.environment}",
                est_hits="medium",
                est_noise=15,
                quality_score=0.75,
                slot_used=f"env:{pattern_name}"
            ))

        return queries


class KUAwareStrategy(StrategyDecorator):
    """
    Decorator that filters/prioritizes queries based on K-U quadrant.

    K-U Quadrants:
    - DISCOVER: Unknown unknowns → Broad queries (T4-T5)
    - VERIFY: Known knowns → Precise queries (T1-T2)
    - TRACE: Known unknowns → Medium queries (T2-T3)
    - EXTRACT: Unknown knowns → All queries
    """

    # Query count limits per quadrant
    QUADRANT_LIMITS = {
        KUQuadrant.DISCOVER: {"max": 20, "focus_tiers": ["T4", "T5"]},
        KUQuadrant.VERIFY: {"max": 10, "focus_tiers": ["T1", "T2"]},
        KUQuadrant.TRACE: {"max": 15, "focus_tiers": ["T2", "T3"]},
        KUQuadrant.EXTRACT: {"max": 25, "focus_tiers": ["T1", "T2", "T3", "T4", "T5"]},
    }

    def __init__(
        self,
        base_strategy: QueryGenerationStrategy,
        ku_quadrant: KUQuadrant
    ):
        super().__init__(base_strategy)
        self.ku_quadrant = ku_quadrant

    def generate(self, context: QueryContext) -> List["QueryResult"]:
        """Generate queries filtered by K-U quadrant."""
        # Update context with quadrant
        if context:
            context.ku_quadrant = self.ku_quadrant

        # Get base queries
        queries = self.base_strategy.generate(context)

        # Apply quadrant filtering
        return self._filter_by_quadrant(queries)

    def _filter_by_quadrant(
        self,
        queries: List["QueryResult"]
    ) -> List["QueryResult"]:
        """Filter and limit queries based on quadrant."""
        limits = self.QUADRANT_LIMITS.get(self.ku_quadrant)
        if not limits:
            return queries

        focus_tiers = set(limits["focus_tiers"])
        max_queries = limits["max"]

        # Prioritize focus tiers
        prioritized = sorted(
            queries,
            key=lambda q: (q.tier in focus_tiers, q.quality_score),
            reverse=True
        )

        return prioritized[:max_queries]


# =============================================================================
# VARIATORS (from query_lab)
# =============================================================================

class BaseVariator(ABC):
    """
    Base class for all variators.

    From query_lab - generates search term variations with strength scores.
    Strength scores:
        5 = Very unique, high value (rare full names, unique surnames)
        4 = Unique, good value (uncommon names, full names with middle)
        3 = Moderate value (common full names, nicknames with surnames)
        2 = Low value (common first names, initials with common surnames)
        1 = Very low value (single common names, ambiguous initials)
    """

    def __init__(self):
        self.name = "base"

    @abstractmethod
    def get_prompt(self, text: str) -> str:
        """Generate prompt for AI variation generation."""
        pass

    @abstractmethod
    def fallback_variations(self, text: str) -> List[str]:
        """Generate fallback variations without AI."""
        pass

    def generate_variations_with_strength(self, text: str) -> List[Tuple[str, int]]:
        """Generate variations with strength scores (1-5)."""
        variations = self.generate_variations(text)

        variations_with_strength = []
        for var in variations:
            strength = self.calculate_strength(text, var)
            variations_with_strength.append((var, strength))

        # Sort by strength (highest first)
        variations_with_strength.sort(key=lambda x: x[1], reverse=True)
        return variations_with_strength

    def calculate_strength(self, original: str, variation: str) -> int:
        """Calculate strength score for a variation."""
        if variation == original:
            return 5  # Original is always high strength
        elif len(variation.split()) >= 3:
            return 4  # 3+ word variations are high value
        elif len(variation.split()) >= 2:
            return 3  # Multi-word variations are moderate
        elif len(variation) > 5:
            return 2  # Single longer words
        else:
            return 1  # Single short words - low strength

    def generate_variations(self, text: str) -> List[str]:
        """Generate variations (fallback only for now)."""
        variations = self.fallback_variations(text)

        # Remove duplicates while preserving order
        seen = set()
        unique = []
        for v in variations:
            if v and v not in seen:
                seen.add(v)
                unique.append(v)

        return unique


class PersonVariator(BaseVariator):
    """Generates variations of person names."""

    def __init__(self):
        super().__init__()
        self.name = "person"

    def get_prompt(self, text: str) -> str:
        return f"""Generate search variations for the person name: "{text}"

Include:
- Full name variations (with/without middle names/initials)
- Common nicknames and diminutives
- Transliterations if non-Latin origin
- Initial combinations (J. Smith, John S.)
- Maiden name patterns if applicable

Return as JSON: {{"variations": ["var1", "var2", ...]}}"""

    def fallback_variations(self, text: str) -> List[str]:
        """Generate person name variations without AI."""
        variations = [text]
        parts = text.strip().split()

        if len(parts) >= 2:
            first = parts[0]
            last = parts[-1]
            middle = parts[1:-1] if len(parts) > 2 else []

            # Full name
            variations.append(text)

            # First Last
            variations.append(f"{first} {last}")

            # Last, First
            variations.append(f"{last}, {first}")

            # Initials
            variations.append(f"{first[0]}. {last}")
            variations.append(f"{first[0]} {last}")
            variations.append(f"{first} {last[0]}.")

            # With middle initials
            if middle:
                middle_init = " ".join(m[0] + "." for m in middle)
                variations.append(f"{first} {middle_init} {last}")
                variations.append(f"{first[0]}. {middle_init} {last}")

            # Common nicknames (hardcoded common ones)
            nicknames = {
                "William": ["Will", "Bill", "Billy", "Willy"],
                "Robert": ["Rob", "Bob", "Bobby", "Robbie"],
                "Richard": ["Rich", "Rick", "Dick", "Ricky"],
                "Michael": ["Mike", "Mikey", "Mick"],
                "James": ["Jim", "Jimmy", "Jamie"],
                "John": ["Jack", "Johnny", "Jon"],
                "Joseph": ["Joe", "Joey"],
                "David": ["Dave", "Davey"],
                "Alexander": ["Alex", "Sasha", "Xander"],
                "Elizabeth": ["Liz", "Beth", "Lizzy", "Eliza"],
                "Margaret": ["Maggie", "Meg", "Peggy"],
                "Catherine": ["Kate", "Katie", "Cathy", "Cat"],
                "Thomas": ["Tom", "Tommy"],
                "Charles": ["Charlie", "Chuck", "Chas"],
                "Edward": ["Ed", "Eddie", "Ted", "Teddy"],
                "Christopher": ["Chris", "Topher", "Kit"],
            }

            if first in nicknames:
                for nick in nicknames[first]:
                    variations.append(f"{nick} {last}")

        return variations

    def calculate_strength(self, original: str, variation: str) -> int:
        """Person-specific strength calculation."""
        parts = original.split()
        var_parts = variation.split()

        if variation == original:
            return 5

        # Full name with middle = high value
        if len(var_parts) >= 3:
            return 4

        # First + Last name = good
        if len(var_parts) == 2 and not any(len(p) <= 2 for p in var_parts):
            return 3

        # Has initials = moderate
        if any("." in p for p in var_parts):
            return 2

        # Single name or just initials = low
        return 1


class CompanyVariator(BaseVariator):
    """Generates variations of company names."""

    SUFFIXES = [
        "Inc", "Inc.", "Incorporated",
        "Corp", "Corp.", "Corporation",
        "Ltd", "Ltd.", "Limited",
        "LLC", "L.L.C.",
        "LLP", "L.L.P.",
        "PLC", "P.L.C.", "Plc",
        "GmbH", "AG", "SA", "S.A.",
        "BV", "B.V.", "NV", "N.V.",
        "Pty", "Pty Ltd", "Pty. Ltd.",
        "Co", "Co.", "Company",
        "&", "and",
    ]

    def __init__(self):
        super().__init__()
        self.name = "company"

    def get_prompt(self, text: str) -> str:
        return f"""Generate search variations for the company name: "{text}"

Include:
- With and without corporate suffixes (Inc, Ltd, Corp, GmbH, etc.)
- Common abbreviations
- DBA/trading names if apparent
- Spelling variations (& vs and, etc.)

Return as JSON: {{"variations": ["var1", "var2", ...]}}"""

    def fallback_variations(self, text: str) -> List[str]:
        """Generate company name variations without AI."""
        variations = [text]

        # Remove suffixes to get base name
        base = text
        for suffix in sorted(self.SUFFIXES, key=len, reverse=True):
            pattern = rf"\s*{re.escape(suffix)}\s*$"
            if re.search(pattern, base, re.IGNORECASE):
                base = re.sub(pattern, "", base, flags=re.IGNORECASE).strip()
                break

        variations.append(base)

        # Add common suffixes
        common_suffixes = ["Inc", "Inc.", "Corp", "Ltd", "LLC"]
        for suffix in common_suffixes:
            variations.append(f"{base} {suffix}")

        # Replace & with and and vice versa
        if "&" in base:
            variations.append(base.replace("&", "and"))
        elif " and " in base.lower():
            variations.append(re.sub(r"\s+and\s+", " & ", base, flags=re.IGNORECASE))

        # Remove "The" prefix
        if base.lower().startswith("the "):
            variations.append(base[4:])

        # Acronym if multiple words
        words = base.split()
        if len(words) >= 2:
            acronym = "".join(w[0].upper() for w in words if w[0].isalpha())
            if len(acronym) >= 2:
                variations.append(acronym)

        return variations


class LocationVariator(BaseVariator):
    """Generates variations of location names."""

    def __init__(self):
        super().__init__()
        self.name = "location"

    def get_prompt(self, text: str) -> str:
        return f"""Generate search variations for the location: "{text}"

Include:
- Local language name vs English name
- Common abbreviations
- Historical names
- Administrative divisions

Return as JSON: {{"variations": ["var1", "var2", ...]}}"""

    def fallback_variations(self, text: str) -> List[str]:
        """Generate location variations without AI."""
        variations = [text]

        # Common city name variations (hardcoded)
        city_aliases = {
            "New York": ["NYC", "New York City", "NY"],
            "Los Angeles": ["LA", "L.A."],
            "United Kingdom": ["UK", "U.K.", "Britain", "Great Britain"],
            "United States": ["USA", "US", "U.S.A.", "U.S.", "America"],
            "Saint Petersburg": ["St. Petersburg", "St Petersburg", "Leningrad"],
            "Moscow": ["Moskva"],
            "Beijing": ["Peking"],
            "Mumbai": ["Bombay"],
            "Kolkata": ["Calcutta"],
            "Chennai": ["Madras"],
        }

        for canonical, aliases in city_aliases.items():
            if text.lower() == canonical.lower():
                variations.extend(aliases)
            elif text in aliases or text.lower() in [a.lower() for a in aliases]:
                variations.append(canonical)
                variations.extend([a for a in aliases if a != text])

        return variations


class PhoneVariator(BaseVariator):
    """Generates variations of phone numbers."""

    def __init__(self):
        super().__init__()
        self.name = "phone"

    def get_prompt(self, text: str) -> str:
        return f"""Generate format variations for the phone number: "{text}"

Include various formatting:
- With/without country code
- Different separator styles (dots, dashes, spaces, none)
- With/without parentheses

Return as JSON: {{"variations": ["var1", "var2", ...]}}"""

    def fallback_variations(self, text: str) -> List[str]:
        """Generate phone number format variations."""
        # Extract just digits
        digits = re.sub(r"\D", "", text)
        variations = [text, digits]

        if len(digits) == 10:  # US format
            variations.extend([
                f"({digits[:3]}) {digits[3:6]}-{digits[6:]}",
                f"{digits[:3]}-{digits[3:6]}-{digits[6:]}",
                f"{digits[:3]}.{digits[3:6]}.{digits[6:]}",
                f"{digits[:3]} {digits[3:6]} {digits[6:]}",
                f"+1{digits}",
                f"+1 {digits[:3]} {digits[3:6]} {digits[6:]}",
            ])
        elif len(digits) == 11 and digits.startswith("1"):  # US with country code
            base = digits[1:]
            variations.extend([
                f"({base[:3]}) {base[3:6]}-{base[6:]}",
                f"{base[:3]}-{base[3:6]}-{base[6:]}",
                f"+1 {base[:3]} {base[3:6]} {base[6:]}",
                base,
            ])

        return variations


# =============================================================================
# VARIETY PROMPT - Principle of Useful Variety
# =============================================================================
#
# WISDOM: "Useful Variety" means we balance:
# - LIKELIHOOD (high-probability formats that actually appear in documents)
# - INFINITY (avoiding explosion into thousands of unlikely variations)
#
# The goal is to generate only FUNCTIONALLY DISTINCT formats -
# variations that would actually match different document patterns.
# =============================================================================

VARIETY_PROMPT = r"""
SYSTEM
You are **VarietyEngine**, a search variation strategist.
Your Goal: Generate ONLY variations that are FUNCTIONALLY DISTINCT.

THE PRINCIPLE OF USEFUL VARIETY
────────────────────────────────────────────────────────────────────────────────
We seek the balance between two forces:
1. LIKELIHOOD - High probability formats that appear in real documents
2. INFINITY - Avoiding explosion into thousands of unlikely patterns

For a phone number like "+1 (555) 123-4567":
✓ USEFUL: "+15551234567", "555-123-4567", "5551234567"  (distinct matching patterns)
✗ USELESS: "+1 555  123  4567", "+1-555-123-4567" (cosmetic differences)

ENTROPY LOGIC
────────────────────────────────────────────────────────────────────────────────
- COMMON names (Smith, Jones, Li) → STRICT variations (few, high-precision)
- UNIQUE names (Zuckerberg, Musk) → BROAD variations (more experimental)
- GENERIC companies → STRICT (need context)
- DISTINCTIVE companies → BROAD (can try more patterns)

The rarer the name, the more variations we can afford.
The more common, the stricter we must be.

SPLIT-SEGMENT RULE (for phones)
────────────────────────────────────────────────────────────────────────────────
For international numbers, search BOTH the full number AND:
- Country Code segment: "+36" OR "36"
- Subscriber Tail segment: Last 6-7 digits alone

Documents often contain only partial numbers - the tail is what matches.

INPUT: {input_value}
TYPE: {input_type}
CONTEXT: {context}

OUTPUT:
Return JSON with variations grouped by likelihood:
{{
  "high_likelihood": ["var1", "var2"],  // Format likely in 70%+ documents
  "medium_likelihood": ["var3", "var4"],  // Format likely in 30-70% documents
  "experimental": ["var5"]  // Format might appear in edge cases
}}
"""


class VarietyGenerator:
    """
    Generates variations using the Principle of Useful Variety.

    Balances Likelihood vs Infinity to produce only functionally distinct
    variations that would actually match different document patterns.

    Uses Entropy Logic:
    - Common names → Strict variations (few, high-precision)
    - Unique names → Broad variations (more experimental)

    Hybrid Architecture:
    - Rule-Based Layer: Fast, deterministic (PersonVariator, CompanyVariator, etc.)
    - AI Enhancement Layer: GPT-5-nano for creative, context-aware variations
    """

    def __init__(self, use_ai: bool = True):
        """
        Initialize the VarietyGenerator.

        Args:
            use_ai: Whether to enable GPT-5-nano AI enhancement layer.
                   Set to False for testing or when API is unavailable.
        """
        self.person_variator = PersonVariator()
        self.company_variator = CompanyVariator()
        self.phone_variator = PhoneVariator()

        # AI enhancement layer (lazy-loaded)
        self._use_ai = use_ai
        self._ai_enhancer = None

    @property
    def ai_enhancer(self):
        """Lazy-load AI enhancer on first use."""
        if self._ai_enhancer is None and self._use_ai:
            try:
                from .ai_variations import AIVariationEnhancer
                self._ai_enhancer = AIVariationEnhancer(enabled=True)
            except ImportError:
                self._ai_enhancer = None
        return self._ai_enhancer

    def calculate_name_entropy(
        self,
        name: str,
        jurisdiction: Optional[str] = None
    ) -> str:
        """
        Determine entropy level for a name using frequency-weighted scoring.

        Uses multi-factor scoring:
        - Factor 1 (50%): Surname frequency lookup
        - Factor 2 (20%): Name length
        - Factor 3 (30%): Script markers (non-Latin = more unique)

        Args:
            name: The full name to analyze
            jurisdiction: Optional 2-letter jurisdiction code for context

        Returns: "low" (common), "medium", or "high" (unique)
        """
        parts = name.lower().split()
        surname = parts[-1] if parts else name.lower()

        # Factor 1: Frequency lookup (50% weight)
        freq_score = get_surname_frequency(surname, jurisdiction)

        # Factor 2: Length heuristic (20% weight)
        if len(surname) < 4:
            length_score = 0.20  # Short = low entropy (common)
        elif len(surname) > 10:
            length_score = 0.80  # Long = high entropy (unique)
        else:
            length_score = 0.50  # Medium length

        # Factor 3: Script markers (30% weight)
        if any(ord(c) > 127 for c in surname):
            script_score = 0.75  # Non-ASCII often more unique
        else:
            script_score = 0.35  # ASCII only

        # Combined score (lower = more common, needs strict variations)
        # Invert frequency (high freq = low entropy)
        combined = (
            0.50 * (1.0 - freq_score) +  # Invert: high freq → low entropy
            0.20 * length_score +
            0.30 * script_score
        )

        # Map to entropy level
        if combined < 0.35:
            return "low"   # Common → Strict variations
        elif combined > 0.60:
            return "high"  # Unique → Broad variations
        else:
            return "medium"

    def calculate_company_entropy(self, name: str) -> str:
        """
        Determine entropy level for a company name.

        Returns: "low" (generic), "medium", or "high" (distinctive)
        """
        words = name.lower().split()

        # Check if all words are generic
        generic_count = sum(1 for w in words if w in GENERIC_COMPANY_TERMS)

        if generic_count == len(words):
            return "low"  # All generic → Strict

        if generic_count > len(words) / 2:
            return "medium"

        return "high"  # Distinctive → Broad variations

    def generate_name_variations(
        self,
        name: str,
        entity_type: str = "person",
        max_variations: int = 10,
    ) -> Dict[str, List[str]]:
        """
        Generate name variations using Entropy Logic.

        Args:
            name: The name to generate variations for
            entity_type: "person" or "company"
            max_variations: Maximum total variations to return

        Returns:
            Dict with "high_likelihood", "medium_likelihood", "experimental" lists
        """
        if entity_type == "person":
            entropy = self.calculate_name_entropy(name)
            base_variations = self.person_variator.fallback_variations(name)
        else:
            entropy = self.calculate_company_entropy(name)
            base_variations = self.company_variator.fallback_variations(name)

        # Categorize variations by likelihood based on entropy
        result = {
            "high_likelihood": [],
            "medium_likelihood": [],
            "experimental": [],
        }

        for i, var in enumerate(base_variations):
            if var == name:
                result["high_likelihood"].append(var)
            elif entropy == "low":
                # Common name → Only high-likelihood variations
                if i < 3:
                    result["high_likelihood"].append(var)
                elif i < 5:
                    result["medium_likelihood"].append(var)
                # Skip experimental for common names
            elif entropy == "medium":
                if i < 4:
                    result["high_likelihood"].append(var)
                elif i < 7:
                    result["medium_likelihood"].append(var)
                else:
                    result["experimental"].append(var)
            else:  # high entropy (unique)
                if i < 5:
                    result["high_likelihood"].append(var)
                elif i < 10:
                    result["medium_likelihood"].append(var)
                else:
                    result["experimental"].append(var)

        # Trim to max_variations
        total = sum(len(v) for v in result.values())
        if total > max_variations:
            # Prioritize high_likelihood
            result["experimental"] = result["experimental"][:max(0, max_variations - len(result["high_likelihood"]) - len(result["medium_likelihood"]))]
            result["medium_likelihood"] = result["medium_likelihood"][:max(0, max_variations - len(result["high_likelihood"]))]

        return result

    def generate_phone_variations(
        self,
        phone: str,
        include_split_segments: bool = True,
    ) -> Dict[str, List[str]]:
        """
        Generate phone variations using Split-Segment Rule.

        For international numbers, also searches:
        - Country code segment alone
        - Subscriber tail (last 6-7 digits) alone

        Args:
            phone: The phone number to generate variations for
            include_split_segments: Whether to include CC and tail segments

        Returns:
            Dict with "high_likelihood", "medium_likelihood", "experimental" lists
        """
        # Get base variations
        base_variations = self.phone_variator.fallback_variations(phone)
        digits = re.sub(r"\D", "", phone)

        result = {
            "high_likelihood": [],
            "medium_likelihood": [],
            "experimental": [],
        }

        # Categorize base variations
        for var in base_variations:
            var_digits = re.sub(r"\D", "", var)

            # Full number with formatting = high likelihood
            if len(var_digits) >= 10:
                result["high_likelihood"].append(var)
            else:
                result["medium_likelihood"].append(var)

        # Split-Segment Rule for international numbers
        if include_split_segments and len(digits) > 10:
            # Extract country code (assume 1-3 digits at start)
            if digits.startswith("1"):
                cc = "+1"
                subscriber = digits[1:]
            elif len(digits) > 11:
                # Likely 2-3 digit country code
                cc = f"+{digits[:2]}"
                subscriber = digits[2:]
            else:
                cc = None
                subscriber = digits[-7:]  # Just use tail

            # Add country code segment
            if cc:
                result["experimental"].append(cc)

            # Add subscriber tail (last 6-7 digits)
            tail6 = digits[-6:]
            tail7 = digits[-7:]

            result["medium_likelihood"].append(tail7)
            result["experimental"].append(tail6)

            # Add formatted tail
            if len(tail7) == 7:
                result["experimental"].append(f"{tail7[:3]}-{tail7[3:]}")

        return result

    def generate_all_variations(
        self,
        value: str,
        value_type: str,
        max_variations: int = 15,
    ) -> Dict[str, List[str]]:
        """
        Generate variations for any value type (sync, rule-based only).

        Args:
            value: The value to generate variations for
            value_type: "person", "company", "phone", "email", "domain"
            max_variations: Maximum variations to return

        Returns:
            Dict with variations grouped by likelihood
        """
        if value_type in ("person", "individual"):
            return self.generate_name_variations(value, "person", max_variations)
        elif value_type in ("company", "organization"):
            return self.generate_name_variations(value, "company", max_variations)
        elif value_type == "phone":
            return self.generate_phone_variations(value)
        else:
            # Default: return as-is
            return {
                "high_likelihood": [value],
                "medium_likelihood": [],
                "experimental": [],
            }

    async def generate_all_variations_async(
        self,
        value: str,
        value_type: str,
        max_variations: int = 15,
        context: Optional[str] = None,
    ) -> Dict[str, List[str]]:
        """
        Generate variations with AI enhancement (async).

        Hybrid approach:
        1. Rule-based layer (fast, deterministic)
        2. AI enhancement layer (GPT-5-nano, creative)

        Args:
            value: The value to generate variations for
            value_type: "person", "company", "phone", "email", "domain"
            max_variations: Maximum variations to return
            context: Optional context for AI (e.g., "Hungarian investigation")

        Returns:
            Dict with variations grouped by likelihood, including AI-generated
        """
        # Step 1: Get rule-based variations
        result = self.generate_all_variations(value, value_type, max_variations)

        # Step 2: AI enhancement (if enabled)
        if self.ai_enhancer:
            try:
                # Flatten existing variations for AI context
                existing = (
                    result["high_likelihood"]
                    + result["medium_likelihood"]
                    + result["experimental"]
                )

                # Get AI-generated variations
                ai_variations = await self.ai_enhancer.enhance_generic(
                    value, value_type, existing, context
                )

                # Add AI variations to experimental category
                # (they're creative, may need verification)
                if ai_variations:
                    result["experimental"].extend(ai_variations)

                    # Add flag to indicate AI was used
                    result["ai_enhanced"] = True
                    result["ai_variations_count"] = len(ai_variations)

            except Exception as e:
                # Fail silently - AI enhancement is optional
                import logging
                logging.getLogger(__name__).warning(f"AI variation enhancement failed: {e}")

        # Trim to max_variations
        total = sum(len(v) for v in [result["high_likelihood"], result["medium_likelihood"], result["experimental"]])
        if total > max_variations:
            # Prioritize high_likelihood, then medium, then experimental
            experimental_limit = max(0, max_variations - len(result["high_likelihood"]) - len(result["medium_likelihood"]))
            result["experimental"] = result["experimental"][:experimental_limit]

        return result


# =============================================================================
# ENTITY TRIANGULATION - Slot-Filling Strategy
# =============================================================================
#
# WISDOM: "Take whatever is unique enough... like the surname alone."
#
# The Slot-Filling Protocol bypasses "namesake noise" by triangulating
# a stable ANCHOR (Surname) with specific ATTRIBUTE SLOTS.
#
# PMI OPTIMIZATION: P("Surname" + "AssociateSurname") is statistically
# rarer (higher signal) than P("FullName") alone.
#
# FAIL-SOFT CASCADE: Don't just try one "perfect" query - cascade from
# specific (Surname + Associate) to broad (Surname + Industry).
# =============================================================================

@dataclass
class EntityProfile:
    """
    Structure for the 'Slots' we have learned about an entity.

    Each filled slot increases triangulation precision.
    The more slots filled, the more specific queries we can generate.
    """
    full_name: str
    entity_type: str = "person"  # person, company, domain, etc.

    # NETWORK SLOTS - High confidence triangulation
    associates: List[str] = field(default_factory=list)  # Known connections

    # CORPORATE SLOTS - Company affiliations
    companies: List[str] = field(default_factory=list)

    # INDUSTRY/SECTOR SLOTS - Contextual narrowing
    industry: List[str] = field(default_factory=list)

    # VITAL SLOTS - Hard identifiers
    dob: Optional[str] = None          # YYYY or YYYY-MM-DD
    identifiers: Dict[str, str] = field(default_factory=dict)  # {oib: "123", ssn: "456"}

    # GEO SLOTS - Location triangulation
    residency_code: Optional[str] = None   # TLD: fr, de, ch
    jurisdictions: List[str] = field(default_factory=list)  # Countries of operation
    addresses: List[str] = field(default_factory=list)

    # TEMPORAL SLOTS - Time anchors
    active_years: List[int] = field(default_factory=list)  # Years of known activity

    # ROLE SLOTS - Position-based triangulation
    roles: List[str] = field(default_factory=list)  # director, CEO, shareholder

    # SOURCE SLOTS - Where they've been found
    known_sources: List[str] = field(default_factory=list)  # domains, registries


@dataclass
class QueryResult:
    """A single query with metadata for the triangulation cascade."""
    q: str                    # The actual query string
    tier: str = "T3"          # T1 (best) to T4 (broadest)
    src: str = "slot_filling" # Source strategy
    est_hits: str = "medium"  # Expected result volume
    est_noise: int = 10       # Noise score (0-100)
    quality_score: float = 0.5  # Query quality score (0-1)
    slot_used: str = ""       # Which slot was used


# Common surnames that require additional anchoring
# =============================================================================
# SURNAME FREQUENCY DATA (Hybrid Approach)
# =============================================================================
#
# Top 200+ surnames across major jurisdictions with frequency tiers:
#   Tier 1 (0.85+): Very common - need strict variations
#   Tier 2 (0.70-0.85): Common - moderate variations
#   Tier 3 (0.50-0.70): Less common - broad variations
#
# For unlisted surnames, use heuristic fallback (length, script detection)
# =============================================================================

SURNAME_FREQUENCY = {
    # USA/Anglo (Top 50)
    "us": {
        "smith": 0.95, "johnson": 0.93, "williams": 0.92, "brown": 0.91, "jones": 0.90,
        "garcia": 0.89, "miller": 0.88, "davis": 0.87, "rodriguez": 0.86, "martinez": 0.85,
        "hernandez": 0.84, "lopez": 0.83, "gonzalez": 0.82, "wilson": 0.81, "anderson": 0.80,
        "thomas": 0.79, "taylor": 0.78, "moore": 0.77, "jackson": 0.76, "martin": 0.75,
        "lee": 0.74, "perez": 0.73, "thompson": 0.72, "white": 0.71, "harris": 0.70,
        "sanchez": 0.69, "clark": 0.68, "ramirez": 0.67, "lewis": 0.66, "robinson": 0.65,
        "walker": 0.64, "young": 0.63, "allen": 0.62, "king": 0.61, "wright": 0.60,
        "scott": 0.59, "torres": 0.58, "nguyen": 0.57, "hill": 0.56, "flores": 0.55,
        "green": 0.54, "adams": 0.53, "nelson": 0.52, "baker": 0.51, "hall": 0.50,
        "rivera": 0.49, "campbell": 0.48, "mitchell": 0.47, "carter": 0.46, "roberts": 0.45,
    },
    # UK (Top 40)
    "uk": {
        "smith": 0.95, "jones": 0.93, "taylor": 0.91, "brown": 0.90, "williams": 0.89,
        "wilson": 0.88, "johnson": 0.87, "davies": 0.86, "robinson": 0.85, "wright": 0.84,
        "thompson": 0.83, "evans": 0.82, "walker": 0.81, "white": 0.80, "roberts": 0.79,
        "green": 0.78, "hall": 0.77, "wood": 0.76, "jackson": 0.75, "clarke": 0.74,
        "patel": 0.73, "khan": 0.72, "lewis": 0.71, "james": 0.70, "phillips": 0.69,
        "mason": 0.68, "mitchell": 0.67, "rose": 0.66, "davis": 0.65, "cox": 0.64,
        "baker": 0.63, "harris": 0.62, "ward": 0.61, "king": 0.60, "turner": 0.59,
        "hill": 0.58, "cooper": 0.57, "morris": 0.56, "moore": 0.55, "clark": 0.54,
    },
    # German (Top 40)
    "de": {
        "mueller": 0.95, "muller": 0.95, "schmidt": 0.93, "schneider": 0.91, "fischer": 0.90,
        "weber": 0.89, "meyer": 0.88, "wagner": 0.87, "becker": 0.86, "schulz": 0.85,
        "hoffmann": 0.84, "schaefer": 0.83, "koch": 0.82, "bauer": 0.81, "richter": 0.80,
        "klein": 0.79, "wolf": 0.78, "schroeder": 0.77, "neumann": 0.76, "schwarz": 0.75,
        "zimmermann": 0.74, "braun": 0.73, "krueger": 0.72, "hofmann": 0.71, "hartmann": 0.70,
        "lange": 0.69, "schmitt": 0.68, "werner": 0.67, "schmitz": 0.66, "krause": 0.65,
        "meier": 0.64, "lehmann": 0.63, "schmid": 0.62, "schulze": 0.61, "maier": 0.60,
        "koehler": 0.59, "herrmann": 0.58, "koenig": 0.57, "walter": 0.56, "mayer": 0.55,
    },
    # Hungarian (Top 30)
    "hu": {
        "nagy": 0.95, "kovacs": 0.93, "kovács": 0.93, "toth": 0.91, "tóth": 0.91,
        "szabo": 0.90, "szabó": 0.90, "horvath": 0.89, "horváth": 0.89, "kiss": 0.88,
        "varga": 0.87, "molnar": 0.86, "molnár": 0.86, "nemeth": 0.85, "németh": 0.85,
        "farkas": 0.84, "balogh": 0.83, "papp": 0.82, "lakatos": 0.81, "takacs": 0.80,
        "takács": 0.80, "juhasz": 0.79, "juhász": 0.79, "olah": 0.78, "oláh": 0.78,
        "simon": 0.77, "fekete": 0.76, "racz": 0.75, "rácz": 0.75, "vincze": 0.74,
    },
    # Slavic/Balkan (Top 40)
    "hr": {
        "horvat": 0.95, "kovac": 0.93, "kovač": 0.93, "babic": 0.91, "babić": 0.91,
        "maric": 0.90, "marić": 0.90, "juric": 0.89, "jurić": 0.89, "novak": 0.88,
        "tomic": 0.87, "tomić": 0.87, "matic": 0.86, "matić": 0.86, "pavic": 0.85,
        "pavić": 0.85, "pavlovic": 0.84, "pavlović": 0.84, "knezevic": 0.83,
        "knežević": 0.83, "vidovic": 0.82, "vidović": 0.82, "petrovic": 0.81,
        "vuković": 0.80, "vukovic": 0.80, "ivanovic": 0.79, "ivanović": 0.79,
    },
    "rs": {
        "jovanovic": 0.95, "jovanović": 0.95, "petrovic": 0.93, "petrović": 0.93,
        "nikolic": 0.91, "nikolić": 0.91, "markovic": 0.90, "marković": 0.90,
        "djordjevic": 0.89, "đorđević": 0.89, "stojanovic": 0.88, "stojanović": 0.88,
        "ilic": 0.87, "ilić": 0.87, "stankovic": 0.86, "stanković": 0.86,
        "pavlovic": 0.85, "pavlović": 0.85, "milosevic": 0.84, "milošević": 0.84,
        "popovic": 0.83, "popović": 0.83, "mitrovic": 0.82, "mitrović": 0.82,
    },
    # Chinese (Romanized - Top 20)
    "cn": {
        "wang": 0.95, "li": 0.94, "zhang": 0.93, "liu": 0.92, "chen": 0.91,
        "yang": 0.90, "huang": 0.89, "zhao": 0.88, "wu": 0.87, "zhou": 0.86,
        "xu": 0.85, "sun": 0.84, "ma": 0.83, "zhu": 0.82, "hu": 0.81,
        "guo": 0.80, "he": 0.79, "lin": 0.78, "luo": 0.77, "gao": 0.76,
    },
    # Korean (Romanized - Top 15)
    "kr": {
        "kim": 0.96, "lee": 0.94, "park": 0.92, "choi": 0.90, "jung": 0.88,
        "kang": 0.86, "cho": 0.85, "yoon": 0.84, "jang": 0.83, "lim": 0.82,
        "han": 0.81, "shin": 0.80, "oh": 0.79, "seo": 0.78, "kwon": 0.77,
    },
    # Japanese (Romanized - Top 20)
    "jp": {
        "sato": 0.95, "suzuki": 0.93, "takahashi": 0.91, "tanaka": 0.90, "watanabe": 0.89,
        "ito": 0.88, "yamamoto": 0.87, "nakamura": 0.86, "kobayashi": 0.85, "kato": 0.84,
        "yoshida": 0.83, "yamada": 0.82, "sasaki": 0.81, "yamaguchi": 0.80, "saito": 0.79,
        "matsumoto": 0.78, "inoue": 0.77, "kimura": 0.76, "hayashi": 0.75, "shimizu": 0.74,
    },
    # Indian (Top 25)
    "in": {
        "sharma": 0.95, "singh": 0.94, "kumar": 0.93, "patel": 0.92, "gupta": 0.91,
        "das": 0.90, "reddy": 0.89, "khan": 0.88, "rao": 0.87, "patil": 0.86,
        "jain": 0.85, "mehta": 0.84, "shah": 0.83, "verma": 0.82, "mishra": 0.81,
        "agarwal": 0.80, "nair": 0.79, "joshi": 0.78, "iyer": 0.77, "menon": 0.76,
        "pillai": 0.75, "desai": 0.74, "choudhury": 0.73, "pandey": 0.72, "kaur": 0.71,
    },
    # Arabic/Persian (Romanized - Top 20)
    "ar": {
        "ahmed": 0.95, "mohamed": 0.94, "mohammed": 0.94, "ali": 0.93, "hassan": 0.92,
        "hussein": 0.91, "khan": 0.90, "omar": 0.89, "abdel": 0.88, "abdul": 0.87,
        "ibrahim": 0.86, "saeed": 0.85, "yousef": 0.84, "saleh": 0.83, "mahmoud": 0.82,
        "khalil": 0.81, "hasan": 0.80, "nasser": 0.79, "karim": 0.78, "amin": 0.77,
    },
    # Russian (Romanized - Top 20)
    "ru": {
        "ivanov": 0.95, "smirnov": 0.93, "kuznetsov": 0.91, "popov": 0.90, "vasiliev": 0.89,
        "petrov": 0.88, "sokolov": 0.87, "mikhailov": 0.86, "novikov": 0.85, "fedorov": 0.84,
        "morozov": 0.83, "volkov": 0.82, "alexeev": 0.81, "lebedev": 0.80, "semenov": 0.79,
        "egorov": 0.78, "pavlov": 0.77, "kozlov": 0.76, "stepanov": 0.75, "nikolaev": 0.74,
    },
    # Spanish (Top 25)
    "es": {
        "garcia": 0.95, "fernandez": 0.93, "gonzalez": 0.92, "rodriguez": 0.91, "lopez": 0.90,
        "martinez": 0.89, "sanchez": 0.88, "perez": 0.87, "gomez": 0.86, "martin": 0.85,
        "jimenez": 0.84, "ruiz": 0.83, "hernandez": 0.82, "diaz": 0.81, "moreno": 0.80,
        "alvarez": 0.79, "muñoz": 0.78, "romero": 0.77, "alonso": 0.76, "gutierrez": 0.75,
        "navarro": 0.74, "torres": 0.73, "dominguez": 0.72, "vazquez": 0.71, "ramos": 0.70,
    },
    # Italian (Top 20)
    "it": {
        "rossi": 0.95, "russo": 0.93, "ferrari": 0.91, "esposito": 0.90, "bianchi": 0.89,
        "romano": 0.88, "colombo": 0.87, "ricci": 0.86, "marino": 0.85, "greco": 0.84,
        "bruno": 0.83, "gallo": 0.82, "conti": 0.81, "costa": 0.80, "mancini": 0.79,
        "costa": 0.78, "giordano": 0.77, "rizzo": 0.76, "lombardi": 0.75, "moretti": 0.74,
    },
    # French (Top 20)
    "fr": {
        "martin": 0.95, "bernard": 0.93, "dubois": 0.91, "thomas": 0.90, "robert": 0.89,
        "richard": 0.88, "petit": 0.87, "durand": 0.86, "leroy": 0.85, "moreau": 0.84,
        "simon": 0.83, "laurent": 0.82, "lefebvre": 0.81, "michel": 0.80, "garcia": 0.79,
        "david": 0.78, "bertrand": 0.77, "roux": 0.76, "vincent": 0.75, "fournier": 0.74,
    },
}

# Flattened set of all common surnames for quick lookup
COMMON_SURNAMES = set()
for jurisdiction_surnames in SURNAME_FREQUENCY.values():
    COMMON_SURNAMES.update(jurisdiction_surnames.keys())


def get_surname_frequency(surname: str, jurisdiction: Optional[str] = None) -> float:
    """
    Get surname frequency score.

    Args:
        surname: The surname to look up
        jurisdiction: Optional 2-letter jurisdiction code (us, uk, de, etc.)

    Returns:
        Frequency score 0.0-1.0 (higher = more common)
        Returns 0.5 for unknown surnames (medium entropy)
    """
    surname_lower = surname.lower()

    if jurisdiction and jurisdiction.lower() in SURNAME_FREQUENCY:
        # Check jurisdiction-specific frequency
        freq = SURNAME_FREQUENCY[jurisdiction.lower()].get(surname_lower)
        if freq is not None:
            return freq

    # Check all jurisdictions
    for jur_surnames in SURNAME_FREQUENCY.values():
        if surname_lower in jur_surnames:
            return jur_surnames[surname_lower]

    # Heuristic fallback for unknown surnames
    # Short = likely common, Long = likely unique, Non-ASCII = likely unique
    if len(surname) < 4:
        return 0.70  # Short surnames tend to be common
    elif len(surname) > 12:
        return 0.30  # Long surnames tend to be unique
    elif any(ord(c) > 127 for c in surname):
        return 0.35  # Non-ASCII often more unique
    else:
        return 0.50  # Unknown medium-length surname


# Generic company terms that need additional context
GENERIC_COMPANY_TERMS = {
    'global', 'international', 'group', 'holdings', 'capital', 'partners',
    'ventures', 'investments', 'consulting', 'services', 'solutions', 'logistics',
    'trading', 'management', 'enterprises', 'industries', 'technologies', 'systems',
    'network', 'platform', 'institute', 'foundation', 'associates', 'advisors',
    'resources', 'development', 'properties', 'realty', 'financial', 'media',
}


class EntityTriangulator(QueryGenerationStrategy):
    """
    Implements the 'Surname Anchor + Slot Filling' strategy.

    WISDOM: "Take whatever is unique enough... like the surname alone."

    The triangulator generates tiered queries:
    - T1: Surname + Associate (Network Edge) - Highest precision
    - T2: Surname + Company (Corporate Edge) - High precision
    - T3: Surname + Year + Role (Registry Edge) - Medium precision
    - T4: site:TLD + Surname + Industry (Sovereign Edge) - Broader

    Fail-Soft Cascade ensures we always have fallback queries
    even when slots are partially filled.

    Implements QueryGenerationStrategy for unified orchestration.
    """

    def __init__(self, profile: EntityProfile):
        self.profile = profile
        self.anchor = self._derive_anchor(profile.full_name, profile.entity_type)
        self.anchor_strength = self._calculate_anchor_strength()
        self._economist = QueryEconomist()

    def _kw(self, term: str, kind: str) -> TokenCandidate:
        return TokenCandidate(term=term, kind=kind)

    def _compose_keywords(self, candidates: List[TokenCandidate], budget: Optional[int] = None) -> str:
        """
        Compose an AND query under an artificial keyword budget.
        Anchor is always included; budget adapts to anchor strength unless provided.
        """
        eff_budget = budget if budget is not None else self._economist.recommended_budget(self.anchor_strength)
        q, _ledger = self._economist.compose_and_query(
            candidates,
            budget=eff_budget,
            anchor_term=self.anchor,
        )
        return q

    # =========================================================================
    # QueryGenerationStrategy Interface Implementation
    # =========================================================================

    def generate(self, context: QueryContext) -> List[QueryResult]:
        """
        Generate queries based on context (Strategy interface).

        Delegates to generate_slot_queries() for actual query generation.
        Applies K-U quadrant filtering if present in context.
        """
        queries = self.generate_slot_queries()

        # Apply K-U quadrant filtering if present
        if context and context.ku_quadrant:
            queries = self._apply_ku_filter(queries, context.ku_quadrant)

        return queries

    def get_tier_distribution(self) -> Dict[str, int]:
        """
        Return expected query count per tier.

        Based on filled slots and anchor strength.
        """
        distribution = {"T1": 0, "T2": 0, "T3": 0, "T4": 0, "T5": 0}

        # T1: Associates
        distribution["T1"] = len(self.profile.associates)

        # T2: Companies
        distribution["T2"] = len(self.profile.companies)

        # T3: Temporal (DOB/years + roles)
        if self.profile.dob:
            distribution["T3"] += 2 if self.profile.roles else 1
        distribution["T3"] += min(len(self.profile.active_years), 2)

        # T4: Sovereign
        distribution["T4"] = 1 if self.profile.residency_code else 0
        distribution["T4"] += min(len(self.profile.jurisdictions), 2)

        # T5: Industry
        distribution["T5"] = min(len(self.profile.industry), 3)

        return distribution

    def _apply_ku_filter(
        self,
        queries: List[QueryResult],
        ku_quadrant: KUQuadrant
    ) -> List[QueryResult]:
        """
        Filter/reorder queries based on K-U quadrant.

        DISCOVER: Prefer T4-T5, broad queries
        VERIFY: Prefer T1-T2, precise queries
        TRACE: Prefer T2-T3, medium precision
        EXTRACT: All queries, balanced
        """
        if ku_quadrant == KUQuadrant.DISCOVER:
            # Prefer broader queries (T4-T5)
            priority = {"T5": 5, "T4": 4, "T3": 3, "T2": 2, "T1": 1}
        elif ku_quadrant == KUQuadrant.VERIFY:
            # Prefer precise queries (T1-T2)
            priority = {"T1": 5, "T2": 4, "T3": 3, "T4": 2, "T5": 1}
        elif ku_quadrant == KUQuadrant.TRACE:
            # Prefer medium precision (T2-T3)
            priority = {"T2": 5, "T3": 5, "T1": 4, "T4": 3, "T5": 2}
        else:  # EXTRACT or default
            # Balanced
            return queries

        # Sort by K-U priority then quality score
        return sorted(
            queries,
            key=lambda q: (priority.get(q.tier, 0), q.quality_score),
            reverse=True
        )

    # =========================================================================
    # Original Triangulator Methods
    # =========================================================================

    def _derive_anchor(self, name: str, entity_type: str) -> str:
        """
        Derive the anchor term from the entity name.

        WISDOM: Avoid name variations by isolating the surname.
        Exception: If surname is common (Smith, Jones), use FULL NAME as anchor.
                   (Initial+surname creates ugly anchors and can drop recall across formats.)

        For companies: Use distinctive core name, strip suffixes.
        """
        if entity_type == "company":
            return self._derive_company_anchor(name)

        # Person name handling
        parts = name.strip().split()
        if len(parts) < 2:
            # Single name - use as-is but with quotes
            return f'"{name}"'

        surname = parts[-1]
        first_name = parts[0]

        # Check if surname needs additional anchoring
        if len(surname) < 3 or surname.lower() in COMMON_SURNAMES:
            # Common surname - use full name to avoid lossy/ugly anchors like "J. Smith"
            return f'"{name}"'

        # Unique enough - return quoted surname only
        return f'"{surname}"'

    def _derive_company_anchor(self, name: str) -> str:
        """Derive anchor for company names."""
        # Strip common suffixes
        suffixes = [
            'inc', 'inc.', 'incorporated', 'corp', 'corp.', 'corporation',
            'ltd', 'ltd.', 'limited', 'llc', 'l.l.c.', 'llp', 'l.l.p.',
            'plc', 'p.l.c.', 'gmbh', 'ag', 'sa', 's.a.', 'bv', 'b.v.',
            'nv', 'n.v.', 'pty', 'pty ltd', 'co', 'co.', 'company',
            '&', 'and', 'the'
        ]

        base = name
        for suffix in sorted(suffixes, key=len, reverse=True):
            pattern = rf'\s*{re.escape(suffix)}\s*$'
            base = re.sub(pattern, '', base, flags=re.IGNORECASE).strip()

        # Remove leading "The"
        if base.lower().startswith('the '):
            base = base[4:]

        # Check if too generic
        words = base.lower().split()
        if all(w in GENERIC_COMPANY_TERMS for w in words):
            # All generic - return full name quoted
            return f'"{name}"'

        return f'"{base}"'

    def _calculate_anchor_strength(self) -> int:
        """
        Rate the anchor strength (1-5).

        5 = Unique surname/name, solo capable
        4 = Uncommon, good standalone
        3 = Moderate, benefits from slot
        2 = Common, needs slot
        1 = Very common/short, mandatory slot required
        """
        anchor_clean = self.anchor.strip('"').lower()
        words = anchor_clean.split()

        # Check for common surname
        if any(w in COMMON_SURNAMES for w in words):
            return 2 if len(words) > 1 else 1

        # Check for short names
        if len(anchor_clean) < 4:
            return 1

        # Check for generic company terms
        if any(w in GENERIC_COMPANY_TERMS for w in words):
            return 2

        # Multi-word with initial = moderate
        if '.' in self.anchor:
            return 3

        # Long unique name
        if len(anchor_clean) > 8:
            return 5

        return 4

    def generate_slot_queries(self) -> List[QueryResult]:
        """
        Generate tiered queries using all available slots.

        Returns queries ordered by expected precision (T1 first).
        """
        queries = []

        # T1: NETWORK SLOT (Surname + Associate) - Highest precision
        queries.extend(self._generate_network_queries())

        # T2: CORPORATE SLOT (Surname + Company)
        queries.extend(self._generate_corporate_queries())

        # T3: VITAL SLOT (Surname + Year/Role)
        queries.extend(self._generate_vital_queries())

        # T4: SOVEREIGN SLOT (site:TLD + Surname)
        queries.extend(self._generate_sovereign_queries())

        # T5: INDUSTRY SLOT (Surname + Industry terms)
        queries.extend(self._generate_industry_queries())

        # Sort by quality score descending
        queries.sort(key=lambda q: q.quality_score, reverse=True)

        return queries

    def _generate_network_queries(self) -> List[QueryResult]:
        """
        T1: Network Edge - Surname + Associate Surname

        WISDOM: P("Surname" + "AssociateSurname") is statistically
        rarer than P("FullName") - higher signal.
        """
        queries = []

        for assoc in self.profile.associates:
            # Extract associate surname
            assoc_parts = assoc.strip().split()
            assoc_surname = assoc_parts[-1] if assoc_parts else assoc

            # Skip if same surname (family member - different query type)
            if assoc_surname.lower() == self.anchor.strip('"').split()[-1].lower():
                continue

            queries.append(QueryResult(
                q=self._compose_keywords([
                    self._kw(self.anchor, "anchor"),
                    self._kw(f'"{assoc_surname}"', "associate"),
                ]),
                tier="T1",
                src="slot_network",
                est_hits="medium" if self.anchor_strength >= 3 else "high",
                est_noise=5,
                quality_score=0.95,
                slot_used="associate"
            ))

        return queries

    def _generate_corporate_queries(self) -> List[QueryResult]:
        """
        T2: Corporate Edge - Surname + Company

        WISDOM: If company is generic, add industry context.
        """
        queries = []

        for company in self.profile.companies:
            company_lower = company.lower()

            # Check if company name is generic
            is_generic = (
                len(company.split()) < 2 or
                any(term in company_lower for term in GENERIC_COMPANY_TERMS)
            )

            if is_generic and self.profile.industry:
                # Add industry context for generic company names
                industry_term = self.profile.industry[0]
                queries.append(QueryResult(
                    q=self._compose_keywords([
                        self._kw(self.anchor, "anchor"),
                        self._kw(f'"{company}"', "company"),
                        self._kw(f'"{industry_term}"', "industry"),
                    ]),
                    tier="T2",
                    src="slot_corporate_contextualized",
                    est_hits="low",
                    est_noise=8,
                    quality_score=0.88,
                    slot_used="company+industry"
                ))
            else:
                # Quote specific company names
                queries.append(QueryResult(
                    q=self._compose_keywords([
                        self._kw(self.anchor, "anchor"),
                        self._kw(f'"{company}"', "company"),
                    ]),
                    tier="T2",
                    src="slot_corporate",
                    est_hits="medium",
                    est_noise=10,
                    quality_score=0.90,
                    slot_used="company"
                ))

        return queries

    def _generate_vital_queries(self) -> List[QueryResult]:
        """
        T3: Vital/Registry Edge - Surname + Year + Role

        WISDOM: "in case of directorship showing up like that"
        Date + Role patterns are highly discriminating.
        """
        queries = []

        # DOB year-based queries
        if self.profile.dob:
            year_match = re.search(r'\d{4}', self.profile.dob)
            if year_match:
                year = year_match.group(0)

                # With role
                if self.profile.roles:
                    role_or = " OR ".join(f'"{r}"' for r in self.profile.roles[:3])
                    queries.append(QueryResult(
                        q=self._compose_keywords([
                            self._kw(self.anchor, "anchor"),
                            self._kw(f'"{year}"', "temporal"),
                            self._kw(f'({role_or})', "role"),
                        ]),
                        tier="T3",
                        src="slot_vital_role",
                        est_hits="low",
                        est_noise=2,
                        quality_score=0.98,
                        slot_used="dob+role"
                    ))

                # Just year (for corporate filings)
                queries.append(QueryResult(
                    q=self._compose_keywords([
                        self._kw(self.anchor, "anchor"),
                        self._kw(f'"{year}"', "temporal"),
                        self._kw('(director OR appointed OR board OR officer)', "role"),
                    ]),
                    tier="T3",
                    src="slot_vital_directorship",
                    est_hits="low",
                    est_noise=3,
                    quality_score=0.95,
                    slot_used="dob"
                ))

        # Active years (without DOB)
        for year in self.profile.active_years[:2]:
            if self.profile.roles:
                role = self.profile.roles[0]
                queries.append(QueryResult(
                    q=self._compose_keywords([
                        self._kw(self.anchor, "anchor"),
                        self._kw(f'"{year}"', "temporal"),
                        self._kw(f'"{role}"', "role"),
                    ]),
                    tier="T3",
                    src="slot_active_year",
                    est_hits="medium",
                    est_noise=8,
                    quality_score=0.85,
                    slot_used="year+role"
                ))

        # Hard identifier queries (most precise)
        for id_type, id_value in self.profile.identifiers.items():
            queries.append(QueryResult(
                q=self._compose_keywords([
                    self._kw(self.anchor, "anchor"),
                    self._kw(f'"{id_value}"', "identifier"),
                ], budget=2),
                tier="T1",  # Identifiers are T1 precision
                src="slot_identifier",
                est_hits="very_low",
                est_noise=1,
                quality_score=0.99,
                slot_used=f"identifier:{id_type}"
            ))

        return queries

    def _generate_sovereign_queries(self) -> List[QueryResult]:
        """
        T4: Sovereign Edge - site:TLD + Surname

        WISDOM: "if he lives abroad, then with the country domain"
        """
        queries = []

        # Primary residency
        if self.profile.residency_code:
            tld = self.profile.residency_code.strip('.')

            # With industry/profession context
            if self.profile.industry:
                term = self.profile.industry[0]
                queries.append(QueryResult(
                    q=f'site:.{tld} ' + self._compose_keywords([
                        self._kw(self.anchor, "anchor"),
                        self._kw(f'"{term}"', "industry"),
                    ]),
                    tier="T4",
                    src="slot_sovereign_industry",
                    est_hits="medium",
                    est_noise=15,
                    quality_score=0.82,
                    slot_used="residency+industry"
                ))

            # Basic sovereign query
            queries.append(QueryResult(
                q=f'site:.{tld} {self.anchor}',
                tier="T4",
                src="slot_sovereign",
                est_hits="high" if self.anchor_strength < 3 else "medium",
                est_noise=20,
                quality_score=0.75,
                slot_used="residency"
            ))

        # Other jurisdictions
        for jurisdiction in self.profile.jurisdictions[:2]:
            # Map country to TLD if needed
            tld = self._country_to_tld(jurisdiction)
            if tld and tld != self.profile.residency_code:
                queries.append(QueryResult(
                    q=f'site:.{tld} {self.anchor}',
                    tier="T4",
                    src="slot_jurisdiction",
                    est_hits="medium",
                    est_noise=18,
                    quality_score=0.78,
                    slot_used=f"jurisdiction:{jurisdiction}"
                ))

        return queries

    def _generate_industry_queries(self) -> List[QueryResult]:
        """
        T5: Industry/Context Edge - Surname + Industry terms

        Broadest queries, used when other slots are empty.
        """
        queries = []

        for industry in self.profile.industry[:3]:
            # Avoid overly broad queries
            if self.anchor_strength < 3:
                # Need at least 2 context terms for weak anchors
                if len(self.profile.industry) > 1:
                    industry2 = self.profile.industry[1] if len(self.profile.industry) > 1 else ""
                    queries.append(QueryResult(
                        q=self._compose_keywords([
                            self._kw(self.anchor, "anchor"),
                            self._kw(f'"{industry}"', "industry"),
                            self._kw(f'"{industry2}"', "industry"),
                        ]),
                        tier="T5",
                        src="slot_industry_narrow",
                        est_hits="medium",
                        est_noise=25,
                        quality_score=0.70,
                        slot_used="industry_x2"
                    ))
            else:
                queries.append(QueryResult(
                    q=self._compose_keywords([
                        self._kw(self.anchor, "anchor"),
                        self._kw(f'"{industry}"', "industry"),
                    ], budget=2),
                    tier="T5",
                    src="slot_industry",
                    est_hits="high",
                    est_noise=30,
                    quality_score=0.65,
                    slot_used="industry"
                ))

        return queries

    def _country_to_tld(self, country: str) -> Optional[str]:
        """Map country name to TLD."""
        country_tld_map = {
            'france': 'fr', 'germany': 'de', 'united kingdom': 'uk', 'uk': 'uk',
            'switzerland': 'ch', 'austria': 'at', 'netherlands': 'nl', 'belgium': 'be',
            'italy': 'it', 'spain': 'es', 'portugal': 'pt', 'poland': 'pl',
            'czech republic': 'cz', 'czechia': 'cz', 'hungary': 'hu', 'romania': 'ro',
            'croatia': 'hr', 'slovenia': 'si', 'serbia': 'rs', 'bulgaria': 'bg',
            'greece': 'gr', 'turkey': 'tr', 'russia': 'ru', 'ukraine': 'ua',
            'united states': 'us', 'usa': 'us', 'canada': 'ca', 'mexico': 'mx',
            'brazil': 'br', 'argentina': 'ar', 'australia': 'au', 'new zealand': 'nz',
            'japan': 'jp', 'china': 'cn', 'south korea': 'kr', 'india': 'in',
            'singapore': 'sg', 'hong kong': 'hk', 'uae': 'ae', 'israel': 'il',
        }
        return country_tld_map.get(country.lower())

    def get_minimum_viable_queries(self) -> List[QueryResult]:
        """
        Get the minimum set of queries that cover all filled slots.

        PMI Optimization: Find the "Longest Minimum" - shortest query
        with highest discriminating power.
        """
        all_queries = self.generate_slot_queries()

        if not all_queries:
            # Fallback to basic anchor query
            return [QueryResult(
                q=self.anchor,
                tier="T5",
                src="fallback_anchor_only",
                est_hits="very_high",
                est_noise=50 if self.anchor_strength < 3 else 30,
                quality_score=0.3 + (self.anchor_strength * 0.1),
                slot_used="none"
            )]

        # Return top queries from each tier (max 10-15 total)
        seen_tiers = set()
        selected = []

        for q in all_queries:
            tier_count = sum(1 for s in selected if s.tier == q.tier)
            if tier_count < 4:  # Max 4 per tier
                selected.append(q)
                seen_tiers.add(q.tier)

            if len(selected) >= 15:
                break

        return selected

    def get_cascade_queries(self) -> Dict[str, List[QueryResult]]:
        """
        Get queries organized by tier for fail-soft cascade execution.

        Execute T1 first. If insufficient results, cascade to T2, etc.
        """
        all_queries = self.generate_slot_queries()

        cascade = {
            "T1": [],
            "T2": [],
            "T3": [],
            "T4": [],
            "T5": [],
        }

        for q in all_queries:
            if q.tier in cascade:
                cascade[q.tier].append(q)

        return cascade


# =============================================================================
# ENTITY TRACE PROMPT - For AI-Assisted Query Generation
# =============================================================================

ENTITY_TRACE_PROMPT = r"""
SYSTEM
You are **EntityTrace**, an advanced OSINT query strategist.
Your Goal: Bypass "namesake noise" by triangulating a stable **ANCHOR** (Surname) with specific **ATTRIBUTE SLOTS**.

USER INPUT: {concepts}
MULTI_CONCEPT: {is_multi}
OPERATORS: {operator_palette}

THE STRATEGY (SLOT-FILLING PROTOCOL):
1. **The Anchor Rule**:
   - Analyze the Entity Name. Isolate the **Surname**.
   - If the Surname is unique (e.g., "Zuckerberg"), DISCARD the first name. Search the Surname as an exact phrase.
   - If the Surname is common (e.g., "Smith"), keep the Initial or Full Name.

2. **The Intersection Logic (Edge Stacking)**:
   - A Surname alone is noise. It becomes signal ONLY when intersected with a filled "Slot".
   - **[Slot A] Network Edge**: "Surname" AND "AssociateSurname". (High Confidence)
   - **[Slot B] Corporate Edge**: "Surname" AND "Company Name". (High Confidence)
   - **[Slot C] Registry Edge**: "Surname" AND (YYYY OR "dd month") AND ("Director" OR "Board").
   - **[Slot D] Sovereign Edge**: "Surname" site:.[country_code]. (If resident abroad).

════════════════════════════════════════════════════════════════════════════════
THE 12-STEP EXECUTION PROCESS
════════════════════════════════════════════════════════════════════════════════

1. SLOT ANALYSIS:
   - Deconstruct input into: ANCHOR (Surname) + SLOTS (Associates, Companies, Industry, Dates, Geo).
   - Label concepts by their "Uniqueness Score".

2. TOKEN EXPANSION:
   - **Associates**: Extract surnames only.
   - **Companies**: If generic (e.g., "General Logistics"), pair with Industry terms.
   - **Geo**: Convert Country Names to TLDs (e.g., "France" -> `site:.fr`).

3. STRENGTH SCORING:
   - Rate the ANCHOR.
     - Unique Surname = 5 (Solo capable).
     - Common Surname = 1 (Must pair with mandatory slot).

4. PHRASE STRATEGY (The Exactness Rule):
   - **Strictly Quote** the Anchor: "Surname".
   - **Strictly Quote** Associate Surnames: "AssociateSurname".

5. REDUCTION LADDER (The Tiers):
   - **Tier 1 (The Network)**: "Anchor" AND "Associate".
   - **Tier 2 (The Corp)**: "Anchor" AND "Company".
   - **Tier 3 (The Filing)**: "Anchor" AND DOB_Year AND ("Director" OR "Appointed").
   - **Tier 4 (The Sov)**: site:TLD "Anchor" AND ("Industry" OR "English").

6. MANDATORY FACETS:
   - The ANCHOR is strictly mandatory.
   - At least one SLOT is mandatory to prevent disambiguation failure.

7. AMBIGUITY GUARD:
   - If Anchor is <4 chars (e.g., "Ma", "Li"), strict intersection with Industry/Company is required.

8. MINIMAL COMBOS (PMI Optimization):
   - Identify the "Longest Minimum": The shortest query with the highest Pointwise Mutual Information.
   - Example: Instead of "Johnathan Smith" "Caterpillar Inc", use "Smith" "Caterpillar".

9. CO-OCCURRENCE CHECK:
   - Verify that the specific combination implies a relationship (e.g., Board Member, Employee).

10. TIER ASSEMBLY:
    - Generate 10-15 queries. Prioritize Tier 1 & 2 (Direct Edges).

11. SANITY PRUNE:
    - Ensure `site:` operators match the known residency.

12. OUTPUT JSON:
    Return the standard schema. Tag `src` as "slot_filling".

{{
 "schema": "{schema_version}",
 "engine": "search_engineer",
 "timestamp": "{timestamp}",
 "mandatory_facets": ["surname_anchor"],
 "queries": [
   {{
     "q": "\"Surname\" \"AssociateSurname\"",
     "tier": "1",
     "src": "slot_filling_network",
     "est_hits": "high",
     "est_noise": 5,
     "cid": "1"
   }}
 ]
}}
"""


# =============================================================================
# MASTER PROMPT - Unified Search System (The Architect)
# =============================================================================
#
# PHILOSOPHY: "Query for the Document that Contains the Answer"
#
# A search query is NOT asking a search engine for the answer directly.
# It is asking for the TEXTUAL ENVIRONMENT where the answer would naturally appear.
#
# If we want to know "Who owns XYZ Corp?", we ask for DOCUMENTS that would
# contain ownership information - corporate filings, annual reports, registry pages.
# =============================================================================

MASTER_PROMPT = r"""
SYSTEM
You are **SearchArchitect**, a master query strategist.
Your Philosophy: We query for the TEXTUAL ENVIRONMENT containing the answer, not the answer itself.

THE FUNDAMENTAL TRUTH
────────────────────────────────────────────────────────────────────────────────
A search engine does not KNOW facts. It INDEXES documents.
Our job is to describe the DOCUMENT that contains what we seek.

Instead of asking: "Who is the CEO of Acme Corp?"
We query for: Documents that would contain CEO announcements, corporate filings, or leadership pages.

THE FOUR QUERY DIMENSIONS
────────────────────────────────────────────────────────────────────────────────
Every effective query considers:

1. WHAT/WHO (Subject)
   - The entity we're researching
   - Name variations, identifiers
   - Related entities (associates, companies)

2. WHERE (Location)
   - Source domains (site:sec.gov, site:companieshouse.gov.uk)
   - TLD restrictions (site:.uk, site:.de)
   - Document types (filetype:pdf)

3. HOW (Context/Pattern)
   - Document type indicators ("annual report", "filing", "press release")
   - Role patterns ("director", "appointed", "resigned")
   - Temporal markers ("2023", "Q4", "fiscal year")

4. WHO/WHAT WITH (Triangulation)
   - Co-occurrence anchors (associate surnames, company names)
   - Relationship indicators ("board member", "subsidiary", "investor")

SEARCH vs WATCH
────────────────────────────────────────────────────────────────────────────────
Two distinct modes of operation:

SEARCH MODE (Active Discovery)
- Immediate execution
- Find what exists NOW
- Exhaust available sources
- Return corpus for analysis

WATCH MODE (Continuous Monitoring)
- Persistent query
- Alert on NEW appearances
- Track changes over time
- Subscribe to future documents

Always clarify which mode the user needs.

QUERY CONSTRUCTION PROTOCOL
────────────────────────────────────────────────────────────────────────────────

1. IDENTIFY THE TEXTUAL ENVIRONMENT
   What KIND of document would contain this information?
   - Corporate filing, news article, court record, registry page?

2. DERIVE THE ANCHOR
   What is the most unique term that MUST appear?
   - Surname for persons (if unique enough)
   - Distinctive company name (stripped of generic suffixes)

3. ADD TRIANGULATION
   What secondary term creates intersection?
   - Associate surname, company name, date, role

4. CONSTRAIN LOCATION (if known)
   - Specific source domains
   - Jurisdiction TLDs
   - Document types

5. TIER THE QUERIES
   - T1: Highest precision (anchor + strong triangulation)
   - T2-T3: Medium precision (anchor + context)
   - T4-T5: Broader discovery (anchor + domain constraints)

INPUT:
{user_query}

KNOWN CONTEXT:
{context}

OUTPUT:
Return structured query set with rationale for each tier.
"""


class UnifiedSearchDirector:
    """
    Implements the Unified Search Philosophy.

    Separates SEARCH (active discovery) from WATCH (continuous monitoring)
    and constructs queries that target the TEXTUAL ENVIRONMENT where
    answers would naturally appear.

    Key Methods:
    - search(): Immediate discovery across available sources
    - watch(): Set up continuous monitoring for new appearances
    - construct_environment_query(): Build query targeting document types
    """

    def __init__(self):
        self.triangulator_cache: Dict[str, EntityTriangulator] = {}
        self.variety_generator = VarietyGenerator()
        self.dimension_builder = DimensionAwareQueryBuilder()

    def search(
        self,
        subject: str,
        subject_type: str = "person",
        profile_data: Optional[Dict[str, Any]] = None,
        location_data: Optional[Dict[str, Any]] = None,
        document_context: Optional[str] = None,
        ku_quadrant: Optional[KUQuadrant] = None,
    ) -> Dict[str, Any]:
        """
        SEARCH MODE: Active discovery across available sources.

        Uses Strategy Pattern for query generation:
        - Base: EntityTriangulator (slot-filling with anchor)
        - Decorator: EnvironmentAwareStrategy (document type targeting)
        - Decorator: KUAwareStrategy (quadrant-based filtering)

        Args:
            subject: The entity to search for
            subject_type: person/company/domain/etc.
            profile_data: Known information for triangulation
            location_data: Domain/jurisdiction constraints
            document_context: Expected document type (e.g., "corporate filing", "news")
            ku_quadrant: Knowledge quadrant for query prioritization

        Returns:
            Dict with:
                - queries: Tiered query list
                - environment: Detected document environment
                - mode: "search"
                - strategy: Strategy chain used
        """
        profile_data = profile_data or {}
        location_data = location_data or {}

        # Build EntityProfile
        profile = EntityProfile(
            full_name=subject,
            entity_type=subject_type,
            associates=profile_data.get("associates", []),
            companies=profile_data.get("companies", []),
            industry=profile_data.get("industry", []),
            dob=profile_data.get("dob"),
            identifiers=profile_data.get("identifiers", {}),
            residency_code=location_data.get("residency_code"),
            jurisdictions=location_data.get("jurisdictions", []),
            active_years=location_data.get("years", []),
            roles=profile_data.get("roles", []),
            known_sources=location_data.get("domains", []),
        )

        # Build strategy chain using Strategy Pattern
        cache_key = f"{subject}:{subject_type}"
        if cache_key not in self.triangulator_cache:
            self.triangulator_cache[cache_key] = EntityTriangulator(profile)

        # Base strategy: EntityTriangulator (implements QueryGenerationStrategy)
        strategy: QueryGenerationStrategy = self.triangulator_cache[cache_key]
        strategy_chain = ["EntityTriangulator"]

        # Decorator: EnvironmentAwareStrategy (if document context provided)
        if document_context:
            domains = location_data.get("domains", [])
            strategy = EnvironmentAwareStrategy(strategy, document_context, domains)
            strategy_chain.append(f"EnvironmentAware({document_context})")

        # Decorator: KUAwareStrategy (if K-U quadrant provided)
        if ku_quadrant:
            strategy = KUAwareStrategy(strategy, ku_quadrant)
            strategy_chain.append(f"KUAware({ku_quadrant.value})")

        # Build query context
        context = QueryContext(
            ku_quadrant=ku_quadrant,
            profile=profile,
        )

        # Generate queries through strategy chain
        query_results = strategy.generate(context)

        # Get triangulator for anchor info (base strategy)
        triangulator = self.triangulator_cache[cache_key]

        # Get variations using Variety Generator
        variations = self.variety_generator.generate_all_variations(
            subject, subject_type
        )

        # Convert QueryResults to output format
        all_queries = []
        for q in query_results:
            all_queries.append({
                "query": q.q,
                "tier": q.tier,
                "source": q.src,
                "quality_score": q.quality_score,
                "slot_used": q.slot_used,
            })

        # Also get cascade for backward compatibility
        cascade = triangulator.get_cascade_queries()

        return {
            "mode": "search",
            "anchor": triangulator.anchor,
            "anchor_strength": triangulator.anchor_strength,
            "queries": all_queries,
            "environment": document_context or "general",
            "variations": variations,
            "cascade": {tier: [q.q for q in qs] for tier, qs in cascade.items()},
            "strategy_chain": " → ".join(strategy_chain),
            "tier_distribution": strategy.get_tier_distribution(),
        }

    def watch(
        self,
        subject: str,
        subject_type: str = "person",
        profile_data: Optional[Dict[str, Any]] = None,
        watch_domains: Optional[List[str]] = None,
        alert_keywords: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        WATCH MODE: Set up continuous monitoring for new appearances.

        Creates persistent queries for ongoing monitoring.

        Args:
            subject: The entity to watch
            subject_type: person/company/domain/etc.
            profile_data: Known information for query construction
            watch_domains: Specific domains to monitor
            alert_keywords: Additional keywords that trigger alerts

        Returns:
            Dict with:
                - watch_queries: Queries for continuous monitoring
                - alert_rules: Conditions that trigger alerts
                - mode: "watch"
        """
        profile_data = profile_data or {}
        watch_domains = watch_domains or []
        alert_keywords = alert_keywords or []

        # Build profile
        profile = EntityProfile(
            full_name=subject,
            entity_type=subject_type,
            associates=profile_data.get("associates", []),
            companies=profile_data.get("companies", []),
        )

        triangulator = EntityTriangulator(profile)
        anchor = triangulator.anchor

        # Build watch queries (simpler than search queries)
        watch_queries = []

        # Basic anchor watch
        watch_queries.append({
            "query": anchor,
            "type": "base_watch",
            "priority": "high",
        })

        # Domain-specific watches
        for domain in watch_domains:
            watch_queries.append({
                "query": f"site:{domain} {anchor}",
                "type": "domain_watch",
                "domain": domain,
                "priority": "medium",
            })

        # Alert keyword combinations
        for keyword in alert_keywords:
            watch_queries.append({
                "query": f'{anchor} "{keyword}"',
                "type": "keyword_alert",
                "keyword": keyword,
                "priority": "high",
            })

        # Build alert rules
        alert_rules = [
            {"condition": "new_document", "action": "notify"},
            {"condition": "keyword_match", "keywords": alert_keywords, "action": "alert"},
            {"condition": "domain_match", "domains": watch_domains, "action": "notify"},
        ]

        return {
            "mode": "watch",
            "subject": subject,
            "anchor": anchor,
            "watch_queries": watch_queries,
            "alert_rules": alert_rules,
            "watch_domains": watch_domains,
            "alert_keywords": alert_keywords,
        }

    def _build_environment_queries(
        self,
        anchor: str,
        document_context: str,
        location_data: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Build queries targeting specific document environments.

        Args:
            anchor: The search anchor term
            document_context: Expected document type
            location_data: Domain/jurisdiction constraints

        Returns:
            List of environment-aware query dicts
        """
        queries = []

        # Map document context to search patterns
        environment_patterns = {
            "corporate_filing": [
                ("annual report", "filetype:pdf"),
                ("10-K", "site:sec.gov"),
                ("company accounts", "site:companieshouse.gov.uk"),
            ],
            "news": [
                ("news", "site:reuters.com OR site:bloomberg.com"),
                ("press release", ""),
                ("announcement", ""),
            ],
            "court_record": [
                ("court", "case OR lawsuit OR judgment"),
                ("litigation", "defendant OR plaintiff"),
            ],
            "registry": [
                ("director", "appointed OR resigned"),
                ("officer", "registration OR incorporation"),
            ],
            "sanctions": [
                ("sanctions", "OFAC OR EU OR UN"),
                ("designated", "blocked OR prohibited"),
            ],
        }

        patterns = environment_patterns.get(document_context, [])

        for pattern_name, pattern_extra in patterns:
            query_parts = [anchor, f'"{pattern_name}"']
            if pattern_extra:
                query_parts.append(f"({pattern_extra})")

            # Add domain constraints if available
            domains = location_data.get("domains", [])
            if domains:
                domain_or = " OR ".join(f"site:{d}" for d in domains[:3])
                query_parts.append(f"({domain_or})")

            queries.append({
                "query": " ".join(query_parts),
                "tier": "T3",
                "source": f"environment:{document_context}",
                "quality_score": 0.75,
                "environment": document_context,
            })

        return queries

    def construct_environment_query(
        self,
        what_who: str,
        where: Optional[str] = None,
        how: Optional[str] = None,
        with_whom: Optional[str] = None,
    ) -> str:
        """
        Construct a query using the four dimensions.

        Args:
            what_who: Subject (entity name, identifier)
            where: Location (domain, jurisdiction, filetype)
            how: Context (document type, patterns)
            with_whom: Triangulation (associate, company)

        Returns:
            Constructed query string
        """
        parts = [f'"{what_who}"']

        if with_whom:
            parts.append(f'"{with_whom}"')

        if how:
            # Add context patterns
            if not how.startswith('"'):
                how = f'({how})'
            parts.append(how)

        if where:
            # Add location constraints
            if "site:" not in where and "filetype:" not in where:
                where = f"site:{where}"
            parts.append(where)

        return " ".join(parts)


# =============================================================================
# DIMENSION-AWARE QUERY BUILDER
# =============================================================================

class DimensionAwareQueryBuilder:
    """
    Builds queries by systematically considering each dimension of available information.

    The builder examines LOCATION and SUBJECT axis dimensions and constructs
    queries that leverage the strongest available signals.
    """

    # Dimension weights for query construction priority
    DIMENSION_WEIGHTS = {
        # SUBJECT dimensions (Y-axis) - what we're searching for
        "identifier": 1.0,      # Hard IDs are definitive
        "network": 0.9,         # Relationships are high signal
        "identity": 0.8,        # Name variations
        "temporal_subject": 0.7,  # DOB, incorporation date
        "attribute": 0.6,       # Role, profession

        # LOCATION dimensions (X-axis) - where to search
        "domain": 0.85,         # Specific source/registry
        "jurisdiction": 0.75,   # Country/legal zone
        "format": 0.5,          # Document type
        "temporal_location": 0.4,  # Archive date
        "physical": 0.3,        # Address (rare in queries)
    }

    def __init__(self):
        self.person_variator = PersonVariator()
        self.company_variator = CompanyVariator()
        self.location_variator = LocationVariator()

    def build_from_dimensions(
        self,
        subject_data: Dict[str, Any],
        location_data: Dict[str, Any],
        intent: str = "discover",
    ) -> List[Dict[str, Any]]:
        """
        Build queries by considering each filled dimension.

        Args:
            subject_data: Subject axis information
                - name: Entity name
                - type: person/company/etc
                - identifiers: {oib: "123", ...}
                - dob: "1990-01-15"
                - roles: ["director", "CEO"]
                - industry: ["finance", "banking"]
                - associates: ["John Doe", "Jane Smith"]
                - companies: ["Acme Corp", "Globex"]
            location_data: Location axis information
                - domains: ["sec.gov", "companieshouse.gov.uk"]
                - jurisdictions: ["US", "UK"]
                - tlds: ["us", "uk", "gov"]
                - filetypes: ["pdf", "html"]
                - years: [2020, 2021, 2022]
            intent: discover/verify/enrich/trace

        Returns:
            List of query dicts with metadata
        """
        queries = []

        # Extract subject anchor
        name = subject_data.get("name", "")
        entity_type = subject_data.get("type", "unknown")

        if not name:
            return []

        # Build EntityProfile for triangulation
        profile = EntityProfile(
            full_name=name,
            entity_type=entity_type,
            associates=subject_data.get("associates", []),
            companies=subject_data.get("companies", []),
            industry=subject_data.get("industry", []),
            dob=subject_data.get("dob"),
            identifiers=subject_data.get("identifiers", {}),
            residency_code=location_data.get("tlds", [None])[0] if location_data.get("tlds") else None,
            jurisdictions=location_data.get("jurisdictions", []),
            active_years=location_data.get("years", []),
            roles=subject_data.get("roles", []),
            known_sources=location_data.get("domains", []),
        )

        # Get triangulated queries
        triangulator = EntityTriangulator(profile)
        slot_queries = triangulator.get_minimum_viable_queries()

        for sq in slot_queries:
            queries.append({
                "query": sq.q,
                "tier": sq.tier,
                "source": sq.src,
                "slot_used": sq.slot_used,
                "quality_score": sq.quality_score,
                "est_noise": sq.est_noise,
            })

        # Add location-constrained queries
        domains = location_data.get("domains", [])
        if domains:
            anchor = triangulator.anchor
            for domain in domains[:3]:
                queries.append({
                    "query": f'site:{domain} {anchor}',
                    "tier": "T2",
                    "source": "dimension_domain",
                    "slot_used": f"domain:{domain}",
                    "quality_score": 0.85,
                    "est_noise": 8,
                })

        # Add filetype queries for document-specific searches
        filetypes = location_data.get("filetypes", [])
        if filetypes and intent in ("discover", "trace"):
            anchor = triangulator.anchor
            for ft in filetypes[:2]:
                queries.append({
                    "query": f'filetype:{ft} {anchor}',
                    "tier": "T4",
                    "source": "dimension_filetype",
                    "slot_used": f"filetype:{ft}",
                    "quality_score": 0.6,
                    "est_noise": 20,
                })

        # Generate variations
        variations = self._get_variations(name, entity_type)
        for var in variations[:5]:
            if var != name:
                queries.append({
                    "query": f'"{var}"',
                    "tier": "T5",
                    "source": "variation",
                    "slot_used": "name_variation",
                    "quality_score": 0.5,
                    "est_noise": 35,
                    "original": name,
                    "variation": var,
                })

        # Sort by quality score
        queries.sort(key=lambda q: q.get("quality_score", 0), reverse=True)

        return queries

    def _get_variations(self, name: str, entity_type: str) -> List[str]:
        """Get variations for a name based on entity type."""
        if entity_type in ("person", "individual"):
            return self.person_variator.fallback_variations(name)
        elif entity_type in ("company", "organization"):
            return self.company_variator.fallback_variations(name)
        elif entity_type in ("location", "address"):
            return self.location_variator.fallback_variations(name)
        return [name]


# =============================================================================
# OPERATORS REFERENCE
# =============================================================================

OPERATORS = {
    # Extraction Operators
    "ent?": {
        "description": "Extract all entities",
        "valid_targets": ["@SOURCE", "@DOCUMENT", "@DOMAIN"],
        "example": "ent? :!domain.com"
    },
    "p?": {
        "description": "Extract persons",
        "valid_targets": ["@SOURCE", "@DOCUMENT"],
        "example": "p? :!#source"
    },
    "c?": {
        "description": "Extract companies",
        "valid_targets": ["@SOURCE", "@DOCUMENT"],
        "example": "c? :domain.com/page!"
    },
    "e?": {
        "description": "Extract emails",
        "valid_targets": ["@SOURCE", "@DOCUMENT"],
        "example": "e? :!#querynode"
    },
    "t?": {
        "description": "Extract phone numbers",
        "valid_targets": ["@SOURCE", "@DOCUMENT"],
        "example": "t? :!domain.com"
    },
    "a?": {
        "description": "Extract addresses",
        "valid_targets": ["@SOURCE", "@DOCUMENT"],
        "example": "a? :#source!"
    },

    # Link Operators
    "bl?": {
        "description": "Get backlink pages",
        "valid_targets": ["@SOURCE", "@DOMAIN"],
        "example": "bl? :!domain.com"
    },
    "?bl": {
        "description": "Get backlink domains",
        "valid_targets": ["@SOURCE", "@DOMAIN"],
        "example": "?bl :!domain.com"
    },
    "ol?": {
        "description": "Get outlink pages",
        "valid_targets": ["@SOURCE", "@DOMAIN"],
        "example": "ol? :domain.com/page!"
    },
    "?ol": {
        "description": "Get outlink domains",
        "valid_targets": ["@SOURCE", "@DOMAIN"],
        "example": "?ol :!domain.com"
    },

    # Enrichment Operators
    "enrich?": {
        "description": "Fill entity slots with external data",
        "valid_targets": ["@PERSON", "@COMPANY", "@ASSET"],
        "example": "enrich? :!#company"
    },
    "sanctions?": {
        "description": "Check sanctions lists",
        "valid_targets": ["@PERSON", "@COMPANY"],
        "example": "sanctions? :!#person"
    },
    "registry?": {
        "description": "Check corporate registries",
        "valid_targets": ["@COMPANY"],
        "example": "registry? :#company!"
    },
    "whois?": {
        "description": "Domain registration lookup",
        "valid_targets": ["@DOMAIN"],
        "example": "whois? :domain.com"
    },

    # Compare Operator
    "=?": {
        "description": "Compare nodes across all dimensions",
        "valid_targets": ["@PERSON", "@COMPANY", "@ASSET", "@SOURCE"],
        "example": "=? :#node_a #node_b"
    },
}

# Valid targets for each operator
OPERATOR_TARGETS = {
    "ent?": ["@SOURCE", "@DOCUMENT", "@DOMAIN"],
    "p?": ["@SOURCE", "@DOCUMENT"],
    "c?": ["@SOURCE", "@DOCUMENT"],
    "e?": ["@SOURCE", "@DOCUMENT"],
    "t?": ["@SOURCE", "@DOCUMENT"],
    "a?": ["@SOURCE", "@DOCUMENT"],
    "enrich?": ["@PERSON", "@COMPANY", "@ASSET"],
    "sanctions?": ["@PERSON", "@COMPANY"],
    "registry?": ["@COMPANY"],
    "bl?": ["@SOURCE", "@DOMAIN"],
    "?bl": ["@SOURCE", "@DOMAIN"],
    "ol?": ["@SOURCE", "@DOMAIN"],
    "?ol": ["@SOURCE", "@DOMAIN"],
    "whois?": ["@DOMAIN"],
    "=?": ["@PERSON", "@COMPANY", "@ASSET", "@SOURCE"],
}


# =============================================================================
# INTENT TRANSLATOR (QUERY COMPILER)
# =============================================================================

class IntentTranslator:
    """
    Agent's syntax knowledge - translates user intent to operations.

    The compiler recognizes intent patterns and maps them to syntax templates.
    The agent doesn't need to know HOW operators work internally.
    It only needs to know WHICH operators to use for WHICH intent.
    """

    # Intent patterns the agent recognizes
    PATTERNS = {
        # Discovery - Finding new entities
        r"who is (connected|linked|associated) to": "DISCOVER_CONNECTIONS",
        r"find (connections|links|relationships)": "DISCOVER_CONNECTIONS",
        r"what (companies|entities) (does|did)": "DISCOVER_ENTITIES",
        r"extract entities": "EXTRACT_ENTITIES",
        r"find (new|other|more) (people|persons|companies|entities)": "DISCOVER_ENTITIES",

        # Verification - Confirming known connections
        r"is .* (linked|connected|associated) to": "VERIFY_CONNECTION",
        r"(confirm|verify|check) (the )?(link|connection)": "VERIFY_CONNECTION",
        r"does .* (know|work with|connect to)": "VERIFY_CONNECTION",

        # Compare / Identity
        r"are .* the same": "COMPARE_IDENTITY",
        r"same (person|company|entity)": "COMPARE_IDENTITY",
        r"what.* in common": "COMPARE_OVERLAP",
        r"compare": "COMPARE_OVERLAP",
        r"(difference|delta) between": "COMPARE_OVERLAP",
        r"overlap": "COMPARE_OVERLAP",

        # Similarity search
        r"(find|what).* similar": "SIMILARITY_SEARCH",
        r"closest to": "SIMILARITY_SEARCH",
        r"like this": "SIMILARITY_SEARCH",
        r"unconnected.* similar": "SIMILARITY_UNLINKED",
        r"group.* by similarity": "CLUSTER",
        r"what connects.* groups": "BRIDGE_SEARCH",

        # Enrichment - Filling slots
        r"find (out )?more about": "ENRICH_ENTITY",
        r"what (else )?do we know": "ENRICH_ENTITY",
        r"dig deeper": "ENRICH_ENTITY",
        r"fill in": "ENRICH_ENTITY",
        r"enrich": "ENRICH_ENTITY",

        # Sanctions/Compliance
        r"(check|run) sanctions": "CHECK_SANCTIONS",
        r"on (any )?sanctions list": "CHECK_SANCTIONS",
        r"sanctioned": "CHECK_SANCTIONS",

        # Registry
        r"(check|search) (corporate )?registr": "CHECK_REGISTRY",
        r"company (house|registry|register)": "CHECK_REGISTRY",
        r"(registered|incorporated) (where|in)": "CHECK_REGISTRY",

        # Domain/WHOIS
        r"who (owns|registered)": "CHECK_WHOIS",
        r"whois": "CHECK_WHOIS",
        r"domain (registration|owner)": "CHECK_WHOIS",

        # Exclusion
        r"but not": "DISCRIMINATE",
        r"exclude": "DISCRIMINATE",
        r"filter out": "DISCRIMINATE",
        r"without": "DISCRIMINATE",

        # Expansion
        r"check all": "EXPAND_SEARCH",
        r"across all": "EXPAND_SEARCH",
        r"everywhere": "EXPAND_SEARCH",
        r"all (jurisdictions|registries|sources)": "EXPAND_SEARCH",

        # Scope control
        r"just (this|that) one": "CONTRACT_SCOPE",
        r"only (this|that)": "CONTRACT_SCOPE",
        r"and (related|connected)": "EXPAND_SCOPE",

        # Link Analysis
        r"who links to": "BACKLINKS",
        r"links to (this|the)": "BACKLINKS",
        r"backlinks": "BACKLINKS",
        r"what does .* link to": "OUTLINKS",
        r"links from": "OUTLINKS",
        r"outlinks": "OUTLINKS",
    }

    # How each intent maps to syntax
    SYNTAX_TEMPLATES = {
        # Discovery
        "DISCOVER_CONNECTIONS": "ent? :!{subject} => #CONNECTIONS",
        "DISCOVER_ENTITIES": "ent? :!{subject} AND {type_filter}",
        "EXTRACT_ENTITIES": "ent? :!{targets}",

        # Verification
        "VERIFY_CONNECTION": "{subject_a} AND {subject_b} :!#SOURCES",

        # Comparison
        "COMPARE_IDENTITY": "=? :#{entity_a} #{entity_b}",
        "COMPARE_OVERLAP": "=? :#{targets}",
        "SIMILARITY_SEARCH": "=? :#{target} :@{class}",
        "SIMILARITY_UNLINKED": "=? :#{target} :@{class} ##unlinked",
        "CLUSTER": "=? :@{class} {filters} ##cluster",
        "BRIDGE_SEARCH": "=? :#{target_a} #{target_b} :@{class} ##bridge",

        # Enrichment
        "ENRICH_ENTITY": "enrich? :!{entity}",

        # Compliance
        "CHECK_SANCTIONS": "sanctions? :!{entity}",
        "CHECK_REGISTRY": "registry? :!{company}",
        "CHECK_WHOIS": "whois? :{domain}",

        # Filtering
        "DISCRIMINATE": "{subject} NOT ({exclusion})",

        # Expansion
        "EXPAND_SEARCH": "ent? :!{subject} AND ({group})",

        # Scope
        "CONTRACT_SCOPE": "{operator} :#{target}!",
        "EXPAND_SCOPE": "{operator} :!#{target}",

        # Link Analysis
        "BACKLINKS": "bl? :!{target}",
        "OUTLINKS": "ol? :!{target}",
    }

    def __init__(self):
        self.variators = {
            EntityType.PERSON: PersonVariator(),
            EntityType.COMPANY: CompanyVariator(),
            EntityType.LOCATION: LocationVariator(),
            EntityType.PHONE: PhoneVariator(),
        }

    def translate(self, user_input: str, context: QueryContext) -> str:
        """
        Translate natural language to syntax.

        Agent knows the language, not the machinery.
        """
        intent = self.detect_intent(user_input)
        entities = self.extract_entities(user_input, context)
        template = self.SYNTAX_TEMPLATES.get(intent, "ent? :!{subject}")
        return self.fill_template(template, entities, context)

    def detect_intent(self, text: str) -> str:
        """Match user text to intent pattern."""
        text_lower = text.lower()
        for pattern, intent in self.PATTERNS.items():
            if re.search(pattern, text_lower):
                return intent
        return "DISCOVER_CONNECTIONS"  # Default

    def extract_entities(self, text: str, context: QueryContext) -> Dict:
        """Pull entity references from text."""
        entities = {}

        # Check for references to current focus
        if "this" in text.lower() or "the" in text.lower():
            entities["subject"] = f"#{context.current_focus}"

        # Check for named entities in context
        for entity_id, entity in context.entities.items():
            if entity.name.lower() in text.lower():
                if "subject" not in entities:
                    entities["subject"] = f"#{entity_id}"
                    entities["subject_a"] = f"#{entity_id}"
                else:
                    entities["subject_b"] = f"#{entity_id}"
                    entities["entity_b"] = f"#{entity_id}"

        return entities

    def fill_template(self, template: str, entities: Dict, context: QueryContext) -> str:
        """Fill template with extracted entities."""
        result = template

        for key, value in entities.items():
            result = result.replace(f"{{{key}}}", value)

        # Fill remaining placeholders with defaults
        result = re.sub(r"\{[^}]+\}", "#UNKNOWN", result)

        return result

    def generate_variations(self, entity: Entity) -> List[Tuple[str, int]]:
        """Generate variations for an entity using appropriate variator."""
        variator = self.variators.get(entity.entity_type)
        if variator:
            return variator.generate_variations_with_strength(entity.name)
        return [(entity.name, 5)]

    def compile_with_variations(self, user_input: str, context: QueryContext) -> Dict:
        """
        Full compilation with variations.

        Returns structured query object with:
        - Primary query
        - Variation queries
        - K-U quadrant
        - Intent classification
        """
        intent = self.detect_intent(user_input)
        base_query = self.translate(user_input, context)

        # Determine K-U quadrant based on context
        ku_quadrant = self.assess_ku_position(context)

        # Generate variation queries
        variation_queries = []
        for entity_id, entity in context.entities.items():
            if entity.name.lower() in user_input.lower():
                variations = self.generate_variations(entity)
                for var_text, strength in variations:
                    if var_text != entity.name:
                        var_query = base_query.replace(
                            f"#{entity_id}",
                            f'"{var_text}"'
                        )
                        variation_queries.append({
                            "query": var_query,
                            "variation": var_text,
                            "strength": strength,
                            "original": entity.name
                        })

        return {
            "intent": intent,
            "ku_quadrant": ku_quadrant.value,
            "primary_query": base_query,
            "variation_queries": variation_queries,
            "context": {
                "focus": context.current_focus,
                "narrative": context.narrative,
                "gaps": context.gaps,
            }
        }

    def assess_ku_position(self, context: QueryContext) -> KUQuadrant:
        """Assess where we are on the Known-Unknown matrix."""
        has_entities = len(context.entities) > 0
        has_sources = len(context.sources) > 0

        if has_entities and has_sources:
            return KUQuadrant.VERIFY
        elif has_entities and not has_sources:
            return KUQuadrant.TRACE
        elif not has_entities and has_sources:
            return KUQuadrant.EXTRACT
        else:
            return KUQuadrant.DISCOVER


# =============================================================================
# QUERY PARSER (for parsing compiled syntax back)
# =============================================================================

class QueryParser:
    """Parse compiled SASTRE syntax into executable components."""

    OPERATOR_PATTERN = re.compile(r"^(\w+\??|\?\w+)\s*:(.+)$")
    NODE_PATTERN = re.compile(r"#(\w+)")
    SCOPE_PATTERN = re.compile(r"(!?)([^!]+)(!?)$")

    def parse(self, query: str) -> Dict:
        """Parse a query string into components."""
        result = {
            "operator": None,
            "targets": [],
            "scope": "expand",  # expand, contract, or single
            "filters": [],
            "chain": [],
        }

        # Handle chained operations
        if "=>" in query:
            parts = [p.strip() for p in query.split("=>")]
            result["chain"] = [self.parse(p) for p in parts]
            return result

        # Extract operator
        match = self.OPERATOR_PATTERN.match(query.strip())
        if match:
            result["operator"] = match.group(1)
            target_str = match.group(2).strip()
        else:
            target_str = query.strip()

        # Extract nodes
        nodes = self.NODE_PATTERN.findall(target_str)
        result["targets"] = nodes

        # Determine scope from ! prefix/suffix
        scope_match = self.SCOPE_PATTERN.match(target_str)
        if scope_match:
            prefix_bang = scope_match.group(1) == "!"
            suffix_bang = scope_match.group(3) == "!"

            if prefix_bang and not suffix_bang:
                result["scope"] = "expand"
            elif suffix_bang and not prefix_bang:
                result["scope"] = "contract"
            else:
                result["scope"] = "single"

        # Extract AND/OR/NOT filters
        if " AND " in query:
            result["filters"].append({"type": "AND", "terms": query.split(" AND ")[1:]})
        if " NOT " in query:
            not_part = query.split(" NOT ")[1]
            result["filters"].append({"type": "NOT", "terms": [not_part.strip("()")]})

        return result


# =============================================================================
# MAIN COMPILER CLASS
# =============================================================================

class SastreQueryCompiler:
    """
    Main entry point for query compilation.

    Combines:
    - Intent translation
    - Variation generation (with Entropy Logic)
    - Query parsing
    - K-U awareness
    - Entity Triangulation (Slot-Filling Strategy)
    - Dimension-Aware Query Building
    - Unified Search Philosophy (Search vs Watch)
    - Variety Generation (Principle of Useful Variety)
    """

    def __init__(self):
        self.translator = IntentTranslator()
        self.parser = QueryParser()
        self.dimension_builder = DimensionAwareQueryBuilder()
        self.variety_generator = VarietyGenerator()
        self.search_director = UnifiedSearchDirector()

    def compile(self, user_input: str, context: QueryContext = None) -> Dict:
        """
        Compile natural language to SASTRE syntax.

        Args:
            user_input: Natural language query
            context: Current investigation state

        Returns:
            Compiled query object with variations
        """
        if context is None:
            context = QueryContext()

        return self.translator.compile_with_variations(user_input, context)

    def compile_triangulated(
        self,
        entity_name: str,
        entity_type: str = "person",
        profile_data: Optional[Dict[str, Any]] = None,
        location_data: Optional[Dict[str, Any]] = None,
        intent: str = "discover",
    ) -> Dict[str, Any]:
        """
        Compile queries using Entity Triangulation (Slot-Filling Strategy).

        This method generates high-precision queries by:
        1. Deriving an optimal anchor from the entity name
        2. Filling available slots (associates, companies, industry, etc.)
        3. Generating tiered queries using the fail-soft cascade

        Args:
            entity_name: Name of the entity to search for
            entity_type: Type of entity (person, company, domain, etc.)
            profile_data: Known information about the entity
                - associates: List of known associates
                - companies: List of affiliated companies
                - industry: Industry terms
                - dob: Date of birth (YYYY or YYYY-MM-DD)
                - identifiers: {oib: "123", ssn: "456", etc.}
                - roles: ["director", "CEO", etc.]
            location_data: Location constraints
                - residency_code: Primary TLD (e.g., "fr", "de")
                - jurisdictions: List of countries
                - domains: Specific source domains
                - filetypes: Document types to search
                - years: Active years
            intent: discover/verify/enrich/trace

        Returns:
            Dict with:
                - anchor: The derived anchor term
                - anchor_strength: Uniqueness rating (1-5)
                - queries: List of tiered queries
                - cascade: Queries organized by tier
                - metadata: Additional compilation info
        """
        profile_data = profile_data or {}
        location_data = location_data or {}

        # Build EntityProfile
        profile = EntityProfile(
            full_name=entity_name,
            entity_type=entity_type,
            associates=profile_data.get("associates", []),
            companies=profile_data.get("companies", []),
            industry=profile_data.get("industry", []),
            dob=profile_data.get("dob"),
            identifiers=profile_data.get("identifiers", {}),
            residency_code=location_data.get("residency_code") or (
                location_data.get("tlds", [None])[0] if location_data.get("tlds") else None
            ),
            jurisdictions=location_data.get("jurisdictions", []),
            active_years=location_data.get("years", []),
            roles=profile_data.get("roles", []),
            known_sources=location_data.get("domains", []),
        )

        # Create triangulator
        triangulator = EntityTriangulator(profile)

        # Generate queries
        queries = triangulator.get_minimum_viable_queries()
        cascade = triangulator.get_cascade_queries()

        # Convert to dict format
        query_list = []
        for q in queries:
            query_list.append({
                "query": q.q,
                "tier": q.tier,
                "source": q.src,
                "slot_used": q.slot_used,
                "quality_score": q.quality_score,
                "est_noise": q.est_noise,
                "est_hits": q.est_hits,
            })

        cascade_dict = {}
        for tier, tier_queries in cascade.items():
            cascade_dict[tier] = [
                {"query": q.q, "source": q.src, "quality_score": q.quality_score}
                for q in tier_queries
            ]

        return {
            "anchor": triangulator.anchor,
            "anchor_strength": triangulator.anchor_strength,
            "queries": query_list,
            "cascade": cascade_dict,
            "intent": intent,
            "metadata": {
                "entity_name": entity_name,
                "entity_type": entity_type,
                "filled_slots": self._count_filled_slots(profile),
                "strategy": "slot_filling_triangulation",
            }
        }

    def compile_from_dimensions(
        self,
        subject_data: Dict[str, Any],
        location_data: Dict[str, Any],
        intent: str = "discover",
    ) -> Dict[str, Any]:
        """
        Build queries by systematically considering each dimension.

        Uses DimensionAwareQueryBuilder to examine all available
        LOCATION and SUBJECT axis information.

        Args:
            subject_data: Subject axis information (name, type, identifiers, etc.)
            location_data: Location axis information (domains, jurisdictions, etc.)
            intent: discover/verify/enrich/trace

        Returns:
            Dict with queries and metadata
        """
        queries = self.dimension_builder.build_from_dimensions(
            subject_data, location_data, intent
        )

        return {
            "queries": queries,
            "intent": intent,
            "strategy": "dimension_aware",
            "subject": subject_data.get("name", ""),
            "entity_type": subject_data.get("type", "unknown"),
        }

    def _count_filled_slots(self, profile: EntityProfile) -> Dict[str, bool]:
        """Count which slots are filled in the profile."""
        return {
            "associates": len(profile.associates) > 0,
            "companies": len(profile.companies) > 0,
            "industry": len(profile.industry) > 0,
            "dob": profile.dob is not None,
            "identifiers": len(profile.identifiers) > 0,
            "residency": profile.residency_code is not None,
            "jurisdictions": len(profile.jurisdictions) > 0,
            "roles": len(profile.roles) > 0,
            "sources": len(profile.known_sources) > 0,
        }

    def search(
        self,
        subject: str,
        subject_type: str = "person",
        profile_data: Optional[Dict[str, Any]] = None,
        location_data: Optional[Dict[str, Any]] = None,
        document_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        SEARCH MODE: Active discovery using the Unified Search Philosophy.

        Constructs queries targeting the textual environment where
        answers would naturally appear.

        Uses:
        - Entity Triangulation (Slot-Filling)
        - Variety Generation (Entropy Logic)
        - Environment-Aware Query Construction

        Args:
            subject: The entity to search for
            subject_type: person/company/domain/etc.
            profile_data: Known information for triangulation
            location_data: Domain/jurisdiction constraints
            document_context: Expected document type

        Returns:
            Comprehensive search result with queries, variations, cascade
        """
        return self.search_director.search(
            subject, subject_type, profile_data, location_data, document_context
        )

    def watch(
        self,
        subject: str,
        subject_type: str = "person",
        profile_data: Optional[Dict[str, Any]] = None,
        watch_domains: Optional[List[str]] = None,
        alert_keywords: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        WATCH MODE: Set up continuous monitoring.

        Creates persistent queries for ongoing monitoring
        with alert rules for new document appearances.

        Args:
            subject: The entity to watch
            subject_type: person/company/domain/etc.
            profile_data: Known information for query construction
            watch_domains: Specific domains to monitor
            alert_keywords: Additional keywords that trigger alerts

        Returns:
            Watch configuration with queries and alert rules
        """
        return self.search_director.watch(
            subject, subject_type, profile_data, watch_domains, alert_keywords
        )

    def generate_variations(
        self,
        value: str,
        value_type: str = "person",
        max_variations: int = 15,
    ) -> Dict[str, List[str]]:
        """
        Generate variations using the Principle of Useful Variety.

        Uses Entropy Logic:
        - Common names → Strict variations (few, high-precision)
        - Unique names → Broad variations (more experimental)

        Args:
            value: The value to generate variations for
            value_type: person/company/phone/email/domain
            max_variations: Maximum variations to return

        Returns:
            Dict with "high_likelihood", "medium_likelihood", "experimental" lists
        """
        return self.variety_generator.generate_all_variations(
            value, value_type, max_variations
        )

    def construct_four_dimension_query(
        self,
        what_who: str,
        where: Optional[str] = None,
        how: Optional[str] = None,
        with_whom: Optional[str] = None,
    ) -> str:
        """
        Construct a query using the Four Query Dimensions.

        The four dimensions:
        1. WHAT/WHO - Subject (entity name, identifier)
        2. WHERE - Location (domain, jurisdiction, filetype)
        3. HOW - Context (document type, patterns)
        4. WHO/WHAT WITH - Triangulation (associate, company)

        Args:
            what_who: Subject (entity name, identifier)
            where: Location (domain, jurisdiction, filetype)
            how: Context (document type, patterns)
            with_whom: Triangulation (associate, company)

        Returns:
            Constructed query string
        """
        return self.search_director.construct_environment_query(
            what_who, where, how, with_whom
        )

    def parse(self, query: str) -> Dict:
        """Parse compiled syntax back into components."""
        return self.parser.parse(query)

    def validate(self, query: str) -> Tuple[bool, List[str]]:
        """
        Validate a SASTRE query.

        Returns (is_valid, list_of_errors)
        """
        errors = []
        parsed = self.parse(query)

        if parsed["operator"]:
            if parsed["operator"] not in OPERATORS:
                errors.append(f"Unknown operator: {parsed['operator']}")

        if not parsed["targets"] and not parsed["chain"]:
            errors.append("Query has no targets")

        return len(errors) == 0, errors


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def compile_query(user_input: str, context: QueryContext = None) -> Dict:
    """Convenience function to compile a query."""
    compiler = SastreQueryCompiler()
    return compiler.compile(user_input, context)


def compile_triangulated_query(
    entity_name: str,
    entity_type: str = "person",
    profile_data: Optional[Dict[str, Any]] = None,
    location_data: Optional[Dict[str, Any]] = None,
    intent: str = "discover",
) -> Dict[str, Any]:
    """
    Compile queries using Entity Triangulation (Slot-Filling).

    Example:
        result = compile_triangulated_query(
            entity_name="John Smith",
            entity_type="person",
            profile_data={
                "associates": ["Jane Doe", "Bob Wilson"],
                "companies": ["Acme Corp", "Globex Inc"],
                "industry": ["finance", "banking"],
                "dob": "1975",
                "roles": ["director", "CEO"],
            },
            location_data={
                "residency_code": "uk",
                "jurisdictions": ["UK", "US"],
            },
            intent="discover"
        )

    Returns:
        Dict with anchor, queries (tiered), cascade, and metadata.
    """
    compiler = SastreQueryCompiler()
    return compiler.compile_triangulated(
        entity_name, entity_type, profile_data, location_data, intent
    )


def triangulate_entity(profile: EntityProfile) -> List[QueryResult]:
    """
    Generate triangulated queries directly from an EntityProfile.

    Example:
        profile = EntityProfile(
            full_name="John Smith",
            associates=["Jane Doe"],
            companies=["Acme Corp"],
            dob="1975",
        )
        queries = triangulate_entity(profile)
    """
    triangulator = EntityTriangulator(profile)
    return triangulator.get_minimum_viable_queries()


def get_cascade_queries(profile: EntityProfile) -> Dict[str, List[QueryResult]]:
    """
    Get queries organized by tier for fail-soft cascade execution.

    Returns dict with T1, T2, T3, T4, T5 tiers.
    Execute T1 first, then cascade down if insufficient results.
    """
    triangulator = EntityTriangulator(profile)
    return triangulator.get_cascade_queries()


def parse_query(query: str) -> Dict:
    """Convenience function to parse a query."""
    compiler = SastreQueryCompiler()
    return compiler.parse(query)


def validate_query(query: str) -> Tuple[bool, List[str]]:
    """Convenience function to validate a query."""
    compiler = SastreQueryCompiler()
    return compiler.validate(query)


def generate_person_variations(name: str) -> List[Tuple[str, int]]:
    """Generate person name variations with strength scores."""
    variator = PersonVariator()
    return variator.generate_variations_with_strength(name)


def generate_company_variations(name: str) -> List[Tuple[str, int]]:
    """Generate company name variations with strength scores."""
    variator = CompanyVariator()
    return variator.generate_variations_with_strength(name)


def generate_useful_variety(
    value: str,
    value_type: str = "person",
    max_variations: int = 15,
) -> Dict[str, List[str]]:
    """
    Generate variations using the Principle of Useful Variety.

    Balances Likelihood vs Infinity using Entropy Logic:
    - Common names → Strict variations (few, high-precision)
    - Unique names → Broad variations (more experimental)

    Args:
        value: The value to generate variations for
        value_type: "person", "company", "phone", "email", "domain"
        max_variations: Maximum variations to return

    Returns:
        Dict with "high_likelihood", "medium_likelihood", "experimental" lists

    Example:
        # For common name "John Smith" - returns fewer, stricter variations
        result = generate_useful_variety("John Smith", "person")

        # For unique name "Elon Musk" - returns more experimental variations
        result = generate_useful_variety("Elon Musk", "person")

        # For phone with Split-Segment Rule
        result = generate_useful_variety("+36301234567", "phone")
        # Returns tail segments for partial matching
    """
    generator = VarietyGenerator()
    return generator.generate_all_variations(value, value_type, max_variations)


def unified_search(
    subject: str,
    subject_type: str = "person",
    profile_data: Optional[Dict[str, Any]] = None,
    location_data: Optional[Dict[str, Any]] = None,
    document_context: Optional[str] = None,
) -> Dict[str, Any]:
    """
    SEARCH MODE: Active discovery using the Unified Search Philosophy.

    Constructs queries targeting the TEXTUAL ENVIRONMENT where
    answers would naturally appear (not the answer itself).

    Uses:
    - Entity Triangulation (Slot-Filling)
    - Variety Generation (Entropy Logic)
    - Four Dimension Query Construction (What/Who, Where, How, With Whom)
    - Environment-Aware Query Construction

    Args:
        subject: The entity to search for
        subject_type: person/company/domain/etc.
        profile_data: Known information for triangulation
            - associates: Known connections
            - companies: Affiliated companies
            - industry: Industry terms
            - dob: Date of birth
            - identifiers: {oib: "123", ssn: "456"}
            - roles: ["director", "CEO"]
        location_data: Domain/jurisdiction constraints
            - domains: ["sec.gov", "companieshouse.gov.uk"]
            - residency_code: Primary TLD
            - jurisdictions: Countries
            - years: Active years
        document_context: Expected document type
            - "corporate_filing", "news", "court_record", "registry", "sanctions"

    Returns:
        Dict with:
            - mode: "search"
            - anchor: Derived anchor term
            - queries: Tiered query list
            - variations: Grouped by likelihood
            - cascade: Queries by tier for fail-soft execution

    Example:
        result = unified_search(
            subject="John Smith",
            subject_type="person",
            profile_data={
                "associates": ["Jane Doe"],
                "companies": ["Acme Corp"],
                "roles": ["director"],
            },
            location_data={
                "domains": ["companieshouse.gov.uk"],
                "residency_code": "uk",
            },
            document_context="corporate_filing"
        )
    """
    director = UnifiedSearchDirector()
    return director.search(subject, subject_type, profile_data, location_data, document_context)


def unified_watch(
    subject: str,
    subject_type: str = "person",
    profile_data: Optional[Dict[str, Any]] = None,
    watch_domains: Optional[List[str]] = None,
    alert_keywords: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    WATCH MODE: Set up continuous monitoring for new appearances.

    Creates persistent queries for ongoing monitoring
    with alert rules for new document appearances.

    Args:
        subject: The entity to watch
        subject_type: person/company/domain/etc.
        profile_data: Known information for query construction
        watch_domains: Specific domains to monitor
        alert_keywords: Additional keywords that trigger alerts

    Returns:
        Dict with:
            - mode: "watch"
            - anchor: Derived anchor term
            - watch_queries: Queries for continuous monitoring
            - alert_rules: Conditions that trigger alerts

    Example:
        result = unified_watch(
            subject="Elon Musk",
            subject_type="person",
            watch_domains=["sec.gov", "bloomberg.com"],
            alert_keywords=["acquisition", "SEC filing", "lawsuit"]
        )
    """
    director = UnifiedSearchDirector()
    return director.watch(subject, subject_type, profile_data, watch_domains, alert_keywords)


def construct_environment_query(
    what_who: str,
    where: Optional[str] = None,
    how: Optional[str] = None,
    with_whom: Optional[str] = None,
) -> str:
    """
    Construct a query using the Four Query Dimensions.

    PHILOSOPHY: Query for the DOCUMENT that contains the answer,
    not the answer itself.

    The four dimensions:
    1. WHAT/WHO - Subject (entity name, identifier)
    2. WHERE - Location (domain, jurisdiction, filetype)
    3. HOW - Context (document type, patterns)
    4. WHO/WHAT WITH - Triangulation (associate, company)

    Args:
        what_who: Subject (entity name, identifier)
        where: Location (domain, jurisdiction, filetype)
        how: Context (document type, patterns)
        with_whom: Triangulation (associate, company)

    Returns:
        Constructed query string

    Example:
        # "Find documents about John Smith at Acme Corp in SEC filings"
        query = construct_environment_query(
            what_who="John Smith",
            where="sec.gov",
            how="director OR officer OR appointed",
            with_whom="Acme Corp"
        )
        # Returns: "John Smith" "Acme Corp" (director OR officer OR appointed) site:sec.gov
    """
    director = UnifiedSearchDirector()
    return director.construct_environment_query(what_who, where, how, with_whom)


# =============================================================================
# TODO: COUNTRY ANCHOR SEARCH INTEGRATION
# =============================================================================
#
# The file tools/query_lab/country_anchor_search.py contains jurisdiction-specific
# search logic that should be integrated with the EntityTriangulator.
#
# Integration points:
# 1. When entity profile includes jurisdiction OR user input specifies country
# 2. Hook up with JESTER/torpedo.py for corporate registry searches
# 3. Use jurisdiction to auto-fill residency_code in EntityProfile
#
# Implementation plan:
# - Import country_anchor_search functions
# - Add jurisdiction_queries() method to EntityTriangulator
# - Integrate with Torpedo.fetch_profile() for automatic enrichment
#
# For now, this works at a basic level if:
# - User input already includes jurisdiction (e.g., "chr: Podravka" for Croatia)
# - Entity profile has jurisdiction field populated
#
# See: tools/query_lab/country_anchor_search.py for full implementation
# =============================================================================


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == "__main__":
    # Create compiler
    compiler = SastreQueryCompiler()

    print("=" * 70)
    print("SASTRE QUERY COMPILER - ENTITY TRIANGULATION DEMO")
    print("=" * 70)

    # -------------------------------------------------------------------------
    # Example 1: Triangulated query with full profile
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("EXAMPLE 1: Full Profile Triangulation (John Smith)")
    print("=" * 70)

    result = compile_triangulated_query(
        entity_name="John Smith",
        entity_type="person",
        profile_data={
            "associates": ["Jane Doe", "Robert Wilson"],
            "companies": ["Acme Corporation", "Global Services Ltd"],
            "industry": ["finance", "banking"],
            "dob": "1975",
            "roles": ["director", "CEO"],
        },
        location_data={
            "residency_code": "uk",
            "jurisdictions": ["UK", "US"],
        },
        intent="discover"
    )

    print(f"\nAnchor: {result['anchor']}")
    print(f"Anchor Strength: {result['anchor_strength']}/5")
    print(f"Filled Slots: {sum(result['metadata']['filled_slots'].values())}")
    print(f"\nGenerated Queries ({len(result['queries'])}):")
    for i, q in enumerate(result['queries'][:10], 1):
        print(f"  {i}. [{q['tier']}] {q['query']}")
        print(f"      Source: {q['source']}, Quality: {q['quality_score']:.2f}")

    # -------------------------------------------------------------------------
    # Example 2: Unique surname (no first name needed)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("EXAMPLE 2: Unique Surname (Zuckerberg)")
    print("=" * 70)

    result2 = compile_triangulated_query(
        entity_name="Mark Zuckerberg",
        entity_type="person",
        profile_data={
            "companies": ["Meta", "Facebook"],
            "industry": ["technology", "social media"],
        },
    )

    print(f"\nAnchor: {result2['anchor']}")
    print(f"Anchor Strength: {result2['anchor_strength']}/5 (unique surname)")
    print(f"\nQueries:")
    for q in result2['queries'][:5]:
        print(f"  [{q['tier']}] {q['query']}")

    # -------------------------------------------------------------------------
    # Example 3: Company search
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("EXAMPLE 3: Company Search (Acme Corporation)")
    print("=" * 70)

    result3 = compile_triangulated_query(
        entity_name="Acme Corporation",
        entity_type="company",
        profile_data={
            "industry": ["manufacturing", "industrial"],
        },
        location_data={
            "residency_code": "us",
            "jurisdictions": ["US", "DE"],
        },
    )

    print(f"\nAnchor: {result3['anchor']}")
    print(f"\nQueries:")
    for q in result3['queries'][:5]:
        print(f"  [{q['tier']}] {q['query']}")

    # -------------------------------------------------------------------------
    # Example 4: Fail-Soft Cascade
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("EXAMPLE 4: Fail-Soft Cascade Structure")
    print("=" * 70)

    profile = EntityProfile(
        full_name="John Smith",
        associates=["Jane Doe"],
        companies=["Acme Corp"],
        dob="1975",
        residency_code="uk",
    )

    cascade = get_cascade_queries(profile)

    print("\nCascade Tiers (execute T1 first, cascade if insufficient results):")
    for tier, queries in cascade.items():
        if queries:
            print(f"\n  {tier} ({len(queries)} queries):")
            for q in queries[:2]:
                print(f"    - {q.q}")

    # -------------------------------------------------------------------------
    # Example 5: Natural Language Compilation (Original method)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("EXAMPLE 5: Natural Language Compilation")
    print("=" * 70)

    context = QueryContext(
        current_focus="john_smith",
        entities={
            "john_smith": Entity(
                id="john_smith",
                name="John Smith",
                entity_type=EntityType.PERSON
            ),
            "acme_corp": Entity(
                id="acme_corp",
                name="Acme Corporation",
                entity_type=EntityType.COMPANY
            ),
        }
    )

    test_queries = [
        "Who is connected to John Smith?",
        "Is John Smith linked to Acme Corporation?",
        "Check sanctions for John Smith",
    ]

    for user_query in test_queries:
        print(f"\nInput: {user_query}")
        result = compiler.compile(user_query, context)
        print(f"  Intent: {result['intent']}")
        print(f"  Primary Query: {result['primary_query']}")

    # -------------------------------------------------------------------------
    # Example 6: Variety Generation (Principle of Useful Variety)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("EXAMPLE 6: Variety Generation (Entropy Logic)")
    print("=" * 70)

    # Common name - strict variations
    common_result = generate_useful_variety("John Smith", "person")
    print(f"\nCommon Name 'John Smith' (strict variations):")
    print(f"  High Likelihood: {common_result['high_likelihood'][:3]}")
    print(f"  Medium Likelihood: {common_result['medium_likelihood'][:2]}")
    print(f"  Experimental: {common_result['experimental'][:2]}")

    # Unique name - broad variations
    unique_result = generate_useful_variety("Elon Musk", "person")
    print(f"\nUnique Name 'Elon Musk' (broader variations):")
    print(f"  High Likelihood: {unique_result['high_likelihood'][:3]}")
    print(f"  Medium Likelihood: {unique_result['medium_likelihood'][:2]}")

    # Phone with Split-Segment Rule
    phone_result = generate_useful_variety("+36301234567", "phone")
    print(f"\nPhone '+36301234567' (Split-Segment Rule):")
    print(f"  High Likelihood: {phone_result['high_likelihood'][:3]}")
    print(f"  Medium Likelihood (includes tail): {phone_result['medium_likelihood'][:2]}")

    # -------------------------------------------------------------------------
    # Example 7: Unified Search (Textual Environment Philosophy)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("EXAMPLE 7: Unified Search (Document Environment Targeting)")
    print("=" * 70)

    search_result = unified_search(
        subject="John Smith",
        subject_type="person",
        profile_data={
            "associates": ["Jane Doe"],
            "companies": ["Acme Corp"],
            "roles": ["director"],
        },
        location_data={
            "residency_code": "uk",
        },
        document_context="corporate_filing"
    )

    print(f"\nMode: {search_result['mode']}")
    print(f"Anchor: {search_result['anchor']}")
    print(f"Environment: {search_result['environment']}")
    print(f"\nTop Queries:")
    for q in search_result['queries'][:5]:
        print(f"  [{q['tier']}] {q['query']}")

    # -------------------------------------------------------------------------
    # Example 8: Unified Watch (Continuous Monitoring)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("EXAMPLE 8: Unified Watch (Continuous Monitoring)")
    print("=" * 70)

    watch_result = unified_watch(
        subject="Elon Musk",
        subject_type="person",
        watch_domains=["sec.gov", "bloomberg.com"],
        alert_keywords=["acquisition", "SEC filing", "lawsuit"]
    )

    print(f"\nMode: {watch_result['mode']}")
    print(f"Anchor: {watch_result['anchor']}")
    print(f"\nWatch Queries:")
    for wq in watch_result['watch_queries'][:4]:
        print(f"  [{wq['type']}] {wq['query']}")
    print(f"\nAlert Rules:")
    for rule in watch_result['alert_rules'][:2]:
        print(f"  - {rule['condition']}: {rule['action']}")

    # -------------------------------------------------------------------------
    # Example 9: Four Dimension Query Construction
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("EXAMPLE 9: Four Dimension Query (What/Who, Where, How, With Whom)")
    print("=" * 70)

    query = construct_environment_query(
        what_who="John Smith",
        where="sec.gov",
        how="director OR officer OR appointed",
        with_whom="Acme Corp"
    )
    print(f"\nConstructed Query: {query}")

    print("\n" + "=" * 70)
    print("QUERY COMPILER DEMO COMPLETE")
    print("=" * 70)
    print("\nAll prompts and rules available:")
    print("  - ENTITY_TRACE_PROMPT: Slot-Filling Protocol")
    print("  - VARIETY_PROMPT: Principle of Useful Variety")
    print("  - MASTER_PROMPT: Unified Search Philosophy")
    print("\nAll classes available:")
    print("  - EntityTriangulator: Surname Anchor + Slot Filling")
    print("  - VarietyGenerator: Entropy Logic variations")
    print("  - UnifiedSearchDirector: Search vs Watch modes")
    print("  - DimensionAwareQueryBuilder: LOCATION/SUBJECT dimensions")
    print("  - SastreQueryCompiler: Main entry point")
    print("=" * 70)
