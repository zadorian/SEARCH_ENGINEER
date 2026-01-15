#!/usr/bin/env python3
"""
Event Search Operator - Searches for events, conferences, concerts, festivals
Supports event:, concert:, conference:, festival: operators with schema integration
Leverages event platforms and Schema.org Event structured data
"""

import sys
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime, timedelta
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
    logging.warning("Event streaming not available for event search")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Event search engines
EVENT_ENGINES = [
    'GO',  # Google - with schema search and Google Events
    'BI',  # Bing
    'BR',  # Brave
    'DD',  # DuckDuckGo
    'YA',  # Yandex
]

# Major event platforms
EVENT_PLATFORMS = {
    'eventbrite': 'site:eventbrite.com',
    'meetup': 'site:meetup.com',
    'ticketmaster': 'site:ticketmaster.com',
    'stubhub': 'site:stubhub.com',
    'ticketek': 'site:ticketek.com',
    'axs': 'site:axs.com',
    'bandsintown': 'site:bandsintown.com',
    'songkick': 'site:songkick.com',
    'resident_advisor': 'site:ra.co',
    'dice': 'site:dice.fm',
    'universe': 'site:universe.com',
    'facebook_events': 'site:facebook.com/events',
    'seatgeek': 'site:seatgeek.com',
    'vivid_seats': 'site:vividseats.com',
    'eventful': 'site:eventful.com',
    'goldstar': 'site:goldstar.com',
    'todaytix': 'site:todaytix.com',
    'ticketfly': 'site:ticketfly.com',
}

# Schema.org structured data queries for events
EVENT_SCHEMAS = [
    'more:pagemap:event',
    'more:pagemap:event-name',
    'more:pagemap:event-startdate',
    'more:pagemap:event-enddate',
    'more:pagemap:event-location',
    'more:pagemap:musicevent',
    'more:pagemap:sportsevent',
    'more:pagemap:businessevent',
    'more:pagemap:theaterevent',
    'more:pagemap:festival',
    'more:pagemap:conference',
    'more:pagemap:exhibition',
    'more:pagemap:courseevent',
]

class EventSearch:
    """
    Event search operator implementation.
    Routes searches to event platforms and uses schema-enhanced queries.
    """
    
    def __init__(self, event_emitter=None):
        """Initialize event search with optional event streaming."""
        self.event_emitter = event_emitter
        self.available_engines = self._check_available_engines()
        
        if STREAMING_AVAILABLE and event_emitter:
            self.streamer = SearchTypeEventEmitter(event_emitter)
        else:
            self.streamer = None
    
    def _check_available_engines(self) -> List[str]:
        """Check which event-supporting engines are available in the system."""
        available = []
        
        # Check ENGINE_CONFIG from brute.py
        try:
            from brute.targeted_searches.brute import ENGINE_CONFIG
            
            for engine_code in EVENT_ENGINES:
                if engine_code in ENGINE_CONFIG:
                    available.append(engine_code)
                    logger.info(f"Event engine {engine_code} available")
                else:
                    logger.debug(f"Event engine {engine_code} not configured")
        except ImportError:
            logger.error("Could not import ENGINE_CONFIG from brute.py")
            # Use fallback engines
            available = ['GO', 'BI', 'BR']
        
        if not available:
            logger.warning("No event engines available, using fallback engines")
            available = ['GO', 'BI', 'BR']
        
        logger.info(f"Available event engines: {available}")
        return available
    
    def _extract_date_location_filters(self, query: str) -> Tuple[str, Optional[Dict]]:
        """
        Extract date and location filters from query.
        
        Patterns:
        - date:2024-12-25
        - location:NYC
        - near:London
        - today, tomorrow, this week, this month
        
        Returns:
            Tuple of (cleaned_query, filters)
        """
        filters = {}
        cleaned_query = query
        
        # Date patterns
        date_pattern = r'\bdate\s*:\s*(\d{4}-\d{2}-\d{2})'
        match = re.search(date_pattern, query, re.IGNORECASE)
        if match:
            filters['date'] = match.group(1)
            cleaned_query = re.sub(date_pattern, '', cleaned_query, flags=re.IGNORECASE)
        
        # Relative date patterns
        today = datetime.now()
        if 'today' in query.lower():
            filters['date'] = today.strftime('%Y-%m-%d')
            cleaned_query = re.sub(r'\btoday\b', '', cleaned_query, flags=re.IGNORECASE)
        elif 'tomorrow' in query.lower():
            filters['date'] = (today + timedelta(days=1)).strftime('%Y-%m-%d')
            cleaned_query = re.sub(r'\btomorrow\b', '', cleaned_query, flags=re.IGNORECASE)
        elif 'this week' in query.lower():
            filters['date_range'] = (today.strftime('%Y-%m-%d'), 
                                    (today + timedelta(days=7)).strftime('%Y-%m-%d'))
            cleaned_query = re.sub(r'\bthis week\b', '', cleaned_query, flags=re.IGNORECASE)
        elif 'this month' in query.lower():
            filters['date_range'] = (today.strftime('%Y-%m-%d'), 
                                    (today + timedelta(days=30)).strftime('%Y-%m-%d'))
            cleaned_query = re.sub(r'\bthis month\b', '', cleaned_query, flags=re.IGNORECASE)
        
        # Location patterns
        location_pattern = r'\b(location|near|in)\s*:\s*([^\s]+)'
        match = re.search(location_pattern, query, re.IGNORECASE)
        if match:
            filters['location'] = match.group(2)
            cleaned_query = re.sub(location_pattern, '', cleaned_query, flags=re.IGNORECASE)
        
        # Year pattern
        year_pattern = r'\b(2024|2025|2026)\b'
        match = re.search(year_pattern, query)
        if match and 'date' not in filters:
            filters['year'] = match.group(1)
        
        return cleaned_query.strip(), filters if filters else None
    
    def _build_event_queries(self, query: str, include_platforms: bool = True, 
                            include_schemas: bool = True, filters: Optional[Dict] = None) -> List[str]:
        """
        Build comprehensive event search queries.
        
        Args:
            query: The search query
            include_platforms: Whether to include platform-specific searches
            include_schemas: Whether to include schema-enhanced searches
            filters: Optional date/location filtering
            
        Returns:
            List of search queries optimized for event content
        """
        queries = []
        
        # Base queries
        queries.append(f'event {query}')
        queries.append(f'"{query}" tickets')
        queries.append(f'"{query}" event')
        queries.append(f'"{query}" concert')
        queries.append(f'"{query}" conference')
        queries.append(f'"{query}" festival')
        queries.append(f'"{query}" show')
        
        # Add date/location to base queries if provided
        if filters:
            base = query
            if 'location' in filters:
                base += f' {filters["location"]}'
            if 'date' in filters:
                base += f' {filters["date"]}'
            elif 'year' in filters:
                base += f' {filters["year"]}'
            queries.insert(0, base)
        
        # Platform-specific searches
        if include_platforms:
            # Focus on top platforms for efficiency
            top_platforms = ['eventbrite', 'meetup', 'ticketmaster', 'stubhub',
                           'facebook_events', 'seatgeek', 'bandsintown']
            for platform_name in top_platforms:
                if platform_name in EVENT_PLATFORMS:
                    platform_filter = EVENT_PLATFORMS[platform_name]
                    platform_query = f'{platform_filter} {query}'
                    if filters and 'location' in filters:
                        platform_query += f' {filters["location"]}'
                    queries.append(platform_query)
        
        # Schema-enhanced searches (Google API only)
        if include_schemas and 'GO' in self.available_engines:
            for schema in EVENT_SCHEMAS:
                schema_query = f'{schema} {query}'
                queries.append(schema_query)
            
            # Specific event schema combinations with filters
            if filters:
                if 'date' in filters:
                    queries.append(f'more:pagemap:event-startdate:{filters["date"]} {query}')
                if 'location' in filters:
                    queries.append(f'more:pagemap:event-location:"{filters["location"]}" {query}')
            
            queries.extend([
                f'more:pagemap:event-name:"{query}"',
                f'more:pagemap:musicevent {query}',
                f'more:pagemap:conference {query}',
                f'more:pagemap:festival {query}',
                f'more:pagemap:sportsevent {query}',
            ])
        
        # Event-specific patterns
        queries.extend([
            f'"{query}" registration',
            f'"{query}" schedule',
            f'"{query}" lineup',
            f'"{query}" speakers',
            f'"{query}" venue',
            f'"{query}" dates',
            f'upcoming {query}',
            f'"{query}" 2024',
            f'"{query}" 2025',
        ])
        
        return queries
    
    async def search(self, query: str, max_results: int = 200) -> List[Dict[str, Any]]:
        """
        Execute event search across available engines.
        
        Args:
            query: The search query (without the event: operator)
            max_results: Maximum results to return
            
        Returns:
            List of search results from event sources
        """
        # Extract date/location filters and clean query
        cleaned_query, filters = self._extract_date_location_filters(query)
        
        logger.info(f"Starting event search for: '{cleaned_query}'")
        if filters:
            logger.info(f"Filters: {filters}")
        logger.info(f"Using engines: {self.available_engines}")
        
        if self.streamer:
            await self.streamer.emit_search_started('event', cleaned_query, self.available_engines)
        
        # Build comprehensive event queries
        event_queries = self._build_event_queries(cleaned_query, filters=filters)
        
        # Import and run brute search with event queries
        try:
            from brute.targeted_searches.brute import BruteSearchEngine
            
            # Create output file for results
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"results/event_{timestamp}.json"
            
            all_results = []
            
            # Run searches for each event query variant
            for event_query in event_queries[:12]:  # Top 12 queries
                logger.info(f"Searching with query: '{event_query}'")
                
                # Initialize brute search
                searcher = BruteSearchEngine(
                    keyword=event_query,
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
                    # Tag results with event search metadata
                    for result in results:
                        result['search_type'] = 'event'
                        result['event_query'] = cleaned_query
                        result['query_variant'] = event_query
                        if filters:
                            result['filters'] = filters
                    all_results.extend(results)
            
            # Deduplicate results by URL
            seen_urls = set()
            unique_results = []
            for result in all_results:
                url = result.get('url', '')
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_results.append(result)
            
            # Score and sort results
            scored_results = self._score_event_results(unique_results, cleaned_query, filters)
            
            if self.streamer:
                await self.streamer.emit_search_completed('event', len(scored_results))
            
            logger.info(f"Event search completed with {len(scored_results)} unique results")
            
            return scored_results[:max_results]
            
        except ImportError as e:
            logger.error(f"Failed to import BruteSearchEngine: {e}")
            return []
        except Exception as e:
            logger.error(f"Event search failed: {e}")
            return []
    
    def _score_event_results(self, results: List[Dict], query: str,
                             filters: Optional[Dict] = None) -> List[Dict]:
        """
        Score and sort event results by relevance.
        
        Prioritizes:
        1. Results from known event platforms
        2. Results with event schema markup
        3. Results with date/location information
        4. Results with ticket/registration keywords
        """
        query_lower = query.lower()
        
        def score_result(result):
            score = 0
            url = result.get('url', '').lower()
            title = result.get('title', '').lower()
            snippet = result.get('snippet', '').lower()
            
            # Check if from known event platform (highest priority)
            major_platforms = ['eventbrite.com', 'meetup.com', 'ticketmaster.com',
                             'stubhub.com', 'facebook.com/events', 'seatgeek.com',
                             'axs.com', 'bandsintown.com', 'dice.fm']
            for platform in major_platforms:
                if platform in url:
                    score += 60
                    break
            
            # Check for event schema markup (from query variant)
            if 'query_variant' in result:
                variant = result['query_variant']
                if 'more:pagemap:event' in variant:
                    score += 50
                elif 'more:pagemap:musicevent' in variant or 'more:pagemap:conference' in variant:
                    score += 45
            
            # Date information (crucial for events)
            date_pattern = r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b|\b\d{4}\b|\b\d{1,2}/\d{1,2}\b'
            if re.search(date_pattern, snippet, re.IGNORECASE):
                score += 35
            
            # Event keywords in title
            event_keywords = ['event', 'concert', 'conference', 'festival', 'show',
                            'tickets', 'registration', 'tour', 'performance', 'exhibition']
            for keyword in event_keywords:
                if keyword in title:
                    score += 25
                    break
            
            # Query appears in title
            if query_lower in title:
                score += 30
            
            # Location information
            if filters and 'location' in filters:
                if filters['location'].lower() in snippet.lower():
                    score += 20
            
            # Ticket/registration keywords
            ticket_keywords = ['tickets', 'register', 'registration', 'buy tickets',
                             'get tickets', 'rsvp', 'book now', 'reserve']
            for keyword in ticket_keywords:
                if keyword in snippet.lower():
                    score += 15
                    break
            
            # Query appears in snippet
            if query_lower in snippet:
                score += 15
            
            # Venue/location indicators
            venue_pattern = r'\b(venue|theater|theatre|arena|stadium|hall|center|centre)\b'
            if re.search(venue_pattern, snippet, re.IGNORECASE):
                score += 10
            
            # Time indicators
            time_pattern = r'\b\d{1,2}:\d{2}\s*(am|pm|AM|PM)?\b|\b(doors|starts?|begins?)\s+at\b'
            if re.search(time_pattern, snippet, re.IGNORECASE):
                score += 8
            
            # Price indicators (events often mention ticket prices)
            if '$' in snippet or 'free' in snippet.lower():
                score += 7
            
            return score
        
        # Score all results
        for result in results:
            result['event_score'] = score_result(result)
        
        # Sort by score (highest first)
        results.sort(key=lambda x: x.get('event_score', 0), reverse=True)
        
        return results
    
    def search_sync(self, query: str, max_results: int = 200) -> List[Dict[str, Any]]:
        """Synchronous wrapper for search method."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.search(query, max_results))
        finally:
            loop.close()

# Adapter to match web_api.api.search expectations
def search(query: str, max_results: int = 200):
    searcher = EventSearch()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(searcher.search(query, max_results))
    finally:
        loop.close()

def detect_event_query(query: str) -> bool:
    """
    Detect if a query should be routed to event search.
    
    Patterns:
    - event:query or event:"query"
    - concert:query
    - conference:query
    - festival:query
    - show:query
    """
    query_lower = query.lower()
    
    # Check for event operators
    event_patterns = [
        'event:',
        'concert:',
        'conference:',
        'festival:',
        'show:',
        'events:',
        'gig:',
        'performance:',
        'exhibition:',
        'meetup:',
    ]
    
    for pattern in event_patterns:
        if pattern in query_lower:
            return True
    
    return False

def extract_event_query(query: str) -> str:
    """Extract the actual search query from an event search query."""
    # Remove operators
    query = query.strip()
    
    # Remove common operator prefixes (case-insensitive)
    prefixes = [
        'event:', 'concert:', 'conference:', 'festival:', 'show:',
        'events:', 'gig:', 'performance:', 'exhibition:', 'meetup:',
        'Event:', 'Concert:', 'Conference:', 'Festival:', 'Show:',
        'Events:', 'Gig:', 'Performance:', 'Exhibition:', 'Meetup:'
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

# Main entry point for event search
async def run_event_search(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """
    Main entry point for event search.
    
    Args:
        query: The full query including event: operator
        event_emitter: Optional event emitter for streaming updates
        
    Returns:
        List of event search results
    """
    # Extract the actual query
    clean_query = extract_event_query(query)
    
    # Create event searcher
    searcher = EventSearch(event_emitter)
    
    # Run search
    return await searcher.search(clean_query)

def run_event_search_sync(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """Synchronous wrapper for event search."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(run_event_search(query, event_emitter))
    finally:
        loop.close()


def main():
    """Main entry point for Event/conference search - compatible with SearchRouter"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Event/conference search')
    parser.add_argument('-q', '--query', required=True, help='Search query')
    args = parser.parse_args()
    
    query = args.query
    
    # Extract clean query by removing operator prefix
    if ':' in query:
        clean_query = query.split(':', 1)[1].strip()
    else:
        clean_query = query
    
    print(f"\n🔍 Event/conference search: {clean_query}")
    
    # Try to use existing search function if available
    try:
        if 'run_event_search_sync' in globals():
            results = globals()['run_event_search_sync'](clean_query)
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
    # Test event search
    import sys
    
    if len(sys.argv) > 1:
        test_query = ' '.join(sys.argv[1:])
    else:
        test_query = "concert:Taylor Swift location:NYC"
    
    print(f"Testing event search with: {test_query}")
    
    if detect_event_query(test_query):
        print("Event query detected!")
        clean_query = extract_event_query(test_query)
        print(f"Extracted query: '{clean_query}'")
        
        results = run_event_search_sync(test_query)
        
        print(f"\nFound {len(results)} event results:")
        for i, result in enumerate(results[:10], 1):
            print(f"\n{i}. {result.get('title', 'No title')}")
            print(f"   URL: {result.get('url', 'No URL')}")
            print(f"   Source: {result.get('source', 'Unknown')}")
            print(f"   Event Score: {result.get('event_score', 0)}")
            if 'filters' in result:
                print(f"   Filters: {result['filters']}")
            snippet = result.get('snippet', '')
            if snippet:
                print(f"   Snippet: {snippet[:150]}...")
    else:
        print("Not an event query")