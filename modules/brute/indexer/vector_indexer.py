"""
Stub Vector indexer when full module is not available.
"""

class Vectorindexer:
    """Minimal stub when full indexer is not available"""
    def __init__(self, *args, **kwargs):
        self.vectors = {}

    def index(self, doc_id, text, embedding=None):
        self.vectors[doc_id] = {"text": text, "embedding": embedding}

    def search(self, query, limit=10):
        return []

    def delete(self, doc_id):
        if doc_id in self.vectors:
            del self.vectors[doc_id]

    def get_embedding(self, text):
        return None

__all__ = ["Vectorindexer"]
