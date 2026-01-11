"""
SASTRE Document Streaming

Stream findings to document sections in real-time.
The user watches citations appear as the investigation progresses.
"""

import asyncio
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, AsyncGenerator, Callable
from datetime import datetime
import json

from .sections import (
    Section,
    SectionState,
    Watcher,
    WatcherRegistry,
    SectionGap,
)


@dataclass
class Finding:
    """A finding to stream to the document."""
    id: str
    entity_name: str
    entity_type: str
    content: str                          # Formatted markdown content
    source: str                           # Source provenance
    confidence: float                     # 0.0 - 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class StreamEvent:
    """An event in the document stream."""
    event_type: str                       # finding, gap_filled, section_created, etc.
    section_id: str
    section_header: str
    content: str
    finding: Optional[Finding] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_sse(self) -> str:
        """Format as Server-Sent Event."""
        data = {
            "event": self.event_type,
            "section_id": self.section_id,
            "section_header": self.section_header,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }
        return f"data: {json.dumps(data)}\n\n"


class StreamingWriter:
    """
    Streams findings to document sections in real-time.

    The document is the PRIMARY INTERFACE - users watch it update live.
    This enables human oversight of the investigation as it progresses.
    """

    def __init__(
        self,
        sections: Dict[str, Section],
        watcher_registry: Optional[WatcherRegistry] = None
    ):
        """
        Initialize streaming writer.

        Args:
            sections: Section ID -> Section mapping
            watcher_registry: Optional registry of watchers
        """
        self.sections = sections
        self.watchers = watcher_registry or WatcherRegistry()

        # Event queue for streaming
        self._event_queue: asyncio.Queue[StreamEvent] = asyncio.Queue()

        # Callbacks
        self._on_finding: List[Callable[[Finding, Section], None]] = []
        self._on_gap_filled: List[Callable[[Section, SectionGap], None]] = []
        self._on_section_update: List[Callable[[Section], None]] = []

        # Statistics
        self.total_findings = 0
        self.findings_by_section: Dict[str, int] = {}

        # Footnote counter
        self._footnote_counter = 1

    async def stream_finding(
        self,
        finding: Finding,
        target_section: Optional[str] = None
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Stream a finding to the document.

        If target_section is not specified, routes based on watcher matches.
        Yields stream events as they're generated.
        """
        # Find target section(s)
        if target_section:
            sections = [self.sections.get(target_section)]
        else:
            # Route based on watcher matches
            finding_dict = {
                "id": finding.id,
                "name": finding.entity_name,
                "entity_type": finding.entity_type,
                "confidence": finding.confidence,
                **finding.metadata,
            }
            matching_watchers = self.watchers.find_matching(finding_dict)
            sections = [self.sections.get(w.section_id) for w in matching_watchers]

        sections = [s for s in sections if s is not None]

        if not sections:
            # Create default section if no match
            default_section = self._create_default_section(finding.entity_type)
            sections = [default_section]

        # Stream to each matching section
        for section in sections:
            event = await self._add_finding_to_section(finding, section)
            yield event

    async def _add_finding_to_section(
        self,
        finding: Finding,
        section: Section
    ) -> StreamEvent:
        """Add a finding to a specific section."""
        # Format the finding
        formatted = self._format_finding(finding)

        # Add to section content
        if section.content:
            section.content += f"\n\n{formatted}"
        else:
            section.content = formatted

        # Update section state
        section.state = SectionState.INCOMPLETE
        section.finding_count += 1
        section.last_updated = datetime.now()

        # Update statistics
        self.total_findings += 1
        self.findings_by_section[section.id] = self.findings_by_section.get(section.id, 0) + 1

        # Update watcher
        watcher = self.watchers.get(section.id)
        if watcher:
            watcher.finding_count += 1
            watcher.last_finding = datetime.now()

        # Create event
        event = StreamEvent(
            event_type="finding",
            section_id=section.id,
            section_header=section.clean_header,
            content=formatted,
            finding=finding,
            metadata={
                "entity_type": finding.entity_type,
                "confidence": finding.confidence,
                "source": finding.source,
            },
        )

        # Queue for SSE streaming
        await self._event_queue.put(event)

        # Trigger callbacks
        for cb in self._on_finding:
            cb(finding, section)

        return event

    def _format_finding(self, finding: Finding) -> str:
        """Format a finding as markdown with Core/Shell/Halo structure."""
        lines = [f"### {finding.entity_name}"]

        # Add footnote for provenance
        fn = self._add_footnote(finding.source)

        # Parse content metadata for Core/Shell/Halo
        meta = finding.metadata

        # Core (verified facts)
        core = meta.get("core", {})
        if core:
            lines.append("\n**Core (Verified)**")
            for key, value in core.items():
                lines.append(f"- {key}: {value} [^{fn}]")

        # Shell (probable facts)
        shell = meta.get("shell", {})
        if shell:
            lines.append("\n**Shell (Probable)**")
            for key, value in shell.items():
                if value:
                    lines.append(f"- {key}: {value} [^{fn}]")

        # Halo (circumstantial)
        halo = meta.get("halo", {})
        if halo:
            lines.append("\n**Halo (Circumstantial)**")
            for key, value in halo.items():
                if value:
                    lines.append(f"- {key}: {value}")

        # If no structured data, use the content directly
        if not core and not shell and not halo:
            lines.append(f"\n{finding.content} [^{fn}]")

        return '\n'.join(lines)

    def _add_footnote(self, source: str) -> int:
        """Add a footnote and return its number."""
        fn_num = self._footnote_counter
        self._footnote_counter += 1
        # Footnote will be collected separately
        return fn_num

    def _create_default_section(self, entity_type: str) -> Section:
        """Create a default section for unrouted findings."""
        import uuid

        section_id = f"section_{uuid.uuid4().hex[:8]}"
        header_map = {
            "PERSON": "## Persons of Interest",
            "COMPANY": "## Companies",
            "ADDRESS": "## Addresses",
            "EMAIL": "## Contact Information",
            "PHONE": "## Contact Information",
            "DOMAIN": "## Domains",
        }
        header = header_map.get(entity_type.upper(), "## Other Findings")

        section = Section(
            id=section_id,
            header=header,
            state=SectionState.EMPTY,
        )
        self.sections[section_id] = section
        return section

    async def fill_gap(
        self,
        section_id: str,
        gap: SectionGap,
        content: str
    ) -> StreamEvent:
        """Fill a gap in a section with new content."""
        section = self.sections.get(section_id)
        if not section:
            raise ValueError(f"Section {section_id} not found")

        # Replace the gap marker with content
        gap_pattern = f"[?] {gap.description}"
        if gap_pattern in section.content:
            section.content = section.content.replace(gap_pattern, content)
        else:
            # Append if pattern not found
            section.content += f"\n\n{content}"

        # Remove gap from list
        section.gaps = [g for g in section.gaps if g.description != gap.description]

        # Update state
        if not section.gaps:
            section.state = SectionState.COMPLETE
        section.last_updated = datetime.now()

        event = StreamEvent(
            event_type="gap_filled",
            section_id=section.id,
            section_header=section.clean_header,
            content=content,
            metadata={"gap_description": gap.description},
        )

        await self._event_queue.put(event)

        for cb in self._on_gap_filled:
            cb(section, gap)

        return event

    async def create_section(
        self,
        header: str,
        initial_content: str = "",
        reason: str = ""
    ) -> StreamEvent:
        """Create a new section dynamically."""
        import uuid

        section_id = f"section_{uuid.uuid4().hex[:8]}"
        section = Section(
            id=section_id,
            header=f"## {header}",
            content=initial_content,
            state=SectionState.EMPTY if not initial_content else SectionState.INCOMPLETE,
        )

        self.sections[section_id] = section

        event = StreamEvent(
            event_type="section_created",
            section_id=section.id,
            section_header=header,
            content=initial_content,
            metadata={"reason": reason},
        )

        await self._event_queue.put(event)

        return event

    async def spawn_surprising_section(
        self,
        entity_a: str,
        entity_b: str,
        connection: str,
        discovered_in: str,
        confidence: float
    ) -> StreamEvent:
        """
        Spawn a section for a Surprising AND discovery.

        These are unexpected co-occurrences that NARRATIVE couldn't predict.
        """
        header = f"\u26a1 Unexpected: {entity_a} + {entity_b}"

        content = f"""During investigation, an unexpected connection was discovered.
This was not in original tasking or predicted by any header.

**Connection:** {connection}
**Discovered in:** {discovered_in}
**Confidence:** {confidence:.0%}

<!-- SURPRISING_AND
entity_a: {entity_a}
entity_b: {entity_b}
connection: {connection}
discovered_in: {discovered_in}
confidence: {confidence}
-->

[?] Requires investigation
"""

        return await self.create_section(
            header=header,
            initial_content=content,
            reason=f"Surprising AND: {entity_a} connected to {entity_b}",
        )

    async def event_stream(self) -> AsyncGenerator[StreamEvent, None]:
        """
        Async generator that yields stream events.

        Use this for SSE streaming to the frontend.
        """
        while True:
            event = await self._event_queue.get()
            yield event

    def on_finding(self, callback: Callable[[Finding, Section], None]) -> None:
        """Register a callback for new findings."""
        self._on_finding.append(callback)

    def on_gap_filled(self, callback: Callable[[Section, SectionGap], None]) -> None:
        """Register a callback for gap fills."""
        self._on_gap_filled.append(callback)

    def on_section_update(self, callback: Callable[[Section], None]) -> None:
        """Register a callback for section updates."""
        self._on_section_update.append(callback)

    def get_footnotes(self) -> List[str]:
        """Get all accumulated footnotes."""
        # In practice, footnotes would be tracked during formatting
        return []

    def get_statistics(self) -> Dict[str, Any]:
        """Get streaming statistics."""
        return {
            "total_findings": self.total_findings,
            "findings_by_section": self.findings_by_section,
            "active_sections": len(self.sections),
            "active_watchers": len(self.watchers.all_active()),
        }
