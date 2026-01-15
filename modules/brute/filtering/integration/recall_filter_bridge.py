#!/usr/bin/env python3
"""
Recall-Filter Bridge
Coordinates RecallOptimizer strategies with FilterManager configurations
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from Search_Types.recall_optimizer import RecallOptimizer, RecallConfig, RecallMode, FilteringLevel
from ..core.filter_manager import FilterManager

logger = logging.getLogger(__name__)


@dataclass
class BridgeConfig:
    """Configuration for recall-filter coordination"""
    # Tier inclusion by recall mode
    tier_inclusion_map: Dict[RecallMode, List[int]] = None
    
    # Score thresholds by filtering level
    score_threshold_map: Dict[FilteringLevel, float] = None
    
    # Dynamic adjustment settings
    enable_dynamic_adjustment: bool = True
    min_results_for_relaxation: int = 10
    max_tier_expansion: int = 4
    
    def __post_init__(self):
        if self.tier_inclusion_map is None:
            self.tier_inclusion_map = {
                RecallMode.MAXIMUM: [1, 2, 3, 4],  # Include all tiers
                RecallMode.BALANCED: [1, 2, 3],     # Exclude lowest tier
                RecallMode.PRECISION: [1, 2]        # Only top tiers
            }
        
        if self.score_threshold_map is None:
            self.score_threshold_map = {
                FilteringLevel.NONE: 0.0,      # No minimum score
                FilteringLevel.MINIMAL: 0.2,   # Very low threshold
                FilteringLevel.MODERATE: 0.5,  # Medium threshold
                FilteringLevel.STRICT: 0.7     # High threshold
            }


class RecallFilterBridge:
    """Bridges RecallOptimizer and FilterManager for coordinated operation"""
    
    def __init__(self,
                 recall_optimizer: RecallOptimizer,
                 filter_manager: FilterManager,
                 bridge_config: Optional[BridgeConfig] = None):
        self.recall_optimizer = recall_optimizer
        self.filter_manager = filter_manager
        self.config = bridge_config or BridgeConfig()
        self.round_stats = {}
    
    def get_filter_config_for_round(self, 
                                  round_num: int,
                                  current_results: int,
                                  search_type: str) -> Dict[str, Any]:
        """
        Get appropriate filter configuration based on recall round
        
        Args:
            round_num: Current search round/wave
            current_results: Number of results found so far
            search_type: Type of search being performed
            
        Returns:
            Filter configuration dictionary
        """
        recall_config = self.recall_optimizer.config
        
        # Base configuration from recall settings
        filter_config = {
            'include_tiers': self.config.tier_inclusion_map.get(
                recall_config.recall_mode, [1, 2, 3]
            ),
            'min_score': self.config.score_threshold_map.get(
                recall_config.filtering_level, 0.5
            ),
            'enable_deduplication': True,
            'adaptive_filtering': self.config.enable_dynamic_adjustment
        }
        
        # Round-specific adjustments
        if round_num > 1:
            # Progressive relaxation
            relaxation_factor = min(round_num - 1, 3) * 0.1
            filter_config['min_score'] = max(
                0, 
                filter_config['min_score'] - relaxation_factor
            )
            
            # Expand tier inclusion if needed
            if (self.config.enable_dynamic_adjustment and 
                current_results < self.config.min_results_for_relaxation):
                
                current_max_tier = max(filter_config['include_tiers'])
                if current_max_tier < self.config.max_tier_expansion:
                    filter_config['include_tiers'].append(current_max_tier + 1)
                    logger.info(f"Expanded tier inclusion to {filter_config['include_tiers']}")
        
        # Search-type specific adjustments
        filter_config.update(self._get_search_type_adjustments(search_type, round_num))
        
        # Store stats for analysis
        self.round_stats[round_num] = {
            'filter_config': filter_config.copy(),
            'current_results': current_results
        }
        
        return filter_config
    
    def _get_search_type_adjustments(self, search_type: str, round_num: int) -> Dict[str, Any]:
        """Get search-type specific filter adjustments"""
        adjustments = {}
        
        if search_type == 'filetype':
            # Relax file extension matching in later rounds
            adjustments['strict_extension_match'] = (round_num == 1)
            adjustments['content_based_detection'] = (round_num >= 2)
            
        elif search_type == 'proximity':
            # Increase distance tolerance
            adjustments['distance_tolerance'] = round_num - 1
            adjustments['order_matters'] = (round_num == 1)
            
        elif search_type == 'date':
            # Expand date range tolerance
            adjustments['date_flexibility_days'] = 30 * (round_num - 1)
            
        elif search_type == 'language':
            # Include more language variations
            adjustments['include_mixed_language'] = (round_num >= 2)
            adjustments['confidence_threshold'] = max(0.5, 0.8 - 0.1 * round_num)
        
        return adjustments
    
    def should_adjust_filtering(self,
                              current_results: int,
                              target_results: int,
                              round_num: int) -> bool:
        """
        Determine if filtering should be adjusted based on results
        
        Args:
            current_results: Number of results found
            target_results: Target number of results
            round_num: Current round number
            
        Returns:
            Boolean indicating if adjustment is needed
        """
        if not self.config.enable_dynamic_adjustment:
            return False
        
        # Need more results
        if current_results < target_results * 0.5:
            return True
        
        # Early rounds with few results
        if round_num <= 2 and current_results < self.config.min_results_for_relaxation:
            return True
        
        return False
    
    def get_adaptive_filter_params(self,
                                 results_history: List[int],
                                 round_num: int) -> Dict[str, Any]:
        """
        Get adaptive filter parameters based on results history
        
        Args:
            results_history: List of result counts per round
            round_num: Current round number
            
        Returns:
            Adaptive filter parameters
        """
        if not results_history:
            return {}
        
        # Calculate growth rate
        growth_rate = 0
        if len(results_history) >= 2:
            growth_rate = (results_history[-1] - results_history[-2]) / max(results_history[-2], 1)
        
        params = {}
        
        # If growth is slowing, relax filters more aggressively
        if growth_rate < 0.2:  # Less than 20% growth
            params['relaxation_boost'] = 0.2
            params['expand_operators'] = True
            logger.info(f"Low growth rate ({growth_rate:.2f}), applying relaxation boost")
        
        # If we have plenty of results, we can be more selective
        total_results = sum(results_history)
        if total_results > 1000:
            params['quality_boost'] = 0.1
            params['enable_clustering'] = True
            logger.info(f"High result count ({total_results}), enabling quality boost")
        
        return params
    
    def merge_configurations(self,
                           recall_strategy: Dict[str, Any],
                           filter_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge recall strategy with filter configuration
        
        Args:
            recall_strategy: Strategy from RecallOptimizer
            filter_config: Configuration for FilterManager
            
        Returns:
            Merged configuration
        """
        merged = {
            # Recall strategy settings
            'use_expansion': recall_strategy.get('use_expansion', False),
            'expansion_types': recall_strategy.get('expansion_types', []),
            'engines_to_use': recall_strategy.get('engines_to_use', 'all'),
            'max_variations': recall_strategy.get('max_variations', 10),
            
            # Filter configuration
            'filtering_enabled': recall_strategy.get('filtering_enabled', True),
            'filter_threshold': filter_config.get('min_score', 0.5),
            'include_tiers': filter_config.get('include_tiers', [1, 2, 3]),
            
            # Special handling
            'relaxation_level': recall_strategy.get('relaxation_level', 0),
            'adaptive_filtering': filter_config.get('adaptive_filtering', True),
            
            # Merged special features
            'features': {}
        }
        
        # Merge special features based on both configs
        if recall_strategy.get('special_patterns'):
            merged['features']['patterns'] = recall_strategy['special_patterns']
        
        if recall_strategy.get('semantic_search') and 'semantic' in recall_strategy.get('expansion_types', []):
            merged['features']['semantic_filtering'] = True
        
        return merged
    
    def get_round_summary(self) -> Dict[str, Any]:
        """Get summary of all rounds for analysis"""
        summary = {
            'total_rounds': len(self.round_stats),
            'recall_mode': self.recall_optimizer.config.recall_mode.value,
            'filtering_level': self.recall_optimizer.config.filtering_level.value,
            'rounds': self.round_stats,
            'config': {
                'tier_inclusion': self.config.tier_inclusion_map,
                'score_thresholds': self.config.score_threshold_map,
                'dynamic_adjustment': self.config.enable_dynamic_adjustment
            }
        }
        
        return summary
    
    def optimize_for_live_filtering(self, 
                                  enable_streaming: bool = True) -> Dict[str, Any]:
        """
        Get optimized configuration for live filtering scenarios
        
        Returns:
            Configuration optimized for streaming/live filtering
        """
        config = {
            'batch_size': 10 if enable_streaming else 100,
            'enable_progressive_filtering': True,
            'fast_deduplication': True,
            'lightweight_scoring': enable_streaming,
            'cache_filter_results': not enable_streaming,
            'parallel_processing': not enable_streaming
        }
        
        # Adjust based on recall mode
        if self.recall_optimizer.config.recall_mode == RecallMode.MAXIMUM:
            config['progressive_tiers'] = [4, 3, 2, 1]  # Process lowest tier first
            config['early_termination'] = False
        else:
            config['progressive_tiers'] = [1, 2, 3, 4]  # Process highest tier first
            config['early_termination'] = True
            
        return config


# Convenience functions
def create_coordinated_system(recall_mode: str = 'balanced',
                            filtering_level: str = 'moderate') -> Dict[str, Any]:
    """
    Create a coordinated recall-filter system
    
    Returns:
        Dictionary with configured components
    """
    from Search_Types.recall_optimizer import RecallOptimizer, RecallConfig, RecallMode, FilteringLevel
    from ..core.filter_manager import FilterManager
    
    # Create recall optimizer
    recall_config = RecallConfig(
        recall_mode=RecallMode(recall_mode),
        filtering_level=FilteringLevel(filtering_level)
    )
    recall_optimizer = RecallOptimizer(recall_config)
    
    # Create filter manager
    filter_manager = FilterManager()
    
    # Create bridge
    bridge = RecallFilterBridge(recall_optimizer, filter_manager)
    
    return {
        'recall_optimizer': recall_optimizer,
        'filter_manager': filter_manager,
        'bridge': bridge,
        'get_config': lambda round_num, results: bridge.get_filter_config_for_round(
            round_num, results, 'general'
        )
    }