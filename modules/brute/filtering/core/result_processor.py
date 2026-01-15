"""
Result Processor

Handles the processing pipeline for search results, including normalization,
filtering, scoring, and classification into primary/secondary tiers.
"""

import asyncio
import logging
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
import time
from collections import defaultdict
import hashlib

from .base_filter import FilterResult, FilterContext

logger = logging.getLogger(__name__)

@dataclass
class ProcessedResult:
    """Final processed result with all filtering and scoring applied"""
    # Original result data
    title: str
    url: str
    snippet: str
    source: str
    
    # Processing results
    final_score: float  # 0-100 composite score
    tier: int          # 1-4 classification
    classification: str # 'primary' or 'secondary'
    
    # Detailed scoring breakdown
    relevance_score: float
    quality_score: float
    authority_score: float
    freshness_score: float
    
    # Metadata
    filter_scores: Dict[str, float]  # Individual filter scores
    reasoning: List[str]             # Why this score was assigned
    metadata: Dict[str, Any]         # Additional data
    processed_at: float
    processing_time: float

class ResultProcessor:
    """
    Core result processing engine that coordinates filtering, scoring,
    and classification of search results.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the result processor.
        
        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}
        self.logger = logging.getLogger(f"{__name__}.ResultProcessor")
        
        # Default processing configuration
        self.default_config = {
            'primary_threshold': 60.0,    # Minimum score for primary results
            'secondary_threshold': 30.0,   # Minimum score for secondary results  
            'max_primary_results': 50,     # Max primary results to return
            'max_secondary_results': 100,  # Max secondary results to return
            'enable_deduplication': True,  # Remove duplicate results
            'similarity_threshold': 0.85,  # URL/content similarity threshold
            'parallel_processing': True,   # Process filters in parallel
            'preserve_order': True,        # Maintain original result ordering
            'score_weights': {             # Weight different scoring factors
                'relevance': 0.35,
                'quality': 0.25, 
                'authority': 0.20,
                'freshness': 0.20
            }
        }
        
        # Merge with user config
        self.config = {**self.default_config, **self.config}
        
        # Statistics tracking
        self.stats = {
            'total_processed': 0,
            'primary_results': 0,
            'secondary_results': 0,
            'filtered_out': 0,
            'duplicates_removed': 0,
            'average_processing_time': 0.0
        }
    
    async def process_results(
        self,
        raw_results: List[Dict[str, Any]],
        filter_results: List[FilterResult], 
        context: FilterContext
    ) -> Dict[str, Any]:
        """
        Main processing method that combines raw results with filter results
        to produce final classified and ranked results.
        
        Args:
            raw_results: Original search results from engines
            filter_results: Results from filtering pipeline
            context: Processing context
            
        Returns:
            Dictionary with primary/secondary results and metadata
        """
        start_time = time.time()
        
        if not raw_results or not filter_results:
            return self._empty_result_set()
        
        try:
            self.logger.info(
                f"Processing {len(raw_results)} results with "
                f"{len(filter_results)} filter results"
            )
            
            # Step 1: Normalize and combine results
            combined_results = await self._combine_results(raw_results, filter_results)
            
            # Step 2: Deduplicate if enabled
            if self.config['enable_deduplication']:
                combined_results = await self._deduplicate_results(combined_results)
            
            # Step 3: Calculate composite scores
            scored_results = await self._calculate_composite_scores(combined_results, context)
            
            # Step 4: Classify into primary/secondary tiers
            classified_results = await self._classify_results(scored_results)
            
            # Step 5: Sort and limit results
            final_results = await self._finalize_results(classified_results)
            
            # Step 6: Update statistics
            processing_time = time.time() - start_time
            self._update_stats(len(raw_results), final_results, processing_time)
            
            self.logger.info(
                f"Processed {len(raw_results)} results -> "
                f"{len(final_results['primary'])} primary, "
                f"{len(final_results['secondary'])} secondary "
                f"in {processing_time:.2f}s"
            )
            
            return final_results
            
        except Exception as e:
            self.logger.error(f"Error processing results: {e}")
            return self._empty_result_set()
    
    async def _combine_results(
        self,
        raw_results: List[Dict[str, Any]],
        filter_results: List[FilterResult]
    ) -> List[Dict[str, Any]]:
        """
        Combine raw search results with filter results.
        
        Args:
            raw_results: Original search results
            filter_results: Filter processing results
            
        Returns:
            Combined results with both original and processed data
        """
        combined = []
        
        # Create a mapping of filter results by ID or index
        filter_map = {}
        for i, fr in enumerate(filter_results):
            # Try to match by ID first, then by index
            if fr.result_id and fr.result_id.startswith('result_'):
                try:
                    idx = int(fr.result_id.split('_')[1])
                    filter_map[idx] = fr
                except (ValueError, IndexError):
                    filter_map[i] = fr
            else:
                filter_map[i] = fr
        
        for i, raw_result in enumerate(raw_results):
            if i in filter_map:
                fr = filter_map[i]
                
                # Combine raw result with filter result
                combined_result = {
                    # Original data
                    'title': raw_result.get('title', 'No Title'),
                    'url': raw_result.get('url', ''),
                    'snippet': raw_result.get('snippet', raw_result.get('description', '')),
                    'source': raw_result.get('source', raw_result.get('engine', 'unknown')),
                    
                    # Filter results
                    'filter_score': fr.score,
                    'tier': fr.tier,
                    'classification': fr.classification,
                    'reasoning': [fr.reasoning],
                    'filter_metadata': fr.metadata,
                    
                    # Additional raw data
                    'raw_data': raw_result,
                    'index': i
                }
                
                combined.append(combined_result)
        
        return combined
    
    async def _deduplicate_results(
        self,
        results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Remove duplicate results based on URL and content similarity.
        
        Args:
            results: Results to deduplicate
            
        Returns:
            Deduplicated results
        """
        if not results:
            return results
        
        # Group by URL first (exact duplicates)
        url_groups = defaultdict(list)
        for result in results:
            url = result.get('url', '').strip().lower()
            if url:
                url_groups[url].append(result)
        
        deduplicated = []
        duplicates_removed = 0
        
        for url, group in url_groups.items():
            if len(group) == 1:
                # No duplicates for this URL
                deduplicated.append(group[0])
            else:
                # Multiple results with same URL - keep the highest scored
                best_result = max(group, key=lambda x: x.get('filter_score', 0))
                deduplicated.append(best_result)
                duplicates_removed += len(group) - 1
        
        # TODO: Add content-based similarity detection for different URLs
        # with similar content using text similarity algorithms
        
        self.stats['duplicates_removed'] += duplicates_removed
        
        if duplicates_removed > 0:
            self.logger.debug(f"Removed {duplicates_removed} duplicate results")
        
        return deduplicated
    
    async def _calculate_composite_scores(
        self,
        results: List[Dict[str, Any]],
        context: FilterContext
    ) -> List[Dict[str, Any]]:
        """
        Calculate composite scores from multiple scoring factors.
        
        Args:
            results: Results to score
            context: Processing context
            
        Returns:
            Results with composite scores added
        """
        scored_results = []
        weights = self.config['score_weights']
        
        for result in results:
            # Get individual scores (default to filter score if others not available)
            filter_score = result.get('filter_score', 0.0)
            
            relevance_score = result.get('relevance_score', filter_score)
            quality_score = result.get('quality_score', filter_score * 0.8)
            authority_score = result.get('authority_score', self._estimate_authority(result))
            freshness_score = result.get('freshness_score', 70.0)  # Default neutral
            
            # Calculate weighted composite score
            composite_score = (
                relevance_score * weights['relevance'] +
                quality_score * weights['quality'] +
                authority_score * weights['authority'] +
                freshness_score * weights['freshness']
            )
            
            # Ensure score is in 0-100 range
            composite_score = max(0.0, min(100.0, composite_score))
            
            result.update({
                'final_score': composite_score,
                'relevance_score': relevance_score,
                'quality_score': quality_score,
                'authority_score': authority_score,
                'freshness_score': freshness_score,
                'composite_score': composite_score
            })
            
            scored_results.append(result)
        
        return scored_results
    
    def _estimate_authority(self, result: Dict[str, Any]) -> float:
        """
        Estimate domain authority based on URL and source information.
        
        Args:
            result: Result to estimate authority for
            
        Returns:
            Authority score (0-100)
        """
        url = result.get('url', '').lower()
        source = result.get('source', '').lower()
        
        # Basic heuristics for domain authority
        authority_score = 50.0  # Default neutral
        
        # High authority domains
        high_authority = [
            '.edu', '.gov', 'wikipedia.org', 'arxiv.org', 
            'nature.com', 'science.org', 'ieee.org'
        ]
        
        # Medium authority domains  
        medium_authority = [
            'reuters.com', 'bbc.com', 'cnn.com', 'wsj.com',
            'guardian.com', 'nytimes.com'
        ]
        
        # Low authority indicators
        low_authority = [
            'blogspot.com', 'wordpress.com', 'medium.com',
            'reddit.com', 'quora.com'
        ]
        
        for domain in high_authority:
            if domain in url:
                authority_score = 85.0
                break
        
        for domain in medium_authority:
            if domain in url:
                authority_score = 70.0
                break
                
        for domain in low_authority:
            if domain in url:
                authority_score = 40.0
                break
        
        # Boost for HTTPS
        if url.startswith('https://'):
            authority_score += 5.0
        
        return min(100.0, authority_score)
    
    async def _classify_results(
        self,
        results: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Classify results into primary and secondary categories.

        Args:
            results: Scored results to classify

        Returns:
            Dictionary with 'primary' and 'secondary' result lists
        """
        primary_threshold = self.config['primary_threshold']
        secondary_threshold = self.config['secondary_threshold']

        primary_results = []
        secondary_results = []
        filtered_out = []

        for result in results:
            score = result.get('final_score', 0.0)
            filter_score = result.get('filter_score', score)
            tier = result.get('tier', 3)
            original_classification = result.get('classification', '')

            # CRITICAL: Respect filter classification for exact phrase filtering
            # If filter marked as 'filtered' or tier=4, filter it out regardless of composite score
            if original_classification == 'filtered' or tier == 4 or filter_score < 1.0:
                result['classification'] = 'filtered'
                result['filter_reason'] = f'Filter score {filter_score:.0f}, tier {tier}'
                filtered_out.append(result)
            elif score >= primary_threshold:
                result['classification'] = 'primary'
                primary_results.append(result)
            elif score >= secondary_threshold:
                result['classification'] = 'secondary'
                secondary_results.append(result)
            else:
                result['classification'] = 'filtered'
                result['filter_reason'] = f'Score {score:.0f} below threshold'
                filtered_out.append(result)

        self.logger.debug(
            f"Classification: {len(primary_results)} primary, "
            f"{len(secondary_results)} secondary, "
            f"{len(filtered_out)} filtered out"
        )

        return {
            'primary': primary_results,
            'secondary': secondary_results,
            'filtered': filtered_out
        }
    
    async def _finalize_results(
        self,
        classified_results: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """
        Sort and limit results, create final output structure.
        
        Args:
            classified_results: Classified result groups
            
        Returns:
            Final result structure with metadata
        """
        # Sort by score (highest first)
        primary = sorted(
            classified_results['primary'], 
            key=lambda x: x.get('final_score', 0), 
            reverse=True
        )[:self.config['max_primary_results']]
        
        secondary = sorted(
            classified_results['secondary'],
            key=lambda x: x.get('final_score', 0),
            reverse=True
        )[:self.config['max_secondary_results']]
        
        # Convert to ProcessedResult objects
        primary_processed = [self._to_processed_result(r) for r in primary]
        secondary_processed = [self._to_processed_result(r) for r in secondary]
        
        return {
            'primary': primary_processed,
            'secondary': secondary_processed,
            'metadata': {
                'total_input': len(classified_results['primary']) + 
                              len(classified_results['secondary']) + 
                              len(classified_results.get('filtered', [])),
                'primary_count': len(primary_processed),
                'secondary_count': len(secondary_processed),
                'filtered_count': len(classified_results.get('filtered', [])),
                'duplicates_removed': self.stats.get('duplicates_removed', 0),
                'processing_config': self.config,
                'processed_at': time.time()
            }
        }
    
    def _to_processed_result(self, result: Dict[str, Any]) -> ProcessedResult:
        """
        Convert internal result format to ProcessedResult object.
        
        Args:
            result: Internal result dictionary
            
        Returns:
            ProcessedResult object
        """
        return ProcessedResult(
            title=result.get('title', 'No Title'),
            url=result.get('url', ''),
            snippet=result.get('snippet', ''),
            source=result.get('source', 'unknown'),
            final_score=result.get('final_score', 0.0),
            tier=result.get('tier', 4),
            classification=result.get('classification', 'secondary'),
            relevance_score=result.get('relevance_score', 0.0),
            quality_score=result.get('quality_score', 0.0),
            authority_score=result.get('authority_score', 0.0),
            freshness_score=result.get('freshness_score', 0.0),
            filter_scores=result.get('filter_metadata', {}).get('scores', {}),
            reasoning=result.get('reasoning', []),
            metadata=result.get('filter_metadata', {}),
            processed_at=time.time(),
            processing_time=0.0  # TODO: Track individual result processing time
        )
    
    def _empty_result_set(self) -> Dict[str, Any]:
        """Return empty result set structure."""
        return {
            'primary': [],
            'secondary': [],
            'metadata': {
                'total_input': 0,
                'primary_count': 0,
                'secondary_count': 0,
                'filtered_count': 0,
                'duplicates_removed': 0,
                'processing_config': self.config,
                'processed_at': time.time(),
                'error': 'No results to process'
            }
        }
    
    def _update_stats(
        self,
        input_count: int,
        final_results: Dict[str, Any],
        processing_time: float
    ) -> None:
        """Update processing statistics."""
        self.stats['total_processed'] += input_count
        self.stats['primary_results'] += final_results['metadata']['primary_count']
        self.stats['secondary_results'] += final_results['metadata']['secondary_count']
        self.stats['filtered_out'] += final_results['metadata']['filtered_count']
        
        # Update average processing time
        if self.stats['total_processed'] > 0:
            total_time = self.stats.get('total_time', 0.0) + processing_time
            self.stats['total_time'] = total_time
            self.stats['average_processing_time'] = (
                total_time / self.stats['total_processed']
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics."""
        return self.stats.copy()