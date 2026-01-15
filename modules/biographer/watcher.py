#!/usr/bin/env python3
"""
BIOGRAPHER Watcher Integration

Integrates with the SASTRE watcher system and Project Note system for person searches.

Architecture:
    1. Project has default "Project Note" (auto-created)
    2. Templates (person profile) loaded into project note
    3. Watchers created as headers in project note
    4. All BRUTE query results scanned by Haiku
    5. Findings streamed to project note under section headings

When a person search starts:
    1. Initialize project note with person profile template
    2. Create watcher with prompt "all about [name]"
    3. Watcher headers in project note: Identity, Corporate, Social, etc.
    4. All subsequent BRUTE searches → watcher.execute() (Haiku scans)
    5. Findings stream to project note sections
    6. biographer_ai reviews and applies verification decisions

Project Note Sections (from template):
    ## Identity & Contact
    ## Corporate Affiliations
    ## Social Profiles
    ## Breach Exposure
    ## Sanctions & Watchlists
    ## Litigation & Legal
"""

import json
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field as dataclass_field
from enum import Enum

from .nodes import Node, generate_id
from .verification import (
    DecisionAction,
    BiographerDecision,
    apply_decision,
    VerificationStatus,
    values_match,  # Use shared implementation
)

logger = logging.getLogger(__name__)

# Import bridges using same pattern as ThinOrchestrator
import sys
import importlib.util

_bridges_file = Path(__file__).parent.parent / "sastre" / "bridges.py"
if _bridges_file.exists():
    _spec = importlib.util.spec_from_file_location("bridges_module", _bridges_file)
    _bridges_module = importlib.util.module_from_spec(_spec)
    try:
        _spec.loader.exec_module(_bridges_module)
        WatcherBridge = _bridges_module.WatcherBridge
        CymonidesBridge = _bridges_module.CymonidesBridge
        BRIDGES_AVAILABLE = True
    except Exception as e:
        logger.debug(f"SASTRE bridges not available: {e}")
        BRIDGES_AVAILABLE = False
        WatcherBridge = None
        CymonidesBridge = None
else:
    BRIDGES_AVAILABLE = False
    WatcherBridge = None
    CymonidesBridge = None

# Import Project Note system
try:
    from ..sastre.narrative.project_note import (
        ProjectNote,
        ProjectNoteSection,
        initialize_biographer_note,
        stream_finding_to_section as project_stream_finding,
    )
    PROJECT_NOTE_AVAILABLE = True
except ImportError:
    PROJECT_NOTE_AVAILABLE = False
    ProjectNote = None
    ProjectNoteSection = None


# Default headings for person profile notes
PERSON_NOTE_HEADINGS = [
    "Identity & Contact",
    "Corporate Affiliations",
    "Social Profiles",
    "Breach Exposure",
    "Sanctions & Watchlists",
    "Litigation & Legal",
]


class WatcherType(Enum):
    """Types of watchers that can be created for biographer."""
    ENTITY = "entity"     # Monitor for person/company entity mentions
    TOPIC = "topic"       # Monitor for sanctions, PEP status
    EVENT = "event"       # Monitor for litigation, court cases
    GENERIC = "generic"   # Header-based content matching


@dataclass
class BiographerWatcher:
    """
    Watcher specification for biographer person searches.

    Attached to:
    - project_id: The investigation project
    - parent_document_id: The dedicated person note
    - subject_node_id: The primary person node (for context)
    """
    watcher_id: str
    name: str
    prompt: str  # "all about [name]"
    project_id: str
    parent_document_id: str  # Dedicated note for findings
    subject_node_id: str     # Primary person node
    query_node_id: str
    watcher_type: WatcherType = WatcherType.GENERIC
    section_mappings: Dict[str, str] = dataclass_field(default_factory=dict)
    created_at: str = dataclass_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "active"
    findings_count: int = 0
    decisions_made: List[Dict[str, Any]] = dataclass_field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "watcher_id": self.watcher_id,
            "name": self.name,
            "prompt": self.prompt,
            "project_id": self.project_id,
            "parent_document_id": self.parent_document_id,
            "subject_node_id": self.subject_node_id,
            "query_node_id": self.query_node_id,
            "watcher_type": self.watcher_type.value,
            "section_mappings": self.section_mappings,
            "created_at": self.created_at,
            "status": self.status,
            "findings_count": self.findings_count,
            "decisions_count": len(self.decisions_made),
        }


@dataclass
class WatcherFinding:
    """
    A finding detected by watcher scanning.

    When Haiku scans BRUTE results, findings matching
    the watcher criteria are captured here.
    """
    finding_id: str
    watcher_id: str
    source_action: str      # Which BRUTE action found this
    source_url: str
    title: str
    content: str
    snippet: Optional[str]
    field_name: str         # Which profile field this maps to
    extracted_value: Any
    relevance_score: float
    section_heading: str    # Which note section to route to
    timestamp: str = dataclass_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "watcher_id": self.watcher_id,
            "source_action": self.source_action,
            "source_url": self.source_url,
            "title": self.title,
            "content": self.content,
            "snippet": self.snippet,
            "field_name": self.field_name,
            "extracted_value": self.extracted_value,
            "relevance_score": self.relevance_score,
            "section_heading": self.section_heading,
            "timestamp": self.timestamp,
        }


# =============================================================================
# WATCHER CREATION
# =============================================================================

async def create_biographer_watcher(
    name: str,
    project_id: str,
    parent_document_id: str,
    subject_node_id: str,
    query_node_id: str,
    watcher_bridge: Optional[Any] = None,
) -> BiographerWatcher:
    """
    Create a biographer watcher attached to project and document.

    Args:
        name: Person name being searched
        project_id: Graph project ID for watcher attachment
        parent_document_id: Dedicated note ID for findings
        subject_node_id: Primary person node ID
        query_node_id: Query node ID
        watcher_bridge: Optional WatcherBridge instance

    Returns:
        BiographerWatcher instance (registered with system if bridge available)
    """
    watcher_id = generate_id("bio_watch_")
    prompt = f"all about {name}"

    # Map field types to note sections
    section_mappings = {
        "emails": "Identity & Contact",
        "phones": "Identity & Contact",
        "names": "Identity & Contact",
        "addresses": "Identity & Contact",
        "linkedin_url": "Social Profiles",
        "social_profiles": "Social Profiles",
        "corporate_roles": "Corporate Affiliations",
        "employment": "Corporate Affiliations",
        "breach_exposure": "Breach Exposure",
        "sanctions": "Sanctions & Watchlists",
        "pep_status": "Sanctions & Watchlists",
        "litigation": "Litigation & Legal",
        "court_cases": "Litigation & Legal",
    }

    watcher = BiographerWatcher(
        watcher_id=watcher_id,
        name=name,
        prompt=prompt,
        project_id=project_id,
        parent_document_id=parent_document_id,
        subject_node_id=subject_node_id,
        query_node_id=query_node_id,
        section_mappings=section_mappings,
    )

    # Register with WatcherBridge if available
    if watcher_bridge or BRIDGES_AVAILABLE:
        bridge = watcher_bridge or WatcherBridge()
        try:
            # Create the watcher in the system
            result = await bridge.create(
                name=f"biographer:{name}",
                project_id=project_id,
                query=prompt,
                parent_document_id=parent_document_id,
            )

            if result and result.get("id"):
                watcher.watcher_id = result["id"]

                # Add subject node as context
                await bridge.add_context(watcher.watcher_id, subject_node_id)

        except Exception as e:
            # Non-fatal - watcher works in local mode
            logger.warning(f"Failed to register watcher with bridge: {e}")

    return watcher


async def create_section_watchers(
    name: str,
    project_id: str,
    parent_document_id: str,
    subject_node_id: str,
    watcher_bridge: Optional[Any] = None,
) -> List[BiographerWatcher]:
    """
    Create specialized watchers for each note section.

    Creates targeted watchers:
    - Entity watcher for persons mentioned
    - Topic watcher for sanctions/PEP
    - Event watcher for litigation
    - Generic watchers for other sections

    Args:
        name: Person name
        project_id: Project ID
        parent_document_id: Dedicated note ID
        subject_node_id: Primary person node
        watcher_bridge: Optional WatcherBridge

    Returns:
        List of created watchers
    """
    watchers = []
    bridge = watcher_bridge or (WatcherBridge() if BRIDGES_AVAILABLE else None)

    if not bridge:
        return watchers

    for heading in PERSON_NOTE_HEADINGS:
        heading_lower = heading.lower()
        result = None

        try:
            if "sanctions" in heading_lower or "watchlist" in heading_lower:
                # Topic watcher for sanctions/PEP
                result = await bridge.create_topic_watcher(
                    project_id=project_id,
                    label=heading,
                    monitored_topic="sanctions",
                    monitored_entities=[name],
                    parent_document_id=parent_document_id,
                )
                watcher_type = WatcherType.TOPIC

            elif "litigation" in heading_lower or "legal" in heading_lower:
                # Event watcher for court cases
                result = await bridge.create_event_watcher(
                    project_id=project_id,
                    monitored_event="lawsuit",
                    label=heading,
                    monitored_entities=[name],
                    parent_document_id=parent_document_id,
                )
                watcher_type = WatcherType.EVENT

            elif "corporate" in heading_lower or "affiliation" in heading_lower:
                # Entity watcher for company roles
                result = await bridge.create_entity_watcher(
                    project_id=project_id,
                    label=heading,
                    monitored_types=["company"],
                    parent_document_id=parent_document_id,
                )
                watcher_type = WatcherType.ENTITY

            else:
                # Generic header-based watcher
                result = await bridge.create(
                    name=f"{heading} ({name})",
                    project_id=project_id,
                    query=f"{heading} for {name}",
                    parent_document_id=parent_document_id,
                )
                watcher_type = WatcherType.GENERIC

            if result and result.get("id"):
                watcher = BiographerWatcher(
                    watcher_id=result["id"],
                    name=heading,
                    prompt=f"{heading} for {name}",
                    project_id=project_id,
                    parent_document_id=parent_document_id,
                    subject_node_id=subject_node_id,
                    query_node_id="",  # Section watchers don't have query node
                    watcher_type=watcher_type,
                )
                watchers.append(watcher)

                # Add context
                await bridge.add_context(result["id"], subject_node_id)

        except Exception as e:
            logger.warning(f"Failed to create watcher for {heading}: {e}")

    return watchers


# =============================================================================
# WATCHER EXECUTION (Scanning BRUTE Results)
# =============================================================================

async def execute_watcher_scan(
    watcher: BiographerWatcher,
    results: List[Dict[str, Any]],
    watcher_bridge: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Execute watcher scan against BRUTE query results.

    This is called after any BRUTE search to check if results
    match the watcher criteria. Haiku evaluates relevance.

    Args:
        watcher: BiographerWatcher to execute
        results: List of search results to scan
        watcher_bridge: Optional WatcherBridge

    Returns:
        Dict with findings summary
    """
    bridge = watcher_bridge or (WatcherBridge() if BRIDGES_AVAILABLE else None)

    if not bridge:
        return {"success": False, "error": "WatcherBridge not available"}

    # Normalize results for watcher execution
    normalized = []
    for r in results:
        normalized.append({
            "title": r.get("title", r.get("name", "Unknown")),
            "url": r.get("url", r.get("source", "")),
            "content": r.get("content", r.get("description", "")),
            "snippet": r.get("snippet", r.get("excerpt", "")),
            "sourceId": r.get("id", ""),
        })

    try:
        result = await bridge.execute(
            project_id=watcher.project_id,
            results=normalized,
            query=watcher.prompt,
        )

        watcher.findings_count += result.get("findings", {}).get("total", 0)
        return result

    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# STREAMING FINDINGS TO DOCUMENT SECTIONS
# =============================================================================

async def stream_finding_to_note(
    finding: WatcherFinding,
    watcher: BiographerWatcher,
    cymonides_bridge: Optional[Any] = None,
) -> bool:
    """
    Stream a finding to the dedicated note under its section heading.

    Args:
        finding: WatcherFinding to stream
        watcher: BiographerWatcher with parent document
        cymonides_bridge: Optional CymonidesBridge

    Returns:
        True if successful
    """
    bridge = cymonides_bridge or (CymonidesBridge() if BRIDGES_AVAILABLE else None)

    if not bridge:
        return False

    try:
        # Format finding text
        finding_text = f"- {finding.extracted_value}"
        if finding.snippet:
            finding_text += f" ({finding.snippet[:100]}...)"

        # Stream to section with footnote
        return await bridge.stream_finding_to_section(
            document_id=watcher.parent_document_id,
            section_title=finding.section_heading,
            finding_text=finding_text,
            source_url=finding.source_url,
        )

    except Exception as e:
        logger.error(f"Error streaming finding: {e}")
        return False


# =============================================================================
# DECISION PROCESSING
# =============================================================================

def process_finding_decision(
    finding: WatcherFinding,
    watcher: BiographerWatcher,
    primary_node: Node,
    existing_sources: Dict[str, List[str]],
) -> BiographerDecision:
    """
    Process a finding and decide: ADD_VERIFIED, ADD_UNVERIFIED, or REJECT.

    This is called by biographer_ai when reviewing watcher findings.

    Args:
        finding: The finding to process
        watcher: Source watcher
        primary_node: Primary person node
        existing_sources: Dict mapping field_name -> list of sources

    Returns:
        BiographerDecision with action and reasoning
    """
    field_name = finding.field_name
    value = finding.extracted_value
    source = finding.source_action

    # Get existing data
    field_sources = existing_sources.get(field_name, [])
    existing_value = primary_node.props.get(field_name)

    # Decision logic
    if not existing_value:
        # First data for this field - add as unverified
        return BiographerDecision(
            action=DecisionAction.ADD_UNVERIFIED,
            field_name=field_name,
            value=value,
            source=source,
            watcher_id=watcher.watcher_id,
            confidence=finding.relevance_score,
        )

    # Check if value matches existing data
    if values_match(value, existing_value):
        # Corroborates existing data
        if source not in field_sources:
            # Different source - upgrade to verified
            return BiographerDecision(
                action=DecisionAction.ADD_VERIFIED,
                field_name=field_name,
                value=value,
                source=source,
                watcher_id=watcher.watcher_id,
                confidence=min(1.0, finding.relevance_score + 0.2),
            )
        else:
            # Same source - reject as duplicate
            return BiographerDecision(
                action=DecisionAction.REJECT,
                field_name=field_name,
                value=value,
                source=source,
                watcher_id=watcher.watcher_id,
                reject_reason=f"Duplicate data from same source ({source}). Already captured in primary node.",
            )

    # Value differs - check field type
    multi_value_fields = [
        "emails", "phones", "social_profiles", "corporate_roles",
        "addresses", "nationalities", "breach_exposure"
    ]

    if field_name in multi_value_fields:
        # Multi-value field - add as unverified (not contradictory)
        return BiographerDecision(
            action=DecisionAction.ADD_UNVERIFIED,
            field_name=field_name,
            value=value,
            source=source,
            watcher_id=watcher.watcher_id,
            confidence=finding.relevance_score,
        )

    # Single-value field with different value - add with low confidence
    return BiographerDecision(
        action=DecisionAction.ADD_UNVERIFIED,
        field_name=field_name,
        value=value,
        source=source,
        watcher_id=watcher.watcher_id,
        confidence=finding.relevance_score * 0.5,  # Lower for contradictions
    )


# =============================================================================
# FULL INITIALIZATION WITH PROJECT NOTE
# =============================================================================

async def initialize_biographer_with_project_note(
    person_name: str,
    project_id: str,
    subject_node_id: str,
    query_node_id: str,
    narrative_bridge: Optional[Any] = None,
    watcher_bridge: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Full initialization: Create project note → Load template → Create watchers.

    This is the recommended way to initialize biographer for a person search.

    Args:
        person_name: Person's name
        project_id: Project ID
        subject_node_id: Primary person node ID
        query_node_id: Query node ID
        narrative_bridge: Optional NarrativeBridge
        watcher_bridge: Optional WatcherBridge

    Returns:
        Dict with:
            - project_note: The initialized ProjectNote
            - watcher: The main BiographerWatcher
            - section_watchers: List of section-specific watchers
    """
    result = {
        "project_note": None,
        "watcher": None,
        "section_watchers": [],
    }

    # Step 1: Initialize project note (creates note + loads template + creates section watchers)
    if PROJECT_NOTE_AVAILABLE:
        try:
            project_note = await initialize_biographer_note(
                project_id=project_id,
                person_name=person_name,
                narrative_bridge=narrative_bridge,
                watcher_bridge=watcher_bridge,
            )
            result["project_note"] = project_note

            # Extract document ID from project note
            document_id = project_note.note_id

            # Create main biographer watcher attached to project note
            watcher = await create_biographer_watcher(
                name=person_name,
                project_id=project_id,
                parent_document_id=document_id,
                subject_node_id=subject_node_id,
                query_node_id=query_node_id,
                watcher_bridge=watcher_bridge,
            )
            result["watcher"] = watcher

            # Section watchers were already created by initialize_biographer_note
            # Extract them from project note
            for section in project_note.sections:
                if section.watcher_id:
                    result["section_watchers"].append({
                        "watcher_id": section.watcher_id,
                        "header": section.header,
                        "template_name": section.template_name,
                    })

            return result

        except Exception as e:
            logger.warning(f"Project note initialization failed: {e}")

    # Fallback: Create watcher without project note system
    try:
        watcher = await create_biographer_watcher(
            name=person_name,
            project_id=project_id,
            parent_document_id=f"doc_{project_id}",  # Placeholder
            subject_node_id=subject_node_id,
            query_node_id=query_node_id,
            watcher_bridge=watcher_bridge,
        )
        result["watcher"] = watcher

        # Create section watchers manually
        section_watchers = await create_section_watchers(
            name=person_name,
            project_id=project_id,
            parent_document_id=f"doc_{project_id}",
            subject_node_id=subject_node_id,
            watcher_bridge=watcher_bridge,
        )
        result["section_watchers"] = [w.to_dict() for w in section_watchers]

    except Exception as e:
        logger.warning(f"Fallback watcher creation failed: {e}")

    return result


# =============================================================================
# CLI / STATE PERSISTENCE
# =============================================================================

def save_watcher_state(watcher: BiographerWatcher, output_dir: Path) -> Path:
    """Save watcher state to file."""
    output_file = output_dir / f"watcher_{watcher.watcher_id}.json"
    with open(output_file, 'w') as f:
        json.dump(watcher.to_dict(), f, indent=2)
    return output_file


def load_watcher_state(watcher_file: Path) -> Dict[str, Any]:
    """Load watcher state from file."""
    with open(watcher_file, 'r') as f:
        return json.load(f)


# =============================================================================
# EXAMPLE / TESTING
# =============================================================================

if __name__ == "__main__":
    from .nodes import create_biographer_node_set

    async def test_watcher():
        # Create node set
        node_set = create_biographer_node_set(
            name="John Smith",
            raw_input="p: John Smith"
        )

        # Create watcher attached to project
        watcher = await create_biographer_watcher(
            name="John Smith",
            project_id="proj_test123",
            parent_document_id="doc_test456",
            subject_node_id=node_set.primary_node.node_id,
            query_node_id=node_set.query_node.node_id,
        )

        print(f"Created watcher: {watcher.watcher_id}")
        print(f"  Prompt: {watcher.prompt}")
        print(f"  Project: {watcher.project_id}")
        print(f"  Parent Doc: {watcher.parent_document_id}")
        print(f"  Subject Node: {watcher.subject_node_id}")

        # Simulate a finding
        finding = WatcherFinding(
            finding_id=generate_id("find_"),
            watcher_id=watcher.watcher_id,
            source_action="brute_search",
            source_url="https://example.com/johnsmith",
            title="John Smith Profile",
            content="John Smith is a director at Acme Corp",
            snippet="director at Acme Corp",
            field_name="corporate_roles",
            extracted_value={"company": "Acme Corp", "role": "Director"},
            relevance_score=0.85,
            section_heading="Corporate Affiliations",
        )

        # Process decision
        decision = process_finding_decision(
            finding=finding,
            watcher=watcher,
            primary_node=node_set.primary_node,
            existing_sources={},
        )

        print(f"\nDecision: {decision.action.value}")
        print(f"  Field: {decision.field_name}")
        print(f"  Value: {decision.value}")
        print(f"  Confidence: {decision.confidence}")
        if decision.reject_reason:
            print(f"  Reject Reason: {decision.reject_reason}")

    asyncio.run(test_watcher())
