#!/usr/bin/env python3
"""
Forum Search - Comprehensive forum and discussion search across multiple platforms
Aggregates results from: Brave discussions, SocialSearcher, BoardReader, and Grok (Twitter/X)
"""

import sys
import asyncio
import json
import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from brute.engines.baresearch import bare_it

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import event streaming for WebSocket support
try:
    from brute.infrastructure.base_streamer import SearchTypeEventEmitter
    STREAMING_AVAILABLE = True
except ImportError:
    STREAMING_AVAILABLE = False
    logging.warning("Event streaming not available for forum search")
    # Fallback class
    class SearchTypeEventEmitter:
        def __init__(self, search_type=None): pass
        def enable_streaming(self, handler=None): pass
        def emit_search_result(self, result, engine=None): pass
        def emit_search_filtered_result(self, result, engine=None): pass
        def emit_engine_status(self, engine, status, results=0): pass
        def start_search(self, query, engines=None): pass
        def complete_search(self, summary=None): pass
        def mark_engine_complete(self, engine, results_count=0, success=True): pass
        def get_search_summary(self): return {}

# BrightData Archive - native cat{forum}! support (17.5 PB cached web data)
try:
    from backdrill.brightdata import BrightDataArchive, search_by_category
    BRIGHTDATA_ARCHIVE_AVAILABLE = True
except ImportError:
    BRIGHTDATA_ARCHIVE_AVAILABLE = False
    BrightDataArchive = None
    search_by_category = None

# Filtering integration
try:
    from brute.scraper.phrase_matcher import PhraseMatcher
    from brute.filtering.core.filter_manager import FilterManager
    FILTERING_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Filtering not available: {e}")
    FILTERING_AVAILABLE = False

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import search engines
# Import search engines with availability flags
try:
    from brute.engines.brave import BraveSearch
    BRAVE_AVAILABLE = True
except ImportError:
    BRAVE_AVAILABLE = False
    logger.warning("Brave search not available")

try:
    from brute.engines.socialsearcher import SocialSearcher as ExactPhraseRecallRunnerSocialSearcher
    SOCIALSEARCHER_AVAILABLE = True
except ImportError:
    SOCIALSEARCHER_AVAILABLE = False
    logger.warning("SocialSearcher not available")

try:
    from brute.engines.boardreader import BoardReaderEngine as ExactPhraseRecallRunnerBoardreaderV2
    BOARDREADER_AVAILABLE = True
except ImportError:
    BOARDREADER_AVAILABLE = False
    logger.warning("BoardReader not available")

try:
    from brute.engines.grok import ExactPhraseRecallRunnerGrok
    GROK_AVAILABLE = True
except ImportError:
    GROK_AVAILABLE = False
    logger.warning("Grok search not available")

# Global deduplication for thread safety
DEDUP_LOCK = threading.Lock()
ALL_FORUM_RESULTS: Dict[str, Dict] = {}

class ForumResult:
    """Unified forum result structure"""
    
    def __init__(self, url: str, title: str, snippet: str, source: str, **kwargs):
        self.url = url
        self.title = title
        self.snippet = snippet
        self.source = source  # 'brave_discussions', 'socialsearcher', 'boardreader', 'grok'
        
        # Optional fields with defaults
        self.forum_type = kwargs.get('forum_type')  # 'reddit', 'twitter', 'traditional_forum', etc.
        self.post_date = kwargs.get('post_date')
        self.author = kwargs.get('author')
        self.engagement_metrics = kwargs.get('engagement_metrics', {})
        self.thread_info = kwargs.get('thread_info', {})
        self.exact_phrase_validated = kwargs.get('exact_phrase_validated', False)
        
        # Metadata
        self.found_by_query = kwargs.get('found_by_query', '')
        self.search_type = kwargs.get('search_type', 'main')
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format"""
        return {
            'url': self.url,
            'title': self.title,
            'snippet': self.snippet,
            'source': self.source,
            'forum_type': self.forum_type,
            'post_date': self.post_date,
            'author': self.author,
            'engagement_metrics': self.engagement_metrics,
            'thread_info': self.thread_info,
            'exact_phrase_validated': self.exact_phrase_validated,
            'found_by_query': self.found_by_query,
            'search_type': self.search_type,
            'engine': self.source  # For compatibility with existing UI
        }

class BraveDiscussionsEngine:
    """Wrapper for Brave discussions search"""
    
    def __init__(self):
        if BRAVE_AVAILABLE:
            self.brave = BraveSearch()
        else:
            self.brave = None
    
    def search(self, query: str, max_results: int = 50) -> List[ForumResult]:
        """Search Brave with discussions filter"""
        if not self.brave:
            logger.warning("Brave search not available")
            return []
        
        try:
            # Use Brave discussions search method
            results = self.brave.discussions_search(
                query=query,
                max_results=max_results
            )
            
            forum_results = []
            for result in results:
                forum_result = ForumResult(
                    url=result.get('url', ''),
                    title=result.get('title', ''),
                    snippet=result.get('snippet', ''),
                    source='brave_discussions',
                    forum_type='discussion_board',
                    found_by_query=query,
                    search_type='main'
                )
                forum_results.append(forum_result)
            
            logger.info(f"Brave discussions: Found {len(forum_results)} results")
            return forum_results
            
        except Exception as e:
            logger.error(f"Brave discussions search failed: {e}")
            return []

class SocialSearcherEngine:
    """Wrapper for SocialSearcher"""
    
    def __init__(self):
        self.available = SOCIALSEARCHER_AVAILABLE
    
    def search(self, query: str, max_results: int = 50) -> List[ForumResult]:
        """Search social networks via SocialSearcher"""
        if not self.available:
            logger.warning("SocialSearcher not available")
            return []
        
        try:
            # Use existing comprehensive SocialSearcher implementation
            runner = ExactPhraseRecallRunnerSocialSearcher(
                phrase=query,
                networks_to_search=['reddit', 'youtube', 'web', 'tumblr'],  # Focus on forum-like networks
                content_types_to_search=[None, 'status', 'link'],  # Relevant content types
                languages_to_search=[None, 'en'],  # English + all languages
                use_parallel=True,
                max_workers=2,
                exception_search_iterations=1  # Reduced for speed
            )
            
            forum_results = []
            for result in runner.run():
                # Map network to forum_type
                network = result.get('network', 'unknown')
                forum_type = {
                    'reddit': 'reddit',
                    'youtube': 'youtube_comments',
                    'tumblr': 'tumblr',
                    'web': 'web_discussions',
                    'vk': 'vkontakte',
                    'flickr': 'flickr_comments',
                    'dailymotion': 'dailymotion_comments'
                }.get(network, 'social_network')
                
                forum_result = ForumResult(
                    url=result.get('url', ''),
                    title=result.get('text', '')[:100] + '...' if result.get('text') else 'Social Media Post',
                    snippet=result.get('text', ''),
                    source='socialsearcher',
                    forum_type=forum_type,
                    post_date=result.get('posted'),
                    author=result.get('user', {}).get('name') if result.get('user') else None,
                    engagement_metrics={
                        'popularity': result.get('popularity'),
                        'sentiment': result.get('sentiment')
                    },
                    found_by_query=result.get('found_by_query', query),
                    search_type=result.get('search_type', 'main')
                )
                forum_results.append(forum_result)
            
            logger.info(f"SocialSearcher: Found {len(forum_results)} results")
            return forum_results
            
        except Exception as e:
            logger.error(f"SocialSearcher search failed: {e}")
            return []

class BoardReaderEngine:
    """Wrapper for BoardReader traditional forums"""
    
    def __init__(self):
        self.available = BOARDREADER_AVAILABLE
    
    async def search_async(self, query: str, max_results: int = 50) -> List[ForumResult]:
        """Async search for BoardReader"""
        if not self.available:
            logger.warning("BoardReader not available")
            return []
        
        try:
            runner = ExactPhraseRecallRunnerBoardreaderV2(
                phrase=query,
                max_results=max_results,
                use_variations=True,
                periods=['365', '180'],  # Reduced for speed
                languages=['All', 'English'],  # Reduced for speed
                sorts=['time', 'relevance']
            )
            
            forum_results = []
            async for result in runner.run():
                forum_result = ForumResult(
                    url=result.url,
                    title=result.title,
                    snippet=result.snippet,
                    source='boardreader',
                    forum_type=result.forum_type or 'traditional_forum',
                    post_date=result.post_date,
                    engagement_metrics={
                        'word_count': result.word_count,
                        'has_links': result.has_links,
                        'external_links_count': len(result.external_links)
                    },
                    thread_info={
                        'content_type': result.content_type,
                        'external_links': result.external_links[:5]  # Limit for performance
                    },
                    found_by_query=result.search_metadata.get('keyword', query),
                    search_type=result.search_metadata.get('search_type', 'main')
                )
                forum_results.append(forum_result)
            
            logger.info(f"BoardReader: Found {len(forum_results)} results")
            return forum_results
            
        except Exception as e:
            logger.error(f"BoardReader search failed: {e}")
            return []
    
    def search(self, query: str, max_results: int = 50) -> List[ForumResult]:
        """Sync wrapper for BoardReader"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.search_async(query, max_results))
        finally:
            loop.close()

class GrokTwitterEngine:
    """Enhanced Grok engine for Twitter/X discussions"""
    
    def __init__(self):
        self.available = GROK_AVAILABLE
    
    def search(self, query: str, max_results: int = 50) -> List[ForumResult]:
        """Search Twitter/X via Grok"""
        if not self.available:
            logger.warning("Grok search not available")
            return []
        
        try:
            runner = ExactPhraseRecallRunnerGrok(
                phrase=query,
                max_search_results=max_results,
                min_engagement=10,  # Lower threshold for discussions
                use_x=True,
                use_news=False  # Focus on X/Twitter only for forum search
            )
            
            results = runner.search(max_results=max_results)
            
            forum_results = []
            for result in results:
                forum_result = ForumResult(
                    url=result.get('url', ''),
                    title=result.get('title', 'Twitter/X Post'),
                    snippet=result.get('snippet', ''),
                    source='grok',
                    forum_type='twitter',
                    found_by_query=query,
                    search_type='main'
                )
                forum_results.append(forum_result)
            
            logger.info(f"Grok Twitter: Found {len(forum_results)} results")
            return forum_results
            
        except Exception as e:
            logger.error(f"Grok Twitter search failed: {e}")
            return []

class ForumSearchRouter(SearchTypeEventEmitter):
    """Main forum search orchestrator"""
    
    def __init__(self, enable_streaming: bool = False, event_handler: Optional[callable] = None):
        # Initialize streaming first
        super().__init__(search_type="forum")
        
        # Initialize engines
        self.engines = {
            'brave_discussions': BraveDiscussionsEngine(),
            'socialsearcher': SocialSearcherEngine(),
            'boardreader': BoardReaderEngine(),
            'grok': GrokTwitterEngine()
        }
        
        # Set up streaming if requested
        if enable_streaming and event_handler:
            self.enable_streaming(event_handler)
        
        # Initialize filtering components
        if FILTERING_AVAILABLE:
            try:
                self.phrase_matcher = PhraseMatcher(max_distance=3)
                self.filter_manager = FilterManager()
                self.enable_exact_phrase_filter = True
                self.filtered_results = []
                logger.info("Filtering integration initialized for forum search")
            except Exception as e:
                logger.warning(f"Could not initialize filtering: {e}")
                self.phrase_matcher = None
                self.filter_manager = None
                self.enable_exact_phrase_filter = False
                self.filtered_results = []
        else:
            self.phrase_matcher = None
            self.filter_manager = None
            self.enable_exact_phrase_filter = False
            self.filtered_results = []
    
    def _filter_results(self, results: List[ForumResult], original_query: str) -> Tuple[List[ForumResult], List[ForumResult]]:
        """Filter results based on exact phrase matching"""
        if not self.enable_exact_phrase_filter or not self.phrase_matcher:
            return results, []
        
        # Extract exact phrases from the original query
        phrases = self.phrase_matcher.extract_phrases(original_query)
        if not phrases:
            return results, []
        
        filtered_results = []
        non_matching_results = []
        
        for result in results:
            title = result.title or ''
            snippet = result.snippet or ''
            
            # Check if any exact phrase is found in title or snippet
            phrase_found = False
            for phrase in phrases:
                if self.phrase_matcher.check_exact_match(phrase, title) or \
                   self.phrase_matcher.check_exact_match(phrase, snippet) or \
                   self.phrase_matcher.check_proximity_match(phrase, title) or \
                   self.phrase_matcher.check_proximity_match(phrase, snippet):
                    phrase_found = True
                    result.exact_phrase_validated = True
                    break
            
            if phrase_found:
                filtered_results.append(result)
            else:
                # Mark as filtered for the "Filtered Out" tab
                result.exact_phrase_validated = False
                non_matching_results.append(result)
        
        return filtered_results, non_matching_results
    
    def _deduplicate_results(self, all_results: List[ForumResult]) -> List[ForumResult]:
        """Deduplicate results across all sources"""
        seen_urls = set()
        deduplicated = []
        
        for result in all_results:
            if result.url and result.url not in seen_urls:
                seen_urls.add(result.url)
                deduplicated.append(result)
        
        logger.info(f"Deduplication: {len(all_results)} -> {len(deduplicated)} results")
        return deduplicated
    
    def search(self, query: str, max_results_per_engine: int = 50) -> Dict[str, Any]:
        """Execute forum search across all engines"""
        logger.info(f"Starting comprehensive forum search for: '{query}'")
        
        # Start streaming
        available_engines = [name for name, engine in self.engines.items()]
        self.start_search(query, available_engines)
        
        # Clear global deduplication
        with DEDUP_LOCK:
            ALL_FORUM_RESULTS.clear()
        
        # BareSearch IT/forums link row
        bare_row = {'title': f'BareSearch IT/Forums: {query}', 'url': bare_it(query), 'source': 'baresearch_it'}
        all_results = [ForumResult(url=bare_row['url'], title=bare_row['title'], snippet='', source=bare_row['source'])]
        engine_results = {}
        
        # Execute searches in parallel
        with ThreadPoolExecutor(max_workers=4) as executor:
            # Submit all search tasks
            future_to_engine = {}
            
            for engine_name, engine in self.engines.items():
                logger.info(f"Starting {engine_name} search...")
                self.emit_engine_status(engine_name, "starting")
                
                future = executor.submit(engine.search, query, max_results_per_engine)
                future_to_engine[future] = engine_name
            
            # Collect results as they complete
            for future in as_completed(future_to_engine):
                engine_name = future_to_engine[future]
                
                try:
                    results = future.result()
                    engine_results[engine_name] = {
                        'results': results,
                        'count': len(results)
                    }
                    
                    # Stream results immediately
                    for result in results:
                        self.emit_search_result(result.to_dict(), engine_name)
                        all_results.append(result)
                    
                    logger.info(f"{engine_name}: Found {len(results)} results")
                    self.mark_engine_complete(engine_name, len(results), success=True)
                    
                except Exception as e:
                    logger.error(f"{engine_name} search failed: {e}")
                    engine_results[engine_name] = {
                        'error': str(e),
                        'count': 0
                    }
                    self.mark_engine_complete(engine_name, 0, success=False)

        # BrightData Archive - native cat{forum}! support
        if BRIGHTDATA_ARCHIVE_AVAILABLE and search_by_category:
            try:
                # Run async search in sync context
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                async def _bd_search():
                    return await search_by_category(
                        category="forum",
                        limit=max_results_per_engine // 2,
                    )

                if loop and loop.is_running():
                    # Already in async context - create task
                    bd_results = asyncio.ensure_future(_bd_search())
                else:
                    # No event loop - run sync
                    bd_results = asyncio.run(_bd_search())

                for r in (bd_results if isinstance(bd_results, list) else []):
                    forum_result = ForumResult(
                        url=r.get('url', ''),
                        title=r.get('title', ''),
                        snippet=r.get('snippet', ''),
                        source='brightdata_archive',
                        forum_type='archive',
                        found_by_query=query,
                    )
                    self.emit_search_result(forum_result.to_dict(), 'brightdata_archive')
                    all_results.append(forum_result)
                logger.info(f"BrightData Archive added forum results")
            except Exception as e:
                logger.warning(f"BrightData Archive forum search failed: {e}")

        # Deduplicate results
        deduplicated_results = self._deduplicate_results(all_results)
        
        # Apply filtering if enabled
        if self.enable_exact_phrase_filter:
            filtered_results, non_matching = self._filter_results(deduplicated_results, query)
            
            # Emit filtered results as streaming events
            for filtered_result in non_matching:
                self.emit_search_filtered_result(filtered_result.to_dict(), 'filter')
            
            # Store filtered results for "Filtered Out" tab
            self.filtered_results.extend(non_matching)
            
            # Use filtered results for final output
            final_results = filtered_results
            
            if non_matching:
                logger.info(f"Filtered out {len(non_matching)} results that didn't match exact phrases")
        else:
            final_results = deduplicated_results
        
        # Prepare response
        response = {
            'query': query,
            'total_results': len(final_results),
            'engines': engine_results,
            'results': [result.to_dict() for result in final_results],
            'sources': list(engine_results.keys()),
            'deduplication_stats': {
                'before': len(all_results),
                'after': len(deduplicated_results)
            }
        }
        
        # Add filtering statistics
        if self.enable_exact_phrase_filter:
            response['filtered_count'] = len(self.filtered_results)
            response['filtered_results'] = [r.to_dict() for r in self.filtered_results]
        
        # Complete streaming with summary
        summary = {
            'total_results': len(final_results),
            'sources_used': len([e for e in engine_results.values() if e.get('count', 0) > 0]),
            'filtered_count': len(self.filtered_results) if self.enable_exact_phrase_filter else 0
        }
        self.complete_search(summary)
        
        logger.info(f"Forum search complete: {len(final_results)} total results from {len(available_engines)} sources")
        return response

# Adapter to match web_api.api.search expectation
def search(query: str, max_results_per_engine: int = 50):
    router = ForumSearchRouter()
    return router.search(query, max_results_per_engine)

def main():
    """CLI entry point for forum search"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Forum and discussion search across multiple platforms')
    parser.add_argument('query', help='Search query')
    parser.add_argument('-m', '--max-results', type=int, default=50, help='Max results per engine')
    parser.add_argument('-o', '--output', help='Output JSON file')
    parser.add_argument('--streaming', action='store_true', help='Enable streaming output')
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create router and run search
    router = ForumSearchRouter(enable_streaming=args.streaming)
    results = router.search(args.query, args.max_results)
    
    # Save results if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"Results saved to: {args.output}")
    
    # Print summary
    print(f"\n=== FORUM SEARCH RESULTS ===")
    print(f"Query: {args.query}")
    print(f"Total Results: {results['total_results']}")
    print(f"Sources Used: {', '.join(results['sources'])}")
    
    if results.get('filtered_count'):
        print(f"Filtered Out: {results['filtered_count']}")
    
    # Show sample results
    if results['results']:
        print(f"\nSample Results:")
        for i, result in enumerate(results['results'][:5], 1):
            print(f"\n{i}. {result['title']}")
            print(f"   Source: {result['source']} ({result.get('forum_type', 'unknown')})")
            print(f"   URL: {result['url']}")
            print(f"   Snippet: {result['snippet'][:150]}...")

if __name__ == '__main__':
    main()