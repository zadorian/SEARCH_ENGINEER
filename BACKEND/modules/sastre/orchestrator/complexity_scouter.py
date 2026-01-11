#!/usr/bin/env python3
"""
SASTRE Complexity Scouter - Adaptive Model Routing

Estimates task complexity to route investigations to appropriate models.
Prevents wasting Opus tokens on simple tasks and under-processing complex ones.

Complexity Signals:
- Multi-jurisdiction investigations → Higher complexity
- Sanctioned entities → Higher complexity
- Ownership tracing (UBO) → Higher complexity
- Cross-reference requirements → Medium complexity
- Single entity, known jurisdiction → Lower complexity

Model Selection:
- High complexity (>0.7) → Opus (full power)
- Medium complexity (0.4-0.7) → Sonnet (balanced)
- Low complexity (<0.4) → Haiku (fast/cheap)

Usage:
    scouter = ComplexityScouter()
    score = await scouter.score(query, routing)
    model = scouter.select_model(score)
    depth = scouter.select_depth(score)
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class ComplexityFactors:
    """Breakdown of complexity factors."""
    multi_jurisdiction: float = 0.0
    sanctioned_entity: float = 0.0
    ownership_trace: float = 0.0
    cross_reference: float = 0.0
    opaque_jurisdiction: float = 0.0
    adverse_indicators: float = 0.0
    entity_count: float = 0.0
    dead_end_count: float = 0.0
    base_score: float = 0.5

    def total(self) -> float:
        """Calculate total complexity score (0-1)."""
        score = self.base_score
        score += self.multi_jurisdiction
        score += self.sanctioned_entity
        score += self.ownership_trace
        score += self.cross_reference
        score += self.opaque_jurisdiction
        score += self.adverse_indicators
        score += self.entity_count
        score += self.dead_end_count
        return min(1.0, max(0.0, score))

    def to_dict(self) -> Dict:
        return {
            "multi_jurisdiction": self.multi_jurisdiction,
            "sanctioned_entity": self.sanctioned_entity,
            "ownership_trace": self.ownership_trace,
            "cross_reference": self.cross_reference,
            "opaque_jurisdiction": self.opaque_jurisdiction,
            "adverse_indicators": self.adverse_indicators,
            "entity_count": self.entity_count,
            "dead_end_count": self.dead_end_count,
            "base_score": self.base_score,
            "total": self.total(),
        }


class ComplexityScouter:
    """
    Estimate task complexity for adaptive model selection.

    Analyzes queries and routing results to determine:
    - Which model to use (Opus/Sonnet/Haiku)
    - How many iterations to allow
    - Whether to enable advanced features
    """

    # Complexity signal weights
    SIGNALS = {
        "multi_jurisdiction": 0.3,      # Multiple countries = complex
        "sanctioned_entity": 0.25,      # Sanctions = complex
        "ownership_trace": 0.2,         # UBO tracing = complex
        "cross_reference": 0.15,        # Director pivot = medium
        "opaque_jurisdiction": 0.2,     # BVI, Cayman, etc. = complex
        "adverse_indicators": 0.15,     # PEP, litigation = medium
        "single_entity": -0.2,          # Simple lookup = reduces
        "known_jurisdiction": -0.1,     # US/UK = reduces
    }

    # Opaque jurisdictions (known for limited disclosure)
    OPAQUE_JURISDICTIONS = {
        "bvi", "ky", "cayman", "je", "gg", "gi", "pa", "sc",
        "li", "mc", "mu", "tc", "vg", "ai", "bm"
    }

    # High-transparency jurisdictions
    TRANSPARENT_JURISDICTIONS = {
        "uk", "us", "de", "fr", "nl", "se", "dk", "no", "fi"
    }

    # Sanctioned/restricted jurisdictions
    SANCTIONED_JURISDICTIONS = {
        "ru", "by", "ir", "kp", "sy", "cu", "ve"
    }

    # Complex investigation keywords
    COMPLEX_KEYWORDS = [
        "ubo", "beneficial owner", "ultimate", "ownership chain",
        "structure", "network", "connections", "associates",
        "sanctions", "pep", "politically exposed", "enforcement",
        "fraud", "money laundering", "aml", "compliance"
    ]

    # Simple investigation keywords
    SIMPLE_KEYWORDS = [
        "basic", "quick", "standard", "kyc", "verify",
        "confirm", "check", "lookup"
    ]

    def __init__(self):
        self.factors = ComplexityFactors()

    async def score(self, query: str, routing: Dict) -> float:
        """
        Calculate complexity score for an investigation.

        Args:
            query: Natural language query
            routing: Result from EdithBridge.route_investigation()

        Returns:
            Complexity score from 0.0 to 1.0
        """
        self.factors = ComplexityFactors()
        query_lower = query.lower()

        # Check for multi-jurisdiction
        jurisdictions = routing.get("jurisdictions", [])
        if not jurisdictions:
            jur = routing.get("jurisdiction_id", "")
            if jur:
                jurisdictions = [jur]

        if len(jurisdictions) > 1:
            self.factors.multi_jurisdiction = self.SIGNALS["multi_jurisdiction"]
        elif len(jurisdictions) == 1:
            jur = jurisdictions[0].lower()
            if jur in self.TRANSPARENT_JURISDICTIONS:
                self.factors.base_score += self.SIGNALS["known_jurisdiction"]

        # Check for opaque jurisdiction
        for jur in jurisdictions:
            if jur.lower() in self.OPAQUE_JURISDICTIONS:
                self.factors.opaque_jurisdiction = self.SIGNALS["opaque_jurisdiction"]
                break

        # Check for sanctioned jurisdiction
        for jur in jurisdictions:
            if jur.lower() in self.SANCTIONED_JURISDICTIONS:
                self.factors.sanctioned_entity = self.SIGNALS["sanctioned_entity"]
                break

        # Check query for complexity keywords
        for keyword in self.COMPLEX_KEYWORDS:
            if keyword in query_lower:
                self.factors.ownership_trace = max(
                    self.factors.ownership_trace,
                    self.SIGNALS["ownership_trace"]
                )

        # Check for simple keywords (reduces complexity)
        for keyword in self.SIMPLE_KEYWORDS:
            if keyword in query_lower:
                self.factors.base_score -= 0.1
                break

        # Check dead-end warnings
        dead_ends = routing.get("dead_end_warnings", [])
        if dead_ends:
            self.factors.dead_end_count = 0.05 * len(dead_ends)

        # Check for adverse indicators in query
        adverse_terms = ["sanctions", "pep", "litigation", "fraud", "criminal"]
        for term in adverse_terms:
            if term in query_lower:
                self.factors.adverse_indicators = self.SIGNALS["adverse_indicators"]
                break

        # Check genre complexity
        genre = routing.get("genre_id", "")
        complex_genres = ["enhanced_dd", "pep_profile", "asset_trace", "m&a_deep_dive"]
        simple_genres = ["kyc", "sanctions_screening"]

        if genre in complex_genres:
            self.factors.cross_reference = self.SIGNALS["cross_reference"]
        elif genre in simple_genres:
            self.factors.base_score -= 0.1

        return self.factors.total()

    def select_model(self, score: float) -> str:
        """
        Select appropriate model based on complexity score.

        Args:
            score: Complexity score (0-1)

        Returns:
            Model identifier string
        """
        if score > 0.7:
            return "claude-opus-4-5-20251101"      # Full power for complex
        elif score > 0.4:
            return "claude-sonnet-4-5-20250929"   # Balanced for medium
        else:
            return "claude-haiku-4-5-20251001"    # Fast for simple

    def select_depth(self, score: float) -> int:
        """
        Select maximum iterations based on complexity.

        Args:
            score: Complexity score (0-1)

        Returns:
            Maximum iteration count
        """
        if score > 0.7:
            return 20   # Comprehensive investigation
        elif score > 0.4:
            return 10   # Enhanced investigation
        else:
            return 5    # Basic investigation

    def select_features(self, score: float) -> Dict[str, bool]:
        """
        Select which advanced features to enable.

        Args:
            score: Complexity score (0-1)

        Returns:
            Dict of feature flags
        """
        return {
            "enable_arbitrage": score > 0.5,       # Cross-jurisdiction intelligence
            "enable_deep_trace": score > 0.6,      # Full ownership tracing
            "enable_cross_ref": score > 0.4,       # Director pivot
            "enable_archive": score > 0.3,         # Historical searches
            "enable_parallel": score > 0.5,        # Parallel execution
            "strict_validation": score > 0.6,      # Strict QC mode
        }

    def get_recommendation(self, score: float) -> Dict:
        """
        Get full recommendation based on complexity.

        Returns model, depth, and feature recommendations.
        """
        return {
            "complexity_score": round(score, 3),
            "complexity_level": self._level_name(score),
            "model": self.select_model(score),
            "max_iterations": self.select_depth(score),
            "features": self.select_features(score),
            "factors": self.factors.to_dict(),
        }

    def _level_name(self, score: float) -> str:
        """Convert score to human-readable level."""
        if score > 0.7:
            return "high"
        elif score > 0.4:
            return "medium"
        else:
            return "low"


# Convenience function
async def assess_complexity(query: str, routing: Dict) -> Dict:
    """Quick complexity assessment."""
    scouter = ComplexityScouter()
    score = await scouter.score(query, routing)
    return scouter.get_recommendation(score)


if __name__ == "__main__":
    import asyncio
    import json

    async def demo():
        scouter = ComplexityScouter()

        # Test cases
        test_cases = [
            {
                "query": "Quick KYC check on UK company ABC Ltd",
                "routing": {"jurisdiction_id": "uk", "genre_id": "kyc", "dead_end_warnings": []}
            },
            {
                "query": "Full DD on BVI company with UBO tracing",
                "routing": {"jurisdiction_id": "bvi", "genre_id": "enhanced_dd", "dead_end_warnings": [
                    {"action": "SEARCH_SHAREHOLDERS", "reason": "BVI does not disclose"}
                ]}
            },
            {
                "query": "PEP profile on Russian businessman with sanctions check",
                "routing": {"jurisdiction_id": "ru", "genre_id": "pep_profile", "dead_end_warnings": []}
            },
        ]

        for i, test in enumerate(test_cases, 1):
            score = await scouter.score(test["query"], test["routing"])
            rec = scouter.get_recommendation(score)
            print(f"\n{'='*60}")
            print(f"Test {i}: {test['query'][:50]}...")
            print(f"{'='*60}")
            print(json.dumps(rec, indent=2))

    asyncio.run(demo())
