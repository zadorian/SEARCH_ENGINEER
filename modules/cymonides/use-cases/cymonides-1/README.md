# Cymonides-1 (C-1): Project Entity Graphs

> **Satellite of:** [`docs/OPERATORS_CONCEPT.md`](../../../../../docs/OPERATORS_CONCEPT.md) — See master for entity extraction operators and the AI vs Deterministic paradigm.

**Purpose:** Per-project knowledge graphs storing entities (people, companies, assets) and typed relationships

## Overview

Cymonides-1 is the **entity storage layer** of DRILL Search. Unlike C-2 (global text corpus), each C-1 index is **project-scoped** - an independent knowledge graph representing one investigation.

**Index Pattern:** `cymonides-1-project-{PROJECT_ID}`

**Examples:**
- `cymonides-1-project-ge13t70tq8v0hw0h994z1v64` (1,722 entities)
- `cymonides-1-project-test` (7 entities)
- `cymonides-1-project-y5p1ujpf31j4vtil3fi80hx5` (1 entity)

---

## Why C-1 Exists

### The Structured Memory Problem

**Problem:** Text corpus (C-2) is great for search, but terrible for:
- "Show me all directors of this company"
- "What companies does John Smith control?"
- "Find circular ownership chains"
- "Who are the beneficial owners?"

**Solution:** C-1 stores **structured entity graphs** with:
- Typed nodes (PERSON, COMPANY, ADDRESS, EMAIL, etc.)
- Typed edges (officer_of, beneficial_owner_of, controls, etc.)
- Rich metadata (dates, confidence scores, source provenance)
- Graph traversal capabilities

### C-2 vs C-1

| Aspect | C-2 (Text Corpus) | C-1 (Entity Graphs) |
|--------|-------------------|---------------------|
| **Scope** | Global (all projects) | Per-project |
| **Storage** | Full-text documents | Structured nodes/edges |
| **Queries** | Keyword search, semantic search | Graph traversal, relationship queries |
| **Updates** | Immutable (append-only) | Mutable (entities evolve) |
| **Size** | Large (532K docs, 5.1GB) | Small per project (1-2K entities) |
| **Use** | "Find documents about X" | "Show me X's network" |

**They work together:**
```
1. User uploads PDF → Stored in C-2
2. Claude extracts entities → Created in C-1
3. User asks "Who are the directors?" → Query C-1
4. User asks "Show me the contract" → Query C-2
5. Entity graph links to source documents in C-2
```

---

## Project Narrative Connection

**Every C-1 index maps to a Project Narrative node in the frontend.**

The project narrative (visible in `client/src/pages/NarrativeEditor.tsx`) is the **root node** that anchors the investigation. All entities and relationships discovered during research are stored in that project's C-1 index.

```
Project Narrative (Frontend) → cymonides-1-project-{id} (Backend ES)
         ↓                                  ↓
   Investigation UI              Entity Graph Storage
```

---

## Schema Architecture

### Single Source of Truth: `input_output/ontology/`

All node types, edge types, and validation rules are defined in:

```
input_output/
├── ontology/
│   ├── graph_schema.json         # Complete node type definitions
│   ├── relationships.json         # Edge type definitions & validation
│   ├── ftm_mapping.json          # FTM compatibility mappings
│   └── ftm_schema_mapping.json   # Extended FTM mappings
```

**CRITICAL:** These are the ONLY schema definitions. All code that creates nodes/edges MUST reference these files.

### Node Types (from `graph_schema.json`)

**Core Entities:**
- `PERSON` - People (with names, DOB, nationalities, PEP status)
- `COMPANY` - Organizations (with registration numbers, jurisdictions)
- `ADDRESS` - Physical locations
- `EMAIL` - Email addresses
- `PHONE` - Phone numbers
- `PERSONA` - Online identities (platform handles)

**Assets:**
- `VESSEL` - Ships, boats
- `PLANE` - Aircraft
- `VEHICLE` - Land vehicles
- `CRYPTOCURRENCY` - Crypto addresses/wallets
- `BANK_ACCOUNT` - Banking details

**Documents:**
- `DOCUMENT` - Files, reports
- `URL` - Web pages
- `REPORT` - Investigation reports
- `NOTE` - Research notes

**Infrastructure:**
- `DOMAIN` - Web domains
- `IP_ADDRESS` - IP addresses
- `SERVER` - Servers

**Plus 40+ more types** - See `input_output/ontology/graph_schema.json` for complete list

### Edge Types (from `relationships.json`)

**Corporate Structure:**
- `officer_of` - Person → Company
- `beneficial_owner_of` - Person/Company → Company
- `subsidiary_of` - Company → Company
- `shareholder_of` - Person/Company → Company

**Ownership:**
- `owner_of` - Entity → Asset
- `registered_owner_of` - Entity → Asset
- `controls` - Entity → Entity

**Communication:**
- `email_of` - Email → Entity
- `phone_of` - Phone → Entity
- `contacted` - Entity → Entity

**Location:**
- `registered_at` - Company → Address
- `located_at` - Entity → Address
- `resident_at` - Person → Address

**Plus 100+ edge types** - See `input_output/ontology/relationships.json` for complete catalog

---

## Entity Extraction Pipeline

### Multi-Tier Extraction Cascade

**Tier 1: Regex (Fast, Free)**
- Patterns: emails, phones, URLs, IPs
- No API calls
- Always runs first

**Tier 2: GPT-5-nano (Fast, Cheap)**
- Model: `gpt-5-nano`
- Use: Simple entity extraction

**Tier 3: Claude Haiku 4.5 (Mid, Balanced)** ⭐
- Model: `claude-haiku-4-5-20251001`
- Use: Complex entities + relationships
- **This is the PRIMARY extraction model**

**Tier 4: Claude Sonnet 4.5 (Full, Expensive)**
- Model: `claude-sonnet-4-5-20250929`
- Use: Disambiguation, comprehensive analysis

### Extraction Workflow

```typescript
// From CymonidesEntityCentre.ts:extractEntitiesFromText()

1. Tier 1: Regex extraction (emails, phones, URLs)
2. Parallel execution:
   - Tier 2: GPT-5-nano (entities)
   - Tier 3: Claude Haiku (entities + relationships)
3. Merge results
4. Deduplicate
5. Create nodes & edges in C-1
6. Broadcast updates via WebSocket
```

**Code Location:** `server/services/CymonidesEntityCentre.ts`

---

## Auto-Generated Nodes & Edges

Certain API responses trigger automatic node/edge creation:

### 1. Corporella (OpenCorporates) API
**Trigger:** Company lookup via Corporella

**Auto-Creates:**
- `COMPANY` node (with registration data)
- `PERSON` nodes for officers
- `officer_of` edges (Person → Company)
- `ADDRESS` node for registered address
- `registered_at` edge (Company → Address)

**Code:** `server/services/corporellaService.ts` + `templateAutoPopulation.ts`

### 2. AllDom (Domain Intelligence)
**Trigger:** Domain analysis

**Auto-Creates:**
- `DOMAIN` node
- `IP_ADDRESS` nodes (if resolved)
- `hosted_at` edges (Domain → IP)
- `BACKLINK` edges (from CC graph)

**Code:** `server/services/alldomService.ts`

### 3. LinkLater (Web Scraping)
**Trigger:** Domain crawl

**Auto-Creates:**
- `URL` nodes (discovered pages)
- `EMAIL` nodes (extracted from pages)
- `PHONE` nodes (extracted from pages)
- `links_to` edges (URL → URL)
- `email_of` / `phone_of` edges

**Code:** `server/services/linklater.ts` + `domainEntityExtractionService.ts`

### 4. Entity Extraction from Documents
**Trigger:** PDF/Word upload to C-2

**Auto-Creates:**
- Entities extracted by Claude Haiku
- `mentioned_in` edges (Entity → Document)
- Relationships between extracted entities

**Code:** `server/services/cymonides-2/EntityExtractor.ts`

---

## Integration with C-2 (Text Corpus)

**Cross-Reference Pattern:**

1. User uploads PDF → Indexed in C-2 (`cymonides-2`)
2. Claude Haiku extracts entities → Created in C-1 (`cymonides-1-project-{id}`)
3. Document-to-entity edges created
4. User can navigate: Entity → "Mentioned in" → Documents

**Link Field:** `extracted_entity_ids` in C-2 documents points to C-1 entity IDs

---

## Key Implementation Files

### Core Services
| File | Purpose |
|------|---------|
| `server/services/CymonidesEntityCentre.ts` | Main entity/edge API |
| `server/services/cymonides-1/EdgeManager.ts` | Edge validation & creation |
| `server/services/cymonides-1/schemas.ts` | C-1 ES mappings |
| `server/services/cymonides-1/indexSetup.ts` | Index initialization |

### Extraction
| File | Purpose |
|------|---------|
| `server/services/extraction/LLMExtractor.ts` | AI extraction (Tiers 2-4) |
| `server/services/extraction/RegexExtractor.ts` | Pattern extraction (Tier 1) |
| `server/services/domainEntityExtractionService.ts` | Domain-specific extraction |
| `server/services/cymonides-2/EntityExtractor.ts` | Document extraction |

### Utilities
| File | Purpose |
|------|---------|
| `server/utils/templateAutoPopulation.ts` | Auto-node/edge creation |
| `server/utils/schemaRegistry.ts` | Schema loading & validation |
| `server/utils/graphWebSocket.ts` | Real-time updates |
| `server/services/edgeRelationshipService.ts` | Edge validation |

---

## Common Workflows

### 1. Create Investigation
```
1. User creates project in frontend
2. Backend creates Project Narrative node
3. C-1 index created: cymonides-1-project-{new_id}
4. Schema initialized from input_output/ontology/
```

### 2. Add Company to Investigation
```
1. User searches company via Corporella
2. API returns structured data
3. Auto-population creates:
   - COMPANY node
   - PERSON nodes (officers)
   - officer_of edges
   - ADDRESS node
   - registered_at edge
4. WebSocket broadcasts updates
5. Frontend graph updates in real-time
```

### 3. Extract Entities from Document
```
1. User uploads PDF → C-2
2. Claude Haiku extraction triggered
3. Entities created in C-1
4. mentioned_in edges created (Entity → Document)
5. Relationships extracted and validated
6. Invalid edges rejected (not in relationships.json)
```

---

## Use Cases That Rely on C-1

| Use Case | How C-1 is Used |
|----------|-----------------|
| **Company Profiles** | Primary entity storage, ownership graphs |
| **Red Flags** | Entity pattern detection (circular ownership, shell companies) |
| **Country Indexes** | Entity graphs per jurisdiction |
| **Data Breaches** | Email nodes linked to breach records |
| **Domains List** | Domain entities with backlink edges |

---

## Related Documentation

- **Schema Source:** `../../input_output/README.md`
- **Ontology Details:** `../../input_output/ontology/graph_schema.json`
- **Edge Catalog:** `../../input_output/ontology/relationships.json`
- **C-2 Integration:** `../cymonides-2/README.md`
- **Extraction Service:** `../../server/services/extraction/LLMExtractor.ts`
- **C-1 Metadata:** `../../metadata/cymonides-1/README.md`

---

## Performance Notes

- **Entity lookup:** Fast (keyword match, few thousand entities per project)
- **Graph traversal:** Moderate (depends on depth and fan-out)
- **Real-time updates:** WebSocket broadcasts for live graph updates
- **Cross-project search:** Not yet implemented (each project isolated)
