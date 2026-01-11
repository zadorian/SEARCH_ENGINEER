"""
SASTRE Sufficiency Check - Constraint-Based + Semantic

Sufficiency is 5 binary constraints PLUS semantic check against the template.
ALL YES -> Ready to export
ANY NO -> Generate targeted queries, loop

The structural constraints:
1. core_fields_populated: All core entity fields have values
2. tasking_headers_addressed: All tasking sections have content
3. no_high_weight_absences: No EXPECTED_NOT_FOUND gaps remain
4. disambiguation_resolved: No BINARY_STAR or all parked explicitly
5. surprising_ands_processed: All investigated or parked

The semantic constraint (added via NarrativeGovernor):
6. story_satisfied: Word count threshold met AND required sections filled
   (This is NOT a percentage - it's template-defined completeness)
"""

from typing import Dict, List, Optional

from .contracts import (
    Document, SufficiencyResult, SectionState, NarrativeGovernor
)

try:
    from .core.schema_reader import get_schema_reader
    SCHEMA_AVAILABLE = True
except Exception:
    SCHEMA_AVAILABLE = False


def check_sufficiency(document: Document) -> SufficiencyResult:
    """
    Check all 5 sufficiency constraints.

    Returns SufficiencyResult with pass/fail for each constraint.
    """
    checks: Dict[str, bool] = {}
    incomplete_reasons: List[str] = []

    # Constraint 1: Core fields populated for all entities
    core_check, core_reason = _check_core_fields(document)
    checks['core_fields_populated'] = core_check
    if not core_check:
        incomplete_reasons.append(core_reason)

    # Constraint 2: All tasking sections have content
    tasking_check, tasking_reason = _check_tasking_headers(document)
    checks['tasking_headers_addressed'] = tasking_check
    if not tasking_check:
        incomplete_reasons.append(tasking_reason)

    # Constraint 3: No high-weight absences remain
    absence_check, absence_reason = _check_high_weight_absences(document)
    checks['no_high_weight_absences'] = absence_check
    if not absence_check:
        incomplete_reasons.append(absence_reason)

    # Constraint 4: All entity collisions resolved or parked
    disambiguation_check, disambiguation_reason = _check_disambiguation(document)
    checks['disambiguation_resolved'] = disambiguation_check
    if not disambiguation_check:
        incomplete_reasons.append(disambiguation_reason)

    # Constraint 5: All Surprising ANDs investigated or parked
    surprising_check, surprising_reason = _check_surprising_ands(document)
    checks['surprising_ands_processed'] = surprising_check
    if not surprising_check:
        incomplete_reasons.append(surprising_reason)

    constraints_met = sum(1 for value in checks.values() if value)
    total_constraints = len(checks)
    overall_score = constraints_met / total_constraints if total_constraints else 0.0

    return SufficiencyResult(
        core_fields_populated=checks.get("core_fields_populated", False),
        tasking_headers_addressed=checks.get("tasking_headers_addressed", False),
        no_high_weight_absences=checks.get("no_high_weight_absences", False),
        disambiguation_resolved=checks.get("disambiguation_resolved", False),
        surprising_ands_processed=checks.get("surprising_ands_processed", False),
        is_sufficient=all(checks.values()),
        overall_score=overall_score,
        narrative_score=1.0 if checks.get("tasking_headers_addressed", False) else 0.0,
        subject_score=1.0 if checks.get("core_fields_populated", False) else 0.0,
        location_score=1.0 if checks.get("no_high_weight_absences", False) else 0.0,
        nexus_score=1.0 if checks.get("disambiguation_resolved", False) else 0.0,
        remaining_gaps=total_constraints - constraints_met,
        collisions_pending=len(document.binary_stars),
        recommendation=incomplete_reasons[0] if incomplete_reasons else "",
    )


def _schema_required_fields(entity_type: str) -> Optional[List[str]]:
    """Return required fields from schema if available."""
    if not SCHEMA_AVAILABLE:
        return None
    try:
        reader = get_schema_reader()
        type_def = reader.get_entity_type(entity_type)
        if not type_def:
            return None
        return [prop.name for prop in type_def.required_properties]
    except Exception:
        return None


def _check_core_fields(document: Document) -> tuple[bool, str]:
    """
    Check if all known entities have their core fields populated.

    Core fields are the minimum required identifiers for each entity type.
    """
    for entity in document.known_entities:
        entity_type = entity.entity_type or "unknown"
        required = _schema_required_fields(entity_type) or ["name"]
        core = entity.attributes.core or {}
        shell = entity.attributes.shell or {}

        for field in required:
            if field == "name":
                if not entity.name:
                    return (False, "Entity missing name")
                continue

            value = core.get(field)
            if value is None or value == "":
                value = shell.get(field)

            if value is None or value == "" or (isinstance(value, list) and len(value) == 0):
                entity_name = entity.name or entity.id or "unknown"
                return (False, f"Entity {entity_name} missing core field: {field}")

    return (True, "")


def _check_tasking_headers(document: Document) -> tuple[bool, str]:
    """
    Check if all tasking-specific sections have content.

    Empty sections indicate unfulfilled tasking.
    """
    empty_sections = []

    for section in document.sections:
        header = (section.header or "").strip()
        if "⚡" in header:
            continue

        if section.state in [SectionState.EMPTY, SectionState.INCOMPLETE]:
            empty_sections.append(header)

    if empty_sections:
        return (False, f"Empty sections: {', '.join(empty_sections[:3])}")

    return (True, "")


def _check_high_weight_absences(document: Document) -> tuple[bool, str]:
    """
    Check if any EXPECTED_NOT_FOUND gaps remain.

    These are high-signal gaps that should be investigated.
    """
    # Check for [?] markers that indicate expected data is missing
    high_priority_gaps = []

    for section in document.sections:
        for gap in section.gaps:
            gap_text = gap if isinstance(gap, str) else str(gap)
            gap_lower = gap_text.lower()
            expected_keywords = [
                "beneficial owner", "registration", "tax id",
                "director", "shareholder", "jurisdiction"
            ]
            if any(kw in gap_lower for kw in expected_keywords):
                high_priority_gaps.append(gap_text)

    if high_priority_gaps:
        return (False, f"Expected fields missing: {high_priority_gaps[0]}")

    return (True, "")


def _check_disambiguation(document: Document) -> tuple[bool, str]:
    """
    Check if all entity collisions are resolved.

    Binary stars must be either resolved or explicitly parked.
    """
    if document.binary_stars:
        unresolved = [
            f"{bs.entity_a_id} / {bs.entity_b_id}"
            for bs in document.binary_stars
        ]
        return (False, f"Unresolved entity collisions: {unresolved[0]}")

    return (True, "")


def _check_surprising_ands(document: Document) -> tuple[bool, str]:
    """
    Check if all Surprising ANDs have been investigated.

    Unexpected connections must be investigated or explicitly parked.
    """
    unprocessed = [
        sa for sa in document.surprising_ands
        if not getattr(sa, "section_spawned", False)
    ]

    if unprocessed:
        return (False, f"Unprocessed connection: {unprocessed[0].connection}")

    return (True, "")


def get_incomplete_constraints(document: Document) -> List[str]:
    """
    Get list of constraint names that are not satisfied.

    Useful for determining which areas need work.
    """
    result = check_sufficiency(document)
    constraints = {
        "core_fields_populated": result.core_fields_populated,
        "tasking_headers_addressed": result.tasking_headers_addressed,
        "no_high_weight_absences": result.no_high_weight_absences,
        "disambiguation_resolved": result.disambiguation_resolved,
        "surprising_ands_processed": result.surprising_ands_processed,
    }
    return [name for name, ok in constraints.items() if not ok]


def summarize_progress(document: Document) -> str:
    """
    Generate human-readable progress summary.
    """
    result = check_sufficiency(document)
    constraints = {
        "core_fields_populated": result.core_fields_populated,
        "tasking_headers_addressed": result.tasking_headers_addressed,
        "no_high_weight_absences": result.no_high_weight_absences,
        "disambiguation_resolved": result.disambiguation_resolved,
        "surprising_ands_processed": result.surprising_ands_processed,
    }
    passed = sum(1 for ok in constraints.values() if ok)
    total = len(constraints)

    lines = [f"Sufficiency: {passed}/{total} constraints met"]

    for constraint, ok in constraints.items():
        status = "OK" if ok else "MISS"
        lines.append(f"  {status} {constraint.replace('_', ' ')}")

    if result.recommendation:
        lines.append("\nBlocking issue:")
        lines.append(f"  - {result.recommendation}")

    return "\n".join(lines)


# =============================================================================
# SEMANTIC SUFFICIENCY (Governor-Based)
# =============================================================================

def check_semantic_sufficiency(
    document: Document,
    governor: NarrativeGovernor,
) -> tuple[bool, str]:
    """
    Check if the story is semantically sufficient for the template.

    This is NOT a percentage check. It asks:
    1. Have we met the word count threshold for this depth level?
    2. Have we filled the required sections for this genre?
    3. Has the governor decided to stop drilling?

    Returns:
        (is_satisfied, reason)
    """
    # Count actual words in document
    total_words = 0
    filled_sections: set = set()

    for section in document.sections:
        content = section.content or ""
        section_words = len(content.split())
        total_words += section_words

        header = (section.header or "").strip().lower()

        # Mark section as filled if it has substantial content
        if section_words >= 50:  # Minimum 50 words to count as "filled"
            filled_sections.add(header)

    # Update governor with current state
    governor.current_word_count = total_words
    for section in filled_sections:
        governor.sections_filled.add(section)

    # Check word count threshold (80% is considered sufficient)
    word_threshold_met = total_words >= governor.max_word_count * 0.8

    # Check required sections
    required_lower = {s.lower() for s in governor.required_sections}
    sections_met = len(required_lower - filled_sections) <= 2  # Allow 2 missing

    # Check governor's decision
    governor_satisfied = not governor.should_continue_drilling()

    # Combine checks
    is_satisfied = (word_threshold_met and sections_met) or governor_satisfied

    if is_satisfied:
        return (True, f"Story satisfied: {total_words} words, {len(filled_sections)} sections")

    # Generate reason
    reasons = []
    if not word_threshold_met:
        needed = int(governor.max_word_count * 0.8) - total_words
        reasons.append(f"Need ~{needed} more words")

    missing_sections = list(required_lower - filled_sections)[:3]
    if missing_sections:
        reasons.append(f"Missing: {', '.join(missing_sections)}")

    return (False, "; ".join(reasons))


def check_full_sufficiency(
    document: Document,
    governor: Optional[NarrativeGovernor] = None,
) -> SufficiencyResult:
    """
    Check both structural AND semantic sufficiency.

    This is the master check that combines:
    - 5 structural constraints (core fields, headers, absences, disambiguation, surprising ANDs)
    - 1 semantic constraint (story satisfied for this genre/depth)

    If governor is provided, the semantic check is included.
    """
    # Get structural result first
    result = check_sufficiency(document)

    # Add semantic check if governor provided
    if governor:
        is_satisfied, reason = check_semantic_sufficiency(document, governor)

        # Update result with semantic info
        if not is_satisfied:
            # Semantic check failed - not sufficient even if structural passed
            result.is_sufficient = False
            if result.recommendation:
                result.recommendation += f"; {reason}"
            else:
                result.recommendation = reason

        # Add governor scores
        result.narrative_score = min(1.0, governor.current_word_count / governor.max_word_count)
        result.overall_score = (
            result.constraints_met / 5 * 0.6 +  # 60% structural
            result.narrative_score * 0.4         # 40% semantic
        )

    return result


def should_stop_investigating(
    document: Document,
    governor: Optional[NarrativeGovernor] = None,
) -> tuple[bool, str]:
    """
    The master question: Should we stop investigating?

    This is what the orchestrator calls to decide whether to continue
    the investigation loop or export the document.

    Returns:
        (should_stop, reason)
    """
    # Check structural constraints
    result = check_sufficiency(document)

    if result.is_complete:
        # All structural constraints met
        if governor:
            # Also check semantic
            semantic_ok, semantic_reason = check_semantic_sufficiency(document, governor)
            if semantic_ok:
                return (True, "All constraints met; story satisfied")
            else:
                return (False, f"Structural OK but: {semantic_reason}")
        else:
            return (True, "All structural constraints met")

    # Structural constraints not met
    return (False, result.recommendation or "Constraints not met")
