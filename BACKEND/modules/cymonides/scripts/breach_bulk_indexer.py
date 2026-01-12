#!/usr/bin/env python3
"""
Fast Breach Bulk Indexer for Elasticsearch
Indexes breach data from Raidforums to sastre ES (via SSH tunnel)

Usage:
    python breach_bulk_indexer.py                    # Index all (from bottom of list)
    python breach_bulk_indexer.py --breach youku.com # Index specific breach
    python breach_bulk_indexer.py --resume           # Resume from checkpoint
    python breach_bulk_indexer.py --list             # List available breaches
    python breach_bulk_indexer.py --skip-indexed     # Skip already indexed breaches

Requirements:
    - SSH tunnel to sastre: ssh -L 9200:localhost:9200 root@176.9.2.153 -N
    - pip install elasticsearch
"""

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Iterator, Dict, Any, List, Tuple, Optional, Set

try:
    from elasticsearch import Elasticsearch
    from elasticsearch.helpers import streaming_bulk
except ImportError:
    print("pip install elasticsearch")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Config
RAIDFORUMS_PATH = Path("/Volumes/My Book/Raidforums/DATABASES/Raidforums")
CHECKPOINT_PATH = Path("/Volumes/My Book/Raidforums/checkpoints")
ES_HOST = "http://localhost:9200"  # Via SSH tunnel
INDEX_NAME = "cymonides-3"
BATCH_SIZE = 10000
MAX_RETRIES = 3

# Delimiter patterns (in order of priority)
DELIMITERS = ['\t', ':', ';', '|', ',']

# Field detection patterns
EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
PHONE_PATTERN = re.compile(r'^[\+]?[(]?[0-9]{1,4}[)]?[-\s\./0-9]{7,}$')
IP_PATTERN = re.compile(r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$')
DATE_PATTERN = re.compile(r'^\d{4}[-/]\d{2}[-/]\d{2}')
URL_PATTERN = re.compile(r'^https?://')


class BreachIndexer:
    """Fast bulk indexer for breach data."""

    def __init__(self, es_host: str = ES_HOST):
        self.es = Elasticsearch([es_host], request_timeout=120, retry_on_timeout=True, max_retries=3)
        self.checkpoint_path = CHECKPOINT_PATH
        self.checkpoint_path.mkdir(parents=True, exist_ok=True)
        self._indexed_breaches: Optional[Set[str]] = None
        self._ensure_index()

    def _ensure_index(self):
        """Create index with dynamic mapping for all breach fields."""
        if not self.es.indices.exists(index=INDEX_NAME):
            mapping = {
                "settings": {
                    "number_of_shards": 3,
                    "number_of_replicas": 0,
                    "refresh_interval": "30s",
                    "index.translog.durability": "async",
                    "index.translog.sync_interval": "30s"
                },
                "mappings": {
                    "dynamic": True,  # Allow dynamic fields
                    "properties": {
                        # Core fields
                        "breach_name": {"type": "keyword"},
                        "source_file": {"type": "keyword"},
                        "line_number": {"type": "long"},
                        "indexed_at": {"type": "date"},
                        "raw_line": {"type": "text", "index": False},
                        # Identity fields
                        "email": {"type": "keyword"},
                        "email_domain": {"type": "keyword"},
                        "username": {"type": "keyword"},
                        "name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                        "first_name": {"type": "keyword"},
                        "last_name": {"type": "keyword"},
                        "full_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                        # Credential fields
                        "password": {"type": "keyword"},
                        "password_hash": {"type": "keyword"},
                        "hash_type": {"type": "keyword"},
                        "salt": {"type": "keyword"},
                        # Contact fields
                        "phone": {"type": "keyword"},
                        "address": {"type": "text"},
                        "city": {"type": "keyword"},
                        "state": {"type": "keyword"},
                        "country": {"type": "keyword"},
                        "zip": {"type": "keyword"},
                        "postal_code": {"type": "keyword"},
                        # Demographics
                        "dob": {"type": "keyword"},
                        "age": {"type": "integer"},
                        "gender": {"type": "keyword"},
                        "ssn": {"type": "keyword"},
                        "national_id": {"type": "keyword"},
                        # Technical
                        "ip": {"type": "ip"},
                        "ip_address": {"type": "ip"},
                        "user_agent": {"type": "text"},
                        "url": {"type": "keyword"},
                        # Timestamps
                        "created_at": {"type": "keyword"},
                        "last_login": {"type": "keyword"},
                        "reg_date": {"type": "keyword"},
                        # Additional
                        "extra_fields": {"type": "object", "enabled": True}
                    }
                }
            }
            self.es.indices.create(index=INDEX_NAME, body=mapping)
            logger.info(f"Created index: {INDEX_NAME}")

    def get_indexed_breaches(self) -> Set[str]:
        """Get set of breach names already in ES."""
        if self._indexed_breaches is not None:
            return self._indexed_breaches

        try:
            result = self.es.search(
                index=INDEX_NAME,
                body={
                    "size": 0,
                    "aggs": {
                        "breaches": {
                            "terms": {"field": "breach_name", "size": 10000}
                        }
                    }
                }
            )
            self._indexed_breaches = {
                b["key"] for b in result.get("aggregations", {}).get("breaches", {}).get("buckets", [])
            }
            logger.info(f"Found {len(self._indexed_breaches)} breaches already indexed")
            return self._indexed_breaches
        except Exception as e:
            logger.warning(f"Could not get indexed breaches: {e}")
            self._indexed_breaches = set()
            return self._indexed_breaches

    def is_breach_indexed(self, breach_name: str) -> bool:
        """Check if a breach is already indexed."""
        return breach_name in self.get_indexed_breaches()

    def detect_delimiter(self, sample_lines: List[str]) -> str:
        """Detect the delimiter used in breach file."""
        for delim in DELIMITERS:
            if all(delim in line for line in sample_lines if line.strip()):
                return delim
        return ':'  # Default fallback

    def detect_hash_type(self, value: str) -> Optional[str]:
        """Detect hash type from string."""
        if not value:
            return None
        value = value.strip()
        if len(value) == 32 and re.match(r'^[a-fA-F0-9]+$', value):
            return "md5"
        if len(value) == 40 and re.match(r'^[a-fA-F0-9]+$', value):
            return "sha1"
        if len(value) == 64 and re.match(r'^[a-fA-F0-9]+$', value):
            return "sha256"
        if value.startswith('$2a$') or value.startswith('$2b$'):
            return "bcrypt"
        if value.startswith('$1$'):
            return "md5crypt"
        if value.startswith('$6$'):
            return "sha512crypt"
        return None

    def parse_line(self, line: str, delimiter: str, breach_name: str, source_file: str, line_num: int) -> Optional[Dict[str, Any]]:
        """Parse a single breach line into a document."""
        line = line.strip()
        if not line:
            return None

        parts = line.split(delimiter)
        if len(parts) < 2:
            return None

        email = None
        password = None
        password_hash = None
        hash_type = None
        username = None
        phone = None

        # Try to identify fields
        for part in parts:
            part = part.strip()
            if not part:
                continue

            # Email detection
            if EMAIL_PATTERN.match(part) and not email:
                email = part.lower()
                continue

            # Hash detection
            detected_hash = self.detect_hash_type(part)
            if detected_hash and not password_hash:
                password_hash = part
                hash_type = detected_hash
                continue

            # Username (if looks like username)
            if re.match(r'^[a-zA-Z0-9_.-]{3,30}$', part) and not username and not email:
                username = part.lower()
                continue

            # Plain password (if not hash)
            if not password and not detected_hash and len(part) > 2:
                password = part

        # Need at least email or username
        if not email and not username:
            return None

        doc = {
            "breach_name": breach_name,
            "raw_line": line[:500],  # Truncate
            "source_file": source_file,
            "line_number": line_num,
            "indexed_at": datetime.utcnow().isoformat()
        }

        if email:
            doc["email"] = email
            doc["email_domain"] = email.split("@")[-1] if "@" in email else None
        if password:
            doc["password"] = password
        if password_hash:
            doc["password_hash"] = password_hash
            doc["hash_type"] = hash_type
        if username:
            doc["username"] = username
        if phone:
            doc["phone"] = phone

        # Generate ID
        doc_id = hashlib.sha256(f"{breach_name}:{line_num}:{line}".encode()).hexdigest()[:20]

        return {"_index": INDEX_NAME, "_id": doc_id, "_source": doc}

    def iter_breach_records(self, breach_path: Path, breach_name: str) -> Iterator[Dict[str, Any]]:
        """Iterate over breach records from files."""
        files = []

        # Find all data files
        for ext in ['*.txt', '*.csv', '*.sql', '*.json', '*.tsv']:
            files.extend(breach_path.rglob(ext))

        # Filter out metadata files
        files = [f for f in files if not f.name.startswith('.') and 'raidforums' not in f.name.lower()]

        if not files:
            logger.warning(f"No data files found in {breach_path}")
            return

        for data_file in files:
            logger.info(f"Processing: {data_file.name}")

            # Get sample for delimiter detection
            try:
                with open(data_file, 'r', encoding='utf-8', errors='ignore') as f:
                    sample_lines = [next(f, '') for _ in range(10)]
                delimiter = self.detect_delimiter(sample_lines)
            except Exception as e:
                logger.warning(f"Failed to read sample from {data_file}: {e}")
                continue

            try:
                with open(data_file, 'r', encoding='utf-8', errors='ignore') as f:
                    for line_num, line in enumerate(f, 1):
                        doc = self.parse_line(line, delimiter, breach_name, data_file.name, line_num)
                        if doc:
                            yield doc
            except Exception as e:
                logger.error(f"Error reading {data_file}: {e}")

    def get_checkpoint(self, breach_name: str) -> int:
        """Get last indexed line for a breach."""
        cp_file = self.checkpoint_path / f"{breach_name.replace(' ', '_')}.checkpoint"
        if cp_file.exists():
            return int(cp_file.read_text().strip())
        return 0

    def save_checkpoint(self, breach_name: str, line_count: int):
        """Save checkpoint for a breach."""
        cp_file = self.checkpoint_path / f"{breach_name.replace(' ', '_')}.checkpoint"
        cp_file.write_text(str(line_count))

    def index_breach(self, breach_name: str, resume: bool = False) -> Tuple[int, int]:
        """Index a single breach to Elasticsearch."""
        breach_path = RAIDFORUMS_PATH / breach_name

        if not breach_path.exists():
            logger.error(f"Breach path not found: {breach_path}")
            return 0, 0

        start_line = 0
        if resume:
            start_line = self.get_checkpoint(breach_name)
            if start_line > 0:
                logger.info(f"Resuming from line {start_line:,}")

        total = 0
        success = 0
        failed = 0
        batch = []

        logger.info(f"Indexing: {breach_name}")
        start_time = time.time()

        for doc in self.iter_breach_records(breach_path, breach_name):
            total += 1

            if total < start_line:
                continue

            batch.append(doc)

            if len(batch) >= BATCH_SIZE:
                s, f = self._bulk_index(batch)
                success += s
                failed += f
                batch = []

                elapsed = time.time() - start_time
                rate = total / elapsed if elapsed > 0 else 0
                logger.info(f"  Progress: {total:,} records ({rate:.0f}/s), {success:,} indexed, {failed:,} failed")
                self.save_checkpoint(breach_name, total)

        # Final batch
        if batch:
            s, f = self._bulk_index(batch)
            success += s
            failed += f

        self.save_checkpoint(breach_name, total)

        elapsed = time.time() - start_time
        logger.info(f"Completed: {breach_name} - {success:,} indexed, {failed:,} failed in {elapsed:.1f}s")

        return success, failed

    def _bulk_index(self, batch: List[Dict]) -> Tuple[int, int]:
        """Bulk index a batch of documents."""
        success = 0
        failed = 0

        try:
            for ok, result in streaming_bulk(
                self.es,
                batch,
                chunk_size=BATCH_SIZE,
                raise_on_error=False,
                max_retries=MAX_RETRIES
            ):
                if ok:
                    success += 1
                else:
                    failed += 1
        except Exception as e:
            logger.error(f"Bulk index error: {e}")
            failed = len(batch)

        return success, failed

    def list_breaches(self) -> List[str]:
        """List available breach directories."""
        if not RAIDFORUMS_PATH.exists():
            logger.error(f"Raidforums path not found: {RAIDFORUMS_PATH}")
            return []

        breaches = sorted([d.name for d in RAIDFORUMS_PATH.iterdir() if d.is_dir()])
        return breaches

    def index_all(self, reverse: bool = True, resume: bool = False):
        """Index all breaches."""
        breaches = self.list_breaches()
        if reverse:
            breaches = breaches[::-1]  # Start from bottom (z to a)

        total_success = 0
        total_failed = 0

        for i, breach in enumerate(breaches, 1):
            logger.info(f"\n[{i}/{len(breaches)}] Starting: {breach}")
            s, f = self.index_breach(breach, resume=resume)
            total_success += s
            total_failed += f

            # Force refresh after each breach
            try:
                self.es.indices.refresh(index=INDEX_NAME)
            except:
                pass

        logger.info(f"\n{'='*60}")
        logger.info(f"ALL BREACHES COMPLETE")
        logger.info(f"Total indexed: {total_success:,}")
        logger.info(f"Total failed: {total_failed:,}")
        logger.info(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Fast Breach Bulk Indexer")
    parser.add_argument("--breach", help="Index specific breach by name")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--list", action="store_true", help="List available breaches")
    parser.add_argument("--reverse", action="store_true", default=True, help="Index from bottom of list (z to a)")
    parser.add_argument("--es-host", default=ES_HOST, help="Elasticsearch host")
    args = parser.parse_args()

    indexer = BreachIndexer(es_host=args.es_host)

    if args.list:
        breaches = indexer.list_breaches()
        print(f"\nAvailable breaches ({len(breaches)}):")
        for b in breaches:
            checkpoint = indexer.get_checkpoint(b)
            status = f" (checkpoint: {checkpoint:,})" if checkpoint > 0 else ""
            print(f"  - {b}{status}")
        return

    if args.breach:
        indexer.index_breach(args.breach, resume=args.resume)
    else:
        indexer.index_all(reverse=args.reverse, resume=args.resume)


if __name__ == "__main__":
    main()
