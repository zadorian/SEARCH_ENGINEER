#!/usr/bin/env python3
"""
Language NOT Search - Integrated Language Exclusion System

Handles -lang:XX operator to exclude a language from results.
Example: -lang:en → Exclude all English results, search in other major languages

Three-tier approach (L1/L2/L3):
- L1 (Native): Use engine-native language params + negative fillers
- L2 (Creative): L1 + translated keywords + cross-language search
- L3 (Brute): L2 + maximum recall with post-filtering

Uses GPT-5-mini for dynamic filler word generation in concert with lang.py

Key capabilities:
- Native NOT operators: Google (-"word"), Bing (NOT "word"), Archive.org, etc.
- Negative filler injection: -"usually", -"about", -"and" for excluded language
- Active search in other languages with positive fillers
- Result filtering by detected language
"""

import asyncio
import logging
import re
import json
from typing import Dict, List, Any, Optional, Tuple, Set
from pathlib import Path
import sys
import os
from datetime import datetime

# Setup paths
parent_dir = Path(__file__).parent.parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

# Import existing modules
from .language import (
    LanguageSearcher,
    LANGUAGE_DATA,
    LANG_CODE_MAP,
    ENGINE_PARAM_MAP,
    generate_common_phrases_for_language,
    BRIGHTDATA_AVAILABLE,
)

# BrightData Archive - native support for -lang{}! via language_blacklist
if BRIGHTDATA_AVAILABLE:
    try:
        from backdrill.brightdata import BrightDataArchive
    except ImportError:
        BRIGHTDATA_AVAILABLE = False

# Import NOT search capabilities
try:
    from ..logic.NOT import NOTSearcher
    NOT_AVAILABLE = True
except ImportError:
    try:
        from brute.logic.NOT import NOTSearcher
        NOT_AVAILABLE = True
    except ImportError:
        NOT_AVAILABLE = False

# Import brute search engine
try:
    from brute.infrastructure.brute import BruteSearchEngine, ENGINE_CONFIG
    BRUTE_AVAILABLE = True
except ImportError:
    try:
        from ...infrastructure.brute import BruteSearchEngine, ENGINE_CONFIG
        BRUTE_AVAILABLE = True
    except ImportError:
        BRUTE_AVAILABLE = False
        ENGINE_CONFIG = {}

# Import AI for dynamic generation
try:
    from TOOLS.openai_chatgpt import chat_sync, analyze
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False

logger = logging.getLogger(__name__)

# ============================================================================
# NEGATIVE FILLER WORDS - Common words to exclude for each language
# ============================================================================
# These are high-frequency words that strongly indicate content in that language
# Using these with - operator dramatically reduces results in that language

NEGATIVE_FILLERS: Dict[str, List[str]] = {
    # English - most common web language, need strong exclusion
    "en": [
        "usually", "about", "however", "therefore", "although",
        "the", "and", "for", "with", "this", "that", "from",
        "more", "also", "such", "been", "have", "will"
    ],
    # German
    "de": [
        "jedoch", "allerdings", "deswegen", "außerdem", "deshalb",
        "und", "der", "die", "das", "mit", "für", "über",
        "auch", "noch", "wird", "sind", "haben"
    ],
    # French
    "fr": [
        "cependant", "toutefois", "également", "notamment", "ainsi",
        "le", "la", "les", "et", "de", "pour", "avec",
        "aussi", "plus", "sont", "cette", "être"
    ],
    # Spanish
    "es": [
        "sin embargo", "además", "también", "aunque", "por tanto",
        "el", "la", "los", "y", "de", "para", "con",
        "más", "como", "sobre", "esta", "tiene"
    ],
    # Italian
    "it": [
        "tuttavia", "inoltre", "pertanto", "comunque", "quindi",
        "il", "la", "i", "e", "di", "per", "con",
        "anche", "sono", "dalla", "questa", "essere"
    ],
    # Portuguese
    "pt": [
        "no entanto", "além disso", "portanto", "contudo", "assim",
        "o", "a", "os", "e", "de", "para", "com",
        "também", "mais", "sobre", "esta", "são"
    ],
    # Dutch
    "nl": [
        "echter", "daarom", "bovendien", "hoewel", "aldus",
        "en", "de", "het", "van", "met", "voor", "over",
        "ook", "zijn", "wordt", "deze", "hebben"
    ],
    # Russian
    "ru": [
        "однако", "поэтому", "кроме того", "также", "таким образом",
        "и", "в", "на", "с", "для", "о", "по",
        "это", "что", "как", "или", "было"
    ],
    # Chinese
    "zh": [
        "但是", "因此", "而且", "虽然", "所以",
        "的", "是", "在", "和", "了", "有", "我",
        "这", "为", "与", "不", "也"
    ],
    # Japanese
    "ja": [
        "しかし", "そのため", "また", "ただし", "それでも",
        "の", "は", "を", "に", "が", "と", "で",
        "も", "から", "まで", "ない", "ある"
    ],
    # Hungarian
    "hu": [
        "azonban", "ezért", "továbbá", "ugyanakkor", "tehát",
        "és", "a", "az", "van", "hogy", "nem", "meg",
        "is", "már", "csak", "mint", "vagy"
    ],
    # Polish
    "pl": [
        "jednak", "dlatego", "ponadto", "również", "zatem",
        "i", "w", "na", "z", "dla", "o", "do",
        "to", "nie", "się", "jest", "co"
    ],
    # Turkish
    "tr": [
        "ancak", "bu nedenle", "ayrıca", "bununla birlikte", "dolayısıyla",
        "ve", "bir", "bu", "için", "ile", "da", "de",
        "gibi", "olan", "olarak", "kadar", "daha"
    ],
    # Arabic
    "ar": [
        "ومع ذلك", "لذلك", "بالإضافة", "كذلك", "وبالتالي",
        "و", "في", "من", "على", "إلى", "عن", "أن",
        "هذا", "التي", "هو", "كان", "بين"
    ]
}

# Major alternative languages to search when one is excluded
ALTERNATIVE_LANGUAGES: Dict[str, List[str]] = {
    "en": ["de", "fr", "es", "it", "nl", "pt", "ru", "zh", "ja"],  # When excluding English
    "de": ["en", "fr", "nl", "it", "pl", "cs"],
    "fr": ["en", "de", "es", "it", "pt", "nl"],
    "es": ["en", "fr", "pt", "it", "de"],
    "it": ["en", "fr", "de", "es"],
    "ru": ["en", "de", "fr", "uk", "pl"],
    "zh": ["en", "ja", "ko", "de"],
    "ja": ["en", "zh", "ko", "de"],
    "pt": ["en", "es", "fr", "it"],
    "nl": ["en", "de", "fr"],
    "pl": ["en", "de", "cs", "ru"],
    "hu": ["en", "de", "sk", "ro"],
    "ar": ["en", "fr", "tr"],
    "tr": ["en", "de", "ar"]
}

# Engines with native language exclusion support
ENGINE_LANG_NOT_SUPPORT = {
    # Engine: (supports_native_lang_param, supports_NOT_operator, supports_minus_operator)
    "GO": (True, False, True),   # Google: lr param + -"word"
    "BI": (True, True, True),    # Bing: mkt param + NOT + -
    "BR": (True, False, True),   # Brave: search_lang + -"word"
    "YA": (True, False, True),   # Yandex: lang param + -"word"
    "DD": (True, False, True),   # DuckDuckGo: kl param + -"word"
    "PX": (True, False, False),  # Perplexity: search_language_filter (array)
    "YO": (True, False, False),  # You.com: country param
    "EX": (False, False, False), # Exa: excludeText param (different)
    "AR": (True, True, True),    # Archive.org: NOT + -
    "FC": (False, False, False), # Firecrawl: no native support
    "GD": (True, False, True),   # GDELT: lang filter + -
}


async def generate_negative_fillers_gpt(
    lang_code: str,
    query: str = "",
    count: int = 8
) -> List[str]:
    """
    Generate negative filler words using GPT-5-mini.
    These are common words that strongly indicate content in the target language.
    """
    if not AI_AVAILABLE:
        # Fallback to static list
        return NEGATIVE_FILLERS.get(lang_code, [])[:count]

    lang_name = LANGUAGE_DATA.get(lang_code, {}).get("name", lang_code.upper())

    prompt = f"""Generate {count} common words in {lang_name} that appear frequently in web content.
Focus on:
1. Conjunctions and connectors (and, but, however, therefore)
2. Articles and pronouns (the, a, this, that)
3. Common verbs (is, are, have, will)
4. Prepositions (in, on, for, with)

These should be high-frequency words that STRONGLY indicate content is in {lang_name}.
Return ONLY the words in {lang_name}, one per line, no translations or explanations.
{"Context: searching for: " + query if query else ""}"""

    try:
        response = chat_sync(
            prompt,
            system="You are a linguistic expert. Output only words in the target language, one per line.",
            model="gpt-5-mini"  # Fast, cheap, good for this task
        )

        words = [line.strip() for line in response.strip().split('\n') if line.strip()]
        logger.info(f"GPT-5-mini generated {len(words)} negative fillers for {lang_code}: {words[:5]}...")
        return words[:count]

    except Exception as e:
        logger.error(f"GPT-5-mini filler generation failed: {e}")
        return NEGATIVE_FILLERS.get(lang_code, [])[:count]


class LanguageNOTSearcher:
    """
    Integrated language exclusion search system.

    Handles -lang:XX operator with three tiers:
    - L1: Native engine params + negative fillers
    - L2: L1 + translated keywords + cross-language search
    - L3: L2 + brute force + post-filtering
    """

    def __init__(self, max_results_per_engine: int = 100):
        self.max_results = max_results_per_engine
        self.language_searcher = LanguageSearcher()
        self.not_searcher = NOTSearcher() if NOT_AVAILABLE else None

        self.stats = {
            "excluded_language": None,
            "alternative_languages": [],
            "negative_fillers_used": [],
            "positive_fillers_used": {},
            "tier_results": {"L1": 0, "L2": 0, "L3": 0},
            "results_filtered": 0,
            "engines_used": []
        }

    async def search_not_language(
        self,
        query: str,
        exclude_lang: str,
        tier: str = "L3"  # L1, L2, or L3
    ) -> Dict[str, Any]:
        """
        Main entry point for -lang:XX searches.

        Args:
            query: Search query (without the -lang:XX operator)
            exclude_lang: Language code to exclude (e.g., "en")
            tier: L1 (native only), L2 (creative), L3 (full brute)

        Returns:
            Results with excluded language filtered out
        """
        start_time = datetime.now()
        exclude_lang = exclude_lang.lower()

        logger.info(f"🚫 Starting -lang:{exclude_lang} search: {query}")
        logger.info(f"   Tier: {tier}")

        self.stats["excluded_language"] = exclude_lang

        # Get alternative languages to search in
        alt_langs = ALTERNATIVE_LANGUAGES.get(exclude_lang, ["de", "fr", "es", "it"])[:5]
        self.stats["alternative_languages"] = alt_langs
        logger.info(f"   Alternative languages: {alt_langs}")

        # Generate negative fillers for excluded language (async with GPT-5-mini)
        negative_fillers = await generate_negative_fillers_gpt(exclude_lang, query)
        self.stats["negative_fillers_used"] = negative_fillers
        logger.info(f"   Negative fillers for {exclude_lang}: {negative_fillers[:5]}...")

        all_results = []

        # ============================================================
        # TIER L1: Native engine params + negative fillers
        # ============================================================
        if tier in ["L1", "L2", "L3"]:
            l1_results = await self._tier_l1_native(query, exclude_lang, negative_fillers)
            all_results.extend(l1_results)
            self.stats["tier_results"]["L1"] = len(l1_results)
            logger.info(f"   L1 (Native): {len(l1_results)} results")

        # ============================================================
        # TIER L2: Creative - search in alternative languages
        # ============================================================
        if tier in ["L2", "L3"]:
            l2_results = await self._tier_l2_creative(query, alt_langs, exclude_lang)
            # Dedupe against L1
            existing_urls = {r.get("url") for r in all_results}
            l2_new = [r for r in l2_results if r.get("url") not in existing_urls]
            all_results.extend(l2_new)
            self.stats["tier_results"]["L2"] = len(l2_new)
            logger.info(f"   L2 (Creative): {len(l2_new)} new results")

        # ============================================================
        # TIER L3: Brute force + post-filtering
        # ============================================================
        if tier == "L3":
            l3_results = await self._tier_l3_brute(query, exclude_lang, negative_fillers)
            # Dedupe against L1+L2
            existing_urls = {r.get("url") for r in all_results}
            l3_new = [r for r in l3_results if r.get("url") not in existing_urls]
            all_results.extend(l3_new)
            self.stats["tier_results"]["L3"] = len(l3_new)
            logger.info(f"   L3 (Brute): {len(l3_new)} new results")

        # Deduplicate final results
        all_results = self._deduplicate(all_results)

        # Final language filtering
        filtered_results = self._filter_by_language(all_results, exclude_lang)
        self.stats["results_filtered"] = len(all_results) - len(filtered_results)

        execution_time = (datetime.now() - start_time).total_seconds()

        logger.info(f"✅ -lang:{exclude_lang} complete: {len(filtered_results)} results")
        logger.info(f"   Time: {execution_time:.2f}s")
        logger.info(f"   Filtered out: {self.stats['results_filtered']}")

        return {
            "query": query,
            "excluded_language": exclude_lang,
            "alternative_languages": alt_langs,
            "tier": tier,
            "results": filtered_results,
            "total_results": len(filtered_results),
            "execution_time_seconds": execution_time,
            "statistics": self.stats.copy()
        }

    async def _tier_l1_native(
        self,
        query: str,
        exclude_lang: str,
        negative_fillers: List[str]
    ) -> List[Dict]:
        """
        L1: Use native engine language params + negative filler operators.

        For engines that support it:
        - Google: -"usually" -"about" (with lr= to prefer other langs)
        - Bing: NOT "usually" NOT "about" (with mkt= param)
        - etc.
        """
        results = []

        for engine_code, (has_lang, has_NOT, has_minus) in ENGINE_LANG_NOT_SUPPORT.items():
            try:
                # Build engine-specific query with negative fillers
                engine_query = self._build_negative_query(
                    query,
                    negative_fillers[:4],  # Use top 4 fillers
                    engine_code,
                    has_NOT,
                    has_minus
                )

                logger.debug(f"L1 {engine_code}: {engine_query[:60]}...")

                # Build language exclusion params
                engine_params = self._build_exclusion_params(engine_code, exclude_lang)

                # Execute search (using existing infrastructure)
                # This would call the actual engine...
                # For now, placeholder that integrates with language.py
                engine_results = await self._execute_engine_search(
                    engine_code, engine_query, engine_params
                )

                for r in engine_results:
                    r["tier"] = "L1"
                    r["engine"] = engine_code
                    r["negative_fillers_used"] = negative_fillers[:4]

                results.extend(engine_results)
                self.stats["engines_used"].append(engine_code)

            except Exception as e:
                logger.error(f"L1 {engine_code} failed: {e}")

        return results

    async def _tier_l2_creative(
        self,
        query: str,
        alt_langs: List[str],
        exclude_lang: str
    ) -> List[Dict]:
        """
        L2: Search actively in alternative languages with positive fillers.

        For each alternative language:
        - Add positive filler words (common words in that language)
        - Use native language params
        - Tag results with detected language
        """
        results = []

        for lang in alt_langs[:3]:  # Top 3 alternative languages
            try:
                # Get positive fillers for this language
                positive_fillers = await generate_common_phrases_for_language(
                    LANGUAGE_DATA.get(lang, {}).get("name", lang),
                    query
                )

                if not positive_fillers:
                    positive_fillers = list(LANG_CODE_MAP.get(lang, {}).keys())[:5]

                self.stats["positive_fillers_used"][lang] = positive_fillers[:3]

                # Build positive query: query + (filler1 OR filler2)
                filler_group = " OR ".join([f'"{f}"' for f in positive_fillers[:3]])
                enhanced_query = f'{query} ({filler_group})'

                logger.debug(f"L2 {lang}: {enhanced_query[:60]}...")

                # Use language searcher for this language
                lang_results = await self.language_searcher.search_language(
                    query, lang, max_results_per_engine=self.max_results // len(alt_langs)
                )

                for r in lang_results.get("results", []):
                    r["tier"] = "L2"
                    r["target_language"] = lang
                    r["positive_fillers_used"] = positive_fillers[:3]

                results.extend(lang_results.get("results", []))

            except Exception as e:
                logger.error(f"L2 {lang} failed: {e}")

        return results

    async def _tier_l3_brute(
        self,
        query: str,
        exclude_lang: str,
        negative_fillers: List[str]
    ) -> List[Dict]:
        """
        L3: Maximum recall with post-filtering.

        Run brute search without language constraints, then filter out
        results in the excluded language based on:
        - URL TLD
        - Snippet language detection
        - Presence of language-specific words
        """
        results = []

        if not self.not_searcher:
            logger.warning("NOT searcher not available for L3")
            return results

        try:
            # Build NOT query with negative fillers
            not_terms = " ".join([f'-"{f}"' for f in negative_fillers[:6]])
            brute_query = f'{query} {not_terms}'

            logger.debug(f"L3 Brute: {brute_query[:80]}...")

            # Run NOT search (uses all free engines + filtering)
            not_results = await self.not_searcher.search_not(brute_query)

            for r in not_results.get("results", []):
                r["tier"] = "L3"

            results.extend(not_results.get("results", []))

        except Exception as e:
            logger.error(f"L3 brute search failed: {e}")

        return results

    def _build_negative_query(
        self,
        query: str,
        fillers: List[str],
        engine_code: str,
        use_NOT: bool,
        use_minus: bool
    ) -> str:
        """Build query with negative filler operators."""

        if use_NOT and engine_code in ["BI", "AR"]:
            # Bing, Archive.org prefer NOT operator
            negations = " ".join([f'NOT "{f}"' for f in fillers])
        elif use_minus:
            # Most engines use -"word"
            negations = " ".join([f'-"{f}"' for f in fillers])
        else:
            # No negation support
            return query

        return f"{query} {negations}"

    def _build_exclusion_params(self, engine_code: str, exclude_lang: str) -> Dict:
        """
        Build engine-specific params that EXCLUDE a language.

        Note: Most engines only support INCLUDE params, not EXCLUDE.
        We work around this by preferring alternative languages.
        """
        params = {}

        # Get alternative language to prefer instead
        alt_lang = ALTERNATIVE_LANGUAGES.get(exclude_lang, ["de"])[0]

        if engine_code == "GO":
            # Google: prefer alternative language
            params["lr"] = f"lang_{alt_lang}"
            params["hl"] = alt_lang
        elif engine_code == "BI":
            # Bing: set market to alternative
            region = LANG_CODE_MAP.get(alt_lang, {}).get("bing_mkt", "de-DE")
            params["mkt"] = region
        elif engine_code == "BR":
            # Brave
            params["search_lang"] = alt_lang
        elif engine_code == "DD":
            # DuckDuckGo
            params["kl"] = f"{alt_lang}-{alt_lang}"
        elif engine_code == "PX":
            # Perplexity: can actually EXCLUDE with array
            all_langs = list(LANGUAGE_DATA.keys())
            params["search_language_filter"] = [l for l in all_langs if l != exclude_lang][:10]

        return params

    async def _execute_engine_search(
        self,
        engine_code: str,
        query: str,
        params: Dict
    ) -> List[Dict]:
        """Execute search on a specific engine with params."""
        if not BRUTE_AVAILABLE:
            logger.warning(f"BruteSearchEngine not available, skipping {engine_code}")
            return []

        try:
            # Create brute searcher instance
            brute = BruteSearchEngine(keyword=query)

            # Execute search with specific engine
            results_data = await brute.search_multiple_engines(
                query,
                engines=[engine_code],
                max_results_per_engine=self.max_results // 5,  # Spread quota
                **params  # Pass language params
            )

            results = results_data.get('results', [])
            logger.debug(f"Engine {engine_code} returned {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Engine {engine_code} search failed: {e}")
            return []

    def _filter_by_language(
        self,
        results: List[Dict],
        exclude_lang: str
    ) -> List[Dict]:
        """
        Post-filter results to remove items in the excluded language.

        Detection methods:
        1. URL TLD (.com, .co.uk, .de, etc.)
        2. Presence of language-specific words in snippet/title
        3. Explicit language tag if available
        """
        filtered = []
        excluded_tlds = self._get_tlds_for_language(exclude_lang)
        excluded_words = set(NEGATIVE_FILLERS.get(exclude_lang, [])[:10])

        for result in results:
            url = result.get("url", "").lower()
            text = f"{result.get('title', '')} {result.get('snippet', '')}".lower()

            # Check 1: URL TLD
            tld_match = any(url.endswith(tld) or f".{tld}/" in url for tld in excluded_tlds)

            # Check 2: Language words in text
            word_count = sum(1 for word in excluded_words if f" {word} " in f" {text} ")
            high_word_match = word_count >= 3

            # Check 3: Explicit language tag
            result_lang = result.get("lang", result.get("language", ""))
            explicit_match = result_lang.lower() == exclude_lang

            # Exclude if strong signals for excluded language
            if explicit_match or (tld_match and high_word_match):
                logger.debug(f"Filtering out: {url[:50]} (lang={exclude_lang})")
                continue

            filtered.append(result)

        return filtered

    def _get_tlds_for_language(self, lang_code: str) -> List[str]:
        """Get TLDs associated with a language."""
        tld_map = {
            "en": [".com", ".co.uk", ".org", ".net", ".us", ".io"],
            "de": [".de", ".at", ".ch"],
            "fr": [".fr", ".be", ".ch", ".ca"],
            "es": [".es", ".mx", ".ar", ".co"],
            "it": [".it"],
            "pt": [".pt", ".br"],
            "nl": [".nl", ".be"],
            "ru": [".ru", ".by"],
            "zh": [".cn", ".tw", ".hk"],
            "ja": [".jp"],
            "ko": [".kr"],
            "pl": [".pl"],
            "hu": [".hu"],
            "tr": [".tr"],
            "ar": [".sa", ".ae", ".eg"]
        }
        return tld_map.get(lang_code, [])

    def _deduplicate(self, results: List[Dict]) -> List[Dict]:
        """Remove duplicate results by URL."""
        seen = set()
        unique = []
        for r in results:
            url = r.get("url", "")
            if url and url not in seen:
                seen.add(url)
                unique.append(r)
        return unique


# ============================================================================
# CLI Interface
# ============================================================================

async def main():
    """CLI for testing -lang:XX searches."""
    import argparse

    parser = argparse.ArgumentParser(description='-lang:XX Language Exclusion Search')
    parser.add_argument('query', help='Search query')
    parser.add_argument('-l', '--exclude-lang', required=True,
                       help='Language code to exclude (e.g., en, de, fr)')
    parser.add_argument('-t', '--tier', choices=['L1', 'L2', 'L3'], default='L3',
                       help='Search tier (L1=native, L2=creative, L3=brute)')
    parser.add_argument('-m', '--max-results', type=int, default=100,
                       help='Max results per engine')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Verbose output')

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    searcher = LanguageNOTSearcher(max_results_per_engine=args.max_results)

    results = await searcher.search_not_language(
        args.query,
        args.exclude_lang,
        tier=args.tier
    )

    print(f"\n🚫 -lang:{args.exclude_lang} Search Results")
    print("=" * 60)
    print(f"Query: {results['query']}")
    print(f"Excluded: {results['excluded_language']}")
    print(f"Alternatives searched: {', '.join(results['alternative_languages'])}")
    print(f"Tier: {results['tier']}")
    print(f"Total results: {results['total_results']}")
    print(f"Time: {results['execution_time_seconds']:.2f}s")

    stats = results['statistics']
    print(f"\nTier breakdown:")
    print(f"  L1 (Native): {stats['tier_results']['L1']}")
    print(f"  L2 (Creative): {stats['tier_results']['L2']}")
    print(f"  L3 (Brute): {stats['tier_results']['L3']}")
    print(f"  Filtered out: {stats['results_filtered']}")

    print(f"\nNegative fillers used: {stats['negative_fillers_used'][:5]}")

    print(f"\nTop 10 results:")
    for i, r in enumerate(results['results'][:10], 1):
        print(f"\n{i}. [{r.get('tier', '?')}] {r.get('title', 'No title')[:60]}")
        print(f"   {r.get('url', 'No URL')[:80]}")
        if r.get('target_language'):
            print(f"   Language: {r['target_language']}")


if __name__ == "__main__":
    asyncio.run(main())
