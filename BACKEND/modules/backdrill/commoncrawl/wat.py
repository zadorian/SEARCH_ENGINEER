"""
CommonCrawl WAT link extractor for BACKDRILL.

Wraps the cclinks_linux Go binary for fast link extraction from WAT files.

Binary location:
- Server: /data/submarine/bin/cclinks_linux
- Local: LINKLATER/scraping/web/go/cmd/cclinks/cclinks_linux

Based on:
- SUBMARINE/sastre_submarine.py CCLinksExtractor
"""

import asyncio
import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

# Binary locations (try server first, then local)
SERVER_BINARY = Path("/data/globallinks/bin/cclinks")
LOCAL_BINARY = Path(__file__).parent.parent.parent / "LINKLATER/scraping/web/go/cmd/cclinks/cclinks_linux"

# Defaults
DEFAULT_ARCHIVE = "CC-MAIN-2024-51"
DEFAULT_THREADS = 10
DEFAULT_MAX_RESULTS = 500
DEFAULT_BATCH_SIZE = 200
DEFAULT_MAX_OUTLINKS = 200


def _find_binary() -> Optional[Path]:
    """Find the cclinks binary."""
    if SERVER_BINARY.exists():
        return SERVER_BINARY
    if LOCAL_BINARY.exists():
        return LOCAL_BINARY
    return None


class CCLinksExtractor:
    """
    Extract links from CommonCrawl WAT files.

    Uses the cclinks_linux Go binary for fast concurrent extraction.

    Commands:
    - extract: Extract outlinks FROM source domains
    - backlinks: Find links TO a target domain (trawler mode)
    - sniper: Find links from specific source domains to target

    Usage:
        extractor = CCLinksExtractor()

        # Extract outlinks from domains
        outlinks = await extractor.extract_outlinks(["example.com"])

        # Find backlinks to a domain
        backlinks = await extractor.find_backlinks("example.com")

        # Sniper: check specific sources for links to target
        links = await extractor.sniper_search("target.com", ["source1.com", "source2.com"])
    """

    def __init__(
        self,
        archive: str = DEFAULT_ARCHIVE,
        binary_path: Optional[Path] = None,
    ):
        self.archive = archive
        self.binary = binary_path or _find_binary()
        self.available = self.binary is not None and self.binary.exists()

        if not self.available:
            logger.warning("cclinks binary not found - WAT extraction unavailable")

    async def extract_outlinks(
        self,
        domains: List[str],
        output_file: Optional[Path] = None,
        max_results: int = DEFAULT_MAX_RESULTS,
        max_per_domain: int = DEFAULT_MAX_OUTLINKS,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> Dict[str, List[str]]:
        """
        Extract outlinks FROM source domains.

        Args:
            domains: Source domains to extract outlinks from
            output_file: Optional file to save raw results
            max_results: Max results per batch
            max_per_domain: Max outlinks per domain
            batch_size: Domains per batch

        Returns:
            Dict mapping source_domain -> list of target URLs
        """
        if not self.available or not domains:
            return {}

        # Use temp file if no output specified
        use_temp = output_file is None
        if use_temp:
            fd, tmp_path = tempfile.mkstemp(suffix='.ndjson')
            os.close(fd)
            output_file = Path(tmp_path)
        else:
            output_file.parent.mkdir(parents=True, exist_ok=True)

        outlinks: Dict[str, List[str]] = defaultdict(list)

        # Process in batches
        for i in range(0, len(domains), batch_size):
            chunk = domains[i:i + batch_size]
            if not chunk:
                continue

            temp_file = output_file.with_name(f"{output_file.stem}_part{i}.ndjson.tmp")

            cmd = [
                str(self.binary), "extract",
                f"--domains={','.join(chunk)}",
                f"--archive={self.archive}",
                f"--output={temp_file}",
                "--format=ndjson",
                f"--threads={DEFAULT_THREADS}",
                f"--max-results={max_results}",
            ]

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                _, stderr = await proc.communicate()

                if proc.returncode != 0:
                    err_msg = stderr.decode().strip()
                    logger.warning(f"cclinks extract failed: {err_msg}")
                    continue

                if not temp_file.exists():
                    continue

                # Parse results
                with open(temp_file, "r") as rf:
                    if not use_temp:
                        wf = open(output_file, "a")

                    for line in rf:
                        line = line.strip()
                        if not line:
                            continue

                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        source_domain = data.get("sourceDomain") or data.get("source_domain")
                        target_url = data.get("target") or data.get("target_url")

                        if source_domain and target_url:
                            if len(outlinks[source_domain]) < max_per_domain:
                                outlinks[source_domain].append(target_url)

                        if not use_temp:
                            wf.write(line + "\n")

                    if not use_temp:
                        wf.close()

            finally:
                if temp_file.exists():
                    temp_file.unlink()

        if use_temp and output_file.exists():
            output_file.unlink()

        return dict(outlinks)

    async def find_backlinks(
        self,
        target_domain: str,
        output_file: Optional[Path] = None,
        source_tlds: Optional[List[str]] = None,
        max_results: int = DEFAULT_MAX_RESULTS,
        segments: str = "0",
    ) -> List[Dict[str, Any]]:
        """
        Find backlinks TO a target domain (Trawler mode).

        Scans WAT files to find pages linking to the target.

        Args:
            target_domain: Domain to find backlinks for
            output_file: Optional file to save results
            source_tlds: Only include links from these TLDs (e.g., [".uk", ".de"])
            max_results: Maximum backlinks to return
            segments: CC segments to process (e.g., "0-5" or "0,1,2")

        Returns:
            List of backlink records
        """
        if not self.available:
            return []

        # Use temp file if no output specified
        use_temp = output_file is None
        if use_temp:
            fd, tmp_path = tempfile.mkstemp(suffix='.ndjson')
            os.close(fd)
            output_file = Path(tmp_path)
        else:
            output_file.parent.mkdir(parents=True, exist_ok=True)

        backlinks = []

        cmd = [
            str(self.binary), "backlinks",
            f"--target-domain={target_domain}",
            f"--archive={self.archive}",
            f"--segments={segments}",
            f"--threads={DEFAULT_THREADS}",
            f"--max-results={max_results}",
            f"--output={output_file}",
        ]

        if source_tlds:
            cmd.append(f"--source-tlds={','.join(source_tlds)}")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                err_msg = stderr.decode().strip()
                logger.warning(f"cclinks backlinks failed: {err_msg}")
                return []

            if output_file.exists():
                with open(output_file, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                backlinks.append(json.loads(line))
                            except json.JSONDecodeError:
                                pass

        except Exception as e:
            logger.error(f"cclinks backlinks error: {e}")
        finally:
            if use_temp and output_file.exists():
                output_file.unlink()

        return backlinks

    async def sniper_search(
        self,
        target_domain: str,
        source_domains: List[str],
        output_file: Optional[Path] = None,
        max_results: int = DEFAULT_MAX_RESULTS,
    ) -> List[Dict[str, Any]]:
        """
        Sniper mode: Find backlinks from specific source domains.

        Faster than full trawler - only checks specified sources.

        Args:
            target_domain: Domain to find backlinks for
            source_domains: Specific domains to check for backlinks
            output_file: Optional file to save results
            max_results: Maximum backlinks to return

        Returns:
            List of backlink records
        """
        if not self.available or not source_domains:
            return []

        # Use temp file if no output specified
        use_temp = output_file is None
        if use_temp:
            fd, tmp_path = tempfile.mkstemp(suffix='.ndjson')
            os.close(fd)
            output_file = Path(tmp_path)
        else:
            output_file.parent.mkdir(parents=True, exist_ok=True)

        backlinks = []

        cmd = [
            str(self.binary), "sniper",
            f"--target-domain={target_domain}",
            f"--source-domains={','.join(source_domains)}",
            f"--archive={self.archive}",
            f"--threads={DEFAULT_THREADS}",
            f"--output={output_file}",
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                err_msg = stderr.decode().strip()
                logger.warning(f"cclinks sniper failed: {err_msg}")
                return []

            if output_file.exists():
                with open(output_file, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                backlinks.append(json.loads(line))
                            except json.JSONDecodeError:
                                pass

        except Exception as e:
            logger.error(f"cclinks sniper error: {e}")
        finally:
            if use_temp and output_file.exists():
                output_file.unlink()

        return backlinks

    def is_available(self) -> bool:
        """Check if binary is available."""
        return self.available
