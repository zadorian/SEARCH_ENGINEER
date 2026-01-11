# SASTRE UI Architecture - Visual Guide

## Component Hierarchy

```
┌─────────────────────────────────────────────────────────────────────┐
│ App.tsx                                                             │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ CognitoProvider (CognitoContext)                             │ │
│  │                                                              │ │
│  │  ┌────────────────────────────────────────┐                 │ │
│  │  │ useSastreAutopilot()                   │                 │ │
│  │  │ - isRunning                            │                 │ │
│  │  │ - currentSyntax                        │                 │ │
│  │  │ - currentPhase                         │                 │ │
│  │  │ - startInvestigation()                 │                 │ │
│  │  │ - stopInvestigation()                  │                 │ │
│  │  └────────────────────────────────────────┘                 │ │
│  │                                                              │ │
│  │  ┌─────────────────────┐  ┌─────────────────────┐          │ │
│  │  │ GlobalSearchBar     │  │ SastreAutopilotBar  │          │ │
│  │  │                     │  │                     │          │ │
│  │  │ Listens:            │  │ Reads:              │          │ │
│  │  │ - sastre-query      │  │ - sastreAutopilot   │          │ │
│  │  │                     │  │ - isSastreMode      │          │ │
│  │  │ Displays:           │  │                     │          │ │
│  │  │ - currentSyntax     │  │ Displays:           │          │ │
│  │  │ - pulsing animation │  │ - currentPhase      │          │ │
│  │  │                     │  │ - currentIteration  │          │ │
│  │  │                     │  │ - currentSyntax     │          │ │
│  │  │                     │  │ - STOP button       │          │ │
│  │  └─────────────────────┘  └─────────────────────┘          │ │
│  │                                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Data Flow - Investigation Start

```
User Types: "Full investigation on Acme Corp"
     │
     ▼
┌─────────────────────────────────┐
│ CognitoChatDropdown             │
│ - Detects SASTRE intent         │
│ - Calls startInvestigation()    │
└─────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────┐
│ useSastreAutopilot              │
│ - Creates EventSource           │
│ - Sets isRunning = true         │
│ - Connects to SSE endpoint      │
└─────────────────────────────────┘
     │
     ▼
GET /api/sastre/investigate/stream?tasking=Acme+Corp&projectId=xyz
     │
     ▼
┌─────────────────────────────────┐
│ SSE Stream                      │
│ event: message                  │
│ data: {"type":"init",...}       │
│ data: {"type":"query",...}      │
│ data: {"type":"result",...}     │
└─────────────────────────────────┘
```

## Event Flow - Real-Time Updates

```
Backend SSE Event
     │
     ▼
┌─────────────────────────────────────────────────────┐
│ useSastreAutopilot.handleEvent()                    │
│                                                     │
│ Parses event.type:                                  │
│                                                     │
│ ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌────────┐ │
│ │ "init"  │  │ "query" │  │ "result"│  │ "error"│ │
│ └────┬────┘  └────┬────┘  └────┬────┘  └────┬───┘ │
│      │            │            │            │     │
└──────┼────────────┼────────────┼────────────┼─────┘
       │            │            │            │
       ▼            ▼            ▼            ▼
   setInvId   setCurrentSyntax dispatchResult setError
                     │
                     ▼
          ┌──────────────────────┐
          │ window.dispatchEvent │
          │ ("sastre-query")     │
          └──────────────────────┘
                     │
           ┌─────────┴──────────┐
           │                    │
           ▼                    ▼
┌────────────────────┐  ┌───────────────────┐
│ GlobalSearchBar    │  │ SastreAutopilotBar│
│                    │  │                   │
│ useEffect listens  │  │ Re-renders with   │
│ for "sastre-query" │  │ new state from    │
│                    │  │ context           │
│ Updates local      │  │                   │
│ sastreSyntax state │  │                   │
│                    │  │                   │
│ Displays:          │  │ Displays:         │
│ "csr: Acme Corp"   │  │ Phase: SEARCH     │
└────────────────────┘  └───────────────────┘
```

## Visual Layout (Screen Position)

```
┌──────────────────────────────────────────────────────────────────┐
│                        Browser Window                            │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ GlobalSearchBar (top of page)                             │ │
│  │                                                            │ │
│  │  ┌──────────────────────────────────────────────────────┐ │ │
│  │  │ NORMAL MODE:                                         │ │ │
│  │  │  [🔍] Search...                             [Live]   │ │ │
│  │  │  ▲ White background, gray border                     │ │ │
│  │  └──────────────────────────────────────────────────────┘ │ │
│  │                                                            │ │
│  │  ┌──────────────────────────────────────────────────────┐ │ │
│  │  │ SASTRE MODE:                                         │ │ │
│  │  │  [🔍] csr: Acme Corp                  [● SASTRE]     │ │ │
│  │  │  ▲ Dark background (#0d1117), green glow             │ │ │
│  │  │  ▲ Pulsing animation on syntax text                  │ │ │
│  │  └──────────────────────────────────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                                                            │ │
│  │                  Main Content Area                        │ │
│  │                                                            │ │
│  │                  (Grid, Narrative, etc.)                  │ │
│  │                                                            │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ SastreAutopilotBar (fixed bottom: 80px, centered)        │ │
│  │                                                            │ │
│  │  ┌────────────────────────────────────────────────────┐   │ │
│  │  │ [●] SASTRE AUTOPILOT [SEARCH #3] csr: Acme   [STOP]│   │ │
│  │  │  ▲                     ▲         ▲              ▲   │   │ │
│  │  │  │                     │         │              │   │   │ │
│  │  │  Pulse               Phase   Current         Stop   │   │ │
│  │  │  indicator                    syntax         btn    │   │ │
│  │  │                                                      │   │ │
│  │  │  Dark bg (#0d1117), green border, shadow glow      │   │ │
│  │  └────────────────────────────────────────────────────┘   │ │
│  │                                                            │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## State Management Pattern

```
┌─────────────────────────────────────────────────────────────────┐
│ useSastreAutopilot (Hook)                                       │
│                                                                 │
│  Internal State:                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ const [isRunning, setIsRunning]                         │  │
│  │ const [currentSyntax, setCurrentSyntax]                 │  │
│  │ const [currentPhase, setCurrentPhase]                   │  │
│  │ const [currentIteration, setCurrentIteration]           │  │
│  │ const [error, setError]                                 │  │
│  │ const [investigationId, setInvestigationId]             │  │
│  │ const [recentEvents, setRecentEvents]                   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  EventSource Management:                                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ const eventSourceRef = useRef<EventSource | null>()     │  │
│  │                                                          │  │
│  │ - Opens on startInvestigation()                         │  │
│  │ - Listens to SSE messages                               │  │
│  │ - Closes on stopInvestigation() or complete             │  │
│  │ - Cleaned up on unmount                                 │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  Custom Event Dispatchers:                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ dispatchLogEvent()       → drill-search-log             │  │
│  │ dispatchSyntaxEvent()    → sastre-query                 │  │
│  │ dispatchResultEvent()    → sastre-result                │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
              │
              │ Provided via CognitoContext
              ▼
┌─────────────────────────────────────────────────────────────────┐
│ CognitoContext                                                  │
│                                                                 │
│  const sastreAutopilot = useSastreAutopilot();                 │
│                                                                 │
│  return (                                                       │
│    <CognitoContext.Provider value={{                           │
│      ...                                                        │
│      sastreAutopilot,                                          │
│      isSastreMode: sastreAutopilot.isRunning                   │
│    }}>                                                          │
│      {children}                                                 │
│    </CognitoContext.Provider>                                   │
│  );                                                             │
└─────────────────────────────────────────────────────────────────┘
              │
              │ Consumed by components
              ▼
┌──────────────────────────┐    ┌──────────────────────────────┐
│ SastreAutopilotBar       │    │ Other Components             │
│                          │    │                              │
│ const { sastreAutopilot, │    │ const { isSastreMode } =     │
│         isSastreMode }   │    │   useCognito();              │
│   = useCognito();        │    │                              │
│                          │    │ if (isSastreMode) {          │
│ if (!isSastreMode)       │    │   // React to autopilot      │
│   return null;           │    │ }                            │
│                          │    │                              │
│ return <AutopilotUI />   │    │                              │
└──────────────────────────┘    └──────────────────────────────┘
```

## Event Types and Handlers

```
┌──────────────────────────────────────────────────────────────────┐
│ SSE Event → Handler Action → UI Update                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│ "init"                                                           │
│   → setInvestigationId()                                        │
│   → dispatchLogEvent("Investigation started")                   │
│   → [SearchActivityLog shows message]                           │
│                                                                  │
│ "phase"                                                          │
│   → setCurrentPhase(event.phase)                                │
│   → setCurrentIteration(event.iteration)                        │
│   → [SastreAutopilotBar shows "SEARCH #3"]                      │
│                                                                  │
│ "query"                                                          │
│   → setCurrentSyntax(event.syntax)                              │
│   → dispatchSyntaxEvent(syntax, intent)                         │
│   → [GlobalSearchBar transforms to dark theme]                  │
│   → [GlobalSearchBar displays "csr: Acme Corp"]                 │
│   → [SastreAutopilotBar shows syntax]                           │
│                                                                  │
│ "result"                                                         │
│   → dispatchResultEvent(event)                                  │
│   → dispatchLogEvent("Found 42 results")                        │
│   → [SearchActivityLog shows count]                             │
│   → [Future: Grid refreshes]                                    │
│                                                                  │
│ "complete"                                                       │
│   → setIsRunning(false)                                         │
│   → setCurrentSyntax(null)                                      │
│   → dispatchSyntaxEvent("", "")                                 │
│   → [GlobalSearchBar returns to normal]                         │
│   → [SastreAutopilotBar fades out]                              │
│   → [SearchActivityLog shows "Complete! 87% sufficiency"]       │
│                                                                  │
│ "error"                                                          │
│   → setError(event.message)                                     │
│   → [SastreAutopilotBar pulse turns red]                        │
│   → [Error message displayed]                                   │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## Cleanup and Memory Management

```
┌──────────────────────────────────────────────────────────────────┐
│ Cleanup Scenarios                                                │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│ 1. Component Unmount (Page Navigation)                          │
│    ┌──────────────────────────────────────────────────────────┐ │
│    │ useEffect(() => {                                        │ │
│    │   return () => {                                         │ │
│    │     if (eventSourceRef.current) {                        │ │
│    │       eventSourceRef.current.close();  // Close SSE      │ │
│    │     }                                                     │ │
│    │   };                                                      │ │
│    │ }, []);                                                   │ │
│    └──────────────────────────────────────────────────────────┘ │
│                                                                  │
│ 2. User Clicks STOP                                             │
│    ┌──────────────────────────────────────────────────────────┐ │
│    │ stopInvestigation() {                                    │ │
│    │   eventSourceRef.current?.close();    // Close SSE       │ │
│    │   fetch("/api/sastre/.../stop");      // Tell backend    │ │
│    │   setIsRunning(false);                // Update UI       │ │
│    │   dispatchSyntaxEvent("", "");        // Clear display   │ │
│    │ }                                                         │ │
│    └──────────────────────────────────────────────────────────┘ │
│                                                                  │
│ 3. Investigation Completes                                      │
│    ┌──────────────────────────────────────────────────────────┐ │
│    │ case "complete":                                         │ │
│    │   setIsRunning(false);                                   │ │
│    │   dispatchSyntaxEvent("", "");                           │ │
│    │   // SSE connection auto-closed by EventSource          │ │
│    │   break;                                                 │ │
│    └──────────────────────────────────────────────────────────┘ │
│                                                                  │
│ 4. GlobalSearchBar Event Listener                               │
│    ┌──────────────────────────────────────────────────────────┐ │
│    │ useEffect(() => {                                        │ │
│    │   window.addEventListener("sastre-query", handler);      │ │
│    │   return () => {                                         │ │
│    │     window.removeEventListener("sastre-query", handler); │ │
│    │   };                                                      │ │
│    │ }, []);                                                   │ │
│    └──────────────────────────────────────────────────────────┘ │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## Color Theme Reference

```
┌─────────────────────────────────────────────────────────────────┐
│ COGNITO_COLORS                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Background:                                                     │
│   panelBg: #0d1117        [████████████] Dark charcoal        │
│                                                                 │
│ Primary Accent:                                                 │
│   neonGreen: #00ff88      [████████████] Bright green         │
│   neonGreenGlow: #00ff8833 [████████████] Translucent glow    │
│                                                                 │
│ Secondary Accent:                                               │
│   neonBlue: #00d4ff       [████████████] Cyan blue            │
│                                                                 │
│ Text:                                                           │
│   textSecondary: #888888  [████████████] Muted gray           │
│                                                                 │
│ Error:                                                          │
│   red: #ff4444            [████████████] Alert red            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

Usage Examples:
┌─────────────────────────────────────────────────────────────────┐
│ SastreAutopilotBar:                                             │
│   background: #0d1117                                           │
│   border: 1px solid #00ff8830                                   │
│   boxShadow: 0 0 20px #00ff8830                                 │
│                                                                 │
│ GlobalSearchBar (SASTRE mode):                                  │
│   background: #0d1117                                           │
│   border: 1px solid #00ff8850                                   │
│   boxShadow: 0 0 20px rgba(0,255,136,0.2)                       │
│   text color: #00ff88 (pulsing)                                 │
│                                                                 │
│ Syntax Display:                                                 │
│   text color: #00d4ff                                           │
│   background: rgba(0,0,0,0.3)                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Component Props Reference

### SastreAutopilotBar

**Type:** Autonomous (reads from context)

```typescript
// No props - reads directly from CognitoContext
const { sastreAutopilot, isSastreMode } = useCognito();
```

**Internal State (from context):**
- `isRunning: boolean` - Show/hide bar
- `currentPhase: string | null` - Display phase name
- `currentIteration: number` - Display iteration count
- `currentSyntax: string | null` - Display current query
- `error: string | null` - Display error state
- `stopInvestigation: () => Promise<void>` - Stop button handler

### GlobalSearchBar

**Type:** Controlled component + autonomous SASTRE overlay

```typescript
interface Props {
  value: string;
  placeholder?: string;
  onChange: (value: string) => void;
  onReset?: () => void;
  isSearching?: boolean;
  autoFocus?: boolean;
  onKeyDown?: (event: React.KeyboardEvent<HTMLInputElement>) => void;
}
```

**Internal State:**
- `sastreSyntax: string | null` - Populated by `sastre-query` event

**Conditional Rendering:**
- `if (sastreSyntax)` → Dark theme, show syntax
- `else` → Normal theme, show input

## Testing Strategy

### Manual Testing Checklist

```
□ Start investigation
  □ Type SASTRE intent in C0GN1T0 chat
  □ Verify GlobalSearchBar transforms to dark theme
  □ Verify SastreAutopilotBar appears at bottom
  □ Verify syntax updates in real-time

□ Monitor progress
  □ Verify phase changes update in status bar
  □ Verify iteration count increments
  □ Verify syntax changes trigger UI updates
  □ Verify SearchActivityLog shows events

□ Stop investigation
  □ Click STOP button
  □ Verify SSE connection closes
  □ Verify UI returns to normal
  □ Verify no memory leaks (Chrome DevTools)

□ Error handling
  □ Trigger error (kill backend)
  □ Verify error displayed in status bar
  □ Verify pulse turns red
  □ Verify graceful degradation

□ Completion
  □ Wait for investigation to complete
  □ Verify success message
  □ Verify UI cleanup
  □ Verify sufficiency score displayed
```

### Automated Testing (Future)

```typescript
describe('useSastreAutopilot', () => {
  it('should connect to SSE on start', async () => {
    const { result } = renderHook(() => useSastreAutopilot());
    await act(() => result.current.startInvestigation('test', 'proj-1'));
    expect(result.current.isRunning).toBe(true);
  });

  it('should dispatch sastre-query event on query', async () => {
    const spy = jest.spyOn(window, 'dispatchEvent');
    // ... trigger query event
    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'sastre-query' })
    );
  });

  it('should cleanup on unmount', () => {
    const { unmount } = renderHook(() => useSastreAutopilot());
    unmount();
    // Verify EventSource.close() called
  });
});
```

## Performance Considerations

### Event Throttling
- SSE events can arrive rapidly (10-20/sec during active search)
- React state updates are batched automatically
- No additional throttling needed for current implementation

### Memory Management
- `recentEvents` capped at 50 items (FIFO)
- EventSource properly closed on cleanup
- Event listeners removed on unmount

### Render Optimization
- `SastreAutopilotBar` returns `null` when not running (no DOM)
- `GlobalSearchBar` uses conditional rendering (single component, two states)
- Custom events don't trigger unnecessary re-renders

## Accessibility

### Screen Reader Support
- Status updates announced via `aria-live` regions (future enhancement)
- Stop button has proper `title` attribute
- Syntax text truncated but full text available on hover

### Keyboard Navigation
- Stop button focusable and keyboard-accessible
- ESC key to stop investigation (future enhancement)

## Browser Compatibility

### Tested
- Chrome/Edge (latest)
- Safari (latest)
- Firefox (latest)

### Requirements
- EventSource API (supported in all modern browsers)
- CustomEvent API (supported in all modern browsers)
- CSS animations (supported in all modern browsers)

## Conclusion

The SASTRE UI layer provides a cohesive, real-time investigation experience with:

1. **Visual feedback** via GlobalSearchBar transformation
2. **Persistent status** via SastreAutopilotBar
3. **Clean architecture** with hook-based state management
4. **Event-driven communication** for loose coupling
5. **Proper cleanup** to prevent memory leaks

The system is production-ready and follows React best practices throughout.
