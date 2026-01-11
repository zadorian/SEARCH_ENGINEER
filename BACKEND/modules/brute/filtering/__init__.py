"""
Search_Engineer Centralized Filtering System

This module provides comprehensive result filtering and ranking capabilities
across all search types. It ensures consistent quality and relevance scoring
while supporting both primary and secondary result classification.

Main Components:
- FilterManager: Central coordinator for all filtering operations
- BaseFilter: Abstract base class for all filter implementations  
- Specialized Filters: Content, quality, duplicate, domain, geographic, temporal
- Hybrid Ranking: Multi-factor scoring and tier classification
- Search Type Integration: Seamless integration with existing search types

Usage:
    from filtering import FilterManager
    
    # Process results through the filtering pipeline
    filtered_results = await FilterManager.process_results(
        raw_results, 
        search_type='filetype',
        query_context={'filetype': 'pdf', 'query': 'annual report'}
    )
    
    # Access primary and secondary results
    primary = filtered_results['primary']      # High relevance
    secondary = filtered_results['secondary']  # Lower relevance but useful
"""

from .core.filter_manager import FilterManager
from .core.base_filter import BaseFilter
from .core.result_processor import ResultProcessor

# Import specialized filters
from .filters.relevance_filter import RelevanceFilter
from .filters.quality_filter import QualityFilter
from .filters.duplicate_filter import DuplicateFilter
from .filters.domain_filter import DomainFilter
from .filters.geographic_filter import GeographicFilter
from .filters.temporal_filter import TemporalFilter
from .filters.content_filter import ContentFilter

# Import ranking components
from .ranking.hybrid_ranker import HybridRanker
from .ranking.scoring_engine import ScoringEngine
from .ranking.tier_classifier import TierClassifier

# Import integration components
# Removed SearchTypeAdapter import to avoid circular dependency with Search_Integration
# Users should import directly: from Search_Integration.search_type_adapter import BaseSearchAdapter
# from .integration.engine_adapter import EngineAdapter  # Module not found

# Import configuration
from .config.filter_config import FilterProfile
from .config.scoring_profiles import ScoringProfile

__version__ = "1.0.0"
__author__ = "Search_Engineer Team"

# Export main interface
__all__ = [
    'FilterManager',
    'BaseFilter', 
    'ResultProcessor',
    'RelevanceFilter',
    'QualityFilter',
    'DuplicateFilter', 
    'DomainFilter',
    'GeographicFilter',
    'TemporalFilter',
    'ContentFilter',
    'HybridRanker',
    'ScoringEngine',
    'TierClassifier',
    # 'SearchTypeAdapter',  # Removed to avoid circular dependency 
    # 'EngineAdapter',      # Module not found
    'FilterProfile',
    'ScoringProfile'
]