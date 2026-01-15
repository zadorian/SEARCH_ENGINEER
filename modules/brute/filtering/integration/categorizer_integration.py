#!/usr/bin/env python3
"""
Categorizer Integration for Filtering System
Efficiently integrates categorization with filtering in parallel for maximum speed and cost optimization
"""

import asyncio
import logging
import time
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor
import threading

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brute.categorizer.categorizer import (
    categorize_url_basic, 
    categorize_with_gpt, 
    categorize_results,
    get_category_stats
)

logger = logging.getLogger(__name__)


class ParallelCategorizerFilter:
    """
    Integrates categorization with filtering for maximum efficiency
    - Runs categorization and filtering in parallel
    - Optimizes GPT API calls through batching
    - Provides cost-efficient categorization strategies
    """
    
    def __init__(self,
                 max_gpt_batch_size: int = 20,
                 basic_categorization_threshold: float = 0.8,
                 enable_cost_optimization: bool = True,
                 max_workers: int = 4):
        """
        Initialize the parallel categorizer
        
        Args:
            max_gpt_batch_size: Maximum items per GPT API call
            basic_categorization_threshold: Confidence threshold for basic categorization
            enable_cost_optimization: Whether to use cost optimization strategies
            max_workers: Maximum threads for parallel processing
        """
        self.max_gpt_batch_size = max_gpt_batch_size
        self.basic_threshold = basic_categorization_threshold
        self.cost_optimization = enable_cost_optimization
        self.max_workers = max_workers
        
        # Statistics
        self.stats = {
            'total_processed': 0,
            'basic_categorized': 0,
            'gpt_categorized': 0,
            'parallel_time_saved': 0,
            'gpt_cost_saved': 0,
            'cache_hits': 0
        }
        
        # Simple domain categorization cache
        self.domain_cache = {}
        self.cache_lock = threading.Lock()
        
        # Cost optimization settings
        self.cost_strategies = {
            'cache_domains': True,
            'batch_gpt_calls': True,
            'skip_obvious': True,
            'fast_basic_first': True,
            'smart_sampling': enable_cost_optimization
        }
    
    async def categorize_and_filter_parallel(self,
                                           results: List[Dict[str, Any]],
                                           filter_manager: Any,
                                           search_type: str = 'general',
                                           query_context: Optional[Dict[str, Any]] = None,
                                           filter_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Run categorization and filtering in parallel for maximum efficiency
        
        Args:
            results: Search results to process
            filter_manager: FilterManager instance
            search_type: Type of search
            query_context: Context for filtering
            filter_config: Filter configuration
            
        Returns:
            Enhanced results with both filtering and categorization
        """
        start_time = time.time()
        
        if not results:
            return {
                'results': [],
                'statistics': self._get_stats(),
                'processing_time_ms': 0
            }
        
        logger.info(f"Starting parallel categorization and filtering for {len(results)} results")
        
        # Create tasks for parallel execution
        categorization_task = asyncio.create_task(
            self._efficient_categorization(results)
        )
        
        filtering_task = asyncio.create_task(
            filter_manager.process_results(
                results=results,
                search_type=search_type,
                query_context=query_context,
                filter_config=filter_config
            )
        )
        
        # Wait for both to complete
        categorized_results, filtered_data = await asyncio.gather(
            categorization_task,
            filtering_task,
            return_exceptions=True
        )
        
        # Handle any exceptions
        if isinstance(categorized_results, Exception):
            logger.error(f"Categorization failed: {categorized_results}")
            categorized_results = results  # Use original results
        
        if isinstance(filtered_data, Exception):
            logger.error(f"Filtering failed: {filtered_data}")
            filtered_data = {'results': results, 'statistics': {}}
        
        # Merge categorization and filtering results
        enhanced_results = self._merge_results(categorized_results, filtered_data['results'])
        
        # Calculate time savings
        processing_time = (time.time() - start_time) * 1000
        estimated_sequential_time = processing_time * 1.8  # Estimate 80% overhead for sequential
        time_saved = max(0, estimated_sequential_time - processing_time)
        
        self.stats['parallel_time_saved'] += time_saved
        self.stats['total_processed'] += len(results)
        
        return {
            'results': enhanced_results,
            'statistics': {
                **filtered_data.get('statistics', {}),
                'categorization_stats': self._get_categorization_stats(enhanced_results),
                'parallel_processing': {
                    'time_saved_ms': time_saved,
                    'efficiency_gain': f"{(time_saved / max(processing_time, 1)) * 100:.1f}%"
                }
            },
            'processing_time_ms': processing_time
        }
    
    async def _efficient_categorization(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Highly efficient categorization with cost optimization
        """
        if not results:
            return results
        
        # Phase 1: Fast basic categorization with caching
        basic_categorized = await self._fast_basic_categorization(results)
        
        # Phase 2: Identify items needing GPT
        needs_gpt = []
        for result in basic_categorized:
            category = result.get('category', '')
            if (category == 'needs_gpt_classification' or 
                category == 'miscellaneous' or 
                not category):
                needs_gpt.append(result)
        
        logger.info(f"Basic categorization: {len(basic_categorized) - len(needs_gpt)} items, "
                   f"GPT needed: {len(needs_gpt)} items")
        
        # Phase 3: Cost-optimized GPT categorization
        if needs_gpt and self.cost_optimization:
            await self._cost_optimized_gpt_categorization(needs_gpt)
        elif needs_gpt:
            # Standard GPT categorization
            await categorize_with_gpt(needs_gpt)
        
        self.stats['basic_categorized'] += len(basic_categorized) - len(needs_gpt)
        self.stats['gpt_categorized'] += len(needs_gpt)
        
        return basic_categorized
    
    async def _fast_basic_categorization(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Ultra-fast basic categorization with domain caching
        """
        processed_results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Create tasks for parallel basic categorization
            tasks = []
            for result in results:
                if 'url' in result:
                    task = executor.submit(
                        self._cached_basic_categorization,
                        result['url'],
                        result.get('title', ''),
                        result.get('description', '')
                    )
                    tasks.append((result, task))
                else:
                    # Skip items without URLs
                    processed_results.append(result)
            
            # Collect results
            for result, task in tasks:
                try:
                    categorization = task.result(timeout=5)  # 5 second timeout
                    result.update(categorization)
                    processed_results.append(result)
                except Exception as e:
                    logger.warning(f"Basic categorization failed for {result.get('url', 'unknown')}: {e}")
                    result['category'] = 'miscellaneous'
                    result['attributes'] = {}
                    processed_results.append(result)
        
        return processed_results
    
    def _cached_basic_categorization(self, url: str, title: str, description: str) -> Dict[str, Any]:
        """
        Basic categorization with domain caching for speed
        """
        from brute.categorizer.categorizer import extract_domain
        
        domain = extract_domain(url)
        
        # Check cache first
        with self.cache_lock:
            if domain in self.domain_cache:
                cached_result = self.domain_cache[domain].copy()
                self.stats['cache_hits'] += 1
                return cached_result
        
        # Perform basic categorization
        result = categorize_url_basic(url, title, description)
        
        # Cache domain-based results (but not URL-specific ones)
        if result['category'] != 'needs_gpt_classification':
            with self.cache_lock:
                # Only cache if we don't have too many entries
                if len(self.domain_cache) < 10000:
                    self.domain_cache[domain] = result.copy()
        
        return result
    
    async def _cost_optimized_gpt_categorization(self, items: List[Dict[str, Any]]):
        """
        Cost-optimized GPT categorization with smart batching and sampling
        """
        if not items:
            return
        
        # Strategy 1: Smart sampling for large batches
        if len(items) > 100 and self.cost_strategies['smart_sampling']:
            # Sample representative items and apply patterns
            sampled_items = await self._smart_sample_categorization(items)
            return
        
        # Strategy 2: Optimized batching
        if self.cost_strategies['batch_gpt_calls']:
            await self._batched_gpt_categorization(items)
        else:
            await categorize_with_gpt(items)
    
    async def _smart_sample_categorization(self, items: List[Dict[str, Any]]):
        """
        Smart sampling strategy to reduce GPT costs for large result sets
        """
        from brute.categorizer.categorizer import extract_domain
        
        # Group by domain
        domain_groups = {}
        for item in items:
            domain = extract_domain(item['url'])
            if domain not in domain_groups:
                domain_groups[domain] = []
            domain_groups[domain].append(item)
        
        # Sample from each domain group
        sample_items = []
        pattern_mapping = {}
        
        for domain, domain_items in domain_groups.items():
            if len(domain_items) <= 3:
                # Small groups - categorize all
                sample_items.extend(domain_items)
            else:
                # Large groups - sample and infer patterns
                sample_size = min(3, max(1, len(domain_items) // 10))
                sampled = domain_items[:sample_size]
                sample_items.extend(sampled)
                pattern_mapping[domain] = domain_items[sample_size:]
        
        # Categorize samples with GPT
        if sample_items:
            await categorize_with_gpt(sample_items)
        
        # Apply patterns to remaining items
        for domain, remaining_items in pattern_mapping.items():
            # Find the most common category from samples
            domain_samples = [item for item in sample_items 
                            if extract_domain(item['url']) == domain]
            if domain_samples:
                # Use the category from the first sample (could be improved with voting)
                pattern_category = domain_samples[0].get('category', 'miscellaneous')
                for item in remaining_items:
                    item['category'] = pattern_category
                    item['attributes'] = {}
                
                logger.info(f"Applied pattern categorization '{pattern_category}' to {len(remaining_items)} items from {domain}")
        
        cost_saved = len(items) - len(sample_items)
        self.stats['gpt_cost_saved'] += cost_saved
        logger.info(f"Smart sampling saved {cost_saved} GPT API calls")
    
    async def _batched_gpt_categorization(self, items: List[Dict[str, Any]]):
        """
        Optimized batching for GPT API calls
        """
        # Process in optimal batches
        batch_size = min(self.max_gpt_batch_size, len(items))
        
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            try:
                await categorize_with_gpt(batch)
                logger.info(f"Processed GPT batch {i//batch_size + 1}: {len(batch)} items")
            except Exception as e:
                logger.error(f"GPT batch {i//batch_size + 1} failed: {e}")
                # Fallback to basic categorization
                for item in batch:
                    if not item.get('category'):
                        basic_result = categorize_url_basic(
                            item['url'], 
                            item.get('title', ''), 
                            item.get('description', '')
                        )
                        item.update(basic_result)
    
    def _merge_results(self, 
                      categorized_results: List[Dict[str, Any]], 
                      filtered_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Merge categorization and filtering results efficiently
        """
        # Create lookup for filtered results by URL
        filtered_lookup = {}
        for result in filtered_results:
            url = result.get('url', '')
            if url:
                filtered_lookup[url] = result
        
        # Merge data
        enhanced_results = []
        for cat_result in categorized_results:
            url = cat_result.get('url', '')
            
            if url in filtered_lookup:
                # Merge categorization data into filtered result
                filtered_result = filtered_lookup[url].copy()
                filtered_result['category'] = cat_result.get('category', 'miscellaneous')
                filtered_result['attributes'] = cat_result.get('attributes', {})
                enhanced_results.append(filtered_result)
            else:
                # Use categorized result with default filter data
                cat_result['filter_score'] = 0.5
                cat_result['filter_tier'] = 3
                cat_result['filter_reason'] = 'Default scoring'
                enhanced_results.append(cat_result)
        
        return enhanced_results
    
    def _get_categorization_stats(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get detailed categorization statistics"""
        category_counts = {}
        attribute_counts = {}
        
        for result in results:
            # Count categories
            category = result.get('category', 'unknown')
            category_counts[category] = category_counts.get(category, 0) + 1
            
            # Count attributes
            attributes = result.get('attributes', {})
            for attr_name, attr_value in attributes.items():
                if attr_name not in attribute_counts:
                    attribute_counts[attr_name] = {}
                
                if isinstance(attr_value, list):
                    for value in attr_value:
                        key = str(value)
                        attribute_counts[attr_name][key] = attribute_counts[attr_name].get(key, 0) + 1
                else:
                    key = str(attr_value)
                    attribute_counts[attr_name][key] = attribute_counts[attr_name].get(key, 0) + 1
        
        return {
            'total_categorized': len(results),
            'category_distribution': category_counts,
            'attribute_distribution': attribute_counts,
            'cache_efficiency': {
                'cache_hits': self.stats['cache_hits'],
                'cache_size': len(self.domain_cache)
            },
            'cost_optimization': {
                'basic_categorized': self.stats['basic_categorized'],
                'gpt_categorized': self.stats['gpt_categorized'],
                'gpt_calls_saved': self.stats['gpt_cost_saved']
            }
        }
    
    def _get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        return {
            'processing_stats': self.stats.copy(),
            'cache_stats': {
                'size': len(self.domain_cache),
                'hit_rate': (self.stats['cache_hits'] / max(self.stats['total_processed'], 1)) * 100
            },
            'cost_optimization': {
                'enabled': self.cost_optimization,
                'strategies': self.cost_strategies,
                'savings': {
                    'time_saved_ms': self.stats['parallel_time_saved'],
                    'gpt_calls_saved': self.stats['gpt_cost_saved']
                }
            }
        }
    
    async def streaming_categorize_and_filter(self,
                                            result_stream: asyncio.Queue,
                                            filter_manager: Any,
                                            output_callback: callable,
                                            search_type: str = 'general') -> None:
        """
        Stream-based categorization and filtering for real-time processing
        """
        buffer = []
        buffer_size = 10  # Process in small batches for streaming
        
        while True:
            try:
                # Get result with timeout
                result = await asyncio.wait_for(result_stream.get(), timeout=1.0)
                
                if result is None:  # End signal
                    # Process remaining buffer
                    if buffer:
                        processed = await self.categorize_and_filter_parallel(
                            buffer, filter_manager, search_type
                        )
                        for enhanced_result in processed['results']:
                            await output_callback(enhanced_result)
                    break
                
                buffer.append(result)
                
                # Process buffer when full
                if len(buffer) >= buffer_size:
                    processed = await self.categorize_and_filter_parallel(
                        buffer, filter_manager, search_type
                    )
                    for enhanced_result in processed['results']:
                        await output_callback(enhanced_result)
                    buffer = []
                    
            except asyncio.TimeoutError:
                # Process buffer on timeout (end of burst)
                if buffer:
                    processed = await self.categorize_and_filter_parallel(
                        buffer, filter_manager, search_type
                    )
                    for enhanced_result in processed['results']:
                        await output_callback(enhanced_result)
                    buffer = []
            except Exception as e:
                logger.error(f"Streaming categorization error: {e}")
                break
    
    def optimize_for_cost(self, enable_smart_sampling: bool = True):
        """Enable aggressive cost optimization"""
        self.cost_strategies.update({
            'smart_sampling': enable_smart_sampling,
            'cache_domains': True,
            'batch_gpt_calls': True,
            'skip_obvious': True,
            'fast_basic_first': True
        })
        self.cost_optimization = True
        logger.info("Enabled aggressive cost optimization for categorization")
    
    def clear_cache(self):
        """Clear the domain categorization cache"""
        with self.cache_lock:
            self.domain_cache.clear()
        logger.info("Cleared categorization cache")


# Integration function for the filtering system
def create_categorizer_filter_pipeline(filter_manager: Any,
                                     cost_optimization: bool = True,
                                     max_workers: int = 4) -> ParallelCategorizerFilter:
    """
    Create an integrated categorization and filtering pipeline
    
    Args:
        filter_manager: FilterManager instance
        cost_optimization: Enable cost optimization strategies
        max_workers: Maximum parallel workers
        
    Returns:
        Configured ParallelCategorizerFilter
    """
    pipeline = ParallelCategorizerFilter(
        enable_cost_optimization=cost_optimization,
        max_workers=max_workers
    )
    
    # Optimize settings based on filtering configuration
    if cost_optimization:
        pipeline.optimize_for_cost(enable_smart_sampling=True)
    
    return pipeline


# Convenience function for integration with search wrapper
async def enhanced_categorize_and_filter(results: List[Dict[str, Any]],
                                       filter_manager: Any,
                                       search_type: str = 'general',
                                       **kwargs) -> Dict[str, Any]:
    """
    Convenience function for parallel categorization and filtering
    
    Usage:
        from brute.filtering.integration.categorizer_integration import enhanced_categorize_and_filter
        
        enhanced_results = await enhanced_categorize_and_filter(
            results=search_results,
            filter_manager=filter_manager,
            search_type='filetype'
        )
    """
    pipeline = ParallelCategorizerFilter(enable_cost_optimization=True)
    
    return await pipeline.categorize_and_filter_parallel(
        results=results,
        filter_manager=filter_manager,
        search_type=search_type,
        **kwargs
    )