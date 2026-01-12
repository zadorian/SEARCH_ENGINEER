#!/usr/bin/env python3
"""
DEEP DIVE - WARC Content Fetcher

Wraps the ccwarc_linux Go binary for fast WARC fetching.
Takes dive plans from DivePlanner and executes them efficiently.

The Go binary handles:
- Range requests for surgical WARC fetches
- Concurrent HTTP connections (50+)
- Gzip decompression
- Content extraction

This Python wrapper:
- Converts dive plans to ccwarc format
- Manages execution and checkpointing
- Streams results back for extraction
"""

import asyncio
import json
import logging
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional, AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
import subprocess

logger = logging.getLogger(__name__)

# Binary location
CCWARC_BINARY = Path("/data/SUBMARINE/bin/ccwarc_linux")

# Defaults
DEFAULT_THREADS = 50
DEFAULT_TIMEOUT = 30


@dataclass
class DiveResult:
    """Result from fetching a single WARC record."""
    url: str
    domain: str
    status: int
    content_type: str
    content: str
    timestamp: str
    warc_file: str
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "domain": self.domain,
            "status": self.status,
            "content_type": self.content_type,
            "content_length": len(self.content) if self.content else 0,
            "timestamp": self.timestamp,
            "warc_file": self.warc_file,
            "error": self.error,
        }


class DeepDiver:
    """
    WARC content fetcher using ccwarc_linux Go binary.

    Usage:
        diver = DeepDiver()

        # Execute a dive plan from DivePlanner
        async for result in diver.execute_plan(plan):
            print(f"Fetched {result.url}: {len(result.content)} bytes")

        # Or fetch specific domains
        async for result in diver.fetch_domains(["example.com", "test.com"]):
            process(result)

        # Or use pre-computed CC records
        async for result in diver.fetch_records(records):
            process(result)
    """

    def __init__(
        self,
        binary_path: Path = CCWARC_BINARY,
        threads: int = DEFAULT_THREADS,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.binary = binary_path
        self.threads = threads
        self.timeout = timeout
        self.available = self.binary.exists()

        if not self.available:
            logger.error(f"ccwarc binary not found at {self.binary}")

    async def execute_plan(
        self,
        plan: "DivePlan",
        checkpoint_dir: Optional[Path] = None,
        checkpoint_path: Optional[Path] = None,
    ) -> AsyncIterator[DiveResult]:
        """
        Execute a dive plan from DivePlanner.

        Converts plan targets to CC records and fetches content.
        Supports checkpointing for resume.
        """
        if not self.available:
            logger.error("ccwarc binary not available")
            return

        if checkpoint_path is None and checkpoint_dir is not None:
            checkpoint_path = Path(checkpoint_dir) / "submarine_plan_checkpoint.json"

        expected_by_domain: Dict[str, int] = {}
        for target in getattr(plan, "targets", []) or []:
            dom = (getattr(target, "domain", "") or "").strip()
            if not dom or dom in plan.completed_domains:
                continue
            expected_by_domain[dom] = expected_by_domain.get(dom, 0) + len(getattr(target, "cc_records", []) or [])

        processed_by_domain: Dict[str, int] = {}
        last_checkpoint_completed = len(getattr(plan, "completed_domains", set()) or set())

        # Collect all CC records from plan targets
        all_records = []
        for target in plan.targets:
            if target.domain in plan.completed_domains:
                continue  # Skip already completed

            for record in target.cc_records:
                all_records.append({
                    "url": record.url,
                    "filename": record.filename,
                    "offset": record.offset,
                    "length": record.length,
                    "domain": target.domain,
                })

        if not all_records:
            logger.info("No records to fetch")
            return

        logger.info(f"Executing dive plan: {len(all_records)} records from {plan.total_domains} domains")

        # Write records to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ndjson", delete=False) as f:
            for r in all_records:
                f.write(json.dumps(r) + "\n")
            records_file = Path(f.name)

        try:
            # Execute ccwarc fetch
            async for result in self._run_fetch(records_file):
                yield result

                # Update checkpoint
                if checkpoint_path and getattr(result, "domain", None):
                    dom = (result.domain or "").strip()
                    if dom and dom in expected_by_domain:
                        processed_by_domain[dom] = processed_by_domain.get(dom, 0) + 1
                        if processed_by_domain[dom] >= expected_by_domain[dom]:
                            if dom not in plan.completed_domains:
                                plan.completed_domains.add(dom)

                    if len(plan.completed_domains) > last_checkpoint_completed:
                        try:
                            plan.save(str(checkpoint_path), full=True)
                            last_checkpoint_completed = len(plan.completed_domains)
                        except Exception:
                            pass
        finally:
            records_file.unlink(missing_ok=True)

    async def fetch_domains(
        self,
        domains: List[str],
        archive: str = "CC-MAIN-2025-51",
    ) -> AsyncIterator[DiveResult]:
        """
        Fetch content for domains using batch mode (index + fetch).
        """
        if not self.available or not domains:
            return

        logger.info(f"Fetching {len(domains)} domains from {archive}")

        # Write domains to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            for d in domains:
                f.write(d + "\n")
            domains_file = Path(f.name)

        try:
            cmd = [
                str(self.binary),
                "batch",
                f"--input={domains_file}",
                f"--archive={archive}",
                f"--threads={self.threads}",
                f"--timeout={self.timeout}",
            ]

            async for result in self._run_command(cmd):
                yield result
        finally:
            domains_file.unlink(missing_ok=True)

    async def fetch_records(
        self,
        records: List[Dict[str, Any]],
    ) -> AsyncIterator[DiveResult]:
        """
        Fetch content from pre-computed CC Index records.
        """
        if not self.available or not records:
            return

        logger.info(f"Fetching {len(records)} pre-computed records")

        # Write records to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ndjson", delete=False) as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
            records_file = Path(f.name)

        try:
            async for result in self._run_fetch(records_file):
                yield result
        finally:
            records_file.unlink(missing_ok=True)

    async def _run_fetch(self, records_file: Path) -> AsyncIterator[DiveResult]:
        """Run ccwarc fetch command with records file."""
        cmd = [
            str(self.binary),
            "fetch",
            f"--records={records_file}",
            f"--threads={self.threads}",
            f"--timeout={self.timeout}",
        ]

        async for result in self._run_command(cmd):
            yield result

    async def _run_command(self, cmd: List[str]) -> AsyncIterator[DiveResult]:
        """
        Run ccwarc command and stream results.

        The binary outputs NDJSON to stdout, one result per line.
        """
        logger.debug(f"Running: {' '.join(cmd)}")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            # Stream stdout line by line
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break

                try:
                    data = json.loads(line.decode("utf-8").strip())
                    yield DiveResult(
                        url=data.get("url", ""),
                        domain=data.get("domain", ""),
                        status=data.get("status", 0),
                        content_type=data.get("content_type", ""),
                        content=data.get("content", ""),
                        timestamp=data.get("timestamp", ""),
                        warc_file=data.get("warc_file", ""),
                        error=data.get("error"),
                    )
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse output: {line[:100]}")
                    continue

            # Wait for process to finish
            await proc.wait()

            if proc.returncode != 0:
                stderr = await proc.stderr.read()
                logger.error(f"ccwarc failed: {stderr.decode()[:500]}")
        finally:
            # If the consumer stops early (breaks out of the async generator),
            # ensure the subprocess is terminated and doesn't deadlock on a full pipe.
            if proc.returncode is None:
                try:
                    proc.terminate()
                except ProcessLookupError:
                    return
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2)
                except Exception:
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        return
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=2)
                    except Exception:
                        return

    def estimate_time(self, record_count: int) -> Dict[str, float]:
        """
        Estimate time to fetch records.

        Based on ~100ms per fetch with concurrent threads.
        """
        # With 50 threads, each batch of 50 takes ~100ms
        batches = record_count / self.threads
        est_seconds = batches * 0.1

        return {
            "record_count": record_count,
            "threads": self.threads,
            "est_seconds": est_seconds,
            "est_minutes": est_seconds / 60,
        }


# Import DivePlan for type hints
import sys
sys.path.insert(0, "/data/SUBMARINE")
try:
    from dive_planner.planner import DivePlan
except ImportError:
    DivePlan = Any  # Fallback


async def main():
    """Test deep diver."""
    diver = DeepDiver()

    if not diver.available:
        print("ccwarc binary not available")
        return

    print(f"Binary: {diver.binary}")
    print(f"Threads: {diver.threads}")

    # Test with example.com
    print("\nFetching example.com...")
    count = 0
    async for result in diver.fetch_domains(["example.com"], archive="CC-MAIN-2025-51"):
        count += 1
        print(f"  [{count}] {result.url}: {len(result.content)} bytes")
        if count >= 5:
            break

    print(f"\nFetched {count} pages")


if __name__ == "__main__":
    asyncio.run(main())
