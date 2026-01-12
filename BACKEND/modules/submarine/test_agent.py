#!/usr/bin/env python3
"""
Test script for SUBMARINE agent

Runs basic functionality tests without requiring live API calls.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from SUBMARINE.agent import SubmarineAgent, MissionResult


def test_result_creation():
    """Test MissionResult dataclass creation."""
    print("✓ Testing MissionResult creation...")

    result = MissionResult(
        query="Test mission",
        pages_fetched=50,
        entities_extracted=[{"type": "email", "value": "test@test.com"}],
        domains_covered=["test.com"],
        confidence_score=0.9,
        sources=["TEST"]
    )

    assert result.query == "Test mission"
    assert result.pages_fetched == 50
    assert len(result.entities_extracted) == 1
    assert result.confidence_score == 0.9

    # Test to_dict
    result_dict = result.to_dict()
    assert isinstance(result_dict, dict)
    assert result_dict["query"] == "Test mission"

    print("  ✓ MissionResult creation works")
    return True


def test_agent_initialization():
    """Test SubmarineAgent initialization."""
    print("✓ Testing SubmarineAgent initialization...")

    agent = SubmarineAgent()

    # Check options are set
    assert agent.options is not None
    assert agent.options.system_prompt is not None
    assert "SUBMARINE" in agent.options.system_prompt
    assert "You are SUBMARINE" in agent.options.system_prompt

    # Check subagents are configured
    assert agent.options.agents is not None
    assert "jester" in agent.options.agents
    assert "backdrill" in agent.options.agents
    assert "explorer" in agent.options.agents
    assert "darkweb" in agent.options.agents

    # Check MCP servers are configured
    assert agent.options.mcp_servers is not None
    assert "submarine" in agent.options.mcp_servers

    # Check no direct tools (delegation only)
    assert agent.options.allowed_tools == []

    print("  ✓ Agent initialization works")
    print(f"  ✓ Subagents configured: {list(agent.options.agents.keys())}")
    return True


def test_parse_result():
    """Test result parsing from JSON response."""
    print("✓ Testing result parsing...")

    agent = SubmarineAgent()

    # Mock JSON response
    mock_response = """
    Here's the mission result:

    ```json
    {
        "query": "Find emails for Acme Corp",
        "pages_fetched": 150,
        "entities_extracted": [
            {
                "type": "email",
                "value": "ceo@acme.com",
                "source_url": "https://acme.com/team"
            }
        ],
        "domains_covered": ["acme.com", "blog.acme.com"],
        "plan_file": "/data/SUBMARINE/plans/mcp_acme_20260111.json",
        "status": "completed",
        "confidence_score": 0.88,
        "sources": ["explorer", "jester"]
    }
    ```

    Mission completed successfully.
    """

    result = agent._parse_result(mock_response, "Find emails for Acme Corp")

    assert result.query == "Find emails for Acme Corp"
    assert result.pages_fetched == 150
    assert len(result.entities_extracted) == 1
    assert result.entities_extracted[0]["value"] == "ceo@acme.com"
    assert len(result.domains_covered) == 2
    assert result.confidence_score == 0.88
    assert "explorer" in result.sources

    print("  ✓ Result parsing works")
    print(f"  ✓ Parsed query: {result.query}")
    print(f"  ✓ Pages fetched: {result.pages_fetched}")
    return True


def test_subagent_configuration():
    """Test that subagents are properly configured."""
    print("✓ Testing subagent configuration...")

    agent = SubmarineAgent()

    # Check jester configuration
    jester_agent = agent.options.agents["jester"]
    assert "JESTER" in jester_agent.prompt
    assert "mcp__submarine__scrape" in jester_agent.tools
    print(f"  ✓ jester: configured")

    # Check explorer configuration
    explorer_agent = agent.options.agents["explorer"]
    assert "explorer" in explorer_agent.description.lower()
    assert "mcp__submarine__submarine_search" in explorer_agent.tools
    print(f"  ✓ explorer: configured")

    # Check darkweb configuration
    darkweb_agent = agent.options.agents["darkweb"]
    assert "darkweb" in darkweb_agent.description.lower()
    assert "mcp__submarine__darkweb_search" in darkweb_agent.tools
    print(f"  ✓ darkweb: configured")

    return True


def test_delegation_only():
    """Test that SUBMARINE has no direct tools (delegation only)."""
    print("✓ Testing delegation-only architecture...")

    agent = SubmarineAgent()

    # SUBMARINE should have NO allowed_tools
    assert agent.options.allowed_tools == []
    print("  ✓ SUBMARINE has 0 direct tools (delegation only)")

    return True


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("SUBMARINE AGENT TEST SUITE")
    print("="*80 + "\n")

    tests = [
        ("Result Creation", test_result_creation),
        ("Agent Initialization", test_agent_initialization),
        ("Result Parsing", test_parse_result),
        ("Subagent Configuration", test_subagent_configuration),
        ("Delegation-Only Architecture", test_delegation_only),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            result = test_func()
            if result:
                passed += 1
                print(f"✅ {test_name}: PASSED\n")
            else:
                failed += 1
                print(f"❌ {test_name}: FAILED\n")
        except Exception as e:
            failed += 1
            print(f"❌ {test_name}: FAILED")
            print(f"   Error: {e}\n")

    print("="*80)
    print(f"TEST RESULTS: {passed} passed, {failed} failed")
    print("="*80)

    if failed == 0:
        print("\n✅ All tests passed! SUBMARINE agent is ready.")
        return 0
    else:
        print(f"\n❌ {failed} test(s) failed. Please review errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
