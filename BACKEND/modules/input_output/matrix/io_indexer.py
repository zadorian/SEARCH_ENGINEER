#!/usr/bin/env python3
"""
IO Matrix Elasticsearch Indexer

Indexes all IO Matrix data into Elasticsearch for fast querying:
- Sources (11,809+) with inputs, outputs, jurisdictions
- Field codes (433+) with entity types and edges
- Modules (16) with capabilities
- Jurisdiction capabilities
- Chain rules

Index: io-matrix
Document types: source, field, module, jurisdiction, chain_rule

Usage:
    python io_indexer.py                    # Full reindex
    python io_indexer.py --sources-only     # Just sources
    python io_indexer.py --check            # Check index stats
    python io_indexer.py --delete           # Delete index

Querying (examples):
    GET io-matrix/_search
    {
        "query": {
            "bool": {
                "must": [
                    {"term": {"doc_type": "source"}},
                    {"term": {"input_classes": "company"}},
                    {"term": {"jurisdictions": "UK"}}
                ]
            }
        }
    }
"""

import json
import logging
import argparse
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from elasticsearch import Elasticsearch, helpers

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Try to import StandardEmbedder
try:
    from CYMONIDES.embedders.standard_embedder import get_embedder
    HAS_EMBEDDER = True
except ImportError as e:
    logging.warning(f"Could not import StandardEmbedder: {e}. Embeddings will be skipped.")
    HAS_EMBEDDER = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("io-indexer")

# Matrix directory
MATRIX_DIR = Path(__file__).parent

# Elasticsearch
ES_HOST = "http://localhost:9200"
INDEX_NAME = "io-matrix"

# Code-to-class mapping (loaded from codes.json)
CODE_TO_CLASS = {}


def load_code_mappings():
    """Load code-to-class mappings from codes.json with comprehensive name inference."""
    global CODE_TO_CLASS
    codes_file = MATRIX_DIR / "codes.json"
    if codes_file.exists():
        with open(codes_file) as f:
            data = json.load(f)
            codes = data.get("codes", data)
            if isinstance(codes, dict):
                for code_id, info in codes.items():
                    if isinstance(info, dict):
                        node_type = info.get("node_type", "").lower()
                        name = info.get("name", "").lower()

                        # Priority 1: explicit node_type
                        if node_type and node_type not in ["unknown", "nexus", ""]:
                            if node_type in ["person", "company", "domain", "email", "phone", "address", "event",
                                           "vessel", "vehicle", "aircraft", "litigation", "username", "linkedin", "url", "file"]:
                                CODE_TO_CLASS[int(code_id)] = node_type
                                continue

                        # Priority 2: infer from name patterns
                        if name:
                            # Person patterns
                            if any(p in name for p in ["person", "director", "officer", "shareholder",
                                                        "beneficial_owner", "signatory", "representative"]):
                                CODE_TO_CLASS[int(code_id)] = "person"
                            # Company patterns
                            elif any(p in name for p in ["company", "corporate", "business", "subsidiary",
                                                          "parent_company", "incorporation", "registry"]):
                                CODE_TO_CLASS[int(code_id)] = "company"
                            # Email patterns
                            elif "email" in name:
                                CODE_TO_CLASS[int(code_id)] = "email"
                            # Phone patterns
                            elif any(p in name for p in ["phone", "tel", "fax", "mobile"]):
                                CODE_TO_CLASS[int(code_id)] = "phone"
                            # Domain/URL patterns
                            elif any(p in name for p in ["domain", "url", "website", "web_"]):
                                CODE_TO_CLASS[int(code_id)] = "domain"
                            # Address patterns
                            elif any(p in name for p in ["address", "street", "city", "country", "postal", "zip"]):
                                CODE_TO_CLASS[int(code_id)] = "address"
    logger.info(f"Loaded {len(CODE_TO_CLASS)} code-to-class mappings")


def get_es_client() -> Elasticsearch:
    """Get Elasticsearch client."""
    return Elasticsearch(ES_HOST)


def create_index_mapping() -> Dict:
    """Create the index mapping with all required fields."""
    return {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "analyzer": {
                    "lowercase_keyword": {
                        "type": "custom",
                        "tokenizer": "keyword",
                        "filter": ["lowercase"]
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                # Common fields
                "doc_type": {"type": "keyword"},
                "id": {"type": "keyword"},
                "name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "description": {"type": "text"},
                "file_name": {"type": "keyword"},
                "indexed_at": {"type": "date"},

                # Embedding field (1024 dims for intfloat/multilingual-e5-large)
                "embedding": {
                    "type": "dense_vector",
                    "dims": 1024,
                    "index": True,
                    "similarity": "cosine"
                },

                # Source-specific fields
                "domain": {"type": "keyword"},
                "url": {"type": "keyword"},
                "search_url": {"type": "keyword"},
                "source_type": {"type": "keyword"},  # api, registry, scrape, etc.
                "category": {"type": "keyword"},  # news, corporate, government, etc.
                "section": {"type": "keyword"},   # sub-category
                "access": {"type": "keyword"},    # public, private, etc.
                "searchable": {"type": "boolean"},
                "friction": {"type": "keyword"},  # low, medium, high
                "handled_by": {"type": "keyword"},  # jester, torpedo, api, etc.

                # Input/Output fields (arrays for filtering)
                "inputs": {"type": "keyword"},  # Raw input codes
                "outputs": {"type": "keyword"},  # Raw output codes
                "input_classes": {"type": "keyword"},  # person, company, domain, etc.
                "output_classes": {"type": "keyword"},
                "input_edges": {"type": "keyword"},  # name_of, email_of, etc.
                "output_edges": {"type": "keyword"},

                # Jurisdiction fields
                "jurisdiction": {"type": "keyword"},  # Primary jurisdiction
                "jurisdictions": {"type": "keyword"},  # All jurisdictions (array)

                # Classification fields
                "classification": {
                    "type": "object",
                    "properties": {
                        "scrape_method": {"type": "keyword"},
                        "requires_js": {"type": "boolean"},
                        "requires_auth": {"type": "boolean"},
                        "rate_limit": {"type": "keyword"}
                    }
                },

                # Metadata (catch-all for extra filterable fields)
                "metadata": {
                    "type": "object",
                    "dynamic": True  # Allow indexing of arbitrary fields
                },

                # Field/Code specific
                "code": {"type": "integer"},
                "entity_class": {"type": "keyword"},
                "edge_type": {"type": "keyword"},
                "creates_node": {"type": "boolean"},
                "creates_edge": {"type": "boolean"},

                # Module specific
                "module_name": {"type": "keyword"},
                "capabilities": {"type": "keyword"},
                "api_endpoint": {"type": "keyword"},
                "supported_inputs": {"type": "keyword"},
                "supported_outputs": {"type": "keyword"},

                # Chain rule specific
                "chain_type": {"type": "keyword"},
                "trigger_input": {"type": "keyword"},
                "trigger_output": {"type": "keyword"},
                "chain_steps": {"type": "nested"},

                # Search optimization
                "all_text": {"type": "text"},  # Combined searchable text
                "tags": {"type": "keyword"}
            }
        }
    }


def code_to_class(code: int) -> Optional[str]:
    """Map a code number to its entity class."""
    return CODE_TO_CLASS.get(code)


def extract_classes_from_codes(codes: List) -> List[str]:
    """Extract entity classes from a list of codes."""
    classes = set()
    for code in codes:
        try:
            if isinstance(code, int):
                cls = code_to_class(code)
                if cls:
                    classes.add(cls)
            elif isinstance(code, str) and code.isdigit():
                cls = code_to_class(int(code))
                if cls:
                    classes.add(cls)
        except (ValueError, TypeError):
            pass
    return list(classes)


def generate_embedding(text: str) -> Optional[List[float]]:
    """Generate embedding for text using standard embedder."""
    if not HAS_EMBEDDER or not text:
        return None
    try:
        embedder = get_embedder()
        # Use encode_passage as these are documents to be indexed
        return embedder.encode_passage(text)
    except Exception as e:
        logger.warning(f"Embedding error: {e}")
        return None


def index_sources(es: Elasticsearch) -> int:
    """Index all sources from sources.json with batch embedding."""
    sources_file = MATRIX_DIR / "sources.json"
    if not sources_file.exists():
        logger.warning(f"Sources file not found: {sources_file}")
        return 0

    logger.info("Loading sources.json...")
    with open(sources_file) as f:
        data = json.load(f)

    sources = data.get("sources", data)
    if isinstance(sources, dict):
        # Convert dict to list of items
        items = []
        for key, value in sources.items():
            if isinstance(value, dict):
                value["id"] = key
                items.append(value)
        sources = items

    logger.info(f"Indexing {len(sources)} sources...")

    def generate_docs_batch(batch_size=32):
        batch_docs = []
        batch_texts = []
        
        embedder = None
        if HAS_EMBEDDER:
            try:
                embedder = get_embedder()
            except Exception as e:
                logger.warning(f"Failed to get embedder: {e}")

        for source in sources:
            # Extract input/output codes
            inputs = source.get("inputs", [])
            outputs = source.get("outputs", [])

            # Map to classes
            input_classes = extract_classes_from_codes(inputs)
            output_classes = extract_classes_from_codes(outputs)

            # Build combined text for search
            all_text = " ".join(filter(None, [
                source.get("name", ""),
                source.get("domain", ""),
                source.get("description", ""),
                source.get("category", ""),
                source.get("section", ""),
                " ".join(source.get("jurisdictions", [])) if isinstance(source.get("jurisdictions"), list) else source.get("jurisdiction", "")
            ]))

            # Ensure jurisdictions is a list of strings
            jurisdictions_raw = source.get("jurisdictions", [])
            if isinstance(jurisdictions_raw, str):
                jurisdictions_raw = [jurisdictions_raw]
            elif not isinstance(jurisdictions_raw, list):
                jurisdictions_raw = []

            jurisdiction = source.get("jurisdiction")
            if jurisdiction and jurisdiction not in jurisdictions_raw:
                jurisdictions_raw.append(jurisdiction)

            # Ensure classification is a dict
            classification = source.get("classification", {})
            if not isinstance(classification, dict):
                classification = {}
            # Preserve TORPEDO execution metadata stored at top-level in sources.json
            scrape_method = source.get("scrape_method")
            if scrape_method and not classification.get("scrape_method"):
                classification["scrape_method"] = str(scrape_method)

            doc = {
                "_index": INDEX_NAME,
                "_id": f"source:{source.get('id', source.get('domain', source.get('name', '')))}",
                "doc_type": "source",
                "id": str(source.get("id", "")),
                "name": str(source.get("name", "")),
                "domain": str(source.get("domain", "")),
                "url": str(source.get("url", "")),
                "search_url": str(source.get("search_url", "")),
                "source_type": str(source.get("type", "")),
                "category": str(source.get("category", "")),
                "section": str(source.get("section", "")),
                "access": str(source.get("access", "")),
                "searchable": bool(source.get("searchable", True)),
                "friction": str(source.get("friction", "")),
                "handled_by": str(source.get("handled_by", "")),
                "inputs": [str(i) for i in inputs] if inputs else [],
                "outputs": [str(o) for o in outputs] if outputs else [],
                "input_classes": input_classes,
                "output_classes": output_classes,
                "jurisdiction": str(jurisdiction) if jurisdiction else "",
                "jurisdictions": [str(j) for j in jurisdictions_raw if j],
                "classification": classification,
                "metadata": source.get("metadata", {}),
                "file_name": "sources.json",
                "all_text": all_text,
                "indexed_at": datetime.utcnow().isoformat()
            }
            
            batch_docs.append(doc);
            batch_texts.append(all_text);

            if len(batch_docs) >= batch_size:
                # Encode batch
                if embedder:
                    try:
                        embeddings = embedder.encode_batch_passages(batch_texts, show_progress=False)
                        for d, emb in zip(batch_docs, embeddings):
                            d["embedding"] = emb
                    except Exception as e:
                        logger.warning(f"Batch embedding error: {e}")
                
                # Yield docs
                for d in batch_docs:
                    yield d
                
                batch_docs = []
                batch_texts = []

        # Process remaining
        if batch_docs:
            if embedder:
                try:
                    embeddings = embedder.encode_batch_passages(batch_texts, show_progress=False)
                    for d, emb in zip(batch_docs, embeddings):
                        d["embedding"] = emb
                except Exception as e:
                    logger.warning(f"Batch embedding error: {e}")
            for d in batch_docs:
                yield d

    success, errors = helpers.bulk(es, generate_docs_batch(), raise_on_error=False, stats_only=True)
    logger.info(f"Sources indexed: {success} success, {errors} errors")
    return success


def index_codes(es: Elasticsearch) -> int:
    """Index all field codes from codes.json."""
    codes_file = MATRIX_DIR / "codes.json"
    if not codes_file.exists():
        logger.warning(f"Codes file not found: {codes_file}")
        return 0

    logger.info("Loading codes.json...")
    with open(codes_file) as f:
        data = json.load(f)

    codes = data.get("codes", data)
    if isinstance(codes, dict) and "meta" in codes:
        # It's a dict with meta, actual codes are elsewhere
        codes = {k: v for k, v in data.items() if k != "meta"}
        if "codes" in codes:
            codes = codes["codes"]

    logger.info(f"Indexing {len(codes)} field codes...")

    def generate_docs():
        items = codes.items() if isinstance(codes, dict) else enumerate(codes)
        for key, value in items:
            if isinstance(value, dict):
                code_num = value.get("code", key)
                if isinstance(code_num, str) and code_num.isdigit():
                    code_num = int(code_num)

                all_text = f"{key} {value.get('name', '')} {value.get('description', '')}"
                embedding = generate_embedding(all_text)

                doc = {
                    "_index": INDEX_NAME,
                    "_id": f"field:{code_num}",
                    "doc_type": "field",
                    "code": code_num,
                    "name": value.get("name", value.get("field_name", key)),
                    "description": value.get("description", ""),
                    "entity_class": code_to_class(code_num) if isinstance(code_num, int) else None,
                    "edge_type": value.get("edge_type"),
                    "creates_node": value.get("creates_node", False),
                    "creates_edge": value.get("creates_edge", False),
                    "file_name": "codes.json",
                    "all_text": all_text,
                    "indexed_at": datetime.utcnow().isoformat()
                }
                if embedding:
                    doc["embedding"] = embedding
                yield doc

    success, errors = helpers.bulk(es, generate_docs(), raise_on_error=False, stats_only=True)
    logger.info(f"Codes indexed: {success} success, {errors} errors")
    return success


def index_modules(es: Elasticsearch) -> int:
    """Index all modules from modules.json."""
    modules_file = MATRIX_DIR / "modules.json"
    if not modules_file.exists():
        logger.warning(f"Modules file not found: {modules_file}")
        return 0

    logger.info("Loading modules.json...")
    with open(modules_file) as f:
        data = json.load(f)

    modules = data.get("modules", data)
    logger.info(f"Indexing {len(modules)} modules...")

    def generate_docs():
        items = modules.items() if isinstance(modules, dict) else enumerate(modules)
        for key, value in items:
            if isinstance(value, dict):
                all_text = f"{key} {value.get('name', '')} {value.get('description', '')}"
                embedding = generate_embedding(all_text)

                doc = {
                    "_index": INDEX_NAME,
                    "_id": f"module:{key}",
                    "doc_type": "module",
                    "module_name": key,
                    "name": value.get("name", key),
                    "description": value.get("description", ""),
                    "api_endpoint": value.get("api_endpoint"),
                    "capabilities": value.get("capabilities", []),
                    "supported_inputs": value.get("inputs", []),
                    "supported_outputs": value.get("outputs", []),
                    "file_name": "modules.json",
                    "all_text": all_text,
                    "indexed_at": datetime.utcnow().isoformat()
                }
                if embedding:
                    doc["embedding"] = embedding
                yield doc

    success, errors = helpers.bulk(es, generate_docs(), raise_on_error=False, stats_only=True)
    logger.info(f"Modules indexed: {success} success, {errors} errors")
    return success


def index_jurisdictions(es: Elasticsearch) -> int:
    """Index jurisdiction capabilities."""
    jur_file = MATRIX_DIR / "jurisdiction_capabilities.json"
    if not jur_file.exists():
        logger.warning(f"Jurisdiction capabilities file not found: {jur_file}")
        return 0

    logger.info("Loading jurisdiction_capabilities.json...")
    with open(jur_file) as f:
        data = json.load(f)

    logger.info(f"Indexing {len(data)} jurisdiction capabilities...")

    def generate_docs():
        items = data.items() if isinstance(data, dict) else enumerate(data)
        for key, value in items:
            if isinstance(value, dict):
                all_text = f"{key} {value.get('name', '')} {value.get('description', '')}"
                embedding = generate_embedding(all_text)

                doc = {
                    "_index": INDEX_NAME,
                    "_id": f"jurisdiction:{key}",
                    "doc_type": "jurisdiction",
                    "jurisdiction": key,
                    "name": value.get("name", key),
                    "description": value.get("description", ""),
                    "capabilities": value.get("capabilities", []),
                    "operators": value.get("operators", []),
                    "supported_inputs": value.get("inputs", []),
                    "supported_outputs": value.get("outputs", []),
                    "file_name": "jurisdiction_capabilities.json",
                    "all_text": all_text,
                    "indexed_at": datetime.utcnow().isoformat()
                }
                if embedding:
                    doc["embedding"] = embedding
                yield doc

    success, errors = helpers.bulk(es, generate_docs(), raise_on_error=False, stats_only=True)
    logger.info(f"Jurisdictions indexed: {success} success, {errors} errors")
    return success


def index_chain_rules(es: Elasticsearch) -> int:
    """Index chain rules."""
    chain_file = MATRIX_DIR / "chain_rules.json"
    if not chain_file.exists():
        logger.warning(f"Chain rules file not found: {chain_file}")
        return 0

    logger.info("Loading chain_rules.json...")
    with open(chain_file) as f:
        data = json.load(f)

    if isinstance(data, list):
        rules = data
    elif isinstance(data, dict):
        rules = data.get("rules", list(data.values()))
    else:
        rules = []

    logger.info(f"Indexing {len(rules)} chain rules...")

    def generate_docs():
        for i, rule in enumerate(rules):
            if isinstance(rule, dict):
                all_text = f"{rule.get('name', '')} {rule.get('description', '')}"
                embedding = generate_embedding(all_text)

                doc = {
                    "_index": INDEX_NAME,
                    "_id": f"chain:{rule.get('id', i)}",
                    "doc_type": "chain_rule",
                    "name": rule.get("name", f"chain_{i}"),
                    "description": rule.get("description", ""),
                    "chain_type": rule.get("type"),
                    "trigger_input": rule.get("trigger_input"),
                    "trigger_output": rule.get("trigger_output"),
                    "file_name": "chain_rules.json",
                    "all_text": all_text,
                    "indexed_at": datetime.utcnow().isoformat()
                }
                if embedding:
                    doc["embedding"] = embedding
                yield doc

    success, errors = helpers.bulk(es, generate_docs(), raise_on_error=False, stats_only=True)
    logger.info(f"Chain rules indexed: {success} success, {errors} errors")
    return success


def index_rules(es: Elasticsearch) -> int:
    """Index core rules from rules.json."""
    rules_file = MATRIX_DIR / "rules.json"
    if not rules_file.exists():
        logger.warning(f"Rules file not found: {rules_file}")
        return 0

    logger.info("Loading rules.json...")
    with open(rules_file) as f:
        data = json.load(f)

    rules = data.get("rules", data)
    logger.info(f"Indexing {len(rules)} rules...")

    def generate_docs():
        items = rules.items() if isinstance(rules, dict) else enumerate(rules)
        for key, value in items:
            if isinstance(value, dict):
                rule_id = value.get("rule_id", key)
                label = value.get("label", "")
                desc = value.get("description", label)
                
                # Input/Output handling
                requires_any = value.get("requires_any", [])
                returns = value.get("returns", [])
                input_classes = extract_classes_from_codes(requires_any)
                output_classes = extract_classes_from_codes(returns)

                all_text = f"{rule_id} {label} {desc} {' '.join(input_classes)} {' '.join(output_classes)}"
                embedding = generate_embedding(all_text)

                doc = {
                    "_index": INDEX_NAME,
                    "_id": f"rule:{rule_id}",
                    "doc_type": "rule",
                    "rule_id": rule_id,
                    "name": label,
                    "description": desc,
                    "friction": value.get("friction", "Open"),
                    "inputs": [str(c) for c in requires_any],
                    "outputs": [str(c) for c in returns],
                    "input_classes": input_classes,
                    "output_classes": output_classes,
                    "resources": value.get("resources", []),
                    "file_name": "rules.json",
                    "all_text": all_text,
                    "indexed_at": datetime.utcnow().isoformat()
                }
                if embedding:
                    doc["embedding"] = embedding
                yield doc

    success, errors = helpers.bulk(es, generate_docs(), raise_on_error=False, stats_only=True)
    logger.info(f"Rules indexed: {success} success, {errors} errors")
    return success


def index_operators(es: Elasticsearch) -> int:
    """Index operators from operators.json."""
    ops_file = MATRIX_DIR / "operators.json"
    if not ops_file.exists():
        logger.warning(f"Operators file not found: {ops_file}")
        return 0

    logger.info("Loading operators.json...")
    with open(ops_file) as f:
        data = json.load(f)

    operators = data.get("operators", data)
    logger.info(f"Indexing {len(operators)} operators...")

    def generate_docs():
        items = operators.items() if isinstance(operators, dict) else enumerate(operators)
        for key, value in items:
            if isinstance(value, dict):
                op_id = value.get("id", key)
                name = value.get("name", op_id)
                desc = value.get("description", value.get("notes", ""))
                
                inputs = value.get("inputs", [])
                outputs = value.get("outputs", [])
                input_classes = extract_classes_from_codes(inputs)
                output_classes = extract_classes_from_codes(outputs)

                all_text = f"{op_id} {name} {desc}"
                embedding = generate_embedding(all_text)

                doc = {
                    "_index": INDEX_NAME,
                    "_id": f"operator:{op_id}",
                    "doc_type": "operator",
                    "operator_id": op_id,
                    "name": name,
                    "description": desc,
                    "category": value.get("category", ""),
                    "inputs": [str(c) for c in inputs],
                    "outputs": [str(c) for c in outputs],
                    "input_classes": input_classes,
                    "output_classes": output_classes,
                    "classification": value.get("classification", {}),
                    "file_name": "operators.json",
                    "all_text": all_text,
                    "indexed_at": datetime.utcnow().isoformat()
                }
                if embedding:
                    doc["embedding"] = embedding
                yield doc

    success, errors = helpers.bulk(es, generate_docs(), raise_on_error=False, stats_only=True)
    logger.info(f"Operators indexed: {success} success, {errors} errors")
    return success


def create_index(es: Elasticsearch, delete_existing: bool = False):
    """Create the index with mapping."""
    if es.indices.exists(index=INDEX_NAME):
        if delete_existing:
            logger.info(f"Deleting existing index: {INDEX_NAME}")
            es.indices.delete(index=INDEX_NAME)
        else:
            logger.info(f"Index {INDEX_NAME} already exists")
            return

    logger.info(f"Creating index: {INDEX_NAME}")
    es.indices.create(index=INDEX_NAME, body=create_index_mapping())
    logger.info(f"Index {INDEX_NAME} created successfully")


def check_index(es: Elasticsearch):
    """Check index statistics."""
    if not es.indices.exists(index=INDEX_NAME):
        logger.info(f"Index {INDEX_NAME} does not exist")
        return

    stats = es.indices.stats(index=INDEX_NAME)
    count = es.count(index=INDEX_NAME)

    print(f"\n=== IO-MATRIX INDEX STATS ===")
    print(f"Total documents: {count['count']}")
    print(f"Index size: {stats['_all']['total']['store']['size_in_bytes'] // 1024}KB")

    # Count by doc_type
    agg = es.search(index=INDEX_NAME, body={
        "size": 0,
        "aggs": {
            "by_type": {"terms": {"field": "doc_type", "size": 10}}
        }
    })

    print("\nBy document type:")
    for bucket in agg["aggregations"]["by_type"]["buckets"]:
        print(f"  {bucket['key']}: {bucket['doc_count']}")

    # Count sources by category
    cat_agg = es.search(index=INDEX_NAME, body={
        "size": 0,
        "query": {"term": {"doc_type": "source"}},
        "aggs": {
            "by_category": {"terms": {"field": "category", "size": 20}}
        }
    })

    print("\nSources by category:")
    for bucket in cat_agg["aggregations"]["by_category"]["buckets"]:
        print(f"  {bucket['key']}: {bucket['doc_count']}")


def full_reindex(es: Elasticsearch):
    """Run full reindex of all IO Matrix data."""
    # Load code mappings first
    load_code_mappings()

    create_index(es, delete_existing=True)

    total = 0
    total += index_sources(es)
    total += index_codes(es)
    total += index_modules(es)
    total += index_jurisdictions(es)
    total += index_chain_rules(es)
    total += index_rules(es)
    total += index_operators(es)

    es.indices.refresh(index=INDEX_NAME)
    logger.info(f"\n=== REINDEX COMPLETE ===")
    logger.info(f"Total documents indexed: {total}")

    check_index(es)


def main():
    global ES_HOST

    parser = argparse.ArgumentParser(description="IO Matrix Elasticsearch Indexer")
    parser.add_argument("--check", action="store_true", help="Check index stats")
    parser.add_argument("--delete", action="store_true", help="Delete index")
    parser.add_argument("--sources-only", action="store_true", help="Only index sources")
    parser.add_argument("--es-host", default=ES_HOST, help="Elasticsearch host")
    args = parser.parse_args()

    ES_HOST = args.es_host

    es = get_es_client()

    if args.check:
        check_index(es)
    elif args.delete:
        if es.indices.exists(index=INDEX_NAME):
            es.indices.delete(index=INDEX_NAME)
            logger.info(f"Index {INDEX_NAME} deleted")
        else:
            logger.info(f"Index {INDEX_NAME} does not exist")
    elif args.sources_only:
        create_index(es, delete_existing=False)
        index_sources(es)
        es.indices.refresh(index=INDEX_NAME)
    else:
        full_reindex(es)


if __name__ == "__main__":
    main()
