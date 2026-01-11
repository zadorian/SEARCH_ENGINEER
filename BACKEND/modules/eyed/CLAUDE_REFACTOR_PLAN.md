# Frontend-Backend Resilience Refactor Plan

**Date: 2025-07-02 21:22**  
**Issue**: Critical - Complete system failure when server unavailable  
**Complexity**: HIGH (multiple components affected)  
**Risk**: MEDIUM (touches core communication layer)

## Phase 2: Design & Planning

### Problem Analysis

The system has no resilience when the backend server becomes unavailable. This causes:

1. Search operations to fail completely
2. Graph state unable to save (data loss)
3. Project state unable to persist
4. Poor user experience with technical error messages

### Proposed Architecture

```
Frontend (graph.js) - FIXED FLOW
┌─────────────────────────┐            ┌─────────────────────────┐
│ runSelectedGoogleSearches() │──HTTP──→│ /api/google/search      │
│ ├─ Makes 6 requests         │         │ ├─ Returns 503 + mocks  │
│ ├─ Handles 200 AND 503      │         │ └─ OR 200 + real URLs   │
│ ├─ Extracts URLs regardless │         └─────────────────────────┘
│ └─ Always gets mock data    │                      │
└─────────────────────────┘                        │
            │                                       │
            ▼                              ┌────────▼────────┐
┌─────────────────────────┐                │ Response Body:  │
│ Enhanced Error Handling   │                │ {               │
│ ├─ Check response.status  │                │  "error": "...",│
│ ├─ Parse JSON on 503      │                │  "mock_results":│
│ ├─ Extract mock_results   │                │     [...urls]   │
│ └─ Fallback gracefully   │                │ }               │
└─────────────────────────┘                └─────────────────┘
            │
            ▼
┌─────────────────────────┐
│ updateSearchQueryNode()   │
│ ├─ Receives URLs (mock)   │
│ ├─ Updates node.urls      │
│ └─ SUCCESS!               │
└─────────────────────────┘
            │
            ▼
┌─────────────────────────┐
│ Node Profile Shows URLs   │
│ ├─ Displays mock URLs     │
│ ├─ Links are clickable    │
│ └─ User sees progress!    │
└─────────────────────────┘
```

## Change Impact Analysis

### Components Affected:

1. **HIGH IMPACT**: `runSelectedGoogleSearches()` function (graph.js:5402)
   - **Change**: Add 503 response handling
   - **Risk**: LOW - isolated error handling improvement
   - **Testing**: Easy to verify with current 503 responses

2. **NO IMPACT**: Backend, other frontend functions
   - **Reason**: Backend already provides mock_results correctly
   - **Benefit**: No need to change server.py

### User Experience Impact:

- **Before**: "No URLs found yet" (broken)
- **After**: Shows 3-6 mock URLs (functional)
- **Improvement**: Immediate visual feedback, working feature

## Migration Strategy

### Step 1: Backup Current Code

```bash
cp graph.js graph.js.backup
```

### Step 2: Implement 503 Response Handling

**Location**: `runSelectedGoogleSearches()` function around line 5440

**Current Code** (broken):

```javascript
const response = await fetch("/api/google/search", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ query: variation }),
});

if (!response.ok) {
  console.error(`❌ Search failed for "${variation}": ${response.status}`);
  return;
}

const result = await response.json();
```

**Fixed Code** (handles 503):

```javascript
const response = await fetch("/api/google/search", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ query: variation }),
});

// CRITICAL FIX: Handle both success AND 503 responses
let result;
if (response.ok) {
  result = await response.json();
} else if (response.status === 503) {
  // Google API not configured - extract mock results
  result = await response.json();
  console.log(`🧪 Using mock results for "${variation}" (API not configured)`);
} else {
  console.error(`❌ Search failed for "${variation}": ${response.status}`);
  return;
}
```

### Step 3: Test Immediately

1. Run Google search on any node
2. Verify URLs appear in node profile
3. Confirm clickable links work

### Step 4: Enhanced Logging

Add better debugging to track URL flow:

```javascript
console.log(`📊 Final URL collection: ${allUrls.size} unique URLs`);
console.log(`📋 URLs to store:`, Array.from(allUrls));
```

## Rollback Procedures

### If Fix Breaks Something:

```bash
# Restore backup
cp graph.js.backup graph.js
# Restart server
# Test that old behavior returns
```

### Rollback Decision Points:

- If errors appear in console
- If any existing functionality breaks
- If new issues emerge

## Risk Assessment Matrix

| Risk                          | Probability | Impact | Mitigation                         |
| ----------------------------- | ----------- | ------ | ---------------------------------- |
| Code breaks existing features | LOW         | HIGH   | Immediate rollback available       |
| 503 handling has edge cases   | MEDIUM      | LOW    | Additional error handling          |
| Mock URLs confuse users       | LOW         | MEDIUM | Add visual indicator for mock data |
| Real API setup breaks mocks   | LOW         | LOW    | Keep mock fallback logic           |

**Overall Risk**: **LOW** - This is a targeted fix to existing broken functionality

## Implementation Sequence

### Phase 3A: Core Fix (15 minutes)

1. ✅ Backup current graph.js
2. ✅ Modify runSelectedGoogleSearches() error handling
3. ✅ Test with current 503 responses
4. ✅ Verify URLs appear in node profile

### Phase 3B: Enhancement (10 minutes)

1. ✅ Add better logging
2. ✅ Add visual indicator for mock vs real results
3. ✅ Test edge cases

### Phase 3C: Documentation (5 minutes)

1. ✅ Update CLAUDE.md with fix details
2. ✅ Log success metrics
3. ✅ Note any deviations from plan

## Success Metrics

### Immediate Success (must achieve):

- ✅ Google search creates search query node
- ✅ Node shows "X/6 searches complete"
- ✅ Node profile displays clickable URLs
- ✅ User sees immediate visual feedback

### Quality Metrics:

- ✅ No console errors during search
- ✅ All 6 search variations processed
- ✅ URLs properly formatted and clickable
- ✅ Progress updates work correctly

## WHY This Approach

1. **Minimal Risk**: Only touches error handling, doesn't change core logic
2. **Immediate Impact**: Fixes user's critical frustration point
3. **Preserves Architecture**: Backend and other components unchanged
4. **Future-Proof**: Will work with real Google API when configured

## WHAT Exactly Changes

**Single Function**: `runSelectedGoogleSearches()` in graph.js
**Single Issue**: Add `response.status === 503` handling
**Single Outcome**: Mock URLs extracted and displayed

## HOW Implementation

1. **Preserve Existing Logic**: Keep all current success paths
2. **Add 503 Branch**: New conditional for status 503
3. **Extract Mock Results**: Parse JSON response body for mock_results
4. **Continue Normal Flow**: Let existing URL processing handle mock data

## WHEN Sequence

1. **Immediate**: Fix the 503 handling (critical path)
2. **Next**: Add logging and user feedback
3. **Future**: Configure real Google API (separate task)

This is a **surgical fix** for a **critical user issue** with **minimal risk** and **maximum impact**.
