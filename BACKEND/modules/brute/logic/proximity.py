

import sys
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Literal, Any
import logging
from datetime import datetime
import os
import asyncio
import json
from urllib.parse import urlparse
import traceback
import inspect
from functools import partial
import requests

# Get the correct path to your project's root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import search engines from self-contained runners
sys.path.insert(0, str(PROJECT_ROOT / 'engines'))

# Import from self-contained runner modules
from exact_phrase_recall_runner_google import GoogleSearch
from exact_phrase_recall_runner_bing import BingSearch
from exact_phrase_recall_runner_yandex import YandexSearch
from exact_phrase_recall_runner_duckduck import MaxExactDuckDuckGo as DuckDuckGoSearch
try:
    from exact_phrase_recall_runner_yep import YepScraper as YepSearch
    YEP_AVAILABLE = True
except ImportError:
    YEP_AVAILABLE = False
    class YepSearch:
        def search(self, *args, **kwargs): return []
from exact_phrase_recall_runner_brave import BraveSearch

# Import additional engines that don't have proximity but can use AI-filled phrases
try:
    from exact_phrase_recall_runner_boardreader import BoardReaderSearch
    BOARDREADER_AVAILABLE = True
except ImportError:
    BOARDREADER_AVAILABLE = False
    class BoardReaderSearch:
        def search(self, *args, **kwargs): return []

try:
    from exact_phrase_recall_runner_exa import ExaSearch
    EXA_AVAILABLE = True
except ImportError:
    EXA_AVAILABLE = False
    class ExaSearch:
        def search(self, *args, **kwargs): return []

try:
    from exact_phrase_recall_runner_gdelt import GDELTSearch
    GDELT_AVAILABLE = True
except ImportError:
    GDELT_AVAILABLE = False
    class GDELTSearch:
        def search(self, *args, **kwargs): return []

try:
    from exact_phrase_recall_runner_grok import GrokSearch
    GROK_AVAILABLE = True
except ImportError:
    GROK_AVAILABLE = False
    class GrokSearch:
        def search(self, *args, **kwargs): return []

try:
    from exact_phrase_recall_runner_publicwww import PublicWWWSearch
    PUBLICWWW_AVAILABLE = True
except ImportError:
    PUBLICWWW_AVAILABLE = False
    class PublicWWWSearch:
        def search(self, *args, **kwargs): return []

try:
    from exact_phrase_recall_runner_socialsearcher import SocialSearcherSearch
    SOCIALSEARCHER_AVAILABLE = True
except ImportError:
    SOCIALSEARCHER_AVAILABLE = False
    class SocialSearcherSearch:
        def search(self, *args, **kwargs): return []

# Set up logger first
logger = logging.getLogger(__name__)

# Import brain for gap filling
try:
    from brain import predict_gap_fillers
    AI_BRAIN_AVAILABLE = True
except ImportError:
    AI_BRAIN_AVAILABLE = False
    logger.warning("Brain module not found, gap filling will be disabled")
    async def predict_gap_fillers(*args, **kwargs):
        return []

# Import filtering functionality
try:
    from brute.scraper.phrase_matcher import PhraseMatcher
    from brute.filtering.core.filter_manager import FilterManager
    FILTERING_AVAILABLE = True
except ImportError:
    FILTERING_AVAILABLE = False
    logger.warning("Filtering modules not available, exact phrase filtering will be disabled")
    class PhraseMatcher:
        def __init__(self, *args, **kwargs): pass
        def extract_phrases(self, text): return []
        def check_exact_match(self, *args, **kwargs): return True
        def check_proximity_match(self, *args, **kwargs): return True
        def matches_phrase_patterns(self, *args, **kwargs): return True
    class FilterManager:
        def __init__(self, *args, **kwargs): pass

# Import streaming functionality
try:
    from brute.infrastructure.base_streamer import SearchTypeEventEmitter
    STREAMING_AVAILABLE = True
except ImportError:
    STREAMING_AVAILABLE = False
    logger.warning("Streaming module not available, event streaming will be disabled")
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

# Import query expansion and recall optimization
try:
    from query_expansion import QueryExpander
    from recall_optimizer import RecallOptimizer, RecallConfig, RecallMode, FilteringLevel
    RECALL_MODULES_AVAILABLE = True
except ImportError:
    RECALL_MODULES_AVAILABLE = False
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
    logger.warning("Recall optimization modules not found")

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

# Import Archive.org implementation
try:
    sys.path.insert(0, str(PROJECT_ROOT))
    from archiveorg import ArchiveOrgSearch as ArchiveOrgSearchBase
    ARCHIVE_AVAILABLE = True
except ImportError:
    ARCHIVE_AVAILABLE = False
    logger.warning("Archive.org module not found, proximity search will be limited")
    class ArchiveOrgSearchBase:
        def search(self, *args, **kwargs): return []

# Archive.org with enhanced proximity support
class ArchiveOrgSearch:
    """Archive.org search with full-text proximity using Lucene ~N operator"""
    def __init__(self):
        self.base = ArchiveOrgSearchBase() if ARCHIVE_AVAILABLE else None
        
    def search(self, query, max_results=10):
        """Search using Archive.org\'s proximity support"""
        if not self.base:
            return []
        
        # Convert our proximity format to Archive.org\'s Lucene syntax
        # Archive.org uses "term1 term2"~N for proximity
        if ' * ' in query:
            # Simple wildcard - Archive.org supports this directly
            return self.base.search(query, max_results)
        
        # Check if it\'s already in Lucene proximity format
        if '~' in query and query.count('"') >= 2:
            # Already formatted for Archive.org proximity
            return self.base.search(query, max_results)
        
        # Try to extract terms for proximity formatting
        import re
        # Look for patterns like: "term1" "term2" or term1 term2
        terms = re.findall(r'"([^"]+)"|([^\s"]+)', query)
        terms = [t[0] or t[1] for t in terms if t[0] or t[1]]
        
        if len(terms) >= 2:
            # Default to proximity of 10 words if not specified
            proximity_query = f'\"{" ".join(terms)}\"~10'
            results = self.base.search(proximity_query, max_results)
            if results:
                return results
        
        # Fallback to regular search
        return self.base.search(query, max_results)
    
    async def search_async(self, query, max_results=10):
        """Async wrapper for proximity search"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.search, query, max_results)

class NewsAPISearch:
    """NewsAPI for phrase searches"""
    def __init__(self, api_key='YOUR_NEWSAPI_KEY'):
        self.api_key = api_key

    def search(self, query, max_results=10):
        url = "https://newsapi.org/v2/everything"
        params = {'q': query, 'apiKey': self.api_key, 'pageSize': max_results}
        response = requests.get(url, params=params)
        if response.status_code == 200:
            articles = response.json().get('articles', [])
            return [{'url': a['url'], 'title': a['title'], 'snippet': a['description']} for a in articles]
        return []

class AlephSearch:
    """Aleph OCRP for proximity/wildcards"""
    def search(self, query, max_results=10):
        # Assume API endpoint; use query_string syntax
        url = "https://aleph.occrp.org/api/2/entities"  # May require auth
        params = {'filter:q': query, 'limit': max_results}
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json().get('results', [])
            return [{'url': d.get('links', {}).get('self', ''), 'title': d['name'], 'snippet': d.get('snippet', '')} for d in data]
        return []

class XSearch:
    """X (Twitter) search using Grok tools"""
    async def search_async(self, query, max_results=10):
        # Use x_keyword_search for exact/phrase
        from xai_tools import x_keyword_search  # Assume tool access
        results = await x_keyword_search(query=query, limit=max_results)
        return [{'url': r['link'], 'title': r['user'], 'snippet': r['text']} for r in results]

# Define proximity types
ProximityMode = Literal["at_least", "exactly", "fewer_than", "wildcard"]

class ProximitySyntaxError(ValueError):
    pass

class ProximitySearcher(SearchTypeEventEmitter):
    """
    Standardized Searcher class for proximity searches.
    This class is designed to be imported and used by main.py.
    Includes real-time event streaming for web interface integration.
    """
    PROXIMITY_REGEX = re.compile(r'^(.*)\s+(\d+<|<s*\d+|~\d+|\*\s*(?:\d+)?)\s+(.*)$', re.IGNORECASE)
    OPERATOR_REGEX = re.compile(r'(\d+<)|(<\s*(\d+))|(~(\d+))|(\*\s*(?:(\d+))?)')

    def __init__(self, additional_args: List[str] = None, recall_config: Optional[Union[RecallConfig, Any]] = None, enable_streaming: bool = False, event_handler: Optional[callable] = None):
        # Initialize streaming first
        super().__init__(search_type="proximity")
        
        self.additional_args = additional_args or []
        self.engines = self._initialize_engines()
        
        # Set up streaming if requested
        if enable_streaming and event_handler:
            self.enable_streaming(event_handler)
        
        # Initialize recall optimization
        if RECALL_MODULES_AVAILABLE:
            self.recall_optimizer = RecallOptimizer(recall_config) if recall_config else RecallOptimizer()
            self.query_expander = QueryExpander()
        else:
            self.recall_optimizer = None
            self.query_expander = None
            
        # Initialize filtering components
        if FILTERING_AVAILABLE:
            self.phrase_matcher = PhraseMatcher(max_distance=3)
            self.filter_manager = FilterManager()
            self.enable_exact_phrase_filter = True
        else:
            self.phrase_matcher = None
            self.filter_manager = None
            self.enable_exact_phrase_filter = False
            
        # Track filtered results
        self.filtered_results = []
        self.filtered_count = 0
        
        logger.info(f"ProximitySearcher initialized with streaming {'enabled' if enable_streaming else 'disabled'}")

    def _filter_results(self, results: List[Dict], query: str) -> Tuple[List[Dict], List[Dict]]:
        """
        Filter results based on exact phrase matching and proximity validation.
        Returns tuple of (passed_results, filtered_results)
        """
        if not self.enable_exact_phrase_filter or not self.phrase_matcher:
            return results, []
            
        passed_results = []
        filtered_results = []
        
        # Extract phrases from the original query
        phrases = self.phrase_matcher.extract_phrases(query)
        
        if not phrases:
            return results, []
        
        for result in results:
            title = result.get('title', '')
            snippet = result.get('snippet', '')
            combined_text = f"{title} {snippet}".lower()
            
            # Check for exact phrase matches
            phrase_match = False
            for phrase in phrases:
                if self.phrase_matcher.matches_phrase_patterns(combined_text, phrase):
                    phrase_match = True
                    break
            
            if phrase_match:
                passed_results.append(result)
            else:
                # Add filter reason
                result['filter_reason'] = 'proximity_phrase_mismatch'
                result['filter_details'] = {
                    'expected_phrases': phrases,
                    'title': title,
                    'snippet': snippet[:200] + '...' if len(snippet) > 200 else snippet
                }
                filtered_results.append(result)
        
        return passed_results, filtered_results

    def _initialize_engines(self) -> Dict:
        """Initializes all available search engines."""
        engines = {}
        engine_classes = {
            'google': GoogleSearch, 'bing': BingSearch, 'yandex': YandexSearch,
            'duckduckgo': DuckDuckGoSearch, 'brave': BraveSearch,
            'archive': ArchiveOrgSearch, 'newsapi': NewsAPISearch, 'aleph': AlephSearch, 'x': XSearch,
            'yep': YepSearch if YEP_AVAILABLE else None,
            'boardreader': BoardReaderSearch if BOARDREADER_AVAILABLE else None,
            'exa': ExaSearch if EXA_AVAILABLE else None,
            'gdelt': GDELTSearch if GDELT_AVAILABLE else None,
            'grok': GrokSearch if GROK_AVAILABLE else None,
            'publicwww': PublicWWWSearch if PUBLICWWW_AVAILABLE else None,
            'socialsearcher': SocialSearcherSearch if SOCIALSEARCHER_AVAILABLE else None,
        }

        for name, EClass in engine_classes.items():
            if EClass:
                try:
                    engines[name] = EClass()
                except Exception as e:
                    logger.warning(f"Could not initialize {name}: {e}")
        return engines

    def parse_query(self, query: str) -> Tuple[str, str, int, ProximityMode]:
        """Parse proximity or wildcard operators"""
        # First, check for wildcards like "term1 *3 term2"
        operators = self.parse_wildcards(query)
        if operators:
            parts = query.replace('"', '').split()
            for i, count in operators.items():
                if i > 0 and i < len(parts) - 1:
                    term1 = parts[i-1].strip()
                    term2 = parts[i+1].strip()
                    return term1, term2, count, 'exactly'  # Treat as exactly N words

        # Fall back to proximity regex
        match = self.PROXIMITY_REGEX.match(query.strip())
        if not match:
            raise ProximitySyntaxError("Invalid query. Use 'term1 OP term2' or 'term1 *N term2'.")

        term1 = match.group(1).strip().strip('"')
        operator_part = match.group(2).strip()
        term2 = match.group(3).strip().strip('"')

        op_match = self.OPERATOR_REGEX.match(operator_part)
        if not op_match:
            raise ProximitySyntaxError(f"Invalid operator: {operator_part}")

        if op_match.group(1):  # N<
            distance = int(op_match.group(1)[:-1])
            mode = "at_least"
        elif op_match.group(2):  # <N
            distance = int(op_match.group(3))
            mode = "fewer_than"
        elif op_match.group(4):  # ~N
            distance = int(op_match.group(5))
            mode = "exactly"
        elif op_match.group(6):  # *N or *
            mode = "wildcard"
            distance = int(op_match.group(7)) if op_match.group(7) else 1
        else:
            raise ProximitySyntaxError(f"Unknown operator: {operator_part}")

        if distance <= 0:
            raise ProximitySyntaxError("Distance must be positive.")

        logger.info(f"Parsed query: term1='{term1}', term2='{term2}', distance={distance}, mode='{mode}'")
        return term1, term2, distance, mode

    def parse_wildcards(self, query: str) -> Dict[int, int]:
        """Parse * operators from wildcards.py"""
        query = query.replace('"', '')
        parts = query.split()
        operators = {}
        for i, part in enumerate(parts):
            if part.startswith("*"):
                if part.replace("*", "").isdigit():
                    operators[i] = int(part.replace("*", ""))
                else:
                    operators[i] = len(part)
        return operators

    async def predict_gap_fillers(self, term1: str, term2: str, gap_size: int) -> List[str]:
        """AI brain gap prediction for proximity search"""
        if not AI_BRAIN_AVAILABLE:
            return []
        
        try:
            return await predict_gap_fillers(term1, term2, gap_size)
        except Exception as e:
            logger.error(f"AI brain gap filling error: {e}")
            return []

    def _count_words_between_in_snippet(self, snippet: str, term1: str, term2: str, bidirectional: bool = True) -> Optional[int]:
        """Count words between terms in snippet, checking both directions for maximum recall"""
        if not snippet or not term1 or not term2:
            return None

        term1_escaped = re.escape(term1)
        term2_escaped = re.escape(term2)
        
        min_distance = None
        
        # Forward direction: term1 ... term2
        match1 = re.search(rf'\b{term1_escaped}\b', snippet, re.IGNORECASE)
        if match1:
            end_index_term1 = match1.end()
            match2 = re.search(rf'\b{term2_escaped}\b', snippet[end_index_term1:], re.IGNORECASE)
            if match2:
                start_index_term2 = end_index_term1 + match2.start()
                text_between = snippet[end_index_term1 : start_index_term2]
                words = text_between.split()
                forward_distance = len(words)
                min_distance = forward_distance
        
        # Reverse direction: term2 ... term1
        if bidirectional:
            match2_rev = re.search(rf'\b{term2_escaped}\b', snippet, re.IGNORECASE)
            if match2_rev:
                end_index_term2 = match2_rev.end()
                match1_rev = re.search(rf'\b{term1_escaped}\b', snippet[end_index_term2:], re.IGNORECASE)
                if match1_rev:
                    start_index_term1 = end_index_term2 + match1_rev.start()
                    text_between_rev = snippet[end_index_term2 : start_index_term1]
                    words_rev = text_between_rev.split()
                    reverse_distance = len(words_rev)
                    if min_distance is None or reverse_distance < min_distance:
                        min_distance = reverse_distance
        
        return min_distance

    async def _generate_search_variations(self, term1: str, term2: str, distance: int, mode: ProximityMode, bidirectional: bool = True, round_num: int = 1) -> Dict[str, List[Tuple[str, str]]]:
        variations = {k: [] for k in self.engines.keys()}
        gemini_predictions = []
        
        # Get recall strategy if available
        if self.recall_optimizer:
            strategy = self.recall_optimizer.get_search_strategy('proximity', round_num=round_num)
        else:
            strategy = {'use_expansion': False, 'use_wildcards': False, 'semantic_proximity': False}

        num_words_to_predict = []
        if mode == "exactly" or mode == "wildcard":
            num_words_to_predict.append(distance)
            # Also try adjacent distances for better recall
            if distance > 0:
                num_words_to_predict.append(distance - 1)
            num_words_to_predict.append(distance + 1)
            gemini_tag_base = "gemini_exact"
        elif mode == "fewer_than":
            # Try ALL distances from 0 to distance-1 for maximum recall
            num_words_to_predict.extend(range(0, distance))
            gemini_tag_base = "gemini_less_than"
        elif mode == "at_least":
            # Progressive expansion: N, N+1, N+2, N+3, N+5, N+10
            num_words_to_predict.extend([distance, distance + 1, distance + 2, distance + 3, distance + 5, distance + 10])
            gemini_tag_base = "gemini_at_least"

        if AI_BRAIN_AVAILABLE and num_words_to_predict:
            # Generate predictions for both directions
            predict_tasks = []
            for num in set(num_words_to_predict):
                if num > 0:
                    predict_tasks.append(self.predict_gap_fillers(term1, term2, num))
                    if bidirectional:
                        predict_tasks.append(self.predict_gap_fillers(term2, term1, num))
            results = await asyncio.gather(*predict_tasks)
            for result in results:
                gemini_predictions.extend(result)

        quoted_term1 = f'"{term1}"'
        quoted_term2 = f'"{term2}"'

        def add_variation(engine, query, tag, direction="forward"):
            if query and engine in variations:
                full_tag = f"{tag}_{direction}" if bidirectional else tag
                variations[engine].append((query, full_tag))

        # Gemini phrases on all engines - both directions
        for phrase in gemini_predictions:
            # Forward direction
            full_phrase = f'"{term1} {phrase} {term2}"'
            gemini_tag = f"{gemini_tag_base}_{len(phrase.split())}"
            for eng in variations:
                add_variation(eng, full_phrase, gemini_tag, "forward")
            
            # Reverse direction if bidirectional
            if bidirectional:
                full_phrase_rev = f'"{term2} {phrase} {term1}"'
                for eng in variations:
                    add_variation(eng, full_phrase_rev, gemini_tag, "reverse")

        # Native ops with BIDIRECTIONAL support
        if mode == "exactly" or mode == "wildcard":
            # Google AROUND - both directions
            add_variation('google', f'{quoted_term1} AROUND({distance}) {quoted_term2}', 'google_around_N', 'forward')
            if bidirectional:
                add_variation('google', f'{quoted_term2} AROUND({distance}) {quoted_term1}', 'google_around_N', 'reverse')
            if distance > 0:
                add_variation('google', f'{quoted_term1} AROUND({distance - 1}) {quoted_term2}', 'google_around_N_minus_1', 'forward')
                if bidirectional:
                    add_variation('google', f'{quoted_term2} AROUND({distance - 1}) {quoted_term1}', 'google_around_N_minus_1', 'reverse')
            # Try N+1 for better recall
            add_variation('google', f'{quoted_term1} AROUND({distance + 1}) {quoted_term2}', 'google_around_N_plus_1', 'forward')
            if bidirectional:
                add_variation('google', f'{quoted_term2} AROUND({distance + 1}) {quoted_term1}', 'google_around_N_plus_1', 'reverse')
            
            # Google additional operators for MAXIMUM RECALL
            add_variation('google', f'intext:{quoted_term1} intext:{quoted_term2}', 'google_intext', 'both')
            add_variation('google', f'allintext:{term1} {term2}', 'google_allintext', 'both')
            add_variation('google', f'intitle:{quoted_term1} intitle:{quoted_term2}', 'google_intitle', 'both')
            add_variation('google', f'allintitle:{term1} {term2}', 'google_allintitle', 'both')
            # Google wildcards between terms
            wildcard_phrase = ' * '.join([term1] + ['*'] * min(distance, 5) + [term2])
            add_variation('google', f'"{wildcard_phrase}"', 'google_wildcard', 'forward')
            if bidirectional:
                wildcard_phrase_rev = ' * '.join([term2] + ['*'] * min(distance, 5) + [term1])
                add_variation('google', f'"{wildcard_phrase_rev}"', 'google_wildcard', 'reverse')
                
            # Bing near - both directions
            add_variation('bing', f'{quoted_term1} near:{distance} {quoted_term2}', 'bing_near_N', 'forward')
            if bidirectional:
                add_variation('bing', f'{quoted_term2} near:{distance} {quoted_term1}', 'bing_near_N', 'reverse')
            if distance > 0:
                add_variation('bing', f'{quoted_term1} near:{distance-1} {quoted_term2}', 'bing_near_N_minus_1', 'forward')
                if bidirectional:
                    add_variation('bing', f'{quoted_term2} near:{distance-1} {quoted_term1}', 'bing_near_N_minus_1', 'reverse')
            
            # Bing additional operators for MAXIMUM RECALL
            add_variation('bing', f'contains:{quoted_term1} contains:{quoted_term2}', 'bing_contains', 'both')
            add_variation('bing', f'intitle:{quoted_term1} intitle:{quoted_term2}', 'bing_intitle', 'both')
            add_variation('bing', f'inbody:{quoted_term1} inbody:{quoted_term2}', 'bing_inbody', 'both')
                    
            # Yandex / operator - both directions
            add_variation('yandex', f'{quoted_term1} /{distance} {quoted_term2}', 'yandex_slash_N', 'forward')
            if bidirectional:
                add_variation('yandex', f'{quoted_term2} /{distance} {quoted_term1}', 'yandex_slash_N', 'reverse')
            if distance > 0:
                add_variation('yandex', f'{quoted_term1} /{distance - 1} {quoted_term2}', 'yandex_slash_N_minus_1', 'forward')
                if bidirectional:
                    add_variation('yandex', f'{quoted_term2} /{distance - 1} {quoted_term1}', 'yandex_slash_N_minus_1', 'reverse')
            # Yandex << operator for unordered proximity
            add_variation('yandex', f'{quoted_term1} <<{distance} {quoted_term2}', 'yandex_unordered_N', 'both')
            
            # Yandex additional operators for MAXIMUM RECALL
            add_variation('yandex', f'title:{quoted_term1} title:{quoted_term2}', 'yandex_title', 'both')
            add_variation('yandex', f'intext:{quoted_term1} intext:{quoted_term2}', 'yandex_intext', 'both')
            
            # Aleph and Archive.org - Lucene syntax handles both directions inherently
            add_variation('aleph', f'"{term1} {term2}"~{distance}', 'aleph_prox_N', 'both')
            if distance > 0:
                add_variation('aleph', f'"{term1} {term2}"~{distance - 1}', 'aleph_prox_N_minus_1', 'both')
            add_variation('archive', f'"{term1} {term2}"~{distance}', 'archive_prox_N', 'both')
            if distance > 0:
                add_variation('archive', f'"{term1} {term2}"~{distance - 1}', 'archive_prox_N_minus_1', 'both')
                
            # Enhanced fallbacks for engines without proximity
            add_variation('x', f'"{term1}" "{term2}"', 'x_broad', 'forward')
            if bidirectional:
                add_variation('x', f'"{term2}" "{term1}"', 'x_broad', 'reverse')
                
            # DuckDuckGo with enhanced operators
            add_variation('duckduckgo', f'{quoted_term1} {quoted_term2}', 'duckduckgo_broad', 'forward')
            add_variation('duckduckgo', f'intitle:{quoted_term1} intitle:{quoted_term2}', 'duckduckgo_intitle', 'both')
            add_variation('duckduckgo', f'intext:{quoted_term1} intext:{quoted_term2}', 'duckduckgo_intext', 'both')
            if bidirectional:
                add_variation('duckduckgo', f'{quoted_term2} {quoted_term1}', 'duckduckgo_broad', 'reverse')
                
            # Yep with enhanced search
            add_variation('yep', f'{quoted_term1} {quoted_term2}', 'yep_broad', 'forward')
            add_variation('yep', f'intitle:{quoted_term1} {quoted_term2}', 'yep_intitle', 'forward')
            if bidirectional:
                add_variation('yep', f'{quoted_term2} {quoted_term1}', 'yep_broad', 'reverse')
                
            # NewsAPI with variations
            add_variation('newsapi', f'{quoted_term1} {quoted_term2}', 'newsapi_broad', 'forward')
            if bidirectional:
                add_variation('newsapi', f'{quoted_term2} {quoted_term1}', 'newsapi_broad', 'reverse')

        if mode == "at_least":
            # Progressive distance expansion: N, N+1, N+2, N+3, N+5, N+10
            distances_to_try = [distance]
            if distance > 0:
                distances_to_try.append(distance - 1)
            distances_to_try.extend([distance + 1, distance + 2, distance + 3, distance + 5, distance + 10])
            
            for d in distances_to_try:
                if d >= 0:  # Ensure non-negative
                    tag_suffix = f"_plus_{d - distance}" if d > distance else (f"_minus_{distance - d}" if d < distance else "")
                    
                    # Google AROUND with progressive distances
                    add_variation('google', f'{quoted_term1} AROUND({d}) {quoted_term2}', f'google_around_N{tag_suffix}', 'forward')
                    if bidirectional:
                        add_variation('google', f'{quoted_term2} AROUND({d}) {quoted_term1}', f'google_around_N{tag_suffix}', 'reverse')
                        
                    # Bing near with progressive distances
                    add_variation('bing', f'{quoted_term1} near:{d} {quoted_term2}', f'bing_near_N{tag_suffix}', 'forward')
                    if bidirectional:
                        add_variation('bing', f'{quoted_term2} near:{d} {quoted_term1}', f'bing_near_N{tag_suffix}', 'reverse')
                        
                    # Yandex with progressive distances
                    add_variation('yandex', f'{quoted_term1} /{d} {quoted_term2}', f'yandex_slash_N{tag_suffix}', 'forward')
                    if bidirectional:
                        add_variation('yandex', f'{quoted_term2} /{d} {quoted_term1}', f'yandex_slash_N{tag_suffix}', 'reverse')
                    add_variation('yandex', f'{quoted_term1} <<{d} {quoted_term2}', f'yandex_unordered_N{tag_suffix}', 'both')
                    
                    # Aleph and Archive with progressive distances
                    add_variation('aleph', f'"{term1} {term2}"~{d}', f'aleph_prox_N{tag_suffix}', 'both')
                    add_variation('archive', f'"{term1} {term2}"~{d}', f'archive_prox_N{tag_suffix}', 'both')
            
            # Broad phrase fallbacks for all engines
            for eng in variations:
                add_variation(eng, f'{quoted_term1} {quoted_term2}', f'{eng}_broad_phrase', 'forward')
                if bidirectional:
                    add_variation(eng, f'{quoted_term2} {quoted_term1}', f'{eng}_broad_phrase', 'reverse')

        if mode == "fewer_than":
            # Try ALL distances from 0 to distance-1 for maximum recall
            for d in range(0, distance):
                # Google AROUND
                add_variation('google', f'{quoted_term1} AROUND({d}) {quoted_term2}', f'google_around_{d}', 'forward')
                if bidirectional:
                    add_variation('google', f'{quoted_term2} AROUND({d}) {quoted_term1}', f'google_around_{d}', 'reverse')
                    
                # Bing near
                add_variation('bing', f'{quoted_term1} near:{d} {quoted_term2}', f'bing_near_{d}', 'forward')
                if bidirectional:
                    add_variation('bing', f'{quoted_term2} near:{d} {quoted_term1}', f'bing_near_{d}', 'reverse')
                    
                # Yandex
                add_variation('yandex', f'{quoted_term1} /{d} {quoted_term2}', f'yandex_slash_{d}', 'forward')
                if bidirectional:
                    add_variation('yandex', f'{quoted_term2} /{d} {quoted_term1}', f'yandex_slash_{d}', 'reverse')
                    
                # Aleph and Archive
                add_variation('aleph', f'"{term1} {term2}"~{d}', f'aleph_prox_{d}', 'both')
                add_variation('archive', f'"{term1} {term2}"~{d}', f'archive_prox_{d}', 'both')
            
            # Special case for adjacent terms (0 distance)
            adjacent_phrase = f'"{term1} {term2}"'
            adjacent_phrase_rev = f'"{term2} {term1}"'
            for eng in variations:
                add_variation(eng, adjacent_phrase, f'{eng}_adjacent', 'forward')
                if bidirectional:
                    add_variation(eng, adjacent_phrase_rev, f'{eng}_adjacent', 'reverse')

        # MAXIMUM RECALL: Add case variations
        term1_upper = term1.upper()
        term2_upper = term2.upper()
        term1_title = term1.title()
        term2_title = term2.title()
        
        # Add case variations for all engines
        for eng in variations:
            # UPPERCASE variations
            add_variation(eng, f'"{term1_upper} {term2_upper}"', f'{eng}_uppercase', 'forward')
            if bidirectional:
                add_variation(eng, f'"{term2_upper} {term1_upper}"', f'{eng}_uppercase', 'reverse')
            
            # Title Case variations
            add_variation(eng, f'"{term1_title} {term2_title}"', f'{eng}_titlecase', 'forward')
            if bidirectional:
                add_variation(eng, f'"{term2_title} {term1_title}"', f'{eng}_titlecase', 'reverse')
                
        # MAXIMUM RECALL: Individual term searches for post-filtering
        for eng in variations:
            # Search for just term1
            add_variation(eng, f'"{term1}"', f'{eng}_term1_only', 'single')
            # Search for just term2
            add_variation(eng, f'"{term2}"', f'{eng}_term2_only', 'single')
            # Both terms without quotes (very broad)
            add_variation(eng, f'{term1} {term2}', f'{eng}_unquoted', 'forward')
            if bidirectional:
                add_variation(eng, f'{term2} {term1}', f'{eng}_unquoted', 'reverse')
                
        # MAXIMUM RECALL: Punctuation variations
        for eng in variations:
            # Hyphenated
            add_variation(eng, f'"{term1}-{term2}"', f'{eng}_hyphenated', 'forward')
            if bidirectional:
                add_variation(eng, f'"{term2}-{term1}"', f'{eng}_hyphenated', 'reverse')
            # Underscore
            add_variation(eng, f'"{term1}_{term2}"', f'{eng}_underscore', 'forward')
            if bidirectional:
                add_variation(eng, f'"{term2}_{term1}"', f'{eng}_underscore', 'reverse')
                
        # MAXIMUM RECALL: Wildcard-specific handling for engines that support it
        if mode == "wildcard":
            # Google supports * wildcard
            if 'google' in variations:
                for i in range(1, min(distance + 1, 10)):  # Up to 10 wildcards
                    wildcard_query = f'"{term1} {" * " * i} {term2}"'
                    add_variation('google', wildcard_query, f'google_wildcard_{i}', 'forward')
                    if bidirectional:
                        wildcard_query_rev = f'"{term2} {" * " * i} {term1}"'
                        add_variation('google', wildcard_query_rev, f'google_wildcard_{i}', 'reverse')
        
        # Add query expansion if enabled
        if self.query_expander and strategy.get('use_expansion'):
            try:
                # Get synonyms for each term
                term1_variations = await self.query_expander.expand_query(term1, 'synonyms', max_variations=3)
                term2_variations = await self.query_expander.expand_query(term2, 'synonyms', max_variations=3)
                
                # Create proximity searches with synonym combinations
                for t1_var in term1_variations[:2]:  # Limit to prevent explosion
                    for t2_var in term2_variations[:2]:
                        if t1_var != term1 or t2_var != term2:  # Skip original
                            # Add basic proximity for key engines
                            synonym_tag = 'synonym_proximity'
                            
                            # Google
                            if 'google' in variations and mode in ["exactly", "wildcard"]:
                                add_variation('google', f'"{t1_var}" AROUND({distance}) "{t2_var}"', 
                                            f'google_{synonym_tag}', 'forward')
                            
                            # Bing
                            if 'bing' in variations and mode in ["exactly", "wildcard"]:
                                add_variation('bing', f'"{t1_var}" near:{distance} "{t2_var}"', 
                                            f'bing_{synonym_tag}', 'forward')
                            
                            # Fallback for other engines
                            for eng in variations:
                                if eng not in ['google', 'bing', 'yandex']:
                                    add_variation(eng, f'"{t1_var}" "{t2_var}"', 
                                                f'{eng}_{synonym_tag}', 'forward')
            except Exception as e:
                logger.warning(f"Query expansion error in proximity search: {e}")
        
        # Add semantic proximity if enabled
        if strategy.get('semantic_proximity'):
            # Create conceptually related searches
            for eng in variations:
                # Search for related concepts
                add_variation(eng, f'("{term1}" OR related:{term1}) ("{term2}" OR related:{term2})', 
                            f'{eng}_semantic', 'both')
                
                # Topic-based search
                add_variation(eng, f'topic:("{term1}" "{term2}")', f'{eng}_topic', 'both')
        
        return variations

    async def search(self, query: str, max_results_per_variation: int = 10, enable_snippet_validation: bool = None) -> Dict:
        """Main search method for the ProximitySearcher class."""
        # Start streaming
        engines_list = list(self.engines.keys())
        self.start_search(query, engines_list)
        
        try:
            term1, term2, distance, mode = self.parse_query(query)
        except ProximitySyntaxError as e:
            logger.error(f"Syntax error: {e}")
            error_msg = str(e)
            self.complete_search({'error': error_msg})
            return {'error': error_msg}
        except Exception as e:
            logger.error(f"Parsing error: {e}")
            error_msg = str(e)
            self.complete_search({'error': error_msg})
            return {'error': error_msg}
        
        # Store original query for metrics
        original_query = query
        
        # Determine snippet validation based on config or parameter
        if enable_snippet_validation is None:
            if self.recall_optimizer:
                # Use validation based on recall mode and round
                strategy = self.recall_optimizer.get_search_strategy('proximity', round_num=1)
                enable_snippet_validation = not strategy.get('disable_snippet_validation', False)
            else:
                enable_snippet_validation = True  # Default behavior

        variations = await self._generate_search_variations(term1, term2, distance, mode, bidirectional=True)

        tasks = []
        engine_stats = {}
        unique_query_keys = set()

        for engine_name, engine in self.engines.items():
            if engine_name in variations:
                tagged_queries = variations[engine_name]
                for i, (q_variation, tag) in enumerate(tagged_queries):
                    if not q_variation: continue

                    query_key = (engine_name, q_variation)
                    if query_key in unique_query_keys:
                        continue
                    unique_query_keys.add(query_key)

                    stat_key = f"{engine_name}_{tag}_{i}"
                    tasks.append(self._search_engine(engine, engine_name, q_variation, max_results_per_variation, stat_key, tag))
                    engine_stats[stat_key] = {'query': q_variation, 'tag': tag, 'processed': 0, 'included_initially': 0, 'passed_snippet_filter': 0, 'status': 'pending'}

        if not tasks:
            return {'error': "No variations generated."}

        engine_outputs = await asyncio.gather(*tasks, return_exceptions=True)

        aggregated_results = {}

        for output in engine_outputs:
            if isinstance(output, Exception):
                logger.error(f"Task failed: {output}")
                continue
            if not isinstance(output, dict) or 'stat_key' not in output or 'tag' not in output:
                continue

            stat_key = output['stat_key']
            tag = output['tag']
            if stat_key not in engine_stats:
                continue

            engine_stats[stat_key]['status'] = 'completed'
            if output.get('error'):
                engine_stats[stat_key]['status'] = 'failed'
                engine_stats[stat_key]['error'] = output['error']
                continue

            results_list = output.get('results', [])
            engine_stats[stat_key]['processed'] = len(results_list)

            for result in results_list:
                url = result.get('url')
                if url:
                    snippet = result.get('snippet', result.get('description', ''))
                    
                    # Score the result if recall optimizer available
                    if self.recall_optimizer:
                        query_terms = [term1, term2]
                        result['confidence_score'] = self.recall_optimizer.score_result(
                            result, 'proximity', query_terms
                        )
                    
                    if url not in aggregated_results:
                        aggregated_results[url] = {
                            'result': {'url': url, 'title': result.get('title', ''), 'snippet': snippet, 
                                     'source_engines': set(), 'tags': set(),
                                     'confidence_score': result.get('confidence_score', 0.5)},
                            'snippets_all': set()
                        }
                    aggregated_results[url]['result']['source_engines'].add(output.get('engine_name', '?'))
                    aggregated_results[url]['result']['tags'].add(tag)
                    if snippet:
                        aggregated_results[url]['snippets_all'].add(snippet)
                        if len(snippet) > len(aggregated_results[url]['result']['snippet']):
                            aggregated_results[url]['result']['snippet'] = snippet

        final_results = []
        for url, data in aggregated_results.items():
            tags = data['result']['tags']
            qualifies_initially = False
            
            # Without snippet validation, include all results
            if not enable_snippet_validation:
                qualifies_initially = True
            else:
                # Original qualification logic
                if mode == "exactly" or mode == "wildcard":
                    includes = any(t.startswith(k) for k in ['google_around_N', 'bing_near_N', 'yandex_slash_N', 'aleph_prox_N', 'gemini_exact'] for t in tags)
                    excludes = any(t.startswith(k) for k in ['google_around_N_minus_1', 'bing_near_N_minus_1', 'yandex_slash_N_minus_1', 'aleph_prox_N_minus_1'] for t in tags)
                    if includes and not excludes:
                        qualifies_initially = True

                elif mode == "at_least":
                    includes = any(t.startswith(k) for k in ['google_broad', 'bing_broad', 'yandex_broad', 'duckduckgo_broad', 'yep_broad', 'aleph_broad', 'x_broad', 'archive_broad', 'newsapi_broad', 'gemini_at_least'] for t in tags)
                    excludes = any(t.startswith(k) for k in ['google_around_N_minus_1', 'bing_near_N_minus_1', 'yandex_slash_N_minus_1', 'aleph_prox_N_minus_1'] for t in tags)
                    if includes and not excludes:
                        qualifies_initially = True

                elif mode == "fewer_than":
                    includes = any(t.startswith(k) for k in ['google_around_N_minus_1', 'bing_near_N_minus_1', 'yandex_slash_N_minus_1', 'aleph_prox_N_minus_1', 'gemini_less_than'] for t in tags)
                    if includes:
                        qualifies_initially = True

            if qualifies_initially:
                final_result = data['result']
                best_snippet = final_result['snippet']
                word_count = None
                
                # Always calculate word count for scoring, even if not filtering
                word_count = self._count_words_between_in_snippet(best_snippet, term1, term2)
                
                if enable_snippet_validation:
                    # Apply snippet validation
                    passed_snippet_test = False
                    
                    if word_count is not None:
                        if mode == "exactly" or mode == "wildcard":
                            if word_count == distance:
                                passed_snippet_test = True
                        elif mode == "at_least":
                            if word_count >= distance:
                                passed_snippet_test = True
                        elif mode == "fewer_than":
                            if word_count < distance:
                                passed_snippet_test = True

                    if not passed_snippet_test and len(data['snippets_all']) > 1:
                        for snippet in data['snippets_all']:
                            if snippet == best_snippet: continue
                            word_count = self._count_words_between_in_snippet(snippet, term1, term2)
                            if word_count is not None:
                                if (mode in ["exactly", "wildcard"] and word_count == distance) or \
                                   (mode == "at_least" and word_count >= distance) or \
                                   (mode == "fewer_than" and word_count < distance):
                                    passed_snippet_test = True
                                    break
                    
                    if not passed_snippet_test:
                        continue  # Skip this result
                
                # Add proximity score boost if terms are found at correct distance
                if word_count is not None and 'confidence_score' in final_result:
                    if mode == "exactly" and word_count == distance:
                        final_result['confidence_score'] = min(1.0, final_result['confidence_score'] + 0.3)
                    elif mode == "at_least" and word_count >= distance:
                        final_result['confidence_score'] = min(1.0, final_result['confidence_score'] + 0.2)
                    elif mode == "fewer_than" and word_count < distance:
                        final_result['confidence_score'] = min(1.0, final_result['confidence_score'] + 0.2)
                
                final_result['source_engines'] = sorted(list(final_result['source_engines']))
                final_result['tags'] = sorted(list(tags))
                final_result['snippet_word_count'] = word_count
                final_result['proximity_validation'] = enable_snippet_validation
                final_results.append(final_result)

        # Apply filtering to final results
        passed_results, filtered_results = self._filter_results(final_results, query)
        
        # Emit filtered results as streaming events
        for filtered_result in filtered_results:
            self.emit_search_filtered_result(filtered_result)
        
        # Emit passed results as streaming events
        for result in passed_results:
            self.emit_search_result(result)
        
        # Update filtered results tracking
        self.filtered_results.extend(filtered_results)
        self.filtered_count += len(filtered_results)
        
        # Log filtering statistics
        if filtered_results:
            logger.info(f"Proximity search filtering: {len(passed_results)} passed, {len(filtered_results)} filtered out")

        # Complete streaming with final summary
        summary = {
            'total_results': len(passed_results),
            'filtered_count': len(filtered_results),
            'unique_results': len(passed_results),
            'filter_statistics': {
                'total_processed': len(final_results),
                'passed': len(passed_results),
                'filtered': len(filtered_results),
                'filter_rate': len(filtered_results) / len(final_results) if final_results else 0
            }
        }
        self.complete_search(summary)
        
        # Return structured data as required by main.py
        return {
            'total_unique_results': len(passed_results),
            'results': passed_results,
            'filtered_results': filtered_results,
            'filtered_count': len(filtered_results),
            'filter_statistics': {
                'total_processed': len(final_results),
                'passed': len(passed_results),
                'filtered': len(filtered_results),
                'filter_rate': len(filtered_results) / len(final_results) if final_results else 0
            }
        }

    async def _search_engine(self, engine, engine_name: str, query: str, max_results: int, stat_key: str, tag: str) -> Dict:
        output = {
            'stat_key': stat_key,
            'engine_name': engine_name,
            'tag': tag,
            'results': [],
            'error': None
        }
        max_results = max(1, int(max_results))
        try:
            search_method = getattr(engine, 'search_async', getattr(engine, 'search', None))
            if not callable(search_method):
                raise NotImplementedError(f"No search method for {engine_name}")

            method_args = [query]
            method_kwargs = {'max_results': max_results} if 'max_results' in inspect.signature(search_method).parameters else {}

            if asyncio.iscoroutinefunction(search_method):
                results = await search_method(*method_args, **method_kwargs)
            else:
                loop = asyncio.get_running_loop()
                func_call = partial(search_method, *method_args, **method_kwargs)
                results = await loop.run_in_executor(None, func_call)

            output['results'] = results or []
        except Exception as e:
            output['error'] = str(e)
        return output

    def save_results(self, data: Dict):
        results_dir = "search_results"
        os.makedirs(results_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_query = "".join(c if c.isalnum() or c in ['_','-'] else "_" for c in data['original_query'])[:60]
        filename = f"prox_wild_search_{safe_query}_{timestamp}.json"
        filepath = os.path.join(results_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Saved results to {filepath}")

# Keep the main block for direct testing if needed
if __name__ == "__main__":
    async def main_test():
        searcher = ProximitySearcher()
        print("\n=== Proximity/Wildcard Search (Test Mode) ===")
        print("Syntax: term1 OP term2 (OP: N<, <N, ~N, *N, *, **, ***)")
        print("Type 'exit' to end.")

        while True:
            try:
                query = input("\nQuery: ").strip()
                if query.lower() in ['exit', 'quit']:
                    break
                if not query:
                    continue

                results_data = await searcher.search(query)

                if 'error' in results_data:
                    print(f"Error: {results_data['error']}")
                    continue

                print(f"\nFound {results_data['total_unique_results']} results.")

                for i, result in enumerate(results_data['results'][:20], 1):
                    print(f"\n{i}. {result.get('title', 'No Title')} [{', '.join(result.get('source_engines', []))}]")
                    print(f"   URL: {result.get('url', 'N/A')}")
                    snippet = result.get('snippet', '')[:250] + '...' if len(result.get('snippet', '')) > 250 else result.get('snippet', '')
                    print(f"   Snippet: {snippet}")

            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {str(e)}")
                traceback.print_exc()

    asyncio.run(main_test())
