#!/usr/bin/env python3
"""
Corporate Registry Search Operator - Searches company registries and business databases
Supports corporate:, company:, registry:, cr: operators
Leverages TORPEDO CRSearcher + sources/corporate_registries.json + BrightData Archive cat{business}!
"""

import sys
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import event streaming
try:
    from brute.infrastructure.base_streamer import SearchTypeEventEmitter
    STREAMING_AVAILABLE = True
except ImportError:
    STREAMING_AVAILABLE = False
    logging.warning("Event streaming not available for corporate search")

# BrightData Archive - native cat{business}! support
try:
    from backdrill.brightdata import BrightDataArchive, search_by_category
    BRIGHTDATA_ARCHIVE_AVAILABLE = True
except ImportError:
    BRIGHTDATA_ARCHIVE_AVAILABLE = False
    BrightDataArchive = None
    search_by_category = None

# TORPEDO CRSearcher - dedicated corporate registry searcher
try:
    from torpedo.EXECUTION.cr_searcher import CRSearcher as TorpedoCRSearcher
    TORPEDO_CR_AVAILABLE = True
except ImportError:
    TORPEDO_CR_AVAILABLE = False
    TorpedoCRSearcher = None

# Corporate search engines (fallback)
CORPORATE_ENGINES = [
    'GO',  # Google
    'BI',  # Bing
    'BR',  # Brave
]

# Known corporate registry domains
CORPORATE_REGISTRIES = {
    'UK': 'site:find-and-update.company-information.service.gov.uk',
    'US_DE': 'site:icis.corp.delaware.gov',
    'US_NY': 'site:appext20.dos.ny.gov',
    'EU': 'site:e-justice.europa.eu',
    'NL': 'site:kvk.nl',
    'DE': 'site:handelsregister.de',
    'FR': 'site:infogreffe.fr',
    'opencorporates': 'site:opencorporates.com',
    'lei': 'site:lei-lookup.com OR site:gleif.org',
}


class CorporateSearcher:
    """
    Corporate registry search implementation.
    Uses TORPEDO CRSearcher for I/O sources + BrightData Archive.
    """

    def __init__(self, event_emitter=None):
        """Initialize corporate search."""
        self.event_emitter = event_emitter
        self.torpedo_searcher = TorpedoCRSearcher() if TORPEDO_CR_AVAILABLE else None
        self._sources_loaded = False

        if STREAMING_AVAILABLE and event_emitter:
            self.streamer = SearchTypeEventEmitter(event_emitter)
        else:
            self.streamer = None

    async def _ensure_sources_loaded(self):
        """Ensure TORPEDO sources are loaded."""
        if not self._sources_loaded and self.torpedo_searcher:
            try:
                count = await self.torpedo_searcher.load_sources()
                logger.info(f"TORPEDO CRSearcher loaded {count} corporate registry sources")
                self._sources_loaded = True
            except Exception as e:
                logger.warning(f"Failed to load TORPEDO CR sources: {e}")

    def get_jurisdictions(self) -> List[str]:
        """Get available jurisdictions from torpedo."""
        if self.torpedo_searcher and hasattr(self.torpedo_searcher, 'get_jurisdictions'):
            return self.torpedo_searcher.get_jurisdictions()
        return list(CORPORATE_REGISTRIES.keys())

    async def search(
        self,
        query: str,
        jurisdiction: Optional[str] = None,
        max_results: int = 100,
        max_sources: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search corporate registries.

        Args:
            query: Company name or registration number
            jurisdiction: Optional jurisdiction filter (UK, US, DE, etc.)
            max_results: Maximum total results
            max_sources: Maximum sources per jurisdiction

        Returns:
            List of corporate registry search results
        """
        query = query.strip()

        logger.info(f"Starting corporate search for: '{query}' (jurisdiction={jurisdiction})")

        if self.streamer:
            await self.streamer.emit_search_started('corporate', query, ['TORPEDO_CR', 'BD_ARCHIVE'])

        all_results = []
        seen_urls = set()

        # TORPEDO CRSearcher - Primary path
        if self.torpedo_searcher:
            await self._ensure_sources_loaded()

            try:
                # Normalize jurisdiction
                jur = None
                if jurisdiction:
                    jur = jurisdiction.upper()
                    if jur == "GB":
                        jur = "UK"

                # Use TORPEDO CRSearcher
                torpedo_results = await self.torpedo_searcher.search(
                    query=query,
                    jurisdiction=jur,
                    max_sources=max_sources
                )

                for result in torpedo_results:
                    url = result.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        result['search_type'] = 'corporate'
                        result['method'] = 'torpedo_cr'
                        all_results.append(result)

                logger.info(f"TORPEDO CRSearcher: {len(torpedo_results)} corporate results")

            except Exception as e:
                logger.warning(f"TORPEDO CRSearcher failed: {e}")

        # BrightData Archive: Native cat{business}! support
        if BRIGHTDATA_ARCHIVE_AVAILABLE and search_by_category:
            try:
                bd_limit = max(max_results // 3, 25)
                bd_results = await search_by_category(
                    category="business",  # Maps to corporate
                    limit=bd_limit,
                )

                for r in bd_results:
                    url = r.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        r['source'] = 'brightdata_archive'
                        r['search_type'] = 'corporate'
                        r['method'] = 'brightdata_archive'
                        all_results.append(r)

                logger.info(f"BrightData Archive added {len(bd_results)} corporate results")

            except Exception as e:
                logger.warning(f"BrightData Archive corporate search failed: {e}")

        # Fallback: General search with registry filters
        if len(all_results) < max_results // 2:
            try:
                from brute.targeted_searches.brute import BruteSearchEngine

                # Build corporate-specific queries
                corporate_queries = [
                    f'"{query}" company registration',
                    f'"{query}" corporate registry',
                    f'"{query}" business registration',
                    f'site:opencorporates.com "{query}"',
                ]

                # Add jurisdiction-specific registry
                if jurisdiction and jurisdiction.upper() in CORPORATE_REGISTRIES:
                    jur_filter = CORPORATE_REGISTRIES[jurisdiction.upper()]
                    corporate_queries.insert(0, f'{jur_filter} "{query}"')

                for corp_query in corporate_queries[:4]:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    output_file = f"results/corporate_{timestamp}.json"

                    searcher = BruteSearchEngine(
                        keyword=corp_query,
                        output_file=output_file,
                        engines=CORPORATE_ENGINES,
                        max_workers=min(len(CORPORATE_ENGINES), 3),
                        event_emitter=self.event_emitter,
                        return_results=True
                    )
                    searcher.search()

                    if hasattr(searcher, 'final_results'):
                        for result in searcher.final_results:
                            url = result.get('url', '')
                            if url and url not in seen_urls:
                                seen_urls.add(url)
                                result['search_type'] = 'corporate'
                                result['method'] = 'brute_fallback'
                                all_results.append(result)

                    if len(all_results) >= max_results:
                        break

            except Exception as e:
                logger.warning(f"Fallback corporate search failed: {e}")

        # Score and sort results
        scored_results = self._score_corporate_results(all_results, query, jurisdiction)

        if self.streamer:
            await self.streamer.emit_search_completed('corporate', len(scored_results))

        logger.info(f"Corporate search completed with {len(scored_results)} total results")

        return scored_results[:max_results]

    def _score_corporate_results(
        self,
        results: List[Dict],
        query: str,
        jurisdiction: Optional[str] = None
    ) -> List[Dict]:
        """Score and sort corporate results by relevance."""
        query_lower = query.lower()

        def score_result(result):
            score = 0
            url = result.get('url', '').lower()
            title = result.get('title', '').lower()

            # Official registry domains (highest priority)
            official_registries = [
                'company-information.service.gov.uk',  # UK
                'corp.delaware.gov',  # US Delaware
                'handelsregister.de',  # Germany
                'infogreffe.fr',  # France
                'kvk.nl',  # Netherlands
                'opencorporates.com',  # OpenCorporates
                'gleif.org',  # LEI
            ]
            for registry in official_registries:
                if registry in url:
                    score += 70
                    break

            # TORPEDO source bonus
            if result.get('method') == 'torpedo_cr':
                score += 40

            # Corporate keywords
            corp_keywords = ['company', 'corporation', 'ltd', 'llc', 'inc',
                           'gmbh', 'bv', 'sa', 'plc', 'registered']
            for keyword in corp_keywords:
                if keyword in title:
                    score += 15
                    break

            # Company number patterns
            import re
            company_num_pattern = r'\b\d{6,10}\b|[A-Z]{2}\d{6,}'
            if re.search(company_num_pattern, title):
                score += 20

            # Query match
            if query_lower in title:
                score += 25

            # BrightData Archive
            if result.get('source') == 'brightdata_archive':
                score += 15

            # Has structured data (from torpedo)
            if result.get('company_name') or result.get('registration_number'):
                score += 25

            return score

        for result in results:
            result['corporate_score'] = score_result(result)

        results.sort(key=lambda x: x.get('corporate_score', 0), reverse=True)

        return results

    def search_sync(self, query: str, jurisdiction: Optional[str] = None,
                   max_results: int = 100) -> List[Dict[str, Any]]:
        """Synchronous wrapper for search method."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.search(query, jurisdiction, max_results))
        finally:
            loop.close()


def detect_corporate_query(query: str) -> bool:
    """Detect if a query should be routed to corporate search."""
    query_lower = query.lower()

    corporate_patterns = [
        'corporate:',
        'company:',
        'registry:',
        'cr:',
        'business:',
        'corp:',
    ]

    for pattern in corporate_patterns:
        if pattern in query_lower:
            return True

    return False


def extract_corporate_query(query: str) -> str:
    """Extract the actual search query from a corporate search query."""
    query = query.strip()

    prefixes = [
        'corporate:', 'company:', 'registry:', 'cr:', 'business:', 'corp:',
        'Corporate:', 'Company:', 'Registry:', 'CR:', 'Business:', 'Corp:'
    ]

    for prefix in prefixes:
        if query.startswith(prefix):
            query = query[len(prefix):].strip()
            if query.startswith('"') and query.endswith('"'):
                query = query[1:-1]
            elif query.startswith("'") and query.endswith("'"):
                query = query[1:-1]
            return query

    return query.strip()


async def run_corporate_search(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """Main entry point for corporate search."""
    clean_query = extract_corporate_query(query)
    searcher = CorporateSearcher(event_emitter)
    return await searcher.search(clean_query)


def run_corporate_search_sync(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """Synchronous wrapper for corporate search."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(run_corporate_search(query, event_emitter))
    finally:
        loop.close()


def search(query: str, max_results: int = 100) -> List[Dict[str, Any]]:
    """Synchronous search function for web API compatibility."""
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, run_corporate_search(query))
            return future.result()
    except RuntimeError:
        return asyncio.run(run_corporate_search(query))


def main():
    """Main entry point for Corporate registry search - compatible with SearchRouter"""
    import argparse

    parser = argparse.ArgumentParser(description='Corporate registry search')
    parser.add_argument('-q', '--query', required=True, help='Company name or reg number')
    parser.add_argument('-j', '--jurisdiction', help='Jurisdiction filter (UK, US, DE)')
    args = parser.parse_args()

    query = args.query

    if ':' in query:
        clean_query = query.split(':', 1)[1].strip()
    else:
        clean_query = query

    print(f"\n🔍 Corporate search: {clean_query}")
    if args.jurisdiction:
        print(f"   Jurisdiction: {args.jurisdiction}")

    results = run_corporate_search_sync(clean_query)

    if results:
        print(f"\nFound {len(results)} results:")
        for i, result in enumerate(results[:10], 1):
            print(f"\n{i}. {result.get('title', 'No Title')}")
            print(f"   URL: {result.get('url')}")
            print(f"   Source: {result.get('source', 'Unknown')}")
            if result.get('company_name'):
                print(f"   Company: {result.get('company_name')}")
            if result.get('registration_number'):
                print(f"   Reg #: {result.get('registration_number')}")
    else:
        print("\nNo results found.")

    return results


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        test_query = ' '.join(sys.argv[1:])
    else:
        test_query = "company:Tesco PLC"

    print(f"Testing corporate search with: {test_query}")

    if detect_corporate_query(test_query):
        print("Corporate query detected!")
        clean_query = extract_corporate_query(test_query)
        print(f"Extracted query: '{clean_query}'")

        results = run_corporate_search_sync(test_query)

        print(f"\nFound {len(results)} corporate results:")
        for i, result in enumerate(results[:10], 1):
            print(f"\n{i}. {result.get('title', 'No title')}")
            print(f"   URL: {result.get('url', 'No URL')}")
            print(f"   Method: {result.get('method', 'Unknown')}")
    else:
        print("Not a corporate query")
