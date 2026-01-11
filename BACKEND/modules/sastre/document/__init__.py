"""
SASTRE Document Module

The document is the PRIMARY INTERFACE for investigations.
User works IN the document, watching citations stream in real-time.

Key concepts:
- Sections: Named parts of the document with state tracking
- Watchers: Monitor sections and route findings to them
- Streaming: Live updates as investigation progresses
- Export: Output to Word, PDF, Markdown
"""

# Interface
from .interface import (
    DocumentInterface,
    Document,
    DocumentParser,
)

# Sections
from .sections import (
    Section,
    SectionState,
    SectionIntent,
    KUQuadrant,
    SectionGap,
    SectionMeta,
    Watcher,
    WatcherRegistry,
    create_watcher_from_section,
)

# Streaming
from .streaming import (
    StreamingWriter,
    Finding,
    StreamEvent,
)

# Export
from .export import (
    ExportConfig,
    ExportResult,
    MarkdownRenderer,
    WordExporter,
    PDFExporter,
    export_document,
)


__all__ = [
    # Interface
    "DocumentInterface",
    "Document",
    "DocumentParser",
    # Sections
    "Section",
    "SectionState",
    "SectionIntent",
    "KUQuadrant",
    "SectionGap",
    "SectionMeta",
    "Watcher",
    "WatcherRegistry",
    "create_watcher_from_section",
    # Streaming
    "StreamingWriter",
    "Finding",
    "StreamEvent",
    # Export
    "ExportConfig",
    "ExportResult",
    "MarkdownRenderer",
    "WordExporter",
    "PDFExporter",
    "export_document",
]
