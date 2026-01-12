#!/usr/bin/env python3
"""
BruteSearch Bridge - Python wrapper for calling Node.js BruteSearch

This bridge allows RuleExecutor to use BruteSearch for rules that require
web search capabilities across 40+ engines with deduplication and streaming.

Usage:
    bridge = BruteSearchBridge()
    results = await bridge.search("Podravka d.d. officers", engines=["GO", "BR"])
    news = await bridge.news_search("Podravka d.d. sanctions")
    person = await bridge.person_search("John Smith", location="US")

Architecture:
- Calls Node.js BruteSearch API at /api/search/stream/brute
- Streams results via Server-Sent Events (SSE)
- Returns standardized results compatible with RuleExecutor
- Supports all BruteSearch options (mode, engines, wave configs, etc.)

Integration with RuleExecutor:
Rules in rules.json can specify:
    {
        "id": "web_search_news",
        "type": "brute_search",
        "config": {
            "mode": "speed",
            "engines": ["GN", "GD", "NW"],  // News engines only
            "timeoutSeconds": 60
        },
        "query_template": "\"{company_name}\" sanctions OR penalties"
    }

Engine Codes (Tier 1):
- GO: Google (instant)
- BI: Bing
- BR: Brave
- YA: Yahoo
- PX: Perplexity (AI)
- EX: Exa (AI)
- AR: Archive.org
- GK: Grok (AI)
- YO: You.com (AI)
- FC: Firecrawl (deep scraping)
- GS: Google SERP API
- GN: Google News SERP API
- GF: Google Forums SERP API
- KG: Knowledge Graph

Engine Codes (Tier 2 - Specialized):
- NW: NewsAPI
- GD: GDELT News
- CR: Crossref (academic)
- PM: PubMed (medical)
- OA: OpenAlex (academic)
- SS: Semantic Scholar
- AR: arXiv
- AA: Anna's Archive (books)
- LG: Library Genesis
- WL: WikiLeaks
- SI: Social Searcher
"""

import asyncio
import aiohttp
import json
import os
from typing import Dict, List, Any, Optional, Literal
from pathlib import Path
from datetime import datetime


class BruteSearchBridge:
    """Bridge for RuleExecutor to call BruteSearch."""

    def __init__(self, api_base: str = None):
        """Initialize BruteSearch bridge.

        Args:
            api_base: Base URL for Node.js server (default: from NODE_SERVER_URL env or http://localhost:3000)
        """
        self.api_base = api_base or os.environ.get('NODE_SERVER_URL', 'http://localhost:3000')
        self._session: Optional[aiohttp.ClientSession] = None

        # Engine category mappings for specialized searches
        self.ENGINE_CATEGORIES = {
            "news": ["GN", "GD", "NW"],  # Google News, GDELT, NewsAPI
            "academic": ["AR", "CR", "PM", "OA", "SS", "JS", "NA", "MU"],  # arXiv, Crossref, PubMed, etc.
            "social": ["TW", "FB", "RD", "SI", "FBP"],  # Twitter, Facebook, Reddit, Social Searcher
            "legal": ["WL"],  # WikiLeaks
            "books": ["AA", "LG", "OL", "GB", "AO"],  # Anna's Archive, LibGen, OpenLibrary
            "archives": ["AR", "AO", "WB"],  # Archive.org, Archive.org Files, Wayback
            "ai": ["PX", "GK", "YO", "EX"],  # Perplexity, Grok, You.com, Exa
            "core": ["GO", "BI", "BR", "YA"],  # Google, Bing, Brave, Yahoo
            "serp": ["GS", "SP", "SPBI", "GF", "GN", "YL", "KG", "NV", "YAS"],  # SERP API engines
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=600)  # 10 minute timeout
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        """Close aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def search(
        self,
        query: str,
        engines: Optional[List[str]] = None,
        mode: Literal["speed", "balanced", "exhaustive"] = "balanced",
        max_results: int = 10000,
        timeout_seconds: int = 180,
        include_keyword_variations: bool = False,
        include_linklater_enrichment: bool = False,
        include_template_engines: bool = True,
        template_engine_limit: int = 30,
        geo: Optional[str] = None,
        language: Optional[str] = None,
        news_categories: Optional[List[str]] = None,
        news_countries: Optional[List[str]] = None,
        news_languages: Optional[List[str]] = None,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """Execute BruteSearch and return results.

        Args:
            query: Search query string
            engines: Optional list of engine codes to use (e.g., ["GO", "BR"])
            mode: Execution mode - "speed" (fast), "balanced", "exhaustive" (all engines)
            max_results: Maximum results per engine (default: 10000)
            timeout_seconds: Global timeout in seconds (default: 180)
            include_keyword_variations: Include Wayback + CC keyword variations
            include_linklater_enrichment: Scrape and enrich top results with entities/links
            include_template_engines: Include 20K+ URL template engines from ES
            template_engine_limit: Max template engines to use (default: 30)
            geo: Geographic filter (country code, e.g., "US")
            language: Language filter (e.g., "en")
            news_categories: News categories for news engines (e.g., ["business", "tech"])
            news_countries: News countries filter (e.g., ["us", "uk"])
            news_languages: News languages filter (e.g., ["en"])
            progress_callback: Optional callback(event_type, data) for streaming progress

        Returns:
            {
                "type": "brute_search",
                "query": str,
                "success": bool,
                "results_count": int,
                "unique_count": int,
                "results": [
                    {
                        "url": str,
                        "title": str,
                        "snippet": str,
                        "engine": str,
                        "engines": [str],  # All engines that found this result
                        "score": float,
                        "publishedDate": str (optional),
                        "raw": {...}
                    }
                ],
                "metadata": {
                    "enginesUsed": [str],
                    "successfulEngines": int,
                    "failedEngines": int,
                    "timeElapsed": int,
                    "deduplicationRate": float,
                    "tier1Results": int,
                    "tier2Results": int,
                    "multiHitResults": int,
                    "avgSourcesPerResult": float,
                    "waveStats": [...],
                    "categoryBreakdown": {...}
                }
            }
        """
        session = await self._get_session()

        # Build query parameters
        params = {
            'query': query,
            'maxResults': max_results,
            'timeoutSeconds': timeout_seconds,
            'mode': mode
        }

        # Add optional parameters
        if geo:
            params['geo'] = geo
        if language:
            params['language'] = language
        if news_categories:
            params['newsCategories'] = ','.join(news_categories)
        if news_countries:
            params['newsCountries'] = ','.join(news_countries)
        if news_languages:
            params['newsLanguages'] = ','.join(news_languages)
        if engines:
            params['engines'] = ','.join(engines)

        # BruteSearch-specific options
        params['includeKeywordVariations'] = str(include_keyword_variations).lower()
        params['includeLinklaterEnrichment'] = str(include_linklater_enrichment).lower()
        params['includeTemplateEngines'] = str(include_template_engines).lower()
        params['templateEngineLimit'] = str(template_engine_limit)

        # Streaming endpoint
        url = f"{self.api_base}/api/search/stream/brute"

        try:
            # Call the streaming endpoint and consume all events
            results = []
            engines_used = []
            metadata = {}
            last_error = None

            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    return {
                        'type': 'brute_search',
                        'query': query,
                        'success': False,
                        'error': f'BruteSearch API returned {resp.status}: {error_text}',
                        'url': url,
                        'params': params
                    }

                # Parse SSE stream
                async for line in resp.content:
                    line_str = line.decode('utf-8').strip()

                    # SSE format: "data: {...}"
                    if line_str.startswith('data: '):
                        try:
                            data = json.loads(line_str[6:])  # Remove "data: " prefix
                            event_type = data.get('type')

                            # Call progress callback if provided
                            if progress_callback:
                                try:
                                    progress_callback(event_type, data)
                                except Exception as e:
                                    print(f"Warning: Progress callback failed: {e}")

                            if event_type == 'result':
                                # New results from an engine
                                new_results = data.get('results', [])
                                results.extend(new_results)

                            elif event_type == 'engine_status':
                                # Engine completed
                                engine_code = data.get('engineCode')
                                if engine_code and engine_code not in engines_used:
                                    engines_used.append(engine_code)

                            elif event_type == 'complete':
                                # Search complete
                                metadata = data.get('metadata', {})
                                break

                            elif event_type == 'error':
                                last_error = data.get('message', 'Unknown error')
                                # Don't break - may have partial results

                        except json.JSONDecodeError as e:
                            # Skip malformed lines
                            continue

            # If we got an error but no results, return error
            if last_error and not results:
                return {
                    'type': 'brute_search',
                    'query': query,
                    'success': False,
                    'error': last_error,
                    'engines_used': engines_used
                }

            return {
                'type': 'brute_search',
                'query': query,
                'success': True,
                'engines': engines or [],  # Requested engines
                'engines_used': engines_used,  # Actually executed engines
                'mode': mode,
                'results_count': len(results),
                'unique_count': metadata.get('uniqueCount', len(results)),
                'results': results,
                'metadata': metadata,
                'url': url,
                'params': params
            }

        except asyncio.TimeoutError:
            return {
                'type': 'brute_search',
                'query': query,
                'success': False,
                'error': f'Request timed out after {timeout_seconds} seconds',
                'timeout': True
            }
        except Exception as e:
            return {
                'type': 'brute_search',
                'query': query,
                'success': False,
                'error': f'BruteSearch failed: {str(e)}',
                'exception': type(e).__name__
            }

    async def news_search(
        self,
        query: str,
        categories: Optional[List[str]] = None,
        countries: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        max_results: int = 1000,
        timeout_seconds: int = 60
    ) -> Dict[str, Any]:
        """Search news sources specifically.

        Args:
            query: Search query
            categories: News categories (e.g., ["business", "tech", "politics"])
            countries: Country codes (e.g., ["us", "uk", "de"])
            languages: Language codes (e.g., ["en", "de"])
            max_results: Max results per engine
            timeout_seconds: Timeout in seconds

        Returns:
            Same structure as search(), filtered to news engines
        """
        return await self.search(
            query=query,
            engines=self.ENGINE_CATEGORIES["news"],
            mode="speed",  # News should be fast
            max_results=max_results,
            timeout_seconds=timeout_seconds,
            news_categories=categories,
            news_countries=countries,
            news_languages=languages,
            include_template_engines=True  # Include news site templates
        )

    async def person_search(
        self,
        name: str,
        location: Optional[str] = None,
        include_social: bool = True,
        max_results: int = 500,
        timeout_seconds: int = 90
    ) -> Dict[str, Any]:
        """Search for person across sources.

        Args:
            name: Person's name
            location: Optional location/country (e.g., "US", "United Kingdom")
            include_social: Include social media engines
            max_results: Max results per engine
            timeout_seconds: Timeout in seconds

        Returns:
            Same structure as search(), optimized for person searches
        """
        # Build query
        query = f'"{name}"'
        if location:
            query += f' {location}'

        # Select engines - core + AI for person search
        engines = self.ENGINE_CATEGORIES["core"] + self.ENGINE_CATEGORIES["ai"]

        if include_social:
            engines.extend(self.ENGINE_CATEGORIES["social"])

        return await self.search(
            query=query,
            engines=engines,
            mode="balanced",
            max_results=max_results,
            timeout_seconds=timeout_seconds,
            include_template_engines=True  # May have people search templates
        )

    async def company_search(
        self,
        company_name: str,
        jurisdiction: Optional[str] = None,
        include_news: bool = True,
        max_results: int = 1000,
        timeout_seconds: int = 120
    ) -> Dict[str, Any]:
        """Search for company across sources.

        Args:
            company_name: Company name
            jurisdiction: Optional jurisdiction code (e.g., "US", "HR")
            include_news: Include news engines
            max_results: Max results per engine
            timeout_seconds: Timeout in seconds

        Returns:
            Same structure as search(), optimized for company searches
        """
        # Build query
        query = f'"{company_name}"'
        if jurisdiction:
            query += f' {jurisdiction}'

        # Select engines - core + AI + news
        engines = self.ENGINE_CATEGORIES["core"] + self.ENGINE_CATEGORIES["ai"]

        if include_news:
            engines.extend(self.ENGINE_CATEGORIES["news"])

        return await self.search(
            query=query,
            engines=engines,
            mode="balanced",
            max_results=max_results,
            timeout_seconds=timeout_seconds,
            geo=jurisdiction,
            include_template_engines=True  # Important for corporate registries
        )

    async def academic_search(
        self,
        query: str,
        max_results: int = 500,
        timeout_seconds: int = 90
    ) -> Dict[str, Any]:
        """Search academic/research sources.

        Args:
            query: Search query
            max_results: Max results per engine
            timeout_seconds: Timeout in seconds

        Returns:
            Same structure as search(), filtered to academic engines
        """
        return await self.search(
            query=query,
            engines=self.ENGINE_CATEGORIES["academic"],
            mode="exhaustive",  # Academic search should be thorough
            max_results=max_results,
            timeout_seconds=timeout_seconds
        )

    def get_engines_by_category(self, category: str) -> List[str]:
        """Get engine codes for a category.

        Args:
            category: Category name (news, academic, social, etc.)

        Returns:
            List of engine codes
        """
        return self.ENGINE_CATEGORIES.get(category, [])

    def get_all_categories(self) -> Dict[str, List[str]]:
        """Get all engine categories.

        Returns:
            Dictionary of category -> engine codes
        """
        return self.ENGINE_CATEGORIES.copy()


# Convenience function for use in rules.json resources
async def brute_search(query: str, config: Dict = None) -> Dict[str, Any]:
    """Execute BruteSearch with config (for use in rules.json).

    Args:
        query: Search query
        config: Configuration dict matching BruteSearch options

    Returns:
        BruteSearch results
    """
    bridge = BruteSearchBridge()

    try:
        # Extract config parameters
        config = config or {}

        result = await bridge.search(
            query=query,
            engines=config.get('engines'),
            mode=config.get('mode', 'balanced'),
            max_results=config.get('maxResults', 10000),
            timeout_seconds=config.get('timeoutSeconds', 180),
            include_keyword_variations=config.get('includeKeywordVariations', False),
            include_linklater_enrichment=config.get('includeLinklaterEnrichment', False),
            include_template_engines=config.get('includeTemplateEngines', True),
            template_engine_limit=config.get('templateEngineLimit', 30),
            geo=config.get('userLocation', {}).get('country') if 'userLocation' in config else None,
            language=config.get('language'),
            news_categories=config.get('newsCategories'),
            news_countries=config.get('newsCountries'),
            news_languages=config.get('newsLanguages')
        )

        return result

    finally:
        await bridge.close()


if __name__ == "__main__":
    # Example usage
    async def main():
        bridge = BruteSearchBridge()

        try:
            # Example 1: Basic search
            print("\n=== Example 1: Basic Search ===")
            result = await bridge.search(
                query="Podravka d.d. officers",
                engines=["GO", "BR"],
                mode="speed",
                timeout_seconds=30
            )
            print(f"Found {result['results_count']} results from {len(result['engines_used'])} engines")

            # Example 2: News search
            print("\n=== Example 2: News Search ===")
            news = await bridge.news_search(
                query="Podravka d.d. sanctions",
                categories=["business"],
                timeout_seconds=30
            )
            print(f"Found {news['results_count']} news results")

            # Example 3: Person search
            print("\n=== Example 3: Person Search ===")
            person = await bridge.person_search(
                name="Marin Pucar",
                location="Croatia",
                include_social=False,
                timeout_seconds=30
            )
            print(f"Found {person['results_count']} results about person")

            # Example 4: Company search
            print("\n=== Example 4: Company Search ===")
            company = await bridge.company_search(
                company_name="Podravka d.d.",
                jurisdiction="HR",
                include_news=True,
                timeout_seconds=60
            )
            print(f"Found {company['results_count']} results about company")

        finally:
            await bridge.close()

    asyncio.run(main())
