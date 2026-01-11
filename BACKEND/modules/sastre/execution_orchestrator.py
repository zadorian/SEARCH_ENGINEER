"""
SASTRE Execution Orchestrator - Mock execution for testing.

DEPRECATION NOTICE:
-------------------
This module provides MOCK execution for testing purposes only.
For REAL investigations, use orchestrator/thin.py which integrates with:
- FullSastreInfrastructure (11 bridges, 200+ endpoints)
- CymonidesState (persistent graph storage)
- CognitiveGapAnalyzer (4-mode gap detection)
- Real API execution (not MockStepExecutor)

This module is kept for:
1. Unit testing plan execution flow
2. Testing slot feeding mechanics
3. Testing collision detection
4. Testing K-U quadrant transitions

For production investigations:
    from SASTRE.orchestrator import ThinOrchestrator, investigate
    result = await investigate("Who is John Smith?", project_id="mycase")

For testing:
    from SASTRE.execution_orchestrator import ExecutionOrchestrator, MockStepExecutor
    orchestrator = ExecutionOrchestrator()
    state = await orchestrator.execute(plan)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Awaitable
from enum import Enum
from datetime import datetime
import asyncio

from .contracts import (
    KUQuadrant, SlotState, SlotPriority,
    EntitySlot, EntitySlotSet, SufficiencyResult,
    Collision, CollisionType, derive_quadrant,
)
from .investigation_planner import (
    InvestigationPlan, PlanStep, QueryTier,
    InvestigationPlanner, QueryGenerator,
)

# Disambiguation functions - inline to avoid circular imports
def detect_collision_simple(
    entity_id: str,
    field_name: str,
    value_a: str,
    value_b: str,
) -> Optional[Collision]:
    """Simple collision detection for slot feeding."""
    if value_a == value_b:
        return None
    str_a = str(value_a).lower().strip()
    str_b = str(value_b).lower().strip()
    if str_a == str_b:
        return None
    return Collision(
        entity_a_id=entity_id,
        entity_b_id=f"{entity_id}_{field_name}",
        collision_type=CollisionType.VALUE_CONFLICT,
        similarity_score=0.0,
        field_name=field_name,
        value_a=str(value_a),
        value_b=str(value_b),
    )


def create_wedge_queries(
    entity_id: str,
    field_name: str,
    conflicting_values: List[Any],
) -> List[Dict[str, Any]]:
    """Create wedge queries to resolve conflicting values."""
    queries = []
    if len(conflicting_values) < 2:
        return queries
    for i, val_a in enumerate(conflicting_values):
        for val_b in conflicting_values[i+1:]:
            str_a = str(val_a)
            str_b = str(val_b)
            queries.append({
                "query_type": "exclusion",
                "target": f"{entity_id}.{field_name}",
                "query": f'"{str_a}" NOT "{str_b}"',
            })
            queries.append({
                "query_type": "intersection",
                "target": f"{entity_id}.{field_name}",
                "query": f'"{str_a}" AND "{str_b}"',
            })
    return queries


# =============================================================================
# Execution State
# =============================================================================

class StepStatus(Enum):
    """Status of a plan step execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepResult:
    """Result of executing a single step."""
    step_id: str
    status: StepStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    data: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    slots_fed: List[str] = field(default_factory=list)
    collisions_detected: List[Collision] = field(default_factory=list)

    @property
    def duration_ms(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds() * 1000
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "data_keys": list(self.data.keys()),
            "errors": self.errors,
            "slots_fed": self.slots_fed,
            "collisions": len(self.collisions_detected),
        }


@dataclass
class ExecutionState:
    """Complete state of plan execution."""
    plan: InvestigationPlan
    step_results: Dict[str, StepResult] = field(default_factory=dict)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    ku_transitions: List[Dict[str, str]] = field(default_factory=list)
    all_collisions: List[Collision] = field(default_factory=list)
    sufficiency_checks: List[SufficiencyResult] = field(default_factory=list)
    child_plans: List["InvestigationPlan"] = field(default_factory=list)  # Cascaded investigations

    @property
    def is_complete(self) -> bool:
        return all(
            r.status in [StepStatus.COMPLETED, StepStatus.SKIPPED, StepStatus.FAILED]
            for r in self.step_results.values()
        )

    @property
    def success_rate(self) -> float:
        if not self.step_results:
            return 0.0
        completed = sum(1 for r in self.step_results.values() if r.status == StepStatus.COMPLETED)
        return completed / len(self.step_results)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.plan.entity_id,
            "entity_name": self.plan.entity_name,
            "jurisdiction": self.plan.jurisdiction,
            "total_steps": len(self.plan.steps),
            "completed_steps": sum(1 for r in self.step_results.values() if r.status == StepStatus.COMPLETED),
            "failed_steps": sum(1 for r in self.step_results.values() if r.status == StepStatus.FAILED),
            "success_rate": f"{self.success_rate:.0%}",
            "collisions_detected": len(self.all_collisions),
            "ku_transitions": self.ku_transitions,
            "step_results": {k: v.to_dict() for k, v in self.step_results.items()},
        }


# =============================================================================
# Mock Executor (for testing without real APIs)
# =============================================================================

class MockStepExecutor:
    """Mock executor for testing - returns simulated data."""

    async def execute(self, step: PlanStep) -> Dict[str, Any]:
        """Simulate executing a step."""
        await asyncio.sleep(0.01)  # Simulate network delay

        # Generate mock data based on output columns
        data = {}
        for col in step.output_columns:
            if col in ["name", "full_name", "person_name"]:
                data[col] = f"Mock Person for {step.input_value}"
            elif col in ["email", "email_address"]:
                data[col] = f"mock_{step.input_value.lower().replace(' ', '.')}@example.com"
            elif col in ["phone", "phone_number"]:
                data[col] = "+1-555-0123"
            elif col in ["registration_number", "company_number"]:
                data[col] = f"REG-{hash(step.input_value) % 100000:05d}"
            elif col in ["directors", "officers", "company_officers"]:
                data[col] = ["Director A", "Director B"]
            elif col in ["shareholders"]:
                data[col] = ["Shareholder X (50%)", "Shareholder Y (50%)"]
            elif col in ["address", "registered_address"]:
                data[col] = f"123 Mock Street, {step.country}"
            elif col in ["litigation_records", "court_cases"]:
                data[col] = []  # Empty - no cases found
            else:
                data[col] = f"mock_{col}_value"

        return {
            "source": step.source_label,
            "reliability": step.reliability,
            "data": data,
        }


# =============================================================================
# Execution Orchestrator
# =============================================================================

class ExecutionOrchestrator:
    """
    Orchestrates the execution of investigation plans.

    Usage:
        orchestrator = ExecutionOrchestrator()
        state = await orchestrator.execute(plan)

        # Or with real executor:
        orchestrator = ExecutionOrchestrator(executor=my_real_executor)
        state = await orchestrator.execute(plan)
    """

    def __init__(
        self,
        executor: Optional[Any] = None,
        on_step_complete: Optional[Callable[[StepResult], Awaitable[None]]] = None,
        on_collision: Optional[Callable[[Collision], Awaitable[None]]] = None,
        on_slot_fed: Optional[Callable[[EntitySlot, Any, "InvestigationPlan", "ExecutionState"], Awaitable[None]]] = None,
        on_cascade: Optional[Callable[[EntitySlot, Any, "InvestigationPlan"], Awaitable[Optional["InvestigationPlan"]]]] = None,
    ):
        """
        Initialize the orchestrator with optional callbacks.

        Args:
            executor: Step executor (mock if not provided)
            on_step_complete: Called after each step completes
            on_collision: Called when slot value conflicts detected
            on_slot_fed: Called when a slot is fed a value (with full context)
            on_cascade: Called to spawn child investigations when entity discovered
        """
        self.executor = executor or MockStepExecutor()
        self.on_step_complete = on_step_complete
        self.on_collision = on_collision
        self.on_slot_fed = on_slot_fed
        self.on_cascade = on_cascade

    async def execute(self, plan: InvestigationPlan) -> ExecutionState:
        """
        Execute all steps in an investigation plan.

        Args:
            plan: The investigation plan to execute

        Returns:
            ExecutionState with all results
        """
        state = ExecutionState(plan=plan)
        state.started_at = datetime.now()

        # Track initial K-U quadrant
        initial_ku = plan.ku_quadrant
        state.ku_transitions.append({
            "from": "start",
            "to": initial_ku.value,
            "reason": "initial",
        })

        # Build dependency graph
        step_deps = {s.step_id: set(s.depends_on) for s in plan.steps}
        pending_steps = {s.step_id: s for s in plan.steps}
        completed_step_ids = set()

        # Execute steps in dependency order
        while pending_steps:
            # Find steps with all dependencies satisfied
            ready_steps = [
                step for step_id, step in pending_steps.items()
                if step_deps[step_id].issubset(completed_step_ids)
            ]

            if not ready_steps:
                # No ready steps but still pending = dependency cycle or all failed deps
                for step_id in list(pending_steps.keys()):
                    result = StepResult(
                        step_id=step_id,
                        status=StepStatus.SKIPPED,
                        errors=["Dependencies not satisfied"],
                    )
                    state.step_results[step_id] = result
                    del pending_steps[step_id]
                break

            # Execute ready steps (could parallelize here)
            for step in ready_steps:
                result = await self._execute_step(step, plan, state)
                state.step_results[step.step_id] = result

                if result.status == StepStatus.COMPLETED:
                    completed_step_ids.add(step.step_id)

                del pending_steps[step.step_id]

                # Callback
                if self.on_step_complete:
                    await self.on_step_complete(result)

            # Check K-U quadrant transition
            new_ku = self._compute_current_ku(plan, state)
            if new_ku != initial_ku:
                state.ku_transitions.append({
                    "from": initial_ku.value,
                    "to": new_ku.value,
                    "reason": f"after {len(completed_step_ids)} steps",
                })
                initial_ku = new_ku

            # Check sufficiency
            sufficiency = self._check_sufficiency(plan, state)
            state.sufficiency_checks.append(sufficiency)

            if sufficiency.is_complete:
                # Early exit if sufficiency met
                for step_id in list(pending_steps.keys()):
                    result = StepResult(
                        step_id=step_id,
                        status=StepStatus.SKIPPED,
                        errors=["Sufficiency already met"],
                    )
                    state.step_results[step_id] = result
                break

        state.completed_at = datetime.now()
        return state

    async def _execute_step(
        self,
        step: PlanStep,
        plan: InvestigationPlan,
        state: ExecutionState,
    ) -> StepResult:
        """Execute a single step and process results."""
        result = StepResult(step_id=step.step_id, status=StepStatus.RUNNING)
        result.started_at = datetime.now()

        try:
            # Handle chained input - get value from previous step
            input_value = step.input_value
            if input_value.startswith("[from"):
                # Parse: [from step_001.column_name]
                import re
                match = re.match(r'\[from (\w+)\.(\w+)\]', input_value)
                if match:
                    from_step, from_col = match.groups()
                    if from_step in state.step_results:
                        prev_data = state.step_results[from_step].data.get("data", {})
                        input_value = prev_data.get(from_col, input_value)

            # Execute the step
            step_data = await self.executor.execute(step)
            result.data = step_data
            result.status = StepStatus.COMPLETED

            # Feed slots with results
            if plan.slot_set and "data" in step_data:
                for col, value in step_data["data"].items():
                    if col in plan.slot_set.slots:
                        slot = plan.slot_set.slots[col]

                        # Check for collision before feeding
                        if slot.values and value not in slot.values:
                            collision = Collision(
                                entity_a_id=plan.entity_id,
                                entity_b_id=f"{plan.entity_id}_{col}",
                                collision_type=CollisionType.VALUE_CONFLICT,
                                similarity_score=0.5,
                                field_name=col,
                                value_a=str(slot.values[0]) if slot.values else "",
                                value_b=str(value),
                            )
                            result.collisions_detected.append(collision)
                            state.all_collisions.append(collision)

                            if self.on_collision:
                                await self.on_collision(collision)

                        # Feed the slot
                        slot.feed(value, step.source_label)
                        result.slots_fed.append(col)

                        # Notify slot fed with full context
                        if self.on_slot_fed:
                            await self.on_slot_fed(slot, value, plan, state)

                        # Check for cascade trigger (spawn child investigation)
                        if self.on_cascade and slot.field_type in ("entity", "person", "company"):
                            child_plan = await self.on_cascade(slot, value, plan)
                            if child_plan:
                                state.child_plans.append(child_plan)

        except Exception as e:
            result.status = StepStatus.FAILED
            result.errors.append(str(e))

        result.completed_at = datetime.now()
        return result

    def _compute_current_ku(
        self,
        plan: InvestigationPlan,
        state: ExecutionState,
    ) -> KUQuadrant:
        """Compute current K-U quadrant based on what's known."""
        if not plan.slot_set:
            return plan.ku_quadrant

        # Subject is "known" if any critical slot is filled
        critical_filled = any(
            s.state in [SlotState.FILLED, SlotState.PARTIAL]
            for s in plan.slot_set.slots.values()
            if s.priority == SlotPriority.CRITICAL
        )

        # Location is known if jurisdiction was provided
        location_known = bool(plan.jurisdiction and plan.jurisdiction != "UNKNOWN")

        return derive_quadrant(critical_filled, location_known)

    def _check_sufficiency(
        self,
        plan: InvestigationPlan,
        state: ExecutionState,
    ) -> SufficiencyResult:
        """Check current sufficiency status."""
        if not plan.slot_set:
            return SufficiencyResult()

        # Core fields populated
        critical_slots = [
            s for s in plan.slot_set.slots.values()
            if s.priority == SlotPriority.CRITICAL
        ]
        core_filled = all(
            s.state in [SlotState.FILLED, SlotState.PARTIAL, SlotState.VOID]
            for s in critical_slots
        )

        # High-weight absences
        hungry_high = [
            s for s in plan.slot_set.get_hungry_slots()
            if s.priority in [SlotPriority.CRITICAL, SlotPriority.HIGH]
        ]

        # Disambiguation resolved
        unresolved_collisions = [
            c for c in state.all_collisions
            if not hasattr(c, 'resolved') or not c.resolved
        ]

        return SufficiencyResult(
            core_fields_populated=core_filled,
            tasking_headers_addressed=len(state.step_results) > 0,
            no_high_weight_absences=len(hungry_high) == 0,
            disambiguation_resolved=len(unresolved_collisions) == 0,
            surprising_ands_processed=True,  # TODO: implement
        )


# =============================================================================
# Slot Gap Analyzer - Routes next queries based on K-U Matrix
# =============================================================================

class SlotGapAnalyzer:
    """
    Simple slot-based gap analyzer for execution state.

    For FULL 4-mode cognitive gap analysis (NARRATIVE/SUBJECT/LOCATION/NEXUS),
    use CognitiveGapAnalyzer from gap_analyzer.py:

        from SASTRE.gap_analyzer import CognitiveGapAnalyzer
        analyzer = CognitiveGapAnalyzer()
        result = analyzer.analyze(document)

    This analyzer is simpler - it looks at hungry/contested slots and
    uses K-U Matrix to determine:
    - VERIFY: Known subject + location → confirm/validate
    - TRACE: Known subject, unknown location → follow trails
    - EXTRACT: Unknown subject, known location → harvest data
    - DISCOVER: Unknown subject + location → broad search
    """

    def __init__(self):
        self.planner = InvestigationPlanner()
        self.generator = QueryGenerator()

    def analyze_gaps(self, state: ExecutionState) -> Dict[str, Any]:
        """
        Analyze gaps in current execution state.

        Returns:
            Gap analysis with recommended next steps
        """
        plan = state.plan
        if not plan.slot_set:
            return {"gaps": [], "recommendations": []}

        # Get hungry slots grouped by priority
        hungry = plan.slot_set.get_hungry_slots()
        contested = plan.slot_set.get_contested_slots()

        gaps = []
        recommendations = []

        # Critical gaps first
        critical_hungry = [s for s in hungry if s.priority == SlotPriority.CRITICAL]
        for slot in critical_hungry:
            gap = {
                "field": slot.field_name,
                "priority": "critical",
                "hunger": slot.hunger,
                "ku_action": self._ku_action_for_gap(slot, plan),
            }
            gaps.append(gap)

            # Generate recommendation
            rec = self._recommend_for_gap(slot, plan, state)
            if rec:
                recommendations.append(rec)

        # High priority gaps
        high_hungry = [s for s in hungry if s.priority == SlotPriority.HIGH]
        for slot in high_hungry[:5]:  # Limit to top 5
            gap = {
                "field": slot.field_name,
                "priority": "high",
                "hunger": slot.hunger,
                "ku_action": self._ku_action_for_gap(slot, plan),
            }
            gaps.append(gap)

        # Contested slots need disambiguation
        for slot in contested:
            gap = {
                "field": slot.field_name,
                "priority": "contested",
                "values": slot.values[:3],
                "ku_action": "disambiguate",
            }
            gaps.append(gap)

            recommendations.append({
                "action": "disambiguate",
                "field": slot.field_name,
                "wedge_queries": create_wedge_queries(
                    plan.entity_id,
                    slot.field_name,
                    slot.values,
                ),
            })

        return {
            "total_gaps": len(gaps),
            "critical_gaps": len(critical_hungry),
            "contested_fields": len(contested),
            "current_ku": self._current_ku(plan, state).value,
            "gaps": gaps,
            "recommendations": recommendations[:10],
        }

    def _ku_action_for_gap(self, slot: EntitySlot, plan: InvestigationPlan) -> str:
        """Determine K-U action for a gap."""
        # If we have the entity name, we're tracing
        if plan.entity_name:
            if plan.jurisdiction and plan.jurisdiction != "UNKNOWN":
                return "verify"  # Known subject + location
            return "trace"  # Known subject, unknown location
        else:
            if plan.jurisdiction and plan.jurisdiction != "UNKNOWN":
                return "extract"  # Unknown subject, known location
            return "discover"  # Unknown both

    def _recommend_for_gap(
        self,
        slot: EntitySlot,
        plan: InvestigationPlan,
        state: ExecutionState,
    ) -> Optional[Dict[str, Any]]:
        """Generate recommendation for filling a gap."""
        # Find steps that feed this slot but haven't been tried
        feeding_steps = [
            s for s in plan.steps
            if slot.field_name in s.feeds_slots
            and s.step_id not in state.step_results
        ]

        if feeding_steps:
            best_step = max(feeding_steps, key=lambda s: s.strength)
            return {
                "action": "execute_step",
                "step_id": best_step.step_id,
                "source": best_step.source_label,
                "expected_output": slot.field_name,
            }

        # Suggest new query
        query = self.generator.generate_for_entity(
            plan.entity_name,
            plan.entity_type,
            f"find {slot.field_name}",
        )

        return {
            "action": "new_query",
            "target_field": slot.field_name,
            "query": query.primary,
            "variations": query.variations[:3],
        }

    def _current_ku(self, plan: InvestigationPlan, state: ExecutionState) -> KUQuadrant:
        """Get current K-U quadrant."""
        if not plan.slot_set:
            return plan.ku_quadrant

        critical_filled = any(
            s.state in [SlotState.FILLED, SlotState.PARTIAL]
            for s in plan.slot_set.slots.values()
            if s.priority == SlotPriority.CRITICAL
        )
        location_known = bool(plan.jurisdiction and plan.jurisdiction != "UNKNOWN")
        return derive_quadrant(critical_filled, location_known)


# Backward-compatible alias
GapAnalyzer = SlotGapAnalyzer


# =============================================================================
# Convenience Functions
# =============================================================================

async def execute_investigation(
    entity_type: str,
    entity_name: str,
    jurisdiction: str,
    known_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute a full investigation and return results.

    Example:
        result = await execute_investigation(
            entity_type="person",
            entity_name="John Smith",
            jurisdiction="AE",
        )
    """
    planner = InvestigationPlanner()
    plan = planner.create_plan(
        entity_type=entity_type,
        entity_name=entity_name,
        jurisdiction=jurisdiction,
        known_data=known_data,
    )

    orchestrator = ExecutionOrchestrator()
    state = await orchestrator.execute(plan)

    # Analyze remaining gaps
    analyzer = GapAnalyzer()
    gaps = analyzer.analyze_gaps(state)

    return {
        "execution": state.to_dict(),
        "gaps": gaps,
        "slot_status": {
            k: {
                "state": v.state.value,
                "values": v.values[:3],
                "hunger": v.hunger,
            }
            for k, v in plan.slot_set.slots.items()
        } if plan.slot_set else {},
    }


def analyze_investigation_gaps(state: ExecutionState) -> Dict[str, Any]:
    """Analyze gaps in an investigation state."""
    analyzer = GapAnalyzer()
    return analyzer.analyze_gaps(state)
