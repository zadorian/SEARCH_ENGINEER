"""
Ranking Module
==============
Result quality ranking with confidence scores.

Scoring formula:
- Engine Tier (40%): Results from reliable engines score higher
- Consensus (30%): URLs from multiple engines get boosted
- Relevance (20%): Query term matching in title/snippet
- Freshness (10%): Recent results score higher
"""
from .result_ranker import ResultRanker, RankedResult, rank_results

__all__ = [
    "ResultRanker",
    "RankedResult",
    "rank_results",
]
