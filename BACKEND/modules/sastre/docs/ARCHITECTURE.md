# SASTRE V4 Architecture

```
                                    ┌─────────────────────────────────────┐
                                    │      USER INTENT (Natural Lang)     │
                                    └──────────────────┬──────────────────┘
                                                       │
                                                       ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ PART I: FOUNDATION                                                                               │
│                                                                                                  │
│   ┌────────────────────────┐              ┌─────────────────────────────────────────────────┐   │
│   │ NARRATIVE DECOMPOSITION │─────────────▶│ FOUR CLASSES: Subject | Location | Narrative | Nexus │
│   └────────────────────────┘              └─────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                       │
                                                       ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ PART II: TACTICAL LAYER                                                                          │
│                                                                                                  │
│   ┌──────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐                │
│   │ K-U ENGINE           │    │ TACTICAL TRIAD      │    │ SLOT HUNGER         │◀───────────┐  │
│   │ Verify|Trace|Extract │    │ Spear | Trap | Net  │    │ Find empty slots    │            │  │
│   │ Discover             │    │                     │    │                     │            │  │
│   └──────────────────────┘    └─────────────────────┘    └─────────────────────┘            │  │
│              ▲                                                                               │  │
│              │ FEEDBACK LOOP ────────────────────────────────────────────────────────────────┘  │
└──────────────┼───────────────────────────────────────────────────────────────────────────────────┘
               │                           │
               │                           ▼
┌──────────────┼───────────────────────────────────────────────────────────────────────────────────┐
│ PART IV: AGENT EXECUTION                 │                                                       │
│                                          │                                                       │
│                          ┌───────────────▼───────────────┐                                       │
│                          │      ⬡ ORCHESTRATOR           │                                       │
│                          │   Coordination & State Mgmt   │                                       │
│                          └───────────────┬───────────────┘                                       │
│                                          │                                                       │
│            ┌─────────────────────────────┼─────────────────────────────┐                         │
│            ▼                             ▼                             ▼                         │
│   ┌─────────────────┐         ┌─────────────────────┐       ┌─────────────────┐                 │
│   │ ⬡ IO EXECUTOR   │         │ PROCESSING AGENTS   │       │ ⬡ GRID ASSESSOR │                 │
│   │                 │         │                     │       │                 │                 │
│   │ Op :Target =>#Tag│        │ ⬡ DISAMBIGUATOR     │       │ Completeness    │                 │
│   │                 │         │   Fuse/Repel/Wedge  │       │ Confidence      │                 │
│   └────────┬────────┘         │                     │       │ Coverage        │                 │
│            │                  │ ⬡ SIMILARITY ENGINE │       │ Coherence       │                 │
│            │                  │   Vectors & =?      │       │                 │                 │
│            │                  │                     │       └────────┬────────┘                 │
│            │                  │ ⬡ NEXUS DETECTION   │                │                          │
│            │                  │   Expectations      │                │                          │
│            │                  └──────────┬──────────┘                │                          │
└────────────┼─────────────────────────────┼───────────────────────────┼──────────────────────────┘
             │                             │                           │
             ▼                             ▼                           │
┌─────────────────────────────────────────────────────────────────┐    │
│ DATA INFRASTRUCTURE                                             │    │
│                                                                 │    │
│   ┌─────────────────┐              ┌─────────────────┐          │    │
│   │ EXTERNAL SOURCES│◀────────────▶│    THE GRID     │──────────┼────┘
│   │ Domains, APIs   │   Entity     │  Internal Graph │          │
│   │ Registries      │  Extraction  │  Nodes, Slots   │          │
│   └─────────────────┘              └────────┬────────┘          │
│                                             │                   │
└─────────────────────────────────────────────┼───────────────────┘
                                              │
                                              ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ PART V: SYNTHESIS & LOOP                                                                         │
│                                                                                                  │
│                                  ┌──────────────────┐                                            │
│                                  │ IS STATE         │                                            │
│                                  │ SUFFICIENT?      │                                            │
│                                  └────────┬─────────┘                                            │
│                                           │                                                      │
│                      ┌────────────────────┼────────────────────┐                                 │
│                      │ NO                 │                YES │                                 │
│                      ▼                    │                    ▼                                 │
│            ┌─────────────────┐            │         ┌─────────────────┐                          │
│            │ Return to       │            │         │ ⬡ WRITER AGENT  │                          │
│            │ SLOT HUNGER     │────────────┼────▶    │                 │                          │
│            │ (see Part II)   │   LOOP     │         └────────┬────────┘                          │
│            └─────────────────┘            │                  │                                   │
│                                           │                  ▼                                   │
│                                           │    ┌──────────────────────────────┐                  │
│                                           │    │ PART III: INTERFACE          │                  │
│                                           │    │                              │                  │
│                                           │    │  ┌────────────────────────┐  │                  │
│                                           │    │  │ HOLOGRAPHIC GRIDVIEW   │  │                  │
│                                           │    │  │ Subject/Location/      │  │                  │
│                                           │    │  │ Narrative rotations    │  │                  │
│                                           │    │  └────────────────────────┘  │                  │
│                                           │    │                              │                  │
│                                           │    │  ┌────────────────────────┐  │                  │
│                                           │    │  │ THE LIVING DOCUMENT    │  │                  │
│                                           │    │  │ Prose output           │  │                  │
│                                           │    │  └────────────────────────┘  │                  │
│                                           │    └──────────────────────────────┘                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Component Mapping

| Diagram Component | Implementation File |
|-------------------|---------------------|
| **PART I: FOUNDATION** | |
| User Intent | `query_compiler.py` IntentTranslator |
| Narrative Decomposition | `document_interface.py` |
| Four Classes | `contracts.py` |
| **PART II: TACTICAL** | |
| K-U Engine | `contracts.py` KUQuadrant, `derive_quadrant()` |
| Tactical Triad | `tactical.py` (Spear/Trap/Net) |
| Slot Hunger | `contracts.py` EntitySlot.is_hungry |
| **PART IV: AGENTS** | |
| Orchestrator | `agents/orchestrator.py` |
| IO Executor | `agents/io_executor.py` → `io_cli.py` |
| Disambiguator | `agents/disambiguator.py` |
| Similarity Engine | `agents/similarity_engine.py` |
| Nexus Detection | `agents/orchestrator.py` (SurprisingAnd) |
| Grid Assessor | `agents/grid_assessor.py`, `gap_analyzer.py` |
| **INFRASTRUCTURE** | |
| External Sources | `io_cli.py` → 86 engines |
| The Grid | `bridges.py` CymonidesState |
| Entity Extraction | `bridges.py` EyeDClient |
| **PART V: SYNTHESIS** | |
| Sufficiency Check | `contracts.py` SufficiencyResult |
| Writer Agent | `agents/writer.py` |
| Holographic GridView | Frontend `SearchResultsGrid.tsx` |
| Living Document | `document_interface.py` |

## Data Flow

1. **User Intent** → IntentTranslator → K-U Quadrant classification
2. **Tactical Layer** → Selects Spear/Trap/Net based on K-U + Slot Hunger
3. **Orchestrator** → Dispatches to IO Executor with syntax queries
4. **IO Executor** → External sources + Grid queries
5. **Processing** → Disambiguator → Similarity → Nexus detection
6. **Grid Assessor** → 4C check (Completeness, Confidence, Coverage, Coherence)
7. **Sufficiency** → If NO: loop to Slot Hunger; If YES: Writer Agent
8. **Output** → Holographic GridView + Living Document
