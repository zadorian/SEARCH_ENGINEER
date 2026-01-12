"""
LinkLater GlobalLinks Client

Query GlobalLinks Go binaries for precomputed CC link relationships.
"""

import asyncio
import json
from pathlib import Path
from typing import List, Optional, Dict
from .models import LinkRecord

# Import temporal module for timeline enrichment
try:
    from ..temporal import TemporalAnalyzer
    TEMPORAL_AVAILABLE = True
except ImportError:
    TEMPORAL_AVAILABLE = False


# GlobalLinks binary path candidates
# Primary: Local to LINKLATER module (BACKEND/modules/LINKLATER/drill/go/bin/)
# Fallback: Legacy categorizer-filterer paths
GLOBALLINKS_CANDIDATES = [
    # Primary location - within LINKLATER module
    Path(__file__).resolve().parent.parent / "drill/go/bin",
    # Legacy paths (categorizer-filterer locations)
    (lambda: Path(__file__).resolve().parents[4] if len(Path(__file__).resolve().parents) > 4 else Path("/nonexistent"))() / "categorizer-filterer/globallinks/globallinks-with-outlinker/bin",
    (lambda: Path(__file__).resolve().parents[4] if len(Path(__file__).resolve().parents) > 4 else Path("/nonexistent"))() / "categorizer-filterer/globallinks/bin",
]


def find_globallinks_binary(binary_name: str = "outlinker") -> Optional[Path]:
    """
    Find a GlobalLinks binary by name.

    Available binaries:
    - outlinker: Query backlinks/outlinks
    - linksapi: API server for link queries
    - storelinks: Link storage/import
    - importer: Data importer

    Args:
        binary_name: Name of binary to find

    Returns:
        Path to binary or None
    """
    for candidate_dir in GLOBALLINKS_CANDIDATES:
        binary_path = candidate_dir / binary_name
        if binary_path.exists():
            return binary_path
    return None


class GlobalLinksClient:
    """Client for GlobalLinks Go binaries."""

    def __init__(self):
        """Initialize client with auto-detected binary paths."""
        self.outlinker = find_globallinks_binary("outlinker")
        self.linksapi = find_globallinks_binary("linksapi")
        self.storelinks = find_globallinks_binary("storelinks")
        self.importer = find_globallinks_binary("importer")

    async def get_backlinks(
        self,
        domain: str,
        limit: int = 100,
        archive: str = "CC-MAIN-2024-10",
        source_tlds: Optional[List[str]] = None,
        source_keywords: Optional[List[str]] = None,
        segments: str = "0",
        threads: Optional[int] = None
    ) -> List[LinkRecord]:
        """
        Get backlinks from GlobalLinks using backlinks command.

        Uses `outlinker backlinks` to download WAT files and extract
        pages linking TO the target domain ON-DEMAND.

        Args:
            domain: Target domain to find backlinks for
            limit: Max results
            archive: Common Crawl archive (e.g., CC-MAIN-2024-10)
            source_tlds: Filter backlinks from specific TLDs (.gov, .edu)
            source_keywords: Filter backlinks from pages with these keywords
            segments: WAT segments to process (default "0" for fast)

        Returns:
            List of LinkRecord objects (source = referring page, target = this domain)
        """
        if not self.outlinker:
            print("[GlobalLinks] outlinker binary not found")
            return []

        try:
            args = [
                str(self.outlinker),
                "backlinks",
                f"--target-domain={domain}",
                f"--archive={archive}",
                f"--segments={segments}",
                f"--max-results={limit}",
                "--format=json",
            ]

            if source_tlds:
                args.append(f"--source-tlds={','.join(source_tlds)}")
            if source_keywords:
                args.append(f"--source-keywords={','.join(source_keywords)}")
            if threads:
                args.append(f"--threads={threads}")

            print(f"[GlobalLinks] Running: {' '.join(args[-4:])}")

            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.outlinker.parent)
            )
            # WAT downloads can take time - 120s timeout
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

            # Log progress from stderr
            stderr_text = stderr.decode().strip()
            if stderr_text:
                for line in stderr_text.split('\n')[:3]:
                    if line.strip():
                        print(f"[GlobalLinks] {line[:80]}")

            records = []
            for line in stdout.decode().strip().split('\n'):
                if not line.strip():
                    continue
                # Skip help text / non-data lines
                if line.startswith(("GlobalLinks", "=", "COMMANDS:", "BACKLINKS", "--", "  ")):
                    continue
                try:
                    # Try JSON format first
                    parsed = json.loads(line)
                    records.append(LinkRecord(
                        source=parsed.get("source", ""),
                        target=parsed.get("target", domain),
                        anchor_text=parsed.get("anchorText"),
                        provider="globallinks"
                    ))
                except json.JSONDecodeError:
                    # Fall back to space-separated format
                    parts = line.split()
                    if len(parts) >= 2 and parts[0].startswith("http"):
                        records.append(LinkRecord(
                            source=parts[0],
                            target=parts[1] if len(parts) > 1 else domain,
                            anchor_text=" ".join(parts[2:]) if len(parts) > 2 else None,
                            provider="globallinks"
                        ))

            print(f"[GlobalLinks] Found {len(records)} backlinks")
            return records[:limit]
        except asyncio.TimeoutError:
            print(f"[GlobalLinks] Timeout after 120s")
            return []
        except Exception as e:
            print(f"[GlobalLinks] Backlinks error: {e}")
        return []

    async def get_outlinks(
        self,
        domain: str,
        limit: int = 100,
        archive: str = "CC-MAIN-2024-10",
        threads: Optional[int] = None
    ) -> List[LinkRecord]:
        """
        Get outlinks from GlobalLinks using extract command.

        Uses `outlinker extract` to find pages this domain links TO.
        Extracts from Common Crawl WAT files.

        Args:
            domain: Source domain to extract outlinks from
            limit: Max results
            archive: Common Crawl archive (e.g., CC-MAIN-2024-10)

        Returns:
            List of LinkRecord objects (source = this domain, target = linked pages)
        """
        if not self.outlinker:
            print("[GlobalLinks] outlinker binary not found")
            return []

        try:
            proc = await asyncio.create_subprocess_exec(
                str(self.outlinker),
                "extract",
                f"--domains={domain}",
                f"--archive={archive}",
                f"--max-results={limit}",
                "--format=json",
                *( [f"--threads={threads}"] if threads else [] ),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.outlinker.parent)
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

            # Check for errors
            stderr_text = stderr.decode().strip()
            if stderr_text and "error" in stderr_text.lower():
                print(f"[GlobalLinks] Extract stderr: {stderr_text[:100]}")

            records = []
            for line in stdout.decode().strip().split('\n'):
                if not line.strip():
                    continue
                # Skip help text / non-data lines
                if line.startswith(("GlobalLinks", "=", "COMMANDS:", "EXTRACT", "--", "  ")):
                    continue
                try:
                    # Try JSON format first
                    parsed = json.loads(line)
                    records.append(LinkRecord(
                        source=parsed.get("source", domain),
                        target=parsed.get("target", ""),
                        anchor_text=parsed.get("anchorText"),
                        provider="globallinks"
                    ))
                except json.JSONDecodeError:
                    # Fall back to space-separated format
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].startswith("http"):
                        records.append(LinkRecord(
                            source=parts[0] if parts[0].startswith("http") else domain,
                            target=parts[1],
                            provider="globallinks"
                        ))
            return records[:limit]
        except Exception as e:
            print(f"[GlobalLinks] Outlinks error: {e}")
        return []

    async def extract_outlinks(
        self,
        domains: List[str],
        archive: str = "CC-MAIN-2024-10",
        country_tlds: Optional[List[str]] = None,
        url_keywords: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
        max_results: int = 1000,
        output_format: str = "json",
        threads: Optional[int] = None
    ) -> List[LinkRecord]:
        """
        Extract outlinks from specific domains using outlinker extract command.

        Args:
            domains: List of source domains to extract from
            archive: Common Crawl archive name (e.g., CC-MAIN-2024-10)
            country_tlds: Filter outlinks to specific country TLDs (.uk, .fr, .de)
            url_keywords: Include only outlinks containing these keywords
            exclude_keywords: Exclude outlinks containing these keywords
            max_results: Maximum results per domain
            output_format: Output format (json, csv, txt)

        Returns:
            List of LinkRecord objects

        Example:
            # Extract outlinks from BBC to UK domains
            await extract_outlinks(
                domains=["bbc.com"],
                country_tlds=[".uk"],
                archive="CC-MAIN-2024-10"
            )
        """
        if not self.outlinker:
            print("[GlobalLinks] outlinker binary not found")
            return []

        try:
            args = [
                str(self.outlinker),
                "extract",
                f"--domains={','.join(domains)}",
                f"--archive={archive}",
                f"--max-results={max_results}",
                f"--format={output_format}",
            ]

            if country_tlds:
                args.append(f"--country-tlds={','.join(country_tlds)}")
            if url_keywords:
                args.append(f"--url-keywords={','.join(url_keywords)}")
            if exclude_keywords:
                args.append(f"--exclude={','.join(exclude_keywords)}")
            if threads:
                args.append(f"--threads={threads}")

            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.outlinker.parent)
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)

            records = []
            for line in stdout.decode().strip().split('\n'):
                if not line.strip():
                    continue
                try:
                    parsed = json.loads(line)
                    records.append(LinkRecord(
                        source=parsed.get("source", ""),
                        target=parsed.get("target", ""),
                        anchor_text=parsed.get("anchorText"),
                        provider="globallinks"
                    ))
                except json.JSONDecodeError:
                    continue
            return records
        except Exception as e:
            print(f"[GlobalLinks] Extract error: {e}")
        return []

    async def search_outlinks(
        self,
        target_domain: str,
        data_path: str = "data/links/"
    ) -> List[LinkRecord]:
        """
        Search for outlinks to a target domain using outlinker search command.

        Args:
            target_domain: Domain to search for
            data_path: Path to link data directory

        Returns:
            List of LinkRecord objects
        """
        if not self.outlinker:
            print("[GlobalLinks] outlinker binary not found")
            return []

        try:
            proc = await asyncio.create_subprocess_exec(
                str(self.outlinker),
                "search",
                f"--target-domain={target_domain}",
                f"--input={data_path}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.outlinker.parent)
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)

            records = []
            for line in stdout.decode().strip().split('\n'):
                if not line.strip():
                    continue
                try:
                    parsed = json.loads(line)
                    records.append(LinkRecord(
                        source=parsed.get("source", ""),
                        target=parsed.get("target", ""),
                        anchor_text=parsed.get("anchorText"),
                        provider="globallinks"
                    ))
                except json.JSONDecodeError:
                    parts = line.split()
                    if len(parts) >= 2:
                        records.append(LinkRecord(
                            source=parts[0],
                            target=parts[1],
                            provider="globallinks"
                        ))
            return records
        except Exception as e:
            print(f"[GlobalLinks] Search error: {e}")
        return []

    # --- Temporal Enrichment Methods ---

    async def enrich_with_temporal(
        self,
        records: List[LinkRecord],
        check_live: bool = False,
        max_concurrent: int = 20
    ) -> List[LinkRecord]:
        """
        Enrich LinkRecords with temporal data (first_seen, last_seen, is_live).

        Uses the TemporalAnalyzer to query Wayback Machine and Common Crawl
        for timeline information on each URL.

        Args:
            records: List of LinkRecord objects to enrich
            check_live: Whether to check if URLs are currently live (slower)
            max_concurrent: Max concurrent temporal lookups

        Returns:
            Same records with temporal fields populated
        """
        if not TEMPORAL_AVAILABLE:
            print("[GlobalLinks] Temporal module not available, skipping enrichment")
            return records

        if not records:
            return records

        # Collect unique URLs (both source and target)
        urls = set()
        for r in records:
            if r.source:
                urls.add(r.source)
            if r.target:
                urls.add(r.target)

        if not urls:
            return records

        try:
            # Initialize temporal analyzer
            temporal = TemporalAnalyzer()

            # Batch fetch timelines
            timelines = await temporal.get_url_timelines_batch(
                urls=list(urls),
                check_live=check_live,
                max_concurrent=max_concurrent
            )

            # Apply temporal data to records
            for record in records:
                # Enrich target URL (more useful - where the link points)
                target_tl = timelines.get(record.target)
                if target_tl:
                    if target_tl.first_seen_wayback:
                        record.first_seen = target_tl.first_seen_wayback.isoformat()
                        record.temporal_source = "wayback"
                    elif target_tl.first_seen_commoncrawl:
                        record.first_seen = target_tl.first_seen_commoncrawl.isoformat()
                        record.temporal_source = "commoncrawl"

                    if target_tl.last_seen_commoncrawl:
                        record.last_seen = target_tl.last_seen_commoncrawl.isoformat()
                    elif target_tl.last_seen_wayback:
                        record.last_seen = target_tl.last_seen_wayback.isoformat()

                    record.is_live = target_tl.is_live

            return records

        except Exception as e:
            print(f"[GlobalLinks] Temporal enrichment error: {e}")
            return records

    async def get_backlinks_with_temporal(
        self,
        domain: str,
        limit: int = 100,
        archive: str = "latest",
        data_path: str = "data/links/",
        check_live: bool = False
    ) -> List[LinkRecord]:
        """
        Get backlinks with temporal enrichment.

        Combines get_backlinks() with temporal timeline data.

        Args:
            domain: Target domain to find backlinks for
            limit: Max results
            archive: Which archive
            data_path: Path to link data
            check_live: Whether to check if URLs are currently live

        Returns:
            List of LinkRecord with temporal fields populated
        """
        records = await self.get_backlinks(domain, limit, archive, data_path)
        return await self.enrich_with_temporal(records, check_live=check_live)

    async def get_outlinks_with_temporal(
        self,
        domain: str,
        limit: int = 100,
        archive: str = "CC-MAIN-2024-10",
        check_live: bool = False
    ) -> List[LinkRecord]:
        """
        Get outlinks with temporal enrichment.

        Combines get_outlinks() with temporal timeline data.

        Args:
            domain: Source domain to extract outlinks from
            limit: Max results
            archive: Common Crawl archive
            check_live: Whether to check if URLs are currently live

        Returns:
            List of LinkRecord with temporal fields populated
        """
        records = await self.get_outlinks(domain, limit, archive)
        return await self.enrich_with_temporal(records, check_live=check_live)

    async def extract_outlinks_with_temporal(
        self,
        domains: List[str],
        archive: str = "CC-MAIN-2024-10",
        country_tlds: Optional[List[str]] = None,
        url_keywords: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
        max_results: int = 1000,
        output_format: str = "json",
        check_live: bool = False
    ) -> List[LinkRecord]:
        """
        Extract outlinks with temporal enrichment.

        Combines extract_outlinks() with temporal timeline data.

        Returns:
            List of LinkRecord with temporal fields populated
        """
        records = await self.extract_outlinks(
            domains, archive, country_tlds, url_keywords,
            exclude_keywords, max_results, output_format
        )
        return await self.enrich_with_temporal(records, check_live=check_live)
