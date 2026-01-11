"""
Navigator: Autonomous Investigation Loop with Watcher Extraction
================================================================

The Navigator is the autopilot brain. It:
1. Assesses K-U state (Grid Assessment)
2. Derives Intent (ENRICH or DISCOVER)
3. Constructs QueryExecutionPlan (search + watchers)
4. Executes search
5. Runs watcher extraction on results
6. Feeds slots with findings
7. Checks sufficiency
8. Loops until complete

ARCHITECTURE:
┌─────────────────────────────────────────────────────────────────────────────┐
│                          NAVIGATOR LOOP                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐                                                        │
│  │ 1. ASSESS K-U   │ ← Grid Assessor (Narrative/Subject/Location/Nexus)     │
│  │    STATE        │                                                        │
│  └────────┬────────┘                                                        │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────┐                                                        │
│  │ 2. DERIVE       │ ← Intent = (Grid State + Narrative) => Action          │
│  │    INTENT       │   ENRICH (go deep) or DISCOVER (go wide)               │
│  └────────┬────────┘                                                        │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────┐                                                        │
│  │ 3. CONSTRUCT    │ ← Query Lab + Watcher Specs                            │
│  │    PLAN         │   QueryExecutionPlan = search + extraction             │
│  └────────┬────────┘                                                        │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────┐                                                        │
│  │ 4. EXECUTE      │ ← IO Router runs search queries                        │
│  │    SEARCH       │                                                        │
│  └────────┬────────┘                                                        │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────┐                                                        │
│  │ 5. RUN WATCHER  │ ← WatcherExecutor processes results                    │
│  │    EXTRACTION   │   Quote + ET3 (event/topic/entity)                     │
│  └────────┬────────┘                                                        │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────┐                                                        │
│  │ 6. FEED SLOTS   │ ← Findings → Entity slots                              │
│  │                 │                                                        │
│  └────────┬────────┘                                                        │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────┐                                                        │
│  │ 7. SUFFICIENCY  │ ← All mandatory slots filled?                          │
│  │    CHECK        │   Narrative questions answered?                        │
│  └────────┬────────┘                                                        │
│           │                                                                 │
│     ┌─────┴─────┐                                                           │
│     │           │                                                           │
│     ▼           ▼                                                           │
│   [DONE]    [LOOP]──────────────────────────────────────────────────────┐   │
│                                                                         │   │
└─────────────────────────────────────────────────────────────────────────┴───┘
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, AsyncIterator, Callable
from enum import Enum
import asyncio
import time
from datetime import datetime

from .query_watcher_integration import (
    WatcherSpec,
    WatcherContextMode,
    WatcherFinding,
    WatcherExecutionResult,
    QueryExecutionPlan,
    ExtractionHints,
    build_execution_plan_with_watchers,
    parse_watcher_syntax,
)


# =============================================================================
# INTENT & STRATEGY (from Abacus spec)
# =============================================================================

class Intent(str, Enum):
    """What to do about the gap."""
    ENRICH = "enrich"    # Go deep - add depth to known anchor
    DISCOVER = "discover"  # Go wide - find unknown anchor


class Strategy(str, Enum):
    """How to execute the intent."""
    VERIFY = "verify"      # ENRICH: Known Subject + Known Location
    TRACE = "trace"        # DISCOVER Location: Known Subject + Unknown Location
    EXTRACT = "extract"    # DISCOVER Subject: Unknown Subject + Known Location
    NET = "net"           # DISCOVER Network: Unknown Subject + Unknown Location


class Target(str, Enum):
    """What the intent targets."""
    SUBJECT = "subject"
    LOCATION = "location"
    NETWORK = "network"


# =============================================================================
# K-U STATE (Knowledge-Unknown mapping)
# =============================================================================

@dataclass
class SlotState:
    """State of a single slot."""
    slot_id: str
    slot_name: str
    entity_id: str
    entity_name: str
    value: Optional[Any] = None
    is_mandatory: bool = False
    is_hungry: bool = False  # Empty mandatory = hungry
    sources: List[str] = field(default_factory=list)
    confidence: float = 0.0
    
    def __post_init__(self):
        self.is_hungry = self.is_mandatory and self.value is None


@dataclass
class EntityKUState:
    """K-U state of a single entity."""
    entity_id: str
    entity_name: str
    entity_type: str  # person, company, etc.
    
    # Slot states
    known_known: List[SlotState] = field(default_factory=list)  # Filled, verified
    known_unknown: List[SlotState] = field(default_factory=list)  # Empty mandatory (hungry)
    
    # Resolution state
    is_verified: bool = False
    is_disambiguated: bool = False
    
    def get_hungry_slots(self) -> List[SlotState]:
        """Get slots that need feeding."""
        return [s for s in self.known_unknown if s.is_hungry]


@dataclass
class LocationKUState:
    """K-U state of locations/sources."""
    checked_sources: List[str] = field(default_factory=list)
    implied_sources: List[str] = field(default_factory=list)  # Suggested but not checked
    unchecked_sources: List[str] = field(default_factory=list)
    
    # Jurisdiction state
    known_jurisdictions: List[str] = field(default_factory=list)
    implied_jurisdictions: List[str] = field(default_factory=list)


@dataclass
class NexusState:
    """State of connections/queries."""
    queries_run: List[Dict[str, Any]] = field(default_factory=list)
    queries_pending: List[Dict[str, Any]] = field(default_factory=list)
    edges_found: List[Dict[str, Any]] = field(default_factory=list)
    edges_expected: List[Dict[str, Any]] = field(default_factory=list)  # Expectation model


@dataclass
class GridAssessment:
    """Complete K-U state assessment from Grid Assessor."""
    
    # Subject states
    entities: List[EntityKUState] = field(default_factory=list)
    
    # Location state
    locations: LocationKUState = field(default_factory=LocationKUState)
    
    # Nexus state
    nexus: NexusState = field(default_factory=NexusState)
    
    # Narrative gaps
    unanswered_questions: List[str] = field(default_factory=list)
    
    # Summary metrics
    total_hungry_slots: int = 0
    total_unchecked_sources: int = 0
    
    def get_all_hungry_slots(self) -> List[Dict[str, str]]:
        """Get all hungry slots across all entities."""
        hungry = []
        for entity in self.entities:
            for slot in entity.get_hungry_slots():
                hungry.append({
                    "entity_id": slot.entity_id,
                    "entity_name": slot.entity_name,
                    "slot_name": slot.slot_name,
                    "slot_id": slot.slot_id,
                })
        return hungry
    
    def has_subject_anchor(self) -> bool:
        """Do we have at least one verified subject?"""
        return any(e.is_verified for e in self.entities)
    
    def has_location_anchor(self) -> bool:
        """Do we have at least one checked source?"""
        return len(self.locations.checked_sources) > 0


# =============================================================================
# SUFFICIENCY CHECK
# =============================================================================

@dataclass
class SufficiencyResult:
    """Result of sufficiency check."""
    is_sufficient: bool
    
    # What's missing
    hungry_slots: List[Dict[str, str]] = field(default_factory=list)
    unanswered_questions: List[str] = field(default_factory=list)
    unchecked_sources: List[str] = field(default_factory=list)
    
    # Confidence
    completeness_score: float = 0.0
    confidence_score: float = 0.0
    
    # Reason
    reason: str = ""


def check_sufficiency(
    assessment: GridAssessment,
    min_completeness: float = 0.8,
    min_confidence: float = 0.7,
) -> SufficiencyResult:
    """
    Check if investigation is sufficient to stop.
    
    Criteria:
    1. No hungry mandatory slots
    2. No unanswered narrative questions
    3. Minimum completeness threshold met
    """
    hungry_slots = assessment.get_all_hungry_slots()
    
    # Calculate completeness
    total_mandatory = sum(
        len(e.known_known) + len(e.known_unknown)
        for e in assessment.entities
    )
    filled = sum(len(e.known_known) for e in assessment.entities)
    completeness = filled / total_mandatory if total_mandatory > 0 else 1.0
    
    # Check criteria
    is_sufficient = (
        len(hungry_slots) == 0 and
        len(assessment.unanswered_questions) == 0 and
        completeness >= min_completeness
    )
    
    reason = ""
    if not is_sufficient:
        reasons = []
        if hungry_slots:
            reasons.append(f"{len(hungry_slots)} hungry slots")
        if assessment.unanswered_questions:
            reasons.append(f"{len(assessment.unanswered_questions)} unanswered questions")
        if completeness < min_completeness:
            reasons.append(f"completeness {completeness:.1%} < {min_completeness:.0%}")
        reason = ", ".join(reasons)
    
    return SufficiencyResult(
        is_sufficient=is_sufficient,
        hungry_slots=hungry_slots,
        unanswered_questions=assessment.unanswered_questions,
        unchecked_sources=assessment.locations.unchecked_sources,
        completeness_score=completeness,
        confidence_score=1.0,  # TODO: Calculate from slot confidences
        reason=reason,
    )


# =============================================================================
# INTENT DERIVATION (THE MOTOR)
# =============================================================================

def derive_intent(assessment: GridAssessment, narrative_goal: str) -> tuple[Intent, Strategy, Target]:
    """
    Derive intent from grid state + narrative context.
    
    This is THE MOTOR of the system.
    
    Intent Calculation:
    - What Unknown is Known due to other Knowns? (illuminated paths → ENRICH)
    - What Known is Unknown enough? (needs verification → ENRICH)
    - Otherwise → DISCOVER
    
    K-U Matrix:
                  LOCATION
                  Known              Unknown
             ┌─────────────────┬─────────────────┐
             │                 │                 │
    Known    │ VERIFY          │ TRACE           │
             │ ENRICH Subject  │ DISCOVER        │
    SUBJECT  │ via Location    │ Location        │
             │                 │                 │
             ├─────────────────┼─────────────────┤
             │                 │                 │
    Unknown  │ EXTRACT         │ DISCOVER        │
             │ DISCOVER        │ DISCOVER        │
             │ Subject         │ Network         │
             │                 │                 │
             └─────────────────┴─────────────────┘
    """
    has_subject = assessment.has_subject_anchor()
    has_location = assessment.has_location_anchor()
    hungry_slots = assessment.get_all_hungry_slots()
    
    # Case 1: Subject + Location known → VERIFY (ENRICH Subject via Location)
    if has_subject and has_location:
        if hungry_slots:
            # Have anchor, have source, slots empty → ENRICH to fill
            return Intent.ENRICH, Strategy.VERIFY, Target.SUBJECT
        else:
            # All filled → still verify/triangulate
            return Intent.ENRICH, Strategy.VERIFY, Target.SUBJECT
    
    # Case 2: Subject known, Location unknown → TRACE (DISCOVER Location)
    if has_subject and not has_location:
        return Intent.DISCOVER, Strategy.TRACE, Target.LOCATION
    
    # Case 3: Subject unknown, Location known → EXTRACT (DISCOVER Subject)
    if not has_subject and has_location:
        return Intent.DISCOVER, Strategy.EXTRACT, Target.SUBJECT
    
    # Case 4: Both unknown → NET (DISCOVER Network)
    return Intent.DISCOVER, Strategy.NET, Target.NETWORK


# =============================================================================
# NAVIGATOR (THE AUTOPILOT BRAIN)
# =============================================================================

@dataclass
class NavigatorConfig:
    """Configuration for Navigator."""
    max_iterations: int = 10
    min_completeness: float = 0.8
    min_confidence: float = 0.7
    exhaustive_extraction: bool = True
    parallel_models: bool = True
    cache_extractions: bool = True


@dataclass
class NavigatorState:
    """Current state of Navigator run."""
    iteration: int = 0
    intent: Optional[Intent] = None
    strategy: Optional[Strategy] = None
    target: Optional[Target] = None
    
    # Accumulated results
    total_queries_run: int = 0
    total_findings: int = 0
    total_slots_fed: int = 0
    
    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class NavigatorEvent:
    """Event emitted during Navigator run."""
    event_type: str  # iteration_start, search_done, extraction_done, slot_fed, done
    iteration: int
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class Navigator:
    """
    The Autopilot Brain.
    
    Runs the full investigation loop:
    1. Assess K-U state
    2. Derive Intent
    3. Construct plan
    4. Execute search
    5. Run extraction
    6. Feed slots
    7. Check sufficiency
    8. Loop
    """
    
    def __init__(
        self,
        config: Optional[NavigatorConfig] = None,
        # Injected dependencies
        grid_assessor: Optional[Callable] = None,
        query_constructor: Optional[Callable] = None,
        search_executor: Optional[Callable] = None,
        watcher_executor: Optional[Callable] = None,
        slot_feeder: Optional[Callable] = None,
    ):
        self.config = config or NavigatorConfig()
        self.state = NavigatorState()
        
        # Injected dependencies (allow mocking)
        self._grid_assessor = grid_assessor
        self._query_constructor = query_constructor
        self._search_executor = search_executor
        self._watcher_executor = watcher_executor
        self._slot_feeder = slot_feeder
    
    async def run(
        self,
        narrative_goal: str,
        initial_query: Optional[str] = None,
        active_watchers: Optional[List[Dict[str, Any]]] = None,
        entities: Optional[List[Dict[str, Any]]] = None,
        sources: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[NavigatorEvent]:
        """
        Run the Navigator loop.
        
        Yields events as it progresses.
        
        Args:
            narrative_goal: What are we trying to find out?
            initial_query: Optional starting query
            active_watchers: Active watchers from project
            entities: Known entities
            sources: Known sources
        """
        self.state = NavigatorState(started_at=datetime.now())
        active_watchers = active_watchers or []
        entities = entities or []
        sources = sources or []
        
        # Parse inline watchers from initial query
        clean_query = initial_query
        if initial_query:
            clean_query, inline_watchers = parse_watcher_syntax(initial_query)
            # Add inline watchers to active watchers
            for w in inline_watchers:
                active_watchers.append({
                    "id": w.watcher_id,
                    "label": w.label,
                    "metadata": {"et3": {"watcherType": w.watcher_type}}
                })
        
        while self.state.iteration < self.config.max_iterations:
            self.state.iteration += 1
            
            yield NavigatorEvent(
                event_type="iteration_start",
                iteration=self.state.iteration,
                data={"narrative_goal": narrative_goal}
            )
            
            # 1. ASSESS K-U STATE
            assessment = await self._assess_ku_state(entities, sources, narrative_goal)
            
            # 2. CHECK SUFFICIENCY (early exit)
            sufficiency = check_sufficiency(
                assessment,
                self.config.min_completeness,
                self.config.min_confidence,
            )
            
            if sufficiency.is_sufficient:
                yield NavigatorEvent(
                    event_type="done",
                    iteration=self.state.iteration,
                    data={
                        "reason": "sufficient",
                        "completeness": sufficiency.completeness_score,
                        "total_findings": self.state.total_findings,
                    }
                )
                self.state.completed_at = datetime.now()
                return
            
            # 3. DERIVE INTENT
            intent, strategy, target = derive_intent(assessment, narrative_goal)
            self.state.intent = intent
            self.state.strategy = strategy
            self.state.target = target
            
            yield NavigatorEvent(
                event_type="intent_derived",
                iteration=self.state.iteration,
                data={
                    "intent": intent.value,
                    "strategy": strategy.value,
                    "target": target.value,
                    "hungry_slots": len(sufficiency.hungry_slots),
                }
            )
            
            # 4. CONSTRUCT EXECUTION PLAN
            plan = await self._construct_plan(
                assessment=assessment,
                intent=intent,
                strategy=strategy,
                target=target,
                narrative_goal=narrative_goal,
                clean_query=clean_query,
                active_watchers=active_watchers,
            )
            
            # 5. EXECUTE SEARCH
            search_results = await self._execute_search(plan)
            self.state.total_queries_run += 1
            
            yield NavigatorEvent(
                event_type="search_done",
                iteration=self.state.iteration,
                data={
                    "results_count": len(search_results),
                }
            )
            
            # 6. RUN WATCHER EXTRACTION
            extraction_result = await self._run_extraction(plan, search_results)
            self.state.total_findings += len(extraction_result.findings)
            
            yield NavigatorEvent(
                event_type="extraction_done",
                iteration=self.state.iteration,
                data={
                    "findings_count": len(extraction_result.findings),
                    "quote_findings": extraction_result.quote_findings,
                    "event_findings": extraction_result.event_findings,
                    "topic_findings": extraction_result.topic_findings,
                    "entity_findings": extraction_result.entity_findings,
                }
            )
            
            # 7. FEED SLOTS
            slots_fed = await self._feed_slots(plan, extraction_result, entities)
            self.state.total_slots_fed += slots_fed
            
            yield NavigatorEvent(
                event_type="slots_fed",
                iteration=self.state.iteration,
                data={
                    "slots_fed": slots_fed,
                    "total_slots_fed": self.state.total_slots_fed,
                }
            )
            
            # Update entities/sources for next iteration
            # (In real impl, would fetch updated state from graph)
            
            # Clear initial query after first iteration
            clean_query = None
        
        # Max iterations reached
        yield NavigatorEvent(
            event_type="done",
            iteration=self.state.iteration,
            data={
                "reason": "max_iterations",
                "total_findings": self.state.total_findings,
            }
        )
        self.state.completed_at = datetime.now()
    
    # -------------------------------------------------------------------------
    # Private methods (delegation to injected dependencies)
    # -------------------------------------------------------------------------
    
    async def _assess_ku_state(
        self,
        entities: List[Dict[str, Any]],
        sources: List[Dict[str, Any]],
        narrative_goal: str,
    ) -> GridAssessment:
        """Delegate to Grid Assessor."""
        if self._grid_assessor:
            return await self._grid_assessor(entities, sources, narrative_goal)
        
        # Default: Build basic assessment from entities/sources
        assessment = GridAssessment()
        
        for e in entities:
            entity_state = EntityKUState(
                entity_id=e.get("id", ""),
                entity_name=e.get("label", ""),
                entity_type=e.get("type", "unknown"),
                is_verified=e.get("verified", False),
            )
            
            # Check slots
            for slot_name, slot_data in e.get("slots", {}).items():
                slot_state = SlotState(
                    slot_id=f"{e['id']}_{slot_name}",
                    slot_name=slot_name,
                    entity_id=e.get("id", ""),
                    entity_name=e.get("label", ""),
                    value=slot_data.get("value"),
                    is_mandatory=slot_data.get("mandatory", False),
                )
                
                if slot_state.is_hungry:
                    entity_state.known_unknown.append(slot_state)
                else:
                    entity_state.known_known.append(slot_state)
            
            assessment.entities.append(entity_state)
        
        for s in sources:
            if s.get("checked"):
                assessment.locations.checked_sources.append(s.get("id", ""))
            else:
                assessment.locations.unchecked_sources.append(s.get("id", ""))
        
        assessment.total_hungry_slots = len(assessment.get_all_hungry_slots())
        assessment.total_unchecked_sources = len(assessment.locations.unchecked_sources)
        
        return assessment
    
    async def _construct_plan(
        self,
        assessment: GridAssessment,
        intent: Intent,
        strategy: Strategy,
        target: Target,
        narrative_goal: str,
        clean_query: Optional[str],
        active_watchers: List[Dict[str, Any]],
    ) -> QueryExecutionPlan:
        """Construct QueryExecutionPlan from assessment and intent."""
        if self._query_constructor:
            return await self._query_constructor(
                assessment, intent, strategy, target, narrative_goal, clean_query, active_watchers
            )
        
        # Default: Use integration function
        # In real impl, would use Query Lab to construct QueryRecipe
        query_recipe = {
            "raw_query": clean_query or narrative_goal,
            "intent": intent.value,
            "strategy": strategy.value,
            "target": target.value,
        }
        
        hungry_slots = assessment.get_all_hungry_slots()
        
        return build_execution_plan_with_watchers(
            query_recipe=query_recipe,
            active_watchers=active_watchers,
            hungry_slots=hungry_slots if intent == Intent.ENRICH else None,
            narrative_goal=narrative_goal,
        )
    
    async def _execute_search(self, plan: QueryExecutionPlan) -> List[Dict[str, Any]]:
        """Execute search queries."""
        if self._search_executor:
            return await self._search_executor(plan)
        
        # Default: Mock results
        return []
    
    async def _run_extraction(
        self,
        plan: QueryExecutionPlan,
        search_results: List[Dict[str, Any]],
    ) -> WatcherExecutionResult:
        """Run watcher extraction on search results."""
        if self._watcher_executor:
            return await self._watcher_executor(plan, search_results)
        
        # Default: Empty results
        return WatcherExecutionResult(
            total_sources_checked=len(search_results),
            total_watchers_run=len(plan.watchers),
        )
    
    async def _feed_slots(
        self,
        plan: QueryExecutionPlan,
        extraction_result: WatcherExecutionResult,
        entities: List[Dict[str, Any]],
    ) -> int:
        """Feed extraction findings to entity slots."""
        if self._slot_feeder:
            return await self._slot_feeder(plan, extraction_result, entities)
        
        # Default: Count findings with slot targets
        fed = 0
        for finding in extraction_result.findings:
            if finding.watcher_id in plan.slot_targets:
                fed += len(plan.slot_targets[finding.watcher_id])
        return fed


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def run_navigator(
    narrative_goal: str,
    initial_query: Optional[str] = None,
    active_watchers: Optional[List[Dict[str, Any]]] = None,
    entities: Optional[List[Dict[str, Any]]] = None,
    sources: Optional[List[Dict[str, Any]]] = None,
    config: Optional[NavigatorConfig] = None,
) -> List[NavigatorEvent]:
    """
    Run Navigator and collect all events.
    
    Convenience wrapper for non-streaming use.
    """
    navigator = Navigator(config=config)
    events = []
    
    async for event in navigator.run(
        narrative_goal=narrative_goal,
        initial_query=initial_query,
        active_watchers=active_watchers,
        entities=entities,
        sources=sources,
    ):
        events.append(event)
    
    return events
