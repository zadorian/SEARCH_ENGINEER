#!/usr/bin/env python3
"""
Scoring Profiles for Search_Engineer Filtering System
Defines different scoring strategies for various use cases
"""

from typing import Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum


class ScoringStrategy(Enum):
    """Available scoring strategies"""
    WEIGHTED_SUM = "weighted_sum"
    MULTIPLICATIVE = "multiplicative"
    HARMONIC_MEAN = "harmonic_mean"
    MAX_SCORE = "max_score"
    HYBRID = "hybrid"


@dataclass
class ScoringProfile:
    """Profile for result scoring"""
    name: str
    description: str
    strategy: ScoringStrategy = ScoringStrategy.WEIGHTED_SUM
    
    # Factor weights (must sum to ~1.0 for weighted sum)
    factor_weights: Dict[str, float] = field(default_factory=lambda: {
        'relevance': 0.40,
        'quality': 0.25,
        'authority': 0.15,
        'freshness': 0.10,
        'completeness': 0.10
    })
    
    # Score transformations
    enable_normalization: bool = True
    enable_log_scaling: bool = False
    enable_sigmoid_transform: bool = False
    
    # Boost factors
    position_boost: bool = True
    position_decay_rate: float = 0.1
    
    domain_boost_map: Dict[str, float] = field(default_factory=dict)
    keyword_boost_map: Dict[str, float] = field(default_factory=dict)
    
    # Penalties
    duplicate_penalty: float = 0.5
    low_quality_penalty: float = 0.3
    spam_penalty: float = 0.8
    
    # Tier boundaries (scores)
    tier_boundaries: List[float] = field(default_factory=lambda: [0.8, 0.6, 0.4, 0.0])
    
    # Special handling
    special_rules: List[Dict[str, Any]] = field(default_factory=list)


# Pre-configured scoring profiles
SCORING_PROFILES = {
    'research': ScoringProfile(
        name='research',
        description='Academic and research-focused scoring',
        strategy=ScoringStrategy.WEIGHTED_SUM,
        factor_weights={
            'relevance': 0.35,
            'quality': 0.30,
            'authority': 0.20,
            'freshness': 0.05,
            'completeness': 0.10
        },
        domain_boost_map={
            '.edu': 1.2,
            '.gov': 1.15,
            'scholar.google.com': 1.3,
            'arxiv.org': 1.25,
            'pubmed.ncbi.nlm.nih.gov': 1.3,
            'ieee.org': 1.2,
            'acm.org': 1.2,
            'nature.com': 1.25,
            'science.org': 1.25
        },
        keyword_boost_map={
            'peer-reviewed': 1.2,
            'journal': 1.15,
            'conference': 1.1,
            'proceedings': 1.1,
            'abstract': 1.05,
            'methodology': 1.1,
            'results': 1.05,
            'conclusion': 1.05
        },
        enable_log_scaling=True,
        tier_boundaries=[0.85, 0.70, 0.50, 0.0]
    ),
    
    'discovery': ScoringProfile(
        name='discovery',
        description='Exploration and discovery-focused scoring',
        strategy=ScoringStrategy.HYBRID,
        factor_weights={
            'relevance': 0.25,
            'quality': 0.20,
            'authority': 0.10,
            'freshness': 0.20,
            'completeness': 0.15,
            'diversity': 0.10  # Special factor for discovery
        },
        enable_sigmoid_transform=True,
        position_boost=False,  # Don't penalize lower positions
        tier_boundaries=[0.75, 0.55, 0.35, 0.0],
        special_rules=[
            {
                'name': 'diversity_bonus',
                'condition': 'unique_domain',
                'bonus': 0.1
            },
            {
                'name': 'niche_content',
                'condition': 'low_popularity',
                'bonus': 0.15
            }
        ]
    ),
    
    'verification': ScoringProfile(
        name='verification',
        description='Fact-checking and verification scoring',
        strategy=ScoringStrategy.MULTIPLICATIVE,
        factor_weights={
            'relevance': 0.30,
            'quality': 0.25,
            'authority': 0.30,
            'freshness': 0.10,
            'completeness': 0.05
        },
        domain_boost_map={
            '.gov': 1.3,
            '.edu': 1.2,
            'snopes.com': 1.25,
            'factcheck.org': 1.25,
            'politifact.com': 1.2,
            'reuters.com': 1.15,
            'apnews.com': 1.15,
            'bbc.com': 1.1,
            'wikipedia.org': 1.05
        },
        spam_penalty=0.9,  # Heavy penalty for spam
        tier_boundaries=[0.90, 0.75, 0.55, 0.0]
    ),
    
    'commercial': ScoringProfile(
        name='commercial',
        description='Commercial and business-focused scoring',
        strategy=ScoringStrategy.WEIGHTED_SUM,
        factor_weights={
            'relevance': 0.45,
            'quality': 0.20,
            'authority': 0.15,
            'freshness': 0.15,
            'completeness': 0.05
        },
        domain_boost_map={
            'amazon.com': 0.9,  # Slight penalty for commercial bias
            'ebay.com': 0.9,
            'alibaba.com': 0.9
        },
        keyword_boost_map={
            'review': 1.1,
            'comparison': 1.15,
            'best': 1.05,
            'top': 1.05,
            'guide': 1.1
        },
        position_boost=True,
        position_decay_rate=0.15  # Stronger decay for commercial
    ),
    
    'technical': ScoringProfile(
        name='technical',
        description='Technical documentation and code scoring',
        strategy=ScoringStrategy.WEIGHTED_SUM,
        factor_weights={
            'relevance': 0.40,
            'quality': 0.20,
            'authority': 0.15,
            'freshness': 0.10,
            'completeness': 0.15
        },
        domain_boost_map={
            'github.com': 1.2,
            'gitlab.com': 1.15,
            'stackoverflow.com': 1.2,
            'docs.python.org': 1.25,
            'developer.mozilla.org': 1.25,
            'docs.microsoft.com': 1.15,
            'aws.amazon.com/documentation': 1.2
        },
        keyword_boost_map={
            'documentation': 1.15,
            'api': 1.1,
            'tutorial': 1.1,
            'example': 1.1,
            'implementation': 1.05,
            'specification': 1.15,
            'reference': 1.1
        },
        tier_boundaries=[0.80, 0.65, 0.45, 0.0]
    ),
    
    'news': ScoringProfile(
        name='news',
        description='News and current events scoring',
        strategy=ScoringStrategy.WEIGHTED_SUM,
        factor_weights={
            'relevance': 0.35,
            'quality': 0.20,
            'authority': 0.20,
            'freshness': 0.25  # High weight on recency
        },
        domain_boost_map={
            'reuters.com': 1.2,
            'apnews.com': 1.2,
            'bbc.com': 1.15,
            'cnn.com': 1.1,
            'nytimes.com': 1.15,
            'wsj.com': 1.15,
            'theguardian.com': 1.1,
            'bloomberg.com': 1.15
        },
        enable_sigmoid_transform=True,
        position_decay_rate=0.05,  # Less decay for news
        special_rules=[
            {
                'name': 'breaking_news',
                'condition': 'age_hours < 2',
                'bonus': 0.2
            },
            {
                'name': 'dated_news',
                'condition': 'age_days > 30',
                'penalty': 0.3
            }
        ]
    ),
    
    'local': ScoringProfile(
        name='local',
        description='Local and geographic-focused scoring',
        strategy=ScoringStrategy.WEIGHTED_SUM,
        factor_weights={
            'relevance': 0.30,
            'quality': 0.15,
            'authority': 0.10,
            'freshness': 0.15,
            'completeness': 0.10,
            'geographic': 0.20  # Special geographic factor
        },
        domain_boost_map={
            '.local': 1.1,
            'yelp.com': 1.05,
            'tripadvisor.com': 1.05,
            'maps.google.com': 1.1
        },
        tier_boundaries=[0.75, 0.60, 0.40, 0.0]
    )
}


class ScoringCalculator:
    """Calculate scores based on profiles"""
    
    @staticmethod
    def calculate_weighted_sum(scores: Dict[str, float], 
                             weights: Dict[str, float]) -> float:
        """Calculate weighted sum of scores"""
        total = 0.0
        for factor, weight in weights.items():
            if factor in scores:
                total += scores[factor] * weight
        return min(1.0, total)  # Cap at 1.0
    
    @staticmethod
    def calculate_multiplicative(scores: Dict[str, float],
                                weights: Dict[str, float]) -> float:
        """Calculate multiplicative score"""
        result = 1.0
        for factor, weight in weights.items():
            if factor in scores:
                # Apply weight as exponent
                result *= pow(scores[factor], weight)
        return result
    
    @staticmethod
    def calculate_harmonic_mean(scores: Dict[str, float],
                               weights: Dict[str, float]) -> float:
        """Calculate weighted harmonic mean"""
        numerator = sum(weights.values())
        denominator = 0.0
        
        for factor, weight in weights.items():
            if factor in scores and scores[factor] > 0:
                denominator += weight / scores[factor]
            else:
                return 0.0  # If any score is 0, harmonic mean is 0
        
        return numerator / denominator if denominator > 0 else 0.0
    
    @staticmethod
    def calculate_max_score(scores: Dict[str, float],
                          weights: Dict[str, float]) -> float:
        """Return the maximum weighted score"""
        max_score = 0.0
        for factor, weight in weights.items():
            if factor in scores:
                max_score = max(max_score, scores[factor] * weight)
        return max_score
    
    @staticmethod
    def apply_transformations(score: float, profile: ScoringProfile) -> float:
        """Apply score transformations"""
        if profile.enable_normalization:
            # Already normalized to 0-1
            pass
        
        if profile.enable_log_scaling:
            # Log scaling (assumes score is 0-1)
            import math
            if score > 0:
                score = (math.log(score + 1) / math.log(2))
        
        if profile.enable_sigmoid_transform:
            # Sigmoid transformation for S-curve
            import math
            score = 1 / (1 + math.exp(-10 * (score - 0.5)))
        
        return max(0.0, min(1.0, score))  # Ensure 0-1 range
    
    @staticmethod
    def apply_boosts_and_penalties(score: float,
                                  result: Dict[str, Any],
                                  profile: ScoringProfile) -> float:
        """Apply boosts and penalties to score"""
        # Position boost
        if profile.position_boost and 'rank' in result:
            position_factor = 1.0 - (profile.position_decay_rate * (result['rank'] - 1))
            score *= max(0.5, position_factor)  # Don't go below 0.5
        
        # Domain boost
        domain = result.get('domain', '')
        for boost_domain, boost_factor in profile.domain_boost_map.items():
            if boost_domain in domain:
                score *= boost_factor
                break
        
        # Keyword boost
        text = f"{result.get('title', '')} {result.get('snippet', '')}".lower()
        for keyword, boost_factor in profile.keyword_boost_map.items():
            if keyword in text:
                score *= boost_factor
        
        # Apply penalties
        if result.get('is_duplicate'):
            score *= (1.0 - profile.duplicate_penalty)
        
        if result.get('quality_score', 1.0) < 0.3:
            score *= (1.0 - profile.low_quality_penalty)
        
        if result.get('spam_score', 0.0) > 0.7:
            score *= (1.0 - profile.spam_penalty)
        
        # Apply special rules
        for rule in profile.special_rules:
            if ScoringCalculator._evaluate_rule(rule, result):
                if 'bonus' in rule:
                    score += rule['bonus']
                elif 'penalty' in rule:
                    score -= rule['penalty']
        
        return max(0.0, min(1.0, score))
    
    @staticmethod
    def _evaluate_rule(rule: Dict[str, Any], result: Dict[str, Any]) -> bool:
        """Evaluate if a special rule applies"""
        condition = rule.get('condition', '')
        
        # Simple condition parsing (extend as needed)
        if 'age_hours' in condition:
            # Extract age comparison
            import re
            match = re.search(r'age_hours\s*([<>=]+)\s*(\d+)', condition)
            if match and 'timestamp' in result:
                # Implement age calculation
                return False  # Placeholder
        
        elif condition == 'unique_domain':
            # Check if domain is unique in result set
            return result.get('is_unique_domain', False)
        
        elif condition == 'low_popularity':
            # Check popularity metrics
            return result.get('popularity_score', 0.5) < 0.3
        
        return False


def calculate_score(result: Dict[str, Any],
                   factor_scores: Dict[str, float],
                   profile: ScoringProfile) -> float:
    """
    Calculate final score for a result using a scoring profile
    
    Args:
        result: Search result with metadata
        factor_scores: Individual factor scores (0-1 range)
        profile: Scoring profile to use
        
    Returns:
        Final score (0-1 range)
    """
    calculator = ScoringCalculator()
    
    # Calculate base score based on strategy
    if profile.strategy == ScoringStrategy.WEIGHTED_SUM:
        base_score = calculator.calculate_weighted_sum(
            factor_scores, profile.factor_weights
        )
    elif profile.strategy == ScoringStrategy.MULTIPLICATIVE:
        base_score = calculator.calculate_multiplicative(
            factor_scores, profile.factor_weights
        )
    elif profile.strategy == ScoringStrategy.HARMONIC_MEAN:
        base_score = calculator.calculate_harmonic_mean(
            factor_scores, profile.factor_weights
        )
    elif profile.strategy == ScoringStrategy.MAX_SCORE:
        base_score = calculator.calculate_max_score(
            factor_scores, profile.factor_weights
        )
    else:  # HYBRID
        # Combine multiple strategies
        ws = calculator.calculate_weighted_sum(factor_scores, profile.factor_weights)
        hm = calculator.calculate_harmonic_mean(factor_scores, profile.factor_weights)
        base_score = 0.7 * ws + 0.3 * hm
    
    # Apply transformations
    transformed_score = calculator.apply_transformations(base_score, profile)
    
    # Apply boosts and penalties
    final_score = calculator.apply_boosts_and_penalties(
        transformed_score, result, profile
    )
    
    return final_score


def get_tier_from_score(score: float, profile: ScoringProfile) -> int:
    """Get tier (1-4) from score based on profile boundaries"""
    for tier, boundary in enumerate(profile.tier_boundaries, 1):
        if score >= boundary:
            return tier
    return 4  # Lowest tier


def get_scoring_profile(name: str) -> ScoringProfile:
    """Get a scoring profile by name"""
    return SCORING_PROFILES.get(name, SCORING_PROFILES['research'])