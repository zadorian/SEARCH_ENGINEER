"""
CYMONIDES Bridges to CLASSES

Single source of truth: /data/CLASSES/{SUBJECT, NEXUS, LOCATION, NARRATIVE}

These bridges provide access to dimensional data from cymonides.
The JSONs live in CLASSES, but CYMONIDES owns the ES index.

Architecture:
    CLASSES/SUBJECT/      <- Source of truth (JSONs, embeddings)
    CLASSES/NEXUS/        <- Source of truth (JSONs, embeddings)
    CYMONIDES/bridges/    <- Bridges that load from CLASSES
    ES: cymonides-1-categories <- Indexed, searchable data

Usage:
    from cymonides.bridges import SubjectBridge, NexusBridge

    # Get synonyms
    subject = SubjectBridge()
    syns = subject.get_profession_synonyms("lawyer", lang="de")

    # Semantic search
    matches = subject.search_semantic("rechtsanwalt")

    # Resolve to canonical
    canonical = subject.resolve("geschäftsführer", category="titles")
"""

from .subject_bridge import SubjectBridge
from .nexus_bridge import NexusBridge

__all__ = ["SubjectBridge", "NexusBridge"]
