"""
LinkLater Backlinks Discovery - Core Python Implementation

Deterministic functions for backlink discovery with 4 query modes:
- ?bl !domain   → Referring domains only (FAST - 100ms)
- bl? !domain   → Referring pages with full enrichment (RICH - 30-60s)
- ?bl domain!   → Referring domains to specific URL
- bl? domain!   → Referring pages to specific URL with enrichment

This is the REAL implementation. MCP server just exposes the syntax.
"""

import asyncio
import aiohttp
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse

# Centralized logging
from ..config import get_logger
logger = get_logger(__name__)

# Relative imports within linkgraph package
from .cc_graph_es import CCGraphESClient
from .host_graph_es import HostGraphESClient
from .globallinks import GlobalLinksClient
from .tor_bridges import TorBridgesClient
from .cc_index_client import CCIndexClient
from .models import LinkRecord


class BacklinkDiscovery:
    """
    Core backlink discovery engine.

    Deterministic, testable, directly callable from Python or MCP.
    """

    def __init__(self, archive: str = "CC-MAIN-2024-10"):
        """Initialize all clients."""
        self.cc_graph = CCGraphESClient()
        self.host_graph = HostGraphESClient()  # 421M edges - INSTANT queries
        self.globallinks = GlobalLinksClient()
        self.tor_bridges = TorBridgesClient()
        self.cc_index = CCIndexClient(archive)  # Fast page URL lookups

    async def close(self):
        """Close all connections."""
        await self.cc_graph.close()
        await self.host_graph.close()

    # =========================================================================
    # PAGE CONTENT FETCHING & LINK EXTRACTION
    # =========================================================================

    async def _fetch_page_content(self, session, url: str, filename: str, offset: int, length: int) -> str:
        """Fetch page content from Common Crawl WARC files."""
        import gzip
        cc_url = f"https://data.commoncrawl.org/{filename}"
        headers = {'Range': f'bytes={offset}-{offset+length-1}'}

        try:
            async with session.get(cc_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status in (200, 206):
                    raw = await response.read()
                    # Decompress if gzipped
                    try:
                        content = gzip.decompress(raw).decode('utf-8', errors='ignore')
                    except Exception as e:
                        content = raw.decode('utf-8', errors='ignore')

                    # WARC format: headers, then HTML
                    parts = content.split('\r\n\r\n', 2)
                    if len(parts) >= 3:
                        return parts[2]
                    elif len(parts) >= 2:
                        return parts[1]
                    return content
        except Exception as e:
            pass
        return ""

    def _extract_links_to_target(self, html: str, target_domain: str) -> List[Dict]:
        """Extract links pointing to target domain from HTML."""
        from bs4 import BeautifulSoup
        try:
            soup = BeautifulSoup(html, 'html.parser')
            links = []
            for a in soup.find_all('a', href=True):
                href = a.get('href', '')
                if target_domain in href:
                    links.append({
                        'url': href,
                        'anchor_text': a.get_text(strip=True)[:200]
                    })
            return links
        except Exception as e:
            return []

    async def _fetch_and_extract_links_direct(
        self,
        pages: List,
        target_domain: str,
        max_concurrent: int = 30
    ) -> List[Dict]:
        """
        Fetch page content DIRECTLY from CC WARC and extract links to target domain.

        FAST: Direct Range requests to data.commoncrawl.org without scraper overhead.

        Args:
            pages: List of PageRecord objects from CC Index (have filename, offset, length)
            target_domain: Domain to find links TO
            max_concurrent: Max concurrent fetches

        Returns:
            List of dicts with source, target, anchor_text
        """
        import gzip

        results = []
        semaphore = asyncio.Semaphore(max_concurrent)

        async def fetch_and_check(session, page) -> Optional[Dict]:
            """Fetch single page and check for target links."""
            async with semaphore:
                try:
                    cc_url = f"https://data.commoncrawl.org/{page.filename}"
                    headers = {'Range': f'bytes={page.offset}-{page.offset + page.length - 1}'}

                    async with session.get(cc_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status not in (200, 206):
                            return None

                        raw = await resp.read()

                        # Decompress if gzipped
                        try:
                            content = gzip.decompress(raw).decode('utf-8', errors='ignore')
                        except Exception as e:
                            content = raw.decode('utf-8', errors='ignore')

                        # WARC format: headers, then HTML
                        parts = content.split('\r\n\r\n', 2)
                        html = parts[2] if len(parts) >= 3 else (parts[1] if len(parts) >= 2 else content)

                        # Check for target domain links
                        links = self._extract_links_to_target(html, target_domain)
                        if links:
                            return {
                                'page_url': page.url,
                                'links': links
                            }
                except Exception:
                    pass
                return None

        async with aiohttp.ClientSession() as session:
            tasks = [fetch_and_check(session, p) for p in pages]
            fetched = await asyncio.gather(*tasks, return_exceptions=True)

            for result in fetched:
                if isinstance(result, dict) and result:
                    for link in result['links']:
                        results.append({
                            'source': result['page_url'],
                            'target': link['url'],
                            'anchor_text': link.get('anchor_text'),
                            'provider': 'cc_content'
                        })

        logger.info(f"Extracted {len(results)} links from {len(pages)} pages scanned")
        return results

    async def _fetch_wat_and_extract_links(
        self,
        records: List,
        target_domain: str,
        max_concurrent: int = 30
    ) -> List[Dict]:
        """
        Fetch WAT content using exact byte offsets and extract links to target.

        TARGETED: Uses CC Index records with exact file locations.
        Much faster than downloading entire WAT files.

        Args:
            records: List of CCIndexRecord objects from archives client
            target_domain: Domain to find links TO
            max_concurrent: Max concurrent fetches

        Returns:
            List of dicts with source, target, anchor_text
        """
        import gzip
        import json
        import re

        results = []
        semaphore = asyncio.Semaphore(max_concurrent)
        processed = 0

        async def fetch_and_check(session, record) -> List[Dict]:
            """Fetch WAT record and check for target links."""
            nonlocal processed
            async with semaphore:
                try:
                    # Get WAT file URL and offset
                    wat_url = record.get_wat_url()
                    offset = record.offset
                    length = record.length

                    # Fetch specific byte range
                    headers = {'Range': f'bytes={offset}-{offset + length - 1}'}

                    async with session.get(wat_url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                        if resp.status not in (200, 206):
                            return []

                        raw = await resp.read()

                        # Decompress if gzipped
                        try:
                            content = gzip.decompress(raw).decode('utf-8', errors='ignore')
                        except Exception as e:
                            content = raw.decode('utf-8', errors='ignore')

                        # Parse WAT JSON to extract links
                        links_found = []

                        # Find JSON content in WAT record
                        json_start = content.find('{')
                        if json_start != -1:
                            json_str = content[json_start:]
                            json_end = json_str.rfind('}')
                            if json_end != -1:
                                json_str = json_str[:json_end+1]

                                try:
                                    data = json.loads(json_str)
                                    envelope = data.get('Envelope', {})
                                    payload = envelope.get('Payload-Metadata', {})
                                    http_resp = payload.get('HTTP-Response-Metadata', {})
                                    html_meta = http_resp.get('HTML-Metadata', {})
                                    links = html_meta.get('Links', [])

                                    # Check each link for target domain
                                    for link in links:
                                        if isinstance(link, dict):
                                            href = link.get('url', link.get('href', ''))
                                            if target_domain.lower() in href.lower():
                                                links_found.append({
                                                    'source': record.url,
                                                    'target': href,
                                                    'anchor_text': link.get('text', '')[:200],
                                                    'provider': 'cc_wat'
                                                })
                                except json.JSONDecodeError:
                                    pass

                        processed += 1
                        if processed % 50 == 0:
                            logger.debug(f"Processed {processed} WAT records...")

                        return links_found

                except Exception as e:
                    return []

        async with aiohttp.ClientSession() as session:
            tasks = [fetch_and_check(session, r) for r in records[:500]]  # Limit to 500
            fetched = await asyncio.gather(*tasks, return_exceptions=True)

            for result in fetched:
                if isinstance(result, list):
                    results.extend(result)

        logger.info(f"Extracted {len(results)} links from {processed} WAT records")
        return results

    async def _fetch_links_offline_sniper(
        self,
        target_domain: str,
        source_domains: List[str],
        archive: str
    ) -> List[Dict]:
        """
        Fetch backlinks using the Offline Sniper mechanism (Python Lookup + Go Extraction).
        """
        import json
        import os
        import subprocess
        import tempfile
        from ..scraping.web.cc_offline_sniper import CCIndexOfflineLookup

        results = []
        
        # 1. Use Offline Lookup to find WAT files for source domains
        logger.info(f"Running Offline Index Lookup for {len(source_domains)} domains...")
        
        # We can run this in a thread executor because it blocks on requests
        loop = asyncio.get_event_loop()
        
        def run_lookup():
            client = CCIndexOfflineLookup(archive)
            all_wat_files = []
            for source in source_domains:
                # Lookup limited to 50 files per domain to stay fast
                wats = client.lookup_domain(source, limit=50)
                if wats:
                    all_wat_files.extend(wats)
            return all_wat_files

        wat_locations = await loop.run_in_executor(None, run_lookup)
        
        if not wat_locations:
            logger.warning("No WAT files found for sources via Offline Index.")
            return []
            
        logger.info(f"Found {len(wat_locations)} potential source pages. Running Go binary...")

        # 2. Create temp file for WAT list
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as tmp:
            json.dump(wat_locations, tmp)
            tmp_path = tmp.name

        try:
            # 3. Run Go binary
            # Path to binary: BACKEND/modules/LINKLATER/drill/go/bin/outlinker
            binary_path = Path(__file__).parent.parent / "scraping" / "web" / "go" / "bin" / "outlinker"
            
            cmd = [
                str(binary_path),
                "sniper",
                f"--target-domain={target_domain}",
                f"--wat-list={tmp_path}",
                f"--archive={archive}",
                "--threads=8",
                "--output=stdout"  # Capture output directly
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if stderr:
                # Log stderr but don't fail, as it contains progress info
                # print(f"[BacklinkDiscovery] Go binary stderr: {stderr.decode()}")
                pass

            # Parse NDJSON output
            for line in stdout.decode().splitlines():
                if not line.strip(): continue
                try:
                    record = json.loads(line)
                    results.append({
                        'source': record.get('source_url', ''),
                        'target': record.get('target_url', ''),
                        'anchor_text': record.get('anchor_text', ''),
                        'provider': 'cc_wat_offline'
                    })
                except json.JSONDecodeError:
                    pass

        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        return results

    # =========================================================================
    # TARGET PARSING
    # =========================================================================

    def parse_target(self, target: str) -> Tuple[str, Optional[str], str]:
        """
        Parse target into (domain, path, target_type).

        Args:
            target: Either "domain.com" or "domain.com/path/to/page.html"

        Returns:
            Tuple of (domain, path_or_none, "domain" or "url")

        Examples:
            "soax.com" → ("soax.com", None, "domain")
            "soax.com/pricing" → ("soax.com", "/pricing", "url")
            "https://soax.com/pricing" → ("soax.com", "/pricing", "url")
        """
        # Remove protocol if present
        if target.startswith(('http://', 'https://')):
            parsed = urlparse(target)
            domain = parsed.netloc
            path = parsed.path if parsed.path and parsed.path != '/' else None
        else:
            # Split on first /
            parts = target.split('/', 1)
            domain = parts[0]
            path = '/' + parts[1] if len(parts) > 1 else None

        target_type = "url" if path else "domain"
        return domain, path, target_type

    # =========================================================================
    # MODE 1: ?bl !domain → REFERRING DOMAINS ONLY (FAST)
    # =========================================================================

    async def get_referring_domains(
        self,
        target: str,
        limit: int = 1000,
        min_weight: int = 1,
        include_majestic: bool = True,
        include_tor: bool = True
    ) -> Dict[str, Any]:
        """
        Get referring domains only (FAST - ~5s with Majestic, 100ms without).

        Uses CC Domain Graph ES + Majestic for domain-level backlinks.

        Args:
            target: Domain or URL
            limit: Max results
            min_weight: Minimum link weight
            include_majestic: Include Majestic domain data (adds ~5s)
            include_tor: Include Tor bridges

        Returns:
            Dict with:
            {
                "target": str,
                "target_type": "domain" or "url",
                "domains": List[Dict],  # Now includes Majestic TF/CF
                "summary": {
                    "total": int,
                    "sources": {"cc_graph": int, "majestic": int, "tor_bridges": int}
                },
                "execution_time_ms": float
            }
        """
        import time
        start = time.time()

        # Parse target
        domain, path, target_type = self.parse_target(target)

        logger.info(f"Querying Host Graph ES (421M edges) for {domain}...")

        # Query Host Graph ES (421M edges, subdomain-level) - INSTANT
        host_results = await self.host_graph.get_backlinks(
            domain=domain,
            limit=limit,
            include_subdomains=True
        )

        logger.info(f"Querying CC Domain Graph for {domain}...")

        # Query CC Graph ES (domain-level only) - as fallback/supplement
        cc_results = await self.cc_graph.get_backlinks(
            domain=domain,
            limit=limit,
            min_weight=min_weight
        )

        # Query Majestic (if enabled) - DOMAINS mode
        majestic_results = []
        if include_majestic:
            logger.info("Querying Majestic API (domains mode)...")
            try:
                from ..api import linklater
                majestic_data = await linklater.get_majestic_backlinks(
                    domain=domain,
                    result_type="domains",  # Domain-level, not pages
                    mode="historic",  # 5 years of data
                    max_results=limit
                )
                # Convert to domain records with TF/CF
                for item in majestic_data:
                    majestic_results.append({
                        "source": item.get("source_domain", ""),
                        "target": domain,
                        "trust_flow": item.get("trust_flow", 0),
                        "citation_flow": item.get("citation_flow", 0),
                        "provider": "majestic"
                    })
            except Exception as e:
                logger.warning(f"Majestic query failed: {e}")

        # Query Tor Bridges (if enabled)
        tor_results = []
        if include_tor:
            logger.info("Querying Tor Bridges...")
            try:
                tor_links = await self.tor_bridges.get_bridges_to_clearnet(
                    clearnet_domain=domain,
                    limit=100
                )
                tor_results = [
                    {
                        "source": urlparse(r.source).netloc if r.source.startswith('http') else r.source.split('/')[0],
                        "target": domain,
                        "provider": "tor_bridge"
                    }
                    for r in tor_links
                ]
            except Exception as e:
                logger.warning(f"Tor query failed: {e}")

        # Combine and deduplicate by source domain
        # Build domain map with enriched data
        domain_map = {}

        # Add Host Graph ES results (421M edges, primary source)
        for record in host_results:
            source_domain = urlparse(record.source).netloc if record.source.startswith('http') else record.source.split('/')[0]
            if source_domain not in domain_map:
                domain_map[source_domain] = {
                    "source": source_domain,
                    "target": domain,
                    "weight": record.weight,
                    "providers": ["host_graph_es"]
                }

        # Add CC Graph results
        for record in cc_results:
            source_domain = urlparse(record.source).netloc if record.source.startswith('http') else record.source.split('/')[0]
            if source_domain not in domain_map:
                domain_map[source_domain] = {
                    "source": source_domain,
                    "target": domain,
                    "weight": record.weight,
                    "providers": ["cc_graph"]
                }
            else:
                if "cc_graph" not in domain_map[source_domain]["providers"]:
                    domain_map[source_domain]["providers"].append("cc_graph")

        # Enrich with Majestic data
        for item in majestic_results:
            source_domain = item["source"]
            if source_domain in domain_map:
                domain_map[source_domain]["trust_flow"] = item.get("trust_flow", 0)
                domain_map[source_domain]["citation_flow"] = item.get("citation_flow", 0)
                domain_map[source_domain]["providers"].append("majestic")
            else:
                domain_map[source_domain] = {
                    "source": source_domain,
                    "target": domain,
                    "trust_flow": item.get("trust_flow", 0),
                    "citation_flow": item.get("citation_flow", 0),
                    "providers": ["majestic"]
                }

        # Add Tor results
        for item in tor_results:
            source_domain = item["source"]
            if source_domain in domain_map:
                domain_map[source_domain]["providers"].append("tor_bridge")
            else:
                domain_map[source_domain] = {
                    "source": source_domain,
                    "target": domain,
                    "providers": ["tor_bridge"]
                }

        # Convert to list and sort by TF/CF if available, otherwise by weight
        unique = list(domain_map.values())
        unique.sort(key=lambda x: (
            (x.get("trust_flow") or 0) + (x.get("citation_flow") or 0),
            x.get("weight") or 0
        ), reverse=True)

        execution_time = (time.time() - start) * 1000

        return {
            "target": target,
            "target_type": target_type,
            "domains": unique[:limit],
            "summary": {
                "total": len(unique[:limit]),
                "sources": {
                    "host_graph_es": len(host_results),  # 421M edges, primary
                    "cc_graph": len(cc_results),
                    "majestic": len(majestic_results),
                    "tor_bridges": len(tor_results)
                }
            },
            "execution_time_ms": round(execution_time, 2)
        }

    # =========================================================================
    # MODE 2: bl? !domain → REFERRING PAGES WITH FULL ENRICHMENT (RICH)
    # =========================================================================

    async def get_referring_pages(
        self,
        target: str,
        limit: int = 100,
        top_domains: int = 20,
        include_majestic: bool = True,
        include_anchor_text: bool = True,
        include_tor: bool = True,
        archive: str = "CC-MAIN-2024-10"
    ) -> Dict[str, Any]:
        """
        Get referring pages with full enrichment (RICH - ~30-60s).

        Pipeline:
        1. CC Domain Graph ES → Get referring domains (100ms)
        2. Sort by weight, take top N domains
        3. GlobalLinks → Extract page URLs + anchor text (5-30s per domain)
        4. Majestic API → Add Trust/Citation Flow + fresh backlinks (5s)
        5. Tor Bridges → Add dark web sources (100ms)

        Args:
            target: Domain or URL
            limit: Max total results
            top_domains: How many top domains to enrich with GlobalLinks
            include_majestic: Add Majestic data (requires API key)
            include_anchor_text: Extract anchor text
            include_tor: Include Tor bridges
            archive: Common Crawl archive for GlobalLinks

        Returns:
            Dict with:
            {
                "target": str,
                "target_type": "domain" or "url",
                "pages": List[Dict],  # Full page data with anchor text
                "summary": {
                    "total": int,
                    "sources": {
                        "cc_graph": int,
                        "globallinks": int,
                        "majestic": int,
                        "tor_bridges": int
                    }
                },
                "execution_time_ms": float
            }
        """
        import time
        start = time.time()

        # Parse target
        domain, path, target_type = self.parse_target(target)

        # STEP 1: Fast host discovery (Host Graph ES - 421M edges)
        logger.info(f"Querying Host Graph ES (421M edges) for {domain}...")
        host_results = await self.host_graph.get_backlinks(
            domain=domain,
            limit=1000,
            include_subdomains=True
        )

        # STEP 1b: Also query CC Domain Graph
        logger.info(f"Querying CC Domain Graph for {domain}...")
        cc_results = await self.cc_graph.get_backlinks(
            domain=domain,
            limit=1000
        )

        # Combine results (host_results are primary)
        all_cc_results = host_results + cc_results

        # STEP 2: Sort by weight and take top N
        sorted_domains = sorted(
            all_cc_results,
            key=lambda x: x.weight or 0,
            reverse=True
        )
        top_n = [r.source for r in sorted_domains[:top_domains]]

        # STEP 3: Use the FAST CC Index mechanism (Priority: API -> Offline Fallback)
        # This queries CC Index API to find which WAT files contain pages from referring domains,
        # then downloads only those specific WAT files (not all 900 per segment)
        gl_results = []

        # Extract domain names from LinkRecord sources
        source_domains = []
        for r in sorted_domains[:top_domains]:
            src = r.source
            if src.startswith('http'):
                src = urlparse(src).netloc
            else:
                src = src.split('/')[0]
            if src and src != domain:
                source_domains.append(src.lower())

        source_domains = list(set(source_domains))  # Deduplicate

        if source_domains:
            logger.info(f"Trying CC Index API for {len(source_domains)} source domains...")
            try:
                from .cc_index_backlinks import get_backlinks_targeted

                # Priority 1: Official API
                backlink_records = await get_backlinks_targeted(
                    target_domain=domain,
                    source_domains=source_domains,
                    archive=archive,
                    max_pages_per_source=50,
                    max_wat_files_per_source=2,
                    max_results=limit
                )

                # Convert BacklinkRecord objects to expected dict format
                for r in backlink_records:
                    gl_results.append({
                        'source': r.source_url,
                        'target': r.target_url,
                        'anchor_text': r.anchor_text,
                        'provider': 'cc_wat'
                    })

                logger.info(f"CC Index API found {len(gl_results)} backlinks with anchor text")

                # If CC Index returned 0 results (likely down or no data), treat as failure to trigger fallback
                # UNLESS we are sure it's not down. But safely, if 0 results, trying offline won't hurt.
                if len(gl_results) == 0:
                    raise Exception("CC Index API returned 0 results - triggering fallback")

            except Exception as e:
                logger.warning(f"CC Index API unavailable/empty: {e}")
                logger.info("Switching to OFFLINE SNIPER mechanism...")

                # FALLBACK: Use Offline Sniper (Python Index Lookup + Go Binary)
                try:
                    gl_results = await self._fetch_links_offline_sniper(
                        target_domain=domain,
                        source_domains=source_domains,
                        archive=archive
                    )
                    logger.info(f"Offline Sniper found {len(gl_results)} backlinks")

                except Exception as e2:
                    logger.warning(f"Offline Sniper also failed: {e2}")
                    logger.info("Falling back to Majestic-only mode")

        # STEP 4: Majestic enrichment (optional)
        majestic_results = []
        if include_majestic:
            logger.info("Querying Majestic API...")
            try:
                from ..api import linklater
                majestic_data = await linklater.get_majestic_backlinks(
                    domain=domain,
                    result_type="pages",
                    mode="historic",  # 5 years of data
                    max_results=limit
                )
                # Convert to LinkRecord format
                for item in majestic_data:
                    majestic_results.append({
                        "source": item.get("source_url", ""),
                        "target": item.get("target_url", target),
                        "anchor_text": item.get("anchor_text"),
                        "trust_flow": item.get("trust_flow", 0),
                        "citation_flow": item.get("citation_flow", 0),
                        "provider": "majestic"
                    })
            except Exception as e:
                logger.warning(f"Majestic query failed: {e}")

        # STEP 5: Tor Bridges (optional)
        tor_results = []
        if include_tor:
            logger.info("Querying Tor Bridges...")
            try:
                tor_links = await self.tor_bridges.get_bridges_to_clearnet(
                    clearnet_domain=domain,
                    limit=100
                )
                tor_results = [
                    {
                        "source": r.source,
                        "target": r.target,
                        "anchor_text": r.anchor_text,
                        "provider": "tor_bridge"
                    }
                    for r in tor_links
                ]
            except Exception as e:
                logger.warning(f"Tor query failed: {e}")

        # STEP 6: Combine and format results
        all_pages = []

        # Add CC Content results (pages that ACTUALLY link to target)
        for record in gl_results:
            all_pages.append({
                "source": record['source'],
                "target": record['target'],
                "anchor_text": record.get('anchor_text') if include_anchor_text else None,
                "provider": "cc_content"
            })

        # Add Majestic results
        all_pages.extend(majestic_results)

        # Add Tor results
        all_pages.extend(tor_results)

        # Deduplicate by source URL
        seen = set()
        unique_pages = []
        for page in all_pages:
            if page["source"] not in seen:
                seen.add(page["source"])
                unique_pages.append(page)

        execution_time = (time.time() - start) * 1000

        return {
            "target": target,
            "target_type": target_type,
            "pages": unique_pages[:limit],
            "summary": {
                "total": len(unique_pages[:limit]),
                "sources": {
                    "host_graph_es": len(host_results),  # 421M edges, primary
                    "cc_graph": len(cc_results),
                    "cc_backlinks": len(gl_results),  # Backlinks found via CC Index
                    "majestic": len(majestic_results),
                    "tor_bridges": len(tor_results)
                }
            },
            "execution_time_ms": round(execution_time, 2)
        }

    # =========================================================================
    # CONVENIENCE METHODS (SYNTAX SUGAR)
    # =========================================================================

    async def query(
        self,
        syntax: str,
        target: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Unified query method using syntax strings.

        Args:
            syntax: One of "?bl", "bl?"
            target: Target with suffix "!domain" or "domain!"
            **kwargs: Additional parameters

        Returns:
            Query results

        Examples:
            await query("?bl", "!soax.com")        # Domains only
            await query("bl?", "!soax.com")        # Pages with enrichment
            await query("?bl", "soax.com/pricing!") # Domains to specific URL
            await query("bl?", "soax.com/pricing!") # Pages to specific URL
        """
        # Parse syntax
        if syntax not in ("?bl", "bl?"):
            raise ValueError(f"Invalid syntax: {syntax}. Must be '?bl' or 'bl?'")

        # Parse target suffix
        if target.startswith("!"):
            target = target[1:]  # Remove ! prefix
        elif target.endswith("!"):
            target = target[:-1]  # Remove ! suffix

        # Route to appropriate method
        if syntax == "?bl":
            return await self.get_referring_domains(target, **kwargs)
        else:  # bl?
            return await self.get_referring_pages(target, **kwargs)


# =============================================================================
# STANDALONE FUNCTIONS (FOR DIRECT PYTHON USAGE)
# =============================================================================

async def get_backlinks_domains(target: str, **kwargs) -> Dict[str, Any]:
    """
    Standalone: Get referring domains only (FAST).

    Syntax: ?bl !domain or ?bl domain!

    Example:
        result = await get_backlinks_domains("soax.com")
        print(f"Found {result['summary']['total']} referring domains")
    """
    discovery = BacklinkDiscovery()
    try:
        return await discovery.get_referring_domains(target, **kwargs)
    finally:
        await discovery.close()


async def get_backlinks_pages(target: str, **kwargs) -> Dict[str, Any]:
    """
    Standalone: Get referring pages with full enrichment (RICH).

    Syntax: bl? !domain or bl? domain!

    Example:
        result = await get_backlinks_pages("soax.com", top_domains=20)
        for page in result['pages']:
            print(f"{page['source']} → {page['anchor_text']}")
    """
    discovery = BacklinkDiscovery()
    try:
        return await discovery.get_referring_pages(target, **kwargs)
    finally:
        await discovery.close()


async def backlinks(syntax: str, target: str, **kwargs) -> Dict[str, Any]:
    """
    Unified backlinks function with syntax support.

    Args:
        syntax: "?bl" (domains) or "bl?" (pages)
        target: "!domain" or "domain!"
        **kwargs: Additional parameters

    Examples:
        # Domains only (FAST)
        result = await backlinks("?bl", "!soax.com")

        # Pages with enrichment (RICH)
        result = await backlinks("bl?", "!soax.com", top_domains=20)

        # Specific URL
        result = await backlinks("?bl", "soax.com/pricing!")
    """
    discovery = BacklinkDiscovery()
    try:
        return await discovery.query(syntax, target, **kwargs)
    finally:
        await discovery.close()


# =============================================================================
# CLI INTERFACE (FOR TESTING)
# =============================================================================

async def main():
    """CLI for testing."""
    import sys
    import json

    if len(sys.argv) < 3:
        print("Usage:")
        print("  python backlinks.py ?bl !domain.com")
        print("  python backlinks.py bl? !domain.com")
        print("  python backlinks.py ?bl domain.com/path!")
        print("  python backlinks.py bl? domain.com/path!")
        sys.exit(1)

    syntax = sys.argv[1]
    target = sys.argv[2]

    # Handle bash escape sequences (shell escapes ! to \!)
    target = target.replace(r'\!', '!')

    print(f"\n{'='*60}")
    print(f"LINKLATER BACKLINK DISCOVERY")
    print(f"{'='*60}")
    print(f"Syntax: {syntax}")
    print(f"Target: {target}")
    print(f"{'='*60}\n")

    result = await backlinks(syntax, target)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
