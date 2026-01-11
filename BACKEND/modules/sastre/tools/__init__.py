"""
SASTRE Tools - Handler functions for SDK tools.

Categories:
- Disambiguation: Collision resolution (FUSE/REPEL/BINARY_STAR)
- Grid: 4-perspective assessment (Narrative/Subject/Location/Nexus)
- IO: Query execution, macro expansion, entity extraction
- QueryLab: Fused query construction
- Writer: Document streaming, footnotes, entity profiles
"""

from .disambig_tools import (
    check_passive_constraints_handler,
    generate_wedge_queries_handler,
    apply_resolution_handler,
)

from .grid_tools import (
    narrative_assessment_handler,
    subject_assessment_handler,
    location_assessment_handler,
    nexus_assessment_handler,
    cross_pollinate_handler,
    full_assessment_handler,
)

from .io_tools import (
    execute_macro_handler,
    expand_variations_handler,
    extract_entities_handler,
    check_source_handler,
)

from .query_lab_tools import (
    build_fused_query_handler,
)

from .writer_tools import (
    write_section_handler,
    write_entity_profile_handler,
    add_footnote_handler,
    flag_surprising_and_handler,
    stream_finding_handler,
)

# Aggregate all tools for easy access
SASTRE_TOOLS = {
    # Disambiguation
    "check_passive_constraints": check_passive_constraints_handler,
    "generate_wedge_queries": generate_wedge_queries_handler,
    "apply_resolution": apply_resolution_handler,
    # Grid Assessment
    "narrative_assessment": narrative_assessment_handler,
    "subject_assessment": subject_assessment_handler,
    "location_assessment": location_assessment_handler,
    "nexus_assessment": nexus_assessment_handler,
    "cross_pollinate": cross_pollinate_handler,
    "full_assessment": full_assessment_handler,
    # IO
    "execute_macro": execute_macro_handler,
    "expand_variations": expand_variations_handler,
    "extract_entities": extract_entities_handler,
    "check_source": check_source_handler,
    # Query Lab
    "build_fused_query": build_fused_query_handler,
    # Writer
    "write_section": write_section_handler,
    "write_entity_profile": write_entity_profile_handler,
    "add_footnote": add_footnote_handler,
    "flag_surprising_and": flag_surprising_and_handler,
    "stream_finding": stream_finding_handler,
}

__all__ = [
    # Disambiguation
    "check_passive_constraints_handler",
    "generate_wedge_queries_handler",
    "apply_resolution_handler",
    # Grid
    "narrative_assessment_handler",
    "subject_assessment_handler",
    "location_assessment_handler",
    "nexus_assessment_handler",
    "cross_pollinate_handler",
    "full_assessment_handler",
    # IO
    "execute_macro_handler",
    "expand_variations_handler",
    "extract_entities_handler",
    "check_source_handler",
    # Query Lab
    "build_fused_query_handler",
    # Writer
    "write_section_handler",
    "write_entity_profile_handler",
    "add_footnote_handler",
    "flag_surprising_and_handler",
    "stream_finding_handler",
    # Aggregate
    "SASTRE_TOOLS",
]
