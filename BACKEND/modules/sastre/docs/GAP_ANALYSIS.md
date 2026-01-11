# SASTRE Gap Analysis: Concept vs. Implementation

## Core Findings

The current codebase contains two conflicting architectural patterns:
1. **Rich State (The Spec):** Represented by `core/state.py`. This defines a full in-memory hierarchy (Narrative -> Query -> Source -> Entity) necessary for the advanced reasoning described in the specification.
2. **Thin Wrapper (The Existing App):** Represented by `orchestrator.py`, `contracts.py`, and `grid/assessor.py`. These components interact directly with the Cymonides (Elasticsearch) and IO APIs, treating the database as the source of truth and minimizing local state.

## Detailed Comparison

### 1. State Management
*   **Concept:** Requires `InvestigationState` populated with `NarrativeItem`, `Query`, `SourceResult`, and `Entity` objects to perform cross-level analysis (e.g., tracking which queries answered which narrative questions).
*   **Implementation:** `core/state.py` implements these classes perfectly. However, `orchestrator.py` does not use them. It tracks only `investigation_id` and phase, relying on direct API calls for everything else.
*   **Gap:** Missing a **Hydrator** layer. The Agent needs to load data from the Cymonides Graph (via `CymonidesClient`) and populate the `InvestigationState` object so the `EnhancedGridAssessor` can reason about it.

### 2. Grid Assessment
*   **Concept:** `GridAssessor` and `EnhancedGridAssessor` iterate over the `InvestigationState` object in memory to identify gaps (`narrative_mode`, `subject_mode`, etc.) and perform cross-pollination.
*   **Implementation:** `grid/assessor.py` performs these assessments by running Elasticsearch queries (`ViewMode` filters) against the `cymonides-1-{projectId}` index.
*   **Gap:** The existing implementation is performant (server-side) but lacks the depth of the Spec's logic (e.g., "Narrative Progress" tracking, "Source Query Overlap" detection). The Spec's logic requires the in-memory graph provided by `InvestigationState`.

### 3. Disambiguation
*   **Concept:** Active/Passive disambiguation using FUSE/REPEL logic.
*   **Implementation:** `disambiguation.py` contains the logic (`Disambiguator` class).
*   **Gap:** It is currently disconnected from the orchestration loop. It needs to be invoked when the `EnhancedGridAssessor` identifies `ENTITY_COLLISION` gaps.

### 4. Agent Architecture
*   **Concept:** Autonomous agents (`Orchestrator`, `IOExecutor`, `Disambiguator`, `Writer`) using `anthropic` SDK.
*   **Implementation:** `agents_legacy.py` defines roles but uses a custom tool definition structure. I have started creating the new agents in `agents/` using `sdk.py`.
*   **Gap:** The new agents need to be fully wired up to the `Hydrator` (to get state) and the `Tools` (to execute actions).

## Recommendations

1.  **Do Not Rewrite Orchestrator:** Keep `orchestrator.py` as the interface to the "Existing App" (Cymonides/IO).
2.  **Implement Hydration:** Create a `bridge/hydrator.py` that queries Cymonides (using `orchestrator.py`'s client) and builds the `InvestigationState` object.
3.  **Connect Agents:** Ensure the new `agents/orchestrator.py` uses this Hydrator to build state before running the `EnhancedGridAssessor`.
4.  **Action Dispatch:** Ensure tools in `tools/` translate Agent decisions back into `CymonidesClient` / `IOClient` calls.
