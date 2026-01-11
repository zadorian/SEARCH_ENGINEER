#!/usr/bin/env python3
"""
Recall Optimizer Module - Monitors and improves recall metrics
Provides configuration for maximum recall vs precision trade-offs
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import json
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)


class RecallMode(Enum):
    """Different recall optimization modes"""
    MAXIMUM = "maximum"      # Prioritize recall above all else
    BALANCED = "balanced"     # Balance recall and precision
    PRECISION = "precision"   # Prioritize precision over recall


class FilteringLevel(Enum):
    """Filtering levels for results"""
    NONE = "none"           # No filtering at all
    MINIMAL = "minimal"     # Only remove obvious non-matches
    MODERATE = "moderate"   # Some quality filtering
    STRICT = "strict"       # Strong filtering for precision


@dataclass
class RecallConfig:
    """Configuration for recall optimization"""
    recall_mode: RecallMode = RecallMode.BALANCED
    filtering_level: FilteringLevel = FilteringLevel.MINIMAL
    search_rounds: int = 3                    # Number of progressive search iterations
    min_results_threshold: int = 10           # Minimum results before triggering fallbacks
    max_results_per_engine: int = 100         # Maximum results to fetch per engine
    enable_query_expansion: bool = True       # Whether to use query expansion
    enable_fallback_searches: bool = True     # Whether to use fallback strategies
    enable_semantic_search: bool = True       # Whether to use semantic variations
    enable_misspellings: bool = False         # Whether to include misspellings (usually False)
    confidence_threshold: float = 0.0         # Minimum confidence score (0 = include all)
    progressive_relaxation: bool = True       # Whether to progressively relax constraints
    track_metrics: bool = True                # Whether to track recall metrics
    

class RecallOptimizer:
    """Optimizes search strategies for maximum recall"""
    
    def __init__(self, config: RecallConfig = None):
        self.config = config or RecallConfig()
        self.metrics = {
            'searches_performed': 0,
            'total_results_found': 0,
            'unique_results': 0,
            'fallback_triggered': 0,
            'expansion_used': 0,
            'rounds_needed': {},
        }
    
    def get_search_strategy(self, search_type: str, current_results: int = 0, 
                          round_num: int = 1) -> Dict[str, Any]:
        """
        Get optimized search strategy based on current state
        
        Args:
            search_type: Type of search (filetype, proximity, etc.)
            current_results: Number of results found so far
            round_num: Current search round
        
        Returns:
            Dictionary with search strategy parameters
        """
        strategy = {
            'use_expansion': False,
            'expansion_types': [],
            'filtering_enabled': True,
            'filter_threshold': 0.5,
            'max_variations': 10,
            'engines_to_use': 'all',
            'fallback_needed': False,
            'relaxation_level': 0,
        }
        
        # Determine strategy based on recall mode
        if self.config.recall_mode == RecallMode.MAXIMUM:
            # Maximum recall strategy
            strategy.update({
                'use_expansion': True,
                'expansion_types': ['synonyms', 'semantic', 'modifiers', 'stems'],
                'filtering_enabled': False,
                'filter_threshold': 0.0,
                'max_variations': 20,
                'engines_to_use': 'all',
                'fallback_needed': current_results < self.config.min_results_threshold,
                'relaxation_level': round_num - 1,
            })
            
            # Add misspellings only if explicitly enabled
            if self.config.enable_misspellings:
                strategy['expansion_types'].append('misspellings')
        
        elif self.config.recall_mode == RecallMode.BALANCED:
            # Balanced strategy
            strategy.update({
                'use_expansion': round_num > 1 or current_results < self.config.min_results_threshold,
                'expansion_types': ['synonyms', 'semantic'] if round_num > 1 else ['synonyms'],
                'filtering_enabled': True,
                'filter_threshold': 0.3,
                'max_variations': 15,
                'engines_to_use': 'primary' if round_num == 1 else 'all',
                'fallback_needed': current_results < self.config.min_results_threshold // 2,
                'relaxation_level': max(0, round_num - 2),
            })
        
        elif self.config.recall_mode == RecallMode.PRECISION:
            # Precision-focused strategy
            strategy.update({
                'use_expansion': False,
                'expansion_types': [],
                'filtering_enabled': True,
                'filter_threshold': 0.7,
                'max_variations': 5,
                'engines_to_use': 'primary',
                'fallback_needed': False,
                'relaxation_level': 0,
            })
        
        # Apply filtering level adjustments
        if self.config.filtering_level == FilteringLevel.NONE:
            strategy['filtering_enabled'] = False
            strategy['filter_threshold'] = 0.0
        elif self.config.filtering_level == FilteringLevel.MINIMAL:
            strategy['filter_threshold'] = max(0.1, strategy['filter_threshold'] - 0.2)
        elif self.config.filtering_level == FilteringLevel.STRICT:
            strategy['filter_threshold'] = min(0.9, strategy['filter_threshold'] + 0.2)
        
        # Search-type specific adjustments
        strategy = self._adjust_for_search_type(strategy, search_type, round_num)
        
        # Track metrics
        if self.config.track_metrics:
            self.metrics['searches_performed'] += 1
            if strategy['use_expansion']:
                self.metrics['expansion_used'] += 1
            if strategy['fallback_needed']:
                self.metrics['fallback_triggered'] += 1
        
        return strategy
    
    def _adjust_for_search_type(self, strategy: Dict, search_type: str, 
                               round_num: int) -> Dict:
        """Adjust strategy based on specific search type"""
        
        if search_type == 'filetype':
            # Filetype searches benefit from specific patterns
            if round_num == 1:
                strategy['special_patterns'] = ['index_of', 'parent_directory']
            elif round_num == 2:
                strategy['special_patterns'] = ['file_hosting', 'download_sites']
                strategy['expansion_types'].append('modifiers')
            else:
                strategy['remove_extension_filter'] = True
                strategy['search_content_not_url'] = True
        
        elif search_type == 'proximity':
            # Proximity searches need special handling
            strategy['bidirectional'] = True
            strategy['distance_variations'] = True
            if round_num > 1:
                strategy['disable_snippet_validation'] = True
                strategy['use_wildcards'] = True
            if round_num > 2:
                strategy['semantic_proximity'] = True
        
        elif search_type == 'location':
            # Location searches benefit from geo-expansion
            strategy['use_geo_expansion'] = True
            strategy['include_nearby_regions'] = round_num > 1
            strategy['use_local_engines'] = True
            if round_num > 2:
                strategy['expand_to_country'] = True
        
        elif search_type == 'corporate':
            # Corporate searches need entity resolution
            strategy['use_entity_variants'] = True
            strategy['include_subsidiaries'] = round_num > 1
            strategy['search_business_sites'] = True
            if round_num > 2:
                strategy['use_general_web_search'] = True
        
        elif search_type == 'date':
            # Date searches need format flexibility
            strategy['date_format_variants'] = True
            strategy['relative_dates'] = round_num > 1
            strategy['seasonal_search'] = round_num > 2
            strategy['use_archive_engines'] = True
        
        elif search_type == 'language':
            # Language searches need cultural awareness
            strategy['use_transliteration'] = round_num > 1
            strategy['include_dialects'] = round_num > 2
            strategy['use_regional_engines'] = True
            strategy['character_variants'] = True
        
        return strategy
    
    def should_continue_searching(self, current_results: int, round_num: int, 
                                search_type: str) -> bool:
        """
        Determine if we should continue with another search round
        
        Args:
            current_results: Number of unique results found so far
            round_num: Current round number
            search_type: Type of search being performed
        
        Returns:
            Boolean indicating whether to continue searching
        """
        # Always stop if we've hit the maximum rounds
        if round_num >= self.config.search_rounds:
            return False
        
        # In maximum recall mode, always continue until max rounds
        if self.config.recall_mode == RecallMode.MAXIMUM:
            return True
        
        # Check if we have enough results
        if current_results >= self.config.min_results_threshold * 2:
            return False
        
        # Continue if we have very few results
        if current_results < self.config.min_results_threshold:
            return True
        
        # For balanced mode, continue if we're getting good incremental results
        if self.config.recall_mode == RecallMode.BALANCED:
            # This would ideally check the rate of new results
            # For now, continue if we haven't hit 2x threshold
            return current_results < self.config.min_results_threshold * 1.5
        
        # For precision mode, usually stop after first round unless very few results
        if self.config.recall_mode == RecallMode.PRECISION:
            return current_results < 5
        
        return False
    
    def score_result(self, result: Dict, search_type: str, 
                    query_terms: List[str]) -> float:
        """
        Score a result based on relevance signals
        
        Args:
            result: Search result dictionary
            search_type: Type of search
            query_terms: Original query terms
        
        Returns:
            Confidence score between 0 and 1
        """
        score = 0.5  # Base score
        
        # Check title relevance
        title = result.get('title', '').lower()
        if title:
            terms_in_title = sum(1 for term in query_terms if term.lower() in title)
            score += (terms_in_title / len(query_terms)) * 0.3
        
        # Check snippet/description relevance
        snippet = result.get('snippet', result.get('description', '')).lower()
        if snippet:
            terms_in_snippet = sum(1 for term in query_terms if term.lower() in snippet)
            score += (terms_in_snippet / len(query_terms)) * 0.2
        
        # URL relevance (domain quality, path relevance)
        url = result.get('url', '').lower()
        if url:
            # Bonus for query terms in URL
            terms_in_url = sum(1 for term in query_terms if term.lower() in url)
            score += (terms_in_url / len(query_terms)) * 0.1
            
            # Penalty for suspicious domains
            suspicious_tlds = ['.tk', '.ml', '.ga', '.cf']
            if any(tld in url for tld in suspicious_tlds):
                score -= 0.2
        
        # Search-type specific scoring
        if search_type == 'filetype':
            # Check if file extension is in URL
            if 'url' in result:
                url = result['url'].lower()
                common_extensions = ['.pdf', '.doc', '.xls', '.ppt', '.zip']
                if any(ext in url for ext in common_extensions):
                    score += 0.2
        
        elif search_type == 'proximity':
            # Check if both terms appear in snippet
            if 'snippet' in result and len(query_terms) >= 2:
                snippet_lower = result['snippet'].lower()
                if all(term.lower() in snippet_lower for term in query_terms[:2]):
                    score += 0.3
        
        elif search_type == 'location':
            # Boost for location-specific domains
            if 'location_relevance' in result:
                score += result['location_relevance'] * 0.4
        
        elif search_type == 'language':
            # Boost for language match
            if 'language_score' in result:
                score += result['language_score'] * 0.4
        
        # Normalize score to 0-1 range
        return max(0.0, min(1.0, score))
    
    def get_fallback_strategies(self, search_type: str, round_num: int) -> List[Dict]:
        """
        Get fallback search strategies when primary search yields few results
        
        Args:
            search_type: Type of search
            round_num: Current round number
        
        Returns:
            List of fallback strategies to try
        """
        strategies = []
        
        # Universal fallback strategies
        if round_num == 2:
            strategies.append({
                'name': 'broad_match',
                'description': 'Remove quotes and exact match requirements',
                'modifications': {
                    'remove_quotes': True,
                    'use_OR_operator': True,
                    'add_related_terms': True,
                }
            })
        
        if round_num >= 3:
            strategies.append({
                'name': 'semantic_expansion',
                'description': 'Use semantic search and concept expansion',
                'modifications': {
                    'use_semantic_search': True,
                    'concept_expansion': True,
                    'category_search': True,
                }
            })
        
        # Search-type specific fallbacks
        if search_type == 'filetype':
            strategies.extend([
                {
                    'name': 'content_search',
                    'description': 'Search content not URLs',
                    'modifications': {
                        'ignore_url_patterns': True,
                        'search_file_content': True,
                        'use_OCR_results': True,
                    }
                },
                {
                    'name': 'archive_search',
                    'description': 'Search archived content',
                    'modifications': {
                        'use_wayback': True,
                        'use_common_crawl': True,
                        'search_cached_pages': True,
                    }
                }
            ])
        
        elif search_type == 'proximity':
            strategies.extend([
                {
                    'name': 'relaxed_proximity',
                    'description': 'Increase proximity distance',
                    'modifications': {
                        'double_distance': True,
                        'remove_order_requirement': True,
                        'paragraph_proximity': True,
                    }
                },
                {
                    'name': 'co_occurrence',
                    'description': 'Find documents with both terms',
                    'modifications': {
                        'no_proximity_requirement': True,
                        'same_page_only': True,
                        'boost_both_terms': True,
                    }
                }
            ])
        
        return strategies
    
    def get_metrics_summary(self) -> Dict:
        """Get summary of recall optimization metrics"""
        return {
            'total_searches': self.metrics['searches_performed'],
            'total_results': self.metrics['total_results_found'],
            'unique_results': self.metrics['unique_results'],
            'fallback_rate': (self.metrics['fallback_triggered'] / 
                            max(1, self.metrics['searches_performed'])),
            'expansion_rate': (self.metrics['expansion_used'] / 
                             max(1, self.metrics['searches_performed'])),
            'average_rounds': (sum(self.metrics['rounds_needed'].values()) / 
                             max(1, len(self.metrics['rounds_needed']))),
        }
    
    def save_config(self, filepath: str):
        """Save current configuration to file"""
        config_dict = {
            'recall_mode': self.config.recall_mode.value,
            'filtering_level': self.config.filtering_level.value,
            'search_rounds': self.config.search_rounds,
            'min_results_threshold': self.config.min_results_threshold,
            'max_results_per_engine': self.config.max_results_per_engine,
            'enable_query_expansion': self.config.enable_query_expansion,
            'enable_fallback_searches': self.config.enable_fallback_searches,
            'enable_semantic_search': self.config.enable_semantic_search,
            'enable_misspellings': self.config.enable_misspellings,
            'confidence_threshold': self.config.confidence_threshold,
            'progressive_relaxation': self.config.progressive_relaxation,
            'track_metrics': self.config.track_metrics,
        }
        
        with open(filepath, 'w') as f:
            json.dump(config_dict, f, indent=2)
    
    @classmethod
    def load_config(cls, filepath: str) -> 'RecallOptimizer':
        """Load configuration from file"""
        with open(filepath, 'r') as f:
            config_dict = json.load(f)
        
        config = RecallConfig(
            recall_mode=RecallMode(config_dict.get('recall_mode', 'balanced')),
            filtering_level=FilteringLevel(config_dict.get('filtering_level', 'minimal')),
            search_rounds=config_dict.get('search_rounds', 3),
            min_results_threshold=config_dict.get('min_results_threshold', 10),
            max_results_per_engine=config_dict.get('max_results_per_engine', 100),
            enable_query_expansion=config_dict.get('enable_query_expansion', True),
            enable_fallback_searches=config_dict.get('enable_fallback_searches', True),
            enable_semantic_search=config_dict.get('enable_semantic_search', True),
            enable_misspellings=config_dict.get('enable_misspellings', False),
            confidence_threshold=config_dict.get('confidence_threshold', 0.0),
            progressive_relaxation=config_dict.get('progressive_relaxation', True),
            track_metrics=config_dict.get('track_metrics', True),
        )
        
        return cls(config)


# Convenience functions
def get_maximum_recall_config() -> RecallConfig:
    """Get configuration for maximum recall"""
    return RecallConfig(
        recall_mode=RecallMode.MAXIMUM,
        filtering_level=FilteringLevel.NONE,
        search_rounds=5,
        min_results_threshold=5,
        max_results_per_engine=200,
        enable_query_expansion=True,
        enable_fallback_searches=True,
        enable_semantic_search=True,
        enable_misspellings=False,
        confidence_threshold=0.0,
        progressive_relaxation=True,
        track_metrics=True,
    )


def get_balanced_config() -> RecallConfig:
    """Get balanced configuration"""
    return RecallConfig()  # Use defaults


def get_precision_config() -> RecallConfig:
    """Get configuration for high precision"""
    return RecallConfig(
        recall_mode=RecallMode.PRECISION,
        filtering_level=FilteringLevel.STRICT,
        search_rounds=2,
        min_results_threshold=20,
        max_results_per_engine=50,
        enable_query_expansion=False,
        enable_fallback_searches=False,
        enable_semantic_search=False,
        enable_misspellings=False,
        confidence_threshold=0.7,
        progressive_relaxation=False,
        track_metrics=True,
    )


if __name__ == "__main__":
    # Test the recall optimizer
    optimizer = RecallOptimizer(get_maximum_recall_config())
    
    # Test strategy generation
    print("Testing search strategies...\n")
    
    for search_type in ['filetype', 'proximity', 'location']:
        print(f"\nSearch type: {search_type}")
        print("=" * 50)
        
        for round_num in range(1, 4):
            strategy = optimizer.get_search_strategy(search_type, 
                                                   current_results=5 * round_num,
                                                   round_num=round_num)
            print(f"\nRound {round_num} strategy:")
            print(json.dumps(strategy, indent=2))
    
    # Test fallback strategies
    print("\n\nTesting fallback strategies...")
    print("=" * 50)
    
    for search_type in ['filetype', 'proximity']:
        fallbacks = optimizer.get_fallback_strategies(search_type, round_num=3)
        print(f"\nFallbacks for {search_type}:")
        for fb in fallbacks:
            print(f"  - {fb['name']}: {fb['description']}")