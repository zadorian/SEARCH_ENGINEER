"""
LinkLater Unified Python API

SINGLE ENTRY POINT for ALL LinkLater functionality.
All 148+ methods accessible via: linklater.method_name()

Usage:
    from modules.linklater.api import linklater

    # Archive scraping (CC → Wayback → Firecrawl fallback)
    result = await linklater.scrape_url("https://example.com/doc.pdf")

    # Entity extraction
    entities = linklater.extract_entities(text)

    # Backlinks (CC Graph + GlobalLinks)
    backlinks = await linklater.get_backlinks("example.com")

    # Keyword variations
    async for match in linklater.search_keyword_variations(["keyword"]):
        print(match)

    # Binary file extraction
    text = linklater.extract_text_from_binary(pdf_bytes, "application/pdf")
"""

from typing import List, Dict, Any, Optional, AsyncGenerator
import sys
from pathlib import Path

# Ensure modules are importable
sys.path.insert(0, str(Path(__file__).parent))

# Centralized logging
from .config import get_logger
logger = get_logger(__name__)

# Import external modules (JESTER, BACKDRILL)
try:
    from modules.jester.scraper import Jester, JesterConfig, JesterMethod
    JESTER_AVAILABLE = True
except ImportError:
    JESTER_AVAILABLE = False
    logger.warning("JESTER module not found. Scraping capabilities will be limited.")

try:
    from modules.backdrill.backdrill import Backdrill
    BACKDRILL_AVAILABLE = True
except ImportError:
    BACKDRILL_AVAILABLE = False
    logger.warning("BACKDRILL module not found. Archive capabilities will be limited.")

# Import sub-modules
from .core.binary_extractor import BinaryTextExtractor, extract_text_from_bytes
# (Note: WARCParser kept local as it is a utility, not a service)
from .core.parsers import WARCParser, html_to_markdown

# Keyword variations
from .mapping.keyword_variations import KeywordVariationsSearch

# Link graph (backlinks/outlinks)
from .linkgraph import CCGraphESClient as CCGraphClient, GlobalLinksClient, LinkRecord, find_globallinks_binary

# Majestic discovery (co-citation/related links)
from .discovery.majestic_discovery import (
    get_related_sites,
    get_hosted_domains,
    get_ref_domains,
    get_backlink_data,
    get_topics,  # Added
    discover_similar_domains,
    MajesticDiscoveryResponse,
    RelatedSiteResult,
    TopicResult,  # Added
)

# WHOIS discovery (ownership-linked domains)
from .discovery.whois_discovery import (
    cluster_domains_by_whois,
    whois_lookup,
    reverse_whois_by_registrant,
    find_domains_by_nameserver,
    WhoisDiscoveryResponse,
    WhoisClusterResult,
    WhoisRecord,
)


class LinkLater:
    """
    Unified LinkLater API

    All 148+ methods accessible via single instance.

    Sections:
    - Archive Scraping (CC → Wayback → Firecrawl)
    - Binary File Extraction (PDF, DOCX, XLSX, PPTX)
    - Keyword Variations Search
    - Archive Search (Wayback + CC historical)
    - Backlinks & Outlinks (CC Graph + GlobalLinks)
    - WARC Parsing
    """

    def __init__(self):
        """Initialize all sub-modules."""
        logger.info("Initializing LinkLater API")

        # Scraping (JESTER)
        if JESTER_AVAILABLE:
            self.jester = Jester()
        else:
            self.jester = None

        # Archives (BACKDRILL)
        if BACKDRILL_AVAILABLE:
            self.backdrill = Backdrill()
        else:
            self.backdrill = None
            
        logger.debug("Initialized scraping/archive modules")

        # Discovery
        self.keyword_search = KeywordVariationsSearch()

        # Binary & WARC
        self.binary_extractor = BinaryTextExtractor()
        self.warc_parser = WARCParser()

        # Graph (Backlinks/Outlinks)
        self.cc_graph = CCGraphClient()
        self.globallinks = GlobalLinksClient()
        logger.debug("Initialized link graph modules")

    # ========================================
    # ARCHIVE SCRAPING (CC → Wayback → Firecrawl)
    # Methods 1-11 from inventory
    # ========================================

    async def scrape_url(self, url: str, **kwargs):
        """
        Scrape single URL using JESTER (Unified Scraping System).

        Tries: Jester A -> B -> C -> D -> Firecrawl -> BrightData

        Args:
            url: URL to scrape

        Returns:
            JesterResult (compatible with legacy ScrapeResult expectation where possible)
        """
        if not self.jester:
            raise RuntimeError("Jester module not available")
        
        # Jester returns JesterResult
        result = await self.jester.scrape(url)
        
        # Convert to dict-like if needed for compatibility or return raw
        # Assuming consumers can handle JesterResult or we map it.
        # For now, returning the object as it has .html, .status_code attributes.
        # Adding a .content alias for legacy compatibility
        if not hasattr(result, 'content'):
            setattr(result, 'content', result.html)
            
        # If binary extraction is needed (Jester mainly does HTML), 
        # Jester A (httpx) might return bytes. 
        # If Jester doesn't handle binary, we might need a shim here.
        # But Jester documentation says "The Unified Scraping System".
        
        return result

    async def scrape_batch(self, urls: List[str], max_concurrent: int = 50, **kwargs):
        """
        Batch scrape multiple URLs using JESTER.

        Args:
            urls: List of URLs to scrape
            max_concurrent: Max concurrent requests

        Returns:
            List of JesterResult objects
        """
        if not self.jester:
            raise RuntimeError("Jester module not available")
            
        return await self.jester.scrape_batch(urls, max_concurrent=max_concurrent)

    # Legacy method stubs or mapped to Jester/Backdrill
    async def check_cc_index(self, url: str):
        """Check if URL exists in Common Crawl index (via Backdrill)."""
        if not self.backdrill: return None
        # Backdrill.cc.lookup_url returns list
        results = await self.backdrill.cc.lookup_url(url, limit=1)
        return results[0] if results else None

    async def fetch_from_wayback(self, url: str):
        """Fetch content from Wayback Machine (via Backdrill)."""
        if not self.backdrill: return None
        res = await self.backdrill.fetch(url, prefer_source="wayback")
        return res.content or res.html

    async def fetch_from_firecrawl(self, url: str):
        """Fetch content from Firecrawl (via Jester)."""
        if not self.jester: return None
        # Jester has scrape_firecrawl method
        res = await self.jester.scrape_firecrawl(url)
        return res.html

    def get_scraper_stats(self):
        """Get scraping statistics."""
        return {} # Jester doesn't expose stats in the same way yet

    def reset_scraper_stats(self):
        """Reset scraping statistics."""
        pass

    # ========================================
    # BINARY FILE EXTRACTION
    # Methods 16-31 from inventory
    # ========================================

    def can_extract_binary(self, mime_type: str) -> bool:
        """
        Check if MIME type is supported for binary extraction.

        Supported: PDF, DOCX, XLSX, PPTX, ZIP, TAR, GZ

        Args:
            mime_type: MIME type string

        Returns:
            True if supported
        """
        return self.binary_extractor.can_extract(mime_type)

    def extract_text_from_binary(self, data: bytes, mime_type: str, filename: str = ""):
        """
        Extract text from binary files.

        Supports:
        - PDF (.pdf) - pypdf + pdfplumber
        - Word (.docx) - python-docx
        - Excel (.xlsx) - openpyxl
        - PowerPoint (.pptx) - python-pptx
        - Archives (.zip, .tar, .gz) - file listings

        Args:
            data: Binary data
            mime_type: MIME type
            filename: Optional filename for extension detection

        Returns:
            ExtractionResult with text, method, success
        """
        return self.binary_extractor.extract_text(data, mime_type, filename)

    # ========================================
    # WARC PARSING
    # Methods 12-15 from inventory
    # ========================================

    def extract_html_from_warc(self, warc_data: bytes):
        """
        Extract HTML from WARC data.

        Args:
            warc_data: WARC file bytes

        Returns:
            HTML string or None
        """
        return self.warc_parser.extract_html(warc_data)

    def extract_binary_from_warc(self, warc_data: bytes):
        """
        Extract binary content from WARC data.

        Args:
            warc_data: WARC file bytes

        Returns:
            Tuple of (binary_data, mime_type)
        """
        return self.warc_parser.extract_binary(warc_data)

    def extract_warc_metadata(self, warc_data: bytes):
        """
        Extract metadata from WARC record.

        Args:
            warc_data: WARC file bytes

        Returns:
            Dict with metadata
        """
        return self.warc_parser.extract_metadata(warc_data)

    def html_to_markdown(self, html: str):
        """
        Convert HTML to Markdown.

        Args:
            html: HTML string

        Returns:
            Markdown string
        """
        return html_to_markdown(html)

    # ========================================
    # CONTENT ENRICHMENT - DEPRECATED/REMOVED
    # Entity extraction is now handled by PACMAN directly
    # ========================================

    def extract_outlinks(self, html: str, base_url: str):
        """
        Extract outlinks from HTML.
        Kept in LinkLater as it relates to link discovery.

        Args:
            html: HTML content
            base_url: Base URL for relative links

        Returns:
            List of outlink URLs
        """
        # Simple regex extraction since Enricher is removed
        import re
        from urllib.parse import urljoin, urlparse
        
        if not html: return []
        
        try:
            link_pattern = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
            matches = link_pattern.findall(html)
            
            domain = urlparse(base_url).netloc.lower().replace('www.', '')
            outlinks = []
            
            for match in matches:
                try:
                    full_url = urljoin(base_url, match)
                    parsed = urlparse(full_url)
                    if parsed.scheme not in ('http', 'https'): continue
                    
                    link_domain = parsed.hostname.lower().replace('www.', '') if parsed.hostname else ''
                    if link_domain == domain: continue # Internal link
                    
                    outlinks.append(full_url)
                except: continue
                
            return list(set(outlinks))[:100]
        except Exception as e:
            logger.warning(f"Failed to extract outlinks: {e}")
            return []

    # ========================================
    # KEYWORD VARIATIONS SEARCH
    # Methods 55-63 from inventory
    # ========================================

    async def search_keyword_variations(self, keywords: List[str], **kwargs):
        """
        Search with keyword variations.

        Generates variations (misspellings, phonetics, swaps) and searches
        Common Crawl + Wayback for all variations.

        Args:
            keywords: List of keywords
            **kwargs: domain, url, verify_snippets, etc.

        Returns:
            VariationSearchResult
        """
        return await self.keyword_search.search(keywords, **kwargs)

    def generate_variations(self, keyword: str):
        """
        Generate keyword variations (heuristic).

        Args:
            keyword: Base keyword

        Returns:
            List of variation strings
        """
        return self.keyword_search.generate_variations(keyword)

    async def generate_variations_llm(self, keyword: str):
        """
        Generate keyword variations using LLM.

        Args:
            keyword: Base keyword

        Returns:
            List of variation strings
        """
        return await self.keyword_search.generate_variations_llm(keyword)

    async def search_wayback(self, variation: str, domain: str = None, url: str = None):
        """
        Search Wayback for keyword variation.

        Args:
            variation: Keyword variation
            domain: Optional domain filter
            url: Optional URL filter

        Returns:
            List of matches
        """
        return await self.keyword_search.search_wayback(variation, domain, url)

    async def search_cc_index(self, variation: str, domain: str = None, url: str = None):
        """
        Search Common Crawl index for keyword variation.

        Args:
            variation: Keyword variation
            domain: Optional domain filter
            url: Optional URL filter

        Returns:
            List of matches
        """
        return await self.keyword_search.search_cc_index(variation, domain, url)

    # ========================================
    # ARCHIVE SEARCH (Historical)
    # Methods 64-75 from inventory
    # ========================================

    async def search_archives(self, domain: str, keyword: str, **kwargs):
        """
        Search archive snapshots for keyword via BACKDRILL.

        Searches Wayback + Common Crawl historical archives.

        Args:
            domain: Domain to search
            keyword: Keyword to find
            **kwargs: start_year, end_year, etc.

        Yields:
            Archive matches
        """
        if not self.backdrill:
            logger.error("Backdrill not available for archive search")
            return

        # Use Backdrill's streaming keyword search (which wraps OptimalArchiveSearcher)
        async for result in self.backdrill.search_keywords_streaming(
            url=domain,
            keywords=[keyword],
            **kwargs
        ):
            yield result

    # FastAPI endpoint for historical search (new)
    async def historical_search(
        self,
        domains: List[str],
        keywords: Optional[List[str]] = None,
        years: Optional[List[int]] = None,
        direction: str = "backwards",
        archive_id: Optional[str] = None,
        sources: List[str] = ["commoncrawl", "wayback"],
    ) -> Dict[str, Any]:
        """
        Search historical archives with domain/year/keyword filtering.

        Uses Backdrill's OptimalArchiveSearcher.
        Returns archive results + discovered domains (as shortcut for current search).
        """
        logger.info(f"LinkLater historical_search: domains={domains}, keywords={keywords}, years={years}, direction={direction}")

        if not self.backdrill:
            return {"error": "Backdrill unavailable", "archive_results": [], "discovered_domains": []}

        all_results = []
        discovered_domains = set()

        if not domains and not keywords:
            logger.warning("Historical search called without domains or keywords.")
            return {"archive_results": [], "discovered_domains": []}

        for domain in domains:
            try:
                async for result in self.backdrill.search_keywords_streaming(
                    url=domain,
                    keywords=keywords,
                    years=years,
                    direction=direction,
                ):
                    all_results.append(result)
                    # Extract domain from result if available
                    result_domain = result.get('domain') if isinstance(result, dict) else getattr(result, 'domain', None)
                    if result_domain:
                        discovered_domains.add(result_domain)
            except Exception as e:
                logger.error(f"Error in historical search for domain {domain}: {e}")

        return {
            "archive_results": all_results,
            "discovered_domains": list(discovered_domains),
            "stats": {
                "total_results": len(all_results),
                "total_discovered_domains": len(discovered_domains)
            }
        }

    # ========================================
    # BACKLINKS & OUTLINKS (CC Graph + GlobalLinks)
    # Methods 89-92, 113-115 from inventory
    # ========================================

    async def get_backlinks(
        self,
        domain: str,
        limit: int = 100,
        use_globallinks: bool = True,
        level: str = "domain"
    ) -> List[LinkRecord]:
        """
        Get backlinks (domains linking TO this domain).

        Uses CC Web Graph (157M domains, 2.1B edges) and optionally GlobalLinks.

        Args:
            domain: Target domain
            limit: Max results
            use_globallinks: Also query GlobalLinks binary
            level: "domain" or "host" (for CC Graph)

        Returns:
            List of LinkRecord objects
        """
        records = []

        # CC Graph
        cc_records = await self.cc_graph.get_backlinks(domain, limit, level=level)
        records.extend(cc_records)

        # GlobalLinks (if enabled and binary available)
        if use_globallinks:
            gl_records = await self.globallinks.get_backlinks(domain, limit)
            records.extend(gl_records)

        return records

    async def get_outlinks(
        self,
        domain: str,
        limit: int = 100,
        use_globallinks: bool = True,
        level: str = "domain"
    ) -> List[LinkRecord]:
        """
        Get outlinks (domains this domain links TO).

        Uses CC Web Graph (157M domains, 2.1B edges) and optionally GlobalLinks.

        Args:
            domain: Source domain
            limit: Max results
            use_globallinks: Also query GlobalLinks binary
            level: "domain" or "host" (for CC Graph)

        Returns:
            List of LinkRecord objects
        """
        records = []

        # CC Graph
        cc_records = await self.cc_graph.get_outlinks(domain, limit, level=level)
        records.extend(cc_records)

        # GlobalLinks (if enabled and binary available)
        if use_globallinks:
            gl_records = await self.globallinks.get_outlinks(domain, limit)
            records.extend(gl_records)

        return records

    def find_globallinks_binary(self, binary_name: str = "outlinker"):
        """
        Find GlobalLinks binary path.

        Available binaries:
        - outlinker: Query backlinks/outlinks
        - linksapi: API server for link queries
        - storelinks: Link storage/import
        - importer: Data importer

        Args:
            binary_name: Name of binary to find

        Returns:
            Path object or None
        """
        return find_globallinks_binary(binary_name)

    async def extract_domain_outlinks(
        self,
        domains: List[str],
        archive: str = "CC-MAIN-2024-10",
        country_tlds: Optional[List[str]] = None,
        url_keywords: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
        max_results: int = 1000
    ):
        """
        Extract outlinks from specific domains (advanced filtering).

        Uses GlobalLinks outlinker extract command for targeted outlink extraction
        from Common Crawl data with advanced filtering capabilities.

        Args:
            domains: List of source domains to extract from
            archive: Common Crawl archive name (e.g., CC-MAIN-2024-10)
            country_tlds: Filter outlinks to specific country TLDs (.uk, .fr, .de)
            url_keywords: Include only outlinks containing these keywords
            exclude_keywords: Exclude outlinks containing these keywords
            max_results: Maximum results per domain

        Returns:
            List of LinkRecord objects

        Example:
            # Extract outlinks from BBC to UK government sites
            results = await linklater.extract_domain_outlinks(
                domains=["bbc.com"],
                country_tlds=[".gov.uk"],
                archive="CC-MAIN-2024-10"
            )
        """
        return await self.globallinks.extract_outlinks(
            domains=domains,
            archive=archive,
            country_tlds=country_tlds,
            url_keywords=url_keywords,
            exclude_keywords=exclude_keywords,
            max_results=max_results
        )

    async def search_domain_in_links(self, target_domain: str, data_path: str = "data/links/"):
        """
        Search for all links to a target domain in local GlobalLinks data.

        Args:
            target_domain: Domain to search for
            data_path: Path to GlobalLinks link data directory

        Returns:
            List of LinkRecord objects
        """
        return await self.globallinks.search_outlinks(target_domain, data_path)

    # ========================================
    # CO-CITATION / RELATED LINKS (rl operator)
    # Majestic GetRelatedSites - domains mentioned alongside target
    # ========================================

    async def get_related_links(
        self,
        domain: str,
        mode: str = "domains",  # "domains" only for now (Majestic limitation)
        datasource: str = "fresh",  # "fresh" (90 days) or "historic" (5 years)
        max_results: int = 100,
        topic_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get co-cited/related links for a domain (rl operator).

        Finds domains that are frequently mentioned alongside the target
        in backlink contexts. If Sites A and B both link to Target AND
        to Competitor, then Competitor is "related" to Target via co-citation.

        Operator syntax:
        - ?rl :!domain.com  → Co-cited domains (fast, domains only)
        - rl? :!domain.com  → Co-cited with context (if available)

        Note: Majestic only returns domains, not the referring pages where
        co-citation occurs. Both ?rl and rl? currently return the same data.

        Args:
            domain: Target domain (e.g., "sebgroup.com")
            mode: "domains" (only mode currently supported)
            datasource: "fresh" (90-day index) or "historic" (5-year index)
            max_results: Maximum related domains to return (max 100)
            topic_filter: Filter by Majestic topic (e.g., "Society/Law")

        Returns:
            List of dicts with co-cited domain data:
            {
                'domain': str,           # Co-cited domain
                'trust_flow': int,       # Majestic Trust Flow
                'citation_flow': int,    # Majestic Citation Flow
                'common_links': int,     # Number of shared backlink sources
                'unique_contexts': int,  # Unique co-citation contexts
                'primary_topic': str,    # Primary topic category
                'source': str,           # 'majestic_related_sites'
            }

        Example:
            # Find competitors of SEB bank
            related = await linklater.get_related_links("sebgroup.com")
            # Returns: nordea.com, handelsbanken.se, swedbank.se, etc.

            # Search historical data
            related = await linklater.get_related_links(
                "example.com",
                datasource="historic"
            )
        """
        response = await get_related_sites(
            domain=domain,
            datasource=datasource,
            max_results=max_results,
            filter_topic=topic_filter
        )

        # Convert MajesticDiscoveryResponse to list of dicts
        results = []
        for r in response.results:
            results.append({
                'domain': r.domain,
                'trust_flow': r.trust_flow,
                'citation_flow': r.citation_flow,
                'common_links': r.common_links,
                'unique_contexts': r.metadata.get('unique_contexts', 0),
                'primary_topic': r.metadata.get('primary_topic', ''),
                'primary_topic_value': r.metadata.get('primary_topic_value', 0),
                'title': r.metadata.get('title', ''),
                'source': r.source,
            })

        return results

    async def get_hosted_domains(
        self,
        domain: str,
        datasource: str = "fresh",
        max_results: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find domains co-hosted on the same IP or subnet.

        Infrastructure clustering - discovers domains sharing hosting.
        Useful for finding affiliated sites, shell companies, or related entities.

        Args:
            domain: Target domain
            datasource: "fresh" or "historic"
            max_results: Maximum domains to return

        Returns:
            List of dicts with co-hosted domain data
        """
        response = await get_hosted_domains(
            domain=domain,
            datasource=datasource,
            max_domains=max_results
        )

        results = []
        for r in response.results:
            results.append({
                'domain': r.domain,
                'trust_flow': r.trust_flow,
                'citation_flow': r.citation_flow,
                'hosting_type': r.hosting_type,  # 'ip' or 'subnet'
                'ref_domains': r.metadata.get('ref_domains', 0),
                'ext_back_links': r.metadata.get('ext_back_links', 0),
                'ip': r.metadata.get('ip', ''),
                'source': r.source,
            })

        return results

    async def get_topics(
        self,
        domain: str,
        datasource: str = "fresh",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get Topical Trust Flow data (GetTopics).

        Returns the topics (categories) associated with the domain,
        ranked by Trust Flow. Useful for:
        - Understanding domain niche (e.g., Society/Law, Business/Finance)
        - Filtering backlinks by relevance (topic: operator)

        Args:
            domain: Target domain
            datasource: 'fresh' or 'historic'
            limit: Max topics to return

        Returns:
            List of dicts with topic data:
            {
                'topic': str,            # e.g., "Society/Law"
                'trust_flow': int,       # Trust Flow in this topic
                'citation_flow': int,    # Citation Flow in this topic
                'topical_trust_flow': int,
                'source': 'majestic_topics'
            }
        """
        response = await get_topics(
            domain=domain,
            datasource=datasource,
            limit=limit
        )

        results = []
        for r in response.results:
            results.append({
                'topic': r.topic,
                'trust_flow': r.trust_flow,
                'citation_flow': r.citation_flow,
                'topical_trust_flow': r.topical_trust_flow,
                'source': r.source,
            })

        return results

    # ========================================
    # WHOIS Discovery - Ownership-Linked Domains (?owl operator)
    # ========================================

    async def get_ownership_linked(
        self,
        domain: str,
        include_nameserver: bool = True,
        max_results: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get domains linked through common ownership (owl operator).

        Discovers domains that share:
        - Same registrant name or organization
        - Same registrant email
        - Same nameservers (infrastructure clustering)

        Uses WhoisXML API for reverse WHOIS lookups.

        Requires WHOIS_API_KEY environment variable.

        Args:
            domain: Target domain to cluster around
            include_nameserver: Also search by shared nameservers
            max_results: Maximum results to return

        Returns:
            List of dicts with ownership-linked domain data:
            {
                'domain': str,           # Related domain
                'match_type': str,       # registrant_name, registrant_org, registrant_email, nameserver
                'match_value': str,      # The shared value (name, email, etc.)
                'confidence': float,     # Match confidence (0.0-1.0)
                'source': str,           # 'whoisxml'
            }

        Example:
            # Find all domains owned by same entity as sebgroup.com
            related = await linklater.get_ownership_linked("sebgroup.com")
            # Returns: seb.se, seb.dk, seb.ee, sebcard.com, etc.

            # Find only by registrant (exclude nameserver clustering)
            related = await linklater.get_ownership_linked(
                "example.com",
                include_nameserver=False
            )
        """
        response = await cluster_domains_by_whois(
            domain=domain,
            include_nameserver=include_nameserver,
            limit=max_results
        )

        results = []
        for r in response.results:
            results.append({
                'domain': r.domain,
                'match_type': r.match_type,
                'match_value': r.match_value,
                'confidence': r.confidence,
                'source': 'whoisxml',
            })

        return results

    async def get_whois_data(
        self,
        domain: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get WHOIS registration data for a domain.

        Uses WhoisXML API for accurate WHOIS data.

        Args:
            domain: Target domain

        Returns:
            Dict with WHOIS data or None if lookup failed:
            {
                'domain': str,
                'registrant_name': str,
                'registrant_org': str,
                'registrant_email': str,
                'registrant_country': str,
                'registrar': str,
                'created_date': str,
                'updated_date': str,
                'expires_date': str,
                'nameservers': List[str],
                'status': List[str],
            }
        """
        record = await whois_lookup(domain)
        if not record:
            return None

        return {
            'domain': record.domain,
            'registrant_name': record.registrant_name,
            'registrant_org': record.registrant_org,
            'registrant_email': record.registrant_email,
            'registrant_country': record.registrant_country,
            'registrar': record.registrar,
            'created_date': record.created_date,
            'updated_date': record.updated_date,
            'expires_date': record.expires_date,
            'nameservers': record.nameservers,
            'status': record.status,
        }

    async def get_majestic_backlinks(
        self,
        domain: str,
        result_type: str = "pages",  # "pages" or "domains"
        mode: str = "fresh",  # "fresh" (90 days) or "historic" (5 years)
        max_results: int = 1000,
        include_anchor_text: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get backlinks from Majestic API.

        Requires MAJESTIC_API_KEY environment variable.

        Majestic provides premium backlink data with:
        - Fresh Index: Last 90 days of crawl data
        - Historic Index: 5+ years of historical data
        - Anchor text extraction
        - Trust Flow and Citation Flow metrics
        - Source page details

        Args:
            domain: Target domain
            result_type: "pages" (individual backlink pages) or "domains" (referring domains)
            mode: "fresh" (90-day index) or "historic" (5-year index)
            max_results: Maximum results to return
            include_anchor_text: Include anchor text in results

        Returns:
            List of dicts with backlink data:
            {
                'source_url': str,      # Referring page URL
                'target_url': str,      # URL on target domain
                'anchor_text': str,     # Anchor text (if available)
                'trust_flow': int,      # Trust Flow score
                'citation_flow': int,   # Citation Flow score
                'source_domain': str,   # Referring domain
                'source_tld': str,      # Referring domain TLD
            }

        Example:
            # Get fresh backlinks with anchor text
            backlinks = await linklater.get_majestic_backlinks(
                "example.com",
                mode="fresh",
                result_type="pages"
            )

            # Get historical referring domains
            domains = await linklater.get_majestic_backlinks(
                "example.com",
                mode="historic",
                result_type="domains"
            )

            # Search anchor texts for keywords
            backlinks = await linklater.get_majestic_backlinks("seb.se")
            libyan_links = [
                b for b in backlinks
                if any(kw in b.get('anchor_text', '').lower()
                       for kw in ['libya', 'libyan', 'tripoli'])
            ]
        """
        import requests
        import os
        from urllib.parse import urlparse

        api_key = os.getenv('MAJESTIC_API_KEY')
        if not api_key:
            raise ValueError("MAJESTIC_API_KEY not found in environment")

        # Use FastAPI endpoint that wraps MajesticBacklinksDiscovery
        endpoint = "http://localhost:8000/api/backlinks"

        try:
            response = requests.post(
                endpoint,
                json={
                    "target": domain,
                    "result_type": result_type,
                    "target_scope": "domain",
                    "mode": mode,
                    "max_source_urls_per_ref_domain": max_results if result_type == "pages" else 1,
                    "max_backlink_results": max_results
                },
                timeout=60
            )
            response.raise_for_status()
            data = response.json()

            # Parse response - API returns {"success": true, "backlinks": [...]}
            results = []
            items = data.get('backlinks', [])

            for item in items:
                if isinstance(item, dict):
                    # Extract domain info
                    if result_type == "domains":
                        domain_str = item.get('domain', '')
                        parsed = urlparse(f"http://{domain_str}" if not domain_str.startswith('http') else domain_str)
                        results.append({
                            'source_domain': parsed.netloc or domain_str,
                            'source_tld': '.' + (parsed.netloc or domain_str).split('.')[-1] if '.' in (parsed.netloc or domain_str) else '',
                            'trust_flow': item.get('trust_flow', 0),
                            'citation_flow': item.get('citation_flow', 0),
                            'source': item.get('source', 'majestic')
                        })
                    else:
                        # Pages - full backlink data
                        source_url = item.get('url', '') or item.get('SourceURL', '')
                        target_url = item.get('target_url', '') or item.get('TargetURL', '')
                        anchor_text = item.get('anchor_text', '') or item.get('AnchorText', '') if include_anchor_text else ''

                        # Extract domain and TLD from source URL
                        parsed = urlparse(source_url if source_url.startswith('http') else f"http://{source_url}")
                        source_domain = parsed.netloc or source_url.split('/')[0]
                        source_tld = '.' + source_domain.split('.')[-1] if '.' in source_domain else ''

                        results.append({
                            'source_url': source_url,
                            'target_url': target_url,
                            'anchor_text': anchor_text,
                            'source_domain': source_domain,
                            'source_tld': source_tld,
                            'trust_flow': item.get('trust_flow', 0) or item.get('SourceTrustFlow', 0),
                            'citation_flow': item.get('citation_flow', 0) or item.get('SourceCitationFlow', 0),
                            'first_indexed_date': item.get('FirstIndexedDate', ''),
                            'last_seen_date': item.get('LastSeenDate', ''),
                        })

            return results

        except requests.exceptions.RequestException as e:
            raise Exception(f"Majestic API error: {e}")

    # ========================================
    # FILETYPE DISCOVERY
    # Methods for finding documents (PDFs, etc.) on domains
    # ========================================

    async def discover_filetypes(
        self,
        domain: str,
        filetype_query: str = "pdf",
        keyword: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Discover files of specific types on a domain.

        Uses multiple sources: Google, Brave, Common Crawl Index.

        Args:
            domain: Target domain (e.g., "sebgroup.com")
            filetype_query: Filetype or alias ("pdf", "document", "spreadsheet")
            keyword: Optional keyword filter (e.g., "annual report")
            limit: Maximum results

        Returns:
            Dict with discovered files:
            {
                "domain": "sebgroup.com",
                "filetypes_searched": ["pdf"],
                "query": "annual report",
                "total_found": 45,
                "results": [
                    {
                        "url": "https://...",
                        "title": "Annual Report 2023",
                        "filetype": "pdf",
                        "source": "google"
                    },
                    ...
                ],
                "sources_used": ["google", "brave", "commoncrawl_index"],
                "elapsed_ms": 1234
            }
        """
        from .discovery.filetype_discovery import discover_filetypes as _discover

        result = await _discover(
            domain=domain,
            filetype_query=filetype_query,
            keyword=keyword,
            limit=limit,
            use_fallbacks=True
        )

        return {
            "domain": result.domain,
            "filetypes_searched": result.filetypes_searched,
            "query": result.query,
            "total_found": result.total_found,
            "results": [
                {
                    "url": r.url,
                    "domain": r.domain,
                    "filetype": r.filetype,
                    "title": r.title,
                    "snippet": r.snippet,
                    "source": r.source,
                    "metadata": r.metadata
                }
                for r in result.results
            ],
            "sources_used": result.sources_used,
            "elapsed_ms": result.elapsed_ms,
            "logs": result.logs  # Cascade discovery logs for frontend display
        }

    async def batch_discover_filetypes(
        self,
        domains: List[str],
        filetype_query: str = "pdf",
        keyword: Optional[str] = None,
        limit_per_domain: int = 50
    ) -> Dict[str, Dict[str, Any]]:
        """
        Batch filetype discovery across multiple domains.

        Args:
            domains: List of domains to search
            filetype_query: Filetype or alias ("pdf", "document", "spreadsheet")
            keyword: Optional keyword filter
            limit_per_domain: Max results per domain

        Returns:
            Dict mapping domain -> discovery results

        Example:
            results = await linklater.batch_discover_filetypes(
                domains=["sebgroup.com", "nordea.com", "handelsbanken.se"],
                filetype_query="pdf",
                keyword="annual report"
            )
        """
        from .discovery.filetype_discovery import batch_discover_filetypes as _batch_discover

        raw_results = await _batch_discover(
            domains=domains,
            filetype_query=filetype_query,
            keyword=keyword,
            limit_per_domain=limit_per_domain
        )

        # Convert to dict format
        results = {}
        all_logs = []  # Aggregate logs from all domains
        for domain, response in raw_results.items():
            results[domain] = {
                "domain": response.domain,
                "filetypes_searched": response.filetypes_searched,
                "query": response.query,
                "total_found": response.total_found,
                "files": [  # Renamed to 'files' for clarity in batch responses
                    {
                        "url": r.url,
                        "domain": r.domain,
                        "filetype": r.filetype,
                        "title": r.title,
                        "snippet": r.snippet,
                        "source": r.source,
                        "metadata": r.metadata
                    }
                    for r in response.results
                ],
                "sources_used": response.sources_used,
                "elapsed_ms": response.elapsed_ms,
                "logs": response.logs
            }
            # Prefix logs with domain for batch tracking
            for log in response.logs:
                all_logs.append({**log, "domain": domain})

        # Also return aggregated logs at top level for easier frontend display
        results["_logs"] = all_logs

        return results

    # ========================================
    # MACRO OPERATIONS (alldom:, crel:, etc.)
    # ========================================

    async def full_domain_analysis(
        self,
        domain: str,
        include_archives: bool = True,
        include_entities: bool = True,
        limit_per_operation: int = 100
    ) -> Dict[str, Any]:
        """
        Complete LINKLATER analysis on a domain - the alldom: operator.

        Runs ALL discovery operations in parallel:
        - Backlinks (bl?, ?bl)
        - Outlinks (ol?, ?ol)
        - Related domains (?rl)
        - IP co-hosted domains (?ipl)
        - WHOIS ownership clusters (?owl)
        - WHOIS data (whois:)
        - Tech stack (tech:)
        - GA tracking clusters (ga?)
        - Historical archives (<-!)
        - Entity extraction (ent?)

        Args:
            domain: Target domain to analyze
            include_archives: Include historical archive search
            include_entities: Include entity extraction from scraped content
            limit_per_operation: Max results per operation type

        Returns:
            Comprehensive domain analysis with all discovered data
        """
        import asyncio
        from datetime import datetime

        results = {
            "domain": domain,
            "timestamp": datetime.utcnow().isoformat(),
            "operations": {},
            "summary": {
                "total_domains_discovered": 0,
                "total_links_found": 0,
                "total_entities_extracted": 0,
                "operations_completed": 0,
                "operations_failed": 0
            }
        }

        # Define all operations to run
        operations = {
            "backlinks": lambda: self.get_backlinks(domain, limit=limit_per_operation, level="domain"),
            "outlinks": lambda: self.get_outlinks(domain, limit=limit_per_operation, level="domain"),
            "related_domains": lambda: self.get_related_links(domain, limit=limit_per_operation),
            "ip_cohosted": lambda: self.get_hosted_domains(domain, limit=limit_per_operation),
            "whois_linked": lambda: self.get_ownership_linked(domain, limit=limit_per_operation),
            "whois_data": lambda: self.get_whois_data(domain),
            "topics": lambda: self.get_topics(domain, limit=limit_per_operation),
        }

        if include_archives:
            operations["archives"] = lambda: self.historical_search(domain=domain, limit=limit_per_operation)

        # Run all operations in parallel
        tasks = {name: asyncio.create_task(op()) for name, op in operations.items()}

        for name, task in tasks.items():
            try:
                result = await task
                results["operations"][name] = {
                    "status": "success",
                    "data": result,
                    "count": len(result) if isinstance(result, (list, dict)) else 1
                }
                results["summary"]["operations_completed"] += 1

                # Update summary counts
                if isinstance(result, list):
                    if name in ("related_domains", "ip_cohosted", "whois_linked"):
                        results["summary"]["total_domains_discovered"] += len(result)
                    elif name in ("backlinks", "outlinks"):
                        results["summary"]["total_links_found"] += len(result)
            except Exception as e:
                results["operations"][name] = {
                    "status": "error",
                    "error": str(e),
                    "count": 0
                }
                results["summary"]["operations_failed"] += 1

        # Entity extraction if requested
        if include_entities:
            try:
                # Scrape main domain page for entity extraction
                scraped = await self.scrape_url(f"https://{domain}")
                if scraped and scraped.get("markdown"):
                    entities = await self.extract_entities(
                        text=scraped["markdown"],
                        url=f"https://{domain}",
                        backend="auto"
                    )
                    results["operations"]["entities"] = {
                        "status": "success",
                        "data": entities,
                        "count": sum(len(v) for v in entities.values() if isinstance(v, list))
                    }
                    results["summary"]["total_entities_extracted"] = results["operations"]["entities"]["count"]
                    results["summary"]["operations_completed"] += 1
            except Exception as e:
                results["operations"]["entities"] = {
                    "status": "error",
                    "error": str(e),
                    "count": 0
                }
                results["summary"]["operations_failed"] += 1

        return results

    async def find_related_companies(
        self,
        company_name: str,
        include_officers: bool = True,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Find companies related to a target company - the crel: operator.

        Uses multiple discovery methods:
        - WHOIS ownership clustering on company domain
        - IP co-hosting analysis
        - GA tracking clusters
        - Shared officer lookup

        Args:
            company_name: Target company name
            include_officers: Also find companies via shared officers
            limit: Max results per discovery method

        Returns:
            Related companies with relationship type
        """
        # This would integrate with Corporella and IO Matrix
        # For now, return structure for future implementation
        return {
            "target_company": company_name,
            "related_companies": [],
            "discovery_methods": ["whois_cluster", "ip_cohost", "ga_cluster", "shared_officers"],
            "status": "requires_corporella_integration"
        }

    # ========================================
    # CONVENIENCE / STANDALONE FUNCTIONS
    # ========================================

    @staticmethod
    async def quick_scrape(url: str):
        """Quick scrape without instance (standalone)."""
        return await scrape_url(url)

    @staticmethod
    async def quick_scrape_batch(urls: List[str]):
        """Quick batch scrape without instance (standalone)."""
        return await scrape_urls(urls)

    @staticmethod
    def quick_extract_entities(text: str):
        """Quick entity extraction without instance (standalone, regex-based)."""
        return extract_all_entities(text)

    @staticmethod
    async def quick_extract_entities_ai(text: str, url: str = "", backend: str = "auto"):
        """
        Quick AI-powered entity extraction without instance.

        Uses Gemini/GPT/GLiNER for better accuracy than regex.

        Args:
            text: Text/HTML to analyze
            url: Source URL
            backend: "auto", "gemini", "gpt", "gliner", or "regex"

        Returns:
            Dict with entities: {"persons": [...], "companies": [...], ...}
        """
        if UNIFIED_EXTRACTION_AVAILABLE and unified_extract_entities:
            return await unified_extract_entities(text, url, backend=backend)
        else:
            return extract_all_entities(text)

    @staticmethod
    def quick_extract_companies(text: str):
        """Quick company extraction without instance (standalone, regex-based)."""
        return extract_companies(text)


# Lazy singleton for async-safe import
_linklater_instance = None

def get_linklater() -> LinkLater:
    """Get or create the singleton LinkLater instance.

    Use this instead of direct import to avoid event loop issues.
    Must be called from within an async context.
    """
    global _linklater_instance
    if _linklater_instance is None:
        _linklater_instance = LinkLater()
    return _linklater_instance

# For backwards compatibility (but may fail outside event loop)
# Use get_linklater() instead for async-safe access
linklater = None  # Set to None, use get_linklater()


# Standalone functions for backwards compatibility
async def get_backlinks(domain: str, limit: int = 100):
    """Standalone: Get backlinks."""
    return await get_linklater().get_backlinks(domain, limit)


async def get_outlinks(domain: str, limit: int = 100):
    """Standalone: Get outlinks."""
    return await get_linklater().get_outlinks(domain, limit)


async def get_related_links(domain: str, limit: int = 100, datasource: str = "fresh"):
    """Standalone: Get co-cited/related links (rl operator)."""
    return await get_linklater().get_related_links(domain, max_results=limit, datasource=datasource)


async def get_ownership_linked(domain: str, limit: int = 100, include_nameserver: bool = True):
    """Standalone: Get ownership-linked domains (owl operator)."""
    return await get_linklater().get_ownership_linked(domain, include_nameserver=include_nameserver, max_results=limit)


async def get_whois_data(domain: str):
    """Standalone: Get WHOIS registration data."""
    return await get_linklater().get_whois_data(domain)


async def get_topics(domain: str, limit: int = 100, datasource: str = "fresh"):
    """Standalone: Get Topical Trust Flow."""
    return await get_linklater().get_topics(domain, datasource=datasource, limit=limit)
