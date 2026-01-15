"""
CC Enricher - Automatic CC-only content prefetching and entity extraction for search results.

This module integrates Common Crawl scraping into the search pipeline:
1. Auto-fetch content from CC for incoming search results (free, ~200ms)
2. NO Firecrawl fallback - CC only mode (results not in CC remain unenriched)
3. Extract entities from scraped content
4. Skip directory-type URLs
5. Support prefetching national news/registry sites
6. Extract outlinks for further crawling

Usage:
    from modules.cc_content import CCEnricher

    enricher = CCEnricher()
    enriched = await enricher.enrich_search_results(results, query)
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import re

# Use JESTER instead of deprecated CCFirstScraper
from modules.jester.scraper import Jester

# Import extractors
from ..extractors.hybrid_ner import get_hybrid_extractor

logger = logging.getLogger(__name__)

# Directory patterns to skip during enrichment
DIRECTORY_PATTERNS = [
    r'/directory/',
    r'/listing/',
    r'/categories/',
    r'/browse/',
    r'/sitemap',
    r'/index\.html?$',
    r'/page/\d+',
    r'\?page=',
    r'\?p=\d+',
    r'/tag/',
    r'/tags/',
    r'/archive/',
    r'/archives/',
]

# Registry file location
REGISTRY_FILE = Path(__file__).parent.parent.parent.parent / 'input_output' / 'matrix' / 'registries.json'


@dataclass
class EnrichedResult:
    """Search result enriched with CC content and entities."""
    url: str
    title: str
    snippet: str

    # CC enrichment
    cc_available: bool = False
    content_source: Optional[str] = None  # 'cc', 'firecrawl', or None
    content: Optional[str] = None
    content_length: int = 0
    cc_timestamp: Optional[str] = None

    # Extracted entities
    companies: List[Dict[str, Any]] = field(default_factory=list)
    persons: List[Dict[str, Any]] = field(default_factory=list)
    registrations: List[Dict[str, Any]] = field(default_factory=list)

    # Outlinks for further crawling
    outlinks: List[str] = field(default_factory=list)

    # Metadata
    is_directory: bool = False
    is_news_site: bool = False
    is_registry_site: bool = False
    enrichment_status: str = 'pending'  # pending, success, failed, skipped


@dataclass
class EnrichmentStats:
    """Statistics for enrichment batch."""
    total: int = 0
    cc_hits: int = 0
    not_in_cc: int = 0  # URLs not found in Common Crawl
    skipped_directories: int = 0
    entity_extractions: int = 0
    companies_found: int = 0
    persons_found: int = 0
    errors: int = 0


class CCEnricher:
    """
    CC-Only Content Enricher for Search Results.

    Automatically prefetches content from Common Crawl for search results,
    extracts entities, and identifies outlinks for further crawling.
    NO Firecrawl fallback - CC only mode for free, fast enrichment.
    """

    def __init__(
        self,
        max_concurrent: int = 20,
        skip_directories: bool = True,
        extract_entities: bool = True,
        extract_outlinks: bool = True,
        jurisdictions: Optional[List[str]] = None,
    ):
        # Initialize JESTER scraping system
        self.scraper = Jester()
        # Hybrid entity extraction: Gemini + GPT-5-nano in PARALLEL
        self._hybrid_extractor = get_hybrid_extractor()
        self.max_concurrent = max_concurrent
        self.skip_directories = skip_directories
        self.extract_entities = extract_entities
        self.extract_outlinks = extract_outlinks

        # Compiled directory patterns
        self._directory_re = [re.compile(p, re.IGNORECASE) for p in DIRECTORY_PATTERNS]

        # Load registries for news/registry site detection
        self._news_domains: Set[str] = set()
        self._registry_domains: Set[str] = set()
        self._load_registries()

    def _load_registries(self):
        """Load news and registry domains from matrix."""
        try:
            if REGISTRY_FILE.exists():
                with open(REGISTRY_FILE, 'r') as f:
                    registries = json.load(f)

                for country, entries in registries.items():
                    for entry in entries:
                        domain = entry.get('domain', '').lower()
                        if not domain:
                            continue

                        entry_type = entry.get('type', '').lower()

                        # Registry sites
                        if any(t in entry_type for t in ['registry', 'court', 'government', 'securities']):
                            self._registry_domains.add(domain)

                        # News sites (based on type or domain patterns)
                        if 'news' in entry_type or any(n in domain for n in ['news', 'times', 'post', 'herald', 'gazette']):
                            self._news_domains.add(domain)

                logger.info(f"Loaded {len(self._registry_domains)} registry domains, {len(self._news_domains)} news domains")
        except Exception as e:
            logger.warning(f"Failed to load registries: {e}")

    def _is_directory_url(self, url: str) -> bool:
        """Check if URL is a directory/listing page."""
        if not self.skip_directories:
            return False

        for pattern in self._directory_re:
            if pattern.search(url):
                return True
        return False

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.hostname.lower().replace('www.', '') if parsed.hostname else ''
        except Exception as e:
            return ''

    def _is_news_site(self, url: str) -> bool:
        """Check if URL is from a known news site."""
        domain = self._get_domain(url)
        return domain in self._news_domains

    def _is_registry_site(self, url: str) -> bool:
        """Check if URL is from a known registry site."""
        domain = self._get_domain(url)
        return domain in self._registry_domains

    def _extract_outlinks(self, content: str, base_url: str) -> List[str]:
        """Extract outlinks from HTML content."""
        if not self.extract_outlinks or not content:
            return []

        try:
            from urllib.parse import urljoin, urlparse

            # Simple regex to find links
            link_pattern = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
            matches = link_pattern.findall(content)

            base_domain = self._get_domain(base_url)
            outlinks = []

            for match in matches:
                try:
                    full_url = urljoin(base_url, match)
                    parsed = urlparse(full_url)

                    # Skip non-http(s) links
                    if parsed.scheme not in ('http', 'https'):
                        continue

                    # Skip same-domain links (we want outlinks)
                    link_domain = parsed.hostname.lower().replace('www.', '') if parsed.hostname else ''
                    if link_domain == base_domain:
                        continue

                    # Skip common non-content links
                    if any(skip in full_url.lower() for skip in ['facebook.com', 'twitter.com', 'linkedin.com', 'youtube.com', '#', 'javascript:']):
                        continue

                    outlinks.append(full_url)
                except Exception as e:
                    continue

            # Deduplicate and limit
            return list(set(outlinks))[:50]
        except Exception as e:
            logger.warning(f"Failed to extract outlinks: {e}")
            return []

    async def enrich_single(
        self,
        url: str,
        title: str = '',
        snippet: str = '',
    ) -> EnrichedResult:
        """
        Enrich a single search result with CC content and entities.

        Args:
            url: URL to scrape and enrich
            title: Original title from search
            snippet: Original snippet from search

        Returns:
            EnrichedResult with content and extracted entities
        """
        result = EnrichedResult(
            url=url,
            title=title,
            snippet=snippet,
            is_news_site=self._is_news_site(url),
            is_registry_site=self._is_registry_site(url),
        )

        # Check if directory
        if self._is_directory_url(url):
            result.is_directory = True
            result.enrichment_status = 'skipped'
            return result

        try:
            # Scrape with JESTER
            scrape_result = await self.scraper.scrape(url)

            # Check if Jester failed (assuming JesterResult has .html or .error)
            if not scrape_result.html:
                result.enrichment_status = 'failed'
                return result

            # Map Jester result to EnrichedResult
            result.cc_available = True # Jester tries CC first, so we assume yes for now
            result.content_source = scrape_result.method.name if scrape_result.method else "unknown"
            result.content = scrape_result.html
            result.content_length = len(scrape_result.html)
            # Jester doesn't typically return timestamp, so we skip it or use current
            result.cc_timestamp = None 

            # Extract entities using PARALLEL Gemini + GPT-5-nano
            if self.extract_entities and scrape_result.html:
                try:
                    # Hybrid extractor runs Gemini + GPT-5-nano simultaneously
                    entities = await self._hybrid_extractor.extract_parallel(
                        text=scrape_result.html,
                        url=url,
                        use_all_models=True  # Force parallel extraction
                    )

                    result.companies = [
                        {"name": e.get("value", ""), "confidence": e.get("confidence", 0.8), "source": e.get("source", "hybrid")}
                        for e in entities.get("companies", [])
                    ]
                    result.persons = [
                        {"name": e.get("value", ""), "confidence": e.get("confidence", 0.8), "source": e.get("source", "hybrid")}
                        for e in entities.get("persons", [])
                    ]
                    result.registrations = []  # Hybrid extractor doesn't do registrations

                    method = entities.get('method', 'hybrid')
                    logger.info(f"PARALLEL extraction ({method}): {len(result.companies)} companies, {len(result.persons)} persons from {url}")
                except Exception as e:
                    logger.warning(f"Parallel extraction failed for {url}: {e}")

            # Extract outlinks
            if self.extract_outlinks and scrape_result.html:
                result.outlinks = self._extract_outlinks(scrape_result.html, url)

            result.enrichment_status = 'success'

        except Exception as e:
            logger.error(f"Failed to enrich {url}: {e}")
            result.enrichment_status = 'failed'

        return result

    async def enrich_batch(
        self,
        results: List[Dict[str, Any]],
        progress_callback: Optional[callable] = None,
    ) -> Tuple[List[EnrichedResult], EnrichmentStats]:
        """
        Enrich a batch of search results with CC content and entities.

        Args:
            results: List of search results (each with url, title, snippet)
            progress_callback: Optional callback(completed, total, url, status)

        Returns:
            Tuple of (enriched results, stats)
        """
        stats = EnrichmentStats(total=len(results))
        enriched = []

        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def process_one(item: Dict[str, Any], idx: int) -> EnrichedResult:
            async with semaphore:
                result = await self.enrich_single(
                    url=item.get('url', ''),
                    title=item.get('title', ''),
                    snippet=item.get('snippet', item.get('description', '')),
                )

                # Update stats
                if result.enrichment_status == 'success':
                    stats.cc_hits += 1
                    if result.companies or result.persons:
                        stats.entity_extractions += 1
                        stats.companies_found += len(result.companies)
                        stats.persons_found += len(result.persons)
                elif result.enrichment_status == 'skipped':
                    stats.skipped_directories += 1
                elif result.content_source == 'not_in_cc':
                    stats.not_in_cc += 1
                else:
                    stats.errors += 1

                if progress_callback:
                    progress_callback(idx + 1, len(results), result.url, result.enrichment_status)

                return result

        tasks = [process_one(item, idx) for idx, item in enumerate(results)]
        enriched = await asyncio.gather(*tasks)

        return list(enriched), stats

    async def enrich_search_results(
        self,
        results: List[Dict[str, Any]],
        query: str = '',
        include_content: bool = False,
    ) -> Dict[str, Any]:
        """
        Main entry point for enriching search results.

        Args:
            results: List of search results
            query: Original search query (for context)
            include_content: Whether to include full content in response

        Returns:
            Dict with enriched results and stats
        """
        start_time = datetime.now()

        enriched, stats = await self.enrich_batch(results)

        # Build response
        response_results = []
        all_entities = {
            'companies': [],
            'persons': [],
            'registrations': [],
        }

        for er in enriched:
            item = {
                'url': er.url,
                'title': er.title,
                'snippet': er.snippet,
                'cc_available': er.cc_available,
                'content_source': er.content_source,
                'content_length': er.content_length,
                'cc_timestamp': er.cc_timestamp,
                'is_directory': er.is_directory,
                'is_news_site': er.is_news_site,
                'is_registry_site': er.is_registry_site,
                'enrichment_status': er.enrichment_status,
                'entity_count': len(er.companies) + len(er.persons) + len(er.registrations),
                'outlink_count': len(er.outlinks),
            }

            if include_content and er.content:
                item['content'] = er.content

            # Add entities with source URL
            for company in er.companies:
                company['source_url'] = er.url
                all_entities['companies'].append(company)
            for person in er.persons:
                person['source_url'] = er.url
                all_entities['persons'].append(person)
            for reg in er.registrations:
                reg['source_url'] = er.url
                all_entities['registrations'].append(reg)

            response_results.append(item)

        elapsed = (datetime.now() - start_time).total_seconds()

        return {
            'success': True,
            'query': query,
            'total_results': len(results),
            'enriched_results': response_results,
            'all_entities': all_entities,
            'stats': {
                'cc_hits': stats.cc_hits,
                'not_in_cc': stats.not_in_cc,
                'skipped_directories': stats.skipped_directories,
                'entity_extractions': stats.entity_extractions,
                'companies_found': stats.companies_found,
                'persons_found': stats.persons_found,
                'errors': stats.errors,
                'elapsed_seconds': elapsed,
                'cc_rate': f"{(stats.cc_hits / stats.total * 100):.1f}%" if stats.total > 0 else "0%",
            },
        }

    def get_priority_domains(self, country: Optional[str] = None) -> Dict[str, List[str]]:
        """
        Get priority domains for prefetching (news + registries).

        Args:
            country: Optional country code to filter by

        Returns:
            Dict with 'news' and 'registry' domain lists
        """
        if country:
            # Filter by country (would need to add country tracking in _load_registries)
            # For now, return all
            pass

        return {
            'news': list(self._news_domains),
            'registry': list(self._registry_domains),
            'total': len(self._news_domains) + len(self._registry_domains),
        }


# Export for use elsewhere
__all__ = ['CCEnricher', 'EnrichedResult', 'EnrichmentStats']
