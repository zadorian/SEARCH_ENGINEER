#!/usr/bin/env python3
"""
Categorizer Integration - Integrate categorizer with search results
"""

import sys
import asyncio
from pathlib import Path
from typing import List, Dict, Any
import logging

# Add paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'categorizer'))

# Import categorizer
try:
    from brute.categorizer import categorize_results
    CATEGORIZER_AVAILABLE = True
except ImportError as e:
    CATEGORIZER_AVAILABLE = False
    logging.warning(f"Categorizer not available: {e}")

logger = logging.getLogger(__name__)


async def categorize_search_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Categorize search results using the categorizer
    
    Args:
        results: List of search result dictionaries
        
    Returns:
        List of results with 'category' and 'attributes' fields added
    """
    if not CATEGORIZER_AVAILABLE:
        logger.warning("Categorizer not available, skipping categorization")
        return results
    
    try:
        # Run categorizer
        categorized_results = await categorize_results(results)
        
        # Log statistics
        category_counts = {}
        for result in categorized_results:
            cat = result.get('category', 'unknown')
            category_counts[cat] = category_counts.get(cat, 0) + 1
        
        logger.info(f"Categorized {len(results)} results: {category_counts}")
        
        return categorized_results
        
    except Exception as e:
        logger.error(f"Error during categorization: {e}")
        # Return original results if categorization fails
        return results


def integrate_categorizer_with_storage():
    """
    Create a wrapped storage function that categorizes before storing
    """
    from .result_storage import ResultStorage
    
    class CategorizedResultStorage(ResultStorage):
        """Storage that automatically categorizes results"""
        
        async def store_search_results_async(self, 
                                           query: str,
                                           results: List[Dict[str, Any]], 
                                           project_id: str,
                                           aggregate_snippets: bool = True) -> int:
            """
            Async version that categorizes before storing
            """
            # Categorize results
            categorized_results = await categorize_search_results(results)
            
            # Store using parent method (sync)
            return self.store_search_results(
                query=query,
                results=categorized_results,
                project_id=project_id,
                aggregate_snippets=aggregate_snippets
            )
    
    return CategorizedResultStorage


# Wrapper function to categorize existing search results
async def categorize_and_update_results(results: List[Dict[str, Any]], 
                                      include_stats: bool = True) -> Dict[str, Any]:
    """
    Categorize results and return with optional statistics
    
    Args:
        results: Search results to categorize
        include_stats: Whether to include category statistics
        
    Returns:
        Dictionary with categorized results and optional stats
    """
    categorized = await categorize_search_results(results)
    
    output = {
        'results': categorized,
        'total': len(categorized)
    }
    
    if include_stats:
        # Calculate statistics
        stats = {
            'by_category': {},
            'by_attribute': {
                'country': {},
                'filetype': {},
                'has_dates': 0
            }
        }
        
        for result in categorized:
            # Count categories
            cat = result.get('category', 'unknown')
            stats['by_category'][cat] = stats['by_category'].get(cat, 0) + 1
            
            # Count attributes
            attrs = result.get('attributes', {})
            if attrs.get('country'):
                country = attrs['country']
                stats['by_attribute']['country'][country] = \
                    stats['by_attribute']['country'].get(country, 0) + 1
            
            if attrs.get('filetype'):
                ft = attrs['filetype']
                stats['by_attribute']['filetype'][ft] = \
                    stats['by_attribute']['filetype'].get(ft, 0) + 1
            
            if attrs.get('dates'):
                stats['by_attribute']['has_dates'] += 1
        
        output['statistics'] = stats
    
    return output


# Integration with main search pipeline
def create_categorizing_callback(original_callback=None):
    """
    Create a callback that categorizes results before passing to original callback
    """
    async def categorizing_callback(search_data: Dict[str, Any]):
        # Categorize results
        if 'results' in search_data:
            search_data['results'] = await categorize_search_results(
                search_data['results']
            )
        
        # Call original callback if provided
        if original_callback:
            await original_callback(search_data)
    
    return categorizing_callback


# CLI tool for categorizing existing results
async def main():
    """CLI interface for testing categorizer"""
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description='Categorize search results')
    parser.add_argument('input_file', help='JSON file with search results')
    parser.add_argument('-o', '--output', help='Output file (default: stdout)')
    parser.add_argument('-s', '--stats', action='store_true', 
                       help='Include statistics')
    
    args = parser.parse_args()
    
    # Load results
    with open(args.input_file, 'r') as f:
        data = json.load(f)
    
    # Handle different input formats
    if isinstance(data, list):
        results = data
    elif isinstance(data, dict) and 'results' in data:
        results = data['results']
    else:
        print("Error: Input must be a list of results or dict with 'results' key")
        return
    
    # Categorize
    output = await categorize_and_update_results(results, include_stats=args.stats)
    
    # Output
    output_json = json.dumps(output, indent=2, ensure_ascii=False)
    
    if args.output:
        with open(args.output, 'w') as f:
            f.write(output_json)
        print(f"Categorized {len(results)} results -> {args.output}")
    else:
        print(output_json)


if __name__ == "__main__":
    asyncio.run(main())