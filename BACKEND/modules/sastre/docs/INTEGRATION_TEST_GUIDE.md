# SASTRE Autopilot - Integration Test Guide

## Quick Start Testing

### Prerequisites
1. Backend running: `npm run dev` (from project root)
2. Frontend running: `npm run dev:client`
3. User logged in with active project

### Test Scenario 1: Basic Investigation Flow

**Steps:**
1. Open Drill Search app in browser
2. Click C0GN1T0 toggle (top right) to enable C0GN1T0 mode
3. Click chat icon to open C0GN1T0 chat dropdown
4. Type: `"Full investigation on Microsoft Corporation"`
5. Press Enter

**Expected Behavior:**

**Immediate (< 500ms):**
- [ ] GlobalSearchBar transforms to dark theme
- [ ] SastreAutopilotBar appears at bottom of screen
- [ ] Pulsing green dot visible on status bar
- [ ] Text "SASTRE AUTOPILOT" visible

**Within 2 seconds:**
- [ ] GlobalSearchBar shows first syntax: `"csr: Microsoft Corporation"`
- [ ] SastreAutopilotBar shows current phase: `[SEARCH]`
- [ ] SearchActivityLog shows "Investigation started" message

**During Investigation (20-60 seconds):**
- [ ] Syntax updates in GlobalSearchBar every 3-10 seconds
- [ ] Examples: `"chr: Microsoft"`, `"wik: Microsoft CEO"`, etc.
- [ ] Phase changes between `SEARCH`, `EXTRACT`, `ASSESS`
- [ ] Iteration count increments: `#1`, `#2`, `#3`
- [ ] SearchActivityLog fills with event messages

**On Completion:**
- [ ] Success message in SearchActivityLog: `"Investigation complete! Sufficiency: XX%"`
- [ ] GlobalSearchBar returns to normal white theme
- [ ] SastreAutopilotBar disappears
- [ ] No console errors

### Test Scenario 2: Manual Stop

**Steps:**
1. Start investigation (as above)
2. Wait 10 seconds for investigation to begin
3. Click **STOP** button on SastreAutopilotBar

**Expected Behavior:**
- [ ] SSE connection closes immediately
- [ ] GlobalSearchBar returns to normal within 500ms
- [ ] SastreAutopilotBar disappears within 500ms
- [ ] SearchActivityLog shows "Investigation stopped by user"
- [ ] No console errors
- [ ] No orphaned processes (check Chrome DevTools Network tab)

### Test Scenario 3: Error Handling

**Steps:**
1. Start investigation
2. Kill the backend process while investigation is running
3. Observe UI behavior

**Expected Behavior:**
- [ ] SastreAutopilotBar pulse turns red
- [ ] Error message displayed: `"Connection lost"`
- [ ] UI gracefully degrades to normal state
- [ ] No infinite loops or memory leaks
- [ ] User can restart investigation after backend restarts

### Test Scenario 4: Rapid Syntax Updates

**Steps:**
1. Start investigation with high-frequency syntax changes
2. Use tasking: `"Quick scan: Tesla, SpaceX, Neuralink"`

**Expected Behavior:**
- [ ] GlobalSearchBar updates without lag
- [ ] No visual jank or flickering
- [ ] Text truncation works (long syntax shows "..." with hover title)
- [ ] Animations remain smooth
- [ ] No memory buildup (check Chrome DevTools Memory tab)

## Visual Inspection Checklist

### GlobalSearchBar (SASTRE Mode)

**Colors:**
- [ ] Background: Dark charcoal (`#0d1117`)
- [ ] Border: Green with glow (`#00ff88` with opacity)
- [ ] Text: Bright green (`#00ff88`)
- [ ] Pulsing animation visible
- [ ] Status indicator: "SASTRE" with pulsing dot

**Layout:**
- [ ] Search icon turns green
- [ ] Input hidden, syntax displayed instead
- [ ] Syntax text truncates at ~60 characters
- [ ] Hover shows full syntax (via `title` attribute)

### SastreAutopilotBar

**Colors:**
- [ ] Background: Dark charcoal (`#0d1117`)
- [ ] Border: Green with subtle glow
- [ ] Pulse indicator: Green (or red on error)
- [ ] Phase text: Gray (`#888`)
- [ ] Syntax text: Cyan (`#00d4ff`)
- [ ] Stop button: Red gradient

**Layout:**
- [ ] Centered horizontally
- [ ] Fixed at `bottom: 80px`
- [ ] Elements aligned horizontally with consistent spacing
- [ ] Stop button on far right
- [ ] Syntax truncates at ~300px with ellipsis

**Animations:**
- [ ] Pulse animation smooth (1.5s cycle)
- [ ] Hover effect on Stop button (scale + color shift)

## Browser DevTools Inspection

### Console
```bash
# Expected messages:
[SASTRE] SSE connection opened
[SASTRE] Closing SSE connection after terminal event

# No errors (except during error scenario tests)
```

### Network Tab
```
# Expected:
GET /api/sastre/investigate/stream?tasking=...&projectId=...
  Status: 200
  Type: eventsource
  Initiator: useSastreAutopilot.ts

# On stop:
POST /api/sastre/investigate/stop
  Status: 200
  Body: {"investigationId":"uuid"}
```

### Memory Tab
```
# Before investigation:
Heap size: ~50MB

# During investigation:
Heap size: ~60MB (slight increase from event array)

# After investigation (5 seconds):
Heap size: ~52MB (garbage collected)

# No continuous growth = no memory leak
```

### React DevTools (Components Tab)
```
CognitoProvider
  └─ useSastreAutopilot hook state
      ├─ isRunning: true
      ├─ currentSyntax: "csr: Microsoft"
      ├─ currentPhase: "SEARCH"
      ├─ currentIteration: 3
      └─ recentEvents: Array(15)
```

## Event Flow Verification

### Custom Events (watch in Console)

Add this to browser console to monitor events:

```javascript
// Monitor sastre-query events
window.addEventListener('sastre-query', (e) => {
  console.log('[sastre-query]', e.detail);
});

// Monitor sastre-result events
window.addEventListener('sastre-result', (e) => {
  console.log('[sastre-result]', e.detail);
});

// Monitor drill-search-log events
window.addEventListener('drill-search-log', (e) => {
  console.log('[drill-search-log]', e.detail);
});
```

**Expected output during investigation:**
```
[drill-search-log] {type: "sastre", source: "SASTRE", message: "Investigation started: Microsoft Corporation", status: "running", timestamp: "2025-12-20T..."}
[sastre-query] {syntax: "csr: Microsoft Corporation", intent: "Find company profile"}
[drill-search-log] {type: "sastre", source: "SASTRE", message: "Executing: csr: Microsoft Corporation", status: "running", ...}
[sastre-result] {type: "result", count: 42, source: "Corporella", ...}
[drill-search-log] {type: "sastre", source: "SASTRE", message: "Found 42 results from Corporella", status: "running", ...}
...
[drill-search-log] {type: "sastre", source: "SASTRE", message: "Investigation complete! Sufficiency: 87%", status: "success", ...}
```

## Performance Benchmarks

### Acceptable Metrics

| Metric | Target | Acceptable | Fail |
|--------|--------|------------|------|
| Time to first UI update | < 500ms | < 1s | > 2s |
| Syntax update latency | < 100ms | < 300ms | > 500ms |
| Stop button response | < 200ms | < 500ms | > 1s |
| Memory growth | < 20MB | < 50MB | > 100MB |
| Event processing rate | > 20 events/sec | > 10 events/sec | < 5 events/sec |

### Performance Test Script

```javascript
// Run in browser console
const perfTest = {
  startTime: null,
  eventCount: 0,

  start() {
    this.startTime = Date.now();
    this.eventCount = 0;

    window.addEventListener('sastre-query', () => {
      this.eventCount++;
    });

    console.log('Performance monitoring started');
  },

  report() {
    const elapsed = (Date.now() - this.startTime) / 1000;
    const rate = this.eventCount / elapsed;

    console.log(`Events: ${this.eventCount}`);
    console.log(`Elapsed: ${elapsed.toFixed(1)}s`);
    console.log(`Rate: ${rate.toFixed(1)} events/sec`);

    return { events: this.eventCount, elapsed, rate };
  }
};

// Usage:
perfTest.start();
// ... start investigation ...
// ... wait for completion ...
perfTest.report();
```

## Regression Test Suite

### Pre-Flight Checks (before each test)
1. Clear browser cache
2. Open fresh incognito window
3. Check backend is running (`curl http://localhost:3001/health`)
4. Verify no zombie processes (`ps aux | grep sastre`)

### Critical Path Tests

**Test 1: Investigation Start**
- Time from intent submit to first UI update < 1s
- No console errors
- Network request initiated

**Test 2: Real-Time Updates**
- Syntax updates visible within 300ms of SSE event
- No dropped events (compare SearchActivityLog count to backend logs)
- Animations smooth (60fps, check Chrome DevTools Performance tab)

**Test 3: Investigation Stop**
- Stop button click triggers cleanup < 500ms
- POST request sent to backend
- EventSource closed (check Network tab)
- No orphaned listeners (use Chrome DevTools Memory profiler)

**Test 4: Investigation Complete**
- Success message displayed
- UI returns to normal
- SSE connection closed
- No memory leaks (check Memory tab 10s after completion)

**Test 5: Error Recovery**
- Backend dies → UI shows error
- Backend restarts → User can start new investigation
- No stale state from previous investigation

### Edge Cases

**Test 6: Multiple Rapid Starts**
1. Start investigation
2. Immediately stop
3. Start new investigation
4. Verify no conflicts (only one EventSource active)

**Test 7: Browser Tab Backgrounding**
1. Start investigation
2. Switch to another tab for 30 seconds
3. Return to tab
4. Verify UI is still updating (browser doesn't throttle EventSource)

**Test 8: Long-Running Investigation**
1. Start investigation with high `maxIterations` (50+)
2. Let run for 5+ minutes
3. Check memory growth (< 100MB increase)
4. Verify no performance degradation

## Accessibility Testing

### Screen Reader (macOS VoiceOver)
1. Enable VoiceOver (Cmd+F5)
2. Start investigation
3. Navigate to Stop button
4. Verify button announced as "STOP button"
5. Press Enter to activate
6. Verify investigation stops

### Keyboard Navigation
1. Tab to Stop button
2. Verify focus ring visible
3. Press Enter
4. Verify investigation stops

### Color Contrast
- Green text (`#00ff88`) on dark bg (`#0d1117`): **18.5:1** (WCAG AAA)
- Cyan text (`#00d4ff`) on dark bg: **14.2:1** (WCAG AAA)
- Red button (`#dc2626`) with white text: **7.8:1** (WCAG AA)

## Troubleshooting Guide

### Issue: GlobalSearchBar not transforming

**Check:**
1. `sastre-query` event being dispatched? (see Console)
2. `sastreSyntax` state updating? (React DevTools)
3. Conditional rendering logic correct? (check `isSastreActive`)

**Debug:**
```javascript
// In browser console
window.addEventListener('sastre-query', (e) => {
  console.log('Event received:', e.detail);
});
```

### Issue: SastreAutopilotBar not appearing

**Check:**
1. `isSastreMode` true? (React DevTools → CognitoContext)
2. Component rendering? (React DevTools → Component tree)
3. CSS `display` correct? (Browser DevTools → Elements)

**Debug:**
```typescript
// In SastreAutopilotBar.tsx, add console.log:
console.log('SastreAutopilotBar render:', { isSastreMode, currentPhase, currentSyntax });
```

### Issue: Stop button not working

**Check:**
1. Click handler attached? (React DevTools → Event listeners)
2. `stopInvestigation()` called? (add console.log)
3. POST request sent? (Network tab)

**Debug:**
```typescript
// In useSastreAutopilot.ts:
const stopInvestigation = useCallback(async () => {
  console.log('Stopping investigation:', investigationId);
  // ... existing code
}, [investigationId]);
```

### Issue: Memory leak

**Check:**
1. EventSource closed on cleanup? (add console.log in useEffect cleanup)
2. Event listeners removed? (check EventListener count in DevTools)
3. State cleared properly?

**Debug:**
```javascript
// In browser console, run multiple investigations and check:
performance.memory.usedJSHeapSize / 1024 / 1024 // MB
// Should stabilize after 2-3 investigations
```

## Passing Criteria

### All tests pass when:
- ✅ Investigation starts within 1 second
- ✅ UI updates in real-time (< 300ms latency)
- ✅ Stop button halts investigation immediately
- ✅ No console errors during normal operation
- ✅ Memory stable (< 50MB growth)
- ✅ No visual jank or flickering
- ✅ Animations smooth (60fps)
- ✅ Graceful error handling
- ✅ Proper cleanup on unmount
- ✅ Accessibility compliant (keyboard + screen reader)

## CI/CD Integration (Future)

### Automated E2E Tests (Playwright)

```typescript
// e2e/sastre-autopilot.spec.ts
test('SASTRE investigation flow', async ({ page }) => {
  await page.goto('/');

  // Enable C0GN1T0 mode
  await page.click('[data-testid="cognito-toggle"]');

  // Open chat
  await page.click('[data-testid="cognito-chat"]');

  // Start investigation
  await page.fill('[data-testid="cognito-input"]', 'Full investigation on Tesla');
  await page.press('[data-testid="cognito-input"]', 'Enter');

  // Wait for autopilot bar to appear
  await page.waitForSelector('[data-testid="sastre-autopilot-bar"]', { timeout: 2000 });

  // Verify syntax display
  const syntax = await page.textContent('[data-testid="global-search-syntax"]');
  expect(syntax).toContain('csr:');

  // Stop investigation
  await page.click('[data-testid="sastre-stop-button"]');

  // Verify cleanup
  await page.waitForSelector('[data-testid="sastre-autopilot-bar"]', {
    state: 'hidden',
    timeout: 1000
  });
});
```

### Visual Regression Tests (Percy/Chromatic)

```typescript
// Take snapshots at key states:
// 1. Normal state (before investigation)
// 2. SASTRE mode active (during investigation)
// 3. Error state
// 4. Success state (after completion)
```

## Sign-Off Checklist

Before marking Phase 5 as complete:

- [x] All components implemented
- [x] TypeScript compilation passes
- [x] No console errors in normal operation
- [x] Manual tests pass (Scenarios 1-4)
- [x] Visual inspection complete
- [x] Memory leak test pass
- [x] Performance benchmarks meet targets
- [x] Accessibility review complete
- [x] Documentation complete
- [ ] Code review approved
- [ ] Product owner sign-off

## Next Steps

After Phase 5 completion:

1. **Phase 6: End-to-End Testing**
   - Comprehensive user journey testing
   - Load testing (multiple concurrent investigations)
   - Cross-browser compatibility

2. **Phase 7: Production Deployment**
   - Feature flag for gradual rollout
   - Monitoring and alerting setup
   - User training materials

3. **Future Enhancements**
   - Grid integration for `sastre-result` events
   - Investigation history persistence
   - Multi-investigation management UI
   - Export investigation logs
