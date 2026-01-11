"""
SASTRE Narrative Governor Loader

Loads NarrativeGovernor from the mined report library:
    - input_output/matrix/report_generation.json: Genre profiles, depth levels
    - input_output/matrix/section_templates_catalog.json: Section word counts
    - input_output/matrix/writing_guide.json: Voice patterns, exemplars

The Narrative is not just output; it is the Governor.
The template defines drill depth; output format dictates input effort.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

from ..contracts import (
    NarrativeGovernor,
    DepthLevel,
    SectionConstraint,
    VoiceProfile,
    CertaintyPhrases,
)

logger = logging.getLogger(__name__)

# Cache for loaded data
_REPORT_GEN_CACHE: Optional[Dict[str, Any]] = None
_SECTION_TEMPLATES_CACHE: Optional[Dict[str, Any]] = None
_WRITING_GUIDE_CACHE: Optional[Dict[str, Any]] = None


def _find_matrix_path() -> Path:
    """Find the input_output/matrix directory."""
    # Try multiple paths
    candidates = [
        Path(__file__).parent.parent.parent.parent.parent / "input_output" / "matrix",
        Path(__file__).parent.parent.parent.parent.parent / "input_output2" / "matrix",
        Path("/Users/attic/01. DRILL_SEARCH/drill-search-app/input_output/matrix"),
        Path("/Users/attic/01. DRILL_SEARCH/drill-search-app/input_output2/matrix"),
    ]

    for path in candidates:
        if path.exists() and (path / "report_generation.json").exists():
            return path

    raise FileNotFoundError(f"Could not find matrix directory. Checked: {candidates}")


def _load_report_generation() -> Dict[str, Any]:
    """Load report_generation.json (cached)."""
    global _REPORT_GEN_CACHE
    if _REPORT_GEN_CACHE is not None:
        return _REPORT_GEN_CACHE

    try:
        matrix_path = _find_matrix_path()
        report_path = matrix_path / "report_generation.json"

        with open(report_path, 'r') as f:
            _REPORT_GEN_CACHE = json.load(f)

        logger.info(f"Loaded report_generation.json from {report_path}")
        return _REPORT_GEN_CACHE
    except Exception as e:
        logger.warning(f"Failed to load report_generation.json: {e}")
        return {}


def _load_section_templates() -> Dict[str, Any]:
    """Load section_templates_catalog.json (cached)."""
    global _SECTION_TEMPLATES_CACHE
    if _SECTION_TEMPLATES_CACHE is not None:
        return _SECTION_TEMPLATES_CACHE

    try:
        matrix_path = _find_matrix_path()
        templates_path = matrix_path / "section_templates_catalog.json"

        with open(templates_path, 'r') as f:
            _SECTION_TEMPLATES_CACHE = json.load(f)

        logger.info(f"Loaded section_templates_catalog.json from {templates_path}")
        return _SECTION_TEMPLATES_CACHE
    except Exception as e:
        logger.warning(f"Failed to load section_templates_catalog.json: {e}")
        return {}


def _load_writing_guide() -> Dict[str, Any]:
    """Load writing_guide.json (cached)."""
    global _WRITING_GUIDE_CACHE
    if _WRITING_GUIDE_CACHE is not None:
        return _WRITING_GUIDE_CACHE

    try:
        matrix_path = _find_matrix_path()
        guide_path = matrix_path / "writing_guide.json"

        with open(guide_path, 'r') as f:
            _WRITING_GUIDE_CACHE = json.load(f)

        logger.info(f"Loaded writing_guide.json from {guide_path}")
        return _WRITING_GUIDE_CACHE
    except Exception as e:
        logger.warning(f"Failed to load writing_guide.json: {e}")
        return {}


def _parse_voice_profile(voice_key: str, report_gen: Dict, writing_guide: Dict) -> VoiceProfile:
    """Build VoiceProfile from both sources."""
    # Get from report_generation.json
    voice_options = report_gen.get("writing_style_rules", {}).get("voice_options", {})
    voice_data = voice_options.get(voice_key, {})

    # Get sample rules from writing_guide.json
    guide_voice_options = writing_guide.get("voice_options", {})

    # Map voice keys to writing guide keys
    voice_key_map = {
        "third_person": "third_person_neutral_observer",
        "first_plural": "first_plural_neutral_observer",
    }
    guide_key = voice_key_map.get(voice_key, voice_key)
    guide_data = guide_voice_options.get(guide_key, {})

    return VoiceProfile(
        voice_type=voice_key,
        description=voice_data.get("description", ""),
        example_openings=voice_data.get("example_openings", []),
        prohibited_phrases=voice_data.get("prohibited_phrases", []),
        sample_rules=guide_data.get("sample_rules", []),
    )


def _parse_certainty_phrases(report_gen: Dict, writing_guide: Dict) -> CertaintyPhrases:
    """Build CertaintyPhrases from both sources."""
    # Get from report_generation.json
    certainty = report_gen.get("writing_style_rules", {}).get("certainty_calibration", {})

    # Also get from writing_guide.json
    guide_certainty = writing_guide.get("certainty_calibration", {})

    return CertaintyPhrases(
        verified_facts=certainty.get("verified_facts", {}).get("phrases", [])
                       or guide_certainty.get("verified_facts_phrases", []),
        high_confidence=certainty.get("high_confidence", {}).get("phrases", []),
        medium_confidence=certainty.get("medium_confidence", {}).get("phrases", []),
        inference=certainty.get("low_confidence_inference", {}).get("phrases", [])
                  or guide_certainty.get("inference_phrases", []),
        unverified=certainty.get("unverified", {}).get("phrases", [])
                   or guide_certainty.get("unverified_claims_phrases", []),
    )


def _parse_section_constraints(section_templates: Dict) -> Dict[str, SectionConstraint]:
    """Build section constraints from section_templates_catalog.json."""
    constraints = {}

    sections = section_templates.get("sections", {})
    for section_name, section_data in sections.items():
        word_range = section_data.get("word_count_range", {})

        constraints[section_name.lower()] = SectionConstraint(
            section_name=section_name,
            min_words=word_range.get("min", 50),
            max_words=word_range.get("max", 1500),
            avg_words=word_range.get("avg", 300),
            required_content=section_data.get("typical_content", []),
            key_phrases=section_data.get("key_phrases", []),
            data_sources=section_data.get("data_sources", []),
        )

    return constraints


def load_governor(
    genre: str = "due_diligence",
    depth: str = "enhanced",
) -> NarrativeGovernor:
    """
    Load a NarrativeGovernor for the specified genre and depth.

    Args:
        genre: Report genre (due_diligence, background_check, asset_trace,
               corporate_intelligence, litigation_support)
        depth: Depth level (basic, enhanced, comprehensive)

    Returns:
        NarrativeGovernor configured from the mined report library
    """
    # Load all JSON files
    report_gen = _load_report_generation()
    section_templates = _load_section_templates()
    writing_guide = _load_writing_guide()

    # Get genre profile
    genre_profiles = report_gen.get("genre_profiles", {})
    profile = genre_profiles.get(genre, genre_profiles.get("due_diligence", {}))

    # Get depth level config
    depth_levels = profile.get("depth_levels", {})
    depth_config = depth_levels.get(depth, depth_levels.get("enhanced", {}))

    # Map depth string to enum
    depth_enum = {
        "basic": DepthLevel.BASIC,
        "enhanced": DepthLevel.ENHANCED,
        "comprehensive": DepthLevel.COMPREHENSIVE,
    }.get(depth, DepthLevel.ENHANCED)

    # Build voice profile
    voice_key = profile.get("voice", "third_person")
    voice = _parse_voice_profile(voice_key, report_gen, writing_guide)

    # Build certainty phrases
    certainty = _parse_certainty_phrases(report_gen, writing_guide)

    # Build section constraints
    section_constraints = _parse_section_constraints(section_templates)

    # Get professional conventions
    conventions = report_gen.get("writing_style_rules", {}).get("professional_conventions", {})

    # Create governor
    governor = NarrativeGovernor(
        genre=genre,
        depth_level=depth_enum,

        # Hard constraints from depth level
        max_word_count=depth_config.get("word_count", 5000),
        max_sections=depth_config.get("sections", 8),
        max_drill_iterations=_iterations_from_depth(depth),
        required_sections=profile.get("typical_sections", []),

        # Section constraints
        section_constraints=section_constraints,

        # Voice and style
        voice=voice,
        formality=profile.get("formality", "professional"),
        stance=profile.get("stance", "neutral_observer"),
        attribution_style=profile.get("attribution_style", "footnoted"),

        # Certainty calibration
        certainty_phrases=certainty,

        # Professional conventions
        entity_introduction_company=conventions.get("entity_introduction", {}).get("company", ""),
        entity_introduction_person=conventions.get("entity_introduction", {}).get("person", ""),
        date_format=conventions.get("date_formatting", {}).get("standard", "DD Month YYYY"),
        currency_format=conventions.get("currency_formatting", {}).get("standard", "€53.02 million"),
        negative_finding_phrase=conventions.get("negative_findings", {}).get("standard",
            "No adverse information was identified."),
    )

    logger.info(f"Created NarrativeGovernor: {genre}/{depth} - max {governor.max_word_count} words, "
                f"{len(governor.required_sections)} sections")

    return governor


def _iterations_from_depth(depth: str) -> int:
    """Map depth level to max drill iterations."""
    return {
        "basic": 5,
        "enhanced": 10,
        "comprehensive": 20,
    }.get(depth, 10)


def get_available_genres() -> List[str]:
    """Get list of available genres from report library."""
    report_gen = _load_report_generation()
    return list(report_gen.get("genre_profiles", {}).keys())


def get_genre_info(genre: str) -> Dict[str, Any]:
    """Get full info for a genre (for UI display)."""
    report_gen = _load_report_generation()
    profile = report_gen.get("genre_profiles", {}).get(genre, {})

    return {
        "genre": genre,
        "description": profile.get("description", ""),
        "typical_sections": profile.get("typical_sections", []),
        "depth_levels": {
            level: {
                "word_count": config.get("word_count", 5000),
                "sections": config.get("sections", 8),
            }
            for level, config in profile.get("depth_levels", {}).items()
        },
        "voice": profile.get("voice", "third_person"),
        "formality": profile.get("formality", "professional"),
    }


def get_exemplar_passages(category: str = None, limit: int = 5) -> List[Dict[str, str]]:
    """
    Get exemplar passages from the writing guide.

    Args:
        category: Filter by category (e.g., "certainty_calibration", "source_attribution")
        limit: Maximum number of passages to return

    Returns:
        List of exemplar passages with 'passage', 'demonstrates', 'why_effective' keys
    """
    writing_guide = _load_writing_guide()
    exemplars = writing_guide.get("exemplar_passages", [])

    if category:
        # Filter by demonstration type
        exemplars = [e for e in exemplars if category.lower() in e.get("demonstrates", "").lower()]

    return exemplars[:limit]


def clear_cache():
    """Clear all cached data (useful for testing)."""
    global _REPORT_GEN_CACHE, _SECTION_TEMPLATES_CACHE, _WRITING_GUIDE_CACHE
    _REPORT_GEN_CACHE = None
    _SECTION_TEMPLATES_CACHE = None
    _WRITING_GUIDE_CACHE = None
