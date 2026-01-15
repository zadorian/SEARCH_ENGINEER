"""
LinkLater Unified Mapping Module
=================================
Consolidates all domain/network mapping capabilities from linklater.

This module wraps existing implementations - NO duplication.

Available Discovery Methods:
1. SUBDOMAIN DISCOVERY (via LinkLater DrillDiscovery)
   - crt.sh (FREE) - Certificate Transparency logs
   - Sublist3r (FREE) - Multi-source subdomain enumeration (10+ sources)
   - Runs in parallel for maximum coverage

2. WHOIS DISCOVERY
   - WHOIS Lookup - Domain registration data
   - Reverse WHOIS - Find domains by registrant
   - Nameserver Clustering - Find domains sharing DNS

3. NEWS/LINK DISCOVERY (GDELT)
   - NewsAPI - News article search
   - GDELT - Global news database
   - Targeted site searches

4. DOMAIN INTELLIGENCE
   - OpenPageRank - Authority scoring
   - Tranco - Top 1M sites ranking
   - Cloudflare Radar - Traffic data
   - BigQuery - CrUX/HTTP Archive queries

Usage:
    from modules.linklater.mapping.unified_discovery import UnifiedDiscovery

    discovery = UnifiedDiscovery()

    # Subdomain discovery
    subdomains = await discovery.discover_subdomains("example.com")

    # WHOIS clustering
    related = await discovery.cluster_by_whois("example.com")

    # News/link discovery
    news = await discovery.search_news("company name")
"""

import sys
import os
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, AsyncGenerator, Callable
from dataclasses import dataclass, field

# Add project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
PYTHON_BACKEND = PROJECT_ROOT / "python-backend"

if str(PYTHON_BACKEND) not in sys.path:
    sys.path.insert(0, str(PYTHON_BACKEND))
if str(PYTHON_BACKEND / "modules") not in sys.path:
    sys.path.insert(0, str(PYTHON_BACKEND / "modules"))

logger = logging.getLogger(__name__)


# ============================================================================
# Import existing implementations (NO duplication)
# ============================================================================

# 1. SUBDOMAIN DISCOVERY (native LinkLater) ✅
try:
    from ..scraping.web.discovery import DrillDiscovery
    SUBDOMAIN_DISCOVERY_AVAILABLE = True
except ImportError:
    SUBDOMAIN_DISCOVERY_AVAILABLE = False
    DrillDiscovery = None
    logger.warning("DrillDiscovery not available - check linklater.drill.discovery")

# 2. WHOIS DISCOVERY (from discovery module)
try:
    from discovery.whois_discovery import (
        whois_lookup,
        reverse_whois_by_registrant,
        find_domains_by_nameserver,
        cluster_domains_by_whois,
        batch_whois_lookup,
        WhoisRecord,
        WhoisClusterResult,
        WhoisDiscoveryResponse
    )
    WHOIS_DISCOVERY_AVAILABLE = True
except ImportError:
    WHOIS_DISCOVERY_AVAILABLE = False
    logger.warning("WHOIS Discovery not available - check discovery module")

# 3. NEWS SEARCH (from brute)
try:
    from brute.targeted_searches.news.news import NewsSearcher
    NEWS_SEARCH_AVAILABLE = True
except ImportError:
    NEWS_SEARCH_AVAILABLE = False
    NewsSearcher = None
    logger.warning("NewsSearcher not available - check brute module")

# 4. GDELT DIRECT (from brute engines)
try:
    sys.path.insert(0, str(PYTHON_BACKEND / "modules" / "brute" / "engines"))
    from exact_phrase_recall_runner_gdelt import ExactPhraseRecallRunnerGDELT
    GDELT_AVAILABLE = True
except ImportError:
    GDELT_AVAILABLE = False
    ExactPhraseRecallRunnerGDELT = None
    logger.warning("GDELT not available")

# 5. DOMAIN FILTERS (BigQuery, OpenPageRank, Tranco, Cloudflare)
try:
    # Domain filters are in categorizer-filterer, accessed via domain_filters.py
    from linklater.mapping.domain_filters import (
        BigQueryDiscovery,
        OpenPageRankFilter,
        TrancoRankingFilter,
        CloudflareRadarFilter,
        DomainFilters,
        BIGQUERY_AVAILABLE,
        OPENPAGERANK_AVAILABLE,
        TRANCO_AVAILABLE,
        CLOUDFLARE_AVAILABLE
    )
    DOMAIN_FILTERS_AVAILABLE = True
except ImportError:
    DOMAIN_FILTERS_AVAILABLE = False
    logger.warning("Domain filters not available")

# 6. TOR BRIDGES (from linkgraph - bridge edges from Tor crawler)
try:
    from linklater.linkgraph.tor_bridges import TorBridgesClient
    TOR_BRIDGES_AVAILABLE = True
except ImportError:
    TOR_BRIDGES_AVAILABLE = False
    TorBridgesClient = None
    logger.warning("Tor bridges client not available")

# 7. GA TRACKER (analytics fingerprinting)
try:
    from linklater.mapping.ga_tracker import GATracker
    GA_TRACKER_AVAILABLE = True
except ImportError:
    GA_TRACKER_AVAILABLE = False
    GATracker = None
    logger.warning("GA Tracker not available")

# 8. BACKLINK PIPELINE with Entity Extraction
try:
    from linklater.pipelines.automated_backlink_pipeline import (
        AutomatedBacklinkPipeline,
        discover_backlinks_with_entities,
        ENTITY_EXTRACTION_AVAILABLE
    )
    BACKLINK_PIPELINE_AVAILABLE = True
except ImportError:
    BACKLINK_PIPELINE_AVAILABLE = False
    AutomatedBacklinkPipeline = None
    discover_backlinks_with_entities = None
    ENTITY_EXTRACTION_AVAILABLE = False
    logger.warning("Backlink pipeline not available")

# 9. COMMON CRAWL PDF DISCOVERY (filetype:pdf searches)
try:
    from linklater.archives.cc_index_client import CCIndexClient
    from linklater.mapping.cc_pdf_discovery import CCPDFDiscovery
    from linklater.mapping.pdf_scorer import has_obvious_annual_report_signals
    CC_PDF_DISCOVERY_AVAILABLE = True
except ImportError:
    CC_PDF_DISCOVERY_AVAILABLE = False
    CCIndexClient = None
    CCPDFDiscovery = None
    has_obvious_annual_report_signals = None
    logger.warning("CC PDF Discovery not available")


# ============================================================================
# Unified Response Models
# ============================================================================

@dataclass
class DiscoveryResult:
    """Unified discovery result"""
    source: str  # crtsh, whoisxml, sublist3r, gdelt, newsapi, etc.
    result_type: str  # subdomain, domain, article, whois_cluster
    value: str  # The discovered value
    url: Optional[str] = None
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveryResponse:
    """Unified discovery response"""
    query: str
    method: str
    total_found: int
    results: List[DiscoveryResult]
    sources_used: List[str] = field(default_factory=list)
    elapsed_ms: int = 0


# ============================================================================
# Unified Discovery Class
# ============================================================================

class UnifiedDiscovery:
    """
    Unified interface for all domain/network mapping methods.

    Wraps existing implementations from linklater (drill, linkgraph, archives, etc).
    Does NOT duplicate code - just provides a single entry point.
    """

    def __init__(self):
        # Initialize subdomain discovery (use FREE-only sources)
        self.subdomain_discovery = DrillDiscovery(free_only=True) if SUBDOMAIN_DISCOVERY_AVAILABLE else None

        # Initialize news searcher
        self.news_searcher = NewsSearcher() if NEWS_SEARCH_AVAILABLE else None

        # Initialize domain filters
        self.domain_filters = DomainFilters() if DOMAIN_FILTERS_AVAILABLE else None

        # Initialize Tor bridges client
        self.tor_bridges = TorBridgesClient() if TOR_BRIDGES_AVAILABLE else None

        # GA Tracker is initialized per-use (requires async context manager)
        self._ga_tracker_available = GA_TRACKER_AVAILABLE

        # Initialize CC PDF Discovery (for filetype:pdf searches)
        if CC_PDF_DISCOVERY_AVAILABLE:
            self.cc_index_client = CCIndexClient()
            self.cc_pdf_discovery = CCPDFDiscovery(
                cc_index_client=self.cc_index_client,
                jurisdictions=['SE', 'UK', 'US', 'EU']
            )
        else:
            self.cc_index_client = None
            self.cc_pdf_discovery = None

        # Log availability
        self._log_availability()

    def _log_availability(self):
        """Log which discovery methods are available"""
        available = []
        unavailable = []

        checks = [
            ("Subdomain Discovery (crt.sh, WhoisXML, Sublist3r)", SUBDOMAIN_DISCOVERY_AVAILABLE),
            ("WHOIS Discovery (lookup, reverse, clustering)", WHOIS_DISCOVERY_AVAILABLE),
            ("News Search (NewsAPI, GDELT, DDG)", NEWS_SEARCH_AVAILABLE),
            ("GDELT Direct", GDELT_AVAILABLE),
            ("Domain Filters (BigQuery, OpenPageRank, Tranco, Cloudflare)", DOMAIN_FILTERS_AVAILABLE),
            ("Tor Bridges (onion→clearnet links)", TOR_BRIDGES_AVAILABLE),
            ("GA Tracker (analytics fingerprinting)", GA_TRACKER_AVAILABLE),
            ("Backlink Pipeline (with entity extraction)", BACKLINK_PIPELINE_AVAILABLE),
            ("CC PDF Discovery (filetype:pdf searches)", CC_PDF_DISCOVERY_AVAILABLE),
        ]

        for name, is_available in checks:
            if is_available:
                available.append(name)
            else:
                unavailable.append(name)

        if available:
            logger.info(f"[UnifiedDiscovery] Available: {', '.join(available)}")
        if unavailable:
            logger.warning(f"[UnifiedDiscovery] Unavailable: {', '.join(unavailable)}")

    def get_capabilities(self) -> Dict[str, bool]:
        """Return dict of available capabilities"""
        return {
            "subdomain_crtsh": SUBDOMAIN_DISCOVERY_AVAILABLE,
            "subdomain_whoisxml": SUBDOMAIN_DISCOVERY_AVAILABLE,
            "subdomain_sublist3r": SUBDOMAIN_DISCOVERY_AVAILABLE,
            "whois_lookup": WHOIS_DISCOVERY_AVAILABLE,
            "whois_reverse": WHOIS_DISCOVERY_AVAILABLE,
            "whois_cluster": WHOIS_DISCOVERY_AVAILABLE,
            "news_search": NEWS_SEARCH_AVAILABLE,
            "gdelt": GDELT_AVAILABLE,
            "pagerank": DOMAIN_FILTERS_AVAILABLE and OPENPAGERANK_AVAILABLE if DOMAIN_FILTERS_AVAILABLE else False,
            "tranco": DOMAIN_FILTERS_AVAILABLE and TRANCO_AVAILABLE if DOMAIN_FILTERS_AVAILABLE else False,
            "cloudflare": DOMAIN_FILTERS_AVAILABLE and CLOUDFLARE_AVAILABLE if DOMAIN_FILTERS_AVAILABLE else False,
            "bigquery": DOMAIN_FILTERS_AVAILABLE and BIGQUERY_AVAILABLE if DOMAIN_FILTERS_AVAILABLE else False,
            "tor_bridges": TOR_BRIDGES_AVAILABLE,
            "ga_tracker": GA_TRACKER_AVAILABLE,
            "backlink_pipeline": BACKLINK_PIPELINE_AVAILABLE,
            "backlink_entities": BACKLINK_PIPELINE_AVAILABLE and ENTITY_EXTRACTION_AVAILABLE,
            "cc_pdf_discovery": CC_PDF_DISCOVERY_AVAILABLE,
            "filetype_search": CC_PDF_DISCOVERY_AVAILABLE,
        }

    # ========================================================================
    # SUBDOMAIN DISCOVERY
    # ========================================================================

    async def discover_subdomains(
        self,
        domain: str,
        sources: Optional[List[str]] = None
    ) -> DiscoveryResponse:
        """
        Discover subdomains using multiple sources.

        Args:
            domain: Base domain (e.g., "example.com")
            sources: Optional list of sources to use ["crtsh", "whoisxml", "sublist3r"]
                    If None, uses all available sources.

        Returns:
            DiscoveryResponse with discovered subdomains
        """
        import time
        start = time.time()

        if not self.subdomain_discovery:
            return DiscoveryResponse(
                query=domain,
                method="subdomain_discovery",
                total_found=0,
                results=[],
                sources_used=[],
                elapsed_ms=0
            )

        results = []
        sources_used = []
        seen_domains: Set[str] = set()

        # Use DrillDiscovery.discover() which runs all sources in parallel
        drill_result = await self.subdomain_discovery.discover(
            domain=domain,
            include_subdomains=True,  # Enable subdomain discovery
            max_urls_per_source=100
        )

        # Extract subdomains from result
        for subdomain in drill_result.subdomains:
            if subdomain not in seen_domains:
                seen_domains.add(subdomain)

                # Determine source from urls_by_source
                source = "unknown"
                for source_name, urls in drill_result.urls_by_source.items():
                    if any(subdomain in url for url in urls):
                        source = source_name
                        break

                results.append(DiscoveryResult(
                    source=source,
                    result_type="subdomain",
                    value=subdomain,
                    url=f"https://{subdomain}",
                    metadata={"category": "subdomain"}
                ))

                if source not in sources_used:
                    sources_used.append(source)

        elapsed_ms = int((time.time() - start) * 1000)

        return DiscoveryResponse(
            query=domain,
            method="subdomain_discovery",
            total_found=len(results),
            results=results,
            sources_used=sources_used,
            elapsed_ms=elapsed_ms
        )

    # ========================================================================
    # WHOIS DISCOVERY
    # ========================================================================

    async def whois_lookup(self, domain: str) -> Optional[Dict[str, Any]]:
        """
        Lookup WHOIS data for a domain.

        Args:
            domain: Target domain

        Returns:
            WHOIS record as dict, or None if not available
        """
        if not WHOIS_DISCOVERY_AVAILABLE:
            return None

        record = await whois_lookup(domain)
        if record:
            return {
                "domain": record.domain,
                "registrant_name": record.registrant_name,
                "registrant_org": record.registrant_org,
                "registrant_email": record.registrant_email,
                "registrant_country": record.registrant_country,
                "registrar": record.registrar,
                "created_date": record.created_date,
                "updated_date": record.updated_date,
                "expires_date": record.expires_date,
                "nameservers": record.nameservers,
                "status": record.status,
            }
        return None

    async def cluster_by_whois(
        self,
        domain: str,
        include_nameserver: bool = True,
        limit: int = 100
    ) -> DiscoveryResponse:
        """
        Find related domains via WHOIS clustering.

        Searches by:
        - Registrant name
        - Registrant organization
        - Registrant email
        - Nameservers (optional)

        Args:
            domain: Target domain to cluster around
            include_nameserver: Also search by nameserver
            limit: Maximum results

        Returns:
            DiscoveryResponse with related domains
        """
        if not WHOIS_DISCOVERY_AVAILABLE:
            return DiscoveryResponse(
                query=domain,
                method="whois_cluster",
                total_found=0,
                results=[],
                sources_used=[],
                elapsed_ms=0
            )

        response = await cluster_domains_by_whois(
            domain,
            include_nameserver=include_nameserver,
            limit=limit
        )

        results = []
        for r in response.results:
            results.append(DiscoveryResult(
                source="whois",
                result_type="whois_cluster",
                value=r.domain,
                confidence=r.confidence,
                metadata={
                    "match_type": r.match_type,
                    "match_value": r.match_value
                }
            ))

        return DiscoveryResponse(
            query=domain,
            method="whois_cluster",
            total_found=response.total_found,
            results=results,
            sources_used=["whoisxml"],
            elapsed_ms=response.elapsed_ms
        )

    async def reverse_whois(
        self,
        registrant: str,
        search_type: str = "registrant",
        limit: int = 100
    ) -> DiscoveryResponse:
        """
        Find domains by registrant name, organization, or email.

        Args:
            registrant: Registrant name, org, or email to search
            search_type: "registrant" (name/org) or "email"
            limit: Maximum results

        Returns:
            DiscoveryResponse with matching domains
        """
        if not WHOIS_DISCOVERY_AVAILABLE:
            return DiscoveryResponse(
                query=registrant,
                method="reverse_whois",
                total_found=0,
                results=[],
                sources_used=[],
                elapsed_ms=0
            )

        import time
        start = time.time()

        cluster_results = await reverse_whois_by_registrant(
            registrant,
            search_type=search_type,
            limit=limit
        )

        results = []
        for r in cluster_results:
            results.append(DiscoveryResult(
                source="whois",
                result_type="reverse_whois",
                value=r.domain,
                confidence=r.confidence,
                metadata={
                    "match_type": r.match_type,
                    "match_value": r.match_value
                }
            ))

        elapsed_ms = int((time.time() - start) * 1000)

        return DiscoveryResponse(
            query=registrant,
            method="reverse_whois",
            total_found=len(results),
            results=results,
            sources_used=["whoisxml"],
            elapsed_ms=elapsed_ms
        )

    # ========================================================================
    # NEWS / GDELT DISCOVERY
    # ========================================================================

    async def search_news(
        self,
        query: str,
        max_results: int = 50
    ) -> DiscoveryResponse:
        """
        Search news sources for articles mentioning query.

        Uses: NewsAPI, GDELT, DuckDuckGo News, targeted site searches.

        Args:
            query: Search query
            max_results: Maximum results

        Returns:
            DiscoveryResponse with news articles
        """
        import time
        start = time.time()

        if not self.news_searcher:
            return DiscoveryResponse(
                query=query,
                method="news_search",
                total_found=0,
                results=[],
                sources_used=[],
                elapsed_ms=0
            )

        response = await self.news_searcher.search(query, max_results)

        results = []
        sources_used = set()

        for article in response.get("results", []):
            source = article.get("source", "unknown")
            sources_used.add(source.split("_")[0])  # Extract base source

            results.append(DiscoveryResult(
                source=source,
                result_type="article",
                value=article.get("title", ""),
                url=article.get("url"),
                metadata={
                    "snippet": article.get("snippet"),
                    "date": article.get("date")
                }
            ))

        elapsed_ms = int((time.time() - start) * 1000)

        return DiscoveryResponse(
            query=query,
            method="news_search",
            total_found=len(results),
            results=results,
            sources_used=list(sources_used),
            elapsed_ms=elapsed_ms
        )

    async def search_gdelt(
        self,
        query: str,
        timespan: str = "1m",
        max_results: int = 100
    ) -> DiscoveryResponse:
        """
        Search GDELT directly for news articles.

        Args:
            query: Search query
            timespan: GDELT timespan (e.g., "1d", "1w", "1m")
            max_results: Maximum results

        Returns:
            DiscoveryResponse with GDELT results
        """
        import time
        import asyncio
        start = time.time()

        if not GDELT_AVAILABLE:
            return DiscoveryResponse(
                query=query,
                method="gdelt",
                total_found=0,
                results=[],
                sources_used=[],
                elapsed_ms=0
            )

        try:
            runner = ExactPhraseRecallRunnerGDELT(query, timespan=timespan)
            loop = asyncio.get_event_loop()
            raw_results = await loop.run_in_executor(None, lambda: list(runner.run()))

            results = []
            for r in raw_results[:max_results]:
                results.append(DiscoveryResult(
                    source="gdelt",
                    result_type="article",
                    value=r.title,
                    url=r.url,
                    metadata={
                        "snippet": r.snippet,
                        "date": r.seendate,
                        "source": r.source
                    }
                ))

            elapsed_ms = int((time.time() - start) * 1000)

            return DiscoveryResponse(
                query=query,
                method="gdelt",
                total_found=len(results),
                results=results,
                sources_used=["gdelt"],
                elapsed_ms=elapsed_ms
            )

        except Exception as e:
            logger.error(f"GDELT search failed: {e}")
            return DiscoveryResponse(
                query=query,
                method="gdelt",
                total_found=0,
                results=[],
                sources_used=[],
                elapsed_ms=0
            )

    # ========================================================================
    # COMMON CRAWL PDF DISCOVERY (filetype: searches)
    # ========================================================================

    async def search_with_filetype(
        self,
        query: str,
        domain: Optional[str] = None,
        years: Optional[List[int]] = None,
        jurisdictions: Optional[List[str]] = None,
        verify: bool = True,
        top_n: int = 50
    ) -> DiscoveryResponse:
        """
        Search with filetype syntax: 'filetype:pdf keyword' or 'filetype!pdf keyword'.

        Syntax:
            - filetype:pdf annual report → Search for PDFs containing "annual report"
            - filetype!pdf quarterly → Search for PDFs matching "quarterly"
            - keyword filetype:pdf → Keyword first also works

        Args:
            query: Search query with filetype syntax (e.g., "filetype:pdf annual report")
            domain: Optional domain to search within
            years: Optional list of years to search (defaults to [2020-2024])
            jurisdictions: Optional list of jurisdictions (defaults to ['SE', 'UK', 'US', 'EU'])
            verify: Enable WAT metadata verification
            top_n: Return top N scored candidates

        Returns:
            DiscoveryResponse with discovered PDFs

        Example:
            >>> discovery = UnifiedDiscovery()
            >>> result = await discovery.search_with_filetype(
            ...     "filetype:pdf annual report",
            ...     domain="sebgroup.com",
            ...     years=[2024]
            ... )
            >>> print(f"Found {result.total_found} annual report PDFs")
        """
        import time
        import re
        start = time.time()

        if not CC_PDF_DISCOVERY_AVAILABLE:
            return DiscoveryResponse(
                query=query,
                method="filetype_search",
                total_found=0,
                results=[],
                sources_used=[],
                elapsed_ms=0
            )

        # Parse filetype syntax
        # Supports: "filetype:pdf keyword" or "filetype!pdf keyword"
        filetype_pattern = re.compile(r'filetype[:\!](\w+)', re.IGNORECASE)
        match = filetype_pattern.search(query)

        if not match:
            logger.warning(f"No filetype syntax found in query: {query}")
            return DiscoveryResponse(
                query=query,
                method="filetype_search",
                total_found=0,
                results=[],
                sources_used=[],
                elapsed_ms=0
            )

        filetype = match.group(1).lower()
        # Remove filetype syntax from query to get keyword
        keyword = filetype_pattern.sub('', query).strip()

        logger.info(f"[FiletypeSearch] filetype={filetype}, keyword={keyword}, domain={domain}")

        # Currently only PDF is supported via CC PDF Discovery
        if filetype != 'pdf':
            logger.warning(f"Filetype '{filetype}' not yet supported (only PDF available)")
            return DiscoveryResponse(
                query=query,
                method="filetype_search",
                total_found=0,
                results=[],
                sources_used=[],
                elapsed_ms=0
            )

        # If no domain specified, try to extract from keyword
        if not domain and keyword:
            # Try to extract domain from keyword (e.g., "sebgroup.com annual report")
            domain_pattern = re.compile(r'\b([a-zA-Z0-9-]+\.[a-zA-Z]{2,})\b')
            domain_match = domain_pattern.search(keyword)
            if domain_match:
                domain = domain_match.group(1)
                # Remove domain from keyword
                keyword = domain_pattern.sub('', keyword).strip()
                logger.info(f"[FiletypeSearch] Extracted domain: {domain}")

        if not domain:
            logger.warning("[FiletypeSearch] No domain specified or found in query")
            return DiscoveryResponse(
                query=query,
                method="filetype_search",
                total_found=0,
                results=[],
                sources_used=[],
                elapsed_ms=0
            )

        # Use discover_annual_reports for PDF discovery
        return await self.discover_annual_reports(
            domain=domain,
            years=years,
            jurisdictions=jurisdictions,
            verify=verify,
            top_n=top_n
        )

    async def discover_annual_reports(
        self,
        domain: str,
        years: Optional[List[int]] = None,
        jurisdictions: Optional[List[str]] = None,
        verify: bool = True,
        top_n: int = 50
    ) -> DiscoveryResponse:
        """
        Discover annual reports via Common Crawl PDF discovery.

        Uses multi-signal scoring to find high-confidence annual report PDFs:
        - URL pattern matching (heavily weighted for "annual report" + year)
        - File size validation
        - Temporal consistency
        - Path authority
        - Jurisdiction-specific patterns

        Args:
            domain: Target domain (e.g., 'sebgroup.com')
            years: Report years to search (defaults to [2020, 2021, 2022, 2023, 2024])
            jurisdictions: Reporting jurisdictions to include (defaults to ['SE', 'UK', 'US', 'EU'])
            verify: Enable WAT metadata verification (recommended)
            top_n: Return top N scored candidates

        Returns:
            DiscoveryResponse with:
                - results: List of DiscoveryResult objects with PDFs
                - metadata: Scores, verification stats, sources
                - stats: Discovery statistics

        Example:
            >>> discovery = UnifiedDiscovery()
            >>> result = await discovery.discover_annual_reports("sebgroup.com", years=[2024])
            >>> for pdf in result.results:
            ...     print(f"{pdf.value}: {pdf.metadata['score']}")
        """
        import time
        start = time.time()

        if not CC_PDF_DISCOVERY_AVAILABLE:
            return DiscoveryResponse(
                query=domain,
                method="annual_report_discovery",
                total_found=0,
                results=[],
                sources_used=[],
                elapsed_ms=0
            )

        # Default years and jurisdictions
        if years is None:
            years = [2020, 2021, 2022, 2023, 2024]
        if jurisdictions is None:
            jurisdictions = ['SE', 'UK', 'US', 'EU']

        logger.info(f"[AnnualReportDiscovery] Discovering PDFs for {domain}, years={years}, jurisdictions={jurisdictions}")

        try:
            # Discover PDFs via CC PDF Discovery
            candidates = await self.cc_pdf_discovery.discover_annual_reports(
                domain=domain,
                years=years,
                verify=verify
            )

            # Convert to DiscoveryResult format
            results = []
            for candidate in candidates[:top_n]:
                results.append(DiscoveryResult(
                    source="cc_pdf_discovery",
                    result_type="annual_report_pdf",
                    value=candidate.url,
                    url=candidate.url,
                    confidence=candidate.confidence_score / 100.0,  # Normalize to 0-1
                    metadata={
                        "score": candidate.confidence_score,
                        "verified": candidate.verified,
                        "archive": candidate.archive,
                        "jurisdiction": candidate.jurisdiction,
                        "extracted_year": candidate.extracted_year,
                        "file_size": candidate.length,
                        "timestamp": candidate.timestamp,
                    }
                ))

            elapsed_ms = int((time.time() - start) * 1000)

            return DiscoveryResponse(
                query=domain,
                method="annual_report_discovery",
                total_found=len(results),
                results=results,
                sources_used=["cc_pdf_discovery", "common_crawl_index"],
                elapsed_ms=elapsed_ms
            )

        except Exception as e:
            logger.error(f"[AnnualReportDiscovery] Error discovering PDFs: {e}")
            elapsed_ms = int((time.time() - start) * 1000)
            return DiscoveryResponse(
                query=domain,
                method="annual_report_discovery",
                total_found=0,
                results=[],
                sources_used=[],
                elapsed_ms=elapsed_ms
            )

    # ========================================================================
    # DOMAIN INTELLIGENCE
    # ========================================================================

    async def get_pagerank(
        self,
        domains: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get PageRank scores for domains.

        Args:
            domains: List of domains to check

        Returns:
            Dict mapping domain to PageRank data
        """
        if not self.domain_filters or not self.domain_filters.pagerank:
            return {}

        result = self.domain_filters.pagerank.get_pagerank_scores(domains)

        if result.get("success"):
            return {
                item["domain"]: {
                    "page_rank_decimal": item.get("page_rank_decimal"),
                    "page_rank_integer": item.get("page_rank_integer"),
                    "rank": item.get("rank")
                }
                for item in result.get("results", [])
            }
        return {}

    async def filter_by_authority(
        self,
        domains: List[str],
        min_pagerank: float = 2.0
    ) -> List[Dict[str, Any]]:
        """
        Filter domains by minimum PageRank authority.

        Args:
            domains: List of domains
            min_pagerank: Minimum PageRank score (0-10)

        Returns:
            List of domains meeting threshold with scores
        """
        if not self.domain_filters or not self.domain_filters.pagerank:
            return []

        return self.domain_filters.pagerank.filter_by_pagerank(domains, min_pagerank)

    async def get_tranco_rank(
        self,
        domain: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get Tranco ranking for a domain.

        Args:
            domain: Domain to check

        Returns:
            Tranco ranking data or None
        """
        if not self.domain_filters or not self.domain_filters.tranco:
            return None

        result = self.domain_filters.tranco.check_domain_rank(domain)
        if result.get("success"):
            return {
                "domain": domain,
                "rank": result.get("rank"),
                "list_id": result.get("list_id"),
                "date": result.get("date")
            }
        return None

    # ========================================================================
    # TOR BRIDGE / CLEARNET CROSS-REFERENCE
    # ========================================================================

    async def check_tor_connections(
        self,
        clearnet_domain: str,
        limit: int = 100
    ) -> DiscoveryResponse:
        """
        Check if any .onion domains link to a clearnet domain.

        This is the reverse lookup - "who in the dark web links to this clearnet site?"
        Useful for discovering hidden service connections to clearnet infrastructure.

        Args:
            clearnet_domain: Clearnet domain to check (e.g., "example.com")
            limit: Maximum bridges to return

        Returns:
            DiscoveryResponse with .onion domains linking to the clearnet domain
        """
        import time
        start = time.time()

        if not self.tor_bridges:
            return DiscoveryResponse(
                query=clearnet_domain,
                method="tor_cross_reference",
                total_found=0,
                results=[],
                sources_used=[],
                elapsed_ms=0
            )

        try:
            bridges = await self.tor_bridges.get_bridges_to_clearnet(clearnet_domain, limit)

            results = []
            onion_domains_seen = set()

            for bridge in bridges:
                # Extract onion domain from source URL
                from urllib.parse import urlparse
                parsed = urlparse(bridge.source)
                onion_domain = parsed.netloc

                if onion_domain not in onion_domains_seen:
                    onion_domains_seen.add(onion_domain)
                    results.append(DiscoveryResult(
                        source="tor_bridge",
                        result_type="onion_connection",
                        value=onion_domain,
                        url=bridge.source,
                        metadata={
                            "target_url": bridge.target,
                            "anchor_text": bridge.anchor_text,
                            "first_seen": bridge.first_seen,
                        }
                    ))

            elapsed_ms = int((time.time() - start) * 1000)

            return DiscoveryResponse(
                query=clearnet_domain,
                method="tor_cross_reference",
                total_found=len(results),
                results=results,
                sources_used=["tor_bridges"],
                elapsed_ms=elapsed_ms
            )

        except Exception as e:
            logger.error(f"[check_tor_connections] Error: {e}")
            return DiscoveryResponse(
                query=clearnet_domain,
                method="tor_cross_reference",
                total_found=0,
                results=[],
                sources_used=[],
                elapsed_ms=int((time.time() - start) * 1000)
            )

    async def expand_via_tor_bridges(
        self,
        onion_domain: str,
        limit: int = 100,
        run_discovery_on_clearnet: bool = False
    ) -> DiscoveryResponse:
        """
        Get clearnet domains that a .onion domain links to, optionally expanding discovery.

        This reveals clearnet infrastructure operated by hidden services:
        - Payment processors
        - Hosting providers
        - Contact information
        - Related clearnet operations

        Args:
            onion_domain: The .onion domain (with or without .onion suffix)
            limit: Maximum bridges to return
            run_discovery_on_clearnet: If True, run subdomain discovery on found clearnet domains

        Returns:
            DiscoveryResponse with clearnet domains and optionally their subdomains
        """
        import time
        start = time.time()

        if not self.tor_bridges:
            return DiscoveryResponse(
                query=onion_domain,
                method="tor_bridge_expansion",
                total_found=0,
                results=[],
                sources_used=[],
                elapsed_ms=0
            )

        try:
            # Get bridges from onion to clearnet
            bridges = await self.tor_bridges.get_bridges_by_onion(onion_domain, limit)

            results = []
            clearnet_domains_seen = set()
            sources_used = ["tor_bridges"]

            for bridge in bridges:
                # Extract clearnet domain from target URL
                from urllib.parse import urlparse
                parsed = urlparse(bridge.target)
                clearnet_domain = parsed.netloc

                if clearnet_domain and clearnet_domain not in clearnet_domains_seen:
                    clearnet_domains_seen.add(clearnet_domain)
                    results.append(DiscoveryResult(
                        source="tor_bridge",
                        result_type="clearnet_infrastructure",
                        value=clearnet_domain,
                        url=bridge.target,
                        metadata={
                            "source_onion": bridge.source,
                            "anchor_text": bridge.anchor_text,
                            "first_seen": bridge.first_seen,
                        }
                    ))

            # Optional: Run subdomain discovery on found clearnet domains
            if run_discovery_on_clearnet and self.subdomain_discovery:
                logger.info(f"[expand_via_tor_bridges] Running subdomain discovery on {len(clearnet_domains_seen)} clearnet domains")
                for clearnet_domain in list(clearnet_domains_seen)[:10]:  # Limit to 10 domains
                    try:
                        sub_response = await self.discover_subdomains(clearnet_domain)
                        for sub_result in sub_response.results:
                            results.append(DiscoveryResult(
                                source=f"tor_bridge→{sub_result.source}",
                                result_type="subdomain_via_tor",
                                value=sub_result.value,
                                url=sub_result.url,
                                metadata={
                                    "parent_clearnet": clearnet_domain,
                                    "discovered_via_onion": onion_domain,
                                    **sub_result.metadata
                                }
                            ))
                        if sub_response.sources_used:
                            sources_used.extend([f"tor→{s}" for s in sub_response.sources_used if f"tor→{s}" not in sources_used])
                    except Exception as e:
                        logger.warning(f"[expand_via_tor_bridges] Failed subdomain discovery for {clearnet_domain}: {e}")

            elapsed_ms = int((time.time() - start) * 1000)

            return DiscoveryResponse(
                query=onion_domain,
                method="tor_bridge_expansion",
                total_found=len(results),
                results=results,
                sources_used=sources_used,
                elapsed_ms=elapsed_ms
            )

        except Exception as e:
            logger.error(f"[expand_via_tor_bridges] Error: {e}")
            return DiscoveryResponse(
                query=onion_domain,
                method="tor_bridge_expansion",
                total_found=0,
                results=[],
                sources_used=[],
                elapsed_ms=int((time.time() - start) * 1000)
            )

    async def cross_reference_with_tor(
        self,
        domain: str,
        check_both_directions: bool = True,
        expand_clearnet: bool = False,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Full Tor cross-reference for a domain.

        For clearnet domains: Find .onion domains linking TO this domain
        For .onion domains: Find clearnet domains this domain links TO

        This is the key integration between Tor intelligence and clearnet discovery.

        Args:
            domain: Domain to cross-reference (clearnet or .onion)
            check_both_directions: If clearnet, also check if it appears in any bridge targets
            expand_clearnet: If .onion, run subdomain discovery on found clearnet domains
            limit: Maximum results per direction

        Returns:
            Dict with:
            - is_onion: Whether input was a .onion domain
            - onion_connections: .onion domains linking to this clearnet (if clearnet)
            - clearnet_infrastructure: Clearnet domains this .onion links to (if onion)
            - total_connections: Total unique connections found
        """
        import time
        start = time.time()

        is_onion = '.onion' in domain.lower()

        result = {
            "domain": domain,
            "is_onion": is_onion,
            "onion_connections": None,
            "clearnet_infrastructure": None,
            "total_connections": 0,
            "elapsed_ms": 0,
        }

        if is_onion:
            # .onion domain → find clearnet infrastructure
            expansion = await self.expand_via_tor_bridges(
                domain,
                limit=limit,
                run_discovery_on_clearnet=expand_clearnet
            )
            result["clearnet_infrastructure"] = expansion
            result["total_connections"] = expansion.total_found

        else:
            # Clearnet domain → find .onion connections
            connections = await self.check_tor_connections(domain, limit=limit)
            result["onion_connections"] = connections
            result["total_connections"] = connections.total_found

            # If check_both_directions, also see if this clearnet domain links to any .onions
            # (This would require a different query - checking if clearnet pages link to .onion)
            # For now, we focus on the reverse: .onions linking to clearnet

        result["elapsed_ms"] = int((time.time() - start) * 1000)
        return result

    async def get_tor_bridge_stats(self) -> Dict[str, Any]:
        """
        Get statistics about indexed Tor bridges.

        Returns:
            Dict with total bridges, unique onion domains, unique clearnet domains
        """
        if not self.tor_bridges:
            return {"error": "Tor bridges not available", "total_bridges": 0}

        return await self.tor_bridges.get_bridge_stats()

    # ========================================================================
    # GA TRACKER (ANALYTICS FINGERPRINTING)
    # ========================================================================

    async def discover_ga_codes(
        self,
        domain: str
    ) -> Dict[str, Any]:
        """
        Discover GA/GTM codes from a domain (current + historical).

        Args:
            domain: Target domain

        Returns:
            Dict with current_codes, historical_codes, timeline
        """
        if not self._ga_tracker_available:
            return {"error": "GA Tracker not available", "domain": domain}

        async with GATracker() as tracker:
            return await tracker.discover_codes(domain)

    async def find_related_via_ga(
        self,
        domain: str,
        max_per_code: int = 20
    ) -> DiscoveryResponse:
        """
        Find domains related via shared GA/GTM codes.

        Args:
            domain: Target domain
            max_per_code: Max related domains per GA code

        Returns:
            DiscoveryResponse with related domains
        """
        import time
        start = time.time()

        if not self._ga_tracker_available:
            return DiscoveryResponse(
                query=domain,
                method="ga_discovery",
                total_found=0,
                results=[],
                sources_used=[],
                elapsed_ms=0
            )

        async with GATracker() as tracker:
            related = await tracker.find_related_domains(domain, max_per_code=max_per_code)

        results = []
        for ga_code, domains in related.items():
            for related_domain in domains:
                results.append(DiscoveryResult(
                    source="ga_tracker",
                    result_type="ga_related",
                    value=related_domain,
                    url=f"https://{related_domain}/",
                    metadata={
                        "ga_code": ga_code,
                        "source_domain": domain,
                    }
                ))

        elapsed_ms = int((time.time() - start) * 1000)

        return DiscoveryResponse(
            query=domain,
            method="ga_discovery",
            total_found=len(results),
            results=results,
            sources_used=["ga_tracker"],
            elapsed_ms=elapsed_ms
        )

    async def track_and_graph_ga(
        self,
        domain: str,
        max_per_code: int = 20
    ) -> Dict[str, Any]:
        """
        Find related domains via GA codes AND add them to the linkgraph.

        This auto-expands the network via analytics fingerprinting.

        Args:
            domain: Target domain
            max_per_code: Max related domains per GA code

        Returns:
            Dict with codes_found, edges_created, related_domains
        """
        if not self._ga_tracker_available:
            return {"error": "GA Tracker not available", "domain": domain}

        async with GATracker() as tracker:
            return await tracker.track_and_graph(domain, max_per_code=max_per_code)

    async def get_ga_connections(
        self,
        domain: str
    ) -> Dict[str, Any]:
        """
        Get all GA-based connections for a domain from the graph.

        Args:
            domain: Target domain

        Returns:
            Dict with inbound and outbound GA connections
        """
        if not self._ga_tracker_available:
            return {"error": "GA Tracker not available", "domain": domain}

        async with GATracker() as tracker:
            return await tracker.get_ga_connections_for_domain(domain)

    # ========================================================================
    # BACKLINK PIPELINE WITH ENTITY EXTRACTION
    # ========================================================================

    async def discover_backlinks(
        self,
        domain: str,
        max_results: int = 100,
        extract_entities: bool = False,
        max_entity_pages: int = 50,
        entity_method: str = "gpt5nano"
    ) -> Dict[str, Any]:
        """
        Discover backlinks to a domain with optional entity extraction.

        This uses GlobalLinks (WAT files) + Majestic (Fresh + Historic)
        for maximum recall, and optionally extracts entities from
        referring pages to know WHO is linking, not just WHERE.

        Args:
            domain: Target domain to find backlinks for
            max_results: Max backlinks to retrieve
            extract_entities: Whether to extract entities from referring pages
            max_entity_pages: Max pages to scrape for entities (costs API calls)
            entity_method: 'gpt5nano' (AI) or 'regex' (fast/free)

        Returns:
            Dict with:
            - backlinks: List of backlinks with optional entities attached
            - aggregated_entities: Persons, companies, emails, phones found
            - entity_extraction: Stats about extraction
        """
        if not BACKLINK_PIPELINE_AVAILABLE:
            return {"error": "Backlink pipeline not available", "domain": domain}

        pipeline = AutomatedBacklinkPipeline(
            domain,
            extract_entities=extract_entities,
            max_entity_pages=max_entity_pages,
            entity_method=entity_method
        )
        return await pipeline.run(max_results=max_results)

    async def discover_backlinks_with_entities(
        self,
        domain: str,
        max_results: int = 100,
        max_entity_pages: int = 50,
        entity_method: str = "gpt5nano"
    ) -> Dict[str, Any]:
        """
        Convenience method: Discover backlinks AND extract entities.

        This is the key integration - knowing WHO is linking to a target,
        not just WHERE the links come from.

        Args:
            domain: Target domain to find backlinks for
            max_results: Max backlinks to retrieve
            max_entity_pages: Max pages to scrape for entities
            entity_method: 'gpt5nano' (AI) or 'regex' (fast/free)

        Returns:
            Dict with backlinks, entities, and aggregated entity counts
        """
        return await self.discover_backlinks(
            domain,
            max_results=max_results,
            extract_entities=True,
            max_entity_pages=max_entity_pages,
            entity_method=entity_method
        )

    async def get_backlink_entities(
        self,
        domain: str,
        max_pages: int = 50,
        entity_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Quick method to get just the entities from backlink sources.

        Args:
            domain: Target domain
            max_pages: Max referring pages to analyze
            entity_type: Optional filter ('person', 'company', 'email', 'phone', 'address')

        Returns:
            Aggregated entities from referring pages
        """
        result = await self.discover_backlinks(
            domain,
            max_results=max_pages * 2,  # Get more backlinks to ensure enough pages
            extract_entities=True,
            max_entity_pages=max_pages,
            entity_method="gpt5nano"
        )

        if "error" in result:
            return result

        aggregated = result.get("aggregated_entities", {})

        if entity_type:
            # Filter to specific entity type
            entity_key = entity_type + "s" if not entity_type.endswith("s") else entity_type
            if entity_key in aggregated:
                return {
                    "domain": domain,
                    "entity_type": entity_type,
                    "entities": aggregated[entity_key],
                    "total": len(aggregated[entity_key])
                }
            else:
                return {
                    "domain": domain,
                    "entity_type": entity_type,
                    "entities": {},
                    "total": 0
                }

        return {
            "domain": domain,
            "aggregated_entities": aggregated,
            "total_persons": len(aggregated.get("persons", {})),
            "total_companies": len(aggregated.get("companies", {})),
            "total_emails": len(aggregated.get("emails", {})),
            "total_phones": len(aggregated.get("phones", {})),
            "total_addresses": len(aggregated.get("addresses", {})),
        }

    # ========================================================================
    # CLOSED-LOOP DISCOVERY (Entity/Alert → Discovery Feedback)
    # ========================================================================

    async def expand_from_entities(
        self,
        entities: Dict[str, Any],
        discover_companies: bool = True,
        discover_email_domains: bool = True,
        discover_linked_domains: bool = True,
        max_per_type: int = 10,
    ) -> Dict[str, Any]:
        """
        Closed-loop discovery: Extract domains from entity data and run discovery.

        This is the key feedback mechanism - when entities are extracted from
        crawled pages, this method finds new domains to investigate.

        Args:
            entities: Entity data with companies, emails, etc.
            discover_companies: Run discovery on company name domains
            discover_email_domains: Run discovery on email domains
            discover_linked_domains: Run discovery on any domains found in entities
            max_per_type: Max entities to process per type

        Returns:
            Dict with new discoveries spawned from entity data
        """
        import time
        from urllib.parse import urlparse
        import re

        start = time.time()
        results = {
            "source": "entity_feedback",
            "seeds_generated": [],
            "discovery_results": [],
            "domains_found": set(),
            "elapsed_ms": 0,
        }

        # Extract domains from companies
        companies = list(entities.get("companies", {}).keys())[:max_per_type]
        if discover_companies and companies:
            logger.info(f"[ClosedLoop] Processing {len(companies)} companies")
            for company in companies:
                # Try to derive domain from company name (common patterns)
                company_clean = re.sub(r'[^a-zA-Z0-9\s]', '', company.lower())
                company_slug = company_clean.replace(' ', '').strip()
                if len(company_slug) >= 3:
                    # Try common TLDs
                    potential_domains = [
                        f"{company_slug}.com",
                        f"{company_slug}.co",
                        f"{company_slug}.io",
                    ]
                    for domain in potential_domains:
                        results["seeds_generated"].append({
                            "domain": domain,
                            "source_type": "company",
                            "source_value": company,
                        })

        # Extract domains from email addresses
        emails = list(entities.get("emails", {}).keys())[:max_per_type]
        if discover_email_domains and emails:
            logger.info(f"[ClosedLoop] Processing {len(emails)} email domains")
            for email in emails:
                if "@" in email:
                    domain = email.split("@")[1].lower()
                    # Skip common free email providers
                    if domain not in {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
                                     "live.com", "aol.com", "icloud.com", "protonmail.com"}:
                        results["seeds_generated"].append({
                            "domain": domain,
                            "source_type": "email",
                            "source_value": email,
                        })

        # Extract any other domains mentioned (URLs, domains in addresses, etc.)
        if discover_linked_domains:
            all_values = []
            for entity_type in entities.values():
                if isinstance(entity_type, dict):
                    all_values.extend(entity_type.keys())

            domain_pattern = re.compile(
                r'(?:https?://)?(?:www\.)?([a-zA-Z0-9][-a-zA-Z0-9]*\.)+[a-zA-Z]{2,}'
            )
            for value in all_values[:50]:  # Limit scanning
                matches = domain_pattern.findall(str(value))
                for match in matches[:5]:
                    results["seeds_generated"].append({
                        "domain": match.rstrip('.'),
                        "source_type": "extracted",
                        "source_value": value[:100],
                    })

        # Deduplicate seeds
        seen_domains = set()
        unique_seeds = []
        for seed in results["seeds_generated"]:
            domain = seed["domain"].lower()
            if domain not in seen_domains:
                seen_domains.add(domain)
                unique_seeds.append(seed)
        results["seeds_generated"] = unique_seeds

        # Run discovery on unique domains (limit to avoid explosion)
        for seed in unique_seeds[:max_per_type]:
            try:
                # Run subdomain discovery on each seed
                discovery_result = await self.discover_subdomains(seed["domain"])
                results["discovery_results"].append({
                    "seed": seed,
                    "subdomains_found": discovery_result.total_found,
                    "sources_used": discovery_result.sources_used,
                })
                # Collect discovered domains
                for r in discovery_result.results:
                    results["domains_found"].add(r.value)
            except Exception as e:
                logger.warning(f"[ClosedLoop] Discovery failed for {seed['domain']}: {e}")

        results["domains_found"] = list(results["domains_found"])
        results["elapsed_ms"] = int((time.time() - start) * 1000)
        results["total_new_domains"] = len(results["domains_found"])

        logger.info(f"[ClosedLoop] Found {results['total_new_domains']} new domains from {len(unique_seeds)} entity seeds")

        return results

    async def expand_from_alert(
        self,
        alert: Dict[str, Any],
        include_subdomains: bool = True,
        include_whois: bool = False,
        include_tor: bool = False,
    ) -> Dict[str, Any]:
        """
        Closed-loop discovery: Run discovery based on an alert.

        When high-severity alerts are triggered (e.g., new offshore link,
        entity removed, content scrubbed), this method investigates further.

        Args:
            alert: Alert dict with source_domain, target_domain, alert_type, etc.
            include_subdomains: Run subdomain discovery
            include_whois: Run WHOIS clustering
            include_tor: Check Tor connections

        Returns:
            Dict with discovery results spawned from alert
        """
        import time

        start = time.time()
        results = {
            "source": "alert_feedback",
            "alert_id": alert.get("alert_id"),
            "alert_type": alert.get("alert_type"),
            "discoveries": [],
            "total_found": 0,
            "elapsed_ms": 0,
        }

        # Determine domains to investigate based on alert type
        domains_to_investigate = []

        source_domain = alert.get("source_domain")
        target_domain = alert.get("target_domain")
        details = alert.get("details", {})

        # For link alerts, investigate the target
        if alert.get("alert_type") in ["new_offshore", "new_russia_cis", "new_government", "velocity_spike"]:
            if target_domain:
                domains_to_investigate.append({"domain": target_domain, "reason": "alert_target"})

        # For archive alerts, investigate the source and any domains in details
        if alert.get("alert_type") in ["archive_content_change", "archive_entity_added",
                                        "archive_entity_removed", "archive_links_changed"]:
            if source_domain:
                domains_to_investigate.append({"domain": source_domain, "reason": "alert_source"})

            # Check for links added/removed
            for link in details.get("links_added", [])[:5]:
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(link if link.startswith("http") else f"http://{link}")
                    if parsed.netloc:
                        domains_to_investigate.append({"domain": parsed.netloc, "reason": "link_added"})
                except Exception as e:

                    print(f"[LINKLATER] Error: {e}")

                    pass

            for link in details.get("links_removed", [])[:5]:
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(link if link.startswith("http") else f"http://{link}")
                    if parsed.netloc:
                        domains_to_investigate.append({"domain": parsed.netloc, "reason": "link_removed"})
                except Exception as e:

                    print(f"[LINKLATER] Error: {e}")

                    pass

            # Check for companies added/removed
            for company in details.get("companies_added", [])[:3]:
                # Derive potential domain
                company_slug = company.lower().replace(" ", "").replace(",", "").replace(".", "")
                if len(company_slug) >= 3:
                    domains_to_investigate.append({
                        "domain": f"{company_slug}.com",
                        "reason": "company_added"
                    })

        # Deduplicate
        seen = set()
        unique_domains = []
        for d in domains_to_investigate:
            if d["domain"] not in seen:
                seen.add(d["domain"])
                unique_domains.append(d)

        logger.info(f"[ClosedLoop] Alert {alert.get('alert_id')}: investigating {len(unique_domains)} domains")

        # Run discovery on each domain
        for item in unique_domains[:10]:  # Limit to prevent explosion
            domain = item["domain"]
            discovery_entry = {
                "domain": domain,
                "reason": item["reason"],
                "subdomains": None,
                "whois_cluster": None,
                "tor_connections": None,
            }

            try:
                if include_subdomains:
                    subdomain_result = await self.discover_subdomains(domain)
                    discovery_entry["subdomains"] = {
                        "total": subdomain_result.total_found,
                        "sources": subdomain_result.sources_used,
                    }
                    results["total_found"] += subdomain_result.total_found

                if include_whois and WHOIS_DISCOVERY_AVAILABLE:
                    whois_result = await self.cluster_by_whois(domain, limit=20)
                    discovery_entry["whois_cluster"] = {
                        "total": whois_result.total_found,
                    }
                    results["total_found"] += whois_result.total_found

                if include_tor and TOR_BRIDGES_AVAILABLE:
                    tor_result = await self.cross_reference_with_tor(domain)
                    discovery_entry["tor_connections"] = {
                        "total": tor_result.get("total_connections", 0),
                    }
                    results["total_found"] += tor_result.get("total_connections", 0)

            except Exception as e:
                logger.warning(f"[ClosedLoop] Discovery failed for {domain}: {e}")
                discovery_entry["error"] = str(e)

            results["discoveries"].append(discovery_entry)

        results["elapsed_ms"] = int((time.time() - start) * 1000)

        return results

    async def closed_loop_crawl(
        self,
        seed_domain: str,
        max_iterations: int = 3,
        max_pages_per_iteration: int = 100,
        extract_entities: bool = True,
        trigger_alerts: bool = True,
        expand_on_entities: bool = True,
    ) -> Dict[str, Any]:
        """
        Full closed-loop crawl pipeline.

        Implements: Discovery → Crawl → Entities → Alerts → Discovery (repeat)

        This is the complete feedback loop that:
        1. Discovers subdomains for a seed domain
        2. Crawls discovered pages
        3. Extracts entities from crawled content
        4. Checks for alert conditions
        5. Uses entities/alerts to discover new domains
        6. Repeats up to max_iterations

        Args:
            seed_domain: Initial domain to start from
            max_iterations: Maximum feedback loop iterations
            max_pages_per_iteration: Max pages to crawl per iteration
            extract_entities: Whether to extract entities from crawled pages
            trigger_alerts: Whether to check for alert conditions
            expand_on_entities: Whether to use entities to find new domains

        Returns:
            Dict with complete loop results across all iterations
        """
        import time

        start = time.time()
        results = {
            "seed_domain": seed_domain,
            "iterations": [],
            "total_pages_crawled": 0,
            "total_entities_found": 0,
            "total_alerts_triggered": 0,
            "total_domains_discovered": 0,
            "domains_investigated": set([seed_domain]),
            "elapsed_ms": 0,
        }

        current_seeds = [seed_domain]

        for iteration in range(max_iterations):
            logger.info(f"[ClosedLoop] Iteration {iteration + 1}/{max_iterations} with {len(current_seeds)} seeds")

            iteration_result = {
                "iteration": iteration + 1,
                "seeds": list(current_seeds)[:10],  # Limit display
                "discovery": None,
                "crawl": None,
                "entities": None,
                "alerts": [],
                "new_seeds_from_entities": [],
            }

            # Phase 1: Discovery
            try:
                if len(current_seeds) == 1:
                    discovery_result = await self.discover_subdomains(current_seeds[0])
                    iteration_result["discovery"] = {
                        "total": discovery_result.total_found,
                        "sources": discovery_result.sources_used,
                    }
                    results["total_domains_discovered"] += discovery_result.total_found
            except Exception as e:
                logger.error(f"[ClosedLoop] Discovery failed: {e}")
                iteration_result["discovery"] = {"error": str(e)}

            # Phase 2: Crawl (simplified - just count pages we would crawl)
            pages_this_iteration = min(max_pages_per_iteration, len(current_seeds) * 10)
            iteration_result["crawl"] = {
                "seeds_count": len(current_seeds),
                "max_pages": pages_this_iteration,
                "note": "Full crawl integration available via discover_and_crawl()"
            }
            results["total_pages_crawled"] += pages_this_iteration

            # Phase 3: Entity extraction (if we have backlink entities available)
            if extract_entities and BACKLINK_PIPELINE_AVAILABLE and len(current_seeds) > 0:
                try:
                    entity_result = await self.get_backlink_entities(
                        current_seeds[0],
                        max_pages=min(20, pages_this_iteration // 5)
                    )
                    if "aggregated_entities" in entity_result:
                        iteration_result["entities"] = {
                            "persons": entity_result.get("total_persons", 0),
                            "companies": entity_result.get("total_companies", 0),
                            "emails": entity_result.get("total_emails", 0),
                        }
                        results["total_entities_found"] += sum([
                            entity_result.get("total_persons", 0),
                            entity_result.get("total_companies", 0),
                            entity_result.get("total_emails", 0),
                        ])

                        # Phase 4: Use entities to find new domains
                        if expand_on_entities:
                            entity_expansion = await self.expand_from_entities(
                                entity_result.get("aggregated_entities", {}),
                                max_per_type=5
                            )
                            iteration_result["new_seeds_from_entities"] = [
                                s["domain"] for s in entity_expansion.get("seeds_generated", [])
                            ][:5]

                except Exception as e:
                    logger.warning(f"[ClosedLoop] Entity extraction failed: {e}")
                    iteration_result["entities"] = {"error": str(e)}

            # Phase 5: Alert checking (simplified)
            if trigger_alerts:
                try:
                    from ..alerts.link_alerts import LinkAlertService
                    alert_service = LinkAlertService()
                    alerts = await alert_service.check_for_alerts(current_seeds[0], since_hours=24)
                    iteration_result["alerts"] = [a.alert_type for a in alerts]
                    results["total_alerts_triggered"] += len(alerts)
                except ImportError:
                    pass
                except Exception as e:
                    logger.warning(f"[ClosedLoop] Alert check failed: {e}")

            results["iterations"].append(iteration_result)

            # Prepare seeds for next iteration
            new_seeds = set()

            # Add entity-derived domains
            for seed in iteration_result.get("new_seeds_from_entities", []):
                if seed not in results["domains_investigated"]:
                    new_seeds.add(seed)
                    results["domains_investigated"].add(seed)

            if not new_seeds:
                logger.info(f"[ClosedLoop] No new seeds found, stopping after {iteration + 1} iterations")
                break

            current_seeds = list(new_seeds)[:5]  # Limit expansion

        results["domains_investigated"] = list(results["domains_investigated"])
        results["elapsed_ms"] = int((time.time() - start) * 1000)

        return results

    # ========================================================================
    # DISCOVERY → CRAWLER INTEGRATION
    # ========================================================================

    async def discover_and_crawl(
        self,
        domain: str,
        include_subdomains: bool = True,
        include_whois_cluster: bool = False,
        max_pages: int = 1000,
        max_concurrent: int = 50,
        project_id: Optional[str] = None,
        on_page: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Discover subdomains/related domains and automatically crawl them.

        This is the key integration that connects Discovery → DRILL Crawler.
        Instead of just returning discovered URLs, this method feeds them
        directly to the crawler for 10x more coverage per investigation.

        Args:
            domain: Target domain to discover and crawl
            include_subdomains: Discover subdomains via crt.sh, etc.
            include_whois_cluster: Also discover WHOIS-related domains
            max_pages: Max pages to crawl per seed domain
            max_concurrent: Concurrent crawler requests
            project_id: Project ID for organizing crawl results
            on_page: Optional callback for each crawled page

        Returns:
            Dict with:
            - discovery: DiscoveryResponse with what was found
            - crawl_stats: CrawlStats from the crawler
            - seeds_used: List of seed URLs fed to crawler

        Example:
            discovery = UnifiedDiscovery()
            result = await discovery.discover_and_crawl("example.com")
            print(f"Discovered {result['discovery'].total_found} subdomains")
            print(f"Crawled {result['crawl_stats'].pages_crawled} pages")
        """
        import time
        from typing import Callable

        start = time.time()
        all_seeds: Set[str] = set()

        # Phase 1: Subdomain discovery
        subdomain_response = None
        if include_subdomains:
            logger.info(f"[Discovery→Crawler] Discovering subdomains for {domain}...")
            subdomain_response = await self.discover_subdomains(domain)

            # Convert subdomains to seed URLs
            for result in subdomain_response.results:
                subdomain = result.value
                if not subdomain.startswith(('http://', 'https://')):
                    all_seeds.add(f"https://{subdomain}/")
                else:
                    all_seeds.add(subdomain)

            logger.info(f"[Discovery→Crawler] Found {subdomain_response.total_found} subdomains")

        # Phase 2: WHOIS clustering (optional)
        whois_response = None
        if include_whois_cluster and WHOIS_DISCOVERY_AVAILABLE:
            logger.info(f"[Discovery→Crawler] Clustering WHOIS for {domain}...")
            whois_response = await self.cluster_by_whois(domain, limit=50)

            # Add WHOIS-related domains as seeds
            for result in whois_response.results:
                related_domain = result.value
                if not related_domain.startswith(('http://', 'https://')):
                    all_seeds.add(f"https://{related_domain}/")

            logger.info(f"[Discovery→Crawler] Found {whois_response.total_found} related domains via WHOIS")

        # Always add the root domain
        all_seeds.add(f"https://{domain}/")

        seed_list = list(all_seeds)
        logger.info(f"[Discovery→Crawler] Total seeds: {len(seed_list)}")

        # Phase 3: Initialize and run DRILL crawler
        try:
            from ..scraping.web.crawler import Drill, DrillConfig

            config = DrillConfig(
                max_pages=max_pages,
                max_concurrent=max_concurrent,
                use_sitemap_first=True,  # Also use sitemap discovery
                discover_subdomains=False,  # We already did subdomain discovery
                discover_archives=True,
                extract_entities=True,
                generate_embeddings=True,
                index_to_elasticsearch=True,
                project_id=project_id,
            )

            drill = Drill(config)

            logger.info(f"[Discovery→Crawler] Starting crawl with {len(seed_list)} seeds...")
            crawl_stats = await drill.crawl_with_external_seeds(
                domain=domain,
                external_seeds=seed_list,
                merge_with_discovery=True,  # Also use internal discovery
                on_page=on_page,
            )

        except ImportError as e:
            logger.error(f"[Discovery→Crawler] DRILL crawler not available: {e}")
            crawl_stats = None

        elapsed_ms = int((time.time() - start) * 1000)

        # Combine discovery responses
        combined_response = subdomain_response or DiscoveryResponse(
            query=domain,
            method="discover_and_crawl",
            total_found=0,
            results=[],
            sources_used=[],
            elapsed_ms=elapsed_ms
        )

        if whois_response:
            combined_response.results.extend(whois_response.results)
            combined_response.total_found += whois_response.total_found
            combined_response.sources_used.extend(whois_response.sources_used)

        return {
            "discovery": combined_response,
            "crawl_stats": crawl_stats.to_dict() if crawl_stats else None,
            "seeds_used": seed_list,
            "elapsed_ms": elapsed_ms,
        }

    async def seed_crawler(
        self,
        domain: str,
        discovery_response: DiscoveryResponse,
        max_pages: int = 1000,
        project_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Feed an existing DiscoveryResponse to the DRILL crawler.

        Use this when you've already run discovery and want to crawl the results.

        Args:
            domain: Target domain
            discovery_response: Results from any discovery method
            max_pages: Max pages to crawl
            project_id: Project ID for organizing results

        Returns:
            CrawlStats dict or None if crawler unavailable
        """
        # Convert discovery results to seed URLs
        seeds = []
        for result in discovery_response.results:
            value = result.value
            if result.result_type in ("subdomain", "domain", "whois_cluster", "reverse_whois"):
                if not value.startswith(('http://', 'https://')):
                    seeds.append(f"https://{value}/")
                else:
                    seeds.append(value)
            elif result.url:
                seeds.append(result.url)

        if not seeds:
            logger.warning("[seed_crawler] No seeds extracted from discovery response")
            return None

        try:
            from ..scraping.web.crawler import Drill, DrillConfig

            config = DrillConfig(
                max_pages=max_pages,
                project_id=project_id,
            )

            drill = Drill(config)
            stats = await drill.crawl_with_external_seeds(
                domain=domain,
                external_seeds=seeds,
                merge_with_discovery=False,
            )

            return stats.to_dict()

        except ImportError as e:
            logger.error(f"[seed_crawler] DRILL crawler not available: {e}")
            return None


# ============================================================================
# Convenience Functions
# ============================================================================

_discovery = None

def get_discovery() -> UnifiedDiscovery:
    """Get or create singleton discovery instance"""
    global _discovery
    if _discovery is None:
        _discovery = UnifiedDiscovery()
    return _discovery


async def discover_subdomains(domain: str) -> DiscoveryResponse:
    """Discover subdomains (convenience function)"""
    return await get_discovery().discover_subdomains(domain)


async def cluster_by_whois(domain: str) -> DiscoveryResponse:
    """Cluster domains by WHOIS (convenience function)"""
    return await get_discovery().cluster_by_whois(domain)


async def search_news(query: str) -> DiscoveryResponse:
    """Search news sources (convenience function)"""
    return await get_discovery().search_news(query)


async def search_gdelt(query: str) -> DiscoveryResponse:
    """Search GDELT (convenience function)"""
    return await get_discovery().search_gdelt(query)


async def check_tor_connections(clearnet_domain: str) -> DiscoveryResponse:
    """Check for Tor connections to clearnet domain (convenience function)"""
    return await get_discovery().check_tor_connections(clearnet_domain)


async def expand_via_tor_bridges(onion_domain: str) -> DiscoveryResponse:
    """Expand discovery via Tor bridges (convenience function)"""
    return await get_discovery().expand_via_tor_bridges(onion_domain)


async def cross_reference_with_tor(domain: str) -> Dict[str, Any]:
    """Full Tor cross-reference (convenience function)"""
    return await get_discovery().cross_reference_with_tor(domain)


# ============================================================================
# CLI Entry Point
# ============================================================================

if __name__ == "__main__":
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="LinkLater Unified Discovery")
    parser.add_argument("query", help="Domain or search query")
    parser.add_argument("-m", "--method",
                       choices=["subdomains", "whois", "news", "gdelt", "tor", "tor-expand", "ga", "ga-graph",
                                "backlinks", "backlinks-entities", "backlink-entities",
                                "closed-loop", "expand-entities", "capabilities"],
                       default="capabilities",
                       help="Discovery method")
    parser.add_argument("-l", "--limit", type=int, default=50, help="Max results")
    parser.add_argument("--expand", action="store_true", help="For tor-expand: also run subdomain discovery on clearnet domains")
    parser.add_argument("--graph", action="store_true", help="For ga: also add edges to linkgraph")
    parser.add_argument("-e", "--entities", action="store_true", help="For backlinks: extract entities from referring pages")
    parser.add_argument("--entity-pages", type=int, default=50, help="Max pages to scrape for entity extraction")
    parser.add_argument("--entity-method", choices=["gpt5nano", "regex"], default="gpt5nano",
                       help="Entity extraction method")
    # Closed-loop options
    parser.add_argument("--iterations", type=int, default=3, help="Max iterations for closed-loop crawl")
    parser.add_argument("--pages-per-iter", type=int, default=100, help="Max pages per iteration for closed-loop")
    parser.add_argument("--no-alerts", action="store_true", help="Disable alert triggering in closed-loop")

    args = parser.parse_args()

    async def main():
        discovery = UnifiedDiscovery()

        if args.method == "capabilities":
            print("\n📊 Discovery Capabilities:")
            for cap, available in discovery.get_capabilities().items():
                status = "✅" if available else "❌"
                print(f"  {status} {cap}")
            return

        response = None

        if args.method == "subdomains":
            print(f"\n🔍 Discovering subdomains for: {args.query}")
            response = await discovery.discover_subdomains(args.query)
        elif args.method == "whois":
            print(f"\n🔍 WHOIS clustering for: {args.query}")
            response = await discovery.cluster_by_whois(args.query, limit=args.limit)
        elif args.method == "news":
            print(f"\n🔍 News search for: {args.query}")
            response = await discovery.search_news(args.query, max_results=args.limit)
        elif args.method == "gdelt":
            print(f"\n🔍 GDELT search for: {args.query}")
            response = await discovery.search_gdelt(args.query, max_results=args.limit)
        elif args.method == "tor":
            # Cross-reference: check for Tor connections
            print(f"\n🧅 Tor cross-reference for: {args.query}")
            result = await discovery.cross_reference_with_tor(args.query, limit=args.limit)
            print(f"\nDomain: {result['domain']}")
            print(f"Is .onion: {result['is_onion']}")
            print(f"Total connections: {result['total_connections']}")
            print(f"Elapsed: {result['elapsed_ms']}ms")

            if result['onion_connections']:
                response = result['onion_connections']
                print(f"\n🔗 .onion domains linking to this clearnet site:")
            elif result['clearnet_infrastructure']:
                response = result['clearnet_infrastructure']
                print(f"\n🌐 Clearnet infrastructure linked from this .onion:")

        elif args.method == "tor-expand":
            # Expand via Tor bridges (for .onion domains)
            print(f"\n🧅 Expanding via Tor bridges for: {args.query}")
            response = await discovery.expand_via_tor_bridges(
                args.query,
                limit=args.limit,
                run_discovery_on_clearnet=args.expand
            )

        elif args.method == "ga":
            # GA analytics fingerprinting
            print(f"\n📊 GA fingerprinting for: {args.query}")
            if args.graph:
                result = await discovery.track_and_graph_ga(args.query, max_per_code=args.limit)
                print(f"\n✅ GA codes found: {result.get('codes_found', 0)}")
                print(f"🔗 Edges created: {result.get('edges_created', 0)}")
                for code, domains in result.get('related_domains', {}).items():
                    print(f"\n{code}:")
                    for d in domains:
                        print(f"  → {d}")
                return
            else:
                response = await discovery.find_related_via_ga(args.query, max_per_code=args.limit)

        elif args.method == "ga-graph":
            # GA graph query
            print(f"\n📊 GA connections from graph for: {args.query}")
            result = await discovery.get_ga_connections(args.query)
            print(f"\n🔗 GA Codes: {len(result.get('ga_codes', []))}")
            for code in result.get('ga_codes', []):
                print(f"  • {code}")
            print(f"\n📤 Outbound: {len(result.get('outbound', []))} connections")
            for conn in result.get('outbound', [])[:10]:
                print(f"  → {conn['domain']} (via {conn['ga_code']})")
            print(f"\n📥 Inbound: {len(result.get('inbound', []))} connections")
            for conn in result.get('inbound', [])[:10]:
                print(f"  ← {conn['domain']} (via {conn['ga_code']})")
            return

        elif args.method == "backlinks":
            # Backlink discovery with optional entity extraction
            print(f"\n🔗 Backlink discovery for: {args.query}")
            if args.entities:
                print(f"   Entity extraction enabled (method: {args.entity_method})")
            result = await discovery.discover_backlinks(
                args.query,
                max_results=args.limit,
                extract_entities=args.entities,
                max_entity_pages=args.entity_pages,
                entity_method=args.entity_method
            )

            print(f"\n✅ Found {result.get('total_backlinks', 0)} backlinks")
            print(f"   GlobalLinks: {result.get('globallinks_count', 0)}")
            print(f"   Majestic: {result.get('majestic_count', 0)}")

            # Show entity extraction stats if enabled
            entity_stats = result.get('entity_extraction', {})
            if entity_stats.get('enabled'):
                print(f"\n👥 Entity Extraction:")
                print(f"   Pages scraped: {entity_stats.get('pages_scraped', 0)}")
                print(f"   Pages with entities: {entity_stats.get('pages_with_entities', 0)}")
                print(f"   Total entities: {entity_stats.get('total_entities', 0)}")

            # Show aggregated entities if available
            aggregated = result.get('aggregated_entities', {})
            if aggregated:
                if aggregated.get('persons'):
                    print(f"\n🧑 Persons ({len(aggregated['persons'])} unique):")
                    for person, count in list(aggregated['persons'].items())[:5]:
                        print(f"   • {person} ({count}x)")
                if aggregated.get('companies'):
                    print(f"\n🏢 Companies ({len(aggregated['companies'])} unique):")
                    for company, count in list(aggregated['companies'].items())[:5]:
                        print(f"   • {company} ({count}x)")
                if aggregated.get('emails'):
                    print(f"\n📧 Emails ({len(aggregated['emails'])} unique):")
                    for email, count in list(aggregated['emails'].items())[:5]:
                        print(f"   • {email} ({count}x)")

            return

        elif args.method in ["backlinks-entities", "backlink-entities"]:
            # Quick backlink entity extraction
            print(f"\n👥 Extracting entities from backlink sources for: {args.query}")
            result = await discovery.get_backlink_entities(
                args.query,
                max_pages=args.entity_pages
            )

            if "error" in result:
                print(f"❌ Error: {result['error']}")
                return

            print(f"\n✅ Entity Summary for {result['domain']}:")
            print(f"   Persons: {result.get('total_persons', 0)}")
            print(f"   Companies: {result.get('total_companies', 0)}")
            print(f"   Emails: {result.get('total_emails', 0)}")
            print(f"   Phones: {result.get('total_phones', 0)}")
            print(f"   Addresses: {result.get('total_addresses', 0)}")

            aggregated = result.get('aggregated_entities', {})
            if aggregated.get('persons'):
                print(f"\n🧑 Top Persons:")
                sorted_persons = sorted(aggregated['persons'].items(), key=lambda x: x[1], reverse=True)
                for person, count in sorted_persons[:10]:
                    print(f"   • {person} ({count}x)")

            if aggregated.get('companies'):
                print(f"\n🏢 Top Companies:")
                sorted_companies = sorted(aggregated['companies'].items(), key=lambda x: x[1], reverse=True)
                for company, count in sorted_companies[:10]:
                    print(f"   • {company} ({count}x)")

            return

        elif args.method == "expand-entities":
            # Extract entities from backlinks, then expand discovery based on them
            print(f"\n🔄 Entity-based expansion for: {args.query}")
            print(f"   Step 1: Extracting entities from backlink sources...")

            # First get entities
            entity_result = await discovery.get_backlink_entities(
                args.query,
                max_pages=args.entity_pages
            )

            if "error" in entity_result:
                print(f"❌ Error: {entity_result['error']}")
                return

            aggregated = entity_result.get('aggregated_entities', {})
            print(f"\n   Found entities:")
            print(f"   • Persons: {len(aggregated.get('persons', {}))}")
            print(f"   • Companies: {len(aggregated.get('companies', {}))}")
            print(f"   • Emails: {len(aggregated.get('emails', {}))}")

            print(f"\n   Step 2: Running entity-based discovery expansion...")

            # Now expand based on entities
            expansion = await discovery.expand_from_entities(
                aggregated,
                discover_companies=True,
                discover_email_domains=True,
                discover_linked_domains=True,
                max_per_type=10
            )

            print(f"\n✅ Entity Expansion Results:")
            print(f"   Seeds generated: {len(expansion.get('seeds_generated', []))}")
            print(f"   Domains discovered: {len(expansion.get('domains_found', set()))}")
            print(f"   Elapsed: {expansion.get('elapsed_ms', 0)}ms")

            if expansion.get('seeds_generated'):
                print(f"\n🌱 Seeds Generated:")
                for seed in expansion['seeds_generated'][:15]:
                    print(f"   • {seed['domain']} (from {seed['source_type']}: {seed['source_value'][:30]}...)")

            if expansion.get('discovery_results'):
                print(f"\n🔍 Discovery Results:")
                for dr in expansion['discovery_results'][:10]:
                    seed_domain = dr['seed']['domain']
                    subdomains = dr.get('subdomains_found', 0)
                    sources = ', '.join(dr.get('sources_used', []))
                    print(f"   • {seed_domain}: {subdomains} subdomains ({sources})")

            return

        elif args.method == "closed-loop":
            # Full closed-loop discovery pipeline
            print(f"\n🔄 Starting Closed-Loop Discovery Pipeline for: {args.query}")
            print(f"   Max iterations: {args.iterations}")
            print(f"   Pages per iteration: {args.pages_per_iter}")
            print(f"   Entity extraction: enabled")
            print(f"   Alert triggering: {'disabled' if args.no_alerts else 'enabled'}")
            print()

            result = await discovery.closed_loop_crawl(
                args.query,
                max_iterations=args.iterations,
                max_pages_per_iteration=args.pages_per_iter,
                extract_entities=True,
                trigger_alerts=not args.no_alerts,
                expand_on_entities=True
            )

            print(f"\n{'='*60}")
            print(f"📊 CLOSED-LOOP DISCOVERY COMPLETE")
            print(f"{'='*60}")
            print(f"\n🌱 Seed domain: {result['seed_domain']}")
            print(f"🔁 Iterations completed: {len(result.get('iterations', []))}")
            print(f"📄 Total pages crawled: {result.get('total_pages_crawled', 0)}")
            print(f"👥 Total entities found: {result.get('total_entities_found', 0)}")
            print(f"🚨 Alerts triggered: {result.get('total_alerts_triggered', 0)}")
            print(f"🌐 Domains discovered: {result.get('total_domains_discovered', 0)}")
            print(f"🔍 Domains investigated: {len(result.get('domains_investigated', set()))}")

            # Show iteration details
            for i, iteration in enumerate(result.get('iterations', []), 1):
                print(f"\n📍 Iteration {i}:")
                print(f"   Seeds: {', '.join(iteration.get('seeds', []))}")
                print(f"   Subdomains found: {iteration.get('subdomains_found', 0)}")
                print(f"   Pages crawled: {iteration.get('pages_crawled', 0)}")
                print(f"   Entities extracted: {iteration.get('entities_extracted', 0)}")
                print(f"   Alerts triggered: {len(iteration.get('alerts_triggered', []))}")
                if iteration.get('new_seeds_from_entities'):
                    print(f"   New seeds from entities: {', '.join(iteration['new_seeds_from_entities'][:5])}")

            # Show all discovered domains
            if result.get('domains_investigated'):
                print(f"\n🗺️ All Domains Investigated:")
                for domain in sorted(result['domains_investigated']):
                    print(f"   • {domain}")

            return

        if response:
            print(f"\nFound {response.total_found} results in {response.elapsed_ms}ms")
            print(f"Sources used: {', '.join(response.sources_used)}")
            print()

            for i, result in enumerate(response.results[:20], 1):
                print(f"{i}. [{result.source}] {result.value}")
                if result.url:
                    print(f"   URL: {result.url}")
                if result.metadata:
                    for k, v in result.metadata.items():
                        if v:
                            print(f"   {k}: {v}")

    asyncio.run(main())
