# CYMONIDES - LOGS

> **Auto-updated by AI agents.** See `AGENT.md` for protocols.

---

## 2026-01-02 - Claude Opus 4.5 - Entity Consolidation Scripts

**Duration:** ~1 hour
**Context:** Creating consolidation scripts for unified canonical indices per the CYMONIDES architecture.

**Completed:**
- Created `ingest/consolidate_search_nodes.py` - Entity consolidation from multiple sources
  - Sources: openownership (36.4M), linkedin_unified, wdc-organization-entities (9.6M), wdc-person-entities (6.8M), wdc-localbusiness-entities (478K)
  - Target: search_nodes index
  - Features: Deterministic IDs (hash-based), 4-field contract (subject, concepts, dimension_keys, doc_type), checkpoint/resume, source transformers
  - CLI: `--source`, `--resume`, `--verify`, `--reset`

- Created `ingest/consolidate_comms.py` - Communications/email consolidation
  - Sources: breach_records (189M), kazaword_emails (92K), emails_unified (5K)
  - Target: comms_unified index
  - Features: Email validation, security tier classification (hash types), email domain extraction
  - Handles kazaword array explosion (all_emails → individual records)

- Created `ingest/consolidate_uk_property.py` - UK Land Registry consolidation
  - Sources: uk_ccod (4.3M), uk_ocod (92K), uk_addresses (4.3M), uk_leases (7.7M)
  - Target: uk_property_unified index
  - Features: Postcode area extraction, region normalization, proprietor name combination
  - Handles multiple proprietor fields (_1, _2)

**Key Findings:**
- Existing `search_nodes` index (1.95M docs) contains UI-generated narrative nodes, not entity data
- Script will add entity records alongside existing docs (no ID conflicts due to deterministic hashing)
- May need to decide on index naming strategy (keep coexistence vs separate indices)

**All Scripts Ready:**
```bash
# Run each consolidation (in order)
python ingest/consolidate_search_nodes.py --source oo    # Start with openownership
python ingest/consolidate_comms.py --source breach       # Start with breach_records
python ingest/consolidate_uk_property.py --source ccod   # Start with uk_ccod
```

**Blockers:** None (all scripts ready for execution)

**Next Steps:**
- Run consolidation scripts (can use --resume if interrupted)
- Geocode remaining indices (openownership 36.4M, uk_ccod 4.3M)

---

## 2026-01-02 - Codex - Matrix Asset Relocation

**Duration:** ~0.4 hours
**Tasks:** Move embedding/indexing assets out of `input_output/matrix` into CYMONIDES and fix references.
**Completed:**
- Moved `industry_matcher.py`, `industry_embeddings.json`, and `strategic_embeddings.json` into `BACKEND/modules/CYMONIDES/`.
- Updated IO CLI imports and embedding loader paths.
- Updated documentation paths in `UNIFIED_SEARCH_ARCHITECTURE_PLAN.md` and `IDEAS_TRACKER.md`.
**Blockers:** None
**Next:** Validate any downstream scripts that consume the industry embeddings JSON.

## 2026-01-02 - Codex - Atlas Backfill Fix

**Duration:** ~0.1 hours
**Tasks:** Restore missing helpers in `backfill_atlas_dimensions.py`.
**Completed:**
- Added `datetime` import plus `normalize_key` and `get_authority_tier` helpers to unblock backfill.
**Blockers:** None
**Next:** None

## 2025-12-31 - GPT-5 - Unified Subject/Location Signals

**Duration:** ~0.6 hours
**Context:** Centralize subject/temporal/spatial extraction and align Chronos with subject signals.

**Completed:**
- Added shared subject definitions + signal hub utilities in `categorizer-filterer`.
- Refactored temporal/geospatial/concept enrichers to use the unified signal hub.
- Moved concept outputs into `subject` signals (themes/phenomena) for C-2 docs.
- Updated Chronos to read subject phenomena + temporal fallbacks and stamp event dates.
- Extended C-2 mappings/types to include `subject` signals and `phenomena` arrays.

**Blockers:** None

**Next Steps:**
- Backfill C-2 subject signals for existing corpus using `enrich_concepts.py`.

---

## 2025-12-31 - Codex - Canonical Node Index

**Duration:** ~0.7 hours
**Context:** Establish a canonical CYMONIDES-1 node index for approval before schema wiring.

**Completed:**
- Added `BACKEND/modules/CYMONIDES/metadata/c-1/ontology/nodes.json` with canonical classes (NARRATIVE/SUBJECT/NEXUS/LOCATION) and subkinds.
- Aligned NEXUS/LOCATION subkinds to grid filter taxonomy (query primary/scope/mode, format/filetypes, geo/temporal).
- Added `note` subtype `template` to narrative nodes.
- Added query + file aliases to the canonical node index (query nodes preserved; document/source/dataset map to file).
- Synced `input_output/ontology/relationships.json` + C-1 relationships to canonical types (phenomenon/theme, location file/domain/address, query preserved).
- Rebuilt C-1 matrix schema nodes.json (and docs copy) to canonical types with LOCATION geo/virtual/temporal nodes and NEXUS query fields.
- Added CYMONIDES TODOs to approve the node index and sync matrix/relationships.

**Blockers:** Approval needed on node list + alias mappings.

**Next Steps:**
- Review/approve node list and alias mappings.
- Sync `input_output/ontology/relationships.json` and Matrix schema nodes to the canonical list.

---

## 2025-12-31 - GPT-5 - Enrichment Button Parity

**Duration:** ~0.2 hours
**Context:** Keep Cymonides standalone enrichment buttons aligned with core UI behavior.

**Completed:**
- Added link-action handling and projectId pass-through in the Cymonides standalone enrichment button component.

**Blockers:** None

**Next Steps:**
- Confirm Cymonides standalone profile buttons open registry links and persist to the active project when applicable.

---

## 2025-12-31 - GPT-5 - Coordinate Nodes as Location

**Duration:** ~0.6 hours
**Context:** Ensure ET3 coordinate nodes are stored as LOCATION nodes (not SOURCE nodes) and keep UI behavior consistent.

**Completed:**
- Switched ET3 coordinate node className to `location` in schema + CoordinateService.
- Treated `location` as source-equivalent for capsule styling and filter counts.
- Allowed selection/action helpers to treat `location` and `source` as aliases where needed.

**Blockers:** None

**Next Steps:**
- Decide whether to migrate legacy `class: source` nodes to `class: location` in C-1 (optional).

---

## 2025-12-31 - GPT-5 - C-2 Content Signals to Grid + Embedding Input

**Duration:** ~1.2 hours
**Context:** Push C-2 content signal tags into C-1 nodes, wire grid filters, and enrich ES-native embedding input.

**Completed:**
- Added `embedding_input` field + pipeline validation for C-2 Elastic inference embeddings.
- Built embedding input that mixes title/summary/keywords/content with content/sector signals.
- Synced C-2 content/sector tags into C-1 source node properties during ingest.
- Added grid filters and UI support for content topics/types/genres/sectors (cross-class aware).
- Extended graph attribute filtering to accept content signal keys.

**Blockers:** None

**Next Steps:**
- Backfill C-2 signals into existing C-1 source nodes if needed.
- Reindex/re-embed C-2 if switching pipeline input to `embedding_input`.

---

## 2025-12-31 - GPT-5 - C-2 Content Type + Genre Signals

**Duration:** ~1 hour
**Context:** Leverage report library terminology + section templates to tag C-2 docs with content types and genres.

**Completed:**
- Added content type/genre signal detection from section templates + report genre indicators.
- Stored `content_type_tags`/`content_genre_tags` + scores in C-2 documents at ingest/dedup.
- Exposed C-2 search filters for topics, content types, genres, sectors, and source constraints.
- Enabled narrative template service to fall back to archived section template catalog.

**Blockers:** None

**Next Steps:**
- Backfill content type/genre tags for existing C-2 corpus.

---

## 2025-12-31 - GPT-5 - C-2 Sector Signals + Elastic Embeddings

**Duration:** ~1.2 hours
**Context:** Integrate sector/topic phrase lists into C-2 indexing and enable Elastic-native embeddings.

**Completed:**
- Added C-2 sector/topic signal detection from aggregated sector phrases.
- Wired signal metadata (sectors, red flags, structures, topics, scores) into C-2 ingestion + dedup merge.
- Added Elastic inference pipeline setup and C-2 mapping updates for dense vectors + signal fields.
- Added semantic search helper using Elasticsearch query-time embeddings.

**Blockers:** None

**Next Steps:**
- Deploy ES text-embedding model and reindex/backfill C-2 embeddings + signals.

---

## 2025-12-29 - GPT-5 - Social Media Operator Wiring

**Duration:** ~0.4 hours
**Context:** Ensure IO CLI can route social media operators through the social_media module.

**Completed:**
- Added `social_media` module executors for direct social prefix routing.
- Expanded social media module inputs/outputs metadata for IO registry.
- Updated IO CLI to recognize social platform prefixes and route to social media search.

**Blockers:** None

**Next Steps:**
- Validate `io_cli.py "fb: <query>"` and `io_cli.py "linkedin: <query>"` execution paths.

---

## 2025-12-29 - GPT-5 - IO Integration Update

**Duration:** ~0.3 hours
**Context:** Register BRUTE social media search in IO routing for Cymonides-driven investigations.

**Completed:**
- Added social media module executors for person + username + company inputs in IO_INTEGRATION.json.
- Registered `social_media.py` in the IO modules registry.

**Blockers:** None

**Next Steps:**
- Confirm social media module outputs align with `person_social_profiles` (code 188) expectations in downstream UIs.

---

## 2025-12-23 - GPT-5 - Link Indexing Sync

**Duration:** ~1 hour
**Context:** Ensure link operators surface page-level URLs + anchors and persist outlink notes in C-2.

**Completed:**
- Added `outlinks` + `outlink_notes` mapping support for C-2 documents and dedup merge logic.
- Plumbed CC-first outlink extraction to return anchor notes.
- Wired Linklater indexing to persist outlink notes into C-2.
- Exposed rich backlinks endpoint for page-level backlinks with anchor text.

**Key Findings:**
- C-2 now stores anchor-aware outlinks for link analysis.
- `bl?/ol?` aggregation can pull page-level links from C-2 and CC graph edges.

**Blockers:** None

**Next Steps:**
- Verify live API responses include `outlink_notes` where available.

---

## 2025-12-04 - Claude (Opus 4.5) - Documentation Session

**Duration:** Part of larger session
**Context:** Consolidating module documentation across project

**Completed:**
- Created `1_CONCEPT.md` with full module documentation
- Created `2_TODO.md` with outstanding tasks from use-cases analysis
- Created `3_LOGS.md` (this file)
- Analyzed all indices: ~537M documents, ~29.5GB total
- Documented all use-cases: company-profiles, domains-list, red-flags, data-breaches, country-indexes

**Key Findings:**
- 13 Elasticsearch indices documented
- CC web graph: 536M+ documents (vertices + edges)
- Breach data: 197K indexed, 497GB unindexed on external drive
- Use-cases provide excellent cross-index workflow documentation

**Index Summary:**
| Category | Docs | Size |
|----------|------|------|
| C-1 Entity Graphs | ~1,730 | 23MB |
| C-2 Text Corpus | 532,630 | 5.1GB |
| CC Web Graph | 536M+ | 24GB |
| Breach Data | 197K | 90MB |
| Country Data | 92K | 225MB |

**Next Steps:**
- See `2_TODO.md` for outstanding tasks
- Priority: Index Raidforums archive

---

## 2025-12-14 - GPT-5.2 - UI Cleanup (Source Pools)

**Context:** Remove dead/placeholder UI that duplicated Source Pools/Websets concepts.

**Completed:**
- Deleted unused placeholder `cymonides-standalone/src/components/ExaWebsetsInterface.tsx`.

**Notes:**
- The operable Source Pools UI lives in the main client (`client/src/components/location/SourcePoolsPanel.tsx`) and is backed by `trpc.sourcePools.*`.

---

## Template for Future Entries

```markdown
## [DATE] - [AGENT] - [SESSION TYPE]
**Duration:** X hours
**Context:** Why this work was done

**Completed:**
- Item 1
- Item 2

**Key Findings:**
- Finding 1
- Finding 2

**Blockers:** Any issues encountered

**Next Steps:** What should happen next
```
## 2026-01-02 - GPT-5 - Consolidation Script Alignment

**Context:** Close dimension-key gaps and promote field-grouped properties for consolidated indices.

**Completed:**
- Added ownership_strength/credibility_tier/security_tier derivations in `scripts/consolidate_entities.py`.
- Promoted `incorporation_date` to top-level in `scripts/consolidate_entities.py` and updated index mapping.
- Promoted `price_paid` to top-level in `scripts/consolidate_uk_property.py`, added year derivation, and updated mapping.
- Aligned security-tier derivation rules in `scripts/consolidate_entities.py` and `scripts/consolidate_comms.py`.

**Notes:**
- `price_paid` is parsed to numeric when possible; raw values remain in metadata.

---
