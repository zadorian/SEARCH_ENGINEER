# URL Node Enhancement - Refactor Plan

**Date**: 2025-07-02 22:20
**Feature**: Double-click URL nodes for website access and backlinks analysis

## Proposed Architecture

### Frontend Flow

```
URL Node Double-Click → Check Node Type → Show URL Options Menu
         ↓                    ↓                     ↓
    Get node.type       If type === 'url'    Display 2 options:
                                              1. Go to Website
                                              2. Get Backlinks
                                                     ↓
                                              If Backlinks → API Call
                                                     ↓
                                              Display Results
```

### Backend API Flow

```
Frontend Request → /api/ahrefs/backlinks → Validate Domain → Ahrefs API
        ↓                                         ↓               ↓
   POST {domain}                          Extract domain    Get backlinks
                                                            Filter spam
                                                                 ↓
                                                          Return JSON
```

## Change Impact Analysis

### Frontend Changes (graph.js)

1. **Modify double-click handler** (line ~811)
   - Add condition for URL nodes
   - Show custom menu instead of expandNode()

2. **Add URL options menu function**
   - Similar to showContextMenu() but simpler
   - Two options: Open URL, Get Backlinks

3. **Add backlinks display function**
   - Create nodes for found backlinks
   - Use existing addNode() infrastructure

### Backend Changes (server.py)

1. **Add Ahrefs configuration**
   - Store API key in environment variable
   - Import required libraries

2. **Add /api/ahrefs/backlinks endpoint**
   - Accept POST with domain
   - Call Ahrefs API
   - Filter results
   - Return JSON

## Migration Strategy

### Step 1: Backend API Setup

1. Add AHREFS_API_KEY to .env file
2. Add ahrefs endpoint to server.py
3. Test endpoint with curl

### Step 2: Frontend Double-Click Handler

1. Modify network.on("doubleClick")
2. Add URL node type check
3. Create showUrlOptionsMenu()

### Step 3: Backlinks Integration

1. Add fetchBacklinks() function
2. Add displayBacklinksResults()
3. Test with real URLs

### Step 4: Polish & Error Handling

1. Add loading indicators
2. Handle API errors gracefully
3. Add result pagination if needed

## Rollback Procedures

1. Git commit before each step
2. Feature flag for new functionality
3. Keep original expandNode() as fallback
4. Backend endpoint can be disabled

## Risk Assessment

| Risk              | Probability | Impact | Mitigation               |
| ----------------- | ----------- | ------ | ------------------------ |
| API Key Exposure  | Low         | High   | Store in backend only    |
| API Rate Limits   | Medium      | Medium | Add caching, show limits |
| Large Result Sets | Medium      | Low    | Pagination, limits       |
| Network Errors    | Low         | Low    | Retry logic, fallbacks   |

## Implementation Details

### Frontend Functions Needed:

```javascript
// 1. Modified double-click handler
if (node && node.type === "url") {
  showUrlOptionsMenu(node, params);
  return;
}

// 2. URL options menu
function showUrlOptionsMenu(node, params) {
  // Create menu with 2 options
}

// 3. Backlinks fetcher
async function fetchBacklinks(domain) {
  // Call backend API
}

// 4. Results display
function displayBacklinksResults(node, backlinks) {
  // Create backlink nodes
}
```

### Backend Endpoint:

```python
@app.route('/api/ahrefs/backlinks', methods=['POST'])
def get_backlinks():
    # Extract domain
    # Call Ahrefs API
    # Filter results
    # Return JSON
```

## Success Criteria

- ✓ URL nodes show custom menu on double-click
- ✓ "Go to Website" opens URL in new tab
- ✓ "Get Backlinks" fetches and displays results
- ✓ API key remains secure in backend
- ✓ Graceful error handling
- ✓ No regression in other node types
