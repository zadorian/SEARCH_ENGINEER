/**
 * EYE-D → Drill Search SQL Integration Module
 * Handles graph aggregation and SQL storage bridge
 */

// ========== SQL INTEGRATION STATE ==========

// Drill Search SQL integration config
const DRILL_SEARCH_BASE_URL = "http://localhost:3000";
// currentProjectId is declared in graph.js // Active project ID from Drill Search
let expandedQueries = new Set(); // Track which query nodes are expanded (showing results)

// Sync suppression flag used by graph.js auto-sync wrappers
if (typeof window !== "undefined") {
  if (window.__SQL_INTEGRATION_ACTIVE === undefined) {
    window.__SQL_INTEGRATION_ACTIVE = false;
  }
  if (window.__SQL_INTEGRATION_SUPPRESS_SYNC === undefined) {
    window.__SQL_INTEGRATION_SUPPRESS_SYNC = false;
  }
}

// Debouncing for position updates
let positionUpdateTimeout = null;
const POSITION_UPDATE_DEBOUNCE_MS = 500;

// ========== SQL API CALLS ==========

async function getNodeCount() {
  if (!currentProjectId) return 0;

  try {
    const response = await fetch(
      `${DRILL_SEARCH_BASE_URL}/api/eyed/node-count?projectId=${currentProjectId}`
    );
    const data = await response.json();
    return data.count || 0;
  } catch (error) {
    console.error("[SQL Integration] Failed to get node count:", error);
    return 0;
  }
}

async function exportGraphFromSQL() {
  if (!currentProjectId) {
    console.warn("[SQL Integration] No active project, cannot export graph");
    return null;
  }

  try {
    const expandedQueriesArray = Array.from(expandedQueries);
    const queryParams = new URLSearchParams({
      projectId: currentProjectId,
      expandedQueries: JSON.stringify(expandedQueriesArray),
    });

    const response = await fetch(
      `${DRILL_SEARCH_BASE_URL}/api/eyed/export?${queryParams}`
    );
    const data = await response.json();

    console.log("[SQL Integration] Exported graph:", data.stats);
    return data;
  } catch (error) {
    console.error("[SQL Integration] Failed to export graph:", error);
    return null;
  }
}

async function expandQuery(queryId) {
  try {
    if (typeof window !== "undefined") {
      window.__SQL_INTEGRATION_SUPPRESS_SYNC = true;
    }
    const response = await fetch(
      `${DRILL_SEARCH_BASE_URL}/api/eyed/expand-query`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ queryId }),
      }
    );

    const data = await response.json();

    if (data.nodes && data.edges) {
      // Add query to expanded set
      expandedQueries.add(queryId);

      // Add source nodes and edges to graph
      nodes.add(data.nodes);
      edges.add(data.edges);

      // Update query node title to remove count
      const queryNode = nodes.get(queryId);
      if (queryNode && queryNode.data) {
        queryNode.title = queryNode.label;
        queryNode.data.collapsed = false;
        queryNode.data.resultCount = undefined;
        nodes.update(queryNode);
      }

      console.log(
        `[SQL Integration] Expanded query ${queryId}: added ${data.nodes.length} sources`
      );
      return true;
    }
    return false;
  } catch (error) {
    console.error("[SQL Integration] Failed to expand query:", error);
    return false;
  } finally {
    if (typeof window !== "undefined") {
      window.__SQL_INTEGRATION_SUPPRESS_SYNC = false;
    }
  }
}

async function collapseQuery(queryId) {
  try {
    if (typeof window !== "undefined") {
      window.__SQL_INTEGRATION_SUPPRESS_SYNC = true;
    }
    // Get IDs of nodes to keep (pinned/anchored sources)
    const keepSourceIds = [];
    const sourceNodes = nodes.get({
      filter: node => {
        // Find sources connected to this query
        const connectedEdges = edges.get({
          filter: edge => edge.from === queryId && edge.type === "query",
        });

        if (connectedEdges.length > 0) {
          // Keep if anchored or has other query connections
          const isAnchored = anchoredNodes.has(node.id);
          const hasOtherQueries =
            edges.get({
              filter: edge =>
                edge.to === node.id &&
                edge.from !== queryId &&
                edge.type === "query",
            }).length > 0;

          if (isAnchored || hasOtherQueries) {
            keepSourceIds.push(node.id);
            return false;
          }
          return true; // This source will be removed
        }
        return false;
      },
    });

    const response = await fetch(
      `${DRILL_SEARCH_BASE_URL}/api/eyed/collapse-query`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ queryId, keepSourceIds }),
      }
    );

    const data = await response.json();

    if (data.removedNodeIds) {
      // Remove from expanded set
      expandedQueries.delete(queryId);

      // Remove source nodes from graph
      nodes.remove(data.removedNodeIds);

      // Remove edges to those sources
      const edgesToRemove = edges
        .get({
          filter: edge =>
            data.removedNodeIds.includes(edge.to) ||
            data.removedNodeIds.includes(edge.from),
        })
        .map(e => e.id);

      edges.remove(edgesToRemove);

      // Update query node to show count
      const queryNode = nodes.get(queryId);
      if (queryNode && queryNode.data) {
        const resultCount = data.removedNodeIds.length;
        queryNode.title = `${queryNode.label}\n${resultCount} results`;
        queryNode.data.collapsed = true;
        queryNode.data.resultCount = resultCount;
        nodes.update(queryNode);
      }

      console.log(
        `[SQL Integration] Collapsed query ${queryId}: removed ${data.removedNodeIds.length} sources`
      );
      return true;
    }
    return false;
  } catch (error) {
    console.error("[SQL Integration] Failed to collapse query:", error);
    return false;
  } finally {
    if (typeof window !== "undefined") {
      window.__SQL_INTEGRATION_SUPPRESS_SYNC = false;
    }
  }
}

async function syncNodeToSQL(node) {
  try {
    const response = await fetch(
      `${DRILL_SEARCH_BASE_URL}/api/eyed/sync-node`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ node }),
      }
    );

    const data = await response.json();

    if (data.success) {
      console.log(
        `[SQL Integration] Synced node ${node.id} → SQL ID ${data.sqlNodeId}`
      );
      return data.sqlNodeId;
    } else if (data.skipped) {
      console.log(`[SQL Integration] Skipped node ${node.id}: ${data.reason}`);
      return null;
    }
    return null;
  } catch (error) {
    console.error("[SQL Integration] Failed to sync node:", error);
    return null;
  }
}

async function syncPositionToSQL(nodeId, x, y) {
  try {
    const response = await fetch(
      `${DRILL_SEARCH_BASE_URL}/api/eyed/sync-position`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nodeId, x, y }),
      }
    );

    const data = await response.json();

    if (data.success) {
      // Silent success - no logging for position updates
      return true;
    }
    return false;
  } catch (error) {
    console.error("[SQL Integration] Failed to sync position:", error);
    return false;
  }
}

async function syncEdgeToSQL(edge) {
  try {
    const response = await fetch(
      `${DRILL_SEARCH_BASE_URL}/api/eyed/sync-edge`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ edge }),
      }
    );

    const data = await response.json();

    if (data.success) {
      console.log(
        `[SQL Integration] Synced edge ${edge.id} → SQL ID ${data.sqlEdgeId}`
      );
      return data.sqlEdgeId;
    }
    return null;
  } catch (error) {
    console.error("[SQL Integration] Failed to sync edge:", error);
    return null;
  }
}

// ========== ENHANCED DOUBLE-CLICK HANDLER ==========

/**
 * Enhanced double-click handler with query expansion/collapse
 * Call this BEFORE the existing double-click logic in graph.js
 */
function handleQueryDoubleClick(nodeId, node) {
  // Check if it's a query node with data.collapsed flag
  if (node && node.data && node.data.sqlClassName === "query") {
    const isCollapsed = node.data.collapsed !== false; // Default to collapsed

    if (isCollapsed) {
      // Expand: load all source results
      console.log(`[SQL Integration] Expanding query: ${nodeId}`);
      expandQuery(nodeId);
    } else {
      // Collapse: hide source results (keep pinned/shared ones)
      console.log(`[SQL Integration] Collapsing query: ${nodeId}`);
      collapseQuery(nodeId);
    }

    return true; // Handled
  }

  return false; // Not a query node, let existing handler process it
}

// ========== POSITION SYNC WITH DEBOUNCING ==========

/**
 * Debounced position sync
 * Call this from network.on('dragEnd') or network.stabilizationIterationsDone
 */
function schedulePositionSync(nodeId, x, y) {
  // Clear existing timeout
  if (positionUpdateTimeout) {
    clearTimeout(positionUpdateTimeout);
  }

  // Schedule new update
  positionUpdateTimeout = setTimeout(() => {
    syncPositionToSQL(nodeId, x, y);
  }, POSITION_UPDATE_DEBOUNCE_MS);
}

// ========== INITIALIZATION ==========

/**
 * Initialize SQL integration and load graph from SQL
 * Call this INSTEAD of loadGraphState on app start
 */
async function initializeSQLIntegration(projectId) {
  console.log("[SQL Integration] Initializing for project:", projectId);

  if (typeof window !== "undefined") {
    window.__SQL_INTEGRATION_ACTIVE = true;
    window.__SQL_INTEGRATION_SUPPRESS_SYNC = true;
  }

  currentProjectId = projectId;

  // Check node count
  const nodeCount = await getNodeCount();
  console.log(`[SQL Integration] Project has ${nodeCount} nodes`);

  if (nodeCount > 1000) {
    console.warn(
      "[SQL Integration] Large graph detected. Consider filtering or manual selection."
    );
    // TODO: Show UI to let user filter before loading
    if (typeof window !== "undefined") {
      window.__SQL_INTEGRATION_SUPPRESS_SYNC = false;
    }
    return;
  }

  // Load graph from SQL
  const graphData = await exportGraphFromSQL();

  if (graphData) {
    // Clear existing graph
    nodes.clear();
    edges.clear();

    // Load nodes
    if (graphData.nodes && graphData.nodes.length > 0) {
      nodes.add(graphData.nodes);
      console.log(`[SQL Integration] Loaded ${graphData.nodes.length} nodes`);
    }

    // Load edges
    if (graphData.edges && graphData.edges.length > 0) {
      edges.add(graphData.edges);
      console.log(`[SQL Integration] Loaded ${graphData.edges.length} edges`);
    }

    // Log stats
    if (graphData.stats) {
      console.log("[SQL Integration] Graph stats:", graphData.stats);
    }

    // Reset expanded queries (all start collapsed)
    expandedQueries.clear();
  }

  if (typeof window !== "undefined") {
    window.__SQL_INTEGRATION_SUPPRESS_SYNC = false;
  }
}

/**
 * Legacy save/load override
 * Replace calls to saveGraphState with this
 */
async function saveGraphStateToSQL() {
  console.log(
    "[SQL Integration] Graph state is auto-synced to SQL on each change"
  );
  // No-op: positions are synced on drag, nodes/edges synced on creation
  // We don't need full-graph saves anymore
}

// ========== EXPORTS ==========

// Export functions for use in graph.js
window.SQLIntegration = {
  initializeSQLIntegration,
  handleQueryDoubleClick,
  schedulePositionSync,
  syncNodeToSQL,
  syncEdgeToSQL,
  expandQuery,
  collapseQuery,
  saveGraphStateToSQL,
  getNodeCount,

  // State accessors
  getCurrentProjectId: () => currentProjectId,
  getExpandedQueries: () => Array.from(expandedQueries),
  setProjectId: projectId => {
    currentProjectId = projectId;
  },
};

console.log("[SQL Integration] Module loaded");
