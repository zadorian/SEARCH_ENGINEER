"""
SASTRE Intent Translator

Translates natural language intents into unified query syntax.
The agent is fluent in the language but ignorant of the machinery.

USER: "Find offshore companies connected to John Smith"
         ↓
AGENT: Translates intent to syntax
         ↓
SYNTAX: "John Smith" AND #OFFSHORE => ent? => registry?
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Set
from enum import Enum
import re


class QueryIntentType(Enum):
    """Categories of investigation intent."""
    EXTRACT = "extract"           # Extract entities from sources
    LINK_ANALYSIS = "link"        # Find backlinks/outlinks
    ENRICH = "enrich"             # Fill entity slots
    DISCOVER = "discover"         # Find new entities/sources
    COMPARE = "compare"           # Compare/similarity search
    FILTER = "filter"             # Filter existing data
    TAG = "tag"                   # Tag/categorize nodes


@dataclass
class TranslatedQuery:
    """Result of translating intent to syntax."""
    syntax: str                   # The query syntax
    intent: QueryIntentType            # Detected intent type
    operators: List[str]          # Operators used
    targets: List[str]            # Targets (web or grid)
    filters: List[str]            # Dimension filters
    result_tag: Optional[str]     # Tag for results
    explanation: str              # Why this translation
    alternatives: List[str] = field(default_factory=list)  # Alternative syntaxes


class IntentTranslator:
    """
    Translates natural language investigation intents to query syntax.

    The translator recognizes patterns in user requests and maps them
    to the appropriate operators and syntax structure.
    """

    # Pattern → Intent mappings
    INTENT_PATTERNS: Dict[str, QueryIntentType] = {
        # Extract patterns
        r"extract|find (people|persons|names|companies|emails|phones)": QueryIntentType.EXTRACT,
        r"who (is|are|appears|mentioned)": QueryIntentType.EXTRACT,
        r"what (companies|entities|people)": QueryIntentType.EXTRACT,

        # Link analysis patterns
        r"(backlinks?|inbound|referring|linking) (to|from)": QueryIntentType.LINK_ANALYSIS,
        r"(outlinks?|outbound|external)": QueryIntentType.LINK_ANALYSIS,
        r"who links to": QueryIntentType.LINK_ANALYSIS,
        r"where does .* link": QueryIntentType.LINK_ANALYSIS,

        # Enrichment patterns
        r"enrich|fill|complete|lookup": QueryIntentType.ENRICH,
        r"check (sanctions|registry|whois)": QueryIntentType.ENRICH,
        r"(sanctions?|pep|watchlist) (check|screening)": QueryIntentType.ENRICH,
        r"corporate (registry|records)": QueryIntentType.ENRICH,

        # Discovery patterns
        r"find (new|more|additional|related)": QueryIntentType.DISCOVER,
        r"discover|search for|look for": QueryIntentType.DISCOVER,
        r"what else|who else": QueryIntentType.DISCOVER,

        # Compare patterns
        r"(are|is) .* (same|identical|different)": QueryIntentType.COMPARE,
        r"compare|similarity|similar to": QueryIntentType.COMPARE,
        r"match|duplicate|merge": QueryIntentType.COMPARE,
        r"cluster|group by": QueryIntentType.COMPARE,

        # Filter patterns
        r"filter|only|just|limit to": QueryIntentType.FILTER,
        r"in (cyprus|panama|bvi|cayman)": QueryIntentType.FILTER,
        r"from (year|\d{4})": QueryIntentType.FILTER,

        # Tag patterns
        r"tag|mark|label|categorize": QueryIntentType.TAG,
    }

    # Entity type keywords → operators
    ENTITY_KEYWORDS: Dict[str, str] = {
        "person": "p?",
        "people": "p?",
        "persons": "p?",
        "names": "p?",
        "individuals": "p?",
        "company": "c?",
        "companies": "c?",
        "corporations": "c?",
        "firms": "c?",
        "organizations": "c?",
        "email": "e?",
        "emails": "e?",
        "phone": "t?",
        "phones": "t?",
        "telephone": "t?",
        "telephones": "t?",
        "address": "a?",
        "addresses": "a?",
        "location": "a?",
        "entity": "ent?",
        "entities": "ent?",
        "all": "ent?",
        "everything": "ent?",
    }

    # Jurisdiction keywords → filters
    JURISDICTION_KEYWORDS: Dict[str, str] = {
        "cyprus": "CY",
        "cypriot": "CY",
        "panama": "PA",
        "panamanian": "PA",
        "bvi": "VG",
        "british virgin islands": "VG",
        "cayman": "KY",
        "caymans": "KY",
        "cayman islands": "KY",
        "delaware": "US-DE",
        "nevada": "US-NV",
        "uk": "GB",
        "british": "GB",
        "seychelles": "SC",
        "malta": "MT",
        "luxembourg": "LU",
        "ireland": "IE",
        "jersey": "JE",
        "guernsey": "GG",
        "isle of man": "IM",
        "netherlands": "NL",
        "switzerland": "CH",
        "liechtenstein": "LI",
        "monaco": "MC",
        "singapore": "SG",
        "hong kong": "HK",
        "dubai": "AE",
        "uae": "AE",
    }

    # Offshore jurisdiction set
    OFFSHORE_JURISDICTIONS: Set[str] = {
        "PA", "VG", "KY", "SC", "JE", "GG", "IM", "LI", "MC", "BZ", "AN",
    }

    def translate(self, intent: str, context: Optional[Dict[str, Any]] = None) -> TranslatedQuery:
        """
        Translate natural language intent to query syntax.

        Args:
            intent: Natural language description of what to do
            context: Optional context (current entities, project state, etc.)

        Returns:
            TranslatedQuery with syntax and explanation
        """
        intent_lower = intent.lower().strip()
        context = context or {}

        # Detect intent type
        intent_type = self._detect_intent_type(intent_lower)

        # Extract target entities/domains
        targets = self._extract_targets(intent_lower, context)

        # Extract filters
        filters = self._extract_filters(intent_lower)

        # Determine operators
        operators = self._determine_operators(intent_lower, intent_type)

        # Extract result tag if mentioned
        result_tag = self._extract_result_tag(intent_lower)

        # Build syntax
        syntax = self._build_syntax(operators, targets, filters, result_tag)

        # Generate explanation
        explanation = self._generate_explanation(intent_type, operators, targets, filters)

        # Generate alternatives
        alternatives = self._generate_alternatives(intent_type, operators, targets, filters)

        return TranslatedQuery(
            syntax=syntax,
            intent=intent_type,
            operators=operators,
            targets=targets,
            filters=filters,
            result_tag=result_tag,
            explanation=explanation,
            alternatives=alternatives,
        )

    def _detect_intent_type(self, intent: str) -> QueryIntentType:
        """Detect the primary intent type from natural language."""
        for pattern, intent_type in self.INTENT_PATTERNS.items():
            if re.search(pattern, intent, re.IGNORECASE):
                return intent_type

        # Default to discover if unclear
        return QueryIntentType.DISCOVER

    def _extract_targets(self, intent: str, context: Dict[str, Any]) -> List[str]:
        """Extract targets (domains, node references) from intent."""
        targets = []

        # Extract quoted strings (entity names)
        for match in re.finditer(r'"([^"]+)"', intent):
            targets.append(match.group(1))

        for match in re.finditer(r"'([^']+)'", intent):
            targets.append(match.group(1))

        # Extract #node references
        for match in re.finditer(r"#(\w+)", intent):
            targets.append(f"#{match.group(1)}")

        # Extract domain-like patterns
        for match in re.finditer(r"(?:on|from|to)\s+(\w+\.\w+(?:\.\w+)?)", intent):
            targets.append(match.group(1))

        # Extract URLs
        for match in re.finditer(r"https?://[^\s]+", intent):
            url = match.group(0)
            # Clean to domain
            domain = re.sub(r"^https?://", "", url).split("/")[0]
            targets.append(domain)

        # Use context if no targets found
        if not targets and "current_entity" in context:
            targets.append(f"#{context['current_entity']}")

        return targets

    def _extract_filters(self, intent: str) -> List[str]:
        """Extract dimension filters from intent."""
        filters = []

        # Jurisdiction filters
        for keyword, code in self.JURISDICTION_KEYWORDS.items():
            if keyword in intent.lower():
                filters.append(f"##jurisdiction:{code}")
                break

        # Offshore keyword
        if "offshore" in intent.lower():
            filters.append("##offshore")

        # Year filters
        year_match = re.search(r"(in|from|during|year)\s*(\d{4})", intent)
        if year_match:
            filters.append(f"##{year_match.group(2)}")

        # Year range
        range_match = re.search(r"(\d{4})\s*-\s*(\d{4})", intent)
        if range_match:
            filters.append(f"##{range_match.group(1)}-{range_match.group(2)}")

        # State filters
        if "unchecked" in intent.lower():
            filters.append("##unchecked")
        if "unverified" in intent.lower():
            filters.append("##unverified")
        if "flagged" in intent.lower():
            filters.append("##flagged")

        # Limit filter
        limit_match = re.search(r"(top|first|limit)\s*(\d+)", intent)
        if limit_match:
            filters.append(f"##limit:{limit_match.group(2)}")

        return filters

    def _determine_operators(self, intent: str, intent_type: QueryIntentType) -> List[str]:
        """Determine which operators to use based on intent."""
        operators = []

        # Extract entity operators from keywords
        for keyword, op in self.ENTITY_KEYWORDS.items():
            if keyword in intent.lower():
                if op not in operators:
                    operators.append(op)
                break

        # Add operators based on intent type
        if intent_type == QueryIntentType.LINK_ANALYSIS:
            if "backlink" in intent.lower() or "referring" in intent.lower() or "inbound" in intent.lower():
                if "domain" in intent.lower():
                    operators.append("?bl")
                else:
                    operators.append("bl?")
            elif "outlink" in intent.lower() or "outbound" in intent.lower():
                if "domain" in intent.lower():
                    operators.append("?ol")
                else:
                    operators.append("ol?")

        elif intent_type == QueryIntentType.ENRICH:
            if "sanction" in intent.lower() or "pep" in intent.lower() or "watchlist" in intent.lower():
                operators.append("sanctions?")
            elif "registry" in intent.lower() or "corporate" in intent.lower():
                operators.append("registry?")
            elif "whois" in intent.lower() or "domain registration" in intent.lower():
                operators.append("whois?")
            else:
                operators.append("enrich?")

        elif intent_type == QueryIntentType.COMPARE:
            operators.append("=?")

        # Default to ent? if no operators determined
        if not operators and intent_type in (QueryIntentType.EXTRACT, QueryIntentType.DISCOVER):
            operators.append("ent?")

        return operators

    def _extract_result_tag(self, intent: str) -> Optional[str]:
        """Extract result tag if mentioned."""
        # Explicit tag syntax
        tag_match = re.search(r"=>\s*#?(\w+)", intent)
        if tag_match:
            return tag_match.group(1)

        # "tag as X" or "mark as X"
        mark_match = re.search(r"(?:tag|mark|label)\s+(?:as|with)\s+#?(\w+)", intent)
        if mark_match:
            return mark_match.group(1)

        return None

    def _build_syntax(
        self,
        operators: List[str],
        targets: List[str],
        filters: List[str],
        result_tag: Optional[str]
    ) -> str:
        """Build the query syntax string."""
        parts = []

        # Operators
        parts.append(" ".join(operators))

        # Colon separator
        parts.append(":")

        # Targets
        target_strs = []
        for target in targets:
            if target.startswith("#"):
                target_strs.append(f"!{target}")  # Grid expanded by default
            else:
                target_strs.append(f"!{target}")  # Web expanded by default
        parts.append(" ".join(target_strs))

        # Filters
        if filters:
            parts.append(" ".join(filters))

        # Result tag
        if result_tag:
            parts.append(f"=> #{result_tag}")

        return " ".join(parts)

    def _generate_explanation(
        self,
        intent_type: QueryIntentType,
        operators: List[str],
        targets: List[str],
        filters: List[str]
    ) -> str:
        """Generate human-readable explanation of the translation."""
        op_names = {
            "ent?": "extract all entities",
            "p?": "extract persons",
            "c?": "extract companies",
            "e?": "extract emails",
            "t?": "extract phones",
            "a?": "extract addresses",
            "bl?": "find backlink pages",
            "?bl": "find backlink domains",
            "ol?": "find outlink pages",
            "?ol": "find outlink domains",
            "enrich?": "enrich entity data",
            "sanctions?": "check sanctions lists",
            "registry?": "check corporate registries",
            "whois?": "lookup domain registration",
            "=?": "compare/find similar",
        }

        op_str = ", ".join(op_names.get(op, op) for op in operators)
        target_str = ", ".join(targets)
        filter_str = " with filters: " + ", ".join(filters) if filters else ""

        return f"Will {op_str} from {target_str}{filter_str}"

    def _generate_alternatives(
        self,
        intent_type: QueryIntentType,
        operators: List[str],
        targets: List[str],
        filters: List[str]
    ) -> List[str]:
        """Generate alternative syntax options."""
        alternatives = []

        # Suggest contracted scope
        if targets and not any(t.startswith("#") for t in targets):
            alt_targets = [f"{t}/!" if not t.endswith("/") else t for t in targets]
            alt = f"{' '.join(operators)} :{' '.join(alt_targets)}"
            alternatives.append(f"{alt}  # Page-level instead of domain")

        # Suggest different entity operators
        if "ent?" in operators:
            for specific_op in ["p?", "c?", "e?"]:
                alt = f"{specific_op} :{' '.join(f'!{t}' for t in targets)}"
                alternatives.append(f"{alt}  # Specific entity type")

        return alternatives[:3]  # Limit to 3 alternatives


# Translation examples for agent reference
TRANSLATION_EXAMPLES: Dict[str, str] = {
    "Find people mentioned on this domain": "p? :!domain.com",
    "Extract all entities from the source": "ent? :!#source",
    "What companies are connected to John Smith": 'c? :"John Smith"',
    "Check sanctions for this person": "sanctions? :!#person",
    "Find backlinks to this domain": "bl? :!domain.com",
    "What domains link to us": "?bl :!domain.com",
    "Are these the same person?": "=? :#john_smith #john_j_smith",
    "Find similar companies in Cyprus": "=? :#target :@COMPANY ##jurisdiction:CY",
    "Extract entities from unchecked sources": "ent? :!#query ##unchecked",
    "Tag offshore companies": "@COMPANY ##offshore => #OFFSHORE",
    "Find companies similar to this shell": "=? :#shell :@COMPANY ##unlinked",
    "What entities appear in both queries": "=? :#query1 #query2 :@SUBJECT ##bridge",
}


# Module-level translator instance
_translator = IntentTranslator()


def translate(intent: str, context: Optional[Dict[str, Any]] = None) -> TranslatedQuery:
    """Translate natural language intent to query syntax."""
    return _translator.translate(intent, context)


def get_examples() -> Dict[str, str]:
    """Get translation examples for agent reference."""
    return TRANSLATION_EXAMPLES.copy()
