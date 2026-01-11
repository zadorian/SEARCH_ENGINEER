// EMERGENCY RESTORE SCRIPT
// Copy and paste this entire script into your browser console

async function emergencyRestoreBoyfriend() {
  console.log("🚨 EMERGENCY RESTORE STARTING...");

  try {
    // Load cache data
    const cacheResponse = await fetch("/api/cache/load");
    const cacheData = await cacheResponse.json();

    if (!cacheData.data || !cacheData.data.graph_state) {
      console.error("❌ No cache data found!");
      return;
    }

    const graphState = cacheData.data.graph_state;
    console.log(
      `✅ Found cached data: ${graphState.nodes.length} nodes, ${graphState.edges.length} edges`
    );

    // Clear current graph
    nodes.clear();
    edges.clear();

    // Load nodes
    if (graphState.nodes && graphState.nodes.length > 0) {
      nodes.add(graphState.nodes);
      console.log(`✅ Loaded ${graphState.nodes.length} nodes`);
    }

    // Load edges
    if (graphState.edges && graphState.edges.length > 0) {
      edges.add(graphState.edges);
      console.log(`✅ Loaded ${graphState.edges.length} edges`);
    }

    // Restore other data
    if (graphState.nodeIdCounter) nodeIdCounter = graphState.nodeIdCounter;
    if (graphState.anchoredNodes) {
      anchoredNodes = new Set(graphState.anchoredNodes);
      console.log(`✅ Restored ${anchoredNodes.size} anchored nodes`);
    }
    if (graphState.nodeSearchQueries) {
      nodeSearchQueries = new Map(graphState.nodeSearchQueries);
    }
    if (graphState.valueToNodeMap) {
      valueToNodeMap = new Map(graphState.valueToNodeMap);
    }

    // Fit the view
    network.fit();

    // Save to current project
    await saveGraphState();
    await saveCurrentProjectState();

    updateStatus(
      `🎉 RESTORED ${graphState.nodes.length} nodes and ${graphState.edges.length} edges!`
    );
    console.log("✅ EMERGENCY RESTORE COMPLETE!");
  } catch (error) {
    console.error("❌ Emergency restore failed:", error);
    updateStatus("❌ Emergency restore failed - check console");
  }
}

// Run it immediately
emergencyRestoreBoyfriend();
