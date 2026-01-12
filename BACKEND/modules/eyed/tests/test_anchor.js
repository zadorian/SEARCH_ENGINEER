// Test script to check what's happening with anchored nodes
console.log("=== ANCHOR TEST ===");

// Check all anchored nodes
if (typeof anchoredNodes !== "undefined" && anchoredNodes.size > 0) {
  console.log(`Found ${anchoredNodes.size} anchored nodes`);

  anchoredNodes.forEach(nodeId => {
    const node = nodes.get(nodeId);
    if (node) {
      console.log(`Node ${nodeId}:`, {
        borderWidth: node.borderWidth,
        borderWidthSelected: node.borderWidthSelected,
        size: node.size,
        color: node.color,
      });
    }
  });
} else {
  console.log("No anchored nodes found");
}

// Check network default options
if (typeof network !== "undefined") {
  console.log("Network options:", network.options.nodes);
}
