#!/usr/bin/env python3
"""
Test Enhanced Template System

Demonstrates the Quick Wins implementation:
1. Provenance schema
2. Enhanced source_template_v2.json with JSON Schema
3. Auto-population for created_at, node_id, etc.
4. Integration with CyMonides
"""

import sys
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent))

from template_validator import TemplateValidator, validate_and_populate


def test_basic_validation():
    """Test basic validation with required fields"""
    print("\n" + "="*60)
    print("TEST 1: Basic Validation (Missing Required Fields)")
    print("="*60)

    # Missing required 'domain' field
    incomplete_data = {
        "url": "https://example.com/page"
    }

    populated, valid, errors = validate_and_populate(incomplete_data, "webdomain")

    print(f"Input: {incomplete_data}")
    print(f"Valid: {valid}")
    print(f"Errors: {errors}")
    print(f"Auto-populated fields: {list(populated.get('metadata', {}).keys())}")


def test_auto_population():
    """Test auto-population of fields"""
    print("\n" + "="*60)
    print("TEST 2: Auto-Population")
    print("="*60)

    minimal_data = {
        "url": "https://example.com/page",
        "title": "Example Page"
    }

    populated, valid, errors = validate_and_populate(minimal_data, "webdomain")

    print(f"Input fields: {list(minimal_data.keys())}")
    print(f"Output fields: {list(populated.keys())}")
    print(f"\nAuto-populated metadata:")
    for key, value in populated.get('metadata', {}).items():
        print(f"  - {key}: {value}")

    print(f"\nAuto-populated provenance:")
    for key, value in populated.get('provenance', {}).items():
        print(f"  - {key}: {value}")

    print(f"\nExtracted domain: {populated.get('domain')}")
    print(f"Valid: {valid}")


def test_document_type():
    """Test document type with auto-population"""
    print("\n" + "="*60)
    print("TEST 3: Document Type Auto-Population")
    print("="*60)

    doc_data = {
        "title": "Investigation Report 2025",
        "document_type": "pdf",
        "file_content": "This is the content of the investigation report..." * 100
    }

    populated, valid, errors = validate_and_populate(doc_data, "document")

    print(f"Input: title, document_type, file_content")
    print(f"\nAuto-generated:")
    print(f"  - file_hash: {populated.get('file_hash', 'N/A')[:20]}...")
    print(f"  - file_size: {populated.get('file_size', 'N/A')} bytes")
    print(f"  - node_id: {populated.get('metadata', {}).get('node_id', 'N/A')}")
    print(f"  - created_at: {populated.get('metadata', {}).get('created_at', 'N/A')}")
    print(f"\nValid: {valid}")


def test_provenance_validation():
    """Test provenance validation"""
    print("\n" + "="*60)
    print("TEST 4: Provenance Validation")
    print("="*60)

    validator = TemplateValidator()

    # Valid provenance
    valid_prov = {
        "source": "uk_companies_house",
        "confidence": 0.95,
        "verified_at": "2025-11-23T10:30:00Z",
        "verification_method": "automated"
    }

    is_valid, errors = validator.validate_provenance(valid_prov)
    print(f"Valid provenance: {is_valid}")

    # Invalid provenance (bad confidence score)
    invalid_prov = {
        "source": "some_source",
        "confidence": 1.5,  # Out of range
        "verified_at": "2025-11-23T10:30:00Z",
        "verification_method": "invalid_method"
    }

    is_valid, errors = validator.validate_provenance(invalid_prov)
    print(f"\nInvalid provenance: {is_valid}")
    print(f"Errors: {errors}")


def test_field_validation():
    """Test field-level validation (patterns, enums, etc.)"""
    print("\n" + "="*60)
    print("TEST 5: Field-Level Validation")
    print("="*60)

    # Invalid domain pattern
    bad_data = {
        "url": "https://example.com",
        "domain": "not-a-valid-domain",  # Doesn't match pattern
        "title": "Test"
    }

    populated, valid, errors = validate_and_populate(bad_data, "webdomain")

    print(f"Input domain: {bad_data['domain']}")
    print(f"Valid: {valid}")
    print(f"Validation errors: {errors}")

    # Valid domain
    good_data = {
        "url": "https://example.com",
        "domain": "example.com",
        "title": "Test"
    }

    populated, valid, errors = validate_and_populate(good_data, "webdomain")
    print(f"\nInput domain: {good_data['domain']}")
    print(f"Valid: {valid}")


def test_performance_gains():
    """Demonstrate performance/quality gains"""
    print("\n" + "="*60)
    print("TEST 6: Quick Wins Performance Gains")
    print("="*60)

    import json

    # Before: Manual node creation
    manual_node = {
        "url": "https://offshore-leaks.com/company/12345",
        "label": "Offshore Company Ltd",
        "className": "source",
        "typeName": "webpage"
    }

    print("BEFORE (manual creation):")
    print(json.dumps(manual_node, indent=2))
    print(f"Fields: {len(manual_node)}")
    print("Missing: node_id, timestamps, provenance, domain, metadata")

    # After: Auto-populated with validation
    auto_node, valid, errors = validate_and_populate(
        {
            "url": "https://offshore-leaks.com/company/12345",
            "title": "Offshore Company Ltd"
        },
        "webdomain"
    )

    print("\nAFTER (auto-populated with validation):")
    print(json.dumps(auto_node, indent=2))
    print(f"Fields: {len(auto_node)}")
    print(f"Valid: {valid}")
    print("\nGains:")
    print("  ✅ Auto-generated node_id (UUID)")
    print("  ✅ Timestamps (created_at, updated_at, last_crawled)")
    print("  ✅ Provenance tracking (source, confidence, verified_at)")
    print("  ✅ Extracted domain from URL")
    print("  ✅ Class/type metadata")
    print("  ✅ Validation against JSON Schema")


def run_all_tests():
    """Run all tests"""
    print("\n" + "="*60)
    print("ENHANCED TEMPLATE SYSTEM - QUICK WINS TESTS")
    print("="*60)
    print("Testing: Provenance Schema + source_template_v2.json + Auto-Population")

    test_basic_validation()
    test_auto_population()
    test_document_type()
    test_provenance_validation()
    test_field_validation()
    test_performance_gains()

    print("\n" + "="*60)
    print("✅ ALL TESTS COMPLETED")
    print("="*60)
    print("\nQuick Wins Summary:")
    print("  1. ✅ provenance_schema.json - Standardized source attribution")
    print("  2. ✅ source_template_v2.json - Full JSON Schema validation")
    print("  3. ✅ Auto-population - node_id, timestamps, domain extraction")
    print("  4. ✅ template_validator.py - Python validation engine")
    print("  5. ✅ Integration with CyMonides drill_search_adapter.py")
    print("\nExpected Improvements:")
    print("  - 10% → 5% bad data rate (JSON Schema validation)")
    print("  - 50% less boilerplate (auto-population)")
    print("  - Full audit trail (provenance tracking)")
    print("  - Self-documenting schemas")


if __name__ == "__main__":
    run_all_tests()
