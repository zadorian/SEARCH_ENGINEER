# Cymonides Use Cases

This folder contains **use-case-centric documentation** showing how different indices work together to solve specific investigative problems.

## Overview

Unlike the `metadata/` folder (which documents indices individually), `use-cases/` shows **cross-index workflows** and query patterns for real investigative scenarios.

## Use Case Folders

### 1. [Cymonides-1 (C-1)](cymonides-1/) ⭐
**Goal:** Per-project entity graphs - structured knowledge storage

**What It Is:** Project-scoped knowledge graphs storing entities (people, companies, assets) and typed relationships

**Index Pattern:** `cymonides-1-project-{PROJECT_ID}`

**Key Capabilities:**
- Structured entity storage (PERSON, COMPANY, ADDRESS, EMAIL, etc.)
- Typed relationships (officer_of, beneficial_owner_of, controls, etc.)
- Graph traversal queries
- Real-time entity extraction via Claude Haiku 4.5
- Auto-generation from API responses (Corporella, AllDom, LinkLater)

**Use:** "Show me all directors", "Find circular ownership", "Map entity networks"

**Schema Source:** `input_output/ontology/` (single source of truth)

---

### 2. [Cymonides-2 (C-2)](cymonides-2/) ⭐
**Goal:** Global text corpus - full-text search across all documents

**What It Is:** Single unified index containing all text content from all sources

**Index Name:** `cymonides-2` (532,630 docs, 5.1GB)

**Sources:**
- YouTube transcripts (487,600 docs)
- Uploaded reports (45,030 docs)
- Books (post-Soviet studies)
- Scraped web content (future)

**Key Capabilities:**
- Full-text keyword search
- Source type filtering
- Semantic search (if embeddings enabled)
- Cross-document search
- Links to C-1 entities

**Use:** "Find all mentions of X", "Search entire library", "Which documents discuss Y?"

---

### 3. [Company Profiles](company-profiles/)
**Goal:** Complete company intelligence - ownership, officers, financials, public records

**Indices Used:**
- `cymonides-1-project-{id}` (entity storage)
- `cymonides_source_enrichments` (domain enrichment)
- `cymonides_source_entities` (web scraping results)
- `cymonides-2` (supporting documents)
- `cymonides_cc_domain_*` (network analysis)

**Key Queries:** Entity lookup, document search, backlink analysis, enrichment checks

---

### 2. [Domains List](domains-list/)
**Goal:** Domain intelligence, lookup, ranking, and network analysis

**Indices Used:**
- `cc_domain_vertices` (100M+ domains)
- `cc_domain_edges` (435M+ links)
- `source_enrichments` (DRILL metadata)
- `bangs` (search shortcuts)
- `source_entities` (extracted entities)
- `cymonides-2` (domain content)

**Key Queries:** Domain lookup, backlink/outlink analysis, TLD filtering, authority scoring

---

### 3. [Red Flags](red-flags/)
**Goal:** Risk indicators, anomaly detection, suspicious patterns

**Indices Used:** **ALL CYMONIDES INDICES** (cross-referenced)

**Detection Categories:**
1. **Entity Red Flags** - Shell companies, circular ownership, director recycling
2. **Domain Red Flags** - Zero backlinks, typosquatting, fake news networks
3. **Content Red Flags** - Contradictions, duplicates, sanitized records
4. **Timeline Red Flags** - Retroactive docs, gaps, timestamp manipulation
5. **Network Red Flags** - Link farms, hidden ownership networks

**Key Queries:** Aggregations for pattern detection, contradiction searches, network analysis

---

### 4. [Data Breaches](data-breaches/)
**Goal:** Breach intelligence, credential analysis, exposure assessment

**Indices Used:**
- `nexus_breach_records` (197K records - subset of Raidforums)
- `nexus_breaches` (breach metadata)
- `cymonides-2` (supporting documents)
- Integration with company-profiles and red-flags

**Key Workflows:**
- Email/password/username lookups
- Domain exposure analysis (all *@company.com breaches)
- Password reuse patterns
- High-value breach prioritization

**Data Source:** Raidforums archive (497GB on /Volumes/My Book - mostly unindexed)

---

### 5. [Country Indexes](country-indexes/)
**Goal:** Country-specific data aggregation and regional investigations

**Current Coverage:**
- **Kazakhstan (KZ)** - kazaword_emails (92K emails)
- **Russia (RU)** - kazaword_emails (shared dataset)

**Indices Used:**
- `kazaword_emails` (KZ/RU email intelligence)
- Integration with breach data, company profiles, domain analysis

**Key Workflows:**
- Regional entity investigations
- Government email discovery
- Cross-border entity tracking
- Email domain analysis by jurisdiction

**Future Expansions:** UZ, KG, TM, UA, AZ

---

## Index Cross-Reference Matrix

| Index Name | C-1 | C-2 | Company | Domains | Red Flags | Breaches | Countries |
|------------|:---:|:---:|:-------:|:-------:|:---------:|:--------:|:---------:|
| **`cymonides-1-project-{id}`** | ✅ **CORE** | 🔗 Links | ✅ Primary | ➖ | ✅ Entity | ➖ | ✅ Graph |
| **`cymonides-2`** | 🔗 Links | ✅ **CORE** | ✅ Docs | ✅ Content | ✅ Contradictions | ✅ Context | ✅ Context |
| `cc_domain_vertices` | ➖ | ➖ | ✅ Network | ✅ Primary | ✅ Isolation | ➖ | ✅ Domains |
| `cc_domain_edges` | ➖ | ➖ | ✅ Network | ✅ Primary | ✅ Clusters | ➖ | ✅ Network |
| `source_enrichments` | ➖ | ➖ | ✅ Domain | ✅ Metadata | ✅ Age | ➖ | ➖ |
| `source_entities` | 🔗 Feeds | ➖ | ✅ Extraction | ✅ Entities | ✅ Sanitization | ➖ | ➖ |
| `bangs` | ➖ | ➖ | ➖ | ✅ Shortcuts | ➖ | ➖ | ➖ |
| `nexus_breach_records` | 🔗 Email nodes | ➖ | ✅ Exposure | ➖ | ✅ Risk | ✅ Primary | ✅ KZ/RU |
| `nexus_breaches` | ➖ | ➖ | ✅ Metadata | ➖ | ✅ Timeline | ✅ Catalog | ➖ |
| `kazaword_emails` | 🔗 Email nodes | ➖ | ✅ Contacts | ➖ | ✅ Patterns | ✅ Lookup | ✅ Primary |

**Legend:**
- ✅ Primary use
- 🔗 Bidirectional links
- ➖ Not used

## How Indices Overlap

The same index can serve different purposes depending on the use case:

- **`cymonides-2`** appears in all use cases:
  - Company Profiles: "Find all documents about this company"
  - Domains List: "Show content from this domain"
  - Red Flags: "Find contradictory statements"

- **`cymonides_cc_domain_edges`** powers:
  - Company Profiles: "Who links to this company's website?"
  - Domains List: "Show backlinks for ranking"
  - Red Flags: "Detect closed link networks"

- **`cymonides-1-project-{id}`** drives:
  - Company Profiles: Primary entity storage
  - Red Flags: Ownership analysis, officer patterns

## Documentation Philosophy

**This folder documents THE QUERIES, not the schemas.**

For schema details, see: `../metadata/{index_name}/metadata.json`

For workflows and query patterns, see: `./{use-case}/README.md`

## Adding New Use Cases

When adding a new investigative workflow:

1. Create folder: `cymonides/use-cases/{use-case-name}/`
2. Add `README.md` with:
   - Purpose statement
   - Indices used (with links to metadata)
   - Typical workflows
   - Example queries
   - Data flow diagram
   - Related modules
   - Cross-references to other use cases
3. Update this file with summary and matrix entry

## Related Documentation

- **Index Schemas:** `../metadata/{index_name}/metadata.json`
- **Storage Overview:** `../README.md`
- **LinkLater Map:** `../../python-backend/modules/linklater/LINKLATER_ELASTICSEARCH_INDEX_MAP.md`
- **Architecture:** `../../docs/CONCEPT.md`
