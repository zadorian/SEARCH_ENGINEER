#!/usr/bin/env python3
"""
Legal Search Operator - Searches court records, legal databases, and case law
Supports legal:, court:, case:, litigation: operators
Leverages sources/legal.json with TORPEDO + BrightData Archive cat{legal}!
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
    logging.warning("Event streaming not available for legal search")

# BrightData Archive - native cat{legal}! support
try:
    from backdrill.brightdata import BrightDataArchive, search_by_category
    BRIGHTDATA_ARCHIVE_AVAILABLE = True
except ImportError:
    BRIGHTDATA_ARCHIVE_AVAILABLE = False
    BrightDataArchive = None
    search_by_category = None

# TORPEDO integration
try:
    from torpedo.EXECUTION.base_searcher import BaseSearcher
    from torpedo.paths import io_sources_dir
    TORPEDO_AVAILABLE = True
except ImportError:
    TORPEDO_AVAILABLE = False
    BaseSearcher = None
    io_sources_dir = None

# Legal search engines
LEGAL_ENGINES = [
    'GO',  # Google
    'BI',  # Bing
    'BR',  # Brave
]

# Legal databases and platforms
LEGAL_PLATFORMS = {
    'caselaw': 'site:caselaw.findlaw.com',
    'courtlistener': 'site:courtlistener.com',
    'justia': 'site:justia.com',
    'law_cornell': 'site:law.cornell.edu',
    'oyez': 'site:oyez.org',
    'pacer': 'site:pacer.uscourts.gov',
    'scotusblog': 'site:scotusblog.com',
    'lexisnexis': 'site:lexisnexis.com',
    'westlaw': 'site:westlaw.com',
    'bailii': 'site:bailii.org',
    'canlii': 'site:canlii.org',
    'austlii': 'site:austlii.edu.au',
    'echr': 'site:hudoc.echr.coe.int',
    'eur_lex': 'site:eur-lex.europa.eu',
}


class LegalSearcher:
    """
    Legal search implementation using TORPEDO + BrightData Archive.
    Routes searches to court/legal sources from I/O matrix.
    """

    def __init__(self, event_emitter=None):
        """Initialize legal search."""
        self.event_emitter = event_emitter
        self.sources: Dict[str, List[Dict[str, Any]]] = {}
        self.sources_loaded = False
        self.base_scraper = BaseSearcher() if TORPEDO_AVAILABLE else None

        if STREAMING_AVAILABLE and event_emitter:
            self.streamer = SearchTypeEventEmitter(event_emitter)
        else:
            self.streamer = None

    async def load_sources(self) -> int:
        """Load legal sources from sources/legal.json."""
        if self.sources_loaded:
            return sum(len(s) for s in self.sources.values())

        try:
            if io_sources_dir:
                legal_path = io_sources_dir() / "legal.json"
            else:
                legal_path = Path("/data/SEARCH_ENGINEER/modules/input_output/matrix/sources/legal.json")

            if not legal_path.exists():
                logger.warning(f"Legal sources not found at {legal_path}")
                return 0

            with open(legal_path) as f:
                data = json.load(f)

            # Format: jurisdiction-keyed dict (UK, US, etc. -> list of sources)
            if isinstance(data, dict) and not data.get("sources"):
                for jur_key, sources_list in data.items():
                    if not isinstance(sources_list, list):
                        continue

                    jur_key = jur_key.upper()
                    if jur_key == "GB":
                        jur_key = "UK"
                    if jur_key in ["META", "METADATA"]:
                        continue

                    for source in sources_list:
                        template = source.get("search_template") or source.get("search_url")
                        if not template or "{q}" not in template:
                            continue

                        self.sources.setdefault(jur_key, []).append({
                            "domain": source.get("domain", ""),
                            "name": source.get("name", source.get("domain", "")),
                            "search_template": template,
                            "friction": source.get("friction", "public"),
                            "source_type": source.get("type", "legal"),
                            "scrape_method": source.get("metadata", {}).get("scrape_method"),
                            "output_schema": source.get("output_schema", {}),
                        })

            # Format B: sources wrapper with list
            elif isinstance(data.get("sources"), list):
                for source in data["sources"]:
                    template = source.get("search_template") or source.get("search_url")
                    if not template or "{q}" not in template:
                        continue

                    jur = (source.get("jurisdiction_primary") or
                           source.get("jurisdictions", ["GLOBAL"])[0] or "GLOBAL").upper()
                    if jur == "GB":
                        jur = "UK"

                    self.sources.setdefault(jur, []).append({
                        "domain": source.get("domain", ""),
                        "name": source.get("name", source.get("domain", "")),
                        "search_template": template,
                        "friction": source.get("friction", "public"),
                        "source_type": source.get("source_type", "legal"),
                        "scrape_method": source.get("scrape_method"),
                    })

            self.sources_loaded = True
            total = sum(len(s) for s in self.sources.values())
            logger.info(f"Loaded {total} legal sources across {len(self.sources)} jurisdictions")
            return total

        except Exception as e:
            logger.error(f"Failed to load legal sources: {e}")
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
        """Search a single legal source using its template."""
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
                    output_schema = source.get("output_schema", {})

                    # Use schema selectors if available
                    link_selector = output_schema.get("article_link_selector", "a[href]")
                    title_selector = output_schema.get("article_title_selector")

                    for link in soup.select(link_selector)[:max_results * 2]:
                        href = link.get("href", "")
                        title = link.get_text(strip=True)

                        if not href or href.startswith("#") or not title:
                            continue
                        if len(title) < 5:
                            continue

                        # Make absolute URL
                        if href.startswith("/"):
                            domain = source.get("domain", "")
                            href = f"https://{domain}{href}"

                        results.append({
                            "title": title[:200],
                            "url": href,
                            "source": source.get("name", source.get("domain", "")),
                            "source_domain": source.get("domain", ""),
                            "search_type": "legal",
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
        max_sources: int = 15,
        max_concurrent: int = 6
    ) -> List[Dict[str, Any]]:
        """
        Search legal sources.

        Args:
            query: Search query (case name, party, legal term)
            jurisdiction: Optional jurisdiction filter (UK, US, etc.)
            max_results: Maximum total results
            max_sources: Maximum sources to query
            max_concurrent: Max concurrent requests

        Returns:
            List of legal search results
        """
        query = query.strip()

        logger.info(f"Starting legal search for: '{query}' (jurisdiction={jurisdiction})")

        if self.streamer:
            await self.streamer.emit_search_started('legal', query, ['TORPEDO', 'BD_ARCHIVE'])

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
            sources_to_search = []
            for jur_sources in self.sources.values():
                sources_to_search.extend(jur_sources[:3])
            sources_to_search = sources_to_search[:max_sources]

        # TORPEDO: Search I/O sources
        if sources_to_search and self.base_scraper:
            semaphore = asyncio.Semaphore(max_concurrent)

            async def fetch_source(source):
                async with semaphore:
                    return await self.search_source(source, query, max_results=8)

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

                logger.info(f"TORPEDO: {len(all_results)} results from {len(sources_to_search)} legal sources")

            except Exception as e:
                logger.warning(f"TORPEDO legal search failed: {e}")

        # BrightData Archive: Native cat{legal}! support
        if BRIGHTDATA_ARCHIVE_AVAILABLE and search_by_category:
            try:
                bd_limit = max(max_results // 3, 25)
                bd_results = await search_by_category(
                    category="legal",
                    limit=bd_limit,
                )

                for r in bd_results:
                    url = r.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        r['source'] = 'brightdata_archive'
                        r['search_type'] = 'legal'
                        r['method'] = 'brightdata_archive'
                        all_results.append(r)

                logger.info(f"BrightData Archive added {len(bd_results)} legal results")

            except Exception as e:
                logger.warning(f"BrightData Archive legal search failed: {e}")

        # Fallback: Platform-specific searches
        if len(all_results) < max_results // 2:
            try:
                from brute.targeted_searches.brute import BruteSearchEngine

                # Build legal-specific queries
                legal_queries = [
                    f'"{query}" court case',
                    f'"{query}" ruling decision',
                    f'"{query}" legal precedent',
                ]

                # Add platform filters
                for platform in ['caselaw', 'justia', 'courtlistener', 'bailii'][:2]:
                    if platform in LEGAL_PLATFORMS:
                        legal_queries.append(f'{LEGAL_PLATFORMS[platform]} {query}')

                for legal_query in legal_queries[:4]:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    output_file = f"results/legal_{timestamp}.json"

                    searcher = BruteSearchEngine(
                        keyword=legal_query,
                        output_file=output_file,
                        engines=LEGAL_ENGINES,
                        max_workers=min(len(LEGAL_ENGINES), 3),
                        event_emitter=self.event_emitter,
                        return_results=True
                    )
                    searcher.search()

                    if hasattr(searcher, 'final_results'):
                        for result in searcher.final_results:
                            url = result.get('url', '')
                            if url and url not in seen_urls:
                                seen_urls.add(url)
                                result['search_type'] = 'legal'
                                result['method'] = 'brute_fallback'
                                all_results.append(result)

                    if len(all_results) >= max_results:
                        break

            except Exception as e:
                logger.warning(f"Fallback legal search failed: {e}")

        # Score and sort results
        scored_results = self._score_legal_results(all_results, query)

        if self.streamer:
            await self.streamer.emit_search_completed('legal', len(scored_results))

        logger.info(f"Legal search completed with {len(scored_results)} total results")

        return scored_results[:max_results]

    def _score_legal_results(self, results: List[Dict], query: str) -> List[Dict]:
        """Score and sort legal results by relevance."""
        query_lower = query.lower()

        def score_result(result):
            score = 0
            url = result.get('url', '').lower()
            title = result.get('title', '').lower()
            snippet = result.get('snippet', '').lower()

            # High-value legal domains
            high_value = ['courtlistener.com', 'caselaw.findlaw.com', 'justia.com',
                         'law.cornell.edu', 'bailii.org', 'canlii.org', 'austlii.edu.au']
            for domain in high_value:
                if domain in url:
                    score += 50
                    break

            # Court domains
            court_domains = ['judiciary.uk', 'supremecourt.', 'courts.gov', 'uscourts.gov']
            for domain in court_domains:
                if domain in url:
                    score += 60
                    break

            # TORPEDO source bonus
            if result.get('method') == 'torpedo':
                score += 30

            # Legal keywords
            legal_keywords = ['court', 'case', 'ruling', 'judgment', 'verdict',
                            'plaintiff', 'defendant', 'appeal', 'statute', 'law']
            for keyword in legal_keywords:
                if keyword in title:
                    score += 20
                    break

            # Query match
            if query_lower in title:
                score += 25
            if query_lower in snippet:
                score += 15

            # Case citation patterns
            import re
            citation_pattern = r'\d+\s*(U\.?S\.?|F\.\d+d?|S\.?Ct\.?|L\.?Ed\.?)'
            if re.search(citation_pattern, title) or re.search(citation_pattern, snippet):
                score += 15

            # BrightData Archive
            if result.get('source') == 'brightdata_archive':
                score += 10

            return score

        for result in results:
            result['legal_score'] = score_result(result)

        results.sort(key=lambda x: x.get('legal_score', 0), reverse=True)

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


def detect_legal_query(query: str) -> bool:
    """Detect if a query should be routed to legal search."""
    query_lower = query.lower()

    legal_patterns = [
        'legal:',
        'court:',
        'case:',
        'litigation:',
        'lawsuit:',
        'ruling:',
    ]

    for pattern in legal_patterns:
        if pattern in query_lower:
            return True

    return False


def extract_legal_query(query: str) -> str:
    """Extract the actual search query from a legal search query."""
    query = query.strip()

    prefixes = [
        'legal:', 'court:', 'case:', 'litigation:', 'lawsuit:', 'ruling:',
        'Legal:', 'Court:', 'Case:', 'Litigation:', 'Lawsuit:', 'Ruling:'
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


async def run_legal_search(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """Main entry point for legal search."""
    clean_query = extract_legal_query(query)
    searcher = LegalSearcher(event_emitter)
    return await searcher.search(clean_query)


def run_legal_search_sync(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """Synchronous wrapper for legal search."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(run_legal_search(query, event_emitter))
    finally:
        loop.close()


def search(query: str, max_results: int = 100) -> List[Dict[str, Any]]:
    """Synchronous search function for web API compatibility."""
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, run_legal_search(query))
            return future.result()
    except RuntimeError:
        return asyncio.run(run_legal_search(query))


def main():
    """Main entry point for Legal search - compatible with SearchRouter"""
    import argparse

    parser = argparse.ArgumentParser(description='Legal/court case search')
    parser.add_argument('-q', '--query', required=True, help='Search query')
    parser.add_argument('-j', '--jurisdiction', help='Jurisdiction filter (UK, US)')
    args = parser.parse_args()

    query = args.query

    if ':' in query:
        clean_query = query.split(':', 1)[1].strip()
    else:
        clean_query = query

    print(f"\n🔍 Legal search: {clean_query}")
    if args.jurisdiction:
        print(f"   Jurisdiction: {args.jurisdiction}")

    results = run_legal_search_sync(clean_query)

    if results:
        print(f"\nFound {len(results)} results:")
        for i, result in enumerate(results[:10], 1):
            print(f"\n{i}. {result.get('title', 'No Title')}")
            print(f"   URL: {result.get('url')}")
            print(f"   Source: {result.get('source', 'Unknown')}")
    else:
        print("\nNo results found.")

    return results


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        test_query = ' '.join(sys.argv[1:])
    else:
        test_query = "legal:contract breach damages"

    print(f"Testing legal search with: {test_query}")

    if detect_legal_query(test_query):
        print("Legal query detected!")
        clean_query = extract_legal_query(test_query)
        print(f"Extracted query: '{clean_query}'")

        results = run_legal_search_sync(test_query)

        print(f"\nFound {len(results)} legal results:")
        for i, result in enumerate(results[:10], 1):
            print(f"\n{i}. {result.get('title', 'No title')}")
            print(f"   URL: {result.get('url', 'No URL')}")
            print(f"   Source: {result.get('source', 'Unknown')}")
    else:
        print("Not a legal query")
