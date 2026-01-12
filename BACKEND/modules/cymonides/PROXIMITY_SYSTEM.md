# CYMONIDES Multi-Axis Proximity System

> **Status:** Mostly implemented, needs backfilling and unified query interface

## The Three Proximity Axes

```
                    CONCEPT (Semantic Space)
                         │
                         │  "Docs conceptually near 'shell company'"
                         │  Query: knn on content_embedding
                         │
                         │
    TIME ────────────────┼──────────────────── SPACE (GEO)
    │                    │                         │
    │ "Events within    │                         │ "Properties within
    │  90 days"         │                         │  5km of this address"
    │                   │                         │
    │ Query: date_range │                         │ Query: geo_distance
    └────────────────────┴─────────────────────────┘
```

---

## 1. GEO PROXIMITY (SPACE)

### Status: ✅ IMPLEMENTED

| Index | Field | Type | Docs | Status |
|-------|-------|------|------|--------|
| `uk_addresses` | `location` | `geo_point` | 4.3M | ✅ Complete |
| `openownership` | `location` | `geo_point` | 36.4M | 🔄 In Progress |
| `uk_ccod` | - | - | 4.3M | ❌ Needs geocoding |
| `uk_ocod` | - | - | 91K | ❌ Needs geocoding |
| `uk_leases` | - | - | 7.7M | ❌ Needs geocoding |

### Query Patterns

```bash
# Find properties within 5km of a point
POST /uk_addresses/_search
{
  "query": {
    "geo_distance": {
      "distance": "5km",
      "location": { "lat": 51.5074, "lon": -0.1278 }
    }
  }
}

# Find properties within 5km of ANOTHER property
POST /uk_addresses/_search
{
  "query": {
    "geo_distance": {
      "distance": "5km",
      "location": {
        "lat": 51.5074,  # From first doc's location
        "lon": -0.1278
      }
    }
  }
}

# Bounding box (regional search)
POST /uk_addresses/_search
{
  "query": {
    "geo_bounding_box": {
      "location": {
        "top_left": { "lat": 51.6, "lon": -0.3 },
        "bottom_right": { "lat": 51.4, "lon": 0.1 }
      }
    }
  }
}
```

### Geocoding Pipeline

Uses:
- UK Postcodes CSV (fast, ~2M/hour)
- Nominatim fallback for free-text addresses (slow, rate-limited)

---

## 2. TEMPORAL PROXIMITY (TIME)

### Status: ✅ IMPLEMENTED (Hierarchical schema + ES mapping + extraction pipeline)

**Implementation:**
- ES mapping updated with hierarchical fields
- `temporal_hierarchy.py` utility created for derivation
- `UniversalExtractor` integrated to populate fields at ingest

**cymonides-2.temporal structure (FULL):**

```json
{
  "temporal": {
    // === POINT IN TIME (Hierarchical) ===
    "published_date": "date",           // Full: 2024-06-15T10:30:00Z
    "year": "integer",                  // Derived: 2024
    "month": "integer",                 // Derived: 6
    "day": "integer",                   // Derived: 15
    "yearmonth": "keyword",             // Derived: "2024-06" (for grouping)
    "decade": "keyword",                // Derived: "2020s"
    "precision": "keyword",             // "day" | "month" | "year" | "decade" | "unknown"

    // === PERIOD / RANGE ===
    "period_start": "date",             // For events spanning time
    "period_end": "date",               //
    "period_start_year": "integer",     // For year-only precision
    "period_end_year": "integer",       //

    // === SEMANTIC ERA ===
    "era": "keyword",                   // "cold_war", "post_soviet", "covid_era"
    "content_years": "long[]",          // All years mentioned in content

    // === ARCHIVE DATES ===
    "first_seen": "date",
    "last_archived": "date"
  }
}
```

### Precision Levels

| Input | Stored As | precision | Example dimension_keys |
|-------|-----------|-----------|------------------------|
| `15 June 2024` | `2024-06-15` | `day` | `year:2024`, `ym:2024-06`, `decade:2020s` |
| `June 2024` | `2024-06-01` | `month` | `year:2024`, `ym:2024-06`, `decade:2020s` |
| `2024` | `2024-01-01` | `year` | `year:2024`, `decade:2020s` |
| `1990s` | `1990-01-01` | `decade` | `decade:1990s` |
| `2019-2021` | period_start/end | `year` | `year:2019`, `year:2020`, `year:2021` |

### Era Mappings

| Era ID | Years | Description |
|--------|-------|-------------|
| `cold_war` | 1947-1991 | Cold War period |
| `post_soviet` | 1991-2000 | Post-Soviet transition |
| `pre_2008` | 2000-2008 | Pre-financial crisis |
| `post_2008` | 2008-2019 | Post-crisis era |
| `covid_era` | 2020-2022 | Pandemic period |
| `post_covid` | 2023+ | Current era |

### Query Patterns

```bash
# === EXACT DATE RANGE ===
POST /cymonides-2/_search
{
  "query": {
    "range": {
      "temporal.published_date": {
        "gte": "2024-01-01",
        "lte": "2024-03-31"
      }
    }
  }
}

# === YEAR PRECISION ===
POST /cymonides-2/_search
{
  "query": {
    "term": { "temporal.year": 2024 }
  }
}

# === MONTH PRECISION (June 2024) ===
POST /cymonides-2/_search
{
  "query": {
    "term": { "temporal.yearmonth": "2024-06" }
  }
}

# === DECADE FILTER ===
POST /cymonides-2/_search
{
  "query": {
    "term": { "temporal.decade": "2020s" }
  }
}

# === ERA FILTER ===
POST /cymonides-2/_search
{
  "query": {
    "term": { "temporal.era": "post_soviet" }
  }
}

# === PERIOD OVERLAP (docs covering 2019-2021) ===
POST /cymonides-2/_search
{
  "query": {
    "bool": {
      "must": [
        { "range": { "temporal.period_start": { "lte": "2021-12-31" }}},
        { "range": { "temporal.period_end": { "gte": "2019-01-01" }}}
      ]
    }
  }
}

# === CONTENT YEARS (docs mentioning these years) ===
POST /cymonides-2/_search
{
  "query": {
    "terms": {
      "temporal.content_years": [2019, 2020, 2021]
    }
  }
}

# === TIME CLUSTERING - by month ===
POST /cymonides-2/_search
{
  "size": 0,
  "aggs": {
    "by_month": {
      "date_histogram": {
        "field": "temporal.published_date",
        "calendar_interval": "month"
      }
    }
  }
}

# === TIME CLUSTERING - by year ===
POST /cymonides-2/_search
{
  "size": 0,
  "aggs": {
    "by_year": {
      "terms": { "field": "temporal.year" }
    }
  }
}

# === PRECISION-AWARE QUERY ===
# Only match docs with at least month precision
POST /cymonides-2/_search
{
  "query": {
    "bool": {
      "must": [
        { "term": { "temporal.yearmonth": "2024-06" }},
        { "terms": { "temporal.precision": ["day", "month"] }}
      ]
    }
  }
}
```

### Other Indices with Temporal Fields

| Index | Temporal Fields | Use Case |
|-------|-----------------|----------|
| `openownership` | `statement_date`, `incorporation_date`, `dissolution_date` | Ownership timeline |
| `breach_records` | `breach_date`, `added_date` | Breach timeline |
| `uk_leases` | `lease_date`, `lease_term` | Property timeline |
| `entity_links` | `first_seen`, `last_verified` | Relationship timeline |

---

## 3. CONCEPT PROXIMITY (SEMANTIC SPACE)

### Status: ✅ IMPLEMENTED (Full vector search)

**cymonides-2 embedding structure:**
```json
{
  "content_embedding": {
    "type": "dense_vector",
    "dims": 768,
    "index": true,
    "similarity": "cosine"
  },
  "concepts": {
    "themes": ["keyword"],           // Matched theme IDs
    "phenomena": ["keyword"],        // Matched phenomena IDs
    "red_flag_themes": ["keyword"],  // Matched red flags
    "methodologies": ["keyword"]     // Matched research methods
  }
}
```

**Golden Lists (265 categories with embeddings):**
- `themes`: 51 categories (e.g., "inv_ownership_analysis", "tech_ai")
- `phenomena`: 60 categories (e.g., "shell_company", "circular_ownership")
- `red_flags`: 11 categories (e.g., "rf_sanctions", "rf_money_laundering")
- `methodologies`: 143 categories (e.g., "regulatory_filing_search")

### Query Patterns

```bash
# KNN - Find docs semantically similar to a query
POST /cymonides-2/_search
{
  "knn": {
    "field": "content_embedding",
    "query_vector": [...768 floats...],  # Embed query with multilingual-e5-base
    "k": 10,
    "num_candidates": 100
  }
}

# KNN + Filters - Semantic search within a category
POST /cymonides-2/_search
{
  "knn": {
    "field": "content_embedding",
    "query_vector": [...],
    "k": 10,
    "num_candidates": 100,
    "filter": {
      "term": { "concepts.phenomena.keyword": "shell_company" }
    }
  }
}

# Find docs with similar concepts (discrete)
POST /cymonides-2/_search
{
  "query": {
    "terms": {
      "concepts.themes.keyword": ["inv_ownership_analysis", "inv_sanctions"]
    }
  }
}

# Find docs by red flag proximity
POST /cymonides-2/_search
{
  "query": {
    "bool": {
      "should": [
        { "term": { "concepts.red_flag_themes.keyword": "rf_sanctions" }},
        { "term": { "concepts.phenomena.keyword": "circular_ownership" }}
      ],
      "minimum_should_match": 1
    }
  }
}
```

### How Concept Matching Works (Ingest Time)

```python
# UniversalExtractor.extract_concepts():
1. Embed document content with multilingual-e5-base (768 dims)
2. Compare against 265 golden list embeddings via cosine similarity
3. Categories with similarity > 0.7 are assigned
4. Store: content_embedding + matched category IDs in concepts.*
```

---

## 4. COMPOUND PROXIMITY QUERIES

### Cross-Axis: GEO + TIME
```bash
# Properties acquired near each other AND around same time
POST /uk_addresses/_search
{
  "query": {
    "bool": {
      "must": [
        { "geo_distance": { "distance": "10km", "location": {...} }},
        { "range": { "lease_date": { "gte": "2020-01-01", "lte": "2020-12-31" }}}
      ]
    }
  }
}
```

### Cross-Axis: CONCEPT + TIME
```bash
# Shell company mentions clustered in time
POST /cymonides-2/_search
{
  "query": {
    "bool": {
      "must": [
        { "term": { "concepts.phenomena.keyword": "shell_company" }},
        { "range": { "temporal.published_date": { "gte": "2019-01-01", "lte": "2019-12-31" }}}
      ]
    }
  }
}
```

### Cross-Axis: CONCEPT + GEO (Via Entity Links)
```bash
# 1. Find docs about shell companies
# 2. Extract mentioned addresses
# 3. Geocode and cluster geographically
# This requires the entity extraction pipeline
```

---

## 5. BACKFILL TASKS

### HIGH PRIORITY

| Task | Index | Records | Status |
|------|-------|---------|--------|
| Geocode openownership | openownership | 36.4M | 🔄 Running |
| Geocode uk_ccod | uk_ccod | 4.3M | ❌ TODO |
| Backfill temporal.published_date | cymonides-2 | 13M | ⚠️ Partial |
| Backfill content_embedding | cymonides-2 | 13M | ⚠️ Tiered (high-value only) |

### MEDIUM PRIORITY

| Task | Notes |
|------|-------|
| Index golden list embeddings to ES | Enable knn on category space itself |
| Add temporal_point to openownership | Normalize statement_date for proximity |
| Backfill content_years extraction | Parse years from document content |

---

## 6. DIMENSION REGISTRY INTEGRATION

The `dimension_registry.json` defines prefixes for filtering:

| Proximity Axis | Dimension Prefixes |
|----------------|-------------------|
| **GEO** | `jur:`, `region:`, `district:`, `postcode:` |
| **TEMPORAL** | `year:` |
| **CONCEPT** | `theme:`, `phenomenon:`, `red_flag:`, `method:` |

These enable dimension_keys-based compound filtering:
```
dimension_keys: ["phenomenon:shell_company", "jur:uk", "year:2020"]
```

---

## 7. QUERY INTERFACE (Proposed)

```typescript
interface ProximityQuery {
  // Geo proximity
  geo?: {
    center: { lat: number; lon: number } | string;  // or doc ID
    radius: string;  // "5km", "10mi"
  };

  // Temporal proximity
  temporal?: {
    center: string | Date;  // ISO date or doc ID
    window: string;  // "90d", "6m", "1y"
  };

  // Concept proximity
  concept?: {
    query: string;  // Natural language or category ID
    threshold?: number;  // Similarity threshold (default 0.7)
  };

  // Combine
  operator: "AND" | "OR";
}
```

Example:
```typescript
{
  geo: { center: "doc_12345", radius: "5km" },
  temporal: { center: "2020-06-15", window: "90d" },
  concept: { query: "shell company detection", threshold: 0.75 },
  operator: "AND"
}
```

---

## 8. ARCHITECTURE SUMMARY

```
┌─────────────────────────────────────────────────────────────────┐
│                    PROXIMITY QUERY ENGINE                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │  GEO AXIS    │  │  TIME AXIS   │  │ CONCEPT AXIS │           │
│  │              │  │              │  │              │           │
│  │ geo_distance │  │ date_range   │  │ knn          │           │
│  │ geo_bbox     │  │ histogram    │  │ terms        │           │
│  │ geo_polygon  │  │ interval     │  │ cosine_sim   │           │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘           │
│         │                 │                 │                    │
│         └─────────────────┼─────────────────┘                    │
│                           │                                      │
│                    ┌──────▼──────┐                               │
│                    │  COMPOUND   │                               │
│                    │  bool query │                               │
│                    └──────┬──────┘                               │
│                           │                                      │
│                    ┌──────▼──────┐                               │
│                    │  RESULTS    │                               │
│                    │  + scores   │                               │
│                    └─────────────┘                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 9. FILES & MODULES

| Component | Location |
|-----------|----------|
| Golden Lists (265 embeddings) | `CYMONIDES/golden_lists/golden_lists_with_embeddings.json` |
| UniversalExtractor | `CYMONIDES/extraction/universal_extractor.py` |
| Temporal Hierarchy | `CYMONIDES/extraction/temporal_hierarchy.py` |
| Dimension Registry | `CYMONIDES/dimension_registry.json` |
| Geocoding Scripts | `BACKEND/modules/ATLAS/geocode_*.py` (TBD) |
| This Spec | `CYMONIDES/PROXIMITY_SYSTEM.md` |
