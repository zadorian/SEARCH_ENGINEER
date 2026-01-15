# CYMONIDES CONCEPT: THE MEMORY ENGINE

> **Satellite of:** [`docs/CONCEPT.md`](../../../docs/CONCEPT.md) — See master for full system philosophy.

---

> **AI AGENTS: DO NOT MODIFY THIS FILE WITHOUT EXPLICIT USER PERMISSION**
>
> Update `2_TODO.md` and `3_LOGS.md` automatically as you work.
> See `AGENT.md` at project root for documentation protocols.

---

## 1. Role & Philosophy

**Global Alignment:** This module represents the "Memory" layer described in the Master Concept—the persistent state that holds "The Knowns" and enables routing decisions.
**Purpose:** Elasticsearch-based indexing, search, and state management. CYMONIDES is not just storage; it's the arbiter of what data exists and what routes are available.

## 2. The Two Core Tiers

### C-1: Entity Graph (Project-Scoped)
**"The Investigation Canvas"**

| Aspect | Details |
|--------|---------|
| Pattern | `cymonides-1-project-{PROJECT_ID}` |
| Function | Per-project knowledge graphs storing entities and relationships |
| Entities | PERSON, COMPANY, ADDRESS, EMAIL, DOMAIN, ASSET |
| Relationships | `officer_of`, `beneficial_owner_of`, `controls`, `shareholder_of` |
| Features | Graph traversal, real-time entity extraction (Claude Haiku 4.5), auto-generation from APIs |

### C-2: Text Corpus (Global)
**"The Searchable Memory"**

| Aspect | Details |
|--------|---------|
| Index | `cymonides-2` |
| Docs | 532,630+ |
| Size | 5.1GB+ |
| Sources | YouTube (487K), Reports (45K), Books, Scraped content, Onion graph (doc_type filtered) |
| Features | Full-text search, source filtering, semantic search, cross-document queries |

**doc_type filtering:** Onion graph data stored with `doc_type: "onion_node"` / `doc_type: "onion_edge"` for isolation.

## 3. Complete Index Registry

### Core Indices

| Index | Docs | Size | Purpose |
|-------|------|------|---------|
| `cymonides-2` | 532,630 | 5.1GB | Global text corpus (C-2) |
| `cymonides-1-project-*` | ~1,730 | 23MB | Per-project entity graphs (C-1) |

### Web Graph Indices

| Index | Docs | Size | Purpose |
|-------|------|------|---------|
| `cc_domain_vertices` | 100,662,487 | 7.5GB | Every domain in Common Crawl |
| `cc_domain_edges` | 435,770,000 | 16.5GB | Link relationships (who links to whom) |

### Domain Intelligence Indices

| Index | Docs | Size | Purpose |
|-------|------|------|---------|
| `source_enrichments` | 5 | 34KB | Per-domain DRILL metadata |
| `source_entities` | 8 | 47KB | Entities extracted from domains |
| `bangs` | 20,389 | 5.2MB | DuckDuckGo-style search shortcuts |

### Breach Intelligence Indices

| Index | Docs | Size | Purpose |
|-------|------|------|---------|
| `nexus_breach_records` | 197,668 | 90.3MB | Parsed breach records |
| `nexus_breaches` | 6 | 21.9KB | Breach metadata catalog |

### Country-Specific Indices

| Index | Docs | Size | Purpose |
|-------|------|------|---------|
| `kazaword_emails` | 92,416 | 225.7MB | KZ/RU email intelligence |

### Company Data Indices

| Index | Docs | Purpose |
|-------|------|---------|
| `affiliate_linkedin_companies` | 2,850,000 | Domain → Company identification |
| `company_profiles` | 496 | Enriched company profiles |
| `unified_domain_profiles` | 5,800,000 | Aggregated domain intelligence |

**Total:** ~537M documents, ~29.5GB

## 4. Use Cases (Cross-Index Workflows)

See `use-cases/` folder for detailed documentation:

### [Company Profiles](use-cases/company-profiles/)
**Indices:** C-1 + `source_enrichments` + `source_entities` + C-2 + `cc_domain_*`
**Workflow:** Entity storage → domain enrichment → web scraping → document collection → network analysis

### [Domains List](use-cases/domains-list/)
**Indices:** `cc_domain_vertices` + `cc_domain_edges` + `source_enrichments` + `bangs`
**Workflow:** Domain lookup → backlink analysis → outlink analysis → TLD grouping → authority ranking

### [Red Flags](use-cases/red-flags/)
**Indices:** ALL (cross-referenced for anomaly detection)
**Detection Categories:**
1. **Entity Red Flags** — Shell companies, circular ownership, director recycling
2. **Domain Red Flags** — Zero backlinks, typosquatting, fake news networks
3. **Content Red Flags** — Contradictions, duplicates, sanitized records
4. **Timeline Red Flags** — Retroactive docs, gaps, timestamp manipulation
5. **Network Red Flags** — Link farms, hidden ownership networks

### [Data Breaches](use-cases/data-breaches/)
**Indices:** `nexus_breach_records` + `nexus_breaches` + C-2
**Capabilities:**
- Email/password/username lookups
- Domain exposure analysis (`*@company.com`)
- Password reuse patterns
- High-value breach prioritization

**Data Source:** Raidforums archive (497GB on external drive - mostly unindexed)

### [Country Indexes](use-cases/country-indexes/)
**Indices:** `kazaword_emails` + integration with breaches, company profiles
**Coverage:** Kazakhstan (KZ), Russia (RU)
**Future:** UZ, KG, TM, UA, AZ

## 5. Index Cross-Reference Matrix

| Index | C-1 | C-2 | Company | Domains | Red Flags | Breaches | Countries |
|-------|:---:|:---:|:-------:|:-------:|:---------:|:--------:|:---------:|
| `cymonides-1-project-*` | **CORE** | Links | Primary | — | Entity | — | Graph |
| `cymonides-2` | Links | **CORE** | Docs | Content | Contradictions | Context | Context |
| `cc_domain_vertices` | — | — | Network | **Primary** | Isolation | — | Domains |
| `cc_domain_edges` | — | — | Network | **Primary** | Clusters | — | Network |
| `source_enrichments` | — | — | Domain | Metadata | Age | — | — |
| `source_entities` | Feeds | — | Extraction | Entities | Sanitization | — | — |
| `bangs` | — | — | — | Shortcuts | — | — | — |
| `nexus_breach_records` | Email nodes | — | Exposure | — | Risk | **Primary** | KZ/RU |
| `nexus_breaches` | — | — | Metadata | — | Timeline | Catalog | — |
| `kazaword_emails` | Email nodes | — | Contacts | — | Patterns | Lookup | **Primary** |

## 6. State-Based Routing

CYMONIDES enables **state-aware routing** for the Matrix:

```typescript
// What data EXISTS determines what routes are AVAILABLE
const viability = await cymonidesRouter.checkRouteViability(
  ruleId,
  inputValue,
  projectId
);

if (viability.isViable) {
  // Route can execute - data exists
} else {
  // Route blocked - need prerequisite first
}
```

## 7. Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| **cymonidesPersistence** | `server/services/cymonidesPersistence.ts` | Core ES operations |
| **cymonidesRouter** | `server/services/cymonidesRouter.ts` | Route suggestions, viability checks |
| **TextManager** | `server/services/cymonides-2/TextManager.ts` | C-2 text indexing/search |
| **EntityExtractor** | `server/services/cymonides-2/EntityExtractor.ts` | Entity extraction from text |
| **Indexing Scripts** | `BACKEND/modules/CYMONIDES/scripts/` | Batch indexing utilities |

## 8. Metadata & Schema Storage

```
CYMONIDES/
├── metadata/
│   ├── c-1/                    # C-1 project indices
│   │   ├── c1-repa/
│   │   ├── c1-test/
│   │   ├── c1-default-project/
│   │   ├── ontology/           # FTM mapping, graph schema
│   │   └── matrix_schema/      # nodes.json, sources.json, modules.json
│   ├── c-2/                    # C-2 corpus metadata
│   │   ├── metadata.json
│   │   └── sources/            # youtube/, reports/, books/
│   ├── cc_domain_edges/
│   ├── cc_domain_vertices/
│   ├── nexus_breach_records/
│   ├── nexus_breaches/
│   ├── kazaword_emails/
│   ├── bangs/
│   ├── source_enrichments/
│   └── source_entities/
└── use-cases/                  # Cross-index workflow docs
    ├── cymonides-1/
    ├── cymonides-2/
    ├── company-profiles/
    ├── domains-list/
    ├── red-flags/
    ├── data-breaches/
    ├── country-indexes/
    ├── text-corpus/
    ├── project-graphs/
    └── web-graph/
```

## 9. Connection Points

| Consumer | Integration | Purpose |
|----------|-------------|---------|
| **Graph UI** | `cymonidesPersistence.getNodes()` | Display entity graph |
| **MACROS** | Viability checks before chain steps | Route validation |
| **LINKLATER** | `cc_domain_*` indices | Link graph queries |
| **EYE-D** | `nexus_*` indices | Breach data lookups |
| **Search Bar** | `cymonides-2` full-text | Corpus search |
| **Red Flags** | ALL indices cross-referenced | Anomaly detection |

## 10. Frontend Integration

**See:** [`CLIENT/docs/CYMONIDES_UI.concept.md`](../../../CLIENT/docs/CYMONIDES_UI.concept.md)

The CYMONIDES frontend provides two modes:

| Mode | UI Component | Backend Method | Purpose |
|------|--------------|----------------|---------|
| **Discovery** | Corpus search panel | `TextManager.search()` | Search 537M docs |
| **Enrichment** | "Check CYMONIDES" profile button | `checkRouteViability()` | Verify entity against corpus |

**Key Frontend Files:**
- `CyMonidesPanel.tsx` — Main corpus search interface
- `ThreeCompartmentInputPython.tsx` — Search input with source filtering

## 11. Physical Storage

**Location:** OrbStack Docker Volume
- Path: `/var/lib/docker/volumes/drill-search-app_elasticsearch_data/_data`
- Container: `drill-search-elasticsearch`
- Access: `http://localhost:9200`
