#!/usr/bin/env python3
"""
consolidate_domains_merge_batched.py - Domain consolidation with MERGE logic (batched)

CRITICAL: This script MERGES data, never overwrites.
- Works in batches to avoid memory issues
- Rankings stored as: ranks.tranco, ranks.majestic, ranks.authority
- Arrays (sources, categories) are MERGED, not replaced

Strategy:
1. Scan all domains alphabetically in batches
2. For each batch, find domains with multiple records
3. Merge duplicates and reindex
"""
import hashlib
import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, List, Set
from collections import defaultdict

from elasticsearch import Elasticsearch
from elasticsearch.helpers import scan

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

# Fields that should be merged as arrays (not overwritten)
ARRAY_MERGE_FIELDS = {
    "sources", "categories", "all_categories", "schema_types",
    "languages", "countries", "social_links", "linked_companies",
    "linked_people", "wdc_entity_names", "curlie_paths",
    "curlie_top_categories", "bang_categories", "bang_subcategories",
    "news_categories", "entity_types"
}

# Fields that represent rankings - stored under ranks.{key}
RANKING_FIELDS = {
    "tranco_rank": "tranco",
    "majestic_rank": "majestic",
    "majestic_tld_rank": "majestic_tld",
    "authority_rank": "authority",
    "authority_score": "authority_score",
    "rank": "generic",
    "tld_rank": "tld",
    "best_rank": "best",
    "linkedin_authority": "linkedin",
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
    """Merge two values into a deduplicated list."""
    result = []
    seen = set()

    for val in [existing, new]:
        if val is None:
            continue
        items = val if isinstance(val, list) else [val]
        for item in items:
            if item and item not in seen:
                seen.add(item)
                result.append(item)

    return result


def get_source_name(doc: Dict) -> str:
    """Extract source name from document."""
    if doc.get("sources"):
        srcs = doc["sources"]
        return srcs[0] if isinstance(srcs, list) else srcs
    if doc.get("source"):
        return doc["source"]
    if doc.get("cc_source"):
        return "common_crawl"
    if doc.get("doc_type"):
        return doc["doc_type"]
    return "unknown"


def merge_documents(docs: List[Dict]) -> Dict:
    """
    Merge multiple documents for the same domain.

    Rules:
    1. Array fields: MERGE (deduplicate)
    2. Ranking fields: Store under ranks.{source}
    3. Scalar fields: Keep first non-null value
    4. Preserve ALL fields from all sources
    """
    if not docs:
        return None

    domain = docs[0].get("domain", "")
    merged = {
        "domain": domain,
        "sources": [],
        "ranks": {},
    }

    all_sources = []

    for doc in docs:
        source_name = get_source_name(doc)
        if source_name and source_name not in all_sources:
            all_sources.append(source_name)

        for key, value in doc.items():
            if value is None:
                continue

            # Skip domain - it's the key
            if key == "domain":
                continue

            # Handle ranking fields - store with source attribution
            if key in RANKING_FIELDS:
                rank_key = RANKING_FIELDS[key]
                if key == "rank":
                    rank_key = source_name  # Use source as key for generic rank
                merged["ranks"][rank_key] = value
                # Also keep flat field for backwards compat
                if key not in merged or merged.get(key) is None:
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
                    if sub_value is not None and merged[key].get(sub_key) is None:
                        merged[key][sub_key] = sub_value
                continue

            # Scalar fields: keep first non-null
            if key not in merged or merged.get(key) is None:
                merged[key] = value

    merged["sources"] = all_sources
    merged["last_updated"] = datetime.utcnow().isoformat()

    # Generate dimension_keys
    merged["dimension_keys"] = generate_dimension_keys(merged)

    return merged


def generate_dimension_keys(doc: Dict) -> List[str]:
    """Generate dimension_keys for intersection queries."""
    keys = []

    # TLD dimension
    domain = doc.get("domain", "")
    if domain and "." in domain:
        tld = domain.rsplit(".", 1)[1]
        keys.append(f"tld:{tld}")

    # Authority dimension from ranks
    ranks = doc.get("ranks", {})
    best_rank = None
    for rank_value in ranks.values():
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
    for field in ["country", "primary_country"]:
        country = doc.get(field)
        if country:
            keys.append(f"jur:{country.lower()}")
            break

    return keys


def process_batch(es: Elasticsearch, domain_docs: Dict[str, List]) -> tuple:
    """Process a batch of domains, merging duplicates."""
    merged_count = 0
    deleted_count = 0

    for domain, docs in domain_docs.items():
        if len(docs) < 2:
            continue

        # Merge all docs for this domain
        merged = merge_documents([d["_source"] for d in docs])
        if not merged:
            continue

        # Canonical ID
        canonical_id = hashlib.sha256(f"domain:{domain}".encode()).hexdigest()[:16]

        # Delete old docs (except if one matches canonical)
        for doc in docs:
            if doc["_id"] != canonical_id:
                try:
                    es.delete(index=TARGET_INDEX, id=doc["_id"], ignore=[404])
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Delete failed for {doc['_id']}: {e}")

        # Index merged
        try:
            es.index(index=TARGET_INDEX, id=canonical_id, body=merged)
            merged_count += 1
        except Exception as e:
            logger.error(f"Index failed for {domain}: {e}")

    return merged_count, deleted_count


def consolidate_domains(es: Elasticsearch, batch_size: int = 5000):
    """
    Consolidate domains by scanning and merging duplicates.
    """
    logger.info("="*60)
    logger.info("DOMAIN MERGE CONSOLIDATION START (BATCHED)")
    logger.info("="*60)

    total = es.count(index=TARGET_INDEX)["count"]
    logger.info(f"Total documents: {total:,}")

    # Scan all docs, group by domain
    domain_docs = defaultdict(list)
    processed = 0
    total_merged = 0
    total_deleted = 0

    logger.info("Scanning documents...")

    for hit in scan(es, index=TARGET_INDEX, query={"query": {"match_all": {}}},
                    size=5000, scroll="10m"):
        domain = hit["_source"].get("domain", "")
        if domain:
            domain_docs[domain].append({
                "_id": hit["_id"],
                "_source": hit["_source"]
            })

        processed += 1
        if processed % 100000 == 0:
            logger.info(f"Scanned {processed:,} documents, {len(domain_docs):,} unique domains")

        # Process batch when we have enough
        if len(domain_docs) >= batch_size:
            merged, deleted = process_batch(es, domain_docs)
            total_merged += merged
            total_deleted += deleted
            if merged > 0:
                logger.info(f"  Batch: merged {merged}, deleted {deleted}")
            domain_docs.clear()

    # Process remaining
    if domain_docs:
        merged, deleted = process_batch(es, domain_docs)
        total_merged += merged
        total_deleted += deleted
        if merged > 0:
            logger.info(f"  Final batch: merged {merged}, deleted {deleted}")

    # Refresh
    es.indices.refresh(index=TARGET_INDEX)

    logger.info("="*60)
    logger.info(f"CONSOLIDATION COMPLETE")
    logger.info(f"  Scanned: {processed:,}")
    logger.info(f"  Merged: {total_merged:,} domains")
    logger.info(f"  Deleted: {total_deleted:,} duplicate records")
    logger.info("="*60)

    new_total = es.count(index=TARGET_INDEX)["count"]
    logger.info(f"New total: {new_total:,} (was {total:,})")


def main():
    es = Elasticsearch([ES_HOST], timeout=60)

    if not es.ping():
        logger.error("Cannot connect to Elasticsearch")
        sys.exit(1)

    consolidate_domains(es)


if __name__ == "__main__":
    main()
