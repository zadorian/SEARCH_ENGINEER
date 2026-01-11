"""
Wrapper for cymonides storage bridge so brute imports resolve.
"""
try:
    from cymonides.indexer.storage_bridge import StorageBridge  # type: ignore
except ImportError:
    class StorageBridge:
        """Minimal stub when cymonides is not available"""
        def __init__(self, *args, **kwargs):
            self.data = {}

        def store(self, key, value):
            self.data[key] = value

        def retrieve(self, key):
            return self.data.get(key)

        def delete(self, key):
            if key in self.data:
                del self.data[key]

        def list_keys(self):
            return list(self.data.keys())

__all__ = ["StorageBridge"]
