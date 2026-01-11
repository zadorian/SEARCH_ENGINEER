# JESTER: Smart Fill Design (The Researcher)

> **Objective:** Port the "Search & Write" capability (formerly Mukodik/FactAssembler) into Jester to restore the "Smart Fill" feature in the Narrative Editor.

## The Concept: "Jester as Researcher"

Currently, Jester is a **Librarian** (Sorter). It takes *existing* documents and organizes them.
To support Smart Fill, Jester must become a **Researcher**. It must go out, find documents, and *then* sort them.

The workflow shifts from:
`Document -> Ingest -> Classify -> Report`
To:
`Query -> Harvest -> Ingest -> Classify -> Report`

---

## 1. New Component: The Harvester

We need a new module `harvester.py` responsible for Phase 0 (Discovery).

**Responsibilities:**
1.  **Search:** specific queries using our best engines.
2.  **Download:** fetch content (HTML/PDF) from results.
3.  **Pre-process:** convert to text for the Ingester.

**Tools to Use:**
*   **Linklater:** For high-recall archive search (Wayback/CC).
*   **Firecrawl:** For live web scraping.
*   **Search_Engineer:** For broad discovery (Brute Search).

**Output:**
A virtual "Document" (or collection of text streams) that `ingester.py` can consume.

---

## 2. Workflow: `fill_section` Mode

We will add a new mode to Jester's `main.py`: `--mode fill_section`.

**Input:**
*   `--query`: The research question (e.g. "Revenue of Acme Corp 2020-2024").
*   `--context`: The section header/topic (e.g. "## Financial Performance").

**Pipeline:**

1.  **Harvest (Phase 0):**
    *   `Harvester` generates search variations from the query.
    *   Executes search via `Linklater` / `Firecrawl`.
    *   Downloads top N results.
    *   *Optimization:* Reuse existing Grid nodes if provided (Context Nodes).

2.  **Ingest (Phase 1):**
    *   `Ingester` reads the downloaded content.
    *   Breaks it into "Atoms" (paragraphs).
    *   *Metadata:* Each atom is tagged with its Source URL.

3.  **Classify (Phase 2):**
    *   **Topic:** The target section header is the *only* topic.
    *   `Classifier` checks every atom: "Is this relevant to [Financial Performance]?"
    *   *Strictness:* High threshold. We only want relevant facts.

4.  **Report (Phase 3):**
    *   `Reporter` takes all atoms classified as "Relevant".
    *   Synthesizes them into a coherent narrative flow.
    *   *Citations:* Appends source URLs as footnotes.

5.  **Audit (Phase 4 - Optional):**
    *   `Auditor` verifies the generated text against the source atoms to ensure no hallucinations.

---

## 3. Implementation Plan

### A. Create `harvester.py`
*   Import `Linklater` and `Firecrawl` wrappers.
*   Implement `search_and_fetch(query, limit=10)`.
*   Implement `fetch_from_grid(node_ids)`.

### B. Update `main.py`
*   Add `--mode` argument.
*   Handle `fill_section` logic branch.
*   Wire up the pipeline: `Harvester` -> `Ingester` -> `Classifier` -> `Reporter`.

### C. Update `jester_mcp.py`
*   Expose `research_topic(query)` tool for the Agent.

### D. Refine `reporter.py`
*   Ensure it can generate a "Section Fragment" (just body text) rather than a full "Report" (with headers/TOC) when in this mode.

---

## 4. Integration with Frontend

The frontend (`NarrativeEditorPanel`) is already wired to call:
`POST /api/jester/run { mode: "fill_section", query: "...", section_header: "..." }`

We just need to implement the backend route to map this request to the CLI command.

**Route:** `BACKEND/api/jester_routes.py`
*   Already has `JesterRequest`.
*   Need to update `run_jester` to handle the `fill_section` arguments.

---

## 5. Migration Checklist

- [ ] Create `harvester.py` in `BACKEND/modules/JESTER/`.
- [ ] Update `main.py` to support `fill_section`.
- [ ] Update `jester_routes.py` to pass query/context args.
- [ ] Verify end-to-end flow with a test query.
