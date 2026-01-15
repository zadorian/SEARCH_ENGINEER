"""
SASTRE Syntax Module

Unified query syntax for web and grid targets.

Syntax: OPERATOR :TARGET [TARGET...] [@CLASS] [##filter...] [=> #tag]

Target determines scope:
- domain.com = external web
- #nodename = internal grid

Position of ! determines expansion:
- ! prefix = expand (domain/node + edges)
- ! suffix = contract (page/node only)
"""

# Parser
from .parser import (
    parse,
    is_grid_query,
    is_compare_query,
    has_io_prefix,
    ParsedQuery,
    Target,
    TargetType,
    HistoricalRange,
    DimensionFilter,
    SyntaxParser,
    # KU Matrix classification (applies to ALL node classes)
    NodeClass,
    SubjectSide,
    LocationSide,
    NexusSide,
    OPERATOR_TO_SUBJECT_SIDE,
    # Operator type enum for execution routing
    OperatorType,
)

# Translator
from .translator import (
    translate,
    get_examples,
    TranslatedQuery,
    QueryIntentType,
    IntentTranslator,
    TRANSLATION_EXAMPLES,
)

# KU Router (Known/Unknown matrix routing)
from .ku_router import (
    KURouter,
    UnknownNode,
    KnownNode,
    RoutingAction,
    route_ku,
    get_ku_router,
    get_intent,
)

# Operators
from .operators import (
    # Definitions
    OperatorDef,
    OperatorCategory,
    ResultGranularity,
    OPERATORS,
    OPERATOR_PATTERNS,
    CLASS_HIERARCHY,
    FILETYPE_EXTENSIONS,
    ENTITY_OPERATOR_TO_TYPE,
    ENTITY_ALL_TYPES,
    VALID_CLASS_REFERENCES,
    CLASS_REMINDER,
    # Functions
    get_operator,
    get_operators_by_category,
    get_applicable_operators,
    expand_class,
    operator_applies_to,
    get_filetype_extensions,
    get_entity_types,
    # Validation
    validate_class,
    validate_chain,
)


__all__ = [
    # Parser
    "parse",
    "is_grid_query",
    "is_compare_query",
    "has_io_prefix",
    "ParsedQuery",
    "Target",
    "TargetType",
    "HistoricalRange",
    "DimensionFilter",
    "SyntaxParser",
    # KU Matrix (2×2 applies to ALL node classes: SUBJECT, LOCATION, NEXUS, NARRATIVE)
    # KK = Known Type, Known Value
    # KU = Known Type, Unknown Value
    # UK = Unknown Type, Known Value
    # UU = Unknown Type, Unknown Value
    "NodeClass",
    "SubjectSide",
    "LocationSide",
    "NexusSide",
    "OPERATOR_TO_SUBJECT_SIDE",
    # Operator type enum for execution routing
    "OperatorType",
    # KU Router (Known/Unknown matrix)
    "KURouter",
    "UnknownNode",
    "KnownNode",
    "RoutingAction",
    "route_ku",
    "get_ku_router",
    "get_intent",
    # Translator
    "translate",
    "get_examples",
    "TranslatedQuery",
    "QueryIntentType",
    "IntentTranslator",
    "TRANSLATION_EXAMPLES",
    # Operators
    "OperatorDef",
    "OperatorCategory",
    "ResultGranularity",
    "OPERATORS",
    "OPERATOR_PATTERNS",
    "CLASS_HIERARCHY",
    "FILETYPE_EXTENSIONS",
    "ENTITY_OPERATOR_TO_TYPE",
    "ENTITY_ALL_TYPES",
    "get_operator",
    "get_operators_by_category",
    "get_applicable_operators",
    "expand_class",
    "operator_applies_to",
    "get_filetype_extensions",
    "get_entity_types",
    # Validation
    "VALID_CLASS_REFERENCES",
    "CLASS_REMINDER",
    "validate_class",
    "validate_chain",
]
