"""LINKLATER API stub."""

class LinkAnalyzer:
    """Stub for link analysis."""
    def __init__(self):
        self.available = False
    
    async def get_backlinks(self, domain):
        return []
    
    async def get_outlinks(self, domain):
        return []
    
    async def analyze(self, url, **kwargs):
        return {"status": "not_available"}

_link_analyzer = LinkAnalyzer()

def get_linklater():
    """Return the singleton LinkAnalyzer instance."""
    return _link_analyzer

# For direct import
link_analyzer = _link_analyzer
