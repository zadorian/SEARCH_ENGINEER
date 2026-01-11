from typing import Dict, Any, List, Optional
import uuid
from ..core.state import InvestigationState, Section, Footnote, SurprisingAnd

async def write_section_handler(
    header: str,
    content: str,
    section_id: str = None, # If updating
    context: InvestigationState = None
) -> Dict[str, Any]:
    """
    Write or update a document section.
    """
    if not context or not context.document:
        return {"error": "No document context"}
        
    doc = context.document
    
    # Check if section exists
    section = None
    if section_id:
        section = next((s for s in doc.sections if s.id == section_id), None)
    else:
        # Check by header
        section = next((s for s in doc.sections if s.header == header), None)
        
    if section:
        section.content = content
        section.state = "complete"
    else:
        section = Section(
            id=f"section_{uuid.uuid4().hex[:8]}",
            header=header,
            content=content,
            state="complete"
        )
        doc.sections.append(section)
        
    return {"status": "written", "section_id": section.id, "length": len(content)}

async def write_entity_profile_handler(
    entity_id: str,
    context: InvestigationState = None
) -> Dict[str, Any]:
    """
    Generate and write an entity profile section.
    """
    if not context:
        return {"error": "No context"}
        
    entity = context.entities.get(entity_id)
    if not entity:
        return {"error": f"Entity {entity_id} not found"}
        
    # Format Nardello-style profile
    lines = [f"## {entity.name} ({entity.entity_type.value.upper()})"]
    
    # Core
    lines.append("\n### Identity")
    for k, v in entity.core.items():
        lines.append(f"- **{k}**: {v.value}")
        
    # Shell
    lines.append("\n### Contact & Location")
    for k, v in entity.shell.items():
        lines.append(f"- **{k}**: {v.value}")
        
    # Halo
    if entity.halo:
        lines.append("\n### Context")
        for k, v in entity.halo.items():
            lines.append(f"- **{k}**: {v.value}")
            
    content = "\n".join(lines)
    
    # Add to document
    result = await write_section_handler(
        header=f"Profile: {entity.name}",
        content=content,
        context=context
    )
    
    return result

async def add_footnote_handler(
    text: str,
    source_url: str = None,
    context: InvestigationState = None
) -> Dict[str, Any]:
    """
    Add a footnote to the document.
    """
    if not context or not context.document:
        return {"error": "No document"}
        
    doc = context.document
    idx = len(doc.footnotes) + 1
    ref = f"[^{idx}]"
    
    footnote = Footnote(
        id=f"fn_{uuid.uuid4().hex[:8]}",
        reference=ref,
        text=text,
        source_url=source_url
    )
    doc.footnotes.append(footnote)
    
    return {"reference": ref, "footnote_id": footnote.id}

async def flag_surprising_and_handler(
    entity_a_id: str,
    entity_b_id: str,
    explanation: str,
    context: InvestigationState = None
) -> Dict[str, Any]:
    """
    Flag a surprising connection (Surprising AND).
    """
    if not context or not context.document:
        return {"error": "No document"}

    sa = SurprisingAnd(
        id=f"sa_{uuid.uuid4().hex[:8]}",
        connection=f"{entity_a_id} <-> {entity_b_id}",
        entity_a=entity_a_id,
        entity_b=entity_b_id,
        why_surprising=explanation
    )
    context.document.surprising_ands.append(sa)

    return {"status": "flagged", "id": sa.id}


async def stream_finding_handler(
    watcher_id: str,
    content: str,
    source_url: str = None,
    source_id: str = None,
    context: InvestigationState = None
) -> Dict[str, Any]:
    """
    Stream a finding to a document watcher/section.

    This is the primary interface for the writer agent to add
    content to document sections in real-time.
    """
    if not context:
        return {"error": "No context provided"}

    # Create footnote if source provided
    footnote_ref = None
    if source_url:
        fn_result = await add_footnote_handler(
            text=f"Source: {source_url}",
            source_url=source_url,
            context=context
        )
        footnote_ref = fn_result.get("reference", "")

    # Format content with citation
    formatted_content = content
    if footnote_ref:
        formatted_content = f"{content}{footnote_ref}"

    # Find the watcher/section and append content
    if context.document:
        for section in context.document.sections:
            if section.id == watcher_id or section.header == watcher_id:
                if section.content:
                    section.content += f"\n\n{formatted_content}"
                else:
                    section.content = formatted_content
                return {
                    "status": "streamed",
                    "watcher_id": watcher_id,
                    "content_length": len(formatted_content)
                }

    return {"error": f"Watcher {watcher_id} not found"}
