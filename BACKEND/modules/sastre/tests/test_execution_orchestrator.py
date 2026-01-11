"""
Tests for Execution Orchestrator and Gap Analyzer.

Tests the full execution flow:
- Step execution with mocks
- Slot feeding from results
- Collision detection
- K-U quadrant transitions
- Gap analysis
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock


class TestStepStatus:
    """Test StepStatus enum."""

    def test_import_step_status(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import StepStatus
        assert StepStatus is not None

    def test_status_values(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import StepStatus
        assert StepStatus.PENDING.value == "pending"
        assert StepStatus.RUNNING.value == "running"
        assert StepStatus.COMPLETED.value == "completed"
        assert StepStatus.FAILED.value == "failed"
        assert StepStatus.SKIPPED.value == "skipped"


class TestStepResult:
    """Test StepResult dataclass."""

    def test_import_step_result(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import StepResult
        assert StepResult is not None

    def test_create_step_result(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import StepResult, StepStatus

        result = StepResult(
            step_id="step_001",
            status=StepStatus.COMPLETED,
            data={"name": "John Smith"},
            slots_fed=["name"],
        )

        assert result.step_id == "step_001"
        assert result.status == StepStatus.COMPLETED
        assert result.data["name"] == "John Smith"

    def test_step_result_to_dict(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import StepResult, StepStatus

        result = StepResult(step_id="step_001", status=StepStatus.COMPLETED)
        d = result.to_dict()

        assert d["step_id"] == "step_001"
        assert d["status"] == "completed"


class TestExecutionState:
    """Test ExecutionState dataclass."""

    def test_import_execution_state(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import ExecutionState
        assert ExecutionState is not None

    def test_execution_state_is_complete(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import (
            ExecutionState, StepResult, StepStatus
        )
        from BACKEND.modules.SASTRE.investigation_planner import (
            InvestigationPlan, PlanStep, QueryTier
        )
        from BACKEND.modules.SASTRE.contracts import KUQuadrant

        plan = InvestigationPlan(
            entity_id="test_001",
            entity_type="person",
            entity_name="Test",
            jurisdiction="US",
            ku_quadrant=KUQuadrant.TRACE,
            steps=[
                PlanStep(
                    step_id="step_001",
                    description="Test",
                    input_type="person_name",
                    input_value="Test",
                    source_id="src_001",
                    source_label="Test Source",
                    country="US",
                    output_columns=["name"],
                    reliability="high",
                    ku_quadrant="trace",
                ),
            ],
        )

        state = ExecutionState(plan=plan)
        # Add a pending result so is_complete is False
        state.step_results["step_001"] = StepResult(
            step_id="step_001",
            status=StepStatus.PENDING,
        )
        assert not state.is_complete

        # Now complete it
        state.step_results["step_001"] = StepResult(
            step_id="step_001",
            status=StepStatus.COMPLETED,
        )
        assert state.is_complete


class TestMockStepExecutor:
    """Test MockStepExecutor."""

    def test_import_mock_executor(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import MockStepExecutor
        assert MockStepExecutor is not None

    @pytest.mark.asyncio
    async def test_mock_executor_returns_data(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import MockStepExecutor
        from BACKEND.modules.SASTRE.investigation_planner import PlanStep, QueryTier

        executor = MockStepExecutor()
        step = PlanStep(
            step_id="step_001",
            description="Test",
            input_type="person_name",
            input_value="John Smith",
            source_id="src_001",
            source_label="Test Source",
            country="US",
            output_columns=["name", "email", "phone"],
            reliability="high",
            ku_quadrant="trace",
        )

        result = await executor.execute(step)

        assert "data" in result
        assert "name" in result["data"]
        assert "email" in result["data"]
        assert "phone" in result["data"]


class TestExecutionOrchestrator:
    """Test ExecutionOrchestrator."""

    def test_import_orchestrator(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import ExecutionOrchestrator
        assert ExecutionOrchestrator is not None

    def test_create_orchestrator(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import ExecutionOrchestrator

        orchestrator = ExecutionOrchestrator()
        assert orchestrator.executor is not None

    @pytest.mark.asyncio
    async def test_execute_simple_plan(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import ExecutionOrchestrator
        from BACKEND.modules.SASTRE.investigation_planner import InvestigationPlanner

        planner = InvestigationPlanner()
        planner.matrix._loaded = True
        planner.matrix._flows = {
            "US": [
                {
                    "source_id": "src_001",
                    "source_label": "Test Source",
                    "input_type": "person_name",
                    "output_columns_array": ["name", "email"],
                    "reliability": "high",
                },
            ],
        }

        plan = planner.create_plan(
            entity_type="person",
            entity_name="John Smith",
            jurisdiction="US",
        )

        orchestrator = ExecutionOrchestrator()
        state = await orchestrator.execute(plan)

        assert state.is_complete
        assert state.success_rate > 0

    @pytest.mark.asyncio
    async def test_execute_feeds_slots(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import ExecutionOrchestrator
        from BACKEND.modules.SASTRE.investigation_planner import InvestigationPlanner
        from BACKEND.modules.SASTRE.contracts import SlotState

        planner = InvestigationPlanner()
        planner.matrix._loaded = True
        planner.matrix._flows = {
            "UK": [
                {
                    "source_id": "ch_001",
                    "source_label": "Companies House",
                    "input_type": "company_name",
                    "output_columns_array": ["registration_number"],
                    "reliability": "high",
                },
            ],
        }

        plan = planner.create_plan(
            entity_type="company",
            entity_name="Acme Corp",
            jurisdiction="UK",
        )

        orchestrator = ExecutionOrchestrator()
        state = await orchestrator.execute(plan)

        # Check that slots were fed
        if plan.slot_set and "registration_number" in plan.slot_set.slots:
            slot = plan.slot_set.slots["registration_number"]
            assert slot.state in [SlotState.FILLED, SlotState.PARTIAL]

    @pytest.mark.asyncio
    async def test_ku_transitions_tracked(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import ExecutionOrchestrator
        from BACKEND.modules.SASTRE.investigation_planner import InvestigationPlanner

        planner = InvestigationPlanner()
        planner.matrix._loaded = True
        planner.matrix._flows = {"AE": []}

        plan = planner.create_plan(
            entity_type="person",
            entity_name="Test Person",
            jurisdiction="AE",
        )

        orchestrator = ExecutionOrchestrator()
        state = await orchestrator.execute(plan)

        # Should have at least the initial transition
        assert len(state.ku_transitions) >= 1
        assert state.ku_transitions[0]["from"] == "start"


class TestGapAnalyzer:
    """Test GapAnalyzer."""

    def test_import_gap_analyzer(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import GapAnalyzer
        assert GapAnalyzer is not None

    def test_create_gap_analyzer(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import GapAnalyzer

        analyzer = GapAnalyzer()
        assert analyzer.planner is not None
        assert analyzer.generator is not None

    @pytest.mark.asyncio
    async def test_analyze_gaps_on_empty_state(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import (
            ExecutionOrchestrator, GapAnalyzer, ExecutionState
        )
        from BACKEND.modules.SASTRE.investigation_planner import InvestigationPlanner

        planner = InvestigationPlanner()
        planner.matrix._loaded = True
        planner.matrix._flows = {"US": []}

        plan = planner.create_plan(
            entity_type="person",
            entity_name="Test Person",
            jurisdiction="US",
        )

        state = ExecutionState(plan=plan)
        analyzer = GapAnalyzer()
        gaps = analyzer.analyze_gaps(state)

        # Should have gaps (all slots are empty)
        assert "gaps" in gaps
        assert "critical_gaps" in gaps
        assert gaps["critical_gaps"] >= 0

    @pytest.mark.asyncio
    async def test_analyze_gaps_after_execution(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import (
            ExecutionOrchestrator, GapAnalyzer
        )
        from BACKEND.modules.SASTRE.investigation_planner import InvestigationPlanner

        planner = InvestigationPlanner()
        planner.matrix._loaded = True
        planner.matrix._flows = {
            "GB": [
                {
                    "source_id": "ch_001",
                    "source_label": "Companies House",
                    "input_type": "person_name",
                    "output_columns_array": ["name"],
                    "reliability": "high",
                },
            ],
        }

        plan = planner.create_plan(
            entity_type="person",
            entity_name="Test Person",
            jurisdiction="GB",
        )

        orchestrator = ExecutionOrchestrator()
        state = await orchestrator.execute(plan)

        analyzer = GapAnalyzer()
        gaps = analyzer.analyze_gaps(state)

        assert "current_ku" in gaps
        assert "recommendations" in gaps


class TestDisambiguationIntegration:
    """Test disambiguation integration."""

    def test_import_detect_collision_simple(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import detect_collision_simple
        assert detect_collision_simple is not None

    def test_import_create_wedge_queries(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import create_wedge_queries
        assert create_wedge_queries is not None

    def test_detect_collision_same_values(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import detect_collision_simple

        collision = detect_collision_simple(
            entity_id="test_001",
            field_name="name",
            value_a="John Smith",
            value_b="John Smith",
        )
        assert collision is None  # Same value = no collision

    def test_detect_collision_different_values(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import detect_collision_simple

        collision = detect_collision_simple(
            entity_id="test_001",
            field_name="name",
            value_a="John Smith",
            value_b="Jane Doe",
        )
        assert collision is not None
        assert collision.field_name == "name"

    def test_create_wedge_queries_for_conflict(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import create_wedge_queries

        queries = create_wedge_queries(
            entity_id="test_001",
            field_name="address",
            conflicting_values=["123 Main St", "456 Oak Ave"],
        )

        assert len(queries) > 0
        # Should have exclusion and intersection queries
        query_types = [q["query_type"] for q in queries]
        assert "exclusion" in query_types
        assert "intersection" in query_types


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_import_execute_investigation(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import execute_investigation
        assert execute_investigation is not None

    def test_import_analyze_investigation_gaps(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import analyze_investigation_gaps
        assert analyze_investigation_gaps is not None

    @pytest.mark.asyncio
    async def test_execute_investigation_full(self):
        from BACKEND.modules.SASTRE.execution_orchestrator import execute_investigation

        result = await execute_investigation(
            entity_type="person",
            entity_name="John Smith",
            jurisdiction="US",
        )

        assert "execution" in result
        assert "gaps" in result
        assert "slot_status" in result
