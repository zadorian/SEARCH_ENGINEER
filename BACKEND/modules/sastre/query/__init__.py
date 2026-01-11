"""
SASTRE Query Module - Query construction, MACRO parsing, corpus checking.
"""

from .constructor import (
    QueryConstructor,
    construct_query_from_gap,
)

from .macro import (
    MacroParser,
    ParsedMacro,
    parse_macro,
    macro_to_query_string,
    build_macro,
)

from .corpus import (
    CorpusChecker,
    CorpusCheckResult,
    CorpusHit,
)

from .lab import (
    QueryLab,
    QueryLabInput,
    QueryLabResult,
    # Axis-aware dimension types
    Axis,
    LocationDimension,
    SubjectDimension,
    FuseVerdict,
    DimensionScore,
    AxisScore,
    MatchResult,
    TestResult,
    FuseResult,
)

from .variations import (
    VariationGenerator,
    generate_name_variations,
    generate_company_variations,
    expand_free_ors,
)

__all__ = [
    'QueryConstructor',
    'construct_query_from_gap',
    'MacroParser',
    'ParsedMacro',
    'parse_macro',
    'macro_to_query_string',
    'build_macro',
    'CorpusChecker',
    'CorpusCheckResult',
    'CorpusHit',
    'QueryLab',
    'QueryLabInput',
    'QueryLabResult',
    # Axis-aware dimension types
    'Axis',
    'LocationDimension',
    'SubjectDimension',
    'FuseVerdict',
    'DimensionScore',
    'AxisScore',
    'MatchResult',
    'TestResult',
    'FuseResult',
    'VariationGenerator',
    'generate_name_variations',
    'generate_company_variations',
    'expand_free_ors',
]
