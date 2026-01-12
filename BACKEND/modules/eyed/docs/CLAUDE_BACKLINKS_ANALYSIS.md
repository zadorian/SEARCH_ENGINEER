# Backlinks Feature Analysis - Phase 1

## Current State Analysis

### 1. What Currently Exists

#### Frontend (graph.js)

- **URL Node Menu** (lines 4873-4908):
  - ✅ Has TWO options already: "Get Domain Backlinks" and "Get Page Backlinks"
  - ✅ Domain option calls: `fetchAndDisplayBacklinks(node, 'domain')`
  - ✅ Page option calls: `fetchAndDisplayBacklinks(node, 'exact')`

- **fetchAndDisplayBacklinks function** (lines 4928-5020):
  - ✅ Creates a "backlinks_query" node
  - ✅ Calls backend with mode parameter
  - ✅ Stores both `urls` array AND `backlinksData` array
  - ✅ Sets proper node properties for display

- **Node Profile Display** (showNodeDetails function, lines 2677-2724):
  - ✅ ALREADY HAS COMPLETE DISPLAY CODE for backlinks_query nodes!
  - ✅ Checks for `node.type === 'backlinks_query'`
  - ✅ Shows rich backlink data with domain, URL, anchor text, etc.
  - ✅ Falls back to simple URL list if backlinksData missing

#### Backend (server.py)

- **/api/ahrefs/backlinks endpoint** (lines 2153-2228):
  - ✅ Accepts 'mode' parameter (domain/exact)
  - ✅ Properly handles both modes
  - ✅ Returns structured data

### 2. The Problem

**Everything looks correct!** The code should work. Let me investigate why it might not be working:

1. **Possible Issue #1**: The node might not have the correct properties when clicked
2. **Possible Issue #2**: The display condition might be failing
3. **Possible Issue #3**: Data might be getting lost between creation and display

### 3. Root Cause Found!

The issue is in how node properties are stored vs accessed:

1. **In fetchAndDisplayBacklinks (line 4970-4981)**:
   - Properties are set directly on the nodeData object:

   ```javascript
   const backlinksNodeData = {
     type: "backlinks_query",
     urls: backlinkUrls,
     backlinksData: backlinks,
     // ...
   };
   ```

2. **In addNode function (line 2385-2388)**:
   - All properties are wrapped under node.data:

   ```javascript
   data: {
       ...data,
       addedAt: Date.now()
   },
   ```

3. **In showNodeDetails (line 2677)**:
   - Looking for properties directly on node:

   ```javascript
   node.type === "backlinks_query" && node.urls && node.urls.length > 0;
   ```

   - Should be looking at: `node.data.urls`

**Solution**: Access properties under node.data in the display code.
