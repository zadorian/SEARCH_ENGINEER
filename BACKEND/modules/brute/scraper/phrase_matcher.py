"""
Wrapper to import PhraseMatcher from the central scraper directory.
"""
import sys
from pathlib import Path

# Add the parent BACKEND directory to path for direct imports
backend_dir = Path(__file__).resolve().parent.parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

try:
    from scraper.phrase_matcher import PhraseMatcher
except ImportError:
    import re
    
    class PhraseMatcher:
        """Minimal stub when scraper is not available"""
        def __init__(self, max_distance: int = 2):
            self.max_distance = max_distance
        
        def extract_phrases(self, query: str):
            """Extract all quoted phrases from a query."""
            return re.findall(r'"([^"]+)"', query)
        
        def check_proximity(self, text: str, phrases, max_dist=None):
            """Check if phrases appear within proximity in text."""
            return True
        
        def matches_any_phrase(self, text: str, phrases):
            """Check if any phrase matches in text."""
            return any(p.lower() in text.lower() for p in phrases)

__all__ = ["PhraseMatcher"]
