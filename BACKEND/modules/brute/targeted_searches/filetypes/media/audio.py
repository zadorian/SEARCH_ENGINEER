#!/usr/bin/env python3
"""
Audio/Podcast Search Operator - Searches audio content and podcast platforms
Supports audio:, podcast: operators with schema integration
Leverages podcast platforms and Schema.org AudioObject/PodcastEpisode structured data
Includes automatic transcription for audio file URLs
"""

import sys
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime
import time
from brute.engines.baresearch import bare_music

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import transcription service
try:
    from toolkit.audio_transcription_service import AudioTranscriptionService
    TRANSCRIPTION_AVAILABLE = True
except ImportError:
    TRANSCRIPTION_AVAILABLE = False
    logging.warning("Audio transcription service not available")

# Import event streaming for filtering events
try:
    from brute.infrastructure.base_streamer import SearchTypeEventEmitter
    STREAMING_AVAILABLE = True
except ImportError:
    STREAMING_AVAILABLE = False
    logging.warning("Event streaming not available for audio search")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Audio/Podcast search engines
AUDIO_ENGINES = [
    'GO',  # Google - with schema search
    'BI',  # Bing
    'BR',  # Brave
    'DD',  # DuckDuckGo
    'YA',  # Yandex
    'AR',  # Archive.org - has audio collections
]

# Major podcast and audio platforms
AUDIO_PLATFORMS = {
    'spotify': 'site:open.spotify.com',
    'apple_podcasts': 'site:podcasts.apple.com',
    'youtube': 'site:youtube.com podcast',
    'soundcloud': 'site:soundcloud.com',
    'podbean': 'site:podbean.com',
    'stitcher': 'site:stitcher.com',
    'iheartradio': 'site:iheart.com',
    'tunein': 'site:tunein.com',
    'audible': 'site:audible.com',
    'podcastaddict': 'site:podcastaddict.com',
    'overcast': 'site:overcast.fm',
    'pocketcasts': 'site:pocketcasts.com',
    'castbox': 'site:castbox.fm',
    'google_podcasts': 'site:podcasts.google.com',
    'npr': 'site:npr.org podcast',
    'bbc': 'site:bbc.co.uk sounds',
    'librivox': 'site:librivox.org',  # Free audiobooks
    'archive_audio': 'site:archive.org mediatype:audio',
}

# Schema.org structured data queries for audio/podcasts
AUDIO_SCHEMAS = [
    'more:pagemap:audioobject',
    'more:pagemap:audioobject-name',
    'more:pagemap:audioobject-duration',
    'more:pagemap:podcastepisode',
    'more:pagemap:podcastepisode-name',
    'more:pagemap:podcastseries',
    'more:pagemap:podcast',
    'more:pagemap:musicrecording',
    'more:pagemap:audiobook',
    'more:pagemap:mediaobject audio',
]

class AudioSearch:
    """
    Audio/Podcast search operator implementation.
    Routes searches to audio platforms and uses schema-enhanced queries.
    Includes automatic transcription for audio file URLs.
    """
    
    def __init__(self, event_emitter=None, auto_transcribe=True):
        """Initialize audio search with optional event streaming and transcription.
        
        Args:
            event_emitter: Optional event emitter for streaming updates
            auto_transcribe: Whether to automatically transcribe audio URLs
        """
        self.event_emitter = event_emitter
        self.available_engines = self._check_available_engines()
        self.auto_transcribe = auto_transcribe and TRANSCRIPTION_AVAILABLE
        
        if STREAMING_AVAILABLE and event_emitter:
            self.streamer = SearchTypeEventEmitter(event_emitter)
        else:
            self.streamer = None
            
        # Initialize transcription service if available
        if self.auto_transcribe:
            self.transcription_service = AudioTranscriptionService()
            logger.info("Audio transcription service initialized")
    
    def _check_available_engines(self) -> List[str]:
        """Check which audio-supporting engines are available in the system."""
        available = []
        
        # Check ENGINE_CONFIG from brute.py
        try:
            from brute.targeted_searches.brute import ENGINE_CONFIG
            
            for engine_code in AUDIO_ENGINES:
                if engine_code in ENGINE_CONFIG:
                    available.append(engine_code)
                    logger.info(f"Audio engine {engine_code} available")
                else:
                    logger.debug(f"Audio engine {engine_code} not configured")
        except ImportError:
            logger.error("Could not import ENGINE_CONFIG from brute.py")
            # Use fallback engines
            available = ['GO', 'BI', 'BR']
        
        if not available:
            logger.warning("No audio engines available, using fallback engines")
            available = ['GO', 'BI', 'BR']
        
        logger.info(f"Available audio engines: {available}")
        return available
    
    def _build_audio_queries(self, query: str, include_platforms: bool = True, 
                            include_schemas: bool = True) -> List[str]:
        """
        Build comprehensive audio/podcast search queries.
        
        Args:
            query: The search query
            include_platforms: Whether to include platform-specific searches
            include_schemas: Whether to include schema-enhanced searches
            
        Returns:
            List of search queries optimized for audio content
        """
        queries = []
        
        # Base queries
        queries.append(f'podcast {query}')
        queries.append(f'"{query}" podcast')
        queries.append(f'audio {query}')
        queries.append(f'"{query}" audio')
        queries.append(f'audiobook {query}')
        
        # Platform-specific searches
        if include_platforms:
            # Focus on top platforms for efficiency
            top_platforms = ['spotify', 'apple_podcasts', 'youtube', 'soundcloud', 
                           'podbean', 'archive_audio', 'npr', 'bbc']
            for platform_name in top_platforms:
                if platform_name in AUDIO_PLATFORMS:
                    platform_filter = AUDIO_PLATFORMS[platform_name]
                    queries.append(f'{platform_filter} {query}')
        
        # Schema-enhanced searches (Google API only)
        if include_schemas and 'GO' in self.available_engines:
            for schema in AUDIO_SCHEMAS:
                queries.append(f'{schema} {query}')
            
            # Specific audio schema combinations
            queries.extend([
                f'more:pagemap:audioobject-name:"{query}"',
                f'more:pagemap:podcastepisode {query}',
                f'more:pagemap:podcastepisode-name:"{query}"',
                f'more:pagemap:audiobook {query}',
                f'more:pagemap:musicrecording {query}',
            ])
        
        # Audio-specific patterns
        queries.extend([
            f'"podcast episode" {query}',
            f'"listen to" {query}',
            f'"audio recording" {query}',
            f'"podcast about" {query}',
            f'interview {query} podcast',
            f'"episode" {query} audio',
            f'mp3 {query}',
            f'"audio file" {query}',
        ])
        
        # File type searches for downloadable audio
        if 'AR' in self.available_engines:
            queries.extend([
                f'filetype:mp3 {query}',
                f'filetype:m4a {query}',
                f'filetype:ogg {query}',
            ])
        
        return queries
    
    async def search(self, query: str, max_results: int = 200) -> List[Dict[str, Any]]:
        """
        Execute audio/podcast search across available engines.
        
        Args:
            query: The search query (without the audio:/podcast: operator)
            max_results: Maximum results to return
            
        Returns:
            List of search results from audio sources
        """
        # Clean the query
        query = query.strip()
        
        logger.info(f"Starting audio search for: '{query}'")
        logger.info(f"Using engines: {self.available_engines}")
        
        if self.streamer:
            await self.streamer.emit_search_started('audio', query, self.available_engines)
        
        # Build comprehensive audio queries
        audio_queries = self._build_audio_queries(query)
        # Prepend BareSearch music URL row
        bare_row = {'title': f'BareSearch Music: {query}', 'url': bare_music(query), 'source': 'baresearch_music'}
        
        # Import and run brute search with audio queries
        try:
            from brute.targeted_searches.brute import BruteSearchEngine
            
            # Create output file for results
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"results/audio_{timestamp}.json"
            
            all_results = []
            
            # Run searches for each audio query variant (limit to prevent overload)
            for audio_query in audio_queries[:12]:  # Top 12 queries
                logger.info(f"Searching with query: '{audio_query}'")
                
                # Initialize brute search
                searcher = BruteSearchEngine(
                    keyword=audio_query,
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
                    # Tag results with audio search metadata
                    for result in results:
                        result['search_type'] = 'audio'
                        result['audio_query'] = query
                        result['query_variant'] = audio_query
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
            scored_results = self._score_audio_results(unique_results, query)
            
            # Process audio URLs for transcription if enabled
            if self.auto_transcribe:
                scored_results = await self._process_audio_transcriptions(scored_results)
            
            if self.streamer:
                await self.streamer.emit_search_completed('audio', len(scored_results))
            
            logger.info(f"Audio search completed with {len(scored_results)} unique results")
            
            return [bare_row] + scored_results[:max_results-1]
            
        except ImportError as e:
            logger.error(f"Failed to import BruteSearchEngine: {e}")
            return []
        except Exception as e:
            logger.error(f"Audio search failed: {e}")
            return []
    
    def _score_audio_results(self, results: List[Dict], query: str) -> List[Dict]:
        """
        Score and sort audio/podcast results by relevance.
        
        Prioritizes:
        1. Results from known audio/podcast platforms
        2. Results with audio schema markup
        3. Results with audio-related keywords in title/snippet
        4. Audio file types (mp3, m4a, etc.)
        """
        query_lower = query.lower()
        
        def score_result(result):
            score = 0
            url = result.get('url', '').lower()
            title = result.get('title', '').lower()
            snippet = result.get('snippet', '').lower()
            
            # Check if from known audio platform (highest priority)
            top_platforms = ['spotify.com', 'podcasts.apple.com', 'soundcloud.com', 
                           'podbean.com', 'youtube.com', 'iheart.com', 'npr.org',
                           'bbc.co.uk', 'archive.org', 'audible.com']
            for platform in top_platforms:
                if platform in url:
                    score += 50
                    break
            
            # Check for audio schema markup (from query variant)
            if 'query_variant' in result:
                variant = result['query_variant']
                if 'more:pagemap:audioobject' in variant:
                    score += 45
                elif 'more:pagemap:podcastepisode' in variant:
                    score += 45
                elif 'more:pagemap:audiobook' in variant:
                    score += 40
            
            # Audio keywords in title (high value)
            audio_keywords = ['podcast', 'episode', 'audio', 'listen', 'ep.', 'ep ', 
                            'interview', 'audiobook', 'radio', 'show']
            for keyword in audio_keywords:
                if keyword in title:
                    score += 25
                    break
            
            # Query appears in title
            if query_lower in title:
                score += 30
            
            # Audio file extensions in URL
            audio_extensions = ['.mp3', '.m4a', '.ogg', '.wav', '.aac', '.flac']
            for ext in audio_extensions:
                if ext in url:
                    score += 20
                    break
            
            # Audio keywords in snippet
            for keyword in audio_keywords:
                if keyword in snippet:
                    score += 10
                    break
            
            # Query appears in snippet
            if query_lower in snippet:
                score += 15
            
            # Duration indicators (common in audio/podcast results)
            import re
            duration_pattern = r'\b\d{1,3}:\d{2}\b|\b\d{1,2}\s*(min|minute|hour|hr)\b'
            if re.search(duration_pattern, snippet, re.IGNORECASE):
                score += 8
            
            # Episode number indicators
            episode_pattern = r'\bep\.?\s*\d+\b|\bepisode\s*\d+\b|\b#\d+\b'
            if re.search(episode_pattern, snippet, re.IGNORECASE):
                score += 10
            
            # Host/guest indicators
            if any(word in snippet.lower() for word in ['host', 'guest', 'featuring', 'with ']):
                score += 5
            
            return score
        
        # Score all results
        for result in results:
            result['audio_score'] = score_result(result)
        
        # Sort by score (highest first)
        results.sort(key=lambda x: x.get('audio_score', 0), reverse=True)
        
        return results
    
    async def _process_audio_transcriptions(self, results: List[Dict]) -> List[Dict]:
        """
        Process search results and transcribe audio URLs.
        
        Args:
            results: List of search results
            
        Returns:
            Updated results with transcriptions
        """
        if not self.auto_transcribe or not self.transcription_service:
            return results
        
        logger.info("Processing audio URLs for transcription...")
        
        # Detect audio links in results
        audio_results = self.transcription_service.detect_audio_links(results)
        
        if audio_results:
            logger.info(f"Found {len(audio_results)} audio URLs to transcribe")
            
            # Process transcriptions
            processed_results = self.transcription_service.process_search_results(
                results, 
                auto_transcribe=True
            )
            
            # Count successful transcriptions
            transcribed_count = sum(1 for r in processed_results if r.get('has_transcription'))
            if transcribed_count > 0:
                logger.info(f"Successfully transcribed {transcribed_count} audio files")
                
                # Emit transcription event if streaming
                if self.streamer:
                    await self.streamer.emit_event('audio_transcribed', {
                        'count': transcribed_count,
                        'total': len(audio_results)
                    })
            
            return processed_results
        
        return results
    
    def search_sync(self, query: str, max_results: int = 200) -> List[Dict[str, Any]]:
        """Synchronous wrapper for search method."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.search(query, max_results))
        finally:
            loop.close()

def detect_audio_query(query: str) -> bool:
    """
    Detect if a query should be routed to audio/podcast search.
    
    Patterns:
    - audio:query or audio:"query"
    - podcast:query or podcast:"query"
    - audiobook:query
    - podcasts:query
    """
    query_lower = query.lower()
    
    # Check for audio operators
    audio_patterns = [
        'audio:',
        'podcast:',
        'audiobook:',
        'podcasts:',
        'sound:',
        'listen:',
    ]
    
    for pattern in audio_patterns:
        if pattern in query_lower:
            return True
    
    return False

def extract_audio_query(query: str) -> str:
    """Extract the actual search query from an audio search query."""
    # Remove operators
    query = query.strip()
    
    # Remove common operator prefixes (case-insensitive)
    prefixes = [
        'audio:', 'podcast:', 'audiobook:', 'podcasts:', 'sound:', 'listen:',
        'Audio:', 'Podcast:', 'Audiobook:', 'Podcasts:', 'Sound:', 'Listen:'
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

# Main entry point for audio search
async def run_audio_search(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """
    Main entry point for audio/podcast search.
    
    Args:
        query: The full query including audio:/podcast: operator
        event_emitter: Optional event emitter for streaming updates
        
    Returns:
        List of audio search results
    """
    # Extract the actual query
    clean_query = extract_audio_query(query)
    
    # Create audio searcher
    searcher = AudioSearch(event_emitter)
    
    # Run search
    return await searcher.search(clean_query)

def run_audio_search_sync(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """Synchronous wrapper for audio search."""
    try:
        # Check if there's already a running event loop
        loop = asyncio.get_running_loop()
        # We're already in an async context, create a task
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, run_audio_search(query, event_emitter))
            return future.result()
    except RuntimeError:
        # No event loop running, create one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(run_audio_search(query, event_emitter))
        finally:
            loop.close()

def main():
    """Main entry point for audio search - compatible with SearchRouter"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Audio content search')
    parser.add_argument('-q', '--query', required=True, help='Search query')
    args = parser.parse_args()
    
    query = args.query
    clean_query = extract_audio_query(query)
    
    print(f"\n🎵 Audio Search: {clean_query}")
    results = run_audio_search_sync(clean_query)
    
    if results:
        print(f"\nFound {len(results)} audio results:")
        for i, result in enumerate(results[:20], 1):
            print(f"\n{i}. {result.get('title', 'No Title')}")
            print(f"   URL: {result.get('url')}")
            if result.get('snippet'):
                print(f"   {result['snippet'][:200]}...")
    else:
        print("\nNo audio results found.")
    
    return results

if __name__ == "__main__":
    # Test audio search
    import sys
    
    if len(sys.argv) > 1:
        test_query = ' '.join(sys.argv[1:])
    else:
        test_query = "podcast:machine learning"
    
    print(f"Testing audio search with: {test_query}")
    
    if detect_audio_query(test_query):
        print("Audio query detected!")
        clean_query = extract_audio_query(test_query)
        print(f"Extracted query: '{clean_query}'")
        
        results = run_audio_search_sync(test_query)
        
        print(f"\nFound {len(results)} audio results:")
        for i, result in enumerate(results[:10], 1):
            print(f"\n{i}. {result.get('title', 'No title')}")
            print(f"   URL: {result.get('url', 'No URL')}")
            print(f"   Source: {result.get('source', 'Unknown')}")
            print(f"   Audio Score: {result.get('audio_score', 0)}")
            snippet = result.get('snippet', '')
            if snippet:
                print(f"   Snippet: {snippet[:150]}...")
    else:
        print("Not an audio query")