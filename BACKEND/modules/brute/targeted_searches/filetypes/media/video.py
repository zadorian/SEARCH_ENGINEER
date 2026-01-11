#!/usr/bin/env python3
"""
Video Search Handler - Searches for videos across multiple search engines
Supports: YouTube, Brave Videos, Archive.org, DuckDuckGo Videos
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import json
from pathlib import Path
import sys
from urllib.parse import quote
# Simple URL builder for Facebook Videos (no scraping)
def _fb_q(query: str) -> str:
    return quote(f'"{query}"')

def fb_videos(query: str) -> str:
    return f"https://www.facebook.com/search/videos/?q={_fb_q(query)}"

def baidu_videos(query: str) -> str:
    """Generate Baidu Video search URL"""
    return f"https://www.baidu.com/sf/vsearch?pd=video&wd={quote(query)}&tn=vsearch&ie=utf-8"

FB_URL_BUILDERS_AVAILABLE = True
BAIDU_URL_BUILDERS_AVAILABLE = True

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import Archive URL checker
try:
    from brute.utils.archive_url_checker import process_archive_results
    ARCHIVE_URL_CHECKER_AVAILABLE = True
except ImportError:
    ARCHIVE_URL_CHECKER_AVAILABLE = False
    print("⚠️  Archive URL checker not available")

# Import video search engines (will be created later)
try:
    from brute.engines.youtube_search import YouTubeSearch
    YOUTUBE_AVAILABLE = True
except ImportError:
    YOUTUBE_AVAILABLE = False
    print("⚠️  YouTube search not available")

try:
    from brute.engines.brave_videos import BraveVideosSearch
    BRAVE_VIDEOS_AVAILABLE = True
except ImportError:
    BRAVE_VIDEOS_AVAILABLE = False
    print("⚠️  Brave Videos search not available")

try:
    from brute.engines.duckduckgo_videos import DuckDuckGoVideosSearch
    DDG_VIDEOS_AVAILABLE = True
except ImportError:
    DDG_VIDEOS_AVAILABLE = False
    print("⚠️  DuckDuckGo Videos search not available")

try:
    from brute.engines.archiveorg import ArchiveOrgSearch
    ARCHIVE_AVAILABLE = True
except ImportError:
    ARCHIVE_AVAILABLE = False
    print("⚠️  Archive.org search not available")

# Streaming support
try:
    from brute.infrastructure.base_streamer import SearchTypeEventEmitter
    STREAMING_AVAILABLE = True
except ImportError:
    print("⚠️  Streaming not available")
    STREAMING_AVAILABLE = False
    # Fallback class
    class SearchTypeEventEmitter:
        def __init__(self, search_type=None): pass
        def enable_streaming(self, handler=None): pass
        def emit_search_result(self, result, engine=None): pass
        def emit_engine_status(self, engine, status, results=0): pass
        def start_search(self, query, engines=None): pass
        def complete_search(self, summary=None): pass
        def mark_engine_complete(self, engine, results_count=0, success=True): pass
        def get_search_summary(self): return {}

logger = logging.getLogger(__name__)


class VideoSearcher(SearchTypeEventEmitter):
    """Searches for videos across multiple search engines"""
    
    def __init__(self, enable_streaming: bool = False, event_handler: Optional[callable] = None):
        # Initialize streaming
        super().__init__(search_type="video_search")
        
        self.engines = self._initialize_engines()
        self.results = []
        self.seen_urls = set()
        
        # Set up streaming if requested
        if enable_streaming and event_handler:
            self.enable_streaming(event_handler)
    
    def _initialize_engines(self) -> Dict[str, Any]:
        """Initialize available video search engines"""
        engines = {}
        
        if YOUTUBE_AVAILABLE:
            try:
                engines['youtube'] = YouTubeSearch()
                logger.info("Initialized YouTube search")
            except Exception as e:
                logger.warning(f"Could not initialize YouTube: {e}")
        
        if BRAVE_VIDEOS_AVAILABLE:
            try:
                engines['brave_videos'] = BraveVideosSearch()
                logger.info("Initialized Brave Videos search")
            except Exception as e:
                logger.warning(f"Could not initialize Brave Videos: {e}")
        
        # Also add Brave web search with video filtering
        try:
            from brute.engines.exact_phrase_recall_runner_brave import BraveSearch
            engines['brave_web_videos'] = BraveSearch()
            engines['brave_web_videos'].set_search_preferences(
                safesearch="moderate",
                freshness="all",
                spellcheck=True
            )
            logger.info("Initialized Brave web search for video content")
        except ImportError:
            logger.warning("Brave web search not available for video content")
        
        if DDG_VIDEOS_AVAILABLE:
            try:
                engines['duckduckgo_videos'] = DuckDuckGoVideosSearch()
                logger.info("Initialized DuckDuckGo Videos search")
            except Exception as e:
                logger.warning(f"Could not initialize DuckDuckGo Videos: {e}")
        
        if ARCHIVE_AVAILABLE:
            try:
                engines['archive'] = ArchiveOrgSearch()
                logger.info("Initialized Archive.org search")
            except Exception as e:
                logger.warning(f"Could not initialize Archive.org: {e}")
        
        # Add Qwant Videos search
        try:
            from brute.engines.qwant import QwantSearchRunner
            engines['qwant_videos'] = QwantSearchRunner
            logger.info("Initialized Qwant Videos search")
        except ImportError:
            logger.warning("Qwant search not available for video content")

        # Lightweight pseudo-engine to provide a direct Facebook Videos link
        if FB_URL_BUILDERS_AVAILABLE:
            engines['facebook_videos'] = object()
            logger.info("Initialized Facebook Videos link provider")
        
        # Lightweight pseudo-engine to provide a direct Baidu Videos link
        if BAIDU_URL_BUILDERS_AVAILABLE:
            engines['baidu_videos'] = object()
            logger.info("Initialized Baidu Videos link provider")
        
        return engines
    
    async def search(self, query: str, max_results: int = 100) -> Dict[str, Any]:
        """
        Search for videos across multiple engines
        
        Args:
            query: Search query
            max_results: Maximum number of results per engine
            
        Returns:
            Dict containing search results and metadata
        """
        # Start streaming
        engines_list = list(self.engines.keys())
        self.start_search(query, engines_list)
        
        if not self.engines:
            error_msg = "No video search engines available"
            logger.error(error_msg)
            self.complete_search({'error': error_msg})
            return {'error': error_msg}
        
        print(f"\\n🎥 Searching for videos: '{query}'")
        print(f"🔍 Using {len(self.engines)} search engines...")
        
        results = {
            'query': query,
            'search_type': 'video',
            'engines': {},
            'total_results': 0,
            'unique_results': 0,
            'results': []
        }
        
        # Create tasks for all engines
        tasks = []
        for engine_name, engine in self.engines.items():
            task = self._search_engine(engine_name, engine, query, max_results)
            tasks.append(task)
        
        # Run all searches concurrently
        engine_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        all_results = []
        for i, (engine_name, engine) in enumerate(self.engines.items()):
            if isinstance(engine_results[i], Exception):
                logger.error(f"Error in {engine_name}: {engine_results[i]}")
                results['engines'][engine_name] = {
                    'error': str(engine_results[i]),
                    'count': 0
                }
                self.mark_engine_complete(engine_name, 0, success=False)
            else:
                engine_data = engine_results[i]
                results['engines'][engine_name] = {
                    'count': len(engine_data),
                    'sample': engine_data[:3] if engine_data else []
                }
                all_results.extend(engine_data)
                self.mark_engine_complete(engine_name, len(engine_data), success=True)
        
        # Process Archive.org URLs to replace with live versions when possible
        if ARCHIVE_URL_CHECKER_AVAILABLE and all_results:
            logger.info(f"Checking Archive.org URLs for live versions...")
            try:
                all_results = await process_archive_results(all_results)
                logger.info(f"Archive URL processing completed")
            except Exception as e:
                logger.warning(f"Archive URL processing failed, continuing with original URLs: {e}")
        
        # Deduplicate results
        unique_results = []
        for result in all_results:
            url = result.get('url', '')
            if url and url not in self.seen_urls:
                self.seen_urls.add(url)
                unique_results.append(result)
                # Emit streaming event
                self.emit_search_result(result, result.get('source', 'unknown'))
        
        results['results'] = unique_results
        results['total_results'] = len(all_results)
        results['unique_results'] = len(unique_results)
        
        # Complete streaming
        summary = {
            'total_results': results['total_results'],
            'unique_results': results['unique_results'],
            'engines_used': len(self.engines)
        }
        self.complete_search(summary)
        
        print(f"\\n✅ Found {results['unique_results']} unique videos from {results['total_results']} total results")
        
        return results
    
    async def _search_engine(self, engine_name: str, engine: Any, query: str, max_results: int) -> List[Dict]:
        """Search a single engine"""
        print(f"\\n🔍 Searching {engine_name}...")
        
        try:
            if engine_name == 'facebook_videos' and FB_URL_BUILDERS_AVAILABLE:
                # We don't scrape FB; just return a navigable link row
                url = fb_videos(query)
                return [{
                    'title': f'Facebook Videos: {query}',
                    'url': url,
                    'source': 'facebook_videos',
                    'thumbnail': '',
                    'description': 'Open Facebook video search for this query.'
                }]
            elif engine_name == 'baidu_videos' and BAIDU_URL_BUILDERS_AVAILABLE:
                # We don't scrape Baidu; just return a navigable link row
                url = baidu_videos(query)
                return [{
                    'title': f'Baidu Videos: {query}',
                    'url': url,
                    'source': 'baidu_videos',
                    'thumbnail': '',
                    'description': 'Open Baidu video search for this query.'
                }]
            elif engine_name == 'archive':
                # Special handling for Archive.org
                archive_query = f'{query} mediatype:movies'
                results = await self._run_async(engine.search, archive_query, max_results)
            elif engine_name == 'brave_web_videos':  
                # Use Brave's specialized video search
                results = await self._run_async(
                    engine.brave_video_search,
                    query,
                    max_results
                )
            elif engine_name == 'qwant_videos':
                # Use Qwant Videos search
                qwant = engine(query, search_type='videos', max_results=max_results)
                results = list(qwant.run())
            else:
                # Standard video search engines
                results = await self._run_async(engine.search, query, max_results)
            
            # Normalize results
            normalized = []
            for result in results:
                normalized_result = self._normalize_result(result, engine_name)
                if normalized_result:
                    normalized.append(normalized_result)
            
            print(f"   ✓ {engine_name}: Found {len(normalized)} videos")
            return normalized
            
        except Exception as e:
            logger.error(f"Error searching {engine_name}: {e}")
            print(f"   ✗ {engine_name}: Error - {str(e)}")
            return []
    
    async def _run_async(self, func, *args):
        """Run a synchronous function asynchronously"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, *args)
    
    def _normalize_result(self, result: Dict, source: str) -> Optional[Dict]:
        """Normalize result format across different engines"""
        try:
            normalized = {
                'title': result.get('title', ''),
                'url': result.get('url', result.get('link', '')),
                'source': source,
                'thumbnail': result.get('thumbnail', result.get('thumb', '')),
                'duration': result.get('duration', ''),
                'view_count': result.get('view_count', result.get('views', '')),
                'upload_date': result.get('upload_date', result.get('published', '')),
                'channel': result.get('channel', result.get('uploader', '')),
                'channel_url': result.get('channel_url', ''),
                'description': result.get('description', result.get('snippet', '')),
                'embed_url': result.get('embed_url', ''),
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Ensure we have a valid URL
            if not normalized['url']:
                return None
            
            return normalized
            
        except Exception as e:
            logger.error(f"Error normalizing result: {e}")
            return None
    
    def save_results(self, results: Dict, output_file: str = None):
        """Save results to file"""
        if not output_file:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"video_search_{results['query']}_{timestamp}.json"
        
        output_path = Path('results') / output_file
        output_path.parent.mkdir(exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\\n💾 Results saved to: {output_path}")
        return str(output_path)


async def main():
    """Example usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Search for videos across multiple engines')
    parser.add_argument('query', help='Search query')
    parser.add_argument('-m', '--max-results', type=int, default=50, help='Max results per engine')
    parser.add_argument('-o', '--output', help='Output file path')
    
    args = parser.parse_args()
    
    searcher = VideoSearcher()
    results = await searcher.search(args.query, args.max_results)
    
    if args.output:
        searcher.save_results(results, args.output)
    
    # Display sample results
    print("\\n📊 Sample Results:")
    for i, result in enumerate(results['results'][:5], 1):
        print(f"\\n{i}. {result['title']}")
        print(f"   URL: {result['url']}")
        print(f"   Source: {result['source']}")
        if result.get('duration'):
            print(f"   Duration: {result['duration']}")
        if result.get('channel'):
            print(f"   Channel: {result['channel']}")


if __name__ == '__main__':
    asyncio.run(main())

# Adapter to match web_api.api.search expectation
def search(query: str, max_results: int = 100):
    searcher = VideoSearcher()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(searcher.search(query, max_results))
        return results.get('results', []) if isinstance(results, dict) else results
    finally:
        loop.close()