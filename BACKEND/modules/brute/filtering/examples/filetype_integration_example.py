#!/usr/bin/env python3
"""
Example: Integrating Filtering System with FileType Search
Shows how to modify search types to use FilterManager and QueryNodeStorage
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path

# Add these imports to filetype.py
from brute.filtering.core.filter_manager import FilterManager
from Search_Integration.search_type_adapter import FileTypeSearchAdapter
from brute.filtering.integration.recall_filter_bridge import RecallFilterBridge
from brute.filtering.config import get_filter_config
from brute.infrastructure.query_node_storage_v2 import QueryNodeStorageV2

logger = logging.getLogger(__name__)


class EnhancedFileTypeSearcher:
    """
    Example of how to enhance FileTypeSearcher with filtering and streaming
    This shows the modifications needed for filetype.py
    """
    
    def __init__(self, 
                 recall_config: Optional[RecallConfig] = None,
                 filter_profile: str = 'balanced',
                 node_storage_path: str = "search_graph.db"):
        # Existing initialization
        self.recall_optimizer = RecallOptimizer(recall_config) if recall_config else None
        self.query_expander = QueryExpander() if RECALL_MODULES_AVAILABLE else None
        
        # NEW: Initialize filtering and storage
        self.filter_manager = FilterManager()
        self.node_storage = QueryNodeStorageV2(node_storage_path)
        self.filter_adapter = FileTypeSearchAdapter(
            self.filter_manager,
            self.node_storage,
            self.recall_optimizer
        )
        
        # NEW: Create recall-filter bridge
        if self.recall_optimizer:
            self.recall_filter_bridge = RecallFilterBridge(
                self.recall_optimizer,
                self.filter_manager
            )
        else:
            self.recall_filter_bridge = None
        
        # Filter configuration
        self.filter_profile = filter_profile
        self.stats = {
            'queries_executed': 0,
            'results_filtered': 0,
            'results_stored': 0
        }
    
    async def search_filetype(self, 
                            base_query: str, 
                            filetype_query: str,
                            max_results_per_engine: int = 50,
                            enable_url_filtering: bool = None,
                            # NEW parameters
                            project_id: str = "default",
                            stream_callback: Optional[Callable] = None,
                            filter_config: Optional[Dict[str, Any]] = None,
                            store_results: bool = True) -> Dict:
        """
        Enhanced search_filetype with filtering and streaming support
        
        New parameters:
            project_id: Project identifier for node storage
            stream_callback: Async callback for streaming results
            filter_config: Override filter configuration
            store_results: Whether to store in QueryNodeStorage
        """
        # Existing setup code...
        target_extensions = self._get_target_extensions(filetype_query)
        if not target_extensions:
            return {'error': f"Unknown filetype: {filetype_query}"}
        
        logger.info(f"Searching for filetypes {target_extensions} related to query: '{base_query}'")
        
        # NEW: Create query node for tracking
        query_node_id = None
        if store_results:
            query_node = self.node_storage.create_query_node(
                query_text=f"{base_query} {filetype_query}",
                query_type="filetype",
                engine="enhanced_filetype",
                parameters={
                    'base_query': base_query,
                    'filetype': filetype_query,
                    'extensions': target_extensions,
                    'filter_profile': self.filter_profile
                },
                project_id=project_id
            )
            query_node_id = query_node['query_id']
        
        # NEW: Set up streaming processor
        streaming_processor = None
        if stream_callback:
            _, streaming_processor = await self.filter_adapter.create_streaming_processor(
                query=base_query,
                project_id=project_id,
                stream_callback=stream_callback
            )
        
        # Initialize result collection
        seen_urls = set()
        all_results = []
        stats_by_source = {}
        search_round = 1
        total_rounds = self.recall_optimizer.config.search_rounds if self.recall_optimizer else 1
        
        # Execute search rounds/waves
        while search_round <= total_rounds:
            # NEW: Get filter configuration for this round
            round_filter_config = None
            if self.recall_filter_bridge:
                round_filter_config = self.recall_filter_bridge.get_filter_config_for_round(
                    round_num=search_round,
                    current_results=len(all_results),
                    search_type='filetype'
                )
            
            # Use provided filter config or round-specific
            active_filter_config = filter_config or round_filter_config or get_filter_config(
                self.filter_profile, 'filetype'
            )
            
            # Get search strategy for this round
            if self.recall_optimizer:
                strategy = self.recall_optimizer.get_search_strategy(
                    'filetype', 
                    current_results=len(all_results),
                    round_num=search_round
                )
            else:
                strategy = {'use_expansion': False}
            
            # Existing search logic...
            round_results = []
            
            # Execute searches (existing code)
            for engine in self._get_engines_for_round(search_round, strategy):
                try:
                    # Generate query variations
                    variations = await self.generate_search_variations(
                        base_query, target_extensions, engine, search_round=search_round
                    )
                    
                    # Execute search
                    engine_results = await self._search_engine(
                        engine, variations, max_results_per_engine
                    )
                    
                    # NEW: Process results through filtering pipeline
                    for result in engine_results:
                        # Skip if already seen
                        url = result.get('url', '')
                        if url in seen_urls:
                            continue
                        
                        seen_urls.add(url)
                        
                        # NEW: Stream processing if enabled
                        if streaming_processor:
                            filtered_result = await streaming_processor(result)
                            if filtered_result:
                                round_results.append(filtered_result)
                                all_results.append(filtered_result)
                        else:
                            # Batch processing
                            round_results.append(result)
                    
                except Exception as e:
                    logger.error(f"Error searching {engine}: {e}")
            
            # NEW: Batch filtering if not streaming
            if round_results and not streaming_processor:
                filtered_data = await self.filter_adapter.process_results_with_filtering(
                    results=round_results,
                    query=base_query,
                    query_context={
                        'filetype': filetype_query,
                        'extensions': target_extensions,
                        'round': search_round
                    },
                    filter_config=active_filter_config,
                    store_in_nodes=store_results,
                    query_id=query_node_id
                )
                
                # Add filtered results
                all_results.extend(filtered_data['results'])
                self.stats['results_filtered'] += len(filtered_data['results'])
            
            # Check if we should continue
            if self.recall_optimizer:
                should_continue = self.recall_optimizer.should_continue_searching(
                    len(all_results), search_round, 'filetype'
                )
                if not should_continue:
                    break
            
            search_round += 1
        
        # NEW: Update query node with final stats
        if query_node_id:
            self.node_storage.update_query_node_stats(
                query_node_id,
                result_count=len(all_results),
                execution_time_ms=0  # Calculate actual time
            )
        
        # Prepare final response
        self.stats['queries_executed'] += 1
        
        return {
            'query': base_query,
            'filetype': filetype_query,
            'total_results': len(all_results),
            'results': all_results,
            'stats_by_source': stats_by_source,
            'rounds_executed': search_round,
            'filter_stats': self.filter_adapter.stats,
            'query_node_id': query_node_id
        }
    
    async def search_filetype_with_waves(self,
                                        base_query: str,
                                        filetype_query: str,
                                        wave_configs: Optional[List[Dict]] = None,
                                        **kwargs) -> Dict:
        """
        Alternative interface using explicit wave configurations
        """
        # This would use the wave executor pattern from the expert recommendations
        pass
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.node_storage:
            self.node_storage.close()


# Example usage function showing how to use the enhanced searcher
async def example_filtered_search():
    """Example of using the enhanced filetype searcher"""
    
    # Create searcher with maximum recall and research scoring
    searcher = EnhancedFileTypeSearcher(
        recall_config=get_maximum_recall_config(),
        filter_profile='research',
        node_storage_path="search_graph.db"
    )
    
    # Define streaming callback
    async def handle_streaming_result(result: Dict[str, Any]):
        print(f"[STREAM] {result.get('title')} - "
              f"Score: {result.get('filter_score', 0):.2f}, "
              f"Tier: {result.get('filter_tier', 4)}")
    
    # Execute search with streaming
    results = await searcher.search_filetype(
        base_query="machine learning algorithms",
        filetype_query="pdf!",
        max_results_per_engine=100,
        enable_url_filtering=False,  # Maximum recall
        project_id="ml_research",
        stream_callback=handle_streaming_result,
        filter_config={
            'include_tiers': [1, 2, 3],  # Exclude tier 4
            'min_score': 0.4,
            'enable_clustering': True
        }
    )
    
    print(f"\nSearch completed:")
    print(f"Total results: {results['total_results']}")
    print(f"Rounds executed: {results['rounds_executed']}")
    print(f"Filter stats: {results['filter_stats']}")
    
    # Show tier distribution
    tier_counts = {}
    for result in results['results']:
        tier = result.get('filter_tier', 4)
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
    
    print(f"\nResults by tier:")
    for tier in sorted(tier_counts.keys()):
        print(f"  Tier {tier}: {tier_counts[tier]} results")


# Minimal changes needed for existing filetype.py:
"""
1. Add imports at the top:
   from brute.filtering.core.filter_manager import FilterManager
   from Search_Integration.search_type_adapter import FileTypeSearchAdapter
   from brute.infrastructure.query_node_storage_v2 import QueryNodeStorageV2

2. In __init__, add:
   self.filter_manager = FilterManager()
   self.node_storage = QueryNodeStorageV2() if store_results else None
   self.filter_adapter = FileTypeSearchAdapter(self.filter_manager, self.node_storage)

3. In search_filetype, add parameters:
   project_id: str = "default"
   stream_callback: Optional[Callable] = None
   filter_config: Optional[Dict[str, Any]] = None

4. After collecting results from each engine:
   if self.filter_adapter:
       filtered_data = await self.filter_adapter.process_results_with_filtering(
           results=engine_results,
           query=base_query,
           query_context={'filetype': filetype_query},
           filter_config=filter_config
       )
       results = filtered_data['results']

5. For streaming support:
   if stream_callback and result:
       await stream_callback(result)

This maintains backward compatibility while adding powerful filtering capabilities!
"""