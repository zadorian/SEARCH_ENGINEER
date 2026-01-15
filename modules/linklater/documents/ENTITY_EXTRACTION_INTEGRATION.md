# LINKLATER Entity Extraction Architecture

**Date:** 2025-12-10 (Updated)
**Status:** PRODUCTION

---

## Summary

LINKLATER provides the **primary entity extraction system** for Drill Search. The architecture uses a layered approach with Python as the single source of truth, accessible via FastAPI endpoints.

---

## Correct Extraction Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 EXTRACTION PIPELINE                          │
│                                                              │
│  Layer 1: Schema.org JSON-LD (free, fast, confidence=1.0)   │
│           └─ Organizations, Persons from structured markup   │
│                                                              │
│  Layer 2: Regex for Emails (fast, reliable)                 │
│           └─ RegexBackend, confidence=0.9                    │
│                                                              │
│  Layer 3: GLiNER + phonenumbers for Phones (local, valid)   │
│           └─ GLiNERBackend + phonenumbers library            │
│           └─ E.164 normalized format                         │
│                                                              │
│  Layer 4: Haiku 4.5 for Persons/Companies/Relationships     │
│           └─ Extracts FROM SCRATCH (not pre-extracted)       │
│           └─ 42 relationship types from ontology             │
│           └─ Dynamic filtering by entity types               │
└─────────────────────────────────────────────────────────────┘
```

**Key Design Principle:** Haiku extracts persons, companies, AND relationships in a SINGLE PASS from scratch. It does NOT validate pre-extracted entities.

---

## API Endpoints

**Base URL:** `/api/linklater/extraction`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/extract` | POST | Full extraction (all entity types + relationships) |
| `/extract-phones` | POST | Phone-only extraction (GLiNER + phonenumbers) |
| `/extract-entities-haiku` | POST | Full Haiku extraction (text input) |
| `/health` | GET | Backend availability check |
| `/ontology` | GET | Valid relationship types |

### POST /extract

**Request:**
```json
{
  "html": "<html>...",
  "url": "https://example.com",
  "extract_relationships": true,
  "use_legacy_flow": false
}
```

**Response:**
```json
{
  "persons": [{"value": "John Smith", "type": "person", "confidence": 0.95}],
  "companies": [{"value": "Acme Corp", "type": "company", "confidence": 0.9}],
  "emails": [{"value": "john@acme.com", "type": "email", "confidence": 0.98}],
  "phones": [{"value": "+14155551234", "type": "phone", "confidence": 0.95}],
  "edges": [
    {
      "source_type": "person",
      "source_value": "John Smith",
      "relation": "employed_by",
      "target_type": "company",
      "target_value": "Acme Corp",
      "confidence": 0.85,
      "evidence": "John Smith is the CEO of Acme Corp"
    }
  ],
  "backend_used": "correct_flow",
  "relationship_backend": "haiku-4.5",
  "processing_time": 2.34
}
```

---

## Relationship Ontology

**Location:** `input_output/ontology/relationships.json`

The ontology contains **42 relationship types** organized by node type:

### Corporate Relationships
- `officer_of`, `director_of`, `employed_by`, `employs`
- `beneficial_owner_of`, `shareholder_of`
- `subsidiary_of`, `legal_parent_of`

### Ownership
- `owns`, `owned_by`, `owner_of`

### Contact
- `has_phone`, `has_email`, `has_address` (handled by regex/GLiNER, excluded from Haiku)

### Location
- `headquartered_at`, `registered_in`, `resides_at`, `located_at`

### Association
- `partner_of`, `affiliated_with`, `related_to`, `associated_with`

### Family
- `married_to`, `child_of`, `sibling_of`

### Social/Web
- `has_linkedin`, `has_twitter`, `has_website`

### Evidence
- `mentioned_in`, `documented_by`, `filed_with`

**Dynamic Filtering:** When extracting, only relationship types valid for the entity types present are included in the Haiku prompt.

---

## Backend Selection

| Entity Type | Backend | Notes |
|-------------|---------|-------|
| Email | Regex | Fast, reliable, no API cost |
| Phone | GLiNER + phonenumbers | Local model + Google's libphonenumber |
| Person | Haiku 4.5 | Extracts from scratch with context |
| Company | Haiku 4.5 | Extracts from scratch with context |
| Relationships | Haiku 4.5 | All person↔company edges in one pass |

---

## Node.js Integration

**Bridge:** `server/services/extractionBridge.ts`

```typescript
import { extractEntities, extractPhones, checkHealth } from './extractionBridge';

// Full extraction
const result = await extractEntities({
  html: content,
  url: 'https://example.com',
  extractRelationships: true
});

// Phone-only extraction
const phones = await extractPhones(html, url);

// Health check
const health = await checkHealth();
```

**Unified Pipeline:** `server/services/extraction/index.ts`

```typescript
import { runExtractionPipeline } from './extraction';

// Uses Python by default, falls back to legacy Node.js
const result = await runExtractionPipeline(content, {
  sourceUrl: url,
  extractRelationships: true
});
```

**Environment Variable:** Set `USE_PYTHON_EXTRACTION=false` to force legacy Node.js extraction.

---

## File Locations

### Python (Primary)
| File | Purpose |
|------|---------|
| `BACKEND/api/linklater_extraction_routes.py` | FastAPI endpoints |
| `BACKEND/modules/LINKLATER/extraction/entity_extractor.py` | Main orchestrator |
| `BACKEND/modules/LINKLATER/extraction/backends/haiku.py` | Haiku 4.5 backend |
| `BACKEND/modules/LINKLATER/extraction/backends/gliner.py` | GLiNER + phonenumbers |
| `BACKEND/modules/LINKLATER/extraction/backends/regex.py` | Regex patterns |
| `BACKEND/modules/LINKLATER/extraction/ontology.py` | Relationship ontology loader |
| `BACKEND/modules/LINKLATER/extraction/models.py` | Entity/Edge data classes |
| `input_output/ontology/relationships.json` | Authoritative relationship schema |

### Node.js (Bridge)
| File | Purpose |
|------|---------|
| `server/services/extractionBridge.ts` | HTTP bridge to Python API |
| `server/services/extraction/index.ts` | Unified extraction interface |
| `server/services/extraction/LLMExtractor.ts` | Legacy fallback |
| `server/services/extraction/RegexExtractor.ts` | Legacy regex fallback |

---

## Performance Characteristics

| Operation | Time | Cost | Notes |
|-----------|------|------|-------|
| Schema.org extraction | <100ms | Free | JSON-LD parsing |
| Regex (email) | <50ms | Free | Pattern matching |
| GLiNER + phonenumbers | 500ms-2s | Free | Local model |
| Haiku full extraction | 2-5s | ~$0.001 | Persons + companies + relationships |
| Total pipeline | 3-8s | ~$0.001 | All layers |

---

## Models Used

| Model | ID | Purpose |
|-------|-----|---------|
| Claude Haiku 4.5 | `claude-haiku-4-5-20251001` | Entity + relationship extraction |
| GLiNER | `urchade/gliner_medium-v2.1` | Local NER for phone candidates |

---

## Usage Examples

### 1. Extract from HTML

```python
from LINKLATER.extraction import extract_entities

result = await extract_entities(
    html="<html><body>John Smith is CEO of Acme Corp...</body></html>",
    url="https://example.com",
    extract_relationships=True
)

print(f"Found {len(result['persons'])} persons")
print(f"Found {len(result['edges'])} relationships")
```

### 2. Phone-Only Extraction

```python
from LINKLATER.extraction.backends.gliner import GLiNERBackend

backend = GLiNERBackend()
result = backend.extract(html, url, include_emails=False, include_phones=True)

for phone in result['phones']:
    print(f"Phone: {phone['value']}")  # E.164 format: +14155551234
```

### 3. Full Haiku Extraction

```python
from LINKLATER.extraction.backends.haiku import HaikuBackend

backend = HaikuBackend()
result = await backend.extract_all(text, url)

for edge in result['edges']:
    print(f"{edge.source_value} --{edge.relation}--> {edge.target_value}")
```

---

## Integration with Cymonides

Extracted entities flow to Cymonides-1 (entity graph):

```
LINKLATER Extraction
        │
        ▼
CymonidesEntityCentre.createEntity()
        │
        ├─► Node created in cymonides-1-{projectId}
        │
        └─► Edges embedded in node documents
```

**Persistence:** `server/services/CymonidesEntityCentre.ts`

---

## Troubleshooting

### Ontology Not Loading

**Symptom:** Only 5 relationship types instead of 42

**Check:**
```python
from LINKLATER.extraction.ontology import get_valid_relations
print(len(get_valid_relations()))  # Should be 42
```

**Fix:** Ensure `input_output/ontology/relationships.json` exists at project root.

### Python API Unavailable

**Symptom:** Node.js falling back to legacy extraction

**Check:**
```typescript
const health = await checkHealth();
console.log(health.linklater_available);  // Should be true
```

**Fix:** Ensure Python FastAPI server is running on `PYTHON_API_URL` (default: `http://localhost:8000`).

### Phone Extraction Missing

**Symptom:** No phones extracted

**Check:** GLiNER and phonenumbers libraries installed:
```bash
pip install gliner phonenumbers
```

---

## Version History

| Date | Change |
|------|--------|
| 2025-12-10 | Consolidated to Python-primary, added ontology, fixed Haiku flow |
| 2025-11-30 | Initial simplified extractor (GPT-5-nano only) |
