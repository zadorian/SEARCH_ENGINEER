"""
Wrapper for cymonides entity graph storage so brute imports resolve.
"""
try:
    from cymonides.indexer.entity_graph_storage import EntityGraphStorage  # type: ignore
except ImportError:
    # Fallback stub when cymonides is not available
    class EntityGraphStorage:
        """Minimal stub when cymonides is not available"""
        def __init__(self, *args, **kwargs):
            self.entities = {}
            self.edges = []

        def add_entity(self, entity_id, entity_type, data=None):
            self.entities[entity_id] = {"type": entity_type, "data": data or {}}

        def add_edge(self, source_id, target_id, edge_type, data=None):
            self.edges.append({
                "source": source_id,
                "target": target_id,
                "type": edge_type,
                "data": data or {}
            })

        def get_entity(self, entity_id):
            return self.entities.get(entity_id)

        def get_edges(self, entity_id=None):
            if entity_id:
                return [e for e in self.edges if e["source"] == entity_id or e["target"] == entity_id]
            return self.edges

        def save(self):
            pass

        def load(self):
            pass

__all__ = ["EntityGraphStorage"]
