"""
Hybrid Ranker

Combines multiple ranking factors including relevance, quality, authority,
and freshness to produce comprehensive result rankings with tier classification.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple
import time
from pathlib import Path
import sys
import statistics

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ..core.base_filter import FilterResult
from .scoring_engine import ScoringEngine
from .tier_classifier import TierClassifier

logger = logging.getLogger(__name__)

class HybridRanker:
    """
    Advanced ranking system that combines multiple scoring factors to produce
    comprehensive result rankings with primary/secondary classification.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize HybridRanker.
        
        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}
        self.logger = logging.getLogger(f"{__name__}.HybridRanker")
        
        # Default configuration
        self.default_config = {
            # Ranking factor weights
            'ranking_weights': {
                'relevance': 0.35,      # How well content matches query
                'quality': 0.25,        # Content quality and authority
                'freshness': 0.20,      # Content recency and updates
                'authority': 0.15,      # Domain and source authority
                'diversity': 0.05       # Result diversity bonus
            },
            
            # Score normalization settings
            'score_normalization': {
                'enabled': True,
                'min_score': 0.0,
                'max_score': 100.0,
                'outlier_threshold': 2.0  # Standard deviations for outlier detection
            },
            
            # Diversity settings
            'diversity_config': {
                'enabled': True,
                'domain_diversity_weight': 0.6,
                'content_type_diversity_weight': 0.4,
                'max_same_domain': 3,
                'diversity_window': 10  # Consider diversity in top N results
            },
            
            # Tier classification thresholds
            'tier_thresholds': {
                'tier_1_min': 85.0,    # Exceptional results
                'tier_2_min': 70.0,    # High quality results
                'tier_3_min': 50.0,    # Good results
                'tier_4_min': 25.0,    # Acceptable results
            },
            
            # Primary/secondary classification
            'classification_thresholds': {
                'primary_min': 60.0,   # Minimum score for primary classification
                'secondary_min': 30.0  # Minimum score for secondary classification
            },
            
            # Advanced ranking features
            'advanced_features': {
                'boost_unique_content': True,
                'penalize_duplicates': True,
                'boost_comprehensive_results': True,
                'position_bias_correction': True,
                'query_intent_matching': True
            }
        }
        
        # Merge configurations
        self.config = {**self.default_config, **self.config}
        
        # Initialize components
        self.scoring_engine = ScoringEngine(self.config.get('scoring_engine', {}))
        self.tier_classifier = TierClassifier(self.config.get('tier_classifier', {}))
        
        # Statistics tracking
        self.stats = {
            'total_ranked': 0,
            'average_scores': {},
            'tier_distribution': {'tier_1': 0, 'tier_2': 0, 'tier_3': 0, 'tier_4': 0},
            'classification_distribution': {'primary': 0, 'secondary': 0}
        }
        
        self.logger.debug(f"HybridRanker initialized with weights: {self.config['ranking_weights']}")
    
    async def rank_results(
        self,
        filter_results: List[FilterResult],
        original_results: List[Dict[str, Any]],
        ranking_context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Main ranking method that processes filter results and produces final rankings.
        
        Args:
            filter_results: Results from filtering pipeline
            original_results: Original search results for reference
            ranking_context: Optional context for ranking decisions
            
        Returns:
            List of ranked results with comprehensive scoring
        """
        if not filter_results or not original_results:
            return []
        
        start_time = time.time()
        context = ranking_context or {}
        
        self.logger.debug(f"Ranking {len(filter_results)} filtered results")
        
        try:
            # Step 1: Combine filter results with original data
            combined_results = await self._combine_filter_and_original_data(
                filter_results, original_results
            )
            
            # Step 2: Calculate comprehensive scores
            scored_results = await self._calculate_comprehensive_scores(
                combined_results, context
            )
            
            # Step 3: Apply diversity adjustments
            if self.config['diversity_config']['enabled']:
                scored_results = await self._apply_diversity_adjustments(scored_results)
            
            # Step 4: Normalize scores
            if self.config['score_normalization']['enabled']:
                scored_results = await self._normalize_scores(scored_results)
            
            # Step 5: Classify into tiers and primary/secondary
            classified_results = await self._classify_results(scored_results)
            
            # Step 6: Apply final ranking with position bias correction
            final_ranked = await self._apply_final_ranking(classified_results, context)
            
            # Step 7: Update statistics
            processing_time = time.time() - start_time
            self._update_stats(final_ranked, processing_time)
            
            self.logger.info(
                f"HybridRanker processed {len(filter_results)} results in {processing_time:.2f}s"
            )
            
            return final_ranked
            
        except Exception as e:
            self.logger.error(f"Error in ranking process: {e}")
            # Return original results with basic scoring as fallback
            return await self._create_fallback_ranking(filter_results, original_results)
    
    async def _combine_filter_and_original_data(
        self,
        filter_results: List[FilterResult],
        original_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Combine filter results with original result data."""
        combined_results = []
        
        # Create mapping from filter results
        filter_map = {}
        for fr in filter_results:
            # Extract index from result_id (e.g., "relevance_5" -> 5)
            try:
                if '_' in fr.result_id:
                    index = int(fr.result_id.split('_')[-1])
                    filter_map[index] = fr
            except (ValueError, IndexError):
                # If we can't parse the index, use position
                filter_map[len(filter_map)] = fr
        
        for i, original in enumerate(original_results):
            if i in filter_map:
                fr = filter_map[i]
                
                combined = {
                    # Original result data
                    'title': original.get('title', 'No Title'),
                    'url': original.get('url', ''),
                    'snippet': original.get('snippet', original.get('description', '')),
                    'source': original.get('source', original.get('engine', 'unknown')),
                    
                    # Filter result data
                    'filter_score': fr.score,
                    'filter_tier': fr.tier,
                    'filter_classification': fr.classification,
                    'filter_reasoning': fr.reasoning,
                    'filter_metadata': fr.metadata,
                    
                    # Original position for bias correction
                    'original_index': i,
                    
                    # Raw original data
                    'original_data': original
                }
                
                combined_results.append(combined)
        
        return combined_results
    
    async def _calculate_comprehensive_scores(
        self,
        combined_results: List[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Calculate comprehensive scores using multiple factors."""
        scored_results = []
        weights = self.config['ranking_weights']
        
        for result in combined_results:
            # Extract individual scores
            scores = await self.scoring_engine.calculate_factor_scores(result, context)
            
            # Calculate weighted composite score
            composite_score = (
                scores['relevance'] * weights['relevance'] +
                scores['quality'] * weights['quality'] +
                scores['freshness'] * weights['freshness'] +
                scores['authority'] * weights['authority']
            )
            
            # Apply advanced features
            if self.config['advanced_features']['boost_comprehensive_results']:
                comprehensive_bonus = self._calculate_comprehensive_bonus(result)
                composite_score += comprehensive_bonus
            
            if self.config['advanced_features']['query_intent_matching']:
                intent_bonus = self._calculate_intent_matching_bonus(result, context)
                composite_score += intent_bonus
            
            # Ensure score is in valid range
            composite_score = max(0.0, min(100.0, composite_score))
            
            # Add scoring details to result
            result.update({
                'individual_scores': scores,
                'composite_score': composite_score,
                'ranking_weights': weights.copy(),
                'scoring_metadata': {
                    'comprehensive_bonus': self._calculate_comprehensive_bonus(result),
                    'intent_matching_bonus': self._calculate_intent_matching_bonus(result, context)
                }
            })
            
            scored_results.append(result)
        
        return scored_results
    
    def _calculate_comprehensive_bonus(self, result: Dict[str, Any]) -> float:
        """Calculate bonus for comprehensive content."""
        snippet = result.get('snippet', '')
        title = result.get('title', '')
        
        bonus = 0.0
        
        # Length bonus (longer content often more comprehensive)
        if len(snippet) > 300:
            bonus += 3.0
        elif len(snippet) > 150:
            bonus += 1.5
        
        # Structure indicators
        structure_indicators = [
            'table of contents', 'overview', 'introduction', 'conclusion',
            'summary', 'detailed', 'comprehensive', 'complete guide'
        ]
        
        combined_text = f"{title} {snippet}".lower()
        structure_matches = sum(1 for indicator in structure_indicators 
                              if indicator in combined_text)
        bonus += structure_matches * 2.0
        
        return min(5.0, bonus)  # Cap at 5 points
    
    def _calculate_intent_matching_bonus(
        self,
        result: Dict[str, Any],
        context: Dict[str, Any]
    ) -> float:
        """Calculate bonus for query intent matching."""
        bonus = 0.0
        
        # This is a simplified implementation
        # In practice, you'd analyze query intent and match against result characteristics
        
        query = context.get('query', '').lower()
        title = result.get('title', '').lower()
        snippet = result.get('snippet', '').lower()
        
        # Intent keywords
        intent_patterns = {
            'how_to': ['how to', 'tutorial', 'guide', 'step by step'],
            'definition': ['what is', 'definition', 'meaning', 'explained'],
            'comparison': ['vs', 'versus', 'compare', 'comparison', 'difference'],
            'list': ['list', 'best', 'top', 'ranking', 'collection'],
            'news': ['news', 'breaking', 'latest', 'update', 'announcement']
        }
        
        for intent_type, keywords in intent_patterns.items():
            if any(keyword in query for keyword in keywords):
                # Check if result matches this intent
                combined_text = f"{title} {snippet}"
                if any(keyword in combined_text for keyword in keywords):
                    bonus += 3.0
                    break
        
        return min(3.0, bonus)  # Cap at 3 points
    
    async def _apply_diversity_adjustments(
        self,
        scored_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Apply diversity adjustments to promote varied results."""
        if not scored_results:
            return scored_results
        
        diversity_config = self.config['diversity_config']
        window_size = diversity_config['diversity_window']
        
        # Sort by current score to work with top results
        scored_results.sort(key=lambda x: x['composite_score'], reverse=True)
        
        # Track domain and content type distribution
        domain_counts = {}
        content_type_counts = {}
        
        for i, result in enumerate(scored_results):
            if i >= window_size:
                break  # Only consider diversity in top N results
            
            # Extract domain
            url = result.get('url', '')
            domain = self._extract_domain(url)
            
            # Track domain distribution
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
            
            # Apply domain diversity penalty
            if domain_counts[domain] > diversity_config['max_same_domain']:
                penalty = (domain_counts[domain] - diversity_config['max_same_domain']) * 5.0
                result['composite_score'] -= penalty
                result['diversity_penalty'] = penalty
            
            # Content type diversity (simplified)
            content_type = self._infer_content_type(result)
            content_type_counts[content_type] = content_type_counts.get(content_type, 0) + 1
            
            # Apply minor content type diversity adjustment
            if content_type_counts[content_type] > 2:
                minor_penalty = (content_type_counts[content_type] - 2) * 1.0
                result['composite_score'] -= minor_penalty
        
        return scored_results
    
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
    
    def _infer_content_type(self, result: Dict[str, Any]) -> str:
        """Infer content type from result characteristics."""
        title = result.get('title', '').lower()
        snippet = result.get('snippet', '').lower()
        url = result.get('url', '').lower()
        combined_text = f"{title} {snippet}"
        
        # Simple content type inference
        if any(word in combined_text for word in ['news', 'breaking', 'report']):
            return 'news'
        elif any(word in combined_text for word in ['tutorial', 'guide', 'how to']):
            return 'tutorial'
        elif any(word in combined_text for word in ['research', 'study', 'paper']):
            return 'academic'
        elif any(word in combined_text for word in ['product', 'buy', 'price']):
            return 'commercial'
        elif any(ext in url for ext in ['.pdf', '.doc', '.docx']):
            return 'document'
        else:
            return 'general'
    
    async def _normalize_scores(
        self,
        scored_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Normalize scores to handle outliers and ensure fair distribution."""
        if not scored_results:
            return scored_results
        
        scores = [result['composite_score'] for result in scored_results]
        
        if len(scores) < 2:
            return scored_results
        
        # Calculate statistics
        mean_score = statistics.mean(scores)
        stdev_score = statistics.stdev(scores) if len(scores) > 1 else 0
        
        # Detect and handle outliers
        outlier_threshold = self.config['score_normalization']['outlier_threshold']
        
        for result in scored_results:
            score = result['composite_score']
            
            # Check if score is an outlier
            if stdev_score > 0:
                z_score = abs(score - mean_score) / stdev_score
                if z_score > outlier_threshold:
                    # Adjust outlier scores toward the mean
                    if score > mean_score:
                        adjusted_score = mean_score + (outlier_threshold * stdev_score)
                    else:
                        adjusted_score = mean_score - (outlier_threshold * stdev_score)
                    
                    result['composite_score'] = adjusted_score
                    result['outlier_adjusted'] = True
                    result['original_score'] = score
        
        # Min-max normalization to ensure scores are in expected range
        min_config = self.config['score_normalization']['min_score']
        max_config = self.config['score_normalization']['max_score']
        
        current_scores = [result['composite_score'] for result in scored_results]
        min_score = min(current_scores)
        max_score = max(current_scores)
        
        if max_score > min_score:  # Avoid division by zero
            for result in scored_results:
                original_score = result['composite_score']
                normalized_score = min_config + (
                    (original_score - min_score) / (max_score - min_score)
                ) * (max_config - min_config)
                
                result['composite_score'] = normalized_score
                result['normalization_applied'] = True
        
        return scored_results
    
    async def _classify_results(
        self,
        scored_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Classify results into tiers and primary/secondary categories."""
        tier_thresholds = self.config['tier_thresholds']
        classification_thresholds = self.config['classification_thresholds']
        
        for result in scored_results:
            score = result['composite_score']
            
            # Determine tier
            if score >= tier_thresholds['tier_1_min']:
                tier = 1
            elif score >= tier_thresholds['tier_2_min']:
                tier = 2
            elif score >= tier_thresholds['tier_3_min']:
                tier = 3
            else:
                tier = 4
            
            # Determine primary/secondary classification
            if score >= classification_thresholds['primary_min']:
                classification = 'primary'
            elif score >= classification_thresholds['secondary_min']:
                classification = 'secondary'
            else:
                classification = 'secondary'  # Don't completely exclude
            
            result.update({
                'final_tier': tier,
                'final_classification': classification,
                'tier_score': score
            })
        
        return scored_results
    
    async def _apply_final_ranking(
        self,
        classified_results: List[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Apply final ranking with position bias correction."""
        # Sort by composite score (primary ranking factor)
        classified_results.sort(key=lambda x: x['composite_score'], reverse=True)
        
        # Apply position bias correction if enabled
        if self.config['advanced_features']['position_bias_correction']:
            classified_results = await self._apply_position_bias_correction(
                classified_results
            )
        
        # Add final ranking positions
        for i, result in enumerate(classified_results):
            result.update({
                'final_rank': i + 1,
                'ranking_confidence': self._calculate_ranking_confidence(result),
                'ranking_metadata': {
                    'ranker': 'HybridRanker',
                    'ranking_factors': list(self.config['ranking_weights'].keys()),
                    'processed_at': time.time()
                }
            })
        
        return classified_results
    
    async def _apply_position_bias_correction(
        self,
        results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Apply corrections for original search engine position bias."""
        for result in results:
            original_index = result.get('original_index', 0)
            
            # Small penalty for results that were originally ranked very low
            # but scored high in our system (might indicate bias)
            if original_index > 20 and result['composite_score'] > 80:
                bias_penalty = min(5.0, (original_index - 20) * 0.2)
                result['composite_score'] -= bias_penalty
                result['position_bias_correction'] = -bias_penalty
            
            # Small boost for results that were originally ranked high
            # and also scored high in our system (confirms quality)
            elif original_index < 5 and result['composite_score'] > 70:
                bias_boost = min(2.0, (5 - original_index) * 0.5)
                result['composite_score'] += bias_boost
                result['position_bias_correction'] = bias_boost
        
        return results
    
    def _calculate_ranking_confidence(self, result: Dict[str, Any]) -> float:
        """Calculate confidence in the ranking decision."""
        confidence = 0.7  # Base confidence
        
        # Higher confidence for results with consistent scores across factors
        individual_scores = result.get('individual_scores', {})
        if individual_scores:
            score_values = list(individual_scores.values())
            if score_values:
                score_variance = statistics.variance(score_values) if len(score_values) > 1 else 0
                # Lower variance = higher confidence
                variance_factor = max(0, 1 - (score_variance / 1000))  # Normalize variance
                confidence += variance_factor * 0.2
        
        # Higher confidence for results with clear tier classification
        final_tier = result.get('final_tier', 4)
        if final_tier <= 2:
            confidence += 0.1
        
        return min(1.0, confidence)
    
    async def _create_fallback_ranking(
        self,
        filter_results: List[FilterResult],
        original_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Create fallback ranking when main ranking fails."""
        fallback_results = []
        
        for i, (fr, original) in enumerate(zip(filter_results, original_results)):
            result = {
                'title': original.get('title', 'No Title'),
                'url': original.get('url', ''),
                'snippet': original.get('snippet', original.get('description', '')),
                'source': original.get('source', 'unknown'),
                'composite_score': fr.score,
                'final_tier': fr.tier,
                'final_classification': fr.classification,
                'final_rank': i + 1,
                'fallback_mode': True,
                'original_data': original
            }
            fallback_results.append(result)
        
        # Sort by score
        fallback_results.sort(key=lambda x: x['composite_score'], reverse=True)
        
        return fallback_results
    
    def _update_stats(self, ranked_results: List[Dict[str, Any]], processing_time: float):
        """Update ranking statistics."""
        self.stats['total_ranked'] += len(ranked_results)
        
        # Update tier distribution
        for result in ranked_results:
            tier = result.get('final_tier', 4)
            tier_key = f'tier_{tier}'
            if tier_key in self.stats['tier_distribution']:
                self.stats['tier_distribution'][tier_key] += 1
        
        # Update classification distribution
        for result in ranked_results:
            classification = result.get('final_classification', 'secondary')
            if classification in self.stats['classification_distribution']:
                self.stats['classification_distribution'][classification] += 1
        
        # Update average scores
        if ranked_results:
            avg_score = sum(r.get('composite_score', 0) for r in ranked_results) / len(ranked_results)
            if 'average_composite_score' not in self.stats['average_scores']:
                self.stats['average_scores']['average_composite_score'] = []
            self.stats['average_scores']['average_composite_score'].append(avg_score)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get ranking statistics."""
        stats = self.stats.copy()
        
        # Calculate running averages
        if 'average_composite_score' in stats['average_scores']:
            scores = stats['average_scores']['average_composite_score']
            stats['average_scores']['overall_average'] = sum(scores) / len(scores)
        
        return stats
    
    def reset_stats(self) -> None:
        """Reset ranking statistics."""
        self.stats = {
            'total_ranked': 0,
            'average_scores': {},
            'tier_distribution': {'tier_1': 0, 'tier_2': 0, 'tier_3': 0, 'tier_4': 0},
            'classification_distribution': {'primary': 0, 'secondary': 0}
        }