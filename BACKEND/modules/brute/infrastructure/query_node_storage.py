"""
Wrapper for cymonides query node storage so brute imports resolve.
"""
try:
    from cymonides.indexer.query_node_storage import QueryNodeStorage  # type: ignore
except ImportError:
    class QueryNodeStorage:
        """Minimal stub when cymonides is not available"""
        def __init__(self, *args, **kwargs):
            self.nodes = {}

        def store_node(self, node_id, data):
            self.nodes[node_id] = data

        def get_node(self, node_id):
            return self.nodes.get(node_id)

        def delete_node(self, node_id):
            if node_id in self.nodes:
                del self.nodes[node_id]

        def list_nodes(self):
            return list(self.nodes.keys())

__all__ = ["QueryNodeStorage"]
