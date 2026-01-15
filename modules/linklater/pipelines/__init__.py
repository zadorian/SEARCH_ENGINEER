"""
LinkLater Pipelines

Automated multi-step processes for backlink discovery, entity extraction, and more.

Note: Lazy imports to avoid triggering aiohttp connector initialization at import time.
Use: from linklater.pipelines.fast_backlink_scanner import FastBacklinkScanner
"""


def __getattr__(name):
    """Lazy import to avoid module-level aiohttp connector issues."""
    if name == 'AutomatedBacklinkPipeline':
        from .automated_backlink_pipeline import AutomatedBacklinkPipeline
        return AutomatedBacklinkPipeline
    elif name == 'discover_backlinks_with_entities':
        from .automated_backlink_pipeline import discover_backlinks_with_entities
        return discover_backlinks_with_entities
    elif name == 'ENTITY_EXTRACTION_AVAILABLE':
        from .automated_backlink_pipeline import ENTITY_EXTRACTION_AVAILABLE
        return ENTITY_EXTRACTION_AVAILABLE
    elif name == 'FastBacklinkScanner':
        from .fast_backlink_scanner import FastBacklinkScanner
        return FastBacklinkScanner
    raise AttributeError(f"module 'LINKLATER.pipelines' has no attribute '{name}'")
