"""
Wrapper to import scraper from the central scraper directory.
"""
import sys
from pathlib import Path

# Add the parent BACKEND directory to path for direct imports
backend_dir = Path(__file__).resolve().parent.parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

try:
    from scraper.scraper import scraper
except ImportError:
    # Provide a stub scraper function
    async def scraper(url: str, *args, **kwargs):
        """Stub scraper when real scraper is not available."""
        return {"url": url, "content": "", "error": "Scraper not available"}

__all__ = ["scraper"]
