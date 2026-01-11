# SASTRE Event Streaming - Quick Reference

## CLI Usage

```bash
# Basic stream mode
python3 -m SASTRE.cli --stream "Investigate Acme Corp"

# With project ID
python3 -m SASTRE.cli --stream -p mycase "Who owns Acme Corp?"

# Resume investigation
python3 -m SASTRE.cli --stream --resume inv_123 -p mycase

# Pipe to file
python3 -m SASTRE.cli --stream "..." > events.jsonl

# Pipe to jq for filtering
python3 -m SASTRE.cli --stream "..." | jq 'select(.type == "finding")'
```

## Event Types

### start
```json
{
  "type": "start",
  "timestamp": "2025-12-20T10:30:00.123456",
  "project_id": "mycase",
  "iteration": 0,
  "tasking": "Investigate Acme Corp",
  "max_iterations": 10
}
```

### phase
```json
{
  "type": "phase",
  "timestamp": "2025-12-20T10:30:00.234567",
  "project_id": "mycase",
  "iteration": 1,
  "phase": "ASSESS",
  "max_iterations": 10
}
```

Phases: `INITIALIZING`, `ASSESSING`, `INVESTIGATING`, `DISAMBIGUATING`, `CHECKING`, `WRITING`, `FINALIZING`, `COMPLETE`

### log
```json
{
  "type": "log",
  "timestamp": "2025-12-20T10:30:01.345678",
  "project_id": "mycase",
  "iteration": 1,
  "message": "Grid state: 5 narrative, 12 subjects, 8 sources",
  "phase": "ASSESS"
}
```

### query
```json
{
  "type": "query",
  "timestamp": "2025-12-20T10:30:02.456789",
  "project_id": "mycase",
  "iteration": 1,
  "syntax": "p: John Smith",
  "intent": "ENRICH_ENTITY",
  "ku_quadrant": "trace",
  "action_type": "SUBJECT_GAP"
}
```

Query intents: `DISCOVER`, `ENRICH_ENTITY`, `DISCOVER_LOCATION`, `VERIFY_CONNECTION`

K-U quadrants: `discover` (Unknown Unknowns), `trace` (Known Unknowns), `extract` (Unknown Knowns), `verify` (Known Knowns)

### result
```json
{
  "type": "result",
  "timestamp": "2025-12-20T10:30:05.678901",
  "project_id": "mycase",
  "iteration": 1,
  "source": "BruteSearch",
  "count": 42,
  "query": "Investigate Acme Corp"
}
```

Sources: `BruteSearch`, `Linklater`, `Corporella`, `Torpedo`, `Jester`, `EYE-D`, `DomainIntel`

### finding
```json
{
  "type": "finding",
  "timestamp": "2025-12-20T10:30:06.789012",
  "project_id": "mycase",
  "iteration": 1,
  "watcher_id": "watcher_Entities of Interest",
  "content": "**Acme Corp** (company) - Delaware",
  "section": "Entities of Interest"
}
```

#### Surprising AND Finding
```json
{
  "type": "finding",
  "timestamp": "2025-12-20T10:30:06.890123",
  "project_id": "mycase",
  "iteration": 1,
  "type": "surprising_and",
  "entity_a": "John Smith",
  "entity_b": "Sanctioned Entity X",
  "reason": "CEO appears on sanctions list",
  "score": 0.95,
  "source": "https://example.com"
}
```

### complete
```json
{
  "type": "complete",
  "timestamp": "2025-12-20T10:30:10.901234",
  "project_id": "mycase",
  "iteration": 3,
  "status": "success",
  "document_id": "doc_abc123",
  "sufficiency_score": 0.85,
  "watcher_count": 7
}
```

## Programmatic Usage

```python
import asyncio
from SASTRE.orchestrator.thin import investigate

events = []

def event_handler(event):
    """Collect events."""
    events.append(event)

    # Filter by type
    if event['type'] == 'finding':
        print(f"Finding: {event['content']}")
    elif event['type'] == 'phase':
        print(f"Phase: {event['phase']} (iteration {event['iteration']})")

async def main():
    result = await investigate(
        tasking="Investigate Acme Corp",
        project_id="mycase",
        max_iterations=10,
        autonomous=True,
        event_callback=event_handler
    )

    print(f"\nCollected {len(events)} events")
    print(f"Status: {result['status']}")
    print(f"Sufficiency: {result['sufficiency']['overall_score']:.0%}")

asyncio.run(main())
```

## Event Flow

```
START → PHASE (ASSESS) → LOG (grid state) → LOG (cognitive gaps)
  → PHASE (INVESTIGATE) → LOG (executing) → QUERY → RESULT
  → FINDING (surprising_and) → PHASE (CHECK) → LOG (sufficiency)
  → PHASE (WRITE) → FINDING (entities) → FINDING (corporate)
  → FINDING (connections) → PHASE (FINALIZE) → LOG (finalizing)
  → COMPLETE
```

## Filtering Examples

### Extract only findings
```bash
python3 -m SASTRE.cli --stream "..." | jq 'select(.type == "finding")'
```

### Extract only log messages from ASSESS phase
```bash
python3 -m SASTRE.cli --stream "..." | jq 'select(.type == "log" and .phase == "ASSESS")'
```

### Count events by type
```bash
python3 -m SASTRE.cli --stream "..." | jq -r '.type' | sort | uniq -c
```

### Extract final sufficiency score
```bash
python3 -m SASTRE.cli --stream "..." | jq 'select(.type == "complete") | .sufficiency_score'
```

### Watch queries in real-time
```bash
python3 -m SASTRE.cli --stream "..." | jq 'select(.type == "query") | .syntax'
```

## TypeScript Definitions

```typescript
type SastreEventType =
  | 'start'
  | 'phase'
  | 'log'
  | 'query'
  | 'result'
  | 'finding'
  | 'complete';

type Phase =
  | 'INITIALIZING'
  | 'ASSESSING'
  | 'INVESTIGATING'
  | 'DISAMBIGUATING'
  | 'CHECKING'
  | 'WRITING'
  | 'FINALIZING'
  | 'COMPLETE'
  | 'FAILED'
  | 'PAUSED';

interface BaseSastreEvent {
  type: SastreEventType;
  timestamp: string;
  project_id: string;
  iteration: number;
}

interface StartEvent extends BaseSastreEvent {
  type: 'start';
  tasking: string;
  max_iterations: number;
}

interface PhaseEvent extends BaseSastreEvent {
  type: 'phase';
  phase: Phase;
  max_iterations: number;
}

interface LogEvent extends BaseSastreEvent {
  type: 'log';
  message: string;
  phase: string;
}

interface QueryEvent extends BaseSastreEvent {
  type: 'query';
  syntax: string;
  intent: string;
  ku_quadrant: 'discover' | 'trace' | 'extract' | 'verify';
  action_type: string;
}

interface ResultEvent extends BaseSastreEvent {
  type: 'result';
  source: string;
  count: number;
  query: string;
}

interface FindingEvent extends BaseSastreEvent {
  type: 'finding';
  watcher_id?: string;
  content: string;
  section?: string;
  // Surprising AND fields (optional)
  entity_a?: string;
  entity_b?: string;
  reason?: string;
  score?: number;
  source?: string;
}

interface CompleteEvent extends BaseSastreEvent {
  type: 'complete';
  status: 'success' | 'error';
  iterations: number;
  document_id: string;
  sufficiency_score: number;
  watcher_count: number;
}

type SastreEvent =
  | StartEvent
  | PhaseEvent
  | LogEvent
  | QueryEvent
  | ResultEvent
  | FindingEvent
  | CompleteEvent;
```

## SSE Frontend Example

```typescript
const eventSource = new EventSource(
  '/api/sastre/investigate/stream?tasking=Investigate+X&project_id=mycase'
);

// Type-specific handlers
eventSource.addEventListener('start', (e) => {
  const event: StartEvent = JSON.parse(e.data);
  console.log('Starting:', event.tasking);
});

eventSource.addEventListener('phase', (e) => {
  const event: PhaseEvent = JSON.parse(e.data);
  updateProgressBar(event.phase, event.iteration, event.max_iterations);
});

eventSource.addEventListener('log', (e) => {
  const event: LogEvent = JSON.parse(e.data);
  appendToConsole(`[${event.phase}] ${event.message}`);
});

eventSource.addEventListener('query', (e) => {
  const event: QueryEvent = JSON.parse(e.data);
  showQuery(event.syntax, event.intent);
});

eventSource.addEventListener('result', (e) => {
  const event: ResultEvent = JSON.parse(e.data);
  updateCounter(event.source, event.count);
});

eventSource.addEventListener('finding', (e) => {
  const event: FindingEvent = JSON.parse(e.data);
  if (event.entity_a && event.entity_b) {
    // Surprising AND
    highlightSurprise(event.entity_a, event.entity_b, event.reason);
  } else {
    // Normal finding
    appendToSection(event.section, event.content);
  }
});

eventSource.addEventListener('complete', (e) => {
  const event: CompleteEvent = JSON.parse(e.data);
  showComplete(event.iterations, event.sufficiency_score);
  eventSource.close();
});

// Error handling
eventSource.onerror = (error) => {
  console.error('SSE error:', error);
  eventSource.close();
};
```

## Event Counts (Typical Investigation)

| Event Type | Min | Typical | Max |
|------------|-----|---------|-----|
| start | 1 | 1 | 1 |
| phase | iterations | 5-10 | iterations |
| log | iterations * 2 | 20-40 | iterations * 11 |
| query | actions | 10-30 | actions |
| result | queries | 10-30 | queries |
| finding | entities | 20-100 | entities * 3 |
| complete | 1 | 1 | 1 |
| **Total** | ~15 | **65-210** | ~500+ |

## Performance Notes

- Events are emitted immediately (no buffering)
- Timestamps are ISO 8601 UTC
- JSON output uses `flush=True` for real-time streaming
- No event coalescing (every action emits independently)
- Average event size: 200-500 bytes
- Typical investigation: 65-210 events over 30-180 seconds

## Error Handling

```python
def _emit(self, event_type: str, data: Optional[Dict[str, Any]] = None):
    """Emit event for frontend streaming consumption."""
    if not self.event_callback:
        return

    try:
        self.event_callback(event)
    except Exception as e:
        logger.warning(f"Event callback error: {e}")
        # Orchestrator continues even if callback fails
```

**Guarantee**: Callback failures never crash the orchestrator.
