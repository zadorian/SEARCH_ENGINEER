#!/usr/bin/env python3
"""
Government Search Operator - Searches government portals and official sources
Supports gov:, government: operators with TORPEDO integration and BrightData Archive
Leverages sources/government.json (814+ sources) for comprehensive government coverage
"""

import sys
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from urllib.parse import quote_plus

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
    logging.warning("Event streaming not available for government search")

# BrightData Archive - native cat{government}! support
try:
    from backdrill.brightdata import BrightDataArchive, search_by_category
    BRIGHTDATA_ARCHIVE_AVAILABLE = True
except ImportError:
    BRIGHTDATA_ARCHIVE_AVAILABLE = False
    BrightDataArchive = None
    search_by_category = None

# TORPEDO integration for source-based searching
try:
    from torpedo.EXECUTION.base_searcher import BaseSearcher
    from torpedo.paths import io_sources_dir
    TORPEDO_AVAILABLE = True
except ImportError:
    TORPEDO_AVAILABLE = False
    BaseSearcher = None
    io_sources_dir = None

# Government search engines
GOV_ENGINES = [
    'GO',  # Google with site:*.gov filters
    'BI',  # Bing
    'BR',  # Brave
    'DD',  # DuckDuckGo
]

# Government TLD patterns
GOV_TLDS = [
    'site:*.gov',
    'site:*.gov.uk',
    'site:*.gov.au',
    'site:*.gc.ca',
    'site:*.gouv.fr',
    'site:*.gob.mx',
    'site:*.gov.in',
    'site:*.gov.br',
    'site:*.go.jp',
    'site:*.gov.cn',
    'site:*.govt.nz',
    'site:europa.eu',
]


class GovSearcher:
    """
    Government search implementation using TORPEDO + BrightData Archive.
    Routes searches to government sources from I/O matrix.
    """

    def __init__(self, event_emitter=None):
        """Initialize government search."""
        self.event_emitter = event_emitter
        self.sources: Dict[str, List[Dict[str, Any]]] = {}  # jurisdiction -> sources
        self.sources_loaded = False
        self.base_scraper = BaseSearcher() if TORPEDO_AVAILABLE else None

        if STREAMING_AVAILABLE and event_emitter:
            self.streamer = SearchTypeEventEmitter(event_emitter)
        else:
            self.streamer = None

    async def load_sources(self) -> int:
        """Load government sources from sources/government.json."""
        if self.sources_loaded:
            return sum(len(s) for s in self.sources.values())

        try:
            if io_sources_dir:
                gov_path = io_sources_dir() / "government.json"
            else:
                gov_path = Path("/data/SEARCH_ENGINEER/modules/input_output/matrix/sources/government.json")

            if not gov_path.exists():
                logger.warning(f"Government sources not found at {gov_path}")
                return 0

            with open(gov_path) as f:
                data = json.load(f)

            sources_list = data.get("sources", [])

            for source in sources_list:
                template = source.get("search_template") or source.get("search_url")
                if not template or "{q}" not in template:
                    continue

                jur = (source.get("jurisdiction_primary") or
                       source.get("jurisdictions", ["GLOBAL"])[0] or "GLOBAL").upper()
                if jur == "GB":
                    jur = "UK"

                self.sources.setdefault(jur, []).append({
                    "id": source.get("id", ""),
                    "domain": source.get("domain", ""),
                    "name": source.get("name", source.get("domain", "")),
                    "search_template": template,
                    "friction": source.get("friction", "public"),
                    "source_type": source.get("source_type", "government_portal"),
                    "scrape_method": source.get("scrape_method"),
                    "quality_tier": source.get("quality_tier", "medium"),
                })

            self.sources_loaded = True
            total = sum(len(s) for s in self.sources.values())
            logger.info(f"Loaded {total} government sources across {len(self.sources)} jurisdictions")
            return total

        except Exception as e:
            logger.error(f"Failed to load government sources: {e}")
            return 0

    def get_jurisdictions(self) -> List[str]:
        """Get list of available jurisdictions."""
        return list(self.sources.keys())

    async def search_source(
        self,
        source: Dict[str, Any],
        query: str,
        max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """Search a single government source using its template."""
        template = source.get("search_template", "")
        if not template or "{q}" not in template:
            return []

        url = template.replace("{q}", quote_plus(query))
        results = []

        try:
            if self.base_scraper:
                response = await self.base_scraper.fetch_url(
                    url,
                    scrape_method=source.get("scrape_method"),
                    use_brightdata=False
                )

                if response.get("success") and response.get("html"):
                    soup = self.base_scraper.parse_html(response["html"])

                    # Extract search results - common patterns
                    for link in soup.select("a[href]")[:max_results * 2]:
                        href = link.get("href", "")
                        title = link.get_text(strip=True)

                        # Skip navigation/internal links
                        if not href or href.startswith("#") or not title:
                            continue
                        if len(title) < 10:
                            continue

                        # Make absolute URL if relative
                        if href.startswith("/"):
                            domain = source.get("domain", "")
                            href = f"https://{domain}{href}"

                        results.append({
                            "title": title[:200],
                            "url": href,
                            "source": source.get("name", source.get("domain", "")),
                            "source_domain": source.get("domain", ""),
                            "source_id": source.get("id", ""),
                            "search_type": "gov",
                            "method": "torpedo",
                        })

                        if len(results) >= max_results:
                            break

        except Exception as e:
            logger.debug(f"Source search failed for {source.get('domain')}: {e}")

        return results

    async def search(
        self,
        query: str,
        jurisdiction: Optional[str] = None,
        max_results: int = 100,
        max_sources: int = 20,
        max_concurrent: int = 8
    ) -> List[Dict[str, Any]]:
        """
        Search government sources.

        Args:
            query: Search query
            jurisdiction: Optional jurisdiction filter (e.g., "US", "UK", "DE")
            max_results: Maximum total results
            max_sources: Maximum sources to query
            max_concurrent: Max concurrent requests

        Returns:
            List of search results
        """
        # Clean query
        query = query.strip()

        logger.info(f"Starting government search for: '{query}' (jurisdiction={jurisdiction})")

        if self.streamer:
            await self.streamer.emit_search_started('gov', query, ['TORPEDO', 'BD_ARCHIVE'])

        # Load sources if needed
        await self.load_sources()

        all_results = []
        seen_urls = set()

        # Get sources for jurisdiction
        if jurisdiction:
            jur = jurisdiction.upper()
            if jur == "GB":
                jur = "UK"
            sources_to_search = self.sources.get(jur, [])[:max_sources]
        else:
            # Global search - take from multiple jurisdictions
            sources_to_search = []
            for jur_sources in self.sources.values():
                sources_to_search.extend(jur_sources[:3])
            sources_to_search = sources_to_search[:max_sources]

        # TORPEDO: Search I/O sources in parallel
        if sources_to_search and self.base_scraper:
            semaphore = asyncio.Semaphore(max_concurrent)

            async def fetch_source(source):
                async with semaphore:
                    return await self.search_source(source, query, max_results=10)

            try:
                source_batches = await asyncio.gather(
                    *(fetch_source(s) for s in sources_to_search),
                    return_exceptions=True
                )

                for batch in source_batches:
                    if isinstance(batch, Exception):
                        continue
                    for result in batch:
                        url = result.get("url", "")
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            all_results.append(result)

                logger.info(f"TORPEDO: {len(all_results)} results from {len(sources_to_search)} sources")

            except Exception as e:
                logger.warning(f"TORPEDO search failed: {e}")

        # BrightData Archive: Native cat{government}! support
        if BRIGHTDATA_ARCHIVE_AVAILABLE and search_by_category:
            try:
                bd_limit = max(max_results // 3, 30)
                bd_results = await search_by_category(
                    category="government",
                    limit=bd_limit,
                )

                # Filter to avoid duplicates from torpedo
                for r in bd_results:
                    url = r.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        r['source'] = 'brightdata_archive'
                        r['search_type'] = 'gov'
                        r['method'] = 'brightdata_archive'
                        all_results.append(r)

                logger.info(f"BrightData Archive added {len(bd_results)} gov results (after dedup)")

            except Exception as e:
                logger.warning(f"BrightData Archive government search failed: {e}")

        # Fallback: General search with gov TLD filters
        if len(all_results) < max_results // 2:
            try:
                from brute.targeted_searches.brute import BruteSearchEngine

                gov_queries = [f'{tld} {query}' for tld in GOV_TLDS[:5]]

                for gov_query in gov_queries[:3]:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    output_file = f"results/gov_{timestamp}.json"

                    searcher = BruteSearchEngine(
                        keyword=gov_query,
                        output_file=output_file,
                        engines=GOV_ENGINES,
                        max_workers=min(len(GOV_ENGINES), 4),
                        event_emitter=self.event_emitter,
                        return_results=True
                    )
                    searcher.search()

                    if hasattr(searcher, 'final_results'):
                        for result in searcher.final_results:
                            url = result.get('url', '')
                            if url and url not in seen_urls:
                                seen_urls.add(url)
                                result['search_type'] = 'gov'
                                result['method'] = 'brute_fallback'
                                all_results.append(result)

                    if len(all_results) >= max_results:
                        break

            except Exception as e:
                logger.warning(f"Fallback search failed: {e}")

        # Score and sort results
        scored_results = self._score_gov_results(all_results, query)

        if self.streamer:
            await self.streamer.emit_search_completed('gov', len(scored_results))

        logger.info(f"Government search completed with {len(scored_results)} total results")

        return scored_results[:max_results]

    def _score_gov_results(self, results: List[Dict], query: str) -> List[Dict]:
        """Score and sort government results by relevance."""
        query_lower = query.lower()

        def score_result(result):
            score = 0
            url = result.get('url', '').lower()
            title = result.get('title', '').lower()

            # Government TLD bonus
            gov_domains = ['.gov', '.gov.uk', '.gov.au', '.gc.ca', '.gouv.fr',
                         '.gob.mx', '.go.jp', 'europa.eu', '.govt.nz']
            for domain in gov_domains:
                if domain in url:
                    score += 50
                    break

            # Official source bonus
            if result.get('method') == 'torpedo':
                score += 30

            # Query match in title
            if query_lower in title:
                score += 25

            # Quality tier bonus
            tier = result.get('quality_tier', 'medium')
            if tier == 'high':
                score += 20
            elif tier == 'medium':
                score += 10

            # BrightData Archive results
            if result.get('source') == 'brightdata_archive':
                score += 15

            return score

        for result in results:
            result['gov_score'] = score_result(result)

        results.sort(key=lambda x: x.get('gov_score', 0), reverse=True)

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


def detect_gov_query(query: str) -> bool:
    """Detect if a query should be routed to government search."""
    query_lower = query.lower()

    gov_patterns = [
        'gov:',
        'government:',
        'official:',
        'agency:',
    ]

    for pattern in gov_patterns:
        if pattern in query_lower:
            return True

    return False


def extract_gov_query(query: str) -> str:
    """Extract the actual search query from a government search query."""
    query = query.strip()

    prefixes = [
        'gov:', 'government:', 'official:', 'agency:',
        'Gov:', 'Government:', 'Official:', 'Agency:'
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


async def run_gov_search(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """Main entry point for government search."""
    clean_query = extract_gov_query(query)
    searcher = GovSearcher(event_emitter)
    return await searcher.search(clean_query)


def run_gov_search_sync(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """Synchronous wrapper for government search."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(run_gov_search(query, event_emitter))
    finally:
        loop.close()


def search(query: str, max_results: int = 100) -> List[Dict[str, Any]]:
    """Synchronous search function for web API compatibility."""
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, run_gov_search(query))
            return future.result()
    except RuntimeError:
        return asyncio.run(run_gov_search(query))


def main():
    """Main entry point for Government search - compatible with SearchRouter"""
    import argparse

    parser = argparse.ArgumentParser(description='Government portal search')
    parser.add_argument('-q', '--query', required=True, help='Search query')
    parser.add_argument('-j', '--jurisdiction', help='Jurisdiction filter (e.g., US, UK, DE)')
    args = parser.parse_args()

    query = args.query

    if ':' in query:
        clean_query = query.split(':', 1)[1].strip()
    else:
        clean_query = query

    print(f"\n🔍 Government search: {clean_query}")
    if args.jurisdiction:
        print(f"   Jurisdiction: {args.jurisdiction}")

    results = run_gov_search_sync(clean_query)

    if results:
        print(f"\nFound {len(results)} results:")
        for i, result in enumerate(results[:10], 1):
            print(f"\n{i}. {result.get('title', 'No Title')}")
            print(f"   URL: {result.get('url')}")
            print(f"   Source: {result.get('source', 'Unknown')}")
            print(f"   Score: {result.get('gov_score', 0)}")
    else:
        print("\nNo results found.")

    return results


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        test_query = ' '.join(sys.argv[1:])
    else:
        test_query = "gov:tax filing requirements"

    print(f"Testing government search with: {test_query}")

    if detect_gov_query(test_query):
        print("Government query detected!")
        clean_query = extract_gov_query(test_query)
        print(f"Extracted query: '{clean_query}'")

        results = run_gov_search_sync(test_query)

        print(f"\nFound {len(results)} government results:")
        for i, result in enumerate(results[:10], 1):
            print(f"\n{i}. {result.get('title', 'No title')}")
            print(f"   URL: {result.get('url', 'No URL')}")
            print(f"   Source: {result.get('source', 'Unknown')}")
            print(f"   Method: {result.get('method', 'Unknown')}")
    else:
        print("Not a government query")
