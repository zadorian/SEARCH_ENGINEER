# Index Unification Master Plan

**Generated:** 2026-01-04
**Status:** ACTIVE
**Total Indices:** 79
**Total Documents:** ~1.9B
**Total Storage:** ~305GB

---

## Overview

This document is the master reference for unifying 79 Elasticsearch indices into coherent entity views. The core principle is **APPEND_ALL** - nothing is overwritten, everything is preserved for semantic search.

---

## CSV Reference Files

| File | Purpose | Rows |
|------|---------|------|
| **`index_status.csv`** | **Master status of all 100 indices** | **100** |
| `index_field_audit.csv` | Field presence audit across 79 indices | 79 |
| `index_field_mapping.csv` | Field-to-field transformations with quality tiers | 161 |
| `index_field_contributions.csv` | Multi-target contributions per index | 147 |
| `index_unification_plan.csv` | Source-to-target mappings with merge strategies | 59 |
| `field_merge_rules.csv` | Per-field merge behavior (APPEND_ALL vs CANONICAL) | 61 |
| `index_geo_extraction.csv` | Geospatial field extraction mapping | 17 |
| `index_temporal_extraction.csv` | Temporal field extraction mapping | 19 |

---

## Index Status Summary

### By Status (100 total indices)

| Status | Count | Description |
|--------|-------|-------------|
| **PRODUCTION** | 74 | Active, usable indices |
| **EPHEMERAL** | 19 | Project-specific, temporary |
| **INCOMPLETE** | 4 | Missing data, needs population |
| **DUPLICATE** | 1 | `search_nodes_v3` = duplicate of `red_flag` |
| **EMPTY** | 1 | `nexus_edges` = 0 docs |
| **LEGACY** | 1 | `io_routes` = may be superseded |

### By Quality

| Quality | Count | Examples |
|---------|-------|----------|
| **HIGH** | 69 | atlas, linkedin_unified, uk_ccod |
| **MEDIUM** | 21 | Project indices, drill_entities |
| **MIXED** | 2 | companies_unified (name field garbage), breach_records (name field garbage) |
| **CONTAMINATED** | 2 | drill_pages, onion-pages (30-50% NER errors) |
| **SPARSE** | 1 | domains_unified (83% unenriched) |
| **PARTIAL** | 1 | openownership (subject_name empty) |
| **GARBAGE** | 1 | persons_unified (full_name unusable) |
| **CORRUPTED** | 1 | emails_unified (email_domain, local_part corrupted) |

### By Category

| Category | Count | Total Docs |
|----------|-------|------------|
| EDGE_GRAPH | 5 | ~1.2B |
| ENTITY_DOMAIN | 5 | ~360M |
| PROJECT_EPHEMERAL | 19 | ~100K |
| EDGE_ET3 | 6 | ~400K |
| WDC_ENTITY | 5 | ~37M |
| CORPUS | 6 | ~14M |
| UK_PROPERTY | 4 | ~16M |
| METADATA | 6 | ~110K |

### Problem Indices (Require Attention)

| Index | Status | Issue | Action |
|-------|--------|-------|--------|
| `search_nodes_v3` | DUPLICATE | Exact copy of red_flag | **SKIP** - use red_flag |
| `nexus_edges` | EMPTY | 0 documents | **POPULATE** or delete |
| `emails_unified` | CORRUPTED | Only 5K docs, fields corrupted | **REBUILD** from breach_records |
| `persons_unified` | GARBAGE | full_name is NER failures | **USE** linkedin_unified instead |
| `domains_unified` | SPARSE | 83% unenriched | **FILTER** by exists:categories |
| `company_profiles` | INCOMPLETE | Only 496 profiles | **POPULATE** from Torpedo |
| `nexus_nodes` | INCOMPLETE | Only 698 nodes | **POPULATE** from unification |

---

## Unification Targets

### Primary Entity Indices

| Target | Primary Sources | Doc Count | Key Fields |
|--------|-----------------|-----------|------------|
| **DOMAIN_UNIFIED** | atlas, domains_unified, cc_host_vertices | ~550M | domain, categories, ranks, company_name |
| **COMPANY_UNIFIED** | companies_unified, openownership, wdc-organization | ~70M | legal_name, company_number, jurisdiction |
| **PERSON_UNIFIED** | linkedin_unified, wdc-person, openownership | ~50M | person_name, job_title, employer |
| **EMAIL_UNIFIED** | breach_records, kazaword_emails | ~190M | email, breach_names, person_ids |
| **PHONE_UNIFIED** | phones_unified, wdc entities | ~100K | phone_e164, person_ids, company_ids |

### Specialized Indices

| Target | Primary Sources | Doc Count | Key Fields |
|--------|-----------------|-----------|------------|
| **BREACH_UNIFIED** | breach_records, nexus_breach_records | ~189M | email, breach_name, breach_year |
| **RED_FLAG** | red_flag (authoritative) | ~2M | sanctions, PEP, adverse media |
| **UK_PROPERTY** | uk_ccod, uk_addresses, uk_leases, uk_ocod | ~16M | title_number, proprietor, address |

### Graph/Edge Indices

| Target | Primary Sources | Edge Count | Purpose |
|--------|-----------------|------------|---------|
| **EDGE_DOMAIN** | cc_web_graph_*, cymonides_cc_domain_edges | ~870M | Domain link graph |
| **EDGE_ENTITY** | entity_links, entity-mentions, et3-* | ~12M | Entity relationships |
| **EDGE_ONION** | onion-graph-edges | ~268K | Dark web links |

---

## Critical Data Quality Warnings

### GARBAGE Fields (NEVER QUERY)

| Index | Field | Problem | Use Instead |
|-------|-------|---------|-------------|
| `persons_unified` | `full_name` | NER failures, article titles, locations | `linkedin_unified.person_name` |
| `companies_unified` | `name` | Mixed entities, duplicates | `companies_unified.legal_name` |
| `breach_records` | `name` | Usernames, article titles | `email` field only |
| `drill_pages` | `persons`, `companies` | 30-50% contamination | Cross-validate |
| `onion-pages` | `persons`, `companies` | 30-50% contamination | Cross-validate |

### CORRUPTED Fields (DO NOT USE)

| Index | Field | Problem |
|-------|-------|---------|
| `emails_unified` | `email_domain` | Data corruption |
| `emails_unified` | `local_part` | Data corruption |

### EMPTY Fields (0% POPULATED)

| Index | Field | Problem |
|-------|-------|---------|
| `openownership` | `subject_name` | Use `interested_party_name` instead |

### SPARSE Indices

| Index | Issue | Workaround |
|-------|-------|------------|
| `domains_unified` | 83.7% unenriched | Filter by `exists: categories` |

---

## Merge Strategies

### Record Matching (`merge_strategy`)

| Strategy | When Used | Example |
|----------|-----------|---------|
| `MERGE_BY_DOMAIN` | Domain-centric indices | atlas + domains_unified |
| `MERGE_BY_ID` | Has unique identifier | companies_unified (company_id) |
| `MERGE_BY_COMPANY_NUMBER` | Registry number matching | openownership |
| `MERGE_BY_LINKEDIN` | LinkedIn URL is key | linkedin_unified |
| `MERGE_BY_EMAIL` | Email is key | emails_unified |
| `MERGE_BY_PHONE` | Phone is key | phones_unified |
| `KEEP_ALL` | Each record unique | Edges, breaches, corpus |
| `ADD_IF_NEW` | Only add non-existing | cc_host_vertices |
| `SKIP` | Duplicate index | search_nodes_v3 |

### Value Handling (`value_merge_strategy`)

| Strategy | Behavior | Use For |
|----------|----------|---------|
| `APPEND_ALL` | Keep ALL values from ALL sources | Names, categories, addresses |
| `KEEP_ALL` | Each record inherently unique | Edges, corpus docs |

### Field Deduplication (`dedupe_method` in field_merge_rules.csv)

| Method | Behavior | Example |
|--------|----------|---------|
| `NONE` | Keep ALL including semantic duplicates | "finance" + "financial services" + "banking" |
| `EXACT` | Dedupe exact string matches only | Emails, sources |
| `CASE_INSENSITIVE` | Dedupe ignoring case | john@acme.com = JOHN@ACME.COM |
| `E164_NORMALIZE` | Normalize phones, then dedupe | +44 20 7123 4567 = +442071234567 |
| `NORMALIZE_CODE` | Normalize country codes | UK = GB = United Kingdom |

---

## Embedding Integration

### Existing Vector Databases (5)

| Embedding Index | Dimensions | Filters | Doc Count |
|-----------------|------------|---------|-----------|
| `domain_category_embeddings` | 384 | DOMAIN_UNIFIED (categories) | ~5K |
| `industry_embeddings.json` | 384 | linkedin_unified (industry) | ~150 |
| `matrix_type_embeddings` | 384 | IO Matrix routing | 2,461 |
| `concept_embeddings.json` | 3072 | LINKLATER tagging | ~50 |
| `cymonides-2.embedded_edges` | 3072 | RAG content | 13M+ |

### Planned Embeddings (5 Priority)

| Opportunity | Effort | Impact | Filters |
|-------------|--------|--------|---------|
| Schema.org types | LOW (200) | HIGH (10M entities) | wdc-organization, wdc-localbusiness |
| Geographic regions | MEDIUM | HIGH (4.3M properties) | uk_ccod, linkedin |
| Job title clusters | MEDIUM | HIGH (2.9M profiles) | linkedin_unified |
| Legal entity designators | LOW (50) | MEDIUM | uk_ccod, openownership |
| Red flag terms | LOW (200) | HIGH | red_flag |

---

## Geospatial Extraction

### Status Summary

| Status | Count | Indices |
|--------|-------|---------|
| ✅ DONE | 4 | uk_ccod, uk_addresses, uk_ocod, wdc-localbusiness |
| 🔶 PARTIAL | 5 | breach_records, linkedin, openownership, persons, wdc-org |
| ⏳ TODO | 8 | companies_unified, red_flag, cymonides-2, etc. |

### Extraction Methods

| Method | Used For | Tool |
|--------|----------|------|
| `POSTCODE_LOOKUP` | UK postcodes | `geospatial/geocode_postcodes.py` |
| `NOMINATIM` | Free-text addresses | `geospatial/geocode_entities.py` |
| `CONVERT_LAT_LON` | Existing coordinates | `geospatial/convert_wdc_coords.py` |
| `CONTENT_EXTRACTION` | NER from text | TBD |

---

## Temporal Extraction

### Status Summary

| Status | Count | Indices |
|--------|-------|---------|
| ✅ DONE | 6 | breach_records, uk_ccod, uk_leases, et3-nodes, etc. |
| 🔶 PARTIAL | 8 | cymonides-2, companies_unified, wdc-person, etc. |
| ⏳ TODO | 5 | linkedin_unified, onion-pages, etc. |

### Derived Fields (from `temporal_hierarchy.py`)

| Field | Type | Example |
|-------|------|---------|
| `year` | integer | 2024 |
| `month` | integer | 6 |
| `day` | integer | 15 |
| `yearmonth` | keyword | "2024-06" |
| `decade` | keyword | "2020s" |
| `era` | keyword | "post_covid" |
| `content_years` | array | [2019, 2020, 2021] |
| `temporal_focus` | keyword | "historical" / "current" / "future" |

### Era Definitions

| Era | Years |
|-----|-------|
| cold_war | 1947-1991 |
| post_soviet | 1991-2000 |
| pre_2008 | 2000-2008 |
| post_2008 | 2008-2019 |
| covid_era | 2020-2022 |
| post_covid | 2023+ |

---

## Pattern Extraction (PACMAN Integration)

### Overview

Pattern extraction from PACMAN has been integrated into the consolidation pipeline. This enables automatic extraction of structured identifiers from unstructured content during consolidation.

### Pattern Extractor Location

`BACKEND/modules/ATLAS/loaders/pattern_extractor.py`

### Supported Pattern Types

| Category | Patterns | Examples |
|----------|----------|----------|
| **Legal Entity IDs** | LEI, UK_CRN, DE_HRB, SEC_CIK, FR_SIREN, NL_KVK, etc. | `5493001KJTIIGC8Y1R12`, `12345678` |
| **Aircraft** | US_FAA, UK_CAA, DE_LBA, FR_DGAC, etc. (20 countries) | `N12345`, `G-ABCD` |
| **Vessels** | IMO, MMSI, CALL_SIGN | `IMO 1234567` |
| **Court Cases** | US_FED, UK_NEUTRAL, EU_CASE, ECHR | `1:23-cv-00456` |
| **Bank Accounts** | IBAN, SWIFT, UK_BANK, US_ROUTING | `GB82WEST12345698765432` |
| **Cryptocurrency** | BTC, BTC_BECH32, ETH, XMR, TRX | `0x742d35Cc...` |
| **Red Flags** | Tripwire matching against `red_flag` index | Sanctions, PEP, adverse media |

### Usage in Consolidation

```python
from ATLAS.loaders.base_consolidator import BaseConsolidator

class MyConsolidator(BaseConsolidator):
    def __init__(self):
        super().__init__(enable_pattern_extraction=True)
        self.load_tripwires()  # Load 1.95M entities from red_flag

    def merge_into_entity(self, entity, doc, source):
        # Auto-extract patterns from content
        if 'content' in doc:
            extracted = self.extract_patterns_from_content(doc['content'])
            if extracted:
                entity.extracted_ids = extracted.get('legal_ids', [])
                entity.red_flags = extracted.get('red_flags', [])
```

### Index Mapping for Extracted Fields

```python
from ATLAS.loaders.base_consolidator import (
    get_extracted_ids_mapping,
    get_red_flags_mapping,
)

# Add to your index mapping:
"extracted_ids": get_extracted_ids_mapping(),  # nested
"red_flags": get_red_flags_mapping(),          # nested
```

### Context Extraction

All extractions include 5 words before and 5 words after the match for context:
```
"a UK company with LEI [5493001KJTIIGC8Y1R12] . Their IBAN is"
```

---

## Implementation Priority

### Phase 1: Fix Quality Issues
1. Mark GARBAGE fields in search UI (prevent queries)
2. Add quality warnings to API responses
3. Document preferred sources

### Phase 2: Domain Unification
1. Merge atlas + domains_unified + top_domains
2. Preserve ALL categories (APPEND_ALL)
3. Add domain_category_embeddings filtering

### Phase 3: Entity Unification
1. COMPANY_UNIFIED from companies_unified + openownership + wdc-org
2. PERSON_UNIFIED from linkedin_unified + wdc-person
3. Cross-link via domain, email, phone

### Phase 4: Geo/Temporal Enrichment
1. Complete geocoding for remaining indices
2. Derive temporal hierarchy for all date fields
3. Build geographic_region_embeddings

### Phase 5: Graph Integration
1. Link all unified entities via edges
2. Build NEXUS cross-domain nodes
3. Enable graph traversal queries

---

## Related Documents

| Document | Location | Purpose |
|----------|----------|---------|
| Architecture Plan | `CYMONIDES/UNIFIED_SEARCH_ARCHITECTURE_PLAN.md` | Master architecture |
| Strategic Embeddings | `CYMONIDES/strategic_embeddings.json` | Embedding opportunities |
| Field Groups | `CYMONIDES/field_groups.json` | Quality ratings |
| Consolidation Scripts | `CYMONIDES/ingest/consolidate_*.py` | Existing scripts |
| Base Consolidator | `ATLAS/loaders/base_consolidator.py` | Consolidation framework |
| Pattern Extractor | `ATLAS/loaders/pattern_extractor.py` | PACMAN pattern extraction |
| PACMAN Source | `CYMONIDES/ingest/sources/Pacman.py` | Original tier classification |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-01-04 | Initial creation with 7 CSVs |
| 2026-01-04 | Added geo/temporal extraction mappings |
| 2026-01-04 | Added APPEND_ALL principle for all multi-value fields |
| 2026-01-04 | Integrated PACMAN pattern extraction into consolidation pipeline |
