"""
SASTRE Writer Agent

Streams findings to document sections in Nardello-style prose.
Routes findings to appropriate watchers based on entity/topic matches.
"""

from typing import Any, Dict, List, Optional
from ..sdk import Agent, Tool


SYSTEM_PROMPT = """You are the SASTRE Writer Agent (Sonnet 4.5).

You write investigation findings in professional Nardello-style prose.
Your role is to format raw findings into readable, properly cited text.

Key responsibilities:
1. Get active watchers (document sections waiting for content)
2. Route findings to appropriate sections based on entity/topic matches
3. Format findings with Core/Shell/Halo structure
4. Add proper footnote citations for all claims

Style guidelines:
- Professional investigative tone
- Objective language (avoid speculation markers unless confidence <0.7)
- Fact-first structure: lead with verified facts, then context
- Active voice, direct sentences
- Proper citation: "[Source Name, Date accessed]" or footnote markers [^1]

Core/Shell/Halo structure:
- **Core (Verified)**: Facts from official sources (registries, filings)
- **Shell (Probable)**: Facts from reliable secondary sources
- **Halo (Circumstantial)**: Context that suggests but doesn't prove

Watcher matching:
- Each document section has a watcher with target entities/topics
- Route findings to the watcher whose targets match the finding
- If no match, create a new section or append to "Other Findings"

Tools available:
- get_active_watchers: Get all document sections awaiting content
- stream_finding: Write a finding to a specific section
- add_footnote: Add a source reference
- check_watcher_match: Check if a finding matches a watcher's targets
"""


def get_active_watchers_handler(
    project_id: str = "default",
    context: Any = None
) -> Dict[str, Any]:
    """Get all active watchers (document sections) awaiting content."""
    from ..document import DocumentInterface

    # Get document interface from context or create default
    doc_interface = getattr(context, 'document_interface', None)
    if not doc_interface:
        # Return empty if no document loaded
        return {
            "watchers": [],
            "total_active": 0,
            "empty_sections": [],
        }

    watchers = doc_interface.get_watchers()
    empty_sections = doc_interface.get_empty_sections()

    return {
        "watchers": [
            {
                "id": w_data['id'],
                "section_id": w_data['section_id'],
                "section_header": header,
                "target_entities": w_data['target_entities'],
                "target_topics": w_data['target_topics'],
                "entity_types": w_data['entity_types'],
                "active": w_data['active'],
            }
            for header, w_data in watchers.items()
        ],
        "total_active": len(watchers),
        "empty_sections": [
            {"id": s.id, "header": s.clean_header}
            for s in empty_sections
        ],
    }


async def stream_finding_handler(
    section_id: str,
    entity_name: str,
    entity_type: str,
    content: str,
    source: str,
    confidence: float = 0.8,
    core: Optional[Dict[str, str]] = None,
    shell: Optional[Dict[str, str]] = None,
    halo: Optional[Dict[str, str]] = None,
    context: Any = None
) -> Dict[str, Any]:
    """Stream a finding to a document section."""
    import uuid
    from ..document import Finding, StreamEvent

    # Get document interface from context
    doc_interface = getattr(context, 'document_interface', None)
    if not doc_interface:
        return {"error": "No document loaded"}

    # Create finding
    finding = Finding(
        id=f"finding_{uuid.uuid4().hex[:8]}",
        entity_name=entity_name,
        entity_type=entity_type,
        content=content,
        source=source,
        confidence=confidence,
        metadata={
            "core": core or {},
            "shell": shell or {},
            "halo": halo or {},
        }
    )

    # Stream to section
    events = []
    async for event in doc_interface.stream_finding(finding, section_id):
        events.append({
            "event_type": event.event_type,
            "section_id": event.section_id,
            "section_header": event.section_header,
            "content_preview": event.content[:200] if event.content else "",
        })

    return {
        "success": True,
        "finding_id": finding.id,
        "events": events,
        "section_id": section_id,
    }


def add_footnote_handler(
    source: str,
    url: Optional[str] = None,
    access_date: Optional[str] = None,
    context: Any = None
) -> Dict[str, Any]:
    """Add a footnote reference and return its number."""
    from datetime import datetime

    doc_interface = getattr(context, 'document_interface', None)
    if not doc_interface:
        return {"error": "No document loaded"}

    # Format source with optional URL and date
    formatted_source = source
    if url:
        formatted_source += f" ({url})"
    if not access_date:
        access_date = datetime.now().strftime('%Y-%m-%d')
    formatted_source += f", accessed {access_date}"

    footnote_num = doc_interface.add_footnote(formatted_source)

    return {
        "footnote_number": footnote_num,
        "marker": f"[^{footnote_num}]",
        "source": formatted_source,
    }


def check_watcher_match_handler(
    entity_name: str,
    entity_type: str,
    topics: List[str] = None,
    context: Any = None
) -> Dict[str, Any]:
    """Check which watchers match a finding's entity/topics."""
    doc_interface = getattr(context, 'document_interface', None)
    if not doc_interface:
        return {"matches": [], "best_match": None}

    finding_dict = {
        "name": entity_name,
        "entity_type": entity_type,
        "topics": topics or [],
    }

    matching_watchers = doc_interface.watcher_registry.find_matching(finding_dict)

    matches = [
        {
            "id": w.id,
            "section_id": w.section_id,
            "section_header": w.section_header,
            "match_strength": "strong" if entity_name in w.target_entities else "weak",
        }
        for w in matching_watchers
    ]

    return {
        "matches": matches,
        "best_match": matches[0] if matches else None,
        "total_matches": len(matches),
    }


def format_finding_handler(
    entity_name: str,
    core: Dict[str, str] = None,
    shell: Dict[str, str] = None,
    halo: Dict[str, str] = None,
    source: str = "",
    footnote_num: int = None,
    context: Any = None
) -> Dict[str, Any]:
    """Format a finding as Nardello-style markdown."""
    lines = [f"### {entity_name}"]

    fn_marker = f" [^{footnote_num}]" if footnote_num else ""

    if core:
        lines.append("\n**Core (Verified)**")
        for key, value in core.items():
            lines.append(f"- {key}: {value}{fn_marker}")

    if shell:
        lines.append("\n**Shell (Probable)**")
        for key, value in shell.items():
            if value:
                lines.append(f"- {key}: {value}{fn_marker}")

    if halo:
        lines.append("\n**Halo (Circumstantial)**")
        for key, value in halo.items():
            if value:
                lines.append(f"- {key}: {value}")

    formatted = '\n'.join(lines)

    return {
        "formatted_content": formatted,
        "word_count": len(formatted.split()),
    }


def create_writer_agent() -> Agent:
    """Create the writer agent."""
    return Agent(
        name="writer",
        model="claude-sonnet-4-5-20250929",
        system_prompt=SYSTEM_PROMPT,
        tools=[
            Tool(
                name="get_active_watchers",
                description="Get all document sections (watchers) awaiting content",
                handler=get_active_watchers_handler,
                input_schema={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "default": "default"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="stream_finding",
                description="Write a finding to a document section with Core/Shell/Halo structure",
                handler=stream_finding_handler,
                input_schema={
                    "type": "object",
                    "properties": {
                        "section_id": {"type": "string", "description": "Target section ID"},
                        "entity_name": {"type": "string", "description": "Entity name (person, company, etc.)"},
                        "entity_type": {"type": "string", "description": "PERSON, COMPANY, ADDRESS, etc."},
                        "content": {"type": "string", "description": "Main content text"},
                        "source": {"type": "string", "description": "Source provenance"},
                        "confidence": {"type": "number", "default": 0.8},
                        "core": {"type": "object", "description": "Verified facts"},
                        "shell": {"type": "object", "description": "Probable facts"},
                        "halo": {"type": "object", "description": "Circumstantial context"}
                    },
                    "required": ["section_id", "entity_name", "entity_type", "content", "source"]
                }
            ),
            Tool(
                name="add_footnote",
                description="Add a source reference and get footnote number",
                handler=add_footnote_handler,
                input_schema={
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "description": "Source name/description"},
                        "url": {"type": "string", "description": "Optional URL"},
                        "access_date": {"type": "string", "description": "Optional access date (YYYY-MM-DD)"}
                    },
                    "required": ["source"]
                }
            ),
            Tool(
                name="check_watcher_match",
                description="Check which sections match a finding's entity/topics",
                handler=check_watcher_match_handler,
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_name": {"type": "string"},
                        "entity_type": {"type": "string"},
                        "topics": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["entity_name", "entity_type"]
                }
            ),
            Tool(
                name="format_finding",
                description="Format a finding as Nardello-style markdown",
                handler=format_finding_handler,
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_name": {"type": "string"},
                        "core": {"type": "object"},
                        "shell": {"type": "object"},
                        "halo": {"type": "object"},
                        "source": {"type": "string"},
                        "footnote_num": {"type": "integer"}
                    },
                    "required": ["entity_name"]
                }
            ),
        ]
    )
