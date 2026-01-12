"""
SASTRE Unified Syntax Parser

Parses the unified query syntax for both web and grid targets.

Syntax: OPERATOR :TARGET [TARGET...] [@CLASS] [##filter...] [=> #tag]

Examples:
    # Web targets
    ent? :!domain.com                    # Extract from domain
    bl? :domain.com/page!                # Backlinks to page

    # Grid targets
    ent? :!#querynode                    # Extract from node + related
    ent? :#querynode!                    # Extract from that node only
    ent? :!#query1 #query2 => #EXTRACTED # Multiple targets, tag results

    # Compare operator
    =? :#john_smith #john_j_smith        # Compare nodes
    =? :#target :@COMPANY                # Find similar companies

SINGLE SOURCES OF TRUTH (Canonical Files):
    - NODE Classes/Types: /data/SEARCH_ENGINEER/BACKEND/modules/input_output/matrix/entity_class_type_matrix.json
    - Relationships (NEXUS): /data/SEARCH_ENGINEER/BACKEND/modules/input_output/matrix/relationships.json
    - I/O Object Types: /data/SEARCH_ENGINEER/BACKEND/modules/input_output/matrix/types.json
    - Query Construction Model: /data/SEARCH_ENGINEER/BACKEND/modules/syntax/QUERY_CONSTRUCTION.md
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Tuple
from enum import Enum

from .operators import (
    OPERATOR_PATTERNS,
    get_operator,
    CLASS_HIERARCHY,
    expand_class,
    get_entity_types,
    get_filetype_extensions,
    OperatorCategory,
)


class TargetType(Enum):
    """Type of target in query."""
    WEB_DOMAIN = "web_domain"         # !domain.com (expanded)
    WEB_PAGE = "web_page"             # domain.com/page! (contracted)
    GRID_EXPANDED = "grid_expanded"   # !#nodename (node + edges)
    GRID_CONTRACTED = "grid_contracted"  # #nodename! (node only)


class NodeClass(Enum):
    """The four fundamental node classes."""
    SUBJECT = "SUBJECT"      # What you're looking for (person, company, email, phone...)
    LOCATION = "LOCATION"    # Where you're looking (domain, jurisdiction, url, address...)
    NEXUS = "NEXUS"          # Relationships (officer_of, shareholder_of, links_to...)
    NARRATIVE = "NARRATIVE"  # Documents, notes, watchers


# =============================================================================
# SUBJECT-SIDE: What you're looking for (LEFT of colon)
# =============================================================================

# Operator → SUBJECT-SIDE type mapping
OPERATOR_TO_SUBJECT_SIDE: Dict[str, str] = {
    # Entity extraction operators
    "ent?": "*",           # All entity types
    "p?": "person",
    "c?": "company",
    "e?": "email",
    "t?": "phone",
    "a?": "address",
    "u?": "username",
    # Full forms
    "@ent?": "*",
    "@entity?": "*",
    "@p?": "person",
    "@person?": "person",
    "@c?": "company",
    "@company?": "company",
    "@e?": "email",
    "@email?": "email",
    "@t?": "phone",
    "@phone?": "phone",
    "@a?": "address",
    "@address?": "address",
    "@u?": "username",
    "@username?": "username",
    # Link analysis (NEXUS relationships)
    "bl?": "backlink",
    "?bl": "backlink_domain",
    "ol?": "outlink",
    "?ol": "outlink_domain",
    "?rl": "related_domain",
    "?ipl": "ip_linked",
    "?owl": "whois_linked",
    # IO prefix operators (also SUBJECT-side)
    "p:": "person",
    "c:": "company",
    "e:": "email",
    "t:": "phone",
    "d:": "domain",
}


@dataclass
class SubjectSide:
    """
    SUBJECT-SIDE: What you're looking for (LEFT of colon).

    KU Matrix (2×2) — applies to ANY node class:
        First letter  = TYPE knowledge  (K=known, U=unknown)
        Second letter = VALUE knowledge (K=known, U=unknown)

        KK = Known Type, Known Value    (specific entity we have)
        KU = Known Type, Unknown Value  (seeking instances of known type)
        UK = Unknown Type, Known Value  (have value, need to classify)
        UU = Unknown Type, Unknown Value (net discovery)

    Examples:
        p? :!domain.com     → KU {class: SUBJECT, type: person, ku: "KU"}
        c? :UK              → KU {class: SUBJECT, type: company, ku: "KU"}
        ent? :!domain.com   → UU {class: SUBJECT, type: *, ku: "UU"}
        bl? :!domain.com    → KU {class: NEXUS, type: backlink, ku: "KU"}
    """
    node_class: NodeClass = NodeClass.SUBJECT
    node_type: str = "*"              # person, company, email, phone, backlink, etc.
    value: Optional[str] = None       # Specific value if KK or UK
    operators: List[str] = field(default_factory=list)
    ku: str = "KU"                    # KK, KU, UK, or UU

    @classmethod
    def from_operators(cls, operators: List[str], value: str = None) -> 'SubjectSide':
        """Create SubjectSide from parsed operators."""
        types = set()
        for op in operators:
            op_lower = op.lower()
            if op_lower in OPERATOR_TO_SUBJECT_SIDE:
                types.add(OPERATOR_TO_SUBJECT_SIDE[op_lower])

        # Determine node_class based on operators
        node_class = NodeClass.SUBJECT
        link_ops = {"bl?", "?bl", "ol?", "?ol", "?rl", "?ipl", "?owl"}
        if any(op.lower() in link_ops for op in operators):
            node_class = NodeClass.NEXUS

        # Determine type
        # * means type is unknown
        type_known = "*" not in types and len(types) > 0
        node_type = "*" if not type_known else (
            list(types)[0] if len(types) == 1 else ",".join(sorted(types))
        )

        # Determine KU status (2×2 matrix)
        # First letter: Type (K if specific type, U if *)
        # Second letter: Value (K if we have specific value, U if seeking)
        value_known = value is not None
        ku = ("K" if type_known else "U") + ("K" if value_known else "U")

        return cls(
            node_class=node_class,
            node_type=node_type,
            value=value,
            operators=operators,
            ku=ku
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        result = {
            "class": self.node_class.value,
            "type": self.node_type,
            "ku": self.ku  # KK, KU, UK, or UU
        }
        if self.value is not None:
            result["value"] = self.value
        return result


# =============================================================================
# LOCATION-SIDE: Where you're looking (RIGHT of colon)
# =============================================================================

@dataclass
class LocationSide:
    """
    LOCATION-SIDE: Where you're looking (RIGHT of colon).

    KU Matrix (2×2) — applies to ANY node class:
        First letter  = TYPE knowledge  (K=known, U=unknown)
        Second letter = VALUE knowledge (K=known, U=unknown)

        KK = Known Type, Known Value    (specific venue: domain.com, UK registry)
        KU = Known Type, Unknown Value  (any venue of this type)
        UK = Unknown Type, Known Value  (have target, need to classify what it is)
        UU = Unknown Type, Unknown Value (search everywhere)

    Examples:
        p? :!domain.com     → KK {class: LOCATION, type: domain, value: "domain.com", ku: "KK"}
        c? :UK              → KK {class: LOCATION, type: jurisdiction, value: "UK", ku: "KK"}
        p? :2022!           → KK {class: LOCATION, type: daterange, value: "2022", ku: "KK"}
        p? :?               → KU {class: LOCATION, type: *, value: null, ku: "UU"} (search anywhere)
    """
    node_class: NodeClass = NodeClass.LOCATION
    node_type: str = "domain"         # domain, jurisdiction, url, address, grid_node, daterange, *
    value: Optional[str] = None       # The actual target value (None if unknown)
    expanded: bool = True             # ! prefix = expanded scope
    ku: str = "KK"                    # KK, KU, UK, or UU

    @classmethod
    def from_target(cls, target: 'Target') -> 'LocationSide':
        """Create LocationSide from parsed Target."""
        # Determine if we have a value
        value_known = target.value and target.value not in ("*", "?", "")

        # Determine location type from target
        if not value_known:
            node_type = "*"
            type_known = False
        elif target.is_grid:
            node_type = "grid_node"
            type_known = True
        elif "/" in target.value:
            node_type = "url"
            type_known = True
        else:
            node_type = "domain"
            type_known = True

        # Compute KU status
        ku = ("K" if type_known else "U") + ("K" if value_known else "U")

        return cls(
            node_class=NodeClass.LOCATION,
            node_type=node_type,
            value=target.value if value_known else None,
            expanded=target.expanded,
            ku=ku
        )

    @classmethod
    def from_jurisdiction(cls, jurisdiction: str) -> 'LocationSide':
        """Create LocationSide from jurisdiction code."""
        value_known = jurisdiction and jurisdiction not in ("*", "?", "")
        ku = "KK" if value_known else "KU"  # Type is always known (jurisdiction)

        return cls(
            node_class=NodeClass.LOCATION,
            node_type="jurisdiction",
            value=jurisdiction.upper() if value_known else None,
            expanded=True,
            ku=ku
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        result = {
            "class": self.node_class.value,
            "type": self.node_type,
            "ku": self.ku  # KK, KU, UK, or UU
        }
        if self.value is not None:
            result["value"] = self.value
        return result


# =============================================================================
# NEXUS-SIDE: The relationship (MIDDLE of triad [A]-[R]-[B])
# =============================================================================

@dataclass
class NexusSide:
    """
    NEXUS-SIDE: The relationship in a triad [A]-[R]-[B].

    KU Matrix (2×2) — applies to relationships too:
        First letter  = TYPE knowledge  (K=known relationship type, U=unknown)
        Second letter = VALUE knowledge (K=known instance, U=unknown instance)

        KK = Known Type, Known Value    ("John Smith is DIRECTOR of Acme" - specific relationship)
        KU = Known Type, Unknown Value  ("Find OFFICER relationships" - seeking instances of type)
        UK = Unknown Type, Known Value  ("A x B" - we know connection exists, not what kind)
        UU = Unknown Type, Unknown Value ("Find ANY relationships")

    Examples:
        John Smith -[director_of]-> Acme    → KK (we know it's director_of, specific instance)
        ?[officer_of]? for Acme Corp        → KU (seeking officer relationships)
        John Smith x Acme Corp              → UK (unknown type, but connection known/suspected)
        ent? x ent?                         → UU (any entity, any relationship)
    """
    node_class: NodeClass = NodeClass.NEXUS
    relationship_type: str = "*"      # officer_of, director_of, shareholder_of, backlink, *, etc.
    value: Optional[str] = None       # Specific relationship instance ID if known
    party_a: Optional[str] = None     # First endpoint (if known)
    party_b: Optional[str] = None     # Second endpoint (if known)
    ku: str = "UK"                    # KK, KU, UK, or UU

    @classmethod
    def from_operator(cls, operator: str, party_a: str = None, party_b: str = None) -> 'NexusSide':
        """Create NexusSide from relationship operator."""
        # Map operators to relationship types
        rel_type_map = {
            "x": "*",                    # Unknown relationship type
            "bl?": "backlink",
            "?bl": "backlink",
            "ol?": "outlink",
            "?ol": "outlink",
            "?rl": "related_link",
            "officer_of": "officer_of",
            "director_of": "director_of",
            "shareholder_of": "shareholder_of",
            "beneficial_owner_of": "beneficial_owner_of",
        }

        op_lower = operator.lower()
        relationship_type = rel_type_map.get(op_lower, operator)

        # Determine KU status
        type_known = relationship_type != "*"
        # For relationships, value_known means we have a specific instance, not just type
        # In most queries, we're seeking relationships (value unknown)
        value_known = False  # Usually unknown in queries

        ku = ("K" if type_known else "U") + ("K" if value_known else "U")

        return cls(
            node_class=NodeClass.NEXUS,
            relationship_type=relationship_type,
            party_a=party_a,
            party_b=party_b,
            ku=ku
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        result = {
            "class": self.node_class.value,
            "type": self.relationship_type,
            "ku": self.ku  # KK, KU, UK, or UU
        }
        if self.value is not None:
            result["value"] = self.value
        if self.party_a is not None:
            result["party_a"] = self.party_a
        if self.party_b is not None:
            result["party_b"] = self.party_b
        return result


@dataclass
class HistoricalRange:
    """Historical time range specification."""
    year_start: Optional[int] = None
    year_end: Optional[int] = None
    backward_from_now: bool = False
    all_historical: bool = False

    @property
    def is_historical(self) -> bool:
        return self.year_start is not None or self.all_historical

    @property
    def is_range(self) -> bool:
        return self.year_end is not None

    def __str__(self):
        if self.all_historical:
            return "<-!"
        if not self.is_historical:
            return "current"
        if self.backward_from_now:
            return f"<-{self.year_start}!"
        if self.is_range:
            return f"{self.year_start}-{self.year_end}!"
        return f"{self.year_start}!"


@dataclass
class Target:
    """A single target (web or grid)."""
    value: str              # domain.com or node_id
    target_type: TargetType
    expanded: bool          # True = include related, False = only this

    @property
    def is_grid(self) -> bool:
        return self.target_type in (TargetType.GRID_EXPANDED, TargetType.GRID_CONTRACTED)

    @property
    def is_web(self) -> bool:
        return self.target_type in (TargetType.WEB_DOMAIN, TargetType.WEB_PAGE)


@dataclass
class DimensionFilter:
    """A dimension filter (##)."""
    dimension: str          # jurisdiction, source, filetype, state, year
    value: str              # CY, registry, pdf, unchecked, 2020
    operator: Optional[str] = None  # For comparisons: >, <, >=, <=


@dataclass
class ChainStep:
    """
    A step in a chained query pipeline.

    Chain syntax: query1 => filter/action => query2 => #result_tag
    Example: ent? "Company A" => filter jurisdiction:UK => p? => #uk_persons
    """
    step_type: str          # "query", "filter", "action", "tag"
    operators: List[str] = field(default_factory=list)  # For query steps
    target: Optional[str] = None     # For query steps
    filter_dimension: Optional[str] = None  # For filter steps
    filter_value: Optional[str] = None      # For filter steps
    action_name: Optional[str] = None       # For action steps (extract, merge, etc.)
    tag_name: Optional[str] = None          # For tag steps

    @classmethod
    def from_query(cls, operators: List[str], target: Optional[str] = None) -> 'ChainStep':
        return cls(step_type="query", operators=operators, target=target)

    @classmethod
    def from_filter(cls, dimension: str, value: str) -> 'ChainStep':
        return cls(step_type="filter", filter_dimension=dimension, filter_value=value)

    @classmethod
    def from_action(cls, action_name: str) -> 'ChainStep':
        return cls(step_type="action", action_name=action_name)

    @classmethod
    def from_tag(cls, tag_name: str) -> 'ChainStep':
        return cls(step_type="tag", tag_name=tag_name)


@dataclass
class ParsedQuery:
    """Result of parsing a unified query."""
    raw_query: str
    operators: List[str]                       # Operator symbols: ["ent?", "p?"]
    targets: List[Target]                      # All targets

    # Primary target (for backwards compat)
    primary_target: str = ""
    target_type: TargetType = TargetType.WEB_DOMAIN

    # ==========================================================================
    # SUBJECT-SIDE / LOCATION-SIDE: The core semantic split
    # ==========================================================================
    # LEFT of colon = SUBJECT-SIDE (what you're looking for)
    # RIGHT of colon = LOCATION-SIDE (where you're looking)
    subject_side: Optional[SubjectSide] = None
    location_side: Optional[LocationSide] = None

    # Flags
    is_grid_query: bool = False               # Any target is grid node
    is_compare: bool = False                  # Has =? operator
    tor_context: bool = False                 # Tor/onion context

    # Historical
    historical: HistoricalRange = field(default_factory=HistoricalRange)

    # Filters
    class_filter: Optional[str] = None        # @PERSON, @COMPANY, etc.
    dimension_filters: List[DimensionFilter] = field(default_factory=list)

    # Action chaining
    result_tag: Optional[str] = None          # => #tag (final tag)
    chain_steps: List[ChainStep] = field(default_factory=list)  # Full chain pipeline
    is_chained: bool = False                  # Has multiple steps

    # Derived from operators
    wants_extraction: bool = False
    wants_links: bool = False
    wants_enrichment: bool = False
    wants_filetype: bool = False
    entity_types: Set[str] = field(default_factory=set)
    filetype_extensions: Set[str] = field(default_factory=set)

    def __post_init__(self):
        """Compute derived fields from operators."""
        for op in self.operators:
            op_def = get_operator(op)
            if not op_def:
                continue

            if op_def.category == OperatorCategory.EXTRACTION:
                self.wants_extraction = True
            elif op_def.category == OperatorCategory.LINK_ANALYSIS:
                self.wants_links = True
            elif op_def.category == OperatorCategory.ENRICHMENT:
                self.wants_enrichment = True
            elif op_def.category == OperatorCategory.FILETYPE:
                self.wants_filetype = True
                self.filetype_extensions.update(get_filetype_extensions(op))
            elif op_def.category == OperatorCategory.COMPARE:
                self.is_compare = True

        # Entity types
        self.entity_types = get_entity_types(self.operators)

        # =======================================================================
        # Populate SUBJECT-SIDE from operators (LEFT of colon)
        # =======================================================================
        if self.operators and self.subject_side is None:
            self.subject_side = SubjectSide.from_operators(self.operators)

        # =======================================================================
        # Populate LOCATION-SIDE from primary target (RIGHT of colon)
        # =======================================================================
        if self.targets and self.location_side is None:
            self.location_side = LocationSide.from_target(self.targets[0])

        # Check dimension_filters for jurisdiction to enhance location_side
        for df in self.dimension_filters:
            if df.dimension == "jurisdiction" and self.location_side:
                # Add jurisdiction context to location_side
                self.location_side = LocationSide(
                    node_class=NodeClass.LOCATION,
                    node_type="jurisdiction",
                    value=df.value.upper(),
                    expanded=self.location_side.expanded if self.location_side else True
                )
                break

    def to_routing_context(self) -> Dict[str, Any]:
        """
        Convert to KU matrix format for routing.

        KU Matrix:
            - subject_side = UNKNOWN (what we're seeking)
            - location_side = KNOWN (context/constraint we have)

        Returns:
            {
                "unknown": {"class": "SUBJECT", "type": "person"},
                "known": {"class": "LOCATION", "type": "domain", "value": "example.com"}
            }
        """
        return {
            "unknown": self.subject_side.to_dict() if self.subject_side else None,
            "known": self.location_side.to_dict() if self.location_side else None
        }


class SyntaxParser:
    """
    Parses unified query syntax.

    Target determines scope:
    - domain.com = external web
    - #nodename = internal grid

    Position of ! determines expansion:
    - ! prefix = expand (domain/node + edges)
    - ! suffix = contract (page/node only)
    """

    def parse(self, query: str) -> Optional[ParsedQuery]:
        """Parse a unified query string."""
        query = query.strip()
        if not query:
            return None

        # Parse chain syntax: query => step => step => #tag
        chain_steps: List[ChainStep] = []
        result_tag = None
        is_chained = False
        primary_query = query

        if "=>" in query:
            is_chained = True
            segments = [s.strip() for s in query.split("=>")]

            # First segment is always the primary query
            primary_query = segments[0]

            # Parse remaining segments as chain steps
            for i, segment in enumerate(segments[1:], 1):
                step = self._parse_chain_segment(segment)
                if step:
                    # If this is the last segment and it's a tag, extract it
                    if i == len(segments) - 1 and step.step_type == "tag":
                        result_tag = step.tag_name
                    chain_steps.append(step)

        # Continue with primary query (first segment or whole query)
        query = primary_query

        # Extract dimension filters: ##jurisdiction:CY, ##2020
        dimension_filters = []
        filter_pattern = re.compile(r"##(\w+)(?::([^\s]+))?")
        for match in filter_pattern.finditer(query):
            dim = match.group(1).lower()
            val = match.group(2) or dim

            # Detect dimension type
            if re.match(r"^\d{4}$", dim):
                dimension_filters.append(DimensionFilter(dimension="year", value=dim))
            elif re.match(r"^\d{4}-\d{4}$", dim):
                dimension_filters.append(DimensionFilter(dimension="year_range", value=dim))
            else:
                dimension_filters.append(DimensionFilter(dimension=dim, value=val))

        query = filter_pattern.sub("", query).strip()

        # Extract class filter: @PERSON, @COMPANY
        class_filter = None
        class_match = re.search(r"@([A-Z]+)", query)
        if class_match:
            candidate = f"@{class_match.group(1).upper()}"
            if candidate in CLASS_HIERARCHY:
                class_filter = candidate
                query = query[:class_match.start()] + query[class_match.end():]
                query = query.strip()

        # Check for :tor/:onion context
        tor_context = False
        if query.endswith(" :tor") or query.endswith(" :onion"):
            tor_context = True
            query = re.sub(r"\s+:(tor|onion)$", "", query)

        # Check if this is a grid query
        has_grid = bool(re.search(r"[!#]#\w+|#\w+!", query))

        if has_grid:
            return self._parse_grid_query(
                query, result_tag, class_filter, dimension_filters, tor_context,
                chain_steps, is_chained
            )
        else:
            return self._parse_web_query(
                query, result_tag, class_filter, dimension_filters, tor_context,
                chain_steps, is_chained
            )

    def _parse_operators(self, operator_str: str) -> List[str]:
        """Extract operators from a string."""
        operators = []
        remaining = operator_str.strip()

        while remaining:
            remaining = remaining.strip()
            if not remaining:
                break

            matched = False
            for pattern in OPERATOR_PATTERNS:
                if remaining.lower().startswith(pattern):
                    operators.append(pattern)
                    remaining = remaining[len(pattern):]
                    matched = True
                    break

            if not matched:
                remaining = remaining[1:]  # Skip unknown char

        return operators

    def _parse_chain_segment(self, segment: str) -> Optional[ChainStep]:
        """
        Parse a single chain segment into a ChainStep.

        Segment types:
        - Tag: #tagname
        - Filter: filter dimension:value OR ##dimension:value
        - Action: action_name (merge, extract, dedupe, compare, etc.)
        - Query: operator target (p? "John Smith")
        """
        segment = segment.strip()
        if not segment:
            return None

        # Tag step: #tagname or just tagname at end
        if segment.startswith("#"):
            tag_name = segment[1:].strip()
            if re.match(r"^\w+$", tag_name):
                return ChainStep.from_tag(tag_name)

        # Filter step: filter dimension:value OR ##dimension:value
        filter_match = re.match(
            r"^(?:filter\s+)?##?(\w+):(.+)$",
            segment,
            re.IGNORECASE
        )
        if filter_match:
            return ChainStep.from_filter(
                dimension=filter_match.group(1).lower(),
                value=filter_match.group(2).strip()
            )

        # Action step: known action keywords
        action_keywords = {
            "merge", "extract", "dedupe", "compare", "enrich",
            "filter", "tag", "export", "link", "validate"
        }
        segment_lower = segment.lower()
        if segment_lower in action_keywords:
            return ChainStep.from_action(segment_lower)

        # Query step: has operator prefix (p?, c?, ent?, =?, etc.)
        operators = self._parse_operators(segment)
        if operators:
            # Extract remaining as target
            remaining = segment
            for op in operators:
                remaining = remaining.replace(op, "", 1)
            target = remaining.strip().strip('"').strip("'")
            return ChainStep.from_query(
                operators=operators,
                target=target if target else None
            )

        # Plain tag name (no # prefix) - common at end of chains
        if re.match(r"^\w+$", segment):
            return ChainStep.from_tag(segment)

        return None

    def _parse_historical(self, target_str: str) -> Tuple[HistoricalRange, str]:
        """Parse historical modifiers from target string."""
        historical = HistoricalRange()

        # All historical: <-!
        if match := re.match(r"<-!\s+(.+)", target_str):
            return HistoricalRange(all_historical=True), match.group(1)

        # Backward: <-YEAR!
        if match := re.match(r"<-(\d{4})!\s+(.+)", target_str):
            return HistoricalRange(
                year_start=int(match.group(1)),
                backward_from_now=True
            ), match.group(2)

        # Range: YEAR-YEAR!
        if match := re.match(r"(\d{4})-(\d{4})!\s+(.+)", target_str):
            return HistoricalRange(
                year_start=int(match.group(1)),
                year_end=int(match.group(2))
            ), match.group(3)

        # Single year: YEAR!
        if match := re.match(r"(\d{4})!\s+(.+)", target_str):
            return HistoricalRange(year_start=int(match.group(1))), match.group(2)

        return historical, target_str

    def _parse_web_query(
        self,
        query: str,
        result_tag: Optional[str],
        class_filter: Optional[str],
        dimension_filters: List[DimensionFilter],
        tor_context: bool,
        chain_steps: List[ChainStep] = None,
        is_chained: bool = False
    ) -> Optional[ParsedQuery]:
        """Parse a web-targeted query."""
        chain_steps = chain_steps or []

        # Split operators and target
        if ":" not in query:
            # Target-only query (implied scrape)
            target_match = re.match(r"^(<-\d{4}!|<-!|\d{4}!|\d{4}-\d{4}!)?\s*!(.+)$", query)
            if target_match:
                historical_part = target_match.group(1) or ""
                target = target_match.group(2).strip().lower()
                historical = self._parse_historical_modifier(historical_part)
                return self._build_web_result(
                    ["?scrape"], target, TargetType.WEB_DOMAIN, historical,
                    result_tag, class_filter, dimension_filters, tor_context, query,
                    chain_steps, is_chained
                )
            return None

        parts = query.split(":", 1)
        operators_str = parts[0].strip()
        target_str = parts[1].strip()

        # Parse operators
        operators = self._parse_operators(operators_str)
        if not operators:
            # Empty operators = implied scrape
            operators = ["?scrape"]

        # Parse historical from target
        historical, target_str = self._parse_historical(target_str)

        # Determine target type
        if target_str.startswith("!"):
            target_type = TargetType.WEB_DOMAIN
            target = target_str[1:].strip().lower()
        elif target_str.endswith("!"):
            target_type = TargetType.WEB_PAGE
            target = target_str[:-1].strip().lower()
        else:
            target_type = TargetType.WEB_DOMAIN
            target = target_str.lower()

        # Clean target
        target = re.sub(r"^https?://", "", target)

        # Auto-detect Tor
        if target.endswith(".onion") or ".onion/" in target:
            tor_context = True

        return self._build_web_result(
            operators, target, target_type, historical,
            result_tag, class_filter, dimension_filters, tor_context, query,
            chain_steps, is_chained
        )

    def _parse_historical_modifier(self, historical_part: str) -> HistoricalRange:
        """Parse a historical modifier string."""
        if not historical_part:
            return HistoricalRange()
        if historical_part == "<-!":
            return HistoricalRange(all_historical=True)
        if historical_part.startswith("<-"):
            year = int(historical_part[2:-1])
            return HistoricalRange(year_start=year, backward_from_now=True)
        if "-" in historical_part:
            parts = historical_part[:-1].split("-")
            return HistoricalRange(year_start=int(parts[0]), year_end=int(parts[1]))
        return HistoricalRange(year_start=int(historical_part[:-1]))

    def _build_web_result(
        self,
        operators: List[str],
        target: str,
        target_type: TargetType,
        historical: HistoricalRange,
        result_tag: Optional[str],
        class_filter: Optional[str],
        dimension_filters: List[DimensionFilter],
        tor_context: bool,
        raw_query: str,
        chain_steps: List[ChainStep] = None,
        is_chained: bool = False
    ) -> ParsedQuery:
        """Build ParsedQuery for web target."""
        expanded = target_type == TargetType.WEB_DOMAIN
        return ParsedQuery(
            raw_query=raw_query,
            operators=operators,
            targets=[Target(value=target, target_type=target_type, expanded=expanded)],
            primary_target=target,
            target_type=target_type,
            is_grid_query=False,
            tor_context=tor_context,
            historical=historical,
            class_filter=class_filter,
            dimension_filters=dimension_filters,
            result_tag=result_tag,
            chain_steps=chain_steps or [],
            is_chained=is_chained,
        )

    def _parse_grid_query(
        self,
        query: str,
        result_tag: Optional[str],
        class_filter: Optional[str],
        dimension_filters: List[DimensionFilter],
        tor_context: bool,
        chain_steps: List[ChainStep] = None,
        is_chained: bool = False
    ) -> Optional[ParsedQuery]:
        """Parse a grid-targeted query."""
        chain_steps = chain_steps or []

        if ":" not in query:
            return None

        parts = query.split(":", 1)
        operators_str = parts[0].strip()
        targets_str = parts[1].strip()

        # Parse operators
        operators = self._parse_operators(operators_str)
        if not operators:
            return None

        # Parse grid targets: !#node (expanded) or #node! (contracted)
        targets = []

        # Pattern for expanded: !#nodename
        for match in re.finditer(r"!#(\w+)", targets_str):
            targets.append(Target(
                value=match.group(1),
                target_type=TargetType.GRID_EXPANDED,
                expanded=True
            ))

        # Pattern for contracted: #nodename!
        for match in re.finditer(r"#(\w+)!", targets_str):
            # Make sure this wasn't already captured as !#
            node_id = match.group(1)
            if not any(t.value == node_id for t in targets):
                targets.append(Target(
                    value=node_id,
                    target_type=TargetType.GRID_CONTRACTED,
                    expanded=False
                ))

        # Plain #nodename (default to expanded)
        for match in re.finditer(r"(?<![!#])#(\w+)(?!!)", targets_str):
            node_id = match.group(1)
            if not any(t.value == node_id for t in targets):
                targets.append(Target(
                    value=node_id,
                    target_type=TargetType.GRID_EXPANDED,
                    expanded=True
                ))

        if not targets:
            return None

        primary = targets[0]

        return ParsedQuery(
            raw_query=query,
            operators=operators,
            targets=targets,
            primary_target=f"#{primary.value}",
            target_type=primary.target_type,
            is_grid_query=True,
            tor_context=tor_context,
            historical=HistoricalRange(),
            class_filter=class_filter,
            dimension_filters=dimension_filters,
            result_tag=result_tag,
            chain_steps=chain_steps,
            is_chained=is_chained,
        )


# Module-level parser instance
_parser = SyntaxParser()


def parse(query: str) -> Optional[ParsedQuery]:
    """Parse a unified query string."""
    return _parser.parse(query)


def is_grid_query(query: str) -> bool:
    """Quick check if query targets grid nodes."""
    return bool(re.search(r"[!#]#\w+|#\w+!", query))


def is_compare_query(query: str) -> bool:
    """Quick check if query is a compare operation."""
    return "=?" in query


def has_io_prefix(query: str) -> bool:
    """Check if query uses IO prefix syntax (p:, c:, e:, d:, t:)."""
    return bool(re.match(r"^\s*[pcedtPCEDT]:\s*", query))
