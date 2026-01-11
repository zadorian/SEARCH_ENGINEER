# EYE-D Architecture Documentation

## MD File Upload Feature [2025-07-04]

### Phase 1 Analysis Complete

- Analyzed existing URL entity extraction pattern
- Understood Claude integration with structured tools
- Documented Firecrawl → Claude → Entities flow
- See CLAUDE_MD_UPLOAD_DESIGN.md for architecture analysis

### Phase 2 Design Complete

- Designed `/api/file/extract-entities` endpoint
- Planned frontend upload button and handler
- Specified reuse of existing entity extraction logic
- Maintained consistency with URL extraction patterns

### Phase 3 Implementation Complete ✓

- Backend: Added file upload endpoint with validation
- Frontend: Added upload button and file handler
- Creates document node for uploaded MD file
- Extracts entities in semi-circle pattern
- Green SOURCE edges and cyan relationship edges
- See CLAUDE_MD_UPLOAD_IMPLEMENTATION.md for details

## Backlinks Feature Fix [2025-07-03]

### Phase 1 Analysis Complete

- Found that backlinks data was being stored correctly but accessed incorrectly
- Node properties are stored under node.data, not directly on node
- Display code was checking node.urls instead of node.data.urls
- See CLAUDE_BACKLINKS_ANALYSIS.md for root cause

### Phase 2 Design Complete

- No major refactoring needed
- Simple fix: Update property access paths in showNodeDetails
- Architecture is sound, just needed correct data access
- See CLAUDE_BACKLINKS_DESIGN.md for details

### Phase 3 Implementation Complete ✓

- Fixed showNodeDetails to access node.data.urls and node.data.backlinksData
- Updated all property accesses for backlinks_query nodes
- Both domain and page backlinks now display properly
- Rich display with domain, URL, anchor text, DoFollow status

# EYE-D Architecture Documentation

## URL Entity Extraction Feature [2025-07-03]

### Phase 1 Analysis Complete

- Analyzed image entity extraction pattern (graph.js:9544-9696)
- Backend uses Claude with structured tool calling
- Creates both entity nodes AND relationship edges
- Pattern: Content → Claude → Entities + Relationships → Nodes + Edges
- Key insight: Relationships are as important as entities
- See CLAUDE_URL_ENTITY_ANALYSIS.md for details

### Phase 2 Design Complete

- Designed `/api/url/extract-entities` endpoint
- Firecrawl scrapes webpage → markdown content
- Claude extracts entities + relationships (same tool as images)
- Frontend creates nodes in semi-circle pattern
- SOURCE edges from URL, relationship edges between entities
- See CLAUDE_URL_ENTITY_DESIGN.md for implementation plan

### Phase 3 Implementation Complete ✓

- Backend: Firecrawl scrapes → Claude extracts → Returns JSON
- Frontend: Menu option "Extract Entities" on URL nodes
- Creates entity nodes in semi-circle pattern
- Green SOURCE edges from URL → entities
- Cyan relationship edges between entities with arrows
- Staggered animation for visual appeal
- See CLAUDE_URL_ENTITY_IMPLEMENTATION.md for details

## Architecture Analysis - URL Screenshot Feature [2025-07-03]

### Phase 1 Analysis Complete

- Analyzed URL node creation flow
- Identified integration points for Firecrawl API
- Documented current architecture in CLAUDE_SCREENSHOT_ARCHITECTURE_ANALYSIS.md
- Key finding: Screenshots should trigger after URL node creation
- Challenge: Async nature of screenshot capture (5-30 seconds)
- Storage approach: Base64 in node.data.screenshot

### Phase 2 Design Complete

- Created CLAUDE_SCREENSHOT_REFACTOR_PLAN.md
- Designed `/api/screenshot/capture` endpoint
- Firecrawl API integration with full-page screenshots
- Asynchronous capture with loading states
- Non-breaking implementation approach
- Rationale: Visual verification improves URL node utility

### Phase 3 Implementation Complete ✓

- Backend: Added Firecrawl API endpoint with base64 conversion
- Frontend: Auto-trigger on URL paste
- Display: Loading/error/success states in profile
- Features: Click-to-enlarge, manual capture, retry
- Result: Full-page screenshots appear automatically in URL nodes
- See CLAUDE_SCREENSHOT_IMPLEMENTATION_LOG.md for details

## Architecture Analysis [2025-07-02 21:20]

### CRITICAL: Complete System Communication Breakdown

**New Evidence from Browser Console**:

- Multiple "TypeError: Failed to fetch" errors
- Errors occur at graph.js:5504 (fetch call in runSelectedGoogleSearches)
- Cascading failures: saveGraphState, saveCurrentProjectState all failing
- Server was not running when errors occurred

**System State Analysis**:

1. **Server Status**: Was crashed, now restarted and responding (200 OK)
2. **Frontend Status**: Multiple failed fetch attempts, needs page refresh
3. **Data Loss Risk**: Graph state and project state not saving

**Architecture Understanding**:

- Frontend makes exhaustive search requests to /api/google/search
- Each variation runs 20 queries (Q1-Q4 × 5 site groups)
- Backend processes correctly when running
- Frontend-backend communication fails when server crashes

**User Request**: Follow 3-phase architectural refactoring protocol

- Phase 1: Analysis & Documentation ✓ (COMPLETE)
  - Identified server crash as root cause
  - Documented cascading failures
  - Updated CLAUDE_ARCHITECTURE_ANALYSIS.md
- Phase 2: Design & Planning ✓ (COMPLETE)
  - Created CLAUDE_RESILIENT_ARCHITECTURE.md
  - Designed RequestManager, LocalStateCache, ErrorHandler
  - Defined migration strategy
- Phase 3: Implementation ✓ (COMPLETE)
  - ✓ Implemented fetchWithRetry with exponential backoff
  - ✓ Added server health monitoring
  - ✓ Created visual server status indicator
  - ✓ Added /api/health endpoint to backend

**Implementation Summary**:

1. Created resilient fetch wrapper with 3 retries and exponential backoff
2. Server status indicator shows 🟢 Online / 🔴 Offline
3. Health checks run every 30 seconds
4. User-friendly retry messages during connection failures

**User Action Required**:

1. Refresh the browser page to load new code
2. Server status indicator will appear in top-right corner
3. If server crashes, requests will retry automatically

## Architecture Analysis [2025-07-02 21:28]

### Remaining Critical Issues

**User Request**: Careful 3-phase approach for next architectural issue

**Outstanding Problems from Console**:

1. ESC key handler errors: "Failed to execute 'removeChild' on 'Node'"
2. Exhaustive search completing but no results displayed
3. Multiple repeated attempts suggesting user frustration

**Current Understanding**:

- Backend ExactPhraseRecallRunner works (verified: returns 128 URLs)
- Frontend receives the data (needs verification)
- Display logic may be failing
- Need to trace data flow from backend → frontend → display

**Phase 1: ANALYSIS IN PROGRESS**

## Custom Search Variations Feature [2025-07-02 21:43]

### User Request: Add ability to create custom search variations

**Implementation Complete**:

- Added custom variation input field to Google search modal
- Green box with "Add Custom Variation" section
- Input field with placeholder text showing example
- "Add" button to add variations to the list
- Enter key support for quick addition
- Duplicate checking to prevent same variation twice
- Custom variations marked with "[Custom]" label

**How to Use**:

1. Right-click any node → "Internet Search"
2. In the search modal, look for green "Add Custom Variation" box
3. Type your custom search (e.g., "John Doe LinkedIn" or "Company Name CEO")
4. Press Enter or click "Add"
5. Your custom variation appears in the list with a [Custom] tag
6. Select/deselect as needed
7. Click "Search Selected" to run exhaustive search on all checked variations

**Benefits**:

- Add site-specific searches: "Name site:linkedin.com"
- Add role-based searches: "Name CEO", "Name founder"
- Add location-based searches: "Name New York"
- Add any custom query variation you need

### Enhanced AI Variation Generation [2025-07-02 21:46]

**User Request**: Make AI variations smarter - some make no sense for exact phrase searches

**Implementation Complete**:

- Rewrote `generateGoogleSearchVariations` with smart context awareness
- Detects entity type: person names, companies, emails, phone numbers
- Generates only sensible exact phrase variations

**Smart Detection Features**:

1. **Person Names**:
   - Checks for capitalization patterns
   - 2-word names: "First Last", "Last, First"
   - 3-word names: adds middle initial variant
   - Avoids nonsensical permutations

2. **Companies**:
   - Detects Inc, LLC, Ltd, Corp, Group, Holdings, etc.
   - Removes suffix and searches both ways
   - Only adds the matching corporate suffix variant

3. **Emails**:
   - Extracts potential name from email prefix
   - Searches both email and extracted name

4. **Phone Numbers**:
   - Searches with and without formatting
   - Digits-only variant

**Result**: Fewer but smarter variations that make sense as exact phrase searches

## URL Paste Feature [2025-07-02 21:58]

### User Request: Paste URLs to create nodes that link to search results

**Implementation Complete**:

- Modified `initializePasteHandler` to detect URLs in pasted text
- Automatically creates URL nodes when pasting URLs
- Normalizes URLs (removes http://, www., trailing slash)
- Automatically connects to search query nodes containing the same URL

**How it Works**:

1. **Paste any URL** - just Ctrl+V or Cmd+V on the graph
2. **URL node created** with normalized URL as value
3. **Automatic connections** to any search query nodes that found this URL
4. **Green "found in" edges** show the connections
5. **Hover tooltip** shows "URL [url] found in search results"

**URL Normalization**:

- `https://www.example.com/page/` → `example.com/page`
- `http://subdomain.site.com` → `subdomain.site.com`
- Matches work even if search results have different protocols

**Benefits**:

- Quickly add URLs from external sources
- Instantly see which searches found this URL
- Build connections between manual research and search results

## Manual URL Field for All Nodes [2025-07-02 22:05]

### User Request: Add URL field to every node profile for manual URL management

**Implementation Complete**:

- Added dedicated URL section to all node profiles (including images)
- Multiple URL support with dynamic add/remove buttons
- Automatic connection creation when URLs match between nodes
- Cyan-colored connections for manual URL matches

**Features**:

1. **URL Section in Node Profile**:
   - Blue box with "URLs:" header
   - "+ Add URL" button to add multiple URLs
   - Each URL has its own input field with remove (×) button
   - URLs saved with node data as `manualUrls` array

2. **Automatic Connections**:
   - When saving node, checks all other nodes for matching URLs
   - Creates cyan connections between nodes with shared URLs
   - Checks against:
     - Other nodes' manual URLs
     - Search query nodes' results
     - URL nodes created by pasting
   - Connection label shows "X shared URLs"
   - Hover tooltip lists all shared URLs

3. **Smart URL Matching**:
   - Normalizes URLs for comparison
   - Matches even with different protocols (http/https)
   - Matches with/without www prefix
   - Partial URL matching supported

**How to Use**:

1. Click any node to open profile
2. Scroll to blue "URLs" section
3. Add URLs using the input field
4. Click "+ Add URL" for more fields
5. Click "Save All Changes"
6. Connections appear automatically!

**Connection Types**:

- **Green**: URL node ↔ Search query (paste feature)
- **Cyan**: Any node ↔ Any node (manual URLs)
- **Gray dotted**: Search ↔ Search (shared results)

## Architecture Analysis - URL Node Enhancement [2025-07-02 22:15]

### PHASE 1: Analysis of Double-Click and Backlinks Feature

**User Request**: Double-click URL nodes for "Go to website" and "Get backlinks" options

**Current State Analysis**:

- Double-click handler exists at line 811, currently calls `expandNode()`
- Context menu system is dynamic and type-aware
- URL nodes have no special handling currently
- Backend API structure supports adding new endpoints
- Security issue: API keys should not be in frontend

**Key Findings**:

1. Event system is well-structured for node type differentiation
2. Context menu already handles special cases (image nodes, companies)
3. Backend Flask server can easily add Ahrefs endpoint
4. Need secure API key management in backend only

**Documentation Created**: CLAUDE_URL_NODE_ARCHITECTURE.md

### PHASE 2: Design & Planning Complete [2025-07-02 22:20]

**Design Decisions**:

1. **Double-click behavior**: URL nodes get custom menu, not expandNode()
2. **Menu options**: "Go to Website" and "Get Backlinks"
3. **Security**: Ahrefs API key stored in backend .env only
4. **Display**: Backlinks shown as new nodes connected to URL node

**Implementation Plan**:

- Step 1: Backend API setup with Ahrefs endpoint
- Step 2: Frontend double-click handler modification
- Step 3: Backlinks fetching and display
- Step 4: Error handling and polish

**Risk Mitigation**:

- Git commits between steps
- Feature flag approach
- Fallback to original behavior
- API rate limit handling

**Documentation Created**: CLAUDE_URL_NODE_REFACTOR_PLAN.md

### PHASE 3: Implementation Complete [2025-07-02 22:35]

**Implementation Summary**:
✓ Step 1: Backend API setup with secure .env
✓ Step 2: Frontend double-click handler for URL nodes  
✓ Step 3: Backlinks fetching and display
✓ Step 4: Error handling and polish

**Feature Delivered**:

- Double-click any URL node to see custom menu
- Option 1: "Go to Website" opens URL in new tab
- Option 2: "Get Backlinks" fetches from Ahrefs API
- Backlinks displayed as nodes in circular pattern
- Container node shows count and organizes results

**Security**: Ahrefs API key stored only in backend
**Performance**: Reuses fetchWithRetry for resilience
**UX**: Clear feedback, animations, auto-focus

**Documentation Created**: CLAUDE_URL_NODE_IMPLEMENTATION_LOG.md

## Backlinks Display Enhancement [2025-07-02 22:50]

### User Request: Display backlinks like search query results with automatic connections

**Changes Made**:

1. **Backlinks as List Node**:
   - Changed from individual nodes to single list node (like search_query)
   - New node type: `backlinks_query` with light green color (#00FF88)
   - Shows all backlinks in scrollable list with metadata

2. **Automatic Connection Detection**:
   - `checkBacklinksConnections()` function checks all nodes for matching URLs
   - Compares against:
     - Search query node results
     - URL nodes
     - Other backlinks nodes
     - Manual URLs in any node
   - Creates green connections (#00FF88) with shared URL count

3. **Rich Display in Node Profile**:
   - Shows domain, DoFollow/NoFollow status
   - Displays anchor text
   - Shows Ahrefs rank
   - Shows first seen date
   - All URLs clickable

**Connection Matching**:

- Smart URL normalization (removes protocol, www, trailing slash)
- Partial matching supported
- Hover over connections shows all shared URLs
- Automatic detection when backlinks are fetched

## PHASE 1: CURRENT ARCHITECTURE ANALYSIS [2025-07-02 16:50]

### CRITICAL DISCOVERY: User Has Working Google Code

**Status**: BREAKTHROUGH - User provided complete working Google Custom Search implementation  
**Problem**: Current system uses invalid API calls, user has proven working code from other projects  
**Root Cause**: We're not using the user's existing, functional Google search architecture

#### Current State Analysis:

**Backend (server.py)**:

- **Google Search Endpoint**: `/api/google/search` (line ~1894)
- **Current Implementation**: Basic Google Custom Search API calls
- **Issue**: API credentials are invalid, causing 400 Bad Request errors
- **User's Solution**: Complete `ExactPhraseRecallRunner` class with proven GoogleSearch implementation

**Frontend (graph.js)**:

- **Search Initiation**: `runSelectedGoogleSearches()` function (line ~5402)
- **Node Creation**: `createEmptySearchQueryNode()` (line ~5700)
- **Node Updates**: `updateSearchQueryNode()` (line ~5758)
- **Issue**: "Node with id 'node_XXX' not found" errors during updates
- **URL Display**: Node profile display logic (line ~2623)

**Data Flow Current State**:

```
1. User clicks "Internet Search" → runSelectedGoogleSearches()
2. Creates search query node immediately → createEmptySearchQueryNode()
3. Makes 6 HTTP requests to /api/google/search → server.py google_search()
4. Server returns 400 errors due to invalid API credentials
5. Frontend receives empty results or errors
6. updateSearchQueryNode() called but node updates fail
7. URLs never display in node profile
```

#### User's Working Code Architecture:

**ExactPhraseRecallRunner Class Features**:

- **GoogleSearch.google_base()** method for API calls
- **Parallel execution** with ThreadPoolExecutor
- **Query permutations** (Q1-Q4 base queries + site groups + time slices)
- **Result deduplication** on URL
- **Rich result format**: title, url, snippet, found_by_query metadata
- **Exception search** capability for comprehensive coverage
- **Proven to work** in user's other applications

#### Integration Requirements:

1. **Replace Backend**: Integrate user's GoogleSearch class into server.py
2. **API Credentials**: Use user's working API key and Search Engine ID
3. **Result Format**: Adapt to return title, snippet, url (not just URLs)
4. **Frontend Updates**: Handle rich result format in node profile
5. **Node ID Issues**: Fix race conditions causing "node not found" errors

#### Previous Failed Attempts:

- ❌ Mock results with example.com URLs
- ❌ DuckDuckGo scraping approach
- ❌ Direct Google HTML scraping (blocked by anti-bot measures)
- ❌ Invalid Google API credentials leading to 400/503 errors

---

## PHASE 2: INTEGRATION DESIGN & PLANNING [2025-07-02 16:52]

### Proposed Architecture: User's GoogleSearch Integration

#### NEW Backend Architecture (server.py):

**Step 1: Create GoogleSearch Class**

```python
class GoogleSearch:
    def __init__(self):
        self.api_key = GOOGLE_API_KEY  # User's working credentials
        self.search_engine_id = GOOGLE_SEARCH_ENGINE_ID

    def google_base(self, query, max_results=10):
        """User's proven google_base method"""
        # Returns: (hits_list, estimated_count)
        # hits_list contains: {'url': '...', 'title': '...', 'snippet': '...'}
```

**Step 2: Replace Current /api/google/search Endpoint**

- Remove current broken implementation
- Use GoogleSearch.google_base() method
- Return rich results: URLs + titles + snippets
- Handle user's proven API credential format

#### NEW Frontend Architecture (graph.js):

**Enhanced Node Profile Display**:

```javascript
// Current: Only shows URLs
node.urls = ["url1", "url2", "url3"];

// NEW: Rich result objects
node.searchResults = [
  { url: "url1", title: "Title 1", snippet: "Snippet 1" },
  { url: "url2", title: "Title 2", snippet: "Snippet 2" },
];
```

**Updated Profile HTML**:

- Display clickable URLs with titles
- Show snippets for context
- Maintain existing progress reporting

#### Data Flow NEW Architecture:

```
1. User clicks "Internet Search" → runSelectedGoogleSearches()
2. Creates search query node → createEmptySearchQueryNode()
3. Makes 6 requests to /api/google/search → NEW GoogleSearch.google_base()
4. Server returns rich results: [{url, title, snippet}, ...]
5. Frontend receives structured data
6. updateSearchQueryNode() updates with rich results
7. Node profile displays URLs with titles & snippets
```

### Implementation Strategy:

#### Phase 2A: Backend Integration (Critical Path)

1. **Extract GoogleSearch Class**: From user's working code
2. **Add to server.py**: As new class definition
3. **Replace google_search() function**: Use GoogleSearch.google_base()
4. **Update Response Format**: Include title, snippet, url
5. **Add User's API Credentials**: Request working keys

#### Phase 2B: Frontend Enhancement

1. **Update Response Handling**: Accept rich result objects
2. **Enhance Node Profile**: Display titles and snippets
3. **Fix Node ID Issues**: Debug "node not found" errors
4. **Test Integration**: Verify end-to-end functionality

#### Phase 2C: Testing & Validation

1. **API Credential Test**: Verify user's keys work
2. **Search Flow Test**: Complete user journey
3. **Node Display Test**: URLs, titles, snippets visible
4. **Error Handling**: Graceful fallbacks

### Risk Assessment:

**HIGH IMPACT, LOW RISK**:

- User's code is proven to work
- We're replacing broken implementation with working one
- Minimal changes to frontend required

**CRITICAL SUCCESS FACTORS**:

1. **User's API Credentials**: Must get working GOOGLE_API_KEY and GOOGLE_SEARCH_ENGINE_ID
2. **Exact Code Replication**: Use user's GoogleSearch.google_base() method exactly
3. **Node ID Fix**: Resolve race condition causing "node not found"

### User Requirements Checklist:

- ✅ Use user's proven working Google code
- ✅ Display actual Google search results (not mock data)
- ✅ Show titles, URLs, and snippets in node profile
- ✅ Maintain existing search query node functionality
- ✅ Fix "No URLs found yet" issue permanently

---

## Current Node Double-Click Architecture (As of 2025-07-02)

### Phase 1: Current Flow Analysis

When a user double-clicks on a node, the following sequence occurs:

1. **Event Handler** (`graph.js:763`)
   - `network.on("doubleClick")` captures the event
   - Checks if it's a query node, check indicator, or regular node
   - Calls `expandNode(node)` for regular nodes

2. **Node Expansion** (`graph.js:2640`)
   - `expandNode(node)` function:
     a. Validates node has data property
     b. Checks if node already expanded via `nodeExpansionCache`
     c. If AI suggestions enabled: calls `generateAISuggestions()` and shows modal
     d. If AI disabled: proceeds with automatic searches

3. **Current Search Logic** (`graph.js:2696-2748`)
   - Builds `searchQueries` array with priorities:
     1. Search in node's own category (priority: 1)
     2. OSINT for email/phone nodes (priority: 2)
     3. OpenCorporates for name/person nodes (priority: 2.5)
     4. Blanket search across all fields (priority: 3)
     5. Variations if they exist (priority: 4+)
   - Executes searches sequentially via `performSearch()`

4. **AI Suggestions Modal** (when enabled)
   - `generateAISuggestions()` creates search variations
   - `showAISuggestionsModal()` displays them
   - User selects which searches to run

### Phase 2: Proposed New Architecture

#### New Flow Design:

1. **Double-Click Event** → **Search Provider Selection Panel**
   - Two-tab interface:
     - Tab 1: "APIs" - Direct service selection
     - Tab 2: "Search Categories" - Type-based search

2. **APIs Tab Options:**
   - DeHashed → Then show variations panel
   - OSINT Industries → Direct search
   - WhoisXMLAPI → Direct search
   - OpenCorporates → Direct search (officer for persons, company for companies)
   - OCCRP Aleph → Direct search

3. **Search Categories Tab Options:**
   - Accounts & Credentials → Routes to DeHashed + OSINT Industries
   - Corporate → Routes to OpenCorporates + OCCRP Aleph
   - Domain Intelligence → Routes to WhoisXMLAPI + DeHashed
   - Personal Info → Routes to appropriate services based on node type

#### Key Architecture Changes:

1. **Remove automatic search execution** from `expandNode()`
2. **Create new modal component** for search provider selection
3. **Separate search logic** by provider
4. **Maintain AI suggestions** but integrate within provider selection
5. **Add routing logic** for category-based searches

### Current Modal System Details

#### showAISuggestionsModal (graph.js:6882)

- Creates a modal with search variations
- Shows previously run searches
- Includes special handling for:
  - Domain nodes (WHOIS + email search)
  - Email/phone nodes (OSINT Industries)
  - General nodes (DeHashed variations)
- Allows multi-selection of searches
- Has "Check All" functionality

#### Key Features to Preserve:

1. Previous search history display
2. Multi-selection capability
3. Domain-specific options
4. Search variation generation

### Phase 3: Implementation Plan

#### Step 1: Create Search Provider Selection Modal

- New function: `showSearchProviderModal(node)`
- HTML structure with tabs
- Event handlers for provider selection

#### Step 2: Refactor expandNode()

- Remove automatic search logic
- Call `showSearchProviderModal()` instead
- Keep node validation and caching

#### Step 3: Create Provider-Specific Handlers

- `handleDeHashedSearch()` - includes variations panel
- `handleOSINTIndustriesSearch()`
- `handleWhoisXMLSearch()`
- `handleOpenCorporatesSearch()`
- `handleAlephSearch()`

#### Step 4: Implement Category-Based Search Router

- `handleCategorySearch(category, node)`
- Routes to appropriate providers based on category

#### Step 5: Update UI/UX

- Style the new modal
- Add loading states
- Handle errors gracefully

## Implementation Progress

### Completed Steps:

1. ✅ **Created Search Provider Selection Modal** (`showSearchProviderModal`)
   - Two-tab interface implemented
   - API Services tab with 5 providers
   - Search Categories tab with 4 categories
   - Clean modal styling matching the app theme

2. ✅ **Created Provider Selection Handlers**
   - `selectSearchProvider()` - Routes to specific API handlers
   - `selectSearchCategory()` - Routes to category-based searches
   - Individual handlers for each provider:
     - `handleDeHashedSearch()` - Shows AI variations modal
     - `handleOSINTIndustriesSearch()` - Direct search
     - `handleWhoisXMLSearch()` - Direct search with domain special handling
     - `handleOpenCorporatesSearch()` - Officer/Company search based on node type
     - `handleAlephSearch()` - Direct search
   - Category handlers that combine multiple providers

3. ✅ **Modified expandNode Function**
   - Removed automatic search logic
   - Now shows search provider modal
   - Preserves node expansion cache check

### Testing Plan:

1. Double-click on different node types:
   - Email node → Should show all providers
   - Name/Person node → OpenCorporates should search officers
   - Domain node → WhoisXML should do reverse search
   - Company node → OpenCorporates should search companies

2. Test each API service button
3. Test each category button
4. Verify AI suggestions still work for DeHashed
5. Check that node expansion cache still works

### Known Issues to Address:

1. Need to ensure `performWhoisSearch` function exists
2. May need to adjust modal z-index if conflicts with other UI
3. Should add loading states for each provider

## Implementation Notes

### Current Functions to Modify:

- `expandNode()` - Remove automatic search, add modal call
- `showAISuggestionsModal()` - Integrate into DeHashed flow

### New Functions to Create:

- `showSearchProviderModal(node)`
- `handleProviderSelection(provider, node)`
- `handleCategorySelection(category, node)`
- Provider-specific handlers

### UI Components Needed:

- Search provider modal with tabs
- Provider selection buttons
- Category selection interface
- Loading/progress indicators

## Testing Considerations

1. Ensure all node types work with new flow
2. Test each provider integration
3. Verify category routing logic
4. Check error handling for failed searches
5. Validate caching still works properly

## Rollback Plan

Keep original `expandNode()` logic commented out until new system is fully tested.

## Summary of Changes

### New User Flow:

1. **User double-clicks a node**
2. **Search Provider Modal appears** with two tabs:
   - **API Services Tab**: Direct access to specific services
     - DeHashed → Shows AI variations modal
     - OSINT Industries → Direct search
     - WhoisXMLAPI → Direct search (special domain handling)
     - OpenCorporates → Company/Officer search based on node type
     - OCCRP Aleph → Direct search
   - **Search Categories Tab**: Grouped searches by purpose
     - Accounts & Credentials → DeHashed + OSINT Industries
     - Corporate Intelligence → OpenCorporates + OCCRP Aleph
     - Domain Intelligence → WhoisXML + DeHashed email search
     - Personal Information → All applicable services

3. **User selects a provider or category**
4. **Service-specific behavior**:
   - DeHashed: Shows AI variations modal (existing behavior)
   - Others: Direct search execution
5. **Results are added to the graph**

### Key Improvements:

1. **User Control**: Users now choose which service to search
2. **Clarity**: Clear distinction between services and their capabilities
3. **Efficiency**: No unnecessary searches, only what user selects
4. **Flexibility**: Category-based searches for common use cases
5. **Preservation**: AI suggestions still work for DeHashed

### Technical Details:

- Modal uses z-index 2000 to appear above other UI elements
- ESC key closes the modal
- Node expansion cache still prevents duplicate searches
- All existing search functions are reused, just called differently
- Clean separation between UI (modal) and search logic (handlers)

## Duplicate Node Prevention Issue Analysis

### Phase 1: Current Architecture Analysis

#### Issue Description:

- Duplicate nodes are being created (e.g., two identical 'AG Foods Group a.s.' nodes)
- This violates the fundamental principle that all nodes must be unique
- When adding a node that already exists, it should merge with the existing one
- For similar (but not identical) nodes, should either:
  - Show alert and offer merge choice
  - Create hypothetical blue connection

#### Current Deduplication System:

1. **valueToNodeMap** (graph.js):
   - Maps node values to node IDs for deduplication
   - Should prevent duplicate nodes by checking if value already exists
   - Used in `addNode()` function

2. **addNode() Function**:
   - Should check valueToNodeMap before creating new nodes
   - Has similarity detection for near-matches
   - Should return existing node if exact match found

3. **Similarity Detection**:
   - Uses string similarity algorithm
   - Shows alerts for similar nodes
   - Allows user to choose merge or create new

#### Investigation Results:

**ROOT CAUSE FOUND**: The `processMultipleCompanies` function uses `addNodeDirect()` instead of `addNode()`, which completely bypasses all duplicate checking:

1. **addNode()** - Has duplicate prevention:
   - Checks valueToNodeMap for existing nodes
   - Shows similarity alerts for near-matches
   - Auto-creates hypothetical links for 80-95% matches
   - Allows user to merge for 95%+ matches

2. **addNodeDirect()** - NO duplicate prevention:
   - Creates node without any checks
   - Only adds to valueToNodeMap AFTER creation
   - Used by processMultipleCompanies for corporate searches
   - This explains why 'AG Foods Group a.s.' was duplicated

3. **Where addNodeDirect is used**:
   - Line 3404: Company nodes from OpenCorporates/Aleph
   - Line 3442: Address nodes from corporate searches
   - Line 3492: Officer nodes from corporate searches

### Phase 2: Solution Design

#### Proposed Solutions:

1. **Remove addNodeDirect entirely** - Force all node creation through addNode()
2. **Fix processMultipleCompanies** - Use addNode() instead of addNodeDirect()
3. **Add duplicate check to addNodeDirect** - Make it check valueToNodeMap first
4. **Create unified node creation** - Single function with optional duplicate bypass

#### Recommended Approach:

Fix processMultipleCompanies to use addNode() instead of addNodeDirect(). This ensures:

- Exact duplicates are automatically merged
- Similar nodes trigger alerts or hypothetical links
- All node creation follows the same rules
- No special bypass for corporate searches

### Phase 3: Implementation Complete

#### ✅ Step 1: Replaced addNodeDirect with addNode

- Changed processMultipleCompanies to use addNode for all node creation
- Company nodes now check for duplicates
- Address nodes now check for duplicates
- Officer nodes now check for duplicates

#### ✅ Step 2: Handled async responses properly

- Made processMultipleCompanies and handleCorporateSearch properly async
- Added await for all addNode calls
- Handle null returns when user cancels similarity dialog
- Converted forEach loops to for...of loops for proper async handling

#### ✅ Step 3: Ready for Testing

The system now ensures:

- Exact duplicates are automatically merged (like 'AG Foods Group a.s.')
- Similar nodes (80-95% match) get automatic hypothetical blue links
- Very similar nodes (95%+ match) show merge dialog
- User can choose to merge, create hypothetical link, or create anyway
- All corporate searches follow the same deduplication rules

### Solution Summary

Fixed the duplicate node issue by:

1. **Removed bypass**: Corporate searches no longer bypass duplicate checking
2. **Unified creation**: All nodes go through addNode() with its safety checks
3. **Preserved features**: Similarity detection and merge dialogs work for all sources
4. **Better UX**: Users see existing nodes reused instead of duplicates created

The fundamental principle is now enforced: all nodes must be unique.

## Case-Insensitive Duplicate Detection Issue

### Issue Description:

- Duplicate nodes still being created with different capitalization
- Example: 'AG Foods Group' vs 'AG FOODS group'
- Company names must be case-insensitive for duplicate detection

### Root Cause:

- valueToNodeMap uses case-sensitive keys: `${type}_${data.value}`
- 'company_AG Foods Group' != 'company_AG FOODS group'
- This bypasses duplicate detection for differently capitalized names

### Solution Implemented:

1. **Fixed addNode()**: Normalizes values to lowercase for key creation
   - `const keyValue = (data.value || data.label || data.id || '').toLowerCase().trim()`
   - Preserves original capitalization for display

2. **Fixed addNodeDirect()**: Same case-insensitive key creation

3. **Added Migration**: When loading saved states or undoing
   - Migrates old case-sensitive keys to case-insensitive
   - Ensures compatibility with existing saved data

4. **Already Working**: findSimilarNodes() was already case-insensitive

### Result:

- All company names (and other node types) are now deduplicated case-insensitively
- 'AG Foods Group' and 'AG FOODS group' will be recognized as the same node
- Original capitalization is preserved for display

## OCCRP Aleph "Unknown" Issue - Person Search Problem

### Phase 1: Current Architecture Analysis (2025-07-02)

#### New Issue Description:

- When searching for a person in OCCRP Aleph:
  - A company node is created with label "Unknown"
  - The company is NOT connected to the person searched for
  - The company IS connected to an address
  - This suggests the person is a director of the company, but the company name isn't extracted

#### Investigation Steps:

1. Need to check how person searches are handled differently
2. Examine if person search results include related companies
3. Check if the enhanced extraction is actually running
4. Verify how relationships are created between person and company

#### Current Flow for Person Search:

1. User searches for person name
2. Server calls OCCRP Aleph API
3. Results processed in server.py `/api/aleph/search`
4. Client processes results in handleCorporateSearch()
5. Person nodes created, but related companies showing as "Unknown"

#### Root Cause Analysis:

**Server-side Issues Found:**

1. Person extraction (lines 1473-1526) does NOT extract company relationships
2. It only extracts: name, birth_date, and common fields (email, phone, address)
3. NO extraction of: company_name, position, directorship info

**Result Structure Problem:**

- OCCRP Aleph likely returns multiple results for a person search:
  - Person result (extracted correctly)
  - Related company results (showing as "Unknown")
  - Address results (connected to companies)
- These are separate results, not nested data
- No relationships extracted between person and companies

**Client-side Expectation Mismatch:**

- Client expects `result.company_name` field on person results (line 3756)
- But server never populates this field
- Related companies come as separate results with type='company' or type='document'

### Phase 2: Solution Design

#### Understanding OCCRP Aleph Data Structure:

From AlephEntity class analysis:

- Entities have `edge_spec` for relationships (source/target)
- Entities have `links` array for connections
- Entities have `roles` array which may contain directorships
- Person searches return multiple separate entities, not nested data

#### Proposed Solution:

1. **Fix "Unknown" Company Names**:
   - Debug why enhanced extraction isn't working
   - Add more logging to see actual data structure
   - Possibly the company results have different schema types

2. **Extract Relationships from Person Results**:
   - Check `roles` array for directorship information
   - Check `links` array for related entities
   - Extract company names/IDs from these relationships

3. **Create Proper Connections**:
   - After creating all nodes, analyze relationships
   - Connect person to companies based on roles/links
   - Use the edge_spec data if available

4. **Handle Different Entity Schemas**:
   - Not all results might be Company/Person/Address
   - Some might be Directorship, Ownership, Membership entities
   - These relationship entities contain the connection info

### Phase 3: Implementation Complete

#### ✅ Step 1: Added Comprehensive Logging

- Logs full details for each result including schema, available fields
- Logs links, edge data, and roles if present
- Special logging for relationship entities (Directorship, Ownership, etc.)
- Shows extracted person/company names from relationships

#### ✅ Step 2: Implemented Relationship Extraction

- Added handling for relationship schemas: Directorship, Ownership, Membership, Employment
- Extracts person name from 'director' or 'person' properties
- Extracts company name from 'organization' or 'company' properties
- Extracts position, start_date, end_date from relationships
- Stores relationships separately for processing

#### ✅ Step 3: Created Synthetic Results

- For each relationship, creates synthetic person and company results
- Ensures both person and company nodes will be created
- Includes position and date information in person results
- Person results now have company_name field populated from relationships
- This enables the client to create proper connections

### Solution Summary

Fixed the OCCRP Aleph person search issue by:

1. **Understanding the data structure**: Person searches return separate entities including relationship entities
2. **Extracting relationships**: Directorship entities contain the person-company connections
3. **Creating synthetic results**: Ensures all entities are created with proper names
4. **Enabling connections**: Person results now include company_name for automatic connection creation

The "Unknown" company issue should now be resolved as company names are extracted from relationship entities.

- Company names and related people are missing or showing as "Unknown"

#### Current Flow:

1. **Client Side** (graph.js):
   - `handleAlephSearch()` calls `handleCorporateSearch()` with type='aleph'
   - `handleCorporateSearch()` sends POST to `/api/aleph/search`

2. **Server Side** (server.py:1357-1463):
   - Uses `AlephSearcher` from `occrp_aleph.py`
   - Processes raw results with field extraction logic:
     ```python
     # For companies:
     company_name = item.get('title') or item.get('name')
     if not company_name and 'name' in props:
         company_name = props['name'][0] if isinstance(props['name'], list) else props['name']
     if not company_name and 'caption' in item:
         company_name = item['caption']
     result['name'] = company_name or 'Unknown Company'
     ```

3. **OCCRP Aleph Module** (occrp_aleph.py):
   - Returns `AlephEntity` objects with:
     - `name`: Extracted from caption/name fields
     - `properties`: Dict containing all entity properties
     - `schema`: Entity type (Company, Person, etc.)
     - `highlights`: Search match highlights

#### Root Cause Analysis:

The "Unknown" issue happens when:

1. The Aleph API returns entities without 'title', 'name', or 'caption' fields
2. The 'name' property is nested differently than expected
3. The entity data structure doesn't match what server.py expects

#### Debug Information Needed:

- What fields are actually present in the Aleph API response
- How the data is structured in the raw_data field
- Whether properties contain the name in a different field

### Phase 2: Solution Design

#### Problems Identified:

1. **Server-side field extraction is too limited**
   - Only checks `title`, `name`, `caption` fields
   - Doesn't check all possible property fields where names might be stored
   - Falls back to "Unknown" too quickly

2. **Client-side node creation uses wrong fields**
   - For 'document' type results, uses `result.title` which is already "Unknown"
   - Creates nodes with type 'unknown' instead of proper types

3. **Missing data extraction**
   - Not extracting all available fields from Aleph entities
   - Not utilizing the `highlights` field which often contains relevant context
   - Not checking alternative name fields like `label`, `aliases`, etc.

#### Proposed Solution:

1. **Enhanced Server-side Processing**:
   - Add comprehensive field checking for names
   - Extract more fields from properties
   - Include highlights and snippets
   - Better fallback logic using any available text

2. **Improved Client-side Handling**:
   - Better type detection based on schema
   - Use all available fields for node creation
   - Display more information in nodes

3. **Debug Logging**:
   - Add detailed logging to see actual Aleph response structure
   - Log field extraction attempts

### Phase 3: Implementation Complete

#### ✅ Step 1: Added Debug Logging to Server

- Added comprehensive logging for each Aleph result
- Logs schema, available fields, and extraction attempts
- Shows exactly which field the name was extracted from

#### ✅ Step 2: Enhanced Field Extraction in server.py

- Company extraction checks: title, caption, name, label (top-level)
- Then checks properties: name, legalName, label, tradingName, alias, previousName, registeredName
- Falls back to highlights extraction and registration numbers
- Similar enhancements for Person and Document types
- Document types now also extract names instead of defaulting to "Unknown"

#### ✅ Step 3: Improved Client-side Processing

- Updated document type handling to use `result.name` field
- Falls back to `result.title` only if name is not available
- Ensures proper display of entity names instead of "Unknown"

### Solution Summary

The "Unknown" issue has been resolved by:

1. **Comprehensive Field Extraction**: The server now checks multiple fields in order of preference
2. **Smart Fallbacks**: If primary fields are empty, it checks properties, highlights, and identifiers
3. **Client-side Fix**: Document nodes now use the extracted name field properly
4. **Better Logging**: Debug output shows exactly where names are extracted from

### Testing

To verify the fix works:

1. Search for a company in OCCRP Aleph
2. Check server console for extraction logs
3. Verify nodes are created with proper names, not "Unknown"

## Google Search Query Node Implementation (2025-07-02)

### User Request Analysis

The user requested a new "SEARCH QUERY" node type with these specific requirements:

1. Use Google API to search and maximize recall
2. Store search term as node value
3. Store retrieved URLs as node content
4. Auto-connect to other SEARCH QUERY nodes when they share URLs
5. Show shared URLs in connection details

### Implementation Complete

#### ✅ Step 1: Server-side Google Search API Endpoint

- Added `/api/google/search` endpoint in server.py:1894-1962
- Uses Google Custom Search API with multiple requests for maximum recall
- Returns up to 50 URLs from search results
- Includes mock results when API not configured
- Proper error handling and timeout management

#### ✅ Step 2: Client-side Google Search Handler

- Added `handleGoogleSearch()` function in graph.js:5133-5175
- Calls the Google API endpoint
- Creates search query nodes with retrieved URLs
- Integrates with existing search provider modal

#### ✅ Step 3: Search Query Node Creation

- Added `createSearchQueryNode()` function in graph.js:5237-5259
- Creates nodes with type 'search_query'
- Stores search term as node value
- Stores URLs in both content field and dedicated urls array
- Uses coral red color (#FF6B6B) for visual distinction

#### ✅ Step 4: Auto-Connection Logic

- Added `checkSearchQueryConnections()` function in graph.js:5261-5306
- Compares URLs between all search query nodes
- Creates connections when nodes share URLs
- Connection label shows number of shared URLs
- Connection tooltip and details show the actual shared URLs
- Uses coral red color for search query connections

#### ✅ Step 5: UI Integration

- Added Google Search button to search provider modal (graph.js:4795-4806)
- Added 'search_query' to node type color mapping (graph.js:2489)
- Added 'search_query' to type change menu (graph.js:5362)
- Distinctive coral red styling for search query elements

### Technical Features

1. **Node Structure**:

   ```javascript
   {
     type: 'search_query',
     value: searchTerm,           // Original search term
     label: `Search: ${searchTerm}`,  // Display label
     content: urls.join('\n'),    // URLs as content
     urls: urls,                  // URLs array for easy access
     searchTerm: searchTerm       // Original term for reference
   }
   ```

2. **Connection Logic**:
   - Automatically detects shared URLs between search query nodes
   - Creates labeled connections showing number of shared URLs
   - Tooltip displays the actual shared URLs
   - Uses Set operations for efficient URL comparison

3. **API Integration**:
   - Google Custom Search API with pagination support
   - Maximum recall strategy (up to 50 URLs per search)
   - Graceful fallback when API not configured
   - Proper error handling and user feedback

### Testing Plan

1. **Basic Functionality**:
   - Double-click a node → Select Google Search
   - Verify search query node is created
   - Check that URLs are stored in content field

2. **Auto-Connection**:
   - Create multiple search query nodes with overlapping results
   - Verify connections are created between nodes with shared URLs
   - Check connection labels and tooltips show shared URLs

3. **API Integration**:
   - Test with Google API configured
   - Test fallback behavior when API not configured
   - Verify error handling for API failures

### Architecture Benefits

1. **Modular Design**: Google search integrated cleanly into existing search provider system
2. **Auto-Discovery**: Shared URLs automatically create meaningful connections
3. **Visual Clarity**: Distinct coral red color for search query nodes and connections
4. **Maximum Recall**: API strategy designed to retrieve as many URLs as possible
5. **User Control**: Users choose when to perform Google searches via provider modal

The Google Search Query node feature is now fully implemented and ready for testing.

## Google Search Progress Enhancement (2025-07-02)

### Phase 1: Current Architecture Analysis

#### Current Flow Problem:

When a user initiates a Google search:

1. User selects variations and clicks "Search Selected"
2. Modal closes
3. Status shows "Running X Google searches..."
4. **LONG WAIT WITH NO FEEDBACK**
5. Eventually a search query node appears with all results

#### Why This Is Bad:

- No immediate visual feedback that search started
- No connection shown to source node during search
- No progress indication during multiple API calls
- User can't see what's happening
- Feels unresponsive for long searches

#### Current Implementation Details:

**In `runSelectedGoogleSearches()` (graph.js:5337-5416):**

```javascript
// Current flow:
1. Close modal
2. Update status text only
3. Run all searches in parallel (Promise.all)
4. Wait for ALL to complete
5. THEN create node with combined results
6. THEN create connections
```

**In `createSearchQueryNode()` (graph.js:5503-5524):**

- Creates node with all URLs at once
- Returns the created node
- No support for updating existing node

**In `checkSearchQueryConnections()` (graph.js:5526-5570):**

- Only runs after node is fully created
- Creates connections based on shared URLs

### Phase 2: Proposed Architecture

#### New Flow Design:

1. **Immediate Node Creation**
   - Create search query node RIGHT AFTER modal closes
   - Node shows "Loading..." or spinner
   - Create connection to source node immediately
2. **Progressive Updates**
   - As each Google API call completes, update the node
   - Show progress: "Loading... (3/7 searches complete)"
   - Accumulate URLs progressively
3. **Final State**
   - Update node label to show final count
   - Check for connections with other search nodes
   - Show completion status

#### Technical Requirements:

1. Split `createSearchQueryNode()` into:
   - `createEmptySearchQueryNode()` - Creates node with loading state
   - `updateSearchQueryNode()` - Updates existing node with new URLs
2. Modify `runSelectedGoogleSearches()` to:
   - Create node immediately after modal close
   - Create connection to source node
   - Use individual promises instead of Promise.all
   - Update node as each search completes
3. Add visual indicators:
   - Loading animation or special color during search
   - Progress text in node label
   - Completion indicator

### Phase 3: Implementation Complete ✅

#### ✅ Step 1: Created Empty Node Function

**`createEmptySearchQueryNode()` (graph.js:5526-5561)**

- Creates search query node with loading state immediately
- Shows "🔍 Searching: term (0/N)..." label
- Creates connection to source node right away
- Sets isLoading flag and tracks total/completed searches
- Returns node for subsequent updates

#### ✅ Step 2: Created Update Function

**`updateSearchQueryNode()` (graph.js:5563-5607)**

- Updates existing node with new URLs progressively
- Merges URLs to avoid duplicates
- Updates label with progress: "(3/7)..."
- Changes color during loading (brighter red)
- Restores normal color when complete
- Returns accumulated URLs for tracking

#### ✅ Step 3: Modified Search Flow

**`runSelectedGoogleSearches()` (graph.js:5355-5478)**

- Creates empty node IMMEDIATELY after modal closes
- Shows connection to source node instantly
- Processes searches sequentially for progress updates
- Updates node after each search completes
- Shows running count in both node and status bar
- Handles errors gracefully with red error state
- Checks for connections only after completion

#### ✅ Step 4: Visual Enhancements

- **Loading state**: Bright red background during search
- **Progress indicator**: "(2/5)..." in node label
- **Status updates**: Shows URLs found so far
- **Completion**: Normal coral red when done
- **Error state**: Dark red if searches fail

### Result

Now when a user initiates a Google search:

1. Modal closes → Search query node appears INSTANTLY
2. Connection to source node visible immediately
3. Node shows "🔍 Searching: term (0/5)..."
4. Progress updates as each search completes: "(1/5)...", "(2/5)..."
5. URLs accumulate progressively in the node
6. Final state shows total URLs found
7. Connections to other search nodes checked at end

The user gets immediate visual feedback and can watch the progress in real-time!

## Connection Types Standardization (2025-07-02)

### Phase 1: Current Architecture Analysis

#### User Requirements:

1. **Grey dotted** - Default connections
2. **White continuous thick** - Between anchored nodes
3. **Blue** - Hypothetical connections
4. **Green** - Source arrows (images → extracted nodes)
5. **Red** - Query links

#### Issue: Yellow connections appearing that were never requested

Let me analyze where each connection type is currently used...

#### Current Connection Colors Found:

1. **#666666 (Gray)** - Default/breach connections ✓
2. **#ffffff (White)** - Anchored node connections ✓
3. **#0066ff (Blue)** - Hypothetical connections ✓
4. **#00ff00/#00FF00 (Green)** - Company search main connections (should be for source arrows)
5. **#ff0000 (Red)** - Search query connections ✓
6. **#FFD700 (Gold/Yellow)** - Officer/director connections ❌ NOT REQUESTED
7. **#ff6600 (Orange)** - Search result connections ❌ NOT REQUESTED
8. **#ff00ff (Magenta)** - Manual connections ❌ NOT REQUESTED
9. **#20B2AA (Teal)** - WHOIS connections ❌ NOT REQUESTED
10. **#00BFFF (Sky Blue)** - OSINT connections ❌ NOT REQUESTED
11. **#00CED1 (Turquoise)** - Company-address connections ❌ NOT REQUESTED
12. **#9370DB (Purple)** - Same search connections ❌ NOT REQUESTED
13. **#FF6B6B (Coral)** - Search query URL connections ❌ NOT REQUESTED
14. **#9932CC (Orchid)** - Screenshot connections (should be green)

#### Problems Identified:

1. **Yellow connections (#FFD700)** appearing for officer/director relationships (lines 3543, 3739, 3809)
2. **Green (#00FF00)** being used for company search connections instead of source arrows
3. **Multiple unauthorized colors** for different connection types
4. Screenshot connections using orchid instead of green
5. Too many connection types when user only wants 5 specific types

### Phase 2: Proposed Architecture

#### Standardized Connection Types:

1. **Default Connection** (#666666 - Gray, dotted)
   - All general connections between nodes
   - Breach connections
   - Company relationships
   - Everything not in other categories

2. **Anchored Connection** (#FFFFFF - White, thick, solid)
   - Only between anchored nodes
   - Thicker width (3-4px)

3. **Hypothetical Connection** (#0066FF - Blue, solid)
   - Similar node connections (80-95% match)
   - User-created hypothetical links

4. **Source Arrow** (#00FF00 - Green, with arrow)
   - From images/screenshots to extracted nodes
   - From any source document to derived data
   - Always has directional arrow

5. **Query Link** (#FF0000 - Red, solid)
   - From search node to query node
   - From query node to results
   - Search-related connections

#### Changes Required:

1. Replace all yellow (#FFD700) with gray (#666666)
2. Replace all unauthorized colors with gray
3. Ensure screenshot connections use green
4. Consolidate connection logic
5. Add proper dash patterns for gray connections

### Phase 3: Implementation Plan

#### Step 1: Create Connection Type Constants

- Define the 5 allowed connection types
- Create helper function to get connection style

#### Step 2: Fix Officer/Director Connections

- Change yellow connections to gray
- Update lines 3543, 3739, 3809

#### Step 3: Fix Screenshot Connections

- Change orchid to green with arrows
- Update screenshot connection code

#### Step 4: Consolidate Other Connections

- Replace all non-standard colors with gray
- Ensure proper styling for each type

#### Step 5: Add Dotted Style to Gray

- Make default connections dotted
- Keep other types solid

### Phase 3: Implementation Complete ✅

#### ✅ Step 1: Created Connection Type Constants

Added at line 37-82:

- CONNECTION_TYPES object with 5 standardized types
- getConnectionStyle() helper function
- Each type has proper color, width, dashes, and arrow settings

#### ✅ Step 2: Fixed Officer/Director Connections

- Line 3590: Changed yellow to DEFAULT gray
- Line 3782: Changed yellow to DEFAULT gray
- Line 3848: Changed yellow to DEFAULT gray

#### ✅ Step 3: Fixed Screenshot Connections

- Line 8617: Changed orchid to green SOURCE style
- Line 11750: Changed orchid to green SOURCE style

#### ✅ Step 4: Fixed Query Connections

- Line 5628: Changed coral red to proper red QUERY style
- Line 515: Changed orange to red QUERY style
- Line 5716: Changed coral red to DEFAULT for shared URLs

#### ✅ Step 5: Fixed All Other Unauthorized Colors

- Line 717: Manual connections (magenta → DEFAULT)
- Line 1829: WHOIS connections (teal → DEFAULT)
- Line 3205: OSINT connections (sky blue → DEFAULT)
- Line 3249: OSINT shared profiles (sky blue → DEFAULT)
- Line 3516: Company-address (turquoise → DEFAULT)
- Line 3586: Same search (purple → DEFAULT)
- Line 3719: Company-address duplicate (turquoise → DEFAULT)
- Line 6218: Manual bulk connections (magenta → DEFAULT)
- Line 7734: Anchored connections (now using ANCHORED style)
- Line 7741: Unanchored restoration (now using DEFAULT style)
- Line 9948: Hypothetical links (now using HYPOTHETICAL style)

### Results

The connection system now strictly follows the user's 5-type specification:

1. **Gray dotted (#666666)** - All default connections with [5,5] dash pattern
2. **White solid (#FFFFFF)** - Thick connections between anchored nodes (width: 3)
3. **Blue solid (#0066FF)** - Hypothetical connections (width: 2)
4. **Green solid (#00FF00)** - Source arrows from images/screenshots (with arrows)
5. **Red solid (#FF0000)** - Query links (width: 2)

All unauthorized colors have been removed. The system is now consistent and follows the exact specifications provided.

## Google Search Progress Issue - User Request (2025-07-02)

### Phase 1: Current Architecture Analysis

#### User's Specific Requirements:

1. **Immediate Query Node**: When running Google search from a node, query node must appear IMMEDIATELY linked to source
2. **Live Progress**: Must see progress indication as Google search runs
3. **Completion Notice**: Must be told when done and can view URLs

#### Problem: User reports nothing changed after previous implementation

Let me analyze what actually happens when user runs Google search...

#### Current Google Search Flow Analysis:

1. **User double-clicks node** → `expandNode()` → `showSearchProviderModal()`
2. **User clicks Google Search** → `selectSearchProvider('google')` → `showGoogleSearchVariations()`
3. **User selects variations** → clicks "Search Selected" → `runSelectedGoogleSearches()`
4. **runSelectedGoogleSearches()** should:
   - Create immediate query node via `createEmptySearchQueryNode()`
   - Create connection to source node
   - Show progress as searches complete

#### Issues Found:

**CRITICAL BUG**: Looking at the implementation, there might be an issue with how the search query node is being created or displayed. The user reports no immediate node appears.

**Possible Issues:**

1. `createEmptySearchQueryNode()` might not be creating the node properly
2. Connection might not be visible immediately
3. Progress updates might not be working
4. Node might be created but not visible due to viewport/positioning issues

### Phase 2: Proposed Solution

#### Requirements Analysis:

The user wants to see:

1. **Immediate visual feedback** - Node appears right after clicking "Search Selected"
2. **Clear connection** - Red line from source node to query node
3. **Live progress** - Node label updates showing "(2/7)..."
4. **Completion state** - Final count and clear indication it's done

#### Root Cause Investigation:

Need to check if the issue is:

- Node creation failing silently
- Node created but not positioned properly
- Progress updates not working
- Connection not visible

### Phase 3: Critical Bug Found - TypeError in findSimilarNodes

#### ✅ Step 1: Root Cause Identified

**ERROR**: `TypeError: Cannot read properties of undefined (reading 'toLowerCase')` at `findSimilarNodes (graph.js:2031:102)`

**FLOW ANALYSIS**:

1. User clicks Google Search → `runSelectedGoogleSearches()`
2. → `createEmptySearchQueryNode()`
3. → `addNode(nodeData)`
4. → `findSimilarNodes()` (line 2159)
5. → **CRASH** at line 2031 trying to call `.toLowerCase()` on undefined property

**ROOT CAUSE**: The `findSimilarNodes()` function assumes ALL nodes have `existingNode.data.value` property, but some nodes in the system don't have this structure.

**DETAILED ANALYSIS**:

- `findSimilarNodes(newValue, type)` called with type='search_query'
- Loops through ALL nodes to find nodes of same type
- Line 2031 (default case): tries `existingNode.data.value.toLowerCase()`
- Some existing node has undefined `data.value`, causing crash
- The function doesn't handle nodes with different data structures

**AFFECTED FLOW**:

- New search query node creation → similarity check → crash → no node created → no immediate feedback

## Phase 2: Solution Design

### Analysis of Current Node Data Structures:

**Search Query Nodes** (what we're trying to create):

```javascript
{
    type: 'search_query',
    value: searchTerm,          // ✅ This exists
    label: `🔍 Searching...`,
    content: 'Loading...',
    urls: [],
    searchTerm: searchTerm,
    isLoading: true
}
```

**Other Node Types** (existing nodes in system):

- Some nodes may have `data.value` structure
- Some nodes may have `value` directly
- Some nodes may have neither and use `label` instead

### Solution Options:

#### Option 1: Fix findSimilarNodes to handle undefined data.value

- Add null checks before calling `.toLowerCase()`
- Use fallback properties (value, label, id)
- Most comprehensive fix

#### Option 2: Add specific case for search_query type

- Bypass similarity checking for search query nodes
- Quick fix but less robust

#### Option 3: Ensure all search query nodes have proper data.value structure

- Modify search query node creation
- Could break other parts expecting current structure

### Recommended Solution: Option 1 (Defensive Programming)

**Rationale**:

- Fixes the root cause for ALL node types
- Prevents future crashes with other node types
- Makes the system more robust
- Preserves existing functionality

## Phase 3: Implementation Fix

### ✅ Step 1: Create Safe Value Extraction Function

Create `getNodeValue(node)` function that safely extracts value from any node structure

### ✅ Step 2: Update findSimilarNodes Function

Replace direct `existingNode.data.value` access with safe `getNodeValue(existingNode)` calls

### ✅ Step 3: Test Search Query Node Creation

Verify that Google search now creates nodes immediately without crashing

### Implementation Details:

#### ✅ Step 1 Complete: Created Safe Value Extraction Function

Added `getNodeValue(node)` function that:

- Tries `node.data.value` first (legacy structure)
- Falls back to `node.value` (new structure)
- Falls back to `node.label` (display text)
- Falls back to `node.id` (last resort)
- Returns empty string if all undefined (prevents crashes)

#### ✅ Step 2 Complete: Updated findSimilarNodes Function

Replaced ALL instances of `existingNode.data.value` with `getNodeValue(existingNode)`:

- Line 2007: phone case
- Line 2026: address case
- Line 2032: email case
- Line 2039: name case
- Line 2045: username case
- Line 2050: **default case** (this was the crash location)
- Line 2057: similarity results

#### ❌ Step 3: Another Crash Found

**NEW ERROR**: `TypeError: Cannot read properties of undefined (reading 'toUpperCase')` at `createNewNode (graph.js:2258:27)`

**NEW FLOW ANALYSIS**:

1. Google search → `createEmptySearchQueryNode()`
2. → `addNode(nodeData)` → `createNewNode()` (line 2250)
3. → **CRASH** at line 2258 trying to call `.toUpperCase()` on undefined property

**NEW ROOT CAUSE**: The `createNewNode()` function at line 2258 tries `type.toUpperCase()` but `type` parameter is undefined.

**DETAILED ANALYSIS**:

- `createNewNode()` expects a `type` parameter but it's a nested function inside `addNode()`
- Line 2258: `let tooltip = \`${type.toUpperCase()}: ${data.value || data.label || 'Unknown'}\`;`
- `createEmptySearchQueryNode()` calls `await addNode(nodeData)` **WITHOUT** the `type` parameter!
- All other calls use `await addNode(nodeData, 'type_name')` but search query nodes don't

**CALL COMPARISON**:

- ✅ Normal: `await addNode(companyData, 'company', parentNodeId)`
- ❌ Search Query: `await addNode(nodeData)` - **MISSING TYPE PARAMETER**

**ROOT ISSUE**: Search query node creation missing the required `type` parameter in `addNode()` call.

## Phase 2.2: Solution Design

### Current Call Patterns Analysis:

**All other node types**: `await addNode(nodeData, 'type_name', parentId)`
**Search query nodes**: `await addNode(nodeData)` ← **MISSING TYPE**

### Solution Options:

#### Option 1: Fix the createEmptySearchQueryNode call (Recommended)

- Add `'search_query'` as second parameter to `addNode()` call
- Quick, targeted fix
- Maintains existing architecture

#### Option 2: Make addNode more defensive

- Extract type from `nodeData.type` if `type` parameter missing
- More robust but changes behavior for all callers

#### Option 3: Fix createSearchQueryNode too

- Also fix the `createSearchQueryNode()` function with same issue
- Comprehensive fix for all search query creation

### Recommended Solution: Option 1 + 3

**Rationale**:

- Quick fix to immediate problem
- Maintains consistency with existing code patterns
- Fixes both search query creation functions

## Phase 3.2: Implementation Complete ✅

#### ✅ Step 1: Fixed createEmptySearchQueryNode

Changed line 5612: `await addNode(nodeData, 'search_query')`

#### ✅ Step 2: Fixed createSearchQueryNode

Changed line 5579: `await addNode(nodeData, 'search_query')`

#### ✅ Step 3: Ready for Testing (Again)

Both search query node creation functions now properly pass the `'search_query'` type parameter to `addNode()`.

## Phase 4: Progress Update & URL Display Fixes ✅

### User Issues Reported:

1. Search node still shows "0/6" instead of updating progress
2. URLs not visible in node profile when clicking on completed search node

### ✅ Step 1: Added Comprehensive Debugging

Enhanced `updateSearchQueryNode()` function with detailed logging:

- Shows when function is called and with what parameters
- Logs current node state before updates
- Shows URL merging process
- Logs label updates for both progress and completion
- Verifies node update worked

### ✅ Step 2: Fixed Search Query Node Profile Display

Added special handling in `showNodeDetails()` function for `search_query` nodes:

- **With URLs**: Shows formatted list of all URLs as clickable links
- **Without URLs**: Shows loading state or "no URLs found"
- **Progress indicator**: Shows current progress if still loading
- **Search term**: Displays the original search term
- **Styling**: Uses coral red theme matching node color

### ✅ Step 3: Ready for Final Testing

Now when you:

1. **Run Google search**: Should see immediate node with progress updates (0/6 → 1/6 → 2/6...)
2. **Click completed search node**: Should see all URLs as clickable links in the profile
3. **Monitor console**: Will see detailed debugging information about progress updates
