// Diagnostic script to check why connections aren't being rebuilt

function diagnoseConnections() {
  console.log("=== CONNECTION DIAGNOSIS ===");

  // 1. Check nodes
  const allNodes = nodes.get();
  console.log(`Total nodes: ${allNodes.length}`);

  // 2. Check edges before rebuild
  console.log(`Edges before rebuild: ${edges.length}`);

  // 3. Group nodes by breach to see what we're working with
  const nodesByBreach = new Map();
  let nodesWithBreach = 0;
  let nodesWithoutBreach = 0;

  allNodes.forEach(node => {
    if (node.data && node.data.breach) {
      nodesWithBreach++;
      const breach = node.data.breach;
      if (!nodesByBreach.has(breach)) {
        nodesByBreach.set(breach, []);
      }
      nodesByBreach.get(breach).push(node.id);
    } else {
      nodesWithoutBreach++;
      console.log("Node without breach data:", node);
    }
  });

  console.log(`Nodes with breach data: ${nodesWithBreach}`);
  console.log(`Nodes without breach data: ${nodesWithoutBreach}`);
  console.log(`Unique breaches: ${nodesByBreach.size}`);

  // 4. Show sample breaches
  let sampleCount = 0;
  nodesByBreach.forEach((nodeIds, breachName) => {
    if (sampleCount < 5) {
      console.log(
        `Breach "${breachName}" has ${nodeIds.length} nodes:`,
        nodeIds
      );
      sampleCount++;
    }
  });

  // 5. Try connecting one breach manually
  const firstBreach = Array.from(nodesByBreach.entries())[0];
  if (firstBreach) {
    const [breachName, nodeIds] = firstBreach;
    console.log(
      `\nTrying to connect breach "${breachName}" with ${nodeIds.length} nodes...`
    );

    // Check if connectBreachNodes exists
    if (typeof connectBreachNodes === "function") {
      console.log("connectBreachNodes function exists");
      connectBreachNodes(nodeIds, breachName);
      console.log(`Edges after connecting one breach: ${edges.length}`);
    } else {
      console.error("connectBreachNodes function not found!");
    }
  }

  // 6. Check vis.js edges DataSet
  console.log("\nChecking edges DataSet:");
  console.log("edges object:", edges);
  console.log("Is DataSet?", edges instanceof vis.DataSet);

  // 7. Try adding a test edge
  console.log("\nTrying to add a test edge...");
  const testNodes = allNodes.slice(0, 2);
  if (testNodes.length >= 2) {
    try {
      const testEdgeId = "test_edge_" + Date.now();
      edges.add({
        id: testEdgeId,
        from: testNodes[0].id,
        to: testNodes[1].id,
        color: { color: "#FF0000" },
        width: 5,
        title: "TEST EDGE",
      });
      console.log("Test edge added successfully");
      console.log(`Edges after test: ${edges.length}`);

      // Remove test edge
      edges.remove(testEdgeId);
      console.log("Test edge removed");
    } catch (e) {
      console.error("Error adding test edge:", e);
    }
  }

  return {
    totalNodes: allNodes.length,
    nodesWithBreach: nodesWithBreach,
    nodesWithoutBreach: nodesWithoutBreach,
    uniqueBreaches: nodesByBreach.size,
    currentEdges: edges.length,
  };
}

// Run diagnosis
console.log("Run diagnoseConnections() to check the issue");
