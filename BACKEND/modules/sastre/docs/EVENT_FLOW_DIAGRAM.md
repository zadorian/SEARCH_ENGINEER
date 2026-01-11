# SASTRE Event Flow Diagram

## Investigation Lifecycle with Event Emissions

```
┌─────────────────────────────────────────────────────────────┐
│                    SASTRE INVESTIGATION                      │
│                                                              │
│  User: python3 -m SASTRE.cli --stream "Investigate X"       │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  ThinOrchestrator.__init__(event_callback=stream_event)     │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  async def run()                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ EVENT: "start"                                        │  │
│  │ {type: "start", tasking: "...", max_iterations: 10}   │  │
│  └───────────────────────────────────────────────────────┘  │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 1: INITIALIZE                                         │
│  ├─ Create investigation in Cymonides                       │
│  ├─ Create narrative document                               │
│  └─ Create section watchers                                 │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 2: MAIN LOOP (iteration 1..max_iterations)           │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  async def _iteration_step()                          │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │ EVENT: "phase"                                  │  │  │
│  │  │ {type: "phase", phase: "ASSESS", iteration: 1}  │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  └───────────────────┬───────────────────────────────────┘  │
│                      │                                       │
│                      ▼                                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  ASSESS PHASE                                       │    │
│  │  ├─ async def _assess()                             │    │
│  │  │  ┌───────────────────────────────────────────┐   │    │
│  │  │  │ EVENT: "log"                              │   │    │
│  │  │  │ {message: "Grid state: ...", phase: "..."}│   │    │
│  │  │  └───────────────────────────────────────────┘   │    │
│  │  │                                                   │    │
│  │  ├─ Run Cognitive Engine (V4.1)                     │    │
│  │  │  └─ async def _run_cognitive_rotation()         │    │
│  │  │     ├─ NARRATIVE mode                            │    │
│  │  │     │  ┌────────────────────────────────────┐    │    │
│  │  │     │  │ EVENT: "log"                       │    │    │
│  │  │     │  │ {message: "[NARRATIVE] N gaps"}    │    │    │
│  │  │     │  └────────────────────────────────────┘    │    │
│  │  │     ├─ SUBJECT mode                              │    │
│  │  │     │  ┌────────────────────────────────────┐    │    │
│  │  │     │  │ EVENT: "log"                       │    │    │
│  │  │     │  │ {message: "[SUBJECT] N gaps"}      │    │    │
│  │  │     │  └────────────────────────────────────┘    │    │
│  │  │     ├─ LOCATION mode                             │    │
│  │  │     │  ┌────────────────────────────────────┐    │    │
│  │  │     │  │ EVENT: "log"                       │    │    │
│  │  │     │  │ {message: "[LOCATION] N gaps"}     │    │    │
│  │  │     │  └────────────────────────────────────┘    │    │
│  │  │     ├─ NEXUS mode                                │    │
│  │  │     │  ┌────────────────────────────────────┐    │    │
│  │  │     │  │ EVENT: "log"                       │    │    │
│  │  │     │  │ {message: "[NEXUS] N gaps"}        │    │    │
│  │  │     │  └────────────────────────────────────┘    │    │
│  │  │     ├─ Corpus search                             │    │
│  │  │     │  ┌────────────────────────────────────┐    │    │
│  │  │     │  │ EVENT: "log"                       │    │    │
│  │  │     │  │ {message: "[CORPUS] N hits"}       │    │    │
│  │  │     │  └────────────────────────────────────┘    │    │
│  │  │     └─ Cross-pollination                         │    │
│  │  │        ┌────────────────────────────────────┐    │    │
│  │  │        │ EVENT: "log"                       │    │    │
│  │  │        │ {message: "[CROSS] N insights"}    │    │    │
│  │  │        └────────────────────────────────────┘    │    │
│  │  │                                                   │    │
│  │  └─ Prioritize actions from cognitive gaps          │    │
│  └─────────────────────────────────────────────────────┘    │
│                      │                                       │
│                      ▼                                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  INVESTIGATE PHASE                                  │    │
│  │  ├─ async def _investigate()                        │    │
│  │  │  ┌───────────────────────────────────────────┐   │    │
│  │  │  │ EVENT: "log"                              │   │    │
│  │  │  │ {message: "Executing queries", phase: ...}│   │    │
│  │  │  └───────────────────────────────────────────┘   │    │
│  │  │                                                   │    │
│  │  └─ For each action:                                │    │
│  │     └─ async def _execute_action(action)            │    │
│  │        ├─ Translate action to query                 │    │
│  │        │  ┌────────────────────────────────────┐    │    │
│  │        │  │ EVENT: "query"                     │    │    │
│  │        │  │ {syntax: "p: John", intent: "..."}│    │    │
│  │        │  └────────────────────────────────────┘    │    │
│  │        │                                             │    │
│  │        ├─ Execute via IO/Bridges                    │    │
│  │        │  ┌────────────────────────────────────┐    │    │
│  │        │  │ EVENT: "result"                    │    │    │
│  │        │  │ {source: "Linklater", count: 42}   │    │    │
│  │        │  └────────────────────────────────────┘    │    │
│  │        │                                             │    │
│  │        └─ Detect Surprising ANDs                    │    │
│  │           └─ async def _detect_surprising_connections()  │
│  │              ┌────────────────────────────────────┐  │    │
│  │              │ EVENT: "finding"                   │  │    │
│  │              │ {type: "surprising_and", ...}      │  │    │
│  │              └────────────────────────────────────┘  │    │
│  └─────────────────────────────────────────────────────┘    │
│                      │                                       │
│                      ▼                                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  DISAMBIGUATE PHASE (if collisions)                 │    │
│  │  ├─ async def _disambiguate()                       │    │
│  │  │  ┌───────────────────────────────────────────┐   │    │
│  │  │  │ EVENT: "log"                              │   │    │
│  │  │  │ {message: "Resolving collisions", ...}    │   │    │
│  │  │  └───────────────────────────────────────────┘   │    │
│  │  └─ Binary cascade disambiguation                   │    │
│  └─────────────────────────────────────────────────────┘    │
│                      │                                       │
│                      ▼                                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  CHECKING PHASE                                     │    │
│  │  ├─ async def _check_sufficiency()                  │    │
│  │  │  ┌───────────────────────────────────────────┐   │    │
│  │  │  │ EVENT: "log"                              │   │    │
│  │  │  │ {message: "Evaluating sufficiency", ...}  │   │    │
│  │  │  └───────────────────────────────────────────┘   │    │
│  │  │  ┌───────────────────────────────────────────┐   │    │
│  │  │  │ EVENT: "log"                              │   │    │
│  │  │  │ {message: "Sufficiency: 85%", ...}        │   │    │
│  │  │  └───────────────────────────────────────────┘   │    │
│  │  │                                                   │    │
│  │  └─ Decision: sufficient? → WRITING                 │    │
│  │              not sufficient? → ASSESS (loop)        │    │
│  └─────────────────────────────────────────────────────┘    │
│                      │                                       │
│                      ▼                                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  WRITING PHASE                                      │    │
│  │  ├─ async def _write()                              │    │
│  │  │  ┌───────────────────────────────────────────┐   │    │
│  │  │  │ EVENT: "log"                              │   │    │
│  │  │  │ {message: "Streaming findings", ...}      │   │    │
│  │  │  └───────────────────────────────────────────┘   │    │
│  │  │                                                   │    │
│  │  └─ Stream findings to watchers                     │    │
│  │     ├─ Entities of Interest                         │    │
│  │     │  ┌────────────────────────────────────────┐   │    │
│  │     │  │ EVENT: "finding"                       │   │    │
│  │     │  │ {section: "Entities", content: "..."}  │   │    │
│  │     │  └────────────────────────────────────────┘   │    │
│  │     ├─ Corporate Structure                          │    │
│  │     │  ┌────────────────────────────────────────┐   │    │
│  │     │  │ EVENT: "finding"                       │   │    │
│  │     │  │ {section: "Corporate", content: "..."}│   │    │
│  │     │  └────────────────────────────────────────┘   │    │
│  │     └─ Connections & Relationships                  │    │
│  │        ┌────────────────────────────────────────┐   │    │
│  │        │ EVENT: "finding"                       │   │    │
│  │        │ {section: "Connections", content: "..."}   │    │
│  │        └────────────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────────────┘    │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 3: FINALIZE                                           │
│  ├─ async def _finalize()                                   │
│  │  ┌───────────────────────────────────────────────────┐   │
│  │  │ EVENT: "log"                                      │   │
│  │  │ {message: "Finalizing investigation", ...}        │   │
│  │  └───────────────────────────────────────────────────┘   │
│  │  ┌───────────────────────────────────────────────────┐   │
│  │  │ EVENT: "complete"                                 │   │
│  │  │ {status: "success", iterations: N,                │   │
│  │  │  document_id: "...", sufficiency_score: 0.85}     │   │
│  │  └───────────────────────────────────────────────────┘   │
│  └─ Return final result                                     │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  CLI Output                                                  │
│  ├─ Stream mode (--stream): events already emitted          │
│  └─ Normal mode: print formatted result                     │
└─────────────────────────────────────────────────────────────┘
```

## Event Type Distribution

```
START (1)
  │
  ├─ Investigation begins
  └─ Tasking and parameters logged

PHASE (1 per iteration)
  │
  ├─ INITIALIZING
  ├─ ASSESSING
  ├─ INVESTIGATING
  ├─ DISAMBIGUATING
  ├─ CHECKING
  ├─ WRITING
  └─ FINALIZING

LOG (11 points)
  │
  ├─ Grid state (ASSESS)
  ├─ Cognitive rotation summary (ASSESS)
  ├─ Narrative mode gaps (ASSESS)
  ├─ Subject mode gaps (ASSESS)
  ├─ Location mode gaps (ASSESS)
  ├─ Nexus mode gaps (ASSESS)
  ├─ Corpus hits (ASSESS)
  ├─ Cross-pollination insights (ASSESS)
  ├─ Query execution start (INVESTIGATE)
  ├─ Disambiguation start (DISAMBIGUATE)
  ├─ Writing start (WRITE)
  ├─ Sufficiency evaluation (CHECK)
  ├─ Sufficiency score (CHECK)
  └─ Finalization (FINALIZE)

QUERY (1 per action)
  │
  ├─ Syntax (e.g., "p: John Smith")
  ├─ Intent (DISCOVER, ENRICH_ENTITY, etc.)
  ├─ K-U Quadrant (discover/trace/extract/verify)
  └─ Action type (NARRATIVE_GAP, SUBJECT_GAP, etc.)

RESULT (1 per query execution)
  │
  ├─ Source (BruteSearch, Linklater, Corporella, etc.)
  ├─ Count (number of results)
  └─ Query (what was searched)

FINDING (4 points)
  │
  ├─ Surprising AND detection (INVESTIGATE)
  ├─ Entities of Interest (WRITE)
  ├─ Corporate Structure (WRITE)
  └─ Connections & Relationships (WRITE)

COMPLETE (1)
  │
  ├─ Status (success/error)
  ├─ Iterations completed
  ├─ Document ID
  ├─ Sufficiency score
  └─ Watcher count
```

## Frontend Integration

### SSE Endpoint (Phase 2)

```typescript
// Frontend connection
const eventSource = new EventSource(
  '/api/sastre/investigate/stream?tasking=Investigate+X&project_id=mycase'
);

eventSource.addEventListener('start', (e) => {
  const data = JSON.parse(e.data);
  console.log('Investigation started:', data.tasking);
});

eventSource.addEventListener('phase', (e) => {
  const data = JSON.parse(e.data);
  updatePhaseIndicator(data.phase, data.iteration, data.max_iterations);
});

eventSource.addEventListener('log', (e) => {
  const data = JSON.parse(e.data);
  appendToConsole(data.message, data.phase);
});

eventSource.addEventListener('query', (e) => {
  const data = JSON.parse(e.data);
  displayQuery(data.syntax, data.intent, data.ku_quadrant);
});

eventSource.addEventListener('result', (e) => {
  const data = JSON.parse(e.data);
  updateResultCounter(data.source, data.count);
});

eventSource.addEventListener('finding', (e) => {
  const data = JSON.parse(e.data);
  appendToSection(data.section, data.content);
});

eventSource.addEventListener('complete', (e) => {
  const data = JSON.parse(e.data);
  showInvestigationComplete(data.iterations, data.sufficiency_score);
  eventSource.close();
});
```

## Summary

Total event emission points: **20**

Event types: **7** (start, phase, log, query, result, finding, complete)

All major orchestration phases covered:
- ✅ Investigation initialization
- ✅ Cognitive assessment (4 modes + corpus + cross-pollination)
- ✅ Query generation and execution
- ✅ Result processing
- ✅ Disambiguation
- ✅ Finding extraction
- ✅ Sufficiency checking
- ✅ Document compilation
- ✅ Investigation completion

**Ready for Phase 2: SSE Endpoint Implementation**
