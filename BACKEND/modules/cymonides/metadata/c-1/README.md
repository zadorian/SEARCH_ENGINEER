# Cymonides-1 (C-1): Project Entity Graphs

**Purpose:** Per-project knowledge graphs storing entities (people, companies, assets) and typed relationships

## Overview

Cymonides-1 is the **entity storage layer** of DRILL Search. Unlike C-2 (global text corpus), each C-1 index is **project-scoped** - an independent knowledge graph representing one investigation.

**Index Pattern:** `cymonides-1-project-{PROJECT_ID}`

**Examples:**
- `cymonides-1-project-ge13t70tq8v0hw0h994z1v64` (1,722 entities)
- `cymonides-1-project-test` (7 entities)
- `cymonides-1-project-y5p1ujpf31j4vtil3fi80hx5` (1 entity)

## Project Narrative Connection

**Every C-1 index maps to a Project Narrative node in the frontend.**

The project narrative (visible in `client/src/pages/NarrativeEditor.tsx`) is the "root node" that anchors the investigation. All entities and relationships discovered during research are stored in that project's C-1 index.

```
Project Narrative (Frontend) → cymonides-1-project-{id} (Backend ES)
         ↓                                  ↓
   Investigation UI              Entity Graph Storage
```

## Schema Architecture

### Single Source of Truth: `input_output/`

All node types, edge types, and validation rules are defined in:

```
input_output/
├── ontology/
│   ├── graph_schema.json         # Complete node type definitions
│   ├── relationships.json         # Edge type definitions & validation
│   ├── ftm_mapping.json          # FTM compatibility mappings
│   └── ftm_schema_mapping.json   # Extended FTM mappings
└── matrix/
    └── (routing rules, flows, sources)
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

## Entity Extraction Pipeline

### Code Location: `server/services/`

**Primary Service:** `CymonidesEntityCentre.ts`
- Single entry point for ALL entity/edge operations
- Consolidates 12+ scattered implementations
- Multi-tier extraction cascade

**Extraction Modules:** `server/services/extraction/`
- `LLMExtractor.ts` - AI-powered extraction (Tiers 2-4)
- `RegexExtractor.ts` - Pattern-based extraction (Tier 1)
- `index.ts` - Extraction orchestration

### Multi-Tier Extraction Cascade

**Tier 1: Regex (Fast, Free)**
- Patterns: emails, phones, URLs, IPs
- No API calls
- Always runs first

**Tier 2: GPT-5-nano (Fast, Cheap)**
- Model: `gpt-5-nano`
- Use: Simple entity extraction
- Location: `extraction/LLMExtractor.ts:44-48`

**Tier 3: Claude Haiku 4.5 (Mid, Balanced)** ⭐
- Model: `claude-haiku-4-5-20251001`
- Use: Complex entities + relationships
- Location: `extraction/LLMExtractor.ts:49-53`
- **This is the PRIMARY extraction model**

**Tier 4: Claude Sonnet 4.5 (Full, Expensive)**
- Model: `claude-sonnet-4-5-20250929`
- Use: Disambiguation, comprehensive analysis
- Location: `extraction/LLMExtractor.ts:54-58`

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

### Key Functions

**Entity Operations:**
```typescript
// server/services/CymonidesEntityCentre.ts

createEntity(params: CreateEntityParams): Promise<EntityResult>
updateEntity(id: string, updates: Partial<Entity>): Promise<Entity>
deleteEntity(id: string): Promise<void>
searchEntities(query: string, filters?: SearchFilters): Promise<Entity[]>
```

**Edge Operations:**
```typescript
// server/services/cymonides-1/EdgeManager.ts

createEdge(params: CreateEdgeParams): Promise<EdgeResult>
validateEdge(from, to, relation): EdgeValidationResult
suggestEdges(entityId: string): Promise<EdgeSuggestion[]>
```

**Extraction:**
```typescript
// server/services/CymonidesEntityCentre.ts

extractEntitiesFromText(
  content: string,
  options?: ExtractionOptions
): Promise<ExtractionResult>
```

## Auto-Generated Nodes & Edges

### Registry of Automatic Creation Rules

**Location:** `server/utils/templateAutoPopulation.ts`

Certain API responses trigger automatic node/edge creation:

#### 1. Corporella (OpenCorporates) API
**Trigger:** Company lookup via Corporella
**Auto-Creates:**
- `COMPANY` node (with registration data)
- `PERSON` nodes for officers
- `officer_of` edges (Person → Company)
- `ADDRESS` node for registered address
- `registered_at` edge (Company → Address)

**Code:** `server/services/corporellaService.ts` + `templateAutoPopulation.ts`

#### 2. AllDom (Domain Intelligence)
**Trigger:** Domain analysis
**Auto-Creates:**
- `DOMAIN` node
- `IP_ADDRESS` nodes (if resolved)
- `hosted_at` edges (Domain → IP)
- `BACKLINK` edges (from CC graph)

**Code:** `server/services/alldomService.ts`

#### 3. LinkLater (Web Scraping)
**Trigger:** Domain crawl
**Auto-Creates:**
- `URL` nodes (discovered pages)
- `EMAIL` nodes (extracted from pages)
- `PHONE` nodes (extracted from pages)
- `links_to` edges (URL → URL)
- `email_of` / `phone_of` edges

**Code:** `server/services/linklater.ts` + `domainEntityExtractionService.ts`

#### 4. Entity Extraction from Documents
**Trigger:** PDF/Word upload to C-2
**Auto-Creates:**
- Entities extracted by Claude Haiku
- `mentioned_in` edges (Entity → Document)
- Relationships between extracted entities

**Code:** `server/services/cymonides-2/EntityExtractor.ts`

### Configuration Files

**Auto-Population Rules:** `server/utils/templateAutoPopulation.ts`
**Schema Validation:** `server/utils/schemaRegistry.ts`
**Edge Validation:** `server/services/edgeRelationshipService.ts`

## Frontend Integration

### Narrative Editor
**Location:** `client/src/pages/NarrativeEditor.tsx`

The narrative editor is the **command center** for investigations. It:
- Creates Project Narrative node (root of C-1)
- Displays entity graph for current project
- Triggers entity extraction from text
- Shows entity relationships
- Auto-fills sections based on graph data

### Graph Visualization
**Components:**
- `client/src/components/GraphView.tsx` (if exists)
- `client/src/components/EntityCard.tsx` (if exists)
- Real-time updates via WebSocket (`server/utils/graphWebSocket.ts`)

## Elasticsearch Structure

### Index Settings
```json
{
  "number_of_shards": 3,
  "number_of_replicas": 0,
  "refresh_interval": "5s"
}
```

### Document Types

**Nodes (Entities):**
```json
{
  "_id": "cuid2_generated_id",
  "className": "entity",
  "typeName": "company",
  "label": "Acme Corp",
  "canonicalValue": "acme-corp-uk-12345678",
  "metadata": {
    "company_number": "12345678",
    "jurisdiction": "GB",
    "status": "active"
  },
  "projectId": "ge13t70tq8v0hw0h994z1v64",
  "userId": 1,
  "status": "active",
  "createdAt": "2025-12-03T...",
  "updatedAt": "2025-12-03T..."
}
```

**Edges (Relationships):**
```json
{
  "_id": "edge_cuid2_id",
  "fromNodeId": "person_node_id",
  "toNodeId": "company_node_id",
  "relation": "officer_of",
  "metadata": {
    "position": "Director",
    "start_date": "2020-01-01"
  },
  "weight": 1.0,
  "confidence": 0.9,
  "projectId": "ge13t70tq8v0hw0h994z1v64",
  "createdAt": "2025-12-03T..."
}
```

## Integration with C-2 (Text Corpus)

**Cross-Reference Pattern:**

1. User uploads PDF → Indexed in C-2 (`cymonides-2`)
2. Claude Haiku extracts entities → Created in C-1 (`cymonides-1-project-{id}`)
3. Document-to-entity edges created
4. User can navigate: Entity → "Mentioned in" → Documents

**Link Field:** `extracted_entity_ids` in C-2 documents points to C-1 entity IDs

## Schema Version Control

**Current Version:** 1.1 (as of 2025-11-04)

**Schema Files:**
- `input_output/ontology/graph_schema.json` - v1.1
- `input_output/ontology/relationships.json` - Active
- `input_output/_schema_archive_2025-11-29/` - Historical versions

**Migration Path:**
- Old schemas archived to `_schema_archive_*/`
- Code updated to reference new locations
- Backward compatibility maintained via FTM mappings

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

### Routers
| File | Purpose |
|------|---------|
| `server/routers/graphRouter.ts` | Graph API endpoints |
| `server/routers/edgeRelationshipRouter.ts` | Edge API |
| `server/routers/enrichmentRouter.ts` | Enrichment triggers |

## Environment Variables

```bash
# AI Models for Extraction
ANTHROPIC_API_KEY=...        # Claude Haiku/Sonnet
OPENAI_API_KEY=...           # GPT-5-nano

# Feature Flags
ENABLE_ENTITY_EXTRACTION=true
ENABLE_RELATIONSHIP_EXTRACTION=true
```

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

## Testing

### Test Files
- `server/services/cymonides-1/testSetup.ts`
- `server/services/cymonides-1/testValidationAndClustering.ts`
- `server/services/cymonides-1/testGridIntegration.ts`

### Manual Testing
```bash
# Create test project
curl -X POST http://localhost:3000/api/graph/project \
  -H 'Content-Type: application/json' \
  -d '{"name": "Test Investigation"}'

# Extract entities
curl -X POST http://localhost:3000/api/graph/extract \
  -H 'Content-Type: application/json' \
  -d '{
    "content": "John Smith is a director of Acme Corp (UK company 12345678).",
    "projectId": "test"
  }'

# Verify index
curl "http://localhost:9200/cymonides-1-project-test/_search?size=100"
```

## Troubleshooting

### Schema Mismatches
**Problem:** Code referencing old schema locations
**Fix:** Update imports to point to `input_output/ontology/`

### Invalid Edge Types
**Problem:** Edge creation fails with "Invalid relationship type"
**Fix:** Check `input_output/ontology/relationships.json` for valid types

### Missing Entities
**Problem:** Extraction runs but no entities created
**Fix:** Check Claude Haiku API key, review extraction logs

### Cross-Project Pollution
**Problem:** Entities appear in wrong project
**Fix:** Ensure `projectId` is passed to all entity creation calls

## Related Documentation

- **Schema Source:** `input_output/README.md`
- **Ontology Details:** `input_output/ontology/graph_schema.json`
- **Edge Catalog:** `input_output/ontology/relationships.json`
- **C-2 Integration:** `../cymonides-2/README.md`
- **Extraction Service:** `server/services/extraction/LLMExtractor.ts`

## Future Enhancements

1. **Graph Analytics**
   - PageRank-style centrality scoring
   - Community detection for entity clustering
   - Anomaly detection (unusual patterns)

2. **Enhanced Extraction**
   - Fine-tuned models for specific domains
   - Multi-language support
   - Historical entity tracking

3. **Cross-Project Search**
   - Search entities across all projects
   - Detect duplicate entities
   - Merge investigations

4. **FTM Full Integration**
   - Export to FTM format
   - Import ICIJ datasets
   - Compatible with Aleph
