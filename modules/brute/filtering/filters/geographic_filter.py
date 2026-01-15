"""Geographic filter stub - location-based filtering"""

class GeographicFilter:
    """Filter results by geographic location"""
    
    def __init__(self, allowed_regions=None, blocked_regions=None):
        self.allowed_regions = allowed_regions or []
        self.blocked_regions = blocked_regions or []
    
    def filter(self, results):
        """Filter results - stub returns all results"""
        return results
    
    def should_keep(self, result):
        """Check if result should be kept - stub always returns True"""
        return True

__all__ = ['GeographicFilter']
