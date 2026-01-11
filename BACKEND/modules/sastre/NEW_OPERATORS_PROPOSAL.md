# SASTRE New Operators Proposal
**Generated:** 2026-01-01
**Status:** PROPOSAL - Pending Implementation

---

## Executive Summary

This document proposes **78 new operators** across **12 categories** to provide comprehensive control over the SASTRE investigation system. These operators follow existing conventions and fill critical gaps identified through systematic codebase analysis.

### Design Principles

1. **Prefix = Type, Suffix = Action**
2. **`!` suffix = scope contraction, `!` prefix = scope expansion**
3. **`?` suffix = extract/query, `?` prefix = deduplicated/unique**
4. **`+` = add/enable, `-` = remove/disable**
5. **`#` = reference (tag, node, workstream)**
6. **`:` separates operator from target**
7. **`=>` chains operations**

---

## 1. WATCHER OPERATORS (Priority: HIGH)

Watchers monitor document sections and route findings back to narratives.

### 1.1 Basic Watcher Creation

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Create Watcher | `+#w:{header}` | Create basic watcher from header text | `WatcherBridge.create()` |
| Create Watcher (alias) | `+#watcher:{header}` | Long form alias | `WatcherBridge.create()` |
| Delete Watcher | `-#w:{watcher_id}` | Delete watcher by ID | `WatcherBridge.delete()` |
| Toggle Watcher | `~#w:{watcher_id}` | Toggle active/paused | `WatcherBridge.toggle()` |
| Pause Watcher | `=#w:{watcher_id}` | Pause watcher | `WatcherBridge.update_status('paused')` |
| Resume Watcher | `!#w:{watcher_id}` | Resume watcher | `WatcherBridge.update_status('active')` |

### 1.2 ET3 Watchers (Event/Topic/Entity)

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Event Watcher | `+#w:evt:{event_type}` | Watch for events (ipo, lawsuit, breach) | `WatcherBridge.create_event_watcher()` |
| Topic Watcher | `+#w:top:{topic}` | Watch for topics (sanctions, pep, compliance) | `WatcherBridge.create_topic_watcher()` |
| Entity Watcher | `+#w:ent:{entity_type}` | Watch for entity types (person, company) | `WatcherBridge.create_entity_watcher()` |

### 1.3 Watcher Management

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| List Watchers | `#w?` | List all active watchers | `WatcherBridge.list_active()` |
| List All | `#w??` | List all watchers (any status) | `WatcherBridge.list_all()` |
| Get Watcher | `#w:{id}?` | Get watcher details | `WatcherBridge.get()` |
| Watcher Findings | `#w:{id}!` | Get watcher findings | `watcher.metadata.findings` |
| Add Context | `#w:{id}+:{node_id}` | Add context node to watcher | `WatcherBridge.add_context()` |
| Remove Context | `#w:{id}-:{node_id}` | Remove context node | `WatcherBridge.remove_context()` |

### 1.4 Watcher Filters

| Operator | Syntax | Description | Example |
|----------|--------|-------------|---------|
| Jurisdiction | `+#w:{header}##jurisdiction:UK` | Filter by jurisdiction | `+#w:Officers##jurisdiction:UK` |
| Entity Filter | `+#w:{header}##entities:{ids}` | Filter by entities | `+#w:News##entities:ent_123,ent_456` |
| Time Filter | `+#w:{header}##since:2024-01-01` | Temporal filter | `+#w:IPO##since:2024-01-01` |

---

## 2. NODE/GRAPH OPERATORS (Priority: HIGH)

Critical gaps in node manipulation capabilities.

### 2.1 Node Deletion (MISSING - CRITICAL)

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Delete Node | `rm!:{node_id}` | Delete single node + cascade edges | `graph.delete_entity()` |
| Delete Node (hash) | `rm!:#node_label` | Delete by label reference | `graph.delete_entity()` |
| Bulk Delete | `rm!:(#a OR #b)` | Delete multiple nodes | `graph.delete_entities()` |
| Delete Confirmed | `rm!!:{node_id}` | Force delete (no confirmation) | `graph.delete_entity(force=True)` |

### 2.2 Node Merge/Split

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Merge Nodes | `merge!:{a}:{b}` | Merge b into a | `/api/graph/nodes/merge` |
| Bulk Merge | `merge!:(#tag) into:{keeper}` | Merge multiple into keeper | `graph.bulk_merge()` |
| Split Node | `split!:{node_id}` | Split entity into duplicates | `graph.split_entity()` |
| Clone Node | `clone!:{node_id}` | Duplicate node for hypothesis | `graph.clone_entity()` |

### 2.3 Edge Operations

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Link Nodes | `link!:{a}:{b}:{type}` | Create edge between nodes | `graph.add_edge()` |
| Unlink Nodes | `unlink!:{a}:{b}` | Remove edge between nodes | `graph.remove_edge()` |
| Unlink Type | `unlink!:{a}:{b}:{type}` | Remove specific edge type | `graph.remove_edge(type=)` |
| Retype Edge | `retype!:{a}:{b}:{old}:{new}` | Change edge type | `graph.retype_edge()` |

### 2.4 Node Properties

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Rename Node | `rename!:{node_id}:{new_label}` | Change node label | `graph.update_entity()` |
| Retype Node | `retype!:{node_id}:{new_type}` | Change entity type | `graph.update_entity()` |
| Set Metadata | `meta!:{node_id}:{key}={value}` | Update metadata field | `update_node_metadata()` |

### 2.5 Graph Traversal (MISSING - CRITICAL)

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Find Path | `path!:{a}:{b}` | Find shortest path A→B | `graph.find_path()` |
| Find Path (depth) | `path!:{a}:{b}:depth={n}` | Path with max depth | `graph.find_path(max_depth=n)` |
| Traverse DFS | `traverse!:{seed}:dfs:depth={n}` | Depth-first traversal | `graph.traverse_dfs()` |
| Traverse BFS | `traverse!:{seed}:bfs:depth={n}` | Breadth-first traversal | `graph.traverse_bfs()` |
| Subgraph | `subgraph!:(#tag)` | Extract subgraph by criteria | `graph.extract_subgraph()` |

### 2.6 Graph Metrics (MISSING)

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Node Centrality | `centrality!:{node_id}` | Calculate node importance | `graph.centrality()` |
| Graph Metrics | `metrics!` | Get graph-wide metrics | `graph.metrics()` |
| Dedup Scan | `dedup!:(#tag):threshold={n}` | Proactive collision scan | `graph.find_collisions()` |
| Connected | `connected?:{node_id}` | Get connected component | `graph.connected_component()` |

---

## 3. WORKFLOW/STATE OPERATORS (Priority: MEDIUM)

Control investigation lifecycle, phases, and checkpoints.

### 3.1 Phase Management

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Set Phase | `phase!:{phase_name}` | Set investigation phase | `state.set_phase()` |
| Query Phase | `phase?` | Get current phase | `state.current_phase` |
| Phase History | `phase-history` | Show phase transitions | `state.phase_log` |
| Skip Phase | `phase-skip!:{phase}` | Skip a phase | `state.skip_phase()` |

**Valid Phases:** INITIALIZING, ASSESSING, INVESTIGATING, DISAMBIGUATING, WRITING, CHECKING, FINALIZING, COMPLETE, FAILED, PAUSED

### 3.2 Checkpoint/Resume

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Checkpoint | `checkpoint!` | Save current state | `state.save_checkpoint()` |
| Checkpoint Named | `checkpoint!:{name}` | Save with custom name | `state.save_checkpoint(name=)` |
| List Checkpoints | `checkpoint?` | List available checkpoints | `state.list_checkpoints()` |
| Restore | `checkpoint-restore!:{id}` | Restore from checkpoint | `state.restore_checkpoint()` |
| Resume | `resume!:{investigation_id}` | Resume investigation | `orchestrator.resume()` |
| Pause | `pause!` | Pause investigation | `state.set_phase('PAUSED')` |
| Continue | `continue!` | Continue paused investigation | `orchestrator.continue()` |

### 3.3 Goal/Track/Path Hierarchy

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Create Goal | `goal!:{title}` | Create investigation goal | `planner.create_goal()` |
| Goal Requirements | `goal-requires!:{sections}` | Set ordered requirements | `goal.requires_ordered` |
| Goal Gaps | `goal-gaps?` | Show missing requirements | `planner.find_gaps()` |
| Create Track | `track!:{track_name}` | Create narrative track | `planner.create_track()` |
| Attach Track | `track:{id}+goal:{goal_id}` | Attach track to goal | `planner.attach_track()` |
| Create Path | `path!:{path_name}` | Create investigation path | `planner.create_path()` |
| Narrative Q | `narrative?:{question}` | Create narrative question | `planner.create_narrative()` |

### 3.4 Project/Case Management

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Create Project | `project!:{name}` | Create new project | `project_manager.create()` |
| Switch Project | `project-use!:{id}` | Switch active project | `set_active_project()` |
| List Projects | `project?` | List all projects | `project_manager.list()` |
| Archive Project | `project-archive!:{id}` | Archive project | `project_manager.archive()` |
| Create Case | `case!:{name}` | Create case in project | `case_manager.create()` |
| Link Investigation | `case+inv!:{case_id}:{inv_id}` | Link investigation to case | `case_manager.link()` |

---

## 4. COLLISION/DISAMBIGUATION OPERATORS

Handle entity ambiguity resolution.

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Flag Collision | `collision!:{a}:{b}` | Mark potential collision | `disambiguation.flag()` |
| List Collisions | `collision?` | Show pending collisions | `disambiguation.pending()` |
| Fuse (Same) | `collision-fuse!:{a}:{b}` | Confirm same entity | `disambiguation.resolve('FUSED')` |
| Repel (Different) | `collision-repel!:{a}:{b}` | Confirm different | `disambiguation.resolve('REPELLED')` |
| Binary Star | `collision-star!:{a}:{b}` | Mark ambiguous/overlapping | `disambiguation.resolve('BINARY_STAR')` |
| Collision Evidence | `collision:{id}?` | Show collision evidence | `disambiguation.get_evidence()` |

---

## 5. AI/ANALYSIS OPERATORS (Priority: MEDIUM)

AI-powered extraction, categorization, and analysis.

### 5.1 Extraction

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Extract (default) | `ext!:{url}` | Extract all entities | `central_extractor.extract()` |
| Extract with Model | `ext[model]!:{url}` | Use specific model | `multi_model_ner.extract()` |
| Extract GLiNER | `ext[gliner]!:{url}` | Fast local extraction | `gliner_extractor.extract()` |
| Extract GPT | `ext[gpt]!:{url}` | GPT-based extraction | `ner_gpt4.extract()` |

### 5.2 Categorization

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Categorize | `cat!:{url}` | Categorize content | `categorizer.categorize()` |
| Categorize Batch | `cat!:(#tag)` | Batch categorize | `categorizer.categorize_batch()` |

### 5.3 Summarization

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Summarize | `sum!:{target}` | Summarize content | `summarizer.summarize()` |
| Summarize Entity | `sum!:#entity` | Summarize entity data | `summarizer.summarize_entity()` |

### 5.4 Analysis

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Analyze | `ana!:{url}` | OSINT analysis | `analyzer.analyze()` |
| Analyze Image | `img!:{url}` | Extract from image | `server.analyze_image()` |
| Gap Fill | `gap!:{section}` | AI-powered gap filling | `optima_websearch.fill_gap()` |

### 5.5 Translation

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Translate | `tr[lang]!:{text}` | Translate text | `translate_query()` |
| Multi-Translate | `tr[*]!:{text}` | Translate to all languages | `translate_multi()` |

### 5.6 Embedding/Vector

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Embed | `emb!:{text}` | Generate embedding | `vector_embedder.embed()` |
| Vector Search | `vs!:{query}` | Semantic vector search | `vector_search.search()` |
| Similar | `sim!:{node_id}` | Find similar nodes | `vector_search.similar()` |

---

## 6. EXPORT/IMPORT OPERATORS

Data export and sharing capabilities.

### 6.1 Export

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Export Word | `export!:docx` | Export as Word document | `export.to_word()` |
| Export PDF | `export!:pdf` | Export as PDF | `export.to_pdf()` |
| Export Markdown | `export!:md` | Export as Markdown | `export.to_markdown()` |
| Export JSON | `export!:json` | Export as JSON | `export.to_json()` |
| Export Subgraph | `export!:(#tag):format={fmt}` | Export subset | `export.subgraph()` |
| Export Neo4j | `export!:neo4j` | Export as Cypher | `export.to_neo4j()` |

### 6.2 Import

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Import JSON | `import!:{path}` | Import from JSON | `import.from_json()` |
| Import CSV | `import!:csv:{path}` | Import from CSV | `import.from_csv()` |

### 6.3 Sharing

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Share | `share!:{email}` | Share with user | `sharing.share()` |
| Share Permission | `share-perm!:{email}:{role}` | Set role (viewer/editor) | `sharing.set_permission()` |
| Revoke Share | `share-revoke!:{email}` | Revoke access | `sharing.revoke()` |
| List Shares | `share?` | List shared users | `sharing.list()` |

---

## 7. SECTION/DOCUMENT OPERATORS

Narrative document section management.

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Create Section | `section!:{header}` | Create document section | `sections.create()` |
| Section State | `section:{id}?` | Get section state | `sections.get_state()` |
| Section Content | `section:{id}!:{content}` | Set section content | `sections.set_content()` |
| Add Footnote | `footnote!:{section_id}:{text}` | Add footnote | `sections.add_footnote()` |
| Section Gaps | `section-gaps?:{id}` | Identify section gaps | `sections.find_gaps()` |
| Skip Section | `skip!:{section}` | Skip section in execution | `orchestrator.skip_section()` |

---

## 8. QUERY EXECUTION OPERATORS

Control query tier and execution.

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Generate Queries | `query-gen!:{entity}:{type}` | Generate queries | `planner.generate_queries()` |
| Set Tier | `query-tier!:{tier}` | Set query tier | `query.set_tier()` |
| Execute Query | `query-exec!:{query_id}` | Execute specific query | `executor.execute()` |
| Skip Query | `query-skip!:{query_id}` | Skip query | `executor.skip()` |
| Rerun Query | `query-rerun!:{query_id}` | Retry failed query | `executor.rerun()` |

**Valid Tiers:** T0A, T0B, T1, T2, T3, M (Matrix)

---

## 9. COMPLEXITY/MODEL ROUTING OPERATORS

Control AI model selection and complexity assessment.

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Complexity Score | `complexity?` | Get complexity score | `scouter.score()` |
| Assess Complexity | `complexity!:{query}` | Assess query complexity | `scouter.assess()` |
| Complexity Factors | `complexity-factors?` | Show all factors | `scouter.factors()` |
| Override Model | `model!:{model_name}` | Force specific model | `orchestrator.set_model()` |
| Set Depth | `depth!:{iterations}` | Set max iterations | `orchestrator.set_depth()` |
| Enable Features | `features!:{list}` | Enable advanced features | `orchestrator.enable_features()` |

---

## 10. ITERATION/REFINEMENT OPERATORS

Control investigation iteration and focus.

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Focus | `focus!:{target}` | Focus on entity/section | `orchestrator.focus()` |
| Add Context | `context+:{note}` | Add manual context | `state.add_context()` |
| Review Section | `review!:{section}` | Request review | `orchestrator.review()` |
| Iterate | `iterate!` | Run another iteration | `orchestrator.iterate()` |
| Refine | `refine!:{criteria}` | Refine by criteria | `orchestrator.refine()` |

---

## 11. GRAPH COMPARISON OPERATORS

Compare and diff graph states.

| Operator | Syntax | Description | Handler |
|----------|--------|-------------|---------|
| Diff Graphs | `diff!:{graph1}:{graph2}` | Compare two graphs | `graph.diff()` |
| Merge Graphs | `merge-graph!:{g1}:{g2}` | Union two graphs | `graph.merge_graphs()` |
| Snapshot | `snapshot!` | Create graph snapshot | `graph.snapshot()` |
| Restore Snapshot | `snapshot-restore!:{id}` | Restore snapshot | `graph.restore_snapshot()` |

---

## 12. DEFINITIONAL EXPANSION OPERATORS

Expand concepts to predefined patterns.

| Operator | Syntax | Description | Example Expansion |
|----------|--------|-------------|-------------------|
| German Company | `[cde]` | German company patterns | GmbH, AG, SE, UG, KG, OHG, eG |
| UK Company | `[cuk]` | UK company patterns | Ltd, PLC, Limited, LLP |
| US Company | `[cus]` | US company patterns | Inc, Corp, LLC, LP |
| German Person | `[pde]` | German honorifics | Herr, Frau, Dr., Prof., Dipl. |
| UK Person | `[puk]` | UK honorifics | Mr, Mrs, Sir, Dame, Dr |
| News Sources | `[news]` | News domain patterns | reuters, bbc, bloomberg |
| Sanctions | `[sanctions]` | Sanctions keywords | OFAC, SDN, BIS, sanctioned |

---

## Implementation Priority

### Phase 1 (Critical - Week 1)
1. **Watcher Operators** - `+#w:`, `-#w:`, `#w?`, etc.
2. **Node Delete** - `rm!:`, `rm!:()`
3. **Path Finding** - `path!:`, `traverse!:`

### Phase 2 (High - Week 2)
4. **Workflow Operators** - `phase!`, `checkpoint!`, `resume!`
5. **Collision Operators** - `collision!`, `collision-fuse!`, `collision-repel!`
6. **Graph Metrics** - `centrality!`, `metrics!`, `dedup!`

### Phase 3 (Medium - Week 3-4)
7. **AI Operators** - `ext!`, `cat!`, `sum!`, `ana!`
8. **Export Operators** - `export!:docx`, `share!`
9. **Goal/Track Operators** - `goal!`, `track!`, `path!`

### Phase 4 (Enhancement - Week 5+)
10. **Graph Comparison** - `diff!`, `merge-graph!`
11. **Model Routing** - `model!`, `complexity!`
12. **Definitional** - `[cde]`, `[sanctions]`

---

## Syntax Summary Table

| Pattern | Meaning | Example |
|---------|---------|---------|
| `+#x:` | Create/add | `+#w:header`, `+#tag` |
| `-#x:` | Delete/remove | `-#w:id`, `-#tag` |
| `~#x:` | Toggle | `~#w:id` |
| `=#x:` | Pause/disable | `=#w:id` |
| `!#x:` | Resume/enable | `!#w:id` |
| `x!:` | Action on target | `rm!:node`, `merge!:a:b` |
| `x?` | Query/list | `#w?`, `phase?` |
| `x!` | Scope expanded | `#node!` (node + edges) |
| `x?:id!` | Get findings/details | `#w:id!` |
| `x+y` | Attach/link | `track:id+goal:id` |
| `x[param]!:` | Parameterized action | `ext[gpt]!:url` |
| `(#a AND #b)` | Bulk selection | `rm!:(#a OR #b)` |
| `##dim:val` | Filter | `+#w:header##jurisdiction:UK` |

---

## Backward Compatibility

All existing operators continue to work unchanged. New operators follow established patterns and do not conflict with existing syntax.

---

## Files to Modify

1. **`executor.py`** - Add detection patterns and handler functions
2. **`syntax/parser.py`** - Update grammar for new operators
3. **`operators.json`** - Register new operators
4. **`bridges.py`** - Implement watcher operator handlers
5. **`core/state.py`** - Add phase/checkpoint methods
6. **`orchestrator/graph.py`** - Add delete, merge, path methods

---

*End of Proposal*
