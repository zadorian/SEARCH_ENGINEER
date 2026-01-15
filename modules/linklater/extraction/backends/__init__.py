"""
Entity Extraction Backends

Pluggable backends for entity extraction:
- GeminiBackend: Gemini 2.0 Flash API (default)
- GPTBackend: GPT-5-nano API
- GLiNERBackend: Local GLiNER model
- RegexBackend: Regex patterns (no API required)

Relationship extraction (Layer 4):
- HaikuRelationshipBackend: Claude Haiku 4.5 for edges between entities
"""

from .gemini import GeminiBackend
from .regex import RegexBackend

# Optional backends (may not be available)
try:
    from .gpt import GPTBackend
except ImportError:
    GPTBackend = None

try:
    from .gliner import GLiNERBackend
except ImportError:
    GLiNERBackend = None

# Relationship extraction backend
try:
    from .haiku import HaikuRelationshipBackend, extract_relationships
except ImportError:
    HaikuRelationshipBackend = None
    extract_relationships = None

__all__ = [
    # Entity extraction backends
    "GeminiBackend",
    "GPTBackend",
    "GLiNERBackend",
    "RegexBackend",
    # Relationship extraction backend (Layer 4)
    "HaikuRelationshipBackend",
    "extract_relationships",
]
