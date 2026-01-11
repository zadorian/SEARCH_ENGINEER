"""
SASTRE Document Interface - The Document is the PRIMARY INTERFACE

The user works IN the document, watching citations stream in real-time.
This is NOT just output - it's the investigation's long-term memory.

Features:
- Section parsing with metadata extraction
- Streaming findings to document
- Surprising AND detection and auto-section spawning
- [?] gap markers
- Core/Shell/Halo entity formatting
- Machine-readable section metadata
"""

import re
import uuid
from typing import List, Dict, Any, Optional, AsyncGenerator
from datetime import datetime

from .contracts import (
    Document, Section, Entity, EntityCluster,
    SurprisingAnd, Collision, NegativeEdge,
    SectionState, Intent, KUQuadrant
)


# =============================================================================
# DOCUMENT PARSER
# =============================================================================

class DocumentParser:
    """
    Parse markdown document into structured sections with metadata.
    """

    # Metadata pattern: [KEY:VALUE]
    METADATA_PATTERN = re.compile(r'\[([A-Z_]+):([^\]]+)\]')

    # Gap marker pattern: [?] description
    GAP_PATTERN = re.compile(r'\[\?\]\s*([^\n]+)')

    # Watcher meta comment pattern
    WATCHER_META_PATTERN = re.compile(
        r'<!--\s*WATCHER_META\n(.*?)\n-->',
        re.DOTALL
    )

    # Surprising AND comment pattern
    SURPRISING_AND_PATTERN = re.compile(
        r'<!--\s*SURPRISING_AND\n(.*?)\n-->',
        re.DOTALL
    )

    @classmethod
    def parse(cls, content: str, document_id: str = None) -> Document:
        """Parse markdown content into Document structure."""
        sections = cls._parse_sections(content)
        title = cls._extract_title(content)

        return Document(
            id=document_id or f"doc_{uuid.uuid4().hex[:8]}",
            title=title,
            tasking="",  # Set externally
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

        # Split by H2 headers
        pattern = re.compile(r'^##\s+(.+)$', re.MULTILINE)
        matches = list(pattern.finditer(content))

        for i, match in enumerate(matches):
            header = match.group(0)
            header_text = match.group(1)
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)

            section_content = content[start:end].strip()
            section = cls._parse_section(header, header_text, section_content)
            sections.append(section)

        return sections

    @classmethod
    def _parse_section(cls, header: str, header_text: str, content: str) -> Section:
        """Parse a single section with metadata."""
        # Extract inline metadata from header
        metadata = {}
        for match in cls.METADATA_PATTERN.finditer(header_text):
            metadata[match.group(1).lower()] = match.group(2)

        # Clean header of metadata
        clean_header = cls.METADATA_PATTERN.sub('', header_text).strip()

        # Extract gaps
        gaps = [m.group(1) for m in cls.GAP_PATTERN.finditer(content)]

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
            watcher_meta = cls._parse_meta_block(watcher_match.group(1))

        # Determine intent and K-U from metadata or infer
        intent = cls._parse_intent(metadata.get('intent', ''))
        k_u = cls._parse_ku(metadata.get('k-u', ''))

        return Section(
            header=f"## {clean_header}",
            intent=intent,
            state=state,
            content=content,
            gaps=gaps,
            k_u_quadrant=k_u,
            watcher_meta=watcher_meta,
        )

    @classmethod
    def _parse_meta_block(cls, block: str) -> Dict[str, str]:
        """Parse key: value lines in a meta block."""
        result = {}
        for line in block.strip().split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                result[key.strip()] = value.strip()
        return result

    @classmethod
    def _parse_intent(cls, intent_str: str) -> Intent:
        """Parse intent string to enum."""
        mapping = {
            'discover_subject': Intent.DISCOVER_SUBJECT,
            'discover_location': Intent.DISCOVER_LOCATION,
            'enrich_subject': Intent.ENRICH_SUBJECT,
            'enrich_location': Intent.ENRICH_LOCATION,
        }
        return mapping.get(intent_str.lower(), Intent.ENRICH_SUBJECT)

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


# =============================================================================
# DOCUMENT INTERFACE
# =============================================================================

class DocumentInterface:
    """
    The document as primary interface for investigation.

    User watches citations stream in real-time.
    Human is in control - can intervene at any point.
    """

    def __init__(self, document: Document):
        self.document = document
        self.footnote_counter = len(document.footnotes) + 1

    @classmethod
    def from_tasking(cls, tasking: str) -> 'DocumentInterface':
        """Create a new document from user tasking."""
        # Parse tasking to create initial structure
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
        # Use first line or first proper noun phrase
        first_line = tasking.strip().split('\n')[0]
        if len(first_line) < 100:
            return first_line
        return "Investigation"

    @staticmethod
    def _create_initial_sections(tasking: str) -> List[Section]:
        """Create initial sections based on tasking."""
        # Default sections for investigation
        sections = [
            Section(
                header="## Executive Summary",
                intent=Intent.ENRICH_SUBJECT,
                state=SectionState.EMPTY,
            ),
            Section(
                header="## Background",
                intent=Intent.ENRICH_SUBJECT,
                state=SectionState.EMPTY,
            ),
            Section(
                header="## Findings",
                intent=Intent.DISCOVER_SUBJECT,
                state=SectionState.EMPTY,
            ),
        ]

        # Add entity-specific sections based on tasking keywords
        tasking_lower = tasking.lower()

        if any(w in tasking_lower for w in ['person', 'individual', 'who']):
            sections.insert(2, Section(
                header="## Personal Information",
                intent=Intent.ENRICH_SUBJECT,
                state=SectionState.EMPTY,
                k_u_quadrant=KUQuadrant.TRACE,
            ))

        if any(w in tasking_lower for w in ['company', 'corporate', 'business']):
            sections.insert(2, Section(
                header="## Corporate Structure",
                intent=Intent.ENRICH_SUBJECT,
                state=SectionState.EMPTY,
                k_u_quadrant=KUQuadrant.TRACE,
            ))

        if any(w in tasking_lower for w in ['connection', 'link', 'relationship']):
            sections.insert(2, Section(
                header="## Connections and Relationships",
                intent=Intent.DISCOVER_SUBJECT,
                state=SectionState.EMPTY,
                k_u_quadrant=KUQuadrant.DISCOVER,
            ))

        return sections

    async def stream_findings(
        self,
        entities: List[Entity],
        target_section: str
    ) -> AsyncGenerator[str, None]:
        """
        Stream findings into the document.

        Yields markdown chunks as they're added.
        """
        section = self._find_section(target_section)
        if not section:
            section = self._create_section(target_section)

        for entity in entities:
            formatted = self._format_entity(entity)
            section.content += f"\n\n{formatted}"
            section.state = SectionState.INCOMPLETE

            # Add to known entities
            if entity not in self.document.known_entities:
                self.document.known_entities.append(entity)

            yield formatted

        self.document.last_updated = datetime.now()

    def _find_section(self, header_or_keyword: str) -> Optional[Section]:
        """Find section by header or keyword."""
        header_lower = header_or_keyword.lower()
        for section in self.document.sections:
            if header_lower in section.header.lower():
                return section
        return None

    def _create_section(self, header: str) -> Section:
        """Create a new section."""
        section = Section(
            header=f"## {header}",
            intent=Intent.ENRICH_SUBJECT,
            state=SectionState.EMPTY,
        )
        self.document.sections.append(section)
        return section

    def _format_entity(self, entity: Entity) -> str:
        """
        Format entity using Core/Shell/Halo structure.

        Makes confidence visible in the document.
        """
        lines = [f"### {entity.name}"]

        # CORE (Verified)
        if entity.attributes.core:
            lines.append("\n**Core (Verified)**")
            for key, value in entity.attributes.core.items():
                fn = self._add_footnote(entity.source)
                lines.append(f"- {key}: {value} [^{fn}]")

        # SHELL (Probable)
        if entity.attributes.shell:
            lines.append("\n**Shell (Probable)**")
            for key, value in entity.attributes.shell.items():
                if value:
                    fn = self._add_footnote(entity.source)
                    lines.append(f"- {key}: {value} [^{fn}]")

        # HALO (Circumstantial)
        if entity.attributes.halo:
            lines.append("\n**Halo (Circumstantial)**")
            for key, value in entity.attributes.halo.items():
                if value:
                    lines.append(f"- {key}: {value}")

        return '\n'.join(lines)

    def _add_footnote(self, source: str) -> int:
        """Add a footnote and return its number."""
        fn_num = self.footnote_counter
        self.footnote_counter += 1
        footnote = f"[^{fn_num}]: Source: {source}, accessed {datetime.now().strftime('%Y-%m-%d')}"
        self.document.footnotes.append(footnote)
        return fn_num

    async def spawn_section(self, surprising_and: SurprisingAnd) -> str:
        """
        Auto-spawn a section for a Surprising AND.

        ⚡ These are unexpected co-occurrences that NARRATIVE couldn't predict.
        """
        header = f"⚡ Unexpected: {surprising_and.connection}"

        section = Section(
            header=f"## {header}",
            intent=Intent.DISCOVER_SUBJECT,
            state=SectionState.INCOMPLETE,
            content=f"""During investigation, an unexpected connection was discovered.
This was not in original tasking or predicted by any header.

**Connection:** {surprising_and.connection}
**Discovered in:** {surprising_and.discovered_in}
**Confidence:** {surprising_and.confidence:.0%}

<!-- SURPRISING_AND
discovered_in: {surprising_and.discovered_in}
co_occurrence: {surprising_and.connection}
confidence: {surprising_and.confidence}
action_taken: Auto-spawned section, awaiting investigation
-->

[?] Requires investigation
""",
            k_u_quadrant=KUQuadrant.DISCOVER,
        )

        self.document.sections.append(section)
        surprising_and.section_spawned = True
        self.document.surprising_ands.append(surprising_and)
        self.document.last_updated = datetime.now()

        return section.header

    async def request_approval(self, query) -> bool:
        """
        Request user approval for a query.

        In autonomous mode, returns True.
        In interactive mode, would prompt user.
        """
        # TODO: Implement interactive approval mechanism
        return True

    def get_watchers(self) -> Dict[str, Dict]:
        """Get all watchers (headers -> prompts)."""
        watchers = {}
        for section in self.document.sections:
            if section.watcher_meta:
                watchers[section.header] = section.watcher_meta
            else:
                # Generate default watcher from section
                watchers[section.header] = {
                    'target': section.header.replace('## ', ''),
                    'intent': section.intent.value,
                    'k_u_quadrant': section.k_u_quadrant.value,
                }
        return watchers

    def to_markdown(self) -> str:
        """
        Render document as markdown.

        Machine-readable with embedded metadata.
        """
        lines = [f"# {self.document.title}\n"]

        # Metadata block
        lines.append(f"<!-- DOCUMENT_META")
        lines.append(f"id: {self.document.id}")
        lines.append(f"tasking: {self.document.tasking}")
        lines.append(f"iteration: {self.document.iteration_count}")
        lines.append(f"last_updated: {self.document.last_updated.isoformat()}")
        lines.append(f"-->")
        lines.append("")

        # Sections
        for section in self.document.sections:
            # Header with inline metadata
            meta_tags = f"[INTENT:{section.intent.value}] [STATE:{section.state.value}] [K-U:{section.k_u_quadrant.value}]"
            lines.append(f"{section.header} {meta_tags}")
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

    def detect_surprising_ands(
        self,
        new_entities: List[Entity]
    ) -> List[SurprisingAnd]:
        """
        Detect unexpected co-occurrences.

        NEXUS finds what NARRATIVE couldn't predict.
        """
        surprises = []

        for new_entity in new_entities:
            for known in self.document.known_entities:
                # Check if they share unexpected connections
                if self._is_surprising_connection(new_entity, known):
                    surprise = SurprisingAnd(
                        connection=f"{known.name} + {new_entity.name}",
                        discovered_in=new_entity.source,
                        entities_involved=[known.id, new_entity.id],
                        confidence=0.7,
                    )
                    surprises.append(surprise)

        return surprises

    def _is_surprising_connection(self, entity_a: Entity, entity_b: Entity) -> bool:
        """
        Check if connection between entities is surprising.

        A connection is surprising if:
        - Entities are of different types (person <-> company)
        - No prior connection was known
        - Context suggests unexpected relationship
        """
        # Different entity types connecting
        if entity_a.entity_type != entity_b.entity_type:
            # Check if they share location or other context
            shell_a = set(str(v).lower() for v in entity_a.attributes.shell.values() if v)
            shell_b = set(str(v).lower() for v in entity_b.attributes.shell.values() if v)

            # If they share context but weren't previously linked, it's surprising
            if shell_a & shell_b:
                return True

        return False
