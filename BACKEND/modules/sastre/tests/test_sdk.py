"""
Tests for SASTRE SDK Module

Tests cover:
- Agent configuration
- Tool definitions
- Investigate function
- Execute function
"""

import pytest


class TestSDKImports:
    """Test that SDK can be imported."""

    def test_import_investigate(self):
        from SASTRE.sdk import investigate
        assert callable(investigate)

    def test_import_sastre_agent(self):
        from SASTRE.sdk import SastreAgent
        assert SastreAgent is not None

    def test_import_agent_config(self):
        from SASTRE.sdk import AgentConfig
        assert AgentConfig is not None

    def test_import_agent_configs(self):
        from SASTRE.sdk import AGENT_CONFIGS
        assert isinstance(AGENT_CONFIGS, dict)

    def test_import_tools(self):
        from SASTRE.sdk import TOOLS
        assert isinstance(TOOLS, dict)

    def test_import_tool_handlers(self):
        from SASTRE.sdk import TOOL_HANDLERS
        assert isinstance(TOOL_HANDLERS, dict)


class TestAgentConfigs:
    """Test agent configurations."""

    def test_nexus_config_exists(self):
        from SASTRE.sdk import AGENT_CONFIGS
        # investigator merged into nexus
        assert "nexus" in AGENT_CONFIGS

    def test_disambiguator_config_exists(self):
        from SASTRE.sdk import AGENT_CONFIGS
        assert "disambiguator" in AGENT_CONFIGS


class TestTools:
    """Test tool definitions."""

    def test_execute_tool_exists(self):
        from SASTRE.sdk import TOOLS
        tool_names = [t.get("name") if isinstance(t, dict) else getattr(t, 'name', None) for t in TOOLS]
        assert "execute" in tool_names or any("execute" in str(t) for t in TOOLS)

    def test_assess_tool_exists(self):
        from SASTRE.sdk import TOOLS
        tool_names = [t.get("name") if isinstance(t, dict) else getattr(t, 'name', None) for t in TOOLS]
        assert "assess" in tool_names or any("assess" in str(t) for t in TOOLS)


class TestToolHandlers:
    """Test tool handlers."""

    def test_handle_execute_exists(self):
        from SASTRE.sdk import handle_execute
        assert callable(handle_execute)

    def test_handle_assess_exists(self):
        from SASTRE.sdk import handle_assess
        assert callable(handle_assess)

    def test_handle_resolve_exists(self):
        from SASTRE.sdk import handle_resolve
        assert callable(handle_resolve)
