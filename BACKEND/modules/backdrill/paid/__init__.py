"""
Paid API wrappers for BACKDRILL.

Optional paid sources with caching:
- Firecrawl: maxAge (30 days cache = 2592000000ms)
- Exa: start_published_date, end_published_date

SOURCE FILES:
- firecrawl.py ← JESTER/MAPPER/config.py FIRECRAWL_MAX_AGE_MS setting
- exa.py ← New implementation based on Exa API docs
"""

from .firecrawl import FirecrawlCache
from .exa import ExaHistorical

__all__ = ["FirecrawlCache", "ExaHistorical"]
