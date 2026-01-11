"""
DRILL Discovery - Full LinkLater Integration

URL discovery using ALL LinkLater capabilities.
This is just another LinkLater module - it uses everything LinkLater already has.

FREE Sources (no API keys required):
1. crt.sh - Certificate transparency → subdomains
2. Sublist3r - Multi-source subdomain enumeration (10+ sources)
3. Common Crawl CDX - Archived URLs
4. Wayback Machine - Archive.org URLs
5. CC Graph - Domain link graph (157M domains, 2.1B edges)
6. GlobalLinks - WAT-based link extraction (Go binary)
7. Tranco - Top domains ranking
8. OpenPageRank - Authority scores (200K FREE/month)
9. Cloudflare Radar - Traffic rankings
10. BigQuery - HTTP Archive/CrUX datasets
11. Sitemap.xml - Standard sitemap parsing
12. robots.txt - Crawl directives

PAID Sources (require API keys):
- Majestic - Premium backlinks with anchor text

Default mode: FREE_ONLY (uses only free sources)
Full mode: Include Majestic if MAJESTIC_API_KEY is set
"""

import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from urllib.parse import urlparse
from datetime import datetime
import os
import json
import re
import sys
from pathlib import Path

# Add parent paths for LinkLater imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

DEFAULT_SOURCE_WEIGHTS = {
    "sitemap": 80,
    "robots": 70,
    "crtsh": 55,
    "sublist3r": 55,
    "commoncrawl": 40,
    "wayback": 35,
    "cc_graph_backlinks": 50,
    "globallinks_backlinks": 50,
    "cc_graph_outlinks": 45,
    "globallinks_outlinks": 45,
    "majestic": 60,
}

ARCHIVE_SOURCES = {"commoncrawl", "wayback"}

HIGH_VALUE_PATTERNS = [
    r"/(investor|investors|investor-relations|ir)\b",
    r"/(annual|report|reports|financials?|filings?|sec|10-k|10q|20-f|prospectus)\b",
    r"/(team|leadership|management|board)\b",
    r"/(about|company|overview|mission|values)\b",
    r"/(press|news|media|blog)\b",
    r"/(governance|compliance|ethics|policy|legal|privacy|terms)\b",
    r"/(careers|jobs|vacancies)\b",
]

DOCUMENT_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv",
}


@dataclass
class DiscoveredURL:
    """A URL discovered from a source."""
    url: str
    source: str
    domain: str
    discovered_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveryResult:
    """Result of URL discovery for a domain."""
    domain: str
    total_urls: int
    urls_by_source: Dict[str, List[str]]
    subdomains: List[str]
    backlink_domains: List[str]  # Domains linking TO target
    outlink_domains: List[str]   # Domains target links TO
    sitemaps_found: List[str]
    discovery_time_seconds: float
    sources_used: List[str]
    sources_failed: List[str]


@dataclass
class SeedCandidate:
    """Ranked seed URL for crawl planning."""
    url: str
    source: str
    score: int
    lane: str
    reasons: List[str] = field(default_factory=list)


class DrillDiscovery:
    """
    Multi-source URL discovery using LinkLater's full capabilities.

    This is a LinkLater module - it doesn't duplicate functionality,
    it orchestrates LinkLater's existing tools.
    """

    def __init__(
        self,
        free_only: bool = True,
        timeout: int = 30,
        max_concurrent: int = 10,
    ):
        """
        Initialize discovery.

        Args:
            free_only: Only use free sources (default True, excludes Majestic)
            timeout: HTTP request timeout in seconds
            max_concurrent: Max concurrent requests
        """
        self.free_only = free_only
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)

        # Check API keys
        self.has_majestic = bool(os.getenv("MAJESTIC_API_KEY")) and not free_only
        self.has_openpagerank = bool(os.getenv("OPENPAGERANK_API_KEY"))
        self.has_cloudflare = bool(os.getenv("CLOUDFLARE_API_TOKEN"))

        # Lazy-loaded LinkLater components
        self._linklater = None
        self._globallinks = None
        self._domain_filters = None

    @property
    def linklater(self):
        """Lazy load LinkLater API."""
        if self._linklater is None:
            try:
                from modules.linklater.api import linklater
                self._linklater = linklater
            except ImportError:
                self._linklater = None
        return self._linklater

    @property
    def globallinks(self):
        """Lazy load GlobalLinks client."""
        if self._globallinks is None:
            try:
                from modules.linklater.linkgraph.globallinks import GlobalLinksClient
                self._globallinks = GlobalLinksClient()
            except ImportError:
                self._globallinks = None
        return self._globallinks

    @property
    def domain_filters(self):
        """Lazy load domain filters."""
        if self._domain_filters is None:
            try:
                from modules.linklater.mapping.domain_filters import DomainFilters
                self._domain_filters = DomainFilters()
            except ImportError:
                self._domain_filters = None
        return self._domain_filters

    async def discover(
        self,
        domain: str,
        include_subdomains: bool = True,
        include_archives: bool = True,
        include_backlinks: bool = True,
        include_outlinks: bool = True,
        max_urls_per_source: int = 1000,
    ) -> DiscoveryResult:
        """
        Discover all URLs for a domain using LinkLater's full capabilities.

        Args:
            domain: Target domain (e.g., "example.com")
            include_subdomains: Discover subdomains via crt.sh
            include_archives: Check Wayback + Common Crawl
            include_backlinks: Get referring pages/domains
            include_outlinks: Get pages this domain links to
            max_urls_per_source: Limit per source

        Returns:
            DiscoveryResult with all discovered URLs
        """
        start_time = asyncio.get_event_loop().time()

        # Clean domain
        domain = domain.lower().strip()
        if domain.startswith(('http://', 'https://')):
            domain = urlparse(domain).netloc

        urls_by_source: Dict[str, List[str]] = {}
        all_subdomains: Set[str] = {domain}
        all_sitemaps: List[str] = []
        backlink_domains: Set[str] = set()
        outlink_domains: Set[str] = set()
        sources_used: List[str] = []
        sources_failed: List[str] = []

        # ====================================================================
        # PHASE 1: Basic Discovery (FREE, always run)
        # ====================================================================
        basic_tasks = [
            ("sitemap", self._discover_sitemaps(domain, max_urls_per_source)),
            ("robots", self._discover_robots(domain)),
        ]

        if include_subdomains:
            basic_tasks.append(("crtsh", self._discover_subdomains_crtsh(domain)))
            basic_tasks.append(("sublist3r", self._discover_subdomains_sublist3r(domain)))

        # ====================================================================
        # PHASE 2: Archive Discovery (FREE)
        # ====================================================================
        if include_archives:
            basic_tasks.append(("wayback", self._discover_wayback(domain, max_urls_per_source)))
            basic_tasks.append(("commoncrawl", self._discover_commoncrawl(domain, max_urls_per_source)))

        # ====================================================================
        # PHASE 3: Link Graph Discovery (FREE - CC Graph + GlobalLinks)
        # ====================================================================
        if include_backlinks:
            basic_tasks.append(("cc_graph_backlinks", self._discover_cc_graph_backlinks(domain, max_urls_per_source)))
            basic_tasks.append(("globallinks_backlinks", self._discover_globallinks_backlinks(domain, max_urls_per_source)))

        if include_outlinks:
            basic_tasks.append(("cc_graph_outlinks", self._discover_cc_graph_outlinks(domain, max_urls_per_source)))
            basic_tasks.append(("globallinks_outlinks", self._discover_globallinks_outlinks(domain, max_urls_per_source)))

        # ====================================================================
        # PHASE 4: Premium Sources (if not free_only)
        # ====================================================================
        if not self.free_only and self.has_majestic:
            basic_tasks.append(("majestic", self._discover_majestic_backlinks(domain, max_urls_per_source)))

        # Run all tasks in parallel
        task_results = await asyncio.gather(
            *[task for _, task in basic_tasks],
            return_exceptions=True
        )

        # Process results
        for (source_name, _), result in zip(basic_tasks, task_results):
            if isinstance(result, Exception):
                sources_failed.append(source_name)
                continue

            if isinstance(result, dict):
                urls = result.get("urls", [])
                subdomains = result.get("subdomains", [])
                sitemaps = result.get("sitemaps", [])
                backlinks = result.get("backlink_domains", [])
                outlinks = result.get("outlink_domains", [])

                if urls:
                    urls_by_source[source_name] = urls[:max_urls_per_source]
                    sources_used.append(source_name)

                if subdomains:
                    all_subdomains.update(subdomains)

                if sitemaps:
                    all_sitemaps.extend(sitemaps)

                if backlinks:
                    backlink_domains.update(backlinks)

                if outlinks:
                    outlink_domains.update(outlinks)

        # Calculate totals
        total_urls = sum(len(urls) for urls in urls_by_source.values())
        elapsed = asyncio.get_event_loop().time() - start_time

        return DiscoveryResult(
            domain=domain,
            total_urls=total_urls,
            urls_by_source=urls_by_source,
            subdomains=sorted(all_subdomains),
            backlink_domains=sorted(backlink_domains),
            outlink_domains=sorted(outlink_domains),
            sitemaps_found=all_sitemaps,
            discovery_time_seconds=round(elapsed, 2),
            sources_used=sources_used,
            sources_failed=sources_failed,
        )

    # ========================================================================
    # FREE SOURCES
    # ========================================================================

    async def _discover_sitemaps(self, domain: str, max_urls: int) -> Dict[str, Any]:
        """Sitemap discovery (FREE)."""
        urls = []
        sitemaps_found = []

        sitemap_locations = [
            f"https://{domain}/sitemap.xml",
            f"https://{domain}/sitemap_index.xml",
            f"https://{domain}/sitemap/sitemap.xml",
            f"https://www.{domain}/sitemap.xml",
        ]

        async with aiohttp.ClientSession() as session:
            for sitemap_url in sitemap_locations:
                content = await self._fetch(sitemap_url, session)
                if not content:
                    continue

                sitemaps_found.append(sitemap_url)
                urls.extend(self._parse_sitemap_urls(content))

                if len(urls) >= max_urls:
                    break

        return {"urls": urls[:max_urls], "sitemaps": sitemaps_found}

    async def _discover_robots(self, domain: str) -> Dict[str, Any]:
        """robots.txt parsing (FREE)."""
        urls = []
        sitemaps = []

        async with aiohttp.ClientSession() as session:
            content = await self._fetch(f"https://{domain}/robots.txt", session)
            if not content:
                return {"urls": [], "sitemaps": []}

            for line in content.split('\n'):
                line = line.strip()
                if line.lower().startswith('sitemap:'):
                    sitemaps.append(line.split(':', 1)[1].strip())
                elif line.lower().startswith('allow:'):
                    path = line.split(':', 1)[1].strip()
                    if path and not path.startswith('*'):
                        urls.append(f"https://{domain}{path}")

        return {"urls": urls, "sitemaps": sitemaps}

    async def _discover_subdomains_crtsh(self, domain: str) -> Dict[str, Any]:
        """crt.sh Certificate Transparency (FREE)."""
        subdomains = set()
        url = f"https://crt.sh/?q=%.{domain}&output=json"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=self.timeout) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for entry in data:
                            name = entry.get("name_value", "")
                            for sub in name.split('\n'):
                                sub = sub.strip().lower().lstrip('*.')
                                if sub.endswith(domain):
                                    subdomains.add(sub)
            except Exception:
                pass

        urls = [f"https://{sub}" for sub in subdomains]
        return {"urls": urls, "subdomains": list(subdomains)}

    async def _discover_subdomains_sublist3r(self, domain: str) -> Dict[str, Any]:
        """
        Sublist3r Multi-Source Subdomain Enumeration (FREE).

        Aggregates from 10+ sources:
        - Google, Bing, Yahoo, Baidu, Ask
        - Netcraft, Virustotal, ThreatCrowd
        - DNSdumpster, ReverseDNS

        Requires: pip install sublist3r
        """
        subdomains = set()

        try:
            # Try to import Sublist3r
            try:
                import sublist3r
            except ImportError:
                # Not installed - silently skip
                return {"urls": [], "subdomains": []}

            # Run Sublist3r in executor (it's blocking/synchronous)
            loop = asyncio.get_event_loop()

            def run_sublist3r():
                import sys
                import os
                # Suppress Sublist3r's multiprocessing stderr noise
                old_stderr = sys.stderr
                sys.stderr = open(os.devnull, 'w')
                try:
                    return sublist3r.main(
                        domain,
                        40,  # threads
                        savefile=None,
                        ports=None,
                        silent=True,  # suppress console output
                        verbose=False,
                        enable_bruteforce=False,  # no DNS bruteforce
                        engines=None  # use all available engines
                    )
                finally:
                    sys.stderr.close()
                    sys.stderr = old_stderr

            results = await loop.run_in_executor(None, run_sublist3r)

            if results:
                for subdomain in results:
                    # CRITICAL: Validate subdomain belongs to target domain
                    subdomain_lower = subdomain.lower()
                    if subdomain_lower == domain or subdomain_lower.endswith(f'.{domain}'):
                        subdomains.add(subdomain_lower)

        except Exception:
            # Fail silently - Sublist3r is optional
            pass

        urls = [f"https://{sub}" for sub in subdomains]
        return {"urls": urls, "subdomains": list(subdomains)}

    async def _discover_wayback(self, domain: str, max_urls: int) -> Dict[str, Any]:
        """Wayback Machine CDX API (FREE)."""
        urls = set()
        cdx_url = (
            f"https://web.archive.org/cdx/search/cdx"
            f"?url={domain}/*&output=json&fl=original&collapse=urlkey&limit={max_urls}"
        )

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(cdx_url, timeout=self.timeout) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for row in data[1:]:  # Skip header
                            if row:
                                urls.add(row[0])
            except Exception:
                pass

        return {"urls": list(urls)[:max_urls]}

    async def _discover_commoncrawl(self, domain: str, max_urls: int) -> Dict[str, Any]:
        """Common Crawl CDX API (FREE)."""
        urls = set()
        cc_index = "CC-MAIN-2025-47"
        cdx_url = f"https://index.commoncrawl.org/{cc_index}-index?url={domain}/*&output=json&limit={max_urls}"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(cdx_url, timeout=self.timeout) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        for line in text.strip().split('\n'):
                            if line:
                                try:
                                    record = json.loads(line)
                                    urls.add(record.get("url", ""))
                                except json.JSONDecodeError:
                                    continue
            except Exception:
                pass

        return {"urls": list(urls)[:max_urls]}

    async def _discover_cc_graph_backlinks(self, domain: str, max_urls: int) -> Dict[str, Any]:
        """CC Web Graph backlinks (FREE - 157M domains, 2.1B edges)."""
        backlink_domains = []

        if self.linklater:
            try:
                records = await self.linklater.cc_graph.get_backlinks(domain, max_urls)
                for record in records:
                    if hasattr(record, 'source'):
                        parsed = urlparse(record.source if record.source.startswith('http') else f"http://{record.source}")
                        backlink_domains.append(parsed.netloc or record.source)
            except Exception:
                pass

        urls = [f"https://{d}" for d in set(backlink_domains)]
        return {"urls": urls[:max_urls], "backlink_domains": list(set(backlink_domains))}

    async def _discover_cc_graph_outlinks(self, domain: str, max_urls: int) -> Dict[str, Any]:
        """CC Web Graph outlinks (FREE)."""
        outlink_domains = []

        if self.linklater:
            try:
                records = await self.linklater.cc_graph.get_outlinks(domain, max_urls)
                for record in records:
                    if hasattr(record, 'target'):
                        parsed = urlparse(record.target if record.target.startswith('http') else f"http://{record.target}")
                        outlink_domains.append(parsed.netloc or record.target)
            except Exception:
                pass

        urls = [f"https://{d}" for d in set(outlink_domains)]
        return {"urls": urls[:max_urls], "outlink_domains": list(set(outlink_domains))}

    async def _discover_globallinks_backlinks(self, domain: str, max_urls: int) -> Dict[str, Any]:
        """GlobalLinks Go binary backlinks (FREE - requires pre-extracted data).

        Note: Requires data/links/ directory with pre-extracted link data.
        If no data exists, returns empty (graceful degradation).
        """
        backlink_domains = []

        if self.globallinks and self.globallinks.outlinker:
            try:
                records = await self.globallinks.get_backlinks(domain, max_urls)
                for record in records:
                    if hasattr(record, 'source') and record.source:
                        # Skip non-URL data
                        if not record.source.startswith('http') and '.' not in record.source:
                            continue
                        src = record.source if record.source.startswith('http') else f"http://{record.source}"
                        parsed = urlparse(src)
                        if parsed.netloc:
                            backlink_domains.append(parsed.netloc)
            except Exception as e:
                print(f"[GlobalLinks backlinks] {e}")

        urls = [f"https://{d}" for d in set(backlink_domains) if d]
        return {"urls": urls[:max_urls], "backlink_domains": list(set(backlink_domains))}

    async def _discover_globallinks_outlinks(self, domain: str, max_urls: int) -> Dict[str, Any]:
        """GlobalLinks Go binary outlinks (FREE - real-time CC extraction).

        Note: Extracts outlinks from Common Crawl WAT files.
        May take longer as it queries CC directly.
        """
        outlink_domains = []

        if self.globallinks and self.globallinks.outlinker:
            try:
                records = await self.globallinks.get_outlinks(domain, max_urls)
                for record in records:
                    if hasattr(record, 'target') and record.target:
                        # Skip non-URL data
                        if not record.target.startswith('http') and '.' not in record.target:
                            continue
                        tgt = record.target if record.target.startswith('http') else f"http://{record.target}"
                        parsed = urlparse(tgt)
                        if parsed.netloc:
                            outlink_domains.append(parsed.netloc)
            except Exception as e:
                print(f"[GlobalLinks outlinks] {e}")

        urls = [f"https://{d}" for d in set(outlink_domains) if d]
        return {"urls": urls[:max_urls], "outlink_domains": list(set(outlink_domains))}

    # ========================================================================
    # PAID SOURCES (only used if free_only=False)
    # ========================================================================

    async def _discover_majestic_backlinks(self, domain: str, max_urls: int) -> Dict[str, Any]:
        """Majestic backlinks (PAID - requires MAJESTIC_API_KEY)."""
        backlink_domains = []
        urls = []

        if self.linklater:
            try:
                records = await self.linklater.get_majestic_backlinks(
                    domain,
                    mode="fresh",
                    result_type="pages",
                    max_results=max_urls
                )
                for record in records:
                    source_url = record.get('source_url', '')
                    source_domain = record.get('source_domain', '')

                    if source_url:
                        urls.append(source_url)
                    if source_domain:
                        backlink_domains.append(source_domain)
            except Exception:
                pass

        return {"urls": urls[:max_urls], "backlink_domains": list(set(backlink_domains))}

    # ========================================================================
    # TARGETED DISCOVERY (GlobalLinks Advanced Features)
    # ========================================================================

    async def discover_country_links(
        self,
        domain: str,
        country_tlds: List[str],
        archive: str = "CC-MAIN-2024-10",
        max_results: int = 1000,
    ) -> Dict[str, Any]:
        """
        Find all outlinks from domain to specific country TLDs.

        Use cases:
        - Find Russian connections: country_tlds=[".ru", ".su"]
        - Find UK government links: country_tlds=[".gov.uk", ".uk"]
        - Find offshore jurisdictions: country_tlds=[".ky", ".bvi", ".pa", ".vg"]

        Args:
            domain: Source domain to analyze
            country_tlds: List of country TLDs to filter for
            archive: CC archive to search
            max_results: Max links to return

        Returns:
            Dict with links grouped by country TLD
        """
        if not self.globallinks or not self.globallinks.outlinker:
            return {"error": "GlobalLinks not available", "links": []}

        try:
            records = await self.globallinks.extract_outlinks(
                domains=[domain],
                archive=archive,
                country_tlds=country_tlds,
                max_results=max_results,
            )

            # Group by TLD
            by_tld: Dict[str, List[Dict]] = {tld: [] for tld in country_tlds}
            for record in records:
                target = record.target if hasattr(record, 'target') else ""
                for tld in country_tlds:
                    if target.endswith(tld) or f"{tld}/" in target:
                        by_tld[tld].append({
                            "source": record.source if hasattr(record, 'source') else domain,
                            "target": target,
                            "anchor": record.anchor_text if hasattr(record, 'anchor_text') else None,
                        })
                        break

            return {
                "domain": domain,
                "archive": archive,
                "country_tlds": country_tlds,
                "total_links": len(records),
                "by_tld": by_tld,
                "links": [
                    {
                        "source": r.source if hasattr(r, 'source') else domain,
                        "target": r.target if hasattr(r, 'target') else "",
                        "anchor": r.anchor_text if hasattr(r, 'anchor_text') else None,
                    }
                    for r in records
                ],
            }
        except Exception as e:
            return {"error": str(e), "links": []}

    async def discover_keyword_links(
        self,
        domain: str,
        keywords: List[str],
        exclude_keywords: Optional[List[str]] = None,
        archive: str = "CC-MAIN-2024-10",
        max_results: int = 1000,
    ) -> Dict[str, Any]:
        """
        Find outlinks containing specific keywords in URL or anchor text.

        Use cases:
        - Find contract/agreement links: keywords=["contract", "agreement", "tender"]
        - Find financial links: keywords=["annual-report", "financial", "investor"]
        - Find legal links: keywords=["lawsuit", "court", "litigation", "judgment"]

        Args:
            domain: Source domain to analyze
            keywords: Keywords to search for in URLs
            exclude_keywords: Keywords to exclude (e.g., ["facebook", "twitter"])
            archive: CC archive to search
            max_results: Max links to return

        Returns:
            Dict with links grouped by keyword
        """
        if not self.globallinks or not self.globallinks.outlinker:
            return {"error": "GlobalLinks not available", "links": []}

        try:
            records = await self.globallinks.extract_outlinks(
                domains=[domain],
                archive=archive,
                url_keywords=keywords,
                exclude_keywords=exclude_keywords,
                max_results=max_results,
            )

            # Group by keyword
            by_keyword: Dict[str, List[Dict]] = {kw: [] for kw in keywords}
            for record in records:
                target = (record.target if hasattr(record, 'target') else "").lower()
                anchor = (record.anchor_text if hasattr(record, 'anchor_text') else "") or ""
                for kw in keywords:
                    if kw.lower() in target or kw.lower() in anchor.lower():
                        by_keyword[kw].append({
                            "source": record.source if hasattr(record, 'source') else domain,
                            "target": record.target if hasattr(record, 'target') else "",
                            "anchor": anchor,
                        })
                        break

            return {
                "domain": domain,
                "archive": archive,
                "keywords": keywords,
                "excluded": exclude_keywords or [],
                "total_links": len(records),
                "by_keyword": by_keyword,
                "links": [
                    {
                        "source": r.source if hasattr(r, 'source') else domain,
                        "target": r.target if hasattr(r, 'target') else "",
                        "anchor": r.anchor_text if hasattr(r, 'anchor_text') else None,
                    }
                    for r in records
                ],
            }
        except Exception as e:
            return {"error": str(e), "links": []}

    async def discover_investigation_links(
        self,
        domain: str,
        investigation_type: str = "corporate",
        archive: str = "CC-MAIN-2024-10",
        max_results: int = 1000,
    ) -> Dict[str, Any]:
        """
        Pre-configured discovery patterns for common investigation types.

        Investigation types:
        - "corporate": Company registries, filings, annual reports
        - "offshore": Offshore jurisdictions and shell company indicators
        - "government": Government and regulatory links
        - "media": News and media coverage
        - "legal": Court records, lawsuits, judgments
        - "financial": Banks, exchanges, financial institutions
        - "sanctions": Sanctions lists, watchlists

        Args:
            domain: Source domain to analyze
            investigation_type: Type of investigation
            archive: CC archive to search
            max_results: Max links to return

        Returns:
            Dict with categorized links
        """
        # Pre-configured patterns for different investigation types
        PATTERNS = {
            "corporate": {
                "country_tlds": [],
                "keywords": [
                    "company-register", "companies-house", "annual-report",
                    "corporate-registry", "business-register", "handelsregister",
                    "registro-mercantil", "infogreffe", "opencorporates",
                ],
                "exclude": ["facebook", "twitter", "linkedin", "youtube"],
            },
            "offshore": {
                "country_tlds": [".ky", ".vg", ".bvi", ".pa", ".bs", ".je", ".gg", ".im", ".lu", ".li", ".mc"],
                "keywords": [
                    "offshore", "nominee", "bearer", "trust", "foundation",
                    "registered-agent", "corporate-services",
                ],
                "exclude": [],
            },
            "government": {
                "country_tlds": [".gov", ".gov.uk", ".gouv.fr", ".gob", ".govt"],
                "keywords": [
                    "ministry", "department", "agency", "commission",
                    "regulator", "authority", "procurement", "tender",
                ],
                "exclude": [],
            },
            "media": {
                "country_tlds": [],
                "keywords": [
                    "news", "article", "story", "report", "investigation",
                    "reuters", "bloomberg", "guardian", "times", "post",
                ],
                "exclude": ["facebook", "twitter"],
            },
            "legal": {
                "country_tlds": [],
                "keywords": [
                    "court", "lawsuit", "litigation", "judgment", "case",
                    "plaintiff", "defendant", "docket", "pacer", "legal",
                ],
                "exclude": [],
            },
            "financial": {
                "country_tlds": [],
                "keywords": [
                    "bank", "exchange", "securities", "investment", "fund",
                    "capital", "trading", "broker", "finra", "sec.gov",
                ],
                "exclude": [],
            },
            "sanctions": {
                "country_tlds": [],
                "keywords": [
                    "sanction", "ofac", "sdn", "watchlist", "blacklist",
                    "designated", "restricted", "embargo", "treasury.gov",
                ],
                "exclude": [],
            },
        }

        if investigation_type not in PATTERNS:
            return {
                "error": f"Unknown investigation type: {investigation_type}",
                "available_types": list(PATTERNS.keys()),
            }

        pattern = PATTERNS[investigation_type]
        results = {"domain": domain, "investigation_type": investigation_type, "links": []}

        # Run country TLD search if configured
        if pattern["country_tlds"]:
            country_results = await self.discover_country_links(
                domain=domain,
                country_tlds=pattern["country_tlds"],
                archive=archive,
                max_results=max_results // 2,
            )
            results["country_links"] = country_results.get("links", [])
            results["by_tld"] = country_results.get("by_tld", {})

        # Run keyword search if configured
        if pattern["keywords"]:
            keyword_results = await self.discover_keyword_links(
                domain=domain,
                keywords=pattern["keywords"],
                exclude_keywords=pattern["exclude"],
                archive=archive,
                max_results=max_results // 2,
            )
            results["keyword_links"] = keyword_results.get("links", [])
            results["by_keyword"] = keyword_results.get("by_keyword", {})

        # Combine all links
        all_links = results.get("country_links", []) + results.get("keyword_links", [])
        results["total_links"] = len(all_links)
        results["links"] = all_links

        return results

    async def discover_multi_domain_links(
        self,
        domains: List[str],
        country_tlds: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        archive: str = "CC-MAIN-2024-10",
        max_results: int = 500,
    ) -> Dict[str, Any]:
        """
        Batch analyze multiple domains for shared link patterns.

        Use case: Find common connections between related entities.
        E.g., Do company A, B, and C all link to the same offshore jurisdiction?

        Args:
            domains: List of domains to analyze together
            country_tlds: Filter by country TLDs
            keywords: Filter by keywords
            archive: CC archive to search
            max_results: Max results per domain

        Returns:
            Dict with per-domain results and shared targets
        """
        if not self.globallinks or not self.globallinks.outlinker:
            return {"error": "GlobalLinks not available", "results": {}}

        try:
            records = await self.globallinks.extract_outlinks(
                domains=domains,
                archive=archive,
                country_tlds=country_tlds,
                url_keywords=keywords,
                max_results=max_results,
            )

            # Group by source domain
            by_domain: Dict[str, List[str]] = {d: [] for d in domains}
            all_targets: Dict[str, Set[str]] = {}  # target -> set of source domains

            for record in records:
                source = record.source if hasattr(record, 'source') else ""
                target = record.target if hasattr(record, 'target') else ""

                # Find which domain this belongs to
                for d in domains:
                    if d in source:
                        by_domain[d].append(target)

                        # Track shared targets
                        target_domain = urlparse(target).netloc if target.startswith('http') else target.split('/')[0]
                        if target_domain not in all_targets:
                            all_targets[target_domain] = set()
                        all_targets[target_domain].add(d)
                        break

            # Find shared targets (linked by 2+ source domains)
            shared = {
                target: list(sources)
                for target, sources in all_targets.items()
                if len(sources) > 1
            }

            return {
                "domains": domains,
                "archive": archive,
                "by_domain": {d: list(set(links)) for d, links in by_domain.items()},
                "shared_targets": shared,
                "total_shared": len(shared),
            }
        except Exception as e:
            return {"error": str(e), "results": {}}

    # ========================================================================
    # UTILITIES
    # ========================================================================

    async def _fetch(self, url: str, session: aiohttp.ClientSession) -> Optional[str]:
        """Fetch URL with rate limiting."""
        async with self.semaphore:
            try:
                async with session.get(url, timeout=self.timeout) as resp:
                    if resp.status == 200:
                        return await resp.text()
            except Exception:
                pass
        return None

    def _parse_sitemap_urls(self, xml_content: str) -> List[str]:
        """Parse URLs from sitemap XML."""
        urls = []
        try:
            root = ET.fromstring(xml_content)
            for loc in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc'):
                if loc.text:
                    urls.append(loc.text)
        except ET.ParseError:
            urls = re.findall(r'<loc>([^<]+)</loc>', xml_content)
        return urls

    def _seed_key(self, url: str) -> str:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        netloc = parsed.netloc or parsed.path.split("/")[0]
        path = parsed.path.rstrip("/")
        return f"{netloc}{path}"

    def _score_seed(
        self,
        url: str,
        source: str,
        prioritize_sitemaps: bool,
    ) -> SeedCandidate:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        path = parsed.path or "/"
        depth = len([segment for segment in path.split("/") if segment])

        score = DEFAULT_SOURCE_WEIGHTS.get(source, 40)
        reasons = [f"source:{source}"]

        if prioritize_sitemaps and source == "sitemap":
            score += 10
            reasons.append("sitemap_priority")

        if any(re.search(pattern, path, re.IGNORECASE) for pattern in HIGH_VALUE_PATTERNS):
            score += 20
            reasons.append("high_value_path")

        ext = os.path.splitext(path)[1].lower()
        if ext in DOCUMENT_EXTENSIONS:
            score += 15
            reasons.append("document")

        if depth <= 1:
            score += 5
            reasons.append("shallow_depth")
        elif depth > 3:
            penalty = (depth - 3) * 2
            score -= penalty
            reasons.append("deep_path_penalty")

        if parsed.query:
            score -= 5
            reasons.append("query_penalty")

        score = max(0, min(score, 100))
        lane = "archive" if source in ARCHIVE_SOURCES else ("sprint" if score >= 75 else "marathon")

        return SeedCandidate(
            url=url,
            source=source,
            score=score,
            lane=lane,
            reasons=reasons,
        )

    def get_ranked_seeds(
        self,
        discovery_result: DiscoveryResult,
        prioritize_sitemaps: bool = True,
        include_backlink_sources: bool = True,
        min_score: int = 0,
        max_seeds: Optional[int] = None,
    ) -> List[SeedCandidate]:
        """
        Rank discovered URLs into prioritized crawl seeds.

        Args:
            discovery_result: Result from discover()
            prioritize_sitemaps: Boost sitemap URLs
            include_backlink_sources: Include backlink/outlink-derived URLs
            min_score: Minimum score to keep
            max_seeds: Optional hard limit on returned seeds

        Returns:
            Ranked list of SeedCandidate entries
        """
        candidates: Dict[str, SeedCandidate] = {}

        backlink_sources = {
            "cc_graph_backlinks",
            "globallinks_backlinks",
            "cc_graph_outlinks",
            "globallinks_outlinks",
            "majestic",
        }

        for source, urls in discovery_result.urls_by_source.items():
            if not include_backlink_sources and source in backlink_sources:
                continue

            for url in urls:
                if not url:
                    continue
                key = self._seed_key(url)
                candidate = self._score_seed(url, source, prioritize_sitemaps)

                if candidate.score < min_score:
                    continue

                existing = candidates.get(key)
                if not existing or candidate.score > existing.score:
                    candidates[key] = candidate

        ranked = sorted(
            candidates.values(),
            key=lambda c: (c.score, c.source),
            reverse=True,
        )

        if max_seeds is not None:
            ranked = ranked[:max_seeds]

        return ranked

    def get_crawl_seeds(
        self,
        discovery_result: DiscoveryResult,
        prioritize_sitemaps: bool = True,
        include_backlink_sources: bool = True,
        min_score: int = 0,
        max_seeds: Optional[int] = None,
    ) -> List[str]:
        """
        Generate prioritized seed URLs for crawling.

        Args:
            discovery_result: Result from discover()
            prioritize_sitemaps: Put sitemap URLs first (Firecrawl pattern)
            include_backlink_sources: Include URLs from backlink domains
            min_score: Minimum score to include
            max_seeds: Optional hard limit on returned seeds

        Returns:
            Ordered list of unique URLs to crawl
        """
        ranked = self.get_ranked_seeds(
            discovery_result,
            prioritize_sitemaps=prioritize_sitemaps,
            include_backlink_sources=include_backlink_sources,
            min_score=min_score,
            max_seeds=max_seeds,
        )
        return [candidate.url for candidate in ranked]


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

async def discover_urls(domain: str, free_only: bool = True, **kwargs) -> DiscoveryResult:
    """Quick discovery using LinkLater's full capabilities."""
    discovery = DrillDiscovery(free_only=free_only)
    return await discovery.discover(domain, **kwargs)


async def discover_offshore_links(domain: str, archive: str = "CC-MAIN-2024-10") -> Dict[str, Any]:
    """
    Quick scan for offshore jurisdiction connections.

    Searches for links to: Cayman Islands, BVI, Panama, Bahamas,
    Jersey, Guernsey, Isle of Man, Luxembourg, Liechtenstein, Monaco.
    """
    discovery = DrillDiscovery()
    return await discovery.discover_investigation_links(
        domain=domain,
        investigation_type="offshore",
        archive=archive,
    )


async def discover_russian_links(domain: str, archive: str = "CC-MAIN-2024-10") -> Dict[str, Any]:
    """Quick scan for Russian/CIS connections."""
    discovery = DrillDiscovery()
    return await discovery.discover_country_links(
        domain=domain,
        country_tlds=[".ru", ".su", ".by", ".kz", ".ua"],
        archive=archive,
    )


async def discover_government_links(domain: str, archive: str = "CC-MAIN-2024-10") -> Dict[str, Any]:
    """Quick scan for government and regulatory connections."""
    discovery = DrillDiscovery()
    return await discovery.discover_investigation_links(
        domain=domain,
        investigation_type="government",
        archive=archive,
    )


async def discover_shared_connections(
    domains: List[str],
    archive: str = "CC-MAIN-2024-10"
) -> Dict[str, Any]:
    """
    Find shared link targets between multiple domains.

    Use case: "Do these 3 companies all link to the same offshore provider?"
    """
    discovery = DrillDiscovery()
    return await discovery.discover_multi_domain_links(
        domains=domains,
        archive=archive,
    )
