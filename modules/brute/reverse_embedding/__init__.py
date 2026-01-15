"""
Reverse Embedding Module

Captures and stores related queries, suggested searches, and "People Also Ask"
from search engine results for query expansion and reverse engineering search intent.

Sources:
- Apify Google Search: relatedQueries, peopleAlsoAsk
- Google SERP: relatedSearches
- Bing: relatedSearches
- BrightData SERP: related_queries
"""

from .storage import ReverseEmbeddingStorage
from .collector import RelatedQueryCollector

__all__ = ['ReverseEmbeddingStorage', 'RelatedQueryCollector']
