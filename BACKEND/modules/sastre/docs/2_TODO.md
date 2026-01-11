# SASTRE - TODO

- [x] Emit centricity rotations for all modes (visible grid rotation)
  - Priority: High
  - Added: 2025-12-22 by GPT-5
  - Notes: Always emit centricity events; add a short delay when streaming to make rotation visible.

- [x] Broadcast narrative note updates from /api/graph/notes updates
  - Priority: High
  - Added: 2025-12-22 by GPT-5
  - Notes: Ensures SASTRE document writes stream into the editor via graph websocket.

- [x] Resolve event gap variables using template role/edge mappings
  - Priority: Medium
  - Added: 2025-12-22 by GPT-5
  - Notes: GapExecutor now parses both gap id formats and resolves role variables against template edge_types.

- [x] Include projectId when loading enrichment buttons
  - Priority: Medium
  - Added: 2025-12-31 by GPT-5
  - Notes: Pass projectId through tRPC enrichment button fetch so Cymonides actions target the active project.

- [x] Add IO event schema validator script
  - Priority: Low
  - Added: 2025-12-22 by GPT-5
  - Notes: Validates anchors and edge_types in event templates against node schemas and event_edges.

- [x] Normalize event template anchors + event edge naming in IO matrix schemas
  - Priority: Medium
  - Added: 2025-12-22 by GPT-5
  - Notes: Removed invalid JSON comment; aligned event_edges with event_templates and set anchors to existing node classes.

- [x] Fix narrative note persistence to use /api/graph/nodes
  - Priority: High
  - Added: 2025-12-21 by GPT-5
  - Notes: Persist-entities expects string values; narrative docs should be note nodes with metadata.

- [x] Repair hydrator mapping + multi-mode hydration
  - Priority: High
  - Added: 2025-12-21 by GPT-5
  - Notes: Align Query/Source mapping with core dataclasses and hydrate subject/location/nexus modes.

- [ ] Verify Narrative Topology persistence (Goal/Track/Path) in Cymonides
  - Priority: Medium
  - Added: 2025-12-21 by GPT-5
  - Notes: Confirm nodes/edges appear in grid and link to queries/sources/entities as expected.

- [ ] Validate Query Lab outputs against IO routes (live)
  - Priority: Medium
  - Added: 2025-12-21 by GPT-5
  - Notes: Spot-check IO route execution vs broad search fallback for fused queries.

- [ ] Link Path → Query/Source/Entity on IO execution results
  - Priority: Low
  - Added: 2025-12-21 by GPT-5
  - Notes: Path linkage now attempts via recent query lookup; add robust linking when IO returns node IDs.

- [ ] Validate cognitive state mapping against live grid rotation output
  - Priority: Medium
  - Added: 2025-12-20 by GPT-5
  - Notes: Verify entity core/shell, source jurisdiction, and embedded edge parsing in CognitiveEngine state.

- [ ] Align SectionState usage across contracts vs document/sections
  - Priority: Low
  - Added: 2025-12-20 by GPT-5
  - Notes: Decide whether to add PARKED to contracts or map watcher status into document snapshots.

- [ ] Add smoke checks for sufficiency snapshot inputs (binary stars, surprising AND)
  - Priority: Low
  - Added: 2025-12-20 by GPT-5
  - Notes: Ensure document parsing captures disambiguation + surprising connections consistently.

- [ ] Verify enrichment endpoints used by dynamic buttons persist results to Cymonides
  - Priority: Medium
  - Added: 2025-12-20 by GPT-5
  - Notes: If not, route through matrix/operator execution or add persistence adapters.

- [ ] Tune profile key thresholds per entity type (company/person)
  - Priority: Low
  - Added: 2025-12-20 by GPT-5
  - Notes: Adjust keys for deterministic routing after reviewing schema requirements.
