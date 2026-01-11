"""
SASTRE Document Interface

The document is the PRIMARY INTERFACE for investigations.
User works IN the document, watching citations stream in real-time.
This is NOT just output - it's the investigation's long-term memory.
"""

import re
import uuid
from typing import List, Dict, Any, Optional, AsyncGenerator
from datetime import datetime
from dataclasses import dataclass, field

from .sections import (
    Section,
    SectionState,
    SectionIntent,
    KUQuadrant,
    SectionGap,
    Watcher,
    WatcherRegistry,
    create_watcher_from_section,
)
from .streaming import StreamingWriter, Finding, StreamEvent


@dataclass
class Document:
    """An investigation document."""
    id: str
    title: str
    tasking: str                                    # Original user request
    sections: List[Section] = field(default_factory=list)
    footnotes: List[str] = field(default_factory=list)

    # Tracking
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    iteration_count: int = 0

    # Entities discovered
    known_entities: List[str] = field(default_factory=list)  # Entity IDs

    # Surprising ANDs detected
    surprising_ands: List[Dict[str, Any]] = field(default_factory=list)


class DocumentParser:
    """Parse markdown document into structured sections."""

    METADATA_PATTERN = re.compile(r'\[([A-Z_]+):([^\]]+)\]')
    GAP_PATTERN = re.compile(r'\[\?\]\s*([^\n]+)')
    WATCHER_META_PATTERN = re.compile(r'<!--\s*WATCHER_META\n(.*?)\n-->', re.DOTALL)

    @classmethod
    def parse(cls, content: str, document_id: Optional[str] = None) -> Document:
        """Parse markdown content into Document structure."""
        sections = cls._parse_sections(content)
        title = cls._extract_title(content)

        return Document(
            id=document_id or f"doc_{uuid.uuid4().hex[:8]}",
            title=title,
            tasking="",
            sections=sections,
            footnotes=cls._extract_footnotes(content),
        )

    @classmethod
    def _extract_title(cls, content: str) -> str:
        """Extract document title from first H1."""
        match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        return match.group(1).strip() if match else "Untitled Investigation"

    @classmethod
    def _parse_sections(cls, content: str) -> List[Section]:
        """Parse document into sections."""
        sections = []
        pattern = re.compile(r'^##\s+(.+)$', re.MULTILINE)
        matches = list(pattern.finditer(content))

        for i, match in enumerate(matches):
            header_text = match.group(1)
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)

            section_content = content[start:end].strip()
            section = cls._parse_section(header_text, section_content)
            sections.append(section)

        return sections

    @classmethod
    def _parse_section(cls, header_text: str, content: str) -> Section:
        """Parse a single section with metadata."""
        # Extract inline metadata
        metadata = {}
        for match in cls.METADATA_PATTERN.finditer(header_text):
            metadata[match.group(1).lower()] = match.group(2)

        clean_header = cls.METADATA_PATTERN.sub('', header_text).strip()

        # Extract gaps
        gaps = [
            SectionGap(description=m.group(1), position=m.start())
            for m in cls.GAP_PATTERN.finditer(content)
        ]

        # Determine state
        if not content or len(content.strip()) < 10:
            state = SectionState.EMPTY
        elif gaps:
            state = SectionState.INCOMPLETE
        else:
            state = SectionState.COMPLETE

        # Extract watcher meta
        watcher_meta = {}
        watcher_match = cls.WATCHER_META_PATTERN.search(content)
        if watcher_match:
            for line in watcher_match.group(1).strip().split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    watcher_meta[key.strip()] = value.strip()

        # Parse intent and K-U
        intent = cls._parse_intent(metadata.get('intent', ''))
        k_u = cls._parse_ku(metadata.get('k-u', ''))

        return Section(
            id=f"section_{uuid.uuid4().hex[:8]}",
            header=f"## {clean_header}",
            content=content,
            state=state,
            gaps=gaps,
            intent=intent,
            k_u_quadrant=k_u,
            watcher_meta=watcher_meta,
        )

    @classmethod
    def _parse_intent(cls, intent_str: str) -> SectionIntent:
        """Parse intent string to enum."""
        mapping = {
            'discover_subject': SectionIntent.DISCOVER_SUBJECT,
            'discover_location': SectionIntent.DISCOVER_LOCATION,
            'enrich_subject': SectionIntent.ENRICH_SUBJECT,
            'enrich_location': SectionIntent.ENRICH_LOCATION,
        }
        return mapping.get(intent_str.lower(), SectionIntent.ENRICH_SUBJECT)

    @classmethod
    def _parse_ku(cls, ku_str: str) -> KUQuadrant:
        """Parse K-U string to enum."""
        mapping = {
            'verify': KUQuadrant.VERIFY,
            'trace': KUQuadrant.TRACE,
            'extract': KUQuadrant.EXTRACT,
            'discover': KUQuadrant.DISCOVER,
        }
        return mapping.get(ku_str.lower(), KUQuadrant.TRACE)

    @classmethod
    def _extract_footnotes(cls, content: str) -> List[str]:
        """Extract footnote definitions."""
        pattern = re.compile(r'^\[\^(\d+)\]:\s*(.+)$', re.MULTILINE)
        return [m.group(0) for m in pattern.finditer(content)]


class DocumentInterface:
    """
    The document as primary interface for investigation.

    User watches citations stream in real-time.
    Human is in control - can intervene at any point.
    """

    def __init__(self, document: Document):
        self.document = document
        self._sections_by_id = {s.id: s for s in document.sections}
        self._footnote_counter = len(document.footnotes) + 1

        # Initialize watcher registry
        self.watcher_registry = WatcherRegistry()
        for section in document.sections:
            watcher = create_watcher_from_section(section)
            self.watcher_registry.register(watcher)

        # Initialize streaming writer
        self.writer = StreamingWriter(
            sections=self._sections_by_id,
            watcher_registry=self.watcher_registry
        )

    @classmethod
    def from_tasking(cls, tasking: str) -> 'DocumentInterface':
        """Create a new document from user tasking."""
        title = cls._extract_title_from_tasking(tasking)
        sections = cls._create_initial_sections(tasking)

        document = Document(
            id=f"doc_{uuid.uuid4().hex[:8]}",
            title=title,
            tasking=tasking,
            sections=sections,
        )

        return cls(document)

    @classmethod
    def from_markdown(cls, content: str) -> 'DocumentInterface':
        """Load document from existing markdown."""
        document = DocumentParser.parse(content)
        return cls(document)

    @staticmethod
    def _extract_title_from_tasking(tasking: str) -> str:
        """Extract title from tasking."""
        first_line = tasking.strip().split('\n')[0]
        return first_line if len(first_line) < 100 else "Investigation"

    @staticmethod
    def _create_initial_sections(tasking: str) -> List[Section]:
        """Create initial sections based on tasking."""
        sections = [
            Section(
                id=f"section_{uuid.uuid4().hex[:8]}",
                header="## Executive Summary",
                intent=SectionIntent.ENRICH_SUBJECT,
                state=SectionState.EMPTY,
            ),
            Section(
                id=f"section_{uuid.uuid4().hex[:8]}",
                header="## Background",
                intent=SectionIntent.ENRICH_SUBJECT,
                state=SectionState.EMPTY,
            ),
            Section(
                id=f"section_{uuid.uuid4().hex[:8]}",
                header="## Findings",
                intent=SectionIntent.DISCOVER_SUBJECT,
                state=SectionState.EMPTY,
            ),
        ]

        tasking_lower = tasking.lower()

        if any(w in tasking_lower for w in ['person', 'individual', 'who']):
            sections.insert(2, Section(
                id=f"section_{uuid.uuid4().hex[:8]}",
                header="## Personal Information",
                intent=SectionIntent.ENRICH_SUBJECT,
                state=SectionState.EMPTY,
                k_u_quadrant=KUQuadrant.TRACE,
            ))

        if any(w in tasking_lower for w in ['company', 'corporate', 'business']):
            sections.insert(2, Section(
                id=f"section_{uuid.uuid4().hex[:8]}",
                header="## Corporate Structure",
                intent=SectionIntent.ENRICH_SUBJECT,
                state=SectionState.EMPTY,
                k_u_quadrant=KUQuadrant.TRACE,
            ))

        if any(w in tasking_lower for w in ['connection', 'link', 'relationship']):
            sections.insert(2, Section(
                id=f"section_{uuid.uuid4().hex[:8]}",
                header="## Connections and Relationships",
                intent=SectionIntent.DISCOVER_SUBJECT,
                state=SectionState.EMPTY,
                k_u_quadrant=KUQuadrant.DISCOVER,
            ))

        return sections

    async def stream_finding(
        self,
        finding: Finding,
        target_section: Optional[str] = None
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream a finding to the document."""
        async for event in self.writer.stream_finding(finding, target_section):
            self.document.last_updated = datetime.now()
            yield event

    def get_section(self, section_id: str) -> Optional[Section]:
        """Get section by ID."""
        return self._sections_by_id.get(section_id)

    def find_section(self, header_keyword: str) -> Optional[Section]:
        """Find section by header keyword."""
        keyword_lower = header_keyword.lower()
        for section in self.document.sections:
            if keyword_lower in section.header.lower():
                return section
        return None

    def create_section(self, header: str, **kwargs) -> Section:
        """Create a new section."""
        section = Section(
            id=f"section_{uuid.uuid4().hex[:8]}",
            header=f"## {header}",
            **kwargs
        )
        self.document.sections.append(section)
        self._sections_by_id[section.id] = section

        # Create watcher
        watcher = create_watcher_from_section(section)
        self.watcher_registry.register(watcher)

        return section

    def get_watchers(self) -> Dict[str, Dict]:
        """Get all watchers (section headers -> metadata)."""
        return {
            w.section_header: {
                'id': w.id,
                'section_id': w.section_id,
                'target_entities': w.target_entities,
                'target_topics': w.target_topics,
                'entity_types': list(w.entity_types),
                'jurisdiction_filter': w.jurisdiction_filter,
                'active': w.active,
            }
            for w in self.watcher_registry.all_active()
        }

    def get_gaps(self) -> List[Dict[str, Any]]:
        """Get all gaps across all sections."""
        gaps = []
        for section in self.document.sections:
            for gap in section.gaps:
                gaps.append({
                    'section_id': section.id,
                    'section_header': section.clean_header,
                    'description': gap.description,
                    'priority': gap.priority,
                    'suggested_query': gap.suggested_query,
                })
        return gaps

    def get_empty_sections(self) -> List[Section]:
        """Get all empty sections."""
        return [s for s in self.document.sections if s.is_empty]

    def add_footnote(self, source: str) -> int:
        """Add a footnote and return its number."""
        fn_num = self._footnote_counter
        self._footnote_counter += 1
        footnote = f"[^{fn_num}]: Source: {source}, accessed {datetime.now().strftime('%Y-%m-%d')}"
        self.document.footnotes.append(footnote)
        return fn_num

    def to_markdown(self) -> str:
        """Render document as markdown with embedded metadata."""
        lines = [f"# {self.document.title}\n"]

        # Metadata block
        lines.append("<!-- DOCUMENT_META")
        lines.append(f"id: {self.document.id}")
        lines.append(f"tasking: {self.document.tasking}")
        lines.append(f"iteration: {self.document.iteration_count}")
        lines.append(f"last_updated: {self.document.last_updated.isoformat()}")
        lines.append("-->")
        lines.append("")

        # Sections
        for section in self.document.sections:
            meta = f"[INTENT:{section.intent.value}] [STATE:{section.state.value}] [K-U:{section.k_u_quadrant.value}]"
            lines.append(f"{section.header} {meta}")
            lines.append("")
            if section.content:
                lines.append(section.content)
            lines.append("")

        # Footnotes
        if self.document.footnotes:
            lines.append("\n## References\n")
            for fn in self.document.footnotes:
                lines.append(fn)

        return '\n'.join(lines)

    async def spawn_surprising_section(
        self,
        entity_a: str,
        entity_b: str,
        connection: str,
        discovered_in: str,
        confidence: float
    ) -> Section:
        """Spawn a section for a Surprising AND discovery."""
        event = await self.writer.spawn_surprising_section(
            entity_a, entity_b, connection, discovered_in, confidence
        )

        # Record surprising AND
        self.document.surprising_ands.append({
            'entity_a': entity_a,
            'entity_b': entity_b,
            'connection': connection,
            'discovered_in': discovered_in,
            'confidence': confidence,
            'section_id': event.section_id,
        })

        return self.get_section(event.section_id)

    def detect_surprising_ands(self, new_entity_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Detect unexpected co-occurrences.

        Returns list of potential surprising ANDs for investigation.
        """
        # This would integrate with the similarity engine
        # For now, return empty - actual logic in similarity/expectations.py
        return []

    def get_statistics(self) -> Dict[str, Any]:
        """Get document statistics."""
        total_content = sum(len(s.content) for s in self.document.sections)
        complete = len([s for s in self.document.sections if s.state == SectionState.COMPLETE])
        empty = len([s for s in self.document.sections if s.state == SectionState.EMPTY])

        return {
            'title': self.document.title,
            'section_count': len(self.document.sections),
            'complete_sections': complete,
            'empty_sections': empty,
            'total_gaps': sum(len(s.gaps) for s in self.document.sections),
            'footnote_count': len(self.document.footnotes),
            'content_length': total_content,
            'known_entities': len(self.document.known_entities),
            'surprising_ands': len(self.document.surprising_ands),
            'last_updated': self.document.last_updated.isoformat(),
        }
