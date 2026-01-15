#!/usr/bin/env python3
"""
OR Search Type - Run multiple independent searches in parallel
Syntax: query1 OR query2 or query1 / query2

Examples:
- climate change OR global warming
- Tesla / Apple / Microsoft
- machine learning OR artificial intelligence OR deep learning
"""

import sys
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)


class OrSearcher:
    """Handle OR searches by running alternatives in parallel"""
    
    def __init__(self, additional_args: List[str] = None):
        self.additional_args = additional_args or []
    
    def split_or_query(self, query: str) -> List[str]:
        """Split query by OR operator into separate queries"""
        # Handle both / and OR
        query = query.replace('/', ' OR ').replace(' OR OR ', ' OR ')
        return [q.strip() for q in query.split(' OR ') if q.strip()]
    
    async def search_single_query(self, query: str, index: int) -> Dict[str, Any]:
        """Run a single search query"""
        try:
            # Import main.py's SearchRouter to route each sub-query
            from main import SearchRouter
            
            print(f"\n🔍 Running sub-query {index + 1}: '{query}'")
            
            # Create a router instance for this sub-query
            router = SearchRouter()
            
            # Analyze what type of search this is
            search_type, _ = router.analyze_query(query)
            
            # For now, we'll collect the search type info
            # In a full implementation, we'd capture the actual results
            return {
                'query': query,
                'search_type': search_type,
                'index': index,
                'status': 'completed'
            }
            
        except Exception as e:
            logger.error(f"Error searching query '{query}': {e}")
            return {
                'query': query,
                'index': index,
                'error': str(e),
                'status': 'failed'
            }
    
    async def search(self, query: str) -> Dict[str, Any]:
        """Run OR search with parallel execution"""
        # Split the query
        sub_queries = self.split_or_query(query)
        
        if len(sub_queries) < 2:
            return {
                'error': 'OR search requires at least 2 alternatives',
                'original_query': query,
                'sub_queries': sub_queries
            }
        
        print(f"🚀 Running {len(sub_queries)} searches in parallel...")
        print(f"📋 Sub-queries: {sub_queries}")
        
        # Create tasks for parallel execution
        tasks = [
            self.search_single_query(sub_query, i) 
            for i, sub_query in enumerate(sub_queries)
        ]
        
        # Run all searches in parallel
        start_time = datetime.now()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = (datetime.now() - start_time).total_seconds()
        
        # Process results
        successful_results = []
        failed_results = []
        
        for result in results:
            if isinstance(result, Exception):
                failed_results.append(str(result))
            elif 'error' in result:
                failed_results.append(result)
            else:
                successful_results.append(result)
        
        return {
            'original_query': query,
            'sub_queries': sub_queries,
            'total_queries': len(sub_queries),
            'successful': len(successful_results),
            'failed': len(failed_results),
            'results': successful_results,
            'errors': failed_results,
            'parallel_execution_time': elapsed,
            'search_type': 'or'
        }
    
    def detect_or_operator(self, query: str) -> bool:
        """Check if query contains OR operator"""
        return ' OR ' in query or '/' in query


def main():
    """Test the OR search functionality"""
    import argparse
    
    parser = argparse.ArgumentParser(description='OR Search - Run multiple searches in parallel')
    parser.add_argument('query', help='Query with OR operator (e.g., "climate change OR global warming")')
    
    args = parser.parse_args()
    
    searcher = OrSearcher()
    
    print(f"🔀 OR Search Test")
    print(f"📝 Query: {args.query}")
    print("=" * 60)
    
    # Run async search
    result = asyncio.run(searcher.search(args.query))
    
    if 'error' in result:
        print(f"❌ Error: {result['error']}")
    else:
        print(f"\n✅ Parallel search completed in {result['parallel_execution_time']:.2f}s")
        print(f"📊 Results: {result['successful']} successful, {result['failed']} failed")
        
        for res in result['results']:
            print(f"\n🔹 Query {res['index'] + 1}: '{res['query']}'")
            print(f"   Search type: {res['search_type']}")
            print(f"   Status: {res['status']}")


if __name__ == "__main__":
    main()