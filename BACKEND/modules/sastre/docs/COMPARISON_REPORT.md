# SASTRE vs. Existing Codebase Comparison Report

## 1. Orchestration
*   **SASTRE Concept:** `SastreOrchestrator` (Agent-driven). Uses `InvestigationState` to reason about "Narrative," "Query," "Source," and "Entity" levels. Driven by `GridAssessor` gaps.
*   **Existing Code:** `InvestigationOrchestrator` in `orchestrator/investigation_engine.py`. Procedural loop iterating through phases (`_search_phase`, `_extract_phase`, etc.).
*   **Verdict:** **Functional Duplicate.** The existing orchestrator handles the "loop" logic procedurally. SASTRE proposes doing it agentically. Implementing `SastreOrchestrator` as a separate class is redundant unless it *wraps* the existing `InvestigationOrchestrator` or replaces its logic entirely.

## 2. Assessment / Auditing
*   **SASTRE Concept:** `GridAssessor`. Structured 4-mode assessment (Narrative, Subject, Location, Nexus) querying the graph.
*   **Existing Code:** `JESTER/auditor.py` (`Auditor`). Uses LLM (`Gemini 3 Pro`) to verify reports against source documents ("Hallucination Check", "Omission Check").
*   **Verdict:** **Conceptual Overlap, Implementation Divergence.** `Auditor` checks *text vs. text*. `GridAssessor` checks *graph completeness*. They solve different problems but fill the "Check" role in the OODA loop.

## 3. Execution (IO)
*   **SASTRE Concept:** `IOExecutor`. Wrapper around `IOClient` to execute macros.
*   **Existing Code:** `InvestigationOrchestrator` methods (`_search_phase` -> `Brute`, `_extract_phase` -> `Jester`, etc.) and `driller/overnight_driller.py` (`OvernightDriller`) for batch processing.
*   **Verdict:** **Wrap, Don't Rebuild.** The SASTRE `IOExecutor` agent should simply call the existing API endpoints defined in `InvestigationOrchestrator` (e.g., `BRUTE_API_URL`, `JESTER_API_URL`) or the `OvernightDriller` for bulk tasks.

## 4. Disambiguation
*   **SASTRE Concept:** `Disambiguator`. Explicit FUSE/REPEL logic using "Physics of Identity."
*   **Existing Code:** `InvestigationGraph` (in `orchestrator/graph.py`, imported by `investigation_engine.py`) handles graph construction. `matrix` phase in `InvestigationOrchestrator` does "Auto-Enrichment."
*   **Verdict:** **Missing Component.** No explicit FUSE/REPEL logic found in scanned files. The `Disambiguator` logic in SASTRE is a unique addition not found in the scanned codebase.

## 5. State Management
*   **SASTRE Concept:** `InvestigationState`. Hierarchical in-memory object (Narrative -> Query -> Source -> Entity).
*   **Existing Code:** `InvestigationGraph` (in `orchestrator/graph.py`). Likely holds the in-memory graph state during `InvestigationOrchestrator` runs.
*   **Verdict:** **Potential Duplicate.** If `InvestigationGraph` tracks entities and edges, `InvestigationState` might be redundant. Need to check `orchestrator/graph.py`.

## Action Plan (Revised)
1.  **Do NOT implement `SastreOrchestrator` logic from scratch.** Use `orchestrator/investigation_engine.py` as the execution engine.
2.  **Focus on the AGENT Layer.** The SASTRE agents (`orchestrator.py` agent, etc.) should just be *prompts and tool definitions* that call the existing Python classes.
3.  **Use `InvestigationGraph`**: Investigate `orchestrator/graph.py` to see if it can serve as the `InvestigationState`.
4.  **Implement Disambiguation**: This appears to be the primary "missing piece" to build.
