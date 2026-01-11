#!/usr/bin/env python3
"""
Review Search Operator - Searches for reviews, ratings, and feedback
Supports review:, rating:, feedback: operators with schema integration
Leverages review platforms and Schema.org Review/AggregateRating structured data
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
    logging.warning("Event streaming not available for review search")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Review search engines
REVIEW_ENGINES = [
    'GO',  # Google - with schema search
    'BI',  # Bing
    'BR',  # Brave
    'DD',  # DuckDuckGo
    'YA',  # Yandex
]

# Major review platforms
REVIEW_PLATFORMS = {
    # Product reviews
    'amazon': 'site:amazon.com reviews',
    'bestbuy': 'site:bestbuy.com reviews',
    'walmart': 'site:walmart.com reviews',
    
    # Business/Service reviews
    'yelp': 'site:yelp.com',
    'google_reviews': 'site:google.com/maps reviews',
    'tripadvisor': 'site:tripadvisor.com',
    'trustpilot': 'site:trustpilot.com',
    'bbb': 'site:bbb.org',
    'glassdoor': 'site:glassdoor.com reviews',
    'indeed': 'site:indeed.com/cmp reviews',
    
    # App reviews
    'app_store': 'site:apps.apple.com reviews',
    'play_store': 'site:play.google.com reviews',
    'microsoft_store': 'site:microsoft.com/store reviews',
    
    # Entertainment reviews
    'imdb': 'site:imdb.com reviews',
    'rotten_tomatoes': 'site:rottentomatoes.com',
    'metacritic': 'site:metacritic.com',
    'goodreads': 'site:goodreads.com',
    'letterboxd': 'site:letterboxd.com',
    
    # Tech reviews
    'cnet': 'site:cnet.com reviews',
    'techradar': 'site:techradar.com reviews',
    'pcmag': 'site:pcmag.com reviews',
    'wirecutter': 'site:nytimes.com/wirecutter',
    'rtings': 'site:rtings.com',
    
    # Car reviews
    'edmunds': 'site:edmunds.com reviews',
    'cars_com': 'site:cars.com reviews',
    'kbb': 'site:kbb.com reviews',
    
    # Restaurant reviews
    'opentable': 'site:opentable.com reviews',
    'zomato': 'site:zomato.com',
    'foursquare': 'site:foursquare.com',
}

# Schema.org structured data queries for reviews
REVIEW_SCHEMAS = [
    'more:pagemap:review',
    'more:pagemap:review-reviewbody',
    'more:pagemap:review-reviewrating',
    'more:pagemap:review-author',
    'more:pagemap:review-datepublished',
    'more:pagemap:aggregaterating',
    'more:pagemap:aggregaterating-ratingvalue',
    'more:pagemap:aggregaterating-reviewcount',
    'more:pagemap:rating',
    'more:pagemap:product-review',
    'more:pagemap:localbusiness-review',
    'more:pagemap:movie-review',
    'more:pagemap:book-review',
    'more:pagemap:restaurant-review',
]

class ReviewSearch:
    """
    Review search operator implementation.
    Routes searches to review platforms and uses schema-enhanced queries.
    """
    
    def __init__(self, event_emitter=None):
        """Initialize review search with optional event streaming."""
        self.event_emitter = event_emitter
        self.available_engines = self._check_available_engines()
        
        if STREAMING_AVAILABLE and event_emitter:
            self.streamer = SearchTypeEventEmitter(event_emitter)
        else:
            self.streamer = None
    
    def _check_available_engines(self) -> List[str]:
        """Check which review-supporting engines are available in the system."""
        available = []
        
        try:
            from brute.targeted_searches.brute import ENGINE_CONFIG
            
            for engine_code in REVIEW_ENGINES:
                if engine_code in ENGINE_CONFIG:
                    available.append(engine_code)
                    logger.info(f"Review engine {engine_code} available")
        except ImportError:
            logger.error("Could not import ENGINE_CONFIG from brute.py")
            available = ['GO', 'BI', 'BR']
        
        if not available:
            available = ['GO', 'BI', 'BR']
        
        logger.info(f"Available review engines: {available}")
        return available
    
    def _extract_rating_filters(self, query: str) -> Tuple[str, Optional[Dict]]:
        """
        Extract rating and review filters from query.
        
        Patterns:
        - rating>4
        - rating:4-5
        - stars>3
        - verified (for verified reviews)
        - recent (for recent reviews)
        
        Returns:
            Tuple of (cleaned_query, filters)
        """
        filters = {}
        cleaned_query = query
        
        # Rating pattern (rating>4, rating<3, etc.)
        rating_pattern = r'\b(rating|stars)\s*([<>])\s*(\d+(?:\.\d+)?)'
        match = re.search(rating_pattern, query, re.IGNORECASE)
        if match:
            operator = match.group(2)
            value = float(match.group(3))
            if operator == '>':
                filters['min_rating'] = value
            else:
                filters['max_rating'] = value
            cleaned_query = re.sub(rating_pattern, '', cleaned_query, flags=re.IGNORECASE)
        
        # Rating range pattern (rating:3-5)
        range_pattern = r'\b(rating|stars)\s*:\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)'
        match = re.search(range_pattern, query, re.IGNORECASE)
        if match:
            filters['min_rating'] = float(match.group(2))
            filters['max_rating'] = float(match.group(3))
            cleaned_query = re.sub(range_pattern, '', cleaned_query, flags=re.IGNORECASE)
        
        # Star patterns (5 stars, 4 star, etc.)
        star_pattern = r'\b(\d+)\s*stars?\b'
        match = re.search(star_pattern, query, re.IGNORECASE)
        if match and 'min_rating' not in filters:
            filters['exact_rating'] = int(match.group(1))
            cleaned_query = re.sub(star_pattern, '', cleaned_query, flags=re.IGNORECASE)
        
        # Verified reviews
        if 'verified' in query.lower():
            filters['verified'] = True
            cleaned_query = re.sub(r'\bverified\b', '', cleaned_query, flags=re.IGNORECASE)
        
        # Recent reviews
        if 'recent' in query.lower() or 'latest' in query.lower():
            filters['recent'] = True
            cleaned_query = re.sub(r'\b(recent|latest)\b', '', cleaned_query, flags=re.IGNORECASE)
        
        # Review count
        count_pattern = r'\b(\d+)\+?\s*reviews?\b'
        match = re.search(count_pattern, query, re.IGNORECASE)
        if match:
            filters['min_reviews'] = int(match.group(1))
            cleaned_query = re.sub(count_pattern, '', cleaned_query, flags=re.IGNORECASE)
        
        return cleaned_query.strip(), filters if filters else None
    
    def _build_review_queries(self, query: str, include_platforms: bool = True, 
                             include_schemas: bool = True, filters: Optional[Dict] = None) -> List[str]:
        """Build comprehensive review search queries."""
        queries = []
        
        # Base queries
        queries.append(f'"{query}" reviews')
        queries.append(f'"{query}" review')
        queries.append(f'"{query}" rating')
        queries.append(f'"{query}" ratings')
        queries.append(f'"{query}" feedback')
        queries.append(f'"{query}" testimonials')
        queries.append(f'"{query}" user reviews')
        queries.append(f'"{query}" customer reviews')
        
        # Add rating-specific queries
        if filters:
            if 'exact_rating' in filters:
                queries.append(f'"{query}" {filters["exact_rating"]} stars')
                queries.append(f'"{query}" {filters["exact_rating"]} star review')
            if 'min_rating' in filters:
                queries.append(f'"{query}" {filters["min_rating"]}+ stars')
            if 'verified' in filters:
                queries.append(f'"{query}" verified reviews')
                queries.append(f'"{query}" verified purchase')
            if 'recent' in filters:
                queries.append(f'"{query}" recent reviews')
                queries.append(f'"{query}" latest reviews')
        
        # Platform-specific searches
        if include_platforms:
            # Determine relevant platforms based on query context
            query_lower = query.lower()
            
            # Select platforms based on context
            if any(word in query_lower for word in ['product', 'buy', 'purchase', 'laptop', 'phone', 'device']):
                platforms = ['amazon', 'bestbuy', 'walmart', 'cnet', 'techradar']
            elif any(word in query_lower for word in ['restaurant', 'food', 'dining', 'cafe']):
                platforms = ['yelp', 'tripadvisor', 'opentable', 'zomato', 'google_reviews']
            elif any(word in query_lower for word in ['hotel', 'travel', 'vacation']):
                platforms = ['tripadvisor', 'booking', 'expedia', 'google_reviews']
            elif any(word in query_lower for word in ['movie', 'film', 'show', 'series']):
                platforms = ['imdb', 'rotten_tomatoes', 'metacritic', 'letterboxd']
            elif any(word in query_lower for word in ['book', 'novel', 'author']):
                platforms = ['goodreads', 'amazon']
            elif any(word in query_lower for word in ['app', 'software', 'game']):
                platforms = ['app_store', 'play_store', 'microsoft_store']
            elif any(word in query_lower for word in ['company', 'business', 'service']):
                platforms = ['trustpilot', 'glassdoor', 'indeed', 'bbb', 'yelp']
            elif any(word in query_lower for word in ['car', 'vehicle', 'auto']):
                platforms = ['edmunds', 'cars_com', 'kbb']
            else:
                # Default to general review platforms
                platforms = ['yelp', 'google_reviews', 'tripadvisor', 'trustpilot', 'amazon']
            
            for platform_name in platforms:
                if platform_name in REVIEW_PLATFORMS:
                    platform_filter = REVIEW_PLATFORMS[platform_name]
                    queries.append(f'{platform_filter} {query}')
        
        # Schema-enhanced searches (Google API only)
        if include_schemas and 'GO' in self.available_engines:
            for schema in REVIEW_SCHEMAS:
                queries.append(f'{schema} {query}')
            
            # Specific review schema combinations
            queries.extend([
                f'more:pagemap:review "{query}"',
                f'more:pagemap:aggregaterating "{query}"',
                f'more:pagemap:review-reviewbody "{query}"',
            ])
            
            if filters:
                if 'min_rating' in filters:
                    queries.append(f'more:pagemap:review-reviewrating:>{filters["min_rating"]} {query}')
                if 'exact_rating' in filters:
                    queries.append(f'more:pagemap:review-reviewrating:{filters["exact_rating"]} {query}')
        
        # Review-specific patterns
        queries.extend([
            f'"{query}" pros and cons',
            f'"{query}" worth it',
            f'"{query}" recommended',
            f'"{query}" comparison',
            f'"{query}" vs',
            f'"{query}" experience',
            f'"{query}" opinion',
            f'best {query}',
            f'worst {query}',
        ])
        
        return queries
    
    async def search(self, query: str, max_results: int = 200) -> List[Dict[str, Any]]:
        """Execute review search across available engines."""
        # Extract rating filters and clean query
        cleaned_query, filters = self._extract_rating_filters(query)
        
        logger.info(f"Starting review search for: '{cleaned_query}'")
        if filters:
            logger.info(f"Filters: {filters}")
        
        if self.streamer:
            await self.streamer.emit_search_started('review', cleaned_query, self.available_engines)
        
        # Build comprehensive review queries
        review_queries = self._build_review_queries(cleaned_query, filters=filters)
        
        try:
            from brute.targeted_searches.brute import BruteSearchEngine
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"results/review_{timestamp}.json"
            
            all_results = []
            
            for review_query in review_queries[:12]:
                logger.info(f"Searching with query: '{review_query}'")
                
                searcher = BruteSearchEngine(
                    keyword=review_query,
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
                        result['search_type'] = 'review'
                        result['review_query'] = cleaned_query
                        result['query_variant'] = review_query
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
            scored_results = self._score_review_results(unique_results, cleaned_query, filters)
            
            if self.streamer:
                await self.streamer.emit_search_completed('review', len(scored_results))
            
            return scored_results[:max_results]
            
        except Exception as e:
            logger.error(f"Review search failed: {e}")
            return []
    
    def _score_review_results(self, results: List[Dict], query: str,
                             filters: Optional[Dict] = None) -> List[Dict]:
        """Score and sort review results by relevance."""
        query_lower = query.lower()
        
        def score_result(result):
            score = 0
            url = result.get('url', '').lower()
            title = result.get('title', '').lower()
            snippet = result.get('snippet', '').lower()
            
            # Check if from known review platform (highest priority)
            major_platforms = ['yelp.com', 'tripadvisor.com', 'trustpilot.com',
                             'amazon.com/product-reviews', 'google.com/maps',
                             'imdb.com', 'rottentomatoes.com', 'metacritic.com',
                             'goodreads.com', 'glassdoor.com', 'cnet.com']
            for platform in major_platforms:
                if platform in url:
                    score += 60
                    break
            
            # Check for review schema markup
            if 'query_variant' in result:
                variant = result['query_variant']
                if 'more:pagemap:review' in variant:
                    score += 50
                elif 'more:pagemap:aggregaterating' in variant:
                    score += 45
            
            # Review keywords in title
            review_keywords = ['review', 'reviews', 'rating', 'ratings', 'feedback',
                             'testimonial', 'opinion', 'experience', 'evaluation']
            for keyword in review_keywords:
                if keyword in title:
                    score += 25
                    break
            
            # Query appears in title
            if query_lower in title:
                score += 30
            
            # Star rating indicators
            star_pattern = r'[★☆⭐]|(\d+(?:\.\d+)?)\s*(stars?|rating)|(\d+(?:\.\d+)?)/5'
            if re.search(star_pattern, snippet):
                score += 20
            
            # Review count indicators
            count_pattern = r'\b\d+\s*(reviews?|ratings?|opinions?|testimonials?)\b'
            if re.search(count_pattern, snippet, re.IGNORECASE):
                score += 15
            
            # Verified review indicators
            if any(word in snippet.lower() for word in ['verified', 'verified purchase', 
                                                         'verified buyer', 'confirmed']):
                score += 12
            
            # Pros/cons indicators
            if any(word in snippet.lower() for word in ['pros', 'cons', 'advantages', 
                                                         'disadvantages', 'benefits']):
                score += 10
            
            # Date indicators (recent reviews are valuable)
            date_pattern = r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b.*\b20\d{2}\b'
            if re.search(date_pattern, snippet):
                score += 8
            
            # Recommendation language
            if any(phrase in snippet.lower() for phrase in ['recommend', 'worth it', 
                                                            'would buy again', 'satisfied']):
                score += 10
            
            # Filter matching
            if filters:
                if 'verified' in filters and 'verified' in snippet.lower():
                    score += 15
                if 'recent' in filters and any(word in snippet.lower() for word in ['recent', 'latest', 'new']):
                    score += 10
            
            return score
        
        # Score all results
        for result in results:
            result['review_score'] = score_result(result)
        
        # Sort by score
        results.sort(key=lambda x: x.get('review_score', 0), reverse=True)
        
        return results
    
    def search_sync(self, query: str, max_results: int = 200) -> List[Dict[str, Any]]:
        """Synchronous wrapper for search method."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.search(query, max_results))
        finally:
            loop.close()

# Adapter to match web_api.api.search expectation
def search(query: str, max_results: int = 200):
    searcher = ReviewSearch()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(searcher.search(query, max_results))
    finally:
        loop.close()

def detect_review_query(query: str) -> bool:
    """Detect if a query should be routed to review search."""
    query_lower = query.lower()
    
    review_patterns = [
        'review:',
        'reviews:',
        'rating:',
        'ratings:',
        'feedback:',
        'testimonial:',
        'opinion:',
    ]
    
    for pattern in review_patterns:
        if pattern in query_lower:
            return True
    
    return False

def extract_review_query(query: str) -> str:
    """Extract the actual search query from a review search query."""
    query = query.strip()
    
    prefixes = [
        'review:', 'reviews:', 'rating:', 'ratings:', 'feedback:', 
        'testimonial:', 'opinion:',
        'Review:', 'Reviews:', 'Rating:', 'Ratings:', 'Feedback:',
        'Testimonial:', 'Opinion:'
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
async def run_review_search(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """Main entry point for review search."""
    clean_query = extract_review_query(query)
    searcher = ReviewSearch(event_emitter)
    return await searcher.search(clean_query)

def run_review_search_sync(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """Synchronous wrapper for review search."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(run_review_search(query, event_emitter))
    finally:
        loop.close()


def main():
    """Main entry point for Review/rating search - compatible with SearchRouter"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Review/rating search')
    parser.add_argument('-q', '--query', required=True, help='Search query')
    args = parser.parse_args()
    
    query = args.query
    
    # Extract clean query by removing operator prefix
    if ':' in query:
        clean_query = query.split(':', 1)[1].strip()
    else:
        clean_query = query
    
    print(f"\n🔍 Review/rating search: {clean_query}")
    
    # Try to use existing search function if available
    try:
        if 'run_review_search_sync' in globals():
            results = globals()['run_review_search_sync'](clean_query)
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
        test_query = "review:iPhone 15 Pro rating>4"
    
    print(f"Testing review search with: {test_query}")
    
    if detect_review_query(test_query):
        print("Review query detected!")
        clean_query = extract_review_query(test_query)
        print(f"Extracted query: '{clean_query}'")
        
        results = run_review_search_sync(test_query)
        
        print(f"\nFound {len(results)} review results:")
        for i, result in enumerate(results[:10], 1):
            print(f"\n{i}. {result.get('title', 'No title')}")
            print(f"   URL: {result.get('url', 'No URL')}")
            print(f"   Score: {result.get('review_score', 0)}")
            if 'filters' in result:
                print(f"   Filters: {result['filters']}")
    else:
        print("Not a review query")