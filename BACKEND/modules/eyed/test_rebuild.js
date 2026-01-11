// Test script to manually verify and fix the connection rebuilding

function testRebuildConnections() {
  console.log("=== TESTING CONNECTION REBUILD ===");

  // 1. Check current state
  const allNodes = nodes.get();
  const allEdges = edges.get();
  console.log(
    `Current state: ${allNodes.length} nodes, ${allEdges.length} edges`
  );

  // 2. Clear edges and rebuild
  console.log("\nClearing all edges...");
  edges.clear();
  console.log(`After clear: ${edges.get().length} edges`);

  // 3. Group nodes by breach
  const nodesByBreach = new Map();
  allNodes.forEach(node => {
    if (node.data && node.data.breach) {
      const breach = node.data.breach;
      if (!nodesByBreach.has(breach)) {
        nodesByBreach.set(breach, []);
      }
      nodesByBreach.get(breach).push(node);
    }
  });

  console.log(`\nFound ${nodesByBreach.size} unique breaches`);

  // 4. Show first 3 breaches
  let count = 0;
  nodesByBreach.forEach((nodeList, breachName) => {
    if (count < 3) {
      console.log(`\nBreach "${breachName}": ${nodeList.length} nodes`);
      nodeList.forEach(node => {
        console.log(`  - ${node.type}: ${node.label} (ID: ${node.id})`);
      });
      count++;
    }
  });

  // 5. Test connecting one breach manually
  const testBreach = Array.from(nodesByBreach.entries())[0];
  if (testBreach) {
    const [breachName, nodeList] = testBreach;
    console.log(
      `\nTest connecting breach "${breachName}" with ${nodeList.length} nodes...`
    );

    // Method 1: Using connectBreachNodes (if it exists)
    if (typeof connectBreachNodes === "function") {
      const nodeIds = nodeList.map(n => n.id);
      console.log("Node IDs:", nodeIds);

      // Add edges manually to test
      for (let i = 0; i < nodeIds.length - 1; i++) {
        for (let j = i + 1; j < nodeIds.length; j++) {
          try {
            edges.add({
              id: `test_${nodeIds[i]}_${nodeIds[j]}`,
              from: nodeIds[i],
              to: nodeIds[j],
              color: { color: "#FF0000" },
              width: 3,
              title: `TEST: Same breach - ${breachName}`,
            });
            console.log(`Added edge: ${nodeIds[i]} -> ${nodeIds[j]}`);
          } catch (e) {
            console.error(`Failed to add edge: ${e.message}`);
          }
        }
      }

      console.log(`Edges after test: ${edges.get().length}`);
    }
  }

  // 6. Now try the full rebuild
  console.log("\n\nRunning full rebuildAllConnections()...");
  if (typeof rebuildAllConnections === "function") {
    rebuildAllConnections();
    console.log(`Final edge count: ${edges.get().length}`);
  } else {
    console.error("rebuildAllConnections function not found!");
  }

  return {
    nodes: allNodes.length,
    breaches: nodesByBreach.size,
    edges: edges.get().length,
  };
}

// Quick fix function
function quickFixConnections() {
  console.log("=== QUICK FIX CONNECTIONS ===");

  // Clear and rebuild using the simpler approach
  edges.clear();

  const allNodes = nodes.get();
  const nodesByBreach = new Map();

  // Group by breach
  allNodes.forEach(node => {
    if (node.data && node.data.breach) {
      const breach = node.data.breach;
      if (!nodesByBreach.has(breach)) {
        nodesByBreach.set(breach, []);
      }
      nodesByBreach.get(breach).push(node.id); // Store just the ID
    }
  });

  // Connect using the original connectBreachNodes function
  let totalEdges = 0;
  nodesByBreach.forEach((nodeIds, breachName) => {
    if (nodeIds.length >= 2) {
      console.log(
        `Connecting ${nodeIds.length} nodes from breach: ${breachName}`
      );

      // Simple star pattern connection
      for (let i = 0; i < nodeIds.length - 1; i++) {
        for (let j = i + 1; j < nodeIds.length; j++) {
          edges.add({
            from: nodeIds[i],
            to: nodeIds[j],
            color: { color: "#00FF00" },
            width: 2,
            title: `Same breach: ${breachName}`,
          });
          totalEdges++;
        }
      }
    }
  });

  console.log(`Created ${totalEdges} connections`);
  saveGraphState();
  network.redraw();
  updateStatus(
    `Rebuilt ${totalEdges} connections for ${nodesByBreach.size} breaches`
  );

  return totalEdges;
}

console.log(
  "Run testRebuildConnections() to test or quickFixConnections() for a quick fix"
);
