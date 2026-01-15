#!/usr/bin/env python3
"""
UK_PROPERTY_UNIFIED CONSOLIDATION SCRIPT

Consolidates UK Land Registry data from multiple sources into a unified uk_property_unified index.

Sources:
  - uk_ccod (4.3M) - Corporate and Commercial Ownership Data
  - uk_ocod (92K) - Overseas Company Ownership Data
  - uk_addresses (4.3M) - Address and ownership records
  - uk_leases (7.7M) - Lease records

Target: uk_property_unified

Core Contract (4 fields):
  - subject: [title_number] if known
  - concepts: [] (property type concepts)
  - dimension_keys: Normalized facets (jur:uk, region:, postcode:, tenure:, etc.)
  - doc_type: "property"

ID Strategy: Deterministic hash-based IDs
  - For CCOD/OCOD: hash(source + title_number)
  - For leases: hash(source + unique_id or uprn)
  - Enables idempotent re-runs

Usage:
    python consolidate_uk_property.py                 # Full run
    python consolidate_uk_property.py --source ccod   # Only uk_ccod
    python consolidate_uk_property.py --resume        # Resume from checkpoint
    python consolidate_uk_property.py --verify        # Verify only
"""

import hashlib
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

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
TARGET_INDEX = "uk_property_unified"
BATCH_SIZE = 1500
SCROLL_SIZE = 5000
SCROLL_TIMEOUT = "10m"

# Checkpoint file
CHECKPOINT_FILE = Path(__file__).parent / "uk_property_checkpoint.json"

# Source configurations
SOURCES = {
    "uk_ccod": {
        "index": "uk_ccod",
        "id_field": "title_number",
        "priority": 1,  # Primary source for title-based records
    },
    "uk_ocod": {
        "index": "uk_ocod",
        "id_field": "title_number",
        "priority": 2,  # Overseas company data
    },
    "uk_addresses": {
        "index": "uk_addresses",
        "id_field": "title_number",  # May also use uprn
        "priority": 3,
    },
    "uk_leases": {
        "index": "uk_leases",
        "id_field": "unique_id",  # Leases have unique_id
        "priority": 4,
    },
}

# UK Region normalization
UK_REGIONS = {
    "greater london": "london",
    "inner london": "london",
    "outer london": "london",
    "south east": "south_east",
    "south west": "south_west",
    "east of england": "east",
    "east anglia": "east",
    "west midlands": "west_midlands",
    "east midlands": "east_midlands",
    "north east": "north_east",
    "north west": "north_west",
    "yorkshire and the humber": "yorkshire",
    "yorkshire": "yorkshire",
}


def generate_deterministic_id(source: str, record_id: str) -> str:
    """Generate deterministic ID from source + record_id."""
    composite = f"{source}:{record_id}"
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


def extract_postcode_area(postcode: str) -> str:
    """Extract the outward code (area) from a UK postcode."""
    if not postcode:
        return ""
    postcode = str(postcode).upper().strip()
    # UK postcode format: AA9A 9AA, A9A 9AA, A9 9AA, A99 9AA, AA9 9AA, AA99 9AA
    # Extract outward code (before space)
    parts = postcode.split()
    if parts:
        outward = parts[0]
        # Extract just the letter prefix (district)
        match = re.match(r'^([A-Z]{1,2})', outward)
        if match:
            return match.group(1).lower()
    return ""


def normalize_region(region: str) -> str:
    """Normalize UK region name."""
    if not region:
        return ""
    region_lower = str(region).strip().lower()
    return UK_REGIONS.get(region_lower, normalize_dimension_value(region_lower))


def combine_proprietor_names(doc: dict) -> List[str]:
    """Combine multiple proprietor names from document."""
    names = []
    for suffix in ["_1", "_2", ""]:
        name_field = f"proprietor_name{suffix}"
        name = doc.get(name_field)
        if name and str(name).strip():
            names.append(str(name).strip())
    # Also check owner_name (uk_addresses format)
    owner_name = doc.get("owner_name")
    if owner_name and str(owner_name).strip():
        names.append(str(owner_name).strip())
    return names


def combine_proprietor_addresses(doc: dict) -> List[str]:
    """Combine multiple proprietor addresses from document."""
    addresses = []
    for suffix in ["_1", "_2", ""]:
        addr_field = f"proprietor_address{suffix}"
        addr = doc.get(addr_field)
        if addr and str(addr).strip():
            addresses.append(str(addr).strip())
    return addresses


def transform_ccod(doc: dict) -> Optional[dict]:
    """Transform uk_ccod record to uk_property_unified format."""
    title_number = doc.get("title_number", "")
    if not title_number:
        return None

    # Generate deterministic ID
    doc_id = generate_deterministic_id("uk_ccod", title_number)

    # Build dimension_keys
    dimension_keys = set()
    add_dimension_key(dimension_keys, "jur", "uk")
    add_dimension_key(dimension_keys, "source", "ccod")

    # Region
    region = doc.get("region")
    if region:
        region_norm = normalize_region(region)
        add_dimension_key(dimension_keys, "region", region_norm)

    # Postcode area
    postcode = doc.get("postcode", "")
    postcode_area = extract_postcode_area(postcode)
    if postcode_area:
        add_dimension_key(dimension_keys, "postcode", postcode_area)

    # District
    district = doc.get("district")
    if district:
        add_dimension_key(dimension_keys, "district", district)

    # County
    county = doc.get("county")
    if county:
        add_dimension_key(dimension_keys, "county", county)

    # Tenure
    tenure = doc.get("tenure", "")
    if tenure:
        add_dimension_key(dimension_keys, "tenure", tenure)

    # Proprietorship category
    prop_cat = doc.get("proprietorship_category_1", "")
    if prop_cat:
        if "company" in prop_cat.lower():
            add_dimension_key(dimension_keys, "owner_type", "company")
        elif "individual" in prop_cat.lower():
            add_dimension_key(dimension_keys, "owner_type", "individual")
        else:
            add_dimension_key(dimension_keys, "owner_type", prop_cat)

    # Combine proprietor names
    proprietor_names = combine_proprietor_names(doc)
    proprietor_addresses = combine_proprietor_addresses(doc)

    result = {
        "id": doc_id,
        "title_number": title_number,

        # Location
        "property_address": doc.get("property_address", ""),
        "postcode": postcode,
        "postcode_area": postcode_area,
        "county": county,
        "region": region,
        "district": district,
        "location": doc.get("location"),  # geo_point

        # Ownership
        "proprietor_name": proprietor_names[0] if proprietor_names else None,
        "proprietor_names": proprietor_names,
        "proprietor_address": proprietor_addresses[0] if proprietor_addresses else None,
        "proprietorship_category": prop_cat,
        "company_reg_no": doc.get("company_reg_no_1"),

        # Provenance
        "source_dataset": "uk_ccod",
        "source_record_id": title_number,

        # Cross-search contract
        "subject": [f"title:{title_number}"],
        "concepts": [],
        "dimension_keys": sorted(dimension_keys),
        "doc_type": "property",

        # Metadata
        "metadata": {
            "tenure": tenure,
            "price_paid": doc.get("price_paid"),
            "date_proprietor_added": doc.get("date_proprietor_added_1"),
            "multiple_address_indicator": doc.get("multiple_address_indicator"),
            "data_source": doc.get("data_source"),
        },

        # Timestamps
        "indexed_at": datetime.utcnow().isoformat(),
    }

    return result


def transform_ocod(doc: dict) -> Optional[dict]:
    """Transform uk_ocod record to uk_property_unified format (overseas companies)."""
    title_number = doc.get("title_number", "")
    if not title_number:
        return None

    doc_id = generate_deterministic_id("uk_ocod", title_number)

    dimension_keys = set()
    add_dimension_key(dimension_keys, "jur", "uk")
    add_dimension_key(dimension_keys, "source", "ocod")
    add_dimension_key(dimension_keys, "owner_type", "overseas_company")

    # Region/postcode
    region = doc.get("region")
    if region:
        add_dimension_key(dimension_keys, "region", normalize_region(region))

    postcode = doc.get("postcode", "")
    postcode_area = extract_postcode_area(postcode)
    if postcode_area:
        add_dimension_key(dimension_keys, "postcode", postcode_area)

    # Country of incorporation
    country_inc = doc.get("country_incorporated")
    if country_inc:
        add_dimension_key(dimension_keys, "country_incorporated", country_inc)

    tenure = doc.get("tenure", "")
    if tenure:
        add_dimension_key(dimension_keys, "tenure", tenure)

    result = {
        "id": doc_id,
        "title_number": title_number,

        # Location
        "property_address": doc.get("property_address", ""),
        "postcode": postcode,
        "postcode_area": postcode_area,
        "county": doc.get("county"),
        "region": region,
        "district": doc.get("district"),
        "location": doc.get("location"),

        # Ownership
        "proprietor_name": doc.get("proprietor_name"),
        "proprietor_names": [doc.get("proprietor_name")] if doc.get("proprietor_name") else [],
        "proprietor_address": doc.get("proprietor_address"),
        "proprietorship_category": "Overseas Company",
        "country_incorporated": country_inc,

        # Provenance
        "source_dataset": "uk_ocod",
        "source_record_id": title_number,

        # Cross-search contract
        "subject": [f"title:{title_number}"],
        "concepts": ["overseas_ownership"],
        "dimension_keys": sorted(dimension_keys),
        "doc_type": "property",

        # Metadata
        "metadata": {
            "tenure": tenure,
            "price_paid": doc.get("price_paid"),
            "date_proprietor_added": doc.get("date_proprietor_added"),
            "additional_proprietor_indicator": doc.get("additional_proprietor_indicator"),
        },

        "indexed_at": datetime.utcnow().isoformat(),
    }

    return result


def transform_addresses(doc: dict) -> Optional[dict]:
    """Transform uk_addresses record to uk_property_unified format."""
    # Prefer title_number, fallback to uprn
    title_number = doc.get("title_number", "")
    uprn = doc.get("uprn", "")

    record_id = title_number or uprn
    if not record_id:
        return None

    doc_id = generate_deterministic_id("uk_addresses", str(record_id))

    dimension_keys = set()
    add_dimension_key(dimension_keys, "jur", "uk")
    add_dimension_key(dimension_keys, "source", "addresses")

    region = doc.get("region")
    if region:
        add_dimension_key(dimension_keys, "region", normalize_region(region))

    postcode = doc.get("postcode", "")
    postcode_area = extract_postcode_area(postcode)
    if postcode_area:
        add_dimension_key(dimension_keys, "postcode", postcode_area)

    tenure = doc.get("tenure", "")
    if tenure:
        add_dimension_key(dimension_keys, "tenure", tenure)

    owner_type = doc.get("owner_type", "")
    if owner_type:
        add_dimension_key(dimension_keys, "owner_type", owner_type)

    # Country of incorporation (for overseas)
    country_inc = doc.get("country_incorporated")
    if country_inc:
        add_dimension_key(dimension_keys, "country_incorporated", country_inc)

    result = {
        "id": doc_id,
        "title_number": title_number if title_number else None,
        "uprn": uprn if uprn else None,

        # Location
        "property_address": doc.get("address") or doc.get("property_description", ""),
        "postcode": postcode,
        "postcode_area": postcode_area,
        "county": doc.get("county"),
        "region": region,
        "district": doc.get("district"),
        "location": doc.get("location"),

        # Ownership
        "proprietor_name": doc.get("owner_name"),
        "proprietor_names": [doc.get("owner_name")] if doc.get("owner_name") else [],
        "company_reg_no": doc.get("company_number"),
        "country_incorporated": country_inc,

        # Provenance
        "source_dataset": "uk_addresses",
        "source_record_id": str(record_id),

        # Cross-search contract
        "subject": [f"title:{title_number}"] if title_number else [],
        "concepts": [],
        "dimension_keys": sorted(dimension_keys),
        "doc_type": "property",

        # Metadata
        "metadata": {
            "tenure": tenure,
            "price_paid": doc.get("price_paid"),
            "lease_date": doc.get("lease_date"),
            "lease_term": doc.get("lease_term"),
            "source": doc.get("source"),
        },

        "indexed_at": datetime.utcnow().isoformat(),
    }

    return result


def transform_leases(doc: dict) -> Optional[dict]:
    """Transform uk_leases record to uk_property_unified format."""
    unique_id = doc.get("unique_id", "")
    uprn = doc.get("uprn", "")

    record_id = unique_id or uprn
    if not record_id:
        return None

    doc_id = generate_deterministic_id("uk_leases", str(record_id))

    dimension_keys = set()
    add_dimension_key(dimension_keys, "jur", "uk")
    add_dimension_key(dimension_keys, "source", "leases")
    add_dimension_key(dimension_keys, "tenure", "leasehold")

    region = doc.get("region")
    if region:
        add_dimension_key(dimension_keys, "region", normalize_region(region))

    # Extract year from lease date
    lease_date = doc.get("date_of_lease", "")
    if lease_date:
        year_match = re.search(r'(19|20)\d{2}', str(lease_date))
        if year_match:
            add_dimension_key(dimension_keys, "year", year_match.group())

    result = {
        "id": doc_id,
        "title_number": doc.get("lessor_title"),  # Link to lessor title
        "uprn": uprn if uprn else None,
        "unique_id": unique_id if unique_id else None,

        # Location
        "property_address": doc.get("property_description", ""),
        "county": doc.get("county"),
        "region": region,

        # Lease details
        "proprietor_name": None,  # Lessee not always available
        "proprietor_names": [],

        # Provenance
        "source_dataset": "uk_leases",
        "source_record_id": str(record_id),

        # Cross-search contract
        "subject": [f"lessor:{doc.get('lessor_title')}"] if doc.get("lessor_title") else [],
        "concepts": ["lease"],
        "dimension_keys": sorted(dimension_keys),
        "doc_type": "property",

        # Metadata
        "metadata": {
            "tenure": "leasehold",
            "price_paid": doc.get("price_paid"),
            "date_of_lease": lease_date,
            "lease_term": doc.get("term"),
            "lessor_title": doc.get("lessor_title"),
            "alienation_clause": doc.get("alienation_clause"),
        },

        "indexed_at": datetime.utcnow().isoformat(),
    }

    return result


# Transformer mapping
TRANSFORMERS = {
    "uk_ccod": transform_ccod,
    "uk_ocod": transform_ocod,
    "uk_addresses": transform_addresses,
    "uk_leases": transform_leases,
}


def load_checkpoint() -> dict:
    """Load checkpoint from file."""
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {"completed_sources": [], "stats": {}}


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

    mapping = {
        "settings": {
            "number_of_shards": 3,
            "number_of_replicas": 0,
            "refresh_interval": "30s",
        },
        "mappings": {
            "properties": {
                # Identity
                "id": {"type": "keyword"},
                "title_number": {"type": "keyword"},
                "uprn": {"type": "keyword"},
                "unique_id": {"type": "keyword"},

                # Location
                "property_address": {
                    "type": "text",
                    "fields": {"keyword": {"type": "keyword", "ignore_above": 512}}
                },
                "postcode": {"type": "keyword"},
                "postcode_area": {"type": "keyword"},
                "county": {"type": "keyword"},
                "region": {"type": "keyword"},
                "district": {"type": "keyword"},
                "location": {"type": "geo_point"},

                # Ownership
                "proprietor_name": {
                    "type": "text",
                    "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}
                },
                "proprietor_names": {"type": "keyword"},
                "proprietor_address": {"type": "text"},
                "proprietorship_category": {"type": "keyword"},
                "company_reg_no": {"type": "keyword"},
                "country_incorporated": {"type": "keyword"},

                # Provenance
                "source_dataset": {"type": "keyword"},
                "source_record_id": {"type": "keyword"},

                # Cross-search contract
                "subject": {"type": "keyword"},
                "concepts": {"type": "keyword"},
                "dimension_keys": {"type": "keyword"},
                "doc_type": {"type": "keyword"},

                # Metadata
                "metadata": {
                    "type": "object",
                    "properties": {
                        "tenure": {"type": "keyword"},
                        "price_paid": {"type": "long"},
                        "date_proprietor_added": {"type": "date", "ignore_malformed": True},
                        "date_of_lease": {"type": "keyword"},
                        "lease_term": {"type": "keyword"},
                    }
                },

                "indexed_at": {"type": "date"},
            }
        }
    }

    es.indices.create(index=TARGET_INDEX, body=mapping)
    logger.info(f"Created target index {TARGET_INDEX}")


def consolidate_source(es: Elasticsearch, source_name: str, checkpoint: dict) -> dict:
    """Consolidate a single source into uk_property_unified."""
    transformer = TRANSFORMERS.get(source_name)
    if not transformer:
        logger.error(f"No transformer for {source_name}")
        return {"indexed": 0, "failed": 0, "skipped": 0}

    stats = {"indexed": 0, "failed": 0, "skipped": 0}
    actions = []

    logger.info(f"Processing {source_name}...")

    for doc in scroll_source(es, source_name):
        try:
            transformed = transformer(doc)
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

                total = stats["indexed"] + stats["failed"] + stats["skipped"]
                if total % 100000 == 0:
                    logger.info(f"  {source_name}: {total:,} processed ({stats['indexed']:,} indexed)")

                actions = []

        except Exception as e:
            logger.warning(f"Transform error: {e}")
            stats["failed"] += 1

    if actions:
        success, errors = bulk(es, actions, raise_on_error=False, stats_only=True)
        stats["indexed"] += success
        stats["failed"] += len(errors) if isinstance(errors, list) else errors

    logger.info(f"  {source_name} complete: {stats['indexed']:,} indexed, {stats['skipped']:,} skipped")
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
                "by_region": {"terms": {"field": "dimension_keys", "include": "region:.*", "size": 15}},
                "by_tenure": {"terms": {"field": "dimension_keys", "include": "tenure:.*", "size": 10}},
                "by_owner_type": {"terms": {"field": "dimension_keys", "include": "owner_type:.*", "size": 10}},
                "top_postcodes": {"terms": {"field": "postcode_area", "size": 15}},
            }
        }
    )

    logger.info("\nBy Source Dataset:")
    for bucket in aggs["aggregations"]["by_source"]["buckets"]:
        logger.info(f"  {bucket['key']}: {bucket['doc_count']:,}")

    logger.info("\nBy Region:")
    for bucket in aggs["aggregations"]["by_region"]["buckets"][:10]:
        logger.info(f"  {bucket['key']}: {bucket['doc_count']:,}")

    logger.info("\nBy Tenure:")
    for bucket in aggs["aggregations"]["by_tenure"]["buckets"]:
        logger.info(f"  {bucket['key']}: {bucket['doc_count']:,}")

    logger.info("\nBy Owner Type:")
    for bucket in aggs["aggregations"]["by_owner_type"]["buckets"]:
        logger.info(f"  {bucket['key']}: {bucket['doc_count']:,}")

    logger.info("\nTop Postcode Areas:")
    for bucket in aggs["aggregations"]["top_postcodes"]["buckets"][:10]:
        logger.info(f"  {bucket['key']}: {bucket['doc_count']:,}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Consolidate UK property data into uk_property_unified")
    parser.add_argument("--source", type=str, help="Process only this source (ccod, ocod, addresses, leases)")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--verify", action="store_true", help="Only verify existing index")
    parser.add_argument("--reset", action="store_true", help="Delete checkpoint and start fresh")
    args = parser.parse_args()

    source_shortcuts = {
        "ccod": "uk_ccod",
        "ocod": "uk_ocod",
        "addresses": "uk_addresses",
        "leases": "uk_leases",
    }

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

    ensure_target_index(es)

    if args.source:
        source_name = source_shortcuts.get(args.source, args.source)
        sources_to_process = [source_name]
    else:
        # Process in priority order: CCOD first (primary), then OCOD, addresses, leases
        sources_to_process = ["uk_ccod", "uk_ocod", "uk_addresses", "uk_leases"]

    if args.resume:
        sources_to_process = [s for s in sources_to_process if s not in checkpoint["completed_sources"]]

    logger.info(f"Sources to process: {sources_to_process}")

    total_stats = {"indexed": 0, "failed": 0, "skipped": 0}

    for source_name in sources_to_process:
        if source_name not in SOURCES:
            logger.warning(f"Unknown source: {source_name}")
            continue

        stats = consolidate_source(es, source_name, checkpoint)
        total_stats["indexed"] += stats["indexed"]
        total_stats["failed"] += stats["failed"]
        total_stats["skipped"] += stats["skipped"]

        checkpoint["completed_sources"].append(source_name)
        checkpoint["stats"][source_name] = stats
        save_checkpoint(checkpoint)

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
