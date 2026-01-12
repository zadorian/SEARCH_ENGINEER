"""
Filetype Index Populator

Populate the cc_domain_filetypes index from Common Crawl Index API.
Queries CC Index for each domain's document inventory and builds
filetype profiles for credibility scoring.

Usage:
    # CLI
    python -m modules.linklater.mapping.filetype_populator \
        --domains-file domains.txt \
        --batch-size 50

    # Programmatic
    from modules.linklater.mapping.filetype_populator import FiletypePopulator

    populator = FiletypePopulator()
    count = await populator.populate_from_domains(["example.com", "test.org"])
    print(f"Populated {count} profiles")

Population Strategies:
    1. Batch: Process list of known domains (initial population)
    2. Opportunistic: Profile domains during backlink discovery
    3. Incremental: Update stale profiles periodically
"""

import os
import re
import math
import logging
import asyncio
from typing import List, Dict, Optional, Set
from datetime import datetime
from dataclasses import dataclass

from .filetype_index import FiletypeIndexManager, FiletypeProfile
from ..cc_config import CC_INDEX_BASE, get_default_archive, get_latest_archive

logger = logging.getLogger(__name__)

# MIME type mapping for filetypes
MIME_MAPPING = {
    "pdf": ["application/pdf"],
    "doc": ["application/msword"],
    "docx": ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
    "xls": ["application/vnd.ms-excel"],
    "xlsx": ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"],
    "ppt": ["application/vnd.ms-powerpoint"],
    "pptx": ["application/vnd.openxmlformats-officedocument.presentationml.presentation"],
}

# File extensions to search
DEFAULT_FILETYPES = ["pdf", "doc", "docx", "xls", "xlsx"]

# Annual report detection patterns
ANNUAL_REPORT_PATTERNS = [
    r"annual[_-]?report",
    r"årsredovisning",
    r"arsredovisning",
    r"jahresbericht",
    r"rapport[_-]?annuel",
    r"relazione[_-]?annuale",
    r"informe[_-]?anual",
    r"jaarverslag",
    r"10-?k",
    r"annual[_-]?accounts",
]

# Compile patterns for efficiency
ANNUAL_REPORT_REGEX = re.compile(
    "|".join(ANNUAL_REPORT_PATTERNS),
    re.IGNORECASE
)


@dataclass
class CCFiletypeResult:
    """Result from CC Index filetype query."""
    url: str
    mime: str
    status: int
    length: int
    timestamp: str


class FiletypePopulator:
    """
    Populate domain filetype profiles from Common Crawl Index.

    Queries the CC Index API to discover documents hosted on domains,
    then builds FiletypeProfile objects for storage.
    """

    # CC Index API base URL - now imported from cc_config
    # DEFAULT_ARCHIVE - now uses get_default_archive() from cc_config

    def __init__(
        self,
        archive: str = None,
        index_manager: FiletypeIndexManager = None,
        max_results_per_type: int = 100
    ):
        """
        Initialize populator.

        Args:
            archive: CC archive to query (default: latest from collinfo.json)
            index_manager: Custom index manager (default: create new)
            max_results_per_type: Max results per filetype per domain
        """
        self.archive = archive or get_default_archive()
        self.index_manager = index_manager or FiletypeIndexManager()
        self.max_results_per_type = max_results_per_type

    async def populate_from_domains(
        self,
        domains: List[str],
        filetypes: List[str] = None,
        parallel: int = 5,
        skip_existing: bool = True
    ) -> int:
        """
        Populate filetype profiles for a list of domains.

        Args:
            domains: List of domains to profile
            filetypes: Extensions to search (default: pdf, doc, docx, xls, xlsx)
            parallel: Number of concurrent requests
            skip_existing: Skip domains already in index

        Returns:
            Number of profiles created/updated

        Example:
            populator = FiletypePopulator()
            count = await populator.populate_from_domains([
                "sebgroup.com",
                "investor.se",
                "handelsbanken.com"
            ])
        """
        filetypes = filetypes or DEFAULT_FILETYPES
        populated = 0

        # Filter existing if requested
        if skip_existing:
            existing = await self.index_manager.batch_lookup(domains)
            domains = [d for d in domains if d not in existing]
            logger.info(f"Skipping {len(existing)} existing profiles")

        if not domains:
            logger.info("No domains to process")
            return 0

        logger.info(f"Processing {len(domains)} domains with parallelism {parallel}")

        # Process in parallel batches
        semaphore = asyncio.Semaphore(parallel)

        async def process_with_limit(domain: str) -> bool:
            async with semaphore:
                return await self._process_domain(domain, filetypes)

        tasks = [process_with_limit(d) for d in domains]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for domain, result in zip(domains, results):
            if isinstance(result, Exception):
                logger.error(f"Error processing {domain}: {result}")
            elif result:
                populated += 1

        logger.info(f"Populated {populated}/{len(domains)} profiles")
        return populated

    async def _process_domain(
        self,
        domain: str,
        filetypes: List[str]
    ) -> bool:
        """
        Process a single domain and upsert its profile.

        Args:
            domain: Domain to profile
            filetypes: Extensions to search

        Returns:
            True if profile was created/updated
        """
        try:
            profile = await self._build_profile(domain, filetypes)

            # Only store if we found something
            if profile.total_documents > 0:
                return await self.index_manager.upsert_profile(profile)
            else:
                logger.debug(f"No documents found for {domain}")
                return False

        except Exception as e:
            logger.error(f"Error building profile for {domain}: {e}")
            return False

    async def _build_profile(
        self,
        domain: str,
        filetypes: List[str]
    ) -> FiletypeProfile:
        """
        Build a FiletypeProfile for a domain by querying CC Index.

        Args:
            domain: Domain to profile
            filetypes: Extensions to search

        Returns:
            FiletypeProfile with document counts and analysis
        """
        import httpx

        filetype_counts: Dict[str, int] = {}
        sample_urls: List[str] = []
        all_urls: Set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            for ext in filetypes:
                try:
                    results = await self._query_cc_for_filetype(client, domain, ext)
                    filetype_counts[ext] = len(results)

                    # Collect sample URLs (first 3 per type)
                    for r in results[:3]:
                        if r.url not in all_urls:
                            sample_urls.append(r.url)
                            all_urls.add(r.url)

                except Exception as e:
                    logger.debug(f"Error querying {ext} for {domain}: {e}")
                    filetype_counts[ext] = 0

        # Calculate totals
        pdf_count = filetype_counts.get("pdf", 0)
        doc_count = filetype_counts.get("doc", 0) + filetype_counts.get("docx", 0)
        xls_count = filetype_counts.get("xls", 0) + filetype_counts.get("xlsx", 0)
        total_documents = sum(filetype_counts.values())

        # Detect annual reports from URLs
        has_annual_reports = self._detect_annual_reports(sample_urls)

        # Calculate authority score
        authority_score = self._calculate_authority(
            filetype_counts,
            has_annual_reports,
            total_documents
        )

        return FiletypeProfile(
            domain=domain,
            filetypes=filetype_counts,
            pdf_count=pdf_count,
            doc_count=doc_count,
            xls_count=xls_count,
            total_documents=total_documents,
            has_annual_reports=has_annual_reports,
            document_authority_score=authority_score,
            sample_urls=sample_urls[:10],
            source="cc_index",
        )

    async def _query_cc_for_filetype(
        self,
        client,
        domain: str,
        ext: str
    ) -> List[CCFiletypeResult]:
        """
        Query CC Index for a specific filetype on a domain.

        Args:
            client: HTTP client
            domain: Domain to search
            ext: File extension (e.g., "pdf")

        Returns:
            List of CCFiletypeResult
        """
        import json

        # Build URL pattern for domain - CC Index uses domain/* pattern
        # Filter by MIME type to find specific file types
        url_pattern = f"{domain}/*"

        # Get MIME types for this extension
        mimes = MIME_MAPPING.get(ext, [])
        mime_filter = mimes[0] if mimes else None  # CC Index takes single MIME

        params = {
            "url": url_pattern,
            "output": "json",
        }

        if mime_filter:
            params["filter"] = f"mime:{mime_filter}"

        endpoint = f"{CC_INDEX_BASE}/{self.archive}-index"

        try:
            response = await client.get(endpoint, params=params)

            if response.status_code == 404:
                return []

            response.raise_for_status()

            results = []
            for line in response.text.strip().split("\n"):
                if line:
                    try:
                        data = json.loads(line)
                        results.append(CCFiletypeResult(
                            url=data.get("url", ""),
                            mime=data.get("mime", ""),
                            status=int(data.get("status", 0)),
                            length=int(data.get("length", 0)),
                            timestamp=data.get("timestamp", ""),
                        ))

                        if len(results) >= self.max_results_per_type:
                            break
                    except json.JSONDecodeError:
                        continue

            return results

        except Exception as e:
            logger.debug(f"CC Index query failed for {domain}/{ext}: {e}")
            return []

    def _detect_annual_reports(self, urls: List[str]) -> bool:
        """
        Check if any URLs indicate annual reports.

        Args:
            urls: List of document URLs

        Returns:
            True if annual report patterns detected
        """
        for url in urls:
            if ANNUAL_REPORT_REGEX.search(url):
                return True
        return False

    def _calculate_authority(
        self,
        counts: Dict[str, int],
        has_annual_reports: bool,
        total_documents: int
    ) -> float:
        """
        Calculate document authority score (0-100).

        Signals:
        - PDF count (0-40): More PDFs = more authoritative
        - Document diversity (0-20): Multiple filetypes = professional
        - Annual reports (0-30): Strong indicator of corporate/institutional
        - Volume threshold (0-10): Minimum viable document presence

        Args:
            counts: Dict of extension -> count
            has_annual_reports: Whether annual reports were detected
            total_documents: Total document count

        Returns:
            Authority score 0-100
        """
        score = 0.0

        # 1. PDF count bonus (logarithmic, caps at 40)
        pdf_count = counts.get("pdf", 0)
        if pdf_count > 0:
            # log10(1) = 0, log10(10) = 1, log10(100) = 2, log10(1000) = 3
            # Scale: 10 * log10(count + 1), max 40
            score += min(40, 10 * math.log10(pdf_count + 1))

        # 2. Document diversity bonus (up to 20)
        active_types = sum(1 for c in counts.values() if c > 0)
        score += min(20, active_types * 5)

        # 3. Annual reports bonus (30)
        if has_annual_reports:
            score += 30

        # 4. Volume threshold bonus (up to 10)
        if total_documents >= 50:
            score += 10
        elif total_documents >= 20:
            score += 7
        elif total_documents >= 10:
            score += 5
        elif total_documents >= 5:
            score += 2

        return min(100.0, score)

    async def populate_from_file(
        self,
        filepath: str,
        parallel: int = 5,
        skip_existing: bool = True
    ) -> int:
        """
        Populate profiles from a file of domains (one per line).

        Args:
            filepath: Path to file with domains
            parallel: Concurrent requests
            skip_existing: Skip already-indexed domains

        Returns:
            Number of profiles created
        """
        with open(filepath, "r") as f:
            domains = [line.strip() for line in f if line.strip()]

        return await self.populate_from_domains(
            domains,
            parallel=parallel,
            skip_existing=skip_existing
        )

    async def opportunistic_profile(
        self,
        domain: str,
        filetypes: List[str] = None
    ) -> Optional[FiletypeProfile]:
        """
        Profile a single domain on-demand.

        Use this during discovery when a domain isn't in the index.
        Non-blocking - returns quickly if CC Index is slow.

        Args:
            domain: Domain to profile
            filetypes: Extensions to search

        Returns:
            FiletypeProfile or None if failed/timed out
        """
        filetypes = filetypes or ["pdf"]  # Quick: just check PDFs

        try:
            profile = await asyncio.wait_for(
                self._build_profile(domain, filetypes),
                timeout=10.0  # Quick timeout
            )

            if profile.total_documents > 0:
                await self.index_manager.upsert_profile(profile)
                return profile
            return None

        except asyncio.TimeoutError:
            logger.debug(f"Timeout profiling {domain}")
            return None
        except Exception as e:
            logger.debug(f"Error profiling {domain}: {e}")
            return None


# CLI interface
async def main():
    """CLI entry point for batch population."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Populate domain filetype profiles from Common Crawl"
    )
    parser.add_argument(
        "--domains-file",
        type=str,
        help="File with domains (one per line)"
    )
    parser.add_argument(
        "--domains",
        type=str,
        nargs="+",
        help="Domains to process"
    )
    parser.add_argument(
        "--archive",
        type=str,
        default=None,  # Uses latest from cc_config
        help="CC archive to query (default: latest from collinfo.json)"
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=5,
        help="Concurrent requests"
    )
    parser.add_argument(
        "--include-existing",
        action="store_true",
        help="Re-process already indexed domains"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show index statistics"
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    populator = FiletypePopulator(archive=args.archive)

    # Show stats
    if args.stats:
        stats = await populator.index_manager.get_stats()
        print("\nFiletype Index Statistics:")
        print(f"  Total domains: {stats.get('total_domains', 0):,}")
        print(f"  Avg PDF count: {stats.get('avg_pdf_count', 0):.1f}")
        print(f"  Avg authority: {stats.get('avg_authority_score', 0):.1f}")
        print(f"  With annual reports: {stats.get('domains_with_annual_reports', 0):,}")
        if stats.get("by_source"):
            print("  By source:")
            for source, count in stats["by_source"].items():
                print(f"    {source}: {count:,}")
        return

    # Get domains to process
    domains = []

    if args.domains_file:
        with open(args.domains_file, "r") as f:
            domains.extend(line.strip() for line in f if line.strip())

    if args.domains:
        domains.extend(args.domains)

    if not domains:
        print("No domains specified. Use --domains or --domains-file")
        return

    print(f"\nProcessing {len(domains)} domains from {args.archive}...")

    count = await populator.populate_from_domains(
        domains,
        parallel=args.parallel,
        skip_existing=not args.include_existing
    )

    print(f"\nCompleted: {count} profiles created/updated")


if __name__ == "__main__":
    asyncio.run(main())
