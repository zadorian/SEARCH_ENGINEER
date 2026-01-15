# Cymonides-1 (C1) Schema Registry

**THE CANONICAL SINGLE SOURCE OF TRUTH** for all node classes, types, relationships, and edge definitions.

## Files

| File | Description | Version |
|------|-------------|---------|
| `node_classes.json` | The 4 dimensions: SUBJECT, LOCATION, NARRATIVE, NEXUS | 1.1.0 |
| `node_types.json` | Hierarchical node type definitions (CLASS > TYPE > SUBTYPE) | 2.1.0 |
| `relationships.json` | NEXUS atomic relationship ontology (~14 root types + subtypes) | 3.2.1 |
| `edge_types.json` | Operational edge definitions with metadata schemas | - |

## The Four Dimensions

```
SUBJECT (GREEN)   - Dynamic/Animate: Entities and their identifiers
LOCATION (WHITE)  - Static/Boundaries: Geographic, temporal, and source references
NARRATIVE (BLUE)  - Documentation and metadata: Projects, tags, notes, evidence
NEXUS (PURPLE)    - Relationships and queries that bridge dimensions
```

## Node Type Hierarchy

Structure: `CLASS > CATEGORY > TYPE`

```
SUBJECT
├── ENTITY: person, organization, object, asset, vessel, aircraft, vehicle, account, document
├── IDENTIFIER: email, phone, national_id, passport, tax_id, reg_number, username, crypto_wallet, lei, bic, iban, domain, ip_address, url, tracking_code
├── CLASSIFIER: industry, profession, title, legal_form, size_class, status
└── CONCEPT: phenomenon, topic, theme

LOCATION
├── GEO: country, region, municipality, address, coordinates
├── TEMPORAL: date, year, month, period, timestamp
├── SOURCE: aggregator, platform, breach, registry, database, archive
├── FORMAT: filetype, mime_type, language
└── CATEGORY: news, corporate, government, academic, social

NARRATIVE
├── PROJECT: project, case, matter
├── TAG: tag, flag, status_tag, verification_tag
├── NOTE: note, comment, annotation
└── EVIDENCE: document, screenshot, transcript

NEXUS
├── RELATIONSHIP: relationship, association, link
├── QUERY: query, search, filter
└── AGGREGATOR_RESULT: aggregator_result, search_result, api_response
```

## Relationship Ontology

The `relationships.json` follows atomic design principles:

1. **ATOMIC**: ~14 fundamental relationship types (particles)
2. **HIERARCHICAL**: Subtypes inherit from parents (officer_of > director_of)
3. **ALIASES**: External system mappings (ftm:Directorship > officer_of)
4. **EMERGENT**: Complex patterns emerge from graph traversal
5. **ALWAYS VALID**: Parent type is always acceptable

Root relationships:
- `same_as` (1) - Entity resolution
- `related_to` (2) - Generic associations, family, partnerships
- `owns` (3) - Ownership relationships
- `controls` (4) - Control without ownership
- `member_of` (5) - Organizational membership
- `located_at` (6) - Geographic relationships
- `has` (7) - Attribute attachments (email, phone, etc.)
- `links_to` (8) - Digital/web relationships
- `mentioned_in` (9) - Evidence/provenance
- `party_to` (10) - Legal proceedings
- `transacts_with` (11) - Financial transactions
- `flagged_with` (12) - Risk flags (PEP, sanctions)
- `succeeds` (13) - Corporate succession
- `regulated_by` (14) - Regulatory relationships
- `not_same_as` (15) - Negative entity resolution
- `enrichment_of` (16) - NEXUS enrichment queries

## Usage

```python
from pathlib import Path
import json

C1_DIR = Path("/data/SEARCH_ENGINEER/BACKEND/modules/cymonides/c1")

# Load node classes
with open(C1_DIR / "node_classes.json") as f:
    node_classes = json.load(f)

# Load node types
with open(C1_DIR / "node_types.json") as f:
    node_types = json.load(f)

# Load relationships
with open(C1_DIR / "relationships.json") as f:
    relationships = json.load(f)

# Load edge types
with open(C1_DIR / "edge_types.json") as f:
    edge_types = json.load(f)
```

## Backward Compatibility

Symlinks exist for backward compatibility:
- `/data/CLASSES/NEXUS/RELATIONSHIPS/ontology.json` > `relationships.json`
- `/data/SEARCH_ENGINEER/BACKEND/modules/cymonides/edge_types.json` > `c1/edge_types.json`

## Satellite Files

Domain-specific type definitions in `/data/CLASSES/`:
- `/data/CLASSES/SUBJECT/identifiers.json` - Identifier patterns
- `/data/CLASSES/SUBJECT/industries.json` - NAICS/NACE industries
- `/data/CLASSES/SUBJECT/professions.json` - SOC/ISCO professions
- `/data/CLASSES/SUBJECT/titles.json` - Professional titles

These satellite files reference `node_types.json` as the canonical source.

## Last Updated

2026-01-13
