#!/usr/bin/env python3
"""
Test Perfect URL Matching - Demonstrate obvious signal detection

Shows how the enhanced pattern matching prioritizes URLs with:
- "annual report" (or equivalent)
- 4-digit year
"""
from __future__ import annotations

if __name__ != "__main__":
    import pytest

    pytest.skip("LINKLATER test scripts are manual/integration; run directly", allow_module_level=True)

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from modules.linklater.mapping.pdf_scorer import (
    PDFScorer,
    PDFCandidate,
    has_obvious_annual_report_signals
)
from modules.linklater.mapping.jurisdiction_patterns import get_pattern


def test_obvious_signals():
    """Test that obvious URLs are immediately recognized."""

    print("="*70)
    print("TESTING OBVIOUS ANNUAL REPORT SIGNAL DETECTION")
    print("="*70)

    test_urls = [
        # PERFECT MATCHES (should score 30/30 on URL pattern)
        ("https://sebgroup.com/investors/annual-report-2024.pdf", True, 30),
        ("https://sebgroup.com/reports/2024-annual-report.pdf", True, 30),
        ("https://sebgroup.se/arsredovisning-2024.pdf", True, 30),
        ("https://company.com/investor/annual_report_2023.pdf", True, 30),
        ("https://sec.gov/10-k-2024.pdf", True, 30),

        # GOOD MATCHES (should score 20-25)
        ("https://company.com/annual-report.pdf", True, 20),  # No year but has term
        ("https://company.de/jahresbericht-2023.pdf", True, 30),  # German

        # MEDIUM MATCHES (should score 15)
        ("https://company.com/2024-financial-results.pdf", True, 15),  # Year + financial
        ("https://company.com/investor-relations/2023-report.pdf", True, 15),

        # POOR MATCHES (should score low or 0)
        ("https://company.com/brochure.pdf", False, 0),
        ("https://company.com/product-catalog-2024.pdf", False, 0),
        ("https://company.com/press-release.pdf", False, 0),
    ]

    scorer = PDFScorer(jurisdictions=['SE', 'UK', 'US', 'EU'])
    se_pattern = get_pattern('SE')

    print("\n" + "-"*70)
    print(f"{'URL':<50} {'Obvious?':<10} {'Score':<10} {'Expected'}")
    print("-"*70)

    passed = 0
    failed = 0

    for url, should_match, expected_score in test_urls:
        # Check obvious signals
        has_obvious = has_obvious_annual_report_signals(url)

        # Score URL pattern
        url_score = scorer._score_url_pattern(url, se_pattern)

        # Determine pass/fail
        obvious_match = "✓" if has_obvious == should_match else "✗"
        score_match = "✓" if url_score >= expected_score else "✗"

        if has_obvious == should_match and url_score >= expected_score:
            passed += 1
            status = "✓"
        else:
            failed += 1
            status = "✗"

        # Truncate URL for display
        display_url = url.split('/')[-1] if len(url) > 45 else url

        print(f"{display_url:<50} {str(has_obvious):<10} {url_score:<10.1f} {expected_score} {status}")

    print("-"*70)
    print(f"\nResults: {passed}/{len(test_urls)} passed ({passed/len(test_urls)*100:.0f}%)")
    print(f"Failed: {failed}")

    return passed == len(test_urls)


def test_multi_jurisdiction():
    """Test jurisdiction-specific patterns."""

    print("\n" + "="*70)
    print("TESTING MULTI-JURISDICTION PATTERN MATCHING")
    print("="*70)

    test_cases = [
        # Swedish
        ("https://sebgroup.se/arsredovisning-2024.pdf", "SE", True),
        ("https://swedbank.se/om-swedbank/finansiell-information/arsredovisningar/2023.pdf", "SE", True),

        # UK
        ("https://barclays.com/investors/annual-report-2024.pdf", "UK", True),
        ("https://hsbc.com/investors/results-and-announcements/annual-report-and-accounts-2023.pdf", "UK", True),

        # US (10-K filings)
        ("https://sec.gov/edgar/data/320193/000032019324000123/aapl-10k-2024.pdf", "US", True),
        ("https://investor.apple.com/sec-filings/form-10-k/2024.pdf", "US", True),

        # EU Multi-language
        ("https://deutsche-bank.de/jahresbericht-2024.pdf", "EU", True),  # German
        ("https://bnpparibas.com/rapport-annuel-2024.pdf", "EU", True),  # French
        ("https://santander.com/informe-anual-2024.pdf", "EU", True),  # Spanish
    ]

    print("\n" + "-"*70)
    print(f"{'URL':<55} {'Jurisdiction':<12} {'Match?'}")
    print("-"*70)

    passed = 0
    for url, jurisdiction, should_match in test_cases:
        has_obvious = has_obvious_annual_report_signals(url)

        display_url = '/'.join(url.split('/')[-2:])
        status = "✓" if has_obvious == should_match else "✗"

        if has_obvious == should_match:
            passed += 1

        print(f"{display_url:<55} {jurisdiction:<12} {status}")

    print("-"*70)
    print(f"\nResults: {passed}/{len(test_cases)} passed ({passed/len(test_cases)*100:.0f}%)")

    return passed == len(test_cases)


def test_year_extraction():
    """Test that years are correctly extracted from URLs."""

    print("\n" + "="*70)
    print("TESTING YEAR EXTRACTION FROM URLs")
    print("="*70)

    from modules.linklater.mapping.jurisdiction_patterns import extract_year_from_url

    test_cases = [
        ("https://company.com/annual-report-2024.pdf", "SE", 2024),
        ("https://company.com/2023-annual-report.pdf", "SE", 2023),
        ("https://company.com/ar-2022.pdf", "SE", 2022),
        ("https://company.com/reports/fy2021.pdf", "SE", 2021),
        ("https://company.com/arsredovisning-2024.pdf", "SE", 2024),
        ("https://company.com/no-year-here.pdf", "SE", 0),  # No year
    ]

    print("\n" + "-"*70)
    print(f"{'URL':<50} {'Expected':<10} {'Extracted':<10} {'Status'}")
    print("-"*70)

    passed = 0
    for url, jurisdiction, expected_year in test_cases:
        extracted = extract_year_from_url(url, jurisdiction)
        status = "✓" if extracted == expected_year else "✗"

        if extracted == expected_year:
            passed += 1

        display_url = url.split('/')[-1]
        print(f"{display_url:<50} {expected_year:<10} {extracted:<10} {status}")

    print("-"*70)
    print(f"\nResults: {passed}/{len(test_cases)} passed ({passed/len(test_cases)*100:.0f}%)")

    return passed == len(test_cases)


def test_complete_scoring():
    """Test complete scoring with all signals."""

    print("\n" + "="*70)
    print("TESTING COMPLETE MULTI-SIGNAL SCORING")
    print("="*70)

    scorer = PDFScorer(jurisdictions=['SE', 'UK', 'US'])

    # Create realistic test candidates
    test_cases = [
        # PERFECT: Annual report + year + good size + recent
        PDFCandidate(
            url="https://sebgroup.com/annual-report-2024.pdf",
            archive="CC-MAIN-2024-51",
            mime="application/pdf",
            status=200,
            length=3_500_000,  # 3.5MB - ideal size
            timestamp="2024-12-01T00:00:00Z"
        ),

        # GOOD: Has term and year, decent size
        PDFCandidate(
            url="https://swedbank.se/arsredovisning-2023.pdf",
            archive="CC-MAIN-2024-10",
            mime="application/pdf",
            status=200,
            length=5_000_000,  # 5MB
            timestamp="2024-03-15T00:00:00Z"
        ),

        # MEDIUM: Has year but generic term
        PDFCandidate(
            url="https://company.com/financial-results-2024.pdf",
            archive="CC-MAIN-2024-51",
            mime="application/pdf",
            status=200,
            length=2_000_000,
            timestamp="2024-11-01T00:00:00Z"
        ),

        # POOR: No year, generic
        PDFCandidate(
            url="https://company.com/investor-presentation.pdf",
            archive="CC-MAIN-2024-51",
            mime="application/pdf",
            status=200,
            length=1_500_000,
            timestamp="2024-10-01T00:00:00Z"
        ),
    ]

    print("\n" + "-"*70)
    print(f"{'URL':<45} {'Score':<10} {'Year':<10} {'Jurisdiction'}")
    print("-"*70)

    for candidate in test_cases:
        score = scorer.score_candidate(candidate, target_year=2024)

        display_url = candidate.url.split('/')[-1]
        print(f"{display_url:<45} {score:<10.1f} {candidate.extracted_year or 'N/A':<10} {candidate.jurisdiction or 'N/A'}")

    print("-"*70)

    # Check that perfect candidate scored highest
    sorted_candidates = sorted(test_cases, key=lambda c: c.confidence_score, reverse=True)
    best = sorted_candidates[0]

    print(f"\nHighest scoring: {best.url.split('/')[-1]} ({best.confidence_score:.1f})")
    print(f"Expected: annual-report-2024.pdf should score highest")

    return best.url.endswith("annual-report-2024.pdf")


if __name__ == '__main__':
    print("\n" + "#"*70)
    print("# PERFECT URL MATCHING - ENHANCED PATTERN DETECTION")
    print("#"*70)

    results = []

    results.append(("Obvious Signals Detection", test_obvious_signals()))
    results.append(("Multi-Jurisdiction Patterns", test_multi_jurisdiction()))
    results.append(("Year Extraction", test_year_extraction()))
    results.append(("Complete Scoring", test_complete_scoring()))

    print("\n" + "="*70)
    print("FINAL RESULTS")
    print("="*70)

    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{test_name:<40} {status}")

    all_passed = all(r[1] for r in results)

    print("="*70)
    print(f"\nOverall: {'✓ ALL TESTS PASSED' if all_passed else '✗ SOME TESTS FAILED'}\n")

    sys.exit(0 if all_passed else 1)
