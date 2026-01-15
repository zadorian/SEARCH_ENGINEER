#!/usr/bin/env python3
"""
Blog Search Operator - Searches blog platforms and blog-specific content
Supports blog:, blogger: operators with schema integration
Leverages blog platforms and Schema.org BlogPosting structured data
"""

import sys
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime
import time

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import event streaming for filtering events
try:
    from brute.infrastructure.base_streamer import SearchTypeEventEmitter
    STREAMING_AVAILABLE = True
except ImportError:
    STREAMING_AVAILABLE = False
    logging.warning("Event streaming not available for blog search")

# BrightData Archive - native cat{blog}! support (17.5 PB cached web data)
try:
    from backdrill.brightdata import BrightDataArchive, search_by_category
    BRIGHTDATA_ARCHIVE_AVAILABLE = True
except ImportError:
    BRIGHTDATA_ARCHIVE_AVAILABLE = False
    BrightDataArchive = None
    search_by_category = None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Blog-specific search engines and platforms
BLOG_ENGINES = [
    'GO',  # Google - with schema search
    'BI',  # Bing
    'BR',  # Brave
    'DD',  # DuckDuckGo
    'YA',  # Yandex
]

# Major blog platforms for site-specific searches
BLOG_PLATFORMS = {
    'medium': 'site:medium.com',
    'wordpress': 'site:wordpress.com OR site:*.wordpress.com',
    'blogger': 'site:blogger.com OR site:*.blogspot.com',
    'devto': 'site:dev.to',
    'hashnode': 'site:hashnode.com OR site:*.hashnode.dev',
    'ghost': 'site:ghost.io OR site:*.ghost.io',
    'substack': 'site:substack.com OR site:*.substack.com',
    'tumblr': 'site:tumblr.com OR site:*.tumblr.com',
    'jekyll': 'site:github.io',  # Many Jekyll blogs hosted on GitHub Pages
    'wix': 'site:wixsite.com OR site:*.wixsite.com',
}

# Schema.org structured data queries for blogs
BLOG_SCHEMAS = [
    'more:pagemap:blogposting',
    'more:pagemap:blogposting-headline',
    'more:pagemap:blogposting-author',
    'more:pagemap:article-articlebody',
    'more:pagemap:creativework-author',
    'more:pagemap:webpage-name blog',
]

class BlogSearch:
    """
    Blog search operator implementation.
    Routes searches to blog platforms and uses schema-enhanced queries.
    """
    
    def __init__(self, event_emitter=None):
        """Initialize blog search with optional event streaming."""
        self.event_emitter = event_emitter
        self.available_engines = self._check_available_engines()
        
        if STREAMING_AVAILABLE and event_emitter:
            self.streamer = SearchTypeEventEmitter(event_emitter)
        else:
            self.streamer = None
    
    def _check_available_engines(self) -> List[str]:
        """Check which blog-supporting engines are available in the system."""
        available = []
        
        # Check ENGINE_CONFIG from brute.py
        try:
            from brute.targeted_searches.brute import ENGINE_CONFIG
            
            for engine_code in BLOG_ENGINES:
                if engine_code in ENGINE_CONFIG:
                    available.append(engine_code)
                    logger.info(f"Blog engine {engine_code} available")
                else:
                    logger.debug(f"Blog engine {engine_code} not configured")
        except ImportError:
            logger.error("Could not import ENGINE_CONFIG from brute.py")
            # Use fallback engines
            available = ['GO', 'BI', 'BR']
        
        if not available:
            logger.warning("No blog engines available, using fallback engines")
            available = ['GO', 'BI', 'BR']
        
        logger.info(f"Available blog engines: {available}")
        return available
    
    def _build_blog_queries(self, query: str, include_platforms: bool = True, 
                           include_schemas: bool = True) -> List[str]:
        """
        Build comprehensive blog search queries.
        
        Args:
            query: The search query
            include_platforms: Whether to include platform-specific searches
            include_schemas: Whether to include schema-enhanced searches
            
        Returns:
            List of search queries optimized for blog content
        """
        queries = []
        
        # Base query
        queries.append(f'blog {query}')
        queries.append(f'"{query}" blog post')
        
        # Platform-specific searches
        if include_platforms:
            for platform_name, platform_filter in BLOG_PLATFORMS.items():
                queries.append(f'{platform_filter} {query}')
        
        # Schema-enhanced searches (Google API only)
        if include_schemas and 'GO' in self.available_engines:
            for schema in BLOG_SCHEMAS:
                queries.append(f'{schema} {query}')
            
            # Specific blog schema combinations
            queries.extend([
                f'more:pagemap:blogposting-headline:"{query}"',
                f'more:pagemap:blogposting {query}',
                f'more:pagemap:article {query} blog',
                f'more:pagemap:blogposting-author {query}',
                f'more:pagemap:blogposting-articlebody {query}',
            ])
        
        # Blog-specific patterns
        queries.extend([
            f'"blog post" {query}',
            f'"blog article" {query}',
            f'tutorial {query} blog',
            f'guide {query} blog',
            f'"how to" {query} blog',
            f'opinion {query} blog',
        ])
        
        return queries
    
    async def search(self, query: str, max_results: int = 200) -> List[Dict[str, Any]]:
        """
        Execute blog search across available engines with blog optimization.
        
        Args:
            query: The search query (without the blog: operator)
            max_results: Maximum results to return
            
        Returns:
            List of search results from blog sources
        """
        # Clean the query
        query = query.strip()
        
        logger.info(f"Starting blog search for: '{query}'")
        logger.info(f"Using engines: {self.available_engines}")
        
        if self.streamer:
            await self.streamer.emit_search_started('blog', query, self.available_engines)
        
        # Build comprehensive blog queries
        blog_queries = self._build_blog_queries(query)
        
        # Import and run brute search with blog queries
        try:
            from brute.targeted_searches.brute import BruteSearchEngine
            
            # Create output file for results
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"results/blog_{timestamp}.json"
            
            all_results = []
            
            # Run searches for each blog query variant
            for blog_query in blog_queries[:10]:  # Limit to top 10 queries for performance
                logger.info(f"Searching with query: '{blog_query}'")
                
                # Initialize brute search
                searcher = BruteSearchEngine(
                    keyword=blog_query,
                    output_file=output_file,
                    engines=self.available_engines,
                    max_workers=min(len(self.available_engines), 5),
                    event_emitter=self.event_emitter,
                    return_results=True
                )
                
                # Run the search
                searcher.search()
                
                # Get results
                if hasattr(searcher, 'final_results'):
                    results = searcher.final_results
                    # Tag results with blog search metadata
                    for result in results:
                        result['search_type'] = 'blog'
                        result['blog_query'] = query
                        result['query_variant'] = blog_query
                    all_results.extend(results)

            # BrightData Archive - native cat{blog}! support
            if BRIGHTDATA_ARCHIVE_AVAILABLE and search_by_category:
                try:
                    bd_results = await search_by_category(
                        category="blog",
                        limit=max_results // 4,
                    )
                    for r in bd_results:
                        r['source'] = 'brightdata_archive'
                        r['search_type'] = 'blog'
                        r['blog_query'] = query
                    all_results.extend(bd_results)
                    logger.info(f"BrightData Archive added {len(bd_results)} blog results")
                except Exception as e:
                    logger.warning(f"BrightData Archive blog search failed: {e}")

            # Deduplicate results by URL
            seen_urls = set()
            unique_results = []
            for result in all_results:
                url = result.get('url', '')
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_results.append(result)
            
            # Score and sort results
            scored_results = self._score_blog_results(unique_results, query)
            
            if self.streamer:
                await self.streamer.emit_search_completed('blog', len(scored_results))
            
            logger.info(f"Blog search completed with {len(scored_results)} unique results")
            
            return scored_results[:max_results]
            
        except ImportError as e:
            logger.error(f"Failed to import BruteSearchEngine: {e}")
            return []
        except Exception as e:
            logger.error(f"Blog search failed: {e}")
            return []
    
    def _score_blog_results(self, results: List[Dict], query: str) -> List[Dict]:
        """
        Score and sort blog results by relevance.
        
        Prioritizes:
        1. Results from known blog platforms
        2. Results with blog schema markup
        3. Results with blog-related keywords in title/snippet
        """
        query_lower = query.lower()
        
        def score_result(result):
            score = 0
            url = result.get('url', '').lower()
            title = result.get('title', '').lower()
            snippet = result.get('snippet', '').lower()
            
            # Check if from known blog platform (highest priority)
            for platform in ['medium.com', 'wordpress.com', 'blogspot.com', 'dev.to', 
                           'hashnode', 'ghost.io', 'substack.com', 'tumblr.com']:
                if platform in url:
                    score += 50
                    break
            
            # Check for blog schema markup (from query variant)
            if 'query_variant' in result:
                variant = result['query_variant']
                if 'more:pagemap:blogposting' in variant:
                    score += 40
                elif 'more:pagemap:article' in variant:
                    score += 30
            
            # Blog keywords in title (high value)
            blog_keywords = ['blog', 'post', 'article', 'tutorial', 'guide', 'how to']
            for keyword in blog_keywords:
                if keyword in title:
                    score += 20
                    break
            
            # Query appears in title
            if query_lower in title:
                score += 25
            
            # Blog keywords in snippet
            for keyword in blog_keywords:
                if keyword in snippet:
                    score += 10
                    break
            
            # Query appears in snippet
            if query_lower in snippet:
                score += 15
            
            # Date indicators (blogs often have dates)
            import re
            date_pattern = r'\b(20\d{2}|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b'
            if re.search(date_pattern, snippet):
                score += 5
            
            # Author indicators
            if any(word in snippet.lower() for word in ['by ', 'author:', 'written by']):
                score += 5
            
            return score
        
        # Score all results
        for result in results:
            result['blog_score'] = score_result(result)
        
        # Sort by score (highest first)
        results.sort(key=lambda x: x.get('blog_score', 0), reverse=True)
        
        return results
    
    def search_sync(self, query: str, max_results: int = 200) -> List[Dict[str, Any]]:
        """Synchronous wrapper for search method."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.search(query, max_results))
        finally:
            loop.close()

def detect_blog_query(query: str) -> bool:
    """
    Detect if a query should be routed to blog search.
    
    Patterns:
    - blog:query or blog:"query"
    - blogger:query
    - blogpost:query
    """
    query_lower = query.lower()
    
    # Check for blog operators
    blog_patterns = [
        'blog:',
        'blogger:',
        'blogpost:',
        'blogs:',
    ]
    
    for pattern in blog_patterns:
        if pattern in query_lower:
            return True
    
    return False

def extract_blog_query(query: str) -> str:
    """Extract the actual search query from a blog search query."""
    # Remove operators
    query = query.strip()
    
    # Remove common operator prefixes (case-insensitive)
    prefixes = [
        'blog:', 'blogger:', 'blogpost:', 'blogs:',
        'Blog:', 'Blogger:', 'Blogpost:', 'Blogs:'
    ]
    
    for prefix in prefixes:
        if query.startswith(prefix):
            query = query[len(prefix):].strip()
            # Remove quotes if present
            if query.startswith('"') and query.endswith('"'):
                query = query[1:-1]
            elif query.startswith("'") and query.endswith("'"):
                query = query[1:-1]
            return query
    
    # If no prefix found, return the query as-is
    return query.strip()

# Main entry point for blog search
async def run_blog_search(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """
    Main entry point for blog search.
    
    Args:
        query: The full query including blog: operator
        event_emitter: Optional event emitter for streaming updates
        
    Returns:
        List of blog search results
    """
    # Extract the actual query
    clean_query = extract_blog_query(query)
    
    # Create blog searcher
    searcher = BlogSearch(event_emitter)
    
    # Run search
    return await searcher.search(clean_query)

def run_blog_search_sync(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """Synchronous wrapper for blog search."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(run_blog_search(query, event_emitter))
    finally:
        loop.close()


def main():
    """Main entry point for Blog/article search - compatible with SearchRouter"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Blog/article search')
    parser.add_argument('-q', '--query', required=True, help='Search query')
    args = parser.parse_args()
    
    query = args.query
    
    # Extract clean query by removing operator prefix
    if ':' in query:
        clean_query = query.split(':', 1)[1].strip()
    else:
        clean_query = query
    
    print(f"\n🔍 Blog/article search: {clean_query}")
    
    # Try to use existing search function if available
    try:
        if 'run_blog_search_sync' in globals():
            results = globals()['run_blog_search_sync'](clean_query)
        elif 'search' in globals():
            results = search(clean_query)
        else:
            print("Note: This search type needs full implementation")
            results = []
    except Exception as e:
        print(f"Search implementation in progress: {e}")
        results = []
    
    if results:
        print(f"\nFound {len(results)} results:")
        for i, result in enumerate(results[:10], 1):
            print(f"\n{i}. {result.get('title', 'No Title')}")
            print(f"   URL: {result.get('url')}")
            if result.get('snippet'):
                print(f"   {result['snippet'][:200]}...")
    else:
        print("\nNo results found (implementation may be pending).")
    
    return results

# Adapter to match web_api.api.search expectation
def search(query: str, max_results: int = 200):
    searcher = BlogSearch()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(searcher.search(extract_blog_query(query), max_results))
    finally:
        loop.close()

if __name__ == "__main__":
    # Test blog search
    import sys
    
    if len(sys.argv) > 1:
        test_query = ' '.join(sys.argv[1:])
    else:
        test_query = "blog:machine learning"
    
    print(f"Testing blog search with: {test_query}")
    
    if detect_blog_query(test_query):
        print("Blog query detected!")
        clean_query = extract_blog_query(test_query)
        print(f"Extracted query: '{clean_query}'")
        
        results = run_blog_search_sync(test_query)
        
        print(f"\nFound {len(results)} blog results:")
        for i, result in enumerate(results[:10], 1):
            print(f"\n{i}. {result.get('title', 'No title')}")
            print(f"   URL: {result.get('url', 'No URL')}")
            print(f"   Source: {result.get('source', 'Unknown')}")
            print(f"   Blog Score: {result.get('blog_score', 0)}")
            snippet = result.get('snippet', '')
            if snippet:
                print(f"   Snippet: {snippet[:150]}...")
    else:
        print("Not a blog query")