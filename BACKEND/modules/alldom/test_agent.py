#!/usr/bin/env python3
"""
Test script for ALLDOM agent

Runs basic functionality tests without requiring live API calls.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alldom.agent import AlldomAgent, DomainProfile


def test_profile_creation():
    """Test DomainProfile dataclass creation."""
    print("✓ Testing DomainProfile creation...")

    profile = DomainProfile(
        domain="example.com",
        whois={"registrar": "Test Registrar"},
        tech_stack=["Nginx", "React"],
        confidence_score=0.9,
        sources=["TEST"]
    )

    assert profile.domain == "example.com"
    assert profile.whois["registrar"] == "Test Registrar"
    assert len(profile.tech_stack) == 2
    assert profile.confidence_score == 0.9

    # Test to_dict
    profile_dict = profile.to_dict()
    assert isinstance(profile_dict, dict)
    assert profile_dict["domain"] == "example.com"

    print("  ✓ DomainProfile creation works")
    return True


def test_agent_initialization():
    """Test AlldomAgent initialization."""
    print("✓ Testing AlldomAgent initialization...")

    agent = AlldomAgent()

    # Check options are set
    assert agent.options is not None
    assert agent.options.system_prompt is not None
    assert "ALLDOM" in agent.options.system_prompt
    assert "You are ALLDOM" in agent.options.system_prompt

    # Check subagents are configured
    assert agent.options.agents is not None
    assert "linklater" in agent.options.agents
    assert "analyzer" in agent.options.agents
    assert "mapper" in agent.options.agents
    assert "backdrill" in agent.options.agents

    # Check MCP servers are configured
    assert agent.options.mcp_servers is not None
    assert "linklater" in agent.options.mcp_servers
    assert "alldom" in agent.options.mcp_servers

    # Check no direct tools (delegation only)
    assert agent.options.allowed_tools == []

    print("  ✓ Agent initialization works")
    print(f"  ✓ Subagents configured: {list(agent.options.agents.keys())}")
    print(f"  ✓ MCP servers configured: {list(agent.options.mcp_servers.keys())}")
    return True


def test_parse_profile():
    """Test profile parsing from JSON response."""
    print("✓ Testing profile parsing...")

    agent = AlldomAgent()

    # Mock JSON response
    mock_response = """
    Here's the domain profile:

    ```json
    {
        "domain": "example.com",
        "whois": {
            "registrar": "GoDaddy",
            "creation_date": "1995-08-14"
        },
        "dns": {
            "a_records": ["93.184.216.34"],
            "ns_records": ["ns1.example.com"]
        },
        "tech_stack": ["Nginx", "Varnish"],
        "subdomains": ["www", "blog", "api"],
        "backlinks": [
            {
                "source": "wikipedia.org",
                "target": "example.com",
                "type": "dofollow"
            }
        ],
        "archive_history": [
            {
                "date": "2010-01-01",
                "status": "active"
            }
        ],
        "entities_extracted": {
            "emails": ["info@example.com"],
            "persons": ["John Doe"]
        },
        "metadata": {
            "title": "Example Domain"
        },
        "confidence_score": 0.95,
        "sources": ["analyzer", "mapper", "linklater", "backdrill"]
    }
    ```

    That's the complete profile.
    """

    profile = agent._parse_profile(mock_response, "example.com")

    assert profile.domain == "example.com"
    assert profile.whois["registrar"] == "GoDaddy"
    assert len(profile.tech_stack) == 2
    assert len(profile.subdomains) == 3
    assert len(profile.backlinks) == 1
    assert profile.confidence_score == 0.95
    assert "linklater" in profile.sources

    print("  ✓ Profile parsing works")
    print(f"  ✓ Parsed domain: {profile.domain}")
    print(f"  ✓ Confidence: {profile.confidence_score}")
    return True


def test_parse_profile_edge_cases():
    """Test profile parsing edge cases."""
    print("✓ Testing profile parsing edge cases...")

    agent = AlldomAgent()

    # Test 1: No JSON in response
    profile1 = agent._parse_profile("No JSON here, just text", "test.com")
    assert profile1.domain == "test.com"  # Fallback to identifier
    print("  ✓ No JSON case handled")

    # Test 2: Malformed JSON
    profile2 = agent._parse_profile("```json\n{invalid json}\n```", "test.com")
    assert profile2.domain == "test.com"  # Fallback
    print("  ✓ Malformed JSON case handled")

    # Test 3: Minimal valid JSON
    profile3 = agent._parse_profile('{"domain": "minimal.com"}', "test.com")
    assert profile3.domain == "minimal.com"
    print("  ✓ Minimal JSON case handled")

    return True


def test_subagent_configuration():
    """Test that subagents are properly configured."""
    print("✓ Testing subagent configuration...")

    agent = AlldomAgent()

    # Check linklater configuration
    linklater_agent = agent.options.agents["linklater"]
    assert "LINKLATER" in linklater_agent.prompt
    assert "mcp__linklater__linklater_backlinks" in linklater_agent.tools
    print(f"  ✓ linklater: configured")

    # Check analyzer configuration
    analyzer_agent = agent.options.agents["analyzer"]
    assert "analyzer" in analyzer_agent.description.lower()
    assert "mcp__alldom__alldom_execute" in analyzer_agent.tools
    print(f"  ✓ analyzer: configured")

    # Check mapper configuration
    mapper_agent = agent.options.agents["mapper"]
    assert "mapper" in mapper_agent.description.lower()
    assert "mcp__alldom__alldom_execute" in mapper_agent.tools
    print(f"  ✓ mapper: configured")

    return True


def test_delegation_only():
    """Test that ALLDOM has no direct tools (delegation only)."""
    print("✓ Testing delegation-only architecture...")

    agent = AlldomAgent()

    # ALLDOM should have NO allowed_tools
    assert agent.options.allowed_tools == []
    print("  ✓ ALLDOM has 0 direct tools (delegation only)")

    return True


async def test_mock_investigation():
    """Test investigation setup (no actual API call)."""
    print("✓ Testing mock investigation (no API call)...")

    agent = AlldomAgent()

    # Verify agent is ready
    assert agent.options is not None
    assert len(agent.options.agents) == 4

    print("  ✓ Agent ready for investigation")
    print("  ⓘ Skipping actual API call (requires ANTHROPIC_API_KEY)")

    return True


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("ALLDOM AGENT TEST SUITE")
    print("="*80 + "\n")

    tests = [
        ("Profile Creation", test_profile_creation),
        ("Agent Initialization", test_agent_initialization),
        ("Profile Parsing", test_parse_profile),
        ("Profile Parsing Edge Cases", test_parse_profile_edge_cases),
        ("Subagent Configuration", test_subagent_configuration),
        ("Delegation-Only Architecture", test_delegation_only),
        ("Mock Investigation", test_mock_investigation),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = asyncio.run(test_func())
            else:
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
        print("\n✅ All tests passed! ALLDOM agent is ready.")
        return 0
    else:
        print(f"\n❌ {failed} test(s) failed. Please review errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
