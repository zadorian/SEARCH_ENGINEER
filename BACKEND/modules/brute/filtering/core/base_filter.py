"""
Base Filter Abstract Class

Provides the foundation for all filtering operations in the Search_Engineer
filtering system. All specialized filters inherit from this base class.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple, Optional
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class FilterResult:
    """Result of filtering operation"""
    result_id: str
    score: float  # 0-100 scale
    tier: int     # 1-4 (1=highest quality, 4=lowest)
    classification: str  # 'primary' or 'secondary'
    reasoning: str
    metadata: Dict[str, Any]
    processed_at: float

@dataclass 
class FilterContext:
    """Context information for filtering"""
    search_type: str
    query: str
    query_context: Dict[str, Any]
    user_preferences: Optional[Dict[str, Any]] = None
    filter_strictness: float = 0.5  # 0.0-1.0 scale

class BaseFilter(ABC):
    """
    Abstract base class for all filters in the Search_Engineer system.
    
    All filters must implement the filter_results method and can optionally
    override configuration and validation methods.
    """
    
    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the base filter.
        
        Args:
            name: Human-readable name for this filter
            config: Optional configuration dictionary
        """
        self.name = name
        self.config = config or {}
        self.stats = {
            'total_processed': 0,
            'total_filtered': 0,
            'total_time': 0.0,
            'average_time': 0.0
        }
        self.logger = logging.getLogger(f"{__name__}.{name}")
        
    @abstractmethod
    async def filter_results(
        self, 
        results: List[Dict[str, Any]], 
        context: FilterContext
    ) -> List[FilterResult]:
        """
        Filter and score a list of search results.
        
        Args:
            results: List of raw search results to filter
            context: Filtering context with query and search type info
            
        Returns:
            List of FilterResult objects with scores and classifications
        """
        pass
    
    async def process(
        self, 
        results: List[Dict[str, Any]], 
        context: FilterContext
    ) -> List[FilterResult]:
        """
        Main processing method that wraps filter_results with timing and stats.
        
        Args:
            results: List of raw search results
            context: Filtering context
            
        Returns:
            List of FilterResult objects
        """
        if not results:
            return []
            
        start_time = time.time()
        
        try:
            self.logger.debug(f"Processing {len(results)} results with {self.name}")
            
            # Validate inputs
            self.validate_inputs(results, context)
            
            # Apply the filter
            filter_results = await self.filter_results(results, context)
            
            # Update statistics
            processing_time = time.time() - start_time
            self.update_stats(len(results), len(filter_results), processing_time)
            
            self.logger.debug(
                f"{self.name} processed {len(results)} results -> "
                f"{len(filter_results)} filtered in {processing_time:.2f}s"
            )
            
            return filter_results
            
        except Exception as e:
            self.logger.error(f"Error in {self.name} filter: {e}")
            # Return empty results with error information
            return [
                FilterResult(
                    result_id=f"error_{i}",
                    score=0.0,
                    tier=4,
                    classification='secondary',
                    reasoning=f"Filter error: {str(e)}",
                    metadata={'error': True, 'filter': self.name},
                    processed_at=time.time()
                ) for i in range(len(results))
            ]
    
    def validate_inputs(
        self, 
        results: List[Dict[str, Any]], 
        context: FilterContext
    ) -> None:
        """
        Validate inputs before filtering. Override in subclasses for specific validation.
        
        Args:
            results: List of search results
            context: Filtering context
            
        Raises:
            ValueError: If inputs are invalid
        """
        if not isinstance(results, list):
            raise ValueError("Results must be a list")
            
        if not isinstance(context, FilterContext):
            raise ValueError("Context must be a FilterContext object")
            
        if not context.search_type:
            raise ValueError("Search type must be specified in context")
    
    def update_stats(
        self, 
        input_count: int, 
        output_count: int, 
        processing_time: float
    ) -> None:
        """
        Update filter performance statistics.
        
        Args:
            input_count: Number of input results
            output_count: Number of output results
            processing_time: Time taken for processing
        """
        self.stats['total_processed'] += input_count
        self.stats['total_filtered'] += output_count
        self.stats['total_time'] += processing_time
        
        if self.stats['total_processed'] > 0:
            self.stats['average_time'] = (
                self.stats['total_time'] / self.stats['total_processed']
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get filter performance statistics."""
        return {
            'filter_name': self.name,
            'total_processed': self.stats['total_processed'],
            'total_filtered': self.stats['total_filtered'],
            'total_time': self.stats['total_time'],
            'average_time_per_result': self.stats['average_time'],
            'filter_rate': (
                self.stats['total_filtered'] / max(self.stats['total_processed'], 1)
            )
        }
    
    def configure(self, config: Dict[str, Any]) -> None:
        """
        Update filter configuration.
        
        Args:
            config: New configuration dictionary
        """
        self.config.update(config)
        self.logger.info(f"Updated {self.name} configuration: {config}")
    
    def get_config(self) -> Dict[str, Any]:
        """Get current filter configuration."""
        return self.config.copy()
    
    def reset_stats(self) -> None:
        """Reset all performance statistics."""
        self.stats = {
            'total_processed': 0,
            'total_filtered': 0,
            'total_time': 0.0,
            'average_time': 0.0
        }
        self.logger.info(f"Reset statistics for {self.name}")

class FilterPipeline:
    """
    Pipeline for chaining multiple filters together.
    """
    
    def __init__(self, filters: List[BaseFilter]):
        """
        Initialize filter pipeline.
        
        Args:
            filters: List of filters to apply in sequence
        """
        self.filters = filters
        self.logger = logging.getLogger(f"{__name__}.FilterPipeline")
    
    async def process(
        self, 
        results: List[Dict[str, Any]], 
        context: FilterContext
    ) -> List[FilterResult]:
        """
        Process results through all filters in the pipeline.
        
        Args:
            results: Raw search results
            context: Filtering context
            
        Returns:
            Final filtered results from the last filter in the pipeline
        """
        if not results:
            return []
        
        current_results = results
        filter_results = []
        
        for filter_instance in self.filters:
            try:
                filter_results = await filter_instance.process(current_results, context)
                self.logger.debug(
                    f"Pipeline: {filter_instance.name} processed "
                    f"{len(current_results)} -> {len(filter_results)} results"
                )
                
                # Convert FilterResults back to dict format for next filter
                # (if we have more filters in pipeline)
                if filter_instance != self.filters[-1]:
                    current_results = [
                        {
                            'id': fr.result_id,
                            'score': fr.score,
                            'tier': fr.tier,
                            'classification': fr.classification,
                            'metadata': fr.metadata,
                            **results[i]  # Preserve original result data
                        }
                        for i, fr in enumerate(filter_results) if i < len(results)
                    ]
                
            except Exception as e:
                self.logger.error(f"Error in pipeline filter {filter_instance.name}: {e}")
                continue
        
        return filter_results
    
    def get_pipeline_stats(self) -> List[Dict[str, Any]]:
        """Get statistics for all filters in the pipeline."""
        return [filter_instance.get_stats() for filter_instance in self.filters]