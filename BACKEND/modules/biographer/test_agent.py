#!/usr/bin/env python3
"""
Test script for BIOGRAPHER agent

Runs basic functionality tests without requiring live API calls.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from BIOGRAPHER.agent import BiographerAgent, PersonProfile


def test_profile_creation():
    """Test PersonProfile dataclass creation."""
    print("✓ Testing PersonProfile creation...")

    profile = PersonProfile(
        name="Test Person",
        identifiers={"email": "test@example.com"},
        employment=[{"company": "Test Corp", "position": "CEO"}],
        confidence_score=0.85,
        sources=["TEST"]
    )

    assert profile.name == "Test Person"
    assert profile.identifiers["email"] == "test@example.com"
    assert len(profile.employment) == 1
    assert profile.confidence_score == 0.85

    # Test to_dict
    profile_dict = profile.to_dict()
    assert isinstance(profile_dict, dict)
    assert profile_dict["name"] == "Test Person"

    print("  ✓ PersonProfile creation works")
    return True


def test_agent_initialization():
    """Test BiographerAgent initialization."""
    print("✓ Testing BiographerAgent initialization...")

    agent = BiographerAgent()

    # Check options are set
    assert agent.options is not None
    assert agent.options.system_prompt is not None
    assert "BIOGRAPHER" in agent.options.system_prompt
    assert "You are BIOGRAPHER" in agent.options.system_prompt

    # Check subagents are configured
    assert agent.options.agents is not None
    assert "eyed" in agent.options.agents
    assert "corporella" in agent.options.agents

    # Check MCP servers are configured
    assert agent.options.mcp_servers is not None
    assert "eyed" in agent.options.mcp_servers
    assert "corporella" in agent.options.mcp_servers

    # Check no direct tools (delegation only)
    assert agent.options.allowed_tools == []

    print("  ✓ Agent initialization works")
    print(f"  ✓ Subagents configured: {list(agent.options.agents.keys())}")
    print(f"  ✓ MCP servers configured: {list(agent.options.mcp_servers.keys())}")
    return True


def test_parse_profile():
    """Test profile parsing from JSON response."""
    print("✓ Testing profile parsing...")

    agent = BiographerAgent()

    # Mock JSON response
    mock_response = """
    Here's the profile:

    ```json
    {
        "name": "John Doe",
        "identifiers": {
            "email": "john@example.com",
            "phone": "+1-555-0123"
        },
        "employment": [
            {
                "company": "Acme Corp",
                "position": "Engineer",
                "dates": "2020-2023",
                "source": "CORPORELLA"
            }
        ],
        "social_profiles": [
            {
                "platform": "LinkedIn",
                "handle": "johndoe",
                "url": "https://linkedin.com/in/johndoe",
                "source": "EYE-D"
            }
        ],
        "breach_exposure": [],
        "disambiguation_notes": ["Clear match found"],
        "confidence_score": 0.9,
        "sources": ["EYE-D", "CORPORELLA"]
    }
    ```

    That's the complete profile.
    """

    profile = agent._parse_profile(mock_response, "john@example.com")

    assert profile.name == "John Doe"
    assert profile.identifiers["email"] == "john@example.com"
    assert len(profile.employment) == 1
    assert profile.employment[0]["company"] == "Acme Corp"
    assert len(profile.social_profiles) == 1
    assert profile.confidence_score == 0.9
    assert "EYE-D" in profile.sources
    assert "CORPORELLA" in profile.sources

    print("  ✓ Profile parsing works")
    print(f"  ✓ Parsed name: {profile.name}")
    print(f"  ✓ Confidence: {profile.confidence_score}")
    return True


def test_parse_profile_edge_cases():
    """Test profile parsing edge cases."""
    print("✓ Testing profile parsing edge cases...")

    agent = BiographerAgent()

    # Test 1: No JSON in response
    profile1 = agent._parse_profile("No JSON here, just text", "test@example.com")
    assert profile1.name == "test@example.com"  # Fallback to identifier
    assert profile1.confidence_score == 0.0
    assert len(profile1.disambiguation_notes) > 0
    print("  ✓ No JSON case handled")

    # Test 2: Malformed JSON
    profile2 = agent._parse_profile("```json\n{invalid json}\n```", "test@example.com")
    assert profile2.name == "test@example.com"  # Fallback
    assert profile2.confidence_score == 0.0
    print("  ✓ Malformed JSON case handled")

    # Test 3: Minimal valid JSON
    profile3 = agent._parse_profile('{"name": "Test Person"}', "test@example.com")
    assert profile3.name == "Test Person"
    assert len(profile3.employment) == 0  # Empty lists for missing fields
    assert len(profile3.social_profiles) == 0
    print("  ✓ Minimal JSON case handled")

    return True


def test_subagent_configuration():
    """Test that subagents are properly configured."""
    print("✓ Testing subagent configuration...")

    agent = BiographerAgent()

    # Check EYE-D configuration
    eyed_agent = agent.options.agents["eyed"]
    assert "EYE-D" in eyed_agent.prompt or "OSINT" in eyed_agent.prompt
    assert len(eyed_agent.tools) > 0
    assert any("search_email" in tool for tool in eyed_agent.tools)
    assert eyed_agent.model == "sonnet"
    print(f"  ✓ EYE-D: {len(eyed_agent.tools)} tools configured")

    # Check CORPORELLA configuration
    corporella_agent = agent.options.agents["corporella"]
    assert "CORPORELLA" in corporella_agent.prompt or "corporate" in corporella_agent.prompt
    assert len(corporella_agent.tools) > 0
    assert any("search_company" in tool for tool in corporella_agent.tools)
    assert corporella_agent.model == "sonnet"
    print(f"  ✓ CORPORELLA: {len(corporella_agent.tools)} tools configured")

    # Check SOCIALITE configuration (optional)
    if "socialite" in agent.options.agents:
        socialite_agent = agent.options.agents["socialite"]
        assert "SOCIALITE" in socialite_agent.prompt or "social" in socialite_agent.prompt
        print(f"  ✓ SOCIALITE: configured")
    else:
        print(f"  ⓘ SOCIALITE: not configured (optional)")

    return True


def test_delegation_only():
    """Test that BIOGRAPHER has no direct tools (delegation only)."""
    print("✓ Testing delegation-only architecture...")

    agent = BiographerAgent()

    # BIOGRAPHER should have NO allowed_tools
    assert agent.options.allowed_tools == []
    print("  ✓ BIOGRAPHER has 0 direct tools (delegation only)")

    # Subagents should have tools
    eyed_tools = agent.options.agents["eyed"].tools
    corporella_tools = agent.options.agents["corporella"].tools

    assert len(eyed_tools) > 0
    assert len(corporella_tools) > 0
    print(f"  ✓ EYE-D has {len(eyed_tools)} tools")
    print(f"  ✓ CORPORELLA has {len(corporella_tools)} tools")

    # Verify no tool overlap (each specialist has unique tools)
    eyed_mcp_prefix = "mcp__eyed__"
    corporella_mcp_prefix = "mcp__corporella__"

    assert all(tool.startswith(eyed_mcp_prefix) for tool in eyed_tools)
    assert all(tool.startswith(corporella_mcp_prefix) for tool in corporella_tools)
    print("  ✓ No tool overlap between specialists")

    return True


def test_system_prompt_quality():
    """Test that system prompts are well-structured."""
    print("✓ Testing system prompt quality...")

    agent = BiographerAgent()

    # Check BIOGRAPHER system prompt
    biographer_prompt = agent.options.system_prompt
    assert "BIOGRAPHER" in biographer_prompt
    assert "delegate" in biographer_prompt.lower()
    assert "EYE-D" in biographer_prompt or "eyed" in biographer_prompt
    assert "CORPORELLA" in biographer_prompt or "corporella" in biographer_prompt
    assert "workflow" in biographer_prompt.lower()
    assert "disambiguate" in biographer_prompt.lower()
    print("  ✓ BIOGRAPHER prompt includes key concepts")

    # Check EYE-D system prompt
    eyed_prompt = agent.options.agents["eyed"].prompt
    assert "EYE-D" in eyed_prompt or "OSINT" in eyed_prompt
    assert "email" in eyed_prompt.lower()
    assert "phone" in eyed_prompt.lower()
    assert "tool" in eyed_prompt.lower()
    print("  ✓ EYE-D prompt includes OSINT capabilities")

    # Check CORPORELLA system prompt
    corporella_prompt = agent.options.agents["corporella"].prompt
    assert "CORPORELLA" in corporella_prompt or "corporate" in corporella_prompt
    assert "company" in corporella_prompt.lower()
    assert "officer" in corporella_prompt.lower()
    assert "tool" in corporella_prompt.lower()
    print("  ✓ CORPORELLA prompt includes corporate capabilities")

    return True


async def test_mock_investigation():
    """Test investigation with mocked subagent (no actual API call)."""
    print("✓ Testing mock investigation (no API call)...")

    # This test just verifies the workflow structure without making real calls
    agent = BiographerAgent()

    # Verify agent is ready
    assert agent.options is not None
    assert agent.options.system_prompt is not None
    assert len(agent.options.agents) >= 2  # At least EYE-D and CORPORELLA

    print("  ✓ Agent ready for investigation")
    print("  ⓘ Skipping actual API call (requires ANTHROPIC_API_KEY)")

    return True


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("BIOGRAPHER AGENT TEST SUITE")
    print("="*80 + "\n")

    tests = [
        ("Profile Creation", test_profile_creation),
        ("Agent Initialization", test_agent_initialization),
        ("Profile Parsing", test_parse_profile),
        ("Profile Parsing Edge Cases", test_parse_profile_edge_cases),
        ("Subagent Configuration", test_subagent_configuration),
        ("Delegation-Only Architecture", test_delegation_only),
        ("System Prompt Quality", test_system_prompt_quality),
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
        print("\n✅ All tests passed! BIOGRAPHER agent is ready.")
        return 0
    else:
        print(f"\n❌ {failed} test(s) failed. Please review errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
