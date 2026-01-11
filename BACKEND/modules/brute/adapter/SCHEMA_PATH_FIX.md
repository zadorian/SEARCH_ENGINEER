# CyMonides Schema Path Fix ✅

## Problem

CyMonides was pointing to a **non-existent directory**:

```python
# BROKEN (old):
SCHEMA_DIR = Path(...) / "input_output2" / "matrix"
EDGE_TYPES_PATH = SCHEMA_DIR / "edge_types.json"
FTM_SCHEMA_PATH = SCHEMA_DIR / "ftm_schema_mapping.json"
```

This directory **doesn't exist**, so schemas weren't loading!

## Solution

Fixed paths to point to the **actual** schema location:

```python
# FIXED (new):
SCHEMA_DIR = Path(...) / "input_output" / "matrix"
EDGE_TYPES_PATH = SCHEMA_DIR / "edges" / "edge_types.json"
FTM_SCHEMA_PATH = SCHEMA_DIR / "edges" / "ftm_schema_mapping.json"
```

## Files Updated

1. `/server/services/cymonides/__init__.py`
2. `/server/services/cymonides/drill_search_adapter.py`

## Results

**Before:**

```
⚠️  Failed to load edge_types.json: [Errno 2] No such file or directory
⚠️  Failed to load ftm_schema_mapping.json: [Errno 2] No such file or directory
Edge types: 0
FTM mappings: 0
```

**After:**

```
✅ Loaded 58 edge types
✅ Loaded FTM schema with 10 entity types
```

## Actual Schema Location

```
/input_output/matrix/
├── edges/
│   ├── edge_types.json (1941 lines, 58 edge types)
│   ├── ftm_schema_mapping.json (237 lines, 10 FTM mappings)
│   └── graph_schema.json (2725 lines)
├── entity_schema_templates/
│   ├── entity_class_type_matrix.json
│   ├── entity_template.json
│   ├── source_template.json
│   ├── query_template.json
│   ├── narrative_template.json
│   └── node_templates.json (249KB)
├── sources.json (10.9MB)
├── rules.json (1.3MB)
└── ... (other schema files)
```

## Edge Type Coverage

**Loaded from `/input_output/matrix/edges/edge_types.json`:**

- **Company edges** (19 types): officer_of, beneficial_owner_of, subsidiary_of, owns, employs, has_address, has_phone, has_email, has_website, has_linkedin, registered_in, headquartered_at, flagged_with, involved_in_litigation, mentioned_in, partner_of

- **Person edges** (18 types): has_phone, has_email, has_address, employed_by, director_of, owns, married_to, child_of, sibling_of, resides_at, has_linkedin, has_twitter, mentioned_in, educated_at, flagged_with

- **Document edges** (2 types): filed_with, associated_with

- **Entity edges** (2 types): related_to, documented_by

**Total: 58 relationship types** (some overlap between categories)

## Next Steps (Optional)

The schema directory also contains:

1. **Entity templates** (`entity_schema_templates/`) - Structural templates for node creation
2. **Class/type matrix** (`entity_class_type_matrix.json`) - Routing logic for discovery vs enrichment
3. **Sources catalog** (`sources.json`) - 10MB of registry/API metadata
4. **Validation rules** (`rules.json`) - 1.3MB of routing rules

These could be integrated for:

- Template-based node creation
- Routing logic (discovery vs enrichment)
- Source provenance tracking
- Advanced validation

But the **critical fix** is done - schemas are now loading correctly!
