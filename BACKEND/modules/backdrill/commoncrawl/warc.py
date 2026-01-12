"""
CommonCrawl WARC content fetcher for BACKDRILL.

Wraps the ccwarc_linux Go binary for fast WARC fetching.

Binary location:
- Server: /data/submarine/bin/ccwarc_linux
- Local: LINKLATER/scraping/web/go/cmd/ccwarc/ccwarc_linux

Based on:
- SUBMARINE/sastre_submarine.py CCWARCFetcher
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

# Binary locations (try server first, then local)
SERVER_BINARY = Path("/data/SEARCH_ENGINEER/BACKEND/modules/jester/scraping/go/cmd/ccwarc/ccwarc_linux")
LOCAL_BINARY = Path(__file__).parent.parent.parent / "LINKLATER/scraping/web/go/cmd/ccwarc/ccwarc_linux"

# Defaults
DEFAULT_ARCHIVE = "CC-MAIN-2024-51"
DEFAULT_THREADS = 50
DEFAULT_TIMEOUT = 30


def _find_binary() -> Optional[Path]:
    """Find the ccwarc binary."""
    if SERVER_BINARY.exists():
        return SERVER_BINARY
    if LOCAL_BINARY.exists():
        return LOCAL_BINARY
    return None


class CCWARCFetcher:
    """
    Fetch HTML content from CommonCrawl WARC files.

    Uses the ccwarc_linux Go binary for fast concurrent fetching.

    Commands:
    - index: Query CC Index for WARC locations
    - fetch: Fetch content from WARC using index records
    - batch: Combined index + fetch in one call

    Usage:
        fetcher = CCWARCFetcher()

        # Index lookup only
        records = await fetcher.index_lookup(["example.com", "test.com"])

        # Fetch content from index records
        results = await fetcher.fetch_content(records_file, output_file)

        # Full pipeline: index + fetch
        results = await fetcher.batch_fetch(["example.com"], output_file)
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
            logger.warning("ccwarc binary not found - WARC fetching unavailable")

    async def index_lookup(
        self,
        domains: List[str],
        output_file: Optional[Path] = None,
        threads: int = DEFAULT_THREADS,
    ) -> List[Dict[str, Any]]:
        """
        Query CC Index to find WARC locations for domains.

        Args:
            domains: List of domains to look up
            output_file: Optional file to save results
            threads: Concurrent threads

        Returns:
            List of CC Index records with WARC locations
        """
        if not self.available or not domains:
            return []

        # Use temp file if no output specified
        use_temp = output_file is None
        if use_temp:
            fd, tmp_path = tempfile.mkstemp(suffix='.ndjson')
            os.close(fd)
            output_file = Path(tmp_path)
        else:
            output_file.parent.mkdir(parents=True, exist_ok=True)

        records = []

        cmd = [
            str(self.binary), "index",
            f"--domains={','.join(domains)}",
            f"--archive={self.archive}",
            f"--threads={threads}",
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
                logger.warning(f"ccwarc index failed: {err_msg}")
                return []

            if output_file.exists():
                with open(output_file, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                records.append(json.loads(line))
                            except json.JSONDecodeError:
                                pass

        except Exception as e:
            logger.error(f"ccwarc index error: {e}")
        finally:
            if use_temp and output_file.exists():
                output_file.unlink()

        return records

    async def fetch_content(
        self,
        records_file: Path,
        output_file: Path,
        threads: int = DEFAULT_THREADS,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> List[Dict[str, Any]]:
        """
        Fetch HTML content from WARC using pre-computed index records.

        Args:
            records_file: NDJSON file with CC Index records
            output_file: Where to save content results
            threads: Concurrent threads
            timeout: Request timeout in seconds

        Returns:
            List of content results with HTML
        """
        if not self.available or not records_file.exists():
            return []

        output_file.parent.mkdir(parents=True, exist_ok=True)
        results = []

        cmd = [
            str(self.binary), "fetch",
            f"--records={records_file}",
            f"--threads={threads}",
            f"--timeout={timeout}",
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
                logger.warning(f"ccwarc fetch failed: {err_msg}")
                return []

            if output_file.exists():
                with open(output_file, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                results.append(json.loads(line))
                            except json.JSONDecodeError:
                                pass

        except Exception as e:
            logger.error(f"ccwarc fetch error: {e}")

        return results

    async def batch_fetch(
        self,
        domains: List[str],
        output_file: Path,
        threads: int = DEFAULT_THREADS,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> List[Dict[str, Any]]:
        """
        Full pipeline: Index lookup + WARC content fetch.

        Args:
            domains: List of domains to fetch
            output_file: Where to save content results
            threads: Concurrent threads
            timeout: Request timeout

        Returns:
            List of content results with HTML
        """
        if not self.available or not domains:
            return []

        output_file.parent.mkdir(parents=True, exist_ok=True)
        results = []

        # Write domains to temp file
        input_file = output_file.with_suffix(".input.txt")
        with open(input_file, "w") as f:
            for domain in domains:
                f.write(f"{domain}\n")

        cmd = [
            str(self.binary), "batch",
            f"--input={input_file}",
            f"--archive={self.archive}",
            f"--threads={threads}",
            f"--timeout={timeout}",
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
                logger.warning(f"ccwarc batch failed: {err_msg}")
            else:
                if output_file.exists():
                    with open(output_file, "r") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                try:
                                    results.append(json.loads(line))
                                except json.JSONDecodeError:
                                    pass

        except Exception as e:
            logger.error(f"ccwarc batch error: {e}")
        finally:
            if input_file.exists():
                input_file.unlink()

        return results

    async def fetch_single(
        self,
        url: str,
        archive: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch content for a single URL.

        Convenience wrapper around batch_fetch.
        """
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "output.ndjson"
            results = await self.batch_fetch([domain], output)

            # Find matching URL
            for r in results:
                if r.get('url') == url:
                    return r

            # Return first result if no exact match
            return results[0] if results else None
