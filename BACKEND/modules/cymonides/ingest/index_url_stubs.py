#!/usr/bin/env python3
"""
Index URL-only stubs to cymonides-2 from multiple sources.

TIER STRATEGY (as per user spec):
1. URL-ONLY STUBS: ALL URLs indexed (millions) - just URL, domain, source_type
2. PRIORITY EXTRACTION: ~60K from parquet get full content + concept extraction
3. HIGH-VALUE EMBEDDINGS: Subset of priority docs get 768-dim content_embedding

This script handles Tier 1: URL-only stubs from:
- finepdfs-corporate (881K)
- affiliate_linkedin_companies (2.85M)
- linkedin_unified (2.88M)
- companies_unified (3.2M)

Usage:
    python index_url_stubs.py --source finepdfs-corporate
    python index_url_stubs.py --source affiliate_linkedin_companies
    python index_url_stubs.py --source all
    python index_url_stubs.py --count-only
"""

import hashlib
import logging
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Iterator, Dict, Optional

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk, scan

# Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Config
ES_HOST = "http://localhost:9200"
TARGET_INDEX = "cymonides-2"
BATCH_SIZE = 1000

# Source configurations
SOURCES = {
    "finepdfs-corporate": {
        "url_field": "url",
        "domain_field": "domain",
        "source_type": "cc-pdf-2025",
        "extra_fields": ["language", "jurisdiction", "priority_score"],
    },
    "affiliate_linkedin_companies": {
        "url_field": "linkedin_url",
        "domain_field": "domain",
        "source_type": "linkedin-company",
        "extra_fields": ["company_name", "industry", "website_url"],
        "secondary_url_field": "website_url",  # Also index website as separate stub
    },
    "linkedin_unified": {
        "url_field": "linkedin_url",
        "domain_field": None,  # No domain field
        "source_type": "linkedin-profile",
        "extra_fields": ["name", "title"],
    },
    "companies_unified": {
        "url_field": "website_url",
        "domain_field": None,
        "source_type": "company-website",
        "extra_fields": ["name", "linkedin_url"],
    },
}


def generate_stub_id(url: str, source_type: str) -> str:
    """Generate deterministic ID for URL stub."""
    return f"{source_type}_{hashlib.md5(url.encode()).hexdigest()}"


def extract_domain_from_url(url: str) -> Optional[str]:
    """Extract domain from URL."""
    if not url:
        return None
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc.lower().replace('www.', '')
    except:
        return None


def build_stub_document(
    source_doc: Dict,
    source_config: Dict,
    source_index: str
) -> Optional[Dict]:
    """Build URL-only stub document for cymonides-2."""
    url_field = source_config["url_field"]
    url = source_doc.get(url_field)

    if not url or not isinstance(url, str):
        return None

    # Get or extract domain
    domain = None
    if source_config.get("domain_field"):
        domain = source_doc.get(source_config["domain_field"])
    if not domain:
        domain = extract_domain_from_url(url)

    source_type = source_config["source_type"]
    doc_id = generate_stub_id(url, source_type)

    stub = {
        "id": doc_id,
        "source_url": url,
        "source_domain": domain or "",
        "source_type": source_type,
        "source_index": source_index,
        "is_stub": True,  # Flag to identify URL-only stubs
        "indexed_at": datetime.utcnow().isoformat() + "Z",
        "content": "",  # Empty - stubs have no content
        "title": "",
        "metadata": {
            "stub_source": source_index,
        },
    }

    # Copy extra fields to metadata
    for field in source_config.get("extra_fields", []):
        if field in source_doc and source_doc[field]:
            stub["metadata"][field] = source_doc[field]

    # Use company_name/name as title if available
    if "company_name" in source_doc and source_doc["company_name"]:
        stub["title"] = source_doc["company_name"]
    elif "name" in source_doc and source_doc["name"]:
        stub["title"] = source_doc["name"]

    return stub


def iter_source_documents(
    es: Elasticsearch,
    source_index: str,
    source_config: Dict
) -> Iterator[Dict]:
    """Iterate over source documents, yielding stub documents."""
    url_field = source_config["url_field"]

    query = {
        "query": {
            "exists": {"field": url_field}
        },
        "_source": [url_field] +
                  ([source_config["domain_field"]] if source_config.get("domain_field") else []) +
                  source_config.get("extra_fields", []) +
                  ([source_config["secondary_url_field"]] if source_config.get("secondary_url_field") else [])
    }

    for doc in scan(es, index=source_index, query=query, scroll='5m', size=1000):
        source_doc = doc["_source"]

        # Primary URL
        stub = build_stub_document(source_doc, source_config, source_index)
        if stub:
            yield stub

        # Secondary URL (e.g., website_url for LinkedIn companies)
        if source_config.get("secondary_url_field"):
            secondary_url = source_doc.get(source_config["secondary_url_field"])
            if secondary_url and secondary_url != source_doc.get(url_field):
                # Create config for secondary URL
                secondary_config = source_config.copy()
                secondary_config["url_field"] = source_config["secondary_url_field"]
                secondary_config["source_type"] = "company-website"
                secondary_stub = build_stub_document(source_doc, secondary_config, source_index)
                if secondary_stub:
                    yield secondary_stub


def index_stubs_from_source(es: Elasticsearch, source_index: str) -> Dict:
    """Index URL stubs from a source index."""
    if source_index not in SOURCES:
        logger.error(f"Unknown source: {source_index}")
        return {"indexed": 0, "failed": 0}

    source_config = SOURCES[source_index]

    logger.info(f"Indexing stubs from {source_index}...")
    logger.info(f"  URL field: {source_config['url_field']}")
    logger.info(f"  Source type: {source_config['source_type']}")

    total_indexed = 0
    total_failed = 0
    actions = []

    for stub in iter_source_documents(es, source_index, source_config):
        actions.append({
            "_index": TARGET_INDEX,
            "_id": stub["id"],
            "_source": stub,
        })

        if len(actions) >= BATCH_SIZE:
            success, failed = bulk(es, actions, raise_on_error=False, stats_only=True)
            total_indexed += success
            total_failed += failed
            logger.info(f"  Indexed batch: {success} ok, {failed} failed (total: {total_indexed:,})")
            actions = []

    # Final batch
    if actions:
        success, failed = bulk(es, actions, raise_on_error=False, stats_only=True)
        total_indexed += success
        total_failed += failed
        logger.info(f"  Final batch: {success} ok, {failed} failed")

    logger.info(f"  Completed: {total_indexed:,} indexed, {total_failed:,} failed")
    return {"indexed": total_indexed, "failed": total_failed}


def count_sources(es: Elasticsearch):
    """Count documents in each source index."""
    logger.info("Counting source documents...")
    for source_index, config in SOURCES.items():
        try:
            count = es.count(index=source_index)["count"]
            logger.info(f"  {source_index}: {count:,} docs")
        except Exception as e:
            logger.warning(f"  {source_index}: ERROR - {e}")

    # Count existing stubs in target
    try:
        stub_count = es.count(
            index=TARGET_INDEX,
            body={"query": {"term": {"is_stub": True}}}
        )["count"]
        logger.info(f"  {TARGET_INDEX} (existing stubs): {stub_count:,}")
    except Exception as e:
        logger.warning(f"  {TARGET_INDEX} stubs: ERROR - {e}")


def main():
    parser = argparse.ArgumentParser(description="Index URL stubs to cymonides-2")
    parser.add_argument('--source', type=str, default='all',
                       help=f"Source index to process: {list(SOURCES.keys())} or 'all'")
    parser.add_argument('--count-only', action='store_true',
                       help="Only count documents, don't index")
    args = parser.parse_args()

    es = Elasticsearch([ES_HOST], request_timeout=120, retry_on_timeout=True, max_retries=3)

    if not es.ping():
        logger.error("Cannot connect to Elasticsearch!")
        return False

    if args.count_only:
        count_sources(es)
        return True

    if args.source == 'all':
        sources_to_process = list(SOURCES.keys())
    else:
        if args.source not in SOURCES:
            logger.error(f"Unknown source: {args.source}")
            logger.info(f"Available sources: {list(SOURCES.keys())}")
            return False
        sources_to_process = [args.source]

    logger.info(f"Processing sources: {sources_to_process}")

    results = {}
    for source in sources_to_process:
        results[source] = index_stubs_from_source(es, source)

    # Summary
    logger.info("\n" + "="*60)
    logger.info("STUB INDEXING COMPLETE")
    logger.info("="*60)
    total_indexed = sum(r["indexed"] for r in results.values())
    total_failed = sum(r["failed"] for r in results.values())
    logger.info(f"Total indexed: {total_indexed:,}")
    logger.info(f"Total failed: {total_failed:,}")
    for source, result in results.items():
        logger.info(f"  {source}: {result['indexed']:,} indexed, {result['failed']:,} failed")

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
