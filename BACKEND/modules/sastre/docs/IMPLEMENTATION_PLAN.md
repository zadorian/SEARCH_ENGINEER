# SASTRE Implementation Plan (Revised)

## Core Directive: NO DUPLICATES
The SASTRE agent must be a thin reasoning layer over the existing, robust Drill Search infrastructure. It must NOT re-implement orchestration, execution, or state management logic that already exists.

## 1. Mapping: Concept -> Codebase

| SASTRE Component | Existing Equivalent | Strategy |
| :--- | :--- | :--- |
| **InvestigationState** | `orchestrator.graph.InvestigationGraph` | **Reuse.** The `InvestigationGraph` class in `orchestrator/graph.py` already tracks entities, edges, frontiers, and iteration metadata. It IS the state. |
| **Orchestrator** | `orchestrator.investigation_engine.InvestigationOrchestrator` | **Wrap.** The existing class handles the procedural loop (`_search_phase`, `_extract_phase`). The SASTRE agent will assume the role of "Operator" invoking this engine, rather than rebuilding the engine itself. |
| **IO Executor** | `driller.overnight_driller.OvernightDriller` | **Reuse.** For batch/bulk operations, use `OvernightDriller`. for targeted queries, use `InvestigationOrchestrator` methods. |
| **Grid Assessor** | `JESTER.auditor.Auditor` (partial) | **Extend.** The existing `Auditor` checks text. We need a lightweight `GraphAssessor` that checks `InvestigationGraph` for gaps (e.g., "Company has no officers"). This is a missing piece but should be a utility on top of the Graph, not a new system. |
| **Disambiguator** | *None Found* | **Implement.** This is the primary missing logic. We need a `DisambiguationService` that takes an `InvestigationGraph` and merges nodes based on FUSE/REPEL logic. |

## 2. Implementation Steps

### Step 1: Disambiguation Service (The Missing Piece)
Create `BACKEND/modules/SASTRE/services/disambiguation.py`.
- **Input:** `InvestigationGraph`
- **Logic:** Iterate through entities, check for collisions (Same name + same context), applying FUSE/REPEL rules.
- **Output:** Modified `InvestigationGraph` (merged nodes).

### Step 2: Graph Assessor (The "Grid" Logic)
Create `BACKEND/modules/SASTRE/services/graph_assessor.py`.
- **Input:** `InvestigationGraph`
- **Logic:** Check for missing edges/attributes based on entity type (e.g., Person missing Email, Company missing Officers).
- **Output:** List of `Gap` objects (which become prompts for the Orchestrator).

### Step 3: SASTRE Agent Interface
Create `BACKEND/modules/SASTRE/agent_interface.py`.
- **Role:** This is the actual "Agent" that the user talks to.
- **Loop:**
    1.  **Hydrate:** Load `InvestigationGraph` (via `InvestigationOrchestrator`).
    2.  **Assess:** Run `GraphAssessor` to find gaps.
    3.  **Reason:** LLM decides next step (Search, Extract, Disambiguate).
    4.  **Act:** Call `InvestigationOrchestrator` methods or `DisambiguationService`.
    5.  **Persist:** Save graph state.

## 3. What We Will DELETE/IGNORE
- `BACKEND/modules/SASTRE/core/state.py` (Redundant with `InvestigationGraph`)
- `BACKEND/modules/SASTRE/orchestrator.py` (Redundant with `InvestigationOrchestrator`)
- `BACKEND/modules/SASTRE/agents/io_executor.py` (Redundant with `OvernightDriller`)

## 4. Final Architecture
User -> `SastreAgent` -> `GraphAssessor` -> `InvestigationOrchestrator` -> `[Brute, Jester, Corporella, Linklater]` -> `InvestigationGraph` -> `DisambiguationService`
