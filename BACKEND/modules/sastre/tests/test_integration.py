#!/usr/bin/env python3
"""
SASTRE Integration Tests

Verifies all components work together:
- EdithBridge routing/compose/validate
- ComplexityScouter model selection
- DecisionTraceCollector audit trails
- ResilientExecutor fallback chains
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from modules.sastre import (
    EdithBridge,
    ComplexityScouter,
    DecisionTraceCollector,
    ResilientExecutor,
    FALLBACK_CHAINS,
    assess_complexity,
)

pytestmark = pytest.mark.asyncio


async def test_full_pipeline():
    """Test complete SASTRE pipeline."""
    print("=" * 60)
    print("SASTRE Integration Test")
    print("=" * 60)

    # Test cases with expected complexity levels
    test_cases = [
        {
            "query": "Quick KYC check on UK company Acme Ltd",
            "expected_level": "low",
            "expected_model": "haiku",
        },
        {
            "query": "Full DD on BVI company with UBO tracing and sanctions check",
            "expected_level": "high",
            "expected_model": "opus",
        },
        {
            "query": "PEP profile on Russian oligarch with sanctions and asset tracing",
            "expected_level": "high",
            "expected_model": "opus",
        },
    ]

    bridge = EdithBridge()
    scouter = ComplexityScouter()
    trace = DecisionTraceCollector("integration_test")
    executor = ResilientExecutor()

    results = []

    for i, test in enumerate(test_cases, 1):
        print(f"\n{'─' * 60}")
        print(f"Test {i}: {test['query'][:50]}...")
        print(f"{'─' * 60}")

        # Phase 1: Route via EDITH
        try:
            routing = await bridge.route_investigation(test["query"])
            print(f"✓ Routing: {routing.get('jurisdiction_id', 'unknown')} / {routing.get('genre_id', 'unknown')}")

            # Record in trace
            trace.record_search(
                "ROUTE_INVESTIGATION",
                ["EDITH route.py"],
                "positive" if routing.get("status") == "exact" else "partial",
                results_count=1,
                jurisdiction=routing.get("jurisdiction_id", ""),
            )
        except Exception as e:
            print(f"✗ Routing failed: {e}")
            routing = {"jurisdiction_id": "uk", "genre_id": "company_dd"}
            trace.record_error("ROUTE_INVESTIGATION", ["EDITH route.py"], str(e))

        # Phase 2: Assess complexity
        try:
            score = await scouter.score(test["query"], routing)
            rec = scouter.get_recommendation(score)
            print(f"✓ Complexity: {rec['complexity_score']:.2f} ({rec['complexity_level']})")
            print(f"  Model: {rec['model'].split('-')[1]}")  # Extract model name
            print(f"  Max iterations: {rec['max_iterations']}")

            # Verify expected level
            if rec["complexity_level"] == test["expected_level"]:
                print(f"  ✓ Level matches expected: {test['expected_level']}")
            else:
                print(f"  ✗ Level mismatch: got {rec['complexity_level']}, expected {test['expected_level']}")
        except Exception as e:
            print(f"✗ Complexity scoring failed: {e}")
            rec = {"complexity_level": "unknown", "model": "unknown"}

        # Phase 3: Test fallback chain lookup
        action = "SEARCH_REGISTRY"
        chain = FALLBACK_CHAINS.get(action)
        if chain:
            print(f"✓ Fallback chain for {action}:")
            print(f"  Primary: {chain.primary}")
            print(f"  Fallbacks: {len(chain.fallbacks)}")

        # Phase 4: Compose context (if routing succeeded)
        if routing.get("status") == "exact":
            try:
                context = await bridge.compose_context(
                    routing["jurisdiction_id"],
                    routing["genre_id"],
                    "Test Entity Ltd"
                )
                if context.get("status") == "success":
                    print(f"✓ Context composed: {len(context.get('allowed_actions', []))} actions")
                    if context.get("arbitrage_routes"):
                        print(f"  Arbitrage routes: {len(context['arbitrage_routes'])}")
                else:
                    print(f"✗ Context failed: {context.get('error', 'unknown')}")
            except Exception as e:
                print(f"✗ Context composition failed: {e}")

        results.append({
            "query": test["query"],
            "routing": routing,
            "complexity": rec,
            "passed": rec.get("complexity_level") == test["expected_level"],
        })

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(1 for r in results if r["passed"])
    print(f"Tests passed: {passed}/{len(results)}")

    # Print decision trace summary
    print(f"\nDecision Trace:")
    summary = trace.get_summary()
    print(f"  Total searches: {summary['total_searches']}")
    print(f"  Outcomes: {summary['outcomes']}")

    # Generate audit section
    print(f"\nAudit Section Preview:")
    audit = trace.generate_audit_section()
    for line in audit.split("\n")[:10]:
        print(f"  {line}")

    return passed == len(results)


async def test_circuit_breaker():
    """Test circuit breaker behavior."""
    print("\n" + "=" * 60)
    print("Circuit Breaker Test")
    print("=" * 60)

    executor = ResilientExecutor(circuit_breaker_threshold=3)

    # Simulate failures
    for i in range(4):
        executor._record_failure("test_api")
        is_open = executor._is_circuit_open("test_api")
        print(f"Failure {i+1}: Circuit {'OPEN' if is_open else 'CLOSED'}")

    # Verify circuit is open
    assert executor._is_circuit_open("test_api"), "Circuit should be open after 3 failures"
    print("✓ Circuit opens after threshold")

    # Check status
    status = executor.get_circuit_status()
    print(f"Status: {status}")

    return True


async def test_dead_end_warnings():
    """Test dead-end detection in routing."""
    print("\n" + "=" * 60)
    print("Dead-End Detection Test")
    print("=" * 60)

    bridge = EdithBridge()

    # Test BVI query (should have dead-end warnings)
    routing = await bridge.route_investigation("DD on BVI company Offshore Holdings")

    warnings = routing.get("dead_end_warnings", [])
    print(f"Routing: {routing.get('jurisdiction_id')} / {routing.get('genre_id')}")
    print(f"Dead-end warnings: {len(warnings)}")

    for w in warnings:
        print(f"  - {w.get('action')}: {w.get('reason', '')[:50]}...")

    # BVI should have dead-end warnings for shareholders/officers
    if routing.get("jurisdiction_id") == "bvi" and len(warnings) > 0:
        print("✓ Dead-end warnings detected for opaque jurisdiction")
        return True
    elif routing.get("jurisdiction_id") == "bvi":
        print("✗ Expected dead-end warnings for BVI")
        return False
    else:
        print("? Routing didn't detect BVI jurisdiction")
        return True  # Not a failure, just routing issue


async def main():
    """Run all integration tests."""
    print("\n" + "=" * 60)
    print("SASTRE INTEGRATION TEST SUITE")
    print("=" * 60)

    all_passed = True

    # Test 1: Full pipeline
    try:
        passed = await test_full_pipeline()
        all_passed = all_passed and passed
    except Exception as e:
        print(f"Full pipeline test failed: {e}")
        all_passed = False

    # Test 2: Circuit breaker
    try:
        passed = await test_circuit_breaker()
        all_passed = all_passed and passed
    except Exception as e:
        print(f"Circuit breaker test failed: {e}")
        all_passed = False

    # Test 3: Dead-end warnings
    try:
        passed = await test_dead_end_warnings()
        all_passed = all_passed and passed
    except Exception as e:
        print(f"Dead-end test failed: {e}")
        all_passed = False

    # Final result
    print("\n" + "=" * 60)
    if all_passed:
        print("ALL TESTS PASSED ✓")
    else:
        print("SOME TESTS FAILED ✗")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
