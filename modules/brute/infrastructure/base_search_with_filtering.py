#!/usr/bin/env python3
"""
Base Search Class with Filtering Support
Provides common filtering functionality for all search types
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseSearchWithFiltering(ABC):
    """Base class for search types that support result filtering"""
    
    def __init__(self):
        self.filtered_results = []
        self.filter_stats = {
            'total_filtered': 0,
            'by_type': {}
        }
    
    def add_filtered_result(self, result: Dict[str, Any], filter_reason: str, 
                          filter_type: str, additional_metadata: Optional[Dict] = None) -> None:
        """
        Add a result to the filtered results list
        
        Args:
            result: The search result that was filtered out
            filter_reason: Human-readable reason for filtering
            filter_type: Type of filter (e.g., 'filetype_mismatch', 'phrase_mismatch', 'domain_filter')
            additional_metadata: Any additional metadata specific to the filter type
        """
        # Ensure required fields
        filtered_result = result.copy()
        filtered_result['filter_reason'] = filter_reason
        filtered_result['filter_type'] = filter_type
        
        # Add additional metadata if provided
        if additional_metadata:
            filtered_result.update(additional_metadata)
        
        # Track in filtered results
        self.filtered_results.append(filtered_result)
        
        # Update statistics
        self.filter_stats['total_filtered'] += 1
        if filter_type not in self.filter_stats['by_type']:
            self.filter_stats['by_type'][filter_type] = 0
        self.filter_stats['by_type'][filter_type] += 1
        
        logger.debug(f"Filtered out result: {result.get('url', 'Unknown URL')} - Reason: {filter_reason}")
    
    def get_filtered_results(self) -> List[Dict[str, Any]]:
        """Get all filtered results"""
        return self.filtered_results
    
    def get_filter_stats(self) -> Dict[str, Any]:
        """Get filtering statistics"""
        return self.filter_stats
    
    def apply_standard_filters(self, result: Dict[str, Any], filters: List[str]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Apply standard filters to a result
        
        Args:
            result: The search result to check
            filters: List of filter names to apply
            
        Returns:
            Tuple of (passes_filters, filter_reason, filter_type)
        """
        # This can be extended with common filters
        # For now, derived classes will implement their specific filters
        return True, None, None
    
    def format_output_with_filters(self, base_output: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add filtered results to the standard output format
        
        Args:
            base_output: The base output dictionary
            
        Returns:
            Output dictionary with filtered results added
        """
        output = base_output.copy()
        
        # Add filtered results
        output['filtered_results'] = self.filtered_results
        output['total_filtered'] = self.filter_stats['total_filtered']
        output['filter_stats'] = self.filter_stats
        
        # Log summary
        if self.filter_stats['total_filtered'] > 0:
            logger.info(f"Filtered out {self.filter_stats['total_filtered']} results:")
            for filter_type, count in self.filter_stats['by_type'].items():
                logger.info(f"  - {filter_type}: {count} results")
        
        return output
    
    @abstractmethod
    async def search(self, *args, **kwargs) -> Dict[str, Any]:
        """Abstract search method to be implemented by derived classes"""
        pass


class CommonFilters:
    """Common filter implementations that can be reused across search types"""
    
    @staticmethod
    def check_domain_blocklist(url: str, blocklist: List[str]) -> bool:
        """Check if URL domain is in blocklist"""
        from urllib.parse import urlparse
        try:
            domain = urlparse(url).netloc.lower()
            return any(blocked in domain for blocked in blocklist)
        except Exception as e:
            return False
    
    @staticmethod
    def check_duplicate_content(result: Dict[str, Any], seen_content: set) -> bool:
        """Check if content (title + snippet) is duplicate"""
        content_key = f"{result.get('title', '')}|{result.get('snippet', result.get('description', ''))}"
        if content_key in seen_content:
            return True
        seen_content.add(content_key)
        return False
    
    @staticmethod
    def check_quality_threshold(result: Dict[str, Any], min_score: float = 0.3) -> bool:
        """Check if result meets minimum quality score"""
        score = result.get('confidence_score', 1.0)
        return score >= min_score
    
    @staticmethod
    def check_content_length(result: Dict[str, Any], min_length: int = 50) -> bool:
        """Check if content meets minimum length requirements"""
        snippet = result.get('snippet', result.get('description', ''))
        return len(str(snippet)) >= min_length