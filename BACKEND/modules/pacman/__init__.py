"""
PACMAN - Universal Extraction Module

The single source of truth for all entity extraction:
- UniversalExtractor: 265-category semantic extraction
- TierClassifier: Document tier classification (Tier 1/2/3)
- Temporal hierarchy extraction
- Red flag entity detection

Usage:
    from PACMAN import UniversalExtractor, extract_all
    
    extractor = UniversalExtractor()
    result = extractor.extract(text)
"""

from .universal_extractor import (
    UniversalExtractor,
    ExtractionResult,
    get_extractor,
    extract_all,
)

from .tier_classifier import (
    Tier,
    TierDecision,
    classify,
    build_document,
    PacmanRunner,
)

from .pacman import (
    Pacman,
    FullExtractResult,
    extract,
    red_flags,
)

__all__ = [
    "UniversalExtractor",
    "ExtractionResult", 
    "get_extractor",
    "extract_all",
    "Tier",
    "TierDecision",
    "classify",
    "build_document",
    "PacmanRunner",
    "Pacman",
    "FullExtractResult",
    "extract",
    "red_flags",
]
