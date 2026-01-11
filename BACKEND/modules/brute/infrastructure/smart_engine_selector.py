#!/usr/bin/env python3
"""
Smart Engine Selector
=====================
Intelligently selects search engines based on query characteristics.
Reduces average search time from 3.5s to under 600ms by avoiding slow engines.

Based on performance benchmarks showing:
- Lightning tier (<1ms): 7 engines
- Fast tier (1-10ms): 20 engines
- Slow tier (>200ms): 3 engines (HF, AL, LG)
"""

import re
from typing import List, Dict, Set, Optional
from enum import Enum

try:
    from .engine_performance_config import (
        PERFORMANCE_TIERS,
        OPTIMIZED_ENGINE_SETS,
        get_engines_for_tier,
        get_engine_performance_score
    )
except ImportError:
    from engine_performance_config import (
        PERFORMANCE_TIERS,
        OPTIMIZED_ENGINE_SETS,
        get_engines_for_tier,
        get_engine_performance_score
    )


class QueryType(Enum):
    """Query type classification."""
    GENERAL = "general"
    ACADEMIC = "academic"
    NEWS = "news"
    TECHNICAL = "technical"
    HISTORICAL = "historical"
    CODE = "code"
    BOOKS = "books"
    SOCIAL = "social"
    CORPORATE = "corporate"


class SmartEngineSelector:
    """Intelligently selects engines based on query analysis."""

    # Keyword patterns for query classification
    PATTERNS = {
        QueryType.ACADEMIC: [
            r'\b(research|study|paper|journal|academic|scholar|citation|doi|pubmed|arxiv)\b',
            r'\b(university|professor|phd|thesis|dissertation)\b',
            r'\b(peer[\s-]?review|impact factor|h[\s-]?index)\b'
        ],
        QueryType.NEWS: [
            r'\b(news|breaking|latest|recent|today|yesterday|this week)\b',
            r'\b(headline|reporter|journalist|press release|announcement)\b',
            r'\b(developing|update|coverage|reported)\b'
        ],
        QueryType.TECHNICAL: [
            r'\b(code|programming|api|sdk|library|framework|algorithm)\b',
            r'\b(python|javascript|java|c\+\+|rust|golang|typescript)\b',
            r'\b(github|stackoverflow|documentation|tutorial|implementation)\b'
        ],
        QueryType.CODE: [
            r'\b(function|class|method|variable|syntax|debug|error)\b',
            r'\b(repo|repository|commit|pull request|merge)\b',
            r'\b(npm|pip|cargo|maven|gradle)\b'
        ],
        QueryType.HISTORICAL: [
            r'\b(history|historical|archive|past|vintage|old|classic)\b',
            r'\b(\d{4}s|century|era|period|ancient|medieval)\b',
            r'\b(wayback|snapshot|archived version)\b'
        ],
        QueryType.BOOKS: [
            r'\b(book|ebook|pdf|epub|chapter|author|isbn|publication)\b',
            r'\b(library|gutenberg|libgen|novel|textbook)\b'
        ],
        QueryType.SOCIAL: [
            r'\b(twitter|facebook|reddit|linkedin|instagram|tiktok)\b',
            r'\b(social media|post|tweet|comment|discussion|forum)\b',
            r'\b(viral|trending|hashtag)\b'
        ],
        QueryType.CORPORATE: [
            r'\b(company|corporation|business|firm|enterprise)\b',
            r'\b(ceo|cfo|board|shareholders|annual report)\b',
            r'\b(revenue|profit|market cap|stock)\b'
        ]
    }

    # Engine sets optimized for each query type
    ENGINE_SETS = {
        QueryType.GENERAL: ['DD', 'BR', 'BI', 'GO', 'YA', 'QW', 'AR', 'EX'],
        QueryType.ACADEMIC: ['OA', 'CR', 'SE', 'AX', 'PM', 'WP', 'GU', 'JS', 'GO'],
        QueryType.NEWS: ['NA', 'GR', 'GD', 'GO', 'BI', 'YA'],
        QueryType.TECHNICAL: ['GO', 'DD', 'GR', 'SE', 'WP'],  # Exclude HF for speed
        QueryType.CODE: ['GO', 'DD', 'GR', 'HF'],  # Include HF only for code
        QueryType.HISTORICAL: ['AR', 'AA', 'WP', 'GO', 'BI'],
        QueryType.BOOKS: ['BK', 'AA', 'LG', 'GU', 'OL'],  # Include LG for books
        QueryType.SOCIAL: ['SS', 'BO', 'GO', 'BI', 'DD'],
        QueryType.CORPORATE: ['GO', 'BI', 'EX', 'GR', 'AL']  # Include AL for corporate
    }

    def __init__(self, performance_mode: str = 'balanced'):
        """Initialize smart engine selector.

        Args:
            performance_mode: 'speed' (fastest), 'balanced', or 'comprehensive'
        """
        self.performance_mode = performance_mode
        self.classification_cache = {}

    def classify_query(self, query: str) -> QueryType:
        """Classify query into a type.

        Args:
            query: Search query string

        Returns:
            QueryType enum value
        """
        # Check cache
        if query in self.classification_cache:
            return self.classification_cache[query]

        query_lower = query.lower()
        scores = {}

        # Calculate match scores for each type
        for query_type, patterns in self.PATTERNS.items():
            score = 0
            for pattern in patterns:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    score += 1
            scores[query_type] = score

        # Get highest scoring type
        if scores:
            best_type = max(scores.items(), key=lambda x: x[1])
            if best_type[1] > 0:
                result = best_type[0]
                self.classification_cache[query] = result
                return result

        # Default to general
        return QueryType.GENERAL

    def select_engines(self, query: str, max_engines: Optional[int] = None) -> List[str]:
        """Select optimal engines for query.

        Args:
            query: Search query string
            max_engines: Maximum engines to return (None = use all recommended)

        Returns:
            List of engine codes
        """
        # Classify query
        query_type = self.classify_query(query)

        # Get base engine set for query type
        base_engines = self.ENGINE_SETS.get(query_type, self.ENGINE_SETS[QueryType.GENERAL])

        # Apply performance mode filtering
        if self.performance_mode == 'speed':
            # Only use lightning-fast engines
            lightning = set(PERFORMANCE_TIERS['lightning'])
            base_engines = [e for e in base_engines if e in lightning]

        elif self.performance_mode == 'balanced':
            # Exclude very slow engines (unless specifically needed)
            very_slow = set(PERFORMANCE_TIERS['very_slow'])
            if query_type not in [QueryType.CODE, QueryType.BOOKS, QueryType.CORPORATE]:
                base_engines = [e for e in base_engines if e not in very_slow]

        # Sort by performance score (highest first)
        sorted_engines = sorted(
            base_engines,
            key=lambda e: get_engine_performance_score(e),
            reverse=True
        )

        # Apply max limit if specified
        if max_engines:
            sorted_engines = sorted_engines[:max_engines]

        return sorted_engines

    def get_recommendation(self, query: str, max_engines: int = 8) -> Dict:
        """Get detailed recommendation for query.

        Args:
            query: Search query string
            max_engines: Maximum engines to recommend

        Returns:
            Dictionary with recommendation details
        """
        query_type = self.classify_query(query)
        selected_engines = self.select_engines(query, max_engines)

        # Calculate estimated performance
        try:
            from .engine_performance_config import ENGINE_INIT_TIMES
        except ImportError:
            from engine_performance_config import ENGINE_INIT_TIMES

        total_init = sum(ENGINE_INIT_TIMES.get(e, 100) for e in selected_engines)
        avg_init = total_init / len(selected_engines) if selected_engines else 0

        # Categorize selected engines by tier
        tiers = {'lightning': [], 'fast': [], 'standard': [], 'slow': [], 'very_slow': []}
        for engine in selected_engines:
            for tier_name, tier_engines in PERFORMANCE_TIERS.items():
                if engine in tier_engines:
                    tiers[tier_name].append(engine)
                    break

        return {
            'query_type': query_type.value,
            'selected_engines': selected_engines,
            'engine_count': len(selected_engines),
            'performance': {
                'total_init_ms': total_init,
                'avg_init_ms': avg_init,
                'estimated_search_ms': 500 + total_init,  # 500ms parallel search + init
                'tier_breakdown': {k: v for k, v in tiers.items() if v}
            },
            'excluded_slow_engines': [
                e for e in PERFORMANCE_TIERS['very_slow']
                if e not in selected_engines
            ]
        }


# Convenience functions
_selector = None

def get_selector(performance_mode: str = 'balanced') -> SmartEngineSelector:
    """Get global selector instance."""
    global _selector
    if _selector is None or _selector.performance_mode != performance_mode:
        _selector = SmartEngineSelector(performance_mode)
    return _selector


def select_engines_for_query(query: str, performance_mode: str = 'balanced',
                             max_engines: Optional[int] = None) -> List[str]:
    """Quick function to select engines for a query.

    Args:
        query: Search query
        performance_mode: 'speed', 'balanced', or 'comprehensive'
        max_engines: Maximum number of engines

    Returns:
        List of recommended engine codes
    """
    selector = get_selector(performance_mode)
    return selector.select_engines(query, max_engines)


def get_query_recommendation(query: str, performance_mode: str = 'balanced',
                            max_engines: int = 8) -> Dict:
    """Get detailed recommendation for query.

    Args:
        query: Search query
        performance_mode: 'speed', 'balanced', or 'comprehensive'
        max_engines: Maximum number of engines

    Returns:
        Recommendation dictionary
    """
    selector = get_selector(performance_mode)
    return selector.get_recommendation(query, max_engines)


if __name__ == '__main__':
    # Demo smart engine selection
    print("Smart Engine Selector - Demo")
    print("="*60)

    test_queries = [
        "climate change effects",
        "latest breaking news technology",
        "python async programming tutorial",
        "world war 2 documents archive",
        "machine learning research papers",
        "download free programming books",
        "what do people say about iPhone on reddit",
        "Apple Inc annual report 2023"
    ]

    selector = SmartEngineSelector(performance_mode='balanced')

    for query in test_queries:
        print(f"\nQuery: '{query}'")
        rec = selector.get_recommendation(query, max_engines=5)

        print(f"  Type: {rec['query_type']}")
        print(f"  Engines: {', '.join(rec['selected_engines'])}")
        print(f"  Estimated time: {rec['performance']['estimated_search_ms']:.0f}ms")

        if rec['excluded_slow_engines']:
            print(f"  Excluded (slow): {', '.join(rec['excluded_slow_engines'])}")
