"""
Mined Context Builder for SASTRE Agents

Injects mined intelligence into agent system prompts for smarter decisions.

Usage:
    from mined_context import (
        get_io_executor_context,
        get_writer_context,
        get_orchestrator_context
    )

    # Enrich IO Executor with jurisdiction-specific intelligence
    context = get_io_executor_context(jurisdiction="HU", action_types=["company_officers", "ubo"])
    full_prompt = BASE_PROMPT + context

    # Enrich Writer with exemplars
    context = get_writer_context(section_type="ownership_analysis", jurisdiction="HU")
    full_prompt = BASE_PROMPT + context
"""

import importlib.util
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

# Load mined_intelligence dynamically without sys.path manipulation
MATRIX_PATH = Path(__file__).resolve().parent.parent.parent.parent / "input_output" / "matrix"
MINED_INTELLIGENCE_PATH = MATRIX_PATH / "mined_intelligence.py"

MINED_AVAILABLE = False
MinedIntelligence = None
get_mined_intelligence = None

if MINED_INTELLIGENCE_PATH.exists():
    try:
        spec = importlib.util.spec_from_file_location("mined_intelligence", MINED_INTELLIGENCE_PATH)
        mined_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mined_module)
        MinedIntelligence = mined_module.MinedIntelligence
        get_mined_intelligence = mined_module.get_mined_intelligence
        MINED_AVAILABLE = True
        logger.info("Mined intelligence loaded successfully")
    except Exception as e:
        logger.warning(f"Failed to load mined intelligence: {e}")
else:
    logger.info("Mined intelligence not available - agents will use base prompts only")


def get_io_executor_context(
    jurisdiction: str,
    action_types: List[str] = None,
    entity_type: str = "company"
) -> str:
    """
    Build context injection for IO Executor agent.

    Includes:
    - Dead ends to avoid for this jurisdiction
    - Source reliability rankings
    - Arbitrage routes when direct fails
    """
    if not MINED_AVAILABLE:
        return ""

    mi = get_mined_intelligence()
    sections = []

    # 1. Dead Ends Warning
    dead_ends = mi.get_dead_ends_for_jurisdiction(jurisdiction)
    if dead_ends:
        sections.append("## KNOWN DEAD ENDS FOR THIS JURISDICTION\n")
        sections.append("Do NOT attempt these queries - they are documented failures:\n\n")
        for de in dead_ends[:10]:  # Top 10
            sections.append(f"- **{de.sought}**: {de.reason}\n")
        sections.append("\n")

    # 2. Arbitrage Routes
    if action_types:
        sections.append("## ARBITRAGE ALTERNATIVES\n")
        sections.append("If direct queries fail, try these cross-jurisdictional routes:\n\n")

        for action in action_types:
            routes = mi.get_arbitrage_routes(jurisdiction, action)
            if routes:
                sections.append(f"### For {action}:\n")
                for route in routes[:3]:
                    sections.append(
                        f"- Via **{route.source_jurisdiction}** ({route.source_registry}): "
                        f"{', '.join(route.info_types)}\n"
                    )
                sections.append("\n")

    # 3. Source Reliability (from jurisdiction data)
    jur_info = mi.get_jurisdiction_info(jurisdiction)
    if jur_info:
        sections.append("## JURISDICTION INTELLIGENCE\n\n")
        if jur_info.get("transparency"):
            sections.append(f"- **Transparency level**: {jur_info['transparency']}\n")
        if jur_info.get("primary_registries"):
            sections.append(f"- **Primary registries**: {', '.join(jur_info['primary_registries'][:5])}\n")
        if jur_info.get("language"):
            sections.append(f"- **Language**: {jur_info['language']}\n")
        if jur_info.get("common_blockers"):
            sections.append(f"- **Common blockers**: {', '.join(jur_info['common_blockers'][:3])}\n")
        sections.append("\n")

    # 4. Rich Methodology (the core value)
    if action_types:
        # Use the first action type as the investigation goal
        goal = action_types[0] if action_types else "corporate_structure"
        methodology_section = get_methodology_context(goal, jurisdiction)
        if methodology_section:
            sections.append(methodology_section)

    return "".join(sections)


def get_writer_context(
    section_type: str,
    jurisdiction: str = None,
    voice: str = "third_person_professional",
    include_exemplar: bool = True
) -> str:
    """
    Build context injection for Writer agent.

    Includes:
    - Exemplar passage for this section type
    - Voice and attribution guidance
    - Section-specific patterns
    """
    if not MINED_AVAILABLE:
        return ""

    mi = get_mined_intelligence()
    sections = []

    # 1. Writing Style
    style = mi.get_writing_style(voice)
    if style:
        sections.append("## WRITING STYLE GUIDANCE\n\n")
        sections.append(f"**Voice**: {voice.replace('_', ' ').title()}\n")
        if style.get("attribution"):
            sections.append(f"**Attribution**: {style['attribution']}\n")
        if style.get("characteristics"):
            sections.append(f"**Key characteristics**: {style['characteristics'][:200]}\n")
        sections.append("\n")

    # 2. Exemplar Passage
    if include_exemplar:
        template = mi.get_section_template(section_type, jurisdiction)
        if template and template.get("exemplar"):
            sections.append("## EXEMPLAR FOR THIS SECTION\n\n")
            sections.append("Match the style of this verified example:\n\n")
            exemplar = template.get("exemplar", "")[:800]
            sections.append(f'"""\n{exemplar}\n"""\n\n')
            sections.append("Key patterns to follow:\n")
            sections.append("- Specific dates and figures\n")
            sections.append("- Footnoted attribution\n")
            sections.append("- Certainty calibration (\"appears to\", \"records indicate\")\n\n")

    # 3. Section-specific guidance
    template = mi.get_section_template(section_type, jurisdiction)
    if template:
        sections.append(f"## {section_type.upper().replace('_', ' ')} SECTION GUIDANCE\n\n")
        if template.get("typical_length"):
            sections.append(f"**Typical length**: {template['typical_length']} words\n")
        if template.get("key_elements"):
            sections.append(f"**Key elements**: {', '.join(template['key_elements'][:5])}\n")
        if template.get("common_sources"):
            sections.append(f"**Common sources**: {', '.join(template['common_sources'][:5])}\n")
        sections.append("\n")

    return "".join(sections)


def get_orchestrator_context(
    entity: str,
    entity_type: str,
    jurisdiction: str,
    found_red_flags: List[str] = None,
    current_phase: str = None
) -> str:
    """
    Build context injection for Orchestrator agent.

    Includes:
    - Investigation fingerprint matching
    - Red flag propagation predictions
    - Playbook recommendations
    """
    if not MINED_AVAILABLE:
        return ""

    mi = get_mined_intelligence()
    sections = []

    # 1. Jurisdiction overview
    jur_info = mi.get_jurisdiction_info(jurisdiction)
    if jur_info:
        sections.append("## JURISDICTION PROFILE\n\n")
        complexity = jur_info.get("complexity_score", 3)
        sections.append(f"**Complexity**: {'★' * complexity}{'☆' * (5-complexity)} ({complexity}/5)\n")
        if jur_info.get("typical_investigation_time"):
            sections.append(f"**Typical time**: {jur_info['typical_investigation_time']}\n")
        if jur_info.get("key_challenges"):
            sections.append(f"**Key challenges**: {', '.join(jur_info['key_challenges'][:3])}\n")
        sections.append("\n")

    # 2. Red Flag Propagation
    if found_red_flags:
        sections.append("## RED FLAG INTELLIGENCE\n\n")
        sections.append(f"**Found flags**: {', '.join(found_red_flags)}\n\n")

        # Get predictions from mined patterns
        # Simple co-occurrence-based prediction
        try:
            sectors = mi._load_json("mined_sectors.json") if hasattr(mi, '_load_json') else {}
            predictions = []

            # Handle both dict and list formats
            sector_items = []
            if isinstance(sectors, dict):
                sector_items = sectors.get("sectors", sectors).values() if isinstance(sectors.get("sectors", sectors), dict) else []
            elif isinstance(sectors, list):
                sector_items = sectors

            # Build co-occurrence from sectors
            for sector_data in sector_items:
                if isinstance(sector_data, dict):
                    flags = sector_data.get("common_red_flags", [])
                    for found in found_red_flags:
                        if found in flags:
                            for other in flags:
                                if other not in found_red_flags and other not in predictions:
                                    predictions.append(other)

            if predictions:
                sections.append("**Predicted related flags** (investigate these):\n")
                for pred in predictions[:5]:
                    sections.append(f"- {pred}\n")
                sections.append("\n")
        except Exception as e:
            logger.debug(f"Red flag propagation skipped: {e}")

    # 3. Dead-end summary for planning
    dead_ends = mi.get_dead_ends_for_jurisdiction(jurisdiction)
    if dead_ends:
        sections.append("## DEAD-END SUMMARY\n\n")
        sections.append(f"**{len(dead_ends)} known dead ends** for {jurisdiction}. Key ones:\n\n")
        for de in dead_ends[:5]:
            sections.append(f"- {de.sought[:60]}...\n")
        sections.append("\nAvoid assigning tasks for these - they will fail.\n\n")

    # 4. Methodology recommendations
    methodology = mi.get_methodology_by_jurisdiction(jurisdiction)
    if methodology:
        sections.append("## RECOMMENDED METHODOLOGY\n\n")
        sections.append("Approaches that worked for similar investigations:\n\n")
        for m in methodology[:3]:
            desc = m.get("description", "")[:150]
            if desc:
                sections.append(f"- {desc}\n")
        sections.append("\n")

    return "".join(sections)


def get_methodology_context(
    investigation_goal: str,
    jurisdiction: str,
    entity_type: str = "company",
    prefer_open_sources: bool = True
) -> str:
    """
    Build rich methodology advice for AI decision-makers.

    This is the core value injection - telling the AI HOW to investigate
    based on 6,126 proven patterns.

    Args:
        investigation_goal: What we're trying to find (e.g., "trace_ubo", "verify_identity")
        jurisdiction: Primary jurisdiction
        entity_type: company/person
        prefer_open_sources: Prioritize low-friction sources

    Returns:
        Detailed methodology guidance with specific source recommendations
    """
    if not MINED_AVAILABLE:
        return ""

    mi = get_mined_intelligence()
    sections = []

    # Load methodology directly for richer access
    methodology_data = mi._load_json("mined_methodology.json")
    patterns = methodology_data.get("patterns", [])

    if not patterns:
        return ""

    sections.append("# METHODOLOGY INTELLIGENCE\n\n")
    sections.append(f"Based on 6,126 proven investigation patterns.\n\n")

    # 1. Jurisdiction-specific methods that worked
    jur_patterns = [p for p in patterns if p.get("jurisdiction") == jurisdiction]
    if jur_patterns:
        sections.append(f"## WHAT WORKS IN {jurisdiction}\n\n")

        # Group by method type
        method_groups = {}
        for p in jur_patterns:
            method = p.get("method", "unknown")
            if method not in method_groups:
                method_groups[method] = {"success": 0, "fail": 0, "patterns": []}
            if p.get("success"):
                method_groups[method]["success"] += 1
            else:
                method_groups[method]["fail"] += 1
            method_groups[method]["patterns"].append(p)

        # Sort by success rate
        sorted_methods = sorted(
            method_groups.items(),
            key=lambda x: x[1]["success"] / max(1, x[1]["success"] + x[1]["fail"]),
            reverse=True
        )

        for method, data in sorted_methods[:6]:
            total = data["success"] + data["fail"]
            rate = 100 * data["success"] / max(1, total)
            sections.append(f"### {method.replace('_', ' ').title()} ({rate:.0f}% success, n={total})\n")

            # Get best examples
            successful = [p for p in data["patterns"] if p.get("success")][:3]
            for p in successful:
                source = p.get("source_used", "")
                friction = p.get("friction", "unknown")
                desc = p.get("description", "")[:150]
                sections.append(f"- **{source}** [{friction}]: {desc}\n")
            sections.append("\n")

    # 2. Methods to AVOID (high failure in this jurisdiction)
    failed_methods = [p for p in jur_patterns if not p.get("success")]
    if failed_methods:
        sections.append(f"## METHODS THAT FAILED IN {jurisdiction}\n\n")

        # Group failures
        fail_groups = {}
        for p in failed_methods:
            method = p.get("method", "unknown")
            if method not in fail_groups:
                fail_groups[method] = []
            fail_groups[method].append(p)

        for method, failures in sorted(fail_groups.items(), key=lambda x: -len(x[1]))[:4]:
            sections.append(f"- **{method}** ({len(failures)} failures): ")
            reasons = set(p.get("description", "")[:80] for p in failures[:2])
            sections.append(f"{'; '.join(reasons)}\n")
        sections.append("\n")

    # 3. Goal-specific methodology
    goal_keywords = {
        "trace_ubo": ["beneficial", "owner", "shareholder", "ownership"],
        "verify_identity": ["identity", "background", "verification", "biographical"],
        "find_assets": ["property", "asset", "land", "real estate", "yacht", "aircraft"],
        "litigation_history": ["court", "litigation", "lawsuit", "legal"],
        "sanctions_check": ["sanction", "watchlist", "OFAC", "screening"],
        "corporate_structure": ["corporate", "structure", "subsidiary", "holding"],
    }

    keywords = goal_keywords.get(investigation_goal, [investigation_goal])

    goal_patterns = [
        p for p in patterns
        if any(kw in p.get("description", "").lower() for kw in keywords)
    ]

    if goal_patterns:
        sections.append(f"## METHODOLOGY FOR: {investigation_goal.replace('_', ' ').upper()}\n\n")

        # Prioritize by friction if requested
        if prefer_open_sources:
            goal_patterns.sort(key=lambda p: (
                0 if p.get("friction") == "open" else
                1 if p.get("friction") == "restricted" else
                2 if p.get("friction") == "paywalled" else 3,
                -1 if p.get("success") else 0
            ))

        sections.append("**Recommended approach (ordered by accessibility):**\n\n")

        seen_sources = set()
        for p in goal_patterns[:10]:
            source = p.get("source_used", "")
            if source in seen_sources:
                continue
            seen_sources.add(source)

            friction = p.get("friction", "unknown")
            success = "✓" if p.get("success") else "✗"
            jur = p.get("jurisdiction", "")
            desc = p.get("description", "")[:120]

            friction_emoji = {
                "open": "🟢",
                "restricted": "🟡",
                "paywalled": "🟠",
                "impossible": "🔴"
            }.get(friction, "⚪")

            sections.append(f"{friction_emoji} **{source}** [{jur}] {success}\n")
            sections.append(f"   {desc}\n\n")

    # 4. Cross-jurisdictional patterns (if jurisdiction has limited data)
    if len(jur_patterns) < 20:
        global_patterns = [p for p in patterns if p.get("jurisdiction") == "GLOBAL" and p.get("success")]
        if global_patterns:
            sections.append("## GLOBAL METHODS (work across jurisdictions)\n\n")
            for p in global_patterns[:5]:
                source = p.get("source_used", "")
                method = p.get("method", "")
                desc = p.get("description", "")[:100]
                sections.append(f"- **{method}** via {source}: {desc}\n")
            sections.append("\n")

    # 5. Source friction summary
    sections.append("## SOURCE ACCESS LEGEND\n\n")
    sections.append("🟢 **open**: Free, no registration required\n")
    sections.append("🟡 **restricted**: Requires registration or local access\n")
    sections.append("🟠 **paywalled**: Requires subscription/payment\n")
    sections.append("🔴 **impossible**: Not publicly accessible\n\n")

    return "".join(sections)


def get_disambiguator_context(
    entity_name: str,
    collision_type: str,
    jurisdictions: List[str] = None
) -> str:
    """
    Build context for Disambiguator agent.

    Includes:
    - Common disambiguation patterns
    - Jurisdiction-specific identity markers
    """
    if not MINED_AVAILABLE:
        return ""

    mi = get_mined_intelligence()
    sections = []

    sections.append("## DISAMBIGUATION INTELLIGENCE\n\n")

    # Get jurisdiction-specific identity markers
    if jurisdictions:
        sections.append("**Key identity markers by jurisdiction**:\n\n")
        for jur in jurisdictions[:3]:
            jur_info = mi.get_jurisdiction_info(jur)
            if jur_info and jur_info.get("identity_markers"):
                markers = jur_info["identity_markers"]
                sections.append(f"- **{jur}**: {', '.join(markers[:4])}\n")

    sections.append("\n**Disambiguation approach**:\n")
    sections.append("1. Look for unique identifiers (ID numbers, birthdates)\n")
    sections.append("2. Cross-reference across jurisdictions\n")
    sections.append("3. Use corporate connections as distinguishers\n")
    sections.append("4. Check media for biographical details\n\n")

    return "".join(sections)


# =============================================================================
# PROMPT ENRICHMENT FUNCTIONS
# =============================================================================

def enrich_prompt(base_prompt: str, context: str) -> str:
    """
    Safely add mined context to a base prompt.
    """
    if not context:
        return base_prompt

    return f"""{base_prompt}

# MINED INTELLIGENCE CONTEXT

The following insights are derived from 636,000+ lines of mined investigation patterns.
Use this intelligence to make better decisions.

{context}
"""


def build_enriched_io_executor_prompt(
    base_prompt: str,
    jurisdiction: str,
    action_types: List[str] = None
) -> str:
    """Build complete IO Executor prompt with mined intelligence."""
    context = get_io_executor_context(jurisdiction, action_types)
    return enrich_prompt(base_prompt, context)


def build_enriched_writer_prompt(
    base_prompt: str,
    section_type: str,
    jurisdiction: str = None
) -> str:
    """Build complete Writer prompt with mined intelligence."""
    context = get_writer_context(section_type, jurisdiction)
    return enrich_prompt(base_prompt, context)


def build_enriched_orchestrator_prompt(
    base_prompt: str,
    entity: str,
    entity_type: str,
    jurisdiction: str,
    found_red_flags: List[str] = None,
    investigation_goal: str = None
) -> str:
    """Build complete Orchestrator prompt with mined intelligence."""
    context = get_orchestrator_context(entity, entity_type, jurisdiction, found_red_flags)

    # Add rich methodology if goal specified
    if investigation_goal:
        methodology = get_methodology_context(investigation_goal, jurisdiction, entity_type)
        context += "\n" + methodology

    return enrich_prompt(base_prompt, context)


def build_methodology_prompt(
    base_prompt: str,
    investigation_goal: str,
    jurisdiction: str,
    entity_type: str = "company"
) -> str:
    """Build prompt focused on methodology advice."""
    context = get_methodology_context(investigation_goal, jurisdiction, entity_type)
    return enrich_prompt(base_prompt, context)
