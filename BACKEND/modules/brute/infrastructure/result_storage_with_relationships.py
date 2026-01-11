"""
Wrapper to reuse cymonides indexer ResultStorage when brute expects its own infra module.
"""
try:
    from cymonides.indexer.result_storage import ResultStorage  # type: ignore
except ImportError:
    # Fallback: create a minimal stub
    class ResultStorage:
        """Minimal stub when cymonides is not available"""
        def __init__(self, *args, **kwargs):
            pass
        def save(self, *args, **kwargs):
            pass
        def get(self, *args, **kwargs):
            return None

__all__ = ["ResultStorage"]
