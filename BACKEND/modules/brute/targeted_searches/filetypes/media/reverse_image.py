#!/usr/bin/env python3
"""
Reverse Image Search Handler - Reverse search images using multiple engines
Supports: Google Lens/Vision API, TinEye, Yandex Images
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import json
from pathlib import Path
import sys
import requests
from urllib.parse import quote_plus

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

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


class ReverseImageSearcher(SearchTypeEventEmitter):
    """Performs reverse image searches across multiple engines"""
    
    def __init__(self, enable_streaming: bool = False, event_handler: Optional[callable] = None):
        # Initialize streaming
        super().__init__(search_type="reverse_image_search")
        
        self.engines = self._initialize_engines()
        self.results = []
        self.seen_urls = set()
        
        # Set up streaming if requested
        if enable_streaming and event_handler:
            self.enable_streaming(event_handler)
    
    def _initialize_engines(self) -> Dict[str, Any]:
        """Initialize available reverse image search engines"""
        engines = {}
        
        # Google Vision API (if available)
        try:
            import os
            if os.getenv('GOOGLE_VISION_API_KEY'):
                engines['google_vision'] = self._init_google_vision()
                logger.info("Initialized Google Vision API")
        except Exception as e:
            logger.warning(f"Could not initialize Google Vision: {e}")
        
        # TinEye API (if available)
        try:
            import os
            if os.getenv('TINEYE_API_KEY'):
                engines['tineye'] = self._init_tineye()
                logger.info("Initialized TinEye API")
        except Exception as e:
            logger.warning(f"Could not initialize TinEye: {e}")
        
        # Yandex Images (free, no API key needed)
        engines['yandex_images'] = self._init_yandex_images()
        logger.info("Initialized Yandex Images reverse search")
        
        return engines
    
    def _init_google_vision(self):
        """Initialize Google Vision API client"""
        import os
        return {
            'api_key': os.getenv('GOOGLE_VISION_API_KEY'),
            'base_url': 'https://vision.googleapis.com/v1/images:annotate'
        }
    
    def _init_tineye(self):
        """Initialize TinEye API client"""
        import os
        return {
            'api_key': os.getenv('TINEYE_API_KEY'),
            'private_key': os.getenv('TINEYE_PRIVATE_KEY'),
            'base_url': 'https://api.tineye.com/rest/search'
        }
    
    def _init_yandex_images(self):
        """Initialize Yandex Images reverse search"""
        return {
            'base_url': 'https://yandex.com/images/search',
            'search_url': 'https://yandex.com/images/search'
        }
    
    async def search(self, image_url: str, max_results: int = 50) -> Dict[str, Any]:
        """
        Perform reverse image search
        
        Args:
            image_url: URL of the image to search for
            max_results: Maximum number of results per engine
            
        Returns:
            Dict containing search results and metadata
        """
        # Start streaming
        engines_list = list(self.engines.keys())
        self.start_search(image_url, engines_list)
        
        if not self.engines:
            error_msg = "No reverse image search engines available"
            logger.error(error_msg)
            self.complete_search({'error': error_msg})
            return {'error': error_msg}
        
        print(f"\\n🔍 Reverse searching image: '{image_url}'")
        print(f"🔍 Using {len(self.engines)} search engines...")
        
        results = {
            'query': image_url,
            'search_type': 'reverse_image',
            'engines': {},
            'total_results': 0,
            'unique_results': 0,
            'results': []
        }
        
        # Create tasks for all engines
        tasks = []
        for engine_name, engine in self.engines.items():
            task = self._search_engine(engine_name, engine, image_url, max_results)
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
        
        print(f"\\n✅ Found {results['unique_results']} unique matches from {results['total_results']} total results")
        
        return results
    
    async def _search_engine(self, engine_name: str, engine: Any, image_url: str, max_results: int) -> List[Dict]:
        """Search a single engine"""
        print(f"\\n🔍 Searching {engine_name}...")
        
        try:
            if engine_name == 'google_vision':
                results = await self._search_google_vision(engine, image_url, max_results)
            elif engine_name == 'tineye':
                results = await self._search_tineye(engine, image_url, max_results)
            elif engine_name == 'yandex_images':
                results = await self._search_yandex_images(engine, image_url, max_results)
            else:
                logger.warning(f"Unknown reverse search engine: {engine_name}")
                return []
            
            # Normalize results
            normalized = []
            for result in results:
                normalized_result = self._normalize_result(result, engine_name)
                if normalized_result:
                    normalized.append(normalized_result)
            
            print(f"   ✓ {engine_name}: Found {len(normalized)} matches")
            return normalized
            
        except Exception as e:
            logger.error(f"Error searching {engine_name}: {e}")
            print(f"   ✗ {engine_name}: Error - {str(e)}")
            return []
    
    async def _search_google_vision(self, engine: Dict, image_url: str, max_results: int) -> List[Dict]:
        """Search using Google Vision API"""
        # For now, return empty - would need Google Vision API implementation
        logger.info("Google Vision API search not yet implemented")
        return []
    
    async def _search_tineye(self, engine: Dict, image_url: str, max_results: int) -> List[Dict]:
        """Search using TinEye API"""
        # For now, return empty - would need TinEye API implementation
        logger.info("TinEye API search not yet implemented")
        return []
    
    async def _search_yandex_images(self, engine: Dict, image_url: str, max_results: int) -> List[Dict]:
        """Search using Yandex Images reverse search"""
        try:
            # Yandex Images reverse search URL
            search_url = f"https://yandex.com/images/search?rpt=imageview&url={quote_plus(image_url)}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            # For now, return a basic result indicating the search was performed
            # A full implementation would parse the Yandex results page
            return [{
                'title': f'Yandex reverse search for image',
                'url': search_url,
                'description': f'Reverse image search results on Yandex Images',
                'similarity': 'unknown',
                'source_page': search_url,
                'found_at': datetime.utcnow().isoformat()
            }]
            
        except Exception as e:
            logger.error(f"Yandex Images reverse search failed: {e}")
            return []
    
    def _normalize_result(self, result: Dict, source: str) -> Optional[Dict]:
        """Normalize result format across different engines"""
        try:
            normalized = {
                'title': result.get('title', ''),
                'url': result.get('url', ''),
                'source': source,
                'thumbnail': result.get('thumbnail', ''),
                'similarity': result.get('similarity', 'unknown'),
                'source_page': result.get('source_page', ''),
                'description': result.get('description', ''),
                'found_at': result.get('found_at', datetime.utcnow().isoformat()),
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
            # Create safe filename from URL
            safe_query = results['query'].replace('/', '_').replace(':', '_')[:50]
            output_file = f"reverse_image_search_{safe_query}_{timestamp}.json"
        
        output_path = Path('results') / output_file
        output_path.parent.mkdir(exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\\n💾 Results saved to: {output_path}")
        return str(output_path)


async def main():
    """Example usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Reverse search images across multiple engines')
    parser.add_argument('image_url', help='Image URL to search for')
    parser.add_argument('-m', '--max-results', type=int, default=50, help='Max results per engine')
    parser.add_argument('-o', '--output', help='Output file path')
    
    args = parser.parse_args()
    
    searcher = ReverseImageSearcher()
    results = await searcher.search(args.image_url, args.max_results)
    
    if args.output:
        searcher.save_results(results, args.output)
    
    # Display results
    print("\\n📊 Results:")
    for i, result in enumerate(results['results'][:10], 1):
        print(f"\\n{i}. {result['title']}")
        print(f"   URL: {result['url']}")
        print(f"   Source: {result['source']}")
        if result.get('similarity') != 'unknown':
            print(f"   Similarity: {result['similarity']}")


if __name__ == '__main__':
    asyncio.run(main())

# Adapter to match web_api.api.search expectation
def search(image_url: str, max_results: int = 50):
    searcher = ReverseImageSearcher()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(searcher.search(image_url, max_results))
        return results.get('results', []) if isinstance(results, dict) else results
    finally:
        loop.close()