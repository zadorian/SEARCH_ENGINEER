#!/usr/bin/env python3
"""
SASTRE ThinOrchestrator - Lightweight Investigation Runner

Orchestrates investigations using:
- EdithBridge for routing, context, validation
- ComplexityScouter for adaptive model selection
- DecisionTraceCollector for audit trails
- ResilientExecutor for fallback handling

The "Thin" philosophy: minimal state, maximum delegation.
All intelligence lives in EDITH templates; orchestrator just executes.

Usage:
    orchestrator = ThinOrchestrator()
    result = await orchestrator.investigate("DD on UK company Test Ltd")

    # Or with streaming
    async for event in orchestrator.investigate_stream("DD on BVI company"):
        print(event)
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, AsyncGenerator, Callable
from enum import Enum

from ..bridges.edith_bridge import EdithBridge
from ..bridges.action_handlers import action_registry, execute_action
from ..narrative.decision_trace import DecisionTraceCollector, SearchOutcome
from ..execution.resilience import ResilientExecutor, FALLBACK_CHAINS
from .complexity_scouter import ComplexityScouter

# Import WatcherBridge using importlib to avoid naming conflict
# (bridges/ directory takes precedence over bridges.py)
import importlib.util
from pathlib import Path
_bridges_file = Path(__file__).parent.parent / "bridges.py"
_spec = importlib.util.spec_from_file_location("bridges_module", _bridges_file)
_bridges_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bridges_module)
WatcherBridge = _bridges_module.WatcherBridge
CymonidesBridge = _bridges_module.CymonidesBridge  # Also get CymonidesBridge

logger = logging.getLogger(__name__)


class InvestigationPhase(Enum):
    """Phases of an investigation."""
    ROUTING = "routing"
    COMPLEXITY = "complexity"
    CONTEXT = "context"
    WATCHER_SETUP = "watcher_setup"  # Create watchers for document sections
    EXECUTION = "execution"
    VALIDATION = "validation"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class InvestigationState:
    """Current state of an investigation."""
    investigation_id: str
    query: str
    phase: InvestigationPhase = InvestigationPhase.ROUTING
    project_id: Optional[str] = None  # Graph project ID for watcher creation
    document_id: Optional[str] = None  # Parent document ID for watchers
    jurisdiction: Optional[str] = None
    genre: Optional[str] = None
    entity: Optional[str] = None
    complexity_score: float = 0.5
    model: str = "claude-sonnet-4-5-20250929"
    max_iterations: int = 10
    allowed_actions: List[str] = field(default_factory=list)
    dd_sections: List[str] = field(default_factory=list)  # Sections from template
    dead_end_warnings: List[Dict] = field(default_factory=list)
    arbitrage_routes: List[Dict] = field(default_factory=list)
    watcher_ids: List[str] = field(default_factory=list)  # Created watcher IDs
    results: Dict[str, List[Dict]] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)

    def elapsed_ms(self) -> float:
        return (time.time() - self.start_time) * 1000


@dataclass
class InvestigationEvent:
    """Event emitted during investigation."""
    phase: InvestigationPhase
    action: str
    status: str  # "started", "completed", "failed", "skipped"
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization."""
        return {
            "phase": self.phase.value,
            "action": self.action,
            "status": self.status,
            "data": self.data,
            "timestamp": self.timestamp,
        }


class ThinOrchestrator:
    """
    Lightweight investigation orchestrator.

    Delegates all intelligence to EDITH templates.
    Focuses on execution flow and error handling.

    Watcher Integration:
    - After context composition, creates watchers for each DD section
    - Watchers monitor for findings that match section criteria
    - Findings are routed back to document sections in real-time
    """

    def __init__(
        self,
        edith: Optional[EdithBridge] = None,
        scouter: Optional[ComplexityScouter] = None,
        executor: Optional[ResilientExecutor] = None,
        watcher: Optional[WatcherBridge] = None,
        cymonides: Optional[Any] = None,
    ):
        """
        Initialize orchestrator with optional dependency injection.

        Args:
            edith: EDITH bridge (created if not provided)
            scouter: Complexity scouter (created if not provided)
            executor: Resilient executor (created if not provided)
            watcher: Watcher bridge for section monitoring (created if not provided)
            cymonides: Cymonides bridge for graph operations (created if not provided)
        """
        self.edith = edith or EdithBridge()
        self.scouter = scouter or ComplexityScouter()
        self.executor = executor or ResilientExecutor()
        self.watcher = watcher or WatcherBridge()
        self.cymonides = cymonides or CymonidesBridge()

        # Wire action handlers to resilient executor
        self._wire_action_handlers()

    def _wire_action_handlers(self):
        """Wire action handlers from registry to resilient executor."""
        # Register handlers as primary sources for each action
        for action, handler in action_registry._handlers.items():
            # Create closure to capture handler
            def make_handler(h):
                async def executor_fn(action_name: str, context: Dict) -> List[Dict]:
                    try:
                        return await h.execute(context)
                    except Exception as e:
                        logger.warning(f"Handler failed: {e}")
                        return []
                return executor_fn

            # Register with the source name from FALLBACK_CHAINS
            from ..execution.resilience import FALLBACK_CHAINS
            chain = FALLBACK_CHAINS.get(action)
            if chain:
                self.executor.register_executor(chain.primary, make_handler(handler))
                # Also register fallback sources that match our handlers
                for fallback_source, _ in chain.fallbacks:
                    if fallback_source not in ["manual_flag", "exhausted"]:
                        self.executor.register_executor(fallback_source, make_handler(handler))

    def register_action_handler(self, action: str, handler: Any):
        """Register a custom handler for an ALLOWED_ACTION."""
        action_registry.register(handler)
        # Use default argument to capture handler by value, avoiding closure issue
        async def executor_fn(a: str, c: Dict, h=handler) -> List[Dict]:
            try:
                return await h.execute(c)
            except Exception as e:
                logger.warning(f"Handler failed: {e}")
                return []
        self.executor.register_executor(action, executor_fn)

    def _check_sufficiency(self, state: InvestigationState) -> Dict[str, Any]:
        """
        Check if investigation is sufficient based on current results.

        Returns dict with:
            - is_sufficient: bool
            - score: float (0.0-1.0)
            - gaps: list of unfilled sections
            - reason: str explanation
        """
        if not state.dd_sections:
            # No sections defined - consider sufficient after any results
            has_results = any(len(r) > 0 for r in state.results.values())
            return {
                "is_sufficient": has_results,
                "score": 1.0 if has_results else 0.0,
                "gaps": [],
                "reason": "No template sections defined"
            }

        # Check which sections have results
        filled_sections = set()
        for action, results in state.results.items():
            if results:
                # Map actions to sections (simplified mapping)
                section = self._action_to_section(action)
                if section:
                    filled_sections.add(section)

        # Calculate gaps
        all_sections = set(state.dd_sections)
        gaps = list(all_sections - filled_sections)

        # Calculate score
        score = len(filled_sections) / len(all_sections) if all_sections else 1.0

        # Sufficient if 80% of sections have content
        is_sufficient = score >= 0.8

        return {
            "is_sufficient": is_sufficient,
            "score": score,
            "gaps": gaps,
            "filled": list(filled_sections),
            "reason": f"{len(filled_sections)}/{len(all_sections)} sections filled"
        }

    def _action_to_section(self, action: str) -> Optional[str]:
        """Map an ALLOWED_ACTION to a template section."""
        action_section_map = {
            "SEARCH_REGISTRY": "OVERVIEW",
            "SEARCH_OFFICERS": "CORPORATE_AFFILIATIONS",
            "SEARCH_SHAREHOLDERS": "KEY_RELATIONSHIPS",
            "SEARCH_FINANCIALS": "SOURCE_OF_WEALTH",
            "SEARCH_LITIGATION": "LITIGATION",
            "SEARCH_SANCTIONS": "SANCTIONS_WATCHLISTS",
            "SEARCH_ADVERSE_MEDIA": "ADVERSE_MEDIA",
            "SEARCH_NEWS": "ADVERSE_MEDIA",
            "SEARCH_PEP": "REGULATORY",
            "SEARCH_INSOLVENCY": "BANKRUPTCY_INSOLVENCY",
            "SEARCH_REGULATORY": "REGULATORY",
        }
        return action_section_map.get(action.upper())

    async def investigate(self, query: str) -> Dict[str, Any]:
        """
        Run a complete investigation.

        Args:
            query: Natural language investigation query

        Returns:
            Dict with investigation results
        """
        events = []
        async for event in self.investigate_stream(query):
            events.append(event)

        # Extract final state from events
        final_event = events[-1] if events else None
        return {
            "status": final_event.status if final_event else "error",
            "events": [e.to_dict() for e in events],
        }

    async def investigate_stream(
        self,
        query: str,
        project_id: Optional[str] = None,
        document_id: Optional[str] = None,
    ) -> AsyncGenerator[InvestigationEvent, None]:
        """
        Run investigation with streaming events.

        Yields InvestigationEvent for each phase/action.

        Args:
            query: Natural language investigation query
            project_id: Graph project ID (required for watcher creation)
            document_id: Parent document ID (watchers attach findings here)

        Yields:
            InvestigationEvent for each step
        """
        import uuid
        investigation_id = uuid.uuid4().hex[:12]

        state = InvestigationState(
            investigation_id=investigation_id,
            query=query,
            project_id=project_id or f"proj_{investigation_id}",
            document_id=document_id,
        )
        trace = DecisionTraceCollector(investigation_id)

        # Phase 1: Routing
        yield InvestigationEvent(
            phase=InvestigationPhase.ROUTING,
            action="route_investigation",
            status="started",
        )

        try:
            routing = await self.edith.route_investigation(query)
            state.jurisdiction = routing.get("jurisdiction_id")
            state.genre = routing.get("genre_id")
            state.entity = routing.get("entity_name", "Unknown")
            state.dead_end_warnings = routing.get("dead_end_warnings", [])

            trace.record_search(
                "ROUTE_INVESTIGATION",
                ["EDITH route.py"],
                "positive" if routing.get("status") == "exact" else "partial",
                jurisdiction=state.jurisdiction or "",
            )

            # Log dead-end warnings
            for warning in state.dead_end_warnings:
                trace.record_skipped(
                    warning.get("action", "UNKNOWN"),
                    warning.get("reason", "Dead-end"),
                    state.jurisdiction or "",
                )

            yield InvestigationEvent(
                phase=InvestigationPhase.ROUTING,
                action="route_investigation",
                status="completed",
                data={
                    "jurisdiction": state.jurisdiction,
                    "genre": state.genre,
                    "entity": state.entity,
                    "dead_ends": len(state.dead_end_warnings),
                },
            )

            if routing.get("status") == "missing":
                yield InvestigationEvent(
                    phase=InvestigationPhase.ERROR,
                    action="route_investigation",
                    status="failed",
                    data={"error": "No template coverage for query"},
                )
                return

        except Exception as e:
            logger.error(f"Routing failed: {e}")
            yield InvestigationEvent(
                phase=InvestigationPhase.ERROR,
                action="route_investigation",
                status="failed",
                data={"error": str(e)},
            )
            return

        # Phase 2: Complexity Assessment
        yield InvestigationEvent(
            phase=InvestigationPhase.COMPLEXITY,
            action="assess_complexity",
            status="started",
        )

        try:
            score = await self.scouter.score(query, routing)
            rec = self.scouter.get_recommendation(score)
            state.complexity_score = score
            state.model = rec["model"]
            state.max_iterations = rec["max_iterations"]

            yield InvestigationEvent(
                phase=InvestigationPhase.COMPLEXITY,
                action="assess_complexity",
                status="completed",
                data={
                    "score": round(score, 3),
                    "level": rec["complexity_level"],
                    "model": state.model.split("-")[1],  # Extract model name
                    "max_iterations": state.max_iterations,
                },
            )

        except Exception as e:
            logger.warning(f"Complexity assessment failed: {e}, using defaults")
            yield InvestigationEvent(
                phase=InvestigationPhase.COMPLEXITY,
                action="assess_complexity",
                status="completed",
                data={"score": 0.5, "level": "medium", "error": str(e)},
            )

        # Phase 3: Context Composition
        yield InvestigationEvent(
            phase=InvestigationPhase.CONTEXT,
            action="compose_context",
            status="started",
        )

        try:
            context = await self.edith.compose_context(
                state.jurisdiction,
                state.genre,
                state.entity,
            )

            if context.get("status") == "success":
                state.allowed_actions = context.get("allowed_actions", [])
                state.arbitrage_routes = context.get("arbitrage_routes", [])
                state.dd_sections = context.get("dd_sections", [])

                yield InvestigationEvent(
                    phase=InvestigationPhase.CONTEXT,
                    action="compose_context",
                    status="completed",
                    data={
                        "allowed_actions": len(state.allowed_actions),
                        "arbitrage_routes": len(state.arbitrage_routes),
                        "dd_sections": len(state.dd_sections),
                    },
                )
            else:
                logger.error(f"Context composition failed. Response: {json.dumps(context, default=str)}")
                yield InvestigationEvent(
                    phase=InvestigationPhase.ERROR,
                    action="compose_context",
                    status="failed",
                    data={"error": context.get("error", f"Context compilation failed: {context}")},
                )
                return

        except Exception as e:
            logger.error(f"Context composition failed: {e}")
            yield InvestigationEvent(
                phase=InvestigationPhase.ERROR,
                action="compose_context",
                status="failed",
                data={"error": str(e)},
            )
            return

        # Phase 4: Watcher Setup (create watchers for DD sections)
        yield InvestigationEvent(
            phase=InvestigationPhase.WATCHER_SETUP,
            action="create_watchers",
            status="started",
            data={"sections": len(state.dd_sections)},
        )

        try:
            # Resolve/Create Subject Node for Watcher Context
            subject_node_id = None
            if state.entity and state.project_id:
                try:
                    # Check if node exists or create it
                    # We use 'create_node' which is idempotent-ish (returns ID) or we should check first.
                    # CymonidesBridge.create_node returns the node_id.
                    subject_node_id = await self.cymonides.create_node(
                        project_id=state.project_id,
                        label=state.entity,
                        node_type="company" if state.genre and "company" in state.genre else "person",
                        node_class="subject"
                    )
                    logger.info(f"Resolved Subject Node: {subject_node_id}")
                except Exception as e:
                    logger.warning(f"Failed to resolve subject node: {e}")

            watchers_created = 0
            for section in state.dd_sections:
                # Determine watcher type based on section
                section_lower = section.lower()

                # Create appropriate watcher type
                result = None
                if "sanctions" in section_lower or "pep" in section_lower:
                    # Topic watcher for sanctions/PEP monitoring
                    result = await self.watcher.create_topic_watcher(
                        project_id=state.project_id,
                        label=section,
                        monitored_topic="sanctions" if "sanctions" in section_lower else "pep",
                        monitored_entities=[state.entity] if state.entity else None,
                        jurisdiction_filter=[state.jurisdiction] if state.jurisdiction else None,
                        parent_document_id=state.document_id,
                    )
                elif "litigation" in section_lower or "court" in section_lower:
                    # Event watcher for litigation/court cases
                    result = await self.watcher.create_event_watcher(
                        project_id=state.project_id,
                        monitored_event="lawsuit",
                        label=section,
                        monitored_entities=[state.entity] if state.entity else None,
                        parent_document_id=state.document_id,
                    )
                elif "director" in section_lower or "officer" in section_lower:
                    # Entity watcher for persons
                    result = await self.watcher.create_entity_watcher(
                        project_id=state.project_id,
                        label=section,
                        monitored_types=["person"],
                        role_filter=["director", "officer", "ceo", "cfo", "coo"],
                        parent_document_id=state.document_id,
                    )
                elif "ownership" in section_lower or "shareholder" in section_lower:
                    # Entity watcher for companies
                    result = await self.watcher.create_entity_watcher(
                        project_id=state.project_id,
                        label=section,
                        monitored_types=["company"],
                        jurisdiction_filter=[state.jurisdiction] if state.jurisdiction else None,
                        parent_document_id=state.document_id,
                    )
                else:
                    # Generic header-based watcher
                    # Descriptive naming for better observability
                    watcher_name = f"{section} ({state.entity})" if state.entity else section
                    
                    # Context-rich query for better retrieval
                    if state.entity and state.jurisdiction:
                        watcher_query = f"{section} for {state.entity} in {state.jurisdiction}"
                    elif state.entity:
                        watcher_query = f"{state.entity} {section}"
                    else:
                        watcher_query = section

                    result = await self.watcher.create(
                        name=watcher_name,
                        project_id=state.project_id,
                        query=watcher_query,
                        parent_document_id=state.document_id,
                    )

                if result and not result.get("error"):
                    watcher_id = result.get("id") or result.get("watcherId")
                    if watcher_id:
                        state.watcher_ids.append(watcher_id)
                        watchers_created += 1
                        
                        # Link watcher to subject node if available
                        if subject_node_id:
                            try:
                                await self.watcher.add_context(watcher_id, subject_node_id)
                            except Exception as e:
                                logger.warning(f"Failed to add context to watcher {watcher_id}: {e}")

            yield InvestigationEvent(
                phase=InvestigationPhase.WATCHER_SETUP,
                action="create_watchers",
                status="completed",
                data={
                    "watchers_created": watchers_created,
                    "watcher_ids": state.watcher_ids,
                },
            )

        except Exception as e:
            logger.warning(f"Watcher setup failed (non-fatal): {e}")
            yield InvestigationEvent(
                phase=InvestigationPhase.WATCHER_SETUP,
                action="create_watchers",
                status="completed",  # Non-fatal - continue without watchers
                data={"error": str(e), "watchers_created": 0},
            )

        # Phase 5: Execute Actions (with iteration loop)
        iteration = 0
        executed_actions = set()  # Track which actions we've run

        while iteration < state.max_iterations:
            iteration += 1

            yield InvestigationEvent(
                phase=InvestigationPhase.EXECUTION,
                action="execute_actions",
                status="started",
                data={
                    "iteration": iteration,
                    "max_iterations": state.max_iterations,
                    "total_actions": len(state.allowed_actions),
                },
            )

            # Filter out dead-end actions and already-executed actions
            dead_end_actions = {w.get("action") for w in state.dead_end_warnings}
            executable_actions = [
                a for a in state.allowed_actions
                if a not in dead_end_actions and a not in executed_actions
            ]

            if not executable_actions:
                # No more actions to execute
                yield InvestigationEvent(
                    phase=InvestigationPhase.EXECUTION,
                    action="execute_actions",
                    status="completed",
                    data={"iteration": iteration, "reason": "no_more_actions"},
                )
                break

            for action in executable_actions:
                yield InvestigationEvent(
                    phase=InvestigationPhase.EXECUTION,
                    action=action,
                    status="started",
                )

                start_time = time.time()
                executed_actions.add(action)  # Mark as executed

                try:
                    results, source = await self.executor.execute_with_fallback(
                        action,
                        {
                            "entity": state.entity,
                            "jurisdiction": state.jurisdiction,
                            "genre": state.genre,
                        },
                    )

                    duration_ms = (time.time() - start_time) * 1000

                    if results:
                        state.results[action] = results
                        trace.record_search(
                            action,
                            [source],
                            "positive",
                            results_count=len(results),
                            duration_ms=duration_ms,
                            jurisdiction=state.jurisdiction,
                        )
                        yield InvestigationEvent(
                            phase=InvestigationPhase.EXECUTION,
                            action=action,
                            status="completed",
                            data={
                                "results": len(results),
                                "source": source,
                                "duration_ms": round(duration_ms),
                            },
                        )
                    elif source == "manual_flag":
                        trace.record_skipped(
                            action,
                            "Flagged for manual intervention",
                            state.jurisdiction,
                        )
                        yield InvestigationEvent(
                            phase=InvestigationPhase.EXECUTION,
                            action=action,
                            status="skipped",
                            data={"reason": "manual_flag"},
                        )
                    else:
                        trace.record_negative(
                            action,
                            [source],
                            "No results found",
                            state.jurisdiction,
                        )
                        yield InvestigationEvent(
                            phase=InvestigationPhase.EXECUTION,
                            action=action,
                            status="completed",
                            data={"results": 0, "source": source},
                        )

                except Exception as e:
                    logger.warning(f"Action {action} failed: {e}")
                    trace.record_error(action, [], str(e), state.jurisdiction)
                    yield InvestigationEvent(
                        phase=InvestigationPhase.EXECUTION,
                        action=action,
                        status="failed",
                        data={"error": str(e)},
                    )

            # Check sufficiency after each iteration
            sufficiency = self._check_sufficiency(state)
            yield InvestigationEvent(
                phase=InvestigationPhase.EXECUTION,
                action="sufficiency_check",
                status="completed",
                data={
                    "iteration": iteration,
                    "is_sufficient": sufficiency["is_sufficient"],
                    "score": sufficiency["score"],
                    "gaps": sufficiency["gaps"][:5],  # Limit for display
                },
            )

            if sufficiency["is_sufficient"]:
                logger.info(f"Investigation sufficient after {iteration} iteration(s)")
                break

            # If not sufficient and more iterations available, continue
            if iteration >= state.max_iterations:
                logger.info(f"Max iterations ({state.max_iterations}) reached")
                break

        # Phase 6: Route findings to watchers
        if state.watcher_ids and state.results:
            yield InvestigationEvent(
                phase=InvestigationPhase.WATCHER_SETUP,  # Reuse watcher phase
                action="evaluate_watchers",
                status="started",
            )

            try:
                # Collect all results into a flat list
                all_results = []
                for action, results in state.results.items():
                    for result in results:
                        # Ensure each result has required fields
                        all_results.append({
                            "title": result.get("name", result.get("title", "Unknown")),
                            "url": result.get("url", result.get("source", "")),
                            "content": result.get("content", result.get("description", "")),
                            "snippet": result.get("snippet", result.get("excerpt", "")),
                            "sourceId": result.get("id", ""),
                        })

                if all_results:
                    watcher_result = await self.watcher.execute(
                        project_id=state.project_id,
                        results=all_results,
                        query=state.query,
                    )

                    findings_count = watcher_result.get("findings", {}).get("total", 0)

                    yield InvestigationEvent(
                        phase=InvestigationPhase.WATCHER_SETUP,
                        action="evaluate_watchers",
                        status="completed",
                        data={
                            "findings": watcher_result.get("findings", {}),
                            "results_evaluated": len(all_results),
                        },
                    )
                else:
                    yield InvestigationEvent(
                        phase=InvestigationPhase.WATCHER_SETUP,
                        action="evaluate_watchers",
                        status="skipped",
                        data={"reason": "No results to evaluate"},
                    )

            except Exception as e:
                logger.warning(f"Watcher evaluation failed (non-fatal): {e}")
                yield InvestigationEvent(
                    phase=InvestigationPhase.WATCHER_SETUP,
                    action="evaluate_watchers",
                    status="completed",  # Non-fatal
                    data={"error": str(e)},
                )

        # Phase 7: Complete
        yield InvestigationEvent(
            phase=InvestigationPhase.COMPLETE,
            action="investigation_complete",
            status="completed",
            data={
                "investigation_id": investigation_id,
                "elapsed_ms": round(state.elapsed_ms()),
                "actions_executed": len(state.results),
                "total_results": sum(len(r) for r in state.results.values()),
                "watchers_created": len(state.watcher_ids),
                "trace_summary": trace.get_summary(),
            },
        )

    async def generate_report(
        self,
        state: InvestigationState,
        trace: DecisionTraceCollector,
    ) -> str:
        """
        Generate final report markdown.

        Args:
            state: Investigation state with results
            trace: Decision trace for methodology section

        Returns:
            Markdown report content
        """
        lines = [
            f"# Investigation Report: {state.entity}",
            "",
            f"**Jurisdiction:** {state.jurisdiction}",
            f"**Genre:** {state.genre}",
            f"**Complexity:** {state.complexity_score:.2f}",
            "",
        ]

        # Add results sections
        for action, results in state.results.items():
            section_name = action.replace("SEARCH_", "").replace("_", " ").title()
            lines.append(f"## {section_name}")
            lines.append("")
            if results:
                for result in results[:5]:  # Limit to first 5
                    lines.append(f"- {result}")
            else:
                lines.append("*No results found.*")
            lines.append("")

        # Add methodology section
        lines.append(trace.generate_audit_section())

        return "\n".join(lines)


# Convenience functions for CLI
async def run_investigation(query: str) -> Dict[str, Any]:
    """Quick investigation runner."""
    orchestrator = ThinOrchestrator()
    return await orchestrator.investigate(query)


async def investigate(
    tasking: str,
    project_id: str = "default",
    max_iterations: int = 10,
    autonomous: bool = True,
    event_callback: Optional[Callable] = None,
    genre: str = "due_diligence",
    depth: str = "enhanced",
    playbook_id: Optional[str] = None,
    document_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run investigation (CLI entry point).

    Args:
        tasking: Investigation query
        project_id: Project name for organization
        max_iterations: Maximum iterations
        autonomous: Run autonomously
        event_callback: Callback for streaming events (receives dict)
        genre: Report genre
        depth: Investigation depth (basic/enhanced/comprehensive)
        playbook_id: Optional playbook to run first
        document_id: Narrative document to attach watchers/findings to
    """
    orchestrator = ThinOrchestrator()

    # Store config in orchestrator for use during investigation
    # (These can be used by the orchestrator in future iterations)
    orchestrator._config = {
        "project_id": project_id,
        "max_iterations": max_iterations,
        "autonomous": autonomous,
        "genre": genre,
        "depth": depth,
        "playbook_id": playbook_id,
        "document_id": document_id,
    }

    if event_callback:
        # Streaming mode - emit events via callback
        events = []
        async for event in orchestrator.investigate_stream(
            tasking,
            project_id=project_id,
            document_id=document_id,
        ):
            event_dict = event.to_dict()
            events.append(event_dict)
            event_callback(event_dict)
        return {
            "status": "complete",
            "events": events,
            "project_id": project_id,
            "investigation_id": events[0]["data"].get("investigation_id") if events else None,
        }
    else:
        result = await orchestrator.investigate(tasking)
        result["project_id"] = project_id
        return result


async def resume_investigation(
    project_id: str,
    investigation_id: str,
    max_iterations: int = 10,
    event_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """
    Resume a previous investigation.

    Args:
        project_id: Project name
        investigation_id: Previous investigation ID to resume
        max_iterations: Maximum additional iterations
        event_callback: Callback for streaming events (receives dict)
    """
    # TODO: Load previous state from investigation_id
    # For now, we need a query to resume - get it from stored state
    # This is a placeholder - in production, load from database

    orchestrator = ThinOrchestrator()

    # Placeholder query for resume - should load from storage
    query = f"Resume investigation {investigation_id}"

    if event_callback:
        events = []
        async for event in orchestrator.investigate_stream(query, project_id=project_id):
            event_dict = event.to_dict()
            events.append(event_dict)
            event_callback(event_dict)
        return {
            "status": "complete",
            "events": events,
            "project_id": project_id,
            "resumed_from": investigation_id,
        }
    else:
        result = await orchestrator.investigate(query)
        result["project_id"] = project_id
        result["resumed_from"] = investigation_id
        return result


if __name__ == "__main__":
    async def demo():
        print("=" * 60)
        print("ThinOrchestrator Demo")
        print("=" * 60)

        orchestrator = ThinOrchestrator()

        queries = [
            "Quick KYC on UK company Test Ltd",
            "Full DD on BVI company Offshore Holdings with UBO tracing",
        ]

        for query in queries:
            print(f"\n{'─' * 60}")
            print(f"Query: {query}")
            print(f"{'─' * 60}")

            async for event in orchestrator.investigate_stream(query):
                status_icon = {
                    "started": "⏳",
                    "completed": "✓",
                    "failed": "✗",
                    "skipped": "⊘",
                }.get(event.status, "?")

                print(f"{status_icon} [{event.phase.value}] {event.action}: {event.status}")
                if event.data:
                    for k, v in event.data.items():
                        print(f"    {k}: {v}")

    asyncio.run(demo())
