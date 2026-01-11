"""
Query-Watcher Integration Layer (V62)
=====================================

Bridges QueryRecipe (search construction) with Watcher System (extraction intelligence).

THE GAP:
- QueryRecipe builds search queries but ignores extraction intelligence
- Watchers extract from results but don't inform query construction
- Navigator loop should fuse both: construct query WITH watchers, extract WITH context

ARCHITECTURE:
┌─────────────────────────────────────────────────────────────────────────────┐
│                        QUERY-WATCHER FUSION                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  QueryRecipe (Search Construction)    Watcher System (Extraction)           │
│  ================================    ===================================    │
│  • Location axis (where to search)   • Header watchers (quote matching)     │
│  • Subject axis (what to find)       • ET3 watchers (event/topic/entity)    │
│  • Nexus terms (connecting tissue)   • HUNTER_KILLER (active hunting)       │
│                                                                             │
│                         ┌─────────────┐                                     │
│                         │   FUSION    │                                     │
│                         │   LAYER     │                                     │
│                         └──────┬──────┘                                     │
│                                │                                            │
│                                ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ QueryExecutionPlan                                                   │   │
│  │ • searchSpec: QueryRecipe (existing)                                 │   │
│  │ • extractionSpec: WatcherSpec[] (NEW)                                │   │
│  │ • contextMode: 'isolated' | 'entity' | 'accumulated'                 │   │
│  │ • slotTargets: Map<watcherId, slotId[]> (slot feeding)               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

WATCHER SOURCES (where watchers come from):
1. Note headers: "# What is John Smith's DOB?" → Watcher
2. Search bar syntax: "John Smith" +w[DOB?] +w[Companies?]
3. Auto-generated from hungry slots
4. Template-driven (EDITH)
5. Entity-attached (contextful extraction)

NAVIGATOR LOOP (with watchers):
1. Construct query (search spec + watcher spec)
2. Execute search
3. For each result: 
   - Header watchers: LLM matches quote
   - ET3 watchers: Extract once, filter many (cached)
4. Slot feeding: Watcher answers → Entity slots
5. Sufficiency check
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Literal, Tuple
from enum import Enum
import re


# =============================================================================
# WATCHER CONTEXT MODES
# =============================================================================

class WatcherContextMode(str, Enum):
    """How watcher extraction sees context."""
    
    # Type A: Query-attached (contextless)
    # Imported from note headers or search bar
    # AI processes each result in isolation
    # No cross-result deduplication
    ISOLATED = "isolated"
    
    # Type B: Entity-attached (contextful)
    # Attached to entity nodes
    # AI sees full entity context (node data, one-hop relations)
    # Answers feed entity slots directly
    ENTITY_CONTEXT = "entity_context"
    
    # Type C: Accumulated
    # AI sees all previous extractions in same run
    # Used for deduplication and synthesis
    ACCUMULATED = "accumulated"


# =============================================================================
# WATCHER SPEC (what to extract)
# =============================================================================

@dataclass
class WatcherSpec:
    """
    Specification for a single watcher in query execution.
    
    Mirrors TypeScript WatcherNode but focused on execution needs.
    """
    
    # Identity
    watcher_id: str
    label: str  # Header text or watcher name
    
    # Type determines extraction method
    watcher_type: Literal["quote", "event", "topic", "entity"]
    
    # ET3 config (for non-quote watchers)
    monitored_event: Optional[str] = None  # e.g., "evt_ipo"
    monitored_topic: Optional[str] = None  # e.g., "top_sanctions"
    monitored_types: Optional[List[str]] = None  # e.g., ["person", "company"]
    monitored_names: Optional[List[str]] = None  # e.g., ["OpenAI"]
    monitored_entities: Optional[List[str]] = None  # Entity IDs for filtering
    
    # Filters
    role_filter: Optional[List[str]] = None  # ["CEO", "Director"]
    jurisdiction_filter: Optional[List[str]] = None  # ["US-DE", "UK"]
    temporal_window: Optional[Dict[str, str]] = None  # {"start": "2024-01", "end": "2024-12"}
    
    # Context mode
    context_mode: WatcherContextMode = WatcherContextMode.ISOLATED
    
    # Target slots (for entity-attached watchers)
    target_slots: Optional[List[str]] = None  # Slot IDs to feed answers to
    target_entity_id: Optional[str] = None  # Entity node ID
    
    # Execution hints
    priority: int = 0  # Higher = process first
    exhaustive: bool = True  # False = use vector sieve filtering
    
    @classmethod
    def from_header(cls, header_text: str, watcher_id: str) -> "WatcherSpec":
        """Create quote watcher from document header."""
        return cls(
            watcher_id=watcher_id,
            label=header_text,
            watcher_type="quote",
            context_mode=WatcherContextMode.ISOLATED,
        )
    
    @classmethod
    def from_event(
        cls,
        watcher_id: str,
        label: str,
        event_type: str,
        entities: Optional[List[str]] = None,
        temporal_window: Optional[Dict[str, str]] = None,
    ) -> "WatcherSpec":
        """Create ET3 event watcher."""
        return cls(
            watcher_id=watcher_id,
            label=label,
            watcher_type="event",
            monitored_event=event_type,
            monitored_entities=entities,
            temporal_window=temporal_window,
            context_mode=WatcherContextMode.ISOLATED,
        )
    
    @classmethod
    def from_slot(
        cls,
        watcher_id: str,
        slot_name: str,
        entity_id: str,
        slot_id: str,
    ) -> "WatcherSpec":
        """
        Create watcher from hungry slot.
        
        Example: Entity "John Smith" has empty DOB slot
        → Creates watcher: "What is John Smith's date of birth?"
        """
        return cls(
            watcher_id=watcher_id,
            label=f"What is {slot_name}?",
            watcher_type="quote",
            context_mode=WatcherContextMode.ENTITY_CONTEXT,
            target_entity_id=entity_id,
            target_slots=[slot_id],
        )


# =============================================================================
# EXTRACTION HINTS (from watchers to extraction)
# =============================================================================

@dataclass
class ExtractionHints:
    """
    Hints derived from active watchers to guide SubjectExtractionService.
    
    Passed to extractSubjects() to prioritize relevant entities.
    """
    
    priority_events: List[str] = field(default_factory=list)
    priority_topics: List[str] = field(default_factory=list)
    priority_entity_types: List[str] = field(default_factory=list)
    priority_entity_names: List[str] = field(default_factory=list)
    priority_roles: List[str] = field(default_factory=list)
    priority_jurisdictions: List[str] = field(default_factory=list)
    
    @classmethod
    def from_watchers(cls, watchers: List[WatcherSpec]) -> "ExtractionHints":
        """Build hints from active watcher specs."""
        hints = cls()
        
        for w in watchers:
            if w.watcher_type == "event" and w.monitored_event:
                hints.priority_events.append(w.monitored_event)
            if w.watcher_type == "topic" and w.monitored_topic:
                hints.priority_topics.append(w.monitored_topic)
            if w.monitored_types:
                hints.priority_entity_types.extend(w.monitored_types)
            if w.monitored_names:
                hints.priority_entity_names.extend(w.monitored_names)
            if w.role_filter:
                hints.priority_roles.extend(w.role_filter)
            if w.jurisdiction_filter:
                hints.priority_jurisdictions.extend(w.jurisdiction_filter)
            if w.monitored_entities:
                hints.priority_entity_names.extend(w.monitored_entities)
        
        # Deduplicate
        hints.priority_events = list(set(hints.priority_events))
        hints.priority_topics = list(set(hints.priority_topics))
        hints.priority_entity_types = list(set(hints.priority_entity_types))
        hints.priority_entity_names = list(set(hints.priority_entity_names))
        hints.priority_roles = list(set(hints.priority_roles))
        hints.priority_jurisdictions = list(set(hints.priority_jurisdictions))
        
        return hints


# =============================================================================
# QUERY EXECUTION PLAN (fused search + extraction)
# =============================================================================

@dataclass
class QueryExecutionPlan:
    """
    Complete execution plan: search spec + extraction spec.
    
    This is what the Navigator builds and passes to the executor.
    """
    
    # Search specification (from QueryRecipe)
    query_recipe: Any  # QueryRecipe from query_recipe.py
    
    # Extraction specification (from watchers)
    watchers: List[WatcherSpec] = field(default_factory=list)
    
    # Default context mode for all watchers
    default_context_mode: WatcherContextMode = WatcherContextMode.ISOLATED
    
    # Slot feeding map: watcher_id -> list of (entity_id, slot_id) tuples
    slot_targets: Dict[str, List[Tuple[str, str]]] = field(default_factory=dict)
    
    # Extraction hints (derived from watchers)
    extraction_hints: Optional[ExtractionHints] = None
    
    # Execution options
    exhaustive_extraction: bool = True  # vs vector sieve
    parallel_models: bool = True  # Multi-model execution
    cache_extractions: bool = True  # Content-hash caching
    
    def __post_init__(self):
        """Derive extraction hints from watchers."""
        if self.watchers and not self.extraction_hints:
            self.extraction_hints = ExtractionHints.from_watchers(self.watchers)
    
    def get_quote_watchers(self) -> List[WatcherSpec]:
        """Get header-based watchers (LLM matching)."""
        return [w for w in self.watchers if w.watcher_type == "quote"]
    
    def get_event_watchers(self) -> List[WatcherSpec]:
        """Get ET3 event watchers."""
        return [w for w in self.watchers if w.watcher_type == "event"]
    
    def get_topic_watchers(self) -> List[WatcherSpec]:
        """Get ET3 topic watchers."""
        return [w for w in self.watchers if w.watcher_type == "topic"]
    
    def get_entity_watchers(self) -> List[WatcherSpec]:
        """Get ET3 entity watchers."""
        return [w for w in self.watchers if w.watcher_type == "entity"]
    
    def has_et3_watchers(self) -> bool:
        """Check if any ET3 watchers exist (for unified extraction)."""
        return any(
            w.watcher_type in ("event", "topic", "entity")
            for w in self.watchers
        )


# =============================================================================
# WATCHER FINDING (extraction result)
# =============================================================================

@dataclass
class WatcherFinding:
    """
    Result of watcher extraction.
    
    For quote watchers: matched quote from content
    For ET3 watchers: extracted event/topic/entity with context
    """
    
    watcher_id: str
    watcher_label: str
    
    # Source info
    source_id: str
    source_url: str
    source_title: Optional[str] = None
    
    # Extraction result
    quote: Optional[str] = None  # For quote watchers
    explanation: Optional[str] = None
    
    # ET3 result
    matched_subject: Optional[str] = None  # Event/topic/entity ID
    matched_canonical: Optional[str] = None  # Human-readable name
    match_type: Optional[Literal["event", "topic", "entity"]] = None
    
    # Entity roles (for event watchers with entity context)
    entity_roles: Optional[Dict[str, str]] = None
    
    # Confidence and provenance
    confidence: float = 1.0
    model_used: Optional[str] = None
    extracted_at: Optional[str] = None
    
    # Slot feeding
    fed_slots: Optional[List[str]] = None  # Slot IDs this finding fed


# =============================================================================
# WATCHER EXECUTION RESULT
# =============================================================================

@dataclass
class WatcherExecutionResult:
    """
    Complete result of watcher execution against search results.
    """
    
    # All findings
    findings: List[WatcherFinding] = field(default_factory=list)
    
    # Stats
    total_sources_checked: int = 0
    total_watchers_run: int = 0
    quote_findings: int = 0
    event_findings: int = 0
    topic_findings: int = 0
    entity_findings: int = 0
    
    # Slot feeding results
    slots_fed: Dict[str, Any] = field(default_factory=dict)  # slot_id -> value
    
    # Cache stats
    cache_hits: int = 0
    cache_misses: int = 0
    
    # Timing
    extraction_time_ms: int = 0
    
    def add_finding(self, finding: WatcherFinding):
        """Add finding and update stats."""
        self.findings.append(finding)
        
        if finding.match_type == "event":
            self.event_findings += 1
        elif finding.match_type == "topic":
            self.topic_findings += 1
        elif finding.match_type == "entity":
            self.entity_findings += 1
        else:
            self.quote_findings += 1


# =============================================================================
# GENERATIVE WATCHER CREATION (AI-driven)
# =============================================================================

@dataclass
class GenerativeWatcherRequest:
    """
    Request for AI to generate watchers from context.
    
    Used when:
    1. User provides tasking but no explicit watchers
    2. Hungry slots need watchers auto-generated
    3. Template suggests watcher patterns
    """
    
    # Context for generation
    narrative_goal: str  # What are we trying to find out?
    known_subjects: List[str] = field(default_factory=list)  # Known entities
    known_locations: List[str] = field(default_factory=list)  # Known sources/jurisdictions
    
    # Hungry slots (slots without values)
    hungry_slots: List[Dict[str, str]] = field(default_factory=list)
    # Each: {"entity_id": "...", "entity_name": "...", "slot_name": "...", "slot_id": "..."}
    
    # Template guidance
    template_sections: Optional[List[str]] = None  # EDITH template sections
    
    # Generation constraints
    max_watchers: int = 10
    watcher_types: List[str] = field(default_factory=lambda: ["quote", "event", "topic", "entity"])


@dataclass
class GeneratedWatcher:
    """AI-generated watcher specification."""
    
    label: str
    watcher_type: Literal["quote", "event", "topic", "entity"]
    rationale: str  # Why this watcher was created
    
    # Type-specific config
    monitored_event: Optional[str] = None
    monitored_topic: Optional[str] = None
    monitored_types: Optional[List[str]] = None
    monitored_names: Optional[List[str]] = None
    
    # Slot binding (if generated from hungry slot)
    target_entity_id: Optional[str] = None
    target_slot_id: Optional[str] = None


# =============================================================================
# WATCHER SYNTAX PARSER (search bar integration)
# =============================================================================

def parse_watcher_syntax(query: str) -> Tuple[str, List[WatcherSpec]]:
    """
    Parse watcher syntax from search bar.
    
    Syntax: "search terms" +w[Question?] +w[Another question?]
    
    Examples:
        "John Smith" +w[DOB?] +w[Companies?]
        "Acme Corp" +w[Directors?] +w[Beneficial owners?]
    
    Returns:
        (clean_query, list of WatcherSpec)
    """
    watcher_specs = []
    clean_query = query
    
    # Pattern: +w[...] or +watcher[...]
    pattern = r'\+w(?:atcher)?\[([^\]]+)\]'
    matches = re.findall(pattern, query)
    
    for i, match in enumerate(matches):
        watcher_id = f"inline_watcher_{i}"
        spec = WatcherSpec.from_header(match.strip(), watcher_id)
        watcher_specs.append(spec)
    
    # Remove watcher syntax from query
    clean_query = re.sub(pattern, '', query).strip()
    
    return clean_query, watcher_specs


# =============================================================================
# INTEGRATION WITH QUERY LAB
# =============================================================================

def build_execution_plan_with_watchers(
    query_recipe: Any,  # QueryRecipe
    active_watchers: List[Dict[str, Any]],  # From watcherService
    hungry_slots: Optional[List[Dict[str, str]]] = None,
    narrative_goal: Optional[str] = None,
) -> QueryExecutionPlan:
    """
    Build complete execution plan from QueryRecipe and active watchers.
    
    This is the main integration point between Query Lab and Watcher System.
    
    Args:
        query_recipe: QueryRecipe from query_recipe.py
        active_watchers: Active watcher nodes from watcherService.getActiveWatchers()
        hungry_slots: Empty slots that need watchers generated
        narrative_goal: Investigation goal for AI watcher generation
    
    Returns:
        QueryExecutionPlan ready for execution
    """
    watcher_specs = []
    
    # 1. Convert active watchers to WatcherSpec
    for w in active_watchers:
        meta = w.get("metadata", {})
        et3 = meta.get("et3", {})
        
        watcher_type = et3.get("watcherType", "quote")
        
        spec = WatcherSpec(
            watcher_id=w["id"],
            label=w.get("label", ""),
            watcher_type=watcher_type,
            monitored_event=et3.get("monitoredEvent"),
            monitored_topic=et3.get("monitoredTopic"),
            monitored_types=et3.get("monitoredTypes"),
            monitored_names=et3.get("monitoredNames"),
            monitored_entities=et3.get("monitoredEntities"),
            role_filter=et3.get("roleFilter"),
            jurisdiction_filter=et3.get("jurisdictionFilter"),
            temporal_window=et3.get("temporalWindow"),
            context_mode=WatcherContextMode.ISOLATED,
            exhaustive=True,
        )
        watcher_specs.append(spec)
    
    # 2. Generate watchers for hungry slots (if any)
    if hungry_slots:
        for slot in hungry_slots:
            slot_watcher = WatcherSpec.from_slot(
                watcher_id=f"slot_watcher_{slot['slot_id']}",
                slot_name=f"{slot['entity_name']}'s {slot['slot_name']}",
                entity_id=slot["entity_id"],
                slot_id=slot["slot_id"],
            )
            watcher_specs.append(slot_watcher)
    
    # 3. Build slot targets map
    slot_targets: Dict[str, List[Tuple[str, str]]] = {}
    for spec in watcher_specs:
        if spec.target_slots and spec.target_entity_id:
            slot_targets[spec.watcher_id] = [
                (spec.target_entity_id, slot_id)
                for slot_id in spec.target_slots
            ]
    
    # 4. Create execution plan
    plan = QueryExecutionPlan(
        query_recipe=query_recipe,
        watchers=watcher_specs,
        slot_targets=slot_targets,
        exhaustive_extraction=True,
        parallel_models=True,
        cache_extractions=True,
    )
    
    return plan
