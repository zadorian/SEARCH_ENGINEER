"""
SASTRE Template Loader - Loads EDITH templates for structured investigations

Template Mode: DD, asset trace, KYC, etc. → loads jurisdiction/section/genre templates
Free-range Mode: Open investigation → no templates, but Sastre writing style applies

Templates are loaded from:
    /data/EDITH/templates/
    ~/.claude/skills/edith-templates/
    OR
    /Users/attic/01. DRILL_SEARCH/drill-search-app/.claude/skills/edith-templates/
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from functools import lru_cache

# Template paths (try multiple locations)
_REPO_ROOT = Path(__file__).resolve().parent.parent
_REPO_TEMPLATES = _REPO_ROOT / "EDITH" / "templates"
_ENV_TEMPLATE_ROOTS = [
    os.getenv("EDITH_TEMPLATES_DIR"),
    os.getenv("EDITH_TEMPLATES_ROOT"),
    os.getenv("SASTRE_TEMPLATES_DIR"),
]

TEMPLATE_PATHS = [
    *(Path(p).expanduser() for p in _ENV_TEMPLATE_ROOTS if p),
    _REPO_TEMPLATES,
    Path("/Users/attic/01. DRILL_SEARCH/drill-search-app/.claude/skills/edith-templates"),
    Path.home() / ".claude/skills/edith-templates",
]


def _find_templates_root() -> Optional[Path]:
    """Find the edith-templates folder."""
    for p in TEMPLATE_PATHS:
        if p.exists():
            return p
    return None


TEMPLATES_ROOT = _find_templates_root()


# =============================================================================
# WRITING STYLE (always loaded, applies to all modes)
# =============================================================================

@lru_cache(maxsize=1)
def get_writing_style() -> str:
    """Get Sastre writing style guide. Always applies."""
    if not TEMPLATES_ROOT:
        return _DEFAULT_WRITING_STYLE

    # Try library first
    style_path = TEMPLATES_ROOT / "library" / "writing_style_guide.json"
    if style_path.exists():
        with open(style_path) as f:
            data = json.load(f)
            return json.dumps(data, indent=2)

    # Try CERTAINTY_CALIBRATION
    cert_path = TEMPLATES_ROOT / "library" / "CERTAINTY_CALIBRATION.skill.md"
    if cert_path.exists():
        with open(cert_path) as f:
            return f.read()

    return _DEFAULT_WRITING_STYLE


@lru_cache(maxsize=1)
def get_methodology() -> str:
    """Get research methodology guide."""
    if not TEMPLATES_ROOT:
        return ""

    path = TEMPLATES_ROOT / "library" / "METHODOLOGY.skill.md"
    if path.exists():
        with open(path) as f:
            return f.read()
    return ""


@lru_cache(maxsize=1)
def get_disclaimers() -> str:
    """Get standard disclaimers."""
    if not TEMPLATES_ROOT:
        return ""

    path = TEMPLATES_ROOT / "library" / "DISCLAIMERS.skill.md"
    if path.exists():
        with open(path) as f:
            return f.read()
    return ""


# =============================================================================
# JURISDICTIONS (loaded on demand for template mode)
# =============================================================================

# Map 2-letter codes to full country names
COUNTRY_CODE_MAP = {
    "HU": "HUNGARY", "UK": "UNITED_KINGDOM", "GB": "UNITED_KINGDOM",
    "US": "UNITED_STATES", "DE": "GERMANY", "FR": "FRANCE",
    "CY": "CYPRUS", "BVI": "BVI", "LU": "LUXEMBOURG",
    "CH": "SWITZERLAND", "AT": "AUSTRIA", "NL": "NETHERLANDS",
    "BE": "BELGIUM", "ES": "SPAIN", "IT": "ITALY",
    "PL": "POLAND", "CZ": "CZECH_REPUBLIC", "SK": "SLOVAKIA",
    "RO": "ROMANIA", "BG": "BULGARIA", "HR": "CROATIA",
    "SI": "SLOVENIA", "RS": "SERBIA", "UA": "UKRAINE",
    "RU": "RUSSIA", "CN": "CHINA", "JP": "JAPAN",
    "KR": "SOUTH_KOREA", "IN": "INDIA", "AU": "AUSTRALIA",
    "NZ": "NEW_ZEALAND", "CA": "CANADA", "MX": "MEXICO",
    "BR": "BRAZIL", "AR": "ARGENTINA", "CL": "CHILE",
    "AE": "UAE", "SA": "SAUDI_ARABIA", "IL": "ISRAEL",
    "ZA": "SOUTH_AFRICA", "NG": "NIGERIA", "KE": "KENYA",
    "SG": "SINGAPORE", "HK": "HONG_KONG", "MY": "MALAYSIA",
    "ID": "INDONESIA", "TH": "THAILAND", "VN": "VIETNAM",
    "PH": "PHILIPPINES", "TW": "TAIWAN",
}


@lru_cache(maxsize=300)
def get_jurisdiction(code: str) -> Optional[Dict[str, Any]]:
    """
    Get jurisdiction template by code (UK, HU, BVI, etc.) or full name.

    Returns:
        Dict with 'content' (full template text) and metadata
    """
    if not TEMPLATES_ROOT:
        return None

    jur_path = TEMPLATES_ROOT / "jurisdictions"
    if not jur_path.exists():
        return None

    code_upper = code.upper().replace(".SKILL", "").replace(" ", "_")

    # Try various filename patterns
    patterns = [
        f"{code_upper}.skill.md",
        f"{code_upper.lower()}.skill.md",
    ]

    # Also try mapped full name
    if code_upper in COUNTRY_CODE_MAP:
        full_name = COUNTRY_CODE_MAP[code_upper]
        patterns.insert(0, f"{full_name}.skill.md")

    for pattern in patterns:
        file_path = jur_path / pattern
        if file_path.exists():
            with open(file_path) as f:
                content = f.read()
            return {
                "code": code_upper,
                "content": content,
                "path": str(file_path)
            }

    # Last resort: search all files for matching code
    for f in jur_path.glob("*.skill.md"):
        if code_upper in f.stem.upper():
            with open(f) as fp:
                content = fp.read()
            return {
                "code": code_upper,
                "content": content,
                "path": str(f)
            }

    return None


def list_jurisdictions() -> List[str]:
    """List all available jurisdiction codes."""
    if not TEMPLATES_ROOT:
        return []

    jur_path = TEMPLATES_ROOT / "jurisdictions"
    if not jur_path.exists():
        return []

    codes = []
    for f in jur_path.glob("*.skill.md"):
        code = f.stem.replace(".skill", "").upper()
        codes.append(code)

    return sorted(set(codes))


# =============================================================================
# GENRES (investigation types)
# =============================================================================

TEMPLATE_GENRES = {
    # These trigger template mode
    "due_diligence", "dd", "person_dd", "company_dd", "enhanced_dd",
    "asset_trace", "asset_tracing",
    "kyc", "kyb", "aml",
    "pep_screening", "sanctions_screening",
    "litigation_support", "fraud_investigation",
    "vendor_dd", "joint_venture_dd",
    "market_intelligence", "competitive_intelligence",
    "background_check", "pre_employment",
}


def is_template_genre(genre: str) -> bool:
    """Check if this genre requires template structure."""
    return genre.lower().replace("-", "_").replace(" ", "_") in TEMPLATE_GENRES


@lru_cache(maxsize=50)
def get_genre(name: str) -> Optional[Dict[str, Any]]:
    """Get genre template by name."""
    if not TEMPLATES_ROOT:
        return None

    genre_path = TEMPLATES_ROOT / "genres"
    if not genre_path.exists():
        return None

    # Normalize name
    name_normalized = name.upper().replace("-", "_").replace(" ", "_")

    for f in genre_path.glob("*.skill.md"):
        if f.stem.replace(".skill", "").upper() == name_normalized:
            with open(f) as fp:
                content = fp.read()
            return {
                "name": name_normalized,
                "content": content,
                "path": str(f)
            }

    return None


def list_genres() -> List[str]:
    """List all available genre names."""
    if not TEMPLATES_ROOT:
        return []

    genre_path = TEMPLATES_ROOT / "genres"
    if not genre_path.exists():
        return []

    return sorted([f.stem.replace(".skill", "").upper() for f in genre_path.glob("*.skill.md")])


# =============================================================================
# SECTIONS (reusable report blocks)
# =============================================================================

@lru_cache(maxsize=100)
def get_section(name: str, category: str = None) -> Optional[Dict[str, Any]]:
    """
    Get section template by name.

    Args:
        name: Section name (e.g., CORPORATE_AFFILIATIONS)
        category: Optional subfolder (e.g., 'universal', 'person', 'company')
    """
    if not TEMPLATES_ROOT:
        return None

    sections_path = TEMPLATES_ROOT / "sections"
    scaffolds_path = TEMPLATES_ROOT / "scaffolds"

    name_normalized = name.upper().replace("-", "_").replace(" ", "_")

    # Search order: sections root, sections subfolders, scaffolds
    search_paths = []

    if category:
        search_paths.append(sections_path / category)
        search_paths.append(scaffolds_path / category)

    search_paths.extend([
        sections_path,
        sections_path / "universal",
        sections_path / "person",
        sections_path / "company",
        scaffolds_path / "universal",
        scaffolds_path / "person",
        scaffolds_path / "company",
    ])

    for search_path in search_paths:
        if not search_path.exists():
            continue

        # Try .skill.md and .scaffold.md
        for ext in [".skill.md", ".scaffold.md", ".md"]:
            file_path = search_path / f"{name_normalized}{ext}"
            if file_path.exists():
                with open(file_path) as f:
                    content = f.read()
                return {
                    "name": name_normalized,
                    "category": search_path.name,
                    "content": content,
                    "path": str(file_path)
                }

    return None


def list_sections() -> List[str]:
    """List all available section names."""
    if not TEMPLATES_ROOT:
        return []

    sections = set()

    for folder in ["sections", "scaffolds"]:
        folder_path = TEMPLATES_ROOT / folder
        if folder_path.exists():
            for f in folder_path.glob("**/*.skill.md"):
                sections.add(f.stem.replace(".skill", "").upper())
            for f in folder_path.glob("**/*.scaffold.md"):
                sections.add(f.stem.replace(".scaffold", "").upper())

    return sorted(sections)


# =============================================================================
# TEMPLATE COMPOSITION
# =============================================================================

def compose_report_template(
    genre: str,
    jurisdiction: Optional[str] = None,
    entity_type: str = "company"
) -> Dict[str, Any]:
    """
    Compose a full report template from genre + jurisdiction + sections.

    Returns:
        Dict with:
            - genre_template: Genre-specific guidance
            - jurisdiction_template: Country-specific sources/registries
            - sections: List of section templates to use
            - writing_style: Sastre writing guide
    """
    result = {
        "is_template_mode": is_template_genre(genre),
        "genre": genre,
        "jurisdiction": jurisdiction,
        "entity_type": entity_type,
        "writing_style": get_writing_style(),
        "methodology": get_methodology(),
    }

    if not result["is_template_mode"]:
        # Free-range mode - no templates, just writing style
        result["sections"] = []
        result["genre_template"] = None
        result["jurisdiction_template"] = None
        return result

    # Template mode - load everything
    result["genre_template"] = get_genre(genre)

    if jurisdiction:
        result["jurisdiction_template"] = get_jurisdiction(jurisdiction)

    # Determine sections based on entity type and genre
    if entity_type == "person":
        section_names = [
            "EXECUTIVE_SUMMARY",
            "OVERVIEW",
            "CAREER_EDUCATION",
            "CORPORATE_AFFILIATIONS",
            "MEDIA_REPUTATION",
            "LITIGATION",
            "REGULATORY",
            "ADVERSE_MEDIA",
            "PEP_STATUS",
            "SANCTIONS_WATCHLISTS",
            "MATTERS_OF_NOTE",
            "RESEARCH_LIMITATIONS",
        ]
    else:  # company
        section_names = [
            "EXECUTIVE_SUMMARY",
            "OVERVIEW",
            "CORPORATE_AFFILIATIONS",
            "KEY_RELATIONSHIPS",
            "SOURCE_OF_WEALTH",
            "REGULATORY",
            "LITIGATION",
            "BANKRUPTCY_INSOLVENCY",
            "ADVERSE_MEDIA",
            "SANCTIONS_WATCHLISTS",
            "MATTERS_OF_NOTE",
            "RESEARCH_LIMITATIONS",
            "RESEARCH_METHODOLOGY",
        ]

    result["sections"] = []
    for name in section_names:
        section = get_section(name, category="universal")
        if section:
            result["sections"].append(section)

    return result


# =============================================================================
# DEFAULT FALLBACK STYLE
# =============================================================================

_DEFAULT_WRITING_STYLE = """
# Sastre Professional Writing Style

## Voice & Tone
- Third person for factual statements
- First plural ("we") for investigative actions
- Professional, analytical stance
- Neutral observer with investigative rigor

## Attribution
- Footnoted with superscript numbers [^1], [^2]
- Every factual claim must have a source

## Certainty Calibration

VERIFIED FACTS (Registry, official filings):
- "Smith was appointed director on 15 January 2020."
- "According to the corporate registry..."

UNVERIFIED CLAIMS (Media, HUMINT):
- "According to media reports..."
- "Sources indicate..."

INFERENCES (Analyst conclusions):
- "This suggests..."
- "Based on available evidence..."
- "This could not be independently verified."

## Entity Formatting
- Bold every person and company on FIRST mention only
- Full legal name in quotes on first mention
- Jurisdiction in parentheses

## Date Format
- DD Month YYYY (e.g., "17 December 2009")
"""


# =============================================================================
# QUICK ACCESS
# =============================================================================

def get_template_context(
    query: str = None,
    genre: str = None,
    jurisdiction: str = None,
    entity_type: str = None
) -> Dict[str, Any]:
    """
    Get full template context for an investigation.

    Auto-detects genre/jurisdiction from query if not specified.
    """
    # Auto-detect from query if needed
    if query and not genre:
        query_lower = query.lower()
        if any(x in query_lower for x in ["dd", "due diligence", "diligence"]):
            genre = "due_diligence"
        elif any(x in query_lower for x in ["asset trace", "asset tracing"]):
            genre = "asset_trace"
        elif any(x in query_lower for x in ["kyc", "know your customer"]):
            genre = "kyc"
        elif any(x in query_lower for x in ["background", "vetting"]):
            genre = "background_check"

    if query and not jurisdiction:
        query_lower = query.lower()
        # Simple jurisdiction detection
        jur_map = {
            "uk": ["uk", "united kingdom", "britain", "england", "companies house"],
            "us": ["usa", "united states", "delaware", "nevada"],
            "hu": ["hungary", "hungarian", "budapest"],
            "de": ["germany", "german", "gmbh"],
            "cy": ["cyprus", "cypriot"],
            "bvi": ["bvi", "british virgin"],
        }
        for code, terms in jur_map.items():
            if any(term in query_lower for term in terms):
                jurisdiction = code.upper()
                break

    if query and not entity_type:
        query_lower = query.lower()
        if any(x in query_lower for x in ["person", "individual", "mr ", "ms ", "dr "]):
            entity_type = "person"
        else:
            entity_type = "company"

    return compose_report_template(
        genre=genre or "open_investigation",
        jurisdiction=jurisdiction,
        entity_type=entity_type or "company"
    )
