"""
LINKLATER Enrichment Module

Universal enrichment pipeline:
1. GPT-5 Nano generates query variations
2. Firecrawl + Exa search with OR queries
3. Entity extraction → graph indexing
"""

from .universal_enricher import (
    UniversalEnricher,
    EnrichmentResult,
    enrich_query,
)

from .query_variations import (
    QueryVariations,
    generate_variations,
    generate_variations_sync,
)

__all__ = [
    'UniversalEnricher',
    'EnrichmentResult',
    'enrich_query',
    'QueryVariations',
    'generate_variations',
    'generate_variations_sync',
]
