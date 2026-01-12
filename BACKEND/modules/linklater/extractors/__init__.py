"""
LINKLATER Extractors - DEPRECATED

This module is deprecated. Use LINKLATER.extraction instead.

The new unified extraction system provides:
- extract_entities() - Main async extraction function
- EntityExtractor - Class-based extractor
- Multiple backends: gemini, gpt, gliner, regex

For backward compatibility, this module still re-exports from the old files:
- structured_ner.py → StructuredEntityExtractor, get_structured_extractor
- gemini_ner.py → GeminiEntityExtractor, get_gemini_extractor

Migration path:
    # OLD (deprecated)
    from modules.LINKLATER.extractors.structured_ner import get_structured_extractor
    extractor = get_structured_extractor()

    # NEW (recommended)
    from modules.LINKLATER.extraction import extract_entities
    entities = await extract_entities(html, url, backend="gemini")
"""

import warnings

# Issue deprecation warning when this module is imported
warnings.warn(
    "LINKLATER.extractors is deprecated. Use LINKLATER.extraction instead.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export from old files for backward compatibility
try:
    from .structured_ner import (
        StructuredEntityExtractor,
        get_structured_extractor,
        URLEntityResult,
        EntityWithSnippet,
    )
except ImportError:
    StructuredEntityExtractor = None
    get_structured_extractor = None
    URLEntityResult = None
    EntityWithSnippet = None

try:
    from .gemini_ner import (
        GeminiEntityExtractor,
        get_gemini_extractor,
        Entity as GeminiEntity,
    )
except ImportError:
    GeminiEntityExtractor = None
    get_gemini_extractor = None
    GeminiEntity = None

try:
    from .hybrid_ner import HybridEntityExtractor
except ImportError:
    HybridEntityExtractor = None

try:
    from .multi_model_ner import MultiModelNER
except ImportError:
    MultiModelNER = None

__all__ = [
    # Structured NER
    "StructuredEntityExtractor",
    "get_structured_extractor",
    "URLEntityResult",
    "EntityWithSnippet",
    # Gemini NER
    "GeminiEntityExtractor",
    "get_gemini_extractor",
    "GeminiEntity",
    # Hybrid NER
    "HybridEntityExtractor",
    # Multi-model NER
    "MultiModelNER",
]
