#!/usr/bin/env python3
"""
C-3 Dataset Indexer - TOOL PROVIDER for Cymonides Agent

This module provides TOOLS that the Cymonides agent (Claude) uses to index datasets.
Claude does the thinking - analyzing data, deciding entity types, creating field mappings.
These tools just execute what Claude decides.

THE HOLY RULE: Preserve ABSOLUTELY EVERYTHING from each dataset.

Tools provided:
- load_dataset_sample() - Load sample records for Claude to analyze
- get_unified_indices() - Get available target indices and their schemas
- index_test_batch() - Index a test batch with Claude's mappings
- index_full() - Full indexing after Claude approves test results
- get_indexing_status() - Check status of indexing tasks

Usage by agent:
    1. Agent calls load_dataset_sample() to see the data
    2. Agent (Claude) THINKS about what entity type this is
    3. Agent (Claude) DECIDES field mappings
    4. Agent calls index_test_batch() with its decisions
    5. Agent reviews results and calls index_full() if approved
"""

import hashlib
import json
import logging
import csv
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Import from parent
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.canonical_standards import (
    INDEX_TIERS,
    C3_UNIFIED_SCHEMA,
    ERA_DEFINITIONS,
    get_era,
    get_decade,
    generate_node_id,
    canonical_value,
)
from memory.status_tracker import StatusTracker

# Elasticsearch
try:
    from elasticsearch import Elasticsearch
    from elasticsearch.helpers import bulk, scan
    HAS_ES = True
except ImportError:
    HAS_ES = False


# ============================================================================
# UNIFIED INDEX SCHEMAS (for Claude to reference)
# ============================================================================

UNIFIED_INDICES = {
    "domains_unified": {
        "entity_type": "domain",
        "description": "Web domains with rankings, WHOIS, DNS data",
        "primary_field": "domain",
        "example_fields": ["domain", "tld", "registrar", "created_date", "nameservers"],
    },
    "persons_unified": {
        "entity_type": "person",
        "description": "People/individuals with names, DOB, biographical data",
        "primary_field": "name",
        "example_fields": ["first_name", "last_name", "birth_date", "nationality"],
    },
    "companies_unified": {
        "entity_type": "company",
        "description": "Legal entities, corporations, organizations",
        "primary_field": "company_name",
        "example_fields": ["company_name", "reg_number", "jurisdiction", "status"],
    },
    "emails_unified": {
        "entity_type": "email",
        "description": "Email addresses with associated metadata",
        "primary_field": "email",
        "example_fields": ["email", "local_part", "domain"],
    },
    "phones_unified": {
        "entity_type": "phone",
        "description": "Phone numbers with carrier, location data",
        "primary_field": "phone",
        "example_fields": ["phone", "country_code", "carrier", "line_type"],
    },
    "geo_unified": {
        "entity_type": "location",
        "description": "Geographic locations, addresses, coordinates",
        "primary_field": "address",
        "example_fields": ["address", "city", "state", "country", "lat", "lon"],
    },
    "credentials_unified": {
        "entity_type": "credential",
        "description": "Username/password pairs from breaches",
        "primary_field": "username",
        "example_fields": ["username", "email", "password_hash"],
    },
    "political_contributions_unified": {
        "entity_type": "political_contribution",
        "description": "Campaign finance, FEC data, political donations",
        "primary_field": "transaction_id",
        "example_fields": ["candidate", "committee", "amount", "contributor", "date"],
    },
    "transactions_unified": {
        "entity_type": "financial_transaction",
        "description": "Financial transactions, payments, transfers",
        "primary_field": "transaction_id",
        "example_fields": ["amount", "currency", "sender", "receiver", "date"],
    },
}


# ============================================================================
# TOOL: LOAD DATASET SAMPLE
# ============================================================================

def load_dataset_sample(
    dataset_path: str,
    sample_size: int = 10
) -> Dict[str, Any]:
    """
    Load sample records from a dataset for Claude to analyze.

    Args:
        dataset_path: Path to dataset file (JSON, JSONL, CSV)
        sample_size: Number of records to sample (default 10)

    Returns:
        Dict with:
        - format: Detected file format
        - total_records: Estimated total count
        - fields: List of all field names found
        - sample_records: The actual sample data for Claude to examine
        - field_stats: For each field, type and example values
    """
    path = Path(dataset_path)
    result = {
        "dataset_path": str(path),
        "format": _detect_format(path),
        "total_records": 0,
        "fields": [],
        "sample_records": [],
        "field_stats": {},
    }

    # Load samples
    records = _load_records(path, result["format"], sample_size)
    result["sample_records"] = records

    if not records:
        result["error"] = "Could not load any records"
        return result

    # Discover fields
    all_fields = set()
    for record in records:
        all_fields.update(_flatten_keys(record))
    result["fields"] = sorted(all_fields)

    # Field stats (type + examples for Claude to see)
    for field_name in result["fields"]:
        values = []
        for record in records:
            val = _get_nested(record, field_name)
            if val is not None:
                values.append(val)

        if values:
            result["field_stats"][field_name] = {
                "type": type(values[0]).__name__,
                "examples": values[:3],  # First 3 non-null examples
                "non_null_count": len(values),
            }

    # Estimate total
    result["total_records"] = _estimate_total(path, result["format"])

    return result


def _detect_format(path: Path) -> str:
    """Detect file format."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    elif suffix == ".jsonl" or suffix == ".ndjson":
        return "jsonl"
    elif suffix == ".json":
        try:
            with open(path) as f:
                first = f.read(1)
            return "jsonl" if first == "{" else "json"
        except:
            return "json"
    return "unknown"


def _load_records(path: Path, fmt: str, limit: int) -> List[Dict]:
    """Load records from file."""
    records = []

    if fmt == "csv":
        try:
            with open(path, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for i, row in enumerate(reader):
                    if i >= limit:
                        break
                    records.append(dict(row))
        except Exception as e:
            logger.error(f"CSV load error: {e}")

    elif fmt == "jsonl":
        try:
            with open(path, encoding='utf-8') as f:
                for i, line in enumerate(f):
                    if i >= limit:
                        break
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except Exception as e:
            logger.error(f"JSONL load error: {e}")

    elif fmt == "json":
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                records = data[:limit]
            elif isinstance(data, dict):
                for key in ["data", "records", "results", "items", "rows"]:
                    if key in data and isinstance(data[key], list):
                        records = data[key][:limit]
                        break
        except Exception as e:
            logger.error(f"JSON load error: {e}")

    return records


def _flatten_keys(obj: Dict, prefix: str = "") -> List[str]:
    """Get all keys from nested dict."""
    keys = []
    for k, v in obj.items():
        full_key = f"{prefix}.{k}" if prefix else k
        keys.append(full_key)
        if isinstance(v, dict):
            keys.extend(_flatten_keys(v, full_key))
    return keys


def _get_nested(obj: Dict, key: str) -> Any:
    """Get value from nested key like 'foo.bar'."""
    parts = key.split(".")
    current = obj
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _estimate_total(path: Path, fmt: str) -> int:
    """Estimate total record count."""
    try:
        if fmt == "csv":
            with open(path) as f:
                return sum(1 for _ in f) - 1  # Minus header
        elif fmt == "jsonl":
            with open(path) as f:
                return sum(1 for _ in f)
        elif fmt == "json":
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, list):
                return len(data)
            for key in ["data", "records", "results", "items", "rows"]:
                if key in data and isinstance(data[key], list):
                    return len(data[key])
    except:
        pass
    return 0


# ============================================================================
# TOOL: GET UNIFIED INDICES
# ============================================================================

def get_unified_indices() -> Dict[str, Any]:
    """
    Get available unified indices and their schemas.

    Returns information about each index so Claude can decide
    which one is appropriate for a given dataset.
    """
    return {
        "indices": UNIFIED_INDICES,
        "holy_rule": (
            "When indexing to ANY unified index, you MUST preserve ALL original "
            "fields in source_records[].fields. Never discard data."
        ),
        "test_protocol": (
            "1. Index 100-1000 docs first\n"
            "2. Review results\n"
            "3. Adjust mappings if needed\n"
            "4. Full indexing only after approval"
        ),
    }


# ============================================================================
# TOOL: INDEX TEST BATCH
# ============================================================================

def index_test_batch(
    dataset_path: str,
    target_index: str,
    field_mappings: Dict[str, str],
    source_name: str,
    batch_size: int = 100,
    project_id: str = "default"
) -> Dict[str, Any]:
    """
    Index a test batch using Claude's field mappings.

    Args:
        dataset_path: Path to dataset
        target_index: Target unified index (e.g., "political_contributions_unified")
        field_mappings: Claude's mapping decisions {source_field: target_field}
        source_name: Name for source attribution
        batch_size: Number of records to test (default 100)
        project_id: Project ID for tracking

    Returns:
        Dict with success/error counts and sample indexed docs
    """
    tracker = StatusTracker(project_id)

    result = {
        "target_index": target_index,
        "batch_size": batch_size,
        "field_mappings": field_mappings,
        "success_count": 0,
        "error_count": 0,
        "sample_docs": [],
        "errors": [],
    }

    # Load sample
    path = Path(dataset_path)
    fmt = _detect_format(path)
    records = _load_records(path, fmt, batch_size)

    if not records:
        result["errors"].append("Could not load records")
        return result

    # Transform records
    transformed = []
    for i, record in enumerate(records):
        try:
            doc = _transform_record(
                record=record,
                target_index=target_index,
                field_mappings=field_mappings,
                source_name=source_name,
            )
            transformed.append(doc)
            result["success_count"] += 1

            # Keep samples
            if len(result["sample_docs"]) < 3:
                result["sample_docs"].append(doc)

        except Exception as e:
            result["error_count"] += 1
            result["errors"].append(f"Record {i}: {str(e)}")

    # Index to ES if available
    if HAS_ES and transformed:
        try:
            es = Elasticsearch(["http://localhost:9200"])
            test_index = f"{target_index}_test"

            # Create index if needed
            if not es.indices.exists(index=test_index):
                es.indices.create(index=test_index, body=_get_index_mapping())

            # Bulk index
            actions = [
                {"_index": test_index, "_id": doc["id"], "_source": doc}
                for doc in transformed
            ]
            success, errors = bulk(es, actions, raise_on_error=False)
            result["es_indexed"] = success
            result["es_errors"] = len(errors) if errors else 0
            result["test_index"] = test_index

        except Exception as e:
            result["es_error"] = str(e)

    # Track in memory
    task = tracker.add_indexing_task(
        tier="c-3",
        source=str(path),
        target_index=target_index,
        total_docs=batch_size,
        metadata={"phase": "test", "field_mappings": field_mappings}
    )
    tracker.record_test_results(
        task_id=task.task_id,
        batch_size=batch_size,
        success_count=result["success_count"],
        error_count=result["error_count"],
        sample_docs=result["sample_docs"],
        issues=result["errors"]
    )
    result["task_id"] = task.task_id

    return result


def _transform_record(
    record: Dict,
    target_index: str,
    field_mappings: Dict[str, str],
    source_name: str,
) -> Dict:
    """
    Transform a source record to unified format.

    THE HOLY RULE: Preserve EVERYTHING in source_records[].fields
    """
    index_def = UNIFIED_INDICES.get(target_index, {})
    entity_type = index_def.get("entity_type", "unknown")

    # Generate deterministic ID
    primary = index_def.get("primary_field", "id")
    id_value = None
    for src, tgt in field_mappings.items():
        if tgt == primary:
            id_value = _get_nested(record, src)
            break

    if not id_value:
        id_value = json.dumps(record, sort_keys=True)

    doc_id = generate_node_id(entity_type, str(id_value))

    # Build document
    doc = {
        "id": doc_id,
        "entity_type": entity_type,
        "indexed_at": datetime.utcnow().isoformat(),
    }

    # Apply Claude's field mappings
    for source_field, target_field in field_mappings.items():
        value = _get_nested(record, source_field)
        if value is not None:
            doc[target_field] = value

    # THE HOLY RULE: Preserve EVERYTHING
    doc["source_records"] = [{
        "source": source_name,
        "source_type": "file",
        "fields": record,  # ALL original fields preserved
        "ingested_at": datetime.utcnow().isoformat(),
    }]

    # Dimension keys for faceted search
    doc["dimension_keys"] = [
        f"source:{canonical_value(source_name)}",
        f"type:{entity_type}",
    ]

    # Temporal if we can find a year
    for field, value in record.items():
        if "year" in field.lower() or "date" in field.lower():
            year = _extract_year(value)
            if year:
                doc["temporal"] = {
                    "year": year,
                    "decade": get_decade(year),
                    "era": get_era(year),
                }
                doc["dimension_keys"].append(f"year:{year}")
                break

    doc["embedded_edges"] = []

    return doc


def _extract_year(value: Any) -> Optional[int]:
    """Extract year from value."""
    if isinstance(value, int) and 1900 <= value <= 2100:
        return value
    import re
    match = re.search(r"(19|20)\d{2}", str(value))
    return int(match.group()) if match else None


def _get_index_mapping() -> Dict:
    """Get ES mapping for unified index."""
    return {
        "settings": {"number_of_shards": 1, "refresh_interval": "5s"},
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "entity_type": {"type": "keyword"},
                "source_records": {"type": "nested"},
                "dimension_keys": {"type": "keyword"},
                "temporal": {"type": "object"},
                "embedded_edges": {"type": "nested"},
                "indexed_at": {"type": "date"},
            }
        }
    }


# ============================================================================
# TOOL: INDEX FULL
# ============================================================================

def index_full(
    dataset_path: str,
    target_index: str,
    field_mappings: Dict[str, str],
    source_name: str,
    batch_size: int = 2000,
    project_id: str = "default"
) -> Dict[str, Any]:
    """
    Full indexing after Claude approves test results.

    Args:
        dataset_path: Path to dataset
        target_index: Target unified index
        field_mappings: Claude's approved field mappings
        source_name: Source name for attribution
        batch_size: Bulk indexing batch size
        project_id: Project ID for tracking

    Returns:
        Dict with indexing results
    """
    tracker = StatusTracker(project_id)
    path = Path(dataset_path)
    fmt = _detect_format(path)

    result = {
        "target_index": target_index,
        "indexed_docs": 0,
        "failed_docs": 0,
        "started_at": datetime.utcnow().isoformat(),
    }

    if not HAS_ES:
        result["error"] = "Elasticsearch not available"
        return result

    try:
        es = Elasticsearch(["http://localhost:9200"])

        # Create index if needed
        if not es.indices.exists(index=target_index):
            es.indices.create(index=target_index, body=_get_index_mapping())

        # Stream and index
        batch = []
        seen_ids = set()

        for record in _stream_records(path, fmt):
            try:
                doc = _transform_record(record, target_index, field_mappings, source_name)

                if doc["id"] not in seen_ids:
                    seen_ids.add(doc["id"])
                    batch.append({
                        "_index": target_index,
                        "_id": doc["id"],
                        "_source": doc
                    })

                if len(batch) >= batch_size:
                    success, errors = bulk(es, batch, raise_on_error=False)
                    result["indexed_docs"] += success
                    result["failed_docs"] += len(errors) if errors else 0
                    batch = []

            except Exception as e:
                result["failed_docs"] += 1

        # Final batch
        if batch:
            success, errors = bulk(es, batch, raise_on_error=False)
            result["indexed_docs"] += success
            result["failed_docs"] += len(errors) if errors else 0

        es.indices.refresh(index=target_index)

    except Exception as e:
        result["error"] = str(e)

    result["completed_at"] = datetime.utcnow().isoformat()
    result["unique_entities"] = len(seen_ids) if 'seen_ids' in dir() else 0

    return result


def _stream_records(path: Path, fmt: str) -> Generator[Dict, None, None]:
    """Stream all records from dataset."""
    if fmt == "csv":
        with open(path, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                yield dict(row)

    elif fmt == "jsonl":
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    elif fmt == "json":
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            for record in data:
                yield record
        elif isinstance(data, dict):
            for key in ["data", "records", "results", "items", "rows"]:
                if key in data and isinstance(data[key], list):
                    for record in data[key]:
                        yield record
                    break


# ============================================================================
# TOOL: GET STATUS
# ============================================================================

def get_indexing_status(project_id: str = "default") -> Dict[str, Any]:
    """
    Get status of all indexing tasks.

    Returns:
        Dict with task status, progress, and history
    """
    tracker = StatusTracker(project_id)
    return tracker.get_project_status()


# ============================================================================
# CLI (for testing)
# ============================================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if len(sys.argv) < 2:
        print("Usage: python c3_dataset_indexer.py <dataset_path>")
        print("\nThis will load a sample for you to examine.")
        sys.exit(1)

    path = sys.argv[1]

    print(f"\n=== Loading sample from: {path} ===\n")
    sample = load_dataset_sample(path, sample_size=5)

    print(f"Format: {sample['format']}")
    print(f"Total records: {sample['total_records']:,}")
    print(f"Fields found: {len(sample['fields'])}")

    print("\nFields and examples:")
    for field, stats in sample["field_stats"].items():
        examples = stats["examples"][:2]
        print(f"  {field}: {stats['type']} -> {examples}")

    print("\n=== Available target indices ===")
    indices = get_unified_indices()
    for name, defn in indices["indices"].items():
        print(f"  {name}: {defn['description']}")

    print("\nSample records:")
    for i, record in enumerate(sample["sample_records"][:2]):
        print(f"\n  Record {i+1}:")
        print(f"  {json.dumps(record, indent=4, default=str)[:500]}...")
