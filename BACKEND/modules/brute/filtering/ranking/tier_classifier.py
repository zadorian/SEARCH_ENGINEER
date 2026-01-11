"""
Tier Classifier

Classifies search results into quality tiers and primary/secondary categories
based on comprehensive scoring and contextual analysis.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple
import time
import statistics
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)

class TierClassifier:
    """
    Classifies search results into quality tiers (1-4) and primary/secondary
    categories based on scoring patterns and contextual factors.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize TierClassifier.
        
        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}
        self.logger = logging.getLogger(f"{__name__}.TierClassifier")
        
        # Default configuration
        self.default_config = {
            # Tier classification thresholds
            'tier_thresholds': {
                'tier_1_min': 85.0,    # Exceptional results (top 5-10%)
                'tier_2_min': 70.0,    # High quality results (top 20-30%)
                'tier_3_min': 50.0,    # Good results (middle 40-50%)
                'tier_4_min': 25.0,    # Acceptable results (bottom 20-30%)
            },
            
            # Primary/Secondary classification
            'classification_thresholds': {
                'primary_min': 60.0,     # Minimum score for primary results
                'secondary_min': 30.0,   # Minimum score for secondary results
                'auto_primary_tier_1': True,   # All tier 1 results are primary
                'auto_primary_tier_2': True,   # All tier 2 results are primary
                'max_primary_percentage': 0.7, # Max 70% of results can be primary
            },
            
            # Adaptive classification settings
            'adaptive_classification': {
                'enabled': True,
                'adjust_for_result_count': True,
                'adjust_for_score_distribution': True,
                'min_results_for_adaptation': 10,
                'score_spread_threshold': 20.0
            },
            
            # Context-based adjustments
            'context_adjustments': {
                'query_specificity_bonus': 5.0,    # Bonus for specific queries
                'search_intent_matching': 5.0,     # Bonus for intent matching
                'domain_expertise_bonus': 3.0,     # Bonus for domain-specific content
                'freshness_requirement_bonus': 3.0  # Bonus when freshness is important
            },
            
            # Quality consistency checks
            'consistency_checks': {
                'cross_factor_consistency': True,   # Check consistency across factors
                'outlier_detection': True,          # Detect and handle outliers
                'tier_gap_analysis': True,          # Ensure meaningful gaps between tiers
                'min_tier_gap': 10.0               # Minimum score gap between tiers
            },
            
            # Special classification rules
            'special_rules': {
                'boost_unique_content': True,       # Boost unique/rare content
                'penalize_duplicate_domains': True, # Penalize too many same-domain results
                'boost_authoritative_sources': True,# Boost high-authority sources
                'consider_result_diversity': True   # Consider diversity in classification
            }
        }
        
        # Merge configurations
        self.config = {**self.default_config, **self.config}
        
        # Classification statistics
        self.stats = {
            'total_classified': 0,
            'tier_distribution': {'tier_1': 0, 'tier_2': 0, 'tier_3': 0, 'tier_4': 0},
            'classification_distribution': {'primary': 0, 'secondary': 0},
            'average_scores_by_tier': {},
            'adaptive_adjustments_made': 0
        }
        
        self.logger.debug("TierClassifier initialized with adaptive classification")
    
    async def classify_results(
        self,
        scored_results: List[Dict[str, Any]],
        classification_context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Main classification method that assigns tiers and primary/secondary labels.
        
        Args:
            scored_results: Results with comprehensive scores
            classification_context: Optional context for classification decisions
            
        Returns:
            List of classified results with tier and classification assignments
        """
        if not scored_results:
            return []
        
        context = classification_context or {}
        
        self.logger.debug(f"Classifying {len(scored_results)} scored results")
        
        try:
            # Step 1: Analyze score distribution
            score_analysis = await self._analyze_score_distribution(scored_results)
            
            # Step 2: Apply adaptive thresholds if enabled
            if self.config['adaptive_classification']['enabled']:
                adjusted_thresholds = await self._calculate_adaptive_thresholds(
                    scored_results, score_analysis, context
                )
            else:
                adjusted_thresholds = self.config['tier_thresholds'].copy()
            
            # Step 3: Apply tier classification
            tier_classified = await self._apply_tier_classification(
                scored_results, adjusted_thresholds, context
            )
            
            # Step 4: Apply primary/secondary classification
            final_classified = await self._apply_primary_secondary_classification(
                tier_classified, context
            )
            
            # Step 5: Apply consistency checks
            if self.config['consistency_checks']['cross_factor_consistency']:
                final_classified = await self._apply_consistency_checks(final_classified)
            
            # Step 6: Apply special rules
            final_classified = await self._apply_special_rules(final_classified, context)
            
            # Step 7: Update statistics
            self._update_classification_stats(final_classified)
            
            self.logger.info(
                f"Classified {len(final_classified)} results: "
                f"Tier distribution: {self._get_tier_distribution(final_classified)}"
            )
            
            return final_classified
            
        except Exception as e:
            self.logger.error(f"Error in classification process: {e}")
            # Return results with basic classification
            return await self._apply_basic_classification(scored_results)
    
    async def _analyze_score_distribution(
        self,
        scored_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze the distribution of scores to inform adaptive classification."""
        scores = [result.get('composite_score', 0) for result in scored_results]
        
        if not scores:
            return {}
        
        analysis = {
            'count': len(scores),
            'min_score': min(scores),
            'max_score': max(scores),
            'mean_score': statistics.mean(scores),
            'median_score': statistics.median(scores),
            'score_range': max(scores) - min(scores),
            'has_outliers': False,
            'score_gaps': []
        }
        
        # Calculate standard deviation if we have enough data
        if len(scores) > 1:
            analysis['std_dev'] = statistics.stdev(scores)
            
            # Detect outliers (scores more than 2 std devs from mean)
            outlier_threshold = 2 * analysis['std_dev']
            outliers = [
                score for score in scores 
                if abs(score - analysis['mean_score']) > outlier_threshold
            ]
            analysis['has_outliers'] = len(outliers) > 0
            analysis['outlier_count'] = len(outliers)
        
        # Find significant score gaps (for tier boundary adjustment)
        sorted_scores = sorted(scores, reverse=True)
        for i in range(len(sorted_scores) - 1):
            gap = sorted_scores[i] - sorted_scores[i + 1]
            if gap > 15.0:  # Significant gap
                analysis['score_gaps'].append({
                    'position': i + 1,
                    'gap_size': gap,
                    'upper_score': sorted_scores[i],
                    'lower_score': sorted_scores[i + 1]
                })
        
        return analysis
    
    async def _calculate_adaptive_thresholds(
        self,
        scored_results: List[Dict[str, Any]],
        score_analysis: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, float]:
        """Calculate adaptive tier thresholds based on score distribution."""
        base_thresholds = self.config['tier_thresholds'].copy()
        adaptive_config = self.config['adaptive_classification']
        
        result_count = len(scored_results)
        
        # Only apply adaptation if we have enough results
        if result_count < adaptive_config['min_results_for_adaptation']:
            return base_thresholds
        
        adjusted_thresholds = base_thresholds.copy()
        
        # Adjust for result count
        if adaptive_config['adjust_for_result_count']:
            if result_count < 20:
                # For smaller result sets, be more lenient
                adjusted_thresholds['tier_1_min'] -= 5.0
                adjusted_thresholds['tier_2_min'] -= 5.0
            elif result_count > 100:
                # For larger result sets, be more strict
                adjusted_thresholds['tier_1_min'] += 3.0
                adjusted_thresholds['tier_2_min'] += 3.0
        
        # Adjust for score distribution
        if adaptive_config['adjust_for_score_distribution']:
            score_range = score_analysis.get('score_range', 0)
            mean_score = score_analysis.get('mean_score', 50)
            
            # If scores are tightly clustered, adjust thresholds toward the mean
            if score_range < adaptive_config['score_spread_threshold']:
                center_offset = mean_score - 60  # Assuming 60 is the typical center
                
                adjusted_thresholds['tier_1_min'] += center_offset * 0.3
                adjusted_thresholds['tier_2_min'] += center_offset * 0.3
                adjusted_thresholds['tier_3_min'] += center_offset * 0.3
                
                self.stats['adaptive_adjustments_made'] += 1
        
        # Use score gaps to inform tier boundaries
        score_gaps = score_analysis.get('score_gaps', [])
        if score_gaps:
            # Find the most significant gap and consider it for tier boundary
            largest_gap = max(score_gaps, key=lambda g: g['gap_size'])
            if largest_gap['gap_size'] > 20.0:
                # Use this gap as a natural tier boundary
                gap_position = largest_gap['position']
                total_results = len(scored_results)
                
                # If gap is in top 10-20%, make it tier 1 boundary
                if gap_position / total_results <= 0.2:
                    adjusted_thresholds['tier_1_min'] = largest_gap['lower_score']
                # If gap is in top 30-40%, make it tier 2 boundary
                elif gap_position / total_results <= 0.4:
                    adjusted_thresholds['tier_2_min'] = largest_gap['lower_score']
        
        # Ensure thresholds are in valid ranges and maintain order
        adjusted_thresholds['tier_1_min'] = max(70.0, min(95.0, adjusted_thresholds['tier_1_min']))
        adjusted_thresholds['tier_2_min'] = max(50.0, min(80.0, adjusted_thresholds['tier_2_min']))
        adjusted_thresholds['tier_3_min'] = max(30.0, min(65.0, adjusted_thresholds['tier_3_min']))
        adjusted_thresholds['tier_4_min'] = max(10.0, min(40.0, adjusted_thresholds['tier_4_min']))
        
        # Ensure proper ordering
        if adjusted_thresholds['tier_2_min'] >= adjusted_thresholds['tier_1_min']:
            adjusted_thresholds['tier_2_min'] = adjusted_thresholds['tier_1_min'] - 5.0
        
        if adjusted_thresholds['tier_3_min'] >= adjusted_thresholds['tier_2_min']:
            adjusted_thresholds['tier_3_min'] = adjusted_thresholds['tier_2_min'] - 5.0
        
        if adjusted_thresholds['tier_4_min'] >= adjusted_thresholds['tier_3_min']:
            adjusted_thresholds['tier_4_min'] = adjusted_thresholds['tier_3_min'] - 5.0
        
        self.logger.debug(f"Adaptive thresholds: {adjusted_thresholds}")
        
        return adjusted_thresholds
    
    async def _apply_tier_classification(
        self,
        scored_results: List[Dict[str, Any]],
        thresholds: Dict[str, float],
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Apply tier classification based on thresholds."""
        for result in scored_results:
            score = result.get('composite_score', 0)
            
            # Apply context-based adjustments
            adjusted_score = await self._apply_context_adjustments(result, context, score)
            
            # Determine tier
            if adjusted_score >= thresholds['tier_1_min']:
                tier = 1
            elif adjusted_score >= thresholds['tier_2_min']:
                tier = 2
            elif adjusted_score >= thresholds['tier_3_min']:
                tier = 3
            else:
                tier = 4
            
            result.update({
                'classification_tier': tier,
                'tier_score': adjusted_score,
                'tier_thresholds_used': thresholds.copy(),
                'score_adjustments': adjusted_score - score
            })
        
        return scored_results
    
    async def _apply_context_adjustments(
        self,
        result: Dict[str, Any],
        context: Dict[str, Any],
        base_score: float
    ) -> float:
        """Apply context-based score adjustments."""
        adjusted_score = base_score
        adjustments = self.config['context_adjustments']
        
        # Query specificity bonus
        query = context.get('query', '')
        if len(query.split()) > 5:  # Specific, detailed query
            adjusted_score += adjustments['query_specificity_bonus']
        
        # Search intent matching
        if self._matches_search_intent(result, context):
            adjusted_score += adjustments['search_intent_matching']
        
        # Domain expertise bonus
        if self._shows_domain_expertise(result, context):
            adjusted_score += adjustments['domain_expertise_bonus']
        
        # Freshness requirement bonus
        if self._meets_freshness_requirements(result, context):
            adjusted_score += adjustments['freshness_requirement_bonus']
        
        return min(100.0, adjusted_score)
    
    def _matches_search_intent(self, result: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Check if result matches search intent."""
        # Simplified intent matching
        query = context.get('query', '').lower()
        title = result.get('title', '').lower()
        snippet = result.get('snippet', '').lower()
        
        # How-to intent
        if any(phrase in query for phrase in ['how to', 'how do', 'tutorial']):
            return any(word in title + snippet for word in ['tutorial', 'guide', 'how', 'step'])
        
        # Definition intent
        if any(phrase in query for phrase in ['what is', 'define', 'definition']):
            return any(word in title + snippet for word in ['definition', 'meaning', 'what', 'overview'])
        
        # Comparison intent
        if any(phrase in query for phrase in ['vs', 'versus', 'compare', 'difference']):
            return any(word in title + snippet for word in ['comparison', 'vs', 'versus', 'difference'])
        
        return False
    
    def _shows_domain_expertise(self, result: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Check if result shows domain expertise."""
        snippet = result.get('snippet', '').lower()
        
        expertise_indicators = [
            'expert', 'specialist', 'professional', 'certified',
            'phd', 'professor', 'researcher', 'authority',
            'years of experience', 'published', 'journal'
        ]
        
        return any(indicator in snippet for indicator in expertise_indicators)
    
    def _meets_freshness_requirements(self, result: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Check if result meets freshness requirements."""
        query = context.get('query', '').lower()
        
        # Check if query indicates freshness need
        freshness_terms = ['latest', 'recent', 'current', 'new', '2024', '2023']
        if not any(term in query for term in freshness_terms):
            return False
        
        # Check if result indicates freshness
        title = result.get('title', '').lower()
        snippet = result.get('snippet', '').lower()
        combined = title + snippet
        
        return any(term in combined for term in freshness_terms)
    
    async def _apply_primary_secondary_classification(
        self,
        tier_classified: List[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Apply primary/secondary classification."""
        classification_config = self.config['classification_thresholds']
        
        # Sort by tier and score for classification
        sorted_results = sorted(
            tier_classified,
            key=lambda x: (x.get('classification_tier', 4), -x.get('tier_score', 0))
        )
        
        primary_count = 0
        max_primary = int(len(sorted_results) * classification_config['max_primary_percentage'])
        
        for result in sorted_results:
            tier = result.get('classification_tier', 4)
            score = result.get('tier_score', 0)
            
            # Auto-primary for tier 1 and 2 (if configured)
            if tier == 1 and classification_config['auto_primary_tier_1']:
                classification = 'primary'
                primary_count += 1
            elif tier == 2 and classification_config['auto_primary_tier_2'] and primary_count < max_primary:
                classification = 'primary'
                primary_count += 1
            # Score-based classification
            elif score >= classification_config['primary_min'] and primary_count < max_primary:
                classification = 'primary'
                primary_count += 1
            elif score >= classification_config['secondary_min']:
                classification = 'secondary'
            else:
                classification = 'secondary'  # Don't completely exclude
            
            result['final_classification'] = classification
        
        return tier_classified
    
    async def _apply_consistency_checks(
        self,
        classified_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Apply consistency checks to ensure logical classification."""
        consistency_config = self.config['consistency_checks']
        
        if not consistency_config['cross_factor_consistency']:
            return classified_results
        
        for result in classified_results:
            # Check if individual factor scores are consistent with final tier
            individual_scores = result.get('individual_scores', {})
            final_tier = result.get('classification_tier', 4)
            
            if individual_scores:
                score_values = list(individual_scores.values())
                avg_individual = sum(score_values) / len(score_values)
                composite_score = result.get('tier_score', 0)
                
                # If there's a large discrepancy, flag for review
                discrepancy = abs(avg_individual - composite_score)
                if discrepancy > 20.0:
                    result['classification_warning'] = f"Score discrepancy: {discrepancy:.1f}"
                    
                    # Adjust tier if necessary
                    if avg_individual > 85 and final_tier > 2:
                        result['classification_tier'] = 2
                        result['tier_adjusted'] = True
                    elif avg_individual < 40 and final_tier < 4:
                        result['classification_tier'] = 4
                        result['tier_adjusted'] = True
        
        # Check for proper tier gaps
        if consistency_config['tier_gap_analysis']:
            tier_scores = {}
            for result in classified_results:
                tier = result.get('classification_tier', 4)
                score = result.get('tier_score', 0)
                if tier not in tier_scores:
                    tier_scores[tier] = []
                tier_scores[tier].append(score)
            
            # Check gaps between tier averages
            tier_averages = {}
            for tier, scores in tier_scores.items():
                tier_averages[tier] = sum(scores) / len(scores)
            
            min_gap = consistency_config['min_tier_gap']
            for tier in [1, 2, 3]:
                if tier in tier_averages and tier + 1 in tier_averages:
                    gap = tier_averages[tier] - tier_averages[tier + 1]
                    if gap < min_gap:
                        self.logger.warning(
                            f"Small gap between tier {tier} and {tier+1}: {gap:.1f}"
                        )
        
        return classified_results
    
    async def _apply_special_rules(
        self,
        classified_results: List[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Apply special classification rules."""
        special_config = self.config['special_rules']
        
        if special_config['boost_authoritative_sources']:
            for result in classified_results:
                url = result.get('url', '').lower()
                authority_domains = ['.edu', '.gov', 'wikipedia.org', 'nature.com']
                
                if any(domain in url for domain in authority_domains):
                    current_tier = result.get('classification_tier', 4)
                    if current_tier > 1:
                        result['classification_tier'] = max(1, current_tier - 1)
                        result['authority_boost_applied'] = True
        
        if special_config['penalize_duplicate_domains']:
            domain_counts = {}
            for result in classified_results:
                url = result.get('url', '')
                domain = self._extract_domain(url)
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
            
            for result in classified_results:
                url = result.get('url', '')
                domain = self._extract_domain(url)
                
                if domain_counts[domain] > 3:  # Too many from same domain
                    current_tier = result.get('classification_tier', 4)
                    if current_tier < 4:
                        result['classification_tier'] = min(4, current_tier + 1)
                        result['domain_penalty_applied'] = True
        
        return classified_results
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except Exception as e:
            return url.lower()
    
    async def _apply_basic_classification(
        self,
        scored_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Apply basic classification when main process fails."""
        base_thresholds = self.config['tier_thresholds']
        
        for result in scored_results:
            score = result.get('composite_score', 50)
            
            # Basic tier assignment
            if score >= base_thresholds['tier_1_min']:
                tier = 1
                classification = 'primary'
            elif score >= base_thresholds['tier_2_min']:
                tier = 2
                classification = 'primary'
            elif score >= base_thresholds['tier_3_min']:
                tier = 3
                classification = 'secondary'
            else:
                tier = 4
                classification = 'secondary'
            
            result.update({
                'classification_tier': tier,
                'final_classification': classification,
                'tier_score': score,
                'basic_classification': True
            })
        
        return scored_results
    
    def _update_classification_stats(self, classified_results: List[Dict[str, Any]]):
        """Update classification statistics."""
        self.stats['total_classified'] += len(classified_results)
        
        for result in classified_results:
            tier = result.get('classification_tier', 4)
            classification = result.get('final_classification', 'secondary')
            
            # Update tier distribution
            tier_key = f'tier_{tier}'
            if tier_key in self.stats['tier_distribution']:
                self.stats['tier_distribution'][tier_key] += 1
            
            # Update classification distribution
            if classification in self.stats['classification_distribution']:
                self.stats['classification_distribution'][classification] += 1
            
            # Update average scores by tier
            score = result.get('tier_score', 0)
            if tier_key not in self.stats['average_scores_by_tier']:
                self.stats['average_scores_by_tier'][tier_key] = []
            self.stats['average_scores_by_tier'][tier_key].append(score)
    
    def _get_tier_distribution(self, results: List[Dict[str, Any]]) -> Dict[str, int]:
        """Get tier distribution for a set of results."""
        distribution = {'tier_1': 0, 'tier_2': 0, 'tier_3': 0, 'tier_4': 0}
        
        for result in results:
            tier = result.get('classification_tier', 4)
            tier_key = f'tier_{tier}'
            if tier_key in distribution:
                distribution[tier_key] += 1
        
        return distribution
    
    def get_stats(self) -> Dict[str, Any]:
        """Get classification statistics."""
        stats = self.stats.copy()
        
        # Calculate average scores by tier
        for tier_key, scores in stats['average_scores_by_tier'].items():
            if scores:
                stats['average_scores_by_tier'][tier_key] = {
                    'average': sum(scores) / len(scores),
                    'count': len(scores),
                    'min': min(scores),
                    'max': max(scores)
                }
        
        return stats
    
    def reset_stats(self) -> None:
        """Reset classification statistics."""
        self.stats = {
            'total_classified': 0,
            'tier_distribution': {'tier_1': 0, 'tier_2': 0, 'tier_3': 0, 'tier_4': 0},
            'classification_distribution': {'primary': 0, 'secondary': 0},
            'average_scores_by_tier': {},
            'adaptive_adjustments_made': 0
        }