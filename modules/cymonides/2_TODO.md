# CYMONIDES - TODO

> **Auto-updated by AI agents.** See `AGENT.md` for protocols.

---

## High Priority

- [ ] Index full Raidforums archive (497GB on external drive)
  - Priority: High
  - Added: 2025-12-04 by Claude
  - Notes: Currently only 197K of millions of records indexed

- [ ] Create `red_flags` index for storing detected anomalies
  - Priority: High
  - Added: 2025-12-04 by Claude
  - Notes: Planned in `use-cases/red-flags/README.md`

- [ ] Expand country indexes beyond KZ/RU
  - Priority: High
  - Added: 2025-12-04 by Claude
  - Notes: Planned: UZ, KG, TM, UA, AZ

## Medium Priority

- [ ] Backfill C-2 subject signals (themes/phenomena) into `subject`
  - Priority: Medium
  - Added: 2025-12-31 by GPT-5
  - Notes: Run `BACKEND/modules/concepts/enrich_concepts.py` to populate the new subject field.

- [ ] Backfill C-2 sector/topic signals for existing corpus
  - Priority: Medium
  - Added: 2025-12-31 by GPT-5
  - Notes: Use aggregated sector phrase lists + ownership topic hints to tag historical docs.

- [ ] Backfill C-2 dense embeddings via Elasticsearch inference
  - Priority: Medium
  - Added: 2025-12-31 by GPT-5
  - Notes: Requires ES model deployment + default pipeline before reindex/update-by-query.

- [ ] Backfill C-2 content type + genre tags from report templates/genres
  - Priority: Medium
  - Added: 2025-12-31 by GPT-5
  - Notes: Populate `content_type_tags` + `content_genre_tags` for existing docs.

- [ ] Build ES-native concept embeddings from report terminology (ownership/asset trace/due diligence)
  - Priority: Medium
  - Added: 2025-12-31 by GPT-5
  - Notes: Create a compact concept index for vector filtering + re-ranking.

- [ ] Implement ML-based anomaly detection on entity graphs
  - Priority: Medium
  - Added: 2025-12-04 by Claude
  - Notes: See `use-cases/red-flags/` future enhancements

- [ ] Add automated contradiction finder (Disambiguator module)
  - Priority: Medium
  - Added: 2025-12-04 by Claude
  - Notes: Cross-document contradiction detection

- [ ] Implement temporal analysis of entity changes
  - Priority: Medium
  - Added: 2025-12-04 by Claude
  - Notes: Timeline-based entity tracking

## Low Priority

- [ ] Network visualization for red flag clusters
  - Priority: Low
  - Added: 2025-12-04 by Claude

- [ ] Composite risk scoring system per entity
  - Priority: Low
  - Added: 2025-12-04 by Claude

---

## Completed

- [x] Relocate embedding assets from IO matrix into CYMONIDES
  - Completed: 2026-01-02 by Codex
  - Notes: Moved industry matcher/embeddings + strategic embeddings and updated references.

- [x] Approve canonical C-1 node index (`metadata/c-1/ontology/nodes.json`) and alias mappings (domain/webdomain, sanction, litigation, etc.)
  - Completed: 2025-12-31 by Codex
  - Notes: Canonical classes/subkinds finalized; query + file aliases added.

- [x] Align matrix schema + relationships to canonical node index
  - Completed: 2025-12-31 by Codex
  - Notes: Synced `input_output/ontology/relationships.json` + C-1 matrix schema nodes.json to canonical taxonomy.

- [x] Add social media module executors to IO integration registry
  - Completed: 2025-12-29 by GPT-5
  - Notes: Registered `social_media.py` for person + username + company + social prefix routing and updated matrix modules list.

- [x] Persist outlink notes in C-2 for link analysis
  - Completed: 2025-12-23 by GPT-5
  - Notes: Added `outlink_notes` mapping + dedup merge and CC-first extraction wiring.

- [x] Add C-2 content type/genre signals and search filters
  - Completed: 2025-12-31 by GPT-5
  - Notes: Uses report section templates + genre indicators for `content_type_tags`/`content_genre_tags` and exposes tag filters in the C-2 search API.

- [x] Propagate C-2 content signals into C-1 grid filters + embedding input
  - Completed: 2025-12-31 by GPT-5
  - Notes: Syncs content topics/types/genres/sectors to source node properties, adds grid filters, and enriches ES embedding input.

- [x] Store ET3 coordinate nodes as LOCATION (not SOURCE)
  - Completed: 2025-12-31 by GPT-5
  - Notes: Coordinate nodes now persist with `className: "location"` and UI filters treat location/source equivalently.

- [x] Sync Cymonides standalone enrichment buttons with link actions + project context
  - Completed: 2025-12-31 by GPT-5
  - Notes: Adds action/url handling and optional projectId pass-through for enrichment button fetches.

- [x] Document all indices in 1_CONCEPT.md
  - Completed: 2025-12-04 by Claude
  - Notes: Full index registry with cross-reference matrix

- [x] Document use-cases folder structure
  - Completed: 2025-12-04 by Claude
  - Notes: Linked to detailed README files in each use-case folder

- [x] Remove placeholder Exa Websets UI component
  - Completed: 2025-12-14 by GPT-5.2
  - Notes: Deleted unused `cymonides-standalone` `ExaWebsetsInterface.tsx`; Source Pools UI is provided by the main app’s `client/src/components/location/SourcePoolsPanel.tsx`.
