#!/usr/bin/env python3
"""
SEARCH_NODES CONSOLIDATION SCRIPT

Consolidates entity data from multiple sources into a unified search_nodes index.

Sources:
  - openownership (36.4M) - Beneficial ownership declarations
  - linkedin_unified - Company and person profiles
  - wdc-organization-entities (9.6M) - Schema.org organizations
  - wdc-person-entities (6.8M) - Schema.org persons
  - wdc-localbusiness-entities (478K) - Local businesses

Target: search_nodes

Core Contract (4 fields):
  - subject: Entity IDs this record represents
  - concepts: Semantic labels for search
  - dimension_keys: Normalized facets for filtering (prefix:value)
  - doc_type: "entity" (for routing)

ID Strategy: Deterministic hash-based IDs
  - ID = hash(source_dataset + ":" + source_record_id)
  - Enables idempotent re-runs

Usage:
    python consolidate_search_nodes.py                 # Full run
    python consolidate_search_nodes.py --source oo    # Only openownership
    python consolidate_search_nodes.py --resume       # Resume from checkpoint
    python consolidate_search_nodes.py --verify       # Verify only
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
TARGET_INDEX = "search_nodes"
BATCH_SIZE = 1000
SCROLL_SIZE = 5000
SCROLL_TIMEOUT = "10m"

# Checkpoint file
CHECKPOINT_FILE = Path(__file__).parent / "search_nodes_checkpoint.json"

# Source configurations
SOURCES = {
    "openownership": {
        "index": "openownership",
        "entity_type_field": "entity_type",
        "entity_type_map": {
            "naturalPerson": "person",
            "legalEntity": "company",
            "registeredEntity": "company",
            "anonymousEntity": "unknown",
        },
        "name_fields": ["interested_party_name", "name"],
        "id_field": "interested_party_id",
        "id_fallback": "record_id",
    },
    "linkedin_unified": {
        "index": "linkedin_unified",
        "entity_type_field": "profile_type",
        "entity_type_map": {
            "company": "company",
            "person": "person",
        },
        "name_fields": ["company_name", "person_name"],
        "id_field": "linkedin_id",
    },
    "wdc-organization-entities": {
        "index": "wdc-organization-entities",
        "entity_type": "company",  # All are companies
        "name_fields": ["name", "legalName", "alternateName"],
        "id_field": "_id",  # Use ES doc ID
    },
    "wdc-person-entities": {
        "index": "wdc-person-entities",
        "entity_type": "person",  # All are persons
        "name_fields": ["name", "givenName", "familyName"],
        "id_field": "_id",
    },
    "wdc-localbusiness-entities": {
        "index": "wdc-localbusiness-entities",
        "entity_type": "localbusiness",
        "name_fields": ["name", "legalName"],
        "id_field": "_id",
    },
}


def generate_deterministic_id(source: str, record_id: str) -> str:
    """
    Generate deterministic ID from source + record_id.

    This enables idempotent re-runs - same source record always gets same ID.
    """
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


def normalize_jurisdiction(value: str) -> str:
    """Normalize jurisdiction to ISO code."""
    if not value:
        return ""
    value = str(value).strip().lower()[:3]
    # Common overrides
    overrides = {
        "gb": "uk",
        "great britain": "uk",
        "united kingdom": "uk",
        "usa": "us",
        "united states": "us",
    }
    return overrides.get(value, value)


def get_first_value(doc: dict, fields: List[str]) -> Optional[str]:
    """Get first non-empty value from a list of field names."""
    for field in fields:
        val = doc.get(field)
        if val and not (isinstance(val, float) and str(val) == "nan"):
            if isinstance(val, list):
                return val[0] if val else None
            return str(val)
    return None


def transform_openownership(doc: dict) -> dict:
    """Transform openownership record to search_nodes format."""
    config = SOURCES["openownership"]

    # Get entity type
    raw_type = doc.get(config["entity_type_field"], "")
    entity_type = config["entity_type_map"].get(str(raw_type), "unknown")

    # Get name
    name = get_first_value(doc, config["name_fields"])
    if not name:
        return None  # Skip records without names

    # Get source record ID
    source_id = doc.get(config["id_field"]) or doc.get(config.get("id_fallback", ""))
    if not source_id:
        source_id = doc.get("_id", "")

    # Generate deterministic ID
    doc_id = generate_deterministic_id("openownership", str(source_id))

    # Build dimension_keys
    dimension_keys = set()
    add_dimension_key(dimension_keys, "ent", entity_type)
    add_dimension_key(dimension_keys, "source", "openownership")

    # Jurisdiction
    jur = doc.get("jurisdiction") or doc.get("country")
    if jur:
        jur_norm = normalize_jurisdiction(jur)
        add_dimension_key(dimension_keys, "jur", jur_norm)

    # Control types as concepts
    control_types = doc.get("control_types", [])
    if isinstance(control_types, str):
        control_types = [control_types]

    concepts = []
    for ct in (control_types or []):
        if ct:
            concepts.append(str(ct).lower())
            add_dimension_key(dimension_keys, "ownership", ct)

    # Ownership strength dimension
    ownership_pct = doc.get("ownership_percentage")
    if ownership_pct:
        try:
            pct = float(ownership_pct)
            if pct >= 75:
                add_dimension_key(dimension_keys, "ownership_strength", "majority")
            elif pct >= 25:
                add_dimension_key(dimension_keys, "ownership_strength", "significant")
            else:
                add_dimension_key(dimension_keys, "ownership_strength", "minority")
        except (ValueError, TypeError):
            pass

    # Build result
    result = {
        "id": doc_id,
        "entity_type": entity_type,
        "name": name,
        "name_normalized": name.lower().strip() if name else "",

        # Provenance
        "source_dataset": "openownership",
        "source_record_id": f"oo:{source_id}",
        "source_url": doc.get("source_url", ""),

        # Cross-search contract
        "subject": [f"oo:{source_id}"],
        "concepts": concepts,
        "dimension_keys": sorted(dimension_keys),
        "doc_type": "entity",

        # Metadata
        "metadata": {
            "jurisdiction": doc.get("jurisdiction"),
            "company_number": doc.get("company_number"),
            "address": doc.get("address"),
            "ownership_pct": ownership_pct,
            "voting_pct": doc.get("voting_percentage"),
            "control_types": control_types,
        },

        # Timestamps
        "indexed_at": datetime.utcnow().isoformat(),
        "statement_date": doc.get("statement_date"),
    }

    # Add location if present
    if doc.get("location"):
        result["metadata"]["location"] = doc["location"]

    return result


def transform_linkedin(doc: dict) -> dict:
    """Transform linkedin_unified record to search_nodes format."""
    config = SOURCES["linkedin_unified"]

    # Get entity type
    profile_type = doc.get(config["entity_type_field"], "")
    entity_type = config["entity_type_map"].get(str(profile_type).lower(), "unknown")

    # Get name based on profile type
    if entity_type == "company":
        name = doc.get("company_name")
    else:
        name = doc.get("person_name")

    if not name:
        name = get_first_value(doc, config["name_fields"])
    if not name:
        return None

    # Get source record ID
    source_id = doc.get(config["id_field"]) or doc.get("_id", "")

    # Generate deterministic ID
    doc_id = generate_deterministic_id("linkedin_unified", str(source_id))

    # Build dimension_keys
    dimension_keys = set()
    add_dimension_key(dimension_keys, "ent", entity_type)
    add_dimension_key(dimension_keys, "source", "linkedin")

    # Industry
    industry = doc.get("industry")
    if industry:
        add_dimension_key(dimension_keys, "industry", industry)

    # Country/jurisdiction
    country = doc.get("country")
    if country:
        jur_norm = normalize_jurisdiction(country)
        add_dimension_key(dimension_keys, "jur", jur_norm)

    # Concepts from industry and specialties
    concepts = []
    if industry:
        concepts.append(industry.lower())
    specialties = doc.get("specialties", [])
    if isinstance(specialties, list):
        concepts.extend([s.lower() for s in specialties if s])

    # Company size dimension
    company_size = doc.get("company_size", "")
    if company_size:
        size_str = str(company_size).lower()
        if "10000" in size_str or "5001" in size_str:
            add_dimension_key(dimension_keys, "size", "enterprise")
        elif "1001" in size_str or "501" in size_str:
            add_dimension_key(dimension_keys, "size", "large")
        elif "201" in size_str or "51" in size_str:
            add_dimension_key(dimension_keys, "size", "medium")
        else:
            add_dimension_key(dimension_keys, "size", "small")

    result = {
        "id": doc_id,
        "entity_type": entity_type,
        "name": name,
        "name_normalized": name.lower().strip() if name else "",

        # Provenance
        "source_dataset": "linkedin_unified",
        "source_record_id": f"li:{source_id}",
        "source_url": doc.get("linkedin_url", ""),

        # Cross-search contract
        "subject": [f"li:{source_id}"],
        "concepts": concepts[:20],  # Limit concepts
        "dimension_keys": sorted(dimension_keys),
        "doc_type": "entity",

        # Metadata
        "metadata": {
            "industry": industry,
            "jurisdiction": country,
            "employee_count": doc.get("company_size"),
            "domain": doc.get("domain") or doc.get("company_domain"),
            "founded": doc.get("founded"),
            "headline": doc.get("headline"),
            "job_title": doc.get("job_title"),
        },

        # Timestamps
        "indexed_at": datetime.utcnow().isoformat(),
    }

    return result


def transform_wdc_organization(doc: dict) -> dict:
    """Transform wdc-organization-entities record to search_nodes format."""
    config = SOURCES["wdc-organization-entities"]

    # Get name
    name = get_first_value(doc, config["name_fields"])
    if not name:
        return None

    # Get source record ID (use ES doc ID)
    source_id = doc.get("_id", "")

    # Generate deterministic ID
    doc_id = generate_deterministic_id("wdc-organization", str(source_id))

    # Build dimension_keys
    dimension_keys = set()
    add_dimension_key(dimension_keys, "ent", "company")
    add_dimension_key(dimension_keys, "source", "wdc")
    add_dimension_key(dimension_keys, "schema", "organization")

    # Domain
    domain = doc.get("domain") or doc.get("url", "")
    if domain and "://" in domain:
        try:
            from urllib.parse import urlparse
            domain = urlparse(domain).netloc
        except:
            pass
    if domain:
        add_dimension_key(dimension_keys, "domain", domain.replace("www.", ""))

    # Industry/category
    industry = doc.get("industry")
    if industry:
        add_dimension_key(dimension_keys, "industry", industry)

    # Country
    country = doc.get("country") or doc.get("addressCountry")
    if country:
        jur_norm = normalize_jurisdiction(country)
        add_dimension_key(dimension_keys, "jur", jur_norm)

    # Concepts from schema.org types
    concepts = []
    schema_types = doc.get("type") or doc.get("types") or doc.get("@type")
    if schema_types:
        if isinstance(schema_types, str):
            schema_types = [schema_types]
        for st in schema_types[:5]:
            if st:
                concepts.append(str(st).lower())

    if industry:
        concepts.append(industry.lower())

    result = {
        "id": doc_id,
        "entity_type": "company",
        "name": name,
        "name_normalized": name.lower().strip() if name else "",

        # Provenance
        "source_dataset": "wdc-organization-entities",
        "source_record_id": f"wdc:org:{source_id}",
        "source_url": doc.get("url", ""),

        # Cross-search contract
        "subject": [f"wdc:org:{source_id}"],
        "concepts": concepts[:20],
        "dimension_keys": sorted(dimension_keys),
        "doc_type": "entity",

        # Metadata
        "metadata": {
            "domain": domain if domain else None,
            "industry": industry,
            "jurisdiction": country,
            "address": doc.get("address"),
            "telephone": doc.get("telephone") or doc.get("Telephone"),
            "schema_type": schema_types[0] if schema_types else None,
            "founding_date": doc.get("foundingDate") or doc.get("foundingdate"),
            "employee_count": doc.get("numberOfEmployees"),
            "description": (doc.get("description") or "")[:500],
        },

        # Timestamps
        "indexed_at": datetime.utcnow().isoformat(),
    }

    return result


def transform_wdc_person(doc: dict) -> dict:
    """Transform wdc-person-entities record to search_nodes format."""
    config = SOURCES["wdc-person-entities"]

    # Get name - try combining given/family if full name not present
    name = doc.get("name")
    if not name:
        given = doc.get("givenName", "")
        family = doc.get("familyName", "")
        if given or family:
            name = f"{given} {family}".strip()
    if not name:
        return None

    # Get source record ID
    source_id = doc.get("_id", "")

    # Generate deterministic ID
    doc_id = generate_deterministic_id("wdc-person", str(source_id))

    # Build dimension_keys
    dimension_keys = set()
    add_dimension_key(dimension_keys, "ent", "person")
    add_dimension_key(dimension_keys, "source", "wdc")
    add_dimension_key(dimension_keys, "schema", "person")

    # Domain from URL
    url = doc.get("url", "")
    domain = ""
    if url and "://" in url:
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.replace("www.", "")
            add_dimension_key(dimension_keys, "domain", domain)
        except:
            pass

    # Country
    country = doc.get("nationality") or doc.get("country")
    if country:
        jur_norm = normalize_jurisdiction(country)
        add_dimension_key(dimension_keys, "jur", jur_norm)

    # Concepts
    concepts = []
    job_title = doc.get("jobTitle")
    if job_title:
        concepts.append(job_title.lower())

    knows_about = doc.get("knowsAbout") or doc.get("knowsabout")
    if knows_about:
        if isinstance(knows_about, list):
            concepts.extend([str(k).lower() for k in knows_about[:10] if k])
        else:
            concepts.append(str(knows_about).lower())

    result = {
        "id": doc_id,
        "entity_type": "person",
        "name": name,
        "name_normalized": name.lower().strip() if name else "",

        # Provenance
        "source_dataset": "wdc-person-entities",
        "source_record_id": f"wdc:pers:{source_id}",
        "source_url": url,

        # Cross-search contract
        "subject": [f"wdc:pers:{source_id}"],
        "concepts": concepts[:20],
        "dimension_keys": sorted(dimension_keys),
        "doc_type": "entity",

        # Metadata
        "metadata": {
            "domain": domain if domain else None,
            "nationality": doc.get("nationality"),
            "job_title": job_title,
            "affiliation": doc.get("affiliation"),
            "works_for": doc.get("worksFor"),
            "birth_date": doc.get("birthDate"),
            "description": (doc.get("description") or "")[:500],
        },

        # Timestamps
        "indexed_at": datetime.utcnow().isoformat(),
    }

    return result


def transform_wdc_localbusiness(doc: dict) -> dict:
    """Transform wdc-localbusiness-entities record to search_nodes format."""
    # Get name
    name = doc.get("name") or doc.get("legalName")
    if not name:
        return None

    # Get source record ID
    source_id = doc.get("_id", "")

    # Generate deterministic ID
    doc_id = generate_deterministic_id("wdc-localbusiness", str(source_id))

    # Build dimension_keys
    dimension_keys = set()
    add_dimension_key(dimension_keys, "ent", "localbusiness")
    add_dimension_key(dimension_keys, "source", "wdc")
    add_dimension_key(dimension_keys, "schema", "localbusiness")

    # Domain from URL
    url = doc.get("url", "")
    domain = ""
    if url and "://" in url:
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.replace("www.", "")
            add_dimension_key(dimension_keys, "domain", domain)
        except:
            pass

    # Country
    country = doc.get("country") or doc.get("addressCountry")
    if country:
        jur_norm = normalize_jurisdiction(country)
        add_dimension_key(dimension_keys, "jur", jur_norm)

    # Category as concept
    concepts = []
    category = doc.get("category")
    if category:
        if isinstance(category, list):
            concepts.extend([str(c).lower() for c in category[:5] if c])
        else:
            concepts.append(str(category).lower())

    result = {
        "id": doc_id,
        "entity_type": "localbusiness",
        "name": name,
        "name_normalized": name.lower().strip() if name else "",

        # Provenance
        "source_dataset": "wdc-localbusiness-entities",
        "source_record_id": f"wdc:lb:{source_id}",
        "source_url": url,

        # Cross-search contract
        "subject": [f"wdc:lb:{source_id}"],
        "concepts": concepts[:20],
        "dimension_keys": sorted(dimension_keys),
        "doc_type": "entity",

        # Metadata
        "metadata": {
            "domain": domain if domain else None,
            "jurisdiction": country,
            "address": doc.get("address"),
            "telephone": doc.get("telephone") or doc.get("Telephone"),
            "price_range": doc.get("priceRange"),
            "opening_hours": doc.get("openingHours"),
            "category": category,
        },

        # Timestamps
        "indexed_at": datetime.utcnow().isoformat(),
    }

    return result


# Transformer mapping
TRANSFORMERS = {
    "openownership": transform_openownership,
    "linkedin_unified": transform_linkedin,
    "wdc-organization-entities": transform_wdc_organization,
    "wdc-person-entities": transform_wdc_person,
    "wdc-localbusiness-entities": transform_wdc_localbusiness,
}


def load_checkpoint() -> dict:
    """Load checkpoint from file."""
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {"completed_sources": [], "last_doc_id": {}, "stats": {}}


def save_checkpoint(checkpoint: dict) -> None:
    """Save checkpoint to file."""
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(checkpoint, f, indent=2)


def scroll_source(es: Elasticsearch, source_name: str, checkpoint: dict) -> Generator[dict, None, None]:
    """Scroll through a source index, yielding documents."""
    config = SOURCES[source_name]
    index = config["index"]

    # Check if we need to resume
    last_id = checkpoint.get("last_doc_id", {}).get(source_name)

    query = {"match_all": {}}

    logger.info(f"Starting scroll for {index}...")

    for doc in scan(
        es,
        index=index,
        query={"query": query},
        scroll=SCROLL_TIMEOUT,
        size=SCROLL_SIZE,
        preserve_order=False,  # Faster without ordering
    ):
        # Add _id to the doc for reference
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
            "number_of_shards": 3,
            "number_of_replicas": 0,  # Speed during indexing
            "refresh_interval": "30s",
            "index.mapping.total_fields.limit": 2000,
        },
        "mappings": {
            "properties": {
                # Identity
                "id": {"type": "keyword"},
                "entity_type": {"type": "keyword"},
                "name": {
                    "type": "text",
                    "fields": {"keyword": {"type": "keyword", "ignore_above": 512}}
                },
                "name_normalized": {"type": "keyword"},

                # Provenance
                "source_dataset": {"type": "keyword"},
                "source_record_id": {"type": "keyword"},
                "source_url": {"type": "keyword"},

                # Cross-search contract
                "subject": {"type": "keyword"},
                "concepts": {"type": "keyword"},
                "dimension_keys": {"type": "keyword"},
                "doc_type": {"type": "keyword"},

                # Metadata (dynamic for flexibility)
                "metadata": {
                    "type": "object",
                    "properties": {
                        "jurisdiction": {"type": "keyword"},
                        "company_number": {"type": "keyword"},
                        "address": {"type": "text"},
                        "industry": {"type": "keyword"},
                        "domain": {"type": "keyword"},
                        "employee_count": {"type": "keyword"},
                        "ownership_pct": {"type": "float"},
                        "voting_pct": {"type": "float"},
                        "location": {"type": "geo_point"},
                    }
                },

                # Timestamps
                "indexed_at": {"type": "date"},
                "statement_date": {"type": "date", "ignore_malformed": True},
            }
        }
    }

    es.indices.create(index=TARGET_INDEX, body=mapping)
    logger.info(f"Created target index {TARGET_INDEX}")


def consolidate_source(es: Elasticsearch, source_name: str, checkpoint: dict) -> dict:
    """Consolidate a single source into search_nodes."""
    transformer = TRANSFORMERS.get(source_name)
    if not transformer:
        logger.error(f"No transformer for {source_name}")
        return {"indexed": 0, "failed": 0, "skipped": 0}

    stats = {"indexed": 0, "failed": 0, "skipped": 0}
    actions = []

    logger.info(f"Processing {source_name}...")

    for doc in scroll_source(es, source_name, checkpoint):
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

            # Bulk index in batches
            if len(actions) >= BATCH_SIZE:
                success, errors = bulk(
                    es, actions,
                    raise_on_error=False,
                    stats_only=True
                )
                stats["indexed"] += success
                stats["failed"] += len(errors) if isinstance(errors, list) else errors

                # Log progress
                total = stats["indexed"] + stats["failed"] + stats["skipped"]
                if total % 50000 == 0:
                    logger.info(f"  {source_name}: {total:,} processed ({stats['indexed']:,} indexed, {stats['skipped']:,} skipped)")

                # Save checkpoint periodically
                if total % 100000 == 0:
                    checkpoint["last_doc_id"][source_name] = doc.get("_id", "")
                    checkpoint["stats"][source_name] = stats.copy()
                    save_checkpoint(checkpoint)

                actions = []

        except Exception as e:
            logger.warning(f"Transform error: {e}")
            stats["failed"] += 1

    # Index remaining
    if actions:
        success, errors = bulk(es, actions, raise_on_error=False, stats_only=True)
        stats["indexed"] += success
        stats["failed"] += len(errors) if isinstance(errors, list) else errors

    # Mark source complete
    if source_name not in checkpoint["completed_sources"]:
        checkpoint["completed_sources"].append(source_name)
    checkpoint["stats"][source_name] = stats
    save_checkpoint(checkpoint)

    logger.info(f"  {source_name} complete: {stats['indexed']:,} indexed, {stats['skipped']:,} skipped, {stats['failed']:,} failed")

    return stats


def verify_consolidation(es: Elasticsearch) -> None:
    """Verify the consolidated index."""
    if not es.indices.exists(index=TARGET_INDEX):
        logger.error(f"Index {TARGET_INDEX} does not exist")
        return

    # Get count
    count = es.count(index=TARGET_INDEX)["count"]
    logger.info(f"\n{'='*60}")
    logger.info(f"VERIFICATION: {TARGET_INDEX}")
    logger.info(f"{'='*60}")
    logger.info(f"Total documents: {count:,}")

    # Aggregations
    aggs = es.search(
        index=TARGET_INDEX,
        body={
            "size": 0,
            "aggs": {
                "by_source": {"terms": {"field": "source_dataset", "size": 20}},
                "by_entity_type": {"terms": {"field": "entity_type", "size": 20}},
                "by_jurisdiction": {"terms": {"field": "dimension_keys", "include": "jur:.*", "size": 20}},
            }
        }
    )

    logger.info("\nBy Source Dataset:")
    for bucket in aggs["aggregations"]["by_source"]["buckets"]:
        logger.info(f"  {bucket['key']}: {bucket['doc_count']:,}")

    logger.info("\nBy Entity Type:")
    for bucket in aggs["aggregations"]["by_entity_type"]["buckets"]:
        logger.info(f"  {bucket['key']}: {bucket['doc_count']:,}")

    logger.info("\nTop Jurisdictions:")
    for bucket in aggs["aggregations"]["by_jurisdiction"]["buckets"][:10]:
        logger.info(f"  {bucket['key']}: {bucket['doc_count']:,}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Consolidate entity data into search_nodes")
    parser.add_argument("--source", type=str, help="Process only this source (oo, li, wdc-org, wdc-pers, wdc-lb)")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--verify", action="store_true", help="Only verify existing index")
    parser.add_argument("--reset", action="store_true", help="Delete checkpoint and start fresh")
    args = parser.parse_args()

    # Source name shortcuts
    source_shortcuts = {
        "oo": "openownership",
        "li": "linkedin_unified",
        "wdc-org": "wdc-organization-entities",
        "wdc-pers": "wdc-person-entities",
        "wdc-lb": "wdc-localbusiness-entities",
    }

    # Connect
    es = Elasticsearch([ES_HOST], request_timeout=120, retry_on_timeout=True, max_retries=3)
    if not es.ping():
        logger.error("Cannot connect to Elasticsearch")
        return

    # Verify only
    if args.verify:
        verify_consolidation(es)
        return

    # Reset checkpoint
    if args.reset and CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        logger.info("Checkpoint deleted")

    # Load checkpoint
    checkpoint = load_checkpoint() if args.resume else {"completed_sources": [], "last_doc_id": {}, "stats": {}}

    # Ensure target index exists
    ensure_target_index(es)

    # Determine which sources to process
    if args.source:
        source_name = source_shortcuts.get(args.source, args.source)
        sources_to_process = [source_name]
    else:
        sources_to_process = list(SOURCES.keys())

    # Skip already completed sources
    if args.resume:
        sources_to_process = [s for s in sources_to_process if s not in checkpoint["completed_sources"]]

    logger.info(f"Sources to process: {sources_to_process}")

    # Process each source
    total_stats = {"indexed": 0, "failed": 0, "skipped": 0}

    for source_name in sources_to_process:
        if source_name not in SOURCES:
            logger.warning(f"Unknown source: {source_name}")
            continue

        stats = consolidate_source(es, source_name, checkpoint)
        total_stats["indexed"] += stats["indexed"]
        total_stats["failed"] += stats["failed"]
        total_stats["skipped"] += stats["skipped"]

    # Refresh index
    logger.info("Refreshing index...")
    es.indices.refresh(index=TARGET_INDEX)

    # Final summary
    logger.info(f"\n{'='*60}")
    logger.info("CONSOLIDATION COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Total indexed: {total_stats['indexed']:,}")
    logger.info(f"Total skipped: {total_stats['skipped']:,}")
    logger.info(f"Total failed: {total_stats['failed']:,}")

    # Verify
    verify_consolidation(es)


if __name__ == "__main__":
    main()
