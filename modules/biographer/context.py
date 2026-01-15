#!/usr/bin/env python3
"""
BIOGRAPHER Context Assembly

Assembles the full context for biographer_ai disambiguation decisions:
1. Project Note (with template populated, sections filled)
2. Active Watchers + their attached context (entities, topics)
3. Disambiguation Anchors (location, temporal, geo, industry, phenomena)
4. IO Routing Suggestions (what sources can fill unfilled slots)

This context is passed to biographer_ai when it needs to make decisions
about incoming watcher findings (ADD_VERIFIED/ADD_UNVERIFIED/REJECT).

DISAMBIGUATION ANCHORS:
- location: Geographic anchor points (country, city, jurisdiction)
- subject: The person/entity being investigated
- temporal: Time-based anchors (DOB, founded date, event dates)
- geo: Geopolitical context (regions, territories)
- industry: Sector/industry classification
- phenomena: Events like IPO, sanctions, litigation, bankruptcy

IO ROUTING:
- Uses io_find_capabilities to show what sources can fill unfilled slots
- Lists execution modules (corporella, eyed, alldom, etc.)
- Pre-populates discernable attributes from project context
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass, field as dataclass_field

logger = logging.getLogger(__name__)

# Import from sibling modules
from .nodes import Node, BiographerNodeSet
from .watcher import BiographerWatcher, WatcherFinding, PERSON_NOTE_HEADINGS

# Import bridges
import sys
import importlib.util

_bridges_file = Path(__file__).parent.parent / "sastre" / "bridges.py"
if _bridges_file.exists():
    _spec = importlib.util.spec_from_file_location("bridges_module", _bridges_file)
    _bridges_module = importlib.util.module_from_spec(_spec)
    try:
        _spec.loader.exec_module(_bridges_module)
        WatcherBridge = _bridges_module.WatcherBridge
        NarrativeBridge = _bridges_module.NarrativeBridge
        BRIDGES_AVAILABLE = True
    except Exception as e:
        logger.debug(f"SASTRE bridges not available: {e}")
        BRIDGES_AVAILABLE = False
        WatcherBridge = None
        NarrativeBridge = None
else:
    BRIDGES_AVAILABLE = False
    WatcherBridge = None
    NarrativeBridge = None

# Import project note
try:
    from ..sastre.narrative.project_note import ProjectNote, load_project_note
    PROJECT_NOTE_AVAILABLE = True
except ImportError:
    PROJECT_NOTE_AVAILABLE = False
    ProjectNote = None

# Import IO Router for routing suggestions
try:
    _io_router_path = Path(__file__).parent.parent / "input_output" / "matrix" / "io_cli.py"
    if _io_router_path.exists():
        import importlib.util
        _spec = importlib.util.spec_from_file_location("io_cli", _io_router_path)
        _io_module = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_io_module)
        IORouter = _io_module.IORouter
        IO_ROUTER_AVAILABLE = True
    else:
        IO_ROUTER_AVAILABLE = False
        IORouter = None
except Exception as e:
    logger.debug(f"IO Router not available: {e}")
    IO_ROUTER_AVAILABLE = False
    IORouter = None

# Import modules.json for execution methods
try:
    _modules_path = Path(__file__).parent.parent / "input_output" / "matrix" / "modules.json"
    if _modules_path.exists():
        with open(_modules_path) as f:
            EXECUTION_MODULES = json.load(f).get("modules", {})
    else:
        EXECUTION_MODULES = {}
except Exception as e:
    logger.debug(f"Failed to load modules.json: {e}")
    EXECUTION_MODULES = {}

# Import codes.json for field code mapping
try:
    _codes_path = Path(__file__).parent.parent / "input_output" / "matrix" / "codes.json"
    if _codes_path.exists():
        with open(_codes_path) as f:
            _codes_data = json.load(f)
            IO_CODES = _codes_data.get("codes", {})
            # Build reverse lookup: field_name -> code_number
            IO_FIELD_TO_CODE = {v.get("name"): k for k, v in IO_CODES.items() if v.get("name")}
    else:
        IO_CODES = {}
        IO_FIELD_TO_CODE = {}
except Exception as e:
    logger.debug(f"Failed to load codes.json: {e}")
    IO_CODES = {}
    IO_FIELD_TO_CODE = {}


# =============================================================================
# PERSON NODE SCHEMA - Fields biographer populates
# =============================================================================

PERSON_NODE_SCHEMA = {
    # Identity & Contact (from EYE-D primarily)
    "person_name": {"io_code": 7, "category": "identity"},
    "date_of_birth": {"io_code": 12, "category": "identity"},  # Critical for disambiguation (person_dob)
    "year_of_birth": {"io_code": None, "category": "identity"},  # Temporal anchor (derived from DOB)
    "emails": {"io_code": 1, "category": "contact"},
    "phones": {"io_code": 2, "category": "contact"},
    "addresses": {"io_code": 17, "category": "contact"},
    "linkedin_url": {"io_code": 5, "category": "social"},
    "national_id": {"io_code": 8, "category": "identity"},
    "passport_id": {"io_code": 10, "category": "identity"},
    "tax_id": {"io_code": 9, "category": "identity"},

    # Corporate (from CORPORELLA primarily)
    "corporate_roles": {"io_code": 42, "category": "corporate"},
    "directorships": {"io_code": 43, "category": "corporate"},
    "shareholdings": {"io_code": 44, "category": "corporate"},
    "beneficial_ownership": {"io_code": 45, "category": "corporate"},

    # Social Profiles (from SOCIALITE)
    "social_profiles": {"io_code": 709, "category": "social"},

    # Breach Exposure (from EYE-D)
    "breach_exposure": {"io_code": 187, "category": "security"},

    # Sanctions & PEP (from OPENSANCTIONS)
    "sanctions_status": {"io_code": 99, "category": "risk"},
    "pep_status": {"io_code": 521, "category": "risk"},

    # Litigation (from linklater/Court Records)
    "litigation": {"io_code": 17, "category": "legal"},
}


# =============================================================================
# DISAMBIGUATION ANCHORS
# =============================================================================

@dataclass
class DisambiguationAnchors:
    """
    Contextual anchors that help biographer_ai disambiguate between
    persons with similar names. These are RELATED NODES that constrain
    the search space.
    """
    # Subject anchor - the person being investigated
    subject_name: str
    subject_aliases: List[str] = dataclass_field(default_factory=list)

    # Location anchors - geographic constraints
    jurisdictions: List[str] = dataclass_field(default_factory=list)  # ISO codes: ["US", "UK", "DE"]
    countries: List[str] = dataclass_field(default_factory=list)  # Full names
    cities: List[str] = dataclass_field(default_factory=list)
    regions: List[str] = dataclass_field(default_factory=list)

    # Temporal anchors - time constraints
    date_of_birth: Optional[str] = None
    year_of_birth: Optional[int] = None
    age_range: Optional[tuple] = None  # (min_age, max_age)
    active_period: Optional[tuple] = None  # (start_year, end_year)

    # Industry/Sector anchors
    industries: List[str] = dataclass_field(default_factory=list)  # ["finance", "tech"]
    sectors: List[str] = dataclass_field(default_factory=list)  # NACE codes

    # Phenomena anchors - notable events
    phenomena: List[str] = dataclass_field(default_factory=list)  # ["ipo", "sanctions", "bankruptcy"]

    # Related entities (for disambiguation via association)
    related_companies: List[str] = dataclass_field(default_factory=list)
    related_persons: List[str] = dataclass_field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject": {
                "name": self.subject_name,
                "aliases": self.subject_aliases,
            },
            "location": {
                "jurisdictions": self.jurisdictions,
                "countries": self.countries,
                "cities": self.cities,
                "regions": self.regions,
            },
            "temporal": {
                "date_of_birth": self.date_of_birth,
                "year_of_birth": self.year_of_birth,
                "age_range": self.age_range,
                "active_period": self.active_period,
            },
            "industry": {
                "industries": self.industries,
                "sectors": self.sectors,
            },
            "phenomena": self.phenomena,
            "related_entities": {
                "companies": self.related_companies,
                "persons": self.related_persons,
            },
        }

    def has_anchors(self) -> bool:
        """Check if any disambiguation anchors are set."""
        return any([
            self.jurisdictions, self.countries, self.cities,
            self.date_of_birth, self.year_of_birth,
            self.industries, self.phenomena,
            self.related_companies, self.related_persons
        ])


# =============================================================================
# IO ROUTING SUGGESTIONS
# =============================================================================

@dataclass
class IORoutingSuggestion:
    """
    A suggested IO source/module that can fill an unfilled slot.
    """
    field_name: str
    io_code: Optional[int]
    module: str  # "eyed", "corporella", "alldom", etc.
    module_path: str
    description: str
    friction: str  # "Open", "Paywalled", "Subscription"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field_name,
            "io_code": self.io_code,
            "module": self.module,
            "path": self.module_path,
            "description": self.description,
            "friction": self.friction,
        }


def get_routing_suggestions_for_field(field_name: str) -> List[IORoutingSuggestion]:
    """
    Get IO modules that can provide data for a given field.
    Uses the modules.json execution methods.
    """
    suggestions = []

    # Get IO code for field
    io_code = None
    schema_entry = PERSON_NODE_SCHEMA.get(field_name, {})
    if schema_entry:
        io_code = schema_entry.get("io_code")

    if not io_code:
        io_code = IO_FIELD_TO_CODE.get(field_name)

    # Find modules that output this code
    for mod_name, mod_info in EXECUTION_MODULES.items():
        outputs = mod_info.get("outputs", [])
        if io_code and io_code in outputs:
            suggestions.append(IORoutingSuggestion(
                field_name=field_name,
                io_code=io_code,
                module=mod_name,
                module_path=mod_info.get("path", ""),
                description=mod_info.get("description", ""),
                friction=mod_info.get("friction", "Unknown"),
            ))

    return suggestions


def get_all_routing_suggestions(filled_fields: Set[str]) -> Dict[str, List[IORoutingSuggestion]]:
    """
    For all unfilled person node fields, get routing suggestions.

    Args:
        filled_fields: Set of field names that already have data

    Returns:
        Dict mapping unfilled field names to routing suggestions
    """
    suggestions = {}

    for field_name in PERSON_NODE_SCHEMA.keys():
        if field_name not in filled_fields:
            field_suggestions = get_routing_suggestions_for_field(field_name)
            if field_suggestions:
                suggestions[field_name] = field_suggestions

    return suggestions


@dataclass
class WatcherContext:
    """
    Context attached to a watcher.

    This includes the entities, topics, and any other context
    that helps the watcher understand what to look for.
    """
    watcher_id: str
    watcher_type: str  # "entity", "topic", "event", "generic"
    prompt: str
    section_header: str

    # Attached context
    monitored_entities: List[str] = dataclass_field(default_factory=list)
    monitored_topics: List[str] = dataclass_field(default_factory=list)
    monitored_events: List[str] = dataclass_field(default_factory=list)

    # Findings received
    findings_count: int = 0
    recent_findings: List[Dict[str, Any]] = dataclass_field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "watcher_id": self.watcher_id,
            "watcher_type": self.watcher_type,
            "prompt": self.prompt,
            "section_header": self.section_header,
            "monitored_entities": self.monitored_entities,
            "monitored_topics": self.monitored_topics,
            "monitored_events": self.monitored_events,
            "findings_count": self.findings_count,
            "recent_findings": self.recent_findings[-5:],  # Last 5 only
        }


@dataclass
class BiographerContext:
    """
    Full context for biographer_ai disambiguation decisions.

    This is what biographer_ai receives when making ADD/REJECT decisions.

    IMPORTANT: Biographer reads project context FIRST and pre-populates
    discernable attributes like jurisdiction. These anchors help disambiguate.
    """
    # Identity
    project_id: str
    person_name: str

    # Project Note (with template populated)
    project_note_id: str
    project_note_label: str
    project_note_sections: List[Dict[str, Any]]
    project_note_content: str  # Current markdown content

    # Primary Node (what we know so far)
    primary_node: Dict[str, Any]

    # Active Watchers + Context
    watchers: List[WatcherContext]

    # Source tracking (for verification decisions)
    field_sources: Dict[str, List[str]]  # field_name -> list of sources

    # Pending findings to process
    pending_findings: List[Dict[str, Any]] = dataclass_field(default_factory=list)

    # DISAMBIGUATION ANCHORS (NEW)
    # Related nodes that help constrain the search space
    disambiguation: Optional[DisambiguationAnchors] = None

    # IO ROUTING SUGGESTIONS (NEW)
    # What sources can fill unfilled slots in the person node schema
    routing_suggestions: Dict[str, List[Dict[str, Any]]] = dataclass_field(default_factory=dict)

    # Filled vs Unfilled fields
    filled_fields: List[str] = dataclass_field(default_factory=list)
    unfilled_fields: List[str] = dataclass_field(default_factory=list)

    # Metadata
    created_at: str = dataclass_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "person_name": self.person_name,
            "project_note": {
                "note_id": self.project_note_id,
                "label": self.project_note_label,
                "sections": self.project_note_sections,
                "content_preview": self.project_note_content[:2000] if self.project_note_content else "",
            },
            "primary_node": self.primary_node,
            "watchers": [w.to_dict() for w in self.watchers],
            "field_sources": self.field_sources,
            "pending_findings_count": len(self.pending_findings),
            # NEW: Disambiguation and routing
            "disambiguation": self.disambiguation.to_dict() if self.disambiguation else None,
            "routing_suggestions": self.routing_suggestions,
            "filled_fields": self.filled_fields,
            "unfilled_fields": self.unfilled_fields,
            "created_at": self.created_at,
        }

    def to_prompt_context(self) -> str:
        """
        Format context as a string for inclusion in biographer_ai prompt.

        CRITICAL: This is what biographer_ai uses for disambiguation decisions.
        It includes:
        1. Disambiguation anchors (location, temporal, industry, phenomena)
        2. IO routing suggestions (what sources can fill unfilled slots)
        """
        lines = [
            "## BIOGRAPHER CONTEXT",
            "",
            f"**Person:** {self.person_name}",
            f"**Project:** {self.project_id}",
        ]

        # DISAMBIGUATION ANCHORS (NEW) - Critical for disambiguation
        if self.disambiguation and self.disambiguation.has_anchors():
            lines.extend([
                "",
                "### Disambiguation Anchors",
                "Use these to constrain and validate incoming data:",
            ])
            d = self.disambiguation
            if d.jurisdictions:
                lines.append(f"  **Jurisdictions:** {', '.join(d.jurisdictions)}")
            if d.countries:
                lines.append(f"  **Countries:** {', '.join(d.countries)}")
            if d.cities:
                lines.append(f"  **Cities:** {', '.join(d.cities)}")
            if d.date_of_birth or d.year_of_birth:
                dob = d.date_of_birth or f"~{d.year_of_birth}"
                lines.append(f"  **DOB:** {dob}")
            if d.industries:
                lines.append(f"  **Industries:** {', '.join(d.industries)}")
            if d.phenomena:
                lines.append(f"  **Phenomena:** {', '.join(d.phenomena)}")
            if d.related_companies:
                lines.append(f"  **Related Companies:** {', '.join(d.related_companies[:5])}")
            if d.related_persons:
                lines.append(f"  **Related Persons:** {', '.join(d.related_persons[:5])}")

        lines.extend([
            "",
            "### Project Note",
            f"Note ID: {self.project_note_id}",
            f"Label: {self.project_note_label}",
            "",
            "**Sections:**",
        ])

        for section in self.project_note_sections:
            watcher_status = "[WATCHER ACTIVE]" if section.get("watcher_id") else ""
            lines.append(f"  - {section.get('header', 'Unknown')} {watcher_status}")

        lines.extend([
            "",
            "### Primary Node (Current Data)",
        ])

        # Show what's in primary node
        props = self.primary_node.get("props", {})
        for field, value in props.items():
            if value and field not in ["created_at", "updated_at"]:
                sources = self.field_sources.get(field, [])
                source_str = f" (from: {', '.join(sources)})" if sources else ""
                lines.append(f"  - {field}: {value}{source_str}")

        # IO ROUTING SUGGESTIONS (NEW) - Show what sources can fill unfilled slots
        if self.routing_suggestions:
            lines.extend([
                "",
                "### IO Routing (Unfilled Fields → Sources)",
                "These sources can fill the remaining slots:",
            ])
            for field_name, suggestions in list(self.routing_suggestions.items())[:10]:
                if suggestions:
                    modules = [s.get("module", "unknown") for s in suggestions]
                    lines.append(f"  • **{field_name}** → {', '.join(set(modules))}")

        lines.extend([
            "",
            "### Active Watchers",
        ])

        for watcher in self.watchers:
            lines.append(f"  - **{watcher.section_header}** [{watcher.watcher_type}]")
            lines.append(f"    Prompt: \"{watcher.prompt}\"")
            if watcher.monitored_entities:
                lines.append(f"    Entities: {', '.join(watcher.monitored_entities)}")
            if watcher.monitored_topics:
                lines.append(f"    Topics: {', '.join(watcher.monitored_topics)}")
            lines.append(f"    Findings: {watcher.findings_count}")

        if self.pending_findings:
            lines.extend([
                "",
                f"### Pending Findings ({len(self.pending_findings)})",
            ])
            for i, finding in enumerate(self.pending_findings[:10], 1):
                lines.append(f"  {i}. {finding.get('field_name')}: {finding.get('extracted_value')}")
                lines.append(f"     Source: {finding.get('source_action')} | Relevance: {finding.get('relevance_score', 0):.2f}")

        return "\n".join(lines)


async def assemble_biographer_context(
    project_id: str,
    person_name: str,
    project_note: Optional[Any] = None,
    primary_node: Optional[Node] = None,
    watcher: Optional[BiographerWatcher] = None,
    section_watchers: Optional[List[BiographerWatcher]] = None,
    pending_findings: Optional[List[WatcherFinding]] = None,
    watcher_bridge: Optional[Any] = None,
    narrative_bridge: Optional[Any] = None,
    # NEW: Disambiguation context
    jurisdiction: Optional[str] = None,
    jurisdictions: Optional[List[str]] = None,
    country: Optional[str] = None,
    city: Optional[str] = None,
    industry: Optional[str] = None,
    phenomena: Optional[List[str]] = None,
    related_companies: Optional[List[str]] = None,
    related_persons: Optional[List[str]] = None,
) -> BiographerContext:
    """
    Assemble full context for biographer_ai.

    CRITICAL: Biographer reads project context FIRST and pre-populates
    discernable attributes. This enables proper disambiguation.

    This gathers:
    1. Project note (with sections/content)
    2. Primary node data
    3. Active watchers + their context
    4. Field source tracking
    5. Pending findings to process
    6. NEW: Disambiguation anchors (location, temporal, industry, phenomena)
    7. NEW: IO routing suggestions (unfilled fields → sources)

    Args:
        project_id: Project ID
        person_name: Person's name
        project_note: ProjectNote instance (or will fetch)
        primary_node: Primary person node (or empty)
        watcher: Main BiographerWatcher
        section_watchers: List of section watchers
        pending_findings: Findings waiting for decisions
        watcher_bridge: Optional WatcherBridge
        narrative_bridge: Optional NarrativeBridge
        # Disambiguation parameters (can be pre-populated from project context)
        jurisdiction: Primary jurisdiction ISO code (e.g., "US", "UK")
        jurisdictions: List of relevant jurisdictions
        country: Country name
        city: City name
        industry: Primary industry
        phenomena: Notable events ["ipo", "sanctions", "litigation"]
        related_companies: Companies associated with person
        related_persons: Persons associated with person

    Returns:
        BiographerContext ready for biographer_ai
    """
    # Default values
    project_note_id = f"note_{project_id}"
    project_note_label = f"{person_name} - Profile"
    project_note_sections = []
    project_note_content = ""

    # Extract from project note if provided
    if project_note:
        project_note_id = project_note.note_id
        project_note_label = project_note.label
        project_note_sections = [s.to_dict() for s in project_note.sections]
        project_note_content = project_note.get_markdown()
    elif narrative_bridge or BRIDGES_AVAILABLE:
        # Try to fetch project note
        bridge = narrative_bridge or NarrativeBridge()
        try:
            notes = await bridge.get_project_notes(project_id)
            if notes:
                note = notes[0]  # First note is default
                project_note_id = note.get("id", project_note_id)
                project_note_label = note.get("label", project_note_label)
                project_note_content = note.get("content", "")
        except Exception as e:
            logger.debug(f"Failed to fetch project notes: {e}")

    # Extract primary node data
    primary_node_dict = {}
    if primary_node:
        primary_node_dict = primary_node.to_dict()

    # Build field source tracking
    field_sources = {}
    if primary_node:
        # Track sources for each field with data
        for field, value in primary_node.props.items():
            if value:
                # Check metadata for sources
                sources = primary_node.metadata.get("field_sources", {}).get(field, [])
                if sources:
                    field_sources[field] = sources

    # Build watcher contexts
    watcher_contexts = []

    # Main watcher
    if watcher:
        main_watcher_ctx = WatcherContext(
            watcher_id=watcher.watcher_id,
            watcher_type=watcher.watcher_type.value if hasattr(watcher.watcher_type, 'value') else str(watcher.watcher_type),
            prompt=watcher.prompt,
            section_header="[Main Watcher]",
            monitored_entities=[person_name],
            findings_count=watcher.findings_count,
        )
        watcher_contexts.append(main_watcher_ctx)

    # Section watchers
    if section_watchers:
        for sw in section_watchers:
            # Determine monitored items based on watcher type
            entities = [person_name]
            topics = []
            events = []

            watcher_type = sw.watcher_type.value if hasattr(sw.watcher_type, 'value') else str(sw.watcher_type)

            if watcher_type == "topic":
                topics = ["sanctions", "pep"]
            elif watcher_type == "event":
                events = ["lawsuit", "litigation"]
            elif watcher_type == "entity":
                entities.extend(["directors", "officers"])

            ctx = WatcherContext(
                watcher_id=sw.watcher_id,
                watcher_type=watcher_type,
                prompt=sw.prompt,
                section_header=sw.name,
                monitored_entities=entities,
                monitored_topics=topics,
                monitored_events=events,
                findings_count=getattr(sw, 'findings_count', 0),
            )
            watcher_contexts.append(ctx)

    # Fetch active watchers from system if bridge available
    if (not watcher_contexts or len(watcher_contexts) < 2) and (watcher_bridge or BRIDGES_AVAILABLE):
        bridge = watcher_bridge or WatcherBridge()
        try:
            active_watchers = await bridge.get_active_watchers()
            for aw in active_watchers:
                if aw.get("projectId") == project_id:
                    ctx = WatcherContext(
                        watcher_id=aw.get("id", ""),
                        watcher_type=aw.get("type", "generic"),
                        prompt=aw.get("query", ""),
                        section_header=aw.get("label", "Unknown"),
                        monitored_entities=aw.get("monitoredEntities", []),
                        monitored_topics=aw.get("monitoredTopics", []),
                        monitored_events=aw.get("monitoredEvents", []),
                    )
                    watcher_contexts.append(ctx)
        except Exception as e:
            logger.debug(f"Failed to fetch active watchers: {e}")

    # Convert pending findings to dicts
    pending_findings_dicts = []
    if pending_findings:
        pending_findings_dicts = [
            f.to_dict() if hasattr(f, 'to_dict') else f
            for f in pending_findings
        ]

    # =========================================================================
    # NEW: Build Disambiguation Anchors
    # =========================================================================
    # Pre-populate from provided context and extract from primary node
    all_jurisdictions = list(jurisdictions or [])
    if jurisdiction and jurisdiction not in all_jurisdictions:
        all_jurisdictions.insert(0, jurisdiction)

    # Extract additional anchors from primary node if available
    node_props = primary_node_dict.get("props", {}) if primary_node_dict else {}

    # Try to extract jurisdiction from addresses
    if not all_jurisdictions and node_props.get("addresses"):
        addrs = node_props["addresses"]
        if isinstance(addrs, list) and addrs:
            # Simple extraction - could be enhanced
            for addr in addrs[:3]:
                if isinstance(addr, dict) and addr.get("country"):
                    c = addr["country"]
                    if len(c) == 2:
                        all_jurisdictions.append(c.upper())

    # Try to extract industry from corporate roles
    extracted_industries = list([industry] if industry else [])
    if node_props.get("corporate_roles"):
        roles = node_props["corporate_roles"]
        if isinstance(roles, list):
            for role in roles[:5]:
                if isinstance(role, dict) and role.get("industry"):
                    if role["industry"] not in extracted_industries:
                        extracted_industries.append(role["industry"])

    # Build disambiguation anchors
    disambiguation_anchors = DisambiguationAnchors(
        subject_name=person_name,
        subject_aliases=[],  # Could extract from secondary nodes
        jurisdictions=all_jurisdictions,
        countries=[country] if country else [],
        cities=[city] if city else [],
        industries=extracted_industries,
        phenomena=phenomena or [],
        related_companies=related_companies or [],
        related_persons=related_persons or [],
    )

    # =========================================================================
    # NEW: Calculate Filled vs Unfilled Fields
    # =========================================================================
    filled_fields_list = []
    unfilled_fields_list = []

    for field_name in PERSON_NODE_SCHEMA.keys():
        value = node_props.get(field_name)
        if value:
            filled_fields_list.append(field_name)
        else:
            unfilled_fields_list.append(field_name)

    # =========================================================================
    # NEW: Get IO Routing Suggestions for Unfilled Fields
    # =========================================================================
    routing_suggestions_dict = {}
    filled_set = set(filled_fields_list)
    all_suggestions = get_all_routing_suggestions(filled_set)

    for field_name, suggestions in all_suggestions.items():
        routing_suggestions_dict[field_name] = [s.to_dict() for s in suggestions]

    return BiographerContext(
        project_id=project_id,
        person_name=person_name,
        project_note_id=project_note_id,
        project_note_label=project_note_label,
        project_note_sections=project_note_sections,
        project_note_content=project_note_content,
        primary_node=primary_node_dict,
        watchers=watcher_contexts,
        field_sources=field_sources,
        pending_findings=pending_findings_dicts,
        # NEW: Disambiguation and routing
        disambiguation=disambiguation_anchors,
        routing_suggestions=routing_suggestions_dict,
        filled_fields=filled_fields_list,
        unfilled_fields=unfilled_fields_list,
    )


def format_context_for_ai(context: BiographerContext) -> str:
    """
    Format BiographerContext as a string for AI prompt injection.

    This is what gets prepended to biographer_ai's input.
    """
    return context.to_prompt_context()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def get_biographer_context(
    project_id: str,
    person_name: str,
    node_set: Optional[BiographerNodeSet] = None,
    project_note: Optional[Any] = None,
    watcher: Optional[BiographerWatcher] = None,
) -> str:
    """
    Get formatted context string for biographer_ai.

    Convenience function that assembles and formats context.

    Args:
        project_id: Project ID
        person_name: Person's name
        node_set: BiographerNodeSet with primary/secondary nodes
        project_note: ProjectNote instance
        watcher: BiographerWatcher instance

    Returns:
        Formatted context string for AI prompt
    """
    primary_node = None
    if node_set:
        primary_node = node_set.primary_node

    context = await assemble_biographer_context(
        project_id=project_id,
        person_name=person_name,
        project_note=project_note,
        primary_node=primary_node,
        watcher=watcher,
    )

    return format_context_for_ai(context)


# =============================================================================
# EXAMPLE / TESTING
# =============================================================================

if __name__ == "__main__":
    import asyncio
    from .nodes import create_biographer_node_set

    async def test_context():
        # Create node set
        node_set = create_biographer_node_set(
            name="John Smith",
            raw_input="p: John Smith"
        )

        # Add some data to primary node
        node_set.primary_node.props["emails"] = ["john@example.com"]
        node_set.primary_node.props["phones"] = ["+1234567890"]
        node_set.primary_node.metadata["field_sources"] = {
            "emails": ["eyed"],
            "phones": ["eyed"],
        }

        # Assemble context
        context = await assemble_biographer_context(
            project_id="proj_test123",
            person_name="John Smith",
            primary_node=node_set.primary_node,
        )

        print("=" * 60)
        print("BIOGRAPHER CONTEXT TEST")
        print("=" * 60)
        print()
        print(context.to_prompt_context())
        print()
        print("=" * 60)
        print("JSON DICT:")
        print("=" * 60)
        print(json.dumps(context.to_dict(), indent=2, default=str))

    asyncio.run(test_context())
