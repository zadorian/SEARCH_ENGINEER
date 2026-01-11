// Graph visualization for DeHashed data
let network = null;
let nodes = null;
let edges = null;
let nodeIdCounter = 0;
let searchCache = new Map(); // Cache for search results
let nodeExpansionCache = new Map(); // Track which nodes have been expanded
let valueToNodeMap = new Map(); // Map values to node IDs for deduplication
let breachConnections = new Map(); // Map breach names to node arrays
let focusedNode = null; // Currently focused node
let originalNodeColors = new Map(); // Store original colors during focus
let isGroupDrag = false; // Track if we're doing a group drag
let initialPositions = null; // Store initial positions for group drag
let currentProfileNode = null; // Currently edited node
let includeHashedPasswords = false; // Option to include hashed passwords
let showArrows = false; // Option to show arrow direction on edges
let showImageSources = true; // Option to show/hide image source connections
let showConnectionLabels = false; // Option to show/hide connection labels
let nodeSearchQueries = new Map(); // Map to store search relationships for query nodes
let anchoredNodes = new Set(); // Set of anchored node IDs
let selectedNodes = new Set(); // Currently selected nodes
let connectionMode = false; // Track if we're in connection mode
let connectionSourceNode = null; // Source node for creating connections
let connectionLine = null; // Visual line while dragging

// Universal Undo system - stores complete graph states
let undoStack = []; // Stack of complete graph states
const MAX_UNDO_STACK_SIZE = 20; // Limit undo history (fewer since we store full states)
let isRestoringFromUndo = false; // Prevent undo operations from creating new undo states

// Cluster system
let clusters = new Map(); // Map cluster IDs to cluster data
let clusterIdCounter = 0;
let showClusterContents = true; // Toggle to show/hide nodes inside clusters
let clusterConnections = new Map(); // Map cluster connections to simplified edges

const INFO_PANEL_DEFAULT_WIDTH = 320;
let infoPanelCollapsed = true;

// Unified UI palette to match Drill Search styling
const UI_COLORS = {
    accent: '#38bdf8',
    accentStrong: '#1d4ed8',
    accentSoft: 'rgba(56, 189, 248, 0.18)',
    border: 'rgba(56, 189, 248, 0.35)',
    surface: '#0f172a',
    surfaceMuted: 'rgba(15, 23, 42, 0.9)',
    textPrimary: '#e2e8f0',
    textMuted: '#cbd5f5',
    warning: '#f97316',
    danger: '#f43f5e'
};

// Standardized Connection Types (per user specification)
const CONNECTION_TYPES = {
    DEFAULT: {
        color: '#666666',     // Gray
        width: 1,
        dashes: [5, 5],      // Dotted
        smooth: false
    },
    ANCHORED: {
        color: '#FFFFFF',     // White
        width: 3,            // Thick
        dashes: false,       // Solid
        smooth: false
    },
    HYPOTHETICAL: {
        color: '#0066FF',     // Blue
        width: 2,
        dashes: false,       // Solid
        smooth: false
    },
    SOURCE: {
        color: UI_COLORS.accent,
        width: 2,
        dashes: false,       // Solid
        arrows: { to: { enabled: true, scaleFactor: 0.8 } },
        smooth: false
    },
    QUERY: {
        color: UI_COLORS.danger,
        width: 2,
        dashes: false,       // Solid
        smooth: false
    }
};

// Helper function to get connection style
function getConnectionStyle(type = 'DEFAULT') {
    const style = CONNECTION_TYPES[type] || CONNECTION_TYPES.DEFAULT;
    return {
        color: { color: style.color },
        width: style.width,
        dashes: style.dashes,
        smooth: style.smooth,
        arrows: style.arrows || { to: { enabled: false } }
    };
}

function setInfoPanelCollapsed(collapsed, options = {}) {
    const infoPanel = document.getElementById('info-panel');
    const toggleButton = document.getElementById('info-panel-toggle');
    if (!infoPanel) {
        return;
    }

    infoPanelCollapsed = collapsed;

    if (collapsed) {
        infoPanel.dataset.prevWidth = infoPanel.style.width || infoPanel.dataset.prevWidth || `${INFO_PANEL_DEFAULT_WIDTH}px`;
        infoPanel.classList.add('collapsed');
        infoPanel.style.width = '0px';
        if (toggleButton) {
            toggleButton.textContent = 'Show Details';
        }
    } else {
        infoPanel.classList.remove('collapsed');
        const savedWidth = localStorage.getItem('infoPanelWidth') || infoPanel.dataset.prevWidth || `${INFO_PANEL_DEFAULT_WIDTH}px`;
        infoPanel.style.width = savedWidth;
        if (toggleButton) {
            toggleButton.textContent = 'Hide Details';
        }
    }

    if (!options.skipSave) {
        localStorage.setItem('infoPanelCollapsed', collapsed ? 'true' : 'false');
    }
}

// Load cache from disk on startup
async function loadCacheFromStorage() {
    try {
        const response = await fetch('/api/cache/load');
        const result = await response.json();
        
        if (result.data) {
            // Load search cache
            if (result.data.search_cache) {
                // Convert object back to Map
                searchCache = new Map(Object.entries(result.data.search_cache));
                console.log(`Loaded ${searchCache.size} cached searches from disk`);
            }
            
            // Return graph state for loading
            return result.data.graph_state;
        }
    } catch (e) {
        console.error('Error loading cache from disk:', e);
    }
    return null;
}

// Save cache to disk
async function saveCacheToStorage() {
    try {
        // Convert Map to object for serialization
        const cacheObj = {};
        searchCache.forEach((value, key) => {
            cacheObj[key] = value;
        });
        
        const data = {
            search_cache: cacheObj
        };
        
        const response = await fetch('/api/cache/save', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        if (result.success) {
            console.log(`Saved ${searchCache.size} searches to disk`);
        }
    } catch (e) {
        console.error('Error saving cache to disk:', e);
    }
}

// Save graph state to disk
async function saveGraphState() {
    try {
        const graphState = {
            nodes: nodes.get(),
            edges: edges.get(),
            nodeIdCounter: nodeIdCounter,
            valueToNodeMap: Array.from(valueToNodeMap.entries()),
            breachConnections: Array.from(breachConnections.entries()),
            nodeSearchQueries: Array.from(nodeSearchQueries.entries()),
            autoShowQueries: autoShowQueries,
            anchoredNodes: Array.from(anchoredNodes)
        };
        
        const data = {
            graph_state: graphState
        };
        
        const response = await fetch('/api/cache/save', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        if (result.success) {
            console.log('Graph state saved to disk');
        }
    } catch (e) {
        console.error('Error saving graph state to disk:', e);
    }
}

// Load graph state from disk (now done via loadCacheFromStorage)
function loadGraphState(graphState) {
    try {
        if (graphState) {
            // Clear existing data first to avoid duplicates
            nodes.clear();
            edges.clear();
            
            // Restore nodes with their saved positions
            if (graphState.nodes) {
                // Ensure each node has its position
                graphState.nodes.forEach(node => {
                    // vis.js needs x and y at the top level
                    if (node.x === undefined || node.y === undefined) {
                        // If position is missing, give it a default
                        node.x = Math.random() * 1000 - 500;
                        node.y = Math.random() * 1000 - 500;
                    }
                });
                nodes.add(graphState.nodes);
            }
            
            // Restore edges and fix their colors
            if (graphState.edges) {
                // Harmonize legacy edge colors with current accent palette
                graphState.edges.forEach(edge => {
                    if (edge.color) {
                        if (edge.color === '#00ff00' || edge.color === '#0f0') {
                            edge.color = UI_COLORS.accent;
                        } else if (edge.color.color === '#00ff00' || edge.color.color === '#0f0') {
                            edge.color.color = UI_COLORS.accent;
                        }
                    }
                });
                edges.add(graphState.edges);
            }
            
            // Restore counters
            if (graphState.nodeIdCounter) {
                nodeIdCounter = graphState.nodeIdCounter;
            }
            
            // Restore value map with case-insensitive migration
            if (graphState.valueToNodeMap) {
                valueToNodeMap = new Map();
                // Migrate old case-sensitive keys to case-insensitive
                for (const [oldKey, nodeId] of graphState.valueToNodeMap) {
                    // Extract type and value from old key
                    const parts = oldKey.split('_');
                    if (parts.length >= 2) {
                        const type = parts[0];
                        const value = parts.slice(1).join('_');
                        // Create new case-insensitive key
                        const newKey = `${type}_${value.toLowerCase().trim()}`;
                        valueToNodeMap.set(newKey, nodeId);
                    } else {
                        // Fallback for malformed keys
                        valueToNodeMap.set(oldKey, nodeId);
                    }
                }
            }
            
            // Restore breach connections
            if (graphState.breachConnections) {
                breachConnections = new Map(graphState.breachConnections);
                
                // Rebuild breach connections if edges are missing
                breachConnections.forEach((nodeIds, breachName) => {
                    console.log(`Checking breach ${breachName} with ${nodeIds.length} nodes`);
                    
                    // Check if connections exist
                    let hasConnections = false;
                    if (nodeIds.length >= 2) {
                        const testEdge = edges.get({
                            filter: edge => edge.title && edge.title.includes(breachName)
                        });
                        hasConnections = testEdge.length > 0;
                    }
                    
                    // Recreate connections if missing
                    if (!hasConnections && nodeIds.length >= 2) {
                        console.log(`Recreating connections for breach: ${breachName}`);
                        connectBreachNodes(nodeIds, breachName);
                    }
                });
            }
            
            // Restore search queries
            if (graphState.nodeSearchQueries) {
                nodeSearchQueries = new Map(graphState.nodeSearchQueries);
                console.log(`Loaded ${nodeSearchQueries.size} search queries`);
            }
            
            // Restore active query nodes
            if (graphState.activeQueryNodes) {
                activeQueryNodes = new Map(graphState.activeQueryNodes);
                console.log(`Loaded ${activeQueryNodes.size} active query nodes`);
            }
            
            // Restore autoShowQueries state and update checkbox
            if (graphState.autoShowQueries !== undefined) {
                autoShowQueries = graphState.autoShowQueries;
                const checkbox = document.getElementById('showQueries');
                if (checkbox) {
                    checkbox.checked = autoShowQueries;
                }
            }
            
            // Restore anchored nodes
            if (graphState.anchoredNodes) {
                anchoredNodes = new Set(graphState.anchoredNodes);
                console.log(`Loaded ${anchoredNodes.size} anchored nodes`);
            }
            
            // Restore clusters
            if (graphState.clusters) {
                clusters = new Map(graphState.clusters);
                console.log(`Loaded ${clusters.size} clusters`);
            }
            
            // Restore cluster ID counter
            if (graphState.clusterIdCounter !== undefined) {
                clusterIdCounter = graphState.clusterIdCounter;
            }
            
            // Update colors and physics for loaded nodes
            const allNodes = nodes.get();
            const updates = [];
            allNodes.forEach(node => {
                let needsUpdate = false;
                const update = { id: node.id };
                
                // Update password node colors
                if (node.type === 'password' || node.type === 'hashed_password') {
                    const newColor = getNodeColor(node.type);
                    update.color = {
                        background: '#000000',
                        border: newColor,
                        highlight: {
                            background: '#1a1a1a',
                            border: newColor
                        }
                    };
                    needsUpdate = true;
                }
                
                // Ensure check indicators have correct physics
                if (node.isCheckIndicator) {
                    update.physics = true;
                    update.mass = 0.1;
                    update.fixed = { x: false, y: false };
                    update.chosen = { node: true, label: true };
                    needsUpdate = true;
                }
                
                // Ensure query nodes have correct physics
                if (node.isQueryNode || node.id.startsWith('query_')) {
                    update.physics = true;
                    update.mass = 1;
                    update.fixed = { x: false, y: false };
                    update.chosen = { node: true, label: true };
                    needsUpdate = true;
                }
                
                // Ensure regular nodes have physics disabled
                if (!node.isCheckIndicator && !node.isQueryNode && !node.id.startsWith('query_') && !node.id.startsWith('check_')) {
                    update.physics = false;
                    needsUpdate = true;
                }
                
                // Apply anchored node styling - ONLY background color
                if (anchoredNodes.has(node.id)) {
                    const typeColor = getNodeColor(node.type);
                    update.borderWidth = 2;  // NORMAL border
                    update.borderWidthSelected = 3;  // NORMAL selected
                    update.size = undefined;  // DEFAULT size
                    update.color = {
                        background: '#000000',  // Black background
                        border: typeColor,
                        highlight: {
                            background: '#1a1a1a',
                            border: typeColor
                        }
                    };
                    update.font = {
                        color: '#FFFFFF'  // White text - ONLY CHANGE
                    };
                    needsUpdate = true;
                }
                
                if (needsUpdate) {
                    updates.push(update);
                }
            });
            if (updates.length > 0) {
                nodes.update(updates);
                console.log(`Updated ${updates.length} nodes with correct properties`);
            }
            
            console.log(`Loaded graph with ${nodes.get().length} nodes and ${edges.get().length} edges`);
            return true;
        }
        return false;
    } catch (e) {
        console.error('Error loading graph state:', e);
        return false;
    }
}

// Track active query nodes
let activeQueryNodes = new Map();
// Track visible search indicators
let visibleSearchIndicators = new Set();

// Draw search indicators on nodes
function drawSearchIndicators() {
    // COMPLETELY DISABLED - NO INDICATORS
    return;
}

// Remove all fucking indicator circles
function removeAllIndicators() {
    if (!nodes) return;
    
    const allNodes = nodes.get();
    const indicatorNodes = allNodes.filter(node => 
        node.isCheckIndicator || node.isMergeIndicator || 
        node.id.startsWith('check_') || node.id.startsWith('merge_')
    );
    
    indicatorNodes.forEach(node => {
        // Remove associated edges
        const connectedEdges = edges.get({
            filter: edge => edge.from === node.id || edge.to === node.id
        });
        connectedEdges.forEach(edge => edges.remove(edge.id));
        
        // Remove the node
        nodes.remove(node.id);
    });
    
    updateStatus(`Removed ${indicatorNodes.length} indicator circles`);
}

// Call this immediately to remove existing circles
if (typeof nodes !== 'undefined' && nodes) {
    removeAllIndicators();
}

// Function to call from console to remove circles
window.removeCircles = function() {
    if (nodes) {
        removeAllIndicators();
        console.log("All indicator circles removed!");
    }
}

// Toggle query node (transform check to query node and back)
function toggleQueryNode(searchKey) {
    const searchData = nodeSearchQueries.get(searchKey);
    if (!searchData) return;
    
    const sourceNode = nodes.get(searchData.sourceNode);
    if (!sourceNode) return;
    
    const queryNodeId = 'query_' + searchData.sourceNode;
    const existingQueryNode = nodes.get(queryNodeId);
    
    if (existingQueryNode) {
        // Query node exists - remove it and its edges
        hideQueryNode(queryNodeId);
    } else {
        // Create query node in place of the check
        const sourcePos = network.getPositions([searchData.sourceNode])[searchData.sourceNode];
        const canvasPos = network.canvasToDOM(sourcePos);
        
        // Remove the check node first
        const checkNodeId = 'check_' + searchData.sourceNode;
        if (nodes.get(checkNodeId)) {
            edges.remove('edge_' + searchData.sourceNode + '_' + checkNodeId);
            nodes.remove(checkNodeId);
        }
        
        const queryNode = {
            id: queryNodeId,
            label: searchData.query,
            title: `Query for: ${searchData.query}\nFound ${searchData.results.length} results\nDouble-click to minimize back to check`,
            color: {
                background: '#000000',
                border: '#ff0000',
                highlight: {
                    background: '#330000',
                    border: '#ff0000'
                }
            },
            borderWidth: 3,
            borderWidthSelected: 4,
            font: {
                color: '#ff0000',
                size: 12,
                face: 'monospace',
                bold: true
            },
            shape: 'box',
            x: sourcePos.x + 200 + Math.random() * 200,
            y: sourcePos.y - 200 - Math.random() * 200,
            isQueryNode: true,
            physics: true,
            mass: 1,
            fixed: {
                x: false,
                y: false
            },
            chosen: {
                node: true,
                label: true
            }
        };
        
        nodes.add(queryNode);
        activeQueryNodes.set(queryNodeId, searchData);
        
        // Add edge from source to query node
        if (searchData.sourceNode !== queryNodeId) {
            edges.add({
                id: 'edge_' + searchData.sourceNode + '_' + queryNodeId,
                from: searchData.sourceNode,
                to: queryNodeId,
                color: {
                    color: '#ff0000'
                },
                dashes: [5, 5],
                width: 1
            });
        }
        
        // Add edges from query node to all results
        searchData.results.forEach(resultId => {
            if (queryNodeId !== resultId) {
                edges.add({
                id: 'edge_' + queryNodeId + '_' + resultId,
                from: queryNodeId,
                to: resultId,
                ...getConnectionStyle('QUERY')
            });
            }
        });
        
        // Redraw indicators to hide the check for this node
        drawSearchIndicators();
    }
}

// Hide query node and restore check indicator
function hideQueryNode(queryNodeId, showCheckBriefly = true) {
    // Remove all edges connected to this query node
    const connectedEdges = edges.get({
        filter: edge => edge.from === queryNodeId || edge.to === queryNodeId
    });
    connectedEdges.forEach(edge => edges.remove(edge.id));
    
    // Remove the query node
    nodes.remove(queryNodeId);
    activeQueryNodes.delete(queryNodeId);
    
    if (autoShowQueries) {
        // Show check briefly then hide it
        drawSearchIndicators();
        setTimeout(() => {
            drawSearchIndicators(); // This will hide the check for this specific node
        }, 500);
    } else {
        // Don't show checks at all when queries toggle is off
        clearSearchIndicators();
    }
}

// Add merge indicator outside node - DISABLED
function addMergeIndicator(nodeId, count) {
    // COMPLETELY DISABLED - NO INDICATORS
    return;
}

// Clear search indicators
function clearSearchIndicators() {
    // Remove DOM indicators if any
    const indicators = document.querySelectorAll('.search-indicator');
    indicators.forEach(indicator => indicator.remove());
    
    // Remove check nodes
    const checkNodes = nodes.get({
        filter: node => node.isCheckIndicator === true
    });
    
    checkNodes.forEach(node => {
        // Remove edge to check node
        edges.remove('edge_' + node.parentNodeId + '_' + node.id);
        // Remove check node
        nodes.remove(node.id);
    });
}

// -----------------------------------------------------------------------------
// C-1 (Cymonides-1) Integration: auto-sync node/edge creation to Elasticsearch
// -----------------------------------------------------------------------------

function isC1IntegrationActive() {
    return (
        typeof window !== 'undefined' &&
        window.C1Integration &&
        typeof window.C1Integration.getCurrentProjectId === 'function' &&
        !!window.C1Integration.getCurrentProjectId()
    );
}

function isC1SyncSuppressed() {
    return (
        typeof window !== 'undefined' &&
        window.C1Integration &&
        typeof window.C1Integration.isSyncSuppressed === 'function' &&
        window.C1Integration.isSyncSuppressed() === true
    );
}

function shouldSyncNodeToC1(node) {
    if (!node) return false;
    const nodeId = String(node.id || '');
    if (node.shape === 'image') return false;
    if (node.data && (node.data.type === 'image' || node.data.dataURL)) return false;
    if (node.isCheckIndicator || node.isMergeIndicator) return false;
    if (nodeId.startsWith('check_') || nodeId.startsWith('merge_')) return false;
    if (nodeId.startsWith('query_') || node.isQueryNode) return false;
    if (node.type === 'query') return false;
    if (node.type === 'cluster' || node.type === 'cluster_inner') return false;
    return true;
}

function shouldSyncEdgeToC1(edge) {
    if (!edge) return false;
    const from = String(edge.from || '');
    const to = String(edge.to || '');
    if (!from || !to) return false;
    if (from.startsWith('check_') || from.startsWith('merge_') || from.startsWith('query_')) return false;
    if (to.startsWith('check_') || to.startsWith('merge_') || to.startsWith('query_')) return false;
    return true;
}

function installC1AutoSync() {
    if (!nodes || !edges) return;
    if (nodes.__c1AutoSyncInstalled) return;

    const originalNodesAdd = nodes.add.bind(nodes);
    nodes.add = function(data, senderId) {
        const ids = originalNodesAdd(data, senderId);

        if (isC1IntegrationActive() && !isC1SyncSuppressed() && window.C1Integration.syncNodeToC1) {
            const items = Array.isArray(data) ? data : (data ? [data] : []);
            items.forEach(node => {
                if (!shouldSyncNodeToC1(node)) return;
                Promise.resolve(window.C1Integration.syncNodeToC1(node)).catch(err => {
                    console.error('[C-1] Failed to sync node:', err);
                });
            });
        }

        return ids;
    };
    nodes.__c1AutoSyncInstalled = true;

    const originalEdgesAdd = edges.add.bind(edges);
    edges.add = function(data, senderId) {
        const ids = originalEdgesAdd(data, senderId);

        if (isC1IntegrationActive() && !isC1SyncSuppressed() && window.C1Integration.syncEdgeToC1) {
            const items = Array.isArray(data) ? data : (data ? [data] : []);
            items.forEach(edge => {
                if (!shouldSyncEdgeToC1(edge)) return;
                Promise.resolve(window.C1Integration.syncEdgeToC1(edge)).catch(err => {
                    console.error('[C-1] Failed to sync edge:', err);
                });
            });
        }

        return ids;
    };
    edges.__c1AutoSyncInstalled = true;
}

// Initialize the graph
function initializeGraph() {
    // Create empty datasets
    nodes = new vis.DataSet([]);
    edges = new vis.DataSet([]);

    // Install C-1 auto-sync wrappers once
    installC1AutoSync();
    
    // Container for the graph
    const container = document.getElementById('network');
    
    // Data for the graph
    const data = {
        nodes: nodes,
        edges: edges
    };
    
    // Options for the graph
    const options = {
        nodes: {
            shape: 'box',
            font: {
                size: 12,
                face: 'monospace',
                multi: true // Allow line breaks
            },
            borderWidth: 2,
            shadow: false,  // No shadow unless selected
            widthConstraint: {
                maximum: 400, // Increased max width
                minimum: 100  // Min width
            },
            margin: 10 // Add padding inside nodes
        },
        edges: {
            arrows: {
                to: {
                    enabled: showArrows,
                    scaleFactor: 0.8
                }
            },
            color: {
                color: '#666666',
                highlight: '#ff0000'
            },
            width: 2,
            smooth: {
                type: 'cubicBezier'
            },
            font: {
                color: '#666666',
                size: 10,
                face: 'monospace',
                align: 'middle'
            }
        },
        physics: {
            enabled: true, // Enable physics for check nodes to move with graph
            solver: 'barnesHut',
            barnesHut: {
                gravitationalConstant: -50,
                centralGravity: 0,
                springLength: 50,
                springConstant: 0.001,
                damping: 0.9,
                avoidOverlap: 0.5
            },
            stabilization: {
                enabled: false // Don't auto-stabilize
            }
        },
        interaction: {
            hover: true,
            tooltipDelay: 300,
            dragNodes: true,
            dragView: true,
            navigationButtons: false,
            multiselect: true,  // Enable multi-select with shift/ctrl
            selectConnectedEdges: false
        },
        manipulation: {
            enabled: false
        }
    };
    
    // Create the network
    network = new vis.Network(container, data, options);
    
    
    // Only update search indicators when needed, not constantly
    // This was causing performance issues and interfering with interactions
    
    // Remove anchor icon drawing - just use visual node properties
    
    // Save positions after network stabilizes (including after zoom/pan)
    let saveTimer = null;
    network.on("stabilized", function() {
        // Debounce saves
        if (saveTimer) clearTimeout(saveTimer);
        saveTimer = setTimeout(() => {
            // Update node positions
            const allNodeIds = nodes.getIds();
            const positions = network.getPositions(allNodeIds);
            const updates = [];
            
            for (let nodeId in positions) {
                if (positions[nodeId]) {
                    const node = nodes.get(nodeId);
                    if (node && (node.x !== positions[nodeId].x || node.y !== positions[nodeId].y)) {
                        updates.push({
                            id: nodeId,
                            x: positions[nodeId].x,
                            y: positions[nodeId].y
                        });
                    }
                }
            }
            
            if (updates.length > 0) {
                nodes.update(updates);
                saveGraphState();
            }
        }, 500); // Wait 500ms after stabilization to save
    });
    
    // Handle node clicks
    network.on("click", function(params) {
        // Reset any drag issues
        isGroupDrag = false;
        initialPositions = null;
        draggedNode = null;
        
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            const node = nodes.get(nodeId);
            
            // Handle connection mode
            if (connectionMode && connectionSourceNode) {
                if (nodeId !== connectionSourceNode) {
                    // Create connection
                    const connectionName = prompt('Enter connection name/reason:') || 'Manual connection';
                    
                    edges.add({
                        from: connectionSourceNode,
                        to: nodeId,
                        ...getConnectionStyle('DEFAULT'),
                        title: connectionName,
                        arrows: showArrows ? 'to' : ''
                    });
                    
                    updateStatus(`Connected ${connectionSourceNode} to ${nodeId}`);
                    saveGraphState();
                }
                
                // Exit connection mode
                cancelConnectionMode();
                return;
            }
            
            // Handle hypothetical link mode
            if (window.hypotheticalLinkMode && window.hypotheticalLinkSourceNode) {
                handleHypotheticalLinkClick(nodeId);
                return;
            }
            
            // Special handling for query nodes
            if (nodeId.startsWith('query_')) {
                const searchData = activeQueryNodes.get(nodeId);
                if (searchData) {
                    // Show the exact search variations in the details panel
                    const detailsDiv = document.getElementById('node-details');
                    const sourceNode = nodes.get(searchData.sourceNode);
                    let html = `
                        <div style="background:${UI_COLORS.surface}; padding:12px; border: 1px solid ${UI_COLORS.border}; border-radius: 12px;">
                            <h3 style="color:${UI_COLORS.accent}; margin:0;">Query Node Details</h3>
                            <table style="width: 100%; margin-top: 12px; font-size: 12px; border-collapse: collapse;">
                                <tr><td style="color:${UI_COLORS.textMuted}; width: 40%; padding:4px 0;">Search Query:</td><td style="color:${UI_COLORS.accent};">${escapeHtml(searchData.query)}</td></tr>
                                <tr><td style="color:${UI_COLORS.textMuted}; padding:4px 0;">Source Node:</td><td style="color:${UI_COLORS.accent};">${sourceNode ? sourceNode.type + ': ' + sourceNode.label : searchData.sourceNode}</td></tr>
                                <tr><td style="color:${UI_COLORS.textMuted}; padding:4px 0;">Search Time:</td><td style="color:${UI_COLORS.accent};">${new Date(searchData.timestamp).toLocaleString()}</td></tr>
                                <tr><td style="color:${UI_COLORS.textMuted}; padding:4px 0;">Results Found:</td><td style="color:${UI_COLORS.accent};">${searchData.results.length}</td></tr>
                            </table>
                            <hr style="border-color:${UI_COLORS.border}; margin: 16px 0;">
                            <h4 style="color:${UI_COLORS.textMuted}; text-transform: uppercase; letter-spacing:0.18em; font-size:11px;">Search Results</h4>
                            <ul style="color:${UI_COLORS.accent}; list-style: none; padding: 0; margin: 8px 0 0;">
                    `;
                    searchData.results.forEach(resultId => {
                        const resultNode = nodes.get(resultId);
                        if (resultNode) {
                            const typeColor = getNodeColor(resultNode.type);
                            html += `<li style="margin: 5px 0; padding: 5px; border-left: 3px solid ${typeColor};">
                                        <span style="color: ${typeColor};">${resultNode.type.toUpperCase()}</span>: 
                                        <span style="color: ${UI_COLORS.accent};">${escapeHtml(resultNode.label)}</span>
                                     </li>`;
                        }
                    });
                    html += `
                            </ul>
                            <div style="margin-top: 16px; padding: 10px; background:${UI_COLORS.surfaceMuted}; border: 1px solid ${UI_COLORS.border}; border-radius: 10px;">
                                <p style="color:${UI_COLORS.textMuted}; font-size: 11px; margin: 0; letter-spacing:0.1em;">ℹ️ Double-click the query node to minimize it back to a check indicator</p>
                            </div>
                        </div>
                    `;
                    detailsDiv.innerHTML = html;
                }
            } else if (node && node.isCheckIndicator) {
                // Show info for check indicators
                const searchKey = node.searchKey;
                const searchData = nodeSearchQueries.get(searchKey);
                if (searchData) {
                    const detailsDiv = document.getElementById('node-details');
                    detailsDiv.innerHTML = `
                        <div style="background:${UI_COLORS.surface}; padding:12px; border:1px solid ${UI_COLORS.border}; border-radius:12px;">
                            <h3 style="color:${UI_COLORS.accent}; margin:0;">Search Indicator</h3>
                            <p style="color:${UI_COLORS.textMuted}; margin:8px 0 4px;">This node has been searched</p>
                            <p style="color:${UI_COLORS.accent}; margin:4px 0;">Found ${searchData.results.length} results</p>
                            <p style="color:${UI_COLORS.textMuted}; margin-top:12px; font-size:11px; letter-spacing:0.1em;">Double-click to expand and see search results</p>
                        </div>
                    `;
                }
            } else {
                showNodeDetails(node);
            }
        }
    });
    
    // Update node list when nodes are added/removed
    nodes.on('add', function() {
        if (document.getElementById('panel-nodes').classList.contains('active')) {
            updateNodeList();
        }
    });
    
    nodes.on('remove', function() {
        if (document.getElementById('panel-nodes').classList.contains('active')) {
            updateNodeList();
        }
    });
    
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
                console.log('Double-clicked query node:', nodeId);
                hideQueryNode(nodeId);
                return;
            } 
            // Check if it's a check indicator
            else if (node && node.isCheckIndicator) {
                // Transform check to query node
                const searchKey = node.searchKey;
                toggleQueryNode(searchKey);
                return;
            }
            // Check if it's a URL node
            else if (node && node.type === 'url') {
                console.log('Double-clicked URL node - calling showUrlOptionsMenu');
                showUrlOptionsMenu(node, params);
                return;
            }
            else {
                console.log('About to call expandNode with node:', node);
                expandNode(node);
            }
        }
    });
    
    // Handle right clicks
    network.on("oncontext", function(params) {
        params.event.preventDefault();
        
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            const node = nodes.get(nodeId);
            showContextMenu(params.event, node);
        } else {
            showContextMenu(params.event, null, params.pointer.canvas);
        }
    });
    
    // Handle mouse down for focus mode - DISABLED
    /*
    // DISABLED - Hold functionality causing map drag issues
    /*
    network.on("hold", function(params) {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            selectConnectedNodes(nodeId);
        }
    });
    */
    
    // Handle mouse up to release focus
    network.on("release", function(params) {
        if (focusedNode) {
            releaseFocus();
        }
    });
    
    // Also release on general mouse up (backup)
    document.addEventListener('mouseup', function() {
        if (focusedNode) {
            releaseFocus();
        }
    });
    
    // Handle ESC key to cancel connection mode
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape' && connectionMode) {
            cancelConnectionMode();
        }
    });
    
    // Handle edge hover
    network.on("hoverEdge", function(params) {
        if (params.edge) {
            const edge = edges.get(params.edge);
            if (edge) {
                // Show edge information
                const fromNode = nodes.get(edge.from);
                const toNode = nodes.get(edge.to);
                
                let info = '';
                if (edge.title && edge.title.includes('Same breach record')) {
                    // Breach record connection
                    info = edge.title;
                } else {
                    // Other connection
                    info = `Connected: ${fromNode.label} - ${toNode.label}`;
                    if (edge.title) {
                        info = edge.title;
                    }
                }
                
                // Update status bar with edge info
                updateStatus(info);
                
                // Create floating tooltip
                let tooltip = document.getElementById('edge-tooltip');
                if (!tooltip) {
                    tooltip = document.createElement('div');
                    tooltip.id = 'edge-tooltip';
                    tooltip.style.cssText = `
                        position: absolute;
                        background: #000;
                        border: 2px solid #0f0;
                        color: #0f0;
                        padding: 10px;
                        font-family: monospace;
                        font-size: 11px;
                        line-height: 1.3;
                        z-index: 1000;
                        max-width: 400px;
                        max-height: 500px;
                        overflow-y: auto;
                        box-shadow: 0 0 10px #0f0;
                        pointer-events: none;
                    `;
                    document.body.appendChild(tooltip);
                }
                
                // Format tooltip content
                let tooltipHTML = '';
                if (edge.title && edge.title.includes('Same breach record')) {
                    tooltipHTML = `<strong style="color: #ff6600;">${escapeHtml(edge.title)}</strong><br>`;
                    tooltipHTML += `<span style="color: #888;">These items were found together</span><br><br>`;
                    tooltipHTML += `<span style="color: ${getNodeColor(fromNode.type)}">${fromNode.type.toUpperCase()}: ${escapeHtml(fromNode.label)}</span><br>`;
                    tooltipHTML += `<span style="color: ${getNodeColor(toNode.type)}">${toNode.type.toUpperCase()}: ${escapeHtml(toNode.label)}</span>`;
                } else {
                    tooltipHTML = `<strong style="color: #0ff;">Connection</strong><br>`;
                    tooltipHTML += `<span style="color: ${getNodeColor(fromNode.type)}">${escapeHtml(fromNode.label)}</span><br>`;
                    tooltipHTML += `<span style="color: ${getNodeColor(toNode.type)}">${escapeHtml(toNode.label)}</span>`;
                    if (edge.title) {
                        tooltipHTML += `<br><span style="color: #888;">${escapeHtml(edge.title)}</span>`;
                    }
                }
                
                tooltip.innerHTML = tooltipHTML;
                tooltip.style.display = 'block';
                
                // Position tooltip near mouse
                const updateTooltipPosition = (e) => {
                    tooltip.style.left = (e.pageX + 15) + 'px';
                    tooltip.style.top = (e.pageY - 30) + 'px';
                };
                
                // Track mouse movement
                document.addEventListener('mousemove', updateTooltipPosition);
                tooltip.setAttribute('data-mousemove-handler', 'true');
                
                // Highlight the edge
                edges.update({
                    id: params.edge,
                    width: 4,
                    color: {
                        color: '#ffff00',
                        highlight: '#ff0000',  // Keep red highlight when clicked
                        inherit: false
                    }
                });
            }
        }
    });
    
    // Handle edge blur (mouse leaves edge)
    network.on("blurEdge", function(params) {
        if (params.edge) {
            const edge = edges.get(params.edge);
            if (edge) {
                // Check if this edge connects two anchored nodes
                const fromAnchored = anchoredNodes.has(edge.from);
                const toAnchored = anchoredNodes.has(edge.to);
                const isBetweenAnchored = fromAnchored && toAnchored;
                
                // Determine the correct color to restore
                let restoreColor = '#666666'; // Default grey
                let restoreWidth = 2;
                let restoreDashes = true;
                
                if (isBetweenAnchored) {
                    // Keep thick white for anchored connections
                    restoreColor = '#ffffff';
                    restoreWidth = 3;
                    restoreDashes = false;
                } else if (edge.color && edge.color.color === '#20B2AA') {
                    // WHOIS connections stay teal
                    restoreColor = '#20B2AA';
                } else if (edge.color && edge.color.color === '#ff00ff') {
                    // Manual connections stay magenta
                    restoreColor = '#ff00ff';
                }
                
                // Restore edge appearance based on its type
                edges.update({
                    id: params.edge,
                    width: restoreWidth,
                    dashes: restoreDashes,
                    color: {
                        color: restoreColor,
                        inherit: false
                    }
                });
                
                // Hide tooltip
                const tooltip = document.getElementById('edge-tooltip');
                if (tooltip) {
                    tooltip.style.display = 'none';
                    // Remove mousemove listener
                    if (tooltip.getAttribute('data-mousemove-handler')) {
                        const handlers = document._getEventListeners ? document._getEventListeners(document).mousemove : [];
                        // Just hide it, the handler will be replaced on next hover
                    }
                }
                
                // Clear status
                updateStatus('Ready');
            }
        }
    });
    
    // Handle keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        // Check if user is typing in an input/textarea field
        const activeElement = document.activeElement;
        const isTyping = activeElement && (
            activeElement.tagName === 'INPUT' || 
            activeElement.tagName === 'TEXTAREA' ||
            activeElement.contentEditable === 'true'
        );
        
        // Delete key for selected nodes (only if not typing)
        if ((e.key === 'Delete' || e.key === 'Backspace') && !isTyping) {
            const selectedNodes = network.getSelectedNodes();
            if (selectedNodes.length > 0) {
                e.preventDefault();
                deleteSelectedNodes(selectedNodes);
            }
        }
        
        // Ctrl/Cmd + A to select all (only if not typing)
        if ((e.ctrlKey || e.metaKey) && e.key === 'a' && !isTyping) {
            e.preventDefault();
            network.selectNodes(nodes.getIds());
        }
        
        // Escape to deselect
        if (e.key === 'Escape') {
            network.unselectAll();
            fixStuckFocus();
        }
        
        // R to reset node colors (only if not typing)
        if ((e.key === 'r' || e.key === 'R') && !isTyping) {
            e.preventDefault();
            if (e.shiftKey) {
                // Shift+R to recover lost nodes
                recoverLostNodes();
            } else {
                fixStuckFocus();
            }
        }
    });
    
    // Ensure node remains visible and properly configured
    function ensureNodeVisible(nodeId) {
        const node = nodes.get(nodeId);
        if (node) {
            const update = {
                id: nodeId,
                hidden: false,
                physics: false
                // Don't update fixed property - let vis.js handle it
            };
            
            // Get current position
            const currentPos = network.getPositions([nodeId])[nodeId];
            if (currentPos && !isNaN(currentPos.x) && !isNaN(currentPos.y)) {
                update.x = currentPos.x;
                update.y = currentPos.y;
            } else if (node.x !== undefined && node.y !== undefined) {
                // Fallback to stored position
                update.x = node.x;
                update.y = node.y;
            } else {
                // Last resort: center the node
                console.warn(`[EnsureVisible] No valid position for node ${nodeId}, centering it`);
                const view = network.getViewPosition();
                update.x = view.x;
                update.y = view.y;
            }
            
            nodes.update(update);
            
            // Force a redraw
            network.redraw();
            
            return true;
        }
        return false;
    }
    
    // Safe node movement function
    function safeMoveNode(nodeId, x, y) {
        if (nodeId && !isNaN(x) && !isNaN(y) && isFinite(x) && isFinite(y)) {
            try {
                // Check if node exists before moving
                const node = nodes.get(nodeId);
                if (!node) {
                    console.error(`[SafeMove] Node ${nodeId} does not exist in dataset`);
                    return false;
                }
                
                console.log(`[SafeMove] Moving node ${nodeId} to (${x}, ${y})`);
                network.moveNode(nodeId, x, y);
                
                // Verify position after move
                const newPos = network.getPositions([nodeId])[nodeId];
                if (!newPos || isNaN(newPos.x) || isNaN(newPos.y)) {
                    console.error(`[SafeMove] Failed to verify position after move for node ${nodeId}`);
                }
                
                return true;
            } catch (error) {
                console.error(`[SafeMove] Failed to move node ${nodeId} to ${x}, ${y}:`, error);
                return false;
            }
        } else {
            console.warn(`[SafeMove] Invalid move parameters for node ${nodeId}: x=${x}, y=${y}`);
            return false;
        }
    }
    
    // Simple drag tracking for merge functionality
    let draggedNode = null;
    
    network.on("dragStart", function(params) {
        if (params.nodes.length > 0) {
            draggedNode = params.nodes[0];
            
            // If we're in group drag mode, store initial positions
            if (isGroupDrag && selectedNodes.size > 1) {
                initialPositions = new Map();
                const positions = network.getPositions(Array.from(selectedNodes));
                selectedNodes.forEach(nodeId => {
                    if (positions[nodeId]) {
                        initialPositions.set(nodeId, { ...positions[nodeId] });
                    }
                });
                console.log('Group drag started with', selectedNodes.size, 'nodes');
            }
        }
    });
    
    // DISABLED - Group dragging causing map movement issues
    /*
    network.on("dragging", function(params) {
        // Only do group drag if we have nodes being dragged AND we're in group drag mode
        if (isGroupDrag && draggedNode && params.nodes && params.nodes.length > 0 && selectedNodes.size > 1 && initialPositions) {
            // Make sure we're actually dragging a node, not just panning
            if (params.nodes.includes(draggedNode)) {
                // Get current position of the dragged node
                const currentPos = network.getPositions([draggedNode])[draggedNode];
                const initialPos = initialPositions.get(draggedNode);
                
                if (currentPos && initialPos) {
                    // Calculate movement delta
                    const deltaX = currentPos.x - initialPos.x;
                    const deltaY = currentPos.y - initialPos.y;
                    
                    // Move all other selected nodes by the same delta
                    const updates = [];
                    selectedNodes.forEach(nodeId => {
                        if (nodeId !== draggedNode) {
                            const nodeInitialPos = initialPositions.get(nodeId);
                            if (nodeInitialPos) {
                                updates.push({
                                    id: nodeId,
                                    x: nodeInitialPos.x + deltaX,
                                    y: nodeInitialPos.y + deltaY
                                });
                            }
                        }
                    });
                    
                    if (updates.length > 0) {
                        nodes.update(updates);
                    }
                }
            }
        }
    });
    */
    
    /* REMOVED COMPLEX DRAG HANDLING
        // Update check indicator and merge indicator positions for dragged nodes
        if (params.nodes.length > 0) {
            // Log current position of main dragged node
            const mainNode = params.nodes[0];
            const currentPos = network.getPositions([mainNode])[mainNode];
            if (!currentPos || isNaN(currentPos.x) || isNaN(currentPos.y)) {
                console.error('[Dragging] Invalid position detected for node:', mainNode, currentPos);
                // Try to recover by ensuring node is visible
                ensureNodeVisible(mainNode);
            }
            params.nodes.forEach(nodeId => {
                const checkNodeId = 'check_' + nodeId;
                const checkNode = nodes.get(checkNodeId);
                if (checkNode) {
                    const parentPos = network.getPositions([nodeId])[nodeId];
                    if (parentPos && !isNaN(parentPos.x) && !isNaN(parentPos.y)) {
                        safeMoveNode(checkNodeId, parentPos.x + 40, parentPos.y - 15);
                    }
                }
                
                // Merge indicators disabled
            });
        }
        
        // Handle group dragging for connected nodes or selected nodes
        if (isGroupDrag && draggedNode && params.nodes.length > 0) {
            // Calculate the movement delta
            const currentPos = network.getPositions([draggedNode])[draggedNode];
            const initialPos = initialPositions.get(draggedNode);
            
            if (currentPos && initialPos && !isNaN(currentPos.x) && !isNaN(currentPos.y) && !isNaN(initialPos.x) && !isNaN(initialPos.y)) {
                const deltaX = currentPos.x - initialPos.x;
                const deltaY = currentPos.y - initialPos.y;
                
                // Move all connected nodes by the same delta
                connectedNodeGroup.forEach(nodeId => {
                    if (nodeId !== draggedNode) { // The dragged node moves automatically
                        const nodeInitialPos = initialPositions.get(nodeId);
                        if (nodeInitialPos && !isNaN(nodeInitialPos.x) && !isNaN(nodeInitialPos.y)) {
                            const newX = nodeInitialPos.x + deltaX;
                            const newY = nodeInitialPos.y + deltaY;
                            if (!isNaN(newX) && !isNaN(newY)) {
                                safeMoveNode(nodeId, newX, newY);
                            }
                        }
                    }
                    
                    // Also move check indicators for connected nodes
                    const checkNodeId = 'check_' + nodeId;
                    const checkNode = nodes.get(checkNodeId);
                    if (checkNode) {
                        const nodePos = network.getPositions([nodeId])[nodeId];
                        if (nodePos && !isNaN(nodePos.x) && !isNaN(nodePos.y)) {
                            safeMoveNode(checkNodeId, nodePos.x + 40, nodePos.y - 15);
                        }
                    }
                    
                    // Merge indicators disabled
                });
                
                // Also move selected nodes if we're dragging multiple selected nodes
                if (selectedNodes.has(draggedNode) && selectedNodes.size > 1) {
                    selectedNodes.forEach(nodeId => {
                        if (nodeId !== draggedNode && !connectedNodeGroup.has(nodeId)) { // Don't double-move connected nodes
                            const nodeInitialPos = initialPositions.get(nodeId);
                            if (nodeInitialPos && !isNaN(nodeInitialPos.x) && !isNaN(nodeInitialPos.y)) {
                                const newX = nodeInitialPos.x + deltaX;
                                const newY = nodeInitialPos.y + deltaY;
                                if (!isNaN(newX) && !isNaN(newY)) {
                                    safeMoveNode(nodeId, newX, newY);
                                }
                            }
                        }
                    });
                }
            }
        }
    });*/
    
    network.on("dragEnd", function(params) {
        // Reset group drag mode
        if (isGroupDrag) {
            console.log('Group drag ended');
            isGroupDrag = false;
            initialPositions = null;
            draggedNode = null;
            saveGraphState(); // Save the new positions
        }
        
        // Simple drag end - handle merge or cluster addition
        if (draggedNode && params.nodes.length > 0) {
            const draggedNodeId = draggedNode;
            
            // Get final position of dragged node
            const draggedPos = network.getPositions([draggedNodeId])[draggedNodeId];
            
            if (draggedPos) {
                // First check if we're over a cluster
                let targetClusterId = null;
                clusters.forEach((cluster, clusterId) => {
                    const clusterNode = nodes.get(clusterId);
                    if (clusterNode) {
                        // Check if dragged position is within cluster bounds
                        const halfWidth = cluster.width / 2;
                        const halfHeight = cluster.height / 2;
                        if (draggedPos.x >= cluster.x - halfWidth && 
                            draggedPos.x <= cluster.x + halfWidth &&
                            draggedPos.y >= cluster.y - halfHeight && 
                            draggedPos.y <= cluster.y + halfHeight) {
                            targetClusterId = clusterId;
                        }
                    }
                });
                
                if (targetClusterId) {
                    // Add node to cluster
                    const draggedNodeObj = nodes.get(draggedNodeId);
                    if (draggedNodeObj && !draggedNodeObj.clusterId) {
                        saveUndoState("Add node to cluster");
                        addNodesToCluster(targetClusterId, [draggedNodeId]);
                        updateStatus(`Added node to cluster`);
                    }
                    return;
                }
                
                // Otherwise check for node merging
                let targetNodeId = null;
                const allNodes = nodes.get();
                
                for (const node of allNodes) {
                    // Skip the dragged node itself, selected nodes, and cluster nodes
                    if (node.id === draggedNodeId || selectedNodes.has(node.id) || node.type === 'cluster' || node.type === 'cluster_inner') continue;
                    
                    const nodePos = network.getPositions([node.id])[node.id];
                    if (nodePos) {
                        // Calculate distance between centers
                        const dx = draggedPos.x - nodePos.x;
                        const dy = draggedPos.y - nodePos.y;
                        const distance = Math.sqrt(dx * dx + dy * dy);
                        
                        // If nodes are very close (within 50 pixels), consider it a merge
                        if (distance < 50) {
                            targetNodeId = node.id;
                            break;
                        }
                    }
                }
                
                if (targetNodeId) {
                    // Check if multiple nodes are selected
                    if (selectedNodes.size > 1) {
                        // Merge all selected nodes into the target
                        const nodesToMerge = Array.from(selectedNodes);
                        for (const nodeId of nodesToMerge) {
                            if (nodeId !== targetNodeId) {
                                mergeNodes(nodeId, targetNodeId);
                            }
                        }
                        updateStatus(`Merged ${nodesToMerge.length} selected nodes into target`);
                    } else {
                        // Single node merge
                        mergeNodes(draggedNodeId, targetNodeId);
                    }
                    
                    // Clear selection after merge
                    network.unselectAll();
                    selectedNodes.clear();
                }
            }
        }

        // SQL Integration: Sync positions to database
        if (window.C1Integration && typeof window.C1Integration.schedulePositionSync === 'function' && params.nodes.length > 0) {
            params.nodes.forEach(nodeId => {
                const node = nodes.get(nodeId);
                if (node && node.x !== undefined && node.y !== undefined) {
                    window.C1Integration.schedulePositionSync(nodeId, node.x, node.y);
                }
            });
        }

        draggedNode = null;
    });
    
    // Track node selection changes
    network.on("selectNode", function(params) {
        selectedNodes.clear();
        params.nodes.forEach(nodeId => selectedNodes.add(nodeId));
        
        // Show anchor button if multiple nodes selected
        const anchorBtn = document.getElementById('anchorSelectedBtn');
        if (selectedNodes.size > 0) {
            anchorBtn.style.display = 'inline-block';
            
            // Check if all selected nodes are anchored
            let allAnchored = true;
            selectedNodes.forEach(nodeId => {
                if (!anchoredNodes.has(nodeId)) {
                    allAnchored = false;
                }
            });
            
            if (allAnchored) {
                anchorBtn.textContent = `Unanchor ${selectedNodes.size} Node${selectedNodes.size > 1 ? 's' : ''}`;
            } else {
                anchorBtn.textContent = `Anchor ${selectedNodes.size} Node${selectedNodes.size > 1 ? 's' : ''}`;
            }
        } else {
            anchorBtn.style.display = 'none';
        }
        
        // Update cluster buttons
        updateClusterButtons();
    });
    
    network.on("deselectNode", function(params) {
        selectedNodes.clear();
        const stillSelected = network.getSelectedNodes();
        stillSelected.forEach(nodeId => selectedNodes.add(nodeId));
        
        // Update anchor button
        const anchorBtn = document.getElementById('anchorSelectedBtn');
        if (selectedNodes.size > 0) {
            anchorBtn.style.display = 'inline-block';
            
            // Check if all selected nodes are anchored
            let allAnchored = true;
            selectedNodes.forEach(nodeId => {
                if (!anchoredNodes.has(nodeId)) {
                    allAnchored = false;
                }
            });
            
            if (allAnchored) {
                anchorBtn.textContent = `Unanchor ${selectedNodes.size} Node${selectedNodes.size > 1 ? 's' : ''}`;
            } else {
                anchorBtn.textContent = `Anchor ${selectedNodes.size} Node${selectedNodes.size > 1 ? 's' : ''}`;
            }
        } else {
            anchorBtn.style.display = 'none';
        }
        
        // Update cluster buttons
        updateClusterButtons();
    });
    
    /* REMOVED THE REST OF COMPLEX DRAG CODE */
    
    // Track node selections for AI chat with Command key support
    network.on("selectNode", function(params) {
        // Check if Command key (metaKey) is pressed for multi-selection
        const event = params.event?.srcEvent || params.event;
        const isMultiSelect = event && (event.metaKey || event.ctrlKey || event.shiftKey);
        
        if (!isMultiSelect && !isGroupDrag) {
            // For normal click, only select the clicked node
            selectedNodes.clear();
            network.unselectAll();
            if (params.nodes.length > 0) {
                const clickedNode = params.nodes[0];
                network.selectNodes([clickedNode]);
                selectedNodes.add(clickedNode);
            }
        } else if (!isGroupDrag) {
            // Multi-select mode
            params.nodes.forEach(nodeId => selectedNodes.add(nodeId));
        }
        // If isGroupDrag, the selection is handled by the hold timer
        
        updateChatInputWithSelection();
        
        // Show anchor button when nodes are selected
        const anchorBtn = document.getElementById('anchorSelectedBtn');
        if (selectedNodes.size > 0) {
            anchorBtn.style.display = 'inline-block';
            
            // Check if all selected nodes are anchored
            let allAnchored = true;
            selectedNodes.forEach(nodeId => {
                if (!anchoredNodes.has(nodeId)) {
                    allAnchored = false;
                }
            });
            
            if (allAnchored) {
                anchorBtn.textContent = `Unanchor ${selectedNodes.size} Node${selectedNodes.size > 1 ? 's' : ''}`;
            } else {
                anchorBtn.textContent = `Anchor ${selectedNodes.size} Node${selectedNodes.size > 1 ? 's' : ''}`;
            }
        }
        
        // Update cluster buttons
        updateClusterButtons();
    });
}

// Show WHOIS results dialog
async function showWhoisResultsDialog(whoisData, searchQuery, parentNodeId) {
    // Handle domain WHOIS results EXACTLY like the Python script
    if (whoisData.query_type === 'domain' && whoisData.records) {
        const records = whoisData.records;
        console.log(`Got ${records.length} WHOIS history records for ${searchQuery}`);
        
        // Combine ALL raw WHOIS text for Claude to analyze
        let allWhoisText = '';
        records.forEach((record, idx) => {
            if (record.rawText || record.cleanText) {
                allWhoisText += `\n\n=== WHOIS RECORD ${idx + 1} (${record.audit?.createdDate || 'Unknown Date'}) ===\n`;
                allWhoisText += record.cleanText || '';
                if (record.rawText) {
                    allWhoisText += '\n\n--- RAW TEXT ---\n' + record.rawText;
                }
            }
        });
        
        console.log('Sending ALL WHOIS data to Claude for analysis...');
        
        // Send ALL the WHOIS data to Claude at once
        try {
            const aiExtraction = await fetch('/api/extract-whois', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ 
                    whois_text: allWhoisText, 
                    domain: searchQuery 
                })
            });
            
            let suggestions = [{
                value: searchQuery,
                type: 'domain',
                source: 'WHOIS Domain Search',
                context: `Domain with ${records.length} historical WHOIS records`,
                parentNodeId: parentNodeId
            }];
            
            if (aiExtraction.ok) {
                const extracted = await aiExtraction.json();
                console.log(`Claude extracted ${extracted.entities?.length || 0} entities from ALL WHOIS data`);
                
                if (extracted.entities) {
                    extracted.entities.forEach(entity => {
                        suggestions.push({
                            value: entity.value,
                            type: entity.type,
                            source: 'WHOIS AI Extract',
                            context: entity.context,
                            parentNodeId: parentNodeId
                        });
                    });
                }
            }
            
            // Show the results dialog
            console.log('=== ABOUT TO SHOW WHOIS DIALOG ===');
            console.log('Suggestions:', suggestions);
            console.log('Search query:', searchQuery);
            console.log('Record count:', records.length);
            showWhoisExtractedDialog(suggestions, searchQuery, records.length);
            console.log('=== WHOIS DIALOG SHOULD BE VISIBLE NOW ===');
            
        } catch (error) {
            console.error('AI WHOIS extraction failed:', error);
            updateStatus('Failed to extract WHOIS data');
        }
        
        return;
    }
    
    // Handle reverse WHOIS results (original code)
    const results = whoisData.results || [];
    console.log('WHOIS Results:', results);
    console.log('Search query:', searchQuery);
    console.log('Parent node ID:', parentNodeId);
    
    // Extract all potential nodes from WHOIS results
    let suggestions = [];
    
    console.log(`Processing ${results.length} WHOIS results`);
    
    // Process only the first few WHOIS records to avoid overwhelming Claude
    const recordsToProcess = results.slice(0, 3); // Process first 3 records
    
    for (const result of recordsToProcess) {
        if (result.type === 'whois_domain' && result.raw_whois_text) {
            // ALWAYS add the domain node first
            if (result.domain) {
                suggestions.push({
                    value: result.domain,
                    type: 'domain',
                    source: 'WHOIS Domain',
                    context: `Domain from WHOIS search | Created: ${result.created || 'Unknown'} | Expires: ${result.expires || 'Unknown'}`,
                    data: result,
                    parentNodeId: parentNodeId // Keep track of parent
                });
            }
            
            // ONLY use AI to extract all information from WHOIS text
            console.log(`Using Claude to extract entities from ${result.domain} WHOIS data`);
            try {
                const aiExtraction = await fetch('/api/extract-whois', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ whois_text: result.raw_whois_text, domain: result.domain })
                });
                
                if (aiExtraction.ok) {
                    const extracted = await aiExtraction.json();
                    console.log(`Claude extracted ${extracted.entities?.length || 0} entities from ${result.domain}`);
                    if (extracted.entities) {
                        extracted.entities.forEach(entity => {
                            // Avoid duplicates
                            if (!suggestions.some(s => s.value === entity.value && s.type === entity.type)) {
                                suggestions.push({
                                    value: entity.value,
                                    type: entity.type,
                                    source: `WHOIS AI Extract - ${result.domain}`,
                                    context: entity.context || `Extracted from ${result.domain} WHOIS`,
                                    data: result,
                                    parentNodeId: parentNodeId // Keep track of parent
                                });
                            }
                        });
                    }
                } else {
                    console.error('AI extraction failed with status:', aiExtraction.status);
                }
            } catch (error) {
                console.error('AI WHOIS extraction failed:', error);
            }
        } else if (result.type === 'whois_reverse' && result.domains) {
            // For reverse WHOIS, we need to search each domain's historical WHOIS
            // This case should rarely happen now since server already fetches full data
            for (const domain of result.domains) {
                suggestions.push({
                    value: domain,
                    type: 'domain',
                    source: 'WHOIS Reverse Search',
                    context: `Domain associated with ${searchQuery}`,
                    data: result,
                    parentNodeId: parentNodeId, // Keep track of parent
                    searchHistorical: true // Flag to search historical WHOIS
                });
            }
        }
    }
    
    if (suggestions.length === 0) {
        updateStatus('No extractable data found in WHOIS results');
        console.log('No suggestions found in WHOIS data');
        return;
    }
    
    console.log(`Found ${suggestions.length} suggestions from WHOIS data`);
    
    // Show dialog with checkboxes for each suggestion
    const html = `
        <div class="modal" id="whoisResultsModal" style="display: block; position: fixed; z-index: 10000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.8);">
            <div class="modal-content" style="background-color: #1a1a1a; margin: 5% auto; padding: 20px; width: 80%; max-width: 800px; max-height: 80vh; overflow-y: auto; border: 2px solid #666;">
                <h2 style="color: #20B2AA; margin-bottom: 20px;">🌐 WHOIS Search Results</h2>
                <p style="margin-bottom: 20px;">Found ${suggestions.length} data points from ${results.length} WHOIS records. Review and select which nodes to create:</p>
                
                <div style="margin-bottom: 20px;">
                    <button onclick="selectAllWhois(true)" style="background: #444; color: white; border: none; padding: 5px 15px; margin-right: 10px; border-radius: 3px; cursor: pointer;">Select All</button>
                    <button onclick="selectAllWhois(false)" style="background: #444; color: white; border: none; padding: 5px 15px; border-radius: 3px; cursor: pointer;">Deselect All</button>
                </div>
                
                <div id="whoisSuggestionsList">
                    ${suggestions.map((suggestion, index) => {
                        const nodeColor = getNodeColor(suggestion.type);
                        return `
                            <div style="margin: 10px 0; padding: 10px; background: #222; border: 1px solid #444; border-radius: 5px;">
                                <label style="display: flex; align-items: center; cursor: pointer;">
                                    <input type="checkbox" id="whois_suggestion_${index}_enabled" checked style="margin-right: 10px;">
                                    <div style="flex: 1;">
                                        <span style="color: ${nodeColor}; font-weight: bold;">[${suggestion.type.toUpperCase()}]</span>
                                        <span style="color: #fff; margin-left: 10px;">${escapeHtml(suggestion.value)}</span>
                                        <div style="color: #888; font-size: 0.9em; margin-top: 5px;">
                                            Source: ${suggestion.source} | ${suggestion.context}
                                            ${suggestion.searchHistorical ? '<br><em>Will search historical WHOIS data for this domain</em>' : ''}
                                        </div>
                                    </div>
                                </label>
                            </div>
                        `;
                    }).join('')}
                </div>
                
                <details style="margin-top: 20px;">
                    <summary style="cursor: pointer; color: #20B2AA;">View Raw WHOIS Data</summary>
                    <pre style="background: #000; padding: 10px; margin-top: 10px; color: #888; overflow: auto; max-height: 300px;">${results.map(r => escapeHtml(r.raw_whois_text || JSON.stringify(r, null, 2))).join('\n\n---\n\n')}</pre>
                </details>
                
                <div style="margin-top: 20px; text-align: right;">
                    <button onclick="cancelWhoisResults()" style="background: #666; color: white; border: none; padding: 10px 20px; margin-right: 10px; border-radius: 5px; cursor: pointer;">Cancel</button>
                    <button onclick="createWhoisNodes('${parentNodeId || ''}', ${suggestions.length})" style="background: #20B2AA; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer;">Create Selected Nodes</button>
                </div>
            </div>
        </div>
    `;
    
    console.log('Inserting WHOIS results dialog into DOM');
    document.body.insertAdjacentHTML('beforeend', html);
    
    // Store suggestions for later use
    window.whoisSuggestions = suggestions;
    console.log('WHOIS dialog should now be visible');
}

// Show dialog with WHOIS extracted entities
function showWhoisExtractedDialog(suggestions, domain, recordCount) {
    console.log(`=== SHOWING WHOIS RESULTS DIALOG ===`);
    console.log(`Domain: ${domain}`);
    console.log(`Record count: ${recordCount}`);
    console.log(`Suggestions count: ${suggestions.length}`);
    console.log('Suggestions:', suggestions);
    
    const html = `
        <div class="modal" id="whoisResultsModal" style="display: block; position: fixed; z-index: 10000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.8);">
            <div class="modal-content" style="background-color: #1a1a1a; margin: 5% auto; padding: 20px; width: 80%; max-width: 800px; max-height: 80vh; overflow-y: auto; border: 2px solid #666;">
                <h2 style="color: #20B2AA; margin-bottom: 20px;">🌐 WHOIS History Analysis for ${escapeHtml(domain)}</h2>
                <p style="margin-bottom: 20px;">Analyzed ${recordCount} historical WHOIS records. Claude extracted ${suggestions.length - 1} entities:</p>
                
                <div style="margin-bottom: 20px;">
                    <button onclick="selectAllWhois(true)" style="background: #444; color: white; border: none; padding: 5px 15px; margin-right: 10px; border-radius: 3px; cursor: pointer;">Select All</button>
                    <button onclick="selectAllWhois(false)" style="background: #444; color: white; border: none; padding: 5px 15px; border-radius: 3px; cursor: pointer;">Deselect All</button>
                </div>
                
                <div id="whoisSuggestionsList">
                    ${suggestions.map((suggestion, index) => {
                        const nodeColor = getNodeColor(suggestion.type);
                        return `
                            <div style="margin: 10px 0; padding: 10px; background: #222; border: 1px solid #444; border-radius: 5px;">
                                <label style="display: flex; align-items: center; cursor: pointer;">
                                    <input type="checkbox" id="whois_suggestion_${index}_enabled" checked style="margin-right: 10px;">
                                    <div style="flex: 1;">
                                        <span style="color: ${nodeColor}; font-weight: bold;">[${suggestion.type.toUpperCase()}]</span>
                                        <span style="color: #fff; margin-left: 10px;">${escapeHtml(suggestion.value)}</span>
                                        <div style="color: #888; font-size: 0.9em; margin-top: 5px;">
                                            ${suggestion.context}
                                        </div>
                                    </div>
                                </label>
                            </div>
                        `;
                    }).join('')}
                </div>
                
                <div style="margin-top: 20px; text-align: right;">
                    <button onclick="cancelWhoisResults()" style="background: #666; color: white; border: none; padding: 10px 20px; margin-right: 10px; border-radius: 5px; cursor: pointer;">Cancel</button>
                    <button onclick="createWhoisNodes('${suggestions[0]?.parentNodeId || ''}', ${suggestions.length})" style="background: #20B2AA; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer;">Create Selected Nodes</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', html);
    window.whoisSuggestions = suggestions;
    console.log('=== WHOIS DIALOG HTML INSERTED ===');
    console.log('Modal element exists:', !!document.getElementById('whoisResultsModal'));
}

// Helper functions for WHOIS dialog
window.selectAllWhois = function(checked) {
    const checkboxes = document.querySelectorAll('[id^="whois_suggestion_"][id$="_enabled"]');
    checkboxes.forEach(cb => cb.checked = checked);
}

// Helper function for AI suggestions
window.selectAllSuggestions = function(checked) {
    const checkboxes = document.querySelectorAll('[id^="suggestion-"]');
    checkboxes.forEach(cb => cb.checked = checked);
}

window.cancelWhoisResults = function() {
    const modal = document.getElementById('whoisResultsModal');
    if (modal) modal.remove();
    updateStatus('WHOIS results cancelled');
}

window.createWhoisNodes = async function(parentNodeId, suggestionCount) {
    const selectedSuggestions = [];
    
    for (let i = 0; i < suggestionCount; i++) {
        const checkbox = document.getElementById(`whois_suggestion_${i}_enabled`);
        if (checkbox && checkbox.checked && window.whoisSuggestions[i]) {
            selectedSuggestions.push(window.whoisSuggestions[i]);
        }
    }
    
    if (selectedSuggestions.length === 0) {
        updateStatus('No items selected');
        return;
    }
    
    // Remove modal
    const modal = document.getElementById('whoisResultsModal');
    if (modal) modal.remove();
    
    // Create nodes and search historical WHOIS for domains
    let createdCount = 0;
    const domainNodes = []; // Track domain nodes for historical searches
    
    for (const suggestion of selectedSuggestions) {
        // Use the parentNodeId from the suggestion if available
        const effectiveParentId = suggestion.parentNodeId || parentNodeId;
        
        const result = addNode({
            value: suggestion.value,
            label: suggestion.value,
            source: suggestion.source,
            context: suggestion.context,
            whoisData: suggestion.data
        }, suggestion.type, effectiveParentId, false, null, false);
        const nodeId = result?.nodeId;
        
        if (nodeId) {
            createdCount++;
            
            // Create a direct connection between parent and new node (for WHOIS relationships)
            if (effectiveParentId && nodeId !== effectiveParentId) {
                // Check if edge already exists
                const existingEdge = edges.get({
                    filter: edge => 
                        (edge.from === effectiveParentId && edge.to === nodeId) ||
                        (edge.from === nodeId && edge.to === effectiveParentId)
                });
                
                if (existingEdge.length === 0 && effectiveParentId !== nodeId) {
                    edges.add({
                        from: effectiveParentId,
                        to: nodeId,
                        ...getConnectionStyle('DEFAULT'),
                        title: `WHOIS connection: ${suggestion.source}`,
                        arrows: showArrows ? 'to' : ''
                    });
                }
            }
            
            // If this is a domain that needs historical WHOIS search
            if (suggestion.searchHistorical && suggestion.type === 'domain') {
                domainNodes.push({ nodeId, domain: suggestion.value });
            }
            
            // Save graph state after each node creation
            saveGraphState();
        }
    }
    
    // Process historical WHOIS searches for domains after all nodes are created
    for (const { nodeId, domain } of domainNodes) {
        updateStatus(`Searching historical WHOIS for ${domain}...`);
        const historicalWhois = await performWhoisSearch(domain, 'domain');
        if (historicalWhois && historicalWhois.results && historicalWhois.results.length > 0) {
            // Show dialog for historical results
            await showWhoisResultsDialog(historicalWhois, domain, nodeId);
        }
        // Add small delay between searches
        await new Promise(resolve => setTimeout(resolve, 500));
    }
    
    updateStatus(`Created ${createdCount} nodes from WHOIS data`);
}

// Helper function for backward compatibility - returns just nodeId
function addNodeSimple(data, type, parentId = null, forceDuplicate = false) {
    // Non-interactive wrapper: never returns a Promise (safe for bulk ingestion)
    const result = addNode(data, type, parentId, forceDuplicate, null, false);
    return result?.nodeId;
}

// Direct node addition that bypasses all checks - for corporate data
function addNodeDirect(data, type) {
    const nodeId = `node_${nodeIdCounter++}`;
    const color = getNodeColor(type);
    
    const node = {
        id: nodeId,
        label: data.label || data.value || 'Unknown',
        title: `${type.toUpperCase()}: ${data.value || data.label || 'Unknown'}`,
        color: {
            background: '#000000',
            border: color,
            highlight: {
                background: '#1a1a1a',
                border: color
            }
        },
        data: {
            ...data,
            addedAt: Date.now()
        },
        type: type,
        x: Math.random() * 1000 - 500,
        y: Math.random() * 1000 - 500,
        physics: false,
        font: {
            color: '#666666',
            multi: 'html',
            size: 12
        },
        shadow: false
    };
    
    nodes.add(node);
    
    // Add to value map (case-insensitive)
    const keyValue = (data.value || data.label || data.id || '').toLowerCase().trim();
    const valueKey = `${type}_${keyValue}`;
    valueToNodeMap.set(valueKey, nodeId);
    
    updateStatus();
    saveGraphState();
    
    return { nodeId: nodeId, isExisting: false };
}

// Normalize phone numbers for similarity comparison
function normalizePhone(phone) {
    return phone.replace(/[^\d]/g, ''); // Remove all non-digits
}

// Normalize addresses for similarity comparison  
function normalizeAddress(address) {
    return address.toLowerCase()
        .replace(/\b(street|st|avenue|ave|road|rd|drive|dr|lane|ln|boulevard|blvd|court|ct)\b/g, '')
        .replace(/[^\w\s]/g, '') // Remove punctuation
        .replace(/\s+/g, ' ') // Normalize spaces
        .trim();
}

// Normalize emails for similarity comparison
function normalizeEmail(email) {
    return email.toLowerCase().trim();
}

// Calculate similarity between two strings (0-1, 1 = identical)
function calculateSimilarity(str1, str2) {
    if (str1 === str2) return 1;
    
    const longer = str1.length > str2.length ? str1 : str2;
    const shorter = str1.length > str2.length ? str2 : str1;
    
    if (longer.length === 0) return 1;
    
    // Calculate Levenshtein distance
    const editDistance = levenshteinDistance(longer, shorter);
    return (longer.length - editDistance) / longer.length;
}

// Levenshtein distance algorithm
function levenshteinDistance(str1, str2) {
    const matrix = [];
    
    for (let i = 0; i <= str2.length; i++) {
        matrix[i] = [i];
    }
    
    for (let j = 0; j <= str1.length; j++) {
        matrix[0][j] = j;
    }
    
    for (let i = 1; i <= str2.length; i++) {
        for (let j = 1; j <= str1.length; j++) {
            if (str2.charAt(i - 1) === str1.charAt(j - 1)) {
                matrix[i][j] = matrix[i - 1][j - 1];
            } else {
                matrix[i][j] = Math.min(
                    matrix[i - 1][j - 1] + 1,
                    matrix[i][j - 1] + 1,
                    matrix[i - 1][j] + 1
                );
            }
        }
    }
    
    return matrix[str2.length][str1.length];
}

// Check for similar existing nodes
// Safely extract value from any node structure
function getNodeValue(node) {
    // Try different possible value properties in order of preference
    if (node.data && node.data.value !== undefined) {
        return node.data.value;
    }
    if (node.value !== undefined) {
        return node.value;
    }
    if (node.label !== undefined) {
        return node.label;
    }
    if (node.id !== undefined) {
        return node.id;
    }
    // Last resort: return empty string to prevent crashes
    return '';
}

function findSimilarNodes(newValue, type) {
    const similarNodes = [];
    const allNodes = nodes.get();
    
    for (const existingNode of allNodes) {
        if (existingNode.type === type) {
            let similarity = 0;
            let normalizedNew, normalizedExisting;
            
            switch (type) {
                case 'phone':
                    normalizedNew = normalizePhone(newValue);
                    normalizedExisting = normalizePhone(getNodeValue(existingNode));
                    
                    // High similarity if normalized phones match
                    if (normalizedNew === normalizedExisting) {
                        similarity = 1;
                    } else if (normalizedNew.length >= 7 && normalizedExisting.length >= 7) {
                        // Compare last 7+ digits for partial matches
                        const newSuffix = normalizedNew.slice(-7);
                        const existingSuffix = normalizedExisting.slice(-7);
                        if (newSuffix === existingSuffix) {
                            similarity = 0.9;
                        } else {
                            similarity = calculateSimilarity(normalizedNew, normalizedExisting);
                        }
                    }
                    break;
                    
                case 'address':
                    normalizedNew = normalizeAddress(newValue);
                    normalizedExisting = normalizeAddress(getNodeValue(existingNode));
                    similarity = calculateSimilarity(normalizedNew, normalizedExisting);
                    break;
                    
                case 'email':
                    normalizedNew = normalizeEmail(newValue);
                    normalizedExisting = normalizeEmail(getNodeValue(existingNode));
                    similarity = calculateSimilarity(normalizedNew, normalizedExisting);
                    break;
                    
                case 'name':
                    // Names are tricky - normalize and check
                    normalizedNew = newValue.toLowerCase().replace(/[^\w\s]/g, '').trim();
                    normalizedExisting = getNodeValue(existingNode).toLowerCase().replace(/[^\w\s]/g, '').trim();
                    similarity = calculateSimilarity(normalizedNew, normalizedExisting);
                    break;
                    
                case 'username':
                    // Usernames should be exact or very similar
                    similarity = calculateSimilarity(newValue.toLowerCase(), getNodeValue(existingNode).toLowerCase());
                    break;
                    
                default:
                    // For other types, basic string similarity
                    similarity = calculateSimilarity(newValue.toLowerCase(), getNodeValue(existingNode).toLowerCase());
            }
            
            // Alert threshold: 0.6+ similarity but not exact match
            if (similarity >= 0.6 && similarity < 1.0) {
                similarNodes.push({
                    nodeId: existingNode.id,
                    value: getNodeValue(existingNode),
                    similarity: similarity,
                    recommendAction: similarity >= 0.95 ? 'merge' : similarity >= 0.8 ? 'hypothetical' : 'review'
                });
            }
        }
    }
    
    return similarNodes.sort((a, b) => b.similarity - a.similarity);
}

// Show similarity alert dialog
function showSimilarityAlert(newValue, type, similarNodes, callback) {
    const html = `
        <div class="modal" id="similarityAlertModal" style="display: block; position: fixed; z-index: 15000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.9);">
            <div class="modal-content" style="background-color: #1a1a1a; margin: 10% auto; padding: 20px; width: 70%; max-width: 600px; border: 3px solid #ff6600; border-radius: 10px;">
                <h2 style="color: #ff6600; margin-bottom: 20px;">⚠️ POTENTIAL DUPLICATE DETECTED</h2>
                <p style="color: #fff; margin-bottom: 15px;">The new <strong>${type.toUpperCase()}</strong> you're adding might be similar to existing nodes:</p>
                
                <div style="background: #222; padding: 15px; margin: 15px 0; border-radius: 5px;">
                    <strong style="color: ${UI_COLORS.accent};">NEW:</strong> <span style="color: ${UI_COLORS.textPrimary};">${escapeHtml(newValue)}</span>
                </div>
                
                <div style="margin: 20px 0;">
                    <h3 style="color: #ff6600; margin-bottom: 10px;">Similar Existing Nodes:</h3>
                    ${similarNodes.map(node => `
                        <div style="background: #333; padding: 10px; margin: 8px 0; border-radius: 5px; border-left: 4px solid #ff6600;">
                            <strong style="color: #ffff00;">EXISTING:</strong> <span style="color: #fff;">${escapeHtml(node.value)}</span>
                            <div style="color: #888; font-size: 0.9em; margin-top: 5px;">
                                Similarity: ${(node.similarity * 100).toFixed(1)}%
                            </div>
                        </div>
                    `).join('')}
                </div>
                
                <div style="background: #003366; padding: 15px; margin: 15px 0; border-radius: 5px; border-left: 4px solid #00BFFF;">
                    <strong style="color: #00BFFF;">💡 Recommendation:</strong>
                    <p style="color: #ccc; margin: 5px 0 0 0;">Review these similarities carefully. Consider merging nodes if they represent the same entity with different formatting.</p>
                </div>
                
                <div style="margin-top: 25px; text-align: center;">
                    <button onclick="handleSimilarityChoice('merge')" style="background: #ff6600; color: white; border: none; padding: 12px 25px; margin: 0 5px; border-radius: 5px; cursor: pointer; font-weight: bold;">MERGE WITH EXISTING</button>
                    <button onclick="handleSimilarityChoice('hypothetical')" style="background: #0066ff; color: white; border: none; padding: 12px 25px; margin: 0 5px; border-radius: 5px; cursor: pointer;">CREATE + HYPOTHETICAL LINK</button>
                    <button onclick="handleSimilarityChoice('create')" style="background: #006600; color: white; border: none; padding: 12px 25px; margin: 0 5px; border-radius: 5px; cursor: pointer;">CREATE SEPARATELY</button>
                    <button onclick="handleSimilarityChoice('cancel')" style="background: #666; color: white; border: none; padding: 12px 25px; margin: 0 5px; border-radius: 5px; cursor: pointer;">CANCEL</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', html);
    
    // Store callback for button handlers
    window.similarityCallback = callback;
    window.similarNodes = similarNodes;
}

// Handle user choice on similarity alert
window.handleSimilarityChoice = function(choice) {
    const modal = document.getElementById('similarityAlertModal');
    if (modal) modal.remove();
    
    if (window.similarityCallback) {
        window.similarityCallback(choice, window.similarNodes);
    }
    
    // Clean up
    delete window.similarityCallback;
    delete window.similarNodes;
};

// Add a node to the graph
function addNode(data, type, parentId = null, forceDuplicate = false, position = null, interactive = true) {
    console.log('=== addNode called ===');
    console.log('Type:', type);
    console.log('Data:', data);
    console.log('ParentId:', parentId);
    console.log('ForceDuplicate:', forceDuplicate);
    
    // Create a unique key based on value and type (case-insensitive)
    const keyValue = (data.value || data.label || data.id || '').toLowerCase().trim();
    const valueKey = `${type}_${keyValue}`;
    console.log('ValueKey:', valueKey);
    
    // Check if node already exists (unless forcing duplicate)
    if (!forceDuplicate && valueToNodeMap.has(valueKey)) {
        const existingNodeId = valueToNodeMap.get(valueKey);
        console.log('Node already exists with ID:', existingNodeId);
        
        // Check if the node is actually in the nodes DataSet
        const existingNode = nodes.get(existingNodeId);
        console.log('Existing node in DataSet:', existingNode);
        
        if (!existingNode) {
            console.error('ERROR: Node ID exists in valueToNodeMap but not in nodes DataSet!');
            // Remove the bad entry
            valueToNodeMap.delete(valueKey);
            console.log('Removed bad entry from valueToNodeMap, will create new node');
        } else {
            // Store search relationship for query nodes
            if (parentId) {
                const searchKey = `${parentId}_search`;
                let searchData = nodeSearchQueries.get(searchKey) || {
                    sourceNode: parentId,
                    query: nodes.get(parentId)?.label,
                    results: []
                };
                if (!searchData.results.includes(existingNodeId)) {
                    searchData.results.push(existingNodeId);
                }
                nodeSearchQueries.set(searchKey, searchData);
            }
            
            updateStatus();
            return { nodeId: existingNodeId, isExisting: true };
        }
    }
    
    // Check for similar nodes (but not exact matches)
    if (!forceDuplicate) {
        const newValue = data.value || data.label || data.id;
        const similarNodes = findSimilarNodes(newValue, type);
        
        if (similarNodes.length > 0) {
            // Auto-create hypothetical links for high similarity (80-95%)
            const autoLinkNodes = similarNodes.filter(n => n.similarity >= 0.8 && n.similarity < 0.95);
            
            if (autoLinkNodes.length > 0) {
                // Create new node first
                const newNodeResult = createNewNode();
                
                // Auto-create hypothetical links
                autoLinkNodes.forEach(similarNode => {
                    const reason = `Auto-detected similarity (${(similarNode.similarity * 100).toFixed(1)}% match)`;
                    createHypotheticalLink(newNodeResult.nodeId, similarNode.nodeId, reason);
                });
                
                updateStatus(`Created node with ${autoLinkNodes.length} hypothetical link(s)`);
                saveGraphState();
                return newNodeResult;
            }
            
            // Show alert for very high similarity (95%+) - likely merge candidates
            const mergeNodes = similarNodes.filter(n => n.similarity >= 0.95);
            if (mergeNodes.length > 0) {
                // Bulk / programmatic calls can't safely block on UI modals
                if (!interactive) {
                    return createNewNode();
                }
                // Show alert and wait for user decision
                return new Promise((resolve) => {
                    showSimilarityAlert(newValue, type, mergeNodes, (choice, nodes) => {
                    if (choice === 'cancel') {
                        resolve(null);
                    } else if (choice === 'merge') {
                        // User chose to merge - return the most similar existing node
                        const targetNodeId = nodes[0].nodeId;
                        
                        // Store search relationship if needed
                        if (parentId) {
                            const searchKey = `${parentId}_search`;
                            let searchData = nodeSearchQueries.get(searchKey) || {
                                sourceNode: parentId,
                                query: nodes.get(parentId)?.label,
                                results: []
                            };
                            if (!searchData.results.includes(targetNodeId)) {
                                searchData.results.push(targetNodeId);
                            }
                            nodeSearchQueries.set(searchKey, searchData);
                        }
                        
                        resolve({ nodeId: targetNodeId, isExisting: true, wasMerged: true });
                    } else if (choice === 'hypothetical') {
                        // User chose hypothetical link - create new node and link it
                        const newNodeResult = createNewNode();
                        const targetNodeId = nodes[0].nodeId;
                        
                        // Create hypothetical link
                        setTimeout(() => {
                            const reason = `Similar to ${nodes[0].value} (${(nodes[0].similarity * 100).toFixed(1)}% match)`;
                            createHypotheticalLink(newNodeResult.nodeId, targetNodeId, reason);
                            saveGraphState();
                        }, 100);
                        
                        resolve(newNodeResult);
                    } else {
                        // User chose to create anyway - continue with normal creation
                        resolve(createNewNode());
                    }
                    });
                });
            }
        }
    }
    
    // Create new node (normal path)
    return createNewNode();
    
    function createNewNode() {
    
    const nodeId = `node_${nodeIdCounter++}`;
    const color = getNodeColor(type);
    
    // Create tooltip with field type and breach info
    let tooltip = `${type.toUpperCase()}: ${data.value || data.label || 'Unknown'}`;
    if (data.breach) {
        tooltip += `\n\nFound in: ${data.breach}`;
        if (data.breachData) {
            const bd = data.breachData;
            if (bd.breach_date) tooltip += `\nBreach Date: ${bd.breach_date}`;
            if (bd.added_date) tooltip += `\nAdded: ${bd.added_date}`;
            if (bd.source) tooltip += `\nSource: ${bd.source}`;
        }
    }
    
    // Calculate position with good spacing and NO OVERLAP
    let x, y;
    const minDistance = 400; // INCREASED minimum distance between any two nodes
    
    if (position) {
        x = position.x;
        y = position.y;
    } else if (parentId && nodes.get(parentId)) {
        // Position relative to parent
        const parentNode = nodes.get(parentId);
        const parentPos = network ? network.getPositions([parentId])[parentId] : {x: 0, y: 0};
        
        // Calculate angle based on existing children
        const connectedToParent = edges.get({
            filter: edge => edge.from === parentId
        }).length;
        
        // Use more points in circle for better distribution
        const maxNodesInCircle = 16; // More slots for better spacing
        const angleStep = (2 * Math.PI) / maxNodesInCircle;
        let angle = connectedToParent * angleStep;
        let distance = 800; // Start with even larger distance
        
        // Find a position that doesn't overlap with existing nodes
        let attempts = 0;
        do {
            x = parentPos.x + distance * Math.cos(angle);
            y = parentPos.y + distance * Math.sin(angle);
            
            // Check if this position overlaps with any existing node
            const allPositions = network ? network.getPositions() : {};
            let tooClose = false;
            
            for (let existingId in allPositions) {
                if (existingId !== parentId) {
                    const existingPos = allPositions[existingId];
                    const dx = x - existingPos.x;
                    const dy = y - existingPos.y;
                    const distanceToExisting = Math.sqrt(dx * dx + dy * dy);
                    
                    if (distanceToExisting < minDistance) {
                        tooClose = true;
                        break;
                    }
                }
            }
            
            if (!tooClose) break;
            
            // Try next angle or increase distance
            attempts++;
            if (attempts % maxNodesInCircle === 0) {
                distance += 300; // Move further out faster
            }
            angle += angleStep;
            
        } while (attempts < 50); // Prevent infinite loop
        
    } else {
        // Position new root nodes in a grid pattern with larger spacing
        const gridSize = Math.ceil(Math.sqrt(nodes.length + 1));
        const index = nodes.length;
        const row = Math.floor(index / gridSize);
        const col = index % gridSize;
        const spacing = 1000; // MASSIVE spacing between grid nodes
        
        x = col * spacing - (gridSize * spacing) / 2;
        y = row * spacing - (gridSize * spacing) / 2;
        
        // Add random offset to prevent perfect grid alignment
        x += (Math.random() - 0.5) * 300;
        y += (Math.random() - 0.5) * 300;
        
        // Final collision check for grid nodes
        const allPositions = network ? network.getPositions() : {};
        let finalAttempts = 0;
        while (finalAttempts < 20) {
            let tooClose = false;
            for (let existingId in allPositions) {
                const existingPos = allPositions[existingId];
                const dx = x - existingPos.x;
                const dy = y - existingPos.y;
                const distanceToExisting = Math.sqrt(dx * dx + dy * dy);
                
                if (distanceToExisting < minDistance) {
                    tooClose = true;
                    break;
                }
            }
            
            if (!tooClose) break;
            
            // Move to a completely different position
            x += (Math.random() - 0.5) * 1000;
            y += (Math.random() - 0.5) * 1000;
            finalAttempts++;
        }
    }
    
    const node = {
        id: nodeId,
        label: data.label || data.value || 'Unknown', // Full value, no truncation
        title: tooltip,
        color: {
            background: '#000000',  // Black background
            border: color,          // Colored border
            highlight: {
                background: '#1a1a1a',
                border: color
            }
        },
        data: {
            ...data,
            addedAt: Date.now() // Track when node was added
        },
        type: type,
        x: x,
        y: y,
        physics: false,  // Regular nodes don't move with physics
        // Remove fixed property - let vis.js handle it internally
        font: {
            color: '#666666',  // Bright green text
            multi: 'html',
            size: 12
        },
        shadow: false,  // No shadow
        shape: 'box',
        shapeProperties: {
            borderRadius: 8  // Rounded corners for all nodes
        }
    };
    
    nodes.add(node);
    
    // No temporary highlighting
    
    // Store in map for deduplication
    if (!forceDuplicate) {
        valueToNodeMap.set(valueKey, nodeId);
    }
    
    // Don't create search connections by default
    // These will be stored in query nodes instead
    if (parentId && parentId !== nodeId) {
        // Store the search relationship for later query node creation
        if (!nodeSearchQueries) {
            window.nodeSearchQueries = new Map();
        }
        
        const searchKey = `${parentId}_search`;
        let searchData = nodeSearchQueries.get(searchKey) || {
            sourceNode: parentId,
            query: nodes.get(parentId)?.label,
            results: [],
            timestamp: new Date().getTime()
        };
        searchData.results.push(nodeId);
        nodeSearchQueries.set(searchKey, searchData);
        
        // Update the parent node to show it has been searched
        const parentNode = nodes.get(parentId);
        if (parentNode) {
            nodes.update({
                id: parentId,
                searched: true
            });
        }
    }
    
    updateStatus();
    saveGraphState(); // Save after adding nodes
    
    console.log('=== Node creation complete ===');
    console.log('Created node ID:', nodeId);
    console.log('Node in DataSet:', nodes.get(nodeId));
    
    return { nodeId: nodeId, isExisting: false };
    
    } // End of createNewNode function
}

// Get edge label based on parent and child nodes
function getEdgeLabel(fromId, toId) {
    const fromNode = nodes.get(fromId);
    const toNode = nodes.get(toId);
    
    if (!fromNode || !toNode) return '';
    
    // For consistency: arrows always point from container to contained
    // or from searcher to found
    return ''; // Remove labels for now - arrows speak for themselves
}

// Create connections for all nodes from the same breach record
function createValueBasedConnections(breach) {
    if (!breach) return;
    
    // Collect all nodes from this breach record
    const breachNodes = [];
    const fields = ['email', 'username', 'password', 'ip_address', 'phone', 'name', 'address', 'domain', 'vin'];
    
    // Gather all node IDs from this breach
    fields.forEach(field => {
        if (breach[field] && breach[field].length > 0) {
            breach[field].forEach(value => {
                const valueKey = `${field}_${String(value).toLowerCase().trim()}`;
                const nodeId = valueToNodeMap.get(valueKey);
                if (nodeId) {
                    breachNodes.push(nodeId);
                }
            });
        }
    });
    
    // Also check hashed passwords if they're included
    if (includeHashedPasswords && breach.hashed_password && breach.hashed_password.length > 0) {
        breach.hashed_password.forEach(hash => {
            const valueKey = `hashed_password_${String(hash).toLowerCase().trim()}`;
            const nodeId = valueToNodeMap.get(valueKey);
            if (nodeId) {
                breachNodes.push(nodeId);
            }
        });
    }
    
    // Connect all nodes from this breach record to each other
    // They're all from the same breach record, so they're all related
    for (let i = 0; i < breachNodes.length; i++) {
        for (let j = i + 1; j < breachNodes.length; j++) {
            const nodeId1 = breachNodes[i];
            const nodeId2 = breachNodes[j];
            
            // Create undirected edge (no arrows)
            const edgeId = `edge_${nodeId1}_${nodeId2}_breach`;
            const reverseEdgeId = `edge_${nodeId2}_${nodeId1}_breach`;
            
            // Check if edge already exists in either direction
            if (!edges.get(edgeId) && !edges.get(reverseEdgeId) && nodeId1 !== nodeId2) {
                const breachName = breach.database_name || 'Unknown';
                edges.add({
                    id: edgeId,
                    from: nodeId1,
                    to: nodeId2,
                    title: `Same breach record: ${breachName}`,
                    color: {
                        color: '#666666',
                        inherit: false
                    },
                    dashes: [5, 5],
                    width: 2,
                    arrows: {
                        to: { enabled: false },
                        from: { enabled: false }
                    }
                });
            }
        }
    }
}

// Get color based on node type
function getNodeColor(type) {
    const colors = {
        'email': '#00CED1',      // Dark turquoise
        'username': '#9370DB',    // Medium purple
        'password': '#FFFF00',    // YELLOW for passwords
        'hashed_password': '#FFD700', // Gold for hashes
        'ip_address': '#FFA500',  // Orange
        'phone': '#808080',       // Gray
        'domain': '#32CD32',      // Lime green
        'name': '#4169E1',        // Royal blue
        'address': '#8B4513',     // Saddle brown
        'vin': '#FF1493',         // Deep pink
        'company': '#00FF00',     // Bright green
        'dob': '#FF69B4',         // Hot pink
        'social': '#FF0000',      // Red
        'url': '#32CD32',         // Lime green for URLs
        'search_query': '#FF6B6B', // Coral red for search queries
        'backlinks_query': '#00FF88', // Light green for backlinks results
        'outlinks_query': '#FF00FF', // Magenta for outlinks results
        'owl_query': '#FFD700',      // Gold for ownership-linked domains
        'backlinks_container': '#008888', // Teal for backlinks container (deprecated)
        'backlink': '#00CCCC'     // Light cyan for individual backlinks (deprecated)
    };
    return colors[type] || '#FFFFFF';
}

// Truncate label for display (disabled - show full text)
function truncateLabel(text) {
    if (!text) return 'Unknown';
    // Return full text - no truncation
    return text;
}

// Show node details in the info panel
// Get the query that found this node
function getQueryForNode(nodeId) {
    // Check all search queries to find which one resulted in this node
    for (let [searchKey, searchData] of nodeSearchQueries.entries()) {
        if (searchData.results && searchData.results.includes(nodeId)) {
            return searchData.query;
        }
    }
    return null;
}

function showNodeDetails(node) {
    if (!node) return;
    
    // Debug logging for backlinks nodes
    if (node.type === 'backlinks_query') {
        console.log('🔍 Backlinks node clicked:', {
            type: node.type,
            hasUrls: !!node.urls,
            urlsLength: node.urls?.length,
            hasBacklinksData: !!node.backlinksData,
            backlinksDataLength: node.backlinksData?.length,
            fullNode: node
        });
    }
    
    // Skip cluster nodes and cluster inner nodes
    if (node.type === 'cluster' || node.type === 'cluster_inner') {
        const detailsDiv = document.getElementById('node-details');
        detailsDiv.innerHTML = `
            <div style="padding: 20px;">
                <h3 style="color: #ff6600;">CLUSTER: ${node.label || node.id}</h3>
                <p>This is a cluster frame containing multiple nodes.</p>
                <p>Use the "Cluster Contents" checkbox to show/hide nodes inside.</p>
            </div>
        `;
        return;
    }
    
    // Initialize node.data if it doesn't exist
    if (!node.data) {
        node.data = {
            value: node.label,
            breach: 'Unknown'
        };
    }
    
    currentProfileNode = node;
    const detailsDiv = document.getElementById('node-details');
    
    // Get connected nodes
    const connectedEdges = edges.get({
        filter: edge => edge.from === node.id || edge.to === node.id
    });
    
    const connectedNodes = [];
    connectedEdges.forEach(edge => {
        const connectedId = edge.from === node.id ? edge.to : edge.from;
        const connectedNode = nodes.get(connectedId);
        if (connectedNode) {
            const nodeType = connectedNode.type || 'unknown';
            connectedNodes.push(`${nodeType}: ${escapeHtml(connectedNode.label)}`);
        }
    });
    
    // Ensure node has a type
    const nodeType = node.type || 'unknown';
    
    let html = `
        <div style="background: #0a0a0a; padding: 10px; border: 1px solid #00ff00;">
            <h3 style="margin: 0 0 10px 0; color: ${getNodeColor(nodeType)}">${nodeType.toUpperCase()}: ${escapeHtml(node.label)}</h3>
            
            <div style="margin-bottom: 10px; display: flex; align-items: center; gap: 10px;">
                <strong>Type:</strong>
                <span style="display: inline-block; width: 12px; height: 12px; background: ${getNodeColor(nodeType)}; border-radius: 2px;"></span>
                <span style="color: ${getNodeColor(nodeType)}">${nodeType}</span>
                <button onclick="showChangeTypeMenu('${node.id}')" style="font-size: 11px; padding: 2px 8px; background: #004400; border: 1px solid #00ff00;">Change</button>
            </div>
            
            <div style="margin-bottom: 15px;">
                <strong>Primary Value:</strong> 
                <input type="text" id="node-primary-value" value="${escapeHtml(node.data?.value || node.label || '')}" 
                       style="width: 100%; background: #000; color: #0f0; border: 1px solid #0f0; padding: 5px; font-family: inherit;">
            </div>
            
            ${node.type === 'search_query' && node.urls && node.urls.length > 0 ? `
                <div style="margin-bottom: 15px; background: #001122; padding: 10px; border: 2px solid #FF6B6B;">
                    <strong style="color: #FF6B6B;">Search Results (${node.urls.length} URLs):</strong>
                    ${node.searchTerm ? `<br><small style="color: #888;">Search Term: "${escapeHtml(node.searchTerm)}"</small>` : ''}
                    ${node.isLoading ? `<br><small style="color: #FF6B6B;">⏳ Search in progress: ${node.completedSearches || 0}/${node.totalSearches || 0} complete</small>` : ''}
                    ${node.searchVariations && node.searchVariations.length > 0 ? `
                        <div style="margin-top: 10px; background: #112200; padding: 8px; border: 1px solid #88FF88; border-radius: 4px;">
                            <strong style="color: #88FF88; font-size: 12px;">🔍 Actual Search Queries Run (${node.searchVariations.length}):</strong>
                            <div style="max-height: 150px; overflow-y: auto; margin-top: 5px; font-size: 11px; color: #CCCCCC;">
                                ${node.searchVariations.map((variation, idx) => `
                                    <div style="padding: 2px 0; border-bottom: 1px solid #334433;">
                                        <span style="color: #88FF88; font-weight: bold;">${idx + 1}.</span>
                                        <span style="color: #FFFF88; font-family: monospace;">${escapeHtml(variation)}</span>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    ` : ''}
                    <div style="max-height: 500px; overflow-y: auto; margin-top: 10px; background: #000; border: 1px solid #FF6B6B; padding: 8px;">
                        ${(node.richResults && node.richResults.length > 0) ? 
                            // YOUR WORKING GOOGLE RESULTS: Display rich results with titles and snippets
                            node.richResults.map((result, idx) => `
                                <div style="padding: 8px 0; border-bottom: 1px solid #333; margin-bottom: 8px;">
                                    <div style="margin-bottom: 4px;">
                                        <span style="color: #FF6B6B; font-weight: bold;">${idx + 1}.</span>
                                        <span style="color: #00FF00; font-weight: bold;">${escapeHtml(result.title)}</span>
                                    </div>
                                    <div style="margin-bottom: 4px;">
                                        <a href="${result.url}" target="_blank" style="color: #00DDFF; text-decoration: underline; font-size: 12px;" 
                                           title="Click to open URL in new tab">${escapeHtml(result.url)}</a>
                                    </div>
                                    <div style="color: #CCCCCC; font-size: 11px; font-style: italic;">
                                        ${highlightSearchTerm(result.snippet, node.searchTerm)}
                                    </div>
                                </div>
                            `).join('') :
                            // Fallback to simple URL list
                            node.urls.map((url, idx) => `
                                <div style="padding: 4px 0; border-bottom: 1px solid #333;">
                                    <span style="color: #FF6B6B; font-weight: bold;">${idx + 1}.</span>
                                    <a href="${url}" target="_blank" style="color: #00DDFF; text-decoration: underline;" 
                                       title="Click to open URL in new tab">${escapeHtml(url)}</a>
                                </div>
                            `).join('')
                        }
                    </div>
                </div>
            ` : node.type === 'search_query' ? `
                <div style="margin-bottom: 15px; background: #221100; padding: 10px; border: 2px solid #FF6B6B;">
                    <strong style="color: #FF6B6B;">Search Query Node</strong>
                    ${node.searchTerm ? `<br><small style="color: #888;">Search Term: "${escapeHtml(node.searchTerm)}"</small>` : ''}
                    ${node.isLoading ? `<br><small style="color: #FF6B6B;">⏳ Search in progress: ${node.completedSearches || 0}/${node.totalSearches || 0} complete</small>` : ''}
                    ${node.searchVariations && node.searchVariations.length > 0 ? `
                        <div style="margin-top: 10px; background: #112200; padding: 8px; border: 1px solid #88FF88; border-radius: 4px;">
                            <strong style="color: #88FF88; font-size: 12px;">🔍 Actual Search Queries Run (${node.searchVariations.length}):</strong>
                            <div style="max-height: 150px; overflow-y: auto; margin-top: 5px; font-size: 11px; color: #CCCCCC;">
                                ${node.searchVariations.map((variation, idx) => `
                                    <div style="padding: 2px 0; border-bottom: 1px solid #334433;">
                                        <span style="color: #88FF88; font-weight: bold;">${idx + 1}.</span>
                                        <span style="color: #FFFF88; font-family: monospace;">${escapeHtml(variation)}</span>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    ` : ''}
                    <div style="margin-top: 10px; color: #888;">
                        ${node.isLoading ? 'Search is currently running...' : 'No URLs found yet'}
                    </div>
                </div>
            ` : node.type === 'backlinks_query' && node.data?.urls && node.data.urls.length > 0 ? `
                <div style="margin-bottom: 15px; background: #001122; padding: 10px; border: 2px solid #00FF88;">
                    <strong style="color: #00FF88;">${node.data.backlinksMode === 'exact' ? 'Page' : 'Domain'} Backlinks Results (${node.data.urls.length} URLs):</strong>
                    ${node.data.searchTerm ? `<br><small style="color: #888;">${node.data.backlinksMode === 'exact' ? 'URL' : 'Domain'}: "${escapeHtml(node.data.searchTerm)}"</small>` : ''}
                    <br><small style="color: #888;">Source: ${node.data.source || 'Ahrefs API'}</small>
                    <div style="max-height: 500px; overflow-y: auto; margin-top: 10px; background: #000; border: 1px solid #00FF88; padding: 8px;">
                        ${(node.data.backlinksData && node.data.backlinksData.length > 0) ? 
                            // Display rich backlink results with metadata
                            node.data.backlinksData.map((backlink, idx) => `
                                <div style="padding: 8px 0; border-bottom: 1px solid #333; margin-bottom: 8px;">
                                    <div style="margin-bottom: 4px;">
                                        <span style="color: #00FF88; font-weight: bold;">${idx + 1}.</span>
                                        <span style="color: #00DDFF; font-weight: bold;">${escapeHtml(backlink.domain)}</span>
                                        ${backlink.dofollow ? '<span style="color: #00FF00; font-size: 10px;">[DoFollow]</span>' : '<span style="color: #888; font-size: 10px;">[NoFollow]</span>'}
                                    </div>
                                    <div style="margin-bottom: 4px;">
                                        <a href="${backlink.url}" target="_blank" style="color: #00DDFF; text-decoration: underline; font-size: 12px;" 
                                           title="Click to open URL in new tab">${escapeHtml(backlink.url)}</a>
                                    </div>
                                    ${backlink.anchor_text ? `
                                        <div style="color: #888; font-size: 11px;">
                                            Anchor: "${escapeHtml(backlink.anchor_text)}"
                                        </div>
                                    ` : ''}
                                    ${backlink.ahrefs_rank ? `
                                        <div style="color: #888; font-size: 11px;">
                                            Ahrefs Rank: ${backlink.ahrefs_rank}
                                        </div>
                                    ` : ''}
                                    ${backlink.first_seen ? `
                                        <div style="color: #888; font-size: 11px;">
                                            First seen: ${new Date(backlink.first_seen).toLocaleDateString()}
                                        </div>
                                    ` : ''}
                                </div>
                            `).join('') :
                            // Fallback to simple URL list
                            node.data.urls.map((url, idx) => `
                                <div style="padding: 4px 0; border-bottom: 1px solid #333;">
                                    <span style="color: #00FF88; font-weight: bold;">${idx + 1}.</span>
                                    <a href="${url}" target="_blank" style="color: #00DDFF; text-decoration: underline;" 
                                       title="Click to open URL in new tab">${escapeHtml(url)}</a>
                                </div>
                            `).join('')
                        }
                    </div>
                </div>
            ` : node.type === 'outlinks_query' && node.data?.urls && node.data.urls.length > 0 ? `
                <div style="margin-bottom: 15px; background: #220011; padding: 10px; border: 2px solid #FF00FF;">
                    <strong style="color: #FF00FF;">Outlinks Results (${node.data.urls.length} URLs):</strong>
                    ${node.data.searchTerm ? `<br><small style="color: #888;">From URL: "${escapeHtml(node.data.searchTerm)}"</small>` : ''}
                    <br><small style="color: #888;">Internal: ${node.data.internalCount || 0} | External: ${node.data.externalCount || 0}</small>
                    <br><small style="color: #888;">Source: ${node.data.source || 'Firecrawl'}</small>
                    <div style="max-height: 500px; overflow-y: auto; margin-top: 10px; background: #000; border: 1px solid #FF00FF; padding: 8px;">
                        ${(node.data.outlinksData && node.data.outlinksData.length > 0) ? 
                            // Group by internal/external
                            (() => {
                                const internal = node.data.outlinksData.filter(link => link.type === 'internal');
                                const external = node.data.outlinksData.filter(link => link.type === 'external');
                                let html = '';
                                
                                if (internal.length > 0) {
                                    html += '<div style="margin-bottom: 15px;"><strong style="color: #00FFFF;">Internal Links:</strong></div>';
                                    internal.forEach((link, idx) => {
                                        html += `
                                            <div style="padding: 4px 0; border-bottom: 1px solid #333;">
                                                <span style="color: #00FFFF; font-weight: bold;">${idx + 1}.</span>
                                                <a href="${link.url}" target="_blank" style="color: #00DDFF; text-decoration: underline;" 
                                                   title="Click to open URL in new tab">${escapeHtml(link.url)}</a>
                                            </div>
                                        `;
                                    });
                                }
                                
                                if (external.length > 0) {
                                    html += '<div style="margin-top: 15px; margin-bottom: 15px;"><strong style="color: #FF6666;">External Links:</strong></div>';
                                    external.forEach((link, idx) => {
                                        html += `
                                            <div style="padding: 4px 0; border-bottom: 1px solid #333;">
                                                <span style="color: #FF6666; font-weight: bold;">${idx + 1}.</span>
                                                <a href="${link.url}" target="_blank" style="color: #FF9999; text-decoration: underline;" 
                                                   title="Click to open URL in new tab">${escapeHtml(link.url)}</a>
                                                <span style="color: #888; font-size: 11px; margin-left: 8px;">(${escapeHtml(link.domain)})</span>
                                            </div>
                                        `;
                                    });
                                }
                                
                                return html;
                            })() :
                            // Fallback to simple URL list
                            node.data.urls.map((url, idx) => `
                                <div style="padding: 4px 0; border-bottom: 1px solid #333;">
                                    <span style="color: #FF00FF; font-weight: bold;">${idx + 1}.</span>
                                    <a href="${url}" target="_blank" style="color: #FF99FF; text-decoration: underline;" 
                                       title="Click to open URL in new tab">${escapeHtml(url)}</a>
                                </div>
                            `).join('')
                        }
                    </div>
                </div>
            ` : node.type === 'owl_query' && node.data?.domains && node.data.domains.length > 0 ? `
                <div style="margin-bottom: 15px; background: #221100; padding: 10px; border: 2px solid #FFD700;">
                    <strong style="color: #FFD700;">🦉 Ownership-Linked Domains (${node.data.domains.length}):</strong>
                    ${node.data.searchTerm ? `<br><small style="color: #888;">Source Domain: "${escapeHtml(node.data.searchTerm)}"</small>` : ''}
                    ${node.data.distinctRegistrants && node.data.distinctRegistrants.length > 0 ? `
                        <br><small style="color: #FFD700;">Registrants searched: ${node.data.distinctRegistrants.join(', ')}</small>
                    ` : ''}
                    <br><small style="color: #888;">API calls: ${node.data.apiCalls || '?'} | Method: ${node.data.method || 'WHOIS'}</small>
                    <div style="max-height: 500px; overflow-y: auto; margin-top: 10px; background: #000; border: 1px solid #FFD700; padding: 8px;">
                        ${(node.data.owlData && node.data.owlData.length > 0) ?
                            // Group by match_type
                            (() => {
                                const byType = {};
                                node.data.owlData.forEach(item => {
                                    const key = item.match_type + '|' + item.match_value;
                                    if (!byType[key]) {
                                        byType[key] = { match_type: item.match_type, match_value: item.match_value, domains: [] };
                                    }
                                    byType[key].domains.push(item.domain);
                                });

                                let html = '';
                                Object.values(byType).forEach(group => {
                                    const typeLabel = group.match_type.replace(/_/g, ' ').replace(/\\b\\w/g, c => c.toUpperCase());
                                    html += `
                                        <div style="margin-bottom: 15px;">
                                            <div style="color: #FFD700; font-weight: bold; border-bottom: 1px solid #FFD700; padding-bottom: 4px; margin-bottom: 8px;">
                                                \${typeLabel}: "\${escapeHtml(group.match_value)}" (\${group.domains.length} domains)
                                            </div>
                                    `;
                                    group.domains.forEach((domain, idx) => {
                                        html += `
                                            <div style="padding: 3px 0; border-bottom: 1px solid #333;">
                                                <span style="color: #FFD700;">\${idx + 1}.</span>
                                                <a href="https://\${domain}" target="_blank" style="color: #FFDD44; text-decoration: underline;"
                                                   title="Click to open domain">\${escapeHtml(domain)}</a>
                                            </div>
                                        `;
                                    });
                                    html += '</div>';
                                });
                                return html;
                            })() :
                            // Fallback to simple domain list
                            node.data.domains.map((domain, idx) => `
                                <div style="padding: 4px 0; border-bottom: 1px solid #333;">
                                    <span style="color: #FFD700; font-weight: bold;">\${idx + 1}.</span>
                                    <a href="https://\${domain}" target="_blank" style="color: #FFDD44; text-decoration: underline;"
                                       title="Click to open domain">\${escapeHtml(domain)}</a>
                                </div>
                            `).join('')
                        }
                    </div>
                </div>
            ` : ''}

            ${node.data?.variations && node.data.variations.length > 0 ? `
                <div style="margin-bottom: 15px; background: #001100; padding: 10px; border: 1px solid #003300;">
                    <strong>Variations (${node.data.variations.length}):</strong>
                    ${node.data.mergeHistory ? `<button onclick="showUnmergeOptions('${node.id}')" style="float: right; font-size: 11px;">Unmerge</button>` : ''}
                    <div style="clear: both; margin-top: 5px;">
                        ${node.data.variations.map((v, idx) => `
                            <div style="padding: 5px; margin: 5px 0; background: #000; border: 1px solid #003300;">
                                <span style="color: ${getNodeColor(v.type)}">${v.type}:</span>
                                <input type="text" id="variation-${idx}" value="${escapeHtml(v.value)}" 
                                       style="width: 70%; background: #000; color: #0f0; border: 1px solid #0f0; padding: 2px; font-family: inherit;">
                                <br><small style="color: #888;">From: ${v.breach || 'Unknown'} • ${v.mergedAt ? new Date(v.mergedAt).toLocaleDateString() : ''}</small>
                                ${v.notes ? `<br><small style="color: #888;">Notes: ${escapeHtml(v.notes)}</small>` : ''}
                            </div>
                        `).join('')}
                    </div>
                </div>
            ` : ''}
            
            <div style="margin-bottom: 15px;">
                <strong>Found in:</strong> <span style="color: #ff0000">${escapeHtml(node.data?.breach || 'Unknown')}</span>
                ${node.data?.breachData?.breach_date ? `<br><small>Breach Date: ${node.data.breachData.breach_date}</small>` : ''}
            </div>
            
            ${getQueryForNode(node.id) ? `
                <div style="margin-bottom: 15px; background: #330000; padding: 10px; border: 2px solid #ff0000;">
                    <strong style="color: #ff0000;">Found by Query:</strong><br>
                    <div style="background: #000000; padding: 8px; border: 1px solid #ff0000; margin-top: 5px;">
                        <span style="color: #ff0000; font-family: monospace;">${escapeHtml(getQueryForNode(node.id))}</span>
                    </div>
                </div>
            ` : ''}
            
            <div style="margin-bottom: 15px;">
                <strong>Connected to (${connectedNodes.length}):</strong>
                <div style="max-height: 150px; overflow-y: auto; margin-top: 5px;">
                    ${connectedNodes.length > 0 ? connectedNodes.map(n => `<div style="padding: 2px 0;">• ${n}</div>`).join('') : '<div>No connections</div>'}
                </div>
            </div>
            
            ${(() => {
                // Check for merged images
                let mergedImages = [];
                if (node.data.mergedImages && node.data.mergedImages.length > 0) {
                    mergedImages = node.data.mergedImages;
                } else if (node.data.variations && node.data.variations.length > 0) {
                    // Check variations for image nodes
                    node.data.variations.forEach(v => {
                        if (v.type === 'image' && v.dataURL) {
                            mergedImages.push({ dataURL: v.dataURL, mergedAt: v.mergedAt });
                        }
                    });
                }
                
                return mergedImages.length > 0 ? `
                    <div style="margin-bottom: 15px; background: #001100; padding: 10px; border: 1px solid #00ff00;">
                        <strong>Merged Images (${mergedImages.length}):</strong>
                        <div style="display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px;">
                            ${mergedImages.map((img, idx) => `
                                <div style="border: 2px solid #00ff00; padding: 5px;">
                                    <img src="${img.dataURL}" style="max-width: 200px; max-height: 200px; cursor: pointer;" 
                                         onclick="window.open('${img.dataURL}', '_blank')" 
                                         title="Click to view full size">
                                    ${img.mergedAt ? `<br><small style="color: #888;">Merged: ${new Date(img.mergedAt).toLocaleDateString()}</small>` : ''}
                                </div>
                            `).join('')}
                        </div>
                    </div>
                ` : '';
            })()}
            
            <div style="margin-bottom: 15px; background: #001122; padding: 10px; border: 1px solid #00DDFF;">
                <strong style="color: #00DDFF;">URLs:</strong>
                <button onclick="addUrlField('${node.id}')" style="float: right; font-size: 11px; padding: 2px 8px; background: #003366; border: 1px solid #00DDFF;">+ Add URL</button>
                <div style="clear: both;"></div>
                <div id="node-urls-container" style="margin-top: 10px;">
                    ${(node.data.manualUrls || []).map((url, idx) => `
                        <div style="display: flex; gap: 10px; margin-bottom: 5px;">
                            <input type="text" id="node-url-${idx}" value="${escapeHtml(url)}" 
                                   style="flex: 1; background: #000; color: #0f0; border: 1px solid #00DDFF; padding: 5px; font-family: inherit;"
                                   placeholder="Enter URL...">
                            <button onclick="removeUrlField(${idx})" style="background: #660000; border: 1px solid #ff0000; color: #ff0000; padding: 5px 10px;">×</button>
                        </div>
                    `).join('')}
                    ${(!node.data.manualUrls || node.data.manualUrls.length === 0) ? `
                        <div style="display: flex; gap: 10px; margin-bottom: 5px;">
                            <input type="text" id="node-url-0" value="" 
                                   style="flex: 1; background: #000; color: #0f0; border: 1px solid #00DDFF; padding: 5px; font-family: inherit;"
                                   placeholder="Enter URL...">
                            <button onclick="removeUrlField(0)" style="background: #660000; border: 1px solid #ff0000; color: #ff0000; padding: 5px 10px;">×</button>
                        </div>
                    ` : ''}
                </div>
            </div>
            
            ${node.type === 'url' ? `
                <div style="margin-bottom: 15px; background: #001122; padding: 10px; border: 1px solid #00FFFF;">
                    <strong style="color: #00FFFF;">Screenshot:</strong>
                    ${node.data.screenshotStatus === 'loading' ? `
                        <div style="text-align: center; padding: 20px;">
                            <div style="color: #00FFFF;">📸 Capturing screenshot...</div>
                            <small style="color: #888;">This may take up to 30 seconds</small>
                        </div>
                    ` : node.data.screenshotStatus === 'error' ? `
                        <div style="text-align: center; padding: 20px;">
                            <div style="color: #FF6666;">❌ Screenshot capture failed</div>
                            <small style="color: #888;">${escapeHtml(node.data.screenshotError || 'Unknown error')}</small>
                            <br>
                            <button onclick="retryScreenshot('${node.id}')" style="margin-top: 10px; font-size: 11px; padding: 4px 12px;">Retry</button>
                        </div>
                    ` : node.data.screenshot ? `
                        <div style="margin-top: 10px;">
                            <img src="${node.data.screenshot}"
                                 style="width: 100%; max-height: 400px; object-fit: contain; border: 1px solid #00FFFF; cursor: pointer;"
                                 onclick="showFullScreenshot('${node.id}')"
                                 title="Click to view full size">
                            <small style="color: #888; display: block; margin-top: 5px;">
                                Captured: ${new Date(node.data.screenshotCapturedAt).toLocaleString()}
                            </small>
                        </div>
                    ` : `
                        <div style="text-align: center; padding: 20px;">
                            <button onclick="captureScreenshot('${node.id}')" style="padding: 8px 16px;">
                                📸 Capture Screenshot
                            </button>
                        </div>
                    `}
                </div>
            ` : ''}

            ${node.type === 'company' ? `
                <div style="margin-bottom: 15px; background: #002200; padding: 10px; border: 2px solid #00FF00;">
                    <strong style="color: #00FF00;">COMPANY PROFILE:</strong>

                    ${node.jurisdiction ? `
                        <div style="margin-top: 8px;">
                            <strong style="color: #88FF88;">Jurisdiction:</strong>
                            <span style="color: #FFFFFF;">${escapeHtml(node.jurisdiction)}</span>
                        </div>
                    ` : ''}

                    ${node.company_number ? `
                        <div style="margin-top: 8px;">
                            <strong style="color: #88FF88;">Company Number:</strong>
                            <span style="color: #FFFFFF;">${escapeHtml(node.company_number)}</span>
                        </div>
                    ` : ''}

                    ${node.status ? `
                        <div style="margin-top: 8px;">
                            <strong style="color: #88FF88;">Status:</strong>
                            <span style="color: ${node.status.toLowerCase().includes('active') ? '#00FF00' : '#FF8800'};">
                                ${escapeHtml(node.status)}
                            </span>
                        </div>
                    ` : ''}

                    ${node.incorporation_date ? `
                        <div style="margin-top: 8px;">
                            <strong style="color: #88FF88;">Incorporation Date:</strong>
                            <span style="color: #FFFFFF;">${escapeHtml(node.incorporation_date)}</span>
                        </div>
                    ` : ''}

                    ${node.url ? `
                        <div style="margin-top: 8px;">
                            <strong style="color: #88FF88;">Registry URL:</strong>
                            <a href="${node.url}" target="_blank" style="color: #00DDFF; text-decoration: underline;">
                                View on ${node.source || 'Registry'}
                            </a>
                        </div>
                    ` : ''}

                    ${node.leak_source ? `
                        <div style="margin-top: 8px; padding: 5px; background: #440000; border: 1px solid #FF0000;">
                            <strong style="color: #FF6666;">⚠️ LEAK DATA:</strong>
                            <span style="color: #FFFF00;">${escapeHtml(node.leak_source)}</span>
                        </div>
                    ` : ''}

                    ${node.source ? `
                        <div style="margin-top: 8px;">
                            <strong style="color: #88FF88;">Data Source:</strong>
                            <span style="color: #888888;">${escapeHtml(node.source)}</span>
                        </div>
                    ` : ''}
                </div>
            ` : ''}
            
            <div>
                <strong>Notes:</strong><br>
                <textarea id="node-notes" style="width: 100%; height: 100px; background: #000; color: #0f0; border: 1px solid #0f0; font-family: inherit; margin-top: 5px;" placeholder="Add notes here...">${escapeHtml(node.data.notes || '')}</textarea>
                <button onclick="showChangeTypeMenu('${node.id}')" style="margin-top: 5px; background: #004400; border: 1px solid #00ff00;">Change Type</button>
            </div>
        </div>
    `;
    
    detailsDiv.innerHTML = html;
    
    // Add auto-save event listeners
    setupAutoSave(node.id);
}

// Expand a node (search for related data)
async function expandNode(node) {
    console.log('expandNode called with:', node);
    
    // Ensure node has data property
    if (!node) {
        console.error('expandNode: No node provided');
        return;
    }
    
    if (!node.data) {
        console.log('Node missing data property, creating from label/title');
        node.data = {
            value: node.label || node.title || node.id,
            label: node.label || node.title || node.id
        };
    }
    
    // Check if this node has been searched before (for information only)
    const nodeKey = `${node.id}_${node.type}_${node.data.value || node.data.label}`;
    const hasBeenSearched = nodeExpansionCache.has(nodeKey);
    
    if (hasBeenSearched) {
        updateStatus('Note: This node has been searched before. Running new search...');
    }
    
    // Always show the search provider selection modal
    showSearchProviderModal(node);
    
    updateStatus('Select a search provider...');
}

// Handle domain node expansion (REVERSE WHOIS + DeHashed email search)
async function handleDomainNodeExpansion(node) {
    const domain = node.data.value || node.label;
    console.log('=== DOMAIN REVERSE SEARCH START ===');
    console.log('Reverse searching domain:', domain);
    updateStatus(`Reverse searching domain: ${domain}...`);
    
    // Mark as expanded
    const nodeKey = `${node.id}_${node.type}_${domain}`;
    nodeExpansionCache.set(nodeKey, true);
    
    try {
        // First get domain's current WHOIS to extract registrant info
        updateStatus(`Getting ${domain} WHOIS for reverse search...`);
        const domainWhois = await performWhoisSearch(domain, 'domain');
        
        if (!domainWhois || !domainWhois.records || domainWhois.records.length === 0) {
            updateStatus(`No WHOIS data found for ${domain} - cannot perform reverse search`);
            return;
        }
        
        // Extract registrant info from the domain's WHOIS
        const latestRecord = domainWhois.records[0];
        const registrantContact = latestRecord.registrantContact || {};
        
        // Build search terms for reverse WHOIS
        const searchTerms = [];
        if (registrantContact.email && !registrantContact.email.includes('privacy') && !registrantContact.email.includes('redacted')) {
            searchTerms.push({ value: registrantContact.email, type: 'email' });
        }
        if (registrantContact.name && !registrantContact.name.includes('privacy') && !registrantContact.name.includes('redacted')) {
            searchTerms.push({ value: registrantContact.name, type: 'terms' });
        }
        if (registrantContact.organization && !registrantContact.organization.includes('privacy') && !registrantContact.organization.includes('redacted')) {
            searchTerms.push({ value: registrantContact.organization, type: 'terms' });
        }
        
        if (searchTerms.length === 0) {
            updateStatus(`${domain} WHOIS data is privacy protected - trying domain history anyway...`);
            // Fall back to showing domain history
            await showWhoisResultsDialog(domainWhois, domain, node.id);
            return;
        }
        
        // Perform REVERSE WHOIS searches for each term
        updateStatus(`Found ${searchTerms.length} search terms - performing reverse WHOIS...`);
        const reversePromises = searchTerms.map(term => performWhoisSearch(term.value, term.type));
        
        // Also search DeHashed for emails with this domain
        const emailSearchPromise = performSearch(`@${domain}`, 'email', node.id);
        
        // Wait for all searches to complete
        const [emailSearchResult, ...reverseResults] = await Promise.all([emailSearchPromise, ...reversePromises]);
        
        // Combine all WHOIS results
        let allDomains = new Set([domain]); // Include original domain
        let allWhoisResults = [];
        
        for (let i = 0; i < reverseResults.length; i++) {
            const result = reverseResults[i];
            const searchTerm = searchTerms[i];
            
            if (result && result.results) {
                console.log(`Reverse WHOIS for ${searchTerm.value} found ${result.results.length} domains`);
                result.results.forEach(r => {
                    if (r.domain) allDomains.add(r.domain);
                });
                allWhoisResults.push(...result.results);
            }
        }
        
        console.log(`Total unique domains found: ${allDomains.size}`);
        updateStatus(`Found ${allDomains.size} domains associated with ${domain} registrant`);
        
        // Show results dialog with all found domains
        if (allWhoisResults.length > 0) {
            const combinedResult = {
                results: allWhoisResults,
                query: domain,
                query_type: 'reverse_domain'
            };
            await showWhoisResultsDialog(combinedResult, domain, node.id);
        } else {
            updateStatus(`No additional domains found for ${domain} registrant`);
        }
        
    } catch (error) {
        console.error('Error during domain reverse search:', error);
        updateStatus(`Error reverse searching domain: ${error.message}`);
    }
    
    console.log('=== DOMAIN REVERSE SEARCH END ===');
}

// Check if query should be searched in WHOIS
function isWhoisCandidate(query, type) {
    // If type is explicitly set, check if it's a whois-able type
    if (type) {
        return type === 'email' || type === 'phone' || type === 'name' || type === 'company';
    }
    
    // Auto-detect if type not provided
    if (/@/.test(query)) {
        return true; // Email
    } else if (/^\+?\d[\d\s\-\(\)\.]{6,}$/.test(query.trim())) {
        return true; // Phone
    } else if (/^[a-zA-Z\s]{3,}$/.test(query) && query.split(' ').length >= 2) {
        return true; // Name (at least two words)
    }
    
    return false;
}

// Perform WHOIS search
async function performWhoisSearch(query, type) {
    try {
        console.log('performWhoisSearch called with:', { query, type });
        updateStatus(`🌐 Searching WHOIS for ${query}...`);
        
        const requestBody = { query, type };
        console.log('Sending WHOIS request:', requestBody);
        
        const response = await fetch('/api/whois', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });
        
        console.log('WHOIS response status:', response.status);
        
        if (!response.ok) {
            console.error('WHOIS search failed:', response.status);
            const errorText = await response.text();
            console.error('Error response:', errorText);
            return null;
        }
        
        const data = await response.json();
        console.log('WHOIS response data:', data);
        
        if (data.error) {
            console.error('WHOIS error:', data.error);
            updateStatus('WHOIS search failed: ' + data.error);
            return null;
        }
        
        return data;
    } catch (error) {
        console.error('WHOIS search error:', error);
        updateStatus('WHOIS search error');
        return null;
    }
}

// Perform OSINT search
async function performOSINTSearch(query, type) {
    try {
        console.log('performOSINTSearch called with:', { query, type });
        updateStatus(`🔍 Searching OSINT Industries for ${query}...`);
        
        const requestBody = { query, type };
        console.log('Sending OSINT request:', requestBody);
        
        const response = await fetch('/api/osint', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });
        
        console.log('OSINT response status:', response.status);
        
        if (!response.ok) {
            console.error('OSINT search failed:', response.status);
            const errorText = await response.text();
            console.error('Error response:', errorText);
            return null;
        }
        
        const data = await response.json();
        console.log('OSINT response data:', data);
        
        if (data.error) {
            console.error('OSINT error:', data.error);
            updateStatus('OSINT search failed: ' + data.error);
            return null;
        }
        
        return data;
    } catch (error) {
        console.error('OSINT search error:', error);
        updateStatus('OSINT search error');
        return null;
    }
}

// Handle web search engines (Brave, DuckDuckGo, Exa, Firecrawl)
async function handleWebSearch(query, engine = 'web-search', parentNodeId = null) {
    try {
        // Map engine type to display name
        const engineNames = {
            'web-search': 'Web Search (All)',
            'brave': 'Brave',
            'duckduckgo': 'DuckDuckGo',
            'exa': 'Exa',
            'firecrawl': 'Firecrawl'
        };
        const engineName = engineNames[engine] || 'Web Search';

        updateStatus(`🔍 Searching ${engineName} for "${query}"...`);

        // Call Drill Search backend for web search
        const DRILL_SEARCH_BASE_URL = 'http://localhost:3000';
        const response = await fetchWithRetry(`${DRILL_SEARCH_BASE_URL}/api/search/stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                query: query,
                engine: engine === 'web-search' ? undefined : engine, // undefined = all engines
                maxResults: 20
            })
        });

        if (!response.ok) {
            throw new Error(`Web search failed: ${response.status}`);
        }

        const data = await response.json();

        if (!data.results || data.results.length === 0) {
            updateStatus(`No results found for "${query}" on ${engineName}`);
            return false;
        }

        // Create query node
        const queryNodeId = `query_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        const queryNode = {
            id: queryNodeId,
            label: query,
            type: 'query',
            shape: 'diamond',
            color: { background: '#000000', border: '#FF0000' },
            font: { color: '#FFFFFF' },
            data: {
                value: query,
                engine: engineName,
                resultCount: data.results.length,
                timestamp: new Date().toISOString(),
                searchType: 'web_search'
            }
        };

        nodes.add(queryNode);

        // Position results around the query node
        const queryPos = network.getPositions([queryNodeId])[queryNodeId];
        const centerX = queryPos ? queryPos.x : 0;
        const centerY = queryPos ? queryPos.y : 0;
        const radius = 500;
        const angleStep = (2 * Math.PI) / data.results.length;

        // Process search results
        data.results.forEach((result, index) => {
            const angle = index * angleStep;
            const x = centerX + radius * Math.cos(angle);
            const y = centerY + radius * Math.sin(angle);

            // Create URL node for each result
            const urlNodeId = `url_${Date.now()}_${index}`;
            const urlNode = {
                id: urlNodeId,
                label: result.title || result.url,
                type: 'url',
                shape: 'box',
                color: { background: '#000000', border: '#FFFFFF' },
                font: { color: '#FFFFFF', size: 12 },
                x: x,
                y: y,
                data: {
                    value: result.url,
                    fullUrl: result.url,
                    title: result.title,
                    snippet: result.snippet,
                    engine: result.engine || engineName,
                    timestamp: new Date().toISOString()
                }
            };

            nodes.add(urlNode);

            // Create edge from query to URL
            edges.add({
                id: `edge_${queryNodeId}_${urlNodeId}`,
                from: queryNodeId,
                to: urlNodeId,
                label: result.engine || engineName,
                color: { color: '#3282b8', opacity: 0.5 },
                width: 1,
                arrows: { to: { enabled: true, scaleFactor: 0.5 } }
            });
        });

        updateStatus(`✅ Found ${data.results.length} results from ${engineName}`);
        return true;

    } catch (error) {
        console.error('Web search error:', error);
        updateStatus(`❌ Web search failed: ${error.message}`);
        return false;
    }
}

// Handle OSINT Industries search
async function handleOSINTSearch(query, parentNodeId = null) {
    try {
        updateStatus(`🔍 Searching OSINT Industries for ${query}...`);
        
        // Auto-detect query type for OSINT
        let osintType = 'email';
        if (query.includes('@')) {
            osintType = 'email';
        } else if (/^\+?\d[\d\s\-\(\)\.]{6,}$/.test(query.trim())) {
            osintType = 'phone';
        }
        
        let searchQueries = [query]; // Start with original query
        
        // For phone numbers, generate local variations using Claude AI
        if (osintType === 'phone') {
            updateStatus(`🔍 Generating phone number variations for OSINT search...`);
            
            try {
                const phoneVariations = await generatePhoneVariations(query);
                if (phoneVariations && phoneVariations.length > 0) {
                    // Add variations but avoid duplicates
                    phoneVariations.forEach(variation => {
                        if (!searchQueries.includes(variation)) {
                            searchQueries.push(variation);
                        }
                    });
                    console.log(`Generated ${phoneVariations.length} phone variations:`, phoneVariations);
                }
            } catch (error) {
                console.warn('Failed to generate phone variations:', error);
                // Continue with original query if variation generation fails
            }
        }
        
        // Search OSINT for each query variation
        const allOsintData = { entities: [], raw_results: [] };
        let searchCount = 0;
        
        for (const searchQuery of searchQueries) {
            updateStatus(`🔍 OSINT search ${++searchCount}/${searchQueries.length}: ${searchQuery}...`);
            
            try {
                const osintData = await performOSINTSearch(searchQuery, osintType);
                
                if (osintData && osintData.entities) {
                    // Merge entities, avoiding duplicates
                    osintData.entities.forEach(entity => {
                        if (!allOsintData.entities.some(existing => 
                            existing.value === entity.value && existing.type === entity.type)) {
                            allOsintData.entities.push({
                                ...entity,
                                context: `${entity.context} (searched: ${searchQuery})`
                            });
                        }
                    });
                }
                
                if (osintData && osintData.raw_results) {
                    allOsintData.raw_results.push(...osintData.raw_results);
                }
                
                // Small delay between searches to avoid rate limiting
                if (searchCount < searchQueries.length) {
                    await new Promise(resolve => setTimeout(resolve, 500));
                }
            } catch (error) {
                console.warn(`OSINT search failed for ${searchQuery}:`, error);
            }
        }
        
        if (!allOsintData.entities || allOsintData.entities.length === 0) {
            updateStatus(`No OSINT results found for ${query} or its variations`);
            return false;
        }
        
        console.log(`Claude extracted ${allOsintData.entities.length} total entities from OSINT data across ${searchQueries.length} variations`);
        
        // Show OSINT results dialog for user approval
        showOSINTResultsDialog(allOsintData, query, parentNodeId);
        
        return true;
    } catch (error) {
        console.error('OSINT search error:', error);
        updateStatus(`OSINT search failed: ${error.message}`);
        return false;
    }
}

// Show OSINT results dialog
function showOSINTResultsDialog(osintData, query, parentNodeId) {
    console.log(`Showing OSINT results dialog with ${osintData.entities.length} entities`);

    // Save query and parent for later use
    window.osintOriginalQuery = query;
    window.osintOriginalParent = parentNodeId;
    window.osintEntities = osintData.entities;

    const html = `
        <div class="modal" id="osintResultsModal" style="display: block; position: fixed; z-index: 10000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.8);">
            <div class="modal-content" style="background-color: #1a1a1a; margin: 5% auto; padding: 20px; width: 80%; max-width: 800px; max-height: 80vh; overflow-y: auto; border: 2px solid #666;">
                <h2 style="color: #00BFFF; margin-bottom: 20px;">🔍 OSINT Industries Results for: ${escapeHtml(query)}</h2>
                <p style="margin-bottom: 20px;">Found ${osintData.total_results || 0} total results across platforms. Claude extracted ${osintData.entities.length} relevant entities:</p>
                
                <div style="margin-bottom: 20px;">
                    <button onclick="selectAllOSINT(true)" style="background: #444; color: white; border: none; padding: 5px 15px; margin-right: 10px; border-radius: 3px; cursor: pointer;">Select All</button>
                    <button onclick="selectAllOSINT(false)" style="background: #444; color: white; border: none; padding: 5px 15px; border-radius: 3px; cursor: pointer;">Deselect All</button>
                </div>
                
                <div id="osintSuggestionsList">
                    ${osintData.entities.map((entity, index) => {
                        const nodeColor = getNodeColor(entity.type);
                        return `
                            <div style="margin: 10px 0; padding: 15px; background: #222; border: 1px solid #444; border-radius: 5px;">
                                <div style="display: flex; align-items: flex-start; gap: 10px;">
                                    <input type="checkbox" id="osint_entity_${index}_enabled" checked style="margin-top: 5px;">
                                    
                                    <div style="flex: 1;">
                                        <div style="display: flex; gap: 10px; margin-bottom: 10px; align-items: center;">
                                            <label style="color: #aaa; font-size: 0.9em; min-width: 40px;">Type:</label>
                                            <select id="osint_entity_${index}_type" style="background: #333; color: #fff; border: 1px solid #555; padding: 3px; border-radius: 3px;">
                                                <option value="email" ${entity.type === 'email' ? 'selected' : ''}>Email</option>
                                                <option value="phone" ${entity.type === 'phone' ? 'selected' : ''}>Phone</option>
                                                <option value="name" ${entity.type === 'name' ? 'selected' : ''}>Name</option>
                                                <option value="username" ${entity.type === 'username' ? 'selected' : ''}>Username</option>
                                                <option value="company" ${entity.type === 'company' ? 'selected' : ''}>Company</option>
                                                <option value="address" ${entity.type === 'address' ? 'selected' : ''}>Address</option>
                                                <option value="url" ${entity.type === 'url' ? 'selected' : ''}>URL</option>
                                                <option value="other" ${entity.type === 'other' ? 'selected' : ''}>Other</option>
                                            </select>
                                        </div>
                                        
                                        <div style="display: flex; gap: 10px; margin-bottom: 10px; align-items: center;">
                                            <label style="color: #aaa; font-size: 0.9em; min-width: 40px;">Value:</label>
                                            <input type="text" id="osint_entity_${index}_value" value="${escapeHtml(entity.value)}" 
                                                   style="flex: 1; background: #333; color: #fff; border: 1px solid #555; padding: 5px; border-radius: 3px;">
                                        </div>
                                        
                                        <div style="display: flex; gap: 10px; margin-bottom: 10px; align-items: flex-start;">
                                            <label style="color: #aaa; font-size: 0.9em; min-width: 40px; margin-top: 5px;">Notes:</label>
                                            <textarea id="osint_entity_${index}_notes" rows="2" placeholder="Add any notes about this entity..."
                                                      style="flex: 1; background: #333; color: #fff; border: 1px solid #555; padding: 5px; border-radius: 3px; resize: vertical;">${escapeHtml(entity.context || '')}</textarea>
                                        </div>
                                        
                                        <div style="color: #666; font-size: 0.8em; margin-top: 5px;">
                                            Source: ${entity.context}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        `;
                    }).join('')}
                    
                    ${osintData.notes && osintData.notes.length > 0 ? `
                        <div style="margin: 20px 0; padding: 15px; background: #001122; border: 1px solid #004466; border-radius: 5px;">
                            <h3 style="color: #00BFFF; margin-bottom: 15px;">📝 Suggested Notes from Claude:</h3>
                            ${osintData.notes.map((note, index) => `
                                <div style="margin: 10px 0; padding: 10px; background: #002233; border: 1px solid #003355; border-radius: 3px;">
                                    <div style="display: flex; gap: 10px; margin-bottom: 8px; align-items: center;">
                                        <input type="checkbox" id="osint_note_${index}_enabled" checked style="margin: 0;">
                                        <label style="color: #aaa; font-size: 0.9em; min-width: 60px;">For Node:</label>
                                        <input type="text" id="osint_note_${index}_target" value="${escapeHtml(note.for_node || '')}" 
                                               style="flex: 1; background: #333; color: #fff; border: 1px solid #555; padding: 3px; border-radius: 3px;" placeholder="Target node value">
                                    </div>
                                    <div style="display: flex; gap: 10px; align-items: flex-start;">
                                        <label style="color: #aaa; font-size: 0.9em; min-width: 60px; margin-top: 5px;">Note:</label>
                                        <textarea id="osint_note_${index}_content" rows="2" 
                                                  style="flex: 1; background: #333; color: #fff; border: 1px solid #555; padding: 5px; border-radius: 3px; resize: vertical;">${escapeHtml(note.note || '')}</textarea>
                                    </div>
                                    <div style="color: #666; font-size: 0.8em; margin-top: 5px;">
                                        Context: ${note.context || 'N/A'}
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    ` : ''}
                </div>
                
                <details style="margin-top: 20px;">
                    <summary style="cursor: pointer; color: #00BFFF;">View Raw OSINT Data (${osintData.total_results || 0} results)</summary>
                    <pre style="background: #000; padding: 10px; margin-top: 10px; color: #888; overflow: auto; max-height: 300px;">${JSON.stringify(osintData.raw_results || [], null, 2)}</pre>
                </details>
                
                <div style="margin-top: 20px; text-align: right;">
                    <button onclick="cancelOSINTResults()" style="background: #666; color: white; border: none; padding: 10px 20px; margin-right: 10px; border-radius: 5px; cursor: pointer;">Cancel</button>
                    <button onclick="createOSINTNodes('${parentNodeId || ''}', ${osintData.entities.length})" style="background: #00BFFF; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer;">Create Selected Nodes</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', html);
    window.osintEntities = osintData.entities;
}

// Helper functions for OSINT dialog
window.selectAllOSINT = function(checked) {
    const checkboxes = document.querySelectorAll('[id^="osint_entity_"][id$="_enabled"]');
    checkboxes.forEach(cb => cb.checked = checked);
}

window.cancelOSINTResults = function() {
    const modal = document.getElementById('osintResultsModal');
    if (modal) modal.remove();
    updateStatus('OSINT results cancelled');
}

window.createOSINTNodes = async function(parentNodeId, entityCount) {
    const selectedEntities = [];
    const selectedNotes = [];

    // Get the original query from the saved data
    const originalQuery = window.osintOriginalQuery || 'OSINT Search';

    // Collect edited entity data from form fields
    for (let i = 0; i < entityCount; i++) {
        const checkbox = document.getElementById(`osint_entity_${i}_enabled`);
        const typeSelect = document.getElementById(`osint_entity_${i}_type`);
        const valueInput = document.getElementById(`osint_entity_${i}_value`);
        const notesTextarea = document.getElementById(`osint_entity_${i}_notes`);
        
        if (checkbox && checkbox.checked && typeSelect && valueInput) {
            selectedEntities.push({
                type: typeSelect.value,
                value: valueInput.value.trim(),
                context: notesTextarea ? notesTextarea.value.trim() : '',
                originalData: window.osintEntities[i] // Keep reference to original
            });
        }
    }
    
    // Collect selected notes from Claude suggestions
    const noteCheckboxes = document.querySelectorAll('[id^="osint_note_"][id$="_enabled"]');
    noteCheckboxes.forEach((checkbox, index) => {
        if (checkbox.checked) {
            const targetInput = document.getElementById(`osint_note_${index}_target`);
            const contentTextarea = document.getElementById(`osint_note_${index}_content`);
            
            if (targetInput && contentTextarea && targetInput.value.trim() && contentTextarea.value.trim()) {
                selectedNotes.push({
                    targetNode: targetInput.value.trim(),
                    content: contentTextarea.value.trim()
                });
            }
        }
    });
    
    if (selectedEntities.length === 0 && selectedNotes.length === 0) {
        updateStatus('No entities or notes selected');
        return;
    }

    // Remove modal
    const modal = document.getElementById('osintResultsModal');
    if (modal) modal.remove();

    // Create OSINT query node (red frame, black background)
    const queryNodeId = `query_osint_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const queryNode = {
        id: queryNodeId,
        label: originalQuery,
        type: 'query',
        shape: 'diamond',
        color: { background: '#000000', border: '#FF0000' },
        font: { color: '#FFFFFF' },
        data: {
            value: originalQuery,
            searchType: 'osint',
            resultCount: selectedEntities.length,
            timestamp: new Date().toISOString()
        }
    };

    nodes.add(queryNode);

    // If there was a parent node (input), connect query to parent
    if (parentNodeId) {
        edges.add({
            id: `edge_${parentNodeId}_${queryNodeId}`,
            from: parentNodeId,
            to: queryNodeId,
            label: 'searched',
            color: { color: '#FF0000', opacity: 0.5 },
            width: 2,
            arrows: { to: { enabled: true, scaleFactor: 0.5 } }
        });
    }

    // Create nodes for selected entities
    let createdCount = 0;
    const createdNodeIds = [];
    
    for (const entity of selectedEntities) {
        try {
            const result = await addNode({
                value: entity.value,
                label: entity.value,
                source: 'OSINT Industries',
                context: entity.context,
                osintData: entity
            }, entity.type, null); // Don't connect to parent, we'll connect to query node

            if (result && result.nodeId) {
                if (!result.isExisting) {
                    createdCount++;
                }
                createdNodeIds.push(result.nodeId);

                // Link to the query node
                const edgeLabel = result.isExisting ?
                    (result.wasMerged ? 'OSINT merged' : 'OSINT found') :
                    'OSINT found';
                const edgeId = `edge_${queryNodeId}_${result.nodeId}_osint`;

                // Check if edge already exists
                const existingEdge = edges.get({
                    filter: edge => (edge.from === queryNodeId && edge.to === result.nodeId) ||
                                   (edge.from === result.nodeId && edge.to === queryNodeId)
                });

                if (existingEdge.length === 0 && queryNodeId !== result.nodeId) {
                    edges.add({
                        id: edgeId,
                        from: queryNodeId,
                        to: result.nodeId,
                        label: edgeLabel,
                        color: { color: '#FF0000', opacity: 0.5 },
                        width: 1,
                        arrows: { to: { enabled: true, scaleFactor: 0.5 } }
                    });
                }
            }
        } catch (error) {
            console.error('Error creating OSINT node:', error);
        }
    }
    
    // Group entities by their source/context and link nodes from the same profile
    const profileGroups = new Map();
    selectedEntities.forEach((entity, index) => {
        const nodeId = createdNodeIds[index];
        if (nodeId) {
            // Group by context/source platform
            const contextKey = entity.context.split(' ').slice(0, 2).join(' '); // First two words as grouping key
            if (!profileGroups.has(contextKey)) {
                profileGroups.set(contextKey, []);
            }
            profileGroups.get(contextKey).push({ nodeId, entity });
        }
    });
    
    // Link nodes within each profile group
    let linkCount = 0;
    profileGroups.forEach((group, context) => {
        if (group.length > 1) {
            // Create edges between all nodes in the same profile group
            for (let i = 0; i < group.length; i++) {
                for (let j = i + 1; j < group.length; j++) {
                    const edgeId = `edge_${group[i].nodeId}_${group[j].nodeId}_osint_profile`;
                    // Check if edge already exists
                    const existingEdge = edges.get({
                        filter: edge => (edge.from === group[i].nodeId && edge.to === group[j].nodeId) ||
                                       (edge.from === group[j].nodeId && edge.to === group[i].nodeId)
                    });
                    
                    if (existingEdge.length === 0) {
                        edges.add({
                            id: edgeId,
                            from: group[i].nodeId,
                            to: group[j].nodeId,
                            title: `shared profile: ${context}`,
                            ...getConnectionStyle('DEFAULT')
                        });
                    }
                    linkCount++;
                }
            }
        }
    });
    
    const connectedCount = createdNodeIds.length - createdCount;
    let statusMsg = `OSINT Industries: `;
    if (createdCount > 0) statusMsg += `created ${createdCount} new nodes`;
    if (connectedCount > 0) {
        if (createdCount > 0) statusMsg += `, `;
        statusMsg += `connected to ${connectedCount} existing nodes`;
    }
    if (linkCount > 0) statusMsg += `, added ${linkCount} profile connections`;
    updateStatus(statusMsg);
    saveGraphState();
}

// Search in corporate databases from context menu
window.searchInCorporateDB = async function(nodeId, searchType) {
    const node = nodes.get(nodeId);
    if (!node) return;
    
    const query = node.value || node.label;
    hideContextMenu();
    
    await handleCorporateSearch(query, searchType, nodeId);
};

// Show company selection panel for multiple results
function showCompanySelectionPanel(companies, query, searchType, parentNodeId) {
    const html = `
        <div class="modal" id="companySelectionModal" style="display: block; position: fixed; z-index: 15000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.9);">
            <div class="modal-content" style="background-color: #1a1a1a; margin: 5% auto; padding: 20px; width: 80%; max-width: 900px; max-height: 80vh; overflow-y: auto; border: 3px solid #00ff00; border-radius: 10px;">
                <h2 style="color: #00ff00; margin-bottom: 20px;">🏢 Select Company - Found ${companies.length} Results</h2>
                <p style="color: #fff; margin-bottom: 15px;">Multiple companies found for "<strong>${escapeHtml(query)}</strong>". Select which ones to add:</p>
                
                <div style="margin-bottom: 15px;">
                    <button onclick="selectAllCompanies(true)" style="background: #006600; color: white; border: none; padding: 8px 15px; margin-right: 10px; border-radius: 5px; cursor: pointer;">Select All</button>
                    <button onclick="selectAllCompanies(false)" style="background: #666600; color: white; border: none; padding: 8px 15px; border-radius: 5px; cursor: pointer;">Deselect All</button>
                </div>
                
                <div style="max-height: 50vh; overflow-y: auto; border: 1px solid #333; padding: 10px; background: #0a0a0a;">
                    ${companies.map((company, idx) => {
                        const hasAddress = company.address && company.address.trim() !== '';
                        const hasOfficers = company.officers && company.officers.length > 0;
                        
                        return `
                        <div style="margin-bottom: 20px; padding: 15px; background: #111; border: 2px solid #333; border-radius: 5px;">
                            <div style="display: flex; align-items: start; margin-bottom: 10px;">
                                <input type="checkbox" id="company-${idx}" data-company-index="${idx}" checked 
                                       style="margin-right: 10px; margin-top: 5px; width: 20px; height: 20px; cursor: pointer;">
                                <div style="flex: 1;">
                                    <h3 style="color: #00ff00; margin: 0 0 5px 0;">${escapeHtml(company.name)}</h3>
                                    <div style="color: #888; font-size: 12px;">
                                        ${company.jurisdiction ? `<span style="color: #0088ff;">[${company.jurisdiction}]</span> ` : ''}
                                        ${company.company_number ? `Company #: ${company.company_number} ` : ''}
                                        ${company.status ? `• Status: <span style="color: ${company.status.toLowerCase().includes('active') ? UI_COLORS.accent : UI_COLORS.warning};">${company.status}</span>` : ''}
                                    </div>
                                    ${company.incorporation_date ? `<div style="color: #888; font-size: 12px;">Incorporated: ${company.incorporation_date}</div>` : ''}
                                    ${company.source ? `<div style="color: #888; font-size: 12px;">Source: ${company.source}</div>` : ''}
                                    ${company.is_leak_data ? `<div style="color: #ff6600; font-size: 12px; font-weight: bold;">⚠️ LEAK DATA: ${company.leak_source}</div>` : ''}
                                    
                                    ${hasAddress ? `
                                        <div style="margin-top: 10px; padding: 10px; background: #0a0a0a; border-left: 3px solid #00CED1;">
                                            <strong style="color: #00CED1;">📍 Address:</strong>
                                            <div style="color: #ccc; margin-top: 5px;">${escapeHtml(company.address)}</div>
                                        </div>
                                    ` : ''}
                                    
                                    ${hasOfficers ? `
                                        <div style="margin-top: 10px; padding: 10px; background: #0a0a0a; border-left: 3px solid #FFD700;">
                                            <strong style="color: #FFD700;">👥 Officers (${company.officers.length}):</strong>
                                            <div style="margin-top: 5px;">
                                                ${company.officers.slice(0, 5).map(officer => `
                                                    <div style="color: #ccc; padding: 3px 0;">
                                                        • ${escapeHtml(officer.name)} 
                                                        <span style="color: #888;">- ${officer.position || 'Officer'}</span>
                                                        ${officer.start_date ? `<span style="color: #666; font-size: 11px;"> (from ${officer.start_date})</span>` : ''}
                                                    </div>
                                                `).join('')}
                                                ${company.officers.length > 5 ? `<div style="color: #666; font-style: italic;">... and ${company.officers.length - 5} more</div>` : ''}
                                            </div>
                                        </div>
                                    ` : ''}
                                    
                                    ${company.url ? `<div style="margin-top: 5px;"><a href="${company.url}" target="_blank" style="color: #0088ff; font-size: 12px;">View on ${company.source}</a></div>` : ''}
                                </div>
                            </div>
                        </div>
                        `;
                    }).join('')}
                </div>
                
                <div style="margin-top: 25px; text-align: center;">
                    <button onclick="processSelectedCompanies()" style="background: #00ff00; color: black; border: none; padding: 12px 25px; margin: 0 5px; border-radius: 5px; cursor: pointer; font-weight: bold;">ADD SELECTED COMPANIES</button>
                    <button onclick="closeCompanySelectionPanel()" style="background: #666; color: white; border: none; padding: 12px 25px; margin: 0 5px; border-radius: 5px; cursor: pointer;">CANCEL</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', html);
    
    // Store data for processing
    window.companySelectionData = {
        companies: companies,
        query: query,
        searchType: searchType,
        parentNodeId: parentNodeId
    };
}

// Handle select/deselect all companies
window.selectAllCompanies = function(select) {
    const checkboxes = document.querySelectorAll('#companySelectionModal input[type="checkbox"]');
    checkboxes.forEach(cb => cb.checked = select);
};

// Process selected companies
window.processSelectedCompanies = function() {
    const selectedIndices = [];
    const checkboxes = document.querySelectorAll('#companySelectionModal input[type="checkbox"]:checked');
    
    checkboxes.forEach(cb => {
        const index = parseInt(cb.getAttribute('data-company-index'));
        if (!isNaN(index)) {
            selectedIndices.push(index);
        }
    });
    
    // Close the modal
    closeCompanySelectionPanel();
    
    if (selectedIndices.length === 0) {
        updateStatus('No companies selected');
        return;
    }
    
    // Process the selected companies
    const data = window.companySelectionData;
    const selectedCompanies = selectedIndices.map(i => data.companies[i]);
    
    // Process each selected company
    processMultipleCompanies(selectedCompanies, data.parentNodeId);
    
    // Clean up
    delete window.companySelectionData;
};

// Close company selection panel
window.closeCompanySelectionPanel = function() {
    const modal = document.getElementById('companySelectionModal');
    if (modal) modal.remove();
    delete window.companySelectionData;
};

// Process multiple selected companies
async function processMultipleCompanies(companies, parentNodeId) {
    console.log('Processing selected companies:', companies);
    console.log('Parent node ID:', parentNodeId);
    
    // Save undo state
    saveUndoState("Add Corporate Search Results");
    
    const createdNodes = [];
    const createdEdges = [];
    const companyNodeIds = []; // Track company nodes to connect them
    
    for (const company of companies) {
        console.log('Processing company:', company);
        
        // Force create company node even if it might exist
        const companyData = {
            value: company.name,
            label: company.name,
            jurisdiction: company.jurisdiction,
            company_number: company.company_number,
            status: company.status,
            incorporation_date: company.incorporation_date,
            url: company.url,
            source: company.source
        };
        
        if (company.is_leak_data) {
            companyData.leak_source = company.leak_source;
            companyData.label += ` [${company.leak_source}]`;
        }
        
        console.log('About to create company node with data:', companyData);
        
        // Use standard node creation with duplicate checking
        const companyNodeResult = await addNode(companyData, 'company', parentNodeId);
        console.log('Company node result:', companyNodeResult);
        
        // Create edge from parent node if provided
        if (parentNodeId && companyNodeResult && companyNodeResult.nodeId) {
            const parentEdgeId = `edge_${parentNodeId}_${companyNodeResult.nodeId}_search`;
            if (!edges.get(parentEdgeId)) {
                edges.add({
                    id: parentEdgeId,
                    from: parentNodeId,
                    to: companyNodeResult.nodeId,
                    label: showConnectionLabels ? 'Search Result' : '',
                    color: { color: '#00FF00' },
                    width: 2,
                    arrows: { to: { enabled: true, scaleFactor: 0.8 } },
                    font: { color: '#00FF00', size: 10 },
                    smooth: false
                });
                createdEdges.push(parentEdgeId);
            }
        }
        
        // Check if user cancelled the similarity dialog
        if (!companyNodeResult) {
            console.log('User cancelled node creation or merge');
            continue; // Skip this company
        }
        
        if (companyNodeResult && companyNodeResult.nodeId) {
            console.log('Company node created/found with ID:', companyNodeResult.nodeId);
            // Always track the node, even if it already existed
            if (!companyNodeResult.isExisting) {
                createdNodes.push(companyNodeResult.nodeId);
            }
            companyNodeIds.push(companyNodeResult.nodeId); // Track for inter-company connections
            
            // Add address node if available
            if (company.address) {
                const addressNodeResult = await addNode({
                    value: company.address,
                    label: company.address,
                    source: company.source
                }, 'address', companyNodeResult.nodeId);
                
                if (addressNodeResult && addressNodeResult.nodeId) {
                    if (!addressNodeResult.isExisting) {
                        createdNodes.push(addressNodeResult.nodeId);
                    }
                    
                    // Always create edge between company and address (even if nodes existed)
                    const edgeId = `edge_${companyNodeResult.nodeId}_${addressNodeResult.nodeId}_registered`;
                    if (!edges.get(edgeId)) {
                        // Build company registration details
                        let registrationDetails = `${company.name}\n`;
                        registrationDetails += `Registered Address: ${company.address}\n`;
                        if (company.jurisdiction) {
                            registrationDetails += `Jurisdiction: ${company.jurisdiction}\n`;
                        }
                        if (company.incorporation_date) {
                            registrationDetails += `Incorporated: ${company.incorporation_date}\n`;
                        }
                        if (company.status) {
                            registrationDetails += `Status: ${company.status}\n`;
                        }
                        registrationDetails += `Source: OpenCorporates`;
                        
                        const edge = {
                            id: edgeId,
                            from: companyNodeResult.nodeId,
                            to: addressNodeResult.nodeId,
                            label: showConnectionLabels ? 'Registered At' : '',
                            title: registrationDetails, // This shows on hover
                            ...getConnectionStyle('DEFAULT')
                        };
                        edges.add(edge);
                        console.log('Added edge:', edge);
                        createdEdges.push(edgeId);
                    }
                }
            }
            
            // Add officer nodes if available
            if (company.officers && company.officers.length > 0) {
                for (const officer of company.officers) {
                    const officerNodeResult = await addNode({
                        value: officer.name,
                        label: officer.name,
                        position: officer.position,
                        start_date: officer.start_date,
                        end_date: officer.end_date,
                        source: company.source
                    }, 'name', companyNodeResult.nodeId);
                    
                    if (officerNodeResult && officerNodeResult.nodeId) {
                        if (!officerNodeResult.isExisting) {
                            createdNodes.push(officerNodeResult.nodeId);
                        }
                        
                        // Always create edge between company and officer (even if nodes existed)
                        const edgeId = `edge_${officerNodeResult.nodeId}_${companyNodeResult.nodeId}_officer`;
                        if (!edges.get(edgeId)) {
                            // Build detailed officer information for the edge tooltip
                            let officerDetails = `${officer.name}\n`;
                            officerDetails += `Position: ${officer.position || 'Officer'}\n`;
                            if (officer.start_date) {
                                officerDetails += `Start Date: ${officer.start_date}\n`;
                            }
                            if (officer.end_date) {
                                officerDetails += `End Date: ${officer.end_date}\n`;
                                officerDetails += `Status: Former/Resigned\n`;
                            } else {
                                officerDetails += `Status: Active\n`;
                            }
                            officerDetails += `Source: OpenCorporates`;
                            
                            edges.add({
                                id: edgeId,
                                from: officerNodeResult.nodeId,
                                to: companyNodeResult.nodeId,
                                label: showConnectionLabels ? (officer.position || 'Officer') : '',
                                title: officerDetails, // This shows on hover
                                ...getConnectionStyle('DEFAULT')
                            });
                            createdEdges.push(edgeId);
                        }
                    }
                }
            }
        }
    }
    
    // Connect all selected companies to each other (they're from the same search result)
    if (companyNodeIds.length > 1) {
        for (let i = 0; i < companyNodeIds.length; i++) {
            for (let j = i + 1; j < companyNodeIds.length; j++) {
                const edgeId = `edge_${companyNodeIds[i]}_${companyNodeIds[j]}_same_search`;
                if (!edges.get(edgeId)) {
                    edges.add({
                        id: edgeId,
                        from: companyNodeIds[i],
                        to: companyNodeIds[j],
                        label: showConnectionLabels ? 'Same Search Result' : '',
                        ...getConnectionStyle('DEFAULT'),
                        smooth: false
                    });
                    createdEdges.push(edgeId);
                }
            }
        }
    }
    
    // Get actual node count after processing
    const totalNodesAfter = nodes.get().length;
    console.log('Total nodes in graph after processing:', totalNodesAfter);
    console.log('Created nodes:', createdNodes);
    console.log('Company node IDs:', companyNodeIds);
    
    // Focus on the created nodes
    if (companyNodeIds.length > 0) {
        network.fit({
            nodes: companyNodeIds,
            animation: {
                duration: 1000,
                easingFunction: 'easeInOutQuad'
            }
        });
    }
    
    updateStatus(`Added ${companies.length} companies with ${createdNodes.length} new nodes and ${createdEdges.length} connections (Total nodes: ${totalNodesAfter})`);
    saveGraphState();
}

// Handle corporate searches (OpenCorporates, OCCRP Aleph, etc.)
async function handleCorporateSearch(query, type, parentNodeId = null) {
    updateStatus(`🏢 Searching corporate databases for ${query}...`);
    
    try {
        let endpoint = '';
        let requestBody = { query };
        
        // Determine which endpoint to use
        if (type === 'opencorporates') {
            endpoint = '/api/opencorporates/search';
            requestBody.search_type = 'company'; // Default to company search
        } else if (type === 'opencorporates_officer') {
            endpoint = '/api/opencorporates/search';
            requestBody.search_type = 'officer'; // Officer search
        } else if (type === 'aleph') {
            endpoint = '/api/aleph/search';
            requestBody.max_results = 50;
        } else if (type === 'corporate') {
            endpoint = '/api/corporate/unified';
            requestBody.sources = ['opencorporates', 'aleph'];
        }
        
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.success) {
            if (data.error) {
                updateStatus(`❌ ${data.error}`);
            } else {
                updateStatus(`No corporate results found for ${query}`);
            }
            return false;
        }
        
        if (!data.results || data.results.length === 0) {
            updateStatus(`No corporate results found for ${query}`);
            return false;
        }
        
        // If multiple companies found, show selection panel
        const companyResults = data.results.filter(r => r.type === 'company');
        if (companyResults.length > 1) {
            showCompanySelectionPanel(companyResults, query, type, parentNodeId);
            return true;
        }
        
        // Process the results
        const createdNodes = [];
        const createdEdges = [];
        
        for (const result of data.results) {
            // Create nodes based on result type
            if (result.type === 'company') {
                // Create company node
                const companyData = {
                    value: result.name,
                    label: result.name,
                    jurisdiction: result.jurisdiction,
                    company_number: result.company_number,
                    status: result.status,
                    incorporation_date: result.incorporation_date,
                    url: result.url,
                    source: result.source
                };
                
                if (result.is_leak_data) {
                    companyData.leak_source = result.leak_source;
                    companyData.label += ` [${result.leak_source}]`;
                }
                
                const companyNodeResult = await addNode(companyData, 'company', parentNodeId);
                if (companyNodeResult && companyNodeResult.nodeId) {
                    createdNodes.push(companyNodeResult.nodeId);
                    
                    // Add address node if available
                    if (result.address) {
                        const addressNodeResult = await addNode({
                            value: result.address,
                            label: result.address,
                            source: result.source
                        }, 'address');
                        
                        if (addressNodeResult && addressNodeResult.nodeId) {
                            createdNodes.push(addressNodeResult.nodeId);
                            
                            // Create edge between company and address
                            const edgeId = `edge_${companyNodeResult.nodeId}_${addressNodeResult.nodeId}_registered`;
                            if (!edges.get(edgeId)) {
                                edges.add({
                                    id: edgeId,
                                    from: companyNodeResult.nodeId,
                                    to: addressNodeResult.nodeId,
                                    label: showConnectionLabels ? 'Registered At' : '',
                                    ...getConnectionStyle('DEFAULT')
                                });
                                createdEdges.push(edgeId);
                            }
                        }
                    }
                    
                    // Add officer nodes if available
                    if (result.officers && result.officers.length > 0) {
                        for (const officer of result.officers) {
                            const officerNodeResult = await addNode({
                                value: officer.name,
                                label: officer.name,
                                position: officer.position,
                                start_date: officer.start_date,
                                end_date: officer.end_date,
                                source: result.source
                            }, 'name');
                            
                            if (officerNodeResult && officerNodeResult.nodeId) {
                                createdNodes.push(officerNodeResult.nodeId);
                                
                                // Create edge between company and officer
                                const edgeId = `edge_${officerNodeResult.nodeId}_${companyNodeResult.nodeId}_officer`;
                                if (!edges.get(edgeId)) {
                                    edges.add({
                                        id: edgeId,
                                        from: officerNodeResult.nodeId,
                                        to: companyNodeResult.nodeId,
                                        label: showConnectionLabels ? (officer.position || 'Officer') : '',
                                        ...getConnectionStyle('DEFAULT')
                                    });
                                    createdEdges.push(edgeId);
                                }
                            }
                        }
                    }
                }
                
            } else if (result.type === 'person') {
                // Create person node
                const personData = {
                    value: result.name,
                    label: result.name,
                    source: result.source
                };
                
                if (result.position) personData.position = result.position;
                if (result.company_name) personData.company = result.company_name;
                if (result.birth_date) personData.birth_date = result.birth_date;
                if (result.url) personData.url = result.url;
                
                const personNodeResult = await addNode(personData, 'name', parentNodeId);
                if (personNodeResult && personNodeResult.nodeId) {
                    createdNodes.push(personNodeResult.nodeId);
                    
                    // If there's an associated company, try to find or create it
                    if (result.company_name) {
                        const companyNodeResult = await addNode({
                            value: result.company_name,
                            label: result.company_name,
                            company_number: result.company_number,
                            jurisdiction: result.jurisdiction,
                            source: result.source
                        }, 'company');
                        
                        if (companyNodeResult && companyNodeResult.nodeId) {
                            createdNodes.push(companyNodeResult.nodeId);
                            
                            // Create edge between person and company
                            const edgeId = `edge_${personNodeResult.nodeId}_${companyNodeResult.nodeId}_position`;
                            if (!edges.get(edgeId)) {
                                // Build detailed officer information for the edge tooltip
                                let officerDetails = `${result.name}\n`;
                                officerDetails += `Position: ${result.position || 'Officer/Director'}\n`;
                                if (result.start_date) {
                                    officerDetails += `Start Date: ${result.start_date}\n`;
                                }
                                if (result.end_date) {
                                    officerDetails += `End Date: ${result.end_date}\n`;
                                    officerDetails += `Status: Former/Resigned\n`;
                                } else {
                                    officerDetails += `Status: Active\n`;
                                }
                                officerDetails += `Company: ${result.company_name}\n`;
                                if (result.jurisdiction) {
                                    officerDetails += `Jurisdiction: ${result.jurisdiction}\n`;
                                }
                                officerDetails += `Source: OpenCorporates (Officer Search)`;
                                
                                edges.add({
                                    id: edgeId,
                                    from: personNodeResult.nodeId,
                                    to: companyNodeResult.nodeId,
                                    label: showConnectionLabels ? (result.position || 'Associated') : '',
                                    title: officerDetails, // This shows on hover
                                    ...getConnectionStyle('DEFAULT')
                                });
                                createdEdges.push(edgeId);
                            }
                        }
                    }
                }
                
            } else if (result.type === 'address') {
                // Create address node
                const addressNodeResult = await addNode({
                    value: result.value || result.title,
                    label: result.value || result.title,
                    source: result.source
                }, 'address', parentNodeId);
                
                if (addressNodeResult && addressNodeResult.nodeId) {
                    createdNodes.push(addressNodeResult.nodeId);
                }
                
            } else if (result.type === 'document') {
                // Create document/other node
                // Use name field if available, fallback to title
                const displayName = result.name || result.title || 'Unknown Entity';
                const docNodeResult = await addNode({
                    value: displayName,
                    label: displayName,
                    snippet: result.snippet,
                    url: result.url,
                    source: result.source,
                    schema: result.schema || 'document'
                }, 'unknown', parentNodeId);
                
                if (docNodeResult && docNodeResult.nodeId) {
                    createdNodes.push(docNodeResult.nodeId);
                }
            }
        }
        
        // Update status
        const sourceName = type === 'opencorporates' ? 'OpenCorporates' : 
                          type === 'aleph' ? 'OCCRP Aleph' : 
                          'Corporate databases';
        updateStatus(`Found ${data.results.length} results from ${sourceName}. Created ${createdNodes.length} nodes and ${createdEdges.length} connections.`);
        
        // Save state
        saveGraphState();
        
        return true;
        
    } catch (error) {
        console.error('Corporate search error:', error);
        updateStatus(`❌ Error searching corporate databases: ${error.message}`);
        return false;
    }
}

// Perform a search
async function performSearch(query, type = null, parentNodeId = null) {
    if (!query) return false;

    // Handle web search engines
    if (type === 'web-search' || type === 'brave' || type === 'duckduckgo' || type === 'exa' || type === 'firecrawl') {
        return await handleWebSearch(query, type, parentNodeId);
    }

    // Handle OSINT searches separately
    if (type === 'osint') {
        return await handleOSINTSearch(query, parentNodeId);
    }

    // Handle corporate searches
    if (type === 'opencorporates' || type === 'aleph' || type === 'corporate') {
        return await handleCorporateSearch(query, type, parentNodeId);
    }
    
    // Check cache first
    const cacheKey = `${query}_${type || 'auto'}`;
    if (searchCache.has(cacheKey)) {
        const cachedData = searchCache.get(cacheKey);
        updateStatus(`Using cached results for ${query}`);
        
        // If no parent node, don't create a search node - just process results without parent
        // This means initial searches won't have a parent node
        
        // Process cached results
        if (cachedData.results && cachedData.results.length > 0) {
            processCachedResults(cachedData.results, parentNodeId);
            updateStatus(`Found ${cachedData.results.length} breaches (cached)`);
            return true;
        } else {
            updateStatus('No results found (cached)');
            return false;
        }
    }
    
    // Check if this is a name, email, or phone number that should also be searched in WHOIS
    const shouldSearchWhois = isWhoisCandidate(query, type);
    
    // Check if this is a username that should be searched in OSINT
    const shouldSearchOSINT = (type === 'username' || (!type && !query.includes('@') && !/^\+?\d[\d\s\-\(\)\.]{6,}$/.test(query.trim())));
    
    // Start WHOIS and/or OSINT search in parallel if applicable (only for initial searches, not expansions)
    let whoisPromise = null;
    let osintPromise = null;
    
    if (!parentNodeId) {
        if (shouldSearchWhois && shouldSearchOSINT) {
            updateStatus(`🔍 Searching DeHashed, WHOIS, and OSINT for ${query}...`);
            whoisPromise = performWhoisSearch(query, type);
            osintPromise = handleOSINTSearch(query, parentNodeId);
        } else if (shouldSearchWhois) {
            updateStatus(`🔍 Searching DeHashed and WHOIS for ${query}...`);
            whoisPromise = performWhoisSearch(query, type);
        } else if (shouldSearchOSINT) {
            updateStatus(`🔍 Searching DeHashed and OSINT for ${query}...`);
            osintPromise = handleOSINTSearch(query, parentNodeId);
        } else {
            updateStatus(`🔍 Searching DeHashed for ${query}...`);
        }
    } else {
        updateStatus(`🔍 Searching DeHashed for ${query}...`);
    }
    
    // Add visual feedback in the search input
    const searchBtn = document.getElementById('searchBtn');
    const originalText = searchBtn.textContent;
    searchBtn.textContent = 'Searching...';
    searchBtn.disabled = true;
    
    try {
        const response = await fetch('/api/search', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ query, type })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.error) {
            updateStatus(`❌ Error: ${data.error}`);
            searchBtn.textContent = originalText;
            searchBtn.disabled = false;
            return false;
        }
        
        // Cache the results and save to storage
        searchCache.set(cacheKey, data);
        saveCacheToStorage();
        
        // If no parent node, don't create a search node - just process results without parent
        // This means initial searches won't have a parent node
        
        // Process the results
        if (data.results && data.results.length > 0) {
            // Show progress while adding nodes
            let processedCount = 0;
            const totalBreaches = data.results.length;
            
            data.results.forEach((breach, index) => {
                const breachInfo = breach.database_name || 'Unknown Database';
                const breachNodes = []; // Track all nodes from this breach
                
                // Update progress
                processedCount++;
                updateStatus(`🔄 Processing breach ${processedCount}/${totalBreaches}...`);
                
                // Add nodes for ALL data types found in the breach
                if (breach.email && breach.email.length > 0) {
                    breach.email.forEach(email => {
                        const nodeId = addNodeSimple({ 
                            value: email, 
                            label: email,
                            breach: breachInfo,
                            breachData: breach
                        }, 'email', parentNodeId);
                        if (nodeId) breachNodes.push(nodeId);
                    });
                }
                
                if (breach.username && breach.username.length > 0) {
                    breach.username.forEach(username => {
                        const nodeId = addNodeSimple({ 
                            value: username, 
                            label: username,
                            breach: breachInfo,
                            breachData: breach
                        }, 'username', parentNodeId);
                        breachNodes.push(nodeId);
                    });
                }
                
                if (breach.ip_address && breach.ip_address.length > 0) {
                    breach.ip_address.forEach(ip => {
                        const nodeId = addNodeSimple({ 
                            value: ip, 
                            label: ip,
                            breach: breachInfo,
                            breachData: breach
                        }, 'ip_address', parentNodeId);
                        breachNodes.push(nodeId);
                    });
                }
                
                if (breach.password && breach.password.length > 0) {
                    breach.password.forEach(password => {
                        const nodeId = addNodeSimple({ 
                            value: password, 
                            label: password,
                            breach: breachInfo,
                            breachData: breach
                        }, 'password', parentNodeId);
                        breachNodes.push(nodeId);
                    });
                }
                
                if (includeHashedPasswords && breach.hashed_password && breach.hashed_password.length > 0) {
                    breach.hashed_password.forEach(hash => {
                        const nodeId = addNodeSimple({ 
                            value: hash, 
                            label: truncateLabel(hash),
                            breach: breachInfo,
                            breachData: breach
                        }, 'hashed_password', parentNodeId);
                        breachNodes.push(nodeId);
                    });
                }
                
                if (breach.phone && breach.phone.length > 0) {
                    breach.phone.forEach(phone => {
                        const nodeId = addNodeSimple({ 
                            value: phone, 
                            label: phone,
                            breach: breachInfo,
                            breachData: breach
                        }, 'phone', parentNodeId);
                        breachNodes.push(nodeId);
                    });
                }
                
                if (breach.name && breach.name.length > 0) {
                    breach.name.forEach(name => {
                        const nodeId = addNodeSimple({ 
                            value: name, 
                            label: name,
                            breach: breachInfo,
                            breachData: breach
                        }, 'name', parentNodeId);
                        breachNodes.push(nodeId);
                    });
                }
                
                if (breach.address && breach.address.length > 0) {
                    breach.address.forEach(address => {
                        const nodeId = addNodeSimple({ 
                            value: address, 
                            label: truncateLabel(address),
                            breach: breachInfo,
                            breachData: breach
                        }, 'address', parentNodeId);
                        breachNodes.push(nodeId);
                    });
                }
                
                if (breach.domain && breach.domain.length > 0) {
                    breach.domain.forEach(domain => {
                        const nodeId = addNodeSimple({ 
                            value: domain, 
                            label: domain,
                            breach: breachInfo,
                            breachData: breach
                        }, 'domain', parentNodeId);
                        breachNodes.push(nodeId);
                    });
                }
                
                if (breach.vin && breach.vin.length > 0) {
                    breach.vin.forEach(vin => {
                        const nodeId = addNodeSimple({ 
                            value: vin, 
                            label: vin,
                            breach: breachInfo,
                            breachData: breach
                        }, 'vin', parentNodeId);
                        breachNodes.push(nodeId);
                    });
                }
                
                // Create connections based on shared values within this breach
                createValueBasedConnections(breach);
            });
            
            updateStatus(`✅ Found ${data.results.length} breaches with ${data.total || data.results.length} total records`);
            
            // Process WHOIS results if we started that search
            if (whoisPromise) {
                whoisPromise.then(whoisData => {
                    if (whoisData && whoisData.results && whoisData.results.length > 0) {
                        updateStatus(`🌐 Found ${whoisData.results.length} WHOIS records`);
                        
                        // Show WHOIS results dialog for user approval
                        showWhoisResultsDialog(whoisData, query, parentNodeId);
                    }
                }).catch(error => {
                    console.error('WHOIS search error:', error);
                });
            }
            
            // Process OSINT results if we started that search
            if (osintPromise) {
                osintPromise.then(result => {
                    console.log('OSINT search completed');
                }).catch(error => {
                    console.error('OSINT search error:', error);
                });
            }
            
            searchBtn.textContent = originalText;
            searchBtn.disabled = false;
            return true;
        } else {
            updateStatus('⚠️ No results found in DeHashed');
            
            // Check WHOIS results if we started that search
            if (whoisPromise) {
                whoisPromise.then(whoisData => {
                    if (whoisData && whoisData.results && whoisData.results.length > 0) {
                        updateStatus(`🌐 Found ${whoisData.results.length} WHOIS records`);
                        
                        // Show WHOIS results dialog for user approval
                        showWhoisResultsDialog(whoisData, query, parentNodeId);
                    }
                }).catch(error => {
                    console.error('WHOIS search error:', error);
                });
            }
            
            // Check OSINT results if we started that search
            if (osintPromise) {
                osintPromise.then(result => {
                    console.log('OSINT search completed (no DeHashed results)');
                }).catch(error => {
                    console.error('OSINT search error:', error);
                });
            }
            
            searchBtn.textContent = originalText;
            searchBtn.disabled = false;
            
            // Add visual feedback for no results
            const statusElement = document.getElementById('status');
            statusElement.style.color = '#ff6600';
            setTimeout(() => {
                statusElement.style.color = '#666666';
            }, 3000);
            return false;
        }
        
    } catch (error) {
        console.error('Search error:', error);
        updateStatus(`❌ Error: ${error.message}`);
        searchBtn.textContent = originalText;
        searchBtn.disabled = false;
        return false;
    }
}

// Process cached results
function processCachedResults(results, parentNodeId) {
    results.forEach(breach => {
        const breachInfo = breach.database_name || 'Unknown Database';
        const breachNodes = []; // Track all nodes from this breach
        
        // Add nodes for ALL data types - same as in performSearch
        if (breach.email && breach.email.length > 0) {
            breach.email.forEach(email => {
                const nodeId = addNodeSimple({ 
                    value: email, 
                    label: email,
                    breach: breachInfo,
                    breachData: breach
                }, 'email', parentNodeId);
                if (nodeId) breachNodes.push(nodeId);
            });
        }
        
        if (breach.username && breach.username.length > 0) {
            breach.username.forEach(username => {
                const nodeId = addNodeSimple({ 
                    value: username, 
                    label: username,
                    breach: breachInfo,
                    breachData: breach
                }, 'username', parentNodeId);
                breachNodes.push(nodeId);
            });
        }
        
        if (breach.ip_address && breach.ip_address.length > 0) {
            breach.ip_address.forEach(ip => {
                const nodeId = addNodeSimple({ 
                    value: ip, 
                    label: ip,
                    breach: breachInfo,
                    breachData: breach
                }, 'ip_address', parentNodeId);
                breachNodes.push(nodeId);
            });
        }
        
        if (breach.password && breach.password.length > 0) {
            breach.password.forEach(password => {
                const nodeId = addNodeSimple({ 
                    value: password, 
                    label: password,
                    breach: breachInfo,
                    breachData: breach
                }, 'password', parentNodeId);
                breachNodes.push(nodeId);
            });
        }
        
        if (includeHashedPasswords && breach.hashed_password && breach.hashed_password.length > 0) {
            breach.hashed_password.forEach(hash => {
                const nodeId = addNodeSimple({ 
                    value: hash, 
                    label: truncateLabel(hash),
                    breach: breachInfo,
                    breachData: breach
                }, 'hashed_password', parentNodeId);
                breachNodes.push(nodeId);
            });
        }
        
        if (breach.phone && breach.phone.length > 0) {
            breach.phone.forEach(phone => {
                const nodeId = addNodeSimple({ 
                    value: phone, 
                    label: phone,
                    breach: breachInfo,
                    breachData: breach
                }, 'phone', parentNodeId);
                breachNodes.push(nodeId);
            });
        }
        
        if (breach.name && breach.name.length > 0) {
            breach.name.forEach(name => {
                const nodeId = addNodeSimple({ 
                    value: name, 
                    label: name,
                    breach: breachInfo,
                    breachData: breach
                }, 'name', parentNodeId);
                breachNodes.push(nodeId);
            });
        }
        
        if (breach.address && breach.address.length > 0) {
            breach.address.forEach(address => {
                const nodeId = addNodeSimple({ 
                    value: address, 
                    label: truncateLabel(address),
                    breach: breachInfo,
                    breachData: breach
                }, 'address', parentNodeId);
                breachNodes.push(nodeId);
            });
        }
        
        if (breach.domain && breach.domain.length > 0) {
            breach.domain.forEach(domain => {
                const nodeId = addNodeSimple({ 
                    value: domain, 
                    label: domain,
                    breach: breachInfo,
                    breachData: breach
                }, 'domain', parentNodeId);
                breachNodes.push(nodeId);
            });
        }
        
        if (breach.vin && breach.vin.length > 0) {
            breach.vin.forEach(vin => {
                const nodeId = addNodeSimple({ 
                    value: vin, 
                    label: vin,
                    breach: breachInfo,
                    breachData: breach
                }, 'vin', parentNodeId);
                breachNodes.push(nodeId);
            });
        }
        
        // Create connections based on shared values within this breach
        createValueBasedConnections(breach);
    });
}

// Update status bar
function updateStatus(message = null) {
    if (message) {
        document.getElementById('status').textContent = message;
    }
    document.getElementById('node-count').textContent = `Nodes: ${nodes.get().length}`;
    document.getElementById('edge-count').textContent = `Edges: ${edges.get().length}`;
    
    // Show selected nodes count
    if (network) {
        const selectedNodes = network.getSelectedNodes();
        if (selectedNodes.length > 1 && selectedNodes.includes(node.id)) {
            document.getElementById('status').textContent += ` | Selected: ${selectedNodes.length}`;
        }
    }
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return String(text).replace(/[&<>"']/g, m => map[m]);
}

// Helper function to highlight search terms in snippets
function highlightSearchTerm(text, searchTerm) {
    if (!text || !searchTerm) return escapeHtml(text);
    
    // Remove quotes from search term if present
    const cleanTerm = searchTerm.replace(/^"|"$/g, '');
    
    // Escape the text first
    const escapedText = escapeHtml(text);
    
    // Create a regex to find the search term (case insensitive)
    const words = cleanTerm.split(/\s+/).filter(word => word.length > 0);
    
    let highlightedText = escapedText;
    words.forEach(word => {
        // Escape regex special characters in the word
        const escapedWord = word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const regex = new RegExp(`(${escapedWord})`, 'gi');
        highlightedText = highlightedText.replace(regex, '<span style="background-color: #FFFF00; color: #000; font-weight: bold;">$1</span>');
    });
    
    return highlightedText;
}

// EMERGENCY RESET - CLEAR SAVED STATE AND RESTORE ORIGINAL NODES
window.emergencyReset = function() {
    // Clear all saved state
    localStorage.clear();
    
    // Clear anchored nodes
    anchoredNodes.clear();
    
    const allNodes = nodes.get();
    const updates = [];
    
    allNodes.forEach(node => {
        updates.push({
            id: node.id,
            color: {
                background: '#000000',
                border: getNodeColor(node.type),
                highlight: {
                    background: '#1a1a1a',
                    border: getNodeColor(node.type)
                }
            },
            font: {
                color: '#666666',
                size: 12,
                face: 'monospace'
            },
            borderWidth: 2,
            borderWidthSelected: 3,
            hidden: false
        });
    });
    
    nodes.update(updates);
    
    // Clear server cache too
    fetch('/api/cache/clear', { method: 'POST' }).catch(() => {});
    
    updateStatus('EMERGENCY RESET - ALL STATE CLEARED, ORIGINAL SIZES RESTORED');
}

// Fix stuck focus mode
// Recover any "lost" nodes by ensuring all are visible
function recoverLostNodes() {
    const allNodes = nodes.get();
    let recoveredCount = 0;
    
    allNodes.forEach(node => {
        const pos = network.getPositions([node.id])[node.id];
        
        // Check if position is invalid or node might be hidden
        if (!pos || isNaN(pos.x) || isNaN(pos.y) || 
            Math.abs(pos.x) > 10000 || Math.abs(pos.y) > 10000) {
            
            console.log(`[Recovery] Recovering lost node: ${node.id}`);
            
            // Get viewport center
            const view = network.getViewPosition();
            
            // Place node at a random position near viewport center
            const offsetX = (Math.random() - 0.5) * 200;
            const offsetY = (Math.random() - 0.5) * 200;
            
            nodes.update({
                id: node.id,
                x: view.x + offsetX,
                y: view.y + offsetY,
                hidden: false,
                physics: false,
                fixed: {
                    x: false,
                    y: false
                }
            });
            
            recoveredCount++;
        }
    });
    
    if (recoveredCount > 0) {
        network.redraw();
        updateStatus(`Recovered ${recoveredCount} lost nodes`);
    }
    
    return recoveredCount;
}

function fixStuckFocus() {
    focusedNode = null;
    originalNodeColors.clear();
    
    // FORCE RESET ALL NODES TO ABSOLUTE NORMAL SIZE
    const allNodes = nodes.get();
    const updates = [];
    
    allNodes.forEach(node => {
        // Special handling for query nodes - KEEP THEM RED!
        if (node.id && node.id.startsWith('query_')) {
            updates.push({
                id: node.id,
                color: {
                    background: '#000000',
                    border: '#ff0000',  // RED border for query nodes
                    highlight: {
                        background: '#330000',
                        border: '#ff0000'  // RED highlight for query nodes
                    }
                },
                font: {
                    color: '#ff0000',  // RED text for query nodes
                    size: 12,
                    face: 'monospace',
                    bold: true
                },
                borderWidth: 3,
                borderWidthSelected: 4,
                hidden: false
            });
        } else {
            // ALL OTHER NODES - FORCE TO NORMAL SIZE
            const borderColor = getNodeColor(node.type);
            const isAnchored = anchoredNodes.has(node.id);
            
            updates.push({
                id: node.id,
                color: {
                    background: '#000000',  // Always black background
                    border: borderColor,
                    highlight: {
                        background: '#1a1a1a',
                        border: borderColor
                    }
                },
                font: {
                    color: isAnchored ? '#FFFFFF' : '#666666',  // White for anchored, gray for others
                    size: isAnchored ? 18 : 12,  // 18 for anchored, 12 for normal
                    face: 'monospace',
                    bold: isAnchored  // Only anchored are bold
                },
                borderWidth: 2,  // NORMAL border width
                borderWidthSelected: 3,  // NORMAL selected width
                hidden: false
            });
        }
    });
    
    nodes.update(updates);
    updateStatus('ALL NODES RESET TO NORMAL SIZE');
}

// Remove self-referencing edges (loops)
function removeSelfLoops() {
    const allEdges = edges.get();
    const loopEdges = allEdges.filter(edge => edge.from === edge.to);
    
    if (loopEdges.length > 0) {
        console.log(`Removing ${loopEdges.length} self-referencing edges`);
        edges.remove(loopEdges.map(edge => edge.id));
        saveGraphState();
    }
}

// Handle search button click
document.getElementById('searchBtn').addEventListener('click', () => {
    const query = document.getElementById('searchInput').value;
    const type = document.getElementById('searchType').value || null;
    
    if (query) {
        performSearch(query, type);
    }
});

// Handle enter key in search input
document.getElementById('searchInput').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        document.getElementById('searchBtn').click();
    }
});

// Show context menu
// Function to create a new node from the context menu
function createNodeFromContextMenu(type, position) {
    const value = prompt(`Enter value for new ${type} node:`);
    if (value) {
        const nodeId = `node_${nodeIdCounter++}`;
        const color = getNodeColor(type);
        const valueKey = `${type}_${value.toLowerCase().trim()}`;

        // Check for duplicates before creating
        if (valueToNodeMap.has(valueKey)) {
            alert("A node with this type and value already exists.");
            const existingNodeId = valueToNodeMap.get(valueKey);
            network.focus(existingNodeId, { scale: 1.5, animation: true });
            hideContextMenu();
            return;
        }

        const node = {
            id: nodeId,
            label: value,
            title: `${type.toUpperCase()}: ${value}`,
            color: {
                background: '#000000',
                border: color,
                highlight: {
                    background: '#1a1a1a',
                    border: color
                }
            },
            data: { value: value, label: value, source: 'Manual' },
            type: type,
            x: position.x,
            y: position.y,
            physics: false,
            font: {
                color: '#666666',
                multi: 'html',
                size: 12
            },
            shadow: false
        };
        
        nodes.add(node);
        valueToNodeMap.set(valueKey, nodeId);
        updateStatus(`Created new ${type} node.`);
        saveGraphState();
    }
    hideContextMenu();
}

// Hide context menu
function hideContextMenu() {
    const menu = document.getElementById('context-menu');
    if (menu) menu.remove();
}

function showContextMenu(event, node, position = null) {
    // Remove any existing context menu
    const existingMenu = document.getElementById('context-menu');
    if (existingMenu) existingMenu.remove();
    
    const menu = document.createElement('div');
    menu.id = 'context-menu';
    menu.style.cssText = `
        position: absolute;
        left: ${event.pageX}px;
        top: ${event.pageY}px;
        background: #000;
        border: 1px solid #0f0;
        padding: 5px;
        z-index: 1000;
        font-family: monospace;
        font-size: 12px;
        max-height: 80vh;
        overflow-y: auto;
    `;
    
    if (node) {
        const selectedNodes = network.getSelectedNodes();
        if (selectedNodes.length > 1 && selectedNodes.includes(node.id)) {
            // Multiple nodes selected
            menu.innerHTML = `
                <div class="menu-item" onclick="deleteSelectedNodes([${selectedNodes.map(id => `'${id}'`).join(',')}])">Delete ${selectedNodes.length} Selected Nodes</div>
                <div class="menu-item" onclick="connectSelectedNodes([${selectedNodes.map(id => `'${id}'`).join(',')}])">Connect Selected Nodes</div>
                <div class="menu-item" onclick="mergeSelectedNodes([${selectedNodes.map(id => `'${id}'`).join(',')}])">Merge ${selectedNodes.length} Selected Nodes</div>
                <div class="menu-item" onclick="createClusterFromSelection()">Create Cluster from ${selectedNodes.length} Nodes</div>
            `;
        } else {
            // Single node context menu
            const isAnchored = anchoredNodes.has(node.id);
            
            // Check if this is an image node
            if (node.shape === 'image' || (node.data && node.data.type === 'image')) {
                // Image node menu
                menu.innerHTML = `
                    <div class="menu-item" onclick="analyzeImageWithClaude('${node.id}')">Analyze Image with Claude</div>
                    <div class="menu-item" onclick="toggleAnchorNode('${node.id}')">${isAnchored ? 'Unanchor' : 'Anchor'} Node</div>
                    <div class="menu-item" onclick="centerNode('${node.id}')">Center Node</div>
                    <div class="menu-item" onclick="startConnectionMode('${node.id}')">Add Connection</div>
                    <div class="menu-item" onclick="deleteNode('${node.id}')">Delete Node</div>
                    <div class="menu-item" onclick="deleteConnections('${node.id}')">Delete Connections</div>
                `;
            } else if (node.type === 'document') {
                // Document node menu
                menu.innerHTML = `
                    <div class="menu-item" onclick="extractEntitiesFromDocument('${node.id}')">🧠 Extract Entities with AI</div>
                    <div class="menu-item" onmousedown="event.stopPropagation();" onclick="showChangeTypeMenu('${node.id}', event);">Change Type</div>
                    <div class="menu-item" onclick="toggleAnchorNode('${node.id}')">${isAnchored ? 'Unanchor' : 'Anchor'} Node</div>
                    <div class="menu-item" onclick="centerNode('${node.id}')">Center Node</div>
                    <div class="menu-item" onclick="startConnectionMode('${node.id}')">Add Connection</div>
                    <div class="menu-item" onclick="startHypotheticalLinkMode('${node.id}')">Add Hypothetical Link</div>
                    <div class="menu-item" onclick="duplicateNode('${node.id}')">Duplicate Node</div>
                    <div class="menu-item" onclick="deleteNode('${node.id}')">Delete Node</div>
                    <div class="menu-item" onclick="deleteConnections('${node.id}')">Delete Connections</div>
                `;
            } else {
                // Regular node menu
                menu.innerHTML = `
                    <div class="menu-item" onmousedown="event.stopPropagation();" onclick="showChangeTypeMenu('${node.id}', event);">Change Type</div>
                    <div class="menu-item" onclick="toggleAnchorNode('${node.id}')">${isAnchored ? 'Unanchor' : 'Anchor'} Node</div>
                    <div class="menu-item" onclick="centerNode('${node.id}')">Center Node</div>
                    <div class="menu-item" onclick="startConnectionMode('${node.id}')">Add Connection</div>
                    <div class="menu-item" onclick="startHypotheticalLinkMode('${node.id}')">Add Hypothetical Link</div>
                    <div class="menu-item" onclick="duplicateNode('${node.id}')">Duplicate Node</div>
                    <div class="menu-item" onclick="deleteNode('${node.id}')">Delete Node</div>
                    <div class="menu-item" onclick="deleteConnections('${node.id}')">Delete Connections</div>
                `;
                
                // Add corporate search options for appropriate node types
                if (node.type === 'company' || node.type === 'name') {
                    menu.innerHTML += `
                        <div style="border-top: 1px solid #0f0; margin: 5px 0;"></div>
                        <div class="menu-item" onclick="searchInCorporateDB('${node.id}', 'opencorporates')">Search in OpenCorporates</div>
                        <div class="menu-item" onclick="searchInCorporateDB('${node.id}', 'aleph')">Search in OCCRP Aleph</div>
                        <div class="menu-item" onclick="searchInCorporateDB('${node.id}', 'corporate')">Search in All Corporate DBs</div>
                    `;
                }
            }
            
            // Add cluster-specific menu items
            addClusterContextMenuItems(menu, node.id);
        }
    } else if (position) {
        // Canvas context menu
        const header = document.createElement('div');
        header.style.cssText = "padding: 3px 5px; font-weight: bold; border-bottom: 1px solid #333;";
        header.textContent = "Create Node:";
        menu.appendChild(header);

        const nodeTypes = [
            { type: 'name', label: 'Person Name' },
            { type: 'company', label: 'Company' },
            { type: 'email', label: 'Email' },
            { type: 'phone', label: 'Phone' },
            { type: 'domain', label: 'Domain' },
            { type: 'url', label: 'URL' },
            { type: 'address', label: 'Address' },
            { type: 'username', label: 'Username' },
            { type: 'password', label: 'Password' },
            { type: 'ip_address', label: 'IP Address' },
        ];

        nodeTypes.forEach(nodeType => {
            const menuItem = document.createElement('div');
            menuItem.className = 'menu-item';
            menuItem.textContent = nodeType.label;
            menuItem.onclick = () => createNodeFromContextMenu(nodeType.type, position);
            menu.appendChild(menuItem);
        });
    }
    
    document.body.appendChild(menu);
    
    // Remove menu on click outside
    setTimeout(() => {
        document.addEventListener('click', function removeMenu(e) {
            const menu = document.getElementById('context-menu');
            // Check if the click is outside the menu
            if (menu && !menu.contains(e.target)) {
                menu.remove();
                document.removeEventListener('click', removeMenu);
            }
        });
    }, 100);
}

// Show URL options menu on double-click
function showUrlOptionsMenu(node, params) {
    console.log('showUrlOptionsMenu called with node:', node);
    
    // Remove any existing menu
    const existingMenu = document.getElementById('url-options-menu');
    if (existingMenu) {
        existingMenu.remove();
    }
    
    // Create menu container
    const menu = document.createElement('div');
    menu.id = 'url-options-menu';
    menu.className = 'context-menu';
    // Get position from params.pointer.DOM or fall back to event properties
    const x = params.pointer?.DOM?.x || params.event?.pageX || params.event?.clientX || 100;
    const y = params.pointer?.DOM?.y || params.event?.pageY || params.event?.clientY || 100;
    
    console.log('Menu position - x:', x, 'y:', y);
    
    menu.style.cssText = `
        position: absolute;
        left: ${x}px;
        top: ${y}px;
        background: #000;
        border: 1px solid #00FFFF;
        padding: 0;
        z-index: 1000;
        box-shadow: 0 2px 10px rgba(0, 255, 255, 0.3);
    `;
    
    // Get the full URL (with protocol)
    const fullUrl = node.data.fullUrl ||
                    (node.data.value.startsWith('http') ? node.data.value : `https://${node.data.value}`);

    // Check if this is a LinkedIn URL
    const isLinkedInUrl = fullUrl.toLowerCase().includes('linkedin.com/');

    // Create menu items
    const menuItems = [
        {
            label: '🌐 Go to Website',
            action: () => {
                window.open(fullUrl, '_blank');
                updateStatus(`Opened ${node.data.value} in new tab`);
            }
        },
        {
            label: '🔗 Get Domain Backlinks',
            action: () => {
                fetchAndDisplayBacklinks(node, 'domain');
            }
        },
        {
            label: '📄 Get Page Backlinks',
            action: () => {
                fetchAndDisplayBacklinks(node, 'exact');
            }
        },
        {
            label: '🔗 Get Outlinks',
            action: () => {
                fetchAndDisplayOutlinks(node);
            }
        },
        {
            label: '🦉 Ownership-Linked Domains',
            action: () => {
                fetchAndDisplayOwnershipLinked(node);
            }
        },
        {
            label: '🧠 Extract Entities',
            action: () => {
                extractEntitiesFromUrl(node);
            }
        }
    ];

    // Add LinkedIn enrichment option if it's a LinkedIn URL
    if (isLinkedInUrl) {
        menuItems.push({
            label: '👔 Enrich LinkedIn Profile',
            action: () => {
                enrichLinkedInProfile(node, fullUrl);
            }
        });
    }
    
    // Add menu items
    menuItems.forEach(item => {
        const menuItem = document.createElement('div');
        menuItem.className = 'context-menu-item';
        menuItem.textContent = item.label;
        menuItem.style.cssText = `
            padding: 8px 16px;
            cursor: pointer;
            color: #00FFFF;
            font-family: monospace;
            border-bottom: 1px solid #003333;
        `;
        
        menuItem.onmouseover = () => {
            menuItem.style.backgroundColor = '#003333';
        };
        menuItem.onmouseout = () => {
            menuItem.style.backgroundColor = 'transparent';
        };
        
        menuItem.onclick = (e) => {
            e.stopPropagation();
            item.action();
            menu.remove();
        };
        
        menu.appendChild(menuItem);
    });
    
    // Add menu to page
    document.body.appendChild(menu);
    
    // Remove menu on click outside
    setTimeout(() => {
        document.addEventListener('click', function removeMenu() {
            const menu = document.getElementById('url-options-menu');
            if (menu) menu.remove();
            document.removeEventListener('click', removeMenu);
        });
    }, 100);
}

// Fetch and display outlinks for a URL node
async function fetchAndDisplayOutlinks(node) {
    try {
        const targetUrl = node.data.fullUrl || `https://${node.data.value}`;
        
        updateStatus(`🔗 Fetching outlinks for ${node.data.value}...`);
        
        const response = await fetchWithRetry('/api/url/outlinks', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ url: targetUrl })
        });
        
        const data = await response.json();
        
        if (data.success && data.outlinks) {
            const outlinks = data.outlinks;
            
            if (outlinks.length === 0) {
                updateStatus(`No outlinks found on ${node.data.value}`);
                return;
            }
            
            updateStatus(`Found ${outlinks.length} outlinks (${data.internal_count} internal, ${data.external_count} external)`);
            
            // Extract URLs from outlinks
            const outlinkUrls = outlinks.map(link => link.url);
            
            // Create an outlinks query node similar to backlinks
            const outlinksNodeData = {
                type: 'outlinks_query',
                value: `Outlinks for ${node.data.value}`,
                label: `🔗 Outlinks: ${node.data.value} (${outlinks.length} URLs)`,
                searchTerm: targetUrl,
                urls: outlinkUrls,
                outlinksData: outlinks,
                internalCount: data.internal_count,
                externalCount: data.external_count,
                source: 'Firecrawl Outlinks',
                isLoading: false
            };
            
            const outlinksNode = await addNode(outlinksNodeData, 'outlinks_query');
            if (!outlinksNode || !outlinksNode.nodeId) return;
            
            // Position near the URL node
            const urlPos = network.getPositions([node.id])[node.id];
            if (urlPos) {
                network.moveNode(outlinksNode.nodeId, urlPos.x - 300, urlPos.y);
            }
            
            // Create edge from URL to outlinks node
            edges.add({
                id: `${node.id}_${outlinksNode.nodeId}_outlinks`,
                from: node.id,
                to: outlinksNode.nodeId,
                label: 'outlinks',
                color: { color: '#FF00FF' },
                width: 2,
                dashes: false
            });
            
            // Save graph state
            saveGraphState();
            
            // Focus on the new node
            setTimeout(() => {
                network.focus(outlinksNode.nodeId, {
                    scale: 1.0,
                    animation: { duration: 1000, easingFunction: 'easeInOutQuad' }
                });
            }, 500);
            
        } else if (data.error) {
            updateStatus(`❌ Error: ${data.error}`);
        } else {
            updateStatus(`❌ Failed to fetch outlinks`);
        }
        
    } catch (error) {
        console.error('Error fetching outlinks:', error);
        updateStatus(`❌ Failed to fetch outlinks: ${error.message}`);
    }
}

// Fetch and display backlinks for a URL node
async function fetchAndDisplayBacklinks(node, mode = 'domain') {
    try {
        const targetUrl = node.data.fullUrl || `https://${node.data.value}`;
        const domain = node.data.value;
        const displayTarget = mode === 'exact' ? targetUrl : domain;
        
        updateStatus(`🔍 Fetching ${mode === 'exact' ? 'page' : 'domain'} backlinks for ${displayTarget}...`);
        
        const response = await fetchWithRetry('/api/ahrefs/backlinks', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ 
                domain: domain,
                url: targetUrl,
                mode: mode 
            })
        });
        
        const data = await response.json();
        
        if (data.success && data.backlinks) {
            const backlinks = data.backlinks;
            
            if (backlinks.length === 0) {
                updateStatus(`No ${mode === 'exact' ? 'page' : 'domain'} backlinks found for ${displayTarget}`);
                return;
            }
            
            updateStatus(`Found ${backlinks.length} ${mode === 'exact' ? 'page' : 'domain'} backlinks for ${displayTarget}`);
            
            // Extract URLs from backlinks
            const backlinkUrls = backlinks.map(bl => bl.url);
            
            // Create a backlinks query node similar to search_query nodes
            const backlinksNodeData = {
                type: 'backlinks_query',
                value: `${mode === 'exact' ? 'Page' : 'Domain'} Backlinks for ${displayTarget}`,
                label: `🔗 ${mode === 'exact' ? 'Page' : 'Domain'} Backlinks: ${displayTarget} (${backlinks.length} URLs)`,
                searchTerm: displayTarget,
                backlinksMode: mode,
                urls: backlinkUrls,
                backlinksData: backlinks, // Store full backlink data for profile display
                content: backlinkUrls.join('\n'),
                source: `Ahrefs ${mode === 'exact' ? 'Page' : 'Domain'} Backlinks`,
                isLoading: false
            };
            
            const backlinksNode = await addNode(backlinksNodeData, 'backlinks_query');
            if (!backlinksNode || !backlinksNode.nodeId) return;
            
            // Position near the URL node
            const urlPos = network.getPositions([node.id])[node.id];
            if (urlPos) {
                network.moveNode(backlinksNode.nodeId, urlPos.x + 300, urlPos.y);
            }
            
            // Create edge from URL to backlinks node
            edges.add({
                id: `${node.id}_${backlinksNode.nodeId}_backlinks`,
                from: node.id,
                to: backlinksNode.nodeId,
                label: 'backlinks',
                color: { color: '#00FFFF' },
                width: 2,
                dashes: false
            });
            
            // Check for connections with existing nodes
            await checkBacklinksConnections(backlinksNode.nodeId, backlinkUrls);
            
            // Save graph state
            saveGraphState();
            
            // Focus on the new node
            setTimeout(() => {
                network.focus(backlinksNode.nodeId, {
                    scale: 1.0,
                    animation: { duration: 1000, easingFunction: 'easeInOutQuad' }
                });
            }, 500);
            
        } else if (data.error) {
            updateStatus(`❌ Error: ${data.error}`);
        } else {
            updateStatus(`❌ Failed to fetch backlinks`);
        }
        
    } catch (error) {
        console.error('Error fetching backlinks:', error);
        updateStatus(`❌ Failed to fetch backlinks: ${error.message}`);
    }
}

// Check for connections between backlinks node and other nodes with matching URLs
async function checkBacklinksConnections(backlinksNodeId, backlinkUrls) {
    try {
        const allNodes = nodes.get();
        let connectionsCreated = 0;
        
        // Normalize backlink URLs for comparison
        const normalizedBacklinks = backlinkUrls.map(url => 
            url.replace(/^https?:\/\//, '')
               .replace(/^www\./, '')
               .replace(/\/$/, '')
        );
        
        for (const otherNode of allNodes) {
            if (otherNode.id === backlinksNodeId) continue; // Skip self
            
            let sharedUrls = [];
            
            // Check against search query nodes
            if (otherNode.type === 'search_query' && otherNode.urls && otherNode.urls.length > 0) {
                for (const searchUrl of otherNode.urls) {
                    const normalizedSearchUrl = searchUrl
                        .replace(/^https?:\/\//, '')
                        .replace(/^www\./, '')
                        .replace(/\/$/, '');
                    
                    // Check if this search URL matches any backlink
                    const matchingBacklinks = backlinkUrls.filter((blUrl, idx) => {
                        const normalizedBl = normalizedBacklinks[idx];
                        return normalizedBl === normalizedSearchUrl || 
                               normalizedBl.includes(normalizedSearchUrl) || 
                               normalizedSearchUrl.includes(normalizedBl);
                    });
                    
                    if (matchingBacklinks.length > 0) {
                        sharedUrls.push(...matchingBacklinks);
                    }
                }
            }
            
            // Check against URL nodes
            if (otherNode.type === 'url' && otherNode.data.value) {
                const otherNormalizedUrl = otherNode.data.value
                    .replace(/^https?:\/\//, '')
                    .replace(/^www\./, '')
                    .replace(/\/$/, '');
                
                const matchingBacklinks = backlinkUrls.filter((blUrl, idx) => {
                    const normalizedBl = normalizedBacklinks[idx];
                    return normalizedBl === otherNormalizedUrl || 
                           normalizedBl.includes(otherNormalizedUrl) || 
                           otherNormalizedUrl.includes(normalizedBl);
                });
                
                if (matchingBacklinks.length > 0) {
                    sharedUrls.push(...matchingBacklinks);
                }
            }
            
            // Check against other backlinks_query nodes
            if (otherNode.type === 'backlinks_query' && otherNode.urls && otherNode.urls.length > 0) {
                for (const otherUrl of otherNode.urls) {
                    const normalizedOtherUrl = otherUrl
                        .replace(/^https?:\/\//, '')
                        .replace(/^www\./, '')
                        .replace(/\/$/, '');
                    
                    const matchingBacklinks = backlinkUrls.filter((blUrl, idx) => {
                        const normalizedBl = normalizedBacklinks[idx];
                        return normalizedBl === normalizedOtherUrl;
                    });
                    
                    if (matchingBacklinks.length > 0) {
                        sharedUrls.push(...matchingBacklinks);
                    }
                }
            }
            
            // Check nodes with manual URLs
            if (otherNode.data && otherNode.data.manualUrls && otherNode.data.manualUrls.length > 0) {
                for (const manualUrl of otherNode.data.manualUrls) {
                    const normalizedManualUrl = manualUrl
                        .replace(/^https?:\/\//, '')
                        .replace(/^www\./, '')
                        .replace(/\/$/, '');
                    
                    const matchingBacklinks = backlinkUrls.filter((blUrl, idx) => {
                        const normalizedBl = normalizedBacklinks[idx];
                        return normalizedBl === normalizedManualUrl || 
                               normalizedBl.includes(normalizedManualUrl) || 
                               normalizedManualUrl.includes(normalizedBl);
                    });
                    
                    if (matchingBacklinks.length > 0) {
                        sharedUrls.push(...matchingBacklinks);
                    }
                }
            }
            
            // Create connection if shared URLs found
            if (sharedUrls.length > 0) {
                // Remove duplicates
                const uniqueSharedUrls = [...new Set(sharedUrls)];
                const edgeId = `${backlinksNodeId}_${otherNode.id}_shared_backlinks`;
                
                // Remove any existing edge in either direction
                edges.remove([edgeId, `${otherNode.id}_${backlinksNodeId}_shared_backlinks`]);
                
                // Create new edge
                const edgeData = {
                    id: edgeId,
                    from: backlinksNodeId,
                    to: otherNode.id,
                    label: `${uniqueSharedUrls.length} shared URL${uniqueSharedUrls.length > 1 ? 's' : ''}`,
                    color: {
                        color: '#00FF88',  // Green for backlink matches
                        highlight: '#00FFAA'
                    },
                    width: 2,
                    dashes: false,
                    title: `Shared URLs:\n${uniqueSharedUrls.join('\n')}`, // Tooltip with URLs
                };
                
                edges.add(edgeData);
                connectionsCreated++;
                console.log(`Connected backlinks to "${otherNode.label}" (${uniqueSharedUrls.length} shared)`);
            }
        }
        
        if (connectionsCreated > 0) {
            updateStatus(`Created ${connectionsCreated} connection${connectionsCreated > 1 ? 's' : ''} from backlinks`);
        }
        
    } catch (error) {
        console.error('Failed to check backlinks connections:', error);
    }
}

// Fetch and display ownership-linked domains (?owl operator)
async function fetchAndDisplayOwnershipLinked(node) {
    try {
        const domain = node.data.value;

        if (!domain) {
            updateStatus('❌ No domain value found');
            return;
        }

        updateStatus(`🦉 Finding ownership-linked domains for ${domain}...`);

        const response = await fetchWithRetry('/api/owl', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                domain: domain,
                include_nameserver: true
            })
        });

        const data = await response.json();

        if (data.success && data.results) {
            const results = data.results;

            if (results.length === 0) {
                updateStatus(`No ownership-linked domains found for ${domain}`);
                return;
            }

            updateStatus(`Found ${results.length} ownership-linked domains for ${domain}`);

            // Extract domain names for the list
            const ownershipDomains = results.map(r => r.domain);

            // Create an owl_query node similar to backlinks_query
            const owlNodeData = {
                type: 'owl_query',
                value: `Ownership-linked: ${domain}`,
                label: `🦉 OWL: ${domain} (${results.length} domains)`,
                searchTerm: domain,
                domains: ownershipDomains,
                owlData: results, // Store full result data for profile display
                distinctRegistrants: data.distinct_registrants || [],
                content: ownershipDomains.join('\n'),
                source: 'WHOIS Ownership Clustering',
                apiCalls: data.api_calls,
                method: data.method,
                isLoading: false
            };

            const owlNode = await addNode(owlNodeData, 'owl_query');
            if (!owlNode || !owlNode.nodeId) return;

            // Position near the source domain node
            const urlPos = network.getPositions([node.id])[node.id];
            if (urlPos) {
                network.moveNode(owlNode.nodeId, urlPos.x + 350, urlPos.y);
            }

            // Create edge from source domain to owl node using QUERY style
            const edgeStyle = getConnectionStyle('QUERY');
            edges.add({
                id: `${node.id}_${owlNode.nodeId}_owl`,
                from: node.id,
                to: owlNode.nodeId,
                label: 'ownership-linked',
                ...edgeStyle
            });

            // Check for connections with existing nodes (matching domains)
            await checkOwlConnections(owlNode.nodeId, ownershipDomains);

            // Save graph state
            saveGraphState();

            // Focus on the new node
            setTimeout(() => {
                network.focus(owlNode.nodeId, {
                    scale: 1.0,
                    animation: { duration: 1000, easingFunction: 'easeInOutQuad' }
                });
            }, 500);

        } else if (data.error) {
            updateStatus(`❌ Error: ${data.error}`);
        } else {
            updateStatus(`❌ Failed to fetch ownership-linked domains`);
        }

    } catch (error) {
        console.error('Error fetching ownership-linked domains:', error);
        updateStatus(`❌ Failed to fetch ownership-linked domains: ${error.message}`);
    }
}

// Check for connections between owl_query node and other nodes with matching domains
async function checkOwlConnections(owlNodeId, owlDomains) {
    try {
        const allNodes = nodes.get();
        let connectionsCreated = 0;

        // Normalize domain names for comparison
        const normalizedOwlDomains = owlDomains.map(d =>
            d.toLowerCase().replace(/^www\./, '').trim()
        );

        for (const otherNode of allNodes) {
            if (otherNode.id === owlNodeId) continue; // Skip self

            let matchingDomains = [];

            // Check against URL/domain nodes
            if ((otherNode.type === 'url' || otherNode.type === 'domain') && otherNode.data.value) {
                const otherDomain = otherNode.data.value
                    .toLowerCase()
                    .replace(/^https?:\/\//, '')
                    .replace(/^www\./, '')
                    .split('/')[0]
                    .trim();

                if (normalizedOwlDomains.includes(otherDomain)) {
                    matchingDomains.push(otherDomain);
                }
            }

            // Check against other owl_query nodes
            if (otherNode.type === 'owl_query' && otherNode.domains && otherNode.domains.length > 0) {
                const otherDomains = otherNode.domains.map(d =>
                    d.toLowerCase().replace(/^www\./, '').trim()
                );

                for (const otherDomain of otherDomains) {
                    if (normalizedOwlDomains.includes(otherDomain) && !matchingDomains.includes(otherDomain)) {
                        matchingDomains.push(otherDomain);
                    }
                }
            }

            // Check against backlinks_query nodes (domain overlap)
            if (otherNode.type === 'backlinks_query' && otherNode.urls && otherNode.urls.length > 0) {
                for (const backUrl of otherNode.urls) {
                    const backDomain = backUrl
                        .toLowerCase()
                        .replace(/^https?:\/\//, '')
                        .replace(/^www\./, '')
                        .split('/')[0]
                        .trim();

                    if (normalizedOwlDomains.includes(backDomain) && !matchingDomains.includes(backDomain)) {
                        matchingDomains.push(backDomain);
                    }
                }
            }

            // Create connection if matching domains found
            if (matchingDomains.length > 0) {
                const uniqueDomains = [...new Set(matchingDomains)];
                const edgeId = `${owlNodeId}_${otherNode.id}_shared_ownership`;

                // Remove any existing edge in either direction
                edges.remove([edgeId, `${otherNode.id}_${owlNodeId}_shared_ownership`]);

                // Create new edge using SOURCE style (green)
                const edgeStyle = getConnectionStyle('SOURCE');
                edges.add({
                    id: edgeId,
                    from: owlNodeId,
                    to: otherNode.id,
                    label: `${uniqueDomains.length} shared domain${uniqueDomains.length > 1 ? 's' : ''}`,
                    ...edgeStyle,
                    title: `Shared domains:\n${uniqueDomains.join('\n')}`, // Tooltip with domains
                });

                connectionsCreated++;
                console.log(`Connected OWL to "${otherNode.label}" (${uniqueDomains.length} shared)`);
            }
        }

        if (connectionsCreated > 0) {
            updateStatus(`Created ${connectionsCreated} connection${connectionsCreated > 1 ? 's' : ''} from ownership-linked`);
        }

    } catch (error) {
        console.error('Failed to check OWL connections:', error);
    }
}

// Show search provider selection modal
function showSearchProviderModal(node) {
    console.log('showSearchProviderModal called for node:', node);
    
    // Store the node globally for access by handlers
    window.currentSearchNode = node;
    
    // Create modal backdrop
    const modal = document.createElement('div');
    modal.id = 'search-provider-modal';
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.8);
        z-index: 2000;
        display: flex;
        justify-content: center;
        align-items: center;
    `;
    
    // Create modal content
    const content = document.createElement('div');
    content.style.cssText = `
        background: #000;
        border: 2px solid #0f0;
        padding: 0;
        width: 700px;
        max-height: 80vh;
        overflow: hidden;
        color: #0f0;
        font-family: monospace;
        display: flex;
        flex-direction: column;
    `;
    
    // Create header with node info
    const header = document.createElement('div');
    header.style.cssText = `
        padding: 15px 20px;
        background: #001100;
        border-bottom: 1px solid #003300;
    `;
    header.innerHTML = `
        <h3 style="color: #0f0; margin: 0;">Search Options for: ${escapeHtml(node.label)}</h3>
        <p style="color: #888; margin: 5px 0 0 0; font-size: 12px;">Type: ${node.type || 'unknown'}</p>
    `;
    
    // Create tab navigation
    const tabNav = document.createElement('div');
    tabNav.style.cssText = `
        display: flex;
        background: #000;
        border-bottom: 2px solid #003300;
    `;
    
    const apiTab = document.createElement('button');
    apiTab.style.cssText = `
        flex: 1;
        padding: 10px;
        background: #001100;
        border: none;
        border-bottom: 2px solid #0f0;
        color: #0f0;
        cursor: pointer;
        font-family: monospace;
        font-size: 14px;
    `;
    apiTab.textContent = '🔌 API Services';
    apiTab.onclick = () => showAPITab();
    
    const categoryTab = document.createElement('button');
    categoryTab.style.cssText = `
        flex: 1;
        padding: 10px;
        background: #000;
        border: none;
        border-bottom: 2px solid transparent;
        color: #888;
        cursor: pointer;
        font-family: monospace;
        font-size: 14px;
    `;
    categoryTab.textContent = '🔍 Search Categories';
    categoryTab.onclick = () => showCategoryTab();
    
    tabNav.appendChild(apiTab);
    tabNav.appendChild(categoryTab);
    
    // Create tab content container
    const tabContent = document.createElement('div');
    tabContent.id = 'search-provider-tab-content';
    tabContent.style.cssText = `
        flex: 1;
        overflow-y: auto;
        padding: 20px;
    `;
    
    // Function to show API tab
    function showAPITab() {
        apiTab.style.background = '#001100';
        apiTab.style.borderBottomColor = '#0f0';
        apiTab.style.color = '#0f0';
        categoryTab.style.background = '#000';
        categoryTab.style.borderBottomColor = 'transparent';
        categoryTab.style.color = '#888';
        
        tabContent.innerHTML = `
            <div class="api-services-grid" style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                <button class="api-service-btn" onclick="selectSearchProvider('dehashed')" style="
                    padding: 20px;
                    background: #001100;
                    border: 2px solid #003300;
                    color: #0f0;
                    cursor: pointer;
                    text-align: left;
                    transition: all 0.2s;
                " onmouseover="this.style.borderColor='#0f0'" onmouseout="this.style.borderColor='#003300'">
                    <h4 style="margin: 0 0 5px 0;">🔓 DeHashed</h4>
                    <p style="margin: 0; font-size: 12px; color: #888;">Breach databases, credentials, personal data</p>
                </button>
                
                <button class="api-service-btn" onclick="selectSearchProvider('osint')" style="
                    padding: 20px;
                    background: #001100;
                    border: 2px solid #003300;
                    color: #0f0;
                    cursor: pointer;
                    text-align: left;
                    transition: all 0.2s;
                " onmouseover="this.style.borderColor='#0f0'" onmouseout="this.style.borderColor='#003300'">
                    <h4 style="margin: 0 0 5px 0;">🕵️ OSINT Industries</h4>
                    <p style="margin: 0; font-size: 12px; color: #888;">Social profiles, accounts, usernames</p>
                </button>
                
                <button class="api-service-btn" onclick="selectSearchProvider('whois')" style="
                    padding: 20px;
                    background: #001100;
                    border: 2px solid #003300;
                    color: #0f0;
                    cursor: pointer;
                    text-align: left;
                    transition: all 0.2s;
                " onmouseover="this.style.borderColor='#0f0'" onmouseout="this.style.borderColor='#003300'">
                    <h4 style="margin: 0 0 5px 0;">🌐 WhoisXMLAPI</h4>
                    <p style="margin: 0; font-size: 12px; color: #888;">Domain registration, WHOIS history</p>
                </button>
                
                <button class="api-service-btn" onclick="selectSearchProvider('opencorporates')" style="
                    padding: 20px;
                    background: #001100;
                    border: 2px solid #003300;
                    color: #0f0;
                    cursor: pointer;
                    text-align: left;
                    transition: all 0.2s;
                " onmouseover="this.style.borderColor='#0f0'" onmouseout="this.style.borderColor='#003300'">
                    <h4 style="margin: 0 0 5px 0;">🏢 OpenCorporates</h4>
                    <p style="margin: 0; font-size: 12px; color: #888;">Company records, officers, addresses</p>
                </button>
                
                <button class="api-service-btn" onclick="selectSearchProvider('aleph')" style="
                    padding: 20px;
                    background: #001100;
                    border: 2px solid #003300;
                    color: #0f0;
                    cursor: pointer;
                    text-align: left;
                    transition: all 0.2s;
                " onmouseover="this.style.borderColor='#0f0'" onmouseout="this.style.borderColor='#003300'">
                    <h4 style="margin: 0 0 5px 0;">📰 OCCRP Aleph</h4>
                    <p style="margin: 0; font-size: 12px; color: #888;">Investigative data, leaks, sanctions</p>
                </button>
                
                <button class="api-service-btn" onclick="selectSearchProvider('google')" style="
                    padding: 20px;
                    background: #110000;
                    border: 2px solid #330000;
                    color: #ff6b6b;
                    cursor: pointer;
                    text-align: left;
                    transition: all 0.2s;
                " onmouseover="this.style.borderColor='#ff6b6b'" onmouseout="this.style.borderColor='#330000'">
                    <h4 style="margin: 0 0 5px 0;">🔍 Google Search</h4>
                    <p style="margin: 0; font-size: 12px; color: #888;">Web search for URLs and online presence</p>
                </button>
            </div>
        `;
    }
    
    // Function to show Category tab
    function showCategoryTab() {
        categoryTab.style.background = '#001100';
        categoryTab.style.borderBottomColor = '#0f0';
        categoryTab.style.color = '#0f0';
        apiTab.style.background = '#000';
        apiTab.style.borderBottomColor = 'transparent';
        apiTab.style.color = '#888';
        
        tabContent.innerHTML = `
            <div class="search-categories" style="display: flex; flex-direction: column; gap: 15px;">
                <button class="category-btn" onclick="selectSearchCategory('accounts')" style="
                    padding: 20px;
                    background: #001100;
                    border: 2px solid #003300;
                    color: #0f0;
                    cursor: pointer;
                    text-align: left;
                    transition: all 0.2s;
                " onmouseover="this.style.borderColor='#0f0'" onmouseout="this.style.borderColor='#003300'">
                    <h4 style="margin: 0 0 5px 0;">🔐 Accounts & Credentials</h4>
                    <p style="margin: 0; font-size: 12px; color: #888;">Search for usernames, emails, passwords across breach databases and social platforms</p>
                    <p style="margin: 5px 0 0 0; font-size: 11px; color: #666;">Services: DeHashed, OSINT Industries</p>
                </button>
                
                <button class="category-btn" onclick="selectSearchCategory('corporate')" style="
                    padding: 20px;
                    background: #001100;
                    border: 2px solid #003300;
                    color: #0f0;
                    cursor: pointer;
                    text-align: left;
                    transition: all 0.2s;
                " onmouseover="this.style.borderColor='#0f0'" onmouseout="this.style.borderColor='#003300'">
                    <h4 style="margin: 0 0 5px 0;">🏛️ Corporate Intelligence</h4>
                    <p style="margin: 0; font-size: 12px; color: #888;">Find company registrations, officers, addresses, and offshore connections</p>
                    <p style="margin: 5px 0 0 0; font-size: 11px; color: #666;">Services: OpenCorporates, OCCRP Aleph</p>
                </button>
                
                <button class="category-btn" onclick="selectSearchCategory('domain')" style="
                    padding: 20px;
                    background: #001100;
                    border: 2px solid #003300;
                    color: #0f0;
                    cursor: pointer;
                    text-align: left;
                    transition: all 0.2s;
                " onmouseover="this.style.borderColor='#0f0'" onmouseout="this.style.borderColor='#003300'">
                    <h4 style="margin: 0 0 5px 0;">🌍 Domain Intelligence</h4>
                    <p style="margin: 0; font-size: 12px; color: #888;">Domain ownership history, related domains, email patterns</p>
                    <p style="margin: 5px 0 0 0; font-size: 11px; color: #666;">Services: WhoisXMLAPI, DeHashed</p>
                </button>
                
                <button class="category-btn" onclick="selectSearchCategory('personal')" style="
                    padding: 20px;
                    background: #001100;
                    border: 2px solid #003300;
                    color: #0f0;
                    cursor: pointer;
                    text-align: left;
                    transition: all 0.2s;
                " onmouseover="this.style.borderColor='#0f0'" onmouseout="this.style.borderColor='#003300'">
                    <h4 style="margin: 0 0 5px 0;">👤 Personal Information</h4>
                    <p style="margin: 0; font-size: 12px; color: #888;">Names, addresses, phone numbers, and associated records</p>
                    <p style="margin: 5px 0 0 0; font-size: 11px; color: #666;">Services: All available</p>
                </button>
                
                <button class="category-btn" onclick="selectSearchCategory('internet')" style="
                    padding: 20px;
                    background: #110000;
                    border: 2px solid #330000;
                    color: #ff6b6b;
                    cursor: pointer;
                    text-align: left;
                    transition: all 0.2s;
                " onmouseover="this.style.borderColor='#ff6b6b'" onmouseout="this.style.borderColor='#330000'">
                    <h4 style="margin: 0 0 5px 0;">🌐 Internet Search</h4>
                    <p style="margin: 0; font-size: 12px; color: #888;">Web search with variations for maximum online presence discovery</p>
                    <p style="margin: 5px 0 0 0; font-size: 11px; color: #666;">Service: Google Search</p>
                </button>
            </div>
        `;
    }
    
    // Create close button
    const closeBtn = document.createElement('button');
    closeBtn.style.cssText = `
        position: absolute;
        top: 15px;
        right: 15px;
        background: transparent;
        border: 1px solid #0f0;
        color: #0f0;
        padding: 5px 10px;
        cursor: pointer;
        font-family: monospace;
    `;
    closeBtn.textContent = '✕';
    closeBtn.onclick = () => {
        document.body.removeChild(modal);
        delete window.currentSearchNode;
    };
    
    // Also close on ESC key
    const handleEsc = (e) => {
        if (e.key === 'Escape') {
            document.body.removeChild(modal);
            delete window.currentSearchNode;
            document.removeEventListener('keydown', handleEsc);
        }
    };
    document.addEventListener('keydown', handleEsc);
    
    // Assemble modal
    content.appendChild(header);
    content.appendChild(closeBtn);
    content.appendChild(tabNav);
    content.appendChild(tabContent);
    modal.appendChild(content);
    document.body.appendChild(modal);
    
    // Show API tab by default
    showAPITab();
    
    // Store tab functions globally for access
    window.showAPITab = showAPITab;
    window.showCategoryTab = showCategoryTab;
}

// Handle search provider selection
window.selectSearchProvider = function(provider) {
    console.log('selectSearchProvider called with:', provider);
    
    const node = window.currentSearchNode;
    if (!node) {
        console.error('No current search node found');
        return;
    }
    
    // Close the provider modal
    const modal = document.getElementById('search-provider-modal');
    if (modal) {
        document.body.removeChild(modal);
    }
    
    // Mark node as being searched to update cache
    const nodeKey = `${node.id}_${node.type}_${node.data.value || node.data.label}`;
    
    switch(provider) {
        case 'dehashed':
            // Show AI suggestions modal for variations
            handleDeHashedSearch(node);
            break;
            
        case 'osint':
            // Direct OSINT Industries search
            handleOSINTIndustriesSearch(node);
            break;
            
        case 'whois':
            // Direct WHOIS search
            handleWhoisXMLSearch(node);
            break;
            
        case 'opencorporates':
            // Direct OpenCorporates search
            handleOpenCorporatesSearch(node);
            break;
            
        case 'aleph':
            // Direct OCCRP Aleph search
            handleAlephSearch(node);
            break;
            
        case 'google':
            // Show variations modal for Google search
            showGoogleSearchVariations(node);
            break;
            
        default:
            console.error('Unknown provider:', provider);
            updateStatus('Unknown search provider');
    }
    
    // Clean up
    delete window.currentSearchNode;
};

// Handle category-based search selection
window.selectSearchCategory = function(category) {
    console.log('selectSearchCategory called with:', category);
    
    const node = window.currentSearchNode;
    if (!node) {
        console.error('No current search node found');
        return;
    }
    
    // Close the provider modal
    const modal = document.getElementById('search-provider-modal');
    if (modal) {
        document.body.removeChild(modal);
    }
    
    switch(category) {
        case 'accounts':
            // Run DeHashed and OSINT Industries searches
            handleAccountsSearch(node);
            break;
            
        case 'corporate':
            // Run OpenCorporates and OCCRP Aleph searches
            handleCorporateIntelligenceSearch(node);
            break;
            
        case 'domain':
            // Run WhoisXML and DeHashed searches
            handleDomainIntelligenceSearch(node);
            break;
            
        case 'personal':
            // Run all applicable searches based on node type
            handlePersonalInfoSearch(node);
            break;
            
        case 'internet':
            // Show Google search variations
            showGoogleSearchVariations(node);
            break;
            
        default:
            console.error('Unknown category:', category);
            updateStatus('Unknown search category');
    }
    
    // Clean up
    delete window.currentSearchNode;
};

// Provider-specific handlers
async function handleDeHashedSearch(node) {
    updateStatus('Generating search variations for DeHashed...');
    
    try {
        // Generate AI suggestions for variations
        const suggestions = await generateAISuggestions(node.data.value || node.label, node.type);
        
        if (suggestions && suggestions.length > 0) {
            // Show the existing AI suggestions modal
            showAISuggestionsModal(suggestions, node);
        } else {
            // If no suggestions, perform direct search
            updateStatus('No variations found, performing direct search...');
            await performSearch(node.data.value || node.label, node.type, node.id);
        }
        
        // Mark as expanded
        const nodeKey = `${node.id}_${node.type}_${node.data.value || node.data.label}`;
        nodeExpansionCache.set(nodeKey, true);
        
    } catch (error) {
        console.error('DeHashed search failed:', error);
        updateStatus('DeHashed search failed');
    }
}

async function handleOSINTIndustriesSearch(node) {
    updateStatus(`🕵️ Searching OSINT Industries for ${node.label}...`);
    
    try {
        await handleOSINTSearch(node.data.value || node.label, node.id);
        
        // Mark as expanded
        const nodeKey = `${node.id}_${node.type}_${node.data.value || node.data.label}`;
        nodeExpansionCache.set(nodeKey, true);
        
    } catch (error) {
        console.error('OSINT Industries search failed:', error);
        updateStatus('OSINT Industries search failed');
    }
}

async function handleWhoisXMLSearch(node) {
    updateStatus(`🌐 Searching WhoisXMLAPI for ${node.label}...`);
    
    try {
        // Special handling for domain nodes
        if (node.type === 'domain') {
            await handleDomainNodeExpansion(node);
        } else {
            await performWhoisSearch(node.data.value || node.label, node.type, node.id);
        }
        
        // Mark as expanded
        const nodeKey = `${node.id}_${node.type}_${node.data.value || node.data.label}`;
        nodeExpansionCache.set(nodeKey, true);
        
    } catch (error) {
        console.error('WhoisXML search failed:', error);
        updateStatus('WhoisXML search failed');
    }
}

async function handleOpenCorporatesSearch(node) {
    updateStatus(`🏢 Searching OpenCorporates for ${node.label}...`);
    
    try {
        // Determine search type based on node type
        let searchType = 'opencorporates';
        if (node.type === 'name' || node.type === 'person') {
            searchType = 'opencorporates_officer';
        }
        
        await handleCorporateSearch(node.data.value || node.label, searchType, node.id);
        
        // Mark as expanded
        const nodeKey = `${node.id}_${node.type}_${node.data.value || node.data.label}`;
        nodeExpansionCache.set(nodeKey, true);
        
    } catch (error) {
        console.error('OpenCorporates search failed:', error);
        updateStatus('OpenCorporates search failed');
    }
}

async function handleAlephSearch(node) {
    updateStatus(`📰 Searching OCCRP Aleph for ${node.label}...`);
    
    try {
        await handleCorporateSearch(node.data.value || node.label, 'aleph', node.id);
        
        // Mark as expanded
        const nodeKey = `${node.id}_${node.type}_${node.data.value || node.data.label}`;
        nodeExpansionCache.set(nodeKey, true);
        
    } catch (error) {
        console.error('OCCRP Aleph search failed:', error);
        updateStatus('OCCRP Aleph search failed');
    }
}

// Generate Google search variations for a search term with smart context awareness
// ALL VARIATIONS ARE EXACT PHRASE SEARCHES (quoted) - no broad searches allowed
function generateGoogleSearchVariations(searchTerm, nodeType = null) {
    const variations = new Set();
    const cleanTerm = searchTerm.trim();
    
    // Helper function to check if string looks like a person's name
    function looksLikeName(term) {
        const parts = term.split(/\s+/);
        if (parts.length < 2 || parts.length > 5) return false;
        
        // Check if parts are capitalized (typical for names)
        const allCapitalized = parts.every(part => 
            part.length > 0 && part[0] === part[0].toUpperCase() && 
            !/^\d/.test(part) && // Not starting with number
            !part.includes('@') && // Not email
            !part.includes('.com') // Not domain
        );
        
        // Check for common name patterns
        const hasCommonNamePattern = /^[A-Z][a-z]+(\s+[A-Z][a-z]+)+$/.test(term) ||
                                   /^[A-Z][a-z]+,\s+[A-Z][a-z]+/.test(term);
        
        return allCapitalized || hasCommonNamePattern;
    }
    
    // Helper function to check if string looks like a company
    function looksLikeCompany(term) {
        const lowerTerm = term.toLowerCase();
        return lowerTerm.includes('inc') || lowerTerm.includes('llc') || 
               lowerTerm.includes('ltd') || lowerTerm.includes('corp') ||
               lowerTerm.includes('company') || lowerTerm.includes('group') ||
               lowerTerm.includes('holdings') || lowerTerm.includes('partners') ||
               lowerTerm.includes('associates') || lowerTerm.includes('& ') ||
               lowerTerm.includes(' and ');
    }
    
    // Always add exact match first
    variations.add(`"${cleanTerm}"`);
    
    const parts = cleanTerm.split(/\s+/).filter(p => p.length > 0);
    
    // Handle based on detected type or node type
    if (nodeType === 'email' || cleanTerm.includes('@')) {
        // For emails, search for the email and the name part
        const namePart = cleanTerm.split('@')[0]
            .replace(/[._-]/g, ' ')
            .split(/\s+/)
            .map(p => p.charAt(0).toUpperCase() + p.slice(1).toLowerCase())
            .join(' ');
        
        if (namePart && namePart !== cleanTerm) {
            variations.add(`"${namePart}"`);
        }
        // All email searches should be exact phrase searches
        
    } else if (nodeType === 'phone' || /^\+?\d[\d\s\-\(\)]+$/.test(cleanTerm)) {
        // Enhanced phone number variations - 10 most likely formats
        const digitsOnly = cleanTerm.replace(/\D/g, '');
        
        // Always add original format first
        variations.add(`"${cleanTerm}"`);
        
        // Generate the 10 most likely phone number formats based on local conventions
        if (digitsOnly.length >= 10) {
            // Extract components based on length
            let countryCode = '';
            let areaCode = '';
            let mainNumber = '';
            
            if (digitsOnly.length === 10) {
                // US/Canada format: (XXX) XXX-XXXX
                areaCode = digitsOnly.slice(0, 3);
                mainNumber = digitsOnly.slice(3, 6) + digitsOnly.slice(6, 10);
            } else if (digitsOnly.length === 11 && digitsOnly.startsWith('1')) {
                // US/Canada with country code: 1-XXX-XXX-XXXX
                countryCode = '1';
                areaCode = digitsOnly.slice(1, 4);
                mainNumber = digitsOnly.slice(4, 7) + digitsOnly.slice(7, 11);
            } else if (digitsOnly.length >= 11) {
                // International format - try to detect country code
                if (digitsOnly.startsWith('1') && digitsOnly.length === 11) {
                    countryCode = '1';
                    areaCode = digitsOnly.slice(1, 4);
                    mainNumber = digitsOnly.slice(4, 7) + digitsOnly.slice(7, 11);
                } else if (digitsOnly.startsWith('44') && digitsOnly.length >= 12) {
                    countryCode = '44';
                    mainNumber = digitsOnly.slice(2);
                } else if (digitsOnly.startsWith('49') && digitsOnly.length >= 11) {
                    countryCode = '49';
                    mainNumber = digitsOnly.slice(2);
                } else if (digitsOnly.startsWith('33') && digitsOnly.length >= 11) {
                    countryCode = '33';
                    mainNumber = digitsOnly.slice(2);
                } else {
                    // Generic international - assume first 1-3 digits are country code
                    countryCode = digitsOnly.slice(0, Math.min(3, digitsOnly.length - 7));
                    mainNumber = digitsOnly.slice(countryCode.length);
                }
            }
            
            // 1. Digits only (already have original, but ensure clean version)
            variations.add(`"${digitsOnly}"`);
            
            if (areaCode && mainNumber.length >= 7) {
                // US/Canada formats
                const prefix = mainNumber.slice(0, 3);
                const suffix = mainNumber.slice(3);
                
                // 2. (XXX) XXX-XXXX
                variations.add(`"(${areaCode}) ${prefix}-${suffix}"`);
                
                // 3. XXX-XXX-XXXX
                variations.add(`"${areaCode}-${prefix}-${suffix}"`);
                
                // 4. XXX.XXX.XXXX
                variations.add(`"${areaCode}.${prefix}.${suffix}"`);
                
                // 5. XXX XXX XXXX
                variations.add(`"${areaCode} ${prefix} ${suffix}"`);
                
                if (countryCode) {
                    // 6. +1 (XXX) XXX-XXXX
                    variations.add(`"+${countryCode} (${areaCode}) ${prefix}-${suffix}"`);
                    
                    // 7. +1-XXX-XXX-XXXX
                    variations.add(`"+${countryCode}-${areaCode}-${prefix}-${suffix}"`);
                    
                    // 8. 1 XXX XXX XXXX
                    variations.add(`"${countryCode} ${areaCode} ${prefix} ${suffix}"`);
                }
            } else if (countryCode && mainNumber) {
                // International formats with local conventions
                
                // Format main number based on country
                let formattedMain = mainNumber;
                if (countryCode === '44' && mainNumber.length >= 10) {
                    // UK: +44 20 1234 5678 or +44 7700 123456
                    const areaOrMobile = mainNumber.slice(0, 2);
                    const rest = mainNumber.slice(2);
                    if (rest.length >= 8) {
                        formattedMain = `${areaOrMobile} ${rest.slice(0, 4)} ${rest.slice(4)}`;
                    }
                } else if (countryCode === '49' && mainNumber.length >= 9) {
                    // Germany: +49 30 12345678
                    const area = mainNumber.slice(0, 2);
                    const rest = mainNumber.slice(2);
                    formattedMain = `${area} ${rest}`;
                } else if (countryCode === '33' && mainNumber.length >= 9) {
                    // France: +33 1 23 45 67 89
                    const area = mainNumber.slice(0, 1);
                    const rest = mainNumber.slice(1);
                    if (rest.length >= 8) {
                        formattedMain = `${area} ${rest.slice(0, 2)} ${rest.slice(2, 4)} ${rest.slice(4, 6)} ${rest.slice(6)}`;
                    }
                }
                
                // 6. +CC XXXXXXXXX (formatted)
                variations.add(`"+${countryCode} ${formattedMain}"`);
                
                // 7. +CC-XXXXXXXXX
                variations.add(`"+${countryCode}-${mainNumber}"`);
                
                // 8. CC XXXXXXXXX
                variations.add(`"${countryCode} ${mainNumber}"`);
                
                // 9. 00CC XXXXXXXXX (European style)
                variations.add(`"00${countryCode} ${mainNumber}"`);
                
                // 10. +CC(0)XXXXXXX (some European conventions)
                if (['44', '49', '33', '31', '32'].includes(countryCode)) {
                    variations.add(`"+${countryCode}(0)${mainNumber}"`);
                }
            }
            
            // All phone number searches must be exact phrase searches
        } else {
            // Short numbers - exact phrase search only
            variations.add(`"${digitsOnly}"`);
        }
        
    } else if (looksLikeCompany(cleanTerm)) {
        // Smart company variations
        const withoutSuffix = cleanTerm
            .replace(/\s*(inc\.?|llc\.?|ltd\.?|corp\.?|corporation|limited|incorporated|company|co\.?|group|holdings|partners|llp|lp)$/i, '')
            .trim();
        
        if (withoutSuffix !== cleanTerm) {
            variations.add(`"${withoutSuffix}"`);
            // Only add ONE most likely variant, not all
            if (cleanTerm.toLowerCase().includes('inc')) {
                variations.add(`"${withoutSuffix} Inc"`);
            } else if (cleanTerm.toLowerCase().includes('llc')) {
                variations.add(`"${withoutSuffix} LLC"`);
            } else if (cleanTerm.toLowerCase().includes('ltd')) {
                variations.add(`"${withoutSuffix} Ltd"`);
            }
        }
        
        // All company searches must be exact phrase searches
        
    } else if (parts.length >= 2 && looksLikeName(cleanTerm)) {
        // Enhanced smart person name variations with international equivalents and nicknames
        
        // Define comprehensive name mappings
        const nameEquivalents = {
            // Hungarian
            'gyuri': ['györgy', 'george', 'jorge', 'giorgio', 'georges'],
            'györgy': ['gyuri', 'george', 'jorge', 'giorgio', 'georges'],
            'zoli': ['zoltán', 'zoltan'],
            'zoltán': ['zoli', 'zoltan'],
            'péter': ['peter', 'petya', 'pete', 'pietro', 'pierre', 'pedro'],
            'andrás': ['andrew', 'andre', 'andras', 'andrey', 'andrea'],
            'jános': ['john', 'janos', 'jan', 'jean', 'giovanni', 'juan'],
            'lászló': ['laszlo', 'ladislav', 'vladislav'],
            'gábor': ['gabor', 'gabriel', 'gabriele'],
            'attila': ['ati', 'atilla'],
            'balázs': ['balazs', 'blaise'],
            'dávid': ['david', 'dave', 'davide'],
            'miklós': ['miklos', 'nicholas', 'nick', 'nicolas', 'nikolai'],
            'tamás': ['tamas', 'thomas', 'tom', 'tommy', 'tomasz'],
            'zsolt': ['zsolt'],
            'béla': ['bela'],
            'imre': ['emery', 'emerich'],
            'krisztián': ['christian', 'kristian', 'chris'],
            'ákos': ['akos'],
            
            // English variants
            'william': ['bill', 'billy', 'will', 'willie', 'liam', 'guillaume', 'wilhelm'],
            'bill': ['william', 'billy', 'will', 'willie'],
            'robert': ['bob', 'bobby', 'rob', 'robbie', 'roberto', 'robert'],
            'bob': ['robert', 'bobby', 'rob', 'robbie'],
            'michael': ['mike', 'mickey', 'mick', 'miguel', 'michel', 'michele'],
            'mike': ['michael', 'mickey', 'mick'],
            'richard': ['rick', 'ricky', 'rich', 'richie', 'dick', 'riccardo'],
            'rick': ['richard', 'ricky', 'rich', 'richie'],
            'james': ['jim', 'jimmy', 'jamie', 'james', 'giacomo', 'jaime'],
            'jim': ['james', 'jimmy', 'jamie'],
            'christopher': ['chris', 'christie', 'christoph', 'cristopher'],
            'chris': ['christopher', 'christie', 'christian', 'krisztián'],
            'matthew': ['matt', 'matty', 'matteo', 'matthias'],
            'matt': ['matthew', 'matty'],
            'anthony': ['tony', 'ant', 'antonio', 'antoine'],
            'tony': ['anthony', 'antonio'],
            'daniel': ['dan', 'danny', 'daniele', 'dani'],
            'dan': ['daniel', 'danny'],
            'david': ['dave', 'davie', 'davide', 'dávid'],
            'dave': ['david', 'davie'],
            'joseph': ['joe', 'joey', 'giuseppe', 'jose'],
            'joe': ['joseph', 'joey'],
            'thomas': ['tom', 'tommy', 'tomás', 'tamas'],
            'tom': ['thomas', 'tommy'],
            'andrew': ['andy', 'drew', 'andre', 'andrás'],
            'andy': ['andrew', 'andre'],
            'joshua': ['josh', 'giosuè'],
            'josh': ['joshua'],
            'nicholas': ['nick', 'nicky', 'nicolas', 'miklós'],
            'nick': ['nicholas', 'nicky'],
            'alexander': ['alex', 'xander', 'alessandro', 'alexandre'],
            'alex': ['alexander', 'alexandra', 'alessandro'],
            'benjamin': ['ben', 'benny', 'benjamin'],
            'ben': ['benjamin', 'benny'],
            'samuel': ['sam', 'sammy', 'samuele'],
            'sam': ['samuel', 'sammy'],
            'jonathan': ['jon', 'johnny', 'gionatan'],
            'jon': ['jonathan', 'john'],
            'john': ['johnny', 'jon', 'giovanni', 'jean', 'juan', 'jános'],
            'johnny': ['john', 'jon'],
            'elizabeth': ['liz', 'lizzy', 'beth', 'betty', 'eliza', 'elisabetta'],
            'liz': ['elizabeth', 'lizzy'],
            'jennifer': ['jen', 'jenny', 'jenn'],
            'jen': ['jennifer', 'jenny'],
            'stephanie': ['steph', 'stefanie', 'stefania'],
            'steph': ['stephanie'],
            'patricia': ['pat', 'patty', 'trish', 'patrizia'],
            'pat': ['patricia', 'patrick'],
            'margaret': ['maggie', 'meg', 'peggy', 'margherita'],
            'maggie': ['margaret'],
            'catherine': ['cathy', 'kate', 'katie', 'cat', 'caterina'],
            'kate': ['catherine', 'katie'],
            'susan': ['sue', 'suzy', 'susanna'],
            'sue': ['susan', 'susanna'],
            'linda': ['lynn', 'lindy'],
            'barbara': ['barb', 'babs', 'barbara'],
            'barb': ['barbara'],
            
            // International variants
            'pierre': ['peter', 'pietro', 'pedro', 'péter'],
            'jean': ['john', 'giovanni', 'juan', 'jános'],
            'marie': ['mary', 'maria', 'maría'],
            'josé': ['joseph', 'giuseppe', 'josef'],
            'carlos': ['charles', 'carlo', 'karl'],
            'antonio': ['anthony', 'antoine', 'antoni'],
            'francesco': ['francis', 'françois', 'francisco'],
            'giovanni': ['john', 'jean', 'juan', 'jános'],
            'alessandro': ['alexander', 'alexandre', 'alejandro'],
            'marco': ['mark', 'marc', 'marcos'],
            'andrea': ['andrew', 'andré', 'andrás'],
            'matteo': ['matthew', 'matthias', 'mateo'],
            'giuseppe': ['joseph', 'jose', 'josef'],
            'stefan': ['stephen', 'stefano', 'esteban'],
            'klaus': ['nicholas', 'claudio'],
            'werner': ['warner'],
            'mikhail': ['michael', 'miguel', 'michel'],
            'vladimir': ['vlad', 'wladimir'],
            'vlad': ['vladimir'],
            'dmitry': ['dmitri', 'dima'],
            'sergey': ['sergio', 'serge'],
            'pavel': ['paul', 'pablo', 'paolo'],
            'alexei': ['alex', 'alexis'],
            'yuri': ['george', 'jorge', 'györgy', 'gyuri'],
            'igor': ['ihor']
        };
        
        // Function to get all name variants
        function getNameVariants(name) {
            const lowerName = name.toLowerCase();
            const variants = new Set([name]); // Always include original
            
            // Add exact matches from mapping
            if (nameEquivalents[lowerName]) {
                nameEquivalents[lowerName].forEach(variant => {
                    variants.add(variant);
                    // Also add capitalized version
                    variants.add(variant.charAt(0).toUpperCase() + variant.slice(1).toLowerCase());
                });
            }
            
            // Check if this name appears as a variant of other names
            for (const [mainName, variants_list] of Object.entries(nameEquivalents)) {
                if (variants_list.includes(lowerName)) {
                    variants.add(mainName);
                    variants.add(mainName.charAt(0).toUpperCase() + mainName.slice(1).toLowerCase());
                    // Add other variants too
                    variants_list.forEach(v => {
                        variants.add(v);
                        variants.add(v.charAt(0).toUpperCase() + v.slice(1).toLowerCase());
                    });
                }
            }
            
            return Array.from(variants).filter(v => v !== name); // Remove original to avoid duplication
        }
        
        if (parts.length === 2) {
            const [first, last] = parts;
            
            // Standard format variations
            variations.add(`"${first} ${last}"`);
            variations.add(`"${last}, ${first}"`);
            
            // Get name variants for first name
            const firstVariants = getNameVariants(first);
            firstVariants.forEach(variant => {
                variations.add(`"${variant} ${last}"`);
                variations.add(`"${last}, ${variant}"`);
            });
            
            // Also try with last name variants if it could be a first name
            const lastVariants = getNameVariants(last);
            lastVariants.forEach(variant => {
                variations.add(`"${first} ${variant}"`);
            });
            
        } else if (parts.length === 3) {
            const [first, middle, last] = parts;
            
            // Standard variations
            variations.add(`"${first} ${last}"`); // Without middle
            variations.add(`"${first} ${middle} ${last}"`); // Full name
            variations.add(`"${first} ${middle.charAt(0)}. ${last}"`); // Middle initial
            
            // Name variants for first name
            const firstVariants = getNameVariants(first);
            firstVariants.forEach(variant => {
                variations.add(`"${variant} ${last}"`);
                variations.add(`"${variant} ${middle} ${last}"`);
                variations.add(`"${variant} ${middle.charAt(0)}. ${last}"`);
            });
            
            // Name variants for middle name
            const middleVariants = getNameVariants(middle);
            middleVariants.forEach(variant => {
                variations.add(`"${first} ${variant} ${last}"`);
                variations.add(`"${first} ${variant.charAt(0)}. ${last}"`);
            });
            
        } else if (parts.length >= 4) {
            // For complex names, use first+last and full name with variants
            const first = parts[0];
            const last = parts[parts.length - 1];
            
            variations.add(`"${first} ${last}"`);
            variations.add(`"${parts.join(' ')}"`);
            
            // First name variants
            const firstVariants = getNameVariants(first);
            firstVariants.forEach(variant => {
                variations.add(`"${variant} ${last}"`);
            });
        }
        
    } else if (parts.length === 1) {
        // Single word - exact phrase search only
        variations.add(`"${cleanTerm}"`);
        
    } else {
        // Unknown multi-word phrase - exact phrase search only
        variations.add(`"${cleanTerm}"`);
    }
    
    // Remove any empty or duplicate variations
    return Array.from(variations).filter(v => v && v.trim().length > 0);
}

// Show Google search variations modal
function showGoogleSearchVariations(node) {
    const searchTerm = node.data.value || node.label;
    const variations = generateGoogleSearchVariations(searchTerm, node.type);
    
    // Create modal
    const modal = document.createElement('div');
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.8);
        z-index: 10000;
        display: flex;
        justify-content: center;
        align-items: center;
    `;
    
    const content = document.createElement('div');
    content.style.cssText = `
        background: #000;
        border: 2px solid #ff6b6b;
        padding: 20px;
        width: 600px;
        max-height: 80vh;
        overflow-y: auto;
        color: #0f0;
        font-family: monospace;
    `;
    
    let html = `
        <h3 style="color: #ff6b6b; margin: 0 0 15px 0;">🔍 Google Search Variations</h3>
        <p style="color: #888; margin: 0 0 20px 0;">Select search variations to query (exact phrase searches):</p>
        <div style="margin-bottom: 15px;">
            <button onclick="checkAllGoogleVariations()" style="
                background: #110000;
                border: 1px solid #ff6b6b;
                color: #ff6b6b;
                padding: 5px 15px;
                cursor: pointer;
                margin-right: 10px;
            ">Check All</button>
            <button onclick="uncheckAllGoogleVariations()" style="
                background: #110000;
                border: 1px solid #ff6b6b;
                color: #ff6b6b;
                padding: 5px 15px;
                cursor: pointer;
            ">Uncheck All</button>
        </div>
        <div style="margin-bottom: 15px; padding: 12px; background: ${UI_COLORS.surface}; border: 1px solid ${UI_COLORS.border}; border-radius: 12px;">
            <p style="color: ${UI_COLORS.accent}; font-weight: 600; margin: 0 0 10px 0; letter-spacing: 0.14em; text-transform: uppercase;">➕ Add Custom Variation:</p>
            <div style="display: flex; gap: 10px;">
                <input type="text" id="custom-variation-input" style="
                    flex: 1;
                    background: #000;
                    border: 1px solid #00ff00;
                    color: #0f0;
                    padding: 5px 10px;
                    font-family: monospace;
                " placeholder='Enter custom search variation (e.g., "John Doe LinkedIn")'
                  onkeypress="if(event.key === 'Enter') addGoogleCustomVariation()">
                <button onclick="addGoogleCustomVariation()" style="
                    background: #001100;
                    border: 1px solid #00ff00;
                    color: #00ff00;
                    padding: 5px 15px;
                    cursor: pointer;
                    font-weight: bold;
                ">Add</button>
            </div>
        </div>
        <div style="margin-bottom: 15px; padding: 10px; background: #221100; border: 2px solid #ff6b6b;">
            <p style="color: #ff6b6b; font-weight: bold; margin: 0;">
                🚀 EXHAUSTIVE SEARCH MODE ACTIVE
            </p>
            <p style="color: #888; margin: 5px 0 0 0; font-size: 12px;">
                Each variation will run Q1-Q4 queries × 100+ TLDs × site groups<br>
                (400+ queries per variation - may take several minutes)
            </p>
        </div>
        <div id="google-variations-list" style="margin-bottom: 20px;">
    `;
    
    variations.forEach((variation, index) => {
        html += `
            <label style="display: block; margin: 5px 0; cursor: pointer;">
                <input type="checkbox" class="google-variation-checkbox" value="${escapeHtml(variation)}" checked 
                       style="margin-right: 10px; cursor: pointer;">
                <span style="color: #0f0;">${escapeHtml(variation)}</span>
            </label>
        `;
    });
    
    html += `
        </div>
        <div style="text-align: right;">
            <button onclick="cancelGoogleSearch()" style="
                background: #001100;
                border: 1px solid #003300;
                color: #888;
                padding: 8px 20px;
                cursor: pointer;
                margin-right: 10px;
            ">Cancel</button>
            <button onclick="runSelectedGoogleSearches()" style="
                background: #110000;
                border: 2px solid #ff6b6b;
                color: #ff6b6b;
                padding: 8px 20px;
                cursor: pointer;
                font-weight: bold;
            ">Search Selected</button>
        </div>
    `;
    
    content.innerHTML = html;
    modal.appendChild(content);
    document.body.appendChild(modal);
    
    // Store current node and modal for access by button handlers
    window.currentGoogleSearchNode = node;
    window.currentGoogleModal = modal;
}

// Button handlers for Google variations modal
window.checkAllGoogleVariations = function() {
    document.querySelectorAll('.google-variation-checkbox').forEach(cb => cb.checked = true);
};

window.uncheckAllGoogleVariations = function() {
    document.querySelectorAll('.google-variation-checkbox').forEach(cb => cb.checked = false);
};

window.addGoogleCustomVariation = function() {
    const input = document.getElementById('custom-variation-input');
    const customVariation = input.value.trim();
    
    if (!customVariation) {
        updateStatus('Please enter a custom search variation');
        return;
    }
    
    // Check if variation already exists
    const existingCheckboxes = document.querySelectorAll('.google-variation-checkbox');
    for (let cb of existingCheckboxes) {
        if (cb.value === customVariation) {
            updateStatus('This variation already exists');
            input.value = '';
            return;
        }
    }
    
    // Add new variation to the list
    const variationsList = document.getElementById('google-variations-list');
    const newLabel = document.createElement('label');
    newLabel.style.cssText = 'display: block; margin: 5px 0; cursor: pointer;';
    newLabel.innerHTML = `
        <input type="checkbox" class="google-variation-checkbox" value="${escapeHtml(customVariation)}" checked 
               style="margin-right: 10px; cursor: pointer;">
        <span style="color: #0f0;">${escapeHtml(customVariation)}</span>
        <span style="color: ${UI_COLORS.accent}; margin-left: 10px;">[Custom]</span>
    `;
    
    variationsList.appendChild(newLabel);
    input.value = '';
    updateStatus(`Added custom variation: ${customVariation}`);
};

window.cancelGoogleSearch = function() {
    if (window.currentGoogleModal) {
        document.body.removeChild(window.currentGoogleModal);
        delete window.currentGoogleModal;
        delete window.currentGoogleSearchNode;
    }
};

// Resilient fetch wrapper with retry logic
async function fetchWithRetry(url, options, maxRetries = 3) {
    let lastError;
    
    for (let i = 0; i < maxRetries; i++) {
        try {
            const response = await fetch(url, options);
            return response;
        } catch (error) {
            lastError = error;
            console.log(`⚠️ Request failed (attempt ${i + 1}/${maxRetries}): ${error.message}`);
            
            if (i < maxRetries - 1) {
                // Exponential backoff: 1s, 2s, 4s
                const delay = Math.pow(2, i) * 1000;
                console.log(`⏳ Retrying in ${delay/1000} seconds...`);
                updateStatus(`Connection failed. Retrying in ${delay/1000} seconds...`);
                await new Promise(resolve => setTimeout(resolve, delay));
            }
        }
    }
    
    // All retries failed
    throw new Error(`Failed after ${maxRetries} attempts: ${lastError.message}`);
}

// Server health monitoring
let serverHealthy = true;

async function checkServerHealth() {
    try {
        const response = await fetch('/api/health', { 
            method: 'GET'
        });
        
        if (response.ok) {
            setServerStatus(true);
        } else {
            setServerStatus(false);
        }
    } catch (error) {
        setServerStatus(false);
    }
}

function setServerStatus(healthy) {
    serverHealthy = healthy;
    const icon = document.getElementById('server-status-icon');
    const text = document.getElementById('server-status-text');
    
    if (icon && text) {
        if (healthy) {
            icon.textContent = '🟢';
            text.textContent = 'Server Online';
            icon.parentElement.style.backgroundColor = '#1a1a1a';
        } else {
            icon.textContent = '🔴';
            text.textContent = 'Server Offline';
            icon.parentElement.style.backgroundColor = '#4a0000';
        }
    }
}

window.runSelectedGoogleSearches = async function() {
    const sourceNode = window.currentGoogleSearchNode;
    if (!sourceNode) return;
    
    // Get selected variations - EACH will be run through exhaustive search
    const selectedVariations = [];
    document.querySelectorAll('.google-variation-checkbox:checked').forEach(cb => {
        selectedVariations.push(cb.value);
    });
    
    if (selectedVariations.length === 0) {
        updateStatus('No search variations selected');
        return;
    }
    
    // Close modal
    window.cancelGoogleSearch();
    
    const originalTerm = sourceNode.data.value || sourceNode.label;
    
    // Create search query node with variations
    const searchQueryNode = await createEmptySearchQueryNode(
        originalTerm + ' [EXHAUSTIVE]',
        sourceNode.id,
        selectedVariations.length,
        selectedVariations  // Pass the actual search variations
    );
    
    if (!searchQueryNode) {
        updateStatus('Failed to create search query node');
        return;
    }
    
    updateStatus(`🚀 Starting EXHAUSTIVE searches for ${selectedVariations.length} variations...`);
    
    try {
        let completedSearches = 0;
        const allUrls = new Set();
        const allResults = [];
        
        // Process each variation through FULL ExactPhraseRecallRunner
        for (let i = 0; i < selectedVariations.length; i++) {
            const variation = selectedVariations[i];
            
            updateStatus(`🚀 Running exhaustive search ${i + 1}/${selectedVariations.length}: "${variation}"...`);
            
            try {
                // Run EXHAUSTIVE search for this variation
                console.log(`🚀 Starting exhaustive search for: "${variation}"`);
                const startTime = Date.now();
                
                const response = await fetchWithRetry('/api/google/search', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        query: variation,
                        run_mode: 'exhaustive',  // ALWAYS exhaustive
                        max_results: 100
                    })
                });
                
                const elapsed = Date.now() - startTime;
                console.log(`⏱️ Search completed in ${elapsed}ms for "${variation}"`);
                if (elapsed < 2000) {
                    console.warn(`⚠️ WARNING: Search completed suspiciously fast (${elapsed}ms) - might not be exhaustive!`);
                }
                
                // CRITICAL FIX: Handle both successful and 503 responses
                let result;
                console.log(`📡 Response status for "${variation}": ${response.status}`);
                
                try {
                    result = await response.json();
                    console.log(`🔍 GOOGLE API RESPONSE for "${variation}":`, result);
                } catch (jsonError) {
                    console.error(`❌ Failed to parse JSON response for "${variation}":`, jsonError);
                    continue;
                }
                
                // Process results - handle your working Google search format
                let newUrls = [];
                let newRichResults = [];
                
                if (result.success && result.urls) {
                    // YOUR WORKING GOOGLE SEARCH RESULTS  
                    newUrls = result.urls;
                    result.urls.forEach(url => allUrls.add(url));
                    
                    // Handle rich results with titles and snippets
                    if (result.results && Array.isArray(result.results)) {
                        newRichResults = result.results;
                        console.log(`✅ Added ${newUrls.length} URLs + ${newRichResults.length} rich results from "${variation}"`);
                        console.log(`📊 Rich results preview:`, newRichResults.slice(0, 2));
                    } else {
                        console.log(`✅ Added ${newUrls.length} URLs from "${variation}" (total: ${allUrls.size})`);
                    }
                } else if (result.mock_results && Array.isArray(result.mock_results)) {
                    // Fallback mock results  
                    console.log(`🧪 Using mock results for "${variation}":`, result.mock_results);
                    newUrls = result.mock_results;
                    result.mock_results.forEach(url => allUrls.add(url));
                    console.log(`✅ Added ${newUrls.length} mock URLs from "${variation}" (total: ${allUrls.size})`);
                } else {
                    console.error(`❌ No URLs found in response for "${variation}":`, result);
                    console.error(`❌ Response keys:`, Object.keys(result));
                }
                
                console.log(`🔧 About to update node with ${newUrls.length} new URLs`);
                console.log(`📋 New URLs to add:`, newUrls);
                
                // Update progress
                completedSearches++;
                const isLastSearch = (completedSearches === selectedVariations.length);
                
                // Update the node with new URLs, rich results, and progress
                await updateSearchQueryNode(
                    searchQueryNode.nodeId,  // FIX: Use nodeId not id
                    newUrls,
                    completedSearches,
                    isLastSearch,
                    newRichResults  // Pass rich results with titles/snippets
                );
                
                // Update status
                if (!isLastSearch) {
                    updateStatus(`🔍 Search progress: ${completedSearches}/${selectedVariations.length} complete (${allUrls.size} URLs found)`);
                }
                
            } catch (searchError) {
                console.error(`❌ CRITICAL: Search failed for variation "${variation}":`, searchError);
                console.error(`❌ Error details:`, searchError.stack || searchError);
                completedSearches++;
                // Log the error but continue with other searches
                updateStatus(`❌ Search failed for "${variation}": ${searchError.message}`);
            }
        }
        
        // Final update
        const finalUrls = Array.from(allUrls);
        console.log(`🏁 FINAL RESULTS: ${finalUrls.length} total URLs collected`);
        console.log(`📋 Final URLs array:`, finalUrls);
        
        if (finalUrls.length > 0) {
            console.log(`🔧 FINAL NODE UPDATE: Updating node ${searchQueryNode.nodeId} with ${finalUrls.length} URLs`);
            
            // Do one final comprehensive update with ALL URLs
            await updateSearchQueryNode(
                searchQueryNode.nodeId,  // FIX: Use nodeId not id
                finalUrls, // Pass ALL URLs
                selectedVariations.length, // All searches complete
                true // Mark as complete
            );
            
            // Store the variations used in the node data
            const finalNode = nodes.get(searchQueryNode.id);
            if (finalNode) {
                console.log(`📊 Current node state after final update:`, finalNode);
                nodes.update({
                    id: searchQueryNode.id,
                    searchVariations: selectedVariations
                });
            }
            
            // Check for connections with other search query nodes
            await checkSearchQueryConnections(nodes.get(searchQueryNode.id));
            updateStatus(`✅ Google search complete: ${finalUrls.length} unique URLs from ${selectedVariations.length} searches`);
        } else {
            console.log(`❌ NO URLS FOUND - allUrls Set was empty`);
            updateStatus('Google searches completed but no URLs found');
        }
        
        // Mark source node as expanded
        const nodeKey = `${sourceNode.id}_${sourceNode.type}_${sourceNode.data.value || sourceNode.data.label}`;
        nodeExpansionCache.set(nodeKey, true);
        
    } catch (error) {
        console.error('Google searches failed:', error);
        updateStatus('Google searches failed: ' + error.message);
        
        // Update node to show error state
        if (searchQueryNode) {
            nodes.update({
                id: searchQueryNode.id,
                label: `Search: ${originalTerm} (Error)`,
                isLoading: false,
                color: { background: '#CC0000', border: '#FF0000' }
            });
        }
    }
};

async function handleGoogleSearch(node) {
    // This function is now called directly when bypassing variations
    // (kept for backward compatibility if needed)
    showGoogleSearchVariations(node);
}

// Category-based search handlers
async function handleAccountsSearch(node) {
    updateStatus('🔐 Searching accounts & credentials...');
    
    // Run DeHashed search with variations
    await handleDeHashedSearch(node);
    
    // Also run OSINT Industries if applicable
    if (node.type === 'email' || node.type === 'username' || node.type === 'phone') {
        await handleOSINTIndustriesSearch(node);
    }
}

async function handleCorporateIntelligenceSearch(node) {
    updateStatus('🏛️ Searching corporate intelligence...');
    
    // Run OpenCorporates search
    await handleOpenCorporatesSearch(node);
    
    // Also run OCCRP Aleph search
    await handleAlephSearch(node);
}

async function handleDomainIntelligenceSearch(node) {
    updateStatus('🌍 Searching domain intelligence...');
    
    // Run WhoisXML search
    await handleWhoisXMLSearch(node);
    
    // Also run DeHashed for email patterns
    const domainEmailQuery = `@${node.data.value || node.label}`;
    await performSearch(domainEmailQuery, 'email', node.id);
}

async function handlePersonalInfoSearch(node) {
    updateStatus('👤 Searching personal information...');
    
    // Run all applicable searches based on node type
    const searchPromises = [];
    
    // Always search DeHashed
    searchPromises.push(handleDeHashedSearch(node));
    
    // Add type-specific searches
    if (node.type === 'email' || node.type === 'phone') {
        searchPromises.push(handleOSINTIndustriesSearch(node));
    }
    
    if (node.type === 'name' || node.type === 'person') {
        searchPromises.push(handleOpenCorporatesSearch(node));
    }
    
    if (isWhoisCandidate(node.data.value || node.label, node.type)) {
        searchPromises.push(handleWhoisXMLSearch(node));
    }
    
    // Run all searches in parallel
    await Promise.all(searchPromises);
}

// Create a search query node with URLs
async function createSearchQueryNode(searchTerm, urls) {
    try {
        const nodeData = {
            type: 'search_query',
            value: searchTerm,
            label: `Search: ${searchTerm}`,
            content: urls.join('\n'), // Store URLs in content field
            urls: urls, // Also store in a specific field for easy access
            searchTerm: searchTerm
        };
        
        const node = await addNode(nodeData, 'search_query');
        if (node) {
            console.log(`Created search query node for "${searchTerm}" with ${urls.length} URLs`);
            return node;
        }
        return null;
    } catch (error) {
        console.error('Failed to create search query node:', error);
        return null;
    }
}

// Create an empty search query node with loading state
async function createEmptySearchQueryNode(searchTerm, sourceNodeId, totalSearches, searchVariations = []) {
    try {
        console.log(`🔍 CREATING IMMEDIATE SEARCH NODE: "${searchTerm}" for source ${sourceNodeId}`);
        console.log(`🔍 Current nodes count:`, nodes ? nodes.length : 'nodes is null');
        console.log(`🔍 Current edges count:`, edges ? edges.length : 'edges is null');
        console.log(`🔍 Network exists:`, !!network);
        console.log(`🔍 Search variations to store:`, searchVariations);
        
        const nodeData = {
            type: 'search_query',
            value: searchTerm,
            label: `🔍 Searching: ${searchTerm} (0/${totalSearches})...`,
            content: 'Loading...', // Initial loading state
            urls: [], // Start with empty URLs
            searchTerm: searchTerm,
            searchVariations: searchVariations, // Store the actual search queries
            isLoading: true,
            totalSearches: totalSearches,
            completedSearches: 0
        };
        
        console.log(`🔍 About to call addNode with:`, nodeData);
        console.log(`🔍 Search variations being stored:`, nodeData.searchVariations);
        const node = await addNode(nodeData, 'search_query');
        console.log(`✅ NODE CREATED:`, node);
        console.log(`✅ Node data contains variations:`, node && nodes.get(node.nodeId)?.searchVariations);
        console.log(`✅ Node ID type:`, typeof node?.nodeId, 'Value:', node?.nodeId);
        console.log(`✅ Source ID type:`, typeof sourceNodeId, 'Value:', sourceNodeId);
        
        if (node && node.nodeId && sourceNodeId) {
            // Create immediate connection to source node
            const edgeData = {
                id: `${sourceNodeId}_${node.nodeId}_search`,
                from: sourceNodeId,
                to: node.nodeId,
                label: 'searched',
                ...getConnectionStyle('QUERY')
            };
            
            console.log(`🔗 CREATING CONNECTION:`, edgeData);
            console.log(`🔗 Edge from ${sourceNodeId} (${typeof sourceNodeId}) to ${node.nodeId} (${typeof node.nodeId})`);
            
            try {
                edges.add(edgeData);
                console.log(`✅ CONNECTION CREATED between ${sourceNodeId} and ${node.nodeId}`);
            } catch (edgeError) {
                console.error(`❌ EDGE CREATION FAILED:`, edgeError);
            }
            
            // Force network refresh to make sure node is visible
            if (network) {
                console.log(`🔄 Forcing network redraw...`);
                network.redraw();
                network.fit(); // Also fit the view to show all nodes
                
                // Position the new node near the source node
                const sourcePosition = network.getPosition(sourceNodeId);
                console.log(`📍 Source position:`, sourcePosition);
                if (sourcePosition) {
                    const newX = sourcePosition.x + 200;
                    const newY = sourcePosition.y + 100;
                    console.log(`📍 Moving new node to: ${newX}, ${newY}`);
                    network.moveNode(node.nodeId, newX, newY);
                }
                
                // Also try to focus on the new area
                network.focus(node.nodeId, {
                    scale: 1.0,
                    animation: {
                        duration: 1000,
                        easingFunction: 'easeInOutQuad'
                    }
                });
            } else {
                console.error(`❌ NETWORK IS NULL - cannot redraw or position`);
            }
            
            updateStatus(`🔍 Created search query node for "${searchTerm}" - starting ${totalSearches} searches...`);
            
            // Double-check the node was actually added
            setTimeout(() => {
                const checkNode = nodes.get(node.nodeId);
                console.log(`🔍 VERIFICATION: Node exists after 500ms:`, !!checkNode);
                if (checkNode) {
                    console.log(`✅ VERIFIED: Node label is:`, checkNode.label);
                } else {
                    console.error(`❌ CRITICAL: Node disappeared after creation!`);
                }
            }, 500);
            
        } else {
            console.error(`❌ FAILED TO CREATE NODE OR CONNECTION:`);
            console.error(`   node:`, node);
            console.error(`   node.nodeId:`, node?.nodeId);
            console.error(`   sourceNodeId:`, sourceNodeId);
        }
        
        return node;
    } catch (error) {
        console.error('❌ Failed to create empty search query node:', error);
        return null;
    }
}

// Update an existing search query node with new URLs, rich results, and progress
async function updateSearchQueryNode(nodeId, newUrls, completedCount, isComplete = false, newRichResults = []) {
    try {
        console.log(`🔄 UPDATING SEARCH QUERY NODE: ${nodeId}, URLs: ${newUrls.length}, Count: ${completedCount}, Complete: ${isComplete}`);
        
        const node = nodes.get(nodeId);
        if (!node) {
            console.error('❌ Node not found for update:', nodeId);
            return;
        }
        
        console.log(`📊 Current node state:`, node);
        
        // Merge new URLs with existing ones
        const existingUrls = node.urls || [];
        const allUrls = [...new Set([...existingUrls, ...newUrls])];
        
        // Merge rich results with existing ones  
        const existingRichResults = node.richResults || [];
        const allRichResults = [...existingRichResults];
        
        // Add new rich results (dedupe by URL)
        for (const newResult of newRichResults) {
            const existingResult = allRichResults.find(r => r.url === newResult.url);
            if (!existingResult) {
                allRichResults.push(newResult);
            }
        }
        
        console.log(`📈 URL merge: existing ${existingUrls.length} + new ${newUrls.length} = total ${allUrls.length}`);
        console.log(`📈 Rich results merge: existing ${existingRichResults.length} + new ${newRichResults.length} = total ${allRichResults.length}`);
        
        // Update node properties (preserve existing searchVariations)
        const updates = {
            urls: allUrls,
            richResults: allRichResults,  // Store rich results with titles/snippets
            content: allUrls.length > 0 ? allUrls.join('\n') : 'No URLs found yet...',
            completedSearches: completedCount,
            searchVariations: node.searchVariations || [] // Preserve search variations
        };
        
        // Update label based on completion status
        if (isComplete) {
            updates.label = `Search: ${node.searchTerm} (${allUrls.length} URLs)`;
            updates.isLoading = false;
            updates.color = getNodeColor('search_query'); // Restore normal color
            console.log(`✅ COMPLETION UPDATE: Final label = "${updates.label}"`);
        } else {
            updates.label = `🔍 Searching: ${node.searchTerm} (${completedCount}/${node.totalSearches})...`;
            // Optional: Add pulsing effect during loading
            updates.color = {
                background: '#FF6B6B',
                border: '#FF8888'
            };
            console.log(`⏳ PROGRESS UPDATE: Label = "${updates.label}"`);
        }
        
        console.log(`🔧 About to update node with:`, updates);
        
        // Update the node - CRITICAL FIX: Update ALL properties
        const completeUpdate = { 
            id: nodeId, 
            ...node, // Keep all existing properties
            ...updates // Apply the updates
        };
        
        console.log(`🔧 COMPLETE UPDATE OBJECT:`, completeUpdate);
        
        nodes.update(completeUpdate);
        
        console.log(`✅ Node update completed: ${completedCount}/${node.totalSearches} complete, ${allUrls.length} URLs`);
        
        // Verify the update worked
        const updatedNode = nodes.get(nodeId);
        console.log(`🔍 VERIFICATION - Updated node:`, updatedNode);
        console.log(`🔍 VERIFICATION - URLs in updated node:`, updatedNode?.urls);
        
        return allUrls;
    } catch (error) {
        console.error('Failed to update search query node:', error);
        return null;
    }
}

// Check for connections between a URL node and search query nodes
async function checkUrlToSearchConnections(urlNodeId, normalizedUrl, fullUrl) {
    try {
        const allNodes = nodes.get();
        let connectionsCreated = 0;
        
        for (const node of allNodes) {
            if (node.type === 'search_query' && node.urls && node.urls.length > 0) {
                // Check if any of the search query's URLs match our pasted URL
                const matchFound = node.urls.some(searchUrl => {
                    // Normalize the search URL the same way
                    const normalizedSearchUrl = searchUrl
                        .replace(/^https?:\/\//, '')
                        .replace(/^www\./, '')
                        .replace(/\/$/, '');
                    
                    return normalizedSearchUrl === normalizedUrl || 
                           searchUrl === fullUrl ||
                           searchUrl.includes(normalizedUrl) ||
                           normalizedUrl.includes(normalizedSearchUrl);
                });
                
                if (matchFound) {
                    // Create connection between URL node and search query node
                    const edgeId = `${urlNodeId}_${node.id}_url_match`;
                    
                    // Check if edge already exists
                    if (!edges.get(edgeId)) {
                        const edgeData = {
                            id: edgeId,
                            from: urlNodeId,
                            to: node.id,
                            label: 'found in',
                            ...getConnectionStyle('DEFAULT'),
                            color: {
                                color: '#00FF00',  // Green for URL match
                                highlight: '#00FF00'
                            },
                            width: 2,
                            title: `URL ${normalizedUrl} found in search results`, // Tooltip on hover
                        };
                        
                        edges.add(edgeData);
                        connectionsCreated++;
                        console.log(`Connected URL node to search query: "${node.label}"`);
                    }
                }
            }
        }
        
        if (connectionsCreated > 0) {
            updateStatus(`Connected URL to ${connectionsCreated} search result${connectionsCreated > 1 ? 's' : ''}`);
        }
        
    } catch (error) {
        console.error('Failed to check URL to search connections:', error);
    }
}

// Check for URL connections when a node's URLs are updated
async function checkNodeUrlConnections(nodeId, urls) {
    try {
        if (!urls || urls.length === 0) return;
        
        const allNodes = nodes.get();
        let connectionsCreated = 0;
        
        // Normalize the URLs for comparison
        const normalizedUrls = urls.map(url => 
            url.replace(/^https?:\/\//, '')
               .replace(/^www\./, '')
               .replace(/\/$/, '')
        );
        
        for (const otherNode of allNodes) {
            if (otherNode.id === nodeId) continue; // Skip self
            
            let sharedUrls = [];
            
            // Check against search query nodes
            if (otherNode.type === 'search_query' && otherNode.urls && otherNode.urls.length > 0) {
                for (const searchUrl of otherNode.urls) {
                    const normalizedSearchUrl = searchUrl
                        .replace(/^https?:\/\//, '')
                        .replace(/^www\./, '')
                        .replace(/\/$/, '');
                    
                    if (normalizedUrls.some(nUrl => nUrl === normalizedSearchUrl || 
                                                   nUrl.includes(normalizedSearchUrl) || 
                                                   normalizedSearchUrl.includes(nUrl))) {
                        sharedUrls.push(searchUrl);
                    }
                }
            }
            
            // Check against URL nodes
            if (otherNode.type === 'url' && otherNode.data.value) {
                const otherNormalizedUrl = otherNode.data.value
                    .replace(/^https?:\/\//, '')
                    .replace(/^www\./, '')
                    .replace(/\/$/, '');
                
                if (normalizedUrls.some(nUrl => nUrl === otherNormalizedUrl || 
                                               nUrl.includes(otherNormalizedUrl) || 
                                               otherNormalizedUrl.includes(nUrl))) {
                    sharedUrls.push(otherNode.data.value);
                }
            }
            
            // Check against other nodes with manual URLs
            if (otherNode.data && otherNode.data.manualUrls && otherNode.data.manualUrls.length > 0) {
                for (const otherUrl of otherNode.data.manualUrls) {
                    const normalizedOtherUrl = otherUrl
                        .replace(/^https?:\/\//, '')
                        .replace(/^www\./, '')
                        .replace(/\/$/, '');
                    
                    if (normalizedUrls.some(nUrl => nUrl === normalizedOtherUrl || 
                                                   nUrl.includes(normalizedOtherUrl) || 
                                                   normalizedOtherUrl.includes(nUrl))) {
                        sharedUrls.push(otherUrl);
                    }
                }
            }
            
            // Create connection if shared URLs found
            if (sharedUrls.length > 0) {
                const edgeId = `${nodeId}_${otherNode.id}_shared_manual_urls`;
                
                // Remove any existing edge in either direction
                edges.remove([edgeId, `${otherNode.id}_${nodeId}_shared_manual_urls`]);
                
                // Create new edge
                const edgeData = {
                    id: edgeId,
                    from: nodeId,
                    to: otherNode.id,
                    label: `${sharedUrls.length} shared URL${sharedUrls.length > 1 ? 's' : ''}`,
                    color: {
                        color: '#00DDFF',  // Cyan for manual URL matches
                        highlight: '#00FFFF'
                    },
                    width: 2,
                    dashes: false,
                    title: `Shared URLs:\n${[...new Set(sharedUrls)].join('\n')}`, // Tooltip with unique URLs
                };
                
                edges.add(edgeData);
                connectionsCreated++;
                console.log(`Connected nodes via shared URLs: "${nodeId}" <-> "${otherNode.id}" (${sharedUrls.length} shared)`);
            }
        }
        
        if (connectionsCreated > 0) {
            updateStatus(`Created ${connectionsCreated} URL connection${connectionsCreated > 1 ? 's' : ''}`);
        }
        
    } catch (error) {
        console.error('Failed to check node URL connections:', error);
    }
}

// Check for connections between search query nodes based on shared URLs
async function checkSearchQueryConnections(newNode) {
    try {
        if (newNode.type !== 'search_query' || !newNode.urls) {
            return;
        }
        
        const newUrls = new Set(newNode.urls);
        const allNodes = nodes.get();
        
        for (const existingNode of allNodes) {
            if (existingNode.type === 'search_query' && 
                existingNode.id !== newNode.id && 
                existingNode.urls) {
                
                const existingUrls = new Set(existingNode.urls);
                const sharedUrls = [...newUrls].filter(url => existingUrls.has(url));
                
                if (sharedUrls.length > 0) {
                    // Create connection between the two search query nodes
                    const edgeId = `${newNode.id}_${existingNode.id}_shared_urls`;
                    
                    // Check if edge already exists
                    const existingEdge = edges.get(edgeId);
                    if (!existingEdge) {
                        const edgeData = {
                            id: edgeId,
                            from: newNode.id,
                            to: existingNode.id,
                            label: `${sharedUrls.length} shared URL${sharedUrls.length > 1 ? 's' : ''}`,
                            ...getConnectionStyle('DEFAULT'),
                            title: `Shared URLs:\n${sharedUrls.join('\n')}`, // Show shared URLs in tooltip
                            connectionDetail: sharedUrls.join('\n') // Store for connection details
                        };
                        
                        edges.add(edgeData);
                        console.log(`Created connection between search queries "${newNode.label}" and "${existingNode.label}" (${sharedUrls.length} shared URLs)`);
                    }
                }
            }
        }
    } catch (error) {
        console.error('Failed to check search query connections:', error);
    }
}

// Add URL field to node details
window.addUrlField = function(nodeId) {
    const container = document.getElementById('node-urls-container');
    const urlCount = container.querySelectorAll('input[id^="node-url-"]').length;
    
    const newField = document.createElement('div');
    newField.style.cssText = 'display: flex; gap: 10px; margin-bottom: 5px;';
    newField.innerHTML = `
        <input type="text" id="node-url-${urlCount}" value="" 
               style="flex: 1; background: #000; color: #0f0; border: 1px solid #00DDFF; padding: 5px; font-family: inherit;"
               placeholder="Enter URL...">
        <button onclick="removeUrlField(${urlCount})" style="background: #660000; border: 1px solid #ff0000; color: #ff0000; padding: 5px 10px;">×</button>
    `;
    
    container.appendChild(newField);
};

// Remove URL field
window.removeUrlField = function(index) {
    const container = document.getElementById('node-urls-container');
    const fields = container.querySelectorAll('div');
    if (fields.length > 1) {
        fields[index].remove();
    } else {
        // Clear the last field instead of removing it
        document.getElementById(`node-url-0`).value = '';
    }
};

// Show change type menu
window.showChangeTypeMenu = function(nodeId, event) {
    console.log('showChangeTypeMenu called with nodeId:', nodeId);
    
    if (event) {
        event.stopPropagation();
    }
    
    const node = nodes.get(nodeId);
    if (!node) {
        console.error('Node not found:', nodeId);
        return;
    }
    
    console.log('Node found:', node);
    
    // Hide the main context menu
    hideContextMenu();
    
    // Create type selection menu
    const typeMenu = document.createElement('div');
    typeMenu.className = 'context-menu';
    // Position the menu - if from context menu, offset it slightly
    const leftPos = event ? (event.clientX + 10) : 200;
    const topPos = event ? (event.clientY - 20) : 200;
    
    typeMenu.style.cssText = `
        position: fixed;
        left: ${leftPos}px;
        top: ${topPos}px;
        z-index: 10001;
        background: #1a1a1a;
        border: 1px solid #00ff00;
        border-radius: 4px;
        padding: 5px 0;
        min-width: 200px;
        box-shadow: 0 2px 10px rgba(0, 255, 0, 0.2);
    `;
    
    const nodeTypes = [
        { type: 'email', label: 'Email', color: '#00CED1' },
        { type: 'username', label: 'Username', color: '#9370DB' },
        { type: 'password', label: 'Password', color: '#FFFF00' },
        { type: 'hashed_password', label: 'Hashed Password', color: '#FFD700' },
        { type: 'ip_address', label: 'IP Address', color: '#FFA500' },
        { type: 'phone', label: 'Phone', color: '#808080' },
        { type: 'domain', label: 'Domain', color: '#32CD32' },
        { type: 'name', label: 'Person Name', color: '#4169E1' },
        { type: 'company', label: 'Company/Organization', color: '#00FF00' },
        { type: 'address', label: 'Address', color: '#8B4513' },
        { type: 'vin', label: 'VIN', color: '#FF1493' },
        { type: 'dob', label: 'Date of Birth', color: '#FF69B4' },
        { type: 'social', label: 'Social/SSN', color: '#FF0000' },
        { type: 'url', label: 'URL', color: '#00FFFF' },
        { type: 'search_query', label: 'Search Query', color: '#FF6B6B' }
    ];
    
    typeMenu.innerHTML = '<div style="font-weight: bold; padding: 5px 10px; border-bottom: 1px solid #333;">Select Node Type:</div>';
    
    nodeTypes.forEach(typeInfo => {
        const item = document.createElement('div');
        item.className = 'menu-item';
        item.style.cssText = `
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 5px 10px;
            cursor: pointer;
            color: #ffffff;
        `;
        item.onmouseover = function() { this.style.background = '#333'; };
        item.onmouseout = function() { this.style.background = 'transparent'; };
        
        item.innerHTML = `
            <span style="display: inline-block; width: 12px; height: 12px; background: ${typeInfo.color}; border-radius: 2px;"></span>
            <span>${typeInfo.label}</span>
            ${node.type === typeInfo.type ? '<span style="color: #00ff00;">✓</span>' : ''}
        `;
        item.onclick = function() {
            console.log('Type item clicked:', typeInfo.type);
            changeNodeType(nodeId, typeInfo.type);
            document.body.removeChild(typeMenu);
        };
        typeMenu.appendChild(item);
    });
    
    // Add click outside handler to close menu
    setTimeout(() => {
        document.addEventListener('click', function closeTypeMenu(e) {
            if (!typeMenu.contains(e.target)) {
                if (document.body.contains(typeMenu)) {
                    document.body.removeChild(typeMenu);
                }
                document.removeEventListener('click', closeTypeMenu);
            }
        });
    }, 100);
    
    document.body.appendChild(typeMenu);
    console.log('Type menu added to body. Menu element:', typeMenu);
};

// Change node type
window.changeNodeType = function(nodeId, newType) {
    console.log('changeNodeType called:', nodeId, newType);
    const node = nodes.get(nodeId);
    if (!node) {
        console.error('Node not found in changeNodeType:', nodeId);
        return;
    }
    
    // Save undo state
    saveUndoState(`Change type of "${node.label}" from ${node.type} to ${newType}`);
    
    // Update node
    const newColor = getNodeColor(newType);
    const updates = {
        id: nodeId,
        type: newType,
        color: {
            background: '#000000',
            border: newColor,
            highlight: {
                background: '#1a1a1a',
                border: newColor
            }
        }
    };
    
    // Update data.type as well
    if (node.data) {
        node.data.type = newType;
        updates.data = node.data;
    }
    
    nodes.update(updates);
    
    // Update node details if it's showing
    if (document.getElementById('node-details').innerHTML.includes(nodeId)) {
        showNodeDetails(nodes.get(nodeId));
    }
    
    updateStatus(`Changed node type to ${newType}`);
    saveGraphState();
};

// Center a node in the arrangement
window.centerNode = function(nodeId) {
    const allNodes = nodes.get();
    if (allNodes.length === 0) return;
    
    // Calculate the center point of all nodes
    let minX = Infinity, maxX = -Infinity;
    let minY = Infinity, maxY = -Infinity;
    
    allNodes.forEach(node => {
        const pos = network.getPositions([node.id])[node.id];
        if (pos) {
            minX = Math.min(minX, pos.x);
            maxX = Math.max(maxX, pos.x);
            minY = Math.min(minY, pos.y);
            maxY = Math.max(maxY, pos.y);
        }
    });
    
    // Calculate center point
    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;
    
    // Move the selected node to center
    network.moveNode(nodeId, centerX, centerY);
    
    // Update node position in dataset
    nodes.update({
        id: nodeId,
        x: centerX,
        y: centerY
    });
    
    // Focus on the centered node
    network.focus(nodeId, {
        scale: 1.0,
        animation: true
    });
    
    updateStatus(`Node centered in arrangement`);
    saveGraphState();
}

// Duplicate a node
window.duplicateNode = function(nodeId) {
    const node = nodes.get(nodeId);
    if (node) {
        const newNode = {
            ...node.data,
            label: node.data.label || node.data.value || 'Duplicate'
        };
        addNode(newNode, node.type, null, true); // Force duplicate
    }
}

// Delete a node
window.deleteNode = function(nodeId) {
    // Save undo state before deletion
    saveUndoState("Delete Node");
    
    nodes.remove(nodeId);
    updateStatus();
    saveGraphState();
}

// Delete connections to a node
window.deleteConnections = function(nodeId) {
    // Save undo state before deleting connections
    saveUndoState("Delete Connections");
    
    const connectedEdges = edges.get({
        filter: function(edge) {
            return edge.from === nodeId || edge.to === nodeId;
        }
    });
    edges.remove(connectedEdges.map(e => e.id));
    updateStatus();
    saveGraphState();
}

// Show change type menu
window.showChangeTypeMenu = function(nodeId) {
    // Remove any existing context menu
    const existingMenu = document.getElementById('context-menu');
    if (existingMenu) existingMenu.remove();
    
    const node = nodes.get(nodeId);
    if (!node) return;
    
    // Get mouse position from last event
    const event = window.event || {};
    
    const menu = document.createElement('div');
    menu.id = 'context-menu';
    menu.style.cssText = `
        position: absolute;
        left: ${event.pageX || 200}px;
        top: ${event.pageY || 200}px;
        background: #000;
        border: 1px solid #0f0;
        padding: 5px;
        z-index: 1001;
        font-family: monospace;
        font-size: 12px;
        max-height: 400px;
        overflow-y: auto;
    `;
    
    const types = [
        { type: 'email', label: 'Email' },
        { type: 'username', label: 'Username' },
        { type: 'password', label: 'Password' },
        { type: 'hashed_password', label: 'Hashed Password' },
        { type: 'ip_address', label: 'IP Address' },
        { type: 'phone', label: 'Phone' },
        { type: 'domain', label: 'Domain' },
        { type: 'name', label: 'Name' },
        { type: 'address', label: 'Address' },
        { type: 'company', label: 'Company' },
        { type: 'dob', label: 'Date of Birth' },
        { type: 'social', label: 'Social Media' },
        { type: 'url', label: 'URL' },
        { type: 'vin', label: 'VIN' },
        { type: 'ssn', label: 'SSN' },
        { type: 'cc', label: 'Credit Card' },
        { type: 'city', label: 'City' },
        { type: 'state', label: 'State' },
        { type: 'zip', label: 'ZIP Code' },
        { type: 'country', label: 'Country' }
    ];
    
    menu.innerHTML = '<div style="font-weight: bold; margin-bottom: 5px; color: #0f0;">Select New Type:</div>';
    
    types.forEach(({ type, label }) => {
        const isCurrentType = node.type === type;
        menu.innerHTML += `
            <div class="menu-item" 
                 onclick="changeNodeType('${nodeId}', '${type}')"
                 style="${isCurrentType ? 'background: #003300; color: #00ff00;' : ''}">
                ${label} ${isCurrentType ? '(current)' : ''}
            </div>
        `;
    });
    
    document.body.appendChild(menu);
    
    // Remove menu on click outside
    setTimeout(() => {
        document.addEventListener('click', function removeMenu(e) {
            const menu = document.getElementById('context-menu');
            if (menu && !menu.contains(e.target)) {
                menu.remove();
                document.removeEventListener('click', removeMenu);
            }
        });
    }, 100);
}


// Start connection mode for creating edges
window.startConnectionMode = function(sourceNodeId) {
    hideContextMenu();
    connectionMode = true;
    connectionSourceNode = sourceNodeId;
    
    updateStatus('Click on target node to create connection (ESC to cancel)');
    
    // Change cursor to crosshair
    document.body.style.cursor = 'crosshair';
    
    // Add visual feedback for source node
    const sourceNode = nodes.get(sourceNodeId);
    if (sourceNode) {
        nodes.update({
            id: sourceNodeId,
            borderWidth: 4,
            color: {
                ...sourceNode.color,
                border: UI_COLORS.accent // Accent border for anchored clusters
            }
        });
    }
    
    // Add overlay canvas for drawing the line
    const container = document.getElementById('network-container');
    const overlay = document.createElement('canvas');
    overlay.id = 'connection-overlay';
    overlay.style.cssText = `
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        pointer-events: none;
        z-index: 999;
    `;
    container.appendChild(overlay);
    
    // Start drawing the line
    document.addEventListener('mousemove', handleConnectionDrag);
    
    // Force immediate draw to show line
    const rect = container.getBoundingClientRect();
    handleConnectionDrag({ clientX: rect.left + rect.width/2, clientY: rect.top + rect.height/2 });
}

// Handle mouse movement during connection mode
function handleConnectionDrag(event) {
    if (!connectionMode || !connectionSourceNode) return;
    
    // Get source node position
    const sourcePos = network.getPositions([connectionSourceNode])[connectionSourceNode];
    if (!sourcePos) return;
    
    // Get the overlay canvas
    const overlay = document.getElementById('connection-overlay');
    if (!overlay) return;
    
    const container = document.getElementById('network-container');
    const rect = container.getBoundingClientRect();
    
    // Set overlay canvas size to match container
    overlay.width = rect.width;
    overlay.height = rect.height;
    
    // Get mouse position relative to the container
    const mouseX = event.clientX - rect.left;
    const mouseY = event.clientY - rect.top;
    
    // Convert positions to canvas coordinates
    const canvasPos = network.canvasToDOM(sourcePos);
    
    // Draw on overlay
    const ctx = overlay.getContext('2d');
    if (ctx) {
        // Clear the entire overlay
        ctx.clearRect(0, 0, overlay.width, overlay.height);
        
        // Draw line from source to mouse
        ctx.strokeStyle = UI_COLORS.accent;
        ctx.lineWidth = 3;
        ctx.setLineDash([5, 5]);
        ctx.beginPath();
        ctx.moveTo(canvasPos.x, canvasPos.y);
        ctx.lineTo(mouseX, mouseY);
        ctx.stroke();
        
        // Draw a small circle at mouse position
        ctx.fillStyle = UI_COLORS.accent;
        ctx.beginPath();
        ctx.arc(mouseX, mouseY, 5, 0, 2 * Math.PI);
        ctx.fill();
    }
}

// Cancel connection mode
function cancelConnectionMode() {
    if (!connectionMode) return;
    
    connectionMode = false;
    
    // Reset source node appearance
    if (connectionSourceNode) {
        const sourceNode = nodes.get(connectionSourceNode);
        if (sourceNode) {
            const originalColor = getNodeColor(sourceNode.type);
            nodes.update({
                id: connectionSourceNode,
                borderWidth: 2,
                color: {
                    ...sourceNode.color,
                    border: originalColor
                }
            });
        }
    }
    
    connectionSourceNode = null;
    document.body.style.cursor = 'default';
    
    // Remove event listener
    document.removeEventListener('mousemove', handleConnectionDrag);
    
    // Remove overlay canvas
    const overlay = document.getElementById('connection-overlay');
    if (overlay) {
        overlay.remove();
    }
    
    // Redraw to clear any artifacts
    network.redraw();
    updateStatus('Ready');
}



// Delete multiple selected nodes
window.deleteSelectedNodes = function(nodeIds) {
    if (confirm(`Delete ${nodeIds.length} selected nodes?`)) {
        // Save undo state before deletion
        saveUndoState(`Delete ${nodeIds.length} nodes`);
        
        nodeIds.forEach(nodeId => {
            nodes.remove(nodeId);
            // Clean up from tracking maps
            valueToNodeMap.forEach((value, key) => {
                if (value === nodeId) {
                    valueToNodeMap.delete(key);
                }
            });
        });
        updateStatus(`Deleted ${nodeIds.length} nodes`);
        saveGraphState();
    }
}

// Connect selected nodes
window.connectSelectedNodes = function(nodeIds) {
    if (nodeIds.length < 2) return;
    
    const connectionName = prompt('Enter connection name/reason:') || 'Manual connection';
    
    // Save undo state before creating connections
    saveUndoState(`Connect ${nodeIds.length} nodes`);
    
    // Connect all selected nodes in a star pattern
    for (let i = 0; i < nodeIds.length - 1; i++) {
        for (let j = i + 1; j < nodeIds.length; j++) {
            if (nodeIds[i] !== nodeIds[j]) { // Prevent self-loops
                edges.add({
                    from: nodeIds[i],
                    to: nodeIds[j],
                    ...getConnectionStyle('DEFAULT'),
                    title: connectionName,
                    arrows: ''
                });
            }
        }
    }
    
    updateStatus(`Connected ${nodeIds.length} nodes`);
    saveGraphState();
}

// Merge selected nodes into one
window.mergeSelectedNodes = function(nodeIds) {
    if (nodeIds.length < 2) return;
    
    // Save undo state before merging
    saveUndoState(`Merge ${nodeIds.length} nodes`);
    
    // Get the target node (first selected node becomes the main one)
    const targetId = nodeIds[0];
    const targetNode = nodes.get(targetId);
    
    if (!targetNode) return;
    
    // Merge all other nodes into the target
    for (let i = 1; i < nodeIds.length; i++) {
        mergeNodes(nodeIds[i], targetId);
    }
    
    updateStatus(`Merged ${nodeIds.length} nodes into ${targetNode.label}`);
    hideContextMenu();
}

// Connect nodes from the same breach
function connectBreachNodes(nodeIds, breachName) {
    if (nodeIds.length < 2) return;
    
    // Connect all nodes in a star pattern (all connected to each other)
    for (let i = 0; i < nodeIds.length - 1; i++) {
        for (let j = i + 1; j < nodeIds.length; j++) {
            if (nodeIds[i] !== nodeIds[j]) {
                // Check if edge already exists
                const existingEdge = edges.get({
                    filter: edge => 
                        (edge.from === nodeIds[i] && edge.to === nodeIds[j]) ||
                        (edge.from === nodeIds[j] && edge.to === nodeIds[i])
                });
                
                if (existingEdge.length === 0) {
                    edges.add({
                        from: nodeIds[i],
                        to: nodeIds[j],
                        color: {
                            color: '#666666' // Gray for breach connections
                        },
                        dashes: false,
                        width: 1,
                        title: `Same breach: ${breachName}`,
                        arrows: ''
                    });
                }
            }
        }
    }
}

// Merge two nodes
function mergeNodes(sourceId, targetId) {
    const sourceNode = nodes.get(sourceId);
    const targetNode = nodes.get(targetId);
    
    if (!sourceNode || !targetNode) return;
    
    // The target (node being dragged onto) becomes the main entity
    // The source (node being dragged) becomes a variation
    
    // Update target node data with variations
    const targetData = { ...targetNode.data };
    
    // Initialize variations array if it doesn't exist
    if (!targetData.variations) {
        targetData.variations = [];
    }
    
    // Initialize merge history if it doesn't exist
    if (!targetData.mergeHistory) {
        targetData.mergeHistory = [];
    }
    
    // Store complete merge information for reversal
    const mergeInfo = {
        nodeId: sourceId,
        value: sourceNode.data.value || sourceNode.label,
        label: sourceNode.label,
        type: sourceNode.type,
        breach: sourceNode.data.breach,
        breachData: sourceNode.data.breachData,
        notes: sourceNode.data.notes || '',
        position: network.getPositions([sourceId])[sourceId],
        mergedAt: new Date().toISOString(),
        originalConnections: edges.get({
            filter: edge => edge.from === sourceId || edge.to === sourceId
        }).map(edge => ({...edge}))
    };
    
    // Store image properties if it's an image node
    if (sourceNode.shape === 'image' && sourceNode.image) {
        mergeInfo.isImage = true;
        mergeInfo.image = sourceNode.image;
    }
    
    // Add source value as a variation
    const variation = {
        id: sourceId, // Keep original ID for unmerging
        value: sourceNode.data.value || sourceNode.label,
        label: sourceNode.label,
        type: sourceNode.type,
        breach: sourceNode.data.breach,
        notes: sourceNode.data.notes || '',
        mergedAt: mergeInfo.mergedAt
    };
    
    // If source is an image node, include the image data
    if (sourceNode.shape === 'image' && sourceNode.image) {
        variation.dataURL = sourceNode.image;
        variation.isImage = true;
        
        // Also add to mergedImages array for easier access
        if (!targetData.mergedImages) {
            targetData.mergedImages = [];
        }
        targetData.mergedImages.push({
            dataURL: sourceNode.image,
            mergedAt: mergeInfo.mergedAt,
            originalId: sourceId,
            label: sourceNode.label
        });
    }
    
    targetData.variations.push(variation);
    
    // Add to merge history
    targetData.mergeHistory.push(mergeInfo);
    
    // If source had variations, add them too
    if (sourceNode.data.variations) {
        targetData.variations.push(...sourceNode.data.variations);
    }
    
    // Merge notes
    if (sourceNode.data.notes && targetNode.data.notes) {
        targetData.notes = targetNode.data.notes + '\n\n[Merged from ' + sourceNode.label + ']\n' + sourceNode.data.notes;
    } else if (sourceNode.data.notes) {
        targetData.notes = sourceNode.data.notes;
    }
    
    // Update label - NO [+n] numbers, just clean label
    const variationCount = targetData.variations.length;
    // Remove ALL existing [+n] patterns from the label first
    const baseLabel = targetNode.label.replace(/\s*\[\+\d+\]/g, '').replace(/<br>\[\+\d+\]/g, '');
    const newLabel = baseLabel; // Just the clean label, no merge count
    
    // Update target node with type in tooltip
    nodes.update({
        id: targetId,
        data: targetData,
        label: newLabel,
        title: `${targetNode.type.toUpperCase()}: ${targetNode.label}\n${variationCount} variation(s)`,
        borderWidth: 3, // Thicker border for merged nodes
        shapeProperties: {
            borderDashes: false
        }
    });
    
    // NO INDICATORS - DISABLED
    
    // Transfer all edges from source to target
    const sourceEdges = edges.get({
        filter: edge => edge.from === sourceId || edge.to === sourceId
    });
    
    sourceEdges.forEach(edge => {
        const newEdge = { ...edge };
        if (edge.from === sourceId) {
            newEdge.from = targetId;
        }
        if (edge.to === sourceId) {
            newEdge.to = targetId;
        }
        
        // Check if this edge already exists
        const exists = edges.get({
            filter: e => (e.from === newEdge.from && e.to === newEdge.to) || 
                        (e.from === newEdge.to && e.to === newEdge.from)
        }).length > 0;
        
        if (!exists && newEdge.from !== newEdge.to) {
            // Check if both nodes are anchored to apply thick white styling
            const fromNode = nodes.get(newEdge.from);
            const toNode = nodes.get(newEdge.to);
            const bothAnchored = anchoredNodes.has(newEdge.from) && anchoredNodes.has(newEdge.to);
            
            edges.add({
                from: newEdge.from,
                to: newEdge.to,
                color: bothAnchored ? '#ffffff' : newEdge.color,
                dashes: bothAnchored ? false : newEdge.dashes,
                width: bothAnchored ? 3 : newEdge.width,
                title: (newEdge.title || '') + ' [via ' + sourceNode.label + ']',
                arrows: newEdge.arrows
            });
        }
    });
    
    // Remove source node
    nodes.remove(sourceId);
    
    // Update tracking maps
    valueToNodeMap.forEach((nodeId, key) => {
        if (nodeId === sourceId) {
            valueToNodeMap.delete(key);
        }
    });
    
    // Update breach connections
    breachConnections.forEach((nodeIds, breach) => {
        const index = nodeIds.indexOf(sourceId);
        if (index > -1) {
            nodeIds.splice(index, 1);
            if (!nodeIds.includes(targetId)) {
                nodeIds.push(targetId);
            }
        }
    });
    
    saveGraphState();
    updateStatus(`Merged "${sourceNode.label}" into "${targetNode.label}"`);
    
    // Update node details if target node is selected
    if (network.getSelectedNodes().includes(targetId)) {
        showNodeDetails(nodes.get(targetId));
    }
}

// Focus on a node and its connections
function focusNode(nodeId) {
    focusedNode = nodeId;
    
    // Get connected nodes
    const connectedNodes = new Set([nodeId]);
    const connectedEdges = edges.get({
        filter: function(edge) {
            if (edge.from === nodeId || edge.to === nodeId) {
                connectedNodes.add(edge.from);
                connectedNodes.add(edge.to);
                return true;
            }
            return false;
        }
    });
    
    // Store original colors and gray out non-connected nodes
    const allNodes = nodes.get();
    const updates = [];
    
    allNodes.forEach(node => {
        originalNodeColors.set(node.id, node.color);
        
        if (!connectedNodes.has(node.id)) {
            updates.push({
                id: node.id,
                color: {
                    background: '#333333',
                    border: '#222222'
                },
                font: {
                    color: '#555555'
                }
            });
        } else {
            // Make connected nodes brighter
            updates.push({
                id: node.id,
                color: {
                    background: node.color,
                    border: '#ffffff'
                },
                borderWidth: 3
            });
        }
    });
    
    nodes.update(updates);
    
    // Fade non-connected edges
    const allEdges = edges.get();
    const edgeUpdates = [];
    
    allEdges.forEach(edge => {
        if (!connectedEdges.find(e => e.id === edge.id)) {
            edgeUpdates.push({
                id: edge.id,
                color: {
                    color: '#333333'
                },
                font: {
                    color: '#333333'
                }
            });
        }
    });
    
    edges.update(edgeUpdates);
}

// Release focus and restore original colors
function releaseFocus() {
    if (!focusedNode) return;
    
    focusedNode = null;
    
    // Restore node colors
    const updates = [];
    originalNodeColors.forEach((color, nodeId) => {
        updates.push({
            id: nodeId,
            color: color,
            borderWidth: 2,
            font: {
                color: '#000000'
            }
        });
    });
    
    nodes.update(updates);
    originalNodeColors.clear();
    
    // Restore edge colors
    const allEdges = edges.get();
    const edgeUpdates = allEdges.map(edge => ({
        id: edge.id,
        color: {
            color: '#666666'
        },
        font: {
            color: '#666666'
        }
    }));
    
    edges.update(edgeUpdates);
}

// Switch tabs
window.switchTab = function(tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');
    
    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById(`${tabName}-tab`).classList.add('active');
    
    if (tabName === 'cache') {
        viewCacheAsMap(); // Default to map view
    }
}

// View cache as map
window.viewCacheAsMap = function() {
    const cacheView = document.getElementById('cache-view');
    let html = '<h3>Cache Map View</h3>';
    
    html += '<div style="margin-bottom: 20px;">';
    html += `<p>Search Cache: ${searchCache.size} entries</p>`;
    html += `<p>Node Expansion Cache: ${nodeExpansionCache.size} entries</p>`;
    html += `<p>Value-to-Node Map: ${valueToNodeMap.size} entries</p>`;
    html += '</div>';
    
    // Show search cache as a tree
    html += '<h4>Search Results by Query:</h4>';
    html += '<div class="cache-map">';
    
    searchCache.forEach((data, key) => {
        const [query, type] = key.split('_');
        html += `<div class="cache-entry" style="cursor: pointer;" 
                     oncontextmenu="loadCacheEntry('${key}'); return false;" 
                     ondblclick="loadCacheEntry('${key}'); switchTab('graph');" 
                     title="Double-click or right-click to load in graph">`;
        html += `<strong>${escapeHtml(query)}</strong> (${type})`;
        if (data.results) {
            html += `<ul>`;
            data.results.forEach(breach => {
                html += `<li>${breach.database_name || 'Unknown'} - `;
                const items = [];
                if (breach.email?.length) items.push(`${breach.email.length} emails`);
                if (breach.username?.length) items.push(`${breach.username.length} usernames`);
                if (breach.password?.length) items.push(`${breach.password.length} passwords`);
                if (breach.ip_address?.length) items.push(`${breach.ip_address.length} IPs`);
                html += items.join(', ');
                html += `</li>`;
            });
            html += `</ul>`;
        }
        html += '</div>';
    });
    
    html += '</div>';
    cacheView.innerHTML = html;
}

// View cache as list
window.viewCacheAsList = function() {
    const cacheView = document.getElementById('cache-view');
    let html = '<h3>Cache List View</h3>';
    
    // Collect all unique values from cache
    const allValues = new Map();
    
    searchCache.forEach((data, key) => {
        if (data.results) {
            data.results.forEach(breach => {
                // Collect emails
                if (breach.email) {
                    breach.email.forEach(email => {
                        if (!allValues.has(email)) {
                            allValues.set(email, { type: 'email', databases: [] });
                        }
                        allValues.get(email).databases.push(breach.database_name || 'Unknown');
                    });
                }
                
                // Collect usernames
                if (breach.username) {
                    breach.username.forEach(username => {
                        if (!allValues.has(username)) {
                            allValues.set(username, { type: 'username', databases: [] });
                        }
                        allValues.get(username).databases.push(breach.database_name || 'Unknown');
                    });
                }
                
                // Collect passwords
                if (breach.password) {
                    breach.password.forEach(password => {
                        if (!allValues.has(password)) {
                            allValues.set(password, { type: 'password', databases: [] });
                        }
                        allValues.get(password).databases.push(breach.database_name || 'Unknown');
                    });
                }
                
                // Collect IPs
                if (breach.ip_address) {
                    breach.ip_address.forEach(ip => {
                        if (!allValues.has(ip)) {
                            allValues.set(ip, { type: 'ip_address', databases: [] });
                        }
                        allValues.get(ip).databases.push(breach.database_name || 'Unknown');
                    });
                }
                
                // Collect addresses
                if (breach.address) {
                    breach.address.forEach(address => {
                        if (!allValues.has(address)) {
                            allValues.set(address, { type: 'address', databases: [] });
                        }
                        allValues.get(address).databases.push(breach.database_name || 'Unknown');
                    });
                }
                
                // Collect names
                if (breach.name) {
                    breach.name.forEach(name => {
                        if (!allValues.has(name)) {
                            allValues.set(name, { type: 'name', databases: [] });
                        }
                        allValues.get(name).databases.push(breach.database_name || 'Unknown');
                    });
                }
                
                // Collect phone numbers
                if (breach.phone) {
                    breach.phone.forEach(phone => {
                        if (!allValues.has(phone)) {
                            allValues.set(phone, { type: 'phone', databases: [] });
                        }
                        allValues.get(phone).databases.push(breach.database_name || 'Unknown');
                    });
                }
                
                // Collect ALL OTHER FIELDS
                const additionalFields = ['company', 'dob', 'hashed_password', 'social', 'url'];
                additionalFields.forEach(fieldName => {
                    if (breach[fieldName]) {
                        const values = Array.isArray(breach[fieldName]) ? breach[fieldName] : [breach[fieldName]];
                        values.forEach(val => {
                            if (val && !allValues.has(val)) {
                                allValues.set(val, { type: fieldName, databases: [] });
                            }
                            if (val) {
                                allValues.get(val).databases.push(breach.database_name || 'Unknown');
                            }
                        });
                    }
                });
            });
        }
    });
    
    // Display as sorted list
    html += '<table style="width: 100%; border-collapse: collapse;">';
    html += '<tr><th>Type</th><th>Value</th><th>Found In</th></tr>';
    
    const sortedValues = Array.from(allValues.entries()).sort((a, b) => a[0].localeCompare(b[0]));
    
    sortedValues.forEach(([value, info]) => {
        const escapedValue = escapeHtml(value);
        html += `<tr style="border-bottom: 1px solid #003300; cursor: pointer;" 
                     oncontextmenu="loadValueIntoGraph('${escapedValue}', '${info.type}'); return false;" 
                     ondblclick="loadValueIntoGraph('${escapedValue}', '${info.type}'); switchTab('graph');" 
                     title="Double-click or right-click to load in graph">`;
        html += `<td style="color: ${getNodeColor(info.type)}; padding: 5px;">${info.type}</td>`;
        html += `<td style="padding: 5px;">${escapedValue}</td>`;
        html += `<td style="padding: 5px;">${[...new Set(info.databases)].join(', ')}</td>`;
        html += '</tr>';
    });
    
    html += '</table>';
    html += `<p style="margin-top: 10px;">Total unique values: ${allValues.size}</p>`;
    
    cacheView.innerHTML = html;
}

// Load a value from cache into the graph
window.loadValueIntoGraph = function(value, type) {
    console.log(`Loading ${type}: ${value} into graph`);
    
    // Check if node already exists
    const existingNode = Array.from(valueToNodeMap.entries()).find(([val, nodeId]) => val === value);
    
    if (existingNode) {
        // Node exists - focus on it
        const nodeId = existingNode[1];
        network.selectNodes([nodeId]);
        network.focus(nodeId, {
            scale: 1.5,
            animation: {
                duration: 500,
                easingFunction: 'easeInOutQuad'
            }
        });
        updateStatus(`Focused on existing ${type}: ${value}`);
    } else {
        // Create new node from cache data
        let nodeData = null;
        let breach = null;
        
        // Find the data in cache
        searchCache.forEach((data, key) => {
            if (data.results && !nodeData) {
                data.results.forEach(result => {
                    if (!nodeData) {
                        // Check if this breach contains the value - CHECK ALL POSSIBLE FIELDS
                        let found = false;
                        
                        // Check array fields
                        const arrayFields = ['email', 'username', 'password', 'ip_address', 'address', 'name', 'phone', 
                                           'company', 'dob', 'hashed_password', 'social', 'url'];
                        
                        for (const field of arrayFields) {
                            if (type === field && result[field]) {
                                const fieldValues = Array.isArray(result[field]) ? result[field] : [result[field]];
                                if (fieldValues.includes(value)) {
                                    found = true;
                                    break;
                                }
                            }
                        }
                        
                        if (found) {
                            nodeData = result;
                            breach = result.database_name || 'Unknown';
                        }
                    }
                });
            }
        });
        
        if (nodeData) {
            // Create the node
            const nodeId = `node_${nodeIdCounter++}`;
            const nodeColor = getNodeColor(type);
            
            const newNode = {
                id: nodeId,
                label: value,
                type: type,
                color: {
                    background: '#000000',
                    border: nodeColor,
                    highlight: {
                        background: '#1a1a1a',
                        border: nodeColor
                    }
                },
                borderWidth: 2,
                borderWidthSelected: 3,
                font: {
                    color: '#666666',
                    size: 12,
                    face: 'monospace',
                    bold: false
                },
                data: {
                    value: value,
                    label: value,
                    breach: breach,
                    breachData: nodeData,
                    addedAt: Date.now()
                },
                title: `${type.toUpperCase()}: ${value}\n\nFound in: ${breach}`,
                physics: true,
                shadow: false
            };
            
            // Add to graph
            nodes.add(newNode);
            valueToNodeMap.set(value, nodeId);
            
            // Position near center
            const viewPosition = network.getViewPosition();
            network.moveNode(nodeId, viewPosition.x, viewPosition.y);
            
            // Select and focus
            network.selectNodes([nodeId]);
            network.focus(nodeId, {
                scale: 1.5,
                animation: {
                    duration: 500,
                    easingFunction: 'easeInOutQuad'
                }
            });
            
            updateStatus(`Added ${type}: ${value} from ${breach}`);
            saveGraphState();
        } else {
            updateStatus(`No data found for ${type}: ${value}`);
        }
    }
}

// Clear cache
window.clearCache = async function() {
    if (confirm('Clear all cached data? This will permanently delete all stored search results from disk.')) {
        try {
            const response = await fetch('/api/cache/clear', {
                method: 'POST'
            });
            
            const result = await response.json();
            if (result.success) {
                searchCache.clear();
                nodeExpansionCache.clear();
                updateStatus('Cache cleared from disk');
                
                // Refresh cache view
                if (document.getElementById('cache-tab').classList.contains('active')) {
                    viewCacheAsMap();
                }
            } else {
                updateStatus('Error clearing cache');
            }
        } catch (e) {
            console.error('Error clearing cache:', e);
            updateStatus('Error clearing cache');
        }
    }
}

// Load cache entry into graph
window.loadCacheEntry = function(cacheKey) {
    const data = searchCache.get(cacheKey);
    if (!data || !data.results) return;
    
    // Switch to graph tab
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector('.tab-button').classList.add('active');
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById('graph-tab').classList.add('active');
    
    // Process the cached results
    processCachedResults(data.results, null);
    updateStatus(`Loaded ${data.results.length} cached results into graph`);
}

// Load specific value into graph
window.loadValueIntoGraph = function(value, type) {
    // Switch to graph tab
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector('.tab-button').classList.add('active');
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById('graph-tab').classList.add('active');
    
    // Search for this value in the cache
    let found = false;
    searchCache.forEach((data, key) => {
        if (data.results) {
            data.results.forEach(breach => {
                // Check if this breach contains the value
                let hasValue = false;
                if (type === 'email' && breach.email?.includes(value)) hasValue = true;
                else if (type === 'username' && breach.username?.includes(value)) hasValue = true;
                else if (type === 'password' && breach.password?.includes(value)) hasValue = true;
                else if (type === 'ip_address' && breach.ip_address?.includes(value)) hasValue = true;
                else if (type === 'phone' && breach.phone?.includes(value)) hasValue = true;
                else if (type === 'name' && breach.name?.includes(value)) hasValue = true;
                else if (type === 'address' && breach.address?.includes(value)) hasValue = true;
                else if (type === 'domain' && breach.domain?.includes(value)) hasValue = true;
                
                if (hasValue) {
                    // Process just this breach for this value
                    processCachedResults([breach], null);
                    found = true;
                }
            });
        }
    });
    
    if (found) {
        updateStatus(`Loaded "${value}" into graph`);
        
        // Focus on the loaded node
        const nodeId = valueToNodeMap.get(`${type}_${value}`);
        if (nodeId) {
            network.focus(nodeId, {
                scale: 1.5,
                animation: {
                    duration: 500,
                    easingFunction: 'easeInOutQuad'
                }
            });
            
            // Select the node
            network.selectNodes([nodeId]);
        }
    } else {
        updateStatus(`Value "${value}" not found in cache`);
    }
}

// Save node notes
window.saveNodeNotes = function() {
    if (!currentProfileNode) return;
    
    const notes = document.getElementById('node-notes').value;
    
    // Update node data
    const updatedData = {
        ...currentProfileNode.data,
        notes: notes
    };
    
    nodes.update({
        id: currentProfileNode.id,
        data: updatedData
    });
    
    // Save to storage
    saveGraphState();
    updateStatus('Notes saved');
}

// Open node profile for editing (deprecated - keeping for compatibility)
window.openProfile = function(nodeId) {
    const node = nodes.get(nodeId);
    if (!node) return;
    
    currentProfileNode = node;
    
    // Show profile panel
    document.getElementById('node-details').style.display = 'none';
    document.getElementById('node-profile').style.display = 'block';
    
    // Build editable form
    let html = '<form id="profile-form">';
    html += `<h4>${node.type.toUpperCase()} - ${node.data.value || node.label}</h4>`;
    
    // Core fields (read-only)
    html += '<fieldset><legend>Core Data</legend>';
    html += `<label>Value: <input type="text" name="value" value="${escapeHtml(node.data.value || '')}" readonly style="background: #333;"></label><br>`;
    html += `<label>Type: <input type="text" value="${node.type}" readonly style="background: #333;"></label><br>`;
    if (node.data.breach) {
        html += `<label>Breach: <input type="text" value="${escapeHtml(node.data.breach)}" readonly style="background: #333;"></label><br>`;
    }
    html += '</fieldset>';
    
    // Editable metadata
    html += '<fieldset><legend>Custom Metadata</legend>';
    html += `<label>Label: <input type="text" name="label" value="${escapeHtml(node.label || '')}"></label><br>`;
    html += `<label>Notes: <textarea name="notes" rows="3">${escapeHtml(node.data.notes || '')}</textarea></label><br>`;
    html += `<label>Tags: <input type="text" name="tags" value="${escapeHtml(node.data.tags || '')}" placeholder="tag1, tag2, tag3"></label><br>`;
    html += `<label>Real Name: <input type="text" name="realName" value="${escapeHtml(node.data.realName || '')}"></label><br>`;
    html += `<label>Organization: <input type="text" name="organization" value="${escapeHtml(node.data.organization || '')}"></label><br>`;
    html += `<label>Location: <input type="text" name="location" value="${escapeHtml(node.data.location || '')}"></label><br>`;
    html += '</fieldset>';
    
    // Connections info
    html += '<fieldset><legend>Connections</legend>';
    const connectedEdges = edges.get({
        filter: edge => edge.from === nodeId || edge.to === nodeId
    });
    html += `<p>Connected to ${connectedEdges.length} nodes</p>`;
    
    // List connected nodes
    const connectedNodes = new Set();
    connectedEdges.forEach(edge => {
        connectedNodes.add(edge.from === nodeId ? edge.to : edge.from);
    });
    
    html += '<ul>';
    connectedNodes.forEach(connId => {
        const connNode = nodes.get(connId);
        if (connNode) {
            html += `<li>${connNode.type}: ${escapeHtml(connNode.label)}</li>`;
        }
    });
    html += '</ul>';
    html += '</fieldset>';
    
    html += '</form>';
    
    document.getElementById('profile-content').innerHTML = html;
}

// Save profile changes
window.saveProfile = function() {
    if (!currentProfileNode) return;
    
    const form = document.getElementById('profile-form');
    const formData = new FormData(form);
    
    // Update node data object first
    const updatedData = {
        ...currentProfileNode.data,
        notes: formData.get('notes') || '',
        tags: formData.get('tags') || '',
        realName: formData.get('realName') || '',
        organization: formData.get('organization') || '',
        location: formData.get('location') || ''
    };
    
    // Update node with new data
    const updates = {
        id: currentProfileNode.id,
        label: formData.get('label') || currentProfileNode.label,
        data: updatedData
    };
    
    nodes.update(updates);
    
    // Get the updated node
    currentProfileNode = nodes.get(currentProfileNode.id);
    
    // Update display
    updateStatus('Profile saved');
    saveGraphState(); // Save to localStorage
    closeProfile();
    showNodeDetails(currentProfileNode);
    
    // Update node list if it's visible
    if (document.getElementById('panel-nodes').classList.contains('active')) {
        updateNodeList();
    }
}

// Close profile
window.closeProfile = function() {
    document.getElementById('node-profile').style.display = 'none';
    document.getElementById('node-details').style.display = 'block';
    currentProfileNode = null;
}

// Toggle hashed passwords inclusion
window.toggleHashedPasswords = function(include) {
    includeHashedPasswords = include;
    updateStatus(include ? 'Hashed passwords will be included' : 'Hashed passwords will be excluded');
    
    // Save preference
    localStorage.setItem('includeHashedPasswords', include);
}

// AI Suggestions toggle
let aiSuggestionsEnabled = true;
window.toggleAISuggestions = function(enabled) {
    aiSuggestionsEnabled = enabled;
    localStorage.setItem('aiSuggestionsEnabled', enabled.toString());
    updateStatus(enabled ? 'AI suggestions enabled' : 'AI suggestions disabled');
}

// Toggle arrow display on edges
window.toggleArrows = function(show) {
    showArrows = show;
    
    // Update all existing edges
    const allEdges = edges.get();
    const updates = allEdges.map(edge => ({
        id: edge.id,
        arrows: {
            to: {
                enabled: showArrows,
                scaleFactor: 0.8
            }
        }
    }));
    
    edges.update(updates);
    updateStatus(showArrows ? 'Arrows enabled' : 'Arrows disabled');
}

// Toggle image source connection display
window.toggleImageSourceDisplay = function(show) {
    showImageSources = show;
    
    // Update visibility of image source edges
    const allEdges = edges.get();
    const updates = [];
    
    allEdges.forEach(edge => {
        if (edge.edgeType === 'image_source') {
            updates.push({
                id: edge.id,
                hidden: !show
            });
        }
    });
    
    if (updates.length > 0) {
        edges.update(updates);
        updateStatus(show ? 'Image source connections visible' : 'Image source connections hidden');
    }
}

// Toggle source display (for the Sources checkbox)
window.toggleSourceDisplay = function(show) {
    // This appears to be a different feature - maybe for showing source breaches?
    // For now, just log it
    console.log('Source display toggled:', show);
    updateStatus(show ? 'Sources visible' : 'Sources hidden');
}

// Toggle query node display
let autoShowQueries = false;

window.toggleQueryDisplay = function(show) {
    autoShowQueries = show;
    
    if (show) {
        // Show search indicators (not query nodes by default)
        drawSearchIndicators();
        updateStatus('Query indicators enabled');
    } else {
        // Hide all query nodes AND search indicators
        activeQueryNodes.forEach((searchData, queryNodeId) => {
            hideQueryNode(queryNodeId, false);
        });
        clearSearchIndicators();
        updateStatus('Query indicators disabled');
    }
}

// Toggle highlighting of unsearched nodes
let unsearchedHighlightActive = false;
window.toggleUnsearchedHighlight = function(highlight) {
    unsearchedHighlightActive = highlight;
    
    if (highlight) {
        // Gray out everything except unsearched nodes
        const allNodes = nodes.get();
        const updates = [];
        let unsearchedCount = 0;
        
        allNodes.forEach(node => {
            const nodeKey = `${node.id}_${node.type}_${node.data?.value || node.data?.label || node.label}`;
            const hasBeenSearched = nodeExpansionCache.has(nodeKey);
            
            if (hasBeenSearched) {
                // Gray out searched nodes
                updates.push({
                    id: node.id,
                    color: {
                        background: '#222222',
                        border: '#444444',
                        highlight: {
                            background: '#333333',
                            border: '#555555'
                        }
                    },
                    font: {
                        color: '#666666',
                        size: 12,
                        face: 'monospace'
                    }
                });
            } else {
                // Keep unsearched nodes bright
                const borderColor = getNodeColor(node.type);
                updates.push({
                    id: node.id,
                    color: {
                        background: '#000000',
                        border: borderColor,
                        highlight: {
                            background: '#1a1a1a',
                            border: borderColor
                        }
                    },
                    font: {
                        color: '#666666',
                        size: 12,
                        face: 'monospace'
                    }
                });
                unsearchedCount++;
            }
        });
        
        nodes.update(updates);
        updateStatus(`Highlighting ${unsearchedCount} unsearched nodes (${allNodes.length - unsearchedCount} searched)`);
    } else {
        // Restore normal colors
        fixStuckFocus();
        updateStatus('Normal view restored');
    }
}

// Generate phone number variations for OSINT Industries search
async function generatePhoneVariations(phoneNumber) {
    const prompt = `You are a phone number analysis expert. Given a phone number, generate ALL possible variations that might be used on social platforms or online services for OSINT Industries search.

Phone Number: "${phoneNumber}"

Generate comprehensive variations including:
1. WITH and WITHOUT country codes (+1, +44, +33, +49, etc.)
2. WITH and WITHOUT the + symbol
3. WITH and WITHOUT leading 0 for local numbers
4. ALL common country codes (US +1, UK +44, France +33, Germany +49, Italy +39, Spain +34, Netherlands +31, Belgium +32, Switzerland +41, Austria +43, Denmark +45, Sweden +46, Norway +47, Poland +48, Czech +420, Slovakia +421)
5. Different formatting (spaces, dashes, dots, parentheses, no formatting)
6. Both 00XX and +XX international prefixes

IMPORTANT: For each phone number, try:
- Original format
- With/without +
- With/without leading 0
- With every major country code
- Multiple formatting styles

Generate 15-25 variations to maximize OSINT search coverage.

Format as JSON array of strings:
["variation1", "variation2", "variation3", ...]`;

    try {
        const response = await fetch('/api/ai-suggestions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                model: 'claude-sonnet-4-20250514',
                max_tokens: 500,
                temperature: 0.3,
                messages: [
                    {
                        role: 'user',
                        content: prompt
                    }
                ]
            })
        });

        if (!response.ok) {
            throw new Error('AI service unavailable for phone variations');
        }

        const data = await response.json();
        const content = data.content?.[0]?.text || data.response;
        
        try {
            // Parse the JSON array from Claude's response
            const variations = JSON.parse(content);
            if (Array.isArray(variations)) {
                return variations;
            }
        } catch (parseError) {
            console.warn('Failed to parse phone variations JSON:', content);
        }
        
        // Fallback: generate basic variations manually
        return generateBasicPhoneVariations(phoneNumber);
        
    } catch (error) {
        console.warn('AI phone variation generation failed:', error);
        // Fallback to basic variations
        return generateBasicPhoneVariations(phoneNumber);
    }
}

// Generate comprehensive phone variations as fallback
function generateBasicPhoneVariations(phoneNumber) {
    const variations = [];
    let cleanNumber = phoneNumber.replace(/[^\d+]/g, '');
    
    // Add original
    variations.push(phoneNumber);
    variations.push(cleanNumber);
    
    // Extract digits only for processing
    const digitsOnly = cleanNumber.replace(/[^\d]/g, '');
    
    // Common country codes to try
    const countryCodes = ['1', '44', '33', '49', '39', '34', '31', '32', '41', '43', '45', '46', '47', '48', '420', '421'];
    
    if (cleanNumber.startsWith('+')) {
        // Has + prefix - generate variations without +
        const withoutPlus = cleanNumber.substring(1);
        variations.push(withoutPlus);
        
        // Find the country code and generate local variations
        for (const cc of countryCodes) {
            if (cleanNumber.startsWith(`+${cc}`)) {
                const localNumber = cleanNumber.substring(cc.length + 1);
                
                // Add local number variations
                variations.push(localNumber);
                variations.push('0' + localNumber); // With leading 0
                
                // Add without country code but keep original format
                if (phoneNumber.includes(' ') || phoneNumber.includes('-') || phoneNumber.includes('.')) {
                    const formattedLocal = phoneNumber.substring(phoneNumber.indexOf(cc) + cc.length);
                    variations.push(formattedLocal);
                    variations.push('0' + formattedLocal);
                }
                break;
            }
        }
    } else if (cleanNumber.startsWith('0')) {
        // Has leading 0 - try with country codes and without 0
        const withoutZero = cleanNumber.substring(1);
        variations.push(withoutZero);
        
        // Try common country codes
        countryCodes.forEach(cc => {
            variations.push(`+${cc}${withoutZero}`);
            variations.push(`${cc}${withoutZero}`);
        });
        
        // Special handling for common patterns
        if (digitsOnly.length === 11) { // UK format
            variations.push(`+44${withoutZero}`);
            variations.push(`0044${withoutZero}`);
        }
    } else {
        // No + or leading 0 - try both
        variations.push('0' + cleanNumber);
        variations.push('+' + cleanNumber);
        
        // Try as local number with country codes
        countryCodes.forEach(cc => {
            variations.push(`+${cc}${cleanNumber}`);
            variations.push(`${cc}${cleanNumber}`);
        });
        
        // If it looks like a number with country code already
        if (digitsOnly.length >= 10) {
            for (const cc of countryCodes) {
                if (digitsOnly.startsWith(cc)) {
                    const localPart = digitsOnly.substring(cc.length);
                    variations.push(`+${cc}${localPart}`);
                    variations.push(`0${localPart}`);
                    variations.push(localPart);
                    break;
                }
            }
        }
    }
    
    // Add formatted variations (with spaces, dashes, dots, parentheses)
    const baseVariations = [...variations];
    baseVariations.forEach(variant => {
        const digits = variant.replace(/[^\d+]/g, '');
        if (digits.length >= 10) {
            // Add common formatting patterns
            if (digits.startsWith('+1') || digits.startsWith('1')) {
                // US format: +1 (XXX) XXX-XXXX
                const d = digits.replace(/^\+?1/, '');
                if (d.length === 10) {
                    variations.push(`+1 (${d.slice(0,3)}) ${d.slice(3,6)}-${d.slice(6)}`);
                    variations.push(`(${d.slice(0,3)}) ${d.slice(3,6)}-${d.slice(6)}`);
                    variations.push(`${d.slice(0,3)}-${d.slice(3,6)}-${d.slice(6)}`);
                    variations.push(`${d.slice(0,3)}.${d.slice(3,6)}.${d.slice(6)}`);
                }
            }
            // Add space formatting for any number
            if (digits.length >= 10) {
                const d = digits.replace(/^\+/, '');
                variations.push(d.replace(/(\d{3})(\d{3})(\d{4})/, '$1 $2 $3'));
                variations.push(d.replace(/(\d{3})(\d{3})(\d{4})/, '$1-$2-$3'));
                variations.push(d.replace(/(\d{3})(\d{3})(\d{4})/, '$1.$2.$3'));
            }
        }
    });
    
    // Remove duplicates and empty strings
    return [...new Set(variations.filter(v => v && v.length > 5))];
}

// Generate AI search suggestions for a node
async function generateAISuggestions(nodeValue, nodeType) {
    const prompt = `You are a cybersecurity investigator assistant. Given a piece of data from a breach, suggest search variations that might find related information in other breaches.

Data: "${nodeValue}"
Type: ${nodeType}

Generate realistic variations that investigators commonly search for. For each suggestion, provide:
1. The search query
2. Brief reason why this variant might exist

Rules:
- For names: try firstname lastname, lastname firstname, no spaces, dots, underscores, nicknames, initials, middle names
- For emails: Extract the username part, try it alone, with numbers, common variations. DO NOT suggest common domain names like yahoo.com, gmail.com etc as standalone searches - focus on the username part and unique patterns
- For usernames: try with numbers, without numbers, common variations, email formats, year suffixes, prefixes
- For phones: try different formats, country codes, without formatting, area codes only, last 4 digits
- For passwords: try common patterns, year variations, similar strings, l33t speak variations
- Generate EXACTLY 10 suggestions (be generous with variations)
- Focus on practical variations that actually occur in breaches
- Include both likely and creative variations
- Be concise with explanations
- IMPORTANT: Never suggest common email domains (gmail.com, yahoo.com, hotmail.com, etc.) as standalone searches

Format as JSON array:
[{"query": "search_term", "reason": "brief explanation", "type": "suggested_search_type"}]`;

    try {
        // Using Anthropic API with Claude Sonnet 4
        const response = await fetch('/api/ai-suggestions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                model: 'claude-sonnet-4-20250514', // Claude Sonnet 4
                max_tokens: 1000,
                temperature: 0.7,
                messages: [
                    {
                        role: 'user',
                        content: prompt
                    }
                ]
            })
        });

        if (!response.ok) {
            if (response.status === 503) {
                throw new Error('Claude API is temporarily overloaded. Please try again in a few moments.');
            } else {
                throw new Error(`AI service error: ${response.status} ${response.statusText}`);
            }
        }

        const data = await response.json();
        
        // Parse the response content as JSON
        const content = data.content?.[0]?.text || data.response;
        return JSON.parse(content);
    } catch (error) {
        console.error('AI suggestion error:', error);
        
        // Fallback: Generate basic suggestions locally
        return generateFallbackSuggestions(nodeValue, nodeType);
    }
}

// Fallback suggestions when AI is unavailable
function generateFallbackSuggestions(value, type) {
    const suggestions = [];
    
    switch (type) {
        case 'name':
            const nameParts = value.split(' ');
            if (nameParts.length >= 2) {
                const first = nameParts[0];
                const last = nameParts[nameParts.length - 1];
                suggestions.push(
                    { query: nameParts.reverse().join(' '), reason: 'Last name first format', type: 'name' },
                    { query: nameParts.join(''), reason: 'No spaces', type: 'username' },
                    { query: nameParts.join('.'), reason: 'Dot separated', type: 'username' },
                    { query: nameParts.join('_'), reason: 'Underscore separated', type: 'username' },
                    { query: nameParts.join('-'), reason: 'Hyphen separated', type: 'username' },
                    { query: first.toLowerCase() + last.toLowerCase(), reason: 'Lowercase concatenated', type: 'username' },
                    { query: first[0] + last, reason: 'First initial + last name', type: 'username' },
                    { query: first + last[0], reason: 'First name + last initial', type: 'username' },
                    { query: last + first, reason: 'Reversed no space', type: 'username' },
                    { query: first + '.' + last + '@gmail.com', reason: 'Common email pattern', type: 'email' }
                );
            }
            break;
            
        case 'email':
            const [username, domain] = value.split('@');
            if (username && domain) {
                // Only suggest domain if it's not a common one
                const commonDomains = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'aol.com', 'msn.com'];
                const shouldSuggestDomain = !commonDomains.includes(domain.toLowerCase());
                
                suggestions.push(
                    { query: username, reason: 'Username part only', type: 'username' },
                    { query: username.replace(/[._]/g, ''), reason: 'Username without separators', type: 'username' },
                    { query: username + '123', reason: 'Username with numbers', type: 'username' },
                    { query: username + '2024', reason: 'Username with current year', type: 'username' },
                    { query: username + '2023', reason: 'Username with last year', type: 'username' },
                    { query: username + '_', reason: 'Username with underscore', type: 'username' },
                    { query: username.toLowerCase(), reason: 'Lowercase username', type: 'username' },
                    { query: username.charAt(0) + username.slice(1).toLowerCase(), reason: 'Capitalized username', type: 'username' },
                    { query: value.replace('@', ''), reason: 'Email without @ symbol', type: 'username' }
                );
                
                // Only add domain suggestion if it's unique/interesting
                if (shouldSuggestDomain) {
                    suggestions.push({ query: domain, reason: 'Unique domain', type: 'domain' });
                } else {
                    // Add another username variation instead
                    suggestions.push({ query: username + '1', reason: 'Username with single digit', type: 'username' });
                }
            }
            break;
            
        case 'username':
            suggestions.push(
                { query: value + '@gmail.com', reason: 'Gmail format', type: 'email' },
                { query: value + '@yahoo.com', reason: 'Yahoo format', type: 'email' },
                { query: value + '@hotmail.com', reason: 'Hotmail format', type: 'email' },
                { query: value + '@outlook.com', reason: 'Outlook format', type: 'email' },
                { query: value.replace(/\d+$/, ''), reason: 'Without trailing numbers', type: 'username' },
                { query: value + '123', reason: 'Common number suffix', type: 'username' },
                { query: value + '2024', reason: 'Current year suffix', type: 'username' },
                { query: value + '_', reason: 'With underscore suffix', type: 'username' },
                { query: value.toLowerCase(), reason: 'Lowercase variant', type: 'username' },
                { query: value.toUpperCase(), reason: 'Uppercase variant', type: 'username' }
            );
            break;
            
        case 'phone':
            const digits = value.replace(/\D/g, '');
            if (digits.length >= 10) {
                suggestions.push(
                    { query: digits, reason: 'Digits only', type: 'phone' },
                    { query: `+1${digits}`, reason: 'With country code', type: 'phone' },
                    { query: digits.slice(-10), reason: 'Last 10 digits', type: 'phone' }
                );
            }
            break;
    }
    
    return suggestions.slice(0, 8); // Limit to 8 suggestions
}

// Toggle anchor state for a single node
window.toggleAnchorNode = function(nodeId) {
    selectedNodes.clear();
    selectedNodes.add(nodeId);
    anchorSelectedNodes();
}

// Anchor selected nodes
window.anchorSelectedNodes = function() {
    if (selectedNodes.size === 0) return;
    
    // Toggle anchor state for selected nodes
    const allNodes = nodes.get();
    const updates = [];
    let anchorCount = 0;
    let unanchorCount = 0;
    
    // Check if ALL selected nodes are already anchored
    let allAlreadyAnchored = true;
    selectedNodes.forEach(nodeId => {
        if (!anchoredNodes.has(nodeId)) {
            allAlreadyAnchored = false;
        }
    });
    
    if (allAlreadyAnchored) {
        // If ALL are anchored, unanchor them all
        selectedNodes.forEach(nodeId => {
            anchoredNodes.delete(nodeId);
            unanchorCount++;
            
            const node = nodes.get(nodeId);
            if (node) {
                const color = getNodeColor(node.type);
                updates.push({
                    id: nodeId,
                    color: {
                        background: '#000000',  // Back to black
                        border: color,
                        highlight: {
                            background: '#1a1a1a',
                            border: color
                        }
                    },
                    font: {
                        color: '#666666',  // Back to green text
                        size: 12,  // FORCE back to normal size
                        bold: false,  // Remove bold
                        face: 'monospace'  // Ensure monospace
                    }
                });
            }
        });
    } else {
        // If ANY are not anchored, anchor ALL of them (keep already anchored ones anchored)
        selectedNodes.forEach(nodeId => {
            if (!anchoredNodes.has(nodeId)) {
                // Only anchor the ones that aren't already anchored
                anchoredNodes.add(nodeId);
                anchorCount++;
                
                const node = nodes.get(nodeId);
                if (node) {
                    const typeColor = getNodeColor(node.type);
                    updates.push({
                        id: nodeId,
                        color: {
                            background: '#000000',  // Black background
                            border: typeColor,
                            highlight: {
                                background: '#1a1a1a',
                                border: typeColor
                            }
                        },
                        font: {
                            color: '#FFFFFF',  // White text only
                            size: 18,  // 1.5x bigger font ONLY
                            bold: true  // THICK/BOLD text only
                        }
                    });
                }
            }
            // Already anchored nodes stay anchored - no changes needed
        });
    }
    
    // Apply updates
    if (updates.length > 0) {
        nodes.update(updates);
        
        // Update edges between anchored nodes
        const allEdges = edges.get();
        const edgeUpdates = [];
        
        allEdges.forEach(edge => {
            // Get the original edge data
            const originalEdge = edges.get(edge.id);
            
            if (anchoredNodes.has(edge.from) && anchoredNodes.has(edge.to)) {
                // Both nodes are anchored - make edge thick white
                edgeUpdates.push({
                    id: edge.id,
                    ...getConnectionStyle('ANCHORED')
                });
            } else if ((anchoredNodes.has(edge.from) || anchoredNodes.has(edge.to)) && 
                       (selectedNodes.has(edge.from) || selectedNodes.has(edge.to))) {
                // One node was just unanchored - restore to dotted grey
                edgeUpdates.push({
                    id: edge.id,
                    ...getConnectionStyle('DEFAULT')
                });
            }
        });
        
        if (edgeUpdates.length > 0) {
            edges.update(edgeUpdates);
        }
        
        // Force refresh to ensure changes take effect
        setTimeout(() => {
            network.redraw();
        }, 100);
    }
    
    // Update button text
    const anchorBtn = document.getElementById('anchorSelectedBtn');
    if (anchorCount > 0) {
        updateStatus(`Anchored ${anchorCount} node${anchorCount > 1 ? 's' : ''}`);
        anchorBtn.textContent = `Unanchor ${selectedNodes.size} Node${selectedNodes.size > 1 ? 's' : ''}`;
    } else if (unanchorCount > 0) {
        updateStatus(`Unanchored ${unanchorCount} node${unanchorCount > 1 ? 's' : ''}`);
        anchorBtn.textContent = `Anchor ${selectedNodes.size} Node${selectedNodes.size > 1 ? 's' : ''}`;
    }
    
    // Save state
    saveGraphState();
    
    // Update anchored highlight if active
    const highlightCheckbox = document.getElementById('highlightAnchored');
    if (highlightCheckbox && highlightCheckbox.checked) {
        toggleAnchoredHighlight(true);
    }
}

// Toggle highlighting of anchored nodes
window.toggleAnchoredHighlight = function(highlight) {
    if (highlight) {
        // Fade all non-anchored nodes and highlight anchored connections
        const allNodes = nodes.get();
        const nodeUpdates = [];
        let anchoredCount = 0;
        
        allNodes.forEach(node => {
            if (anchoredNodes.has(node.id)) {
                // Anchored nodes in highlight mode - still just background change
                anchoredCount++;
                const typeColor = getNodeColor(node.type);
                nodeUpdates.push({
                    id: node.id,
                    borderWidth: 2,  // NORMAL border even in highlight
                    borderWidthSelected: 3,  // NORMAL selected border
                    color: {
                        background: '#000000',  // Black background
                        border: typeColor,
                        highlight: {
                            background: '#1a1a1a',
                            border: typeColor
                        }
                    },
                    font: {
                        color: '#FFFFFF'  // White text
                    }
                });
            } else {
                // Fade non-anchored nodes
                nodeUpdates.push({
                    id: node.id,
                    borderWidth: 1,
                    color: {
                        background: '#0a0a0a',
                        border: '#222222',
                        highlight: {
                            background: '#1a1a1a',
                            border: '#333333'
                        }
                    },
                    font: {
                        color: '#333333',
                        size: 10
                    },
                    shadow: false
                });
            }
        });
        
        nodes.update(nodeUpdates);
        
        // Highlight edges between anchored nodes
        const allEdges = edges.get();
        const edgeUpdates = [];
        
        allEdges.forEach(edge => {
            if (anchoredNodes.has(edge.from) && anchoredNodes.has(edge.to)) {
                // Keep normal appearance for edges between anchored nodes
                edgeUpdates.push({
                    id: edge.id,
                    width: edge.title && edge.title.includes('Same breach') ? 3 : 2,
                    color: {
                        color: '#00FF00',  // Keep normal green
                        highlight: '#FF0000'
                    },
                    shadow: false
                });
            } else {
                // Fade other edges
                edgeUpdates.push({
                    id: edge.id,
                    width: 1,
                    color: {
                        color: '#222222',
                        highlight: '#333333'
                    },
                    shadow: false
                });
            }
        });
        
        edges.update(edgeUpdates);
        updateStatus(`Highlighting ${anchoredCount} anchored nodes and their connections`);
    } else {
        // Restore normal view
        fixStuckFocus();
        
        // Restore anchored nodes with ONLY background color changed
        const updates = [];
        anchoredNodes.forEach(nodeId => {
            const node = nodes.get(nodeId);
            if (node) {
                const typeColor = getNodeColor(node.type);
                updates.push({
                    id: nodeId,
                    color: {
                        background: '#000000',  // Black background
                        border: typeColor,
                        highlight: {
                            background: '#1a1a1a',
                            border: typeColor
                        }
                    },
                    font: {
                        color: '#FFFFFF',  // White text only
                        size: 18,  // 1.5x bigger font ONLY
                        bold: true  // THICK/BOLD text only
                    }
                });
            }
        });
        
        if (updates.length > 0) {
            nodes.update(updates);
        }
        
        // Restore normal edge appearance
        const allEdges = edges.get();
        const edgeUpdates = allEdges.map(edge => ({
            id: edge.id,
            width: edge.title && edge.title.includes('Same breach') ? 3 : 2,
            color: edge.color || { color: '#666666', highlight: '#ff0000' },
            shadow: { enabled: false }
        }));
        
        edges.update(edgeUpdates);
        
        updateStatus('Normal view restored');
    }
}

// Show AI suggestions modal
function showAISuggestionsModal(suggestions, originalNode) {
    const modal = document.createElement('div');
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.8);
        z-index: 2000;
        display: flex;
        justify-content: center;
        align-items: center;
    `;
    
    const content = document.createElement('div');
    content.style.cssText = `
        background: #000;
        border: 2px solid #0f0;
        padding: 20px;
        max-width: 600px;
        max-height: 80vh;
        overflow-y: auto;
        color: #0f0;
        font-family: monospace;
    `;
    
    // Get previously run searches for this node
    const previousSearches = [];
    nodeSearchQueries.forEach((searchData, searchKey) => {
        if (searchData.sourceNode === originalNode.id) {
            previousSearches.push({
                query: searchData.query,
                timestamp: searchData.timestamp,
                results: searchData.results.length
            });
        }
    });
    
    let html = `
        <h3 style="color: #0f0; margin-bottom: 15px;">Search Variations for: ${escapeHtml(originalNode.label)}</h3>
        <p style="color: #888; margin-bottom: 20px;">Select variations to search for:</p>
    `;
    
    // Show previously run searches
    if (previousSearches.length > 0) {
        html += `
            <div style="margin-bottom: 20px; padding: 10px; background: #001100; border: 1px solid #003300;">
                <h4 style="color: #ffff00; margin: 0 0 10px 0;">Previously Run Searches:</h4>
        `;
        previousSearches.forEach(search => {
            const date = new Date(search.timestamp).toLocaleString();
            html += `
                <div style="margin: 5px 0; padding: 5px; background: #000; border-left: 3px solid #666;">
                    <span style="color: #888;">${escapeHtml(search.query)}</span> 
                    <small style="color: #666;">(${search.results} results on ${date})</small>
                </div>
            `;
        });
        html += `</div>`;
    }
    
    // Add WHOIS search as first option if applicable
    const allSuggestions = [];
    const whoisQuery = originalNode.data.value || originalNode.label;
    const isWhoisEligible = isWhoisCandidate(whoisQuery, originalNode.type);
    console.log('WHOIS check:', {
        query: whoisQuery,
        type: originalNode.type,
        isEligible: isWhoisEligible
    });
    
    // Special options for domain nodes
    if (originalNode.type === 'domain') {
        allSuggestions.push({
            query: whoisQuery,
            reason: '🌐 Full WHOIS history search - Extract all contacts, emails, phones, addresses from historical records',
            type: 'domain_whois',
            isDomainWhois: true
        });
        allSuggestions.push({
            query: `@${whoisQuery}`,
            reason: '📧 Search for all email addresses using this domain in breach databases',
            type: 'email',
            isDomainEmailSearch: true
        });
    } else if (isWhoisEligible) {
        allSuggestions.push({
            query: whoisQuery,
            reason: 'Search WHOIS database for domain registrations and contact info',
            type: 'whois',
            isWhois: true
        });
    }
    
    // Add OSINT Industries search for email and phone nodes
    if (originalNode.type === 'email' || originalNode.type === 'phone') {
        allSuggestions.push({
            query: whoisQuery,
            reason: `🔍 OSINT Industries search - Find social profiles, accounts, and additional data for this ${originalNode.type}`,
            type: 'osint',
            isOSINT: true
        });
    }
    
    allSuggestions.push(...suggestions);
    
    // AI suggestions
    if (allSuggestions.length > 0) {
        html += `<h4 style="color: #00ff00; margin: 10px 0;">Search Suggestions:</h4>`;
        html += `
            <div style="margin-bottom: 10px;">
                <button onclick="selectAllSuggestions(true)" style="background: #444; color: white; border: none; padding: 5px 15px; margin-right: 10px; border-radius: 3px; cursor: pointer;">Select All</button>
                <button onclick="selectAllSuggestions(false)" style="background: #444; color: white; border: none; padding: 5px 15px; border-radius: 3px; cursor: pointer;">Deselect All</button>
            </div>
        `;
        allSuggestions.forEach((suggestion, index) => {
            const nodeColor = suggestion.isWhois ? '#20B2AA' : suggestion.isOSINT ? '#ff6600' : getNodeColor(suggestion.type);
            const icon = suggestion.isWhois ? '🌐 ' : suggestion.isOSINT ? '🔍 ' : '';
            html += `
                <label style="display: block; margin: 10px 0; padding: 10px; border: 1px solid #333; cursor: pointer; ${suggestion.isWhois ? 'background: #002222;' : suggestion.isOSINT ? 'background: #221100;' : ''}">
                    <input type="checkbox" id="suggestion-${index}" checked style="margin-right: 10px;" data-is-whois="${suggestion.isWhois || false}" data-is-osint="${suggestion.isOSINT || false}">
                    <strong style="color: ${nodeColor}">${icon}${escapeHtml(suggestion.query)}</strong>
                    <span style="color: #888; margin-left: 10px;">(${suggestion.type})</span>
                    <br>
                    <small style="color: #666; margin-left: 25px;">${escapeHtml(suggestion.reason)}</small>
                </label>
            `;
        });
    }
    
    // Custom variations section
    html += `
        <div style="margin-top: 20px; padding: 10px; background: #000011; border: 1px solid #000033;">
            <h4 style="color: #66ff66; margin: 0 0 10px 0;">Add Custom Variations:</h4>
            <div id="custom-variations">
                <div style="display: flex; gap: 10px; margin-bottom: 10px;">
                    <input type="text" id="custom-query-0" placeholder="Enter search variation..." style="flex: 1; background: #000; color: #0f0; border: 1px solid #0f0; padding: 5px; font-family: monospace;">
                    <select id="custom-type-0" style="background: #000; color: #0f0; border: 1px solid #0f0; padding: 5px;">
                        <option value="">Auto</option>
                        <option value="email">Email</option>
                        <option value="username">Username</option>
                        <option value="password">Password</option>
                        <option value="phone">Phone</option>
                        <option value="ip_address">IP</option>
                        <option value="domain">Domain</option>
                        <option value="name">Name</option>
                    </select>
                </div>
            </div>
            <button onclick="addCustomVariation()" style="padding: 5px 10px; margin-right: 10px;">Add Another</button>
        </div>
        
        <div style="margin-top: 20px; display: flex; gap: 10px;">
            <button onclick="executeAISuggestions()" style="flex: 1;">Search Selected</button>
            <button onclick="cancelAISuggestions()" style="flex: 1;">Cancel</button>
        </div>
    `;
    
    content.innerHTML = html;
    modal.appendChild(content);
    document.body.appendChild(modal);
    
    // Store suggestions for execution
    window.currentAISuggestions = suggestions;
    window.currentAllSuggestions = allSuggestions; // Store the complete list including WHOIS
    window.currentOriginalNode = originalNode;
}

// Add custom variation input
window.addCustomVariation = function() {
    const container = document.getElementById('custom-variations');
    const count = container.children.length;
    
    const newVariation = document.createElement('div');
    newVariation.style.cssText = 'display: flex; gap: 10px; margin-bottom: 10px;';
    newVariation.innerHTML = `
        <input type="text" id="custom-query-${count}" placeholder="Enter search variation..." style="flex: 1; background: #000; color: #0f0; border: 1px solid #0f0; padding: 5px; font-family: monospace;">
        <select id="custom-type-${count}" style="background: #000; color: #0f0; border: 1px solid #0f0; padding: 5px;">
            <option value="">Auto</option>
            <option value="email">Email</option>
            <option value="username">Username</option>
            <option value="password">Password</option>
            <option value="phone">Phone</option>
            <option value="ip_address">IP</option>
            <option value="domain">Domain</option>
            <option value="name">Name</option>
        </select>
        <button onclick="this.parentElement.remove()" style="background: #660000; color: #ff0000; border: 1px solid #ff0000; padding: 5px;">×</button>
    `;
    
    container.appendChild(newVariation);
}

// Cancel AI suggestions modal
window.cancelAISuggestions = function() {
    const modal = document.querySelector('[style*="position: fixed"]');
    if (modal) {
        modal.remove();
    }
    updateStatus('AI suggestions cancelled');
}

// Execute selected AI suggestions
window.executeAISuggestions = function() {
    // Find and immediately close the modal
    const modal = document.querySelector('[style*="position: fixed"]');
    if (!modal) {
        console.error('No modal found to close');
        return;
    }
    
    const selectedSuggestions = [];
    
    // Build the complete suggestions list (same as in showAISuggestionsModal)
    const allSuggestions = [];
    const whoisQuery = window.currentOriginalNode.data.value || window.currentOriginalNode.label;
    
    // Special options for domain nodes
    if (window.currentOriginalNode.type === 'domain') {
        allSuggestions.push({
            query: whoisQuery,
            reason: '🌐 Full WHOIS history search - Extract all contacts, emails, phones, addresses from historical records',
            type: 'domain_whois',
            isDomainWhois: true
        });
        allSuggestions.push({
            query: `@${whoisQuery}`,
            reason: '📧 Search for all email addresses using this domain in breach databases',
            type: 'email',
            isDomainEmailSearch: true
        });
    } else if (isWhoisCandidate(whoisQuery, window.currentOriginalNode.type)) {
        allSuggestions.push({
            query: whoisQuery,
            reason: 'Search WHOIS database for domain registrations and contact info',
            type: 'whois',
            isWhois: true
        });
    }
    
    // Add OSINT Industries search for email and phone nodes
    if (window.currentOriginalNode.type === 'email' || window.currentOriginalNode.type === 'phone') {
        allSuggestions.push({
            query: whoisQuery,
            reason: `🔍 OSINT Industries search - Find social profiles, accounts, and additional data for this ${window.currentOriginalNode.type}`,
            type: 'osint',
            isOSINT: true
        });
    }
    
    allSuggestions.push(...(window.currentAISuggestions || []));
    
    // Get selected suggestions BEFORE closing modal
    allSuggestions.forEach((suggestion, index) => {
        const checkbox = document.getElementById(`suggestion-${index}`);
        if (checkbox && checkbox.checked) {
            selectedSuggestions.push(suggestion);
        }
    });
    
    // Get custom variations BEFORE closing modal
    const customContainer = document.getElementById('custom-variations');
    if (customContainer) {
        for (let i = 0; i < customContainer.children.length; i++) {
            const queryInput = document.getElementById(`custom-query-${i}`);
            const typeSelect = document.getElementById(`custom-type-${i}`);
            
            if (queryInput && queryInput.value.trim()) {
                selectedSuggestions.push({
                    query: queryInput.value.trim(),
                    type: typeSelect ? typeSelect.value : '',
                    reason: 'Custom user variation'
                });
            }
        }
    }
    
    // NOW close the modal immediately
    modal.remove();
    console.log('AI suggestions modal closed, starting searches...');
    
    if (selectedSuggestions.length === 0) {
        updateStatus('No variations selected');
        return;
    }
    
    updateStatus(`Searching for ${selectedSuggestions.length} AI suggestions...`);
    
    // Execute searches sequentially with delay
    let searchIndex = 0;
    const executeNext = async () => {
        if (searchIndex >= selectedSuggestions.length) {
            updateStatus(`Completed ${selectedSuggestions.length} AI-suggested searches`);
            return;
        }
        
        const suggestion = selectedSuggestions[searchIndex];
        updateStatus(`AI Search ${searchIndex + 1}/${selectedSuggestions.length}: ${suggestion.query}`);
        
        // Check search type
        if (suggestion.isDomainWhois) {
            // Full domain WHOIS history search
            console.log('Performing full WHOIS history search for domain:', suggestion.query);
            updateStatus(`🌐 Searching WHOIS history for ${suggestion.query}...`);
            try {
                const whoisData = await performWhoisSearch(suggestion.query, 'domain');
                console.log('WHOIS search result:', whoisData);
                if (whoisData && whoisData.results && whoisData.results.length > 0) {
                    await showWhoisResultsDialog(whoisData, suggestion.query, window.currentOriginalNode.id);
                } else {
                    updateStatus('No WHOIS history found');
                }
            } catch (error) {
                console.error('WHOIS search error:', error);
                updateStatus('WHOIS search failed: ' + error.message);
            }
        } else if (suggestion.isDomainEmailSearch) {
            // Search for emails with this domain
            console.log('Searching for emails with domain:', suggestion.query);
            await performSearch(suggestion.query, 'email', window.currentOriginalNode.id);
        } else if (suggestion.isWhois) {
            // Regular WHOIS search
            console.log('Performing WHOIS search for:', suggestion.query, 'with type:', window.currentOriginalNode.type);
            updateStatus(`🌐 Searching WHOIS for ${suggestion.query}...`);
            try {
                const whoisData = await performWhoisSearch(suggestion.query, window.currentOriginalNode.type);
                console.log('WHOIS search result:', whoisData);
                if (whoisData && whoisData.results && whoisData.results.length > 0) {
                    await showWhoisResultsDialog(whoisData, suggestion.query, window.currentOriginalNode.id);
                } else {
                    updateStatus('No WHOIS results found');
                    console.log('No WHOIS results in data:', whoisData);
                }
            } catch (error) {
                console.error('WHOIS search error:', error);
                updateStatus('WHOIS search failed: ' + error.message);
            }
        } else {
            await performSearch(suggestion.query, suggestion.type, window.currentOriginalNode.id);
        }
        
        searchIndex++;
        setTimeout(executeNext, 1000); // 1 second delay between searches
    };
    
    executeNext();
}

// Chat interface functionality
let chatHistory = [];
// Update chat input to show selected nodes
function updateChatInputWithSelection() {
    const chatInput = document.getElementById('chat-input');
    if (!chatInput) return;
    
    if (selectedNodes.size === 0) {
        chatInput.placeholder = "Ask AI about connections, patterns, or observations...";
        chatInput.value = chatInput.value.replace(/^Selected: [^:]+: /, '');
    } else {
        const selectedLabels = Array.from(selectedNodes).map(nodeId => {
            const node = nodes.get(nodeId);
            return node ? node.label : nodeId;
        });
        
        const selectionText = selectedLabels.length === 1 
            ? selectedLabels[0] 
            : `${selectedLabels.length} nodes (${selectedLabels.slice(0, 2).join(', ')}${selectedLabels.length > 2 ? '...' : ''})`;
            
        chatInput.placeholder = `Ask about selected: ${selectionText}`;
        
        // Add selection prefix to input if user hasn't typed yet
        if (!chatInput.value || chatInput.value.startsWith('Selected: ')) {
            chatInput.value = `Selected: ${selectionText}: `;
        }
    }
}

// Toggle chat visibility
window.toggleChatVisibility = function() {
    const chatContainer = document.getElementById('ai-chat-container');
    const minimizedBar = document.getElementById('ai-chat-minimized');
    const toggleButton = document.getElementById('toggle-chat');
    
    if (chatContainer.style.display === 'none') {
        // Show the full chat
        chatContainer.style.display = 'flex';
        minimizedBar.style.display = 'none';
        if (toggleButton) toggleButton.textContent = 'Hide';
    } else {
        // Hide the full chat and show minimized bar
        chatContainer.style.display = 'none';
        minimizedBar.style.display = 'block';
        if (toggleButton) toggleButton.textContent = 'Show';
    }
}

// Toggle select all nodes for AI context
window.toggleSelectAllNodes = function(selectAll) {
    const allNodes = nodes.get();
    const visibleNodes = allNodes.filter(node => !node.hidden);
    
    if (selectAll) {
        // Select all visible nodes
        selectedNodes.clear();
        visibleNodes.forEach(node => {
            selectedNodes.add(node.id);
        });
        network.setSelection({ nodes: Array.from(selectedNodes) });
        updateStatus(`Selected all ${selectedNodes.size} visible nodes for AI context`);
    } else {
        // Deselect all nodes
        selectedNodes.clear();
        network.setSelection({ nodes: [] });
        updateStatus('Deselected all nodes');
    }
    
    // Update chat input to reflect selection
    updateChatInputWithSelection();
    
    // Update the checkbox state if it doesn't match
    const checkbox = document.getElementById('selectAllNodes');
    if (checkbox && checkbox.checked !== selectAll) {
        checkbox.checked = selectAll;
    }
}

// Send chat message
window.sendChatMessage = async function() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    
    if (!message) return;
    
    // Add user message to chat
    addChatMessage('user', message);
    input.value = '';
    
    // Show typing indicator
    addChatMessage('ai', 'Analyzing graph data...', true);
    
    try {
        // Generate graph context for AI
        const graphContext = generateGraphContext();
        
        // Send to AI
        const response = await getChatResponse(message, graphContext);
        
        // Remove typing indicator and add AI response
        removeChatMessage();
        addChatMessage('ai', response);
        
        // Auto-extract entities if an image is selected
        const selectedNodeIds = Array.from(selectedNodes);
        let imageNodeId = null;
        
        for (const nodeId of selectedNodeIds) {
            const node = nodes.get(nodeId);
            if (node && node.shape === 'image') {
                imageNodeId = nodeId;
                break;
            }
        }
        
        if (imageNodeId) {
            console.log('Image selected, auto-extracting entities from response');
            autoExtractEntitiesFromResponse(response, imageNodeId);
        }
        
    } catch (error) {
        removeChatMessage();
        addChatMessage('ai', `Error: ${error.message}. Please check the console for details.`);
        console.error('Chat error:', error);
    }
}

// Add message to chat
function addChatMessage(sender, message, isTyping = false) {
    const chatMessages = document.getElementById('chat-messages');
    const messageDiv = document.createElement('div');
    messageDiv.style.cssText = `
        margin-bottom: 10px;
        padding: 8px;
        border-radius: 4px;
        ${sender === 'user' ? 
            'background-color: #001100; border-left: 3px solid #00ff00; margin-left: 20px;' : 
            'background-color: #000011; border-left: 3px solid #0088ff; margin-right: 20px;'
        }
        ${isTyping ? 'opacity: 0.7; font-style: italic;' : ''}
    `;
    
    const senderSpan = document.createElement('span');
    senderSpan.style.cssText = `
        font-weight: bold;
        color: ${sender === 'user' ? UI_COLORS.accent : UI_COLORS.textMuted};
        font-size: 10px;
        display: block;
        margin-bottom: 5px;
    `;
    senderSpan.textContent = sender === 'user' ? 'YOU' : 'AI ASSISTANT';
    
    const messageSpan = document.createElement('span');
    messageSpan.style.color = '#cccccc';
    
    // Convert basic markdown to HTML
    let formattedMessage = message
        .replace(/\*\*(.*?)\*\*/g, '<strong style="color: #ffffff; font-weight: bold;">$1</strong>') // **bold**
        .replace(/\*(.*?)\*/g, '<em style="font-style: italic;">$1</em>') // *italic*
        .replace(/`(.*?)`/g, '<code style="background: #333; padding: 1px 3px; border-radius: 2px;">$1</code>') // `code`
        .replace(/\n/g, '<br>'); // line breaks
    
    messageSpan.innerHTML = formattedMessage;
    
    messageDiv.appendChild(senderSpan);
    messageDiv.appendChild(messageSpan);
    
    if (isTyping) {
        messageDiv.id = 'typing-indicator';
    }
    
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Remove last message (for typing indicator)
function removeChatMessage() {
    const typingIndicator = document.getElementById('typing-indicator');
    if (typingIndicator) {
        typingIndicator.remove();
    }
}

// Generate graph context for AI
function generateGraphContext() {
    const allNodes = nodes.get();
    const allEdges = edges.get();
    
    // Filter to only visible (non-hidden) nodes
    const visibleNodes = allNodes.filter(node => !node.hidden);
    const visibleEdges = allEdges.filter(edge => !edge.hidden);
    
    // Summarize visible nodes by type
    const nodesByType = {};
    visibleNodes.forEach(node => {
        if (!nodesByType[node.type]) {
            nodesByType[node.type] = [];
        }
        nodesByType[node.type].push({
            label: node.label,
            breach: node.data?.breach,
            hasBeenSearched: nodeExpansionCache.has(`${node.id}_${node.type}_${node.data?.value || node.data?.label}`)
        });
    });
    
    // Summarize connections by breach (only for visible nodes)
    const breachSummary = {};
    breachConnections.forEach((nodeIds, breachName) => {
        const visibleNodeIds = nodeIds.filter(nodeId => {
            const node = nodes.get(nodeId);
            return node && !node.hidden;
        });
        
        if (visibleNodeIds.length > 0) {
            const nodeTypes = new Set();
            visibleNodeIds.forEach(nodeId => {
                const node = nodes.get(nodeId);
                if (node) nodeTypes.add(node.type);
            });
            breachSummary[breachName] = {
                nodeCount: visibleNodeIds.length,
                types: Array.from(nodeTypes)
            };
        }
    });
    
    // Add selected node details if any nodes are selected
    const selectedNodeDetails = [];
    if (selectedNodes.size > 0) {
        Array.from(selectedNodes).forEach(nodeId => {
            const node = nodes.get(nodeId);
            if (node && !node.hidden) {
                // Get connected nodes
                const connectedEdges = edges.get({
                    filter: edge => (edge.from === nodeId || edge.to === nodeId) && !edge.hidden
                });
                
                const connectedLabels = [];
                connectedEdges.forEach(edge => {
                    const connectedId = edge.from === nodeId ? edge.to : edge.from;
                    const connectedNode = nodes.get(connectedId);
                    if (connectedNode && !connectedNode.hidden) {
                        connectedLabels.push(`${connectedNode.type}: ${connectedNode.label}`);
                    }
                });
                
                selectedNodeDetails.push({
                    id: nodeId,
                    type: node.type,
                    label: node.label,
                    value: node.data?.value || node.label,
                    breach: node.data?.breach,
                    notes: node.data?.notes,
                    variations: node.data?.variations || [],
                    connections: connectedLabels,
                    hasBeenSearched: nodeExpansionCache.has(`${node.id}_${node.type}_${node.data?.value || node.data?.label}`)
                });
            }
        });
    }
    
    return {
        totalNodes: visibleNodes.length,
        totalEdges: visibleEdges.length,
        nodesByType: nodesByType,
        breachSummary: breachSummary,
        searchedNodeCount: nodeExpansionCache.size,
        selectedNodes: selectedNodeDetails
    };
}

// Auto-extract entities from image using Claude's tool calling
async function autoExtractEntitiesFromImage(imageNodeId) {
    console.log('Auto-extracting entities from image:', imageNodeId);
    
    const imageNode = nodes.get(imageNodeId);
    if (!imageNode || !imageNode.shape === 'image') {
        console.error('Invalid image node for extraction');
        return;
    }
    
    // Get the image data
    const imageData = imageNode.data?.imageData || imageNode.image;
    if (!imageData) {
        console.error('No image data found in node');
        return;
    }
    
    try {
        updateStatus('Analyzing image with Claude...');
        
        // Call the vision API with tool calling
        const response = await fetch('/api/vision', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                image_data: imageData
            })
        });
        
        if (!response.ok) {
            throw new Error(`Vision API error: ${response.status}`);
        }
        
        const result = await response.json();
        console.log('Vision API result:', result);
        
        if (!result.success) {
            console.error('Vision API failed:', result.error);
            updateStatus('Failed to analyze image');
            return;
        }
        
        const entities = result.entities || [];
        const relationships = result.relationships || [];
        const createdNodes = new Map();
        
        // Create nodes for all entities
        for (const entity of entities) {
            const nodeResult = addNode({
                value: entity.value,
                label: entity.value,
                source: 'AI Image Extract',
                notes: entity.notes || '',
                confidence: entity.confidence || 'medium'
            }, entity.type, null, false, null, false);
            
            if (nodeResult && nodeResult.nodeId) {
                createdNodes.set(entity.value, nodeResult.nodeId);
                
                // Update node with notes and confidence
                const node = nodes.get(nodeResult.nodeId);
                if (node) {
                    nodes.update({
                        id: nodeResult.nodeId,
                        title: `${entity.type.toUpperCase()}: ${entity.value}\n${entity.notes || ''}\nConfidence: ${entity.confidence}`,
                        data: {
                            ...node.data,
                            notes: entity.notes,
                            confidence: entity.confidence
                        }
                    });
                }
                
                // Create purple SOURCE edge from image
                const edgeId = `edge_${imageNodeId}_${nodeResult.nodeId}_source`;
                if (!edges.get(edgeId)) {
                    edges.add({
                        id: edgeId,
                        from: imageNodeId,
                        to: nodeResult.nodeId,
                        ...getConnectionStyle('SOURCE'),
                        label: 'SOURCE',
                        edgeType: 'image_source',
                        hidden: !showImageSources,
                        smooth: {
                            type: 'curvedCW',
                            roundness: 0.2
                        }
                    });
                }
            }
        }
        
        // Create relationships between entities
        for (const rel of relationships) {
            // Find node IDs
            let sourceId = createdNodes.get(rel.source);
            let targetId = createdNodes.get(rel.target);
            
            // Try to find in existing nodes if not in created nodes
            if (!sourceId) {
                const sourceNodes = nodes.get({
                    filter: n => n.label && n.label === rel.source
                });
                if (sourceNodes.length > 0) sourceId = sourceNodes[0].id;
            }
            
            if (!targetId) {
                const targetNodes = nodes.get({
                    filter: n => n.label && n.label === rel.target
                });
                if (targetNodes.length > 0) targetId = targetNodes[0].id;
            }
            
            // Create relationship edge
            if (sourceId && targetId && sourceId !== targetId) {
                const edgeId = `edge_${sourceId}_${targetId}_${rel.relationship.replace(/\s+/g, '_')}`;
                if (!edges.get(edgeId)) {
                    edges.add({
                        id: edgeId,
                        from: sourceId,
                        to: targetId,
                        label: showConnectionLabels ? rel.relationship : '',
                        title: `${rel.relationship}\n${rel.notes || ''}\nConfidence: ${rel.confidence || 'medium'}`,
                        color: { color: '#00CED1' },
                        width: 2,
                        arrows: { to: { enabled: true, scaleFactor: 0.8 } },
                        font: { color: '#00CED1', size: 12 },
                        smooth: false,
                        data: {
                            notes: rel.notes,
                            confidence: rel.confidence,
                            originalLabel: rel.relationship
                        }
                    });
                    console.log(`Created relationship: ${rel.source} -> ${rel.target} [${rel.relationship}]`);
                }
            }
        }
        
        if (createdNodes.size > 0) {
            saveGraphState();
            updateStatus(`Extracted ${createdNodes.size} entities and ${relationships.length} relationships from image`);
        } else {
            updateStatus('No entities found in image');
        }
        
    } catch (error) {
        console.error('Failed to extract entities from image:', error);
        updateStatus('Failed to analyze image');
    }
}

// Select all nodes connected to the given node (for group dragging)
function selectConnectedNodes(nodeId) {
    console.log('Selecting connected nodes for:', nodeId);
    
    // Clear current selection
    selectedNodes.clear();
    
    // Add the main node
    selectedNodes.add(nodeId);
    
    // Find all connected nodes
    const allEdges = edges.get();
    const connectedNodeIds = new Set();
    
    allEdges.forEach(edge => {
        if (edge.from === nodeId) {
            connectedNodeIds.add(edge.to);
        } else if (edge.to === nodeId) {
            connectedNodeIds.add(edge.from);
        }
    });
    
    // Add connected nodes to selection
    connectedNodeIds.forEach(connectedId => {
        selectedNodes.add(connectedId);
    });
    
    // Update visual selection
    network.setSelection({
        nodes: Array.from(selectedNodes),
        edges: []
    });
    
    // Mark as group drag ready
    isGroupDrag = true;
    
    updateStatus(`Selected ${selectedNodes.size} connected nodes for group movement`);
    console.log('Selected nodes:', Array.from(selectedNodes));
}

// Toggle connection label display
window.toggleConnectionLabels = function(show) {
    showConnectionLabels = show;
    
    // Update visibility of all relationship edges
    const allEdges = edges.get();
    const updates = [];
    
    allEdges.forEach(edge => {
        // Only affect relationship edges (not SOURCE or other edge types)
        if (!edge.edgeType || edge.edgeType !== 'image_source') {
            const update = {
                id: edge.id
            };
            
            if (show) {
                // Show labels
                if (edge.data && edge.data.originalLabel) {
                    update.label = edge.data.originalLabel;
                } else if (edge.title && edge.title.includes('\n')) {
                    // Extract label from title (first line)
                    update.label = edge.title.split('\n')[0];
                }
            } else {
                // Hide labels but keep in data for hover
                if (edge.label) {
                    update.data = {
                        ...(edge.data || {}),
                        originalLabel: edge.label
                    };
                    update.label = '';
                }
            }
            
            updates.push(update);
        }
    });
    
    if (updates.length > 0) {
        edges.update(updates);
        updateStatus(show ? 'Connection labels visible' : 'Connection labels hidden');
    }
}

// Extract entities from selected image using tool calling
window.extractFromSelectedImage = async function() {
    const selectedNodeIds = Array.from(selectedNodes);
    let imageNodeId = null;
    
    // Find selected image node
    for (const nodeId of selectedNodeIds) {
        const node = nodes.get(nodeId);
        if (node && node.shape === 'image') {
            imageNodeId = nodeId;
            break;
        }
    }
    
    if (!imageNodeId) {
        alert('Please select an image node first');
        return;
    }
    
    // Call the extraction function
    await autoExtractEntitiesFromImage(imageNodeId);
}

// Get AI chat response
async function getChatResponse(userMessage, graphContext) {
    let systemPrompt = `You are a cybersecurity investigator's AI assistant analyzing breach data connections.

IMPORTANT: When extracting entities from any content (including images), carefully distinguish between:
- "name" type: Individual person names (John Doe, Jane Smith, etc.)
- "company" type: Organization/company names (Microsoft, Apple Inc, FBI, etc.)

Always use "company" type for organizations, businesses, agencies, not "name".

Current graph state (visible nodes only):
- Total visible nodes: ${graphContext.totalNodes || 0}
- Total visible connections: ${graphContext.totalEdges || 0}
- Nodes searched/expanded: ${graphContext.searchedNodeCount || 0}

Node types and counts:
${graphContext.nodesByType ? Object.entries(graphContext.nodesByType).map(([type, nodes]) => 
    `- ${type}: ${nodes.length} (${nodes.filter(n => n.hasBeenSearched).length} searched)`
).join('\n') : '- No nodes in graph'}

Breach data summary:
${graphContext.breachSummary ? Object.entries(graphContext.breachSummary).map(([breach, info]) => 
    `- ${breach}: ${info.nodeCount} items (${info.types.join(', ')})`
).join('\n') : '- No breach data available'}`;

    // Add selected node details if any are selected
    if (graphContext.selectedNodes && graphContext.selectedNodes.length > 0) {
        systemPrompt += `\n\nCURRENTLY SELECTED NODES (${graphContext.selectedNodes.length}):`;
        graphContext.selectedNodes.forEach((node, index) => {
            const nodeType = (node.type || 'unknown').toUpperCase();
            const nodeLabel = node.label || node.value || 'unlabeled';
            systemPrompt += `\n${index + 1}. ${nodeType}: "${nodeLabel}"`;
            if (node.breach) systemPrompt += `\n   - Found in breach: ${node.breach}`;
            if (node.notes) systemPrompt += `\n   - Notes: ${node.notes}`;
            if (node.variations && node.variations.length > 0) {
                systemPrompt += `\n   - Has ${node.variations.length} merged variation(s)`;
            }
            if (node.connections && node.connections.length > 0) {
                systemPrompt += `\n   - Connected to: ${node.connections.slice(0, 5).join(', ')}${node.connections.length > 5 ? '...' : ''}`;
            }
            systemPrompt += `\n   - Searched: ${node.hasBeenSearched ? 'Yes' : 'No'}`;
        });
        
        systemPrompt += `\n\nThe user is asking about these selected nodes. Focus your analysis on them and their relationships.`;
    }

    systemPrompt += `\n\nProvide insights about:
- Patterns you notice in the data
- Potential investigation leads
- Relationships between different data types
- Anomalies or interesting connections
- Suggested next steps for investigation

Be concise but insightful. Focus on actionable intelligence.

When analyzing images, remind the user to use the "Extract From Image" button for structured entity extraction with proper relationships and purple source connections.`;

    if (graphContext.selectedNodes && graphContext.selectedNodes.length > 0) {
        systemPrompt += ` Pay special attention to the selected nodes and their significance.`;
    }

    try {
        const response = await fetch('/api/ai-chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                model: 'claude-opus-4-20250514',
                max_tokens: 800,
                temperature: 0.7,
                messages: [
                    {
                        role: 'system',
                        content: systemPrompt
                    },
                    ...chatHistory,
                    {
                        role: 'user',
                        content: userMessage
                    }
                ]
            })
        });

        if (!response.ok) {
            const errorText = await response.text();
            console.error('API Error Response:', errorText);
            throw new Error(`AI service error (${response.status}): ${errorText}`);
        }

        const data = await response.json();
        console.log('AI Response Data:', data);
        const aiResponse = data.content?.[0]?.text || 'Sorry, I could not generate a response.';
        
        // Update chat history
        chatHistory.push(
            { role: 'user', content: userMessage },
            { role: 'assistant', content: aiResponse }
        );
        
        // Keep chat history manageable (last 10 exchanges)
        if (chatHistory.length > 20) {
            chatHistory = chatHistory.slice(-20);
        }
        
        return aiResponse;
        
    } catch (error) {
        throw error;
    }
}

// Handle Enter key in chat input - moved to window load event
function initializeChatInput() {
    const chatInput = document.getElementById('chat-input');
    if (chatInput) {
        chatInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendChatMessage();
            }
        });
        console.log('Chat input initialized');
    } else {
        console.error('Chat input not found');
    }
}

// Recreate breach connections manually
window.recreateBreachConnections = function() {
    // Clear existing breach connections
    const existingBreachEdges = edges.get({
        filter: edge => edge.title && edge.title.includes('Same breach:')
    });
    edges.remove(existingBreachEdges.map(e => e.id));
    
    // Rebuild from node data
    const nodesByBreach = new Map();
    const allNodes = nodes.get();
    
    allNodes.forEach(node => {
        if (node.data && node.data.breach) {
            const breach = node.data.breach;
            if (!nodesByBreach.has(breach)) {
                nodesByBreach.set(breach, []);
            }
            nodesByBreach.get(breach).push(node.id);
        }
    });
    
    // Clear and rebuild breachConnections map
    breachConnections.clear();
    
    // Connect nodes from same breach
    let totalConnections = 0;
    nodesByBreach.forEach((nodeIds, breachName) => {
        if (nodeIds.length >= 2) {
            connectBreachNodes(nodeIds, breachName);
            totalConnections += (nodeIds.length * (nodeIds.length - 1)) / 2;
        }
    });
    
    saveGraphState();
    updateStatus(`Recreated connections for ${nodesByBreach.size} breaches`);
    console.log(`Created ${totalConnections} potential connections across ${nodesByBreach.size} breaches`);
}

// Debug connections
window.debugConnections = function() {
    console.log('=== BREACH CONNECTIONS DEBUG ===');
    console.log('Breach connections map:', breachConnections);
    console.log('Total breaches tracked:', breachConnections.size);
    
    breachConnections.forEach((nodes, breach) => {
        console.log(`Breach: ${breach} has ${nodes.length} nodes:`, nodes);
    });
    
    console.log('Total edges:', edges.get().length);
    const breachEdges = edges.get({
        filter: edge => edge.title && edge.title.includes('Same breach')
    });
    console.log('Breach connection edges:', breachEdges.length);
    
    // Make all edges more visible temporarily
    const allEdges = edges.get();
    const updates = allEdges.map(edge => ({
        id: edge.id,
        width: 5,
        color: {
            color: '#ffff00',
            inherit: false
        }
    }));
    edges.update(updates);
    
    setTimeout(() => {
        // Restore original colors
        const restore = allEdges.map(edge => ({
            id: edge.id,
            width: edge.title && edge.title.includes('Same breach') ? 3 : 2,
            color: edge.color
        }));
        edges.update(restore);
    }, 3000);
    
    updateStatus(`Highlighting ${edges.get().length} edges for 3 seconds`);
}

// Switch panel tabs
window.switchPanelTab = function(tabName) {
    // Update tab buttons
    document.querySelectorAll('.panel-tab').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');
    
    // Update tab content
    document.querySelectorAll('.panel-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById(`panel-${tabName}`).classList.add('active');
    
    if (tabName === 'nodes') {
        updateNodeList();
    }
}

// Update node list
let currentNodeFilter = 'all';
function updateNodeList() {
    const nodeList = document.getElementById('node-list');
    const allNodes = nodes.get();
    
    // Filter nodes by type
    const filteredNodes = currentNodeFilter === 'all' 
        ? allNodes 
        : allNodes.filter(node => node.type === currentNodeFilter);
    
    // Sort by label
    filteredNodes.sort((a, b) => (a.label || '').localeCompare(b.label || ''));
    
    let html = '';
    filteredNodes.forEach(node => {
        const isVisible = !node.hidden;
        const color = getNodeColor(node.type);
        const fullValue = node.label || node.data?.value || '';
        const isLong = fullValue.length > 100;
        
        html += `
            <div class="node-item" onclick="selectNodeInGraph('${node.id}')">
                <input type="checkbox" 
                    class="node-select-checkbox"
                    data-node-id="${node.id}"
                    onclick="event.stopPropagation();"
                    style="margin-right: 5px;">
                <input type="checkbox" 
                    ${isVisible ? 'checked' : ''} 
                    onclick="toggleNodeVisibility('${node.id}', this.checked); event.stopPropagation();"
                    title="Show/Hide">
                <div class="node-item-content">
                    <span class="node-item-label ${isLong ? 'expandable' : ''}" 
                          onclick="${isLong ? `toggleExpand(this); event.stopPropagation();` : ''}">
                        ${escapeHtml(fullValue)}
                    </span>
                    ${isLong ? '<span class="expand-hint">[Click to toggle]</span>' : ''}
                    <span class="node-item-type" style="background-color: ${color}; color: #000;">
                        ${node.type}
                    </span>
                </div>
            </div>
        `;
    });
    
    nodeList.innerHTML = html || '<p>No nodes to display</p>';
}

// Filter node list
window.filterNodeList = function(type) {
    currentNodeFilter = type;
    
    // Update active button
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');
    
    updateNodeList();
}

// Toggle node visibility
window.toggleNodeVisibility = function(nodeId, visible) {
    const node = nodes.get(nodeId);
    if (node) {
        nodes.update({
            id: nodeId,
            hidden: !visible
        });
        
        // Also hide/show connected edges
        const connectedEdges = edges.get({
            filter: edge => edge.from === nodeId || edge.to === nodeId
        });
        
        connectedEdges.forEach(edge => {
            edges.update({
                id: edge.id,
                hidden: !visible
            });
        });
    }
}

// Toggle all nodes (filtered by current type selection)
window.toggleAllNodes = function(visible) {
    const allNodes = nodes.get();
    
    // Filter nodes by current filter selection
    const filteredNodes = currentNodeFilter === 'all' 
        ? allNodes 
        : allNodes.filter(node => node.type === currentNodeFilter);
    
    // Update only the filtered nodes
    const updates = filteredNodes.map(node => ({
        id: node.id,
        hidden: !visible
    }));
    
    nodes.update(updates);
    
    // Hide/show edges connected to these nodes
    const filteredNodeIds = new Set(filteredNodes.map(n => n.id));
    const connectedEdges = edges.get({
        filter: edge => filteredNodeIds.has(edge.from) || filteredNodeIds.has(edge.to)
    });
    
    const edgeUpdates = connectedEdges.map(edge => ({
        id: edge.id,
        hidden: !visible
    }));
    
    edges.update(edgeUpdates);
    
    const action = visible ? 'Showing' : 'Hiding';
    const typeText = currentNodeFilter === 'all' ? 'all nodes' : `all ${currentNodeFilter} nodes`;
    updateStatus(`${action} ${filteredNodes.length} ${typeText}`);
    
    updateNodeList();
}

// Select node in graph
window.selectNodeInGraph = function(nodeId) {
    network.selectNodes([nodeId]);
    network.focus(nodeId, {
        scale: 1.5,
        animation: true
    });
    
    // Switch to details tab and show node details
    document.querySelectorAll('.panel-tab')[0].click();
    const node = nodes.get(nodeId);
    if (node) {
        showNodeDetails(node);
    }
}

// Toggle expand/collapse for long values
window.toggleExpand = function(element) {
    element.classList.toggle('collapsed');
}

// Show visual feedback when a node has already been searched
function showNodeSearchedFeedback(nodeId) {
    const nodePosition = network.getPositions([nodeId])[nodeId];
    if (!nodePosition) return;
    
    // Convert network coordinates to DOM coordinates
    const domPosition = network.canvasToDOM(nodePosition);
    
    // Create checkmark element
    const checkmark = document.createElement('div');
    checkmark.innerHTML = '✅';
    checkmark.style.cssText = `
        position: absolute;
        left: ${domPosition.x}px;
        top: ${domPosition.y - 30}px;
        font-size: 24px;
        z-index: 1000;
        animation: fadeInOut 2s ease-in-out;
        pointer-events: none;
    `;
    
    // Add to the network container
    const networkContainer = document.getElementById('network');
    networkContainer.appendChild(checkmark);
    
    // Remove after animation
    setTimeout(() => {
        checkmark.remove();
    }, 2000);
}

// Initialize header auto-hide functionality
function initializeHeaderAutoHide() {
    const header = document.getElementById('header');
    let hideTimeout;
    let isMouseOverHeader = false;
    
    // Auto-hide after 3 seconds of inactivity
    function startHideTimer() {
        clearTimeout(hideTimeout);
        hideTimeout = setTimeout(() => {
            if (!isMouseOverHeader) {
                header.classList.add('minimized');
            }
        }, 3000);
    }
    
    // Show header when mouse is at top of screen
    document.addEventListener('mousemove', (e) => {
        if (e.clientY <= 50) {
            header.classList.remove('minimized');
            startHideTimer();
        }
    });
    
    // Keep header visible when mouse is over it
    header.addEventListener('mouseenter', () => {
        isMouseOverHeader = true;
        header.classList.remove('minimized');
        clearTimeout(hideTimeout);
    });
    
    header.addEventListener('mouseleave', () => {
        isMouseOverHeader = false;
        startHideTimer();
    });
    
    // Keep header visible when typing in search
    const searchInput = document.getElementById('searchInput');
    searchInput.addEventListener('focus', () => {
        header.classList.remove('minimized');
        clearTimeout(hideTimeout);
    });
    
    searchInput.addEventListener('blur', () => {
        startHideTimer();
    });
    
    // Start the timer initially
    startHideTimer();
}

// Initialize sidebar resizing
function initializeSidebarResize() {
    const infoPanel = document.getElementById('info-panel');
    const toggleButton = document.getElementById('info-panel-toggle');
    let isResizing = false;
    let startX = 0;
    let startWidth = 0;
    
    // Create resize handle
    const resizeHandle = document.createElement('div');
    resizeHandle.style.cssText = `
        position: absolute;
        left: 0;
        top: 0;
        bottom: 0;
        width: 6px;
        cursor: ew-resize;
        z-index: 10;
    `;
    
    infoPanel.style.position = 'relative';
    infoPanel.appendChild(resizeHandle);
    
    resizeHandle.addEventListener('mousedown', (e) => {
        if (infoPanelCollapsed) {
            return;
        }
        isResizing = true;
        startX = e.clientX;
        startWidth = parseInt(document.defaultView.getComputedStyle(infoPanel).width, 10);
        document.body.style.cursor = 'ew-resize';
        e.preventDefault();
    });
    
    document.addEventListener('mousemove', (e) => {
        if (!isResizing || infoPanelCollapsed) return;
        const newWidth = startWidth - (e.clientX - startX);
        infoPanel.style.width = Math.min(Math.max(newWidth, 200), window.innerWidth * 0.5) + 'px';
    });

    document.addEventListener('mouseup', () => {
        if (isResizing) {
            isResizing = false;
            document.body.style.cursor = '';
            // Save the width preference
            if (!infoPanelCollapsed) {
                localStorage.setItem('infoPanelWidth', infoPanel.style.width);
            }
        }
    });

    // Restore saved width
    const savedWidth = localStorage.getItem('infoPanelWidth');
    if (savedWidth) {
        infoPanel.style.width = savedWidth;
    }

    const savedCollapsed = localStorage.getItem('infoPanelCollapsed');
    if (savedCollapsed !== null) {
        infoPanelCollapsed = savedCollapsed === 'true';
    }
    setInfoPanelCollapsed(infoPanelCollapsed, { skipSave: true });

    if (toggleButton) {
        toggleButton.addEventListener('click', () => {
            const nextState = !infoPanelCollapsed;
            setInfoPanelCollapsed(nextState);
            if (!nextState) {
                const width = localStorage.getItem('infoPanelWidth') || infoPanel.dataset.prevWidth || `${INFO_PANEL_DEFAULT_WIDTH}px`;
                infoPanel.style.width = width;
            }
        });
    }
}

// Force load graph data
function forceLoadGraph() {
    console.log('FORCE LOAD CLICKED!');
    fetch('/api/cache/load')
        .then(r => {
            console.log('Got response:', r);
            return r.json();
        })
        .then(data => {
            console.log('Force loading data:', data);
            if (data.data && data.data.graph_state && data.data.graph_state.nodes) {
                const nodeCount = data.data.graph_state.nodes.length;
                console.log('Found nodes:', nodeCount);
                if (nodeCount > 0) {
                    console.log('Calling loadGraphState...');
                    loadGraphState(data.data.graph_state);
                    console.log('Nodes after load:', nodes.get().length);
                    
                    // REBUILD CONNECTIONS!
                    rebuildAllConnections();
                    
                    network.fit();
                    updateStatus(`Force loaded ${nodeCount} nodes and rebuilt connections`);
                } else {
                    updateStatus('No nodes found in saved state');
                }
            } else {
                console.log('No graph state in data:', data);
                updateStatus('No graph state found');
            }
        })
        .catch(err => {
            console.error('Force load error:', err);
            updateStatus('Error loading graph: ' + err);
        });
}

// Rebuild all connections based on node data
function rebuildAllConnections() {
    console.log('Rebuilding all connections...');
    
    // Clear existing edges first
    edges.clear();
    
    const allNodes = nodes.get();
    console.log('Total nodes:', allNodes.length);
    
    // Simple breach grouping ONLY
    const breaches = {};
    allNodes.forEach(node => {
        if (node.data && node.data.breach) {
            const breach = node.data.breach;
            if (!breaches[breach]) {
                breaches[breach] = [];
            }
            breaches[breach].push(node.id);
        }
    });
    
    // Add edges for breaches - SIMPLE VERSION
    let edgeCount = 0;
    Object.keys(breaches).forEach(breach => {
        const nodeIds = breaches[breach];
        if (nodeIds.length >= 2 && nodeIds.length <= 50) { // LIMIT TO SMALLER BREACHES
            console.log(`Breach ${breach}: ${nodeIds.length} nodes`);
            
            // Simple hub connection - connect all to first node only
            const hubNode = nodeIds[0];
            for (let i = 1; i < nodeIds.length; i++) {
                if (hubNode !== nodeIds[i]) {
                    edges.add({
                        from: hubNode,
                        to: nodeIds[i],
                        color: { color: '#666666' },
                        width: 1,
                        title: `Same breach: ${breach}`,
                        arrows: { to: { enabled: false } }
                    });
                }
            }
            edgeCount++;
        }
    });
    
    console.log(`Added ${edgeCount} connections`);
    updateStatus(`Added ${edgeCount} connections`);
    saveGraphState();
}

// Initialize when page loads
window.addEventListener('load', async () => {
    // Load hashed password preference
    const savedHashPref = localStorage.getItem('includeHashedPasswords');
    if (savedHashPref !== null) {
        includeHashedPasswords = savedHashPref === 'true';
        document.getElementById('includeHashes').checked = includeHashedPasswords;
    }
    
    // Load AI suggestions preference
    const savedAIPref = localStorage.getItem('aiSuggestionsEnabled');
    if (savedAIPref !== null) {
        aiSuggestionsEnabled = savedAIPref === 'true';
        document.getElementById('aiSuggestions').checked = aiSuggestionsEnabled;
    }
    
    initializeGraph();
    initializeChatInput();
    
    // Load projects after initializing graph
    await loadProjects();
    
    // Initialize sidebar resizing
    initializeSidebarResize();
    
    // Initialize header auto-hide
    initializeHeaderAutoHide();
    
    // Initialize paste handler for images
    initializePasteHandler();
    
    // Graph state is now loaded through the project system in loadProjects()
    
    // Draw search indicators if queries are enabled
    if (autoShowQueries) {
        setTimeout(() => {
            drawSearchIndicators();
        }, 500); // Wait for network to stabilize
    }
    
    // Fix any stuck gray nodes after loading
    setTimeout(() => {
        fixStuckFocus();
        removeSelfLoops();
    }, 500);
    
    // Add CSS for context menu and cache view
    const style = document.createElement('style');
    style.textContent = `
        .menu-item {
            padding: 5px 10px;
            cursor: pointer;
            color: #0f0;
        }
        .menu-item:hover {
            background: #0f0;
            color: #000;
        }
        .cache-entry {
            margin-bottom: 15px;
            padding: 10px;
            border: 1px solid #003300;
            background-color: #001100;
            cursor: context-menu;
        }
        .cache-entry:hover {
            border-color: #00ff00;
        }
        .cache-entry strong {
            color: #ffff00;
        }
        .cache-entry ul {
            margin-top: 5px;
            margin-left: 20px;
        }
        .cache-entry li {
            color: #00ff00;
            margin: 2px 0;
        }
        #cache-view h3 {
            color: #ffff00;
            margin-bottom: 10px;
        }
        #cache-view h4 {
            color: #00ffff;
            margin: 15px 0 10px 0;
        }
        #cache-view table th {
            text-align: left;
            padding: 5px;
            border-bottom: 2px solid #00ff00;
            color: #ffff00;
        }
        #cache-view table tr {
            cursor: context-menu;
        }
        #cache-view table tr:hover {
            background-color: #002200;
        }
        .node-item-label.expandable {
            cursor: pointer;
            max-height: 200px;
            overflow-y: auto;
        }
        .node-item-label.expandable.collapsed {
            max-height: 40px;
            overflow: hidden;
            position: relative;
        }
        .node-item-label.expandable.collapsed::after {
            content: '...';
            position: absolute;
            bottom: 0;
            right: 0;
            background: #050505;
            padding: 0 5px;
        }
        .expand-hint {
            font-size: 9px;
            color: #888;
            margin-left: 5px;
        }
    `;
    document.head.appendChild(style);
});

// Switch between tabs
window.switchTab = function(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Show selected tab
    document.getElementById(`${tabName}-tab`).classList.add('active');
    
    // Update button
    document.querySelector(`.tab-button[onclick="switchTab('${tabName}')"]`).classList.add('active');
}

// Analyze image with Claude using tool calling
window.analyzeImageWithClaude = async function(nodeId) {
    const node = nodes.get(nodeId);
    if (!node || (!node.image && node.shape !== 'image')) {
        updateStatus('No image found for analysis');
        return;
    }
    
    // Hide context menu
    const menu = document.getElementById('context-menu');
    if (menu) menu.remove();
    
    // Use the new tool calling extraction function
    await autoExtractEntitiesFromImage(nodeId);
}

// Manual screenshot capture button
window.captureScreenshot = function(nodeId) {
    const node = nodes.get(nodeId);
    if (node && node.type === 'url') {
        const url = node.data.fullUrl || `https://${node.data.value}`;
        triggerScreenshotCapture(nodeId, url);
    }
};

// Retry screenshot capture
window.retryScreenshot = function(nodeId) {
    const node = nodes.get(nodeId);
    if (node && node.type === 'url') {
        const url = node.data.fullUrl || `https://${node.data.value}`;
        triggerScreenshotCapture(nodeId, url);
    }
};

// Show full screenshot in modal
window.showFullScreenshot = function(nodeId) {
    const node = nodes.get(nodeId);
    if (!node || !node.data.screenshot) return;
    
    // Create modal overlay
    const modal = document.createElement('div');
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.9);
        z-index: 9999;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
    `;
    
    // Create image container
    const imgContainer = document.createElement('div');
    imgContainer.style.cssText = `
        max-width: 90%;
        max-height: 90%;
        overflow: auto;
        position: relative;
    `;
    
    // Create image
    const img = document.createElement('img');
    img.src = node.data.screenshot;
    img.style.cssText = `
        display: block;
        width: auto;
        height: auto;
        max-width: 100%;
        border: 2px solid #00FFFF;
    `;
    
    // Close button
    const closeBtn = document.createElement('div');
    closeBtn.textContent = '✕';
    closeBtn.style.cssText = `
        position: absolute;
        top: 10px;
        right: 10px;
        width: 30px;
        height: 30px;
        background: #000;
        color: #00FFFF;
        border: 2px solid #00FFFF;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        font-size: 20px;
    `;
    
    // Add elements
    imgContainer.appendChild(img);
    imgContainer.appendChild(closeBtn);
    modal.appendChild(imgContainer);
    document.body.appendChild(modal);
    
    // Close on click
    modal.onclick = () => modal.remove();
    closeBtn.onclick = (e) => {
        e.stopPropagation();
        modal.remove();
    };
    
    // Close on escape
    const escHandler = (e) => {
        if (e.key === 'Escape') {
            modal.remove();
            document.removeEventListener('keydown', escHandler);
        }
    };
    document.addEventListener('keydown', escHandler);
};

// Extract entities from a URL using Firecrawl + Claude
async function extractEntitiesFromUrl(urlNode) {
    try {
        const targetUrl = urlNode.data.fullUrl || `https://${urlNode.data.value}`;
        const nodeId = urlNode.id;
        
        // Set loading state on URL node
        nodes.update({
            id: nodeId,
            data: {
                ...urlNode.data,
                extractionStatus: 'loading'
            }
        });
        
        updateStatus(`🧠 Extracting entities from ${urlNode.data.value}...`);
        
        // Call backend API
        const response = await fetchWithRetry('/api/url/extract-entities', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                url: targetUrl,
                nodeId: nodeId
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Entity extraction failed');
        }
        
        const result = await response.json();
        
        if (result.success) {
            const entities = result.entities || [];
            const relationships = result.relationships || [];
            const createdNodes = new Map();
            
            updateStatus(`Creating ${entities.length} entities and ${relationships.length} relationships...`);
            
            // Get URL node position for arranging entities
            const urlPos = network.getPositions([nodeId])[nodeId];
            const centerX = urlPos ? urlPos.x : 0;
            const centerY = urlPos ? urlPos.y : 0;
            
            // Group entities by type for better positioning
            const entitiesByType = {};
            entities.forEach(entity => {
                if (!entitiesByType[entity.type]) {
                    entitiesByType[entity.type] = [];
                }
                entitiesByType[entity.type].push(entity);
            });
            
            // Position entities in a semi-circle around the URL node
            let totalIndex = 0;
            const radius = 300;
            const totalEntities = entities.length;
            
            // Create nodes for all entities
            for (const [type, typeEntities] of Object.entries(entitiesByType)) {
                for (const entity of typeEntities) {
                    // Calculate position in semi-circle
                    const angle = Math.PI + (Math.PI * totalIndex / Math.max(totalEntities - 1, 1));
                    const x = centerX + radius * Math.cos(angle);
                    const y = centerY + radius * Math.sin(angle);
                    
                    // Create the entity node
                    const nodeResult = addNode({
                        value: entity.value,
                        label: entity.value,
                        source: 'URL Entity Extract',
                        notes: entity.notes || '',
                        confidence: entity.confidence || 'medium',
                        extractedFrom: targetUrl
                    }, entity.type, null, false, null, false);
                    
                    if (nodeResult && nodeResult.nodeId) {
                        createdNodes.set(entity.value, nodeResult.nodeId);
                        
                        // Position the node
                        setTimeout(() => {
                            network.moveNode(nodeResult.nodeId, x, y);
                        }, 100 + totalIndex * 50); // Stagger for animation
                        
                        // Update node with additional data
                        const node = nodes.get(nodeResult.nodeId);
                        if (node) {
                            nodes.update({
                                id: nodeResult.nodeId,
                                title: `${entity.type.toUpperCase()}: ${entity.value}\n${entity.notes || ''}\nConfidence: ${entity.confidence}`,
                                data: {
                                    ...node.data,
                                    notes: entity.notes,
                                    confidence: entity.confidence,
                                    extractedFromUrl: targetUrl
                                }
                            });
                        }
                        
                        // Create green SOURCE edge from URL to entity
                        const edgeId = `edge_${nodeId}_${nodeResult.nodeId}_url_source`;
                        if (!edges.get(edgeId)) {
                            edges.add({
                                id: edgeId,
                                from: nodeId,
                                to: nodeResult.nodeId,
                                ...getConnectionStyle('SOURCE'),
                                label: 'EXTRACTED',
                                title: 'Extracted from URL content',
                                edgeType: 'url_source',
                                smooth: {
                                    type: 'curvedCW',
                                    roundness: 0.2
                                }
                            });
                        }
                    }
                    
                    totalIndex++;
                }
            }
            
            // Create relationships between entities
            setTimeout(() => {
                for (const rel of relationships) {
                    // Find node IDs
                    let sourceId = createdNodes.get(rel.source);
                    let targetId = createdNodes.get(rel.target);
                    
                    // Try to find in existing nodes if not in created nodes
                    if (!sourceId) {
                        const sourceNodes = nodes.get({
                            filter: n => n.label && n.label === rel.source
                        });
                        if (sourceNodes.length > 0) sourceId = sourceNodes[0].id;
                    }
                    
                    if (!targetId) {
                        const targetNodes = nodes.get({
                            filter: n => n.label && n.label === rel.target
                        });
                        if (targetNodes.length > 0) targetId = targetNodes[0].id;
                    }
                    
                    // Create relationship edge
                    if (sourceId && targetId && sourceId !== targetId) {
                        const edgeId = `edge_${sourceId}_${targetId}_${rel.relationship.replace(/\s+/g, '_')}`;
                        if (!edges.get(edgeId)) {
                            edges.add({
                                id: edgeId,
                                from: sourceId,
                                to: targetId,
                                label: showConnectionLabels ? rel.relationship : '',
                                title: `${rel.relationship}\n${rel.notes || ''}\nConfidence: ${rel.confidence || 'medium'}`,
                                color: { color: '#00CED1' },
                                width: 2,
                                arrows: { to: { enabled: true, scaleFactor: 0.8 } },
                                font: { color: '#00CED1', size: 12 },
                                smooth: false,
                                data: {
                                    notes: rel.notes,
                                    confidence: rel.confidence,
                                    originalLabel: rel.relationship
                                }
                            });
                            console.log(`Created relationship: ${rel.source} -> ${rel.target} [${rel.relationship}]`);
                        }
                    }
                }
            }, 1000); // Wait for nodes to be created
            
            // Update URL node to clear loading state
            nodes.update({
                id: nodeId,
                data: {
                    ...nodes.get(nodeId).data,
                    extractionStatus: 'success',
                    entitiesExtracted: entities.length,
                    relationshipsExtracted: relationships.length
                }
            });
            
            // Focus on the URL node to see all extracted entities
            setTimeout(() => {
                network.focus(nodeId, {
                    scale: 0.8,
                    animation: {
                        duration: 1000,
                        easingFunction: 'easeInOutQuad'
                    }
                });
            }, 1500);
            
            saveGraphState();
            updateStatus(`✅ Extracted ${entities.length} entities and ${relationships.length} relationships from ${urlNode.data.value}`);
            
        } else {
            throw new Error('Extraction failed');
        }
        
    } catch (error) {
        console.error('Entity extraction error:', error);
        
        // Update node with error state
        if (urlNode && urlNode.id) {
            nodes.update({
                id: urlNode.id,
                data: {
                    ...nodes.get(urlNode.id).data,
                    extractionStatus: 'error',
                    extractionError: error.message
                }
            });
        }
        
        updateStatus(`❌ Failed to extract entities: ${error.message}`);
    }
}

// Enrich LinkedIn profile using OSINT Industries
async function enrichLinkedInProfile(urlNode, linkedInUrl) {
    try {
        const nodeId = urlNode.id;

        // Set loading state on URL node
        nodes.update({
            id: nodeId,
            data: {
                ...urlNode.data,
                enrichmentStatus: 'loading'
            }
        });

        updateStatus(`👔 Enriching LinkedIn profile from OSINT Industries...`);

        // Extract name from LinkedIn URL if possible
        // LinkedIn URLs typically look like: linkedin.com/in/firstname-lastname
        let searchQuery = linkedInUrl;
        let queryType = null;

        const linkedInMatch = linkedInUrl.match(/linkedin\.com\/in\/([^\/\?]+)/i);
        if (linkedInMatch) {
            // Convert linkedin slug to name (e.g., "john-doe" -> "john doe")
            const slug = linkedInMatch[1];
            searchQuery = slug.replace(/-/g, ' ');
            // Auto-detect will figure out if it's email or phone, default to searching as name/email
            queryType = null; // Let backend auto-detect
        }

        // Call OSINT API
        const response = await fetchWithRetry('/api/osint', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                query: searchQuery,
                type: queryType
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'LinkedIn enrichment failed');
        }

        const result = await response.json();

        if (result.entities && result.entities.length > 0) {
            const entities = result.entities;
            updateStatus(`Found ${entities.length} related entities from OSINT data...`);

            // Create LinkedIn enrichment query node (red frame, black background)
            const queryNodeId = `query_linkedin_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
            const queryNode = {
                id: queryNodeId,
                label: `LinkedIn: ${searchQuery}`,
                type: 'query',
                shape: 'diamond',
                color: { background: '#000000', border: '#FF0000' },
                font: { color: '#FFFFFF' },
                data: {
                    value: searchQuery,
                    searchType: 'linkedin_enrichment',
                    resultCount: entities.length,
                    linkedInUrl: linkedInUrl,
                    timestamp: new Date().toISOString()
                }
            };

            nodes.add(queryNode);

            // Connect LinkedIn URL to query node
            edges.add({
                id: `edge_${nodeId}_${queryNodeId}`,
                from: nodeId,
                to: queryNodeId,
                label: 'enriched',
                color: { color: '#FF0000', opacity: 0.5 },
                width: 2,
                arrows: { to: { enabled: true, scaleFactor: 0.5 } }
            });

            // Get query node position for arranging entities
            const queryPos = network.getPositions([queryNodeId])[queryNodeId];
            const centerX = queryPos ? queryPos.x : 0;
            const centerY = queryPos ? queryPos.y : 0;

            // Position entities in a circle around the query node
            const radius = 400;
            const angleStep = (2 * Math.PI) / entities.length;

            entities.forEach((entity, index) => {
                const angle = index * angleStep;
                const x = centerX + radius * Math.cos(angle);
                const y = centerY + radius * Math.sin(angle);

                // Determine entity type and color
                const entityType = entity.type || 'person';
                const entityName = entity.name || entity.label || 'Unknown';

                // Create entity node
                const entityNodeId = `entity_${entityType}_${Date.now()}_${index}`;
                const entityNode = {
                    id: entityNodeId,
                    label: entityName,
                    type: entityType,
                    x: x,
                    y: y,
                    data: {
                        ...entity,
                        value: entityName,
                        source: 'osint_linkedin',
                        linkedInUrl: linkedInUrl,
                        timestamp: new Date().toISOString()
                    },
                    color: getEntityTypeColor(entityType),
                    font: { color: '#FFFFFF' },
                    shape: 'box'
                };

                nodes.add(entityNode);

                // Create edge from query node to entity
                edges.add({
                    id: `edge_linkedin_${queryNodeId}_${entityNodeId}`,
                    from: queryNodeId,
                    to: entityNodeId,
                    label: 'found',
                    color: { color: '#FF0000', opacity: 0.5 },
                    width: 1,
                    arrows: { to: { enabled: true, scaleFactor: 0.5 } }
                });
            });

            // Update node with success state
            nodes.update({
                id: nodeId,
                data: {
                    ...nodes.get(nodeId).data,
                    enrichmentStatus: 'success',
                    entityCount: entities.length,
                    lastEnriched: new Date().toISOString()
                }
            });

            updateStatus(`✅ Successfully enriched LinkedIn profile: ${entities.length} entities added`);
        } else {
            updateStatus(`ℹ️ No additional entities found for this LinkedIn profile`);
            nodes.update({
                id: nodeId,
                data: {
                    ...nodes.get(nodeId).data,
                    enrichmentStatus: 'no_results'
                }
            });
        }

    } catch (error) {
        console.error('LinkedIn enrichment error:', error);

        // Update node with error state
        if (urlNode && urlNode.id) {
            nodes.update({
                id: urlNode.id,
                data: {
                    ...nodes.get(urlNode.id).data,
                    enrichmentStatus: 'error',
                    enrichmentError: error.message
                }
            });
        }

        updateStatus(`❌ Failed to enrich LinkedIn profile: ${error.message}`);
    }
}

// Helper function to get color based on entity type
function getEntityTypeColor(type) {
    const colors = {
        'person': '#4A90E2',
        'email': '#50C878',
        'phone': '#FF6B6B',
        'address': '#F39C12',
        'organization': '#9B59B6',
        'username': '#1ABC9C',
        'default': '#95A5A6'
    };
    return colors[type] || colors['default'];
}

// Extract entities from a document/markdown node using Claude
async function extractEntitiesFromDocument(documentNode) {
    try {
        const nodeId = documentNode.id;
        const documentData = documentNode.data;
        
        // Check if this document was already processed
        if (documentData && documentData.entityCount > 0) {
            const proceed = confirm(`This document has already been processed and has ${documentData.entityCount} entities extracted. Do you want to re-extract entities?`);
            if (!proceed) {
                return;
            }
        }
        
        // Check if currently processing
        if (documentData && documentData.isProcessing) {
            updateStatus(`⚠️ Document is currently being processed. Please wait.`);
            return;
        }
        
        // Set loading state on document node
        nodes.update({
            id: nodeId,
            data: {
                ...documentData,
                extractionStatus: 'loading',
                isProcessing: true
            }
        });
        
        const filename = documentData && documentData.value ? documentData.value : documentNode.label;
        updateStatus(`🧠 Extracting entities from ${filename}...`);
        
        // Trigger file upload dialog for manual content input if no file was uploaded
        if (!documentData || !documentData.uploadedAt) {
            const fileInput = document.createElement('input');
            fileInput.type = 'file';
            fileInput.accept = '.md';
            fileInput.style.display = 'none';
            
            fileInput.onchange = async (event) => {
                const file = event.target.files[0];
                if (!file) {
                    // Reset processing state
                    nodes.update({
                        id: nodeId,
                        data: {
                            ...documentData,
                            extractionStatus: null,
                            isProcessing: false
                        }
                    });
                    return;
                }
                
                // Create form data and upload
                const formData = new FormData();
                formData.append('file', file);
                formData.append('nodeId', nodeId);
                
                const response = await fetchWithRetry('/api/file/extract-entities', {
                    method: 'POST',
                    body: formData
                });
                
                await handleExtractionResponse(response, nodeId, file.name);
            };
            
            document.body.appendChild(fileInput);
            fileInput.click();
            document.body.removeChild(fileInput);
            return;
        }
        
        // For previously uploaded files, trigger re-extraction
        const response = await fetchWithRetry('/api/file/extract-entities', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                reextract: true,
                filename: filename,
                nodeId: nodeId
            })
        });
        
        await handleExtractionResponse(response, nodeId, filename);
        
    } catch (error) {
        console.error('Document entity extraction error:', error);
        
        // Update node with error state
        if (documentNode && documentNode.id) {
            nodes.update({
                id: documentNode.id,
                data: {
                    ...nodes.get(documentNode.id).data,
                    extractionStatus: 'error',
                    extractionError: error.message,
                    isProcessing: false
                }
            });
        }
        
        updateStatus(`❌ Failed to extract entities from document: ${error.message}`);
    }
}

// Helper function to handle extraction response
async function handleExtractionResponse(response, nodeId, filename) {
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Entity extraction failed');
    }
    
    const result = await response.json();
    
    if (result.success) {
        const entities = result.entities || [];
        const relationships = result.relationships || [];
        const createdNodes = new Map();
        
        updateStatus(`Creating ${entities.length} entities and ${relationships.length} relationships...`);
        
        // Get document node position for arranging entities
        const docPos = network.getPositions([nodeId])[nodeId];
        const centerX = docPos ? docPos.x : 0;
        const centerY = docPos ? docPos.y : 0;
        
        // Position entities in a semi-circle around the document node
        let totalIndex = 0;
        const radius = 300;
        const totalEntities = entities.length;
        
        // Create nodes for all entities
        for (const entity of entities) {
            // Calculate position in semi-circle
            const angle = Math.PI + (Math.PI * totalIndex / Math.max(totalEntities - 1, 1));
            const x = centerX + radius * Math.cos(angle);
            const y = centerY + radius * Math.sin(angle);
            
            // Create the entity node
            const nodeResult = await addNode({
                value: entity.value,
                label: entity.value,
                source: 'Document Entity Extract',
                notes: entity.notes || '',
                confidence: entity.confidence || 'medium',
                extractedFromFile: filename
            }, entity.type);
            
            if (nodeResult && nodeResult.nodeId) {
                createdNodes.set(entity.value, nodeResult.nodeId);
                
                // Position the node
                setTimeout(() => {
                    network.moveNode(nodeResult.nodeId, x, y);
                }, 100 + totalIndex * 50); // Stagger for animation
                
                // Update node with additional data
                const node = nodes.get(nodeResult.nodeId);
                if (node) {
                    nodes.update({
                        id: nodeResult.nodeId,
                        title: `${entity.type.toUpperCase()}: ${entity.value}\n${entity.notes || ''}\nConfidence: ${entity.confidence}`,
                        data: {
                            ...node.data,
                            notes: entity.notes,
                            confidence: entity.confidence,
                            extractedFromFile: filename
                        }
                    });
                }
                
                // Create green SOURCE edge from document to entity
                const edgeId = `edge_${nodeId}_${nodeResult.nodeId}_doc_source`;
                if (!edges.get(edgeId)) {
                    edges.add({
                        id: edgeId,
                        from: nodeId,
                        to: nodeResult.nodeId,
                        ...getConnectionStyle('SOURCE'),
                        label: 'EXTRACTED',
                        title: 'Extracted from document content',
                        edgeType: 'doc_source',
                        smooth: {
                            type: 'curvedCW',
                            roundness: 0.2
                        }
                    });
                }
            }
            
            totalIndex++;
        }
        
        // Create relationships between entities
        setTimeout(() => {
            for (const rel of relationships) {
                // Find node IDs
                let sourceId = createdNodes.get(rel.source);
                let targetId = createdNodes.get(rel.target);
                
                // Try to find in existing nodes if not in created nodes
                if (!sourceId) {
                    const sourceNodes = nodes.get({
                        filter: n => n.label && n.label === rel.source
                    });
                    if (sourceNodes.length > 0) sourceId = sourceNodes[0].id;
                }
                
                if (!targetId) {
                    const targetNodes = nodes.get({
                        filter: n => n.label && n.label === rel.target
                    });
                    if (targetNodes.length > 0) targetId = targetNodes[0].id;
                }
                
                // Create relationship edge
                if (sourceId && targetId && sourceId !== targetId) {
                    const edgeId = `edge_${sourceId}_${targetId}_${rel.relationship.replace(/\s+/g, '_')}`;
                    if (!edges.get(edgeId)) {
                        edges.add({
                            id: edgeId,
                            from: sourceId,
                            to: targetId,
                            label: showConnectionLabels ? rel.relationship : '',
                            title: `${rel.relationship}\n${rel.notes || ''}\nConfidence: ${rel.confidence || 'medium'}`,
                            color: { color: '#00CED1' },
                            width: 2,
                            arrows: { to: { enabled: true, scaleFactor: 0.8 } },
                            font: { color: '#00CED1', size: 12 },
                            smooth: false,
                            data: {
                                notes: rel.notes,
                                confidence: rel.confidence,
                                originalLabel: rel.relationship
                            }
                        });
                        console.log(`Created relationship: ${rel.source} -> ${rel.target} [${rel.relationship}]`);
                    }
                }
            }
        }, 1000); // Wait for nodes to be created
        
        // Update document node to clear loading state
        nodes.update({
            id: nodeId,
            data: {
                ...nodes.get(nodeId).data,
                extractionStatus: 'success',
                entitiesExtracted: entities.length,
                relationshipsExtracted: relationships.length,
                entityCount: entities.length,
                relationshipCount: relationships.length,
                isProcessing: false
            }
        });
        
        // Focus on the document node to see all extracted entities
        setTimeout(() => {
            network.focus(nodeId, {
                scale: 0.8,
                animation: {
                    duration: 1000,
                    easingFunction: 'easeInOutQuad'
                }
            });
        }, 1500);
        
        saveGraphState();
        updateStatus(`✅ Extracted ${entities.length} entities and ${relationships.length} relationships from document`);
        
    } else {
        throw new Error('Extraction failed');
    }
}

// Trigger screenshot capture for a URL node
async function triggerScreenshotCapture(nodeId, url) {
    try {
        const node = nodes.get(nodeId);
        if (!node) return;
        
        // Set loading state
        nodes.update({
            id: nodeId,
            data: {
                ...node.data,
                screenshotStatus: 'loading'
            }
        });
        
        updateStatus(`📸 Capturing screenshot for ${node.data.value}...`);
        
        // Call backend API
        const response = await fetchWithRetry('/api/screenshot/capture', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                url: url,
                nodeId: nodeId
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Screenshot capture failed');
        }
        
        const result = await response.json();
        
        if (result.success && result.screenshot) {
            // Update node with screenshot
            const updatedNode = nodes.get(nodeId);
            nodes.update({
                id: nodeId,
                data: {
                    ...updatedNode.data,
                    screenshot: result.screenshot,
                    screenshotStatus: 'success',
                    screenshotCapturedAt: new Date().toISOString()
                }
            });
            
            updateStatus(`✅ Screenshot captured for ${updatedNode.data.value}`);
            
            // Refresh profile if this node is currently displayed
            if (currentProfileNode && currentProfileNode.id === nodeId) {
                showNodeDetails(nodes.get(nodeId));
            }
            
            // Save graph state
            saveGraphState();
        }
        
    } catch (error) {
        console.error('Screenshot capture error:', error);
        
        // Update node with error state
        const node = nodes.get(nodeId);
        if (node) {
            nodes.update({
                id: nodeId,
                data: {
                    ...node.data,
                    screenshotStatus: 'error',
                    screenshotError: error.message
                }
            });
        }
        
        // Don't show error to user - screenshots are optional enhancement
        console.log(`Screenshot capture failed for ${url}: ${error.message}`);
    }
}

// Initialize paste handler for images
function initializePasteHandler() {
    console.log('Initializing paste handler...');
    document.addEventListener('paste', async (e) => {
        console.log('Paste event triggered!');
        
        // Check if we're in the graph tab
        if (!document.getElementById('graph-tab').classList.contains('active')) {
            console.log('Not in graph tab, ignoring paste');
            return;
        }
        
        // Check if we're pasting into an input field or textarea
        const activeElement = document.activeElement;
        if (activeElement && (activeElement.tagName === 'INPUT' || activeElement.tagName === 'TEXTAREA')) {
            console.log('Pasting into input/textarea, allowing default behavior');
            return; // Let the default paste behavior happen
        }
        
        const items = e.clipboardData.items;
        
        // Check for text first (could be URL)
        const textData = e.clipboardData.getData('text/plain');
        console.log('Paste event - text data:', textData);
        
        if (textData && textData.trim()) {
            const trimmedText = textData.trim();
            console.log('Trimmed text:', trimmedText);
            
            // Check if it's an email address first
            const emailPattern = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
            console.log('Email pattern test result:', emailPattern.test(trimmedText));
            
            if (emailPattern.test(trimmedText)) {
                e.preventDefault();
                console.log('Email detected, creating email node...');
                
                // Create email node
                const nodeData = {
                    value: trimmedText,
                    label: trimmedText,
                    source: 'Pasted Email'
                };
                
                // Get current view position for node placement
                const viewPos = network.getViewPosition();
                
                // Add node at center of current view
                const result = await addNode(nodeData, 'email');
                
                if (result && result.nodeId) {
                    // Position the node at center of view
                    setTimeout(() => {
                        network.moveNode(result.nodeId, viewPos.x, viewPos.y);
                    }, 100);
                    
                    updateStatus(`Created email node: ${trimmedText}`);
                }
                
                return; // Don't check for URL if it's an email
            }
            
            // Check if it's a URL - using a more permissive pattern
            const urlPattern = /^(https?:\/\/)?([\w\-]+\.)+[\w\-]+(\/[\w\-._~:/?#[\]@!$&'()*+,;=.]*)?$/i;
            console.log('URL pattern test result:', urlPattern.test(trimmedText));
            
            if (urlPattern.test(trimmedText)) {
                e.preventDefault();
                console.log('URL detected, creating URL node...');
                
                // Normalize URL: remove protocol and www
                let normalizedUrl = trimmedText
                    .replace(/^https?:\/\//, '')  // Remove http:// or https://
                    .replace(/^www\./, '')         // Remove www.
                    .replace(/\/$/, '');           // Remove trailing slash
                
                console.log(`Pasting URL: ${trimmedText} -> ${normalizedUrl}`);
                
                // Create URL node
                const nodeData = {
                    value: normalizedUrl,
                    label: normalizedUrl,
                    fullUrl: trimmedText,
                    source: 'Pasted URL'
                };
                
                // Get current view position for node placement
                const viewPos = network.getViewPosition();
                const scale = network.getScale();
                
                // Add node at center of current view
                const result = await addNode(nodeData, 'url');
                
                if (result && result.nodeId) {
                    // Position the node at center of view
                    setTimeout(() => {
                        network.moveNode(result.nodeId, viewPos.x, viewPos.y);
                    }, 100);
                    
                    // Check for connections to search query nodes
                    checkUrlToSearchConnections(result.nodeId, normalizedUrl, trimmedText);
                    
                    // Trigger screenshot capture in background
                    triggerScreenshotCapture(result.nodeId, trimmedText);
                    
                    updateStatus(`Created URL node: ${normalizedUrl}`);
                }
                
                return;
            }
        }
        
        for (let i = 0; i < items.length; i++) {
            if (items[i].type.indexOf('image') !== -1) {
                e.preventDefault();
                
                const blob = items[i].getAsFile();
                const reader = new FileReader();
                
                reader.onload = function(event) {
                    const dataURL = event.target.result;
                    
                    // Create image node
                    const nodeId = `node_${nodeIdCounter++}`;
                    const timestamp = new Date().toLocaleString();
                    
                    const imageNode = {
                        id: nodeId,
                        label: `Image ${timestamp}`,
                        shape: 'image',
                        image: dataURL,
                        size: 50,
                        borderWidth: 2,
                        borderWidthSelected: 3,
                        color: {
                            border: '#00FF00',
                            highlight: {
                                border: '#00FF00'
                            }
                        },
                        font: {
                            color: '#00FF00',
                            size: 10,
                            face: 'monospace'
                        },
                        data: {
                            type: 'image',
                            timestamp: timestamp,
                            dataURL: dataURL
                        },
                        physics: true
                    };
                    
                    // Add to graph at current view position
                    nodes.add(imageNode);
                    
                    // Position safely without overlap
                    const viewPosition = network.getViewPosition();
                    let x = viewPosition.x;
                    let y = viewPosition.y;
                    
                    // Check for collisions and adjust position
                    const allPositions = network.getPositions();
                    const minDistance = 400;
                    let attempts = 0;
                    
                    while (attempts < 30) {
                        let tooClose = false;
                        for (let existingId in allPositions) {
                            const existingPos = allPositions[existingId];
                            const dx = x - existingPos.x;
                            const dy = y - existingPos.y;
                            const distance = Math.sqrt(dx * dx + dy * dy);
                            
                            if (distance < minDistance) {
                                tooClose = true;
                                break;
                            }
                        }
                        
                        if (!tooClose) break;
                        
                        // Move to a different position
                        x = viewPosition.x + (Math.random() - 0.5) * 800;
                        y = viewPosition.y + (Math.random() - 0.5) * 800;
                        attempts++;
                    }
                    
                    network.moveNode(nodeId, x, y);
                    
                    // Select the new node
                    network.selectNodes([nodeId]);
                    
                    updateStatus(`Pasted image as node ${nodeId}`);
                    saveGraphState();
                };
                
                reader.readAsDataURL(blob);
                break;
            }
        }
    });
    
    console.log('Paste handler initialized - images can be pasted into graph');
}

// Save node notes (keeping for backwards compatibility)
window.saveNodeNotes = function() {
    if (currentProfileNode) {
        saveNodeDetails(currentProfileNode.id);
    }
}

// Save all node details including primary value and variations
// Setup auto-save for all input fields in the profile
function setupAutoSave(nodeId) {
    // Debounce timer
    let saveTimer;
    
    const debouncedSave = () => {
        clearTimeout(saveTimer);
        saveTimer = setTimeout(() => {
            saveNodeDetails(nodeId);
        }, 500); // Save after 500ms of no typing
    };
    
    // Primary value input
    const primaryInput = document.getElementById('node-primary-value');
    if (primaryInput) {
        primaryInput.addEventListener('input', debouncedSave);
        primaryInput.addEventListener('blur', () => saveNodeDetails(nodeId));
    }
    
    // Notes textarea
    const notesTextarea = document.getElementById('node-notes');
    if (notesTextarea) {
        notesTextarea.addEventListener('input', debouncedSave);
        notesTextarea.addEventListener('blur', () => saveNodeDetails(nodeId));
    }
    
    // URL inputs (including dynamically added ones)
    const urlContainer = document.getElementById('node-urls-container');
    if (urlContainer) {
        // Use event delegation for URL inputs
        urlContainer.addEventListener('input', (e) => {
            if (e.target && e.target.id && e.target.id.startsWith('node-url-')) {
                debouncedSave();
            }
        });
        urlContainer.addEventListener('blur', (e) => {
            if (e.target && e.target.id && e.target.id.startsWith('node-url-')) {
                saveNodeDetails(nodeId);
            }
        }, true);
    }
    
    // Variation inputs
    const variationInputs = document.querySelectorAll('input[id^="variation-"]');
    variationInputs.forEach(input => {
        input.addEventListener('input', debouncedSave);
        input.addEventListener('blur', () => saveNodeDetails(nodeId));
    });
}

window.saveNodeDetails = async function(nodeId) {
    const node = nodes.get(nodeId);
    if (!node) return;
    
    const primaryValue = document.getElementById('node-primary-value')?.value;
    const notes = document.getElementById('node-notes')?.value;
    
    const nodeData = { ...node.data };
    
    // Update primary value
    if (primaryValue) {
        nodeData.value = primaryValue;
    }
    
    // Update variations if they exist
    if (nodeData.variations) {
        nodeData.variations.forEach((v, idx) => {
            const variationInput = document.getElementById(`variation-${idx}`);
            if (variationInput) {
                v.value = variationInput.value;
            }
        });
    }
    
    // Collect URLs from all URL fields
    const urlInputs = document.querySelectorAll('input[id^="node-url-"]');
    const urls = [];
    urlInputs.forEach(input => {
        const url = input.value.trim();
        if (url) {
            urls.push(url);
        }
    });
    
    // Store URLs in node data
    nodeData.manualUrls = urls;
    
    // Update notes
    nodeData.notes = notes || '';
    
    // Update the node
    nodes.update({
        id: nodeId,
        data: nodeData,
        label: primaryValue || node.label
    });
    
    // Check for URL connections with other nodes
    await checkNodeUrlConnections(nodeId, urls);
    
    saveGraphState();
    // Silently save - no status update for auto-save
}

// Show unmerge options
window.showUnmergeOptions = function(nodeId) {
    const node = nodes.get(nodeId);
    if (!node || !node.data.mergeHistory) return;
    
    const menu = document.createElement('div');
    menu.style.cssText = `
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        background: #000;
        border: 2px solid #0f0;
        padding: 20px;
        z-index: 2000;
        max-width: 400px;
        max-height: 400px;
        overflow-y: auto;
    `;
    
    let html = `
        <h3 style="color: #0f0; margin-bottom: 10px;">Unmerge Variations</h3>
        <p style="color: #0f0; margin-bottom: 15px;">Select variations to unmerge:</p>
    `;
    
    node.data.mergeHistory.forEach((merge, idx) => {
        html += `
            <label style="display: block; margin: 5px 0; color: #0f0;">
                <input type="checkbox" id="unmerge-${idx}" value="${idx}">
                ${escapeHtml(merge.label)} (${merge.type}) - ${merge.breach || 'Unknown'}
            </label>
        `;
    });
    
    html += `
        <div style="margin-top: 15px;">
            <button onclick="performUnmerge('${nodeId}')">Unmerge Selected</button>
            <button onclick="this.parentElement.parentElement.remove()">Cancel</button>
        </div>
    `;
    
    menu.innerHTML = html;
    document.body.appendChild(menu);
}

// Perform unmerge
window.performUnmerge = function(nodeId) {
    const node = nodes.get(nodeId);
    if (!node || !node.data.mergeHistory) return;
    
    const selectedIndices = [];
    node.data.mergeHistory.forEach((merge, idx) => {
        const checkbox = document.getElementById(`unmerge-${idx}`);
        if (checkbox && checkbox.checked) {
            selectedIndices.push(idx);
        }
    });
    
    if (selectedIndices.length === 0) {
        alert('No variations selected');
        return;
    }
    
    // Process unmerges in reverse order to maintain indices
    selectedIndices.sort((a, b) => b - a);
    
    selectedIndices.forEach(idx => {
        const mergeInfo = node.data.mergeHistory[idx];
        
        // Check if this was an image node
        const variation = node.data.variations.find(v => v.id === mergeInfo.nodeId);
        const isImageNode = variation && variation.isImage;
        
        // Recreate the original node
        const restoredNode = {
            id: mergeInfo.nodeId,
            label: mergeInfo.label,
            type: mergeInfo.type,
            x: mergeInfo.position.x,
            y: mergeInfo.position.y,
            data: {
                value: mergeInfo.value,
                label: mergeInfo.label,
                breach: mergeInfo.breach,
                breachData: mergeInfo.breachData,
                notes: mergeInfo.notes
            }
        };
        
        // Set up as image node if it was one
        if (isImageNode && variation.dataURL) {
            restoredNode.shape = 'image';
            restoredNode.image = variation.dataURL;
            restoredNode.size = 50;
            restoredNode.borderWidth = 2;
            restoredNode.borderWidthSelected = 3;
            restoredNode.color = {
                border: '#00FF00',
                highlight: {
                    border: '#00FF00'
                }
            };
            restoredNode.font = {
                color: '#00FF00',
                size: 10,
                face: 'monospace'
            };
            restoredNode.data.type = 'image';
            restoredNode.data.dataURL = variation.dataURL;
        } else {
            // Regular node
            restoredNode.title = `${mergeInfo.type.toUpperCase()}: ${mergeInfo.value}`;
            restoredNode.color = getNodeColor(mergeInfo.type);
            restoredNode.font = {
                multi: 'html',
                size: 12
            };
        }
        
        nodes.add(restoredNode);
        
        // Restore original connections
        mergeInfo.originalConnections.forEach(edge => {
            // Skip if it would create a connection to the merged node
            if ((edge.from === nodeId && edge.to === mergeInfo.nodeId) ||
                (edge.to === nodeId && edge.from === mergeInfo.nodeId)) {
                return;
            }
            
            // Check if edge already exists
            const exists = edges.get({
                filter: e => e.from === edge.from && e.to === edge.to
            }).length > 0;
            
            if (!exists) {
                edges.add(edge);
            }
        });
        
        // Remove from variations and merge history
        const nodeData = { ...node.data };
        nodeData.variations = nodeData.variations.filter(v => v.id !== mergeInfo.nodeId);
        nodeData.mergeHistory.splice(idx, 1);
        
        // Also remove from mergedImages array if it exists
        if (nodeData.mergedImages) {
            nodeData.mergedImages = nodeData.mergedImages.filter(img => img.originalId !== mergeInfo.nodeId);
        }
        
        // Update the node
        const variationCount = nodeData.variations.length;
        nodes.update({
            id: nodeId,
            data: nodeData,
            label: node.label.replace(/ \[\+\d+\]/, '') + (variationCount > 0 ? ` [+${variationCount}]` : ''),
            title: `${node.label}\n${variationCount} variation(s)`,
            borderWidth: variationCount > 0 ? 3 : 1
        });
    });
    
    // Close the menu
    document.querySelector('div[style*="position: fixed"]').remove();
    
    saveGraphState();
    updateStatus(`Unmerged ${selectedIndices.length} variation(s)`);
    
    // Refresh node details if still selected
    if (network.getSelectedNodes().includes(nodeId)) {
        showNodeDetails(nodes.get(nodeId));
    }
}

// Force load graph from server
window.forceLoadGraph = function() {
    if (!network || !nodes || !edges) {
        alert('Graph not initialized! Reloading page...');
        location.reload();
        return;
    }
    
    fetch('/api/cache/load')
        .then(r => r.json())
        .then(data => {
            if (data.data && data.data.graph_state && data.data.graph_state.nodes) {
                alert('Loading ' + data.data.graph_state.nodes.length + ' nodes...');
                
                // Clear existing data
                nodes.clear();
                edges.clear();
                
                // Add nodes directly
                nodes.add(data.data.graph_state.nodes);
                
                // Add edges if any
                if (data.data.graph_state.edges) {
                    edges.add(data.data.graph_state.edges);
                }
                
                // Fit view
                setTimeout(() => {
                    network.fit();
                    updateStatus('Force loaded ' + nodes.length + ' nodes');
                }, 100);
            } else {
                alert('No data found in cache!');
            }
        })
        .catch(err => {
            alert('Error loading: ' + err);
        });
}

// Restore all data from cache
window.restoreAllData = function() {
    const majorSearches = [
        'sy.hishan@gmail.com_email',
        'Sarah Hishan_name',
        'Sarah Hishan_blanket_search', 
        'SarahH_username',
        'SE16 2XG, GB_address',
        '447717575654_phone'
    ];
    
    let totalRestored = 0;
    majorSearches.forEach(cacheKey => {
        if (searchCache.has(cacheKey)) {
            const data = searchCache.get(cacheKey);
            if (data && data.results && data.results.length > 0) {
                processCachedResults(data.results, null);
                totalRestored += data.results.length;
            }
        }
    });
    
    if (totalRestored > 0) {
        updateStatus(`Restored ${totalRestored} items from cache`);
        saveGraphState();
        // Focus on network
        network.fit({ animation: { duration: 500 } });
    } else {
        updateStatus('No cached data found to restore');
    }
}

// Create hypothetical link between two nodes
function createHypotheticalLink(nodeId1, nodeId2, reason = "Hypothetical connection") {
    // Check if link already exists
    const existingEdge = edges.get({
        filter: edge => (edge.from === nodeId1 && edge.to === nodeId2) ||
                       (edge.from === nodeId2 && edge.to === nodeId1)
    });
    
    if (existingEdge.length === 0 && nodeId1 !== nodeId2) {
        const edgeId = `hypothetical_${nodeId1}_${nodeId2}`;
        edges.add({
            id: edgeId,
            from: nodeId1,
            to: nodeId2,
            ...getConnectionStyle('HYPOTHETICAL'),
            title: `Hypothetical: ${reason}`,
            hypothetical: true
        });
        
        console.log(`Created hypothetical link between ${nodeId1} and ${nodeId2}`);
        return true;
    }
    return false;
}

// Add manual hypothetical link creation to context menu
function addHypotheticalLinkOption(menu, nodeId) {
    menu.innerHTML += `
        <div class="menu-item" onclick="startHypotheticalLinkMode(${nodeId})">
            Create Hypothetical Link
        </div>
    `;
}

// Start hypothetical link creation mode
window.startHypotheticalLinkMode = function(nodeId) {
    // Hide context menu
    const menu = document.getElementById("context-menu");
    if (menu) menu.remove();
    
    window.hypotheticalLinkSourceNode = nodeId;
    window.hypotheticalLinkMode = true;
    
    updateStatus("Click on another node to create a hypothetical link");
    
    // Change cursor to indicate linking mode
    document.body.style.cursor = "crosshair";
}

// Handle hypothetical link mode clicks
function handleHypotheticalLinkClick(targetNodeId) {
    if (window.hypotheticalLinkMode && window.hypotheticalLinkSourceNode) {
        const reason = prompt("Enter reason for hypothetical connection:", "Similar pattern detected");
        if (reason) {
            createHypotheticalLink(window.hypotheticalLinkSourceNode, targetNodeId, reason);
            updateStatus(`Created hypothetical link: ${reason}`);
            saveGraphState();
        }
        
        // Exit hypothetical link mode
        window.hypotheticalLinkMode = false;
        window.hypotheticalLinkSourceNode = null;
        document.body.style.cursor = "default";
    }
}



// Generate comprehensive report using Claude AI
window.generateReport = async function(scope) {
    updateStatus(`Generating ${scope} report with Claude AI...`);
    
    // Determine which nodes to include
    let targetNodes = [];
    let reportTitle = "";
    
    switch(scope) {
        case "selected":
            targetNodes = network.getSelectedNodes();
            reportTitle = "Selected Nodes Analysis Report";
            if (targetNodes.length === 0) {
                updateStatus("No nodes selected for report");
                return;
            }
            break;
        case "anchored":
            targetNodes = Array.from(anchoredNodes);
            reportTitle = "Anchored Nodes Analysis Report";
            if (targetNodes.length === 0) {
                updateStatus("No anchored nodes for report");
                return;
            }
            break;
        case "all":
            targetNodes = nodes.get().map(n => n.id);
            reportTitle = "Complete Graph Analysis Report";
            if (targetNodes.length === 0) {
                updateStatus("No nodes on board for report");
                return;
            }
            break;
    }
    
    // Collect detailed node and connection data
    const reportData = {
        title: reportTitle,
        scope: scope,
        nodeCount: targetNodes.length,
        nodes: [],
        connections: [],
        breaches: new Set(),
        dataTypes: new Set(),
        sources: new Set()
    };
    
    // Gather node information
    targetNodes.forEach(nodeId => {
        const node = nodes.get(nodeId);
        if (node) {
            const nodeInfo = {
                id: nodeId,
                type: node.type || "unknown",
                value: node.data?.value || node.label || "Unknown",
                label: node.label,
                breach: node.data?.breach || "Unknown",
                source: node.data?.source || "DeHashed",
                breachDate: node.data?.breachData?.breach_date || null,
                addedDate: node.data?.breachData?.added_date || null,
                notes: node.data?.notes || "",
                isAnchored: anchoredNodes.has(nodeId),
                variations: node.data?.variations?.length || 0,
                mergedImages: node.data?.mergedImages?.length || 0
            };
            
            reportData.nodes.push(nodeInfo);
            reportData.breaches.add(nodeInfo.breach);
            reportData.dataTypes.add(nodeInfo.type);
            reportData.sources.add(nodeInfo.source);
        }
    });
    
    // Gather connection information
    const allEdges = edges.get();
    const relevantEdges = allEdges.filter(edge => 
        targetNodes.includes(edge.from) && targetNodes.includes(edge.to)
    );
    
    relevantEdges.forEach(edge => {
        const fromNode = nodes.get(edge.from);
        const toNode = nodes.get(edge.to);
        
        if (fromNode && toNode) {
            const connectionInfo = {
                from: fromNode.label || fromNode.id,
                fromType: fromNode.type || "unknown", 
                to: toNode.label || toNode.id,
                toType: toNode.type || "unknown",
                type: edge.hypothetical ? "hypothetical" : 
                      edge.color?.color === "#ffffff" ? "anchored" :
                      edge.color?.color === "#ff00ff" ? "manual" :
                      edge.color?.color === "#00BFFF" ? "OSINT" :
                      edge.color?.color === "#20B2AA" ? "WHOIS" : "breach-related",
                reason: edge.title || "Related data",
                dashed: edge.dashes ? true : false
            };
            
            reportData.connections.push(connectionInfo);
        }
    });
    
    // Convert sets to arrays for JSON
    reportData.breaches = Array.from(reportData.breaches);
    reportData.dataTypes = Array.from(reportData.dataTypes);
    reportData.sources = Array.from(reportData.sources);
    
    // Generate Claude AI report with retry logic
    let retryCount = 0;
    const maxRetries = 3;
    
    while (retryCount < maxRetries) {
        try {
            updateStatus(`Generating ${scope} report... (attempt ${retryCount + 1}/${maxRetries})`);
            
            const response = await fetch("/api/ai-suggestions", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    model: "claude-sonnet-4-20250514",
                    max_tokens: 4000,
                    temperature: 0.3,
                    messages: [
                        {
                            role: "user",
                            content: `You are a cybersecurity analyst. Create a comprehensive intelligence report based on the following breach investigation data.

REPORT DATA:
${JSON.stringify(reportData, null, 2)}

Create a professional intelligence report with the following structure:

# ${reportData.title}

## Executive Summary
Provide a high-level overview of the key findings, scope, and significance.

## Data Overview  
- Total entities analyzed: ${reportData.nodeCount}
- Data types found: ${reportData.dataTypes.join(", ")}
- Breaches involved: ${reportData.breaches.length}
- Sources: ${reportData.sources.join(", ")}
- Connections identified: ${reportData.connections.length}

## Detailed Findings

### Entities by Type
Break down the data by type (emails, usernames, passwords, phones, etc.) and highlight patterns.

### Breach Analysis
Analyze which breaches are represented and their significance.

### Connection Analysis  
Describe the relationships between entities and what they reveal.

### Notable Patterns
Identify any significant patterns, clusters, or anomalies.

## Individual Entity Details
List key entities with their context and connections.

## Risk Assessment
Assess the security implications and potential impact.

## Recommendations
Provide actionable recommendations based on the findings.

## Conclusion
Summarize the key takeaways and next steps.

---
*Report generated on ${new Date().toLocaleString()} using Claude AI analysis*

Format the report in clear, professional markdown with proper headings, bullet points, and emphasis where appropriate. Be thorough but concise. Focus on actionable intelligence.`
                        }
                    ]
                })
            });

            if (response.ok) {
                const data = await response.json();
                const reportContent = data.content?.[0]?.text || data.response;
                
                if (reportContent) {
                    // Display the report in a modal
                    showReportModal(reportContent, reportTitle);
                    updateStatus(`${scope} report generated successfully`);
                    return; // Success, exit the retry loop
                } else {
                    throw new Error("No report content received");
                }
            } else if (response.status === 503) {
                // Service unavailable - Claude API overloaded
                retryCount++;
                if (retryCount < maxRetries) {
                    const delay = Math.pow(2, retryCount) * 1000; // Exponential backoff
                    updateStatus(`Claude API busy (503), retrying in ${delay/1000}s...`);
                    await new Promise(resolve => setTimeout(resolve, delay));
                    continue;
                } else {
                    throw new Error("Claude API service unavailable after multiple attempts");
                }
            } else {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
        } catch (error) {
            retryCount++;
            if (retryCount < maxRetries && (error.message.includes("503") || error.message.includes("network"))) {
                const delay = Math.pow(2, retryCount) * 1000;
                updateStatus(`Network error, retrying in ${delay/1000}s...`);
                await new Promise(resolve => setTimeout(resolve, delay));
                continue;
            } else {
                console.error("Report generation error:", error);
                console.log("Generating fallback report without Claude API...");
                generateFallbackReport(reportData, reportTitle, scope);
                break;
            }
        }
    }
};

// Generate fallback report without Claude API
function generateFallbackReport(reportData, reportTitle, scope) {
    const report = `# ${reportData.title}

## Executive Summary
This intelligence report analyzes ${reportData.nodeCount} data entities across ${reportData.breaches.length} breach sources. The analysis reveals ${reportData.connections.length} connections between entities, providing insights into data exposure patterns and potential security implications.

## Data Overview
- **Total entities analyzed:** ${reportData.nodeCount}
- **Data types found:** ${reportData.dataTypes.join(", ")}
- **Breaches involved:** ${reportData.breaches.length} (${reportData.breaches.join(", ")})
- **Sources:** ${reportData.sources.join(", ")}
- **Connections identified:** ${reportData.connections.length}
- **Anchored entities:** ${reportData.nodes.filter(n => n.isAnchored).length}

## Detailed Findings

### Entities by Type
${generateEntityBreakdown(reportData)}

### Breach Analysis
${generateBreachAnalysis(reportData)}

### Connection Analysis
The analysis identified ${reportData.connections.length} relationships between entities:
${generateConnectionAnalysis(reportData)}

### Notable Patterns
${generatePatternAnalysis(reportData)}

## Individual Entity Details
${generateEntityDetails(reportData)}

## Risk Assessment
Based on the data analysis:
- **Exposure Level:** ${assessExposureLevel(reportData)}
- **Data Sensitivity:** Multiple PII types exposed including ${reportData.dataTypes.filter(t => ['email', 'phone', 'name', 'password'].includes(t)).join(", ")}
- **Breach Scope:** ${reportData.breaches.length} different breach${reportData.breaches.length > 1 ? 'es' : ''} affecting the analyzed entities

## Recommendations
1. **Immediate Actions:**
   - Monitor all exposed email addresses for suspicious activity
   - Change passwords for all affected accounts
   - Enable two-factor authentication where possible

2. **Long-term Security:**
   - Implement breach monitoring for identified entities
   - Review and strengthen authentication mechanisms
   - Consider identity protection services

## Conclusion
This analysis of ${reportData.nodeCount} entities reveals a complex web of data exposures across ${reportData.breaches.length} breach incidents. The ${reportData.connections.length} identified connections highlight the interconnected nature of the exposed data and underscore the importance of comprehensive security monitoring.

---
*Report generated on ${new Date().toLocaleString()} using automated analysis (Claude API unavailable)*`;

    showReportModal(report, reportTitle);
    updateStatus(`${scope} report generated (fallback mode)`);
}

// Helper functions for fallback report generation
function generateEntityBreakdown(reportData) {
    const typeGroups = {};
    reportData.nodes.forEach(node => {
        if (!typeGroups[node.type]) typeGroups[node.type] = 0;
        typeGroups[node.type]++;
    });
    
    let breakdown = "";
    Object.entries(typeGroups).forEach(([type, count]) => {
        breakdown += `- **${type.charAt(0).toUpperCase() + type.slice(1)}:** ${count} entities\n`;
    });
    return breakdown;
}

function generateBreachAnalysis(reportData) {
    if (reportData.breaches.length === 0) return "No specific breach information available.";
    
    let analysis = `The following ${reportData.breaches.length} breach${reportData.breaches.length > 1 ? 'es were' : ' was'} identified:\n`;
    reportData.breaches.forEach(breach => {
        const breachNodes = reportData.nodes.filter(n => n.breach === breach);
        analysis += `- **${breach}:** ${breachNodes.length} entities\n`;
    });
    return analysis;
}

function generateConnectionAnalysis(reportData) {
    if (reportData.connections.length === 0) return "- No direct connections identified between entities.";
    
    const connectionTypes = {};
    reportData.connections.forEach(conn => {
        if (!connectionTypes[conn.type]) connectionTypes[conn.type] = 0;
        connectionTypes[conn.type]++;
    });
    
    let analysis = "";
    Object.entries(connectionTypes).forEach(([type, count]) => {
        analysis += `- **${type.charAt(0).toUpperCase() + type.slice(1)} connections:** ${count}\n`;
    });
    return analysis;
}

function generatePatternAnalysis(reportData) {
    const patterns = [];
    
    // Check for multiple data types per entity
    const multiTypeEntities = reportData.nodes.filter(n => n.variations > 0).length;
    if (multiTypeEntities > 0) {
        patterns.push(`${multiTypeEntities} entities have multiple data variations`);
    }
    
    // Check for entities across multiple breaches
    const entityBreaches = {};
    reportData.nodes.forEach(node => {
        if (!entityBreaches[node.value]) entityBreaches[node.value] = new Set();
        entityBreaches[node.value].add(node.breach);
    });
    
    const multiBreachEntities = Object.values(entityBreaches).filter(breaches => breaches.size > 1).length;
    if (multiBreachEntities > 0) {
        patterns.push(`${multiBreachEntities} entities appear across multiple breaches`);
    }
    
    // Check for high-connectivity nodes
    const highConnectivity = reportData.connections.length > reportData.nodeCount;
    if (highConnectivity) {
        patterns.push("High connectivity detected - entities are highly interconnected");
    }
    
    return patterns.length > 0 ? patterns.map(p => `- ${p}`).join("\n") : "- No significant patterns detected in current dataset";
}

function generateEntityDetails(reportData) {
    const importantEntities = reportData.nodes.filter(n => n.isAnchored || n.variations > 0 || n.mergedImages > 0);
    
    if (importantEntities.length === 0) {
        return "No entities marked as particularly significant.";
    }
    
    let details = "";
    importantEntities.slice(0, 10).forEach(entity => { // Limit to first 10
        details += `**${entity.value}** (${entity.type})\n`;
        details += `- Source: ${entity.source} (${entity.breach})\n`;
        if (entity.isAnchored) details += `- Status: Anchored for investigation\n`;
        if (entity.variations > 0) details += `- Variations: ${entity.variations} related entries\n`;
        if (entity.mergedImages > 0) details += `- Images: ${entity.mergedImages} attached\n`;
        if (entity.notes) details += `- Notes: ${entity.notes.substring(0, 100)}${entity.notes.length > 100 ? '...' : ''}\n`;
        details += "\n";
    });
    
    return details;
}

function assessExposureLevel(reportData) {
    const sensitiveTypes = ['email', 'phone', 'password', 'name', 'ssn', 'cc'].filter(type => 
        reportData.dataTypes.includes(type)
    ).length;
    
    if (sensitiveTypes >= 4) return "HIGH - Multiple sensitive data types exposed";
    if (sensitiveTypes >= 2) return "MEDIUM - Some sensitive data exposed";
    return "LOW - Limited sensitive data exposure";
}

// Show report in a modal window
function showReportModal(reportContent, title) {
    // Convert markdown to HTML for better display
    const htmlContent = reportContent
        .replace(/^# (.+)$/gm, "<h1>$1</h1>")
        .replace(/^## (.+)$/gm, "<h2>$1</h2>")
        .replace(/^### (.+)$/gm, "<h3>$1</h3>")
        .replace(/^\* (.+)$/gm, "<li>$1</li>")
        .replace(/^- (.+)$/gm, "<li>$1</li>")
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/\*(.+?)\*/g, "<em>$1</em>")
        .replace(/\n\n/g, "</p><p>")
        .replace(/^(?!<[hul])/gm, "<p>")
        .replace(/$(?![hul>])/gm, "</p>")
        .replace(/<p><\/p>/g, "")
        .replace(/<p>(<[hul])/g, "$1")
        .replace(/(<\/[hul]>)<\/p>/g, "$1");
    
    const modal = document.createElement("div");
    modal.id = "reportModal";
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.9);
        z-index: 20000;
        display: flex;
        justify-content: center;
        align-items: center;
    `;
    
    modal.innerHTML = `
        <div style="
            background: ${UI_COLORS.surface};
            border: 1px solid ${UI_COLORS.border};
            width: 90%;
            max-width: 1000px;
            height: 90%;
            padding: 24px;
            overflow-y: auto;
            font-family: 'IBM Plex Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
            color: ${UI_COLORS.textPrimary};
            position: relative;
            border-radius: 18px;
            box-shadow: 0 24px 60px rgba(15, 23, 42, 0.65);
            backdrop-filter: blur(8px);
        ">
            <div style="display: flex; align-items: center; margin-bottom: 24px; border-bottom: 1px solid ${UI_COLORS.border}; padding-bottom: 12px; gap: 12px;">
                <h2 style="margin: 0; color: ${UI_COLORS.accent}; text-transform: uppercase; letter-spacing: 0.22em; font-size: 13px;">${title}</h2>
                <div style="margin-left: auto; display: flex; gap: 10px;">
                    <button onclick="copyReportToClipboard()" style="background: ${UI_COLORS.surfaceMuted}; color: ${UI_COLORS.textPrimary}; border: 1px solid ${UI_COLORS.border}; padding: 6px 12px; cursor: pointer; border-radius: 9999px; letter-spacing: 0.18em; text-transform: uppercase; font-size: 10px;">Copy</button>
                    <button onclick="downloadReport()" style="background: ${UI_COLORS.surfaceMuted}; color: ${UI_COLORS.textPrimary}; border: 1px solid ${UI_COLORS.border}; padding: 6px 12px; cursor: pointer; border-radius: 9999px; letter-spacing: 0.18em; text-transform: uppercase; font-size: 10px;">Download</button>
                    <button onclick="closeReportModal()" style="background: rgba(15, 23, 42, 0.9); color: ${UI_COLORS.textPrimary}; border: 1px solid ${UI_COLORS.border}; padding: 6px 12px; cursor: pointer; border-radius: 9999px; letter-spacing: 0.18em; text-transform: uppercase; font-size: 10px;">Close</button>
                </div>
            </div>
            <div id="reportContent" style="line-height: 1.7; font-size: 12px; color: ${UI_COLORS.textPrimary};">
                ${htmlContent}
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Store report content globally for copy/download
    window.currentReportContent = reportContent;
    window.currentReportTitle = title;
}

// Close report modal
window.closeReportModal = function() {
    const modal = document.getElementById("reportModal");
    if (modal) modal.remove();
}

// Copy report to clipboard
window.copyReportToClipboard = function() {
    if (window.currentReportContent) {
        navigator.clipboard.writeText(window.currentReportContent).then(() => {
            updateStatus("Report copied to clipboard");
        }).catch(err => {
            console.error("Copy failed:", err);
            updateStatus("Copy failed");
        });
    }
}

// Download report as text file
window.downloadReport = function() {
    if (window.currentReportContent && window.currentReportTitle) {
        const blob = new Blob([window.currentReportContent], { type: "text/markdown" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${window.currentReportTitle.replace(/[^a-zA-Z0-9]/g, "_")}_${new Date().toISOString().split("T")[0]}.md`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        updateStatus("Report downloaded");
    }
}

// ==================== UNIVERSAL UNDO SYSTEM ====================

// Save current graph state to undo stack
function saveUndoState(actionDescription = "Action") {
    if (isRestoringFromUndo) return; // Don't save undo states when restoring
    
    console.log(`Saving undo state: ${actionDescription}`);
    
    const currentState = {
        timestamp: Date.now(),
        description: actionDescription,
        nodes: nodes.get(),
        edges: edges.get(),
        nodeIdCounter: nodeIdCounter,
        valueToNodeMap: Array.from(valueToNodeMap.entries()),
        breachConnections: Array.from(breachConnections.entries()),
        nodeSearchQueries: Array.from(nodeSearchQueries.entries()),
        anchoredNodes: Array.from(anchoredNodes),
        selectedNodes: Array.from(selectedNodes),
        clusters: Array.from(clusters.entries()).map(([id, cluster]) => [
            id, {
                ...cluster,
                nodeIds: Array.from(cluster.nodeIds)
            }
        ]),
        clusterIdCounter: clusterIdCounter,
        showClusterContents: showClusterContents
    };
    
    // Add to undo stack
    undoStack.push(currentState);
    
    // Limit stack size
    if (undoStack.length > MAX_UNDO_STACK_SIZE) {
        undoStack.shift(); // Remove oldest state
    }
    
    // Update undo button
    const undoBtn = document.getElementById('undoBtn');
    if (undoBtn) {
        undoBtn.disabled = false;
        undoBtn.title = `Undo: ${actionDescription}`;
    }
    
    console.log(`Undo stack now has ${undoStack.length} states`);
}

// Restore previous graph state
function undoLastAction() {
    if (undoStack.length === 0) {
        updateStatus("Nothing to undo");
        return;
    }
    
    const previousState = undoStack.pop();
    isRestoringFromUndo = true;
    
    console.log(`Undoing: ${previousState.description}`);
    
    try {
        // Clear current graph
        nodes.clear();
        edges.clear();
        
        // Restore all data
        nodes.add(previousState.nodes);
        edges.add(previousState.edges);
        
        // Restore global variables
        nodeIdCounter = previousState.nodeIdCounter;
        // Restore value map with case-insensitive migration
        valueToNodeMap = new Map();
        for (const [oldKey, nodeId] of previousState.valueToNodeMap) {
            const parts = oldKey.split('_');
            if (parts.length >= 2) {
                const type = parts[0];
                const value = parts.slice(1).join('_');
                const newKey = `${type}_${value.toLowerCase().trim()}`;
                valueToNodeMap.set(newKey, nodeId);
            } else {
                valueToNodeMap.set(oldKey, nodeId);
            }
        }
        breachConnections = new Map(previousState.breachConnections);
        nodeSearchQueries = new Map(previousState.nodeSearchQueries || []);
        anchoredNodes = new Set(previousState.anchoredNodes);
        selectedNodes = new Set(previousState.selectedNodes);
        clusterIdCounter = previousState.clusterIdCounter || 0;
        showClusterContents = previousState.showClusterContents !== undefined ? previousState.showClusterContents : true;
        
        // Restore clusters
        clusters.clear();
        if (previousState.clusters) {
            previousState.clusters.forEach(([id, clusterData]) => {
                clusters.set(id, {
                    ...clusterData,
                    nodeIds: new Set(clusterData.nodeIds)
                });
            });
        }
        
        // Update UI
        network.selectNodes(Array.from(selectedNodes));
        updateClusterButtons();
        updateNodeCount();
        updateEdgeCount();
        
        // Update cluster contents checkbox
        const clusterContentsCheckbox = document.getElementById('showClusterContents');
        if (clusterContentsCheckbox) {
            clusterContentsCheckbox.checked = showClusterContents;
        }
        
        // Update cluster visuals
        updateClusterVisuals();
        
        updateStatus(`Undid: ${previousState.description}`);
        
    } catch (error) {
        console.error("Error during undo:", error);
        updateStatus(`Undo failed: ${error.message}`);
    } finally {
        isRestoringFromUndo = false;
    }
    
    // Update undo button
    const undoBtn = document.getElementById('undoBtn');
    if (undoBtn) {
        if (undoStack.length === 0) {
            undoBtn.disabled = true;
            undoBtn.title = "Nothing to undo";
        } else {
            undoBtn.title = `Undo: ${undoStack[undoStack.length - 1].description}`;
        }
    }
    
    console.log(`Undo stack now has ${undoStack.length} states`);
}

// ==================== CLUSTER SYSTEM ====================

// Create a new cluster with selected nodes
function createCluster(nodeIds, clusterName = null) {
    console.log("createCluster called with:", nodeIds, clusterName);
    
    if (!nodeIds || nodeIds.length === 0) {
        console.log("No nodes provided for cluster creation");
        updateStatus("No nodes selected for cluster creation");
        return null;
    }
    
    console.log("Getting cluster nodes from vis.js dataset");
    const nodesToCluster = nodes.get(nodeIds);
    console.log("Retrieved nodes:", nodesToCluster);
    
    const clusterId = `cluster_${clusterIdCounter++}`;
    const name = clusterName || `Cluster ${clusters.size + 1}`;
    
    // Calculate cluster position (center of contained nodes)
    let centerX = 0, centerY = 0;
    nodesToCluster.forEach(node => {
        centerX += node.x || 0;
        centerY += node.y || 0;
    });
    centerX /= nodesToCluster.length;
    centerY /= nodesToCluster.length;
    
    // Create cluster data structure
    const cluster = {
        id: clusterId,
        label: name,
        nodeIds: new Set(nodeIds),
        x: centerX,
        y: centerY,
        width: 400,
        height: 300,
        color: '#444444',
        borderColor: '#ff6600',
        borderWidth: 4,
        visible: true,
        contentsVisible: showClusterContents
    };
    
    clusters.set(clusterId, cluster);
    
    // Update nodes to be part of cluster
    nodeIds.forEach(nodeId => {
        const node = nodes.get(nodeId);
        if (node) {
            node.clusterId = clusterId;
            node.clusterRelativeX = (node.x || 0) - centerX;
            node.clusterRelativeY = (node.y || 0) - centerY;
            // Show nodes by default since showClusterContents is true
            node.hidden = !showClusterContents;
        }
    });
    
    nodes.update(nodesToCluster);
    
    console.log("Cluster data structure created:", cluster);
    
    // Create cluster visual representation
    console.log("Calling updateClusterVisuals...");
    updateClusterVisuals();
    
    // Rebuild connections to use cluster connections
    console.log("Calling rebuildClusterConnections...");
    rebuildClusterConnections();
    
    console.log("Cluster creation completed successfully");
    updateStatus(`Created cluster "${name}" with ${nodeIds.length} nodes`);
    return clusterId;
}

// Remove a cluster and restore individual nodes
function removeCluster(clusterId) {
    const cluster = clusters.get(clusterId);
    if (!cluster) return;
    
    // First, restore all original edges that were hidden by clustering
    const allEdges = edges.get();
    allEdges.forEach(edge => {
        // Remove cluster-specific edges
        if (edge.id.includes('cluster_') || edge.originalEdgeId) {
            edges.remove(edge.id);
        } else {
            // Restore original edges by making them visible
            edge.hidden = false;
            edges.update(edge);
        }
    });
    
    // Restore nodes
    const clusterNodes = nodes.get(Array.from(cluster.nodeIds));
    clusterNodes.forEach(node => {
        delete node.clusterId;
        delete node.clusterRelativeX;
        delete node.clusterRelativeY;
        node.hidden = false;
    });
    
    nodes.update(clusterNodes);
    clusters.delete(clusterId);
    
    // Remove cluster visual
    updateClusterVisuals();
    
    // Only rebuild if there are still clusters
    if (clusters.size > 0) {
        rebuildClusterConnections();
    }
    
    updateStatus(`Removed cluster "${cluster.label}" - connections restored`);
}

// Toggle visibility of cluster contents
window.toggleClusterContents = function(show = null) {
    showClusterContents = show !== null ? show : !showClusterContents;
    
    // Update all cluster nodes visibility
    clusters.forEach(cluster => {
        const clusterNodes = nodes.get(Array.from(cluster.nodeIds));
        clusterNodes.forEach(node => {
            node.hidden = !showClusterContents;
        });
        nodes.update(clusterNodes);
        cluster.contentsVisible = showClusterContents;
    });
    
    // When showing contents, ensure clusters are large enough
    if (showClusterContents) {
        // Give nodes time to update positions
        setTimeout(() => {
            updateClusterVisuals();
        }, 100);
    } else {
        updateClusterVisuals();
    }
    
    updateStatus(`Cluster contents ${showClusterContents ? 'shown' : 'hidden'}`);
}

// Update cluster visual representation
function updateClusterVisuals() {
    console.log("updateClusterVisuals called");
    console.log("Current clusters:", clusters);
    
    // Remove existing cluster visuals
    const existingClusters = nodes.get().filter(node => node.type === 'cluster' || node.type === 'cluster_inner');
    console.log("Existing cluster visuals to remove:", existingClusters);
    if (existingClusters.length > 0) {
        nodes.remove(existingClusters.map(c => c.id));
    }
    
    // Add cluster visual nodes
    const clusterVisuals = [];
    console.log("Processing", clusters.size, "clusters");
    clusters.forEach(cluster => {
        if (cluster.visible) {
            // Calculate cluster bounds based on contained nodes
            const clusterNodes = nodes.get(Array.from(cluster.nodeIds)).filter(n => n.type !== 'cluster');
            if (clusterNodes.length > 0) {
                let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
                clusterNodes.forEach(node => {
                    minX = Math.min(minX, (node.x || 0) - 25);
                    maxX = Math.max(maxX, (node.x || 0) + 25);
                    minY = Math.min(minY, (node.y || 0) - 25);
                    maxY = Math.max(maxY, (node.y || 0) + 25);
                });
                
                // Add much larger padding for cluster frame
                const padding = 80;
                minX -= padding;
                maxX += padding;
                minY -= padding;
                maxY += padding;
                
                cluster.x = (minX + maxX) / 2;
                cluster.y = (minY + maxY) / 2;
                cluster.width = maxX - minX;
                cluster.height = maxY - minY;
            }
            
            // Create cluster frame visual
            clusterVisuals.push({
                id: cluster.id,
                label: cluster.label,
                x: cluster.x,
                y: cluster.y,
                type: 'cluster',
                shape: 'box',
                color: {
                    background: 'rgba(255, 102, 0, 0.05)',
                    border: cluster.borderColor,
                    highlight: {
                        background: 'rgba(255, 102, 0, 0.1)',
                        border: '#ffaa44'
                    }
                },
                borderWidth: 6,
                borderWidthSelected: 8,
                shapeProperties: {
                    borderDashes: false,
                    borderRadius: 10
                },
                font: {
                    color: '#ff6600',
                    size: 18,
                    face: 'Arial',
                    bold: true
                },
                size: 1, // Size controlled by width/height constraints
                widthConstraint: { minimum: cluster.width, maximum: cluster.width },
                heightConstraint: { minimum: cluster.height, maximum: cluster.height },
                physics: false,
                fixed: false,
                mass: 10 // Heavy mass to prevent movement
            });
            
            // Create inner border for double-line effect
            clusterVisuals.push({
                id: cluster.id + '_inner',
                label: '',
                x: cluster.x,
                y: cluster.y,
                type: 'cluster_inner',
                shape: 'box',
                color: {
                    background: 'transparent',
                    border: cluster.borderColor,
                    highlight: {
                        background: 'transparent',
                        border: '#ffaa44'
                    }
                },
                borderWidth: 2,
                borderWidthSelected: 3,
                shapeProperties: {
                    borderDashes: false,
                    borderRadius: 8
                },
                size: 1,
                widthConstraint: { minimum: cluster.width - 10, maximum: cluster.width - 10 },
                heightConstraint: { minimum: cluster.height - 10, maximum: cluster.height - 10 },
                physics: false,
                fixed: false,
                chosen: false,
                mass: 10
            });
        }
    });
    
    console.log("Generated cluster visuals:", clusterVisuals);
    if (clusterVisuals.length > 0) {
        console.log("Adding", clusterVisuals.length, "cluster visuals to graph");
        nodes.add(clusterVisuals);
        console.log("Cluster visuals added successfully");
    } else {
        console.log("No cluster visuals to add");
    }
}

// Rebuild connections to route through clusters
function rebuildClusterConnections() {
    if (clusters.size === 0) return;
    
    const allEdges = edges.get();
    const newEdges = [];
    const clusteredEdges = new Set(); // Track which edges have been clustered
    
    allEdges.forEach(edge => {
        const fromNode = nodes.get(edge.from);
        const toNode = nodes.get(edge.to);
        
        if (!fromNode || !toNode) return;
        
        const fromCluster = fromNode.clusterId;
        const toCluster = toNode.clusterId;
        
        // If both nodes are in the same cluster, hide the edge when contents are hidden
        if (fromCluster && toCluster && fromCluster === toCluster) {
            edge.hidden = !showClusterContents;
            newEdges.push(edge);
        }
        // If nodes are in different clusters, create cluster-to-cluster connection
        else if (fromCluster && toCluster && fromCluster !== toCluster) {
            const clusterEdgeId = `${fromCluster}_to_${toCluster}`;
            
            if (!clusteredEdges.has(clusterEdgeId)) {
                newEdges.push({
                    id: clusterEdgeId,
                    from: fromCluster,
                    to: toCluster,
                    color: { color: '#ffaa00', opacity: 0.8 },
                    width: 3,
                    dashes: [5, 5],
                    title: `Cluster connection (${Array.from(clusters.get(fromCluster).nodeIds).length} ↔ ${Array.from(clusters.get(toCluster).nodeIds).length} nodes)`,
                    originalEdgeId: edge.id
                });
                clusteredEdges.add(clusterEdgeId);
            }
            
            // Hide original edge unless showing cluster contents
            edge.hidden = !showClusterContents;
            newEdges.push(edge);
        }
        // If one node is in cluster, connect to cluster
        else if (fromCluster && !toCluster) {
            const clusterEdgeId = `${fromCluster}_to_${edge.to}`;
            
            if (!clusteredEdges.has(clusterEdgeId)) {
                newEdges.push({
                    id: clusterEdgeId,
                    from: fromCluster,
                    to: edge.to,
                    color: { color: '#ff8800', opacity: 0.8 },
                    width: 2,
                    dashes: [3, 3],
                    title: `Cluster to node connection`,
                    originalEdgeId: edge.id
                });
                clusteredEdges.add(clusterEdgeId);
            }
            
            edge.hidden = !showClusterContents;
            newEdges.push(edge);
        }
        else if (!fromCluster && toCluster) {
            const clusterEdgeId = `${edge.from}_to_${toCluster}`;
            
            if (!clusteredEdges.has(clusterEdgeId)) {
                newEdges.push({
                    id: clusterEdgeId,
                    from: edge.from,
                    to: toCluster,
                    color: { color: '#ff8800', opacity: 0.8 },
                    width: 2,
                    dashes: [3, 3],
                    title: `Node to cluster connection`,
                    originalEdgeId: edge.id
                });
                clusteredEdges.add(clusterEdgeId);
            }
            
            edge.hidden = !showClusterContents;
            newEdges.push(edge);
        }
        // Normal edge between unclustered nodes
        else {
            newEdges.push(edge);
        }
    });
    
    edges.update(newEdges);
}

// Move cluster and all contained nodes
function moveCluster(clusterId, deltaX, deltaY) {
    const cluster = clusters.get(clusterId);
    if (!cluster) return;
    
    // Update cluster position
    cluster.x += deltaX;
    cluster.y += deltaY;
    
    // Move all contained nodes
    const clusterNodes = nodes.get(Array.from(cluster.nodeIds));
    clusterNodes.forEach(node => {
        node.x = (node.x || 0) + deltaX;
        node.y = (node.y || 0) + deltaY;
    });
    
    nodes.update(clusterNodes);
    updateClusterVisuals();
}

// Add selected nodes to existing cluster
function addNodesToCluster(clusterId, nodeIds) {
    const cluster = clusters.get(clusterId);
    if (!cluster) return;
    
    nodeIds.forEach(nodeId => {
        cluster.nodeIds.add(nodeId);
        const node = nodes.get(nodeId);
        if (node) {
            node.clusterId = clusterId;
            node.clusterRelativeX = (node.x || 0) - cluster.x;
            node.clusterRelativeY = (node.y || 0) - cluster.y;
            if (!showClusterContents) {
                node.hidden = true;
            }
        }
    });
    
    nodes.update(nodes.get(nodeIds));
    updateClusterVisuals();
    rebuildClusterConnections();
    updateStatus(`Added ${nodeIds.length} nodes to cluster "${cluster.label}"`);
}

// Remove nodes from cluster
function removeNodesFromCluster(nodeIds) {
    nodeIds.forEach(nodeId => {
        const node = nodes.get(nodeId);
        if (node && node.clusterId) {
            const cluster = clusters.get(node.clusterId);
            if (cluster) {
                cluster.nodeIds.delete(nodeId);
            }
            delete node.clusterId;
            delete node.clusterRelativeX;
            delete node.clusterRelativeY;
            node.hidden = false;
        }
    });
    
    nodes.update(nodes.get(nodeIds));
    updateClusterVisuals();
    rebuildClusterConnections();
    updateStatus(`Removed ${nodeIds.length} nodes from cluster`);
}

// Get cluster information for a node
function getNodeCluster(nodeId) {
    const node = nodes.get(nodeId);
    return node && node.clusterId ? clusters.get(node.clusterId) : null;
}

// UI functions for cluster management
window.createClusterFromSelection = function() {
    console.log("createClusterFromSelection called");
    console.log("selectedNodes:", selectedNodes);
    
    const selectedNodeIds = Array.from(selectedNodes);
    console.log("selectedNodeIds:", selectedNodeIds);
    
    if (selectedNodeIds.length < 2) {
        console.log("Not enough nodes selected");
        updateStatus("Select at least 2 nodes to create a cluster");
        return;
    }
    
    // Save undo state before creating cluster
    saveUndoState("Create Cluster");
    
    console.log("Prompting for cluster name");
    const clusterName = prompt("Enter cluster name:", `Cluster ${clusters.size + 1}`);
    if (clusterName === null) {
        console.log("User cancelled cluster creation");
        return; // User cancelled
    }
    
    console.log("Creating cluster with name:", clusterName);
    const clusterId = createCluster(selectedNodeIds, clusterName || undefined);
    console.log("Created cluster ID:", clusterId);
    
    if (clusterId) {
        // Clear selection after clustering
        network.selectNodes([]);
        selectedNodes.clear();
        updateClusterButtons();
        console.log("Cluster creation completed");
    } else {
        console.log("Cluster creation failed");
    }
}

window.removeSelectedCluster = function() {
    const selectedNodeIds = Array.from(selectedNodes);
    if (selectedNodeIds.length !== 1) {
        updateStatus("Select exactly one cluster to remove");
        return;
    }
    
    const selectedNode = nodes.get(selectedNodeIds[0]);
    if (!selectedNode || selectedNode.type !== 'cluster') {
        updateStatus("Selected item is not a cluster");
        return;
    }
    
    if (confirm(`Remove cluster "${selectedNode.label}"? All nodes will be restored.`)) {
        // Save undo state before removing cluster
        saveUndoState(`Remove Cluster "${selectedNode.label}"`);
        
        removeCluster(selectedNode.id);
        network.selectNodes([]);
        selectedNodes.clear();
        updateClusterButtons();
    }
}

function updateClusterButtons() {
    console.log("updateClusterButtons called, selectedNodes.size:", selectedNodes.size);
    
    const createBtn = document.getElementById('createClusterBtn');
    const removeBtn = document.getElementById('removeClusterBtn');
    
    console.log("createBtn found:", !!createBtn);
    console.log("removeBtn found:", !!removeBtn);
    
    if (createBtn) {
        const shouldDisable = selectedNodes.size < 2;
        createBtn.disabled = shouldDisable;
        console.log("Create button disabled:", shouldDisable);
    }
    
    if (removeBtn) {
        const selectedNodeIds = Array.from(selectedNodes);
        if (selectedNodeIds.length === 1) {
            const selectedNode = nodes.get(selectedNodeIds[0]);
            removeBtn.disabled = !selectedNode || selectedNode.type !== 'cluster';
        } else {
            removeBtn.disabled = true;
        }
        console.log("Remove button disabled:", removeBtn.disabled);
    }
}

// Add cluster support to existing context menu
function addClusterContextMenuItems(menu, nodeId) {
    const node = nodes.get(nodeId);
    if (!node) return;
    
    menu.innerHTML += '<hr>';
    
    if (node.type === 'cluster') {
        menu.innerHTML += `
            <div class="context-menu-item" onclick="removeCluster('${nodeId}'); hideContextMenu();">
                Remove Cluster
            </div>
            <div class="context-menu-item" onclick="toggleClusterContents(); hideContextMenu();">
                ${showClusterContents ? 'Hide' : 'Show'} Contents
            </div>
        `;
    } else {
        const cluster = getNodeCluster(nodeId);
        if (cluster) {
            menu.innerHTML += `
                <div class="context-menu-item" onclick="removeNodesFromCluster(['${nodeId}']); hideContextMenu();">
                    Remove from Cluster
                </div>
            `;
        } else if (selectedNodes.size >= 2) {
            menu.innerHTML += `
                <div class="context-menu-item" onclick="createClusterFromSelection(); hideContextMenu();">
                    Create Cluster from Selected
                </div>
            `;
        }
    }
}

// Integrate cluster drag handling
function handleClusterDrag(nodeId, event) {
    const node = nodes.get(nodeId);
    if (!node || node.type !== 'cluster') return false;
    
    // This will be called during drag operations
    const cluster = clusters.get(nodeId);
    if (cluster) {
        const newPosition = network.getPositions([nodeId])[nodeId];
        const deltaX = newPosition.x - cluster.x;
        const deltaY = newPosition.y - cluster.y;
        
        if (Math.abs(deltaX) > 5 || Math.abs(deltaY) > 5) {
            moveCluster(nodeId, deltaX, deltaY);
        }
    }
    
    return true;
}

// Global base URL for the (optional) external project API; default to same-origin.
const DRILL_SEARCH_BASE_URL = window.DRILL_SEARCH_BASE_URL || '';

// Project Management Functions
let currentProjectId = null;

async function loadProjects() {
    try {
        const response = await fetch(`${DRILL_SEARCH_BASE_URL}/api/projects`);
        const data = await response.json();
        
        const projectSelect = document.getElementById('projectSelect');
        projectSelect.innerHTML = '';
        
        if (data.projects.length === 0) {
            // No projects, create a default one
            await createNewProject('Default Project', 'Initial project');
            return;
        }
        
        data.projects.forEach(project => {
            const option = document.createElement('option');
            option.value = project.id;
            option.textContent = project.label || project.name;
            if (project.is_active) {
                option.selected = true;
                currentProjectId = project.id;
            }
            projectSelect.appendChild(option);
        });
        
        // Load active project's graph
        await loadActiveProject();
    } catch (error) {
        console.error('Failed to load projects:', error);
        updateStatus('Failed to load projects');
    }
}

async function loadActiveProject() {
    try {
        // Otherwise proceed with normal EYE-D project loading
        const response = await fetch('/api/projects/active');
        const data = await response.json();

        if (data.project) {
            currentProjectId = data.project.id;
            
            // Clear current graph
            nodes.clear();
            edges.clear();
            nodeIdCounter = 0;
            valueToNodeMap.clear();
            breachConnections.clear();
            nodeSearchQueries.clear();
            activeQueryNodes.clear();
            anchoredNodes.clear();
            selectedNodes.clear();
            searchCache.clear();

            // Load graph from Cymonides-1 (C-1) Elasticsearch when available
            let loadedFromC1 = false;
            if (window.C1Integration && typeof window.C1Integration.initializeC1Integration === 'function') {
                try {
                    await window.C1Integration.initializeC1Integration(currentProjectId);
                    loadedFromC1 = true;
                } catch (e) {
                    console.error('[C-1] Failed to load graph from Elasticsearch:', e);
                }
            }

            // Fallback: legacy per-project stored graph_data (should not be primary)
            if (!loadedFromC1 && data.project.graph_data) {
                console.log('[Legacy] Project has graph_data; loading as fallback');

                let graphData = data.project.graph_data;
                if (typeof graphData === 'string') {
                    try {
                        graphData = JSON.parse(graphData);
                    } catch (e) {
                        console.error('Failed to parse graph data:', e);
                        updateStatus('Failed to parse project data');
                        return;
                    }
                }

                if (graphData.nodes && graphData.nodes.length > 0) {
                    loadGraphState(graphData);
                    setTimeout(() => network.fit(), 500);
                }
            }
            
            // Load entities for the project
            await loadProjectEntities(data.project.name);
            
            updateStatus(`Loaded project: ${data.project.name}`);
        }
    } catch (error) {
        console.error('Failed to load active project:', error);
        updateStatus('Failed to load active project');
    }
}

// Entity Panel Functions
let entityPanelVisible = false;

window.toggleEntityPanel = function() {
    const panel = document.getElementById('entity-panel');
    entityPanelVisible = !entityPanelVisible;
    panel.style.display = entityPanelVisible ? 'flex' : 'none';
    
    if (entityPanelVisible) {
        // Reload entities when panel is shown
        const projectSelect = document.getElementById('projectSelect');
        const projectName = projectSelect.options[projectSelect.selectedIndex]?.text;
        if (projectName && projectName !== 'Loading...') {
            loadProjectEntities(projectName);
        }
    }
};

async function loadProjectEntities(projectName) {
    if (!projectName) return;
    
    try {
        console.log('Loading entities for project:', projectName);
        const response = await fetch(`/api/projects/${encodeURIComponent(projectName)}/entities`);
        
        if (!response.ok) {
            if (response.status === 503) {
                document.getElementById('entity-stats').innerHTML = `
                    <div style="color: #ff6600;">Entity features not available</div>
                `;
                document.getElementById('entity-list').innerHTML = '';
                return;
            }
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.success) {
            // Update stats
            document.getElementById('entity-stats').innerHTML = `
                <div style="color: #00ff00; margin-bottom: 5px;">📊 Project: ${projectName}</div>
                <div style="display: flex; justify-content: space-between;">
                    <span>Total Entities: <strong style="color: #00ffff;">${data.total_entities}</strong></span>
                    <span>Total Facts: <strong style="color: #ffff00;">${data.total_facts}</strong></span>
                </div>
            `;
            
            // Display entities
            const entityList = document.getElementById('entity-list');
            entityList.innerHTML = '';
            
            // Group by type
            const entityTypes = {};
            data.entities.forEach(entity => {
                if (!entityTypes[entity.type]) {
                    entityTypes[entity.type] = [];
                }
                entityTypes[entity.type].push(entity);
            });
            
            // Display each type
            Object.entries(entityTypes).forEach(([type, entities]) => {
                const typeSection = document.createElement('div');
                typeSection.style.cssText = 'margin-bottom: 15px;';
                
                const typeHeader = document.createElement('div');
                typeHeader.style.cssText = `color: ${UI_COLORS.accent}; font-weight: 600; margin-bottom: 6px; cursor: pointer; letter-spacing: 0.16em; text-transform: uppercase; font-size: 11px;`;
                typeHeader.innerHTML = `▼ ${type.toUpperCase()} (${entities.length})`;
                typeHeader.onclick = () => toggleTypeSection(type);

                const typeContent = document.createElement('div');
                typeContent.id = `entity-type-${type}`;
                typeContent.style.cssText = 'margin-left: 10px;';

                entities.forEach(entity => {
                    const entityDiv = document.createElement('div');
                    entityDiv.style.cssText = `margin-bottom: 10px; padding: 10px; background: ${UI_COLORS.surfaceMuted}; border: 1px solid ${UI_COLORS.border}; border-radius: 12px; cursor: pointer; transition: border-color 0.2s ease, transform 0.2s ease;`;
                    entityDiv.onmouseover = () => {
                        entityDiv.style.borderColor = UI_COLORS.accent;
                        entityDiv.style.transform = 'translateY(-2px)';
                    };
                    entityDiv.onmouseout = () => {
                        entityDiv.style.borderColor = UI_COLORS.border;
                        entityDiv.style.transform = 'none';
                    };
                    entityDiv.onclick = () => showEntityFacts(projectName, entity.name);

                    entityDiv.innerHTML = `
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="color: ${UI_COLORS.textPrimary}; font-weight: 600; letter-spacing: 0.08em;">${escapeHtml(entity.name)}</span>
                            <span style="color: ${UI_COLORS.textMuted}; font-size: 10px;">${entity.fact_count} facts</span>
                        </div>
                        ${entity.facts.length > 0 ? `
                            <div style="margin-top: 5px; font-size: 10px; color: ${UI_COLORS.textMuted};">
                                ${escapeHtml(entity.facts[0].fact || entity.facts[0].content || '').substring(0, 100)}...
                            </div>
                        ` : ''}
                    `;
                    
                    typeContent.appendChild(entityDiv);
                });
                
                typeSection.appendChild(typeHeader);
                typeSection.appendChild(typeContent);
                entityList.appendChild(typeSection);
            });
            
            // Show panel if hidden
            if (!entityPanelVisible) {
                toggleEntityPanel();
            }
        }
    } catch (error) {
        console.error('Failed to load entities:', error);
        document.getElementById('entity-stats').innerHTML = `
            <div style="color: #ff0000;">Failed to load entities: ${error.message}</div>
        `;
    }
}

function toggleTypeSection(type) {
    const section = document.getElementById(`entity-type-${type}`);
    if (section) {
        section.style.display = section.style.display === 'none' ? 'block' : 'none';
    }
}

async function showEntityFacts(projectName, entityName) {
    try {
        const response = await fetch(`/api/projects/${encodeURIComponent(projectName)}/entity/${encodeURIComponent(entityName)}/facts`);
        const data = await response.json();
        
        if (data.success) {
            // Create modal to show all facts
            const modal = document.createElement('div');
            modal.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.9);
                z-index: 2000;
                display: flex;
                align-items: center;
                justify-content: center;
            `;
            
            const content = document.createElement('div');
            content.style.cssText = `
                background: #1a1a1a;
                border: 2px solid #00ff00;
                border-radius: 8px;
                padding: 20px;
                max-width: 80%;
                max-height: 80vh;
                overflow-y: auto;
                position: relative;
            `;
            
            content.innerHTML = `
                <button onclick="this.parentElement.parentElement.remove()" style="
                    position: absolute;
                    top: 10px;
                    right: 10px;
                    background: transparent;
                    border: 1px solid #00ff00;
                    color: #00ff00;
                    padding: 5px 10px;
                    cursor: pointer;
                ">×</button>
                <h2 style="color: #00ff00; margin-bottom: 20px;">${escapeHtml(entityName)}</h2>
                <div style="color: #888; margin-bottom: 15px;">Total Facts: ${data.fact_count}</div>
                <div style="max-height: 60vh; overflow-y: auto;">
                    ${data.facts.map((fact, idx) => `
                        <div style="margin-bottom: 15px; padding: 10px; background: #0a0a0a; border-left: 3px solid #00ffff;">
                            <div style="color: #ccc; margin-bottom: 5px;">${escapeHtml(fact.fact || fact.content || '')}</div>
                            <div style="font-size: 10px; color: #666;">
                                Source: ${escapeHtml(fact.source_file || 'Unknown')} 
                                ${fact.extraction_date ? `• ${new Date(fact.extraction_date).toLocaleDateString()}` : ''}
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;
            
            modal.appendChild(content);
            document.body.appendChild(modal);
            
            // Close on click outside
            modal.onclick = (e) => {
                if (e.target === modal) {
                    modal.remove();
                }
            };
        }
    } catch (error) {
        console.error('Failed to load entity facts:', error);
        alert('Failed to load entity facts: ' + error.message);
    }
}

async function handleProjectSwitch(projectId) {
    if (!projectId || projectId === currentProjectId) return;
    
    // Save current project state before switching
    await saveCurrentProjectState();
    
    try {
        const response = await fetch(`/api/projects/${projectId}/switch`, {
            method: 'POST'
        });
        
        if (response.ok) {
            currentProjectId = projectId;
            await loadActiveProject();
        } else {
            updateStatus('Failed to switch project');
        }
    } catch (error) {
        console.error('Failed to switch project:', error);
        updateStatus('Failed to switch project');
    }
}

async function saveCurrentProjectState() {
    // NO SQL GRAPH: persistence is handled by C-1 (Elasticsearch) via C1Integration auto-sync.
    return;
}

function showNewProjectDialog() {
    document.getElementById('projectModal').style.display = 'block';
    document.getElementById('newProjectName').value = '';
    document.getElementById('newProjectDescription').value = '';
    document.getElementById('newProjectName').focus();
}

function hideProjectModal() {
    document.getElementById('projectModal').style.display = 'none';
}

async function createNewProject(name, description) {
    const projectName = name || document.getElementById('newProjectName').value.trim();
    const projectDesc = description || document.getElementById('newProjectDescription').value.trim();
    
    if (!projectName) {
        alert('Please enter a project name');
        return;
    }
    
    // Save current project state before creating new one
    await saveCurrentProjectState();
    
    try {
        const response = await fetch(`${DRILL_SEARCH_BASE_URL}/api/projects`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: projectName,
                description: projectDesc
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            hideProjectModal();
            await loadProjects();
            updateStatus(`Created new project: ${projectName}`);
        } else {
            alert('Failed to create project: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Failed to create project:', error);
        alert('Failed to create project');
    }
}

async function deleteCurrentProject() {
    if (!currentProjectId) return;
    
    const projectSelect = document.getElementById('projectSelect');
    const projectName = projectSelect.options[projectSelect.selectedIndex].text;
    
    if (!confirm(`Are you sure you want to delete project "${projectName}"? This cannot be undone.`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/projects/${currentProjectId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            await loadProjects();
            updateStatus(`Deleted project: ${projectName}`);
        } else {
            alert('Failed to delete project');
        }
    } catch (error) {
        console.error('Failed to delete project:', error);
        alert('Failed to delete project');
    }
}

// Save graph state before unload (C-1 persistence is event-driven; this keeps local cache warm)
window.addEventListener('beforeunload', function() {
    try {
        saveGraphState();
    } catch (e) {
        // ignore
    }
});

// Store last AI message globally
let lastAIMessage = '';

// Override addChatMessage to capture AI responses
const originalAddChatMessage = addChatMessage;
addChatMessage = function(sender, message, isTyping) {
    if (sender === 'ai' && !isTyping) {
        lastAIMessage = message;
    }
    originalAddChatMessage(sender, message, isTyping);
};

// Extract entities from last AI message
window.extractEntitiesFromLastMessage = function() {
    if (!lastAIMessage) {
        alert('No AI message to extract from');
        return;
    }
    
    // Check for selected image node
    const selectedNodeIds = Array.from(selectedNodes);
    let imageNodeId = null;
    
    for (const nodeId of selectedNodeIds) {
        const node = nodes.get(nodeId);
        if (node && node.shape === 'image') {  // Check shape instead of data.type
            imageNodeId = nodeId;
            break;
        }
    }
    
    if (!imageNodeId) {
        alert('Please select an image node first');
        return;
    }
    
    console.log('Extracting from image node:', imageNodeId);
    console.log('Last AI message:', lastAIMessage);
    
    const createdNodes = new Map();
    let entityCount = 0;
    let connectionCount = 0;
    
    // More flexible entity extraction patterns
    const patterns = [
        // Companies/Organizations
        /(?:company|organization|corp|corporation|business|agency|firm)[::\s]+([^,\n]+)/gi,
        /([A-Z][A-Za-z\s&]+(?:Inc|LLC|Corp|Corporation|Ltd|Limited|Company|Group|Industries|Services|Solutions|Technologies|Agency|Department|Bureau|Foundation|Institute|Association)\.?)/g,
        
        // People names
        /(?:person|individual|name|contact)[::\s]+([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)/gi,
        /(?:Mr\.|Ms\.|Mrs\.|Dr\.|Prof\.)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)/g,
        
        // Emails
        /([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/g,
        
        // Phone numbers
        /(\+?1?[-.\s]?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4})/g,
        
        // Addresses
        /(\d+\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Plaza|Place|Pl)(?:\s+#?\d+)?)/gi
    ];
    
    const typeMap = {
        0: 'company', 1: 'company',
        2: 'name', 3: 'name',
        4: 'email',
        5: 'phone',
        6: 'address'
    };
    
    // Extract entities
    patterns.forEach((pattern, index) => {
        const matches = Array.from(lastAIMessage.matchAll(pattern));
        matches.forEach(match => {
            const value = match[1].trim();
            if (value && value.length > 2) {
                let nodeType = typeMap[index] || 'unknown';
                
                // Force company type for anything with company keywords
                if (/(?:Inc|LLC|Corp|Corporation|Ltd|Limited|Company|Group|Industries|Services|Solutions|Technologies|Agency|Department|Bureau|Foundation|Institute|Association)\.?/i.test(value)) {
                    nodeType = 'company';
                    console.log('Detected company:', value);
                } else if (nodeType === 'name') {
                    console.log('Detected person:', value);
                }
                
                const result = addNode({
                    value: value,
                    label: value,
                    source: 'AI Image Extract'
                }, nodeType, null, false, null, false);
                
                if (result && result.nodeId && !result.isExisting) {
                    createdNodes.set(value, result.nodeId);
                    entityCount++;
                    
                    // Create purple SOURCE edge
                    const edgeId = `edge_${imageNodeId}_${result.nodeId}_source`;
                    if (!edges.get(edgeId)) {
                        edges.add({
                            id: edgeId,
                            from: imageNodeId,
                            to: result.nodeId,
                            ...getConnectionStyle('SOURCE'),
                            label: 'SOURCE',
                            edgeType: 'image_source',
                            hidden: !showImageSources
                        });
                    }
                }
            }
        });
    });
    
    // Extract relationships
    const relPatterns = [
        /([^-,\n]+?)\s*(?:->|→|works?\s+(?:at|for)|employed\s+by|CEO\s+of|founder\s+of|director\s+of|manager\s+at)\s*([^,\n]+)/gi,
        /([^-,\n]+?)\s*(?:belongs?\s+to|owned\s+by|email\s+of|phone\s+of|contact\s+for)\s*([^,\n]+)/gi
    ];
    
    relPatterns.forEach(pattern => {
        const matches = Array.from(lastAIMessage.matchAll(pattern));
        matches.forEach(match => {
            const source = match[1].trim();
            const target = match[2].trim();
            const relationship = match[0].includes('work') || match[0].includes('employ') ? 'Employee' :
                               match[0].includes('CEO') ? 'CEO' :
                               match[0].includes('founder') ? 'Founder' :
                               match[0].includes('director') ? 'Director' :
                               match[0].includes('manager') ? 'Manager' :
                               match[0].includes('email') ? 'Email' :
                               match[0].includes('phone') ? 'Phone' :
                               match[0].includes('belong') || match[0].includes('owned') ? 'Owns' :
                               'Related';
            
            // Find nodes
            let sourceId = createdNodes.get(source);
            let targetId = createdNodes.get(target);
            
            if (!sourceId) {
                nodes.get().forEach(node => {
                    if (node.label === source || node.label.includes(source)) {
                        sourceId = node.id;
                    }
                });
            }
            
            if (!targetId) {
                nodes.get().forEach(node => {
                    if (node.label === target || node.label.includes(target)) {
                        targetId = node.id;
                    }
                });
            }
            
            if (sourceId && targetId && sourceId !== targetId) {
                const edgeId = `edge_${sourceId}_${targetId}_rel`;
                if (!edges.get(edgeId)) {
                    edges.add({
                        id: edgeId,
                        from: sourceId,
                        to: targetId,
                        label: relationship,
                        color: { color: '#00CED1' },
                        width: 2,
                        arrows: { to: { enabled: true, scaleFactor: 0.8 } },
                        font: { color: '#00CED1', size: 12 }
                    });
                    connectionCount++;
                }
            }
        });
    });
    
    saveGraphState();
    updateStatus(`Extracted ${entityCount} entities and ${connectionCount} connections`);
};

// Quick fix function to change all nodes containing company names to company type
window.fixCompanyNodes = function() {
    const companyKeywords = ['Inc', 'LLC', 'Corp', 'Corporation', 'Ltd', 'Company', 'Group', 'Industries', 'Services', 'Solutions', 'Technologies', 'Microsoft', 'Google', 'Apple', 'Amazon', 'FBI', 'CIA', 'NSA'];
    let fixed = 0;
    
    nodes.get().forEach(node => {
        if (node.type === 'name') {
            const label = node.label || '';
            const hasCompanyKeyword = companyKeywords.some(keyword => 
                label.toLowerCase().includes(keyword.toLowerCase())
            );
            
            if (hasCompanyKeyword) {
                changeNodeType(node.id, 'company');
                fixed++;
            }
        }
    });
    
    updateStatus(`Fixed ${fixed} company nodes`);
    return fixed;
};

// Temporary recovery function for legacy data
window.recoverLegacyData = async function() {
    if (!confirm('This will load the graph_state.json file from cache. Continue?')) return;
    
    try {
        const response = await fetch('/api/cache/load');
        const result = await response.json();
        
        if (result.data && result.data.graph_state) {
            console.log('Loading legacy data:', result.data.graph_state);
            
            // Clear current graph
            nodes.clear();
            edges.clear();
            
            // Load the state
            loadGraphState(result.data.graph_state);
            
            // Fit view
            setTimeout(() => {
                network.fit();
                updateStatus(`Recovered ${nodes.get().length} nodes from cache`);
            }, 500);
            
            // Save to current project
            if (currentProjectId) {
                await saveCurrentProjectState();
                updateStatus('Data saved to current project');
            }
        } else {
            alert('No cached data found');
        }
    } catch (error) {
        console.error('Recovery failed:', error);
        alert('Failed to recover data: ' + error.message);
    }
};



// Initialize server health monitoring
document.addEventListener('DOMContentLoaded', function() {
    // Check health every 30 seconds
    setInterval(checkServerHealth, 30000);
    checkServerHealth(); // Initial check
});

// File Upload Functions
window.uploadFile = function() {
    // Trigger the hidden file input
    document.getElementById('file-input').click();
};

// New unified file upload handler
window.handleFileUpload = async function(event) {
    console.log('🔧 FILE UPLOAD HANDLER - Unified for images and documents');
    const file = event.target.files[0];
    if (!file) return;
    
    const fileName = file.name.toLowerCase();
    const imageExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'];
    const isImage = imageExtensions.some(ext => fileName.endsWith(ext));
    const isMarkdown = fileName.endsWith('.md');
    
    if (isImage) {
        // Handle image upload
        await handleImageUpload(file);
    } else if (isMarkdown) {
        // Handle markdown upload
        await handleMdUpload(file);
    } else {
        alert('Unsupported file type. Please upload images (.jpg, .png, etc.) or markdown files (.md)');
        event.target.value = ''; // Reset input
        return;
    }
    
    // Reset the file input
    event.target.value = '';
};

// Handle image file upload
async function handleImageUpload(file) {
    try {
        updateStatus(`📷 Uploading image: ${file.name}...`);
        
        // Read the file as data URL
        const reader = new FileReader();
        reader.onload = async function(e) {
            const imageData = e.target.result;
            
            // Create image node
            const imageNodeData = {
                value: file.name,
                label: `🖼️ ${file.name}`,
                source: 'Image Upload',
                uploadedAt: new Date().toISOString(),
                fileSize: file.size,
                imageData: imageData
            };
            
            const imageNode = await addNode(imageNodeData, 'image');
            if (!imageNode || !imageNode.nodeId) {
                throw new Error('Failed to create image node');
            }
            
            // Position the image node in the center
            const centerPos = network.getViewPosition();
            network.moveNode(imageNode.nodeId, centerPos.x, centerPos.y);
            
            // Update the node to be an actual image node
            nodes.update({
                id: imageNode.nodeId,
                shape: 'image',
                image: imageData,
                size: 50
            });
            
            updateStatus(`✅ Image uploaded: ${file.name}`);
            saveGraphState();
        };
        
        reader.onerror = function() {
            throw new Error('Failed to read image file');
        };
        
        reader.readAsDataURL(file);
        
    } catch (error) {
        console.error('Image upload error:', error);
        updateStatus(`❌ Failed to upload image: ${error.message}`);
    }
}

// Handle markdown file upload (reuse existing logic)
async function handleMdUpload(file) {
    return handleMdFileUpload({ target: { files: [file] } });
}

window.handleMdFileUpload = async function(event) {
    console.log('🔧 MD FILE HANDLER VERSION 2.1 - totalEntities FIXED');
    const file = event.target.files[0];
    if (!file) return;
    
    // Validate file type
    if (!file.name.toLowerCase().endsWith('.md')) {
        alert('Please select a .md (Markdown) file');
        event.target.value = ''; // Reset input
        return;
    }
    
    // File size info (no limit anymore - we chunk on server)
    console.log(`File size: ${(file.size / 1024 / 1024).toFixed(2)} MB`);
    
    try {
        updateStatus(`📄 Uploading ${file.name}...`);
        
        // Create form data
        const formData = new FormData();
        formData.append('file', file);
        
        // First create a document node for the file
        const fileNodeData = {
            value: file.name,
            label: `📄 ${file.name}`,
            source: 'MD File Upload',
            uploadedAt: new Date().toISOString(),
            fileSize: file.size,
            isProcessing: true
        };
        
        const fileNode = await addNode(fileNodeData, 'document');
        if (!fileNode || !fileNode.nodeId) {
            throw new Error('Failed to create document node');
        }
        
        // Position the document node in the center
        const centerPos = network.getViewPosition();
        network.moveNode(fileNode.nodeId, centerPos.x, centerPos.y);
        
        updateStatus(`🤖 Extracting entities from ${file.name}...`);
        
        // Call the backend API
        const response = await fetch('/api/file/extract-entities', {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Entity extraction failed');
        }
        
        const result = await response.json();
        
        if (result.success) {
            const entities = result.entities || [];
            const relationships = result.relationships || [];
            const createdNodes = new Map();
            
            updateStatus(`Creating ${entities.length} entities and ${relationships.length} relationships...`);
            
            console.log(`🐞 DEBUG MD: entities.length = ${entities.length}, typeof entities = ${typeof entities}`);
            
            // Update document node to remove processing flag
            nodes.update({
                id: fileNode.nodeId,
                data: {
                    ...nodes.get(fileNode.nodeId).data,
                    isProcessing: false,
                    entityCount: entities.length,
                    relationshipCount: relationships.length
                }
            });
            
            // Get document node position for arranging entities
            const docPos = network.getPositions([fileNode.nodeId])[fileNode.nodeId];
            const centerX = docPos ? docPos.x : 0;
            const centerY = docPos ? docPos.y : 0;
            
            // SIMPLE GRID POSITIONING - NO OVERLAP GUARANTEED
            const gridSize = Math.ceil(Math.sqrt(entities.length)); // Square grid
            const spacing = currentNodeSpacing; // Use current spacing setting
            let currentRow = 0;
            let currentCol = 0;
            
            console.log(`🎯 POSITIONING ${entities.length} entities in ${gridSize}x${gridSize} grid with ${spacing}px spacing`);
            
            // Create nodes for all entities
            for (let i = 0; i < entities.length; i++) {
                const entity = entities[i];
                
                // Calculate grid position
                const row = Math.floor(i / gridSize);
                const col = i % gridSize;
                
                // Calculate actual coordinates
                const x = centerX + (col - gridSize/2) * spacing;
                const y = centerY + (row - gridSize/2) * spacing;
                
                console.log(`🔹 Entity ${i}: "${entity.value}" -> Grid(${row},${col}) -> Position(${x.toFixed(0)}, ${y.toFixed(0)})`);
                
                // Create the entity node
                const nodeResult = await addNode({
                    value: entity.value,
                    label: entity.value,
                    source: 'MD File Extract',
                    notes: entity.notes || '',
                    confidence: entity.confidence || 'medium',
                    extractedFrom: file.name
                }, entity.type);
                
                if (nodeResult && nodeResult.nodeId) {
                    createdNodes.set(entity.value, nodeResult.nodeId);
                    
                    console.log(`✅ Created node ${nodeResult.nodeId} for "${entity.value}" at (${x}, ${y})`);
                    
                    // FORCE POSITION IMMEDIATELY
                    nodes.update({
                        id: nodeResult.nodeId,
                        x: x,
                        y: y,
                        fixed: { x: true, y: true }, // Lock position
                        physics: false
                    });
                    
                    // BACKUP: Force position with network API
                    network.moveNode(nodeResult.nodeId, x, y);
                    
                    // Update node with additional data
                    const node = nodes.get(nodeResult.nodeId);
                    if (node) {
                        nodes.update({
                            id: nodeResult.nodeId,
                            title: `${entity.type.toUpperCase()}: ${entity.value}\n${entity.notes || ''}\nConfidence: ${entity.confidence}`,
                            data: {
                                ...node.data,
                                notes: entity.notes,
                                confidence: entity.confidence,
                                extractedFromFile: file.name
                            }
                        });
                    }
                    
                    // Create green SOURCE edge from document to entity
                    const edgeId = `edge_${fileNode.nodeId}_${nodeResult.nodeId}_file_source`;
                    if (!edges.get(edgeId)) {
                        edges.add({
                            id: edgeId,
                            from: fileNode.nodeId,
                            to: nodeResult.nodeId,
                            ...getConnectionStyle('SOURCE'),
                            label: 'EXTRACTED',
                            title: 'Extracted from MD file',
                            edgeType: 'file_source',
                            smooth: {
                                type: 'curvedCW',
                                roundness: 0.2
                            }
                        });
                    }
                }
            }
            
            // Create relationships between entities after a delay
            setTimeout(() => {
                for (const rel of relationships) {
                    // Find node IDs
                    let sourceId = createdNodes.get(rel.source);
                    let targetId = createdNodes.get(rel.target);
                    
                    // Try to find in existing nodes if not in created nodes
                    if (!sourceId) {
                        const sourceNodes = nodes.get({
                            filter: n => n.label && n.label === rel.source
                        });
                        if (sourceNodes.length > 0) {
                            sourceId = sourceNodes[0].id;
                        }
                    }
                    
                    if (!targetId) {
                        const targetNodes = nodes.get({
                            filter: n => n.label && n.label === rel.target
                        });
                        if (targetNodes.length > 0) {
                            targetId = targetNodes[0].id;
                        }
                    }
                    
                    // Create edge if both nodes exist
                    if (sourceId && targetId && sourceId !== targetId) {
                        const relEdgeId = `edge_${sourceId}_${targetId}_relationship`;
                        if (!edges.get(relEdgeId)) {
                            edges.add({
                                id: relEdgeId,
                                from: sourceId,
                                to: targetId,
                                label: rel.relationship,
                                title: `${rel.relationship}\nConfidence: ${rel.confidence}\n${rel.notes || ''}`,
                                color: { color: '#00FFFF' },
                                width: 2,
                                dashes: false,
                                arrows: {
                                    to: { enabled: true, scaleFactor: 0.8 }
                                },
                                smooth: {
                                    type: 'curvedCW',
                                    roundness: 0.2
                                }
                            });
                        }
                    }
                }
                
                updateStatus(`✅ Extracted ${entities.length} entities and ${relationships.length} relationships from ${file.name}`);
                
                // Save graph state
                saveGraphState();
                
                // Focus on the document node
                setTimeout(() => {
                    network.focus(fileNode.nodeId, {
                        scale: 0.8,
                        animation: {
                            duration: 1000,
                            easingFunction: 'easeInOutQuad'
                        }
                    });
                }, 1000);
            }, 1000); // Fixed delay
        }
        
    } catch (error) {
        console.error('MD file upload error:', error);
        updateStatus(`❌ Error: ${error.message}`);
        alert(`Failed to process MD file: ${error.message}`);
    } finally {
        // Reset the file input
        event.target.value = '';
    }
};

// Delete selected nodes from the node list
window.deleteSelectedNodesFromList = function() {
    // Get all selected checkboxes
    const selectedCheckboxes = document.querySelectorAll('.node-select-checkbox:checked');
    const selectedNodeIds = Array.from(selectedCheckboxes).map(cb => cb.getAttribute('data-node-id'));
    
    if (selectedNodeIds.length === 0) {
        alert('No nodes selected for deletion');
        return;
    }
    
    // Confirm deletion
    const message = `Are you sure you want to delete ${selectedNodeIds.length} selected node(s)? This cannot be undone.`;
    if (!confirm(message)) {
        return;
    }
    
    // Save undo state before deletion
    saveUndoState(`Delete ${selectedNodeIds.length} nodes from sidebar`);
    
    // Delete the nodes
    try {
        nodes.remove(selectedNodeIds);
        
        // Update status
        updateStatus(`Deleted ${selectedNodeIds.length} nodes`);
        
        // Save graph state
        saveGraphState();
        
        // Update the node list display
        updateNodeList();
        
        console.log(`Deleted ${selectedNodeIds.length} nodes:`, selectedNodeIds);
    } catch (error) {
        console.error('Error deleting nodes:', error);
        alert('Error deleting nodes: ' + error.message);
    }
};

// Toggle select all nodes in the list
window.toggleSelectAllNodes = function(selectAll) {
    const checkboxes = document.querySelectorAll('.node-select-checkbox');
    checkboxes.forEach(checkbox => {
        checkbox.checked = selectAll;
    });
};

// Global spacing variable
let currentNodeSpacing = 400;

// Adjust spacing between all nodes
window.adjustNodeSpacing = function(newSpacing) {
    currentNodeSpacing = parseInt(newSpacing);
    
    // Update the display value
    document.getElementById('spacing-value').textContent = currentNodeSpacing;
    
    console.log(`🎚️ Adjusting node spacing to ${currentNodeSpacing}px`);
    
    // Get all nodes that were created from MD files (have extractedFromFile property)
    const allNodes = nodes.get();
    const mdFileNodes = allNodes.filter(node => 
        node.data && node.data.extractedFromFile && node.type !== 'document'
    );
    
    if (mdFileNodes.length === 0) {
        console.log('No MD file nodes found to reposition');
        return;
    }
    
    // Find the document node (center point)
    const documentNode = allNodes.find(node => node.type === 'document');
    let centerX = 0, centerY = 0;
    
    if (documentNode) {
        const docPos = network.getPositions([documentNode.id])[documentNode.id];
        centerX = docPos ? docPos.x : 0;
        centerY = docPos ? docPos.y : 0;
    }
    
    // Recalculate positions with new spacing
    const gridSize = Math.ceil(Math.sqrt(mdFileNodes.length));
    const updates = [];
    
    for (let i = 0; i < mdFileNodes.length; i++) {
        const node = mdFileNodes[i];
        
        // Calculate new grid position
        const row = Math.floor(i / gridSize);
        const col = i % gridSize;
        
        // Calculate new coordinates with new spacing
        const x = centerX + (col - gridSize/2) * currentNodeSpacing;
        const y = centerY + (row - gridSize/2) * currentNodeSpacing;
        
        updates.push({
            id: node.id,
            x: x,
            y: y,
            fixed: { x: true, y: true },
            physics: false
        });
        
        // Also move with network API
        network.moveNode(node.id, x, y);
    }
    
    // Apply all updates at once
    if (updates.length > 0) {
        nodes.update(updates);
        console.log(`✅ Repositioned ${updates.length} nodes with ${currentNodeSpacing}px spacing`);
        
        // Save the new positions
        saveGraphState();
    }
};
