import sys
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging
from datetime import datetime
import os
import asyncio
import json
from urllib.parse import urlparse
import requests  # For API calls to new engines

# Get the correct path to your project's root
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Import search engines from self-contained runners


# Set up logger first
logger = logging.getLogger(__name__)

# Import from self-contained runner modules with individual error handling
try:
    from exact_phrase_recall_runner_google import GoogleSearch
    GOOGLE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import Google search: {e}")
    GOOGLE_AVAILABLE = False

try:
    from exact_phrase_recall_runner_bing import BingSearch
    BING_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import Bing search: {e}")
    BING_AVAILABLE = False

try:
    from exact_phrase_recall_runner_yandex import YandexSearch
    YANDEX_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import Yandex search: {e}")
    YANDEX_AVAILABLE = False

try:
    from exact_phrase_recall_runner_duckduck import MaxExactDuckDuckGo as DuckDuckGoSearch
    DUCKDUCKGO_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import DuckDuckGo search: {e}")
    DUCKDUCKGO_AVAILABLE = False

try:
    from exact_phrase_recall_runner_yep import YepScraper as YepSearch
    YEP_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import Yep search: {e}")
    YEP_AVAILABLE = False

try:
    from exact_phrase_recall_runner_brave import BraveSearch
    BRAVE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import Brave search: {e}")
    BRAVE_AVAILABLE = False

# Import AI brain for language phrase generation
try:
    from brain import get_ai_brain, AIRequest, TaskType
    AI_BRAIN_AVAILABLE = True
except ImportError:
    AI_BRAIN_AVAILABLE = False
    logger.warning("AI brain not found, language phrase generation will be disabled")

# Import site search module
try:
    from brute.infrastructure.site import SiteSearch
    SITE_SEARCH_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import Site search module: {e}")
    SITE_SEARCH_AVAILABLE = False

# Embedded data (self-contained, no external imports)
ENGINE_PARAM_MAP = {
    'google': {
        'lang_param': 'lr',      # e.g., lang_de
        'ui_lang_param': 'hl',   # e.g., de
        'region_param': 'cr',    # e.g., countryDE
        'geo_param': 'gl'        # e.g., de
    },
    'bing': {
        'market_param': 'mkt',       # e.g., de-DE
        'lang_param': 'setLang'      # e.g., de
    },
    'brave': {
        'lang_param': 'search_lang', # e.g., de
        'region_param': 'country'    # e.g., DE
    },
    'duckduckgo': {
        'region_lang_param': 'kl'    # e.g., de-de
    },
    'yandex': {
        'region_param': 'lr',        # Region ID, e.g., 187 for Germany
        'lang_param': 'lang'         # e.g., de
    },
    'yep': {
        'lang_param': 'lang',        # Assumed, e.g., de
        'country_param': 'country'   # Assumed, e.g., DE
    }
}

LANG_CODE_MAP = {
    'en': {
        'google_lr': 'lang_en', 'google_hl': 'en', 'google_cr': 'countryUS', 'google_gl': 'us',
        'bing_mkt': 'en-US', 'bing_setLang': 'en',
        'brave_search_lang': 'en', 'brave_country': 'US',
        'duckduckgo_kl': 'us-en',
        'yandex_lang': 'en', 'yandex_lr': '225',  # English region
        'yep_lang': 'en', 'yep_country': 'US'
    },
    'de': {
        'google_lr': 'lang_de', 'google_hl': 'de', 'google_cr': 'countryDE', 'google_gl': 'de',
        'bing_mkt': 'de-DE', 'bing_setLang': 'de',
        'brave_search_lang': 'de', 'brave_country': 'DE',
        'duckduckgo_kl': 'de-de',
        'yandex_lang': 'de', 'yandex_lr': '187',  # Germany
        'yep_lang': 'de', 'yep_country': 'DE'
    },
    'fr': {
        'google_lr': 'lang_fr', 'google_hl': 'fr', 'google_cr': 'countryFR', 'google_gl': 'fr',
        'bing_mkt': 'fr-FR', 'bing_setLang': 'fr',
        'brave_search_lang': 'fr', 'brave_country': 'FR',
        'duckduckgo_kl': 'fr-fr',
        'yandex_lang': 'fr', 'yandex_lr': '124',  # France
        'yep_lang': 'fr', 'yep_country': 'FR'
    },
    'es': {
        'google_lr': 'lang_es', 'google_hl': 'es', 'google_cr': 'countryES', 'google_gl': 'es',
        'bing_mkt': 'es-ES', 'bing_setLang': 'es',
        'brave_search_lang': 'es', 'brave_country': 'ES',
        'duckduckgo_kl': 'es-es',
        'yandex_lang': 'es', 'yandex_lr': '213',  # Spain
        'yep_lang': 'es', 'yep_country': 'ES'
    },
    'it': {
        'google_lr': 'lang_it', 'google_hl': 'it', 'google_cr': 'countryIT', 'google_gl': 'it',
        'bing_mkt': 'it-IT', 'bing_setLang': 'it',
        'brave_search_lang': 'it', 'brave_country': 'IT',
        'duckduckgo_kl': 'it-it',
        'yandex_lang': 'it', 'yandex_lr': '205',  # Italy
        'yep_lang': 'it', 'yep_country': 'IT'
    },
    'pt': {
        'google_lr': 'lang_pt', 'google_hl': 'pt', 'google_cr': 'countryBR', 'google_gl': 'br',
        'bing_mkt': 'pt-BR', 'bing_setLang': 'pt',
        'brave_search_lang': 'pt', 'brave_country': 'BR',
        'duckduckgo_kl': 'pt-br',
        'yandex_lang': 'pt', 'yandex_lr': '216',  # Brazil
        'yep_lang': 'pt', 'yep_country': 'BR'
    },
    'nl': {
        'google_lr': 'lang_nl', 'google_hl': 'nl', 'google_cr': 'countryNL', 'google_gl': 'nl',
        'bing_mkt': 'nl-NL', 'bing_setLang': 'nl',
        'brave_search_lang': 'nl', 'brave_country': 'NL',
        'duckduckgo_kl': 'nl-nl',
        'yandex_lang': 'nl', 'yandex_lr': '158',  # Netherlands
        'yep_lang': 'nl', 'yep_country': 'NL'
    },
    'ru': {
        'google_lr': 'lang_ru', 'google_hl': 'ru', 'google_cr': 'countryRU', 'google_gl': 'ru',
        'bing_mkt': 'ru-RU', 'bing_setLang': 'ru',
        'brave_search_lang': 'ru', 'brave_country': 'RU',
        'duckduckgo_kl': 'ru-ru',
        'yandex_lang': 'ru', 'yandex_lr': '225',  # Russia
        'yep_lang': 'ru', 'yep_country': 'RU'
    },
    'zh': {
        'google_lr': 'lang_zh', 'google_hl': 'zh', 'google_cr': 'countryCN', 'google_gl': 'cn',
        'bing_mkt': 'zh-CN', 'bing_setLang': 'zh',
        'brave_search_lang': 'zh', 'brave_country': 'CN',
        'duckduckgo_kl': 'zh-cn',
        'yandex_lang': 'zh', 'yandex_lr': '134',  # China
        'yep_lang': 'zh', 'yep_country': 'CN'
    },
    'ja': {
        'google_lr': 'lang_ja', 'google_hl': 'ja', 'google_cr': 'countryJP', 'google_gl': 'jp',
        'bing_mkt': 'ja-JP', 'bing_setLang': 'ja',
        'brave_search_lang': 'ja', 'brave_country': 'JP',
        'duckduckgo_kl': 'ja-jp',
        'yandex_lang': 'ja', 'yandex_lr': '137',  # Japan
        'yep_lang': 'ja', 'yep_country': 'JP'
    }
}

REGION_VARIANT_MAP = {
    'en': {
        'GB': {'google_cr': 'countryUK', 'google_gl': 'uk', 'bing_mkt': 'en-GB', 'brave_country': 'GB', 'duckduckgo_kl': 'uk-en', 'yandex_lr': '213'},
        'CA': {'google_cr': 'countryCA', 'google_gl': 'ca', 'bing_mkt': 'en-CA', 'brave_country': 'CA', 'duckduckgo_kl': 'ca-en', 'yandex_lr': '124'},
        'AU': {'google_cr': 'countryAU', 'google_gl': 'au', 'bing_mkt': 'en-AU', 'brave_country': 'AU', 'duckduckgo_kl': 'au-en', 'yandex_lr': '191'},
    },
    'de': {
        'AT': {'google_cr': 'countryAT', 'google_gl': 'at', 'bing_mkt': 'de-AT', 'brave_country': 'AT', 'duckduckgo_kl': 'at-de', 'yandex_lr': '172'},
        'CH': {'google_cr': 'countryCH', 'google_gl': 'ch', 'bing_mkt': 'de-CH', 'brave_country': 'CH', 'duckduckgo_kl': 'ch-de', 'yandex_lr': '167'}
    },
    'fr': {
        'CA': {'google_cr': 'countryCA', 'google_gl': 'ca', 'bing_mkt': 'fr-CA', 'brave_country': 'CA', 'duckduckgo_kl': 'ca-fr', 'yandex_lr': '124'},
        'BE': {'google_cr': 'countryBE', 'google_gl': 'be', 'bing_mkt': 'fr-BE', 'brave_country': 'BE', 'duckduckgo_kl': 'be-fr', 'yandex_lr': '157'},
        'CH': {'google_cr': 'countryCH', 'google_gl': 'ch', 'bing_mkt': 'fr-CH', 'brave_country': 'CH', 'duckduckgo_kl': 'ch-fr', 'yandex_lr': '167'}
    },
    'es': {
        'MX': {'google_cr': 'countryMX', 'google_gl': 'mx', 'bing_mkt': 'es-MX', 'brave_country': 'MX', 'duckduckgo_kl': 'mx-es', 'yandex_lr': '159'},
        'AR': {'google_cr': 'countryAR', 'google_gl': 'ar', 'bing_mkt': 'es-AR', 'brave_country': 'AR', 'duckduckgo_kl': 'ar-es', 'yandex_lr': '1'}
    }
}

LANGUAGE_DATA = {
    'en': {'name': 'English', 'regions': ['US', 'GB', 'CA', 'AU', 'NZ', 'IE', 'IN']},
    'de': {'name': 'German', 'regions': ['DE', 'AT', 'CH']},
    'nl': {'name': 'Dutch', 'regions': ['NL', 'BE']},
    'fr': {'name': 'French', 'regions': ['FR', 'CA', 'BE', 'CH']},
    'es': {'name': 'Spanish', 'regions': ['ES', 'MX', 'AR', 'CO', 'PE', 'CL', 'US']},
    'it': {'name': 'Italian', 'regions': ['IT', 'CH']},
    'pt': {'name': 'Portuguese', 'regions': ['PT', 'BR']},
    'ru': {'name': 'Russian', 'regions': ['RU', 'BY', 'KZ']},
    'pl': {'name': 'Polish', 'regions': ['PL']},
    'cs': {'name': 'Czech', 'regions': ['CZ']},
    'zh': {'name': 'Chinese', 'regions': ['CN', 'TW', 'HK', 'SG']},
    'ja': {'name': 'Japanese', 'regions': ['JP']},
    'ko': {'name': 'Korean', 'regions': ['KR']},
    'sv': {'name': 'Swedish', 'regions': ['SE']},
    'da': {'name': 'Danish', 'regions': ['DK']},
    'no': {'name': 'Norwegian', 'regions': ['NO']},
    'fi': {'name': 'Finnish', 'regions': ['FI']},
    'ar': {'name': 'Arabic', 'regions': ['SA', 'EG', 'AE', 'MA', 'TN']},
    'hi': {'name': 'Hindi', 'regions': ['IN']},
    'tr': {'name': 'Turkish', 'regions': ['TR']}
}

async def generate_common_phrases_for_language(language_name: str, search_query: str = "") -> List[str]:
    """Generate common phrases for a language using AI brain (fallback: gpt-4.1-nano)"""
    if not AI_BRAIN_AVAILABLE:
        return []
    
    try:
        brain = get_ai_brain()
        
        # Enhanced prompt that considers the search context
        if search_query:
            prompt = f"""
            Generate 8-12 common words and short phrases in {language_name} that are frequently used in web content related to "{search_query}".
            
            Include:
            1. Common navigation terms (about, contact, home, more, etc.)
            2. Action words (read, click, learn, discover, etc.) 
            3. Content indicators (article, news, information, guide, etc.)
            4. Domain-specific terms related to the search topic
            
            Focus on terms that would appear in titles, headings, and navigation menus of {language_name} websites.
            Return only the words/phrases in {language_name}, one per line, without numbers or explanations.
            """
        else:
            prompt = f"""
            Generate 10 common words and short phrases in {language_name} that are frequently used in web content.
            
            Include a mix of:
            - Website navigation terms
            - Common action words  
            - Content type indicators
            - Universal website elements
            
            Focus on everyday terms that would appear in articles, blogs, and websites.
            Return only the words/phrases in {language_name}, one per line, without numbers or explanations.
            """
        
        request = AIRequest(
            task_type=TaskType.QUERY_EXPANSION,
            prompt=prompt,
            model_preference="gpt-4.1-nano",  # Use nano as fallback
            temperature=0.7
        )
        
        response = await brain.process_request(request)
        if response.error:
            logger.error(f"AI brain language phrase generation error: {response.error}")
            return []
        
        # Parse response to extract phrases
        phrases = [line.strip() for line in response.content.strip().split('\n') if line.strip()]
        return phrases[:10]  # Limit to 10 phrases
        
    except Exception as e:
        logger.error(f"Error generating language phrases: {e}")
        return []

class LanguageSearcher:
    """Language-specific search coordinator using self-contained search engines."""

    def __init__(self):
        """Initialize search engines."""
        self.engines = {}
        
        # Initialize site search module
        self.site_search = SiteSearch() if SITE_SEARCH_AVAILABLE else None
        
        # Try to initialize each engine based on availability
        if GOOGLE_AVAILABLE:
            try:
                self.engines['google'] = GoogleSearch()
                logger.info("Initialized Google search for language search")
            except Exception as e:
                logger.warning(f"Could not initialize Google for language search: {e}")
        
        if BING_AVAILABLE:
            try:
                self.engines['bing'] = BingSearch()
                logger.info("Initialized Bing search for language search")
            except Exception as e:
                logger.warning(f"Could not initialize Bing for language search: {e}")
        
        if YANDEX_AVAILABLE:
            try:
                self.engines['yandex'] = YandexSearch()
                logger.info("Initialized Yandex search for language search")
            except Exception as e:
                logger.warning(f"Could not initialize Yandex for language search: {e}")
        
        if DUCKDUCKGO_AVAILABLE:
            try:
                self.engines['duckduckgo'] = DuckDuckGoSearch()
                logger.info("Initialized DuckDuckGo search for language search")
            except Exception as e:
                logger.warning(f"Could not initialize DuckDuckGo for language search: {e}")
        
        if YEP_AVAILABLE:
            try:
                self.engines['yep'] = YepSearch()
                logger.info("Initialized Yep search for language search")
            except Exception as e:
                logger.warning(f"Could not initialize Yep for language search: {e}")
        
        if BRAVE_AVAILABLE:
            try:
                self.engines['brave'] = BraveSearch()
                logger.info("Initialized Brave search for language search")
            except Exception as e:
                logger.warning(f"Could not initialize Brave for language search: {e}")

    def _get_engine_params(self, engine_name: str, lang_code: str, region_code: Optional[str] = None) -> Dict:
        """Constructs the parameter dictionary for a given engine, language, and optional region."""
        params = {}
        if engine_name not in ENGINE_PARAM_MAP or lang_code not in LANG_CODE_MAP:
            logger.warning(f"No parameter mapping found for engine '{engine_name}' or lang_code '{lang_code}'.")
            return params

        engine_specifics = ENGINE_PARAM_MAP[engine_name]
        lang_defaults = LANG_CODE_MAP[lang_code]

        # Apply base language & default region parameters
        for param_type, engine_param_name in engine_specifics.items():
            default_map_key = f"{engine_name}_{engine_param_name}"
            if default_map_key in lang_defaults:
                params[engine_param_name] = lang_defaults[default_map_key]

        # Apply regional overrides if region_code is provided
        if region_code:
            region_code_upper = region_code.upper()
            if lang_code in REGION_VARIANT_MAP and region_code_upper in REGION_VARIANT_MAP[lang_code]:
                region_overrides = REGION_VARIANT_MAP[lang_code][region_code_upper]
                logger.debug(f"Applying regional overrides for {lang_code}/{region_code_upper}: {region_overrides}")
                for map_key, value in region_overrides.items():
                     if map_key.startswith(engine_name + "_"):
                         engine_param_name = map_key.split('_', 1)[1]
                         params[engine_param_name] = value
                         logger.debug(f"  Override applied: {engine_param_name} = {value}")

        logger.debug(f"Generated params for {engine_name}/{lang_code}/{region_code}: {params}")
        return params

    async def search_language(self, query: str, lang_code: str, max_results_per_engine: int = 500) -> Dict:
        """Search across engines using language/region parameters and AI enhancement."""
        lang_code = lang_code.lower()
        if lang_code not in LANGUAGE_DATA:
            return {'error': f"Language code '{lang_code}' not supported or mapped."}
        if lang_code not in LANG_CODE_MAP:
             logger.error(f"CRITICAL: Language code '{lang_code}' exists in LANGUAGE_DATA but not in LANG_CODE_MAP.")
             return {'error': f"Internal configuration error for language code '{lang_code}'. Mappings missing."}

        lang_info = LANGUAGE_DATA[lang_code]
        target_language_name = lang_info['name']
        logger.info(f"Starting language search for '{query}' in {target_language_name} ({lang_code})")

        # Get AI-generated common phrases
        common_phrases = []
        if AI_BRAIN_AVAILABLE:
             logger.info(f"Attempting to generate common phrases for {target_language_name} via AI brain...")
             common_phrases = await generate_common_phrases_for_language(target_language_name, query)
        else:
            logger.warning("AI brain not initialized, skipping common phrase generation.")

        all_results = []
        engine_stats = {}
        tasks = []
        search_variations_run = set()

        primary_region = lang_info.get('regions', [None])[0]

        for engine_name, engine in self.engines.items():
            def add_task_if_new(variation_tag: str, search_query: str, params: Dict):
                if not params:
                     logger.warning(f"Skipping task '{variation_tag}' for {engine_name}: No parameters generated.")
                     return
                params_tuple = frozenset(params.items())
                query_modifier = search_query if search_query != query else None
                task_key = (engine_name, params_tuple, query_modifier)

                if task_key not in search_variations_run:
                    stat_key = f"{engine_name}_{variation_tag}"
                    tasks.append(self._search_engine(
                        engine, engine_name, search_query, params, max_results_per_engine, stat_key
                    ))
                    search_variations_run.add(task_key)
                    engine_stats[stat_key] = {
                        'processed': 0, 'unique_added': 0,
                        'params': params,
                        'query': search_query,
                        'status': 'pending'
                    }

            # 1. Base search with language parameters
            base_params = self._get_engine_params(engine_name, lang_code)
            add_task_if_new(f"base_{lang_code}", query, base_params)

            # 2. Regional search for primary region
            if primary_region:
                region_params = self._get_engine_params(engine_name, lang_code, primary_region)
                if region_params != base_params:
                     add_task_if_new(f"region_{primary_region}", query, region_params)

            # Site TLD search is now handled by site module separately

            # 4. AI-enhanced search with common phrases
            if common_phrases:
                 or_phrases = " OR ".join([f'"{p.strip()}"' for p in common_phrases if p.strip()])
                 if or_phrases:
                      quoted_original_query = f'"{query.strip()}"' if ' ' in query.strip() else query.strip()
                      ai_query = f'{quoted_original_query} AND ({or_phrases})'
                      add_task_if_new(f"ai_enhanced_{lang_code}", ai_query, base_params)

        # Add site module search for primary region TLD
        if self.site_search and primary_region:
            primary_region_tld = primary_region.lower()
            if len(primary_region_tld) == 2:
                tasks.append(self._search_with_site_module(query, primary_region_tld, max_results_per_engine))

        # Execute searches
        logger.info(f"Running {len(tasks)} search tasks for language {lang_code}...")
        engine_outputs = await asyncio.gather(*tasks, return_exceptions=True)

        seen_urls = set()
        raw_results_map = {}

        for output in engine_outputs:
            stat_key = "unknown_task"
            try:
                if isinstance(output, Exception):
                    logger.error(f"Language search task failed: {output}")
                    continue

                if not isinstance(output, dict) or 'stat_key' not in output:
                    logger.error(f"Invalid result format from language search task: {output}")
                    continue

                stat_key = output['stat_key']
                if stat_key not in engine_stats:
                     logger.error(f"Received result for unknown stat_key: {stat_key}")
                     continue

                engine_stats[stat_key]['status'] = 'completed'
                if output.get('error'):
                     engine_stats[stat_key]['status'] = 'failed'
                     engine_stats[stat_key]['error'] = output['error']
                     logger.warning(f"Task {stat_key} reported an error: {output['error']}")
                     continue

                results_list = output.get('results', [])
                engine_stats[stat_key]['processed'] = len(results_list)

                if results_list:
                    for result in results_list:
                        url = result.get('url', '')
                        if url:
                            if url not in raw_results_map:
                                raw_results_map[url] = []
                            result['task_stat_key'] = stat_key
                            result['params_used'] = engine_stats[stat_key]['params']
                            result['query_used'] = engine_stats[stat_key]['query']
                            raw_results_map[url].append(result)

            except Exception as e:
                 logger.error(f"Error processing result for task key {stat_key}: {e}")
                 if stat_key in engine_stats:
                      engine_stats[stat_key]['status'] = 'processing_error'
                      engine_stats[stat_key]['error'] = str(e)

        # Assess language match and deduplicate
        logger.info(f"Assessing language match for {len(raw_results_map)} unique URLs...")
        scored_results = []
        processed_urls = set()

        for url, results_group in raw_results_map.items():
            if url in processed_urls: 
                continue

            best_result = results_group[0]
            lang_score = self._assess_language_match(best_result, lang_code, common_phrases)
            best_result['language_score'] = lang_score

            # Aggregate info from all variations
            sources = set()
            variations = set()
            params_list = []
            queries_list = set()
            for r in results_group:
                 sources.add(r.get('source', 'unknown_source'))
                 variations.add(r.get('task_stat_key', 'unknown_variation'))
                 params_list.append(r.get('params_used', {}))
                 queries_list.add(r.get('query_used', ''))

            best_result['sources'] = sorted(list(sources))
            best_result['found_by_variations'] = sorted(list(variations))
            best_result['params_used_list'] = params_list
            best_result['queries_used_list'] = sorted(list(queries_list))

            # Cleanup
            best_result.pop('task_stat_key', None)
            best_result.pop('params_used', None)
            best_result.pop('query_used', None)

            scored_results.append(best_result)
            processed_urls.add(url)

            # Update stats
            for variation_key in variations:
                 if variation_key in engine_stats:
                     engine_stats[variation_key]['unique_added'] = engine_stats[variation_key].get('unique_added', 0) + 1

        # Sort by language score
        scored_results.sort(key=lambda x: x.get('language_score', 0), reverse=True)

        # Build output
        output_data = {
            'query': query,
            'language_code': lang_code,
            'language_name': target_language_name,
            'timestamp': datetime.now().isoformat(),
            'search_type': 'language',
            'total_unique_results': len(scored_results),
            'engine_stats': engine_stats,
            'results': scored_results
        }

        self.save_results(output_data)
        return output_data

    def _assess_language_match(self, result: Dict, lang_code: str, common_phrases: List[str]) -> float:
        """Assess how likely the result is in the target language."""
        score = 0.0
        if lang_code not in LANGUAGE_DATA:
            return score

        lang_info = LANGUAGE_DATA[lang_code]
        text_content = ' '.join([
            result.get('title', ''),
            result.get('snippet', result.get('description', ''))
        ]).lower()

        # Check for common words
        if common_phrases and text_content:
            found_words = sum(1 for word in common_phrases[:5] if f' {word} ' in f' {text_content} ')
            if found_words > 0:
                 score += min(found_words / 3, 1.0) * 0.3

        # Check URL TLD and path for language/region codes
        url = result.get('url', '').lower()
        if url:
            try:
                parsed_url = urlparse(url)
                domain = parsed_url.netloc
                path = parsed_url.path

                # Check primary region TLD
                if lang_info.get('regions'):
                    primary_tld = '.' + lang_info['regions'][0].lower()
                    if domain.endswith(primary_tld) and len(primary_tld) == 3:
                        score += 0.4

                # Check for lang code in path or subdomain
                lang_patterns = [f'/{lang_code}/', f'/{lang_code}-']
                if lang_code in REGION_VARIANT_MAP:
                     for region in REGION_VARIANT_MAP[lang_code]:
                          variant_code = REGION_VARIANT_MAP[lang_code][region].get('bing_mkt', '').lower()
                          if variant_code:
                               lang_patterns.append(f'/{variant_code}/')

                subdomain_pattern = f'{lang_code}.'

                if any(p in path for p in lang_patterns) or domain.startswith(subdomain_pattern):
                    score += 0.3

            except Exception as e:
                logger.warning(f"URL parsing failed for {url}: {e}")

        return min(score, 1.0)

    async def _search_with_site_module(self, query: str, tld: str, max_results: int) -> Dict:
        """Use site module for TLD-based language searches."""
        stat_key = f"site_module_tld_{tld}"
        output = {
            'stat_key': stat_key,
            'engine_name': 'site_module',
            'results': [],
            'params_used': {'tld': tld},
            'query_used': f'{query} site:.{tld}',
            'error': None
        }
        
        try:
            # Search by TLD
            results = await self.site_search.search_by_tld(query, tld, max_results)
            
            # Convert results to expected format
            all_results = []
            for engine, urls in results.items():
                for url in urls:
                    all_results.append({
                        'url': url,
                        'title': f"{query} - {tld.upper()} domain search",
                        'snippet': f"Found on .{tld} domain via {engine}",
                        'source': 'site_module'
                    })
            
            output['results'] = all_results
            logger.info(f"Site module (TLD {tld}): Found {len(all_results)} results")
            
        except Exception as e:
            logger.error(f"Error in site module search: {e}")
            output['error'] = str(e)
        
        return output

    async def _search_engine(self, engine, engine_name: str, query: str,
                           search_params: Dict, max_results: int, stat_key: str) -> Dict:
        """Executes search for a specific engine with given parameters."""
        output = {
            'stat_key': stat_key,
            'engine_name': engine_name,
            'results': [],
            'params_used': search_params,
            'query_used': query,
            'error': None
        }
        logger.debug(f"Executing {engine_name} search ({stat_key}). Query: '{query}', Params: {search_params}")
        
        try:
            # Use the search method from our self-contained runners
            search_method = getattr(engine, 'search', None)
            if not search_method or not callable(search_method):
                 raise NotImplementedError(f"Engine '{engine_name}' does not have a compatible 'search' method.")

            # Try to pass language parameters if the engine supports them
            if search_params and hasattr(search_method, '__code__'):
                # Check if the search method accepts additional parameters
                import inspect
                sig = inspect.signature(search_method)
                
                # Build kwargs based on what the method accepts
                kwargs = {'max_results': max_results}
                
                # Add language parameters if supported
                for param_name, param_value in search_params.items():
                    if param_name in sig.parameters:
                        kwargs[param_name] = param_value
                    elif engine_name == 'bing' and param_name == 'mkt':
                        # Bing specifically uses 'mkt' parameter
                        kwargs['mkt'] = param_value
                    elif engine_name == 'google' and param_name in ['hl', 'lr', 'cr', 'gl']:
                        # Google uses these language parameters
                        kwargs[param_name] = param_value
                    elif engine_name == 'yandex' and param_name in ['lr', 'lang']:
                        # Yandex uses these language parameters
                        kwargs[param_name] = param_value
                    elif engine_name == 'brave' and param_name in ['search_lang', 'country']:
                        # Brave uses these language parameters
                        kwargs[param_name] = param_value
                    elif engine_name == 'duckduckgo' and param_name == 'kl':
                        # DuckDuckGo uses 'kl' for region/language
                        kwargs[param_name] = param_value
                
                logger.debug(f"Calling {engine_name} search with language params: {kwargs}")
                results = search_method(query, **kwargs)
            else:
                # Fallback to basic search
                logger.debug(f"Using basic search for {engine_name} (no language param support)")
                results = search_method(query, max_results=max_results)

            if results is None: 
                results = []

            # Add source metadata
            for r in results:
                 r['source'] = engine_name

            output['results'] = results
            logger.info(f"{engine_name.title()} ({stat_key}): Found {len(results)} results.")

        except Exception as e:
            logger.error(f"Error in {engine_name} ({stat_key}) search: {e}")
            output['error'] = str(e)

        return output

    def save_results(self, data: Dict):
        """Save language search results to a JSON file."""
        results_dir = "search_results"
        os.makedirs(results_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_query = "".join(c if c.isalnum() else "_" for c in data['query'])[:50]
        lang_code = data['language_code']
        filename = f"lang_search_{safe_query}_{lang_code}_{timestamp}.json"
        filepath = os.path.join(results_dir, filename)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"\nSaved language search results to {filepath}")
        except Exception as e:
            print(f"Error saving language search results to {filepath}: {e}")

def main():
    """Main entry point for language search"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Language-specific search across multiple engines')
    parser.add_argument('query', help='Search query')
    parser.add_argument('lang_code', help='Language code (e.g., en, de, fr, es, it)')
    parser.add_argument('-o', '--output', help='Output JSON file')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    # Set up logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    async def run_search():
        searcher = LanguageSearcher()
        
        if args.lang_code not in LANGUAGE_DATA:
            logger.error(f"Error: Language code '{args.lang_code}' not supported.")
            logger.info(f"Available languages: {', '.join(sorted(LANGUAGE_DATA.keys()))}")
            return
        
        results_data = await searcher.search_language(args.query, args.lang_code)
        
        if 'error' in results_data:
            logger.error(f"Error: {results_data['error']}")
            return
        
        lang_name = LANGUAGE_DATA[args.lang_code]['name']
        logger.info(f"\n🌍 Language search results for '{args.query}' in {lang_name}")
        logger.info(f"📊 Found {results_data['total_unique_results']} unique results")
        
        # Show top results
        for i, result in enumerate(results_data['results'][:10], 1):
            logger.info(f"\n{i}. [{', '.join(result.get('sources', ['N/A']))}] {result.get('title', 'No Title')}")
            logger.info(f"   🔗 URL: {result.get('url', 'N/A')}")
            logger.info(f"   🎯 Language Score: {result.get('language_score', 0):.2f}")
            snippet = result.get('snippet', result.get('description', ''))
            if snippet:
                if isinstance(snippet, list): 
                    snippet = snippet[0] if snippet else ''
                snippet = str(snippet)
                snippet = snippet[:200] + '...' if len(snippet) > 200 else snippet
                logger.info(f"   📝 Snippet: {snippet}")
        
        # Save to file if specified
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(results_data, f, indent=2)
            logger.info(f"\n💾 Results saved to: {args.output}")
    
    asyncio.run(run_search())

if __name__ == "__main__":
    main()