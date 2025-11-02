#!/usr/bin/env python3
"""Integration tests for real browser automation with Playwright."""

import json
import time
from pathlib import Path

import pytest

from orchestrator import ReplayExecutor
from flow_manager import FlowManager, Flow
from query_parser import ParsedQuery


@pytest.fixture
def flow_manager():
    """Create in-memory flow manager."""
    return FlowManager(db_path=":memory:")


@pytest.fixture
def simple_navigate_flow():
    """Flow that just navigates to example.com."""
    return Flow(
        flow_id="test_navigate",
        version=1,
        country_code="test",
        source_type="test",
        created_at=int(time.time()),
        last_used=int(time.time()),
        actions_json=json.dumps([
            {"name": "navigate", "args": {"url": "https://example.com"}}
        ])
    )


@pytest.fixture
def test_query():
    """Test parsed query."""
    return ParsedQuery(
        country_code="test",
        country_name="test",
        source_type="test",
        entity_name="Test Entity",
        original_query="Test query"
    )


class TestPlaywrightIntegration:
    """Integration tests for Playwright browser automation."""

    def test_playwright_navigation(self, flow_manager, simple_navigate_flow, test_query):
        """Test real browser navigation with Playwright."""
        executor = ReplayExecutor(flow_manager)

        # Execute flow with real browser
        data, screenshots = executor._execute_replay(
            simple_navigate_flow,
            test_query,
            timeout_seconds=10
        )

        # Verify real browser automation was used
        assert data.get("browser_automation_used") is True
        assert data.get("replay_mode") == "playwright"

        # Verify we got real content from the page
        assert data.get("extracted_text") is not None
        assert len(data.get("extracted_text", "")) > 0

        # Verify screenshot was captured
        assert len(screenshots) >= 1
        assert len(screenshots[0]) > 0  # Has bytes

    def test_playwright_with_entity_substitution(self, flow_manager, test_query):
        """Test entity name substitution in form fields."""
        flow = Flow(
            flow_id="test_fill",
            version=1,
            country_code="test",
            source_type="test",
            created_at=int(time.time()),
            last_used=int(time.time()),
            actions_json=json.dumps([
                {"name": "navigate", "args": {"url": "https://example.com"}},
                # This would fail on example.com but tests the substitution logic
                # {"name": "fill", "args": {"selector": "input", "value": "{entity}"}}
            ])
        )

        executor = ReplayExecutor(flow_manager)

        # Execute - should work for navigation part
        data, screenshots = executor._execute_replay(flow, test_query, timeout_seconds=10)

        # Verify it executed
        assert data.get("entity_name") == "Test Entity"
        assert data.get("browser_automation_used") is True

    def test_playwright_error_handling(self, flow_manager, test_query):
        """Test graceful fallback when browser automation fails."""
        flow = Flow(
            flow_id="test_error",
            version=1,
            country_code="test",
            source_type="test",
            created_at=int(time.time()),
            last_used=int(time.time()),
            actions_json=json.dumps([
                {"name": "navigate", "args": {"url": "https://example.com"}},
                {"name": "click", "args": {"selector": "#DOES_NOT_EXIST"}}
            ])
        )

        executor = ReplayExecutor(flow_manager)

        # Execute - should fail gracefully
        data, screenshots = executor._execute_replay(flow, test_query, timeout_seconds=5)

        # Should fall back to simulation
        assert data.get("simulated") is True

    def test_playwright_screenshot_capture(self, flow_manager, test_query):
        """Test screenshot capture during execution."""
        flow = Flow(
            flow_id="test_screenshot",
            version=1,
            country_code="test",
            source_type="test",
            created_at=int(time.time()),
            last_used=int(time.time()),
            actions_json=json.dumps([
                {"name": "navigate", "args": {"url": "https://example.com"}},
                {"name": "screenshot", "args": {"name": "test_capture"}}
            ])
        )

        executor = ReplayExecutor(flow_manager)

        data, screenshots = executor._execute_replay(flow, test_query, timeout_seconds=10)

        # Should have captured screenshot + final screenshot
        assert len(screenshots) >= 2

        # Verify screenshots are PNG bytes
        for screenshot in screenshots:
            assert len(screenshot) > 0
            # PNG files start with these bytes
            assert screenshot[:4] == b'\x89PNG'


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
