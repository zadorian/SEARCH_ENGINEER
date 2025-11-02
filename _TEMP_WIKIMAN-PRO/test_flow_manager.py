#!/usr/bin/env python3
"""Unit tests for flow_manager.py."""

import json
import shutil
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from flow_manager import (
    Flow,
    FlowExecution,
    FlowManager,
    FlowManagerError,
    FlowNotFoundError,
)


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database for testing."""
    db_path = tmp_path / "test_flows.db"
    screenshot_path = tmp_path / "test_screenshots"
    return db_path, screenshot_path


@pytest.fixture
def manager(temp_db):
    """Create FlowManager instance with temporary database."""
    db_path, screenshot_path = temp_db
    return FlowManager(db_path=db_path, screenshot_base=screenshot_path)


@pytest.fixture
def sample_actions():
    """Sample action list for testing."""
    return [
        {"name": "navigate", "args": {"url": "https://example.com"}},
        {"name": "click_at", "args": {"x": 450, "y": 320}, "element_hint": "Search button"},
        {"name": "type_text_at", "args": {"x": 450, "y": 200, "text": "{{company_name}}"}},
    ]


@pytest.fixture
def sample_screenshots():
    """Sample screenshot data for testing."""
    # Create fake PNG data (minimal valid PNG header)
    png_header = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    return [png_header + b'\x00' * 100 for _ in range(3)]


class TestDatabaseInitialization:
    """Tests for database initialization."""

    def test_database_creation(self, manager):
        """Database and tables are created."""
        assert manager.db_path.exists()

        # Verify tables exist
        import sqlite3
        with sqlite3.connect(manager.db_path) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = [row[0] for row in tables]

            assert "flows" in table_names
            assert "flow_executions" in table_names

    def test_wal_mode_enabled(self, manager):
        """WAL mode is enabled for concurrency."""
        import sqlite3
        with sqlite3.connect(manager.db_path) as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode.lower() == "wal"

    def test_indexes_created(self, manager):
        """Indexes are created for common queries."""
        import sqlite3
        with sqlite3.connect(manager.db_path) as conn:
            indexes = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
            index_names = [row[0] for row in indexes]

            assert "idx_flows_country_type" in index_names
            assert "idx_executions_flow_id" in index_names


class TestFlowSave:
    """Tests for save_flow method."""

    def test_save_flow_basic(self, manager, sample_actions):
        """Save flow with basic metadata."""
        flow = manager.save_flow(
            flow_id="test_flow_v1",
            version=1,
            country_code="HU",
            source_type="corporate_registry",
            actions=sample_actions,
        )

        assert flow.flow_id == "test_flow_v1"
        assert flow.version == 1
        assert flow.country_code == "hu"  # Lowercased
        assert flow.source_type == "corporate_registry"
        assert flow.execution_count == 0
        assert flow.success_count == 0
        assert flow.is_deprecated is False
        assert len(flow.actions) == 3

    def test_save_flow_with_screenshots(self, manager, sample_actions, sample_screenshots):
        """Save flow with screenshots."""
        flow = manager.save_flow(
            flow_id="test_flow_v2",
            version=1,
            country_code="de",
            source_type="corporate_registry",
            actions=sample_actions,
            screenshots=sample_screenshots,
        )

        assert flow.screenshot_dir is not None
        assert flow.screenshot_count == 3

        # Verify screenshots saved to disk
        screenshot_dir = Path(flow.screenshot_dir)
        assert screenshot_dir.exists()
        assert len(list(screenshot_dir.glob("*.png"))) == 3

    def test_save_duplicate_flow_fails(self, manager, sample_actions):
        """Saving duplicate flow_id raises error."""
        manager.save_flow(
            flow_id="test_flow_v1",
            version=1,
            country_code="hu",
            source_type="corporate_registry",
            actions=sample_actions,
        )

        with pytest.raises(FlowManagerError, match="already exists"):
            manager.save_flow(
                flow_id="test_flow_v1",
                version=2,
                country_code="hu",
                source_type="corporate_registry",
                actions=sample_actions,
            )

    def test_save_flow_latency_instrumentation(self, manager, sample_actions):
        """save_flow logs latency for SLA validation."""
        with patch("flow_manager.perf_logger") as mock_logger:
            manager.save_flow(
                flow_id="test_flow_v1",
                version=1,
                country_code="hu",
                source_type="corporate_registry",
                actions=sample_actions,
            )

            # Verify performance log called
            assert mock_logger.info.called
            call_args = mock_logger.info.call_args[0][0]
            log_data = json.loads(call_args)
            assert log_data["operation"] == "flow_manager.save_flow"
            assert "duration_ms" in log_data
            assert log_data["status"] == "success"


class TestFlowFind:
    """Tests for find_flow method."""

    def test_find_flow_success(self, manager, sample_actions):
        """Find existing flow by country and source type."""
        manager.save_flow(
            flow_id="hungary_v1",
            version=1,
            country_code="hu",
            source_type="corporate_registry",
            actions=sample_actions,
        )

        found = manager.find_flow("hu", "corporate_registry")

        assert found is not None
        assert found.flow_id == "hungary_v1"
        assert found.country_code == "hu"

    def test_find_flow_not_found(self, manager):
        """find_flow returns None if no match."""
        found = manager.find_flow("xx", "corporate_registry")
        assert found is None

    def test_find_flow_returns_latest_version(self, manager, sample_actions):
        """find_flow returns highest version."""
        manager.save_flow(
            flow_id="hungary_v1",
            version=1,
            country_code="hu",
            source_type="corporate_registry",
            actions=sample_actions,
        )
        manager.save_flow(
            flow_id="hungary_v2",
            version=2,
            country_code="hu",
            source_type="corporate_registry",
            actions=sample_actions,
        )

        found = manager.find_flow("hu", "corporate_registry")

        assert found is not None
        assert found.version == 2
        assert found.flow_id == "hungary_v2"

    def test_find_flow_excludes_deprecated(self, manager, sample_actions):
        """find_flow excludes deprecated flows by default."""
        flow = manager.save_flow(
            flow_id="hungary_v1",
            version=1,
            country_code="hu",
            source_type="corporate_registry",
            actions=sample_actions,
        )

        # Deprecate flow
        manager.deprecate_flow(flow.flow_id, "Test deprecation")

        # Should not find deprecated flow
        found = manager.find_flow("hu", "corporate_registry")
        assert found is None

    def test_find_flow_include_deprecated(self, manager, sample_actions):
        """find_flow can include deprecated flows."""
        flow = manager.save_flow(
            flow_id="hungary_v1",
            version=1,
            country_code="hu",
            source_type="corporate_registry",
            actions=sample_actions,
        )

        manager.deprecate_flow(flow.flow_id, "Test deprecation")

        # Should find with include_deprecated=True
        found = manager.find_flow("hu", "corporate_registry", include_deprecated=True)
        assert found is not None
        assert found.is_deprecated is True

    def test_find_flow_latency_instrumentation(self, manager, sample_actions):
        """find_flow logs latency for SLA validation."""
        manager.save_flow(
            flow_id="hungary_v1",
            version=1,
            country_code="hu",
            source_type="corporate_registry",
            actions=sample_actions,
        )

        with patch("flow_manager.perf_logger") as mock_logger:
            manager.find_flow("hu", "corporate_registry")

            # Verify performance log called
            assert mock_logger.info.called
            call_args = mock_logger.info.call_args[0][0]
            log_data = json.loads(call_args)
            assert log_data["operation"] == "flow_manager.find_flow"
            assert "duration_ms" in log_data


class TestFlowRetrieval:
    """Tests for get_flow and list_flows methods."""

    def test_get_flow_by_id(self, manager, sample_actions):
        """Get flow by ID."""
        saved = manager.save_flow(
            flow_id="test_flow_v1",
            version=1,
            country_code="hu",
            source_type="corporate_registry",
            actions=sample_actions,
        )

        retrieved = manager.get_flow("test_flow_v1")

        assert retrieved.flow_id == saved.flow_id
        assert retrieved.version == saved.version

    def test_get_flow_not_found(self, manager):
        """get_flow raises error if not found."""
        with pytest.raises(FlowNotFoundError, match="not found"):
            manager.get_flow("nonexistent_flow")

    def test_list_flows_all(self, manager, sample_actions):
        """List all flows."""
        manager.save_flow(
            flow_id="hungary_v1",
            version=1,
            country_code="hu",
            source_type="corporate_registry",
            actions=sample_actions,
        )
        manager.save_flow(
            flow_id="germany_v1",
            version=1,
            country_code="de",
            source_type="corporate_registry",
            actions=sample_actions,
        )

        flows = manager.list_flows()

        assert len(flows) == 2
        flow_ids = {flow.flow_id for flow in flows}
        assert "hungary_v1" in flow_ids
        assert "germany_v1" in flow_ids

    def test_list_flows_by_country(self, manager, sample_actions):
        """List flows filtered by country."""
        manager.save_flow(
            flow_id="hungary_v1",
            version=1,
            country_code="hu",
            source_type="corporate_registry",
            actions=sample_actions,
        )
        manager.save_flow(
            flow_id="germany_v1",
            version=1,
            country_code="de",
            source_type="corporate_registry",
            actions=sample_actions,
        )

        flows = manager.list_flows(country_code="hu")

        assert len(flows) == 1
        assert flows[0].country_code == "hu"

    def test_list_flows_excludes_deprecated(self, manager, sample_actions):
        """list_flows excludes deprecated by default."""
        flow = manager.save_flow(
            flow_id="hungary_v1",
            version=1,
            country_code="hu",
            source_type="corporate_registry",
            actions=sample_actions,
        )

        manager.deprecate_flow(flow.flow_id, "Test")

        flows = manager.list_flows()
        assert len(flows) == 0


class TestExecutionRecording:
    """Tests for record_execution method."""

    def test_record_execution_success(self, manager, sample_actions):
        """Record successful execution."""
        flow = manager.save_flow(
            flow_id="test_flow_v1",
            version=1,
            country_code="hu",
            source_type="corporate_registry",
            actions=sample_actions,
        )

        execution = manager.record_execution(
            execution_id="exec_001",
            flow_id=flow.flow_id,
            execution_time_ms=3500,
            success=True,
            input_params={"company_name": "Test Company"},
            output_data={"result": "success"},
        )

        assert execution.execution_id == "exec_001"
        assert execution.success is True
        assert execution.execution_time_ms == 3500

        # Verify flow metrics updated
        updated_flow = manager.get_flow(flow.flow_id)
        assert updated_flow.execution_count == 1
        assert updated_flow.success_count == 1
        assert updated_flow.success_rate == 1.0

    def test_record_execution_failure(self, manager, sample_actions):
        """Record failed execution."""
        flow = manager.save_flow(
            flow_id="test_flow_v1",
            version=1,
            country_code="hu",
            source_type="corporate_registry",
            actions=sample_actions,
        )

        execution = manager.record_execution(
            execution_id="exec_002",
            flow_id=flow.flow_id,
            execution_time_ms=2500,
            success=False,
            error_type="NetworkError",
            error_message="Connection timeout",
        )

        assert execution.success is False
        assert execution.error_type == "NetworkError"

        # Verify flow metrics updated
        updated_flow = manager.get_flow(flow.flow_id)
        assert updated_flow.execution_count == 1
        assert updated_flow.success_count == 0
        assert updated_flow.success_rate == 0.0

    def test_record_execution_with_screenshots(self, manager, sample_actions, sample_screenshots):
        """Record execution with screenshots."""
        flow = manager.save_flow(
            flow_id="test_flow_v1",
            version=1,
            country_code="hu",
            source_type="corporate_registry",
            actions=sample_actions,
        )

        execution = manager.record_execution(
            execution_id="exec_003",
            flow_id=flow.flow_id,
            execution_time_ms=3500,
            success=True,
            screenshots=sample_screenshots,
        )

        assert execution.screenshot_dir is not None
        assert execution.screenshot_count == 3

        # Verify screenshots saved
        screenshot_dir = Path(execution.screenshot_dir)
        assert screenshot_dir.exists()
        assert len(list(screenshot_dir.glob("*.png"))) == 3

    def test_get_execution_history(self, manager, sample_actions):
        """Get execution history for a flow."""
        flow = manager.save_flow(
            flow_id="test_flow_v1",
            version=1,
            country_code="hu",
            source_type="corporate_registry",
            actions=sample_actions,
        )

        # Record multiple executions
        for i in range(5):
            manager.record_execution(
                execution_id=f"exec_{i:03d}",
                flow_id=flow.flow_id,
                execution_time_ms=3000 + i * 100,
                success=(i % 2 == 0),
            )
            time.sleep(0.01)  # Ensure different timestamps

        history = manager.get_execution_history(flow.flow_id, limit=3)

        assert len(history) == 3
        # Should be in reverse chronological order
        assert history[0].execution_id == "exec_004"
        assert history[1].execution_id == "exec_003"
        assert history[2].execution_id == "exec_002"


class TestAutoDeprecation:
    """Tests for auto-deprecation rules."""

    def test_auto_deprecate_three_consecutive_failures(self, manager, sample_actions):
        """Flow auto-deprecated after 3 consecutive failures."""
        flow = manager.save_flow(
            flow_id="test_flow_v1",
            version=1,
            country_code="hu",
            source_type="corporate_registry",
            actions=sample_actions,
        )

        # Record 3 consecutive failures
        for i in range(3):
            manager.record_execution(
                execution_id=f"exec_{i:03d}",
                flow_id=flow.flow_id,
                execution_time_ms=3000,
                success=False,
                error_type="NetworkError",
            )

        # Verify flow is deprecated
        updated_flow = manager.get_flow(flow.flow_id)
        assert updated_flow.is_deprecated is True
        assert "3 consecutive failures" in updated_flow.deprecation_reason

    def test_no_auto_deprecate_with_success_between_failures(self, manager, sample_actions):
        """Flow not deprecated if success between failures."""
        flow = manager.save_flow(
            flow_id="test_flow_v1",
            version=1,
            country_code="hu",
            source_type="corporate_registry",
            actions=sample_actions,
        )

        # Failure, failure, success, failure
        manager.record_execution("exec_001", flow.flow_id, 3000, False)
        manager.record_execution("exec_002", flow.flow_id, 3000, False)
        manager.record_execution("exec_003", flow.flow_id, 3000, True)
        manager.record_execution("exec_004", flow.flow_id, 3000, False)

        # Should not be deprecated
        updated_flow = manager.get_flow(flow.flow_id)
        assert updated_flow.is_deprecated is False

    def test_auto_deprecate_low_success_rate(self, manager, sample_actions):
        """Flow auto-deprecated when success rate < 30% with >10 executions."""
        flow = manager.save_flow(
            flow_id="test_flow_v1",
            version=1,
            country_code="hu",
            source_type="corporate_registry",
            actions=sample_actions,
        )

        # Record 12 executions: 3 success, 9 failures (25% success rate)
        # Pattern: F F S F F S F F S F F S (avoid 3 consecutive failures)
        pattern = [False, False, True, False, False, True, False, False, True, False, False, True]
        for i, success in enumerate(pattern):
            manager.record_execution(
                execution_id=f"exec_{i:03d}",
                flow_id=flow.flow_id,
                execution_time_ms=3000,
                success=success,
            )

        # Verify flow is deprecated due to low success rate
        updated_flow = manager.get_flow(flow.flow_id)
        assert updated_flow.is_deprecated is True
        assert "Low success rate" in updated_flow.deprecation_reason

    def test_no_auto_deprecate_with_few_executions(self, manager, sample_actions):
        """Flow not deprecated if <10 executions even with low success rate."""
        flow = manager.save_flow(
            flow_id="test_flow_v1",
            version=1,
            country_code="hu",
            source_type="corporate_registry",
            actions=sample_actions,
        )

        # Record 5 executions: 1 success, 4 failures (20% success rate)
        # Pattern: S F F S F (avoid 3 consecutive failures)
        pattern = [True, False, False, True, False]
        for i, success in enumerate(pattern):
            manager.record_execution(
                execution_id=f"exec_{i:03d}",
                flow_id=flow.flow_id,
                execution_time_ms=3000,
                success=success,
            )

        # Should not be deprecated (too few executions)
        updated_flow = manager.get_flow(flow.flow_id)
        assert updated_flow.is_deprecated is False

    def test_manual_deprecation(self, manager, sample_actions):
        """Manual deprecation works correctly."""
        flow = manager.save_flow(
            flow_id="test_flow_v1",
            version=1,
            country_code="hu",
            source_type="corporate_registry",
            actions=sample_actions,
        )

        manager.deprecate_flow(flow.flow_id, "Website redesigned")

        updated_flow = manager.get_flow(flow.flow_id)
        assert updated_flow.is_deprecated is True
        assert updated_flow.deprecation_reason == "Website redesigned"


class TestFlowDeletion:
    """Tests for delete_flow method."""

    def test_delete_flow(self, manager, sample_actions):
        """Delete flow and execution records."""
        flow = manager.save_flow(
            flow_id="test_flow_v1",
            version=1,
            country_code="hu",
            source_type="corporate_registry",
            actions=sample_actions,
        )

        # Record execution
        manager.record_execution(
            execution_id="exec_001",
            flow_id=flow.flow_id,
            execution_time_ms=3000,
            success=True,
        )

        # Delete flow
        manager.delete_flow(flow.flow_id)

        # Verify flow doesn't exist
        with pytest.raises(FlowNotFoundError):
            manager.get_flow(flow.flow_id)

        # Verify executions deleted
        history = manager.get_execution_history(flow.flow_id)
        assert len(history) == 0

    def test_delete_flow_with_screenshots(self, manager, sample_actions, sample_screenshots):
        """Delete flow and its screenshots."""
        flow = manager.save_flow(
            flow_id="test_flow_v1",
            version=1,
            country_code="hu",
            source_type="corporate_registry",
            actions=sample_actions,
            screenshots=sample_screenshots,
        )

        screenshot_dir = Path(flow.screenshot_dir)
        assert screenshot_dir.exists()

        # Delete flow
        manager.delete_flow(flow.flow_id, delete_screenshots=True)

        # Verify screenshots deleted
        assert not screenshot_dir.exists()


class TestStatistics:
    """Tests for get_stats method."""

    def test_get_stats_empty_database(self, manager):
        """Get stats from empty database."""
        stats = manager.get_stats()

        assert stats["total_flows"] == 0
        assert stats["active_flows"] == 0
        assert stats["deprecated_flows"] == 0
        assert stats["total_executions"] == 0
        assert stats["overall_success_rate"] == 0.0

    def test_get_stats_with_flows(self, manager, sample_actions):
        """Get stats with multiple flows."""
        # Create flows
        flow1 = manager.save_flow(
            flow_id="hungary_v1",
            version=1,
            country_code="hu",
            source_type="corporate_registry",
            actions=sample_actions,
        )
        flow2 = manager.save_flow(
            flow_id="germany_v1",
            version=1,
            country_code="de",
            source_type="corporate_registry",
            actions=sample_actions,
        )

        # Record executions
        manager.record_execution("exec_001", flow1.flow_id, 3000, True)
        manager.record_execution("exec_002", flow1.flow_id, 3000, False)
        manager.record_execution("exec_003", flow2.flow_id, 3000, True)

        # Deprecate one flow
        manager.deprecate_flow(flow2.flow_id, "Test")

        stats = manager.get_stats()

        assert stats["total_flows"] == 2
        assert stats["active_flows"] == 1
        assert stats["deprecated_flows"] == 1
        assert stats["total_executions"] == 3
        assert stats["successful_executions"] == 2
        assert stats["overall_success_rate"] == pytest.approx(2/3, 0.01)
        assert stats["flows_by_country"]["hu"] == 1
        assert "de" not in stats["flows_by_country"]  # Deprecated flow excluded


class TestFlowProperties:
    """Tests for Flow dataclass properties."""

    def test_flow_success_rate_calculation(self):
        """Flow calculates success rate correctly."""
        flow = Flow(
            flow_id="test",
            version=1,
            country_code="hu",
            source_type="corporate",
            created_at=int(time.time()),
            last_used=int(time.time()),
            execution_count=10,
            success_count=7,
        )

        assert flow.success_rate == 0.7

    def test_flow_actions_property(self):
        """Flow parses actions JSON."""
        actions = [{"name": "click", "args": {"x": 100}}]
        flow = Flow(
            flow_id="test",
            version=1,
            country_code="hu",
            source_type="corporate",
            created_at=int(time.time()),
            last_used=int(time.time()),
            actions_json=json.dumps(actions),
        )

        assert flow.actions == actions


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
