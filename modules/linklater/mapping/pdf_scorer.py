#!/usr/bin/env python3
"""
PDF Multi-Signal Scoring Algorithm

Scores PDF candidates by likelihood of being annual reports using
multiple signals: URL patterns, file size, temporal match, path authority,
and jurisdiction matching.
"""
import re
from dataclasses import dataclass
from typing import Dict, Optional, List
from datetime import datetime
from urllib.parse import urlparse
import logging

from .jurisdiction_patterns import (
    AnnualReportPattern,
    get_pattern,
    match_url_pattern,
    extract_year_from_url,
    JURISDICTION_PATTERNS
)

logger = logging.getLogger(__name__)


@dataclass
class PDFCandidate:
    """
    Candidate PDF from Common Crawl Index.

    Attributes:
        url: PDF URL
        archive: CC archive name (e.g., 'CC-MAIN-2024-10')
        mime: MIME type (should be application/pdf)
        status: HTTP status code
        length: File size in bytes
        timestamp: ISO 8601 timestamp when crawled
        confidence_score: Computed confidence score (0-100)
        verified: Whether WAT verification passed
        metadata: Additional metadata from verification
        jurisdiction: Matched jurisdiction code
        extracted_year: Year extracted from URL
    """
    url: str
    archive: str
    mime: str
    status: int
    length: int
    timestamp: str
    confidence_score: float = 0.0
    verified: bool = False
    metadata: Optional[Dict] = None
    jurisdiction: Optional[str] = None
    extracted_year: int = 0


def has_obvious_annual_report_signals(url: str) -> bool:
    """
    Quick check: Does URL have obvious annual report signals?

    Returns True if URL contains:
    - "annual report" (or equivalent) AND/OR
    - 4-digit year AND financial terms

    Use this for fast pre-filtering before full scoring.

    Example:
        if has_obvious_annual_report_signals(url):
            score = scorer.score_candidate(candidate)
        else:
            # Skip - not worth scoring
            pass
    """
    import re
    url_lower = url.lower()

    # Check for year
    has_year = bool(re.search(r'\b(19|20)\d{2}\b', url))

    # Check for annual report terms
    annual_terms = [
        'annual-report', 'annual_report', 'annualreport',
        'årsredovisning', 'arsredovisning', 'årsrapport',
        'jahresbericht', 'rapport-annuel', 'rapportannuel',
        'relazione-annuale', 'informe-anual', 'informeanual',
        'jaarverslag', 'jaarrapport',
        '10-k', '10k', 'form-10-k'
    ]

    has_annual_term = any(term in url_lower for term in annual_terms)

    # STRONG signal: has annual report term
    if has_annual_term:
        return True

    # MEDIUM signal: has year + financial terms
    if has_year:
        financial_terms = ['financial', 'fiscal', 'investor', 'earnings', 'results', 'report']
        if any(term in url_lower for term in financial_terms):
            return True

    # Otherwise, not obvious enough
    return False


class PDFScorer:
    """
    Score PDFs by likelihood of being annual reports.

    Uses multi-signal scoring algorithm combining:
    1. URL Pattern Score (0-30): Pattern match quality
    2. File Size Score (0-20): File size in expected range
    3. Temporal Score (0-20): Year/timestamp matching
    4. Path Authority Score (0-20): URL path quality
    5. Jurisdiction Match Score (0-10): Pattern specificity

    Total possible score: 100
    Recommended threshold: 60+ for high confidence
    """

    def __init__(self, jurisdictions: List[str] = None):
        """
        Initialize scorer with jurisdiction patterns.

        Args:
            jurisdictions: List of jurisdiction codes to score against.
                          If None, uses all available jurisdictions.
        """
        if jurisdictions:
            self.patterns = {j: get_pattern(j) for j in jurisdictions}
        else:
            self.patterns = JURISDICTION_PATTERNS.copy()

    def score_candidate(
        self,
        candidate: PDFCandidate,
        target_year: Optional[int] = None
    ) -> float:
        """
        Compute composite confidence score for PDF candidate.

        Args:
            candidate: PDF candidate to score
            target_year: Optional target year to match against

        Returns:
            Total score (0-100)
        """
        total_score = 0.0

        # Try to match against each jurisdiction pattern
        best_jurisdiction = None
        best_pattern_score = 0.0

        for jurisdiction, pattern in self.patterns.items():
            # URL Pattern Score (0-30)
            pattern_score = self._score_url_pattern(candidate.url, pattern)

            if pattern_score > best_pattern_score:
                best_pattern_score = pattern_score
                best_jurisdiction = jurisdiction

        # Store matched jurisdiction
        candidate.jurisdiction = best_jurisdiction

        # URL Pattern Score (best match)
        total_score += best_pattern_score

        # File Size Score (0-20)
        if best_jurisdiction:
            pattern = self.patterns[best_jurisdiction]
            total_score += self._score_file_size(candidate.length, pattern.file_size_range)

        # Temporal Score (0-20)
        year_in_url = extract_year_from_url(candidate.url, best_jurisdiction or 'SE')
        candidate.extracted_year = year_in_url
        total_score += self._score_temporal_match(
            candidate.timestamp,
            year_in_url,
            target_year
        )

        # Path Authority Score (0-20)
        if best_jurisdiction:
            pattern = self.patterns[best_jurisdiction]
            total_score += self._score_path_authority(candidate.url, pattern)

        # Jurisdiction Match Score (0-10)
        total_score += self._score_jurisdiction_specificity(
            candidate.url,
            best_jurisdiction
        )

        candidate.confidence_score = round(total_score, 2)
        return candidate.confidence_score

    def _score_url_pattern(self, url: str, pattern: AnnualReportPattern) -> float:
        """
        Score URL pattern match quality (0-30).

        SCORING PRIORITY:
        30 = "annual report" + 4-digit year (PERFECT match)
        25 = Jurisdiction-specific term + year (e.g., "årsredovisning 2024")
        20 = "annual report" WITHOUT year (good but missing key signal)
        15 = Year present but no annual report term
        10 = Generic financial terms only
        0 = No match
        """
        url_lower = url.lower()

        # Extract 4-digit year if present
        import re
        year_match = re.search(r'\b(19|20)\d{2}\b', url)
        has_year = bool(year_match)

        # Check for "annual report" or equivalents
        # Normalize separators to catch all variants
        url_normalized = url_lower.replace('_', '-').replace(' ', '-')

        annual_report_terms = [
            'annual-report', 'annualreport',
            'årsredovisning', 'arsredovisning',
            'jahresbericht', 'rapport-annuel',
            'relazione-annuale', 'informe-anual',
            '10-k', '10k'  # US SEC filing
        ]

        has_annual_report = any(term in url_normalized for term in annual_report_terms)

        # PERFECT MATCH: "annual report" + year = 30 points
        if has_annual_report and has_year:
            return 30.0

        # VERY GOOD: Annual report without year = 20 points
        if has_annual_report and not has_year:
            return 20.0

        # DECENT: Year present but no annual report term
        # Could be "2024-financial-results.pdf" or "2023-report.pdf"
        if has_year and not has_annual_report:
            # Check for other financial/report terms
            financial_terms = ['financial', 'fiscal', 'earnings', 'results', 'report']
            if any(term in url_lower for term in financial_terms):
                # "report" + year gets slightly higher score
                if 'report' in url_lower:
                    return 18.0
                return 15.0

        # FALLBACK: Check pattern regex matches
        for regex in pattern.url_patterns:
            match = regex.search(url)
            if match:
                # If regex matched and extracted year
                if match.groups() and has_year:
                    return 25.0  # Good match via regex
                return 15.0  # Regex match but no year

        # GENERIC: Contains "report" or "pdf" with no other signals
        if 'report' in url_lower or 'financial' in url_lower:
            return 10.0

        return 0.0

    def _score_file_size(
        self,
        file_size: int,
        size_range: tuple[int, int]
    ) -> float:
        """
        Score file size appropriateness (0-20).

        20 = Within optimal range
        10 = Acceptable but outside optimal
        0 = Too small or too large
        """
        min_size, max_size = size_range

        if min_size <= file_size <= max_size:
            # Within expected range
            optimal_min = min_size * 2  # e.g., 1MB for 500KB min
            optimal_max = max_size // 2  # e.g., 25MB for 50MB max

            if optimal_min <= file_size <= optimal_max:
                return 20.0
            else:
                return 15.0

        # Too small (likely not full annual report)
        if file_size < min_size:
            # Give partial credit if within 2x threshold
            if file_size > min_size // 2:
                return 5.0
            return 0.0

        # Too large (might be invalid or combined reports)
        if file_size > max_size:
            # Give partial credit if within 2x threshold
            if file_size < max_size * 2:
                return 10.0
            return 0.0

        return 0.0

    def _score_temporal_match(
        self,
        timestamp: str,
        year_in_url: int,
        target_year: Optional[int] = None
    ) -> float:
        """
        Score temporal consistency (0-20).

        20 = Year in URL matches timestamp AND target year
        15 = Year in URL matches timestamp OR target year
        10 = Recent timestamp (last 5 years)
        5 = Older but plausible
        0 = No temporal signals
        """
        score = 0.0

        # Parse timestamp
        try:
            crawl_date = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            crawl_year = crawl_date.year
        except (ValueError, AttributeError):
            crawl_year = 0

        # Year in URL matches crawl year
        if year_in_url and crawl_year:
            # Perfect match (report from same year as crawl)
            if year_in_url == crawl_year:
                score += 10.0
            # Off by one year (common for fiscal years)
            elif abs(year_in_url - crawl_year) == 1:
                score += 8.0
            # Within 2 years (still plausible)
            elif abs(year_in_url - crawl_year) <= 2:
                score += 5.0

        # Year in URL matches target year
        if target_year and year_in_url:
            if year_in_url == target_year:
                score += 10.0
            # Off by one (fiscal year edge cases)
            elif abs(year_in_url - target_year) == 1:
                score += 7.0

        # Recent crawl (prefer fresh content)
        if crawl_year:
            current_year = datetime.now().year
            years_old = current_year - crawl_year

            if years_old <= 1:
                score += 5.0
            elif years_old <= 3:
                score += 3.0
            elif years_old <= 5:
                score += 1.0

        # If no year extracted, give minimal score for recent crawls
        if not year_in_url and crawl_year:
            current_year = datetime.now().year
            if current_year - crawl_year <= 2:
                score += 5.0

        return min(score, 20.0)  # Cap at 20

    def _score_path_authority(
        self,
        url: str,
        pattern: AnnualReportPattern
    ) -> float:
        """
        Score URL path authority (0-20).

        20 = High-authority path (/investor-relations/, etc.)
        15 = Medium-authority path (/reports/, etc.)
        10 = Generic path
        0 = Low-quality path
        """
        url_lower = url.lower()
        parsed = urlparse(url)
        path = parsed.path.lower()

        # Check high-authority patterns
        for auth_pattern in pattern.path_authority_patterns:
            if auth_pattern.search(path):
                # Exact match on high-authority path
                if any(
                    indicator in path
                    for indicator in ['investor', 'financial-information', 'sec-filing']
                ):
                    return 20.0
                # Medium-authority match
                return 15.0

        # Generic but acceptable paths
        generic_paths = ['/reports/', '/publications/', '/documents/', '/media/']
        if any(gp in path for gp in generic_paths):
            return 10.0

        # Low-quality paths (downloads, temp, etc.)
        low_quality = ['/download/', '/temp/', '/cache/', '/wp-content/uploads/']
        if any(lq in path for lq in low_quality):
            return 5.0

        return 0.0

    def _score_jurisdiction_specificity(
        self,
        url: str,
        jurisdiction: Optional[str]
    ) -> float:
        """
        Score jurisdiction pattern specificity (0-10).

        10 = Highly specific pattern (årsredovisning, 10-K)
        5 = Generic pattern (annual report)
        0 = No jurisdiction match
        """
        if not jurisdiction:
            return 0.0

        url_lower = url.lower()

        # Swedish-specific
        if jurisdiction == 'SE':
            swedish_terms = ['årsredovisning', 'arsredovisning', 'bokslutskommuniké']
            if any(term in url_lower for term in swedish_terms):
                return 10.0

        # US-specific (SEC filings)
        if jurisdiction == 'US':
            us_terms = ['10-k', '10k', 'def-14a', 'proxy']
            if any(term in url_lower for term in us_terms):
                return 10.0

        # UK-specific
        if jurisdiction == 'UK':
            uk_terms = ['annual-accounts', 'strategic-report']
            if any(term in url_lower for term in uk_terms):
                return 10.0

        # EU-specific (non-English)
        if jurisdiction == 'EU':
            eu_terms = [
                'jahresbericht', 'rapport-annuel', 'relazione-annuale',
                'informe-anual', 'jaarverslag'
            ]
            if any(term in url_lower for term in eu_terms):
                return 10.0

        # Generic match (annual report)
        if 'annual' in url_lower and 'report' in url_lower:
            return 5.0

        return 0.0

    def score_batch(
        self,
        candidates: List[PDFCandidate],
        target_year: Optional[int] = None
    ) -> List[PDFCandidate]:
        """
        Score multiple candidates and sort by confidence.

        Args:
            candidates: List of PDF candidates
            target_year: Optional target year

        Returns:
            Sorted list (highest score first)
        """
        for candidate in candidates:
            self.score_candidate(candidate, target_year)

        return sorted(candidates, key=lambda c: c.confidence_score, reverse=True)

    def filter_by_threshold(
        self,
        candidates: List[PDFCandidate],
        min_score: float = 60.0
    ) -> List[PDFCandidate]:
        """
        Filter candidates by minimum score threshold.

        Args:
            candidates: List of scored candidates
            min_score: Minimum confidence score (default: 60)

        Returns:
            Filtered list
        """
        return [c for c in candidates if c.confidence_score >= min_score]

    def get_score_breakdown(
        self,
        candidate: PDFCandidate,
        target_year: Optional[int] = None
    ) -> Dict[str, float]:
        """
        Get detailed score breakdown for debugging.

        Args:
            candidate: PDF candidate
            target_year: Optional target year

        Returns:
            Dict with component scores
        """
        breakdown = {}

        # Find best jurisdiction match
        best_jurisdiction = None
        best_pattern_score = 0.0

        for jurisdiction, pattern in self.patterns.items():
            pattern_score = self._score_url_pattern(candidate.url, pattern)
            if pattern_score > best_pattern_score:
                best_pattern_score = pattern_score
                best_jurisdiction = jurisdiction

        breakdown['url_pattern'] = best_pattern_score
        breakdown['jurisdiction'] = best_jurisdiction or 'none'

        if best_jurisdiction:
            pattern = self.patterns[best_jurisdiction]
            breakdown['file_size'] = self._score_file_size(
                candidate.length,
                pattern.file_size_range
            )
            breakdown['path_authority'] = self._score_path_authority(
                candidate.url,
                pattern
            )

        year_in_url = extract_year_from_url(candidate.url, best_jurisdiction or 'SE')
        breakdown['extracted_year'] = year_in_url
        breakdown['temporal'] = self._score_temporal_match(
            candidate.timestamp,
            year_in_url,
            target_year
        )

        breakdown['jurisdiction_specificity'] = self._score_jurisdiction_specificity(
            candidate.url,
            best_jurisdiction
        )

        breakdown['total'] = sum(
            v for k, v in breakdown.items()
            if isinstance(v, (int, float))
        )

        return breakdown
