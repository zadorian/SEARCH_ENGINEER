#!/usr/bin/env python3
"""
Default Filter Configurations for Search_Engineer
Provides pre-configured settings for different filtering scenarios
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


@dataclass
class FilterProfile:
    """Configuration profile for filtering"""
    name: str
    description: str
    
    # Tier settings
    include_tiers: List[int] = field(default_factory=lambda: [1, 2, 3])
    
    # Score thresholds
    min_relevance_score: float = 0.3
    min_quality_score: float = 0.3
    min_overall_score: float = 0.3
    
    # Filter weights
    filter_weights: Dict[str, float] = field(default_factory=lambda: {
        'relevance': 1.0,
        'quality': 0.8,
        'domain': 0.6,
        'temporal': 0.7,
        'geographic': 0.5,
        'language': 0.9,
        'content': 0.7
    })
    
    # Processing options
    enable_deduplication: bool = True
    enable_clustering: bool = False
    enable_diversity_boost: bool = False
    
    # Performance settings
    max_processing_time_ms: int = 5000
    batch_size: int = 100
    parallel_processing: bool = True
    
    # Adaptive settings
    enable_adaptive_filtering: bool = True
    adaptive_threshold_adjustment: float = 0.1
    min_results_threshold: int = 10


# Pre-configured profiles
FILTER_PROFILES = {
    'maximum_recall': FilterProfile(
        name='maximum_recall',
        description='Maximize recall - include all potentially relevant results',
        include_tiers=[1, 2, 3, 4],
        min_relevance_score=0.0,
        min_quality_score=0.0,
        min_overall_score=0.0,
        filter_weights={
            'relevance': 0.8,
            'quality': 0.3,
            'domain': 0.2,
            'temporal': 0.4,
            'geographic': 0.3,
            'language': 0.7,
            'content': 0.5
        },
        enable_adaptive_filtering=True,
        adaptive_threshold_adjustment=0.2
    ),
    
    'balanced': FilterProfile(
        name='balanced',
        description='Balance between recall and precision',
        include_tiers=[1, 2, 3],
        min_relevance_score=0.3,
        min_quality_score=0.2,
        min_overall_score=0.25,
        enable_diversity_boost=True
    ),
    
    'high_precision': FilterProfile(
        name='high_precision',
        description='Prioritize precision - only high quality results',
        include_tiers=[1, 2],
        min_relevance_score=0.7,
        min_quality_score=0.6,
        min_overall_score=0.65,
        filter_weights={
            'relevance': 1.0,
            'quality': 1.0,
            'domain': 0.8,
            'temporal': 0.6,
            'geographic': 0.7,
            'language': 0.9,
            'content': 0.8
        },
        enable_clustering=True,
        enable_adaptive_filtering=False
    ),
    
    'research': FilterProfile(
        name='research',
        description='Academic/research focus - prioritize authority and quality',
        include_tiers=[1, 2, 3],
        min_relevance_score=0.4,
        min_quality_score=0.5,
        min_overall_score=0.45,
        filter_weights={
            'relevance': 0.9,
            'quality': 1.0,
            'domain': 0.9,  # Prioritize authoritative domains
            'temporal': 0.8,  # Recent research is important
            'geographic': 0.3,
            'language': 0.8,
            'content': 0.9
        },
        enable_clustering=True,
        enable_diversity_boost=True
    ),
    
    'news': FilterProfile(
        name='news',
        description='News search - prioritize recency and credibility',
        include_tiers=[1, 2],
        min_relevance_score=0.5,
        min_quality_score=0.4,
        min_overall_score=0.45,
        filter_weights={
            'relevance': 0.9,
            'quality': 0.8,
            'domain': 1.0,  # News domain authority crucial
            'temporal': 1.0,  # Recency is key
            'geographic': 0.6,
            'language': 0.8,
            'content': 0.7
        },
        max_processing_time_ms=3000  # Faster for breaking news
    ),
    
    'local': FilterProfile(
        name='local',
        description='Local search - prioritize geographic relevance',
        include_tiers=[1, 2, 3],
        min_relevance_score=0.3,
        min_quality_score=0.2,
        min_overall_score=0.25,
        filter_weights={
            'relevance': 0.8,
            'quality': 0.5,
            'domain': 0.4,
            'temporal': 0.6,
            'geographic': 1.0,  # Geographic relevance is key
            'language': 0.7,
            'content': 0.6
        }
    ),
    
    'technical': FilterProfile(
        name='technical',
        description='Technical documentation - prioritize accuracy and detail',
        include_tiers=[1, 2],
        min_relevance_score=0.6,
        min_quality_score=0.5,
        min_overall_score=0.55,
        filter_weights={
            'relevance': 1.0,
            'quality': 0.9,
            'domain': 0.7,
            'temporal': 0.5,  # Older docs can still be valuable
            'geographic': 0.2,
            'language': 0.8,
            'content': 1.0  # Content structure very important
        },
        enable_clustering=True
    )
}


# Search type specific configurations
SEARCH_TYPE_CONFIGS = {
    'filetype': {
        'primary_filters': ['content', 'relevance'],
        'boost_exact_extension': True,
        'content_analysis_depth': 'deep',
        'special_handling': {
            'pdf': {'extract_metadata': True},
            'doc': {'check_compatibility': True},
            'code': {'syntax_validation': True}
        }
    },
    
    'proximity': {
        'primary_filters': ['relevance'],
        'distance_scoring': True,
        'snippet_analysis': 'detailed',
        'context_window': 100  # characters around match
    },
    
    'location': {
        'primary_filters': ['geographic', 'relevance'],
        'geo_precision': 'city',
        'include_nearby': True,
        'radius_km': 50
    },
    
    'corporate': {
        'primary_filters': ['domain', 'quality', 'relevance'],
        'entity_recognition': True,
        'verify_official_sources': True,
        'subsidiary_detection': True
    },
    
    'date': {
        'primary_filters': ['temporal', 'relevance'],
        'date_extraction': 'aggressive',
        'relative_date_handling': True,
        'timezone_aware': False
    },
    
    'language': {
        'primary_filters': ['language', 'relevance'],
        'language_detection': 'multi-model',
        'confidence_threshold': 0.8,
        'mixed_language_handling': 'segment'
    }
}


# Performance optimization settings
PERFORMANCE_CONFIGS = {
    'real_time': {
        'max_processing_time_ms': 100,
        'batch_size': 10,
        'parallel_processing': False,
        'cache_enabled': False,
        'lightweight_scoring': True
    },
    
    'streaming': {
        'max_processing_time_ms': 500,
        'batch_size': 1,
        'parallel_processing': False,
        'progressive_processing': True,
        'early_termination': True
    },
    
    'batch': {
        'max_processing_time_ms': 10000,
        'batch_size': 1000,
        'parallel_processing': True,
        'cache_enabled': True,
        'full_analysis': True
    },
    
    'interactive': {
        'max_processing_time_ms': 2000,
        'batch_size': 50,
        'parallel_processing': True,
        'progressive_updates': True,
        'ui_friendly': True
    }
}


def get_filter_config(profile_name: str = 'balanced',
                     search_type: Optional[str] = None,
                     performance_mode: str = 'interactive') -> Dict[str, Any]:
    """
    Get complete filter configuration
    
    Args:
        profile_name: Name of filter profile
        search_type: Type of search being performed
        performance_mode: Performance optimization mode
        
    Returns:
        Complete configuration dictionary
    """
    # Get base profile
    profile = FILTER_PROFILES.get(profile_name, FILTER_PROFILES['balanced'])
    
    config = {
        'profile': profile.name,
        'include_tiers': profile.include_tiers,
        'thresholds': {
            'relevance': profile.min_relevance_score,
            'quality': profile.min_quality_score,
            'overall': profile.min_overall_score
        },
        'weights': profile.filter_weights,
        'options': {
            'deduplication': profile.enable_deduplication,
            'clustering': profile.enable_clustering,
            'diversity': profile.enable_diversity_boost,
            'adaptive': profile.enable_adaptive_filtering
        },
        'performance': {
            'max_time_ms': profile.max_processing_time_ms,
            'batch_size': profile.batch_size,
            'parallel': profile.parallel_processing
        }
    }
    
    # Add search type specific settings
    if search_type and search_type in SEARCH_TYPE_CONFIGS:
        config['search_type_config'] = SEARCH_TYPE_CONFIGS[search_type]
    
    # Apply performance optimizations
    if performance_mode in PERFORMANCE_CONFIGS:
        perf_config = PERFORMANCE_CONFIGS[performance_mode]
        config['performance'].update(perf_config)
    
    return config


def get_adaptive_config(base_profile: str,
                       current_results: int,
                       target_results: int,
                       round_number: int) -> Dict[str, Any]:
    """
    Get adaptive configuration based on current state
    
    Args:
        base_profile: Starting profile name
        current_results: Number of results found so far
        target_results: Target number of results
        round_number: Current search round
        
    Returns:
        Adapted configuration
    """
    config = get_filter_config(base_profile)
    
    # Calculate result ratio
    result_ratio = current_results / max(target_results, 1)
    
    # Adjust thresholds based on results
    if result_ratio < 0.5:  # Too few results
        # Relax thresholds
        adjustment = min(0.3, 0.1 * round_number)
        config['thresholds']['relevance'] = max(0, config['thresholds']['relevance'] - adjustment)
        config['thresholds']['quality'] = max(0, config['thresholds']['quality'] - adjustment)
        config['thresholds']['overall'] = max(0, config['thresholds']['overall'] - adjustment)
        
        # Expand tier inclusion
        max_tier = max(config['include_tiers'])
        if max_tier < 4:
            config['include_tiers'].append(max_tier + 1)
    
    elif result_ratio > 2.0:  # Too many results
        # Tighten thresholds
        adjustment = min(0.2, 0.05 * round_number)
        config['thresholds']['relevance'] += adjustment
        config['thresholds']['quality'] += adjustment
        config['thresholds']['overall'] += adjustment
        
        # Enable clustering to group similar results
        config['options']['clustering'] = True
        config['options']['diversity'] = True
    
    # Round-specific adjustments
    if round_number > 3:
        # In later rounds, prioritize diversity
        config['options']['diversity'] = True
        config['weights']['relevance'] *= 0.9  # Slightly reduce relevance weight
    
    return config