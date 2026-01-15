import sys
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple
import logging
from datetime import datetime
import os
import asyncio
import requests
from urllib.parse import urlparse

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import search engines from engines directory
sys.path.insert(0, str(Path(__file__).parent.parent / 'engines'))

try:
    from exact_phrase_recall_runner_google import GoogleSearch
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

try:
    from exact_phrase_recall_runner_bing import BingSearch
    BING_AVAILABLE = True
except ImportError:
    BING_AVAILABLE = False

try:
    from exact_phrase_recall_runner_brave import BraveSearch
    BRAVE_AVAILABLE = True
except ImportError:
    BRAVE_AVAILABLE = False

try:
    from exact_phrase_recall_runner_duckduck import MaxExactDuckDuckGo as DuckDuckGoSearch
    DUCKDUCKGO_AVAILABLE = True
except ImportError:
    DUCKDUCKGO_AVAILABLE = False

# Import AI brain for common phrases
try:
    from brain import get_ai_brain, AIRequest, TaskType
    AI_BRAIN_AVAILABLE = True
except ImportError:
    AI_BRAIN_AVAILABLE = False

# Import site search module
try:
    from .site import SiteSearcher as SiteSearch
    SITE_SEARCH_AVAILABLE = True
except (ImportError, NameError):
    SITE_SEARCH_AVAILABLE = False

# Filtering integration
try:
    from brute.scraper.phrase_matcher import PhraseMatcher
    from brute.filtering.core.filter_manager import FilterManager
    FILTERING_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Filtering not available: {e}")
    FILTERING_AVAILABLE = False

# Streaming integration
try:
    from brute.infrastructure.base_streamer import SearchTypeEventEmitter
    STREAMING_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Streaming not available: {e}")
    STREAMING_AVAILABLE = False
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

# BrightData Archive (17.5 PB cached web data) - geo{}/lang{}/cat{}/date{} native
try:
    from backdrill.brightdata import BrightDataArchive
    BRIGHTDATA_AVAILABLE = True
except ImportError as e:
    print(f"Warning: BrightData Archive not available: {e}")
    BRIGHTDATA_AVAILABLE = False

logger = logging.getLogger(__name__)

# =============================================================================
# GEO NEGATION SUPPORT: -geo{de}! → exclude Germany, search elsewhere
# =============================================================================

# Alternative countries to search when one is excluded
ALTERNATIVE_COUNTRIES: Dict[str, List[str]] = {
    "de": ["us", "gb", "fr", "nl", "at", "ch"],  # Exclude Germany → search US, UK, FR...
    "us": ["gb", "ca", "au", "de", "fr", "nl"],  # Exclude US → search UK, CA, AU...
    "gb": ["us", "ca", "au", "de", "fr", "ie"],  # Exclude UK → search US, CA, AU...
    "fr": ["us", "gb", "de", "be", "ch", "ca"],  # Exclude France
    "ru": ["us", "gb", "de", "fr", "ua", "pl"],  # Exclude Russia
    "cn": ["us", "gb", "jp", "kr", "tw", "sg"],  # Exclude China
    "jp": ["us", "gb", "kr", "tw", "de", "fr"],  # Exclude Japan
    "au": ["us", "gb", "nz", "ca", "sg", "de"],  # Exclude Australia
    "ca": ["us", "gb", "au", "de", "fr", "nl"],  # Exclude Canada
    "nl": ["us", "gb", "de", "be", "fr", "at"],  # Exclude Netherlands
    "es": ["us", "gb", "fr", "de", "pt", "mx"],  # Exclude Spain
    "it": ["us", "gb", "de", "fr", "ch", "at"],  # Exclude Italy
    "br": ["us", "pt", "es", "ar", "mx", "gb"],  # Exclude Brazil
    "in": ["us", "gb", "sg", "ae", "au", "ca"],  # Exclude India
    "kr": ["us", "jp", "gb", "de", "tw", "sg"],  # Exclude South Korea
}

# Country TLDs for post-filtering (when engines don't support native exclusion)
COUNTRY_TLDS: Dict[str, List[str]] = {
    "de": [".de", ".berlin", ".bayern", ".hamburg", ".koeln", ".nrw", ".saarland"],
    "us": [".us", ".gov", ".mil"],
    "gb": [".uk", ".co.uk", ".org.uk", ".gov.uk", ".london", ".scot", ".wales"],
    "fr": [".fr", ".paris", ".bzh", ".alsace", ".corsica"],
    "ru": [".ru", ".su", ".moscow", ".tatar"],
    "cn": [".cn", ".中国", ".香港"],
    "jp": [".jp", ".tokyo", ".osaka", ".nagoya"],
    "au": [".au", ".com.au", ".sydney", ".melbourne"],
    "ca": [".ca", ".quebec"],
    "nl": [".nl", ".amsterdam"],
    "es": [".es", ".cat", ".madrid", ".barcelona", ".gal"],
    "it": [".it", ".roma", ".milano", ".napoli"],
    "br": [".br", ".com.br"],
    "in": [".in", ".co.in", ".delhi", ".bangalore"],
    "kr": [".kr", ".co.kr", ".seoul"],
    "pl": [".pl", ".warszawa"],
    "ch": [".ch", ".swiss"],
    "at": [".at", ".wien"],
    "be": [".be", ".brussels", ".vlaanderen"],
    "se": [".se", ".stockholm"],
    "no": [".no", ".oslo"],
    "dk": [".dk", ".copenhagen"],
    "fi": [".fi", ".helsinki"],
    "ie": [".ie", ".dublin"],
    "pt": [".pt", ".lisboa"],
    "mx": [".mx", ".com.mx"],
    "ar": [".ar", ".com.ar"],
}


def get_alternative_countries(exclude_country: str) -> List[str]:
    """Get alternative countries to search when one is excluded."""
    exclude_country = exclude_country.lower()
    return ALTERNATIVE_COUNTRIES.get(exclude_country, ["us", "gb", "de", "fr", "au"])[:5]


def filter_by_country(results: List[Dict], exclude_country: str) -> List[Dict]:
    """
    Post-filter results to remove items from excluded country.

    Uses TLD matching and URL patterns to identify country.
    For engines that don't support native geo exclusion.
    """
    exclude_country = exclude_country.lower()
    excluded_tlds = COUNTRY_TLDS.get(exclude_country, [f".{exclude_country}"])

    filtered = []
    for result in results:
        url = result.get("url", "").lower()

        # Check TLD
        tld_match = any(
            url.endswith(tld) or f"{tld}/" in url
            for tld in excluded_tlds
        )

        if not tld_match:
            filtered.append(result)
        else:
            logger.debug(f"Filtered out (geo={exclude_country}): {url[:60]}")

    return filtered


async def search_brightdata_geo_exclude(
    query: str,
    exclude_country: str,
    domains: Optional[List[str]] = None,
    date: Optional[str] = None,
) -> List[Dict]:
    """
    Search BrightData Archive with country exclusion (native support).

    -geo{de}! → ip_country_blacklist: ['de']
    """
    if not BRIGHTDATA_AVAILABLE:
        return []

    try:
        bd = BrightDataArchive()
        result = await bd.search(
            domains=domains,
            countries_exclude=[exclude_country.lower()],  # Native blacklist!
            date=date,
        )

        if "error" in result:
            return []

        search_id = result.get("search_id")
        if search_id:
            import asyncio
            for _ in range(10):
                await asyncio.sleep(2)
                status = await bd.get_search_status(search_id)
                if status.get("ready"):
                    return [{
                        "source": "brightdata_archive",
                        "search_id": search_id,
                        "files_count": status.get("files_count", 0),
                        "excluded_country": exclude_country,
                        "native_exclusion": True,
                    }]
                if "error" in status:
                    break

        await bd.close()
    except Exception as e:
        logger.error(f"BrightData geo exclusion failed: {e}")

    return []

class LocationSearcher(SearchTypeEventEmitter):
    """Standardized Searcher class for location-specific searches."""
    
    def __init__(self, additional_args: List[str] = None, enable_streaming: bool = False, event_handler: Optional[callable] = None):
        # Initialize streaming first
        super().__init__(search_type="location")
        
        self.additional_args = additional_args or []
        self.engines = self._initialize_engines()
        self.ddg_regions = self._get_ddg_regions()
        self.market_codes = self._get_market_codes()
        self.google_lang_codes = self._get_google_lang_codes()
        self.ai_brain = self._initialize_ai_brain()
        self.site_search = self._initialize_site_search()
        
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
                logger.info("Filtering integration initialized for location search")
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

    async def search(self, query: str) -> Dict:
        """Standardized search method called by main.py."""
        # Start streaming
        engines_list = list(self.engines.keys())
        self.start_search(query, engines_list)
        
        try:
            keyword, country_code, language_code = self._parse_query(query)
            if not country_code:
                error_msg = "No valid location operator found. Use loc:XX, near:XX, or location:XX."
                self.complete_search({'error': error_msg})
                return {'error': error_msg}

            results_data = await self.search_location(keyword, country_code, language_code, original_query=query)
            
            # Complete streaming with summary
            summary = {
                'total_results': results_data.get('total_results', 0),
                'filtered_count': results_data.get('filtered_count', 0),
                'country_code': country_code,
                'language_code': language_code
            }
            self.complete_search(summary)
            
            # Standardize the output
            return {
                'total_unique_results': results_data.get('total_results', 0),
                'results': results_data.get('results', []),
                'filtered_count': results_data.get('filtered_count', 0),
                'filtered_results': results_data.get('filtered_results', [])
            }
        except Exception as e:
            logger.error(f"Error during location search: {e}")
            error_msg = str(e)
            self.complete_search({'error': error_msg})
            return {'error': error_msg}

    def _parse_query(self, query: str) -> Tuple[str, Optional[str], Optional[str]]:
        """Extracts keyword, country code, and language code from the query."""
        # Pattern to find loc:XX, near:XX, or location:XX
        pattern = r'\b(loc|near|location):([a-zA-Z]{2})\b'
        match = re.search(pattern, query, re.IGNORECASE)
        
        if match:
            country_code = match.group(2).lower()
            # Remove the operator from the query to get the keyword
            keyword = re.sub(pattern, '', query, flags=re.IGNORECASE).strip()
        else:
            keyword = query
            country_code = None

        # For now, language code is not parsed from the query, but could be added
        language_code = None 
        
        return keyword, country_code, language_code
    
    def _filter_results(self, results: List[Dict], original_query: str) -> Tuple[List[Dict], List[Dict]]:
        """Filter results based on exact phrase matching and return both filtered and non-matching."""
        if not self.enable_exact_phrase_filter or not self.phrase_matcher:
            return results, []
        
        # Extract exact phrases from the original query (before location parsing)
        phrases = self.phrase_matcher.extract_phrases(original_query)
        if not phrases:
            return results, []
        
        filtered_results = []
        non_matching_results = []
        
        for result in results:
            title = result.get('title', '')
            snippet = result.get('snippet', result.get('description', ''))
            
            # Check if any exact phrase is found in title or snippet
            phrase_found = False
            for phrase in phrases:
                if self.phrase_matcher.check_exact_match(phrase, title) or \
                   self.phrase_matcher.check_exact_match(phrase, snippet) or \
                   self.phrase_matcher.check_proximity_match(phrase, title) or \
                   self.phrase_matcher.check_proximity_match(phrase, snippet):
                    phrase_found = True
                    break
            
            if phrase_found:
                filtered_results.append(result)
            else:
                # Mark as filtered for the "Filtered Out" tab
                filtered_result = result.copy()
                filtered_result['filter_reason'] = f"Exact phrase not found: {', '.join(phrases)}"
                filtered_result['filter_type'] = 'exact_phrase'
                non_matching_results.append(filtered_result)
        
        return filtered_results, non_matching_results

    async def search_location(self, keyword: str, country_code: str, language_code: Optional[str] = None, max_results: int = 100, original_query: str = None) -> Dict:
        country_code = country_code.lower()
        all_results = []
        stats = {}
        
        if ' ' in keyword and not (keyword.startswith('"') and keyword.endswith('"')):
            quoted_keyword = f'"{keyword}"'
        else:
            quoted_keyword = keyword
        
        search_variations = [(keyword, 'market_specific')]
        
        common_phrases = []
        if language_code and self.ai_brain:
            common_phrases = await self._get_ai_phrases(keyword, language_code)
        
        if common_phrases:
            or_phrases = " OR ".join([f'"{p.strip()}"' for p in common_phrases if p.strip()])
            if or_phrases:
                gemini_query = f'{quoted_keyword} AND ({or_phrases})'
                search_variations.append((gemini_query, 'gemini_common'))
        
        tasks = []
        if self.site_search:
            tasks.append(self._search_with_site_module(quoted_keyword, country_code, max_results))
        
        for engine_name, engine in self.engines.items():
            for query, query_type in search_variations:
                tasks.append(self._search_engine(engine, engine_name, query, query_type, country_code, language_code, max_results))
        
        ddg_region = self.ddg_regions.get(country_code)
        if ddg_region:
            tasks.append(self._search_ddg(keyword, ddg_region, language_code, max_results))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        seen_urls = set()
        for engine_results in results:
            if isinstance(engine_results, Exception): continue
            engine_name = engine_results['engine']
            query_type = engine_results['query_type']
            results_list = engine_results['results']
            
            key = f"{engine_name}_{query_type}"
            if key not in stats: stats[key] = {'total_results': 0, 'unique_results': 0}
            stats[key]['total_results'] += len(results_list)
            
            for result in results_list:
                url = result['url']
                if url not in seen_urls:
                    seen_urls.add(url)
                    result['location_relevance'] = self._assess_location_relevance(url, country_code)
                    if language_code: result['language_relevance'] = self._assess_language_relevance(result, language_code)
                    all_results.append(result)
                    stats[key]['unique_results'] += 1
        
        # Apply filtering if enabled
        if self.enable_exact_phrase_filter and original_query and all_results:
            filtered_results, non_matching = self._filter_results(all_results, original_query)
            
            # Emit filtered results as streaming events
            for filtered_result in non_matching:
                self.emit_search_filtered_result(filtered_result)
            
            # Store filtered results for "Filtered Out" tab
            self.filtered_results.extend(non_matching)
            
            # Use filtered results for processing
            all_results = filtered_results
            
            if non_matching:
                logger.info(f"Filtered out {len(non_matching)} location results that didn't match exact phrases")
        
        all_results.sort(key=lambda x: x.get('location_relevance', 0) + x.get('language_relevance', 0), reverse=True)
        
        # Emit results as streaming events
        for result in all_results:
            self.emit_search_result(result)

        # Prepare result data with filtering statistics
        result_data = {
            'query': keyword, 'country_code': country_code, 'language_code': language_code,
            'timestamp': datetime.now().isoformat(), 'total_results': len(all_results),
            'stats': stats, 'results': all_results
        }
        
        # Add filtering statistics
        if self.enable_exact_phrase_filter:
            result_data['filtered_count'] = len(self.filtered_results)
            result_data['filtered_results'] = self.filtered_results
            if self.filtered_results:
                total_before_filter = len(all_results) + len(self.filtered_results)
                print(f"\nFiltered out: {len(self.filtered_results)} results ({len(self.filtered_results)/total_before_filter*100:.1f}%)")
        
        return result_data

    # ... (keep all other helper methods: _search_engine, _search_ddg, etc.)
    # The following are helper methods that are already part of the class

    def _initialize_engines(self):
        engines = {}
        if GOOGLE_AVAILABLE: 
            try:
                engines['google'] = GoogleSearch()
            except Exception as e:
                logger.warning(f"Could not initialize Google: {e}")
        if BING_AVAILABLE: 
            try:
                engines['bing'] = BingSearch()
            except Exception as e:
                logger.warning(f"Could not initialize Bing: {e}")
        if BRAVE_AVAILABLE: 
            try:
                engines['brave'] = BraveSearch()
            except Exception as e:
                logger.warning(f"Could not initialize Brave: {e}")
        if DUCKDUCKGO_AVAILABLE: 
            try:
                engines['duckduckgo'] = DuckDuckGoSearch(phrase="")  # Initialize with empty phrase
            except Exception as e:
                logger.warning(f"Could not initialize DuckDuckGo: {e}")
        return engines

    def _get_ddg_regions(self):
        return {
            'us': 'us-en', 'uk': 'uk-en', 'ca': 'ca-en', 'au': 'au-en', 'nz': 'nz-en', 'ie': 'ie-en',
            'de': 'de-de', 'fr': 'fr-fr', 'es': 'es-es', 'it': 'it-it', 'nl': 'nl-nl', 'pl': 'pl-pl',
            'se': 'se-sv', 'dk': 'dk-da', 'no': 'no-no', 'fi': 'fi-fi', 'pt': 'pt-pt', 'jp': 'jp-jp',
            'kr': 'kr-kr', 'cn': 'cn-zh', 'tw': 'tw-tzh', 'ru': 'ru-ru', 'br': 'br-pt', 'mx': 'mx-es'
        }

    def _get_market_codes(self):
        return {
            'us': 'en-US', 'uk': 'en-GB', 'ca': 'en-CA', 'au': 'en-AU', 'nz': 'en-NZ', 'ie': 'en-IE',
            'de': 'de-DE', 'fr': 'fr-FR', 'es': 'es-ES', 'it': 'it-IT', 'nl': 'nl-NL', 'pl': 'pl-PL',
            'se': 'sv-SE', 'dk': 'da-DK', 'no': 'nb-NO', 'fi': 'fi-FI', 'pt': 'pt-PT', 'jp': 'ja-JP',
            'kr': 'ko-KR', 'cn': 'zh-CN', 'tw': 'zh-TW', 'ru': 'ru-RU', 'br': 'pt-BR', 'mx': 'es-MX'
        }

    def _get_google_lang_codes(self):
        return {
            'us': 'lang_en', 'uk': 'lang_en', 'de': 'lang_de', 'fr': 'lang_fr', 'es': 'lang_es',
            'it': 'lang_it', 'nl': 'lang_nl', 'pl': 'lang_pl', 'se': 'lang_sv', 'dk': 'lang_da',
            'no': 'lang_no', 'fi': 'lang_fi', 'pt': 'lang_pt', 'ru': 'lang_ru', 'jp': 'lang_ja', 'kr': 'lang_ko',
            'cn': 'lang_zh-CN', 'tw': 'lang_zh-TW'
        }

    def _initialize_ai_brain(self):
        if AI_BRAIN_AVAILABLE: return get_ai_brain()
        return None

    def _initialize_site_search(self):
        if SITE_SEARCH_AVAILABLE: return SiteSearch()
        return None

    async def _get_ai_phrases(self, keyword, language_code):
        lang_names = {
            'en': 'English', 'de': 'German', 'fr': 'French', 'es': 'Spanish', 'it': 'Italian',
            'pt': 'Portuguese', 'nl': 'Dutch', 'ru': 'Russian', 'zh': 'Chinese', 'ja': 'Japanese',
            'ko': 'Korean', 'ar': 'Arabic'
        }
        language_name = lang_names.get(language_code, 'English')
        prompt = f'Generate 8-10 common words in {language_name} related to "{keyword}".'
        request = AIRequest(task_type=TaskType.QUERY_EXPANSION, prompt=prompt)
        response = await self.ai_brain.process_request(request)
        if not response.error: return [line.strip() for line in response.content.strip().split('\n') if line.strip()][:8]
        return []

    async def _search_engine(self, engine_instance, engine_name: str, query: str, query_type: str, country_code: str, language_code: Optional[str], max_results: int) -> Dict:
        results = []
        search_args = [query.strip('"')]
        search_kwargs = {'max_results': max_results}
        try:
            if engine_name == 'bing' and country_code in self.market_codes:
                mkt = self.market_codes.get(country_code, 'en-US')
                results = await asyncio.to_thread(engine_instance.search, query.strip('"'), max_results=max_results, mkt=mkt)
            elif engine_name == 'google':
                search_kwargs['geolocation'] = country_code
                if language_code and language_code in self.google_lang_codes: search_kwargs['language'] = self.google_lang_codes[language_code]
                search_method = getattr(engine_instance, 'search_async', engine_instance.search)
                if asyncio.iscoroutinefunction(search_method): results = await search_method(*search_args, **search_kwargs)
                else: results = await asyncio.to_thread(search_method, *search_args, **search_kwargs)
            else:
                search_method = getattr(engine_instance, 'search_async', engine_instance.search)
                if asyncio.iscoroutinefunction(search_method): results = await search_method(*search_args, **search_kwargs)
                else: results = await asyncio.to_thread(search_method, *search_args, **search_kwargs)
            return self._format_engine_output(engine_name, query_type, query, results)
        except Exception as e:
            logger.error(f"Error in {engine_name} search: {e}")
            return {'engine': engine_name, 'query_type': query_type, 'results': []}

    async def _search_ddg(self, keyword: str, region: str, language_code: Optional[str], max_results: int) -> Dict:
        # This is a placeholder. The actual DDG search logic needs to be implemented.
        return self._format_engine_output("duckduckgo", "market_specific", keyword, [])

    async def _search_with_site_module(self, keyword: str, country_code: str, max_results: int) -> Dict:
        try:
            results = await self.site_search.search_by_country(keyword, country_code, max_results)
            all_results = []
            for engine, urls in results.items():
                for url in urls:
                    all_results.append({'url': url, 'title': f'{keyword} - {country_code.upper()}', 'snippet': f'.{country_code} domain'})
            return {'engine': 'site_module', 'query_type': 'domain_tld', 'results': all_results}
        except Exception as e:
            logger.error(f"Error in site module search: {e}")
            return {'engine': 'site_module', 'query_type': 'domain_tld', 'results': []}

    def _format_engine_output(self, engine_name, query_type, query_used, results_list):
         for result in results_list:
             result['source'] = engine_name
             result['query_used'] = query_used
             result['query_type'] = query_type
         return {'engine': engine_name, 'query_type': query_type, 'results': results_list}

    def _assess_location_relevance(self, url: str, country_code: str) -> float:
        score = 0.0
        parsed = urlparse(url)
        if parsed.netloc.endswith(f'.{country_code}'): score += 0.5
        if f'/{country_code}/' in parsed.path: score += 0.2
        if parsed.netloc.startswith(f'{country_code}.'): score += 0.3
        return min(score, 1.0)

    def _assess_language_relevance(self, result: Dict, language_code: str) -> float:
        score = 0.0
        text_content = ' '.join([result.get('title', ''), result.get('snippet', '')]).lower()
        url = result.get('url', '').lower()
        parsed_url = urlparse(url)
        if f'/{language_code}/' in parsed_url.path or parsed_url.netloc.startswith(f'{language_code}.'): score += 0.5
        return min(score, 1.0)

if __name__ == "__main__":
    async def main_test():
        searcher = LocationSearcher()
        print("=== Location Search (Test Mode) ===")
        while True:
            try:
                query = input("Query (e.g., 'restaurants loc:fr'): ").strip()
                if query.lower() in ['exit', 'quit']: break
                if not query: continue
                results_data = await searcher.search(query)
                if 'error' in results_data:
                    print(f"Error: {results_data['error']}")
                    continue
                print(f"Found {results_data['total_unique_results']} results.")
                for i, result in enumerate(results_data['results'][:10], 1):
                    print(f"{i}. {result.get('title', 'No Title')} ({result.get('url')})")
            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {e}")

    asyncio.run(main_test())