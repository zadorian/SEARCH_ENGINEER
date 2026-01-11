"""
SASTRE Grid Assessor Agent

Evaluates investigation completeness from 4 perspectives (centricities).
Reports gaps and suggests next queries based on K-U quadrant analysis.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
from ..sdk import Agent, Tool
from ..contracts import KUQuadrant, Gap


class GridView(Enum):
    """Grid view modes - the 4 centricities."""
    NARRATIVE = "narrative"     # Document-centric: completeness of sections
    SUBJECT = "subject"         # Entity-centric: completeness per entity
    LOCATION = "location"       # Source-centric: coverage per jurisdiction/source
    NEXUS = "nexus"             # Intersection-centric: expected vs found connections


# KUQuadrant imported from contracts.py - single source of truth
# Gap imported from contracts.py - single source of truth


SYSTEM_PROMPT = """You are the SASTRE Grid Assessor (Sonnet 4.5).

You evaluate investigation completeness from 4 centricities:

1. **NARRATIVE View**: Document completeness
   - Which sections are empty?
   - Which sections have gaps [?] markers?
   - What's the citation density per section?

2. **SUBJECT View**: Entity completeness
   - Which entities have thin profiles?
   - Which entity types are underrepresented?
   - Are there entities mentioned but not profiled?

3. **LOCATION View**: Source completeness
   - Which jurisdictions have been searched?
   - Which source types are missing? (registries, news, social, etc.)
   - What's the temporal coverage?

4. **NEXUS View**: Connection completeness
   - Which entity pairs have EXPECTED but NOT FOUND connections?
   - Which have UNEXPECTED (Surprising AND) connections?
   - What's the overall network density?

K-U Quadrant Analysis:
- **VERIFY** (Known Subject + Known Location): We know X exists at Y, confirm details
- **TRACE** (Known Subject + Unknown Location): We know X, find where it appears
- **EXTRACT** (Unknown Subject + Known Location): We have Y, find what's there
- **DISCOVER** (Unknown Subject + Unknown Location): Pure exploration

For each gap, suggest a query using SASTRE syntax:
- Person enrichment: p: John Smith
- Company lookup: c: Acme Corp :US
- Backlinks: bl? :!domain.com
- Entity extraction: ent? :!domain.com
- Similarity search: =? :#target :@CLASS

Tools available:
- assess_narrative: Evaluate document sections
- assess_subjects: Evaluate entity profiles
- assess_locations: Evaluate source coverage
- assess_nexus: Evaluate connection completeness
- get_full_assessment: Combined assessment from all views
- suggest_next_queries: Get prioritized query suggestions
"""


def assess_narrative_handler(
    project_id: str = "default",
    context: Any = None
) -> Dict[str, Any]:
    """Assess document completeness from Narrative view."""
    doc_interface = getattr(context, 'document_interface', None)

    if not doc_interface:
        return {
            "view": "narrative",
            "status": "no_document",
            "sections": [],
            "gaps": [],
        }

    stats = doc_interface.get_statistics()
    gaps_list = doc_interface.get_gaps()
    empty = doc_interface.get_empty_sections()

    gaps = []
    for s in empty:
        gaps.append({
            "id": f"gap_{s.id}",
            "type": "empty_section",
            "section_id": s.id,
            "section_header": s.clean_header,
            "ku_quadrant": s.k_u_quadrant.value if hasattr(s, 'k_u_quadrant') else "trace",
            "priority": 0.8,
            "suggested_query": f"Research needed for: {s.clean_header}",
        })

    for gap in gaps_list:
        gaps.append({
            "id": f"gap_{gap['section_id']}_{len(gaps)}",
            "type": "inline_gap",
            "section_id": gap['section_id'],
            "section_header": gap['section_header'],
            "description": gap['description'],
            "ku_quadrant": "trace",
            "priority": gap.get('priority', 0.6),
            "suggested_query": gap.get('suggested_query', ''),
        })

    return {
        "view": "narrative",
        "status": "assessed",
        "total_sections": stats['section_count'],
        "complete_sections": stats['complete_sections'],
        "empty_sections": stats['empty_sections'],
        "total_gaps": stats['total_gaps'],
        "footnote_count": stats['footnote_count'],
        "completeness_score": stats['complete_sections'] / max(stats['section_count'], 1),
        "gaps": gaps,
    }


def assess_subjects_handler(
    project_id: str = "default",
    entity_types: List[str] = None,
    context: Any = None
) -> Dict[str, Any]:
    """Assess entity profile completeness from Subject view."""
    # This would query Cymonides for entity profiles
    # For now, return structure

    return {
        "view": "subject",
        "status": "assessed",
        "entity_types_checked": entity_types or ["PERSON", "COMPANY"],
        "profiles": {
            "total": 0,
            "complete": 0,
            "thin": 0,
            "mentioned_not_profiled": 0,
        },
        "gaps": [],
        "suggested_queries": [],
    }


def assess_locations_handler(
    project_id: str = "default",
    context: Any = None
) -> Dict[str, Any]:
    """Assess source/jurisdiction coverage from Location view."""

    return {
        "view": "location",
        "status": "assessed",
        "jurisdictions_searched": [],
        "source_types_used": [],
        "temporal_coverage": {
            "earliest": None,
            "latest": None,
        },
        "gaps": [],
        "suggested_queries": [],
    }


def assess_nexus_handler(
    project_id: str = "default",
    context: Any = None
) -> Dict[str, Any]:
    """Assess connection completeness from Nexus view."""
    doc_interface = getattr(context, 'document_interface', None)

    surprising_ands = []
    if doc_interface:
        surprising_ands = doc_interface.document.surprising_ands

    return {
        "view": "nexus",
        "status": "assessed",
        "connection_stats": {
            "expected_found": 0,
            "expected_not_found": 0,
            "unexpected_found": len(surprising_ands),
        },
        "surprising_ands": surprising_ands,
        "gaps": [],
        "suggested_queries": [],
    }


def get_full_assessment_handler(
    project_id: str = "default",
    context: Any = None
) -> Dict[str, Any]:
    """Get combined assessment from all 4 views."""
    narrative = assess_narrative_handler(project_id, context)
    subjects = assess_subjects_handler(project_id, None, context)
    locations = assess_locations_handler(project_id, context)
    nexus = assess_nexus_handler(project_id, context)

    # Calculate overall completeness
    scores = [
        narrative.get('completeness_score', 0),
        subjects['profiles']['complete'] / max(subjects['profiles']['total'], 1) if subjects['profiles']['total'] > 0 else 0,
        len(locations.get('jurisdictions_searched', [])) / 3,  # Assume 3 expected
        1.0 - (nexus['connection_stats']['expected_not_found'] / max(sum(nexus['connection_stats'].values()), 1)),
    ]
    overall_score = sum(scores) / len(scores)

    # Combine all gaps
    all_gaps = (
        narrative.get('gaps', []) +
        subjects.get('gaps', []) +
        locations.get('gaps', []) +
        nexus.get('gaps', [])
    )

    # Sort by priority
    all_gaps.sort(key=lambda g: g.get('priority', 0), reverse=True)

    return {
        "project_id": project_id,
        "overall_completeness": overall_score,
        "by_view": {
            "narrative": narrative,
            "subject": subjects,
            "location": locations,
            "nexus": nexus,
        },
        "priority_gaps": all_gaps[:10],  # Top 10 gaps
        "total_gaps": len(all_gaps),
    }


def suggest_next_queries_handler(
    project_id: str = "default",
    max_queries: int = 5,
    context: Any = None
) -> Dict[str, Any]:
    """Get prioritized query suggestions based on gaps."""
    assessment = get_full_assessment_handler(project_id, context)

    suggestions = []
    for gap in assessment.get('priority_gaps', [])[:max_queries]:
        suggested = gap.get('suggested_query', '')

        # Enhance with SASTRE syntax if not already formatted
        if suggested and not any(op in suggested for op in ['p:', 'c:', 'e:', 'd:', 'bl?', 'ent?', '=?']):
            # Try to convert natural language to syntax
            if 'person' in suggested.lower():
                suggested = f"p: [person name from context]"
            elif 'company' in suggested.lower():
                suggested = f"c: [company name from context]"
            elif 'domain' in suggested.lower():
                suggested = f"ent? :![domain from context]"

        suggestions.append({
            "query": suggested,
            "rationale": gap.get('description', ''),
            "gap_id": gap.get('id', ''),
            "ku_quadrant": gap.get('ku_quadrant', 'discover'),
            "priority": gap.get('priority', 0.5),
            "target_view": gap.get('type', 'unknown'),
        })

    return {
        "project_id": project_id,
        "suggestions": suggestions,
        "total_gaps": assessment['total_gaps'],
        "overall_completeness": assessment['overall_completeness'],
    }


def rotate_centricity_handler(
    current_view: str,
    context: Any = None
) -> Dict[str, Any]:
    """Rotate to next centricity view for fresh perspective."""
    view_order = ["narrative", "subject", "location", "nexus"]
    current_idx = view_order.index(current_view) if current_view in view_order else 0
    next_idx = (current_idx + 1) % len(view_order)
    next_view = view_order[next_idx]

    return {
        "previous_view": current_view,
        "next_view": next_view,
        "view_index": next_idx,
        "guidance": {
            "narrative": "Focus on document sections and citation gaps",
            "subject": "Focus on entity profiles and thin records",
            "location": "Focus on jurisdictions and source types",
            "nexus": "Focus on connections and surprising intersections",
        }.get(next_view, ""),
    }


def create_grid_assessor_agent() -> Agent:
    """Create the grid assessor agent."""
    return Agent(
        name="grid_assessor",
        model="claude-sonnet-4-5-20250929",
        system_prompt=SYSTEM_PROMPT,
        tools=[
            Tool(
                name="assess_narrative",
                description="Evaluate document sections for completeness",
                handler=assess_narrative_handler,
                input_schema={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "default": "default"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="assess_subjects",
                description="Evaluate entity profile completeness",
                handler=assess_subjects_handler,
                input_schema={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "default": "default"},
                        "entity_types": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Filter to specific entity types"
                        }
                    },
                    "required": []
                }
            ),
            Tool(
                name="assess_locations",
                description="Evaluate jurisdiction/source coverage",
                handler=assess_locations_handler,
                input_schema={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "default": "default"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="assess_nexus",
                description="Evaluate connection completeness and surprising ANDs",
                handler=assess_nexus_handler,
                input_schema={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "default": "default"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="get_full_assessment",
                description="Get combined assessment from all 4 centricities",
                handler=get_full_assessment_handler,
                input_schema={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "default": "default"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="suggest_next_queries",
                description="Get prioritized query suggestions based on gaps",
                handler=suggest_next_queries_handler,
                input_schema={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "default": "default"},
                        "max_queries": {"type": "integer", "default": 5}
                    },
                    "required": []
                }
            ),
            Tool(
                name="rotate_centricity",
                description="Rotate to next view for fresh perspective",
                handler=rotate_centricity_handler,
                input_schema={
                    "type": "object",
                    "properties": {
                        "current_view": {
                            "type": "string",
                            "enum": ["narrative", "subject", "location", "nexus"]
                        }
                    },
                    "required": ["current_view"]
                }
            ),
        ]
    )
