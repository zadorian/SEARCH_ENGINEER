#!/usr/bin/env python3
"""
FileType Search - Specialized filetype document search across multiple search engines with macro operators
Supports aliases like 'document!', 'spreadsheet!', 'file!' and engine-specific optimizations
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Any
import logging
from datetime import datetime
import os
import asyncio
import json
import requests
import concurrent.futures

# Get the correct path to your project's root
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Import search engines from self-contained runners


# Add inurl search module path (use relative path)


# Set up logger first
logger = logging.getLogger(__name__)

# Import AI brain for download phrase generation
try:
    from brain import get_ai_brain, AIRequest, TaskType
    AI_BRAIN_AVAILABLE = True
except ImportError:
    AI_BRAIN_AVAILABLE = False
    logger.warning("AI brain not found, download phrase generation will be disabled")

# Import query expansion and recall optimization
try:
    from query_expansion import QueryExpander
    from recall_optimizer import RecallOptimizer, RecallConfig, RecallMode, FilteringLevel
    RECALL_MODULES_AVAILABLE = True
except ImportError:
    RECALL_MODULES_AVAILABLE = False
    logger.warning("Recall optimization modules not found")
    # Create dummy classes for type hints when modules unavailable
    class RecallConfig:
        """Dummy RecallConfig for when recall_optimizer is unavailable"""
        pass
    class RecallOptimizer:
        """Dummy RecallOptimizer for when recall_optimizer is unavailable"""
        def __init__(self, config=None):
            pass
    class QueryExpander:
        """Dummy QueryExpander for when query_expansion is unavailable"""
        pass

# Import phrase matcher for exact phrase and proximity filtering
try:
    from brute.scraper.phrase_matcher import PhraseMatcher
    PHRASE_MATCHER_AVAILABLE = True
except ImportError:
    PHRASE_MATCHER_AVAILABLE = False
    logger.warning("Phrase matcher not found, exact phrase filtering will be disabled")

# Import event streaming for filtering events
try:
    from brute.infrastructure.base_streamer import SearchTypeEventEmitter
    STREAMING_AVAILABLE = True
except ImportError:
    STREAMING_AVAILABLE = False
    logger.warning("Event streaming not available for filetype search")
    class SearchTypeEventEmitter:
        def __init__(self, search_type=None): pass
        def emit_search_result(self, result, engine=None): pass
        def emit_search_filtered_result(self, result, engine=None): pass
        def emit_engine_status(self, engine, status, results=0): pass
        def start_search(self, query, engines=None): pass
        def complete_search(self, summary=None): pass
        def mark_engine_complete(self, engine, results_count=0, success=True): pass

# Import strict filetype URL validator
try:
    from filetype_url_validator import FiletypeURLValidator
    FILETYPE_VALIDATOR_AVAILABLE = True
except ImportError:
    FILETYPE_VALIDATOR_AVAILABLE = False
    logger.warning("Filetype URL validator not found, strict validation will be disabled")

# Import inurl search functionality
try:
    from master_search import SearchEngines, URLCleaner, DomainChecker
    INURL_AVAILABLE = True
    logger.info("inURL search module loaded successfully")
except ImportError as e:
    INURL_AVAILABLE = False
    logger.warning(f"inURL search module not available: {e}")
    # Create fallback classes
    class SearchEngines:
        def search_wayback(self, query, limit): return []
        def search_common_crawl(self, query, limit): return []
    class URLCleaner:
        @staticmethod
        def clean_url(url): return url
    class DomainChecker:
        @staticmethod
        def check_domain_batch(domains): return {}

# Import from self-contained runner modules with individual error handling
try:
    from brute.engines.google import GoogleSearch
    GOOGLE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import Google search: {e}")
    GOOGLE_AVAILABLE = False

try:
    from brute.engines.bing import BingSearch
    BING_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import Bing search: {e}")
    BING_AVAILABLE = False

try:
    from brute.engines.yandex import YandexSearch
    YANDEX_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import Yandex search: {e}")
    YANDEX_AVAILABLE = False

try:
    from brute.engines.duckduckgo import MaxExactDuckDuckGo as DuckDuckGoSearch
    DUCKDUCKGO_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import DuckDuckGo search: {e}")
    DUCKDUCKGO_AVAILABLE = False

try:
    from brute.engines.yep import YepScraper as YepSearch
    YEP_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import Yep search: {e}")
    YEP_AVAILABLE = False

try:
    from brute.engines.brave import BraveSearch
    BRAVE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import Brave search: {e}")
    BRAVE_AVAILABLE = False

try:
    from archiveorg import ArchiveOrgSearch
    ARCHIVEORG_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import Archive.org search: {e}")
    ARCHIVEORG_AVAILABLE = False

# Import InURL search module for better inurl: searches
try:
    from inurl import InURLSearch
    INURL_SEARCH_AVAILABLE = True
    logger.info("InURL search module loaded - will use for inurl: queries")
except ImportError as e:
    logger.warning(f"Could not import InURL search module: {e}")
    INURL_SEARCH_AVAILABLE = False

# Import Site search module for site: searches
try:
    from brute.infrastructure.site import SiteSearch
    SITE_SEARCH_AVAILABLE = True
    logger.info("Site search module loaded - will use for site: queries")
except ImportError as e:
    logger.warning(f"Could not import Site search module: {e}")
    SITE_SEARCH_AVAILABLE = False

async def generate_download_phrases(filetype_extensions: List[str], language: str = "en") -> List[str]:
    """Generate download phrases for filetypes using AI brain in specified language"""
    if not AI_BRAIN_AVAILABLE:
        return []
    
    try:
        brain = get_ai_brain()
        
        # Map language codes to language names
        lang_names = {
            'en': 'English', 'de': 'German', 'fr': 'French', 'es': 'Spanish', 
            'it': 'Italian', 'pt': 'Portuguese', 'nl': 'Dutch', 'ru': 'Russian',
            'zh': 'Chinese', 'ja': 'Japanese', 'ko': 'Korean', 'ar': 'Arabic'
        }
        language_name = lang_names.get(language, 'English')
        
        # Create extension list for prompt
        ext_list = ', '.join(filetype_extensions[:5])  # Limit to first 5 extensions
        
        prompt = f"""
        Generate 6-8 common download phrases in {language_name} that people use when searching for {ext_list} files.
        
        Include phrases like:
        - "download [filetype]"
        - "free [filetype] download"
        - "[filetype] file download"
        - "get [filetype]"
        
        Return only the phrases in {language_name}, one per line, without numbers or explanations.
        Focus on natural search terms people actually use.
        """
        
        request = AIRequest(
            task_type=TaskType.QUERY_EXPANSION,
            prompt=prompt,
            model_preference="gpt-4.1-nano",
            temperature=0.7
        )
        
        response = await brain.process_request(request)
        if response.error:
            logger.error(f"AI brain download phrase generation error: {response.error}")
            return []
        
        # Parse response to extract phrases
        phrases = [line.strip() for line in response.content.strip().split('\n') if line.strip()]
        return phrases[:8]  # Limit to 8 phrases
        
    except Exception as e:
        logger.error(f"Error generating download phrases: {e}")
        return []

class EnhancedInURLSearcher:
    """Enhanced inURL search with archive support and live/dead link checking"""
    
    def __init__(self):
        if INURL_AVAILABLE:
            self.search_engines = SearchEngines()
            self.url_cleaner = URLCleaner()
            self.domain_checker = DomainChecker()
        else:
            logger.warning("Enhanced inURL search unavailable - falling back to basic functionality")
    
    def search_inurl_filetype(self, base_query: str, extensions: List[str], include_archives: bool = True) -> Dict:
        """Search for URLs containing filetype extensions with archive support"""
        if not INURL_AVAILABLE:
            return {'error': 'inURL search module not available', 'results': []}
        
        all_results = set()
        archive_results = set()
        
        # Build inurl search queries for each extension
        for ext in extensions:
            # Search for URLs containing the extension
            inurl_queries = [
                f"inurl:.{ext}",
                f"inurl:{ext}",
                f'"{base_query}" inurl:.{ext}',
                f'"{base_query}" filetype:{ext}',
                f"{base_query} site:*.{ext}/*"
            ]
            
            for query in inurl_queries:
                try:
                    # Search regular engines
                    google_results = self.search_engines.search_google(query, 50)
                    all_results.update(google_results)
                    
                    # Search Bing if available
                    try:
                        bing_results = self.search_engines.search_bing(query, 50)
                        all_results.update(bing_results)
                    except Exception as e:

                        print(f"[BRUTE] Error: {e}")

                        pass
                    
                    if include_archives:
                        # Search Wayback Machine
                        try:
                            wayback_results = self.search_engines.search_wayback(f"{base_query} {ext}", 100)
                            archive_results.update(wayback_results)
                        except Exception as e:
                            logger.debug(f"Wayback search failed for {query}: {e}")
                        
                        # Search Common Crawl
                        try:
                            cc_results = self.search_engines.search_common_crawl(f"{base_query} {ext}", 100)
                            archive_results.update(cc_results)
                        except Exception as e:
                            logger.debug(f"Common Crawl search failed for {query}: {e}")
                
                except Exception as e:
                    logger.warning(f"Search failed for query '{query}': {e}")
        
        # Clean and filter URLs
        filtered_results = []
        for url in all_results:
            clean_url = self.url_cleaner.clean_url(url)
            # Check if URL actually contains the target extension
            if any(f".{ext}" in clean_url.lower() for ext in extensions):
                filtered_results.append(clean_url)
        
        filtered_archive_results = []
        for url in archive_results:
            clean_url = self.url_cleaner.clean_url(url)
            if any(f".{ext}" in clean_url.lower() for ext in extensions):
                filtered_archive_results.append(clean_url)
        
        # Check live/dead status
        live_results = []
        dead_results = []
        
        all_unique_urls = list(set(filtered_results + filtered_archive_results))
        
        if all_unique_urls:
            logger.info(f"📡 Checking live/dead status of {len(all_unique_urls)} URLs...")
            
            # Check in batches for better performance
            batch_size = 20
            for i in range(0, len(all_unique_urls), batch_size):
                batch = all_unique_urls[i:i + batch_size]
                status_results = self.domain_checker.check_domain_batch(batch)
                
                for url, (is_live, wayback_date) in status_results.items():
                    result_item = {
                        'url': url,
                        'is_live': is_live,
                        'wayback_date': wayback_date,
                        'source': 'wayback' if url in filtered_archive_results else 'live_search',
                        'extensions_found': [ext for ext in extensions if f".{ext}" in url.lower()]
                    }
                    
                    if is_live:
                        live_results.append(result_item)
                    else:
                        dead_results.append(result_item)
                        # Add wayback link for dead URLs
                        if wayback_date:
                            result_item['wayback_url'] = f"https://web.archive.org/web/{wayback_date.replace('-', '')}/{url}"
        
        return {
            'live_results': live_results,
            'dead_results': dead_results,
            'total_live': len(live_results),
            'total_dead': len(dead_results),
            'extensions_searched': extensions,
            'base_query': base_query
        }
    
    def check_single_url_status(self, url: str, timeout: int = 5) -> Tuple[bool, Optional[str]]:
        """Check if a single URL is live and get wayback date if dead"""
        if not url.startswith(('http://', 'https://')):
            url = f"https://{url}"
        
        # Check if URL is live
        try:
            response = requests.get(url, timeout=timeout, allow_redirects=True)
            if response.status_code == 200:
                return True, None
        except Exception as e:

            print(f"[BRUTE] Error: {e}")

            pass
        
        # If dead, check Wayback Machine
        try:
            cdx_url = f"https://web.archive.org/cdx/search/cdx?url={url}&output=json&limit=1"
            response = requests.get(cdx_url, timeout=timeout)
            if response.status_code == 200:
                data = response.json()
                if len(data) > 1:
                    timestamp = data[1][1]
                    wayback_date = datetime.strptime(timestamp, '%Y%m%d%H%M%S').strftime('%Y-%m-%d')
                    return False, wayback_date
        except Exception as e:

            print(f"[BRUTE] Error: {e}")

            pass
        
        return False, None

try:
    from base_search_with_filtering import BaseSearchWithFiltering
    BASE_FILTERING_AVAILABLE = True
except ImportError:
    BASE_FILTERING_AVAILABLE = False
    logger.warning("Base filtering class not available")
    class BaseSearchWithFiltering:
        def __init__(self): 
            self.filtered_results = []
        def add_filtered_result(self, result, reason, filter_type, metadata=None):
            pass

class FileTypeSearcher(BaseSearchWithFiltering, SearchTypeEventEmitter):
    """Specialized filetype document search across multiple search engines with macro operators."""

    # Aliases map user-friendly terms to lists of actual extensions
    # Added compound macros like 'document!', 'spreadsheet!', 'file!', 'media!'
    FILETYPE_ALIASES = {
        'word': ['doc', 'docx', 'odt', 'rtf'],
        'excel': ['xls', 'xlsx', 'ods', 'csv'],
        'powerpoint': ['ppt', 'pptx', 'odp'],
        'document': ['pdf', 'doc', 'docx', 'odt', 'rtf', 'txt', 'pages', 'wpd'],
        'spreadsheet': ['xls', 'xlsx', 'ods', 'csv', 'numbers', 'tsv'],
        'presentation': ['ppt', 'pptx', 'odp', 'key'],
        'text': ['txt', 'rtf', 'log', 'md', 'rst', 'tex', 'json', 'xml', 'yaml', 'yml', 'csv', 'tsv', 'sql', 'ini', 'cfg'],
        'code': ['py', 'js', 'java', 'cpp', 'c', 'cs', 'rb', 'go', 'php', 'swift', 'kt', 'html', 'css', 'sh', 'ts', 'jsx', 'tsx', 'vue', 'scss', 'less', 'sql', 'r', 'scala', 'rust', 'dart', 'lua'],
        'archive': ['zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz', 'cab', 'dmg', 'iso'],
        'image': ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'tiff', 'tif', 'webp', 'ico', 'psd', 'ai', 'eps', 'raw', 'heic'],
        'audio': ['mp3', 'wav', 'aac', 'flac', 'ogg', 'wma', 'm4a', 'opus', 'aiff', 'au', 'ra'],
        'video': ['mp4', 'avi', 'mkv', 'mov', 'wmv', 'flv', 'webm', 'ogv', 'm4v', '3gp', 'mpg', 'mpeg', 'vob', 'ts', 'mts'],
        # NEW: Enhanced media macros
        'media': ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'tiff', 'webp', 'mp3', 'wav', 'aac', 'flac', 'ogg', 'mp4', 'avi', 'mkv', 'mov', 'wmv', 'flv', 'webm'],
        # Single extensions for direct use
        'pdf': ['pdf'],
        'doc': ['doc'],
        'docx': ['docx'],
        'xls': ['xls'],
        'xlsx': ['xlsx'],
        'ppt': ['ppt'],
        'pptx': ['pptx'],
        'txt': ['txt'],
        'csv': ['csv'],
        'json': ['json'],
        'xml': ['xml'],
        'html': ['html'],
        'zip': ['zip'],
        'file': []  # Special: all extensions, handled dynamically
    }

    # Engine-specific operator templates or flags
    # Using placeholders {ext} or {ext_list}
    ENGINE_OPERATORS = {
        'google': '(filetype:{ext} OR ext:{ext})',
        'bing': '(filetype:{ext} OR ext:{ext} OR contains:{ext})',
        'brave': 'ext:{ext}',
        'duckduckgo': 'filetype:{ext}',
        'yandex': 'mime:{ext}',
        'yep': 'filetype:{ext}',
        'archiveorg': {
            'pdf': 'mediatype:texts AND format:"Portable Document Format"',
            'doc': 'mediatype:texts AND format:"Microsoft Word"',
            'docx': 'mediatype:texts AND format:"Microsoft Word 2007"',
            'xls': 'mediatype:texts AND format:"Microsoft Excel"',
            'xlsx': 'mediatype:texts AND format:"Microsoft Excel 2007"',
            'ppt': 'mediatype:texts AND format:"Microsoft Powerpoint"',
            'pptx': 'mediatype:texts AND format:"Microsoft Powerpoint 2007"',
            'txt': 'mediatype:texts AND format:"Text"',
            'zip': 'format:"ZIP"',
            'jpg': 'mediatype:image AND format:"JPEG"',
            'jpeg': 'mediatype:image AND format:"JPEG"',
            'png': 'mediatype:image AND format:"PNG"',
            'mp3': 'mediatype:audio AND format:"MP3"',
            'mp4': 'mediatype:movies AND format:"MPEG4"',
            'default': 'format:{ext}'  # Fallback for unspecified extensions
        }
    }

    def __init__(self, recall_config: Optional[Union[RecallConfig, Any]] = None, enable_exact_phrase_filter: bool = True):
        """Initialize search engines"""
        # Initialize parent classes
        if BASE_FILTERING_AVAILABLE:
            super(BaseSearchWithFiltering, self).__init__()
        else:
            # Initialize filtering manually
            self.filtered_results = []
            self.filter_stats = {'total_filtered': 0, 'by_type': {}}
        
        if STREAMING_AVAILABLE:
            super(SearchTypeEventEmitter, self).__init__("filetype")
            
        self.engines = {}
        
        # Initialize recall optimization
        if RECALL_MODULES_AVAILABLE:
            self.recall_optimizer = RecallOptimizer(recall_config) if recall_config else RecallOptimizer()
            self.query_expander = QueryExpander()
        else:
            self.recall_optimizer = None
            self.query_expander = None
        
        # Initialize phrase matcher for filtering
        self.enable_exact_phrase_filter = enable_exact_phrase_filter
        if PHRASE_MATCHER_AVAILABLE and enable_exact_phrase_filter:
            self.phrase_matcher = PhraseMatcher(max_distance=3)
        else:
            self.phrase_matcher = None
        
        # Initialize strict filetype URL validator
        if FILETYPE_VALIDATOR_AVAILABLE:
            self.url_validator = FiletypeURLValidator()
            logger.info("Strict filetype URL validator initialized")
        else:
            self.url_validator = None
            logger.warning("Filetype URL validator not available")
        
        # Initialize enhanced inURL searcher (old method for backward compatibility)
        if INURL_AVAILABLE:
            self.old_inurl_searcher = EnhancedInURLSearcher()
            logger.info("Legacy inURL searcher initialized")
        else:
            self.old_inurl_searcher = None
            logger.warning("Legacy inURL searcher not available")
            
        # Initialize new modular searchers
        self.inurl_search = InURLSearch() if INURL_SEARCH_AVAILABLE else None
        self.site_search = SiteSearch() if SITE_SEARCH_AVAILABLE else None
        
        if self.inurl_search:
            logger.info("New InURL search module initialized for better inurl: queries")
        if self.site_search:
            logger.info("New Site search module initialized for site: queries")
        
        # Try to initialize each engine based on availability
        if GOOGLE_AVAILABLE:
            try:
                self.engines['google'] = GoogleSearch()
                logger.info("Initialized Google search for filetype search")
            except Exception as e:
                logger.warning(f"Could not initialize Google for filetype search: {e}")
        
        if BING_AVAILABLE:
            try:
                self.engines['bing'] = BingSearch()
                logger.info("Initialized Bing search for filetype search")
            except Exception as e:
                logger.warning(f"Could not initialize Bing for filetype search: {e}")
        
        if YANDEX_AVAILABLE:
            try:
                self.engines['yandex'] = YandexSearch()
                logger.info("Initialized Yandex search for filetype search")
            except Exception as e:
                logger.warning(f"Could not initialize Yandex for filetype search: {e}")
        
        if DUCKDUCKGO_AVAILABLE:
            try:
                self.engines['duckduckgo'] = DuckDuckGoSearch()
                logger.info("Initialized DuckDuckGo search for filetype search")
            except Exception as e:
                logger.warning(f"Could not initialize DuckDuckGo for filetype search: {e}")
        
        if YEP_AVAILABLE:
            try:
                self.engines['yep'] = YepSearch()
                logger.info("Initialized Yep search for filetype search")
            except Exception as e:
                logger.warning(f"Could not initialize Yep for filetype search: {e}")
        
        if BRAVE_AVAILABLE:
            try:
                self.engines['brave'] = BraveSearch()
                logger.info("Initialized Brave search for filetype search")
            except Exception as e:
                logger.warning(f"Could not initialize Brave for filetype search: {e}")
        
        if ARCHIVEORG_AVAILABLE:
            try:
                self.engines['archiveorg'] = ArchiveOrgSearch()
                logger.info("Initialized Archive.org search for filetype search")
            except Exception as e:
                logger.warning(f"Could not initialize Archive.org for filetype search: {e}")

        # Pre-calculate all unique extensions for 'file!' optimization
        self._all_extensions = sorted(list(set(ext for alias_list in self.FILETYPE_ALIASES.values() for ext in alias_list if alias_list)))
        logger.info(f"FileTypeSearcher: Calculated {len(self._all_extensions)} unique extensions for 'file!' mode.")

    def _get_target_extensions(self, filetype_query: str) -> List[str]:
        """Resolve alias, direct extension, or 'file!' query into a list of extensions."""
        query_lower = filetype_query.lower().replace('!', '')  # Remove trailing '!'
        
        # --- 'file!' HANDLING ---
        if query_lower == 'file':
            logger.info("'file!' detected, using all known extensions.")
            return self._all_extensions
        
        # Existing alias/direct extension lookup
        return self.FILETYPE_ALIASES.get(query_lower, [query_lower])  # Return list even for single extension

    def format_query_for_engine(self, base_query: str, extensions: List[str], engine_name: str) -> str:
        """Format the query string for a specific engine based on target extensions."""
        operators = self.ENGINE_OPERATORS.get(engine_name)
        if not operators:
            logger.warning(f"No operator defined for engine: {engine_name}. Using default 'filetype:'.")
            operators = 'filetype:{ext}'  # Default fallback

        # Handle special case for Archive.org with dictionary format
        if isinstance(operators, dict):
            or_parts = []
            for ext in extensions:
                # Look for specific format string for this extension
                if ext in operators:
                    or_parts.append(operators[ext])
                else:
                    # Use default template
                    default_op = operators.get('default', 'format:{ext}')
                    or_parts.append(default_op.format(ext=ext))
            
            final_operator = f"({' OR '.join(or_parts)})" if len(or_parts) > 1 else (or_parts[0] if or_parts else '')
        else:
            # Standard template string
            op_template = operators
            or_parts = [op_template.format(ext=ext) for ext in extensions]
            final_operator = f"({' OR '.join(or_parts)})" if len(or_parts) > 1 else (or_parts[0] if or_parts else '')

        # Combine base query with operator
        clean_base_query = base_query.strip()
        if not clean_base_query:  # If only searching for a filetype
            return final_operator

        # Ensure base query is quoted if it contains spaces and isn't already
        if ' ' in clean_base_query and not (clean_base_query.startswith('"') and clean_base_query.endswith('"')):
            clean_base_query = f'"{clean_base_query}"'

        # Special handling for Archive.org's AND syntax
        if engine_name == 'archiveorg' and ' AND ' in final_operator:
            return f"{clean_base_query} AND {final_operator}"
        else:
            return f"{clean_base_query} {final_operator}"

    async def generate_search_variations(self, base_query: str, extensions: List[str], engine_name: str, language: str = "en", search_round: int = 1) -> List[str]:
        """Generate multiple query variations for broader searching, including inurl:.ext and AI download phrases."""
        variations = []
        clean_base_query = base_query.strip()
        # Quote base query if it contains spaces for combining with operators
        quoted_base = f'"{clean_base_query}"' if ' ' in clean_base_query and not (clean_base_query.startswith('"') and clean_base_query.endswith('"')) else clean_base_query

        # Get recall strategy if available
        if self.recall_optimizer:
            strategy = self.recall_optimizer.get_search_strategy('filetype', round_num=search_round)
        else:
            strategy = {'use_expansion': False, 'special_patterns': []}

        # 1. Primary formatted query using engine-specific filetype operators
        primary_query = self.format_query_for_engine(clean_base_query, extensions, engine_name)
        if primary_query:
            variations.append(primary_query)

        # 2. Add inurl:.ext variations for ALL extensions (enhanced)
        engines_supporting_inurl = ['google', 'bing', 'brave', 'duckduckgo', 'yep']
        if engine_name in engines_supporting_inurl:
            for ext in extensions:
                # Basic check for valid extension format
                if ext and len(ext) < 10 and ext.replace('_', '').replace('-', '').isalnum():
                    inurl_part = f"inurl:.{ext}"  # Construct like inurl:.pdf
                    # Combine with base query if present
                    if clean_base_query:
                        inurl_query = f"{quoted_base} {inurl_part}"
                    else:
                        inurl_query = inurl_part
                    variations.append(inurl_query)
                else:
                    logger.warning(f"Skipping inurl generation for potentially invalid extension: '{ext}'")

        # 3. Add YouTube support for video searches
        video_extensions = {'mp4', 'avi', 'mkv', 'mov', 'wmv', 'flv', 'webm', 'ogv', 'm4v', '3gp', 'mpg', 'mpeg'}
        is_video_search = any(ext in video_extensions for ext in extensions)
        
        if is_video_search and engine_name in ['google', 'bing', 'brave', 'duckduckgo']:
            # Add YouTube-specific searches for video content
            youtube_query = f"{quoted_base} site:youtube.com"
            variations.append(youtube_query)
            
            # Add video-specific terms
            if clean_base_query:
                video_query = f"{quoted_base} video"
                variations.append(video_query)

        # 4. Generate AI download phrases in relevant language
        if AI_BRAIN_AVAILABLE and clean_base_query:
            try:
                download_phrases = await generate_download_phrases(extensions, language)
                for phrase in download_phrases[:3]:  # Limit to top 3 phrases
                    if phrase:
                        # Create query with download phrase
                        download_query = f"{quoted_base} {phrase}"
                        variations.append(download_query)
            except Exception as e:
                logger.warning(f"Failed to generate download phrases: {e}")

        # 5. L3: Brute Force - Broad keyword match (Strict filtering required downstream)
        # Only add these in later rounds or if specifically requested for deep recall
        if search_round >= 2 or (strategy and strategy.get('use_broad_match', False)):
            for ext in extensions:
                # Simple "query pdf" - catches pages that mention the filetype
                # MUST be filtered strictly by URL downstream
                broad_query = f"{quoted_base} {ext}"
                if broad_query not in variations:
                    variations.append(broad_query)
                
                # "query .pdf" - slightly more specific
                dot_query = f"{quoted_base} .{ext}"
                if dot_query not in variations:
                    variations.append(dot_query)

        # Add query expansion if enabled
        if self.query_expander and strategy.get('use_expansion'):
            try:
                # Get expanded queries
                expanded = await self.query_expander.expand_query(clean_base_query, 'all', max_variations=5)
                for exp_query in expanded[:3]:  # Limit to prevent explosion
                    # Combine with filetype operators
                    exp_with_type = self.format_query_for_engine(exp_query, extensions, engine_name)
                    if exp_with_type and exp_with_type not in variations:
                        variations.append(exp_with_type)
            except Exception as e:
                logger.warning(f"Query expansion error: {e}")
        
        # Add special patterns from recall strategy
        if strategy.get('special_patterns'):
            special_patterns = {
                'index_of': [
                    f'"index of" {quoted_base}',
                    f'intitle:"index of" {quoted_base}',
                    f'"parent directory" {quoted_base}'
                ],
                'parent_directory': [
                    f'"parent directory" {quoted_base} -html -htm -php',
                    f'intitle:"index of" "parent directory" {quoted_base}'
                ],
                'file_hosting': [
                    f'{quoted_base} site:dropbox.com',
                    f'{quoted_base} site:drive.google.com',
                    f'{quoted_base} site:mega.nz',
                    f'{quoted_base} site:mediafire.com'
                ],
                'download_sites': [
                    f'{quoted_base} inurl:download',
                    f'{quoted_base} inurl:files',
                    f'{quoted_base} inurl:documents',
                    f'{quoted_base} "click to download"'
                ]
            }
            
            for pattern_type in strategy['special_patterns']:
                if pattern_type in special_patterns:
                    variations.extend(special_patterns[pattern_type][:2])  # Limit per type
        
        # Deduplicate the final list of queries
        final_variations = list(dict.fromkeys(variations))
        logger.debug(f"Generated {len(final_variations)} variations for {engine_name}: {final_variations}")
        return final_variations

    async def _search_with_inurl_module(self, base_query: str, extensions: List[str], max_results: int = 100) -> Tuple[str, List[Dict]]:
        """Use the new InURL module to search for file extensions"""
        if not self.inurl_search:
            return ("inurl_module", [])
        
        all_results = []
        try:
            # Search for each extension using the InURL module
            for ext in extensions:
                results = await self.inurl_search.search_extension_urls(ext, base_query, max_results)
                # Flatten results from all engines
                for engine, urls in results.items():
                    for url in urls:
                        all_results.append({
                            'url': url,
                            'title': f"{base_query} - {ext} file",
                            'snippet': f"Found via InURL module from {engine}",
                            'source': 'inurl_module'
                        })
            
            # Remove duplicates while preserving order
            seen = set()
            unique_results = []
            for result in all_results:
                if result['url'] not in seen:
                    seen.add(result['url'])
                    unique_results.append(result)
            
            logger.info(f"InURL module found {len(unique_results)} unique results for extensions: {extensions}")
            return ("inurl_module", unique_results)
            
        except Exception as e:
            logger.error(f"Error using InURL module: {e}")
            return ("inurl_module", [])
    
    async def _search_with_site_module(self, base_query: str, pattern: str, max_results: int = 100) -> Tuple[str, List[Dict]]:
        """Use the new Site module for site: pattern searches"""
        if not self.site_search:
            return ("site_module", [])
        
        all_results = []
        try:
            results = await self.site_search.search_by_pattern(base_query, pattern)
            # Convert results to expected format
            for engine, urls in results.items():
                for url in urls:
                    all_results.append({
                        'url': url,
                        'title': f"{base_query} - site pattern search",
                        'snippet': f"Found via Site module from {engine} with pattern: {pattern}",
                        'source': 'site_module'
                    })
            
            # Remove duplicates while preserving order
            seen_urls = set()
            unique_results = []
            for result in all_results:
                if result['url'] not in seen_urls:
                    seen_urls.add(result['url'])
                    unique_results.append(result)
            
            logger.info(f"Site module found {len(unique_results)} unique results for pattern: {pattern}")
            return ("site_module", unique_results)
            
        except Exception as e:
            logger.error(f"Error using Site module: {e}")
            return ("site_module", [])
    
    async def search_filetype(self, base_query: str, filetype_query: str, max_results_per_engine: int = 50, enable_url_filtering: bool = None) -> Dict:
        """Search for specific filetypes across all engines."""
        target_extensions = self._get_target_extensions(filetype_query)
        if not target_extensions:
            logger.error(f"Could not resolve filetype query: {filetype_query}")
            return {'error': f"Unknown filetype: {filetype_query}"}

        logger.info(f"Searching for filetypes {target_extensions} related to query: '{base_query}'")
        # Display slightly differently for 'file!'
        if filetype_query.lower() == 'file!':
            logger.info(f"📁 Searching for ALL KNOWN filetypes (query: '{base_query}')")
        else:
            logger.info(f"📁 Searching for filetypes: {', '.join(target_extensions)} (query: '{base_query}')")

        seen_urls = set()
        all_results = []
        filtered_results = []  # Track filtered out results
        stats_by_source = {}
        search_round = 1
        total_rounds = self.recall_optimizer.config.search_rounds if self.recall_optimizer else 1
        
        # Determine URL filtering based on config or parameter
        if enable_url_filtering is None:
            if self.recall_optimizer:
                # Use filtering based on recall mode
                enable_url_filtering = self.recall_optimizer.config.filtering_level != FilteringLevel.NONE
            else:
                enable_url_filtering = True  # Default behavior
        
        # Progressive search rounds
        while search_round <= total_rounds:
            tasks = []
            
            # Create search tasks for each engine
            for engine_name, engine in self.engines.items():
                tasks.append(self._search_engine(engine_name, engine, base_query, target_extensions, 
                                               max_results_per_engine, language="en", search_round=search_round))
        
            # Add InURL module search if available
            if self.inurl_search:
                tasks.append(self._search_with_inurl_module(base_query, target_extensions, max_results_per_engine * 2))
            
            # Add Site module search for extension patterns if available
            if self.site_search and target_extensions:
                # Create site patterns for extensions like site:*.pdf/*
                for ext in target_extensions[:3]:  # Limit to first 3 extensions
                    pattern = f"*.{ext}/*"
                    tasks.append(self._search_with_site_module(base_query, pattern, max_results_per_engine))

            # Gather results
            engine_outputs = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            round_results = 0
            for output in engine_outputs:
                if isinstance(output, Exception):
                    logger.error(f"Search task failed: {output}")
                    continue
                if not isinstance(output, tuple) or len(output) != 2:
                    logger.error(f"Invalid result format from task: {output}")
                    continue

                engine_name, results_list = output
                if not results_list or not isinstance(results_list, list):
                    if engine_name not in stats_by_source:
                        stats_by_source[engine_name] = {'processed_results': 0, 'unique_added': 0, 'matched_filetype': 0}
                    continue

                processed = 0
                unique_added = 0
                matched_filetype = 0
                filtered_out = 0
                for result in results_list:
                    processed += 1
                    url = result.get('url', '').lower()
                    
                    # Score the result if recall optimizer available
                    if self.recall_optimizer:
                        query_terms = base_query.split()
                        result['confidence_score'] = self.recall_optimizer.score_result(
                            result, 'filetype', query_terms
                        )
                    
                    # Check URL for file extensions (if filtering enabled)
                    if enable_url_filtering:
                        # Use strict URL validator if available
                        if self.url_validator:
                            url_matches = self.url_validator.validate_result(result, target_extensions)
                            if not url_matches:
                                filtered_out += 1
                                # Add to filtered results with metadata
                                if BASE_FILTERING_AVAILABLE:
                                    self.add_filtered_result(
                                        result, 
                                        f"URL does not contain valid {', '.join(target_extensions)} file",
                                        'filetype_mismatch',
                                        {'expected_extensions': target_extensions, 'source': engine_name}
                                    )
                                else:
                                    result['filter_reason'] = f"URL does not contain valid {', '.join(target_extensions)} file"
                                    result['filter_type'] = 'filetype_mismatch'
                                    result['expected_extensions'] = target_extensions
                                    result['source'] = engine_name
                                    filtered_results.append(result)
                                
                                # Emit filtered result event for streaming
                                if STREAMING_AVAILABLE and hasattr(self, 'emit_search_filtered_result'):
                                    self.emit_search_filtered_result(result, engine_name)
                                logger.debug(f"Filtered out non-{target_extensions} result: {result.get('url', '')}")
                        else:
                            # Fallback to simple check
                            url_matches = url and any(f".{ext}" in url for ext in target_extensions)
                            if not url_matches:
                                filtered_out += 1
                                if BASE_FILTERING_AVAILABLE:
                                    self.add_filtered_result(
                                        result,
                                        f"URL does not contain {', '.join(target_extensions)} extension",
                                        'filetype_mismatch',
                                        {'expected_extensions': target_extensions, 'source': engine_name}
                                    )
                                else:
                                    result['filter_reason'] = f"URL does not contain {', '.join(target_extensions)} extension"
                                    result['filter_type'] = 'filetype_mismatch'
                                
                                    result['expected_extensions'] = target_extensions
                                    result['source'] = engine_name
                                    filtered_results.append(result)
                                
                                # Emit filtered result event for streaming
                                if STREAMING_AVAILABLE and hasattr(self, 'emit_search_filtered_result'):
                                    self.emit_search_filtered_result(result, engine_name)
                    else:
                        # Without filtering, include all results
                        url_matches = True
                        # But still check if it DOES match for scoring purposes
                        if self.url_validator:
                            actual_match = self.url_validator.validate_url_filetype(result.get('url', ''), target_extensions)
                        else:
                            actual_match = url and any(f".{ext}" in url for ext in target_extensions)
                        if actual_match:
                            matched_filetype += 1
                            # Boost confidence if URL contains extension
                            if 'confidence_score' in result:
                                result['confidence_score'] = min(1.0, result['confidence_score'] + 0.3)

                    if url_matches:
                        # Apply exact phrase filtering if enabled
                        include_result = True
                        if self.enable_exact_phrase_filter and self.phrase_matcher:
                            phrases = self.phrase_matcher.extract_phrases(base_query)
                            if phrases:
                                # Check if result matches exact phrase criteria
                                title = result.get('title', '')
                                snippet = result.get('snippet', '') or result.get('description', '')
                                text_to_check = f"{title} {snippet}".lower()
                                
                                phrase_found = False
                                for phrase in phrases:
                                    # Check for exact match
                                    if phrase.lower() in text_to_check:
                                        phrase_found = True
                                        result['filter_match_type'] = 'exact'
                                        break
                                    # Check for proximity match
                                    proximity_match, positions = self.phrase_matcher.check_proximity(text_to_check, phrase)
                                    if proximity_match:
                                        phrase_found = True
                                        result['filter_match_type'] = 'proximity'
                                        result['filter_match_positions'] = positions
                                        break
                                
                                include_result = phrase_found
                                if not phrase_found:
                                    # Add to filtered results for phrase mismatch
                                    result['filter_reason'] = f"Does not contain exact phrase: '{phrase}'"
                                    result['filter_type'] = 'phrase_mismatch'
                                    result['searched_phrase'] = phrase
                                    result['source'] = engine_name
                                    filtered_results.append(result)
                                    filtered_out += 1
                        
                        if include_result:
                            if enable_url_filtering:
                                matched_filetype += 1
                            if url and url not in seen_urls:
                                seen_urls.add(url)
                                result['source'] = engine_name  # Ensure source is set
                                result['search_round'] = search_round
                                all_results.append(result)
                                unique_added += 1
                                round_results += 1

                # Update stats
                if engine_name not in stats_by_source:
                    stats_by_source[engine_name] = {'processed_results': 0, 'matched_filetype': 0, 'unique_added': 0, 'filtered_out': 0}
                
                stats_by_source[engine_name]['processed_results'] += processed
                stats_by_source[engine_name]['matched_filetype'] += matched_filetype
                stats_by_source[engine_name]['unique_added'] += unique_added
                stats_by_source[engine_name]['filtered_out'] += filtered_out
            
            # Check if we should continue searching
            if self.recall_optimizer:
                if not self.recall_optimizer.should_continue_searching(len(all_results), search_round, 'filetype'):
                    logger.info(f"Stopping at round {search_round} with {len(all_results)} results")
                    break
            
            search_round += 1

        # Final output
        logger.info("\n--- FileType Search Summary ---")
        total_unique = len(all_results)
        logger.info(f"Base Query: {base_query}")
        logger.info(f"FileTypes Searched: {', '.join(target_extensions)}")
        logger.info(f"Total unique matching results: {total_unique}")
        logger.info("\nResults per source:")
        total_filtered = 0
        for source, stats in stats_by_source.items():
            filtered = stats.get('filtered_out', 0)
            total_filtered += filtered
            logger.info(f"  - {source}: Processed {stats['processed_results']}, Matched FileType {stats['matched_filetype']}, Added {stats['unique_added']} unique, Filtered out {filtered}")
        
        if enable_url_filtering and total_filtered > 0:
            logger.info(f"\n🚫 STRICT FILTERING: {total_filtered} results were filtered out for not being actual {', '.join(target_extensions)} files")
        logger.info("--------------------------")

        # Sort results by URL
        all_results.sort(key=lambda x: x.get('url', ''))

        output_data = {
            'base_query': base_query,
            'filetype_query': filetype_query,
            'target_extensions': target_extensions,
            'timestamp': datetime.now().isoformat(),
            'search_type': 'filetype',
            'total_unique_results': total_unique,
            'total_filtered': len(filtered_results),
            'engine_stats': stats_by_source,
            'results': all_results,
            'filtered_results': filtered_results
        }

        # Run enhanced inURL search if available
        if self.inurl_searcher and INURL_AVAILABLE:
            logger.info(f"\n🔍 Running enhanced inURL search with archive support...")
            try:
                inurl_results = self.inurl_searcher.search_inurl_filetype(base_query, target_extensions, include_archives=True)
                
                if 'error' not in inurl_results:
                    # Add inURL results to output
                    output_data['inurl_search'] = inurl_results
                    
                    # Display enhanced results
                    logger.info(f"\n--- Enhanced inURL Search Results ---")
                    logger.info(f"🟢 Live URLs found: {inurl_results['total_live']}")
                    logger.info(f"🔴 Dead URLs found: {inurl_results['total_dead']}")
                    
                    # Show live results
                    if inurl_results['live_results']:
                        logger.info(f"\n🟢 LIVE PAGES:")
                        for i, result in enumerate(inurl_results['live_results'][:10], 1):
                            logger.info(f"  {i}. {result['url']}")
                            logger.info(f"     Extensions: {', '.join(result['extensions_found'])}")
                    
                    # Show dead results with archive links
                    if inurl_results['dead_results']:
                        logger.info(f"🔴 ARCHIVE LINKS (dead pages):")
                        for i, result in enumerate(inurl_results['dead_results'][:10], 1):
                            logger.info(f"  {i}. DEAD: {result['url']}")
                            if result.get('wayback_url'):
                                logger.info(f"     ARCHIVE: {result['wayback_url']}")
                            elif result.get('wayback_date'):
                                logger.info(f"     Last seen: {result['wayback_date']}")
                            logger.info(f"     Extensions: {', '.join(result['extensions_found'])}")
                    
                    logger.info("--------------------------------------")
                else:
                    logger.error(f"⚠️ Enhanced inURL search failed: {inurl_results.get('error', 'Unknown error')}")
            
            except Exception as e:
                logger.error(f"Enhanced inURL search error: {e}")
                logger.error(f"⚠️ Enhanced inURL search failed: {e}")

        self.save_results(output_data)
        return output_data

    async def _search_engine(self, engine_name: str, engine_instance, base_query: str, extensions: List[str], max_results: int, language: str = "en", search_round: int = 1):
        """Run search on a specific engine instance with generated query variations."""
        engine_results_list = []
        try:
            queries_to_run = await self.generate_search_variations(base_query, extensions, engine_name, language, search_round)
            limit_per_query = max(1, max_results // len(queries_to_run)) if queries_to_run else max_results
            logger.info(f"{engine_name.title()}: Running {len(queries_to_run)} query variations.")

            for search_query in queries_to_run:
                partial_results = []
                try:
                    logger.info(f"{engine_name.title()} Query: {search_query}")
                    
                    # Use the search method from our self-contained runners
                    search_method = getattr(engine_instance, 'search', None)
                    if not search_method or not callable(search_method):
                        logger.warning(f"Engine {engine_name} has no suitable search method.")
                        continue
                    
                    partial_results = search_method(search_query, max_results=limit_per_query)
                    if partial_results is None:
                        partial_results = []

                    # Add query used info and source
                    for res in partial_results:
                        res['query_used'] = search_query
                        res['source'] = engine_name
                    
                    engine_results_list.extend(partial_results)
                    logger.info(f"{engine_name.title()}: Found {len(partial_results)} for '{search_query}'")

                except Exception as e:
                    logger.error(f"{engine_name.title()} search error for query '{search_query}': {e}")
                    continue  # Continue with next query variation

            return engine_name, engine_results_list

        except Exception as e:
            logger.error(f"{engine_name.title()} overall search error: {e}")
            return engine_name, []

    def save_results(self, data: Dict):
        """Save filetype search results to a JSON file."""
        results_dir = "search_results"
        os.makedirs(results_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_query = "".join(c if c.isalnum() else "_" for c in data['base_query'])[:30]
        safe_ft = "".join(c if c.isalnum() else "_" for c in data['filetype_query'])[:20]
        filename = f"filetype_search_{safe_ft}_{safe_query}_{timestamp}.json"
        filepath = os.path.join(results_dir, filename)

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"\n💾 Saved filetype results to {filepath}")
        except Exception as e:
            logger.error(f"Error saving filetype results to {filepath}: {e}")


def main():
    """Main entry point for filetype search"""
    import argparse
    
    parser = argparse.ArgumentParser(description='FileType search across multiple engines')
    parser.add_argument('query', nargs='+', help='Search query with filetype (e.g., "annual report pdf!" or "contracts document!")')
    parser.add_argument('-o', '--output', help='Output JSON file')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    # Set up logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Parse query and filetype
    query_parts = args.query
    
    # Find the last word ending with '!' as the filetype query
    filetype_query = None
    base_query_parts = []
    for i, part in enumerate(reversed(query_parts)):
        if part.endswith('!') and filetype_query is None:
            filetype_query = part
            base_query_parts = query_parts[:-(i+1)]
            break

    if filetype_query is None:
        logger.error("Error: Please specify a filetype ending with '!' (e.g., pdf!, docx!, word!, excel!).")
        logger.info("Available aliases:", list(FileTypeSearcher.FILETYPE_ALIASES.keys()))
        return

    base_query = " ".join(base_query_parts)
    
    async def run_search():
        searcher = FileTypeSearcher()
        
        logger.info(f"📁 FileType search for '{base_query}' within '{filetype_query}' files")
        search_output = await searcher.search_filetype(base_query, filetype_query)

        if 'error' in search_output:
            logger.error(f"Error: {search_output['error']}")
            return

        if search_output.get('results'):
            logger.info("\n--- Sample Results ---")
            for i, result in enumerate(search_output['results'][:10], 1):
                logger.info(f"\n{i}. [{result.get('source', 'N/A')}] {result.get('title', 'No Title')}")
                logger.info(f"   🔗 URL: {result.get('url', 'N/A')}")
                logger.info(f"   📝 Query Used: {result.get('query_used', 'N/A')}")
                snippet = result.get('snippet', result.get('description', ''))
                if snippet:
                    snippet = snippet[:200] + '...' if len(snippet) > 200 else snippet
                    logger.info(f"   📄 Snippet: {snippet}")
        else:
            logger.info("No matching results found.")

        # Save to file if specified
        if args.output:
            search_output['results'] = search_output.get('results', [])  # Ensure results key exists
            with open(args.output, 'w') as f:
                json.dump(search_output, f, indent=2)
            print(f"\n💾 Results saved to: {args.output}")

    asyncio.run(run_search())


if __name__ == "__main__":
    main()