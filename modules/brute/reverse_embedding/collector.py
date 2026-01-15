"""
Related Query Collector

Extracts related queries, suggestions, and PAA from various search engine responses.
"""

import logging
from typing import List, Dict, Any, Optional
from .storage import ReverseEmbeddingStorage

logger = logging.getLogger(__name__)


class RelatedQueryCollector:
    """
    Collects and stores related queries from multiple search engines.
    
    Supported formats:
    - Apify Google Search: relatedQueries, peopleAlsoAsk
    - Google SERP API: relatedSearches
    - BrightData SERP: related_queries
    - Bing: relatedSearches
    - SerpAPI: related_searches, people_also_ask
    """
    
    def __init__(self, storage: Optional[ReverseEmbeddingStorage] = None):
        self.storage = storage or ReverseEmbeddingStorage()
    
    def collect_from_apify(self, query: str, response: Dict[str, Any]) -> Dict[str, int]:
        """
        Extract related data from Apify Google Search response.
        
        Apify returns:
        - relatedQueries: [{title: str}]
        - peopleAlsoAsk: [{question: str, answer: str, url: str}]
        """
        stats = {'related': 0, 'paa': 0}
        
        # Related queries
        related_queries = response.get('relatedQueries', [])
        if related_queries:
            queries = []
            for item in related_queries:
                if isinstance(item, dict):
                    queries.append(item.get('title', ''))
                elif isinstance(item, str):
                    queries.append(item)
            
            if queries:
                stats['related'] = self.storage.store_related_queries(
                    query, queries, 'AP', 'related'
                )
        
        # People Also Ask
        paa = response.get('peopleAlsoAsk', [])
        if paa:
            stats['paa'] = self.storage.store_people_also_ask(query, paa, 'AP')
        
        # Store raw for analysis
        if related_queries or paa:
            self.storage.store_raw_response(query, 'AP', 'full', response)
        
        logger.info(f"Apify collection: {stats['related']} related, {stats['paa']} PAA for '{query}'")
        return stats
    
    def collect_from_serpapi(self, query: str, response: Dict[str, Any]) -> Dict[str, int]:
        """
        Extract related data from SerpAPI response.
        
        SerpAPI returns:
        - related_searches: [{query: str, link: str}]
        - related_questions: [{question: str, snippet: str, link: str}]
        """
        stats = {'related': 0, 'paa': 0}
        
        # Related searches
        related = response.get('related_searches', [])
        if related:
            queries = [item.get('query', '') for item in related if item.get('query')]
            if queries:
                stats['related'] = self.storage.store_related_queries(
                    query, queries, 'SA', 'related'
                )
        
        # Related questions (PAA equivalent)
        paa = response.get('related_questions', []) or response.get('people_also_ask', [])
        if paa:
            # Normalize to common format
            normalized_paa = []
            for item in paa:
                normalized_paa.append({
                    'question': item.get('question', ''),
                    'answer': item.get('snippet', ''),
                    'url': item.get('link', '')
                })
            stats['paa'] = self.storage.store_people_also_ask(query, normalized_paa, 'SA')
        
        return stats
    
    def collect_from_brightdata(self, query: str, response: Dict[str, Any]) -> Dict[str, int]:
        """
        Extract related data from BrightData SERP response.
        
        BrightData returns:
        - related_queries: [str] or [{query: str}]
        - people_also_ask: [{question: str, answer: str}]
        """
        stats = {'related': 0, 'paa': 0}
        
        # Related queries
        related = response.get('related_queries', []) or response.get('relatedSearches', [])
        if related:
            if isinstance(related[0], dict):
                queries = [item.get('query', '') or item.get('title', '') for item in related]
            else:
                queries = related
            
            if queries:
                stats['related'] = self.storage.store_related_queries(
                    query, queries, 'SB', 'related'
                )
        
        # PAA
        paa = response.get('people_also_ask', []) or response.get('peopleAlsoAsk', [])
        if paa:
            stats['paa'] = self.storage.store_people_also_ask(query, paa, 'SB')
        
        return stats
    
    def collect_from_google_native(self, query: str, response: Dict[str, Any]) -> Dict[str, int]:
        """
        Extract from raw Google response (scraped).
        
        Format varies but typically:
        - relatedSearches: [str]
        """
        stats = {'related': 0, 'paa': 0}
        
        related = (
            response.get('relatedSearches', []) or 
            response.get('related_searches', []) or
            response.get('suggestions', [])
        )
        
        if related:
            if isinstance(related[0], dict):
                queries = [item.get('query', '') or item.get('text', '') for item in related]
            else:
                queries = related
            
            if queries:
                stats['related'] = self.storage.store_related_queries(
                    query, queries, 'GO', 'related'
                )
        
        return stats
    
    def collect_from_bing(self, query: str, response: Dict[str, Any]) -> Dict[str, int]:
        """Extract from Bing API response."""
        stats = {'related': 0, 'paa': 0}
        
        related = response.get('relatedSearches', {}).get('value', [])
        if related:
            queries = [item.get('text', '') for item in related if item.get('text')]
            if queries:
                stats['related'] = self.storage.store_related_queries(
                    query, queries, 'BI', 'related'
                )
        
        return stats
    
    def collect_from_duckduckgo(self, query: str, response: Dict[str, Any]) -> Dict[str, int]:
        """Extract from DuckDuckGo response."""
        stats = {'related': 0, 'paa': 0}
        
        # DDG returns RelatedTopics
        related = response.get('RelatedTopics', [])
        if related:
            queries = []
            for item in related:
                if isinstance(item, dict):
                    # Can be nested with 'Topics'
                    if 'Topics' in item:
                        for sub in item['Topics']:
                            if sub.get('Text'):
                                queries.append(sub['Text'].split(' - ')[0])
                    elif item.get('Text'):
                        queries.append(item['Text'].split(' - ')[0])
            
            if queries:
                stats['related'] = self.storage.store_related_queries(
                    query, queries, 'DD', 'related'
                )
        
        return stats
    
    def collect_auto(self, query: str, response: Dict[str, Any], engine_code: str) -> Dict[str, int]:
        """
        Auto-detect response format and collect.
        
        Args:
            query: Original search query
            response: Raw API response
            engine_code: 2-letter engine code (AP, SA, SB, GO, BI, DD, etc.)
        
        Returns:
            Stats dict with counts
        """
        engine_handlers = {
            'AP': self.collect_from_apify,
            'SA': self.collect_from_serpapi,
            'SB': self.collect_from_brightdata,
            'GO': self.collect_from_google_native,
            'BI': self.collect_from_bing,
            'DD': self.collect_from_duckduckgo,
        }
        
        handler = engine_handlers.get(engine_code)
        if handler:
            return handler(query, response)
        
        # Generic fallback - try common field names
        stats = {'related': 0, 'paa': 0}
        
        # Try all common field names
        for field in ['relatedQueries', 'related_queries', 'relatedSearches', 
                      'related_searches', 'suggestions']:
            related = response.get(field, [])
            if related:
                if isinstance(related[0], dict):
                    queries = [
                        item.get('query', '') or item.get('title', '') or item.get('text', '')
                        for item in related
                    ]
                else:
                    queries = related
                
                queries = [q for q in queries if q]
                if queries:
                    stats['related'] = self.storage.store_related_queries(
                        query, queries, engine_code, 'related'
                    )
                    break
        
        # Try PAA fields
        for field in ['peopleAlsoAsk', 'people_also_ask', 'related_questions']:
            paa = response.get(field, [])
            if paa:
                stats['paa'] = self.storage.store_people_also_ask(query, paa, engine_code)
                break
        
        return stats
    
    def get_stats(self) -> Dict[str, int]:
        """Get collection statistics."""
        return self.storage.get_stats()
