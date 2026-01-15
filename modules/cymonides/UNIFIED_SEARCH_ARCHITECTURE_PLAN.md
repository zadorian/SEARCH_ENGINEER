# UNIFIED SEARCH ARCHITECTURE PLAN
**Generated: 2025-12-30** | **Updated: 2026-01-02**
**Consolidated from: query_patterns.json, strategic_embeddings.json, multidimensional_indexing.json**

---

## ⚠️ CRITICAL DATA QUALITY WARNINGS

> **READ BEFORE QUERYING ANY INDEX**

| Index | Field | Issue | Action |
|-------|-------|-------|--------|
| `openownership` | `subject_name` | **0% populated** - mapping exists but field empty | Use `interested_party_name` or `company_number` instead |
| `domains_unified` | (general) | **83.7% unenriched** - only 16.3% have category data | Filter by `exists: {field: "categories"}` for enriched subset |
| `persons_unified` | `full_name` | **GARBAGE** - NER failures, article titles, locations | DO NOT USE for person search |
| `companies_unified` | `name` | **GARBAGE** - mixed entity types, duplicates | Use `linkedin_unified.company_name` instead |
| `breach_records` | `name` | **GARBAGE** - usernames, article titles | Use `email` field only |
| `drill_pages` | `persons`, `companies` | **30-50% contamination** | Cross-validate with other indices |
| `emails_unified` | `email_domain`, `local_part` | **CORRUPTED** - do not use | Use `breach_records.email_domain` |

---

## EXECUTIVE SUMMARY

This plan defines how to query, filter, and enrich 1.7B documents across 150+ Elasticsearch indices using:
1. **43 Semantic Field Groups** - Unified field names across indices (35 in field_groups.json, 41 queryable in query_patterns.json)
2. **5 Existing Vector Databases** - Already operational for semantic search
3. **11 New Embedding Opportunities** - Small vectors, massive filtering power
4. **8 Multi-Dimensional Filters** - Compound queries across entity/location/time/ownership

**Core Philosophy**: "Embed the metadata, not the content. 1K embeddings can filter 100M records."

---

## PART 1: EXISTING INFRASTRUCTURE

### 1.1 Vector Databases Already Operational

| Name | Location | Docs | Dims | Filters |
|------|----------|------|------|---------|
| **Domain Categories** | ES: `domain_category_embeddings` | ~5K | 384 | 178M domains |
| **LinkedIn Industries** | `BACKEND/modules/CYMONIDES/industry_embeddings.json` | ~150 | 384 | 2.9M profiles |
| **IO Matrix Types** | ES: `matrix_type_embeddings` | 2,461 | 384 | Query routing |
| **LINKLATER Concepts** | `.cache/concept_embeddings.json` | ~50 | 3072 | Content tagging |
| **RAG Content** | ES: `cymonides-2` | 13M+ | 3072 | Domain Q&A |

### 1.2 Existing Indexed Dimensions

| Dimension | Source | Values | Searchable |
|-----------|--------|--------|------------|
| entity_type | entity_links, openownership | company, person | ✅ |
| jurisdiction | openownership, uk_ccod | ISO codes + UK regions | ✅ |
| industry | linkedin_unified | ~150 industries | ✅ + embedded |
| domain_category | domains_unified | ~5K DMOZ categories | ✅ + embedded |

---

## PART 2: FIELD GROUPS (43 Total)

### 2.1 HIGH Quality Groups (Use for Search)

| Group | Status | Fields | Indices | Use Case |
|-------|--------|--------|---------|----------|
| **PERSON_NAME** | SPARSE_BUT_CLEAN | interested_party_name | openownership | High-precision person search |
| **COMPANY_NAME** | EXCELLENT | proprietor_name_1^3, company_name^2, owner_name | uk_ccod, linkedin, uk_addresses, uk_ocod | Cross-index company search |
| **EMAIL_RAW** | EXCELLENT | email, all_emails | breach_records, kazaword, onion-pages | Email lookup + provider patterns |
| **EMAIL_DOMAIN** | EXCELLENT | email_domain | breach_records | Fast domain filtering (*.ru, *.uk) |
| **PHONE_FULL** | EXCELLENT | phone_e164, phone_raw | phones_unified | E.164 lookup + raw input |

### 2.2 MEDIUM Quality Groups (Use with Caution)

| Group | Warning | Use Case |
|-------|---------|----------|
| MIXED_NAME | Contains "ltd ltd ltd" duplicates | Fallback when PERSON + COMPANY fail |
| EMAIL_OBJECT | Index appears empty | Search by sender NAME |

### 2.3 GARBAGE Groups (Exclude from Search)

| Group | Problem |
|-------|---------|
| GARBAGE_NAME | NER failures: article titles, usernames, locations mixed in |

**Fields to Avoid:**
- `persons_unified.full_name`
- `companies_unified.name`
- `breach_records.name`
- `drill_pages.persons`, `drill_pages.companies`

---

## PART 3: NEW EMBEDDING OPPORTUNITIES

### Priority 1: Schema.org Types (LOW effort, HIGH impact)
- **Source**: wdc-organization-entities.type, wdc-localbusiness-entities.type
- **Cardinality**: ~200 types
- **Filters**: 10M WDC entities
- **Leverage**: 50,000x
- **Example**: User searches "banks" → matches FinancialService, Bank, CreditUnion

### Priority 2: Geographic Regions (MEDIUM effort, HIGH impact)
- **Source**: uk_ccod.county, uk_ccod.district
- **Cardinality**: ~60 counties, ~400 districts
- **Filters**: 4.3M UK properties + 2.9M LinkedIn
- **Example**: "properties in Northern England" → expands to GREATER MANCHESTER, MERSEYSIDE, LANCASHIRE

### Priority 3: Job Title Clusters (MEDIUM effort, HIGH impact)
- **Source**: linkedin_unified.headline
- **Strategy**: Cluster 50K titles into ~500 semantic groups
- **Example**: "executives" → matches CEO, Managing Director, President, Chairman

### Priority 4: Legal Entity Designators (LOW effort, MEDIUM impact)
- **Source**: Extracted from company names
- **Cardinality**: ~50 designators
- **Example**: "public companies" → matches PLC, AG

### Priority 5: Red Flag Terms (LOW effort, HIGH impact)
- **Cardinality**: ~200 investigation terms
- **Categories**:
  - Sanctions: SDN, OFAC, blacklisted, designated
  - Fraud: ponzi, pyramid scheme, embezzlement
  - PEP: politically exposed, government official
  - Distress: liquidation, insolvency, dissolved
- **Example**: "suspicious companies" → ranks by red flag term density

### Priority 6: Source Type Credibility (LOW effort, HIGH impact)
- **Source**: Derive from `source_type`, `source`, publisher patterns
- **Cardinality**: ~20 credibility tiers
- **Values**:
  - `official_register` → Companies House, SEC EDGAR, official gazettes
  - `regulatory_filing` → Annual reports, prospectuses, 10-Ks
  - `news_major` → Reuters, Bloomberg, FT, WSJ
  - `news_local` → Regional newspapers, trade press
  - `aggregator` → OpenCorporates, similar aggregators
  - `user_generated` → LinkedIn, social media profiles
  - `unverified` → Scraped web, forums, blogs
- **Leverage**: 100M+ documents gain credibility score
- **Example**: "Find all companies + only official sources" → filters to registry data

### Priority 7: Product/Service Taxonomy (MEDIUM effort, HIGH impact)
- **Source**: Schema.org types + DMOZ categories + custom mapping
- **Cardinality**: ~500 product/service categories
- **Strategy**: Map WDC entity types to standardized product taxonomy
- **Categories**:
  - Financial: banking, insurance, investment, crypto
  - Real Estate: residential, commercial, development
  - Legal: law firm, notary, corporate services
  - Professional: accounting, consulting, audit
- **Example**: "offshore service providers" → matches CSPs, trust companies, nominee services

### Priority 8: Investigation Phenomenon Embeddings (LOW effort, HIGH impact)
- **Cardinality**: ~30 phenomenon patterns
- **Values**:
  - `shell_company` → Indicators: no employees, registered agent, offshore
  - `nominee_director` → Indicators: mass directorships, corporate director
  - `layered_ownership` → Indicators: >3 ownership layers, trust/foundation
  - `rapid_turnover` → Indicators: <2 year lifespan, frequent officer changes
  - `circular_ownership` → Indicators: A owns B owns C owns A patterns
- **Example**: "find shell companies" → semantic match to phenomenon indicators

---

## PART 4: MULTI-DIMENSIONAL FILTERING

### 4.1 New Ordinal Dimensions to Derive

| Dimension | Source | Values | Purpose |
|-----------|--------|--------|---------|
| **ownership_strength** | entity_links.ownership_pct + control_types | passive → minority → significant → board → full | Filter by control level |
| **security_tier** | breach_records.hash_type | critical (plaintext) → poor (sha1) → moderate (3des) → good (bcrypt) | Filter by breach severity |
| **credibility_tier** | wdc-*.publisher | official → institutional → media → user-generated | Filter by source reliability |
| **ownership_recency** | entity_links.first_seen | new_2024 → stable_3y → legacy → historic | Filter by ownership age |

### 4.2 Compound Filter Examples

**Investigation Filters:**
```
Person + UK + >25% ownership + acquired 2020-2024 + in breach records
Company + offshore jurisdiction + multiple ownership layers + property assets
Email + plaintext breach + same domain as company officer
```

**Red Flag Filters:**
```
Ownership chains > 3 layers + offshore + recent changes
Same person + multiple companies + different jurisdictions + rapid turnover
Domain + high-risk category + breach exposure + PEP connections
```

### 4.3 Elasticsearch Compound Query Pattern
```json
{
  "bool": {
    "must": [
      {"term": {"entity_type": "company"}},
      {"term": {"jurisdiction": "UK"}},
      {"range": {"ownership_pct": {"gte": 25}}},
      {"range": {"first_seen": {"gte": "2020-01-01"}}}
    ]
  }
}
```

### 4.4 Dimension Keys: Allowlist & Denylist

**dimension_keys** are normalized `prefix:value` strings for multi-dimensional filtering.
Not all dimensions are suitable for intersection queries.

#### ✅ ALLOWLIST (Use for Intersections)

| Prefix | Cardinality | Example Values | Rationale |
|--------|-------------|----------------|-----------|
| `theme:` | ~50 | `theme:offshore`, `theme:sanctions` | Investigation themes - core filtering |
| `phenomenon:` | ~30 | `phenomenon:shell_company`, `phenomenon:nominee` | Red flag patterns |
| `red_flag:` | ~200 | `red_flag:pep`, `red_flag:ofac_sdn` | Tripwire matches |
| `sector:` | ~150 | `sector:banking`, `sector:real_estate` | LinkedIn industry mappings |
| `jurisdiction:` | ~250 | `jurisdiction:GB`, `jurisdiction:VG` | ISO country + offshore codes |
| `year:` | ~50 | `year:2020`, `year:2024` | Temporal bucketing |
| `entity_type:` | ~10 | `entity_type:company`, `entity_type:person` | BODS classification |
| `control_type:` | ~5 | `control_type:shareholding`, `control_type:voting` | Ownership nature |
| `tenure:` | ~3 | `tenure:freehold`, `tenure:leasehold` | UK property type |
| `hash_type:` | ~10 | `hash_type:plaintext`, `hash_type:bcrypt` | Breach severity |
| `source_type:` | ~20 | `source_type:officialRegister`, `source_type:news` | Provenance tier |
| `region:` | ~15 | `region:GREATER_LONDON`, `region:SCOTLAND` | UK macro geography |
| `county:` | ~100 | `county:WEST_YORKSHIRE` | UK administrative |

#### ⚠️ IDENTIFIERS (Use for Lookup, NOT Intersection)

These are **essential for direct lookup** but don't belong in intersection/facet queries:

| Prefix | Cardinality | Use For | NOT For |
|--------|-------------|---------|---------|
| `domain:` | 178M+ | Direct lookup: "all records for acme.com" | Faceting: useless to count 178M unique values |
| `email:` | 37M+ | Direct lookup: "find john@acme.com" | Intersection: no categorical grouping |
| `url:` | Unbounded | Direct lookup: "find this exact page" | Aggregation: every URL is unique |
| `phone:` | 50K+ | Direct lookup: "who owns +44..." | Faceting: each number is an identifier |
| `company_number:` | 11M+ | Direct lookup: "find company 08641349" | Intersection: it's a primary key |
| `title_number:` | 4M+ | Direct lookup: "find title WYK803313" | Aggregation: unique identifiers |
| `postcode:` | 1M+ | Direct lookup + local clustering | Intersection at scale: too granular |
| `ip_address:` | Unbounded | Direct lookup + /24 prefix analysis | Faceting: unique identifiers |
| `email_domain:` | 10M+ | Direct lookup: "*@acme.com" | Intersection: use `tld:` instead for jurisdiction |

**Key insight**: These are LOOKUP dimensions, not FILTERING dimensions. Use them to find specific entities, not to categorize/intersect.

#### ⚠️ CONDITIONAL (Use with Aggregation First)

| Prefix | Cardinality | When to Use |
|--------|-------------|-------------|
| `breach_name:` | ~500 | Aggregate first, then filter by top breaches |
| `tld:` | ~1500 | Aggregate first, then use for jurisdiction proxy |
| `district:` | ~400 | Use when region is too coarse |

---

## PART 5: QUERY PATTERNS BY DATA TYPE

### 5.1 Email Queries
| Pattern | Query | Sample Hits |
|---------|-------|-------------|
| Exact | `{"term": {"email.keyword": "user@gmail.com"}}` | 1 |
| Domain wildcard | `{"wildcard": {"email": "*@gmail.com"}}` | 33.2M |
| Local wildcard | `{"wildcard": {"email": "admin@*"}}` | 107K |
| Prefix | `{"prefix": {"email": "test"}}` | 68.9K |

### 5.2 Company Queries
| Pattern | Query | Use Case |
|---------|-------|----------|
| Exact | `{"term": {"proprietor_name_1.keyword": "ACME LIMITED"}}` | Known company |
| Match | `{"match": {"proprietor_name_1": "ACME"}}` | Fuzzy match |
| Multi-match | `{"multi_match": {"query": "$COMPANY", "fields": ["proprietor_name_1^3", "company_name^2"]}}` | Cross-index |
| Wildcard | `{"wildcard": {"proprietor_name_1.keyword": "*LIMITED"}}` | Find all LTDs |

### 5.3 Phone Queries
| Pattern | Query | Use Case |
|---------|-------|----------|
| E.164 exact | `{"term": {"phone_e164": "+12127940044"}}` | Programmatic lookup |
| Country prefix | `{"prefix": {"phone_e164": "+44"}}` | All UK numbers |
| Area code | `{"term": {"area_code": "212"}}` | NYC area (caution: not unique) |

---

## PART 5.5: QUERY ROUTING

### How Field Groups Connect to Query Execution

```
User Query → IO Router → Field Group Resolver → Query Patterns → Elasticsearch
                ↓                  ↓                    ↓
           flows.json    field_group_resolver.py   query_patterns.json
```

### File Responsibilities

| File | Location | Purpose |
|------|----------|---------|
| `field_groups.json` | `input_output/matrix/` | Defines 43 semantic groups with quality ratings |
| `query_patterns.json` | `input_output/matrix/` | Per-index query templates for 41 queryable groups |
| `field_group_resolver.py` | `input_output/matrix/` | Python resolver: input → group → fields → indices |
| `flows.json` | `input_output/matrix/` | IO Matrix routes: input_type → output_type → module |

### Resolution Flow Example

```python
# User searches: "john.smith@acme.com"

# 1. IO Router detects email pattern
input_type = "email"  # from flows.json input detection

# 2. Field Group Resolver maps to group
from field_group_resolver import resolve_group
group = resolve_group(input_type)  # Returns "EMAIL_RAW"

# 3. Query Patterns provides ES query
patterns = query_patterns["EMAIL"]["EMAIL_RAW"]
# Returns: {"term": {"email.keyword": "john.smith@acme.com"}}

# 4. Execute across mapped indices
indices = patterns["group_total"]["indices"]
# Returns: ["breach_records", "kazaword_emails", "onion-pages"]
```

### Group Quality → Query Strategy

| Quality | Groups | Strategy |
|---------|--------|----------|
| `HIGH` / `EXCELLENT` | PERSON_NAME, COMPANY_NAME, EMAIL_RAW, PHONE_FULL | Direct query, trust results |
| `MEDIUM` | MIXED_NAME, EMAIL_OBJECT | Query with warnings, require validation |
| `GARBAGE` | GARBAGE_NAME | **DO NOT QUERY** - negative filtering only |
| `INTERNAL_ONLY` | SYSTEM_ID, DATE_SYSTEM, SYSTEM_META | Backend use only, never expose to users |

### Cross-Index Query Generation

When a query spans multiple indices, use the `group_total.multi_match` pattern:

```json
// COMPANY_NAME group spans 4 indices
{
  "multi_match": {
    "query": "ACME LIMITED",
    "fields": ["proprietor_name_1^3", "company_name^2", "owner_name", "proprietor_name"],
    "type": "best_fields"
  }
}
// Indices: uk_ccod, linkedin_unified, uk_addresses, uk_ocod
```

---

## PART 6: IMPLEMENTATION PHASES

### Phase 1: Derive Ordinal Fields (1-2 days)
Add to existing indices via ES ingest pipeline or batch job:
- `security_tier` on breach_records
- `credibility_tier` on wdc-* indices
- `ownership_strength` on entity_links
- `region_code` on uk_ccod

### Phase 2: Create New Embeddings (2-3 days)
Using all-MiniLM-L6-v2 (384-dim) for consistency:
- Schema.org types (~200 embeddings)
- UK geographic regions (~500 embeddings)
- Red flag terms (~200 embeddings)

### Phase 3: Job Title Clustering (3-5 days)
- Extract unique headlines from linkedin_unified
- Cluster into ~500 semantic groups
- Embed cluster centroids

### Phase 4: Composite Vectors (Future)
- Create multi-field embeddings: `embed(entity_type + industry + jurisdiction)`
- Enable semantic similarity across multiple dimensions

---

## PART 7: DATA QUALITY NOTES

### Known Issues
| Index | Field | Issue |
|-------|-------|-------|
| openownership | subject_name | 0% populated - possible mapping error |
| domains_unified | (general) | 83.7% unenriched |
| GARBAGE_NAME fields | (multiple) | 30-50% contamination |

### Schema Improvements Needed
- IP fields should be `ip` type not `keyword`
- Missing `.keyword` subfields on several text fields
- Derived fields needed: `has_breach`, `ubo_depth`, `risk_score`

---

## APPENDIX: FILE LOCATIONS

| File | Purpose |
|------|---------|
| `BACKEND/modules/CYMONIDES/query_patterns.json` | Per-index query patterns for 43 field groups |
| `BACKEND/modules/CYMONIDES/strategic_embeddings.json` | Embedding opportunities + existing vector DBs |
| `BACKEND/modules/CYMONIDES/multidimensional_indexing.json` | Multi-dimensional filter specifications |
| `BACKEND/modules/CYMONIDES/field_groups.json` | Semantic field group definitions |
| `BACKEND/modules/CYMONIDES/field_group_resolver.py` | Python resolver for field groups |
| `BACKEND/modules/CYMONIDES/industry_matcher.py` | LinkedIn industry semantic matcher |
| `BACKEND/modules/CYMONIDES/industry_embeddings.json` | Pre-computed industry embeddings (1.8MB) |
| `BACKEND/modules/DEFINITIONAL/unified_categories/embeddings.py` | Domain category embedding manager |
| `BACKEND/modules/LINKLATER/.cache/concept_embeddings.json` | LINKLATER concept embeddings (3.5MB) |

---

## DECISIONS

### DECISION 1: Graph Edge Index Naming ✅ RESOLVED

**Issue**: Two naming conventions exist for web graph edges:
- `cymonides_cc_domain_edges` (CYMONIDES module naming)
- `cc_web_graph_edges` (generic descriptive naming)

**Decision**: Use `cc_web_graph_edges` as the canonical name.

**Rationale**:
1. Module names (CYMONIDES) should not appear in index names - modules may be refactored
2. `cc_web_graph` is more descriptive of the content (CommonCrawl Web Graph)
3. Consistent with other edge indices: `entity_links`, `ownership_edges`

**Index Naming Convention**:
```
{source}_{content_type}_{record_type}

Examples:
- cc_web_graph_edges      (CommonCrawl web graph, edge records)
- uk_ccod_properties      (UK CCOD, property records)
- openownership_statements (OpenOwnership, statement records)
```

---

### DECISION 2: Domain Consolidation ⏳ PENDING

**Question**: Merge 4 domain indices (178M + 5.8M + 8.4M + 8.6M) into one `atlas` index?

**Trade-offs**:
| Approach | Pros | Cons |
|----------|------|------|
| Consolidate | Single source of truth, deduplicated | 14+ hour job, new schema |
| Keep separate | No migration needed, can query individually | Duplicates across indices, multi-index queries slower |

**Recommendation**: Consolidate, but after completing current geocoding tasks.

---

### DECISION 3: Field Group Count Reconciliation ✅ RESOLVED

**Issue**: `query_patterns.json` claims 43 groups, `field_groups.json` has 43 groups, but only 41 are queryable.

**Resolution**:
- `field_groups.json`: 43 total groups (includes SYSTEM_ID, EMBEDDING which are internal)
- `query_patterns.json`: 41 queryable groups (excludes internal-only groups)
- Executive summary updated to reflect both counts
