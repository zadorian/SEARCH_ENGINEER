"""
Wrapper for cymonides query node storage v2 so brute imports resolve.
"""
try:
    from cymonides.indexer.query_node_storage_v2 import QueryNodeStorageV2  # type: ignore
except ImportError:
    class QueryNodeStorageV2:
        """Minimal stub when cymonides is not available"""
        def __init__(self, *args, **kwargs):
            self.nodes = {}
            self.edges = []

        def store_node(self, node_id, data):
            self.nodes[node_id] = data

        def get_node(self, node_id):
            return self.nodes.get(node_id)

        def add_edge(self, source, target, edge_type):
            self.edges.append({"source": source, "target": target, "type": edge_type})

        def get_edges(self, node_id=None):
            if node_id:
                return [e for e in self.edges if e["source"] == node_id or e["target"] == node_id]
            return self.edges

        def delete_node(self, node_id):
            if node_id in self.nodes:
                del self.nodes[node_id]

__all__ = ["QueryNodeStorageV2"]
