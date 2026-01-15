"""
Wrapper for cymonides whoosh indexer so brute imports resolve.
"""
try:
    from cymonides.indexer.whoosh_indexer import Whooshindexer  # type: ignore
except ImportError:
    class Whooshindexer:
        """Minimal stub when cymonides is not available"""
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

__all__ = ["Whooshindexer"]
