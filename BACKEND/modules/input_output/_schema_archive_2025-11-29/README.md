# Archived Schema Files (November 29, 2025)

These files have been deprecated and archived. **DO NOT USE THEM.**

## Authoritative Source

**All edge/relationship schemas are now consolidated in:**
```
input_output/ontology/relationships.json
```

This file is THE single source of truth for:
- All 40+ edge/relationship types
- Source and target type validation
- Required/optional metadata fields
- FTM (FollowTheMoney) schema mappings
- Divergence documentation

## Why These Files Were Archived

### `master_entity_edges_matrix.json` (282KB)
- **Original Purpose:** Node templates with embedded edge type data
- **Problem:** Mixed concerns (node templates + edge schemas in one file)
- **Status:** Edge schemas extracted to `relationships.json`; node template functionality moved elsewhere

### `edges.json` (20KB, from `matrix/schema/`)
- **Original Purpose:** Subset of edge definitions
- **Problem:** Outdated and incomplete (only 1 edge type vs 40+ in consolidated file)
- **Status:** All content superseded by `relationships.json`

## Migration Notes

Code that previously referenced:
- `master_entity_edges_matrix.json` → Now use `ontology/relationships.json`
- `matrix/schema/edges.json` → Now use `ontology/relationships.json`

The `edgeRelationshipService.ts` has been updated to load from the new location.

## FTM Interoperability

FTM mappings are now embedded inline in `relationships.json`:
- `ftm_relation`: Maps to FTM schema type (e.g., "Directorship", "Ownership")
- `ftm_divergence`: Documents rationale when Drill Search intentionally differs

Reference copy of detailed FTM property mappings: `ontology/ftm_schema_mapping.json`

## Rollback

If needed, these files can be restored from this archive directory.
Git history also preserves all previous versions.
