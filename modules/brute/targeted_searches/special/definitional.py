"""
Definitional Search - Type-Based Domain Discovery

Automatically queries WDC when searches contain [type] brackets.

Query Syntax:
    [restaurant] berlin          → Find restaurant sites, search for "berlin"
    [bank] de! pdf!             → German bank sites with PDFs
    [person] : [company] de!    → Extract persons from German company sites
    "annual report" : [bank]    → Search "annual report" on bank sites

Components:
    - SUBJECT (left of :) = What to find/extract (keywords, [entity types])
    - LOCATION (right of :) = WHERE to search ([site types], geo!, format!, etc.)

The : is optional. If no : is present:
    - [type] values = LOCATION (site targeting)
    - Keywords = NEXUS (what to search for)
"""

import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

MODULES_DIR = Path(__file__).resolve().parents[3]
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

# Import orchestrator and query parser
try:
    from DEFINITIONAL.orchestrator import (
        DefinitionalOrchestrator,
        LociDimension,
        GearLevel,
        OrchestrationResult,
    )
    ORCHESTRATOR_AVAILABLE = True
except ImportError:
    ORCHESTRATOR_AVAILABLE = False

# Import WDC materialization for auto-indexing discovered entities
try:
    from cymonides.scripts.wdc import (
        WDCMaterializer,
        materialize_wdc_search,
        get_canonical_id,
    )
    WDC_MATERIALIZATION_AVAILABLE = True
except ImportError:
    WDC_MATERIALIZATION_AVAILABLE = False


# =============================================================================
# QUERY PARSER
# =============================================================================

@dataclass
class ParsedQuery:
    """Parsed definitional query."""
    # SUBJECT: What to find/extract
    subject_keywords: List[str]       # Plain keywords: "annual report"
    subject_entity_types: List[str]   # Entity extraction: [person], [company]

    # LOCATION: Where to search
    loci_site_types: List[str]        # Site types: [restaurant], [bank]
    loci_geo: List[str]               # Geography: de!, us?, eu!
    loci_format: List[str]            # Format: pdf!, audio!, image!, etc.
    loci_language: List[str]          # Language: lang:de, lang:fr
    loci_temporal: List[str]          # Time: 2024!, 2020-2024
    loci_link: List[str]              # Links: ol:gov, bl:edu
    subject_link_ops: List[str]       # Subject-side link ops (e.g., bl?, ol?)

    # Raw components
    raw_query: str
    has_colon_separator: bool

    def has_loci(self) -> bool:
        """Check if query has any LOCATION constraints."""
        return bool(
            self.loci_site_types or
            self.loci_geo or
            self.loci_format or
            self.loci_language or
            self.loci_temporal or
            self.loci_link
        )

    def has_subject_extraction(self) -> bool:
        """Check if query requests entity extraction."""
        return bool(self.subject_entity_types)

    def get_search_keyword(self) -> str:
        """Get the keyword part for traditional search."""
        return " ".join(self.subject_keywords)


FORMAT_TOKENS = {
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "csv", "xml", "json", "html",
    "document", "spreadsheet", "presentation", "text", "archive", "image", "audio",
    "video", "media", "code", "file",
}
FORMAT_TOKEN_PATTERN = re.compile(
    r"\b@?(?:"
    + "|".join(sorted((re.escape(token) for token in FORMAT_TOKENS), key=len, reverse=True))
    + r")[!?]",
    re.IGNORECASE,
)


def parse_definitional_query(query: str) -> ParsedQuery:
    """
    Parse a definitional query into SUBJECT and LOCATION components.

    Syntax:
        [type]              → Bracketed = site type or entity type
        keyword             → Plain text = search keyword
        geo!                → Exclamation = exclusive geo filter (TLD)
        geo?                → Question = inclusive geo filter
        pdf!                → Format filter
        lang:de             → Language filter
        ol:gov              → Outlinks filter
        bl:edu              → Backlinks filter
        :                   → Separates SUBJECT from LOCATION

    Examples:
        "[restaurant] berlin"
            → subject_keywords=["berlin"], loci_site_types=["restaurant"]

        "[person] : [company] de!"
            → subject_entity_types=["person"], loci_site_types=["company"], loci_geo=["de"]

        "annual report : [bank] de! pdf!"
            → subject_keywords=["annual", "report"], loci_site_types=["bank"],
              loci_geo=["de"], loci_format=["pdf"]
    """
    result = ParsedQuery(
        subject_keywords=[],
        subject_entity_types=[],
        loci_site_types=[],
        loci_geo=[],
        loci_format=[],
        loci_language=[],
        loci_temporal=[],
        loci_link=[],
        subject_link_ops=[],
        raw_query=query,
        has_colon_separator=":" in query,
    )

    # Split by : if present
    if ":" in query:
        parts = query.split(":", 1)
        subject_part = parts[0].strip()
        loci_part = parts[1].strip()
    else:
        # No separator - need to infer
        subject_part = query
        loci_part = query

    # Parse SUBJECT part (left of :)
    subject_link_matches = re.findall(r'\b(bl|ol)\?\b', subject_part, re.IGNORECASE)
    for match in subject_link_matches:
        op = match.lower()
        if op == "bl":
            result.subject_link_ops.append("backlink")
        elif op == "ol":
            result.subject_link_ops.append("outlink")
    if subject_link_matches:
        subject_part = re.sub(r'\b(?:bl|ol)\?\b', '', subject_part, flags=re.IGNORECASE).strip()
    # Extract [bracketed] items as entity types to extract
    bracket_pattern = r'\[([^\]]+)\]'
    subject_brackets = re.findall(bracket_pattern, subject_part)
    for item in subject_brackets:
        item_lower = item.lower().strip()
        # Common entity types go to extraction
        if item_lower in ("person", "company", "email", "phone", "address", "organization"):
            result.subject_entity_types.append(item_lower)
        else:
            # Other [types] in SUBJECT position could be search intent
            # For now, treat as keyword
            result.subject_keywords.append(item)

    # Remove brackets from subject to get plain keywords
    subject_clean = re.sub(bracket_pattern, '', subject_part).strip()
    # Also remove quotes for phrase matching
    subject_clean = subject_clean.replace('"', '').replace("'", "")
    if subject_clean:
        result.subject_keywords.extend(subject_clean.split())

    # Parse LOCATION part (right of : or whole query if no :)
    # Extract [bracketed] items as site types
    loci_brackets = re.findall(bracket_pattern, loci_part)
    for item in loci_brackets:
        item_clean = item.strip()
        # These are site types (LOCATION) not entity types (SUBJECT)
        if item_clean.lower() not in ("person", "company", "email", "phone", "address"):
            result.loci_site_types.append(item_clean)

    # Remove brackets to parse modifiers
    loci_clean = re.sub(bracket_pattern, '', loci_part).strip()

    # Parse modifiers
    tokens = loci_clean.split()
    for token in tokens:
        token_lower = token.lower()

        # Language: lang:de, lang:en
        if token_lower.startswith("lang:"):
            result.loci_language.append(token_lower.replace("lang:", ""))
            continue

        # Outlinks: ol:gov, ol:edu
        if token_lower.startswith("ol:"):
            result.loci_link.append(f"outlink:{token_lower.replace('ol:', '')}")
            continue

        # Backlinks: bl:gov, bl:edu
        if token_lower.startswith("bl:"):
            result.loci_link.append(f"backlink:{token_lower.replace('bl:', '')}")
            continue

        # Geo with ! or ? modifier: de!, us?, eu!
        if token_lower.endswith("!") or token_lower.endswith("?"):
            value = token_lower[:-1]
            if value.startswith("@"):
                value = value[1:]
            # Check if it's a format token (pdf, audio, image, etc.)
            if value in FORMAT_TOKENS:
                result.loci_format.append(value)
            elif len(value) <= 3 and value.isalpha():
                # Geo codes (de, us)
                result.loci_geo.append(value)
            elif value.isdigit() and len(value) == 4:
                # Year: 2024!
                result.loci_temporal.append(value)
            continue

        # Temporal range: 2020-2024
        if re.match(r'^\d{4}-\d{4}$', token_lower):
            result.loci_temporal.append(token_lower)
            continue

    return result


def build_loci_dimensions(parsed: ParsedQuery) -> List[LociDimension]:
    """Convert parsed query to LociDimension objects for orchestrator."""
    dimensions = []

    # Site types → domcat:site_type
    for site_type in parsed.loci_site_types:
        dimensions.append(LociDimension(
            dimension="domcat",
            subdimension="site_type",
            value=site_type,
            exclusive=True,
        ))

    # Geo → geo dimension
    for geo in parsed.loci_geo:
        dimensions.append(LociDimension(
            dimension="geo",
            value=geo,
            exclusive=True,
        ))

    # Format → format dimension
    for fmt in parsed.loci_format:
        dimensions.append(LociDimension(
            dimension="format",
            value=fmt,
            exclusive=True,
        ))

    # Language → lang dimension (uses WDC)
    for lang in parsed.loci_language:
        dimensions.append(LociDimension(
            dimension="lang",
            value=lang,
            exclusive=True,
        ))

    # Temporal → temp dimension
    for temp in parsed.loci_temporal:
        dimensions.append(LociDimension(
            dimension="temp",
            value=temp,
            exclusive=True,
        ))

    # Links → link dimension
    for link in parsed.loci_link:
        if link.startswith("outlink:"):
            dimensions.append(LociDimension(
                dimension="link",
                subdimension="outlinks",
                value=link.replace("outlink:", ""),
            ))
        elif link.startswith("backlink:"):
            dimensions.append(LociDimension(
                dimension="link",
                subdimension="backlinks",
                value=link.replace("backlink:", ""),
            ))

    return dimensions


# =============================================================================
# DEFINITIONAL SEARCHER
# =============================================================================

class DefinitionalSearcher:
    """
    Definitional search with automatic WDC integration.

    When queries contain [type] brackets, automatically:
    1. Parses query into SUBJECT and LOCATION
    2. Queries WDC for matching domains (site types)
    3. Applies geo/format/link filters
    4. Optionally extracts entities from results
    5. Materializes discovered entities to Cymonides-1

    Usage:
        searcher = DefinitionalSearcher()
        result = await searcher.search("[restaurant] berlin de!")
        # Returns German restaurant domains + search results
    """

    def __init__(
        self,
        auto_materialize: bool = True,
        project_id: str = "default",
    ):
        self.auto_materialize = auto_materialize
        self.project_id = project_id
        self._orchestrator = None

    def _get_orchestrator(self) -> Optional[DefinitionalOrchestrator]:
        """Lazy-load orchestrator."""
        if not ORCHESTRATOR_AVAILABLE:
            return None
        if self._orchestrator is None:
            self._orchestrator = DefinitionalOrchestrator()
        return self._orchestrator

    async def search(
        self,
        query: str,
        max_results: int = 50,
        gear_level: str = "L2",
        extract_entities: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute definitional search.

        Args:
            query: Query with optional [type] brackets and modifiers
            max_results: Maximum results to return
            gear_level: "L1" (fast), "L2" (balanced), "L3" (thorough)
            extract_entities: Whether to extract entities from results

        Returns:
            {
                "results": [...],           # Search results (domains/URLs)
                "domains": [...],           # Discovered domains
                "entities": [...],          # Extracted entities (if enabled)
                "materialized": [...],      # Node IDs (if auto_materialize)
                "parsed_query": {...},      # Query breakdown
                "plan_explanation": "...",  # Execution plan
                "stats": {...},             # Execution statistics
            }
        """
        # Parse query
        parsed = parse_definitional_query(query)

        result = {
            "results": [],
            "domains": [],
            "entities": [],
            "materialized": [],
            "expanded_query": query,
            "parsed_query": {
                "subject_keywords": parsed.subject_keywords,
                "subject_entity_types": parsed.subject_entity_types,
                "subject_link_ops": parsed.subject_link_ops,
                "loci_site_types": parsed.loci_site_types,
                "loci_geo": parsed.loci_geo,
                "loci_format": parsed.loci_format,
                "loci_language": parsed.loci_language,
                "loci_link": parsed.loci_link,
                "has_loci": parsed.has_loci(),
            },
            "plan_explanation": "",
            "stats": {},
        }

        # If no LOCATION constraints, fall back to basic search
        if not parsed.has_loci():
            result["stats"]["mode"] = "keyword_only"
            result["expanded_query"] = parsed.get_search_keyword()
            return result

        # Get orchestrator
        orchestrator = self._get_orchestrator()
        if not orchestrator:
            result["stats"]["error"] = "Orchestrator not available"
            return result

        # Convert to LOCATION dimensions
        dimensions = build_loci_dimensions(parsed)

        # Map gear level
        gear_map = {
            "L1": GearLevel.L1,
            "L2": GearLevel.L2,
            "L3": GearLevel.L3,
        }
        gear = gear_map.get(gear_level, GearLevel.L2)

        # Build execution plan
        plan = orchestrator.build_plan(dimensions, gear_level=gear)
        result["plan_explanation"] = orchestrator.explain_plan(plan)

        # Execute plan
        extraction_types = parsed.subject_entity_types if extract_entities else None
        keyword = parsed.get_search_keyword() or None

        orch_result: OrchestrationResult = await orchestrator.execute_plan(
            plan=plan,
            keyword=keyword,
            extraction_types=extraction_types,
        )

        # Populate results
        result["results"] = orch_result.results[:max_results]
        result["domains"] = orch_result.domains_discovered[:max_results]
        result["entities"] = orch_result.entities_extracted
        result["stats"] = orch_result.stats
        result["stats"]["errors"] = orch_result.errors

        # Auto-materialize discovered entities to Cymonides-1
        if self.auto_materialize and WDC_MATERIALIZATION_AVAILABLE and orch_result.entities_extracted:
            materialized_ids = await self._materialize_entities(
                entities=orch_result.entities_extracted,
                discovery_query=query,
            )
            result["materialized"] = materialized_ids

        return result

    async def _materialize_entities(
        self,
        entities: List[Dict[str, Any]],
        discovery_query: str,
    ) -> List[str]:
        """Materialize extracted entities to Cymonides-1."""
        if not entities:
            return []

        # Convert to WDC-style format for materialization
        wdc_entities = []
        for entity in entities:
            wdc_entities.append({
                "name": entity.get("title") or entity.get("snippet", "")[:100],
                "type": entity.get("entity_type", "entity"),
                "source_url": entity.get("url", ""),
                "source_domain": entity.get("domain", ""),
            })

        try:
            from cymonides.scripts.wdc import materialize_wdc_search

            result = await materialize_wdc_search(
                wdc_results=wdc_entities,
                project_id=self.project_id,
                discovery_query=discovery_query,
                relevance_threshold=0.5,  # Lower threshold for search results
                extract_edges=True,
            )
            return result.materialized
        except Exception as e:
            return []

    def parse_query(self, query: str) -> Dict[str, Any]:
        """
        Parse query without executing (for UI preview).

        Returns breakdown of SUBJECT and LOCATION components.
        """
        parsed = parse_definitional_query(query)
        dimensions = build_loci_dimensions(parsed)

        return {
            "subject": {
                "keywords": parsed.subject_keywords,
                "entity_types": parsed.subject_entity_types,
                "link_ops": parsed.subject_link_ops,
            },
            "loci": {
                "site_types": parsed.loci_site_types,
                "geo": parsed.loci_geo,
                "format": parsed.loci_format,
                "language": parsed.loci_language,
                "temporal": parsed.loci_temporal,
                "link": parsed.loci_link,
            },
            "dimensions": [
                {
                    "dimension": d.dimension,
                    "subdimension": d.subdimension,
                    "value": d.value,
                    "exclusive": d.exclusive,
                }
                for d in dimensions
            ],
            "has_loci": parsed.has_loci(),
            "has_extraction": parsed.has_subject_extraction(),
            "search_keyword": parsed.get_search_keyword(),
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def definitional_search(
    query: str,
    max_results: int = 50,
    project_id: str = "default",
    auto_materialize: bool = True,
) -> Dict[str, Any]:
    """
    Convenience function for definitional search.

    Usage:
        from brute.targeted_searches.special.definitional import definitional_search

        result = await definitional_search("[restaurant] berlin de!")
        print(f"Found {len(result['domains'])} German restaurant domains")
    """
    searcher = DefinitionalSearcher(
        auto_materialize=auto_materialize,
        project_id=project_id,
    )
    return await searcher.search(query, max_results=max_results)


def is_definitional_query(query: str) -> bool:
    """
    Quick check if a query should use definitional search.

    Returns True if query contains [type] brackets or LOCATION modifiers.
    """
    # Has [bracketed] type
    if re.search(r'\[[^\]]+\]', query):
        return True

    # Has format modifier (audio!, image!, pdf!, etc.)
    if FORMAT_TOKEN_PATTERN.search(query):
        return True

    # Has geo modifier (de!, us?, etc.)
    if re.search(r'\b[a-z]{2,3}[!?]', query, re.IGNORECASE):
        return True

    # Has lang: prefix
    if "lang:" in query.lower():
        return True

    # Has link prefix (ol:, bl:)
    if re.search(r'\b(ol|bl):', query, re.IGNORECASE):
        return True

    return False
