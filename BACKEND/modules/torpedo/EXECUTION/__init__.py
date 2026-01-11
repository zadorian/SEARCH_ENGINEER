"""
TORPEDO EXECUTION - Search Execution Against Classified Sources

Uses classification results from PROCESSING to search sources with optimal method.

Scripts:
    - base_searcher.py: Abstract base for source-type searchers
    - cr_searcher.py: Corporate Registry searcher
    - news_searcher.py: News searcher

Usage:
    from TORPEDO.EXECUTION import CRSearcher, NewsSearcher

    searcher = NewsSearcher()
    results = await searcher.search("London", jurisdiction="UK")
"""

from .base_searcher import BaseSearcher
from .cr_searcher import CRSearcher
from .news_searcher import NewsSearcher
