# C0GN1T0 <-> SASTRE Integration Survey

**Date:** December 20, 2025
**Auditor:** Gemini CLI Agent
**Subject:** Feasibility of "Autopilot" Integration between C0GN1T0 (Frontend AI) and SASTRE (Backend Investigation)

## 1. Current State Assessment

### A. The "Driver" (C0GN1T0)
*   **Location:** `client/src/contexts/CognitoContext.tsx`
*   **Capabilities:** Handles chat interaction, context awareness (grid cells, graph nodes), and "doc-write" operations to Edith.
*   **Missing Capability:** Cannot currently *trigger* an investigation in the main interface. It observes context but does not drive the search bar.

### B. The "Vehicle" (SASTRE / DrillSearchPython)
*   **Location:** `client/src/pages/DrillSearchPython.tsx`
*   **Capabilities:** Has a robust `IOProgressPanel` that displays module status, progress bars, and errors.
*   **Execution Mechanism:** Uses `runStreamingInvestigation` (via `lib/ioService`) to talk to the backend. This supports streaming updates (`onModuleStart`, `onProgress`).
*   **Missing Control:** The "STOP" button logic exists in comments (`// Store cleanup function...`) but is not exposed in the UI.

### C. The "Engine" (SASTRE Backend)
*   **Status:** The `check-sastre-branch-7Uc7O` merge (now in `sastre`) has the necessary `UnifiedExecutor` and `ThinOrchestrator` to run complex, multi-step investigations.
*   **Streaming:** The backend already emits progress events that the frontend's `runStreamingInvestigation` knows how to consume.

## 2. Requirements for "Autopilot" Experience

To enable `c0gn1t0` to "drive" the app as requested:

### Step 1: The "Drive" Command (Frontend)
`c0gn1t0` needs a way to push commands to the main search controller.
*   **Action:** Add a `drill:execute-command` event listener in `DrillSearchPython.tsx`.
*   **Logic:** When `c0gn1t0` emits a tool call like `investigate(query)`, `CognitoContext` dispatches this event. `DrillSearchPython` catches it, sets the search bar text, and fires `handleSearch`.

### Step 2: Visual Feedback ("Ghost Typing")
The user wants to see the syntax being written.
*   **Action:** In `DrillSearchPython.tsx`, when an automated command is received, use a "typewriter effect" to update the `keyword` state visibly before submitting.

### Step 3: Granular Logging
The `IOProgressPanel` is good but high-level.
*   **Action:** Enhance `IOProgressPanel` to show a scrolling log of "micro-events" (e.g., "SASTRE: Generating search syntax...", "SASTRE: Filtering for 'registry'").
*   **Source:** These events should come from the SASTRE backend's `CognitiveLog` (from `gap_analyzer.py`) streaming back to the frontend.

### Step 4: The Kill Switch
*   **Action:** Expose the `abortController` from `runStreamingInvestigation` to the `IOProgressPanel`'s UI as a red "STOP AUTOPILOT" button.

### Step 5: Streaming to Edith
*   **Action:** The `UnifiedExecutor` in the backend should optionally accept a `target_document_id`. If set, it uses `JesterBridge` to stream narrative findings directly into that document ID as they are discovered, leveraging the existing "doc-write" logic in `CognitoContext`.

## 3. Implementation Plan (Read-Only Recommendation)

1.  **Frontend:** Update `DrillSearchPython.tsx` to listen for `drill:execute-command`.
2.  **Frontend:** Update `CognitoContext.tsx` to parse "investigate" tool calls and dispatch the event.
3.  **Frontend:** Add "STOP" button to `IOProgressPanel`.
4.  **Backend:** Ensure `ThinOrchestrator` streams `gap_analyzer` logs as progress events.

---
*Survey completed by Gemini CLI Agent.*
