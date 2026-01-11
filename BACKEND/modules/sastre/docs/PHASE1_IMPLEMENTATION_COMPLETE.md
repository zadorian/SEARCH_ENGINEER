# Phase 1: Python Event Streaming - Implementation Complete

## Overview

Phase 1 of the C0GN1T0 + SASTRE Autopilot integration has been successfully implemented. The ThinOrchestrator now emits structured JSON events at all key points in the investigation loop, and the CLI supports streaming these events to stdout for frontend consumption.

## Implementation Details

### 1. ThinOrchestrator Event Emission

**File**: `BACKEND/modules/SASTRE/orchestrator/thin.py`

#### Event Callback Parameter

The `ThinOrchestrator.__init__` method accepts an optional `event_callback` parameter:

```python
def __init__(
    self,
    project_id: str,
    tasking: str,
    max_iterations: int = 10,
    autonomous: bool = True,
    event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
):
    self.event_callback = event_callback
```

#### Event Emission Method

The `_emit` method handles all event emission with consistent structure:

```python
def _emit(self, event_type: str, data: Optional[Dict[str, Any]] = None):
    """Emit event for frontend streaming consumption."""
    if not self.event_callback:
        return

    event = {
        "type": event_type,
        "timestamp": datetime.now().isoformat(),
        "project_id": self.project_id,
        "iteration": self._iteration,
        **(data or {})
    }
    try:
        self.event_callback(event)
    except Exception as e:
        logger.warning(f"Event callback error: {e}")
```

#### Event Types and Emission Points

| Event Type | Count | Purpose | Example Data |
|------------|-------|---------|--------------|
| `start` | 1 | Investigation begins | `{"tasking": "...", "max_iterations": 10}` |
| `phase` | 1 | Phase transition | `{"phase": "ASSESS", "iteration": 1}` |
| `log` | 11 | Important log messages | `{"message": "...", "phase": "ASSESS"}` |
| `query` | 1 | Query execution | `{"syntax": "p: John Smith", "intent": "discover"}` |
| `result` | 1 | Results received | `{"source": "Linklater", "count": 5}` |
| `finding` | 4 | Finding written to watcher | `{"watcher_id": "...", "content": "..."}` |
| `complete` | 1 | Investigation complete | `{"status": "success", "iterations": 5}` |

**Total Event Emission Points**: 20

#### Event Emission Locations

1. **Investigation Start** (line 205-208)
```python
self._emit("start", {
    "tasking": self.tasking,
    "max_iterations": self.max_iterations,
})
```

2. **Phase Transitions** (line 381-385)
```python
self._emit("phase", {
    "phase": self._phase.value,
    "iteration": self._iteration + 1,
    "max_iterations": self.max_iterations,
})
```

3. **Log Messages** (multiple locations)
   - Grid state assessment (line 440-443)
   - Cognitive rotation results (line 495-520)
   - Investigation queries (line 795-798)
   - Disambiguation (line 1133-1136)
   - Writing phase (line 1333-1336)
   - Sufficiency check (line 1463-1478)
   - Finalization (line 1492-1495)

4. **Query Execution** (line 969-974)
```python
self._emit("query", {
    "syntax": primary_query,
    "intent": intent,
    "ku_quadrant": ku,
    "action_type": action_type,
})
```

5. **Results Received** (line 986-990)
```python
self._emit("result", {
    "source": "BruteSearch",
    "count": result_count,
    "query": question[:50],
})
```

6. **Findings Written** (multiple locations)
   - Surprising AND detection (line 860-867)
   - Entities of Interest (line 1362-1366)
   - Corporate Structure (line 1386-1390)
   - Connections & Relationships (line 1401-1405)

7. **Investigation Complete** (line 1522-1528)
```python
self._emit("complete", {
    "status": "success",
    "iterations": self._iteration,
    "document_id": document_id,
    "sufficiency_score": sufficiency.get("overall_score", 0),
    "watcher_count": len(watcher_stats),
})
```

### 2. CLI Stream Mode

**File**: `BACKEND/modules/SASTRE/cli.py`

#### Stream Option

Added `--stream` (or `-s`) flag to CLI:

```python
parser.add_argument("--stream", "-s", action="store_true",
                   help="Stream JSON events to stdout (for frontend)")
```

#### Stream Event Callback

Simple callback function that outputs events as JSON lines:

```python
def stream_event(event: dict) -> None:
    """Output event as JSON line for frontend consumption."""
    print(json.dumps(event), flush=True)
```

#### Callback Wiring

The callback is conditionally passed to the orchestrator:

```python
# Determine event callback for streaming mode
event_callback = stream_event if args.stream else None

# Pass to orchestrator
result = await investigate(
    tasking=args.tasking,
    project_id=args.project,
    max_iterations=args.iterations,
    autonomous=True,
    event_callback=event_callback
)
```

#### Output Handling

In stream mode, suppress normal CLI output (events already emitted):

```python
# Output results (skip in stream mode - already emitted via events)
if args.stream:
    # Final result already emitted via 'complete' event
    return
```

## Usage

### Command Line

```bash
# Stream events to stdout
python3 -m SASTRE.cli --stream "Investigate Acme Corp"

# Stream events with project ID
python3 -m SASTRE.cli --stream --project mycase "Who owns Acme Corp?"

# Resume investigation in stream mode
python3 -m SASTRE.cli --stream --resume inv_abc123 --project mycase
```

### Example Output

```json
{"type": "start", "timestamp": "2025-12-20T10:30:00.123456", "project_id": "mycase", "iteration": 0, "tasking": "Investigate Acme Corp", "max_iterations": 10}
{"type": "phase", "timestamp": "2025-12-20T10:30:00.234567", "project_id": "mycase", "iteration": 1, "phase": "ASSESS", "max_iterations": 10}
{"type": "log", "timestamp": "2025-12-20T10:30:01.345678", "project_id": "mycase", "iteration": 1, "message": "Grid state: 0 narrative, 0 subjects, 0 sources, 0 connections", "phase": "ASSESS"}
{"type": "phase", "timestamp": "2025-12-20T10:30:02.456789", "project_id": "mycase", "iteration": 1, "phase": "INVESTIGATE"}
{"type": "query", "timestamp": "2025-12-20T10:30:02.567890", "project_id": "mycase", "iteration": 1, "syntax": "c: Acme Corp", "intent": "ENRICH_ENTITY", "ku_quadrant": "trace", "action_type": "SUBJECT_GAP"}
{"type": "result", "timestamp": "2025-12-20T10:30:05.678901", "project_id": "mycase", "iteration": 1, "source": "BruteSearch", "count": 42, "query": "Acme Corp"}
{"type": "finding", "timestamp": "2025-12-20T10:30:06.789012", "project_id": "mycase", "iteration": 1, "watcher_id": "watcher_Entities of Interest", "content": "**Acme Corp** (company) - Delaware", "section": "Entities of Interest"}
{"type": "complete", "timestamp": "2025-12-20T10:30:10.890123", "project_id": "mycase", "iteration": 3, "status": "success", "document_id": "doc_123", "sufficiency_score": 0.85, "watcher_count": 7}
```

### Programmatic Usage

```python
import asyncio
from SASTRE.orchestrator.thin import investigate

collected_events = []

def my_event_handler(event: dict):
    """Custom event handler."""
    collected_events.append(event)
    print(f"[{event['type']}] {event.get('message', '')}")

async def run_investigation():
    result = await investigate(
        tasking="Investigate John Smith",
        project_id="mycase",
        max_iterations=10,
        autonomous=True,
        event_callback=my_event_handler
    )
    print(f"Collected {len(collected_events)} events")
    return result

asyncio.run(run_investigation())
```

## Event Structure

All events follow a consistent structure:

```typescript
interface SastreEvent {
  type: 'start' | 'phase' | 'log' | 'query' | 'result' | 'finding' | 'complete';
  timestamp: string;  // ISO 8601 format
  project_id: string;
  iteration: number;
  // Type-specific fields
  [key: string]: any;
}
```

### Event-Specific Fields

#### start
```typescript
{
  type: 'start',
  tasking: string,
  max_iterations: number
}
```

#### phase
```typescript
{
  type: 'phase',
  phase: 'INITIALIZING' | 'ASSESSING' | 'INVESTIGATING' | 'DISAMBIGUATING' |
         'CHECKING' | 'WRITING' | 'FINALIZING' | 'COMPLETE' | 'FAILED' | 'PAUSED',
  max_iterations: number
}
```

#### log
```typescript
{
  type: 'log',
  message: string,
  phase: string
}
```

#### query
```typescript
{
  type: 'query',
  syntax: string,          // Query in SASTRE syntax (e.g., "p: John Smith")
  intent: string,          // DISCOVER, ENRICH_ENTITY, VERIFY_CONNECTION, etc.
  ku_quadrant: string,     // discover, trace, extract, verify
  action_type: string      // NARRATIVE_GAP, SUBJECT_GAP, etc.
}
```

#### result
```typescript
{
  type: 'result',
  source: string,          // BruteSearch, Linklater, Corporella, etc.
  count: number,
  query: string
}
```

#### finding
```typescript
{
  type: 'finding',
  watcher_id: string,
  content: string,         // Markdown content
  section: string,         // Section name
  // Optional:
  type?: 'surprising_and',
  entity_a?: string,
  entity_b?: string,
  reason?: string,
  score?: number,
  source?: string
}
```

#### complete
```typescript
{
  type: 'complete',
  status: 'success' | 'error',
  iterations: number,
  document_id: string,
  sufficiency_score: number,  // 0.0 to 1.0
  watcher_count: number
}
```

## Testing

### Syntax Verification

Both files compile without errors:

```bash
cd BACKEND/modules/SASTRE
python3 -m py_compile orchestrator/thin.py
python3 -m py_compile cli.py
```

### Help Output Verification

```bash
cd BACKEND/modules
python3 -m SASTRE.cli --help | grep stream
```

Output:
```
  --stream, -s          Stream JSON events to stdout (for frontend)
```

### Event Emission Count

| Event Type | Emission Points |
|------------|-----------------|
| start      | 1               |
| phase      | 1               |
| log        | 11              |
| query      | 1               |
| result     | 1               |
| finding    | 4               |
| complete   | 1               |
| **TOTAL**  | **20**          |

## Next Steps (Phase 2)

Phase 1 (Python Event Streaming) is complete. Next phase will implement:

**Phase 2: Node.js SSE Endpoint**

Create a FastAPI endpoint that:
1. Spawns SASTRE CLI as subprocess with `--stream` flag
2. Captures stdout (JSON lines)
3. Converts to Server-Sent Events (SSE)
4. Streams to frontend in real-time

**File**: `BACKEND/api/sastre_routes.py`

```python
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

router = APIRouter()

@router.get("/sastre/investigate/stream")
async def stream_investigation(tasking: str, project_id: str = "default"):
    """Stream SASTRE investigation events via SSE."""
    async def event_generator():
        proc = await asyncio.create_subprocess_exec(
            "python3", "-m", "SASTRE.cli",
            "--stream", "--project", project_id, tasking,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        async for line in proc.stdout:
            event = json.loads(line)
            yield {
                "event": event["type"],
                "data": json.dumps(event)
            }

    return EventSourceResponse(event_generator())
```

## Summary

✅ **Phase 1 Complete**: Python event streaming fully implemented
- ThinOrchestrator emits 7 event types at 20 key points
- CLI `--stream` mode outputs events as JSON lines
- All events have consistent structure with timestamps
- Ready for frontend SSE consumption

**Next**: Implement Phase 2 (Node.js/FastAPI SSE endpoint)
