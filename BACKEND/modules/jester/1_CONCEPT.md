# TORPEDO - Template-based Registry Search System

**"Bang-Inspired Site-Engine Router with Self-Learning Extraction"**

---

## I. Core Philosophy

TORPEDO is **not** a general-purpose crawler. It's a **template-driven registry search system** that:

1. **Knows the recipe** - Each source has a specific URL template + extraction schema
2. **Learns what it doesn't know** - GPT-5-nano expands schemas when it finds new fields
3. **Becomes deterministic** - Eventually 100% regex-based, no AI needed

> "We don't ask the engine to be smart for us. We ask it to be exhaustive, then we learn the structure."

---

## II. Architecture

```
                        TORPEDO SEARCH FLOW

   User Query                    Template Engine              Result Processing
   ┌──────────────┐              ┌────────────────┐          ┌─────────────────┐
   │ cde:Acme GmbH│──────────────│ handelsregister│──────────│ Self-Learning   │
   │              │  inputType   │ .de template   │  JESTER  │ Extraction      │
   │ Input: c     │  + jurisdiction│              │  scrape  │                 │
   │ Jurisdiction:│  = template  │ URL Template:  │          │ Schema + Nano   │
   │ de           │  lookup      │ https://...    │          │ Expansion       │
   └──────────────┘              │ {query}        │          └─────────────────┘
                                 └────────────────┘                   │
                                                                      ▼
                                                            ┌─────────────────┐
                                                            │ cymonides-1-{id}│
                                                            │ Elasticsearch   │
                                                            │ Index           │
                                                            └─────────────────┘
```

### Search Syntax (Bang-Inspired)

| Syntax | Meaning | Example |
|--------|---------|---------|
| `c{jur}:query` | Company search in jurisdiction | `cde:Acme GmbH` |
| `p{jur}:query` | Person search in jurisdiction | `phu:Kovács János` |
| `e:query` | Email search | `e:john@example.com` |
| `u:query` | Username search | `u:johndoe123` |
| `t:query` | Phone/telephone search | `t:+49123456789` |
| `cr{jur}:query` | Corporate registry by reg number | `cruk:12345678` |
| `lit{jur}:query` | Litigation search | `litus:Acme Corp` |
| `reg{jur}:query` | Regulatory search | `reguk:FCA` |
| `at{jur}:query` | Asset/property search | `atus:123 Main St` |
| `misc{jur}:query` | Miscellaneous/other | `miscde:keyword` |
| `platform?query` | Platform search | `linkedin?John Doe` |

### Input Types

| Code | Full Name | Description |
|------|-----------|-------------|
| `c` | company | Company name search |
| `p` | person | Person/individual name |
| `e` | email | Email address |
| `u` | username | Username/handle |
| `t` | phone | Phone/telephone number |
| `cr` | corporate_reg | Corporate registry by registration number |
| `lit` | litigation | Litigation/court records |
| `reg` | regulatory | Regulatory filings |
| `at` | asset | Asset/property records |
| `misc` | miscellaneous | Other/catch-all |

---

## III. Self-Learning Extraction Loop

The core innovation of TORPEDO is its **self-learning extraction system**:

```
                    SELF-LEARNING LOOP

   ┌─────────────────────────────────────────────────────────┐
   │                                                         │
   │  1. Load Schema         2. Extract with Schema          │
   │  ┌──────────────┐       ┌──────────────────────┐       │
   │  │torpedo_schemas│──────▶│ Regex-based Extract  │       │
   │  │ index in ES  │       │ (deterministic)      │       │
   │  └──────────────┘       └──────────┬───────────┘       │
   │                                     │                   │
   │  5. Save Updated Schema             │                   │
   │  ┌──────────────┐       ┌──────────▼───────────┐       │
   │  │ torpedo_schemas│◀─────│ 3. GPT-5-nano Check │       │
   │  │ (expanded)   │       │ "Any new fields?"   │       │
   │  └──────────────┘       └──────────┬───────────┘       │
   │                                     │                   │
   │                         ┌──────────▼───────────┐       │
   │                         │ 4. Expand Schema     │       │
   │                         │ if new fields found  │       │
   │                         └──────────────────────┘       │
   │                                                         │
   └─────────────────────────────────────────────────────────┘

   After ~10 nano calls with no new fields → STOPS calling nano
   Schema becomes 100% deterministic
```

### Schema Structure

```typescript
interface LearnedOutputSchema {
  templateCode: string;           // e.g., "handelsregister_de"
  resultType: string;             // e.g., "company_profile"
  fields: SchemaField[];          // Array of learned fields
  lastUpdated: string;            // ISO timestamp
  totalExtractions: number;       // How many times used
  nanoCallCount: number;          // Track learning progress
  schemaVersion: number;          // Schema iteration
}

interface SchemaField {
  name: string;                   // e.g., "company_name"
  fieldCode: number;              // Matrix code (13, 43, etc.)
  patterns: string[];             // Regex patterns as strings
  cssSelector?: string;           // DOM selector if applicable
  jsonPath?: string;              // JSON path if applicable
  nodeType: string;               // FtM node type
  confidence: number;             // 0-1 extraction confidence
  exampleValues: string[];        // Sample extracted values
  learnedAt: string;              // When field was discovered
  hitCount: number;               // Times field was found
}
```

### Field Codes (Matrix Integration)

| Code | Field Name | Description |
|------|------------|-------------|
| 13 | company_name | Legal company name |
| 43 | company_reg_id | Registration/company number |
| 7 | person_name | Full person name |
| 3 | email | Email address |
| 4 | phone | Phone number |
| 11 | address | Physical address |
| 44 | jurisdiction | Country/jurisdiction |
| 45 | registration_date | Date of registration |
| 46 | status | Active/dissolved status |
| 47 | legal_form | Legal entity type |
| 48 | directors | Director names |
| 49 | shareholders | Shareholder info |
| 50 | capital | Share capital |

---

## IV. Template Engine Index

Templates are stored in Elasticsearch: `template_engines` index

### Template Structure

```json
{
  "code": "handelsregister_de",
  "name": "German Commercial Register",
  "domain": "handelsregister.de",
  "jurisdiction": "de",
  "urlTemplate": "https://www.handelsregister.de/search?company={query}",
  "inputTypes": ["company_name", "company_reg_id"],
  "sourceType": "cr",
  "investigationTypes": ["corporate", "litigation", "asset"],
  "reliabilityTier": 1,
  "requiresAuth": false,
  "rateLimit": 10,
  "outputFields": [
    {"fieldCode": 13, "name": "company_name"},
    {"fieldCode": 43, "name": "registration_number"},
    {"fieldCode": 46, "name": "status"}
  ]
}
```

### Template Count

As of December 2025:
- **6,621 active templates** across 150+ jurisdictions
- Templates organized by:
  - `sourceType`: cr (corporate registry), lit (litigation), reg (regulatory), at (asset), misc
  - `jurisdiction`: ISO 2-letter country codes
  - `inputTypes`: What data the template accepts

---

## V. Integration with JESTER

TORPEDO uses JESTER for the actual scraping:

```
TORPEDO (Router)                    JESTER (Executor)
┌─────────────────┐                ┌─────────────────┐
│ Template Lookup │                │ URL Scraping    │
│ URL Generation  │───────────────▶│ Content Extract │
│ Schema Apply    │◀───────────────│ HTML/JSON Parse │
│ Field Mapping   │                │ Error Handling  │
└─────────────────┘                └─────────────────┘
```

### JESTER Components Used

| Component | Purpose |
|-----------|---------|
| `executor.py` | Runs the actual HTTP requests and scraping |
| `experimenter.py` | Discovers new output schemas from unknown sources |
| `seekleech.py` | Mines templates from discovered domains |
| `harvester.py` | Collects raw HTML/JSON content |
| `ingester.py` | Processes content into structured data |

---

## VI. SeekLeech Integration

SeekLeech is the template mining system that powers TORPEDO's template database:

```
                    SEEKLEECH TEMPLATE MINING

   Domain Pool                   SeekLeech                  Template Store
   ┌──────────────┐              ┌────────────────┐        ┌─────────────────┐
   │ ATLAS        │              │ Mine URL       │        │ template_engines│
   │ 8.5M domains │──────────────│ patterns from  │───────▶│ ES index        │
   │              │              │ domain crawls  │        │ 6,621 templates │
   └──────────────┘              └────────────────┘        └─────────────────┘
```

### What SeekLeech Discovers

1. **URL Patterns** - How queries map to URLs
2. **Form Structures** - POST data patterns
3. **Result Selectors** - CSS/XPath for extraction
4. **Pagination Logic** - How to get more results
5. **Rate Limits** - How often to query

---

## VII. Elasticsearch Indices

| Index | Purpose |
|-------|---------|
| `template_engines` | URL templates per source |
| `torpedo_schemas` | Learned extraction schemas |
| `cymonides-1-{projectId}` | Extracted results per project |

### Sample Document in `cymonides-1-{projectId}`

```json
{
  "url": "https://handelsregister.de/company/12345",
  "query": "Acme GmbH",
  "templateCode": "handelsregister_de",
  "extractedAt": "2025-12-16T10:30:00Z",
  "fields": {
    "company_name": "Acme GmbH",
    "company_reg_id": "HRB 12345",
    "jurisdiction": "de",
    "status": "active",
    "registration_date": "2015-03-15"
  },
  "fieldCodes": [13, 43, 44, 46, 45],
  "schemaVersion": 3,
  "extractionMethod": "schema_deterministic"
}
```

---

## VIII. API Integration

### Search Orchestrator

TORPEDO is wired into `searchOrchestrator.ts`:

```typescript
// Parser detects torpedo syntax
const parsed = parseSearchQuery("cde:Acme GmbH");
// parsed.mode = "torpedo_search"
// parsed.torpedoInputType = "c"
// parsed.torpedoJurisdiction = "de"

// Handler processes torpedo search
case "torpedo_search":
  result = await handleTorpedoSearch(parsed, options);
  break;
```

### torpedoResultProcessor.ts

The processor handles:
1. Template lookup from ES
2. URL generation with query substitution
3. JESTER scraping execution
4. Schema-based extraction
5. Nano expansion if needed
6. Result indexing to `cymonides-1-{projectId}`

---

## IX. Key Files

| File | Location | Purpose |
|------|----------|---------|
| `torpedoResultProcessor.ts` | `server/services/` | Self-learning extraction engine |
| `searchParser.ts` | `server/utils/` | Parses torpedo syntax |
| `searchOrchestrator.ts` | `server/lib/` | Routes to torpedo handler |
| `seekleech.py` | `BACKEND/modules/JESTER/` | Template mining |
| `executor.py` | `BACKEND/modules/JESTER/` | URL scraping execution |
| `experimenter.py` | `BACKEND/modules/JESTER/` | Schema discovery |

---

## X. Training New Templates

To add a new template manually:

```typescript
import { trainTemplateSchema } from '../services/torpedoResultProcessor';

// Train from example page
await trainTemplateSchema(
  "new_registry_uk",
  "https://example-registry.co.uk/company/12345678",
  "<html>...scraped content...</html>"
);
```

Or let SeekLeech auto-discover from domain crawls.

---

## XI. Design Decisions

### Why Self-Learning?

1. **6,621+ sources** - Can't manually define all schemas
2. **Sources change** - Fields get added/removed
3. **Quality improves** - More extractions = better patterns
4. **Eventually deterministic** - No AI needed after learning

### Why Per-Template Schemas?

1. **Each source is different** - Same field, different selectors
2. **Isolation** - One source's schema doesn't affect others
3. **Version tracking** - Can roll back bad learning

### Why GPT-5-nano?

1. **Fast** - 50ms per call
2. **Cheap** - Minimal token usage
3. **Good enough** - Only needs to identify field names
4. **Temporary** - Stops after schema stabilizes

---

## XII. Future Enhancements

1. **Schema Sharing** - Cross-template pattern inheritance
2. **Confidence Decay** - Reduce confidence if patterns stop matching
3. **Auto-Pruning** - Remove fields that consistently fail
4. **Multi-page Assembly** - Combine data from paginated results
5. **Change Detection** - Alert when source structure changes

---

## XIII. Relationship to Other Modules

```
                    MODULE RELATIONSHIPS

   ┌─────────────────────────────────────────────────────────┐
   │                        FRONTIER                         │
   │              (Domain Discovery Orchestrator)            │
   └─────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
   │   ALLDOM    │     │  LINKLATER  │     │   TORPEDO   │
   │ Domain Ops  │     │ Archive Intel│     │Registry Srch│
   └─────────────┘     └─────────────┘     └──────┬──────┘
                                                  │
                                           ┌──────▼──────┐
                                           │   JESTER    │
                                           │ Scraping    │
                                           └──────┬──────┘
                                                  │
                                           ┌──────▼──────┐
                                           │   ATLAS     │
                                           │ Domain Intel│
                                           │ 8.5M domains│
                                           └─────────────┘
```

---

**Last Updated:** December 2025
**Maintainer:** C0GN1T0 / Drill Search Team
