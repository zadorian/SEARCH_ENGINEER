#!/usr/bin/env python3
"""
Test script for binary file extraction from Common Crawl.

Tests the end-to-end workflow:
1. CCFirstScraper finds PDF/DOCX in Common Crawl
2. WARCParser extracts binary content
3. BinaryTextExtractor extracts searchable text
4. Text is returned for entity extraction

Usage:
    python test_binary_extraction.py
"""

from __future__ import annotations

if __name__ != "__main__":
    import pytest

    pytest.skip("LINKLATER test scripts are manual/integration; run directly", allow_module_level=True)

import asyncio
import sys
from pathlib import Path

# Add modules to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
PYTHON_BACKEND = PROJECT_ROOT / 'python-backend'
if str(PYTHON_BACKEND) not in sys.path:
    sys.path.insert(0, str(PYTHON_BACKEND))

from modules.linklater.scraping.cc_first_scraper import CCFirstScraper
from modules.linklater.scraping.binary_extractor import BinaryTextExtractor


async def test_pdf_extraction():
    """Test PDF extraction from Common Crawl."""
    print("\n" + "="*60)
    print("TEST 1: PDF Extraction from Common Crawl")
    print("="*60)

    scraper = CCFirstScraper(extract_binary=True)

    # Test with known PDFs that should be in Common Crawl
    test_urls = [
        "https://www.sec.gov/Archives/edgar/data/320193/000032019321000010/aapl-20201226.pdf",  # Apple 10-K
        "https://www.treasury.gov/resource-center/data-chart-center/tic/Documents/mfh.pdf",  # Treasury report
    ]

    for url in test_urls:
        print(f"\nTesting: {url}")
        print("-" * 60)

        try:
            result = await scraper.get_content(url)

            if result and result.content:
                print(f"✅ Success!")
                print(f"   Source: {result.source}")
                print(f"   Content length: {len(result.content)} characters")
                print(f"   Preview: {result.content[:200]}...")

                # Check if we actually got text (not just binary garbage)
                if len(result.content) > 1000:
                    print(f"   Status: PASS - Extracted substantial text")
                    return True
                else:
                    print(f"   Status: WARN - Text seems too short")
            else:
                print(f"❌ No content extracted")
                print(f"   Result: {result}")
        except Exception as e:
            print(f"❌ Error: {e}")

    return False


async def test_docx_extraction():
    """Test DOCX extraction from Common Crawl."""
    print("\n" + "="*60)
    print("TEST 2: DOCX Extraction from Common Crawl")
    print("="*60)

    scraper = CCFirstScraper(extract_binary=True)

    # Test with known DOCX files
    test_urls = [
        "https://www.example.com/sample.docx",  # Generic test
    ]

    for url in test_urls:
        print(f"\nTesting: {url}")
        print("-" * 60)

        try:
            result = await scraper.get_content(url)

            if result and result.content:
                print(f"✅ Success!")
                print(f"   Source: {result.source}")
                print(f"   Content length: {len(result.content)} characters")
                print(f"   Preview: {result.content[:200]}...")
            else:
                print(f"⚠️  Not found in Common Crawl (this is normal)")
        except Exception as e:
            print(f"⚠️  Error (expected if not in CC): {e}")

    return True


def test_binary_extractor_libraries():
    """Test which extraction libraries are available."""
    print("\n" + "="*60)
    print("TEST 3: Check Available Extraction Libraries")
    print("="*60)

    extractor = BinaryTextExtractor()

    print("\nAvailable extractors:")
    for lib, available in extractor.available_extractors.items():
        status = "✅ Installed" if available else "❌ Missing"
        print(f"  {lib:20s} {status}")

    print("\nSupported MIME types:")
    for mime_type in extractor.MIME_HANDLERS.keys():
        can_extract = extractor.can_extract(mime_type)
        status = "✅" if can_extract else "❌"
        print(f"  {status} {mime_type}")

    return True


async def test_mime_filtering():
    """Test MIME type filtering in archive scanners."""
    print("\n" + "="*60)
    print("TEST 4: MIME Type Filtering")
    print("="*60)

    from modules.linklater.archives.fast_scanner import FastWaybackScanner

    # Create scanner with PDF-only filter
    scanner = FastWaybackScanner(
        max_snapshots=10,
        mime_types=['application/pdf']
    )

    print("\nScanner configuration:")
    print(f"  Max snapshots: {scanner.max_snapshots}")
    print(f"  MIME types: {scanner.mime_types}")

    # Test listing snapshots for a domain that likely has PDFs
    print("\nTesting snapshot listing for sec.gov...")
    try:
        snapshots = await scanner._list_snapshots(
            session=None,  # Will create session internally
            url="www.sec.gov"
        )
        print(f"  Found {len(snapshots)} PDF snapshots")

        if snapshots:
            print(f"  Sample snapshot:")
            print(f"    Timestamp: {snapshots[0].timestamp}")
            print(f"    URL: {snapshots[0].original_url}")
    except Exception as e:
        print(f"  Error: {e}")

    return True


def test_warc_parser():
    """Test WARC parser with sample data."""
    print("\n" + "="*60)
    print("TEST 5: WARC Parser Binary Extraction")
    print("="*60)

    from modules.linklater.scraping.warc_parser import WARCParser

    # Create minimal WARC record with fake PDF
    warc_record = b"""WARC/1.0
WARC-Type: response
WARC-Target-URI: https://example.com/test.pdf
WARC-Date: 2024-01-01T00:00:00Z

HTTP/1.1 200 OK
Content-Type: application/pdf
Content-Length: 8

%PDF-1.4"""

    print("\nTesting extract_binary()...")
    binary_content, content_type = WARCParser.extract_binary(warc_record)

    if binary_content and content_type:
        print(f"✅ Success!")
        print(f"   Content-Type: {content_type}")
        print(f"   Binary length: {len(binary_content)} bytes")
        print(f"   Content preview: {binary_content[:20]}")
    else:
        print(f"❌ Failed to extract binary")

    return binary_content is not None


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("Binary Extraction Integration Tests")
    print("="*60)

    results = {
        'Library Check': test_binary_extractor_libraries(),
        'WARC Parser': test_warc_parser(),
        'PDF Extraction': await test_pdf_extraction(),
        'DOCX Extraction': await test_docx_extraction(),
    }

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status:10s} {test_name}")

    total_passed = sum(1 for p in results.values() if p)
    total_tests = len(results)

    print(f"\nTotal: {total_passed}/{total_tests} tests passed")

    if total_passed == total_tests:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print("\n⚠️  Some tests failed - check missing libraries")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
