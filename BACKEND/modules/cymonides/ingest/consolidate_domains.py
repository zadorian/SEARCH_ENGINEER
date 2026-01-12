#!/usr/bin/env python3
"""
consolidate_domains.py - Domain consolidation into domains_unified

Target: domains_unified (canonical domain index)
Sources:
  - wdc-domain-profiles (246K) - WDC domain profiles
  - unified_domain_profiles (5.8M) - Previously unified profiles
  - top_domains (8.6M) - Top domain rankings
  - Any future domain sources

Following the {entity}_unified naming convention.
"""
import hashlib
import logging
import sys
from datetime import datetime
from typing import Any, Dict, Generator, Optional

from elasticsearch import Elasticsearch
from elasticsearch.helpers import scan, bulk

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/data/CYMONIDES/ingest/consolidate_domains.log")
    ]
)
logger = logging.getLogger(__name__)

TARGET_INDEX = "domains_unified"

# Source indices with their doc counts and field mappings
SOURCES = [
    {
        "index": "wdc-domain-profiles",
        "doc_type": "wdc_domain",
        "field_map": {
            "domain": "domain",
            "url": "url",
            "schema_types": "schema_types",
            "wdc_confidence": "wdc_confidence",
            "wdc_entity_count": "wdc_entity_count",
            "wdc_entity_names": "wdc_entity_names",
        }
    },
    {
        "index": "top_domains",
        "doc_type": "top_domain",
        "field_map": {
            "domain": "domain",
            "rank": "rank",
            "tranco_rank": "tranco_rank",
        }
    },
]

def generate_domain_id(domain: str) -> str:
    """Generate deterministic ID for a domain."""
    return hashlib.sha256(f"domain:{domain.lower().strip()}".encode()).hexdigest()[:16]

def normalize_domain(domain: str) -> str:
    """Normalize domain to lowercase, strip www."""
    if not domain:
        return ""
    d = domain.lower().strip()
    if d.startswith("www."):
        d = d[4:]
    return d

def generate_dimension_keys(doc: Dict) -> list:
    """Generate dimension_keys for intersection queries."""
    keys = []
    
    # TLD dimension
    domain = doc.get("domain", "")
    if domain:
        parts = domain.rsplit(".", 1)
        if len(parts) == 2:
            keys.append(f"tld:{parts[1]}")
    
    # Authority dimension
    rank = doc.get("rank") or doc.get("tranco_rank")
    if rank and isinstance(rank, (int, float)):
        if rank <= 10000:
            keys.append("auth:top10k")
        elif rank <= 100000:
            keys.append("auth:top100k")
        elif rank <= 1000000:
            keys.append("auth:top1m")
    
    # Country dimension
    country = doc.get("country") or doc.get("primary_country")
    if country:
        keys.append(f"jur:{country.lower()}")
    
    # Category dimensions
    categories = doc.get("categories") or doc.get("all_categories") or []
    if isinstance(categories, list):
        for cat in categories[:5]:  # Limit to 5 categories
            keys.append(f"sector:{cat.lower().replace( , _)}")
    
    return keys

def transform_document(source_doc: Dict, source_config: Dict) -> Dict:
    """Transform source document to domains_unified schema."""
    field_map = source_config.get("field_map", {})
    doc_type = source_config.get("doc_type", "domain")
    
    # Map fields
    target_doc = {}
    for source_field, target_field in field_map.items():
        if source_field in source_doc:
            target_doc[target_field] = source_doc[source_field]
    
    # Ensure required fields
    domain = normalize_domain(target_doc.get("domain", ""))
    if not domain:
        return None
    
    target_doc["domain"] = domain
    target_doc["doc_type"] = doc_type
    target_doc["indexed_at"] = datetime.utcnow().isoformat()
    
    # Generate dimension_keys
    target_doc["dimension_keys"] = generate_dimension_keys(target_doc)
    
    # Add source tracking
    existing_sources = target_doc.get("sources", [])
    if source_config["index"] not in existing_sources:
        if isinstance(existing_sources, list):
            existing_sources.append(source_config["index"])
        else:
            existing_sources = [source_config["index"]]
    target_doc["sources"] = existing_sources
    
    return target_doc

def scroll_source(es: Elasticsearch, source_config: Dict, batch_size: int = 1000) -> Generator:
    """Scroll through source index and yield transformed documents."""
    index = source_config["index"]
    logger.info(f"Scrolling source: {index}")
    
    for hit in scan(es, index=index, query={"query": {"match_all": {}}}, size=batch_size):
        source_doc = hit["_source"]
        target_doc = transform_document(source_doc, source_config)
        
        if target_doc:
            domain = target_doc["domain"]
            doc_id = generate_domain_id(domain)
            
            yield {
                "_op_type": "update",
                "_index": TARGET_INDEX,
                "_id": doc_id,
                "doc": target_doc,
                "doc_as_upsert": True
            }

def consolidate_source(es: Elasticsearch, source_config: Dict, batch_size: int = 1000):
    """Consolidate a single source into domains_unified."""
    index = source_config["index"]
    
    # Check if source exists
    if not es.indices.exists(index=index):
        logger.warning(f"Source index {index} does not exist, skipping")
        return 0
    
    source_count = es.count(index=index)["count"]
    logger.info(f"Starting consolidation of {index} ({source_count:,} docs)")
    
    processed = 0
    errors = 0
    
    for success, info in bulk(es, scroll_source(es, source_config, batch_size), chunk_size=batch_size):
        if success:
            processed += 1
        else:
            errors += 1
            if errors < 10:
                logger.error(f"Error: {info}")
        
        if processed % 100000 == 0:
            logger.info(f"  {processed:,} processed from {index}")
    
    logger.info(f"Completed {index}: {processed:,} upserted, {errors:,} errors")
    return processed

def verify_consolidation(es: Elasticsearch):
    """Verify the consolidated index."""
    if not es.indices.exists(index=TARGET_INDEX):
        logger.error(f"Target index {TARGET_INDEX} does not exist")
        return
    
    count = es.count(index=TARGET_INDEX)["count"]
    logger.info(f"VERIFICATION: {TARGET_INDEX} = {count:,} documents")
    
    # Sample dimension_keys
    result = es.search(
        index=TARGET_INDEX,
        body={
            "size": 0,
            "aggs": {
                "dimension_keys": {
                    "terms": {"field": "dimension_keys", "size": 20}
                }
            }
        }
    )
    
    keys = result["aggregations"]["dimension_keys"]["buckets"]
    logger.info(f"Top dimension_keys: {[k['key'] for k in keys[:10]]}")

def main():
    es = Elasticsearch(["http://localhost:9200"])
    
    logger.info("="*60)
    logger.info("DOMAINS CONSOLIDATION START")
    logger.info(f"Target: {TARGET_INDEX}")
    logger.info("="*60)
    
    # Ensure target exists
    if not es.indices.exists(index=TARGET_INDEX):
        logger.error(f"Target index {TARGET_INDEX} does not exist - run initial setup first")
        sys.exit(1)
    
    total_processed = 0
    
    for source_config in SOURCES:
        processed = consolidate_source(es, source_config)
        total_processed += processed
    
    es.indices.refresh(index=TARGET_INDEX)
    
    logger.info("="*60)
    logger.info(f"CONSOLIDATION COMPLETE: {total_processed:,} total processed")
    logger.info("="*60)
    
    verify_consolidation(es)

if __name__ == "__main__":
    main()
