#!/usr/bin/env python3
"""
Finance Search Operator - Searches financial databases, reports, and market data
Supports finance:, financial:, stock:, market: operators
Leverages BrightData Archive cat{finance}! and financial data platforms
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
    logging.warning("Event streaming not available for finance search")

# BrightData Archive - native cat{finance}! support
try:
    from backdrill.brightdata import BrightDataArchive, search_by_category
    BRIGHTDATA_ARCHIVE_AVAILABLE = True
except ImportError:
    BRIGHTDATA_ARCHIVE_AVAILABLE = False
    BrightDataArchive = None
    search_by_category = None

# Finance search engines
FINANCE_ENGINES = [
    'GO',  # Google
    'BI',  # Bing
    'BR',  # Brave
    'DD',  # DuckDuckGo
]

# Financial data platforms for site-specific searches
FINANCE_PLATFORMS = {
    'sec': 'site:sec.gov',
    'edgar': 'site:sec.gov/cgi-bin/browse-edgar',
    'bloomberg': 'site:bloomberg.com',
    'reuters': 'site:reuters.com',
    'yahoo_finance': 'site:finance.yahoo.com',
    'marketwatch': 'site:marketwatch.com',
    'seeking_alpha': 'site:seekingalpha.com',
    'morningstar': 'site:morningstar.com',
    'wsj': 'site:wsj.com',
    'ft': 'site:ft.com',
    'nasdaq': 'site:nasdaq.com',
    'nyse': 'site:nyse.com',
    'investopedia': 'site:investopedia.com',
    'cnbc': 'site:cnbc.com',
    'fool': 'site:fool.com',
    'barchart': 'site:barchart.com',
    'finviz': 'site:finviz.com',
    'stockanalysis': 'site:stockanalysis.com',
}

# Financial document types
FINANCE_DOC_TYPES = [
    '10-K',  # Annual report
    '10-Q',  # Quarterly report
    '8-K',   # Current report
    'DEF 14A',  # Proxy statement
    'S-1',   # IPO registration
    '13F',   # Institutional holdings
    '13D',   # Beneficial ownership
    '4',     # Insider trading
]


class FinanceSearcher:
    """
    Finance search implementation using BrightData Archive + platform searches.
    """

    def __init__(self, event_emitter=None):
        """Initialize finance search."""
        self.event_emitter = event_emitter
        self.available_engines = self._check_available_engines()

        if STREAMING_AVAILABLE and event_emitter:
            self.streamer = SearchTypeEventEmitter(event_emitter)
        else:
            self.streamer = None

    def _check_available_engines(self) -> List[str]:
        """Check which finance-supporting engines are available."""
        available = []

        try:
            from brute.targeted_searches.brute import ENGINE_CONFIG

            for engine_code in FINANCE_ENGINES:
                if engine_code in ENGINE_CONFIG:
                    available.append(engine_code)
                    logger.info(f"Finance engine {engine_code} available")
        except ImportError:
            available = ['GO', 'BI', 'BR']

        if not available:
            available = ['GO', 'BI', 'BR']

        return available

    def _build_finance_queries(
        self,
        query: str,
        doc_type: Optional[str] = None,
        include_platforms: bool = True
    ) -> List[str]:
        """Build comprehensive finance search queries."""
        queries = []

        # Base queries
        queries.append(f'{query} financial')
        queries.append(f'"{query}" SEC filing')
        queries.append(f'"{query}" investor relations')
        queries.append(f'"{query}" annual report')

        # Document type specific
        if doc_type:
            queries.append(f'"{query}" {doc_type}')
            queries.append(f'site:sec.gov "{query}" {doc_type}')

        # Platform-specific searches
        if include_platforms:
            priority_platforms = ['sec', 'edgar', 'bloomberg', 'yahoo_finance',
                                 'reuters', 'marketwatch', 'seeking_alpha']
            for platform in priority_platforms:
                if platform in FINANCE_PLATFORMS:
                    queries.append(f'{FINANCE_PLATFORMS[platform]} {query}')

        # Financial patterns
        queries.extend([
            f'"{query}" earnings report',
            f'"{query}" quarterly earnings',
            f'"{query}" stock price',
            f'"{query}" market cap',
            f'"{query}" financial statements',
            f'"{query}" balance sheet',
            f'"{query}" income statement',
            f'"{query}" cash flow',
            f'"{query}" analyst rating',
        ])

        return queries

    async def search(
        self,
        query: str,
        doc_type: Optional[str] = None,
        max_results: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search financial sources.

        Args:
            query: Search query (company name, ticker, etc.)
            doc_type: Optional SEC document type filter (10-K, 10-Q, etc.)
            max_results: Maximum results to return

        Returns:
            List of financial search results
        """
        query = query.strip()

        logger.info(f"Starting finance search for: '{query}' (doc_type={doc_type})")

        if self.streamer:
            await self.streamer.emit_search_started('finance', query, self.available_engines)

        all_results = []
        seen_urls = set()

        # BrightData Archive: Native cat{finance}! support (priority)
        if BRIGHTDATA_ARCHIVE_AVAILABLE and search_by_category:
            try:
                bd_limit = max(max_results // 3, 30)
                bd_results = await search_by_category(
                    category="finance",
                    limit=bd_limit,
                )

                for r in bd_results:
                    url = r.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        r['source'] = 'brightdata_archive'
                        r['search_type'] = 'finance'
                        r['method'] = 'brightdata_archive'
                        all_results.append(r)

                logger.info(f"BrightData Archive added {len(bd_results)} finance results")

            except Exception as e:
                logger.warning(f"BrightData Archive finance search failed: {e}")

        # Build and execute finance-specific queries
        finance_queries = self._build_finance_queries(query, doc_type)

        try:
            from brute.targeted_searches.brute import BruteSearchEngine

            for finance_query in finance_queries[:8]:
                logger.info(f"Searching with query: '{finance_query}'")

                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                output_file = f"results/finance_{timestamp}.json"

                searcher = BruteSearchEngine(
                    keyword=finance_query,
                    output_file=output_file,
                    engines=self.available_engines,
                    max_workers=min(len(self.available_engines), 4),
                    event_emitter=self.event_emitter,
                    return_results=True
                )

                searcher.search()

                if hasattr(searcher, 'final_results'):
                    for result in searcher.final_results:
                        url = result.get('url', '')
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            result['search_type'] = 'finance'
                            result['finance_query'] = query
                            result['query_variant'] = finance_query
                            result['method'] = 'brute_search'
                            if doc_type:
                                result['doc_type_filter'] = doc_type
                            all_results.append(result)

                if len(all_results) >= max_results:
                    break

        except ImportError as e:
            logger.error(f"Failed to import BruteSearchEngine: {e}")
        except Exception as e:
            logger.error(f"Finance search failed: {e}")

        # Score and sort results
        scored_results = self._score_finance_results(all_results, query, doc_type)

        if self.streamer:
            await self.streamer.emit_search_completed('finance', len(scored_results))

        logger.info(f"Finance search completed with {len(scored_results)} results")

        return scored_results[:max_results]

    def _score_finance_results(
        self,
        results: List[Dict],
        query: str,
        doc_type: Optional[str] = None
    ) -> List[Dict]:
        """Score and sort finance results by relevance."""
        query_lower = query.lower()

        def score_result(result):
            score = 0
            url = result.get('url', '').lower()
            title = result.get('title', '').lower()
            snippet = result.get('snippet', '').lower()

            # High-value finance domains
            high_value = ['sec.gov', 'bloomberg.com', 'reuters.com', 'wsj.com', 'ft.com']
            for domain in high_value:
                if domain in url:
                    score += 60
                    break

            # Medium-value finance platforms
            medium_value = ['yahoo.com/finance', 'marketwatch.com', 'seekingalpha.com',
                          'morningstar.com', 'nasdaq.com', 'nyse.com']
            for domain in medium_value:
                if domain in url:
                    score += 40
                    break

            # SEC filing bonus
            if 'sec.gov' in url:
                score += 30
                if doc_type and doc_type.lower() in url.lower():
                    score += 40

            # Document type keywords
            doc_keywords = ['10-k', '10-q', '8-k', 'proxy', 'filing', 'annual report',
                          'quarterly', 'earnings', 'financial statements']
            for keyword in doc_keywords:
                if keyword in title or keyword in snippet:
                    score += 20
                    break

            # Query match
            if query_lower in title:
                score += 25
            if query_lower in snippet:
                score += 15

            # Financial keywords
            finance_keywords = ['investor', 'shareholder', 'dividend', 'revenue',
                              'profit', 'loss', 'margin', 'eps', 'pe ratio']
            for keyword in finance_keywords:
                if keyword in snippet:
                    score += 10
                    break

            # BrightData Archive premium
            if result.get('source') == 'brightdata_archive':
                score += 15

            return score

        for result in results:
            result['finance_score'] = score_result(result)

        results.sort(key=lambda x: x.get('finance_score', 0), reverse=True)

        return results

    def search_sync(self, query: str, doc_type: Optional[str] = None,
                   max_results: int = 100) -> List[Dict[str, Any]]:
        """Synchronous wrapper for search method."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.search(query, doc_type, max_results))
        finally:
            loop.close()


def detect_finance_query(query: str) -> bool:
    """Detect if a query should be routed to finance search."""
    query_lower = query.lower()

    finance_patterns = [
        'finance:',
        'financial:',
        'stock:',
        'market:',
        'sec:',
        'filing:',
        'investor:',
    ]

    for pattern in finance_patterns:
        if pattern in query_lower:
            return True

    return False


def extract_finance_query(query: str) -> str:
    """Extract the actual search query from a finance search query."""
    query = query.strip()

    prefixes = [
        'finance:', 'financial:', 'stock:', 'market:', 'sec:', 'filing:', 'investor:',
        'Finance:', 'Financial:', 'Stock:', 'Market:', 'SEC:', 'Filing:', 'Investor:'
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


async def run_finance_search(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """Main entry point for finance search."""
    clean_query = extract_finance_query(query)
    searcher = FinanceSearcher(event_emitter)
    return await searcher.search(clean_query)


def run_finance_search_sync(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """Synchronous wrapper for finance search."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(run_finance_search(query, event_emitter))
    finally:
        loop.close()


def search(query: str, max_results: int = 100) -> List[Dict[str, Any]]:
    """Synchronous search function for web API compatibility."""
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, run_finance_search(query))
            return future.result()
    except RuntimeError:
        return asyncio.run(run_finance_search(query))


def main():
    """Main entry point for Finance search - compatible with SearchRouter"""
    import argparse

    parser = argparse.ArgumentParser(description='Financial data search')
    parser.add_argument('-q', '--query', required=True, help='Search query')
    parser.add_argument('-t', '--doc-type', help='SEC document type (10-K, 10-Q, 8-K)')
    args = parser.parse_args()

    query = args.query

    if ':' in query:
        clean_query = query.split(':', 1)[1].strip()
    else:
        clean_query = query

    print(f"\n🔍 Finance search: {clean_query}")
    if args.doc_type:
        print(f"   Document type: {args.doc_type}")

    results = run_finance_search_sync(clean_query)

    if results:
        print(f"\nFound {len(results)} results:")
        for i, result in enumerate(results[:10], 1):
            print(f"\n{i}. {result.get('title', 'No Title')}")
            print(f"   URL: {result.get('url')}")
            print(f"   Score: {result.get('finance_score', 0)}")
    else:
        print("\nNo results found.")

    return results


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        test_query = ' '.join(sys.argv[1:])
    else:
        test_query = "finance:Apple Inc 10-K"

    print(f"Testing finance search with: {test_query}")

    if detect_finance_query(test_query):
        print("Finance query detected!")
        clean_query = extract_finance_query(test_query)
        print(f"Extracted query: '{clean_query}'")

        results = run_finance_search_sync(test_query)

        print(f"\nFound {len(results)} finance results:")
        for i, result in enumerate(results[:10], 1):
            print(f"\n{i}. {result.get('title', 'No title')}")
            print(f"   URL: {result.get('url', 'No URL')}")
            print(f"   Source: {result.get('source', 'Unknown')}")
    else:
        print("Not a finance query")
