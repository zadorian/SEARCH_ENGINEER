#!/usr/bin/env python3
"""
COMMS_UNIFIED CONSOLIDATION SCRIPT

Consolidates communication/email data from multiple sources into a unified comms_unified index.

Sources:
  - breach_records (189M) - Individual email addresses with breach metadata
  - kazaword_emails (92K) - Email messages (explode all_emails array)
  - emails_unified (5K) - Additional email records

Target: comms_unified

Core Contract (4 fields):
  - subject: [] (empty for comms - no entity linkage yet)
  - concepts: [] (empty for comms)
  - dimension_keys: Normalized facets (emaildom:, sectier:, source:, year:)
  - doc_type: "communication"

ID Strategy: Deterministic hash-based IDs
  - ID = hash(source_dataset + ":" + email)
  - Enables idempotent re-runs
  - Deduplicates same email from same source

Usage:
    python consolidate_comms.py                    # Full run
    python consolidate_comms.py --source breach   # Only breach_records
    python consolidate_comms.py --resume          # Resume from checkpoint
    python consolidate_comms.py --verify          # Verify only
"""

import hashlib
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Set

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk, scan

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Config
ES_HOST = "http://localhost:9200"
TARGET_INDEX = "comms_unified"
BATCH_SIZE = 2000
SCROLL_SIZE = 5000
SCROLL_TIMEOUT = "15m"

# Checkpoint file
CHECKPOINT_FILE = Path(__file__).parent / "comms_checkpoint.json"

# Source configurations
SOURCES = {
    "breach_records": {
        "index": "breach_records",
        "email_field": "email",
        "explode": False,  # One email per record
    },
    # NOTE: kazaword_emails disabled - index does not exist
    "emails_unified": {
        "index": "emails_unified",
        "email_field": "email",
        "explode": False,
    },
}

# Security tier classification based on hash type
HASH_SECURITY_TIERS = {
    # Weak (easily crackable)
    "plaintext": "critical",
    "plain": "critical",
    "md5": "weak",
    "sha1": "weak",
    "mysql": "weak",
    "mysql4": "weak",
    "mysql5": "weak",
    "des": "weak",
    "lm": "weak",
    "ntlm": "moderate",

    # Moderate
    "sha256": "moderate",
    "sha384": "moderate",
    "sha512": "moderate",
    "whirlpool": "moderate",

    # Strong (modern hashing)
    "bcrypt": "strong",
    "scrypt": "strong",
    "argon2": "strong",
    "pbkdf2": "strong",
}


def generate_deterministic_id(source: str, email: str) -> str:
    """
    Generate deterministic ID from source + email.

    This enables idempotent re-runs - same email from same source always gets same ID.
    """
    # Normalize email for consistent hashing
    email_norm = email.lower().strip()
    composite = f"{source}:{email_norm}"
    return hashlib.sha256(composite.encode()).hexdigest()[:24]


def normalize_dimension_value(value: str) -> str:
    """Normalize a value for use in dimension_keys."""
    if not value:
        return ""
    value = str(value).strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return value


def add_dimension_key(keys: set, prefix: str, value: Any) -> None:
    """Add a dimension key with prefix:value format."""
    if not value:
        return
    if isinstance(value, list):
        for v in value:
            normalized = normalize_dimension_value(str(v))
            if normalized:
                keys.add(f"{prefix}:{normalized}")
    else:
        normalized = normalize_dimension_value(str(value))
        if normalized:
            keys.add(f"{prefix}:{normalized}")


def extract_email_parts(email: str) -> tuple:
    """Extract local part and domain from email address."""
    email = str(email).strip().lower()
    if '@' not in email:
        return ("", "")
    parts = email.split('@')
    local_part = parts[0]
    domain = parts[1] if len(parts) > 1 else ""
    return (local_part, domain)


def classify_hash_security(hash_type: str) -> str:
    """Classify hash type into security tier."""
    if not hash_type:
        return "unknown"
    hash_lower = str(hash_type).lower().strip()

    # Check exact match first
    if hash_lower in HASH_SECURITY_TIERS:
        return HASH_SECURITY_TIERS[hash_lower]

    # Check partial match
    for pattern, tier in HASH_SECURITY_TIERS.items():
        if pattern in hash_lower:
            return tier

    return "unknown"


def validate_email(email: str) -> bool:
    """Basic email validation."""
    if not email or not isinstance(email, str):
        return False
    email = email.strip()
    if len(email) < 5 or len(email) > 320:
        return False
    if '@' not in email:
        return False
    local, domain = email.split('@', 1)
    if not local or not domain:
        return False
    if '.' not in domain:
        return False
    return True


def transform_breach_record(doc: dict) -> Optional[dict]:
    """Transform breach_records record to comms_unified format."""
    email = doc.get("email", "")
    if not validate_email(email):
        return None

    email = email.lower().strip()
    local_part, email_domain = extract_email_parts(email)

    # Generate deterministic ID
    doc_id = generate_deterministic_id("breach_records", email)

    # Build dimension_keys
    dimension_keys = set()
    add_dimension_key(dimension_keys, "source", "breach")
    add_dimension_key(dimension_keys, "emaildom", email_domain)

    # Breach year
    breach_year = doc.get("breach_year")
    if breach_year:
        add_dimension_key(dimension_keys, "year", str(breach_year))

    # Security tier from hash type
    hash_type = doc.get("hash_type", "")
    security_tier = classify_hash_security(hash_type)
    add_dimension_key(dimension_keys, "sectier", security_tier)

    # Country
    country = doc.get("country")
    if country:
        add_dimension_key(dimension_keys, "jur", country)

    result = {
        "id": doc_id,
        "email": email,
        "email_domain": email_domain,
        "local_part": local_part,

        # Provenance
        "source_dataset": "breach_records",
        "source_record_id": doc.get("_id", ""),
        "breach_name": doc.get("breach_name"),
        "breach_year": breach_year,

        # Cross-search contract
        "subject": [],
        "concepts": [],
        "dimension_keys": sorted(dimension_keys),
        "doc_type": "communication",

        # Metadata
        "metadata": {
            "name": doc.get("name"),
            "address": doc.get("address"),
            "phone": doc.get("phone"),
            "ip_address": doc.get("ip_address"),
            "password_hash": doc.get("password_hash"),
            "hash_type": hash_type,
            "city": doc.get("city"),
            "state": doc.get("state"),
            "country": country,
            "user_id": doc.get("user_id"),
        },

        # Timestamps
        "indexed_at": datetime.utcnow().isoformat(),
    }

    return result


def transform_kazaword_email(doc: dict, email: str) -> Optional[dict]:
    """Transform a single email from kazaword_emails to comms_unified format."""
    if not validate_email(email):
        return None

    email = email.lower().strip()
    local_part, email_domain = extract_email_parts(email)

    # Generate deterministic ID
    doc_id = generate_deterministic_id("kazaword_emails", email)

    # Build dimension_keys
    dimension_keys = set()
    add_dimension_key(dimension_keys, "source", "kazaword")
    add_dimension_key(dimension_keys, "emaildom", email_domain)

    # Extract year from date
    date_str = doc.get("date", "")
    if date_str:
        year_match = re.search(r'(19|20)\d{2}', str(date_str))
        if year_match:
            add_dimension_key(dimension_keys, "year", year_match.group())

    result = {
        "id": doc_id,
        "email": email,
        "email_domain": email_domain,
        "local_part": local_part,

        # Provenance
        "source_dataset": "kazaword_emails",
        "source_record_id": doc.get("message_id", doc.get("_id", "")),

        # Cross-search contract
        "subject": [],
        "concepts": [],
        "dimension_keys": sorted(dimension_keys),
        "doc_type": "communication",

        # Metadata (from email context)
        "metadata": {
            "source_archive": doc.get("source_archive"),
            "originating_ip": doc.get("originating_ip"),
            "email_date": date_str,
        },

        # Timestamps
        "indexed_at": datetime.utcnow().isoformat(),
    }

    return result


def transform_emails_unified(doc: dict) -> Optional[dict]:
    """Transform emails_unified record to comms_unified format."""
    email = doc.get("email", "")
    if not validate_email(email):
        return None

    email = email.lower().strip()
    local_part, email_domain = extract_email_parts(email)

    # Generate deterministic ID
    doc_id = generate_deterministic_id("emails_unified", email)

    # Build dimension_keys
    dimension_keys = set()
    add_dimension_key(dimension_keys, "source", "unified")
    add_dimension_key(dimension_keys, "emaildom", email_domain)

    result = {
        "id": doc_id,
        "email": email,
        "email_domain": email_domain,
        "local_part": local_part,

        # Provenance
        "source_dataset": "emails_unified",
        "source_record_id": doc.get("_id", ""),

        # Cross-search contract
        "subject": [],
        "concepts": [],
        "dimension_keys": sorted(dimension_keys),
        "doc_type": "communication",

        # Metadata
        "metadata": {},

        # Timestamps
        "indexed_at": datetime.utcnow().isoformat(),
    }

    return result


def load_checkpoint() -> dict:
    """Load checkpoint from file."""
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {"completed_sources": [], "stats": {}, "processed_docs": {}}


def save_checkpoint(checkpoint: dict) -> None:
    """Save checkpoint to file."""
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(checkpoint, f, indent=2)


def scroll_source(es: Elasticsearch, source_name: str) -> Generator[dict, None, None]:
    """Scroll through a source index, yielding documents."""
    config = SOURCES[source_name]
    index = config["index"]

    logger.info(f"Starting scroll for {index}...")

    for doc in scan(
        es,
        index=index,
        query={"query": {"match_all": {}}},
        scroll=SCROLL_TIMEOUT,
        size=SCROLL_SIZE,
        preserve_order=False,
    ):
        doc["_source"]["_id"] = doc["_id"]
        yield doc["_source"]


def ensure_target_index(es: Elasticsearch) -> None:
    """Create target index if it doesn't exist."""
    if es.indices.exists(index=TARGET_INDEX):
        logger.info(f"Target index {TARGET_INDEX} exists")
        return

    # Create index with mapping
    mapping = {
        "settings": {
            "number_of_shards": 5,  # More shards for large dataset
            "number_of_replicas": 0,
            "refresh_interval": "60s",  # Less frequent refresh during bulk
            "index.mapping.total_fields.limit": 500,
        },
        "mappings": {
            "properties": {
                # Identity
                "id": {"type": "keyword"},
                "email": {"type": "keyword"},
                "email_domain": {"type": "keyword"},
                "local_part": {"type": "keyword"},

                # Provenance
                "source_dataset": {"type": "keyword"},
                "source_record_id": {"type": "keyword"},
                "breach_name": {"type": "keyword"},
                "breach_year": {"type": "integer"},

                # Cross-search contract
                "subject": {"type": "keyword"},
                "concepts": {"type": "keyword"},
                "dimension_keys": {"type": "keyword"},
                "doc_type": {"type": "keyword"},

                # Metadata
                "metadata": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "text"},
                        "address": {"type": "text"},
                        "phone": {"type": "keyword"},
                        "ip_address": {"type": "ip", "ignore_malformed": True},
                        "password_hash": {"type": "keyword", "index": False},
                        "hash_type": {"type": "keyword"},
                        "city": {"type": "keyword"},
                        "state": {"type": "keyword"},
                        "country": {"type": "keyword"},
                        "user_id": {"type": "keyword"},
                    }
                },

                # Timestamps
                "indexed_at": {"type": "date"},
            }
        }
    }

    es.indices.create(index=TARGET_INDEX, body=mapping)
    logger.info(f"Created target index {TARGET_INDEX}")


def consolidate_breach_records(es: Elasticsearch, checkpoint: dict) -> dict:
    """Consolidate breach_records into comms_unified."""
    stats = {"indexed": 0, "failed": 0, "skipped": 0}
    actions = []
    seen_emails: Set[str] = set()  # Dedupe within this run

    logger.info("Processing breach_records...")

    for doc in scroll_source(es, "breach_records"):
        try:
            transformed = transform_breach_record(doc)
            if transformed is None:
                stats["skipped"] += 1
                continue

            # Skip duplicates within this run
            if transformed["id"] in seen_emails:
                stats["skipped"] += 1
                continue
            seen_emails.add(transformed["id"])

            actions.append({
                "_index": TARGET_INDEX,
                "_id": transformed["id"],
                "_source": transformed,
            })

            # Bulk index in batches
            if len(actions) >= BATCH_SIZE:
                success, errors = bulk(
                    es, actions,
                    raise_on_error=False,
                    stats_only=True
                )
                stats["indexed"] += success
                stats["failed"] += len(errors) if isinstance(errors, list) else errors

                total = stats["indexed"] + stats["failed"] + stats["skipped"]
                if total % 500000 == 0:
                    logger.info(f"  breach_records: {total:,} processed ({stats['indexed']:,} indexed)")
                    save_checkpoint(checkpoint)

                actions = []

                # Clear seen set periodically to manage memory (some duplicates may slip through)
                if len(seen_emails) > 5000000:
                    seen_emails.clear()

        except Exception as e:
            logger.warning(f"Transform error: {e}")
            stats["failed"] += 1

    # Index remaining
    if actions:
        success, errors = bulk(es, actions, raise_on_error=False, stats_only=True)
        stats["indexed"] += success
        stats["failed"] += len(errors) if isinstance(errors, list) else errors

    logger.info(f"  breach_records complete: {stats['indexed']:,} indexed, {stats['skipped']:,} skipped")
    return stats


def consolidate_kazaword(es: Elasticsearch, checkpoint: dict) -> dict:
    """Consolidate kazaword_emails into comms_unified (exploding all_emails)."""
    stats = {"indexed": 0, "failed": 0, "skipped": 0}
    actions = []
    seen_emails: Set[str] = set()

    logger.info("Processing kazaword_emails (exploding all_emails)...")

    for doc in scroll_source(es, "kazaword_emails"):
        try:
            all_emails = doc.get("all_emails", [])
            if not all_emails:
                stats["skipped"] += 1
                continue

            if isinstance(all_emails, str):
                all_emails = [all_emails]

            for email in all_emails:
                transformed = transform_kazaword_email(doc, email)
                if transformed is None:
                    stats["skipped"] += 1
                    continue

                if transformed["id"] in seen_emails:
                    stats["skipped"] += 1
                    continue
                seen_emails.add(transformed["id"])

                actions.append({
                    "_index": TARGET_INDEX,
                    "_id": transformed["id"],
                    "_source": transformed,
                })

            # Bulk index in batches
            if len(actions) >= BATCH_SIZE:
                success, errors = bulk(
                    es, actions,
                    raise_on_error=False,
                    stats_only=True
                )
                stats["indexed"] += success
                stats["failed"] += len(errors) if isinstance(errors, list) else errors
                actions = []

        except Exception as e:
            logger.warning(f"Transform error: {e}")
            stats["failed"] += 1

    # Index remaining
    if actions:
        success, errors = bulk(es, actions, raise_on_error=False, stats_only=True)
        stats["indexed"] += success
        stats["failed"] += len(errors) if isinstance(errors, list) else errors

    logger.info(f"  kazaword_emails complete: {stats['indexed']:,} indexed, {stats['skipped']:,} skipped")
    return stats


def consolidate_emails_unified(es: Elasticsearch, checkpoint: dict) -> dict:
    """Consolidate emails_unified into comms_unified."""
    stats = {"indexed": 0, "failed": 0, "skipped": 0}
    actions = []

    logger.info("Processing emails_unified...")

    for doc in scroll_source(es, "emails_unified"):
        try:
            transformed = transform_emails_unified(doc)
            if transformed is None:
                stats["skipped"] += 1
                continue

            actions.append({
                "_index": TARGET_INDEX,
                "_id": transformed["id"],
                "_source": transformed,
            })

            if len(actions) >= BATCH_SIZE:
                success, errors = bulk(
                    es, actions,
                    raise_on_error=False,
                    stats_only=True
                )
                stats["indexed"] += success
                stats["failed"] += len(errors) if isinstance(errors, list) else errors
                actions = []

        except Exception as e:
            stats["failed"] += 1

    if actions:
        success, errors = bulk(es, actions, raise_on_error=False, stats_only=True)
        stats["indexed"] += success
        stats["failed"] += len(errors) if isinstance(errors, list) else errors

    logger.info(f"  emails_unified complete: {stats['indexed']:,} indexed")
    return stats


def verify_consolidation(es: Elasticsearch) -> None:
    """Verify the consolidated index."""
    if not es.indices.exists(index=TARGET_INDEX):
        logger.error(f"Index {TARGET_INDEX} does not exist")
        return

    count = es.count(index=TARGET_INDEX)["count"]
    logger.info(f"\n{'='*60}")
    logger.info(f"VERIFICATION: {TARGET_INDEX}")
    logger.info(f"{'='*60}")
    logger.info(f"Total documents: {count:,}")

    aggs = es.search(
        index=TARGET_INDEX,
        body={
            "size": 0,
            "aggs": {
                "by_source": {"terms": {"field": "source_dataset", "size": 10}},
                "by_security_tier": {"terms": {"field": "dimension_keys", "include": "sectier:.*", "size": 10}},
                "top_domains": {"terms": {"field": "email_domain", "size": 15}},
                "by_year": {"terms": {"field": "dimension_keys", "include": "year:.*", "size": 15}},
            }
        }
    )

    logger.info("\nBy Source Dataset:")
    for bucket in aggs["aggregations"]["by_source"]["buckets"]:
        logger.info(f"  {bucket['key']}: {bucket['doc_count']:,}")

    logger.info("\nBy Security Tier:")
    for bucket in aggs["aggregations"]["by_security_tier"]["buckets"]:
        logger.info(f"  {bucket['key']}: {bucket['doc_count']:,}")

    logger.info("\nTop Email Domains:")
    for bucket in aggs["aggregations"]["top_domains"]["buckets"][:10]:
        logger.info(f"  {bucket['key']}: {bucket['doc_count']:,}")

    logger.info("\nBy Year:")
    for bucket in aggs["aggregations"]["by_year"]["buckets"][:10]:
        logger.info(f"  {bucket['key']}: {bucket['doc_count']:,}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Consolidate communication data into comms_unified")
    parser.add_argument("--source", type=str, help="Process only this source (breach, kazaword, unified)")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--verify", action="store_true", help="Only verify existing index")
    parser.add_argument("--reset", action="store_true", help="Delete checkpoint and start fresh")
    args = parser.parse_args()

    # Source shortcuts
    source_shortcuts = {
        "breach": "breach_records",
        "kazaword": "kazaword_emails",
        "unified": "emails_unified",
    }

    # Connect
    es = Elasticsearch([ES_HOST], request_timeout=120, retry_on_timeout=True, max_retries=3)
    if not es.ping():
        logger.error("Cannot connect to Elasticsearch")
        return

    if args.verify:
        verify_consolidation(es)
        return

    if args.reset and CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        logger.info("Checkpoint deleted")

    checkpoint = load_checkpoint() if args.resume else {"completed_sources": [], "stats": {}}

    # Ensure target index
    ensure_target_index(es)

    # Process sources
    total_stats = {"indexed": 0, "failed": 0, "skipped": 0}

    if args.source:
        source_name = source_shortcuts.get(args.source, args.source)
        sources_to_process = [source_name]
    else:
        sources_to_process = ["breach_records", "kazaword_emails", "emails_unified"]

    if args.resume:
        sources_to_process = [s for s in sources_to_process if s not in checkpoint["completed_sources"]]

    logger.info(f"Sources to process: {sources_to_process}")

    for source_name in sources_to_process:
        if source_name == "breach_records":
            stats = consolidate_breach_records(es, checkpoint)
    # NOTE: kazaword_emails disabled - index does not exist
            continue

        total_stats["indexed"] += stats["indexed"]
        total_stats["failed"] += stats["failed"]
        total_stats["skipped"] += stats["skipped"]

        checkpoint["completed_sources"].append(source_name)
        checkpoint["stats"][source_name] = stats
        save_checkpoint(checkpoint)

    # Refresh
    logger.info("Refreshing index...")
    es.indices.refresh(index=TARGET_INDEX)

    logger.info(f"\n{'='*60}")
    logger.info("CONSOLIDATION COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Total indexed: {total_stats['indexed']:,}")
    logger.info(f"Total skipped: {total_stats['skipped']:,}")
    logger.info(f"Total failed: {total_stats['failed']:,}")

    verify_consolidation(es)


if __name__ == "__main__":
    main()
