"""
Stub Whoosh indexer when full module is not available.
"""

class Whooshindexer:
    """Minimal stub when full indexer is not available"""
    def __init__(self, *args, **kwargs):
        self.documents = []

    def index(self, doc):
        self.documents.append(doc)

    def search(self, query, limit=10):
        return []

    def delete(self, doc_id):
        pass

    def commit(self):
        pass

    def optimize(self):
        pass

__all__ = ["Whooshindexer"]
