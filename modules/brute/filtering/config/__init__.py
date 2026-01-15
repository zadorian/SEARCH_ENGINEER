#!/usr/bin/env python3
"""
Filter Configuration Module
Provides default configurations and scoring profiles
"""

from .filter_config import (
    FilterProfile,
    FILTER_PROFILES,
    SEARCH_TYPE_CONFIGS,
    PERFORMANCE_CONFIGS,
    get_filter_config,
    get_adaptive_config
)

from .scoring_profiles import (
    ScoringStrategy,
    ScoringProfile,
    SCORING_PROFILES,
    ScoringCalculator,
    calculate_score,
    get_tier_from_score,
    get_scoring_profile
)

__all__ = [
    # Filter Config
    'FilterProfile',
    'FILTER_PROFILES',
    'SEARCH_TYPE_CONFIGS',
    'PERFORMANCE_CONFIGS',
    'get_filter_config',
    'get_adaptive_config',
    
    # Scoring Profiles
    'ScoringStrategy',
    'ScoringProfile', 
    'SCORING_PROFILES',
    'ScoringCalculator',
    'calculate_score',
    'get_tier_from_score',
    'get_scoring_profile'
]