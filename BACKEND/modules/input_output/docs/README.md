# CLEAN MATRIX - NO REFERENCES

**Created:** 2025-11-23
**Philosophy:** Minimal, self-contained, no cross-references

---

## STRUCTURE

```
input_output2/matrix/
├── sources.json      1.6 MB  - 2,496 sources across 69 jurisdictions
├── edge_types.json     36 KB  - Valid relationship types
└── legend.json        6.4 KB  - Entity type ID→Label mappings
```

**That's it. 3 files.**

---

## COMPARISON TO OLD STRUCTURE

### Before (35 files + 4 directories)

```
input_output/matrix/
├── flows.json                      69 KB   → Merged into sources.json
├── registries.json                1.1 MB   → Merged into sources.json
├── legend.json                    6.4 KB   → Copied as-is ✅
├── edge_types.json                 36 KB   → Copied as-is ✅
├── meta_description.json           63 B    → DELETED
├── meta_spec_version.json           5 B    → DELETED
├── meta_friction_order.json        43 B    → DELETED
├── meta_generated_at.json          26 B    → DELETED
├── meta_last_updated.json          34 B    → DELETED
├── metadata.json                  408 B    → DELETED (broken reference)
├── corporella.json                163 KB   → Module spec (not core matrix)
├── eyed.json                      1.5 KB   → Module spec (not core matrix)
├── alldom.json                    1.4 KB   → Module spec (not core matrix)
├── rules.json                     1.2 MB   → Transformation logic (separate concern)
├── field_meta.json                 43 KB   → Field definitions (not routing)
├── node_templates.json            244 KB   → Template data (not routing)
├── graph_schema.json               57 KB   → Schema spec (documentation)
├── entity_template*.json           2-3 KB  → Templates (not routing)
├── source_template.json           962 B    → Template (not routing)
├── query_template.json            1.2 KB   → Template (not routing)
├── narrative_template.json        1.0 KB   → Template (not routing)
├── ftm_schema_mapping.json        5.4 KB   → FtM spec (separate concern)
├── entity_class_type_matrix.json  4.4 KB   → Class mappings (derivative)
├── documentation.json              21 KB   → Auto-generated docs
├── readme_graph.json              3.1 KB   → Viz config
├── code_snippets.json              11 KB   → Examples
├── additional_specs.json          134 KB   → Extended specs
├── database_capabilities.json     4.4 KB   → DB features
├── datasets.json                  3.9 KB   → File inventory
├── project_docs.json              554 KB   → Documentation
├── company_bang_urls.json          47 KB   → DuckDuckGo bangs
├── index.json                     575 B    → Pointer file
├── alldom/ (empty)                         → DELETED
├── corporella/ (empty)                     → DELETED
└── eyed/ (empty)                           → DELETED
```

### After (3 files)

```
input_output2/matrix/
├── sources.json      - ALL routing sources (registries + datasets)
├── edge_types.json   - Graph relationship rules
└── legend.json       - Entity type ID mappings
```

**Reduction:** 35 files → 3 files (91% reduction)

---

## WHAT WE KEPT

### ✅ sources.json (1.6 MB)

**Unified catalog of all data sources:**

- 2,475 manual registries (from old registries.json)
- 21 ALEPH datasets (from old flows.json)
- Total: 2,496 sources across 69 jurisdictions

**Schema standardized:**

```json
{
  "AL": [
    {
      "id": "qkb.gov.al_corporate_registry",
      "name": "National Business Center",
      "jurisdiction": "AL",
      "domain": "qkb.gov.al",
      "url": "https://qkb.gov.al/",
      "section": "misc",
      "type": "corporate_registry",
      "access": "public",
      "inputs": [],
      "outputs": ["companies", "ownership"],
      "notes": "Searching by name, address, shareholder",
      "flows": [],
      "metadata": {
        "source": "wiki",
        "last_verified": null,
        "reliability": "medium"
      }
    }
  ]
}
```

**ALEPH entries include structured flows:**

```json
{
  "id": "aleph_776",
  "name": "Azerbaijan Commercial Taxpayers [ALEPH]",
  "inputs": ["company_name", "company_id", "person_name"],
  "flows": [
    {
      "input": "company_name",
      "output_schema": "Company",
      "output_fields": ["company_name", "company_id", "company_officers", ...]
    }
  ]
}
```

### ✅ edge_types.json (36 KB)

**Graph relationship rules - unchanged**

Defines valid edges:

- `officer_of`, `beneficial_owner_of`, `shareholder_of`
- `has_email`, `has_phone`, `has_address`, `has_website`
- `registered_at`, `located_at`, etc.

**This file is perfect as-is.** No changes needed.

### ✅ legend.json (6.4 KB)

**Entity type ID→Label mappings - unchanged**

Simple dictionary:

```json
{
  "1": "email",
  "2": "phone",
  "13": "company_name",
  "14": "company_reg_id"
}
```

**This file is perfect as-is.** No changes needed.

---

## WHAT WE DELETED

### ❌ Meta Files (6 files → 0)

**Old fragmented metadata:**

- `meta_description.json` - "Unified input/output routing matrix"
- `meta_spec_version.json` - "1.1"
- `meta_friction_order.json` - ["Open", "Paywalled", "Restricted"]
- `meta_generated_at.json` - ISO timestamp
- `meta_last_updated.json` - ISO timestamp
- `metadata.json` - Broken reference to non-existent file

**New approach:** No metadata files. If needed, embed in sources.json entries.

### ❌ Module Specs (3 files)

- `corporella.json` (163 KB) - Backend module configuration
- `eyed.json` (1.5 KB) - EYE-D module spec
- `alldom.json` (1.4 KB) - ALLDOM module spec

**Reason:** These are backend implementation details, not routing matrix data.
**Move to:** `python-backend/modules/*/config.json` if needed.

### ❌ Templates (7 files)

- `entity_template.json`
- `entity_template_full.json`
- `entity_template_compact.json`
- `source_template.json`
- `query_template.json`
- `narrative_template.json`
- `node_templates.json` (244 KB)

**Reason:** These are code scaffolding, not routing data.
**Move to:** TypeScript type definitions or delete if auto-generated.

### ❌ Documentation/Specs (9 files)

- `documentation.json` (21 KB) - Auto-generated docs
- `graph_schema.json` (57 KB) - Schema spec
- `readme_graph.json` (3.1 KB) - Visualization config
- `code_snippets.json` (11 KB) - Implementation examples
- `additional_specs.json` (134 KB) - Extended specifications
- `database_capabilities.json` (4.4 KB) - DB feature matrix
- `datasets.json` (3.9 KB) - File inventory
- `project_docs.json` (554 KB) - Project documentation
- `index.json` (575 B) - Pointer file

**Reason:** Documentation != Data. Keep in `docs/` or regenerate.

### ❌ Transformation Logic (2 files)

- `rules.json` (1.2 MB) - Have→Get transformation rules
- `field_meta.json` (43 KB) - Field definitions

**Reason:** Business logic, not routing catalog.
**Decision:** If needed, keep separately or derive from sources.json.

### ❌ Special Purpose (3 files)

- `ftm_schema_mapping.json` (5.4 KB) - FtM schema conversions
- `entity_class_type_matrix.json` (4.4 KB) - Class/type mappings
- `company_bang_urls.json` (47 KB) - DuckDuckGo bang URLs

**Reason:** Separate concerns (FtM integration, search shortcuts).
**Decision:** Move to respective module directories.

---

## BENEFITS

1. **No Cross-References** - Each file is self-contained
2. **Faster Loading** - 3 files vs 35 files
3. **Clear Purpose** - Routing data only
4. **Easy to Validate** - Single schema per file
5. **No Orphans** - Everything has a clear owner
6. **Human Readable** - Consistent formatting
7. **Version Control Friendly** - Logical diffs

---

## USAGE

### TypeScript/Node.js

```typescript
import sources from "./input_output2/matrix/sources.json";
import edgeTypes from "./input_output2/matrix/edge_types.json";
import legend from "./input_output2/matrix/legend.json";

// Get all Albanian sources
const albanianSources = sources.AL;

// Find corporate registries
const registries = sources.AL.filter(s => s.type === "corporate_registry");

// Get ALEPH datasets
const alephSources = Object.values(sources)
  .flat()
  .filter(s => s.metadata.source === "aleph");

// Lookup entity type
const entityLabel = legend["13"]; // "company_name"
```

### Python

```python
import json
from pathlib import Path

MATRIX = Path(__file__).parent / 'input_output2' / 'matrix'

with open(MATRIX / 'sources.json') as f:
    sources = json.load(f)

with open(MATRIX / 'edge_types.json') as f:
    edge_types = json.load(f)

with open(MATRIX / 'legend.json') as f:
    legend = json.load(f)

# Get UK sources
uk_sources = sources.get('GB', [])

# Find paywalled sources
paywalled = [
    s for country in sources.values()
    for s in country
    if s['access'] == 'paywalled'
]
```

---

## MIGRATION PATH

### Step 1: Test New Structure

```bash
# Update server/utils/ioMatrix.ts to load from input_output2/
# Run tests
npm run dev
```

### Step 2: Verify Functionality

- Check ioRouter still works
- Verify Matrix dropdown loads
- Test route execution

### Step 3: Swap Directories

```bash
cd /Users/attic/DRILL_SEARCH/drill-search-app
mv input_output input_output.old
mv input_output2 input_output
```

### Step 4: Update References

```bash
# Update imports in:
# - server/utils/ioMatrix.ts
# - server/services/cymonidesRouter.ts
# - Any Python scripts using the matrix
```

### Step 5: Archive Old Structure

```bash
tar -czf input_output.old.tar.gz input_output.old
rm -rf input_output.old
```

---

## APPENDIX: Fields Explanation

**From your requirements:**

| Your Field      | sources.json Field | Notes                                       |
| --------------- | ------------------ | ------------------------------------------- |
| registry name   | `name`             | Human-readable name                         |
| jurisdiction    | `jurisdiction`     | Country/state code                          |
| domain          | `domain`           | Primary domain                              |
| search page url | `url`              | Direct search URL                           |
| note            | `notes`            | Additional context                          |
| input           | `inputs`           | Array of accepted input types               |
| output          | `outputs`          | Array of output fields                      |
| flows           | `flows`            | Structured I/O transformations              |
| section         | `section`          | cr, lit, reg, at, misc                      |
| type            | `type`             | corporate_registry, court_records, etc.     |
| paywalled       | `access`           | public, paywalled, registration, restricted |

**Additional fields we included:**

- `id` - Unique identifier (domain + type)
- `metadata.source` - Origin (wiki, aleph, manual)
- `metadata.reliability` - Data quality indicator
- `metadata.last_verified` - When entry was last checked

**Intelligence metadata (added 2025-11-23):**

- `exposes_related_entities` - Boolean: Does this source reveal related entities?
- `related_entity_types` - Array: What types (UBO, subsidiaries, directors, shareholders, parent_company, affiliated_entities, foreign_entities, historical_entities)
- `classification` - Source taxonomy (Official Registry, Private Aggregator, Leak Dataset, OSINT Platform, Court System, etc.)
- `arbitrage_opportunities` - Array of specific intelligence strategies this source enables

---

## INTELLIGENCE FILTERING (The Arbitrage Analyst Layer)

The enhanced schema enables strategic intelligence gathering through metadata-driven filtering:

### Strategic Filter Examples

#### Find Free UBO Sources

```typescript
// Find jurisdictions with free beneficial ownership data
const freeUBOSources = Object.entries(sources)
  .map(([jurisdiction, srcs]) => ({
    jurisdiction,
    sources: srcs.filter(
      s => s.related_entity_types.includes("UBO") && s.access === "public"
    ),
  }))
  .filter(x => x.sources.length > 0);

// Result: Rare! Only certain jurisdictions (UK, some EU) have this
```

#### Find Foreign Entity Reveals

```typescript
// Sources that expose cross-border relationships
const foreignEntitySources = Object.values(sources)
  .flat()
  .filter(
    s =>
      s.related_entity_types.includes("foreign_entities") ||
      s.arbitrage_opportunities.some(opp => opp.includes("Foreign"))
  );

// Arbitrage: Use these to find hidden international connections
```

#### Compare Official vs Leak Datasets

```typescript
// Find leak datasets for comparison with official registries
const leakDatasets = Object.values(sources)
  .flat()
  .filter(s => s.classification === "Leak Dataset");

const officialRegistries = Object.values(sources)
  .flat()
  .filter(s => s.classification === "Official Registry");

// Strategy: Cross-reference leaked data with official records
// to find discrepancies, hidden ownership, or timeline gaps
```

#### Identify Historical Tracking Sources

```typescript
// Sources that reveal former directors/shareholders
const historicalSources = Object.values(sources)
  .flat()
  .filter(
    s =>
      s.related_entity_types.includes("historical_entities") ||
      s.arbitrage_opportunities.some(opp => opp.includes("Historical"))
  );

// Arbitrage: Track entity movements over time, identify patterns
```

#### Find OSINT-to-Registry Validation Chains

```typescript
// Build validation pipeline: OSINT → Official Registry
const osintPlatforms = Object.values(sources)
  .flat()
  .filter(s => s.classification === "OSINT Platform");

const officialRegistriesByJurisdiction = {};
Object.entries(sources).forEach(([jurisdiction, srcs]) => {
  officialRegistriesByJurisdiction[jurisdiction] = srcs.filter(
    s => s.classification === "Official Registry"
  );
});

// Strategy: Use OSINT to gather leads, validate against official sources
```

#### Arbitrage Opportunity Search

```typescript
// Find all sources with specific arbitrage strategies
const bulkDownloadSources = Object.values(sources)
  .flat()
  .filter(s =>
    s.arbitrage_opportunities.some(opp => opp.includes("Bulk Pattern Analysis"))
  );

const foreignBranchReveals = Object.values(sources)
  .flat()
  .filter(s =>
    s.arbitrage_opportunities.some(opp => opp.includes("Foreign Branch Reveal"))
  );

// Compile strategic playbook for specific investigation needs
```

### Classification Taxonomy

Sources are automatically classified into strategic categories:

- **Official Registry** - Government-run corporate registries (`.gov` domains)
- **Private Aggregator** - Commercial data providers (paywalled)
- **Leak Dataset** - Panama Papers, Paradise Papers, etc. (ALEPH)
- **Structured Dataset** - Vetted ALEPH datasets (non-leak)
- **OSINT Platform** - Drill Search OSINT modules (EYE-D)
- **Intelligence Aggregator** - Corporate intel modules (Corporella)
- **Technical Intelligence** - Domain/infrastructure intel (AllDom)
- **Court System** - Litigation and court records
- **Public Database** - Free public data sources
- **Regulatory Authority** - Compliance and regulatory filings
- **Other** - Miscellaneous sources

### Example: Complete Enhanced Entry

```json
{
  "id": "qkb.gov.al_corporate_registry",
  "name": "National Business Center",
  "jurisdiction": "AL",
  "domain": "qkb.gov.al",
  "url": "https://qkb.gov.al/",
  "section": "misc",
  "type": "corporate_registry",
  "access": "public",
  "inputs": [],
  "outputs": ["companies", "ownership"],
  "notes": "Searching by name, address, shareholder",
  "flows": [],
  "metadata": {
    "source": "wiki",
    "last_verified": null,
    "reliability": "medium"
  },
  "exposes_related_entities": true,
  "related_entity_types": ["shareholders"],
  "classification": "Official Registry",
  "arbitrage_opportunities": []
}
```

### Stats (Post-Enhancement)

- **Total sources:** 2,498
- **Sources exposing related entities:** 211 (8.4%)
- **Sources with arbitrage opportunities:** 43 (1.7%)
- **Classifications identified:** 10 distinct types

---

## VALIDATION

```bash
# Check file validity
cd input_output2/matrix
python3 -m json.tool sources.json > /dev/null && echo "✅ sources.json valid"
python3 -m json.tool edge_types.json > /dev/null && echo "✅ edge_types.json valid"
python3 -m json.tool legend.json > /dev/null && echo "✅ legend.json valid"

# Count entries
echo "Sources: $(cat sources.json | jq '[.[] | length] | add')"
echo "Jurisdictions: $(cat sources.json | jq 'keys | length')"
echo "Edge types: $(cat edge_types.json | jq 'keys | length')"
echo "Entity types: $(cat legend.json | jq 'keys | length')"
```

Expected output:

```
✅ sources.json valid
✅ edge_types.json valid
✅ legend.json valid
Sources: 2496
Jurisdictions: 69
Edge types: 8
Entity types: 216
```

---

**Result: Clean, minimal, self-contained matrix ready for production.**
