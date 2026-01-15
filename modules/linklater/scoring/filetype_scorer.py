"""
Filetype Credibility Scorer

Multi-signal credibility scoring incorporating filetype intelligence.
Follows the pdf_scorer.py pattern of component-based scoring.

Philosophy:
    Domains hosting structured documents (PDFs, DOCs, XLS) are more likely
    to be authoritative sources worth investigating. A company that publishes
    annual reports is more credible than a random blog linking to our target.

Scoring Components (calibrated to Linklater's 30-90 score range):
    - PDF Presence Bonus: +10-15 (based on volume)
    - Annual Report Bonus: +20 (strong institutional signal)
    - Document Diversity Bonus: +5 (professional organization)
    - Authority Score Bonus: +0-10 (based on computed authority)

Usage:
    from modules.linklater.scoring import FiletypeCredibilityScorer
    from modules.linklater.mapping.filetype_index import FiletypeProfile

    scorer = FiletypeCredibilityScorer()

    # Single domain scoring
    profile = await manager.get_profile("example.com")
    result = scorer.score(profile, base_score=45.0)
    print(f"Total: {result.total_score}, Bonus: {result.filetype_bonus}")

    # Batch scoring during discovery
    profiles = await manager.batch_lookup(domains)
    results = scorer.batch_score(domain_scores, profiles)
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional, List, Any

logger = logging.getLogger(__name__)

# Import type hint only - actual import at runtime
try:
    from ..mapping.filetype_index import FiletypeProfile
except ImportError:
    FiletypeProfile = Any  # type: ignore


@dataclass
class ScoringResult:
    """
    Result of filetype credibility scoring.

    Attributes:
        base_score: Original score before filetype adjustment
        filetype_bonus: Total bonus from filetype presence
        pdf_bonus: Bonus specifically from PDF presence
        annual_report_bonus: Bonus from annual report detection
        diversity_bonus: Bonus from document type diversity
        authority_bonus: Bonus from computed authority score
        total_score: Final score (base + all bonuses)
        explanation: Human-readable explanation
        profile_found: Whether a profile was found for this domain
    """
    base_score: float
    filetype_bonus: float
    pdf_bonus: float = 0.0
    annual_report_bonus: float = 0.0
    diversity_bonus: float = 0.0
    authority_bonus: float = 0.0
    total_score: float = 0.0
    explanation: str = ""
    profile_found: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "base_score": self.base_score,
            "filetype_bonus": self.filetype_bonus,
            "pdf_bonus": self.pdf_bonus,
            "annual_report_bonus": self.annual_report_bonus,
            "diversity_bonus": self.diversity_bonus,
            "authority_bonus": self.authority_bonus,
            "total_score": self.total_score,
            "explanation": self.explanation,
            "profile_found": self.profile_found,
        }


class FiletypeCredibilityScorer:
    """
    Score link credibility based on filetype presence.

    Bonuses are calibrated to work with Linklater's existing
    score range (30-90 typically):
    - Base scores: 35-65 from source type + trust flow
    - Keyword bonuses: +25-30
    - Site type bonuses: +5-20 (gov, news)
    - Filetype bonuses: +10-35 (this scorer)

    Final scores are capped at 100.
    """

    # Score bonuses (calibrated to existing Linklater range)
    PDF_BONUS_BASE = 10          # Has any PDFs
    PDF_BONUS_HIGH_VOLUME = 15   # Has 20+ PDFs
    PDF_BONUS_VERY_HIGH = 18     # Has 100+ PDFs

    ANNUAL_REPORT_BONUS = 20     # Has detected annual reports

    DIVERSITY_BONUS = 5          # Has 3+ filetype categories

    # Authority score bonuses (0-10 based on computed authority)
    AUTHORITY_THRESHOLDS = [
        (80, 10),  # Authority >= 80 → +10
        (60, 7),   # Authority >= 60 → +7
        (40, 5),   # Authority >= 40 → +5
        (20, 2),   # Authority >= 20 → +2
    ]

    MAX_SCORE = 100  # Cap total score

    def __init__(
        self,
        pdf_bonus_base: int = None,
        annual_report_bonus: int = None,
        max_score: int = None
    ):
        """
        Initialize scorer with optional custom bonuses.

        Args:
            pdf_bonus_base: Override base PDF bonus
            annual_report_bonus: Override annual report bonus
            max_score: Override max score cap
        """
        if pdf_bonus_base is not None:
            self.PDF_BONUS_BASE = pdf_bonus_base
        if annual_report_bonus is not None:
            self.ANNUAL_REPORT_BONUS = annual_report_bonus
        if max_score is not None:
            self.MAX_SCORE = max_score

    def score(
        self,
        profile: Optional["FiletypeProfile"],
        base_score: float = 0.0
    ) -> ScoringResult:
        """
        Calculate filetype-based credibility bonus.

        Args:
            profile: Domain's filetype profile (or None if unknown)
            base_score: Existing score from other factors

        Returns:
            ScoringResult with breakdown of all bonuses

        Example:
            profile = await manager.get_profile("investor.example.com")
            result = scorer.score(profile, base_score=55)
            # result.total_score might be 90 (55 + 15 pdf + 20 annual)
        """
        # No profile found - return base score unchanged
        if profile is None:
            return ScoringResult(
                base_score=base_score,
                filetype_bonus=0.0,
                total_score=base_score,
                explanation="No filetype data available",
                profile_found=False,
            )

        explanations = []
        pdf_bonus = 0.0
        annual_report_bonus = 0.0
        diversity_bonus = 0.0
        authority_bonus = 0.0

        # 1. PDF Presence Bonus (based on volume)
        pdf_count = profile.pdf_count
        if pdf_count > 0:
            if pdf_count >= 100:
                pdf_bonus = self.PDF_BONUS_VERY_HIGH
                explanations.append(f"Very high PDF volume ({pdf_count}): +{pdf_bonus}")
            elif pdf_count >= 20:
                pdf_bonus = self.PDF_BONUS_HIGH_VOLUME
                explanations.append(f"High PDF volume ({pdf_count}): +{pdf_bonus}")
            else:
                pdf_bonus = self.PDF_BONUS_BASE
                explanations.append(f"PDF presence ({pdf_count}): +{pdf_bonus}")

        # 2. Annual Report Bonus (strong institutional signal)
        if profile.has_annual_reports:
            annual_report_bonus = self.ANNUAL_REPORT_BONUS
            explanations.append(f"Annual reports detected: +{annual_report_bonus}")

        # 3. Document Diversity Bonus
        active_types = sum(1 for v in profile.filetypes.values() if v > 0)
        if active_types >= 3:
            diversity_bonus = self.DIVERSITY_BONUS
            explanations.append(f"Document diversity ({active_types} types): +{diversity_bonus}")

        # 4. Authority Score Bonus (from pre-computed authority)
        authority = profile.document_authority_score
        if authority > 0:
            for threshold, bonus in self.AUTHORITY_THRESHOLDS:
                if authority >= threshold:
                    authority_bonus = bonus
                    explanations.append(f"Authority score ({authority:.0f}): +{authority_bonus}")
                    break

        # Calculate totals
        filetype_bonus = pdf_bonus + annual_report_bonus + diversity_bonus + authority_bonus
        total_score = min(base_score + filetype_bonus, self.MAX_SCORE)

        return ScoringResult(
            base_score=base_score,
            filetype_bonus=filetype_bonus,
            pdf_bonus=pdf_bonus,
            annual_report_bonus=annual_report_bonus,
            diversity_bonus=diversity_bonus,
            authority_bonus=authority_bonus,
            total_score=total_score,
            explanation="; ".join(explanations) if explanations else "No filetype bonuses",
            profile_found=True,
        )

    def batch_score(
        self,
        domains_with_scores: Dict[str, float],
        profiles: Dict[str, "FiletypeProfile"]
    ) -> Dict[str, ScoringResult]:
        """
        Score multiple domains at once.

        Efficient method for scoring all linking domains during
        backlink discovery.

        Args:
            domains_with_scores: Dict mapping domain -> base score
            profiles: Dict mapping domain -> FiletypeProfile

        Returns:
            Dict mapping domain -> ScoringResult

        Example:
            # During backlink pipeline Phase 4
            base_scores = {r.source: r.score for r in results}
            profiles = await manager.batch_lookup(base_scores.keys())
            scored = scorer.batch_score(base_scores, profiles)

            for domain, result in scored.items():
                print(f"{domain}: {result.base_score} -> {result.total_score}")
        """
        results = {}
        for domain, base_score in domains_with_scores.items():
            profile = profiles.get(domain)
            results[domain] = self.score(profile, base_score)
        return results

    def get_score_breakdown(
        self,
        profile: "FiletypeProfile",
        base_score: float = 0.0
    ) -> Dict[str, Any]:
        """
        Get detailed score breakdown for debugging.

        Args:
            profile: FiletypeProfile to analyze
            base_score: Base score to start from

        Returns:
            Dict with all components and explanations
        """
        result = self.score(profile, base_score)
        return {
            "domain": profile.domain,
            "base_score": result.base_score,
            "components": {
                "pdf_bonus": result.pdf_bonus,
                "annual_report_bonus": result.annual_report_bonus,
                "diversity_bonus": result.diversity_bonus,
                "authority_bonus": result.authority_bonus,
            },
            "total_filetype_bonus": result.filetype_bonus,
            "total_score": result.total_score,
            "explanation": result.explanation,
            "profile": {
                "pdf_count": profile.pdf_count,
                "total_documents": profile.total_documents,
                "has_annual_reports": profile.has_annual_reports,
                "document_authority_score": profile.document_authority_score,
                "filetypes": profile.filetypes,
            }
        }


# Convenience function
def calculate_filetype_bonus(
    pdf_count: int = 0,
    has_annual_reports: bool = False,
    filetype_diversity: int = 1,
    authority_score: float = 0.0
) -> float:
    """
    Quick calculation of filetype bonus without full profile.

    Useful for inline calculations when you don't have a full profile.

    Args:
        pdf_count: Number of PDFs
        has_annual_reports: Whether annual reports were found
        filetype_diversity: Number of different filetype categories
        authority_score: Computed authority score (0-100)

    Returns:
        Total filetype bonus
    """
    bonus = 0.0

    # PDF bonus
    if pdf_count >= 100:
        bonus += 18
    elif pdf_count >= 20:
        bonus += 15
    elif pdf_count > 0:
        bonus += 10

    # Annual report bonus
    if has_annual_reports:
        bonus += 20

    # Diversity bonus
    if filetype_diversity >= 3:
        bonus += 5

    # Authority bonus
    if authority_score >= 80:
        bonus += 10
    elif authority_score >= 60:
        bonus += 7
    elif authority_score >= 40:
        bonus += 5
    elif authority_score >= 20:
        bonus += 2

    return bonus
