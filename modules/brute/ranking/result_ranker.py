#!/usr/bin/env python3
"""
Result Ranker - Quality ranking with confidence scores.

Scoring Formula:
- Engine Tier (40%): Results from reliable engines score higher
- Consensus (30%): URLs appearing from multiple engines get boosted
- Relevance (20%): Query term matching in title/snippet
- Freshness (10%): Recent results score higher

Output: Each result gets a confidence score (0-100) and ranking position.
"""
from __future__ import annotations

import re
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class RankedResult:
    """A search result with confidence scoring."""
    url: str
    title: str
    snippet: str
    engine: str
    tier: str

    # Scoring
    confidence_score: float = 0.0
    tier_score: float = 0.0
    consensus_score: float = 0.0
    relevance_score: float = 0.0
    freshness_score: float = 0.0

    # Metadata
    rank: int = 0
    engines_found_in: List[str] = field(default_factory=list)
    date_detected: Optional[str] = None
    domain: str = ""

    # Original data
    raw_result: Dict[str, Any] = field(default_factory=dict)


class ResultRanker:
    """
    Result quality ranker with multi-factor scoring.

    Produces confidence scores (0-100) based on:
    - Engine reliability (tier)
    - Cross-engine consensus
    - Query term relevance
    - Content freshness
    """

    # Engine tier reliability scores (0-1)
    TIER_SCORES = {
        'lightning': 0.95,  # Highly reliable fast engines
        'fast': 0.85,       # Reliable mainstream engines
        'standard': 0.75,   # Standard reliability
        'slow': 0.65,       # Slower, variable quality
        'very_slow': 0.55,  # Shadow/alternative sources
    }

    # Specific engine reliability overrides
    ENGINE_RELIABILITY = {
        'GO': 0.98,  # Google
        'BI': 0.97,  # Bing
        'DD': 0.96,  # DuckDuckGo
        'BR': 0.95,  # Brave
        'WP': 0.95,  # Wikipedia
        'SE': 0.93,  # SemanticScholar
        'CR': 0.92,  # Crossref
        'PM': 0.94,  # PubMed
        'AX': 0.93,  # arXiv
        'AR': 0.92,  # Archive.org
        'EX': 0.91,  # Exa
        'YA': 0.90,  # Yandex
        'NA': 0.88,  # NewsAPI
        'GR': 0.85,  # Grok
        'GD': 0.82,  # GDELT
        'LG': 0.70,  # LibGen
        'AA': 0.72,  # AnnasArchive
        'AL': 0.78,  # Aleph
        'HF': 0.80,  # HuggingFace
    }

    # Scoring weights (must sum to 1.0)
    WEIGHTS = {
        'tier': 0.40,      # Engine reliability
        'consensus': 0.30,  # Multi-engine agreement
        'relevance': 0.20,  # Query matching
        'freshness': 0.10,  # Recency
    }

    # Date patterns for freshness detection
    DATE_PATTERNS = [
        r'(\d{4})-(\d{2})-(\d{2})',  # 2024-01-15
        r'(\d{1,2})/(\d{1,2})/(\d{4})',  # 1/15/2024
        r'(\w+)\s+(\d{1,2}),?\s+(\d{4})',  # January 15, 2024
        r'(\d{1,2})\s+(\w+)\s+(\d{4})',  # 15 January 2024
    ]

    def __init__(
        self,
        tier_weight: float = 0.40,
        consensus_weight: float = 0.30,
        relevance_weight: float = 0.20,
        freshness_weight: float = 0.10
    ):
        """
        Initialize ranker with custom weights.

        Args:
            tier_weight: Weight for engine tier score (default 0.40)
            consensus_weight: Weight for consensus score (default 0.30)
            relevance_weight: Weight for relevance score (default 0.20)
            freshness_weight: Weight for freshness score (default 0.10)
        """
        # Validate weights
        total = tier_weight + consensus_weight + relevance_weight + freshness_weight
        if abs(total - 1.0) > 0.001:
            logger.warning("Weights don't sum to 1.0 (%.2f), normalizing", total)
            tier_weight /= total
            consensus_weight /= total
            relevance_weight /= total
            freshness_weight /= total

        self.weights = {
            'tier': tier_weight,
            'consensus': consensus_weight,
            'relevance': relevance_weight,
            'freshness': freshness_weight,
        }

        self._compiled_date_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.DATE_PATTERNS
        ]

    def rank(
        self,
        results: List[Dict[str, Any]],
        query: str,
        engine_tiers: Optional[Dict[str, str]] = None
    ) -> List[RankedResult]:
        """
        Rank results with confidence scores.

        Args:
            results: List of raw search results
            query: Original search query
            engine_tiers: Optional dict mapping engine codes to tiers

        Returns:
            List of RankedResult sorted by confidence score (descending)
        """
        if not results:
            return []

        engine_tiers = engine_tiers or {}

        # Step 1: Build URL consensus map
        url_engines = self._build_consensus_map(results)

        # Step 2: Score each result
        ranked_results: List[RankedResult] = []

        for result in results:
            url = result.get('url', '')
            if not url:
                continue

            # Create ranked result
            ranked = self._create_ranked_result(result, engine_tiers)

            # Calculate scores
            ranked.tier_score = self._calculate_tier_score(
                ranked.engine, ranked.tier, engine_tiers
            )
            ranked.consensus_score = self._calculate_consensus_score(
                url, url_engines
            )
            ranked.relevance_score = self._calculate_relevance_score(
                query, ranked.title, ranked.snippet
            )
            ranked.freshness_score = self._calculate_freshness_score(result)

            # Calculate final confidence score
            ranked.confidence_score = self._calculate_final_score(ranked)

            # Add engines that found this URL
            ranked.engines_found_in = list(url_engines.get(url, set()))

            ranked_results.append(ranked)

        # Sort by confidence score (descending)
        ranked_results.sort(key=lambda r: r.confidence_score, reverse=True)

        # Assign ranks
        for i, result in enumerate(ranked_results, 1):
            result.rank = i

        logger.info(
            "Ranked %d results, top score: %.1f",
            len(ranked_results),
            ranked_results[0].confidence_score if ranked_results else 0
        )

        return ranked_results

    def _build_consensus_map(
        self,
        results: List[Dict[str, Any]]
    ) -> Dict[str, Set[str]]:
        """Build map of URL -> set of engines that found it."""
        url_engines: Dict[str, Set[str]] = defaultdict(set)

        for result in results:
            url = result.get('url', '')
            engine = result.get('engine', result.get('engine_code', 'unknown'))
            if url:
                url_engines[url].add(engine)

        return url_engines

    def _create_ranked_result(
        self,
        result: Dict[str, Any],
        engine_tiers: Dict[str, str]
    ) -> RankedResult:
        """Create a RankedResult from raw result dict."""
        url = result.get('url', '')
        engine = result.get('engine', result.get('engine_code', 'unknown'))

        # Extract domain
        try:
            domain = urlparse(url).netloc
        except Exception:
            domain = ''

        return RankedResult(
            url=url,
            title=result.get('title', 'Untitled'),
            snippet=result.get('snippet', result.get('description', '')),
            engine=engine,
            tier=result.get('tier', engine_tiers.get(engine, 'fast')),
            domain=domain,
            date_detected=result.get('date', result.get('published_date')),
            raw_result=result
        )

    def _calculate_tier_score(
        self,
        engine: str,
        tier: str,
        engine_tiers: Dict[str, str]
    ) -> float:
        """Calculate tier-based reliability score (0-100)."""
        # Check for engine-specific override
        if engine in self.ENGINE_RELIABILITY:
            return self.ENGINE_RELIABILITY[engine] * 100

        # Fall back to tier score
        return self.TIER_SCORES.get(tier, 0.75) * 100

    def _calculate_consensus_score(
        self,
        url: str,
        url_engines: Dict[str, Set[str]]
    ) -> float:
        """
        Calculate consensus score based on multi-engine agreement (0-100).

        Results found by multiple engines are more trustworthy.
        """
        engines = url_engines.get(url, set())
        count = len(engines)

        if count <= 1:
            return 50.0  # Single engine = baseline
        elif count == 2:
            return 70.0
        elif count == 3:
            return 85.0
        elif count >= 4:
            return 95.0

        return 50.0

    def _calculate_relevance_score(
        self,
        query: str,
        title: str,
        snippet: str
    ) -> float:
        """
        Calculate relevance score based on query term matching (0-100).
        """
        if not query:
            return 50.0

        # Extract query terms (lowercase, no special chars)
        query_terms = set(re.findall(r'\w+', query.lower()))
        if not query_terms:
            return 50.0

        # Combine title and snippet
        text = f"{title} {snippet}".lower()
        text_words = set(re.findall(r'\w+', text))

        # Count matching terms
        matches = len(query_terms & text_words)
        match_ratio = matches / len(query_terms)

        # Check for exact phrase match
        exact_match_bonus = 0
        query_phrase = query.lower()
        if query_phrase in text:
            exact_match_bonus = 20

        # Title match bonus
        title_bonus = 0
        title_lower = title.lower()
        for term in query_terms:
            if term in title_lower:
                title_bonus += 5

        # Calculate score
        base_score = match_ratio * 60  # Up to 60 for term coverage
        score = base_score + exact_match_bonus + min(title_bonus, 20)

        return min(100.0, max(0.0, score))

    def _calculate_freshness_score(self, result: Dict[str, Any]) -> float:
        """
        Calculate freshness score based on detected date (0-100).
        """
        # Check for explicit date fields
        date_str = (
            result.get('date') or
            result.get('published_date') or
            result.get('published') or
            result.get('timestamp')
        )

        if not date_str:
            # Try to extract from snippet
            snippet = result.get('snippet', '')
            date_str = self._extract_date_from_text(snippet)

        if not date_str:
            return 50.0  # Unknown = neutral

        # Parse date
        try:
            # Try ISO format first
            if isinstance(date_str, str):
                if 'T' in date_str:
                    date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                else:
                    date = datetime.strptime(date_str[:10], '%Y-%m-%d')
            else:
                return 50.0

            # Calculate age in days
            now = datetime.now(date.tzinfo) if date.tzinfo else datetime.now()
            age_days = (now - date).days

            # Score based on age
            if age_days < 0:
                return 50.0  # Future date = suspicious
            elif age_days <= 7:
                return 95.0  # Past week
            elif age_days <= 30:
                return 85.0  # Past month
            elif age_days <= 90:
                return 75.0  # Past quarter
            elif age_days <= 365:
                return 65.0  # Past year
            elif age_days <= 730:
                return 55.0  # Past 2 years
            else:
                return 45.0  # Older

        except Exception:
            return 50.0

    def _extract_date_from_text(self, text: str) -> Optional[str]:
        """Try to extract a date from text."""
        for pattern in self._compiled_date_patterns:
            match = pattern.search(text)
            if match:
                return match.group(0)
        return None

    def _calculate_final_score(self, result: RankedResult) -> float:
        """Calculate weighted final confidence score."""
        score = (
            result.tier_score * self.weights['tier'] +
            result.consensus_score * self.weights['consensus'] +
            result.relevance_score * self.weights['relevance'] +
            result.freshness_score * self.weights['freshness']
        )
        return round(score, 1)


def rank_results(
    results: List[Dict[str, Any]],
    query: str,
    engine_tiers: Optional[Dict[str, str]] = None
) -> List[RankedResult]:
    """Convenience function to rank results."""
    ranker = ResultRanker()
    return ranker.rank(results, query, engine_tiers)


if __name__ == '__main__':
    # Demo ranking
    print("Result Ranker - Demo")
    print("=" * 60)

    # Mock results
    mock_results = [
        {
            'url': 'https://en.wikipedia.org/wiki/Machine_learning',
            'title': 'Machine learning - Wikipedia',
            'snippet': 'Machine learning is a branch of artificial intelligence...',
            'engine': 'GO',
            'tier': 'standard',
            'date': '2024-11-01',
        },
        {
            'url': 'https://en.wikipedia.org/wiki/Machine_learning',  # Duplicate URL
            'title': 'Machine learning - Wikipedia',
            'snippet': 'Machine learning is a branch of AI...',
            'engine': 'BI',
            'tier': 'lightning',
        },
        {
            'url': 'https://arxiv.org/abs/2311.12345',
            'title': 'Deep Machine Learning: A Survey',
            'snippet': 'This paper surveys machine learning methods...',
            'engine': 'AX',
            'tier': 'standard',
            'date': '2024-10-15',
        },
        {
            'url': 'https://example.com/ml-tutorial',
            'title': 'ML Tutorial for Beginners',
            'snippet': 'Learn about artificial intelligence and data science...',
            'engine': 'DD',
            'tier': 'lightning',
        },
        {
            'url': 'https://old-archive.com/ml-paper',
            'title': 'Historical Machine Learning Paper',
            'snippet': 'An old paper about machine learning from 1995...',
            'engine': 'LG',
            'tier': 'very_slow',
            'date': '1995-06-01',
        },
    ]

    ranker = ResultRanker()
    ranked = ranker.rank(mock_results, "machine learning")

    print(f"\nQuery: 'machine learning'")
    print(f"Results ranked: {len(ranked)}")
    print()

    for r in ranked[:5]:
        print(f"#{r.rank} [Score: {r.confidence_score:.1f}]")
        print(f"  URL: {r.url[:60]}...")
        print(f"  Title: {r.title[:50]}")
        print(f"  Engine: {r.engine} ({r.tier})")
        print(f"  Scores: tier={r.tier_score:.0f}, consensus={r.consensus_score:.0f}, "
              f"relevance={r.relevance_score:.0f}, fresh={r.freshness_score:.0f}")
        if len(r.engines_found_in) > 1:
            print(f"  Found in: {', '.join(r.engines_found_in)}")
        print()
