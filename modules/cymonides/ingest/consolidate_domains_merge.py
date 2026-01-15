#!/usr/bin/env python3
"""
consolidate_domains_merge.py - Domain consolidation with MERGE logic

CRITICAL: This script MERGES data, never overwrites.
- Same domain from multiple sources → ONE document with ALL data
- Rankings stored as: ranks.tranco, ranks.majestic, ranks.authority
- Arrays (sources, categories) are MERGED, not replaced
- All source-specific fields preserved under namespaced keys

Target: domains_unified (canonical domain index)
"""
import hashlib
import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional, Set

from elasticsearch import Elasticsearch
from elasticsearch.helpers import scan, bulk

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/data/CYMONIDES/ingest/consolidate_domains_merge.log")
    ]
)
logger = logging.getLogger(__name__)

ES_HOST = "http://localhost:9200"
TARGET_INDEX = "domains_unified"
BATCH_SIZE = 500

# Fields that should be merged as arrays (not overwritten)
ARRAY_MERGE_FIELDS = [
    "sources", "categories", "all_categories", "schema_types",
    "languages", "countries", "social_links", "linked_companies",
    "linked_people", "wdc_entity_names", "curlie_paths",
]

# Fields that represent rankings from different sources
RANKING_FIELDS = {
    "tranco_rank": "tranco",
    "majestic_rank": "majestic",
    "majestic_tld_rank": "majestic_tld",
    "authority_rank": "authority",
    "authority_score": "authority_score",
    "rank": "generic",  # Will be attributed to source
    "tld_rank": "tld",
    "best_rank": "best",
}


def normalize_domain(domain: str) -> str:
    """Normalize domain to lowercase, strip www."""
    if not domain:
        return ""
    d = domain.lower().strip()
    if d.startswith("www."):
        d = d[4:]
    return d


def merge_arrays(existing: Any, new: Any) -> List:
    """Merge two values into a deduplicated array."""
    result = set()

    if existing:
        if isinstance(existing, list):
            result.update(existing)
        else:
            result.add(existing)

    if new:
        if isinstance(new, list):
            result.update(new)
        else:
            result.add(new)

    return list(result)


def merge_documents(existing: Dict, new_doc: Dict, source_name: str) -> Dict:
    """
    Merge new_doc into existing, preserving all data.

    Rules:
    1. Array fields: MERGE (deduplicate)
    2. Ranking fields: Store under ranks.{source}
    3. Scalar fields: Keep existing if set, otherwise use new
    4. Source-specific fields: Namespace under {source}.{field}
    """
    merged = existing.copy()

    # Track sources
    sources = merge_arrays(merged.get("sources"), source_name)
    merged["sources"] = sources

    # Initialize ranks object if not exists
    if "ranks" not in merged:
        merged["ranks"] = {}

    for key, value in new_doc.items():
        if value is None:
            continue

        # Skip domain - it's the key
        if key == "domain":
            continue

        # Handle ranking fields - store with source attribution
        if key in RANKING_FIELDS:
            rank_key = RANKING_FIELDS[key]
            # If generic "rank", attribute to source
            if key == "rank":
                rank_key = source_name
            merged["ranks"][rank_key] = value
            # Also keep flat field for backwards compat
            if key not in merged or merged[key] is None:
                merged[key] = value
            continue

        # Handle array merge fields
        if key in ARRAY_MERGE_FIELDS:
            merged[key] = merge_arrays(merged.get(key), value)
            continue

        # Handle nested objects (merge recursively)
        if isinstance(value, dict):
            if key not in merged or not isinstance(merged.get(key), dict):
                merged[key] = {}
            for sub_key, sub_value in value.items():
                if sub_value is not None:
                    if merged[key].get(sub_key) is None:
                        merged[key][sub_key] = sub_value
            continue

        # Scalar fields: keep existing if set
        if key not in merged or merged[key] is None:
            merged[key] = value

    # Update timestamp
    merged["last_updated"] = datetime.utcnow().isoformat()

    return merged


def generate_dimension_keys(doc: Dict) -> List[str]:
    """Generate dimension_keys for intersection queries."""
    keys = []

    # TLD dimension
    domain = doc.get("domain", "")
    if domain:
        parts = domain.rsplit(".", 1)
        if len(parts) == 2:
            keys.append(f"tld:{parts[1]}")

    # Authority dimension from ranks
    ranks = doc.get("ranks", {})
    best_rank = None
    for rank_source, rank_value in ranks.items():
        if isinstance(rank_value, (int, float)) and rank_value > 0:
            if best_rank is None or rank_value < best_rank:
                best_rank = rank_value

    if best_rank:
        if best_rank <= 1000:
            keys.append("auth:top1k")
        elif best_rank <= 10000:
            keys.append("auth:top10k")
        elif best_rank <= 100000:
            keys.append("auth:top100k")
        elif best_rank <= 1000000:
            keys.append("auth:top1m")

    # Country dimension
    country = doc.get("country") or doc.get("primary_country")
    if country:
        keys.append(f"jur:{country.lower()}")

    # Source dimensions
    for src in doc.get("sources", []):
        keys.append(f"source:{src}")

    return keys


def consolidate_domains(es: Elasticsearch):
    """
    Consolidate all domains_unified records into properly merged documents.

    Strategy:
    1. Scan all documents grouped by domain
    2. Merge all records for same domain
    3. Reindex merged document
    """
    logger.info("="*60)
    logger.info("DOMAIN MERGE CONSOLIDATION START")
    logger.info("="*60)

    # Get total count
    total = es.count(index=TARGET_INDEX)["count"]
    logger.info(f"Total documents to process: {total:,}")

    # We'll aggregate by domain
    # First, get all unique domains with their doc counts
    logger.info("Scanning for domains with multiple records...")

    # Use aggregation to find domains with >1 record
    agg_result = es.search(
        index=TARGET_INDEX,
        body={
            "size": 0,
            "aggs": {
                "duplicate_domains": {
                    "terms": {
                        "field": "domain",
                        "min_doc_count": 2,
                        "size": 100000
                    }
                }
            }
        }
    )

    duplicate_domains = [b["key"] for b in agg_result["aggregations"]["duplicate_domains"]["buckets"]]
    logger.info(f"Found {len(duplicate_domains):,} domains with multiple records")

    if not duplicate_domains:
        logger.info("No duplicates to merge!")
        return

    # Process each duplicate domain
    merged_count = 0
    deleted_count = 0

    for i, domain in enumerate(duplicate_domains):
        if i % 1000 == 0:
            logger.info(f"Processing domain {i:,}/{len(duplicate_domains):,}: {domain}")

        # Get all docs for this domain
        result = es.search(
            index=TARGET_INDEX,
            body={
                "query": {"term": {"domain": domain}},
                "size": 100
            }
        )

        hits = result["hits"]["hits"]
        if len(hits) < 2:
            continue

        # Merge all docs
        merged = {"domain": domain}
        doc_ids_to_delete = []

        for hit in hits:
            source = hit["_source"]
            source_name = "unknown"

            # Determine source
            if source.get("sources"):
                source_name = source["sources"][0] if isinstance(source["sources"], list) else source["sources"]
            elif source.get("source"):
                source_name = source["source"]
            elif source.get("cc_source"):
                source_name = "common_crawl"
            elif source.get("doc_type"):
                source_name = source["doc_type"]

            merged = merge_documents(merged, source, source_name)
            doc_ids_to_delete.append(hit["_id"])

        # Generate dimension_keys
        merged["dimension_keys"] = generate_dimension_keys(merged)

        # Use domain as the canonical ID
        canonical_id = hashlib.sha256(f"domain:{domain}".encode()).hexdigest()[:16]

        # Delete old docs and index merged
        for doc_id in doc_ids_to_delete:
            if doc_id != canonical_id:
                try:
                    es.delete(index=TARGET_INDEX, id=doc_id, ignore=[404])
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete {doc_id}: {e}")

        # Index merged document
        es.index(index=TARGET_INDEX, id=canonical_id, body=merged)
        merged_count += 1

    # Refresh index
    es.indices.refresh(index=TARGET_INDEX)

    logger.info("="*60)
    logger.info(f"CONSOLIDATION COMPLETE")
    logger.info(f"  Merged: {merged_count:,} domains")
    logger.info(f"  Deleted: {deleted_count:,} duplicate records")
    logger.info("="*60)

    # Verify
    new_total = es.count(index=TARGET_INDEX)["count"]
    logger.info(f"New total: {new_total:,} (was {total:,})")


def main():
    es = Elasticsearch([ES_HOST])

    if not es.ping():
        logger.error("Cannot connect to Elasticsearch")
        sys.exit(1)

    consolidate_domains(es)


if __name__ == "__main__":
    main()
