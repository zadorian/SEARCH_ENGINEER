#!/usr/bin/env python3
"""
Index FINEPDFS parquet files to cymonides-2 corpus with FULL EXTRACTION.

Usage:
    python index_to_cymonides.py                    # Index with full extraction
    python index_to_cymonides.py --skip-extraction  # Index metadata only (fast)
    python index_to_cymonides.py --verify-only      # Just verify existing

Extracts via UniversalExtractor (265 category embeddings):
- Conceptual: themes, phenomena, red_flag_themes, methodologies
- Temporal: published_date, content_years, temporal_focus
- Spatial: locations, primary_jurisdiction

TIERED EMBEDDING STORAGE:
Keep full 768-dim content_embedding ONLY for high-value documents:
- is_regulatory = true
- red_flag_alert = true (hit tripwire)
- has_financial_tables = true
- priority_score >= 80
- is_annual_report = true (detected via patterns)
- Registry-linked (SEC, Companies House, GLEIF, exchanges)

Flags-only for bulk corpus (category IDs stored, no embedding):
- Saves ~85% storage while maintaining tripwire detection
"""

import hashlib
import logging
import re
import sys
import importlib.util
from pathlib import Path
from datetime import datetime

try:
    import pyarrow.parquet as pq
    import pandas as pd
except ImportError:
    print("pip install pyarrow pandas")
    sys.exit(1)

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

# Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Config
# ingest/ is inside CYMONIDES, so go up 5 levels to project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
CYMONIDES_ROOT = Path(__file__).resolve().parent.parent
ES_HOST = "http://localhost:9200"
INDEX = "cymonides-2"
SOURCE_TYPE = "cc-pdf-2025"
PARQUET_DIR = PROJECT_ROOT / "output" / "finepdfs_corporate"
BATCH_SIZE = 100  # Smaller batches for extraction (memory)

# Lazy load extractor
_extractor = None

def get_extractor():
    """Lazy load UniversalExtractor from cymonides/extraction/."""
    global _extractor
    if _extractor is None:
        # Use CYMONIDES local extraction module
        extractor_path = CYMONIDES_ROOT / "extraction" / "universal_extractor.py"
        spec = importlib.util.spec_from_file_location("universal_extractor", extractor_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        logger.info("Loading UniversalExtractor with 265 category embeddings...")
        _extractor = module.UniversalExtractor()
        # Trigger lazy loading
        _ = _extractor.golden
        _ = _extractor.model
    return _extractor


def extract_title(row) -> str:
    """Extract title from URL or first line of text."""
    url = str(row.get('url', '') or '')

    # Try filename from URL
    if '/' in url:
        filename = url.split('/')[-1]
        # Remove .pdf extension and clean up
        filename = filename.replace('.pdf', '').replace('.PDF', '')
        filename = filename.replace('-', ' ').replace('_', ' ').replace('%20', ' ')
        if len(filename) > 5 and len(filename) < 200:
            return filename[:200]

    # Fallback to first line of text
    text = str(row.get('text', '') or '')
    if text:
        # Get first non-empty line
        for line in text.split('\n')[:10]:
            line = line.strip()
            if len(line) > 10 and len(line) < 300:
                return line[:200]

    return "Untitled PDF"


def normalize_lang(lang) -> str:
    """Normalize language code (eng_Latn -> en)."""
    if not lang or pd.isna(lang):
        return "unknown"
    lang = str(lang)
    # Handle formats like "eng_Latn"
    if '_' in lang:
        lang = lang.split('_')[0]
    return lang[:3].lower()


def _normalize_dimension_value(value: str) -> str:
    value = str(value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return value


def _add_dimension_keys(keys: set, prefix: str, values):
    if not values:
        return
    for value in values:
        normalized = _normalize_dimension_value(value)
        if normalized:
            keys.add(f"{prefix}:{normalized}")


# Registry-linked domain patterns (high-value indicators)
REGISTRY_DOMAINS = {
    'sec.gov', 'edgar-online.com', 'sedar.com',  # SEC/SEDAR filers
    'companieshouse.gov.uk', 'find-and-update.company-information.service.gov.uk',  # UK Companies House
    'gleif.org', 'lei-lookup.com',  # GLEIF/LEI
    'nyse.com', 'nasdaq.com', 'londonstockexchange.com', 'euronext.com',  # Exchanges
    'annualreports.com', 'annualreportservice.com',  # Annual report aggregators
}

# Annual report detection patterns
ANNUAL_REPORT_PATTERNS = [
    'annual report', 'annual review', 'yearly report',
    'form 10-k', 'form 20-f', 'annual accounts',
    'financial statements', 'audited accounts',
    'geschäftsbericht', 'rapport annuel', 'relazione annuale',
]


def is_high_value_document(row, doc: dict) -> bool:
    """
    Determine if a document qualifies for full content embedding storage.

    High-value criteria (keep 768-dim embedding):
    - is_regulatory = true
    - red_flag_alert = true (hit tripwire)
    - has_financial_tables = true
    - priority_score >= 80
    - is_annual_report = true
    - Registry-linked (SEC, Companies House, GLEIF, exchanges)

    Returns:
        True if document should have content_embedding stored
    """
    # Check metadata flags
    if doc.get('metadata', {}).get('is_regulatory'):
        return True

    if doc.get('metadata', {}).get('has_financial_tables'):
        return True

    if doc.get('metadata', {}).get('priority_score', 0) >= 80:
        return True

    # Red flag alert (set during extraction)
    if doc.get('red_flag_alert'):
        return True

    # Check domain for registry links
    domain = str(row.get('domain', '') or '').lower()
    url = str(row.get('url', '') or '').lower()
    for registry_domain in REGISTRY_DOMAINS:
        if registry_domain in domain or registry_domain in url:
            return True

    # Check for annual report patterns in title/content
    title = doc.get('title', '').lower()
    content_preview = doc.get('content', '')[:5000].lower()
    for pattern in ANNUAL_REPORT_PATTERNS:
        if pattern in title or pattern in content_preview:
            doc['metadata']['is_annual_report'] = True
            return True

    return False


def build_document(row, doc_id: str, run_extraction: bool = True) -> dict:
    """Build cymonides-2 document from parquet row with optional semantic extraction."""
    url = str(row.get('url', '') or '')
    text = str(row.get('text', '') or '')

    # Parse comma-separated fields
    sectors = []
    if row.get('detected_sectors') and not pd.isna(row.get('detected_sectors')):
        sectors = [s.strip() for s in str(row['detected_sectors']).split(',') if s.strip()]

    detected_red_flags = []
    if row.get('detected_red_flags') and not pd.isna(row.get('detected_red_flags')):
        detected_red_flags = [
            r.strip() for r in str(row['detected_red_flags']).split(',') if r.strip()
        ]

    reasons = []
    if row.get('reasons') and not pd.isna(row.get('reasons')):
        reasons = [r.strip() for r in str(row['reasons']).split(',') if r.strip()]

    # Handle potential NaN values
    def safe_bool(val):
        if pd.isna(val):
            return False
        return bool(val)

    def safe_int(val, default=0):
        if pd.isna(val):
            return default
        try:
            return int(val)
        except:
            return default

    def safe_str(val, default=None):
        if pd.isna(val) or val is None:
            return default
        return str(val)

    doc = {
        "id": doc_id,
        "source_url": url,
        "source_domain": safe_str(row.get('domain'), ''),
        "source_type": SOURCE_TYPE,
        "content": text[:100000] if text else '',  # Truncate large texts
        "title": extract_title(row),
        "language": normalize_lang(row.get('language')),
        "word_count": safe_int(row.get('token_count')),
        "fetched_at": safe_str(row.get('date')),
        "content_hash": hashlib.md5(text.encode()).hexdigest() if text else None,
        "metadata": {
            "jurisdiction": safe_str(row.get('jurisdiction')),
            "is_regulatory": safe_bool(row.get('is_regulatory')),
            "has_financial_tables": safe_bool(row.get('has_financial_tables')),
            "sectors": sectors,
            "priority_score": safe_int(row.get('priority_score')),
            "reasons": reasons,
            "cc_dump": safe_str(row.get('dump')),
            "sector_signal_score": safe_int(row.get('sector_signal_score')),
        },
        "project_ids": [],
        "extracted_entity_ids": [],
    }

    # Run UniversalExtractor for semantic dimensions
    if run_extraction and text and len(text) > 100:
        try:
            extractor = get_extractor()
            extraction = extractor.extract(text, meta_date=safe_str(row.get('date')))

            # Conceptual extraction (themes, phenomena, red_flags, methodologies)
            doc["concepts"] = {
                "themes": [t["canonical"] for t in extraction.themes],
                "phenomena": [p["canonical"] for p in extraction.phenomena],
                "red_flag_themes": [rf["canonical"] for rf in extraction.red_flag_themes],
                "methodologies": [m["canonical"] for m in extraction.methodologies],
            }
            doc["subject"] = {
                "themes": [t["id"] for t in extraction.themes],
                "phenomena": [p["id"] for p in extraction.phenomena],
                "red_flag_themes": [rf["id"] for rf in extraction.red_flag_themes],
                "methodologies": [m["id"] for m in extraction.methodologies],
            }

            # Temporal extraction (with hierarchical fields)
            doc["temporal"] = {
                "content_years": extraction.content_years,
                "temporal_focus": extraction.temporal_focus,
            }
            if extraction.published_date:
                doc["temporal"]["published_date"] = extraction.published_date
            # Hierarchical temporal fields
            if extraction.temporal_year:
                doc["temporal"]["year"] = extraction.temporal_year
            if extraction.temporal_month:
                doc["temporal"]["month"] = extraction.temporal_month
            if extraction.temporal_day:
                doc["temporal"]["day"] = extraction.temporal_day
            if extraction.temporal_yearmonth:
                doc["temporal"]["yearmonth"] = extraction.temporal_yearmonth
            if extraction.temporal_decade:
                doc["temporal"]["decade"] = extraction.temporal_decade
            if extraction.temporal_era:
                doc["temporal"]["era"] = extraction.temporal_era
            if extraction.temporal_precision and extraction.temporal_precision != "unknown":
                doc["temporal"]["precision"] = extraction.temporal_precision
            # Period fields
            if extraction.period_start:
                doc["temporal"]["period_start"] = extraction.period_start
            if extraction.period_end:
                doc["temporal"]["period_end"] = extraction.period_end
            if extraction.period_start_year:
                doc["temporal"]["period_start_year"] = extraction.period_start_year
            if extraction.period_end_year:
                doc["temporal"]["period_end_year"] = extraction.period_end_year
            # Content time hierarchy
            if extraction.content_decade:
                doc["temporal"]["content_decade"] = extraction.content_decade
            if extraction.content_era:
                doc["temporal"]["content_era"] = extraction.content_era
            if extraction.content_year_min:
                doc["temporal"]["content_year_min"] = extraction.content_year_min
            if extraction.content_year_max:
                doc["temporal"]["content_year_max"] = extraction.content_year_max
            if extraction.content_year_primary:
                doc["temporal"]["content_year_primary"] = extraction.content_year_primary

            # Spatial extraction
            if extraction.locations:
                doc["extracted_locations"] = [
                    {"formatted_address": loc.get("name", ""), "hierarchy": {"country": loc.get("name", "")}}
                    for loc in extraction.locations[:10]
                ]
            if extraction.primary_jurisdiction:
                doc["metadata"]["extracted_jurisdiction"] = extraction.primary_jurisdiction

            # Red flag entity alerts (OFAC, sanctions)
            if extraction.has_red_flag_entity:
                doc["red_flag_alert"] = True
                doc["red_flag_entities"] = [
                    {"name": rf["name"], "list": rf["list"], "severity": rf["severity"]}
                    for rf in extraction.red_flag_entities[:10]
                ]

            # Extracted subjects (events/themes/topics from phenomena)
            doc["extracted_subjects"] = {
                "themes": [t["id"] for t in extraction.themes[:5]],
                "phenomena": [p["id"] for p in extraction.phenomena[:5]],
                "events": [p["id"] for p in extraction.phenomena if "event" in p["id"].lower()][:5],
                "topics": [p["id"] for p in extraction.phenomena if "genre" in p["id"].lower()][:5],
            }

            # TIERED EMBEDDING: Only store content_embedding for high-value documents
            if is_high_value_document(row, doc):
                try:
                    # Use extractor's model to compute 768-dim embedding
                    doc_text = text[:8000]  # Truncate for embedding
                    embedding = extractor.model.encode(f"passage: {doc_text}", convert_to_numpy=True)
                    doc["content_embedding"] = embedding.tolist()
                    doc["has_embedding"] = True
                    doc["embedding_reason"] = _get_embedding_reason(row, doc)
                except Exception as embed_err:
                    logger.warning(f"Embedding failed for {url[:50]}: {embed_err}")
                    doc["has_embedding"] = False
            else:
                doc["has_embedding"] = False

        except Exception as e:
            logger.warning(f"Extraction failed for {url[:50]}: {e}")

    # Dimension keys for fast filtering (from concepts + metadata)
    dimension_keys = set()
    concepts = doc.get("concepts", {}) or {}
    _add_dimension_keys(dimension_keys, "theme", concepts.get("themes"))
    _add_dimension_keys(dimension_keys, "phenomenon", concepts.get("phenomena"))
    _add_dimension_keys(dimension_keys, "red_flag", concepts.get("red_flag_themes"))
    _add_dimension_keys(dimension_keys, "method", concepts.get("methodologies"))
    _add_dimension_keys(dimension_keys, "sector", sectors)
    _add_dimension_keys(dimension_keys, "sector_red_flag", detected_red_flags)
    _add_dimension_keys(dimension_keys, "jurisdiction", [doc["metadata"].get("jurisdiction")])
    _add_dimension_keys(dimension_keys, "jurisdiction", [doc["metadata"].get("extracted_jurisdiction")])
    _add_dimension_keys(dimension_keys, "lang", [doc.get("language")])
    _add_dimension_keys(dimension_keys, "source", [SOURCE_TYPE])

    temporal = doc.get("temporal") or {}
    if isinstance(temporal, dict):
        _add_dimension_keys(dimension_keys, "year", temporal.get("content_years"))
        published = temporal.get("published_date")
        if published:
            match = re.search(r"\b(19|20)\d{2}\b", str(published))
            if match:
                _add_dimension_keys(dimension_keys, "year", [match.group(0)])

    if dimension_keys:
        doc["dimension_keys"] = sorted(dimension_keys)

    return doc


def _get_embedding_reason(row, doc: dict) -> str:
    """Return the reason why this document was flagged as high-value."""
    reasons = []
    if doc.get('metadata', {}).get('is_regulatory'):
        reasons.append('regulatory')
    if doc.get('metadata', {}).get('has_financial_tables'):
        reasons.append('financial_tables')
    if doc.get('metadata', {}).get('priority_score', 0) >= 80:
        reasons.append(f"priority_{doc['metadata']['priority_score']}")
    if doc.get('red_flag_alert'):
        reasons.append('red_flag')
    if doc.get('metadata', {}).get('is_annual_report'):
        reasons.append('annual_report')

    domain = str(row.get('domain', '') or '').lower()
    for registry in REGISTRY_DOMAINS:
        if registry in domain:
            reasons.append(f'registry:{registry}')
            break

    return ','.join(reasons) if reasons else 'unknown'


def index_parquet_to_cymonides(run_extraction: bool = True):
    """
    Main indexing function.

    Args:
        run_extraction: If True, run UniversalExtractor on each document for
                       semantic dimensions (themes, phenomena, temporal, spatial).
                       If False, index metadata only (fast mode).
    """
    logger.info(f"Connecting to Elasticsearch at {ES_HOST}...")
    es = Elasticsearch([ES_HOST], request_timeout=120, retry_on_timeout=True, max_retries=3)

    if not es.ping():
        logger.error("Cannot connect to Elasticsearch!")
        return False

    # Check if index exists
    if not es.indices.exists(index=INDEX):
        logger.error(f"Index {INDEX} does not exist!")
        return False

    logger.info(f"Index {INDEX} found. Starting indexing...")
    if run_extraction:
        logger.info("FULL EXTRACTION MODE: Running UniversalExtractor (265 categories)")
        logger.info("This will take longer but extract themes/phenomena/temporal/spatial")
    else:
        logger.info("FAST MODE: Skipping extraction, metadata only")

    # Find parquet files
    parquet_files = sorted(PARQUET_DIR.glob("corporate_pdfs_*.parquet"))

    if not parquet_files:
        logger.error(f"No parquet files found in {PARQUET_DIR}")
        return False

    logger.info(f"Found {len(parquet_files)} parquet files")

    total_indexed = 0
    total_failed = 0
    total_extracted = 0
    total_with_embedding = 0

    for pq_file in parquet_files:
        logger.info(f"\nProcessing {pq_file.name}...")

        try:
            table = pq.read_table(pq_file)
            df = table.to_pandas()
            logger.info(f"  Loaded {len(df):,} records")
        except Exception as e:
            logger.error(f"  Failed to read {pq_file}: {e}")
            continue

        actions = []

        for idx, row in df.iterrows():
            url = str(row.get('url', '') or '')
            if not url:
                continue

            # Generate doc ID
            doc_id = f"cc-pdf-2025_{hashlib.md5(url.encode()).hexdigest()}"

            try:
                doc = build_document(row, doc_id, run_extraction=run_extraction)
                actions.append({
                    "_index": INDEX,
                    "_id": doc_id,
                    "_source": doc,
                })
                if "concepts" in doc:
                    total_extracted += 1
                if doc.get("has_embedding"):
                    total_with_embedding += 1
            except Exception as e:
                logger.warning(f"  Failed to build doc for {url[:50]}: {e}")
                continue

            # Bulk index in batches
            if len(actions) >= BATCH_SIZE:
                success, failed = bulk(es, actions, raise_on_error=False, stats_only=True)
                total_indexed += success
                total_failed += failed
                embed_pct = (total_with_embedding / max(total_extracted, 1)) * 100
                logger.info(f"  Indexed batch: {success} ok, {failed} failed (total: {total_indexed:,}, extracted: {total_extracted:,}, embeddings: {total_with_embedding:,} [{embed_pct:.1f}%])")
                actions = []

        # Index remaining
        if actions:
            success, failed = bulk(es, actions, raise_on_error=False, stats_only=True)
            total_indexed += success
            total_failed += failed
            logger.info(f"  Final batch: {success} ok, {failed} failed")

    logger.info(f"\n{'='*60}")
    logger.info(f"INDEXING COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Total indexed: {total_indexed:,}")
    logger.info(f"Total failed: {total_failed:,}")
    logger.info(f"Total with extraction: {total_extracted:,}")
    logger.info(f"Total with embedding: {total_with_embedding:,} (high-value docs)")
    logger.info(f"Flags-only (no embedding): {total_extracted - total_with_embedding:,}")
    if total_extracted > 0:
        embed_pct = (total_with_embedding / total_extracted) * 100
        storage_saved = 100 - embed_pct
        logger.info(f"Embedding rate: {embed_pct:.1f}% ({storage_saved:.1f}% storage saved)")
    logger.info(f"Source type: {SOURCE_TYPE}")
    logger.info(f"{'='*60}")

    return True


def verify_indexed():
    """Verify indexed documents with aggregation query."""
    es = Elasticsearch([ES_HOST])

    result = es.search(
        index=INDEX,
        body={
            "size": 0,
            "query": {"term": {"source_type": SOURCE_TYPE}},
            "aggs": {
                "total_docs": {"value_count": {"field": "source_type"}},
                "by_jurisdiction": {"terms": {"field": "metadata.jurisdiction", "size": 20}},
                "by_regulatory": {"terms": {"field": "metadata.is_regulatory"}},
                "by_sectors": {"terms": {"field": "metadata.sectors", "size": 10}},
                "by_embedding": {"terms": {"field": "has_embedding"}},
                "embedding_reasons": {"terms": {"field": "embedding_reason.keyword", "size": 20}},
            }
        }
    )

    hits = result['hits']['total']['value']
    logger.info(f"\n=== VERIFICATION ===")
    logger.info(f"Documents with source_type={SOURCE_TYPE}: {hits:,}")

    if 'aggregations' in result:
        aggs = result['aggregations']

        # Embedding stats (tiered storage)
        if 'by_embedding' in aggs:
            logger.info(f"\nEmbedding Distribution (Tiered Storage):")
            with_embed = 0
            without_embed = 0
            for bucket in aggs['by_embedding']['buckets']:
                if bucket['key_as_string'] == 'true':
                    with_embed = bucket['doc_count']
                    logger.info(f"  With embedding (high-value): {bucket['doc_count']:,}")
                else:
                    without_embed = bucket['doc_count']
                    logger.info(f"  Flags-only (no embedding): {bucket['doc_count']:,}")
            if with_embed + without_embed > 0:
                pct = (without_embed / (with_embed + without_embed)) * 100
                logger.info(f"  Storage saved: {pct:.1f}%")

        if 'embedding_reasons' in aggs and aggs['embedding_reasons']['buckets']:
            logger.info(f"\nEmbedding Reasons (why high-value):")
            for bucket in aggs['embedding_reasons']['buckets'][:10]:
                logger.info(f"  {bucket['key']}: {bucket['doc_count']:,}")

        if 'by_jurisdiction' in aggs:
            logger.info(f"\nBy Jurisdiction:")
            for bucket in aggs['by_jurisdiction']['buckets'][:10]:
                logger.info(f"  {bucket['key']}: {bucket['doc_count']:,}")

        if 'by_regulatory' in aggs:
            logger.info(f"\nBy Regulatory:")
            for bucket in aggs['by_regulatory']['buckets']:
                logger.info(f"  {bucket['key']}: {bucket['doc_count']:,}")

        if 'by_sectors' in aggs:
            logger.info(f"\nTop Sectors:")
            for bucket in aggs['by_sectors']['buckets'][:5]:
                logger.info(f"  {bucket['key']}: {bucket['doc_count']:,}")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Index FINEPDFS to cymonides-2 with semantic extraction")
    parser.add_argument('--verify-only', action='store_true', help="Only verify, don't index")
    parser.add_argument('--skip-extraction', action='store_true',
                       help="Skip UniversalExtractor (fast mode, metadata only)")
    args = parser.parse_args()

    if args.verify_only:
        verify_indexed()
    else:
        run_extraction = not args.skip_extraction
        success = index_parquet_to_cymonides(run_extraction=run_extraction)
        if success:
            verify_indexed()
