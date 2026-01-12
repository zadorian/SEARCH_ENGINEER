# PACMAN

Universal extraction engine for documents - extracts themes, phenomena, temporal signals, spatial data, and red flags using 265-category semantic embeddings.

## Architecture

```
                              PACMAN
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  ┌──────────────┐                                               │
│  │   Document   │                                               │
│  │    (text)    │                                               │
│  └──────┬───────┘                                               │
│         │                                                       │
│         ▼                                                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              UniversalExtractor                          │   │
│  │  ┌─────────────────────────────────────────────────────┐ │   │
│  │  │  multilingual-e5-base (768 dims, 100+ languages)    │ │   │
│  │  └─────────────────────────────────────────────────────┘ │   │
│  │                         │                                │   │
│  │         ┌───────────────┼───────────────┐                │   │
│  │         ▼               ▼               ▼                │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐          │   │
│  │  │ Conceptual │  │  Temporal  │  │  Spatial   │          │   │
│  │  │ Extraction │  │ Extraction │  │ Extraction │          │   │
│  │  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘          │   │
│  │        │               │               │                 │   │
│  │        ▼               ▼               ▼                 │   │
│  │  ┌──────────┐    ┌──────────┐    ┌──────────┐            │   │
│  │  │• themes  │    │• pub_date│    │• locations│           │   │
│  │  │• phenom  │    │• years   │    │• jurisd   │           │   │
│  │  │• red_flag│    │• decade  │    │           │           │   │
│  │  │• methods │    │• era     │    │           │           │   │
│  │  └──────────┘    └──────────┘    └──────────┘            │   │
│  └──────────────────────────────────────────────────────────┘   │
│                         │                                       │
│                         ▼                                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   TierClassifier                         │   │
│  │  ┌─────────┐    ┌─────────┐    ┌─────────┐               │   │
│  │  │ TIER 1  │    │ TIER 2  │    │ TIER 3  │               │   │
│  │  │  Full   │    │ Extract │    │  Skip   │               │   │
│  │  │embedding│    │  only   │    │         │               │   │
│  │  └─────────┘    └─────────┘    └─────────┘               │   │
│  └──────────────────────────────────────────────────────────┘   │
│                         │                                       │
│                         ▼                                       │
│               ┌─────────────────┐                               │
│               │ ExtractionResult│                               │
│               └─────────────────┘                               │
└─────────────────────────────────────────────────────────────────┘
```

## 265 Categories

| Type | Count | Examples |
|------|-------|----------|
| Themes | 51 | ownership_analysis, asset_trace, sanctions |
| Phenomena | 60 | due_diligence, fraud_investigation, merger |
| Red Flags | 11 | money_laundering, pep, offshore |
| Methodologies | 143 | corporate_registry_search, humint |

## Public API

```python
from PACMAN import UniversalExtractor, extract_all, ExtractionResult

# Full extraction
extractor = UniversalExtractor()
result: ExtractionResult = extractor.extract(text, meta_date="2024-01-01")

# Quick extraction
result_dict = extract_all(text)
```

### UniversalExtractor

| Method | Description |
|--------|-------------|
| `extract(text, meta_date, entities)` | Full extraction, returns ExtractionResult |
| `extract_concepts(text, top_k)` | Extract themes/phenomena only |
| `extract_temporal(text, meta_date)` | Extract temporal signals |
| `extract_spatial(text, entities)` | Extract location signals |
| `extract_red_flags(text, entities)` | Detect OFAC/sanctions matches |

### ExtractionResult

| Field | Type | Description |
|-------|------|-------------|
| `themes` | List[Dict] | Matched industry/investigation themes |
| `phenomena` | List[Dict] | Matched events/report genres |
| `red_flag_themes` | List[Dict] | Risk category matches |
| `methodologies` | List[Dict] | Research approach matches |
| `published_date` | str | ISO date when published |
| `content_years` | List[int] | Years discussed in content |
| `temporal_focus` | str | "historical", "current", "future" |
| `locations` | List[Dict] | Extracted locations |
| `primary_jurisdiction` | str | Main country code |
| `red_flag_entities` | List[Dict] | OFAC/sanctions matches |

### TierClassifier

| Function | Description |
|----------|-------------|
| `classify(doc)` | Returns Tier (1/2/3) for document |
| `build_document(row, doc_id)` | Build indexed document |

## Usage

```python
from PACMAN import UniversalExtractor

extractor = UniversalExtractor()

text = """
OpenAI announced a major funding round of $6.6 billion in October 2024,
valuing the AI company at $157 billion. The San Francisco-based startup
is developing advanced artificial intelligence systems.
"""

result = extractor.extract(text)

print(result.themes)        # [{"id": "ai_technology", "canonical": "AI Technology", "score": 0.82}]
print(result.phenomena)     # [{"id": "funding_round", "canonical": "Funding Round", "score": 0.78}]
print(result.content_years) # [2024]
print(result.primary_jurisdiction)  # "US"
```

## Dependencies

- `sentence-transformers` - multilingual-e5-base model
- `numpy` - vector operations
- Golden lists from `input_output/matrix/golden_lists_with_embeddings.json`

## Files

| File | Purpose |
|------|---------|
| `__init__.py` | Public API exports |
| `universal_extractor.py` | Main extraction engine |
| `temporal_hierarchy.py` | Temporal signal derivation |
| `tier_classifier.py` | Document tier classification |
