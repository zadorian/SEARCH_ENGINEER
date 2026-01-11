// SIMPLE FIX - Just rebuild the fucking connections
function fixConnections() {
  console.log("Fixing connections...");

  // Get all nodes
  const allNodes = nodes.get();
  console.log("Found", allNodes.length, "nodes");

  // Group by breach
  const breaches = {};
  allNodes.forEach(node => {
    if (node.data && node.data.breach) {
      if (!breaches[node.data.breach]) {
        breaches[node.data.breach] = [];
      }
      breaches[node.data.breach].push(node.id);
    }
  });

  // Add edges for each breach
  let edgeCount = 0;
  Object.keys(breaches).forEach(breach => {
    const nodeIds = breaches[breach];
    console.log("Breach", breach, "has", nodeIds.length, "nodes");

    if (nodeIds.length >= 2) {
      // Connect first node to all others
      for (let i = 1; i < nodeIds.length; i++) {
        edges.add({
          from: nodeIds[0],
          to: nodeIds[i],
          color: { color: "#666666" },
          width: 1,
          title: "Same breach: " + breach,
        });
        edgeCount++;
      }
    }
  });

  console.log("Added", edgeCount, "edges");
  return edgeCount;
}

// Run it
fixConnections();
