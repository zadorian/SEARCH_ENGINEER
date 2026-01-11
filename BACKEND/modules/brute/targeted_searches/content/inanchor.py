#!/usr/bin/env python3
"""
InAnchor Search - Find pages by searching anchor text (link text) pointing to them

Anchor text is the visible, clickable text in a hyperlink. Searching anchor text
finds pages that others link TO using specific keywords.

Example: inanchor:"annual report" finds pages that other sites link to with
         anchor text containing "annual report"

Data Sources:
- Majestic GetAnchorText: Returns anchor text used in backlinks to a domain
- Majestic SearchByKeyword: Searches Title/URL/Anchor across their index
- Google inanchor: operator (when available)
- Bing inanchor: operator (when available)
- Common Crawl WAT files: Contain outlink anchor text data
"""

import sys
import asyncio
import logging
from pathlib import Path
from typing import List, Set, Dict, Optional, Tuple, Any
from datetime import datetime
import json
import os

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'engines'))

logger = logging.getLogger(__name__)

# Import search engines with error handling
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
    from exact_phrase_recall_runner_brave import BraveSearch
    BRAVE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import Brave search: {e}")
    BRAVE_AVAILABLE = False

# Import Majestic for anchor text search
# GetAnchorText: Returns all anchor text phrases used to link TO a target domain
# SearchByKeyword: Searches Title/URL/Anchor across their entire index
try:
    import httpx
    MAJESTIC_API_KEY = os.getenv("MAJESTIC_API_KEY")
    MAJESTIC_AVAILABLE = bool(MAJESTIC_API_KEY)
    MAJESTIC_BASE_URL = "https://api.majestic.com/api/json"
    if not MAJESTIC_AVAILABLE:
        logger.warning("MAJESTIC_API_KEY not set - Majestic anchor search disabled")
except ImportError:
    MAJESTIC_AVAILABLE = False
    MAJESTIC_API_KEY = None
    MAJESTIC_BASE_URL = None

# Import Common Crawl for WAT-based anchor search
# WAT files contain link metadata including anchor text for all outlinks
try:
    from modules.LINKLATER.search import CommonCrawlAnchorSearch
    CC_ANCHOR_AVAILABLE = True
except ImportError:
    try:
        # Fallback - direct WAT parser
        from alldom.providers.commoncrawl import CommonCrawlProvider
        CC_ANCHOR_AVAILABLE = True
        CommonCrawlAnchorSearch = None  # Will use provider directly
    except ImportError:
        logger.warning("Common Crawl anchor search not available")
        CC_ANCHOR_AVAILABLE = False
        CommonCrawlAnchorSearch = None

# Import GlobalLinks for FAST anchor text search
# GlobalLinks Go binaries return anchor_text directly from pre-processed WAT files
# This is the FASTEST path for anchor text when you have a target domain
try:
    from modules.LINKLATER.linkgraph.globallinks import GlobalLinksClient
    GLOBALLINKS_AVAILABLE = True
except ImportError:
    logger.warning("GlobalLinks not available - fast anchor search disabled")
    GLOBALLINKS_AVAILABLE = False
    GlobalLinksClient = None

# Import ParallelWATFetcher for high-throughput WAT processing
# 20-50x speedup through concurrent downloads, extracts links with anchor text
try:
    from modules.LINKLATER.parallel_wat_fetcher import ParallelWATFetcher
    PARALLEL_WAT_AVAILABLE = True
except ImportError:
    logger.warning("ParallelWATFetcher not available")
    PARALLEL_WAT_AVAILABLE = False
    ParallelWATFetcher = None

# Import BacklinkDiscovery for direct WARC range requests with anchor extraction
try:
    from modules.LINKLATER.linkgraph.backlinks import BacklinkDiscovery
    BACKLINK_DISCOVERY_AVAILABLE = True
except ImportError:
    logger.warning("BacklinkDiscovery not available")
    BACKLINK_DISCOVERY_AVAILABLE = False
    BacklinkDiscovery = None

# Import snippet enrichment
try:
    from snippet_enrichment import SnippetEnricher
    ENRICHMENT_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import snippet enrichment: {e}")
    ENRICHMENT_AVAILABLE = False


class InAnchorSearch:
    """Search for pages by anchor text (link text) pointing to them"""

    def __init__(self):
        """Initialize search engine instances"""
        self.google_search = GoogleSearch() if GOOGLE_AVAILABLE else None
        self.bing_search = BingSearch() if BING_AVAILABLE else None
        self.brave_search = BraveSearch() if BRAVE_AVAILABLE else None
        self.enricher = SnippetEnricher() if ENRICHMENT_AVAILABLE else None

        # Track which engines are available
        self.available_engines = []
        if GOOGLE_AVAILABLE: self.available_engines.append('google')
        if BING_AVAILABLE: self.available_engines.append('bing')
        if BRAVE_AVAILABLE: self.available_engines.append('brave')
        if MAJESTIC_AVAILABLE: self.available_engines.append('majestic')
        if CC_ANCHOR_AVAILABLE: self.available_engines.append('common_crawl')
        if GLOBALLINKS_AVAILABLE: self.available_engines.append('globallinks')
        if PARALLEL_WAT_AVAILABLE: self.available_engines.append('parallel_wat')
        if BACKLINK_DISCOVERY_AVAILABLE: self.available_engines.append('backlink_discovery')

        logger.info(f"InAnchor Search initialized with engines: {self.available_engines}")

        # For tracking filtered results
        self.filtered_results = []

    def generate_search_variations(self, keyword: str) -> List[Tuple[str, str]]:
        """Generate L1/L2/L3 query variations for anchor text search"""
        variations = []

        # L1: Native Operator (High Precision)
        if ' ' in keyword:
            # Phrase - must be quoted
            variations.append((f'inanchor:"{keyword}"', 'L1'))
            variations.append((f'allinanchor:{keyword}', 'L1'))
        else:
            variations.append((f'inanchor:{keyword}', 'L1'))

        # L2: Alternative operators and tricks
        # Try link: operator as it's related to incoming links
        variations.append((f'link:"{keyword}"', 'L2'))

        # L3: Brute Force with strict filtering
        # Search for keyword anywhere, then filter via Majestic anchor data
        variations.append((f'"{keyword}"', 'L3'))

        return variations

    async def search_anchors(
        self,
        keyword: str,
        target_domain: Optional[str] = None,
        max_results: int = 100
    ) -> Dict[str, Any]:
        """
        Search for pages linked with specific anchor text.

        Args:
            keyword: The anchor text keyword to search for
            target_domain: Optional - if provided, find anchor text linking TO this domain
            max_results: Maximum results per engine

        Returns:
            Dictionary with search results and Majestic anchor data
        """
        self.filtered_results = []
        all_results = {}

        # Generate query variations
        variations = self.generate_search_variations(keyword)

        # Create tasks for parallel execution
        tasks = []

        # FAST PATH: If target_domain is provided, use GlobalLinks first (fastest)
        # GlobalLinks Go binaries return anchor_text directly from pre-processed WAT
        if target_domain and GLOBALLINKS_AVAILABLE:
            tasks.append(self._search_anchors_via_globallinks(target_domain, keyword, max_results))

        # If target_domain is provided, also use Majestic GetAnchorText
        if target_domain and MAJESTIC_AVAILABLE:
            tasks.append(self._get_anchor_text_for_domain(target_domain, keyword, max_results))

        # BacklinkDiscovery - direct WARC range requests with anchor extraction
        # Good for specific target domains
        if target_domain and BACKLINK_DISCOVERY_AVAILABLE:
            tasks.append(self._search_anchors_via_backlink_discovery(target_domain, keyword, max_results))

        # Majestic SearchByKeyword - searches their index for anchor text matches
        # Works without target domain (global search)
        if MAJESTIC_AVAILABLE:
            tasks.append(self._search_anchors_via_majestic(keyword, max_results))

        # Common Crawl WAT - contains outlink anchor text from crawled pages
        if CC_ANCHOR_AVAILABLE:
            tasks.append(self._search_anchors_via_cc(keyword, target_domain, max_results))

        # ParallelWATFetcher - high-throughput WAT processing (20-50x speedup)
        # Best for bulk domain discovery with anchor filtering
        if PARALLEL_WAT_AVAILABLE and target_domain:
            tasks.append(self._search_anchors_via_parallel_wat(target_domain, keyword, max_results))

        # Helper to run search engine
        async def run_engine_search(engine_name, engine_instance, variation, strategy):
            try:
                loop = asyncio.get_event_loop()
                limit = max(10, max_results // len(variations))
                results = await loop.run_in_executor(None, engine_instance.search, variation, limit)

                valid_results = []
                for item in results:
                    url = item.get('url', '') if isinstance(item, dict) else str(item)
                    title = item.get('title', '') if isinstance(item, dict) else ''
                    snippet = item.get('snippet', '') if isinstance(item, dict) else ''

                    if not url:
                        continue

                    valid_results.append({
                        'url': url,
                        'title': title,
                        'snippet': snippet,
                        'source': engine_name,
                        'strategy': strategy,
                    })

                return engine_name, valid_results
            except Exception as e:
                logger.error(f"{engine_name} search error: {e}")
                return engine_name, []

        # Launch search engine tasks
        for query_var, strategy in variations:
            if self.google_search:
                tasks.append(run_engine_search('google', self.google_search, query_var, strategy))
            if self.bing_search:
                tasks.append(run_engine_search('bing', self.bing_search, query_var, strategy))
            # Brave doesn't support inanchor well, skip for L1
            if self.brave_search and strategy != 'L1':
                tasks.append(run_engine_search('brave', self.brave_search, query_var, strategy))

        # Execute all tasks
        if tasks:
            results_list = await asyncio.gather(*tasks, return_exceptions=True)

            for res in results_list:
                if isinstance(res, Exception):
                    logger.error(f"Task error: {res}")
                    continue
                if isinstance(res, tuple) and len(res) == 2:
                    engine, results = res
                    if engine not in all_results:
                        all_results[engine] = []
                    # Dedupe by URL
                    seen_urls = {r['url'] for r in all_results[engine]}
                    for r in results:
                        if r['url'] not in seen_urls:
                            all_results[engine].append(r)
                            seen_urls.add(r['url'])
                elif isinstance(res, dict):
                    # Majestic results
                    if 'anchor_text' in res:
                        all_results['majestic_anchor_text'] = res
                    elif 'search_results' in res:
                        all_results['majestic_search'] = res

        return all_results

    async def _get_anchor_text_for_domain(
        self,
        domain: str,
        filter_keyword: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Get anchor text phrases used to link TO a specific domain.

        Uses Majestic GetAnchorText API.

        Args:
            domain: The target domain to get incoming anchor text for
            filter_keyword: Optional keyword to filter anchor text by
            limit: Maximum anchor phrases to return

        Returns:
            Dict with anchor_text list and statistics
        """
        if not MAJESTIC_AVAILABLE:
            return {"anchor_text": [], "error": "Majestic not available"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # GetAnchorText params:
                # - item0: The domain to analyze
                # - Mode: 0=exact URL, 1=subdomain, 2=root domain
                # - datasource: historic or fresh
                # - MaxTopics: Number of anchor phrases
                params = {
                    "app_api_key": MAJESTIC_API_KEY,
                    "cmd": "GetAnchorText",
                    "item0": domain,
                    "Mode": 2,  # Root domain
                    "datasource": "fresh",  # Fresh index for recent anchors
                    "MaxTopics": min(limit, 500),
                }

                response = await client.get(MAJESTIC_BASE_URL, params=params)
                response.raise_for_status()
                data = response.json()

                if data.get("Code") != "OK":
                    logger.warning(f"Majestic GetAnchorText error: {data.get('ErrorMessage', 'Unknown')}")
                    return {"anchor_text": [], "error": data.get("ErrorMessage")}

                # Extract anchor text phrases
                anchor_phrases = []
                items = data.get("DataTables", {}).get("AnchorText", {}).get("Data", [])

                for item in items:
                    anchor = item.get("AnchorText", "")
                    ref_domains = item.get("RefDomains", 0)
                    total_links = item.get("TotalLinks", 0)

                    # Filter by keyword if provided
                    if filter_keyword:
                        if filter_keyword.lower() not in anchor.lower():
                            continue

                    anchor_phrases.append({
                        "anchor_text": anchor,
                        "referring_domains": ref_domains,
                        "total_links": total_links,
                        "target_domain": domain,
                    })

                logger.info(f"Majestic GetAnchorText returned {len(anchor_phrases)} phrases for {domain}")
                return {
                    "anchor_text": anchor_phrases,
                    "target_domain": domain,
                    "filter_keyword": filter_keyword,
                    "total_found": len(anchor_phrases),
                }

        except httpx.TimeoutException:
            logger.warning(f"Majestic GetAnchorText timeout for {domain}")
            return {"anchor_text": [], "error": "Timeout"}
        except Exception as e:
            logger.error(f"Majestic GetAnchorText error: {e}")
            return {"anchor_text": [], "error": str(e)}

    async def _search_anchors_via_majestic(self, keyword: str, max_results: int) -> Dict[str, Any]:
        """
        Search Majestic's index for pages linked with specific anchor text.

        Uses SearchByKeyword which searches Title/URL/Anchor across their index.
        We're specifically interested in anchor text matches here.

        Args:
            keyword: The anchor text keyword to search for
            max_results: Maximum results to return

        Returns:
            Dict with search results
        """
        if not MAJESTIC_AVAILABLE:
            return {"search_results": [], "error": "Majestic not available"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                params = {
                    "app_api_key": MAJESTIC_API_KEY,
                    "cmd": "SearchByKeyword",
                    "Query": keyword,
                    "Scope": 2,  # Both historic and fresh
                    "MaxResults": min(max_results, 100),
                    "Highlight": 0,
                }

                response = await client.get(MAJESTIC_BASE_URL, params=params)
                response.raise_for_status()
                data = response.json()

                if data.get("Code") != "OK":
                    logger.warning(f"Majestic SearchByKeyword error: {data.get('ErrorMessage')}")
                    return {"search_results": [], "error": data.get("ErrorMessage")}

                # Extract results
                results = []
                items = data.get("DataTables", {}).get("Results", {}).get("Data", [])

                for item in items:
                    url = item.get("URL", "")
                    title = item.get("Title", "")
                    # Majestic indicates where keyword matched
                    match_location = item.get("MatchLocation", "")

                    if url:
                        results.append({
                            "url": url,
                            "title": title,
                            "match_location": match_location,  # "anchor", "title", or "url"
                            "source": "majestic",
                        })

                # Prioritize anchor matches
                anchor_matches = [r for r in results if r.get("match_location") == "anchor"]
                other_matches = [r for r in results if r.get("match_location") != "anchor"]

                logger.info(f"Majestic anchor search: {len(anchor_matches)} anchor matches, {len(other_matches)} other")

                return {
                    "search_results": anchor_matches + other_matches,
                    "anchor_matches": len(anchor_matches),
                    "total_matches": len(results),
                    "keyword": keyword,
                }

        except httpx.TimeoutException:
            logger.warning(f"Majestic anchor search timeout for '{keyword}'")
            return {"search_results": [], "error": "Timeout"}
        except Exception as e:
            logger.error(f"Majestic anchor search error: {e}")
            return {"search_results": [], "error": str(e)}

    async def _search_anchors_via_cc(
        self,
        keyword: str,
        target_domain: Optional[str] = None,
        max_results: int = 100
    ) -> Dict[str, Any]:
        """
        Search Common Crawl WAT files for anchor text matches.

        WAT (Web Archive Transformation) files contain metadata extracted from
        WARC files, including all outlinks with their anchor text.

        Args:
            keyword: The anchor text keyword to search for
            target_domain: Optional - filter to links pointing to this domain
            max_results: Maximum results to return

        Returns:
            Dict with search results from CC
        """
        if not CC_ANCHOR_AVAILABLE:
            return {"search_results": [], "error": "Common Crawl not available"}

        try:
            # If we have the dedicated anchor search class, use it
            if CommonCrawlAnchorSearch is not None:
                searcher = CommonCrawlAnchorSearch()
                results = await searcher.search_by_anchor(
                    anchor_text=keyword,
                    target_domain=target_domain,
                    limit=max_results
                )
                return {
                    "search_results": results,
                    "source": "common_crawl",
                    "keyword": keyword,
                }

            # Fallback: Use CC index API to find pages, then check WAT for anchors
            # This is less efficient but works without the dedicated searcher
            from alldom.providers.commoncrawl import CommonCrawlProvider
            provider = CommonCrawlProvider()

            # Search CC index for pages that might link with this anchor
            # We search for the keyword in URLs as a proxy
            results = []

            if target_domain:
                # If target domain specified, get backlinks from CC
                snapshots = await provider.get_snapshots(
                    url=f"*.{target_domain}/*",
                    use_latest_index_only=True
                )
                # Filter and format
                for snap in snapshots[:max_results]:
                    results.append({
                        "url": snap.url,
                        "target": target_domain,
                        "source": "common_crawl",
                        "note": "Potential anchor match - verify via WAT",
                    })
            else:
                # General search - look for keyword in crawled content
                # CC CDX doesn't directly support anchor search, so this is approximate
                snapshots = await provider.get_snapshots(
                    url=f"*{keyword}*",
                    use_latest_index_only=True
                )
                for snap in snapshots[:max_results]:
                    results.append({
                        "url": snap.url,
                        "source": "common_crawl",
                        "note": "URL contains keyword - check anchor via WAT",
                    })

            logger.info(f"CC anchor search: {len(results)} potential matches for '{keyword}'")
            return {
                "search_results": results,
                "source": "common_crawl",
                "keyword": keyword,
                "approximate": True,  # Flag that this is not exact anchor matching
            }

        except Exception as e:
            logger.error(f"CC anchor search error: {e}")
            return {"search_results": [], "error": str(e)}

    async def _search_anchors_via_globallinks(
        self,
        target_domain: str,
        keyword: Optional[str] = None,
        max_results: int = 100
    ) -> Dict[str, Any]:
        """
        FASTEST PATH: Search anchor text via GlobalLinks Go binaries.

        GlobalLinks processes WAT files and returns anchor_text directly.
        30-60 seconds for full enrichment vs minutes for other methods.

        Args:
            target_domain: Domain to find backlinks for (required)
            keyword: Optional keyword to filter anchor text by
            max_results: Maximum results

        Returns:
            Dict with backlinks containing anchor text
        """
        if not GLOBALLINKS_AVAILABLE or GlobalLinksClient is None:
            return {"search_results": [], "error": "GlobalLinks not available"}

        try:
            client = GlobalLinksClient()

            # Get backlinks with anchor text
            # source_keywords filters pages containing keyword in anchor/content
            records = await client.get_backlinks(
                domain=target_domain,
                limit=max_results,
                source_keywords=[keyword] if keyword else None,
            )

            # Filter and format results
            results = []
            for record in records:
                anchor = record.anchor_text or ""

                # If keyword specified, filter by anchor text match
                if keyword and keyword.lower() not in anchor.lower():
                    continue

                results.append({
                    "source_url": record.source,
                    "target_domain": target_domain,
                    "anchor_text": anchor,
                    "source": "globallinks",
                })

            logger.info(f"GlobalLinks: {len(results)} backlinks with anchor text for {target_domain}")
            return {
                "search_results": results,
                "source": "globallinks",
                "target_domain": target_domain,
                "keyword": keyword,
            }

        except Exception as e:
            logger.error(f"GlobalLinks anchor search error: {e}")
            return {"search_results": [], "error": str(e)}

    async def _search_anchors_via_backlink_discovery(
        self,
        target_domain: str,
        keyword: Optional[str] = None,
        max_results: int = 100
    ) -> Dict[str, Any]:
        """
        Search anchor text via BacklinkDiscovery (direct WARC range requests).

        Uses CC Index API to find pages, then fetches specific byte ranges
        from WARC files to extract links with anchor text.

        Args:
            target_domain: Domain to find backlinks for
            keyword: Optional keyword to filter anchor text by
            max_results: Maximum results

        Returns:
            Dict with extracted links and anchor text
        """
        if not BACKLINK_DISCOVERY_AVAILABLE or BacklinkDiscovery is None:
            return {"search_results": [], "error": "BacklinkDiscovery not available"}

        try:
            discovery = BacklinkDiscovery()

            # Get backlinks with anchor text extraction
            backlinks = await discovery.get_backlinks(
                domain=target_domain,
                limit=max_results,
                extract_anchor=True,  # Enable anchor text extraction
            )

            # Filter and format results
            results = []
            for bl in backlinks:
                anchor = bl.get("anchor_text", "") or ""

                # If keyword specified, filter by anchor text match
                if keyword and keyword.lower() not in anchor.lower():
                    continue

                results.append({
                    "source_url": bl.get("url", ""),
                    "target_domain": target_domain,
                    "anchor_text": anchor,
                    "source": "backlink_discovery",
                })

            logger.info(f"BacklinkDiscovery: {len(results)} links with anchor text")
            return {
                "search_results": results,
                "source": "backlink_discovery",
                "target_domain": target_domain,
                "keyword": keyword,
            }

        except Exception as e:
            logger.error(f"BacklinkDiscovery anchor search error: {e}")
            return {"search_results": [], "error": str(e)}

    async def _search_anchors_via_parallel_wat(
        self,
        target_domain: str,
        keyword: Optional[str] = None,
        max_results: int = 100
    ) -> Dict[str, Any]:
        """
        High-throughput anchor search via ParallelWATFetcher.

        20-50x speedup through concurrent WAT downloads.
        Extracts links with anchor text from WAT metadata.

        Args:
            target_domain: Domain to find links for
            keyword: Optional keyword to filter anchor text by
            max_results: Maximum results

        Returns:
            Dict with extracted links and anchor text
        """
        if not PARALLEL_WAT_AVAILABLE or ParallelWATFetcher is None:
            return {"search_results": [], "error": "ParallelWATFetcher not available"}

        try:
            fetcher = ParallelWATFetcher()

            # Fetch WAT data for target domain
            results = []
            async for record in fetcher.process_wat_content(
                target_domains=[target_domain],
                max_results=max_results
            ):
                # Extract links with anchor text
                links = record.get("links", [])
                for link in links:
                    if isinstance(link, dict):
                        anchor = link.get("text", "") or ""
                        href = link.get("href", "") or link.get("url", "")

                        # If keyword specified, filter by anchor text match
                        if keyword and keyword.lower() not in anchor.lower():
                            continue

                        if href:
                            results.append({
                                "source_url": record.get("url", ""),
                                "target_url": href,
                                "anchor_text": anchor,
                                "source": "parallel_wat",
                            })

                if len(results) >= max_results:
                    break

            logger.info(f"ParallelWATFetcher: {len(results)} links with anchor text")
            return {
                "search_results": results,
                "source": "parallel_wat",
                "target_domain": target_domain,
                "keyword": keyword,
            }

        except Exception as e:
            logger.error(f"ParallelWATFetcher anchor search error: {e}")
            return {"search_results": [], "error": str(e)}

    async def discover_anchor_patterns(
        self,
        domain: str,
        min_referring_domains: int = 2
    ) -> Dict[str, Any]:
        """
        Discover common anchor text patterns used to link to a domain.

        Useful for understanding how a domain is perceived/referenced.

        Args:
            domain: Target domain to analyze
            min_referring_domains: Minimum referring domains for an anchor phrase

        Returns:
            Dict with anchor pattern analysis
        """
        anchor_data = await self._get_anchor_text_for_domain(domain, None, 500)

        if "error" in anchor_data:
            return anchor_data

        # Analyze patterns
        patterns = {
            "branded": [],      # Contains domain name
            "navigational": [], # "click here", "read more", etc.
            "topical": [],      # Descriptive of content
            "url": [],          # Naked URLs as anchor
        }

        navigational_phrases = ["click here", "read more", "learn more", "here", "link", "website", "site"]
        domain_parts = domain.replace("www.", "").split(".")[0].lower()

        for anchor in anchor_data.get("anchor_text", []):
            text = anchor["anchor_text"].lower()
            ref_domains = anchor["referring_domains"]

            if ref_domains < min_referring_domains:
                continue

            if domain_parts in text or domain.lower() in text:
                patterns["branded"].append(anchor)
            elif any(nav in text for nav in navigational_phrases):
                patterns["navigational"].append(anchor)
            elif text.startswith("http") or "." in text.split()[0] if text else False:
                patterns["url"].append(anchor)
            else:
                patterns["topical"].append(anchor)

        return {
            "domain": domain,
            "patterns": patterns,
            "summary": {
                "branded_count": len(patterns["branded"]),
                "navigational_count": len(patterns["navigational"]),
                "topical_count": len(patterns["topical"]),
                "url_count": len(patterns["url"]),
            },
            "top_topical": sorted(patterns["topical"], key=lambda x: x["referring_domains"], reverse=True)[:20],
        }


def is_inanchor_query(query: str) -> bool:
    """Check if query contains inanchor operators"""
    inanchor_patterns = ['inanchor:', 'allinanchor:']
    return any(pattern in query.lower() for pattern in inanchor_patterns)


class InanchorSearcher:
    """Standardized searcher class for inanchor searches that returns full results."""

    def __init__(self, additional_args: List[str] = None):
        self.additional_args = additional_args or []
        self.inanchor_search = InAnchorSearch()
        self.enricher = SnippetEnricher() if ENRICHMENT_AVAILABLE else None

    def search(self, query: str, target_domain: Optional[str] = None) -> Dict[str, Any]:
        """Standardized search method that returns results with anchor data."""
        try:
            # Extract keyword from query
            if query.lower().startswith('inanchor:'):
                keyword = query[9:].strip().strip('"\'')
            elif query.lower().startswith('allinanchor:'):
                keyword = query[12:].strip()
            else:
                keyword = query.strip()

            # Run async search synchronously
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                results = loop.run_until_complete(
                    self.inanchor_search.search_anchors(keyword, target_domain)
                )
            finally:
                loop.close()

            # Format results
            formatted_results = []
            seen_urls = set()

            # Collect from all sources
            for source, source_results in results.items():
                if source.startswith('majestic'):
                    # Handle Majestic results
                    if isinstance(source_results, dict):
                        for item in source_results.get('search_results', []):
                            url = item.get('url', '')
                            if url and url not in seen_urls:
                                seen_urls.add(url)
                                formatted_results.append({
                                    'url': url,
                                    'title': item.get('title', f'Page at {url}'),
                                    'snippet': f'Anchor match: {keyword}',
                                    'source': source,
                                    'match_location': item.get('match_location', 'unknown'),
                                    'rank': len(formatted_results) + 1,
                                })
                else:
                    # Handle search engine results
                    for item in source_results:
                        url = item.get('url', '') if isinstance(item, dict) else str(item)
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            formatted_results.append({
                                'url': url,
                                'title': item.get('title', f'Page at {url}') if isinstance(item, dict) else '',
                                'snippet': item.get('snippet', f'Anchor contains "{keyword}"') if isinstance(item, dict) else '',
                                'source': source,
                                'strategy': item.get('strategy', 'L1') if isinstance(item, dict) else 'L1',
                                'rank': len(formatted_results) + 1,
                            })

            # Include raw anchor text data if available
            anchor_text_data = None
            if 'majestic_anchor_text' in results:
                anchor_text_data = results['majestic_anchor_text']

            return {
                'query': query,
                'keyword': keyword,
                'target_domain': target_domain,
                'total_results': len(formatted_results),
                'results': formatted_results,
                'anchor_text_data': anchor_text_data,
                'search_type': 'inanchor',
                'engines_used': list(results.keys()),
            }

        except Exception as e:
            logger.error(f"Error during inanchor search: {e}")
            return {'error': str(e), 'results': []}


async def main():
    """Main function for testing"""
    print("""
    inAnchor - Anchor Text Search
    Find pages by the link text pointing to them

    Example: "annual report" finds pages linked with that anchor text
    """)

    if len(sys.argv) > 1:
        keyword = ' '.join(sys.argv[1:])
    else:
        keyword = input("Enter anchor text to search for: ").strip()

    if not keyword:
        print("Keyword required!")
        return

    target = input("Optional - target domain (or press Enter to skip): ").strip() or None

    searcher = InAnchorSearch()
    results = await searcher.search_anchors(keyword, target)

    print(f"\nPages linked with anchor text containing '{keyword}':")
    print("=" * 60)

    for source, data in results.items():
        print(f"\n{source.upper()}:")
        if isinstance(data, dict):
            if 'anchor_text' in data:
                print(f"  Anchor phrases found: {len(data['anchor_text'])}")
                for anchor in data['anchor_text'][:5]:
                    print(f"    - {anchor['anchor_text']} ({anchor['referring_domains']} domains)")
            elif 'search_results' in data:
                print(f"  Search results: {len(data['search_results'])}")
                for item in data['search_results'][:5]:
                    print(f"    - {item['url']}")
        elif isinstance(data, list):
            print(f"  Results: {len(data)}")
            for item in data[:5]:
                url = item.get('url', item) if isinstance(item, dict) else item
                print(f"    - {url}")


if __name__ == "__main__":
    asyncio.run(main())
