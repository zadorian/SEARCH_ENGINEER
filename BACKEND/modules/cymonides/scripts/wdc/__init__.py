"""
WDC (Web Data Commons) integration for Cymonides.

This module handles materialization of WDC Schema.org entities into
the Cymonides-1 entity graph.

CRITICAL: Uses MAIN SYSTEM's CymonidesIndexer for ID generation!
- Same ID generation as Grid extraction (SHA256-based)
- Same normalization (removes Inc., Ltd., Corp., GmbH suffixes)
- Same document schema (canonicalValue, source_urls, embedded_edges)

This ensures WDC entities MERGE with entities from Grid extraction,
rather than creating duplicates.

Architecture:
- DEFINITIONAL handles LOCATION (WHERE to search) - domain profiles, language, geo
- CYMONIDES handles materialization (WHEN entities become graph nodes)
- LINKLATER handles extraction (WHAT entities/relationships to extract from content)

Components:
- materialization_gate.py: Convert WDC entities to C-1 nodes
"""

from .materialization_gate import (
    WDCMaterializer,
    MaterializationResult,
    materialize_wdc_search,
    map_schema_type,
    SCHEMA_TO_CYMONIDES,
    WDC_PROPERTY_TO_RELATION,
    # ID consistency helpers
    get_canonical_id,
    get_canonical_value,
)

__all__ = [
    "WDCMaterializer",
    "MaterializationResult",
    "materialize_wdc_search",
    "map_schema_type",
    "SCHEMA_TO_CYMONIDES",
    "WDC_PROPERTY_TO_RELATION",
    # ID consistency helpers
    "get_canonical_id",
    "get_canonical_value",
]
