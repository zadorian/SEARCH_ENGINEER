# EYE-D → Drill Search SQL Integration Guide

This guide explains the changes needed in `graph.js` to enable SQL storage and graph aggregation.

## Files Created

1. **graph-sql-integration.js** - New module with SQL API calls and aggregation logic
2. **index.html** - Modified to load integration module before graph.js

## Required Changes to graph.js

### 1. Add Query Double-Click Handler (Line ~858)

**FIND** (around line 858):

```javascript
// Handle double clicks
network.on("doubleClick", function(params) {
    console.log('Double-click event triggered, params:', params);
    if (params.nodes.length > 0) {
        const nodeId = params.nodes[0];
        const node = nodes.get(nodeId);
        console.log('Double-clicked node:', nodeId, 'type:', node ? node.type : 'undefined');

        // Check if it's a query node
        if (nodeId.startsWith('query_')) {
```

**ADD BEFORE** the existing query node check:

```javascript
// Handle double clicks
network.on("doubleClick", function(params) {
    console.log('Double-click event triggered, params:', params);
    if (params.nodes.length > 0) {
        const nodeId = params.nodes[0];
        const node = nodes.get(nodeId);
        console.log('Double-clicked node:', nodeId, 'type:', node ? node.type : 'undefined');

        // SQL Integration: Check if it's a query node with SQL collapse/expand
        if (window.SQLIntegration && window.SQLIntegration.handleQueryDoubleClick(nodeId, node)) {
            return; // Handled by SQL integration
        }

        // Check if it's a query node
        if (nodeId.startsWith('query_')) {
```

### 2. Add Position Sync on Drag End (Line ~970 area)

**FIND** the `network.on("dragEnd", ...)` handler (search for "dragEnd"):

```javascript
network.on("dragEnd", function (params) {
  // existing drag end logic
});
```

**ADD INSIDE** the dragEnd handler, at the end:

```javascript
network.on("dragEnd", function (params) {
  // ... existing code ...

  // SQL Integration: Sync positions to database
  if (window.SQLIntegration && params.nodes.length > 0) {
    params.nodes.forEach(nodeId => {
      const node = nodes.get(nodeId);
      if (node && node.x !== undefined && node.y !== undefined) {
        window.SQLIntegration.schedulePositionSync(nodeId, node.x, node.y);
      }
    });
  }
});
```

### 3. Replace loadGraphState Call (Search for "loadGraphState")

**FIND** where `loadGraphState()` or `loadCacheFromStorage()` is called on initialization (likely in `window.onload` or similar):

**REPLACE**:

```javascript
// Old way:
loadCacheFromStorage();
// or
loadGraphState(graphState);
```

**WITH**:

```javascript
// SQL Integration: Check if we have a project ID from Drill Search
const urlParams = new URLSearchParams(window.location.search);
const projectId = urlParams.get("projectId");

if (projectId && window.SQLIntegration) {
  // Load from SQL database
  console.log("[Integration] Loading graph from SQL for project:", projectId);
  window.SQLIntegration.initializeSQLIntegration(projectId);
} else {
  // Fallback to file storage
  loadCacheFromStorage();
}
```

### 4. Optional: Add Node/Edge Sync on Creation

If you want to sync new nodes/edges to SQL immediately when created:

**FIND** where nodes are added (search for `nodes.add` or `addNode` function)

**ADD AFTER** successful node creation:

```javascript
// After adding node
nodes.add(newNode);

// SQL Integration: Sync to database
if (window.SQLIntegration && window.SQLIntegration.getCurrentProjectId()) {
  window.SQLIntegration.syncNodeToSQL(newNode);
}
```

**FIND** where edges are added (search for `edges.add` or `addEdge` function)

**ADD AFTER** successful edge creation:

```javascript
// After adding edge
edges.add(newEdge);

// SQL Integration: Sync to database
if (window.SQLIntegration && window.SQLIntegration.getCurrentProjectId()) {
  window.SQLIntegration.syncEdgeToSQL(newEdge);
}
```

## Testing the Integration

1. **Start both servers**:

   ```bash
   # Terminal 1: Drill Search
   cd /Users/attic/DRILL_SEARCH/drill-search-app
   pnpm dev:all

   # Terminal 2: EYE-D
   cd "/Users/attic/Library/Mobile Documents/com~apple~CloudDocs/01_ACTIVE_PROJECTS/Development/EYE-D/web"
   python3 server.py
   ```

2. **Open EYE-D with project ID**:

   ```
   http://localhost:8080?projectId=<some-project-id>
   ```

3. **Test query expand/collapse**:
   - Double-click a query node → should expand and load source URLs
   - Double-click again → should collapse and show count

4. **Test position sync**:
   - Drag a node
   - Check browser console for `[SQL Integration] Synced position...` (silent, no log)
   - Refresh page → position should be persisted

5. **Check Drill Search database**:
   ```sql
   SELECT * FROM nodes WHERE "projectId" = '<project-id>';
   SELECT * FROM edges WHERE "fromNodeId" IN (SELECT id FROM nodes WHERE "projectId" = '<project-id>');
   ```

## Aggregation Behavior

- **Queries**: Always visible, start collapsed with result count
- **Entities**: Always visible
- **Narratives**: Always visible
- **Sources**: Only visible when query is expanded
- **Double-click query**: Toggle expand/collapse
- **Shared results**: If two queries share a URL, that URL stays visible when both are collapsed (shows query-to-query connection)

## Rollback

To disable SQL integration and go back to file storage:

1. Remove `<script src="graph-sql-integration.js"></script>` from index.html
2. Remove the SQL integration code from graph.js
3. Restart EYE-D server
