#!/usr/bin/env python3
"""
Query Router - Intelligent engine selection based on multi-axis analysis.

Implements SWITCHBOARD pattern to reduce engine count from 65 to 10-15 per query,
achieving 75% faster searches while maintaining high recall.

Engine Selection Strategy:
1. Analyze query across four axes (SUBJECT, LOCATION, OBJECT, TEMPORAL)
2. Map detected axes to engine capabilities via tags
3. Apply interaction rules for axis combinations
4. Score and rank engines by relevance
5. Return optimal subset (10-15 engines)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from .axis_analyzer import (
        AxisAnalyzer,
        AxisAnalysis,
        SubjectType,
        LocationContext,
        ObjectOperator,
        TemporalContext,
    )
except ImportError:
    from axis_analyzer import (
        AxisAnalyzer,
        AxisAnalysis,
        SubjectType,
        LocationContext,
        ObjectOperator,
        TemporalContext,
    )

logger = logging.getLogger(__name__)


@dataclass
class EngineTag:
    """Tags describing engine capabilities."""
    code: str
    name: str
    tags: Set[str] = field(default_factory=set)
    tier: str = "fast"  # lightning, fast, standard, slow, very_slow
    reliability: float = 0.85
    disabled: bool = False


@dataclass
class QueryAnalysis:
    """Complete query analysis for routing."""
    original_query: str
    cleaned_query: str
    axis_analysis: AxisAnalysis
    detected_intent: str  # 'discovery', 'lookup', 'verification', 'research'
    complexity_score: float  # 0-1, how complex is this query


@dataclass
class EngineRecommendation:
    """Engine selection recommendation."""
    query_analysis: QueryAnalysis
    recommended_engines: List[str]  # Engine codes
    engine_scores: Dict[str, float]  # Code -> relevance score
    tier_breakdown: Dict[str, List[str]]  # Tier -> codes
    estimated_time_ms: int
    explanation: str


class QueryRouter:
    """
    Intelligent query router implementing SWITCHBOARD pattern.

    Maps query characteristics to engine capabilities for optimal
    engine subset selection.
    """

    # Engine tags define capabilities
    # Tags: general, academic, news, social, books, archives, corporate,
    #       code, regional_us, regional_eu, regional_ru, regional_cn, etc.
    ENGINE_TAGS: Dict[str, EngineTag] = {
        # General Web Search
        'GO': EngineTag('GO', 'Google', {'general', 'web', 'news', 'local'}, 'standard', 0.98),
        'BI': EngineTag('BI', 'Bing', {'general', 'web', 'news', 'corporate'}, 'lightning', 0.97),
        'DD': EngineTag('DD', 'DuckDuckGo', {'general', 'web', 'privacy'}, 'lightning', 0.96),
        'BR': EngineTag('BR', 'Brave', {'general', 'web', 'privacy'}, 'lightning', 0.95),
        'YA': EngineTag('YA', 'Yandex', {'general', 'web', 'regional_ru'}, 'fast', 0.94),
        'QW': EngineTag('QW', 'Qwant', {'general', 'web', 'regional_eu', 'privacy'}, 'fast', 0.90),

        # Academic / Research
        'SE': EngineTag('SE', 'SemanticScholar', {'academic', 'research', 'papers'}, 'fast', 0.93),
        'OA': EngineTag('OA', 'OpenAlex', {'academic', 'research', 'papers'}, 'fast', 0.91),
        'CR': EngineTag('CR', 'Crossref', {'academic', 'research', 'papers', 'doi'}, 'fast', 0.92),
        'AX': EngineTag('AX', 'arXiv', {'academic', 'research', 'papers', 'preprints'}, 'standard', 0.93),
        'PM': EngineTag('PM', 'PubMed', {'academic', 'medical', 'research', 'papers'}, 'standard', 0.94),
        'JS': EngineTag('JS', 'JSTOR', {'academic', 'research', 'papers', 'books'}, 'fast', 0.88),
        'SG': EngineTag('SG', 'SAGEJournals', {'academic', 'research', 'papers'}, 'fast', 0.87),
        'MU': EngineTag('MU', 'ProjectMUSE', {'academic', 'research', 'papers'}, 'fast', 0.87),
        'NT': EngineTag('NT', 'Nature', {'academic', 'research', 'papers', 'science'}, 'fast', 0.89),

        # News
        'NA': EngineTag('NA', 'NewsAPI', {'news', 'current_events', 'media'}, 'lightning', 0.90),
        'GR': EngineTag('GR', 'Grok', {'news', 'social', 'realtime'}, 'fast', 0.88),
        'GD': EngineTag('GD', 'GDELT', {'news', 'global', 'events'}, 'standard', 0.85),

        # Books / Literature
        'GU': EngineTag('GU', 'Gutenberg', {'books', 'literature', 'free'}, 'fast', 0.90),
        'OL': EngineTag('OL', 'OpenLibrary', {'books', 'library'}, 'fast', 0.88),
        'BK': EngineTag('BK', 'Books', {'books', 'literature'}, 'fast', 0.85),
        'AA': EngineTag('AA', 'AnnasArchive', {'books', 'archives', 'shadow'}, 'fast', 0.80),
        'LG': EngineTag('LG', 'LibGen', {'books', 'shadow', 'academic'}, 'very_slow', 0.75, disabled=False),

        # Archives / Historical
        'AR': EngineTag('AR', 'Archive.org', {'archives', 'historical', 'wayback'}, 'fast', 0.92),
        'WP': EngineTag('WP', 'Wikipedia', {'reference', 'facts', 'historical'}, 'standard', 0.95),
        'W': EngineTag('W', 'WikiLeaks', {'archives', 'leaks', 'investigative'}, 'fast', 0.82),

        # Social / Forums
        'SS': EngineTag('SS', 'SocialSearcher', {'social', 'social_media'}, 'fast', 0.80),
        'BO': EngineTag('BO', 'BoardReader', {'social', 'forums', 'discussions'}, 'fast', 0.75, disabled=True),

        # Code / Technical
        'HF': EngineTag('HF', 'HuggingFace', {'code', 'ml', 'ai', 'models'}, 'very_slow', 0.85),

        # Corporate / OSINT
        'AL': EngineTag('AL', 'Aleph', {'corporate', 'osint', 'leaks', 'documents'}, 'very_slow', 0.80),
        'EX': EngineTag('EX', 'Exa', {'general', 'semantic', 'ai'}, 'standard', 0.91),

        # Specialized
        'PW': EngineTag('PW', 'PublicWWW', {'code', 'html', 'source'}, 'lightning', 0.82),
        'YE': EngineTag('YE', 'Yep', {'general', 'web'}, 'slow', 0.78),
        'SP': EngineTag('SP', 'Startpage', {'general', 'privacy'}, 'lightning', 0.88),
        'YO': EngineTag('YO', 'You.com', {'general', 'ai'}, 'lightning', 0.85),
        'BS': EngineTag('BS', 'BareSearch', {'general', 'web'}, 'fast', 0.80),
        'BA': EngineTag('BA', 'Baidu', {'general', 'regional_cn'}, 'fast', 0.85),
    }

    # Subject type to tags mapping
    SUBJECT_TAG_MAP: Dict[SubjectType, Set[str]] = {
        SubjectType.PERSON: {'general', 'social', 'corporate', 'osint'},
        SubjectType.COMPANY: {'corporate', 'osint', 'news', 'general'},
        SubjectType.PHONE: {'osint', 'general'},
        SubjectType.EMAIL: {'osint', 'general'},
        SubjectType.ADDRESS: {'general', 'local'},
        SubjectType.DOMAIN: {'general', 'web', 'code'},
        SubjectType.IP_ADDRESS: {'osint', 'code'},
        SubjectType.USERNAME: {'social', 'osint'},
        SubjectType.TOPIC: {'general', 'web'},
        SubjectType.ACADEMIC: {'academic', 'research', 'papers'},
        SubjectType.NEWS: {'news', 'current_events', 'media'},
        SubjectType.PRODUCT: {'general', 'web'},
        SubjectType.LEGAL: {'archives', 'osint', 'general'},
        SubjectType.FINANCIAL: {'corporate', 'news', 'general'},
        SubjectType.MEDICAL: {'academic', 'medical', 'research'},
        SubjectType.CODE: {'code', 'ml', 'ai'},
        SubjectType.BOOK: {'books', 'literature', 'library'},
        SubjectType.SOCIAL: {'social', 'social_media', 'forums'},
    }

    # Location to regional tags mapping
    LOCATION_TAG_MAP: Dict[LocationContext, Set[str]] = {
        LocationContext.GLOBAL: set(),  # No regional preference
        LocationContext.US: {'regional_us'},
        LocationContext.UK: {'regional_eu'},  # Close enough for UK
        LocationContext.EU: {'regional_eu'},
        LocationContext.RUSSIA: {'regional_ru'},
        LocationContext.CHINA: {'regional_cn'},
        LocationContext.JAPAN: {'regional_jp'},
        LocationContext.LATAM: {'regional_latam'},
        LocationContext.AFRICA: set(),
        LocationContext.MIDDLE_EAST: set(),
        LocationContext.ASIA_PACIFIC: set(),
        LocationContext.LOCAL: {'local'},
    }

    # Operator to engine preference mapping
    OPERATOR_ENGINE_MAP: Dict[ObjectOperator, List[str]] = {
        ObjectOperator.SITE: ['GO', 'BI', 'DD', 'BR'],  # Site search
        ObjectOperator.FILETYPE: ['GO', 'BI', 'DD'],  # Filetype search
        ObjectOperator.EXACT_PHRASE: ['GO', 'BI', 'DD', 'YA'],  # Good at exact match
        ObjectOperator.CACHE: ['GO', 'AR'],  # Cache/archive
        ObjectOperator.LINK: ['GO', 'BI', 'EX'],  # Backlinks
    }

    # Temporal to engine preference mapping
    TEMPORAL_ENGINE_MAP: Dict[TemporalContext, List[str]] = {
        TemporalContext.RECENT: ['NA', 'GR', 'GD', 'GO', 'BI'],  # News engines
        TemporalContext.HISTORICAL: ['AR', 'AA', 'WP', 'GU'],  # Archive engines
    }

    # Tier timeouts (milliseconds)
    TIER_TIMEOUTS: Dict[str, int] = {
        'lightning': 30000,   # 30s
        'fast': 60000,        # 60s
        'standard': 90000,    # 90s
        'slow': 120000,       # 120s
        'very_slow': 180000,  # 180s
    }

    def __init__(
        self,
        max_engines: int = 15,
        min_engines: int = 5,
        performance_mode: str = 'balanced'
    ):
        """
        Initialize query router.

        Args:
            max_engines: Maximum engines to recommend (default 15)
            min_engines: Minimum engines to recommend (default 5)
            performance_mode: 'speed', 'balanced', or 'comprehensive'
        """
        self.max_engines = max_engines
        self.min_engines = min_engines
        self.performance_mode = performance_mode
        self.axis_analyzer = AxisAnalyzer()

    def route(self, query: str) -> EngineRecommendation:
        """
        Route query to optimal engine subset.

        Args:
            query: Search query string

        Returns:
            EngineRecommendation with selected engines and metadata
        """
        # Analyze query
        axis_analysis = self.axis_analyzer.analyze(query)

        # Determine intent and complexity
        intent = self._detect_intent(axis_analysis)
        complexity = self._calculate_complexity(axis_analysis)

        query_analysis = QueryAnalysis(
            original_query=query,
            cleaned_query=axis_analysis.cleaned_query,
            axis_analysis=axis_analysis,
            detected_intent=intent,
            complexity_score=complexity
        )

        # Score engines
        engine_scores = self._score_engines(axis_analysis)

        # Select engines
        selected = self._select_engines(engine_scores, axis_analysis)

        # Build recommendation
        recommendation = self._build_recommendation(
            query_analysis, selected, engine_scores
        )

        logger.info(
            "Query routed: '%s' -> %d engines (%s)",
            query[:50], len(selected), ', '.join(selected[:5])
        )

        return recommendation

    def _detect_intent(self, analysis: AxisAnalysis) -> str:
        """Detect query intent from axis analysis."""
        # Specific entity = lookup
        if analysis.detected_entities:
            return 'lookup'

        # Operators = verification
        if analysis.operators:
            return 'verification'

        # Academic/research subjects = research
        if SubjectType.ACADEMIC in analysis.subject_types:
            return 'research'

        # Default = discovery
        return 'discovery'

    def _calculate_complexity(self, analysis: AxisAnalysis) -> float:
        """Calculate query complexity score (0-1)."""
        score = 0.0

        # More subject types = more complex
        score += len(analysis.subject_types) * 0.15

        # Operators add complexity
        score += len(analysis.operators) * 0.1

        # Non-global location adds complexity
        if analysis.location_context != LocationContext.GLOBAL:
            score += 0.2

        # Temporal constraints add complexity
        if analysis.temporal_context != TemporalContext.ANY_TIME:
            score += 0.15

        return min(1.0, score)

    def _score_engines(self, analysis: AxisAnalysis) -> Dict[str, float]:
        """Score each engine based on query characteristics."""
        scores: Dict[str, float] = {}

        # Get relevant tags from subject types
        relevant_tags: Set[str] = set()
        for subject_type in analysis.subject_types:
            relevant_tags.update(self.SUBJECT_TAG_MAP.get(subject_type, set()))

        # Add location tags
        relevant_tags.update(
            self.LOCATION_TAG_MAP.get(analysis.location_context, set())
        )

        # Score each engine
        for code, engine in self.ENGINE_TAGS.items():
            if engine.disabled:
                scores[code] = 0.0
                continue

            score = 0.0

            # Tag match score (0-50 points)
            if relevant_tags:
                tag_overlap = len(engine.tags & relevant_tags)
                tag_score = (tag_overlap / len(relevant_tags)) * 50
                score += tag_score

            # Reliability bonus (0-20 points)
            score += engine.reliability * 20

            # Performance mode adjustment
            if self.performance_mode == 'speed':
                # Heavily penalize slow engines
                tier_penalty = {
                    'lightning': 0, 'fast': 5, 'standard': 15, 'slow': 30, 'very_slow': 50
                }
                score -= tier_penalty.get(engine.tier, 30)
            elif self.performance_mode == 'comprehensive':
                # Slight bonus to slow but thorough engines
                tier_bonus = {'very_slow': 10, 'slow': 5}
                score += tier_bonus.get(engine.tier, 0)

            # Operator-based boosts
            for operator in analysis.operators:
                if code in self.OPERATOR_ENGINE_MAP.get(operator, []):
                    score += 15

            # Temporal boosts
            if code in self.TEMPORAL_ENGINE_MAP.get(analysis.temporal_context, []):
                score += 10

            scores[code] = max(0, score)

        return scores

    def _select_engines(
        self,
        scores: Dict[str, float],
        analysis: AxisAnalysis
    ) -> List[str]:
        """Select optimal engine subset from scores."""
        # Sort by score descending
        sorted_engines = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        selected: List[str] = []
        selected_tiers: Dict[str, int] = {
            'lightning': 0, 'fast': 0, 'standard': 0, 'slow': 0, 'very_slow': 0
        }

        # Tier limits based on performance mode
        tier_limits = {
            'speed': {'lightning': 6, 'fast': 4, 'standard': 2, 'slow': 0, 'very_slow': 0},
            'balanced': {'lightning': 5, 'fast': 5, 'standard': 3, 'slow': 1, 'very_slow': 1},
            'comprehensive': {'lightning': 4, 'fast': 5, 'standard': 4, 'slow': 2, 'very_slow': 2},
        }
        limits = tier_limits.get(self.performance_mode, tier_limits['balanced'])

        for code, score in sorted_engines:
            if len(selected) >= self.max_engines:
                break

            if score <= 0:
                continue

            engine = self.ENGINE_TAGS.get(code)
            if not engine or engine.disabled:
                continue

            # Check tier limit
            if selected_tiers[engine.tier] >= limits[engine.tier]:
                continue

            selected.append(code)
            selected_tiers[engine.tier] += 1

        # Ensure minimum engines
        if len(selected) < self.min_engines:
            # Add more from general engines
            general_fallback = ['GO', 'BI', 'DD', 'BR', 'YA', 'EX']
            for code in general_fallback:
                if code not in selected and len(selected) < self.min_engines:
                    selected.append(code)

        return selected

    def _build_recommendation(
        self,
        query_analysis: QueryAnalysis,
        selected: List[str],
        scores: Dict[str, float]
    ) -> EngineRecommendation:
        """Build recommendation from selection results."""
        # Group by tier
        tier_breakdown: Dict[str, List[str]] = {
            'lightning': [], 'fast': [], 'standard': [], 'slow': [], 'very_slow': []
        }
        for code in selected:
            engine = self.ENGINE_TAGS.get(code)
            if engine:
                tier_breakdown[engine.tier].append(code)

        # Estimate time based on slowest tier in use
        estimated_time = 30000  # Base 30s
        for tier in ['very_slow', 'slow', 'standard', 'fast', 'lightning']:
            if tier_breakdown[tier]:
                estimated_time = self.TIER_TIMEOUTS[tier]
                break

        # Build explanation
        analysis = query_analysis.axis_analysis
        explanation_parts = []

        if analysis.subject_types:
            subjects = ', '.join(s.name.lower() for s in analysis.subject_types[:3])
            explanation_parts.append(f"detected subjects: {subjects}")

        if analysis.location_context != LocationContext.GLOBAL:
            explanation_parts.append(f"region: {analysis.location_context.name.lower()}")

        if analysis.operators:
            ops = ', '.join(o.name.lower() for o in analysis.operators[:2])
            explanation_parts.append(f"operators: {ops}")

        explanation = f"Selected {len(selected)} engines ({'; '.join(explanation_parts)})"

        return EngineRecommendation(
            query_analysis=query_analysis,
            recommended_engines=selected,
            engine_scores={code: scores[code] for code in selected},
            tier_breakdown={k: v for k, v in tier_breakdown.items() if v},
            estimated_time_ms=estimated_time,
            explanation=explanation
        )

    def get_engines_for_tier(self, tier: str) -> List[str]:
        """Get all engine codes for a specific tier."""
        return [
            code for code, engine in self.ENGINE_TAGS.items()
            if engine.tier == tier and not engine.disabled
        ]

    def get_all_enabled_engines(self) -> List[str]:
        """Get all enabled engine codes."""
        return [
            code for code, engine in self.ENGINE_TAGS.items()
            if not engine.disabled
        ]


# Singleton for convenience
_router: Optional[QueryRouter] = None

def get_router(
    max_engines: int = 15,
    performance_mode: str = 'balanced'
) -> QueryRouter:
    """Get global QueryRouter instance."""
    global _router
    if _router is None:
        _router = QueryRouter(max_engines=max_engines, performance_mode=performance_mode)
    return _router


def route_query(query: str, performance_mode: str = 'balanced') -> EngineRecommendation:
    """Quick function to route a query."""
    router = get_router(performance_mode=performance_mode)
    return router.route(query)


if __name__ == '__main__':
    # Demo query routing
    print("Query Router - Demo")
    print("=" * 70)

    test_queries = [
        "climate change effects",                          # General topic
        "John Smith CEO Apple",                            # Person + Company
        "+1-555-123-4567",                                 # Phone lookup
        "site:github.com python async await",             # Code + operator
        "filetype:pdf annual report Apple 2023",          # Corporate + operator
        "latest news Ukraine Russia",                      # News + location
        "machine learning research papers 2024",          # Academic
        "download programming books python",              # Books
        "what do people say about Tesla on reddit",       # Social
        "Berlin wall history 1989",                       # Historical
    ]

    router = QueryRouter(max_engines=12, performance_mode='balanced')

    for query in test_queries:
        print(f"\n{'─'*70}")
        print(f"Query: '{query}'")

        rec = router.route(query)

        print(f"Intent: {rec.query_analysis.detected_intent}")
        print(f"Complexity: {rec.query_analysis.complexity_score:.2f}")
        print(f"Engines ({len(rec.recommended_engines)}): {', '.join(rec.recommended_engines)}")
        print(f"Est. time: {rec.estimated_time_ms}ms")
        print(f"Explanation: {rec.explanation}")

        if rec.tier_breakdown:
            tiers = [f"{t}:{len(e)}" for t, e in rec.tier_breakdown.items()]
            print(f"Tier breakdown: {', '.join(tiers)}")
