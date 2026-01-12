#!/usr/bin/env python3
"""
Test CC PDF Discovery for Swedish Banks

Tests the PDF discovery pipeline with real Common Crawl queries
for Swedish banks (SEB, Swedbank, Handelsbanken, Nordea).
"""
from __future__ import annotations

if __name__ != "__main__":
    import pytest

    pytest.skip("LINKLATER test scripts are manual/integration; run directly", allow_module_level=True)

import asyncio
import sys
import logging
from pathlib import Path

# Add python-backend directory to path
backend_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(backend_dir))

from modules.linklater.archives.cc_index_client import CCIndexClient
from modules.linklater.mapping.cc_pdf_discovery import CCPDFDiscovery

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Swedish banks to test
TEST_BANKS = {
    'SEB': ['sebgroup.com', 'seb.se'],
    'Swedbank': ['swedbank.com', 'swedbank.se'],
    'Handelsbanken': ['handelsbanken.com', 'handelsbanken.se'],
    'Nordea': ['nordea.com', 'nordea.se'],
}


async def test_single_domain(domain: str, years: list[int] = None):
    """Test PDF discovery for a single domain."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Testing: {domain}")
    logger.info(f"{'='*60}")

    if years is None:
        years = [2024, 2023, 2022]

    # Initialize clients
    cc_client = CCIndexClient(timeout=30)
    discovery = CCPDFDiscovery(
        cc_index_client=cc_client,
        jurisdictions=['SE', 'UK', 'US', 'EU']
    )

    try:
        # Discover annual reports
        candidates = await discovery.discover_annual_reports(
            domain=domain,
            years=years,
            archives=[
                "CC-MAIN-2024-51",  # Recent
                "CC-MAIN-2024-46",
                "CC-MAIN-2024-10",  # Q1 2024
                "CC-MAIN-2023-50",  # Q4 2023
                "CC-MAIN-2023-14",  # Q1 2023
            ],
            verify=False,  # Skip WAT verification for now
            min_score=50.0,  # Lower threshold for testing
            max_results=20
        )

        logger.info(f"\n{'─'*60}")
        logger.info(f"Results for {domain}:")
        logger.info(f"{'─'*60}")
        logger.info(f"Found {len(candidates)} candidates\n")

        if candidates:
            for i, candidate in enumerate(candidates[:10], 1):
                logger.info(
                    f"{i:2d}. [{candidate.confidence_score:5.1f}] "
                    f"{candidate.jurisdiction or 'N/A':3s} | "
                    f"{candidate.extracted_year or '????'} | "
                    f"{candidate.length/1024/1024:6.2f}MB | "
                    f"{candidate.url}"
                )

            # Detailed breakdown for top candidate
            if candidates:
                logger.info(f"\n{'─'*60}")
                logger.info("Score breakdown for top candidate:")
                logger.info(f"{'─'*60}")
                breakdown = discovery.get_score_breakdown(candidates[0], target_year=2024)
                for key, value in breakdown.items():
                    logger.info(f"  {key:25s}: {value}")

        else:
            logger.warning(f"No candidates found for {domain}")

    finally:
        await cc_client.close()


async def test_all_banks():
    """Test PDF discovery for all Swedish banks."""
    logger.info(f"\n{'#'*60}")
    logger.info("Testing PDF Discovery for Swedish Banks")
    logger.info(f"{'#'*60}\n")

    results = {}

    for bank_name, domains in TEST_BANKS.items():
        logger.info(f"\nTesting {bank_name}...")
        bank_results = []

        for domain in domains:
            try:
                cc_client = CCIndexClient(timeout=30)
                discovery = CCPDFDiscovery(
                    cc_index_client=cc_client,
                    jurisdictions=['SE', 'UK']  # Swedish + English
                )

                candidates = await discovery.discover_annual_reports(
                    domain=domain,
                    years=[2024, 2023],
                    archives=["CC-MAIN-2024-51", "CC-MAIN-2024-10"],
                    verify=False,
                    min_score=50.0,
                    max_results=5
                )

                bank_results.extend(candidates)
                await cc_client.close()

            except Exception as e:
                logger.error(f"Error testing {domain}: {e}")

        results[bank_name] = bank_results

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("Summary")
    logger.info(f"{'='*60}")

    for bank_name, candidates in results.items():
        logger.info(
            f"{bank_name:15s}: {len(candidates):2d} candidates "
            f"(avg score: {sum(c.confidence_score for c in candidates)/len(candidates) if candidates else 0:.1f})"
        )

    total = sum(len(c) for c in results.values())
    logger.info(f"\nTotal candidates found: {total}")


async def test_streaming():
    """Test streaming discovery mode."""
    logger.info(f"\n{'='*60}")
    logger.info("Testing Streaming Discovery")
    logger.info(f"{'='*60}\n")

    cc_client = CCIndexClient(timeout=30)
    discovery = CCPDFDiscovery(
        cc_index_client=cc_client,
        jurisdictions=['SE']
    )

    try:
        logger.info("Streaming results for sebgroup.com...")
        count = 0

        async for candidate in discovery.discover_with_streaming(
            domain='sebgroup.com',
            years=[2024],
            archives=["CC-MAIN-2024-51", "CC-MAIN-2024-46"],
            min_score=50.0
        ):
            count += 1
            logger.info(
                f"  {count}. [{candidate.confidence_score:5.1f}] {candidate.url}"
            )

        logger.info(f"\nStreamed {count} candidates")

    finally:
        await cc_client.close()


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == 'all':
            asyncio.run(test_all_banks())
        elif sys.argv[1] == 'stream':
            asyncio.run(test_streaming())
        else:
            # Test specific domain
            domain = sys.argv[1]
            years = [int(y) for y in sys.argv[2:]] if len(sys.argv) > 2 else [2024, 2023]
            asyncio.run(test_single_domain(domain, years))
    else:
        # Default: test SEB
        asyncio.run(test_single_domain('sebgroup.com', [2024, 2023, 2022]))
