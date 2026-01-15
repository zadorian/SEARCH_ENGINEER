"""
Search_Engineer Centralized Filtering System

Filtering is now entity-based via PACMAN extraction:
- filter_by_location() - filter by jurisdiction ISO codes
- filter_by_person() - filter by person name
- filter_by_company() - filter by company name
- filter_by_date_range() - filter by temporal period
- filter_has_identifiers() - filter by LEI, IBAN, etc.
"""

# Core components - required
from .core.filter_manager import FilterManager
from .core.base_filter import BaseFilter
from .core.result_processor import ResultProcessor

# Import specialized filters that exist
try:
    from .filters.duplicate_filter import DuplicateFilter
except ImportError:
    DuplicateFilter = None

try:
    from .filters.domain_filter import DomainFilter
except ImportError:
    DomainFilter = None

try:
    from .filters.exact_phrase_filter import ExactPhraseFilter
except ImportError:
    ExactPhraseFilter = None

# Import ranking components
try:
    from .ranking.hybrid_ranker import HybridRanker
except ImportError:
    HybridRanker = None

try:
    from .ranking.scoring_engine import ScoringEngine
except ImportError:
    ScoringEngine = None

try:
    from .ranking.tier_classifier import TierClassifier
except ImportError:
    TierClassifier = None

# Import configuration
try:
    from .config.filter_config import FilterProfile
except ImportError:
    FilterProfile = None

try:
    from .config.scoring_profiles import ScoringProfile
except ImportError:
    ScoringProfile = None

# PACMAN-based entity filters (the real filtering)
try:
    from ..pacman_processor import (
        filter_by_location,
        filter_by_person,
        filter_by_company,
        filter_by_date_range,
        filter_has_identifiers,
        filter_has_company_numbers,
        filter_by_designation,
        filter_by_semantic_concept,
        filter_by_red_flag_category,
        get_result_entities,
    )
    ENTITY_FILTERS_AVAILABLE = True
except ImportError:
    ENTITY_FILTERS_AVAILABLE = False
    filter_by_location = None
    filter_by_person = None
    filter_by_company = None
    filter_by_date_range = None
    filter_has_identifiers = None
    filter_has_company_numbers = None
    filter_by_designation = None
    filter_by_semantic_concept = None
    filter_by_red_flag_category = None
    get_result_entities = None

__version__ = "1.1.0"

# Export main interface
__all__ = [
    # Core
    'FilterManager',
    'BaseFilter',
    'ResultProcessor',
    # Filters
    'DuplicateFilter',
    'DomainFilter',
    'ExactPhraseFilter',
    # Ranking
    'HybridRanker',
    'ScoringEngine',
    'TierClassifier',
    # Config
    'FilterProfile',
    'ScoringProfile',
    # Entity-based filters (via PACMAN)
    'filter_by_location',
    'filter_by_person',
    'filter_by_company',
    'filter_by_date_range',
    'filter_has_identifiers',
    'filter_has_company_numbers',
    'filter_by_designation',
    'filter_by_semantic_concept',
    'filter_by_red_flag_category',
    'get_result_entities',
    'ENTITY_FILTERS_AVAILABLE',
]
