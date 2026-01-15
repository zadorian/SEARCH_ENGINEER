"""
Filter Manager

Central coordinator for the Search_Engineer filtering system. Manages all
filtering operations, coordinates multiple filters, and provides the main
interface for search type integration.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Type
import time
from pathlib import Path
import sys

# Add the project root to the path for imports
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from .base_filter import BaseFilter, FilterContext, FilterResult, FilterPipeline
from .result_processor import ResultProcessor

logger = logging.getLogger(__name__)

class FilterManager:
    """
    Central coordinator for all filtering operations in the Search_Engineer system.
    
    This class provides the main interface for search types to process their results
    through the comprehensive filtering pipeline.
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        """Singleton pattern to ensure one FilterManager instance."""
        if cls._instance is None:
            cls._instance = super(FilterManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the FilterManager.
        
        Args:
            config: Optional configuration dictionary
        """
        if FilterManager._initialized:
            return
            
        self.config = config or {}
        self.logger = logging.getLogger(f"{__name__}.FilterManager")
        
        # Initialize components
        self.result_processor = ResultProcessor(self.config.get('processor', {}))
        self.filters = {}
        self.pipelines = {}
        
        # Default configuration
        self.default_config = {
            'parallel_filtering': True,
            'max_workers': 4,
            'timeout_seconds': 30,
            'fallback_on_error': True,
            'cache_filters': True,
            'adaptive_filtering': True,  # Adjust based on result quality
            'min_results_threshold': 5,  # Minimum results before applying strict filtering
        }
        
        # Merge configurations
        self.config = {**self.default_config, **self.config}
        
        # Statistics
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'total_results_processed': 0,
            'average_processing_time': 0.0,
            'filter_usage': {}
        }
        
        # Initialize default filters
        self._initialize_default_filters()
        
        FilterManager._initialized = True
        self.logger.info("FilterManager initialized successfully")
    
    def _initialize_default_filters(self) -> None:
        """Initialize the default set of filters."""
        try:
            # Import filter classes
            from ..filters.relevance_filter import RelevanceFilter
            from ..filters.quality_filter import QualityFilter
            from ..filters.duplicate_filter import DuplicateFilter
            from ..filters.domain_filter import DomainFilter
            from ..filters.content_filter import ContentFilter
            from ..filters.exact_phrase_filter import ExactPhraseFilter
            
            # Create filter instances
            self.filters = {
                'relevance': RelevanceFilter(),
                'quality': QualityFilter(),
                'duplicate': DuplicateFilter(),
                'domain': DomainFilter(),
                'content': ContentFilter(),
                'exact_phrase': ExactPhraseFilter()
            }
            
            # Create default pipelines for different search types
            self._create_default_pipelines()
            
            self.logger.info(f"Initialized {len(self.filters)} default filters")
            
        except ImportError as e:
            self.logger.warning(f"Could not import some filters: {e}")
            self.logger.warning("Operating with reduced filtering capabilities")
    
    def _create_default_pipelines(self) -> None:
        """Create default filter pipelines for different search types."""
        # General pipeline for most search types
        general_pipeline = FilterPipeline([
            self.filters['relevance'],
            self.filters['quality'],
            self.filters['duplicate'],
            self.filters['domain']
        ])
        
        # Content-focused pipeline for filetype searches
        content_pipeline = FilterPipeline([
            self.filters['content'],
            self.filters['relevance'],
            self.filters['quality'], 
            self.filters['duplicate']
        ])
        
        # Exact phrase pipeline for quoted searches - strict filtering
        exact_phrase_pipeline = FilterPipeline([
            self.filters['exact_phrase'],  # Primary filter for phrase matching
            self.filters['duplicate']      # Only remove duplicates, keep all phrase matches
        ])
        
        # Brute search pipeline with exact phrase filtering
        brute_pipeline = FilterPipeline([
            self.filters['exact_phrase'],  # First apply exact phrase filtering
            self.filters['relevance'],
            self.filters['quality'],
            self.filters['duplicate']
        ])
        
        # Store pipelines
        self.pipelines = {
            'default': general_pipeline,
            'general': general_pipeline,
            'brute': brute_pipeline,           # Use exact phrase filtering for brute searches
            'exact_phrase': exact_phrase_pipeline, # Dedicated exact phrase pipeline
            'filetype': content_pipeline,
            'content': content_pipeline,
            'corporate': general_pipeline,
            'location': general_pipeline,
            'proximity': general_pipeline,
            'language': general_pipeline,
            'date': general_pipeline,
            'news': general_pipeline
        }
    
    async def process_results(
        self,
        results: List[Dict[str, Any]],
        search_type: str = 'general',
        query_context: Optional[Dict[str, Any]] = None,
        filter_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Main interface for processing search results through the filtering system.
        
        Args:
            results: Raw search results to filter and rank
            search_type: Type of search ('filetype', 'corporate', 'location', etc.)
            query_context: Additional context about the query
            filter_config: Optional configuration for this filtering request
            
        Returns:
            Dictionary with:
            - 'primary': List of high-quality results
            - 'secondary': List of lower-quality but potentially useful results
            - 'metadata': Processing information and statistics
        """
        start_time = time.time()
        request_id = f"req_{int(time.time() * 1000)}"
        
        self.stats['total_requests'] += 1
        
        try:
            self.logger.info(
                f"[{request_id}] Processing {len(results)} results for "
                f"search_type='{search_type}'"
            )
            
            if not results:
                return self._empty_response("No results provided")
            
            # Create filtering context
            context = self._create_context(search_type, query_context, filter_config)
            
            # Adaptive filtering: adjust strictness based on result count
            if self.config['adaptive_filtering']:
                context = self._adapt_filtering_context(context, len(results))
            
            # Select appropriate filter pipeline
            pipeline = self._select_pipeline(search_type, context)
            
            # Apply filters
            filter_results = await self._apply_filters(results, context, pipeline)
            
            # Process results (combine, score, classify)
            processed_results = await self.result_processor.process_results(
                results, filter_results, context
            )
            
            # Update statistics
            processing_time = time.time() - start_time
            self._update_stats(request_id, search_type, len(results), processing_time, True)
            
            # Add processing metadata
            processed_results['metadata'].update({
                'request_id': request_id,
                'search_type': search_type,
                'processing_time': processing_time,
                'filters_applied': [f.name for f in pipeline.filters] if pipeline else [],
                'context': context.__dict__ if hasattr(context, '__dict__') else {}
            })
            
            self.logger.info(
                f"[{request_id}] Successfully processed {len(results)} results -> "
                f"{len(processed_results['primary'])} primary, "
                f"{len(processed_results['secondary'])} secondary "
                f"in {processing_time:.2f}s"
            )
            
            return processed_results
            
        except Exception as e:
            self.logger.error(f"[{request_id}] Error processing results: {e}")
            self._update_stats(request_id, search_type, len(results), 0, False)
            
            if self.config['fallback_on_error']:
                return self._fallback_response(results, search_type, str(e))
            else:
                return self._empty_response(f"Processing error: {str(e)}")
    
    def _create_context(
        self,
        search_type: str,
        query_context: Optional[Dict[str, Any]],
        filter_config: Optional[Dict[str, Any]]
    ) -> FilterContext:
        """Create filtering context from parameters."""
        context_data = query_context or {}
        
        return FilterContext(
            search_type=search_type,
            query=context_data.get('query', ''),
            query_context=context_data,
            user_preferences=filter_config,
            filter_strictness=filter_config.get('strictness', 0.5) if filter_config else 0.5
        )
    
    def _adapt_filtering_context(
        self,
        context: FilterContext,
        result_count: int
    ) -> FilterContext:
        """
        Adapt filtering context based on result count and quality.
        
        Args:
            context: Original filtering context
            result_count: Number of results to filter
            
        Returns:
            Adapted filtering context
        """
        # Less strict filtering for smaller result sets
        if result_count < self.config['min_results_threshold']:
            context.filter_strictness = max(0.1, context.filter_strictness - 0.3)
            self.logger.debug(
                f"Reduced filter strictness to {context.filter_strictness:.2f} "
                f"for {result_count} results"
            )
        
        # More strict filtering for very large result sets
        elif result_count > 200:
            context.filter_strictness = min(0.9, context.filter_strictness + 0.2)
            self.logger.debug(
                f"Increased filter strictness to {context.filter_strictness:.2f} "
                f"for {result_count} results"
            )
        
        return context
    
    def _select_pipeline(
        self,
        search_type: str,
        context: FilterContext
    ) -> Optional[FilterPipeline]:
        """
        Select appropriate filter pipeline for the search type.
        
        Args:
            search_type: Type of search
            context: Filtering context
            
        Returns:
            FilterPipeline to use, or None if no pipeline available
        """
        # Try search type specific pipeline first
        if search_type in self.pipelines:
            pipeline = self.pipelines[search_type]
            self.logger.debug(f"Using {search_type} pipeline")
            return pipeline
        
        # Fall back to default pipeline
        if 'default' in self.pipelines:
            pipeline = self.pipelines['default']
            self.logger.debug(f"Using default pipeline for {search_type}")
            return pipeline
        
        self.logger.warning(f"No pipeline available for {search_type}")
        return None
    
    async def _apply_filters(
        self,
        results: List[Dict[str, Any]],
        context: FilterContext,
        pipeline: Optional[FilterPipeline]
    ) -> List[FilterResult]:
        """
        Apply filters to results using the specified pipeline.
        
        Args:
            results: Results to filter
            context: Filtering context
            pipeline: Filter pipeline to use
            
        Returns:
            List of FilterResult objects
        """
        if not pipeline:
            # Create basic filter results if no pipeline available
            return [
                FilterResult(
                    result_id=f"result_{i}",
                    score=50.0,  # Neutral score
                    tier=3,      # Medium tier
                    classification='secondary',
                    reasoning="No filtering pipeline available",
                    metadata={'no_pipeline': True},
                    processed_at=time.time()
                ) for i in range(len(results))
            ]
        
        try:
            # Apply the filter pipeline
            filter_results = await asyncio.wait_for(
                pipeline.process(results, context),
                timeout=self.config['timeout_seconds']
            )
            
            return filter_results
            
        except asyncio.TimeoutError:
            self.logger.warning(f"Filter pipeline timed out after {self.config['timeout_seconds']}s")
            return self._create_timeout_results(results)
            
        except Exception as e:
            self.logger.error(f"Error applying filter pipeline: {e}")
            return self._create_error_results(results, str(e))
    
    def _create_timeout_results(self, results: List[Dict[str, Any]]) -> List[FilterResult]:
        """Create filter results for timeout situations."""
        return [
            FilterResult(
                result_id=f"result_{i}",
                score=40.0,  # Lower score due to timeout
                tier=3,
                classification='secondary',
                reasoning="Filter processing timed out",
                metadata={'timeout': True},
                processed_at=time.time()
            ) for i in range(len(results))
        ]
    
    def _create_error_results(
        self,
        results: List[Dict[str, Any]],
        error_msg: str
    ) -> List[FilterResult]:
        """Create filter results for error situations."""
        return [
            FilterResult(
                result_id=f"result_{i}",
                score=30.0,  # Low score due to error
                tier=4,
                classification='secondary',
                reasoning=f"Filter error: {error_msg}",
                metadata={'error': True, 'error_message': error_msg},
                processed_at=time.time()
            ) for i in range(len(results))
        ]
    
    def _empty_response(self, reason: str) -> Dict[str, Any]:
        """Create empty response structure."""
        return {
            'primary': [],
            'secondary': [],
            'metadata': {
                'total_input': 0,
                'primary_count': 0,
                'secondary_count': 0,
                'filtered_count': 0,
                'error': reason,
                'processed_at': time.time()
            }
        }
    
    def _fallback_response(
        self,
        results: List[Dict[str, Any]],
        search_type: str,
        error_msg: str
    ) -> Dict[str, Any]:
        """
        Create fallback response that returns original results with minimal processing.
        
        Args:
            results: Original results
            search_type: Search type
            error_msg: Error message
            
        Returns:
            Fallback response structure
        """
        # Convert raw results to basic processed format
        processed_results = []
        
        for i, result in enumerate(results):
            processed_result = {
                'title': result.get('title', 'No Title'),
                'url': result.get('url', ''),
                'snippet': result.get('snippet', result.get('description', '')),
                'source': result.get('source', result.get('engine', 'unknown')),
                'final_score': 50.0,  # Neutral score
                'tier': 3,
                'classification': 'secondary',
                'relevance_score': 50.0,
                'quality_score': 50.0,
                'authority_score': 50.0,
                'freshness_score': 50.0,
                'filter_scores': {},
                'reasoning': [f"Fallback mode: {error_msg}"],
                'metadata': {'fallback': True, 'original_index': i},
                'processed_at': time.time(),
                'processing_time': 0.0
            }
            processed_results.append(processed_result)
        
        return {
            'primary': processed_results[:10],  # Top 10 as primary
            'secondary': processed_results[10:], # Rest as secondary
            'metadata': {
                'total_input': len(results),
                'primary_count': min(10, len(results)),
                'secondary_count': max(0, len(results) - 10),
                'filtered_count': 0,
                'fallback_mode': True,
                'error': error_msg,
                'search_type': search_type,
                'processed_at': time.time()
            }
        }
    
    def _update_stats(
        self,
        request_id: str,
        search_type: str,
        result_count: int,
        processing_time: float,
        success: bool
    ) -> None:
        """Update processing statistics."""
        if success:
            self.stats['successful_requests'] += 1
        else:
            self.stats['failed_requests'] += 1
        
        self.stats['total_results_processed'] += result_count
        
        # Update average processing time
        if self.stats['total_requests'] > 0:
            total_time = (
                self.stats.get('total_processing_time', 0.0) + processing_time
            )
            self.stats['total_processing_time'] = total_time
            self.stats['average_processing_time'] = (
                total_time / self.stats['successful_requests']
            ) if self.stats['successful_requests'] > 0 else 0.0
        
        # Track filter usage by search type
        if search_type not in self.stats['filter_usage']:
            self.stats['filter_usage'][search_type] = 0
        self.stats['filter_usage'][search_type] += 1
    
    # Utility methods for search type integration
    
    def add_filter(self, name: str, filter_instance: BaseFilter) -> None:
        """Add a new filter to the manager."""
        self.filters[name] = filter_instance
        self.logger.info(f"Added filter: {name}")
    
    def remove_filter(self, name: str) -> None:
        """Remove a filter from the manager."""
        if name in self.filters:
            del self.filters[name]
            self.logger.info(f"Removed filter: {name}")
    
    def create_custom_pipeline(
        self,
        name: str,
        filter_names: List[str]
    ) -> None:
        """
        Create a custom filter pipeline.
        
        Args:
            name: Name for the pipeline
            filter_names: List of filter names to include
        """
        filters = []
        for filter_name in filter_names:
            if filter_name in self.filters:
                filters.append(self.filters[filter_name])
            else:
                self.logger.warning(f"Filter '{filter_name}' not found")
        
        if filters:
            self.pipelines[name] = FilterPipeline(filters)
            self.logger.info(f"Created pipeline '{name}' with {len(filters)} filters")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics."""
        stats = self.stats.copy()
        
        # Add filter stats
        stats['filter_stats'] = {}
        for name, filter_instance in self.filters.items():
            stats['filter_stats'][name] = filter_instance.get_stats()
        
        # Add processor stats
        stats['processor_stats'] = self.result_processor.get_stats()
        
        return stats
    
    def reset_stats(self) -> None:
        """Reset all statistics."""
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'total_results_processed': 0,
            'average_processing_time': 0.0,
            'filter_usage': {}
        }
        
        # Reset filter stats
        for filter_instance in self.filters.values():
            filter_instance.reset_stats()
        
        self.logger.info("Reset all FilterManager statistics")

# Global instance
_filter_manager = None

def get_filter_manager(config: Optional[Dict[str, Any]] = None) -> FilterManager:
    """Get the global FilterManager instance."""
    global _filter_manager
    if _filter_manager is None:
        _filter_manager = FilterManager(config)
    return _filter_manager