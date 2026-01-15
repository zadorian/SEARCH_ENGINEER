"""
Wrapper to reuse scraper modules from the central scraper directory.
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
    # Fallback stub
    class PhraseMatcher:
        """Minimal stub when scraper is not available"""
        def __init__(self, *args, **kwargs):
            self.max_distance = kwargs.get('max_distance', 2)
        def extract_phrases(self, query):
            import re
            return re.findall(r'"([^"]+)"', query)
        def check_proximity(self, text, phrases, max_dist=None):
            return True
        def matches_any_phrase(self, text, phrases):
            return any(p.lower() in text.lower() for p in phrases)

try:
    from scraper.scraper import scraper
except ImportError:
    scraper = None

__all__ = ["PhraseMatcher", "scraper"]
