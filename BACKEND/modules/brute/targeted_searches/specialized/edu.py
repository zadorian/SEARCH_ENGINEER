#!/usr/bin/env python3
"""
Educational Search Operator - Searches for courses, tutorials, educational content
Supports edu:, course:, education: operators with schema integration
Leverages educational platforms and Schema.org Course/EducationalOrganization structured data
"""

import sys
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime
import time
import re

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import event streaming for filtering events
try:
    from brute.infrastructure.base_streamer import SearchTypeEventEmitter
    STREAMING_AVAILABLE = True
except ImportError:
    STREAMING_AVAILABLE = False
    logging.warning("Event streaming not available for educational search")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Educational search engines
EDU_ENGINES = [
    'GO',  # Google - with schema search
    'BI',  # Bing
    'BR',  # Brave
    'DD',  # DuckDuckGo
    'YA',  # Yandex
]

# Major educational platforms
EDU_PLATFORMS = {
    'coursera': 'site:coursera.org',
    'edx': 'site:edx.org',
    'udemy': 'site:udemy.com',
    'khan_academy': 'site:khanacademy.org',
    'mit_ocw': 'site:ocw.mit.edu',
    'stanford_online': 'site:online.stanford.edu',
    'harvard_online': 'site:online-learning.harvard.edu',
    'udacity': 'site:udacity.com',
    'pluralsight': 'site:pluralsight.com',
    'linkedin_learning': 'site:linkedin.com/learning',
    'skillshare': 'site:skillshare.com',
    'masterclass': 'site:masterclass.com',
    'futurelearn': 'site:futurelearn.com',
    'codecademy': 'site:codecademy.com',
    'treehouse': 'site:teamtreehouse.com',
    'datacamp': 'site:datacamp.com',
    'brilliant': 'site:brilliant.org',
    'edu_domains': 'site:*.edu',
}

# Schema.org structured data queries for education
EDU_SCHEMAS = [
    'more:pagemap:course',
    'more:pagemap:course-name',
    'more:pagemap:course-provider',
    'more:pagemap:educationalorganization',
    'more:pagemap:learningresource',
    'more:pagemap:educationaloccupationalprogram',
    'more:pagemap:courseevent',
    'more:pagemap:educationalevent',
    'more:pagemap:syllabus',
]

class EduSearch:
    """
    Educational search operator implementation.
    Routes searches to educational platforms and uses schema-enhanced queries.
    """
    
    def __init__(self, event_emitter=None):
        """Initialize educational search with optional event streaming."""
        self.event_emitter = event_emitter
        self.available_engines = self._check_available_engines()
        
        if STREAMING_AVAILABLE and event_emitter:
            self.streamer = SearchTypeEventEmitter(event_emitter)
        else:
            self.streamer = None
    
    def _check_available_engines(self) -> List[str]:
        """Check which edu-supporting engines are available in the system."""
        available = []
        
        try:
            from brute.targeted_searches.brute import ENGINE_CONFIG
            
            for engine_code in EDU_ENGINES:
                if engine_code in ENGINE_CONFIG:
                    available.append(engine_code)
                    logger.info(f"Educational engine {engine_code} available")
        except ImportError:
            logger.error("Could not import ENGINE_CONFIG from brute.py")
            available = ['GO', 'BI', 'BR']
        
        if not available:
            available = ['GO', 'BI', 'BR']
        
        logger.info(f"Available educational engines: {available}")
        return available
    
    def _extract_level_filters(self, query: str) -> Tuple[str, Optional[Dict]]:
        """
        Extract level and type filters from query.
        
        Patterns:
        - level:beginner, level:intermediate, level:advanced
        - free courses
        - certification
        """
        filters = {}
        cleaned_query = query
        
        # Level pattern
        level_pattern = r'\blevel\s*:\s*(beginner|intermediate|advanced)'
        match = re.search(level_pattern, query, re.IGNORECASE)
        if match:
            filters['level'] = match.group(1).lower()
            cleaned_query = re.sub(level_pattern, '', cleaned_query, flags=re.IGNORECASE)
        
        # Free courses
        if 'free' in query.lower():
            filters['free'] = True
            cleaned_query = re.sub(r'\bfree\b', '', cleaned_query, flags=re.IGNORECASE)
        
        # Certification
        if any(word in query.lower() for word in ['certification', 'certificate', 'certified']):
            filters['certification'] = True
        
        return cleaned_query.strip(), filters if filters else None
    
    def _build_edu_queries(self, query: str, include_platforms: bool = True, 
                          include_schemas: bool = True, filters: Optional[Dict] = None) -> List[str]:
        """Build comprehensive educational search queries."""
        queries = []
        
        # Base queries
        queries.append(f'course {query}')
        queries.append(f'"{query}" tutorial')
        queries.append(f'"{query}" course')
        queries.append(f'learn {query}')
        queries.append(f'"{query}" education')
        queries.append(f'"{query}" training')
        
        # Add level-specific queries
        if filters:
            if 'level' in filters:
                queries.append(f'{filters["level"]} {query} course')
            if 'free' in filters:
                queries.append(f'free {query} course')
            if 'certification' in filters:
                queries.append(f'{query} certification')
        
        # Platform-specific searches
        if include_platforms:
            top_platforms = ['coursera', 'edx', 'udemy', 'khan_academy', 
                           'mit_ocw', 'codecademy', 'edu_domains']
            for platform_name in top_platforms:
                if platform_name in EDU_PLATFORMS:
                    platform_filter = EDU_PLATFORMS[platform_name]
                    queries.append(f'{platform_filter} {query}')
        
        # Schema-enhanced searches (Google API only)
        if include_schemas and 'GO' in self.available_engines:
            for schema in EDU_SCHEMAS:
                queries.append(f'{schema} {query}')
            
            queries.extend([
                f'more:pagemap:course-name:"{query}"',
                f'more:pagemap:course {query}',
                f'more:pagemap:learningresource {query}',
            ])
        
        # Educational patterns
        queries.extend([
            f'"{query}" syllabus',
            f'"{query}" curriculum',
            f'"{query}" lesson',
            f'"{query}" homework',
            f'"{query}" lecture',
            f'"{query}" MOOC',
            f'online {query} class',
        ])
        
        return queries
    
    async def search(self, query: str, max_results: int = 200) -> List[Dict[str, Any]]:
        """Execute educational search across available engines."""
        # Extract level filters and clean query
        cleaned_query, filters = self._extract_level_filters(query)
        
        logger.info(f"Starting educational search for: '{cleaned_query}'")
        if filters:
            logger.info(f"Filters: {filters}")
        
        if self.streamer:
            await self.streamer.emit_search_started('edu', cleaned_query, self.available_engines)
        
        # Build comprehensive edu queries
        edu_queries = self._build_edu_queries(cleaned_query, filters=filters)
        
        try:
            from brute.targeted_searches.brute import BruteSearchEngine
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"results/edu_{timestamp}.json"
            
            all_results = []
            
            for edu_query in edu_queries[:12]:
                logger.info(f"Searching with query: '{edu_query}'")
                
                searcher = BruteSearchEngine(
                    keyword=edu_query,
                    output_file=output_file,
                    engines=self.available_engines,
                    max_workers=min(len(self.available_engines), 5),
                    event_emitter=self.event_emitter,
                    return_results=True
                )
                
                searcher.search()
                
                if hasattr(searcher, 'final_results'):
                    results = searcher.final_results
                    for result in results:
                        result['search_type'] = 'edu'
                        result['edu_query'] = cleaned_query
                        result['query_variant'] = edu_query
                        if filters:
                            result['filters'] = filters
                    all_results.extend(results)
            
            # Deduplicate results
            seen_urls = set()
            unique_results = []
            for result in all_results:
                url = result.get('url', '')
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_results.append(result)
            
            # Score and sort results
            scored_results = self._score_edu_results(unique_results, cleaned_query, filters)
            
            if self.streamer:
                await self.streamer.emit_search_completed('edu', len(scored_results))
            
            return scored_results[:max_results]
            
        except Exception as e:
            logger.error(f"Educational search failed: {e}")
            return []
    
    def _score_edu_results(self, results: List[Dict], query: str,
                          filters: Optional[Dict] = None) -> List[Dict]:
        """Score and sort educational results by relevance."""
        query_lower = query.lower()
        
        def score_result(result):
            score = 0
            url = result.get('url', '').lower()
            title = result.get('title', '').lower()
            snippet = result.get('snippet', '').lower()
            
            # Check if from known educational platform
            major_platforms = ['coursera.org', 'edx.org', 'udemy.com', 'khanacademy.org',
                             'mit.edu', 'stanford.edu', 'harvard.edu', 'codecademy.com']
            for platform in major_platforms:
                if platform in url:
                    score += 60
                    break
            
            # .edu domain bonus
            if '.edu' in url:
                score += 30
            
            # Check for course schema markup
            if 'query_variant' in result:
                variant = result['query_variant']
                if 'more:pagemap:course' in variant:
                    score += 50
            
            # Educational keywords in title
            edu_keywords = ['course', 'tutorial', 'lesson', 'learn', 'education',
                          'training', 'class', 'lecture', 'curriculum', 'syllabus']
            for keyword in edu_keywords:
                if keyword in title:
                    score += 25
                    break
            
            # Query appears in title
            if query_lower in title:
                score += 30
            
            # Level indicators
            if any(word in snippet.lower() for word in ['beginner', 'introduction', 'basics']):
                score += 8
            
            # Free indicator
            if 'free' in snippet.lower():
                score += 10
            
            # Certificate/certification
            if any(word in snippet.lower() for word in ['certificate', 'certification', 'certified']):
                score += 12
            
            # Duration/length indicators
            duration_pattern = r'\b\d+\s*(hours?|weeks?|months?|lessons?|modules?)\b'
            if re.search(duration_pattern, snippet, re.IGNORECASE):
                score += 7
            
            return score
        
        # Score all results
        for result in results:
            result['edu_score'] = score_result(result)
        
        # Sort by score
        results.sort(key=lambda x: x.get('edu_score', 0), reverse=True)
        
        return results
    
    def search_sync(self, query: str, max_results: int = 200) -> List[Dict[str, Any]]:
        """Synchronous wrapper for search method."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.search(query, max_results))
        finally:
            loop.close()

def detect_edu_query(query: str) -> bool:
    """Detect if a query should be routed to educational search."""
    query_lower = query.lower()
    
    edu_patterns = [
        'edu:',
        'course:',
        'education:',
        'tutorial:',
        'learn:',
        'training:',
        'class:',
    ]
    
    for pattern in edu_patterns:
        if pattern in query_lower:
            return True
    
    return False

def extract_edu_query(query: str) -> str:
    """Extract the actual search query from an educational search query."""
    query = query.strip()
    
    prefixes = [
        'edu:', 'course:', 'education:', 'tutorial:', 'learn:', 'training:', 'class:',
        'Edu:', 'Course:', 'Education:', 'Tutorial:', 'Learn:', 'Training:', 'Class:'
    ]
    
    for prefix in prefixes:
        if query.startswith(prefix):
            query = query[len(prefix):].strip()
            if query.startswith('"') and query.endswith('"'):
                query = query[1:-1]
            elif query.startswith("'") and query.endswith("'"):
                query = query[1:-1]
            return query
    
    return query.strip()

# Main entry point
async def run_edu_search(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """Main entry point for educational search."""
    clean_query = extract_edu_query(query)
    searcher = EduSearch(event_emitter)
    return await searcher.search(clean_query)

def run_edu_search_sync(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """Synchronous wrapper for educational search."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(run_edu_search(query, event_emitter))
    finally:
        loop.close()


def search(query: str) -> List[Dict[str, Any]]:
    """Synchronous search function for web API compatibility"""
    try:
        # Check if there's already a running event loop
        loop = asyncio.get_running_loop()
        # We're already in an async context, use ThreadPoolExecutor
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, run_edu_search(query))
            return future.result()
    except RuntimeError:
        # No event loop running, create one
        return asyncio.run(run_edu_search(query))

def main():
    """Main entry point for Educational content search - compatible with SearchRouter"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Educational content search')
    parser.add_argument('-q', '--query', required=True, help='Search query')
    args = parser.parse_args()
    
    query = args.query
    
    # Extract clean query by removing operator prefix
    if ':' in query:
        clean_query = query.split(':', 1)[1].strip()
    else:
        clean_query = query
    
    print(f"\n🔍 Educational content search: {clean_query}")
    
    # Try to use existing search function if available
    try:
        if 'run_edu_search_sync' in globals():
            results = globals()['run_edu_search_sync'](clean_query)
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

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        test_query = ' '.join(sys.argv[1:])
    else:
        test_query = "course:python programming free"
    
    print(f"Testing educational search with: {test_query}")
    
    if detect_edu_query(test_query):
        print("Educational query detected!")
        clean_query = extract_edu_query(test_query)
        print(f"Extracted query: '{clean_query}'")
        
        results = run_edu_search_sync(test_query)
        
        print(f"\nFound {len(results)} educational results:")
        for i, result in enumerate(results[:10], 1):
            print(f"\n{i}. {result.get('title', 'No title')}")
            print(f"   URL: {result.get('url', 'No URL')}")
            print(f"   Score: {result.get('edu_score', 0)}")
    else:
        print("Not an educational query")