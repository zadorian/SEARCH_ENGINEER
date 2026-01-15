#!/usr/bin/env python3
"""
Build Comprehensive Golden Lists from ALL Mined Report Data.

Extracts vocabulary from:
1. mined_section_templates.json - Investigation section types (ownership_analysis, asset_trace, etc.)
2. mined_genres.json - Report genres (due_diligence, corporate_intelligence, etc.)
3. aggregated_sectors.json - 693 sectors with red flags
4. mined_methodology.json - Research methods (corporate_registry_search, humint, etc.)
5. mined_routes.json - Input/output type mappings

Creates golden_lists_comprehensive.json with:
- themes: Industry sectors + Investigation categories
- phenomena: Events + Report genres
- red_flags: Sector-specific risk indicators
- methodologies: Research approaches
"""

import json
import logging
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
MINED_DIR = PROJECT_ROOT / "input_output" / "matrix_backup_20251125" / "mined"
OUTPUT_DIR = PROJECT_ROOT / "input_output" / "matrix"
EXISTING_GOLDEN = PROJECT_ROOT / "input_output" / "matrix" / "golden_lists.json"


def load_json(path: Path) -> dict:
    """Load JSON file safely."""
    if not path.exists():
        logger.warning(f"File not found: {path}")
        return {}
    with open(path, 'r') as f:
        return json.load(f)


def extract_section_types(mined_templates: dict) -> Dict[str, Dict]:
    """
    Extract investigation themes from mined_section_templates.json.

    Each section_type becomes a theme with variations from typical_content and key_phrases.
    """
    themes = {}
    templates = mined_templates.get('templates', [])

    # Group by section_type
    by_type = defaultdict(list)
    for t in templates:
        section_type = t.get('section_type', '')
        if section_type:
            by_type[section_type].append(t)

    logger.info(f"Found {len(by_type)} unique section types from {len(templates)} templates")

    # Only include types with >= 5 occurrences (statistically significant)
    MIN_COUNT = 5

    for section_type, instances in by_type.items():
        if len(instances) < MIN_COUNT:
            continue

        # Collect all keywords
        variations = set()

        for t in instances:
            # Add section title variations
            title = t.get('section_title', '')
            if title and len(title) > 3:
                variations.add(title.lower())

            # Add typical content keywords
            for content in t.get('typical_content', []):
                if content and len(content) > 3:
                    variations.add(content.lower())

        # Clean and dedupe
        clean_variations = []
        seen = set()
        for v in sorted(variations):
            v_clean = v.strip().replace('_', ' ')
            if v_clean and v_clean not in seen and len(v_clean) > 3:
                seen.add(v_clean)
                clean_variations.append(v_clean)

        if len(clean_variations) >= 3:  # Need at least 3 variations
            # Create canonical name
            canonical = section_type.replace('_', ' ').title()

            themes[f"inv_{section_type}"] = {
                "id": f"inv_{section_type}",
                "canonical": canonical,
                "variations": clean_variations[:30],  # Cap at 30 variations
                "source": "mined_section_templates",
                "instance_count": len(instances)
            }

    return themes


def extract_report_genres(mined_genres: dict) -> Dict[str, Dict]:
    """
    Extract phenomena from mined_genres.json.

    Report genres (due_diligence, asset_trace, etc.) become phenomena.
    """
    phenomena = {}
    genres = mined_genres.get('genres', [])

    # Count genres
    genre_counts = defaultdict(lambda: {"count": 0, "purposes": set()})

    for g in genres:
        primary = g.get('primary_type', '')
        if primary:
            genre_counts[primary]["count"] += 1
            for p in g.get('purpose_indicators', []):
                genre_counts[primary]["purposes"].add(p.lower())

        # Also count secondary types
        for secondary in g.get('secondary_types', []):
            genre_counts[secondary]["count"] += 1
            for p in g.get('purpose_indicators', []):
                genre_counts[secondary]["purposes"].add(p.lower())

    logger.info(f"Found {len(genre_counts)} unique report genres from {len(genres)} reports")

    MIN_COUNT = 3

    for genre, data in genre_counts.items():
        if data["count"] < MIN_COUNT:
            continue

        # Build variations from genre name + purposes
        variations = [genre.replace('_', ' ')]
        variations.extend(list(data["purposes"])[:20])

        canonical = genre.replace('_', ' ').title()

        phenomena[f"genre_{genre}"] = {
            "id": f"genre_{genre}",
            "canonical": canonical,
            "variations": variations,
            "source": "mined_genres",
            "report_count": data["count"]
        }

    return phenomena


def extract_red_flags(aggregated_sectors: dict) -> Dict[str, Dict]:
    """
    Extract red flag themes from aggregated_sectors.json.

    Groups red flags into semantic clusters for tripwire matching.
    """
    themes = {}
    sectors = aggregated_sectors.get('sectors', {})

    # Collect ALL red flags
    all_flags = defaultdict(set)  # category -> flags

    # Define red flag categories
    RF_CATEGORIES = {
        "money_laundering": ["money laundering", "aml", "laundering", "smurfing", "layering", "placement", "integration"],
        "beneficial_ownership": ["beneficial owner", "ubo", "nominee", "proxy", "hidden ownership", "opaque structure"],
        "offshore": ["offshore", "tax haven", "shell company", "brass plate", "letterbox", "bvi", "cayman", "panama"],
        "sanctions": ["sanction", "ofac", "sdn", "blacklist", "designated", "embargo", "asset freeze"],
        "pep": ["pep", "politically exposed", "government official", "political connection", "state capture"],
        "fraud": ["fraud", "embezzlement", "misappropriation", "ponzi", "scam", "deception"],
        "corruption": ["corruption", "bribery", "kickback", "illicit payment", "facilitation payment"],
        "conflict_interest": ["conflict of interest", "related party", "self-dealing", "insider"],
        "regulatory": ["regulatory breach", "violation", "non-compliance", "enforcement", "fine", "penalty"],
        "reputational": ["reputational risk", "adverse media", "negative press", "controversy", "scandal"],
    }

    for sector_name, sector_data in sectors.items():
        for rf in sector_data.get('red_flags', []):
            rf_lower = rf.lower()

            # Categorize each red flag
            for category, keywords in RF_CATEGORIES.items():
                if any(kw in rf_lower for kw in keywords):
                    all_flags[category].add(rf_lower)
                    break
            else:
                # Uncategorized - add to general
                all_flags["general_risk"].add(rf_lower)

    logger.info(f"Categorized {sum(len(v) for v in all_flags.values())} red flags into {len(all_flags)} categories")

    # Build themes from categories
    for category, flags in all_flags.items():
        if len(flags) < 5:
            continue

        canonical = category.replace('_', ' ').title()
        variations = sorted(list(flags))[:50]  # Cap at 50

        themes[f"rf_{category}"] = {
            "id": f"rf_{category}",
            "canonical": f"Red Flag: {canonical}",
            "variations": variations,
            "source": "aggregated_sectors",
            "flag_count": len(flags)
        }

    return themes


def extract_methodologies(mined_methodology: dict) -> Dict[str, Dict]:
    """
    Extract research methodology themes from mined_methodology.json.
    """
    themes = {}
    patterns = mined_methodology.get('patterns', [])

    # Group by method
    by_method = defaultdict(lambda: {"descriptions": [], "sources": set(), "jurisdictions": set()})

    for p in patterns:
        method = p.get('method', '')
        if method:
            by_method[method]["descriptions"].append(p.get('description', ''))
            by_method[method]["sources"].add(p.get('source_used', ''))
            by_method[method]["jurisdictions"].add(p.get('jurisdiction', ''))

    logger.info(f"Found {len(by_method)} unique research methods from {len(patterns)} patterns")

    for method, data in by_method.items():
        if len(data["descriptions"]) < 3:
            continue

        # Build variations
        variations = [method.replace('_', ' ')]

        # Add unique description fragments
        for desc in data["descriptions"][:10]:
            if desc and len(desc) > 10:
                # Extract key phrases
                variations.append(desc.lower()[:100])

        # Add source types
        for src in data["sources"]:
            if src and len(src) > 3:
                variations.append(src.lower())

        canonical = method.replace('_', ' ').title()

        themes[f"method_{method}"] = {
            "id": f"method_{method}",
            "canonical": f"Method: {canonical}",
            "variations": list(set(variations))[:30],
            "source": "mined_methodology",
            "pattern_count": len(data["descriptions"])
        }

    return themes


def extract_output_types(mined_routes: dict) -> Set[str]:
    """Extract all output types from routes as potential tripwire targets."""
    output_types = set()

    for route in mined_routes.get('routes', []):
        for ot in route.get('output_types', []):
            output_types.add(ot.lower().replace('_', ' '))

    return output_types


def merge_with_existing(existing: dict, new_themes: dict, new_phenomena: dict) -> dict:
    """
    Merge new extractions with existing golden_lists.json.

    Preserves existing themes/phenomena and adds new investigation-centric ones.
    """
    result = {
        "meta": {
            "version": "2.0.0",
            "description": "Comprehensive Golden Lists - Industry + Investigation themes from 1,230+ classified reports",
            "model": "intfloat/multilingual-e5-base",
            "dims": 768,
            "sources": [
                "golden_lists.json (original)",
                "mined_section_templates.json",
                "mined_genres.json",
                "aggregated_sectors.json",
                "mined_methodology.json",
                "mined_routes.json"
            ]
        },
        "themes": {
            "description": "Industry sectors + Investigation categories",
            "categories": []
        },
        "phenomena": {
            "description": "Events + Report genres",
            "categories": []
        },
        "red_flags": {
            "description": "Sector-specific risk indicators for tripwires",
            "categories": []
        },
        "methodologies": {
            "description": "Research approaches for matching report sections",
            "categories": []
        }
    }

    # Add existing themes
    for cat in existing.get('themes', {}).get('categories', []):
        cat['source'] = 'original_golden_lists'
        result['themes']['categories'].append(cat)

    # Add new investigation themes
    for theme_id, theme_data in new_themes.items():
        result['themes']['categories'].append(theme_data)

    # Add existing phenomena
    for cat in existing.get('phenomena', {}).get('categories', []):
        cat['source'] = 'original_golden_lists'
        result['phenomena']['categories'].append(cat)

    # Add new genre phenomena
    for phenom_id, phenom_data in new_phenomena.items():
        result['phenomena']['categories'].append(phenom_data)

    return result


def add_red_flags_and_methods(result: dict, red_flags: dict, methodologies: dict) -> dict:
    """Add red flag and methodology categories."""

    for rf_id, rf_data in red_flags.items():
        result['red_flags']['categories'].append(rf_data)

    for method_id, method_data in methodologies.items():
        result['methodologies']['categories'].append(method_data)

    return result


def main():
    """Main extraction pipeline."""
    logger.info("=" * 60)
    logger.info("Building Comprehensive Golden Lists from Mined Report Data")
    logger.info("=" * 60)

    # Load all source files
    logger.info("\n1. Loading source files...")

    mined_templates = load_json(MINED_DIR / "mined_section_templates.json")
    mined_genres = load_json(MINED_DIR / "mined_genres.json")
    aggregated_sectors = load_json(MINED_DIR / "aggregated_sectors.json")
    mined_methodology = load_json(MINED_DIR / "mined_methodology.json")
    mined_routes = load_json(MINED_DIR / "mined_routes.json")
    existing_golden = load_json(EXISTING_GOLDEN)

    # Extract from each source
    logger.info("\n2. Extracting investigation themes from section templates...")
    inv_themes = extract_section_types(mined_templates)
    logger.info(f"   Extracted {len(inv_themes)} investigation themes")

    logger.info("\n3. Extracting report genres as phenomena...")
    genre_phenomena = extract_report_genres(mined_genres)
    logger.info(f"   Extracted {len(genre_phenomena)} genre phenomena")

    logger.info("\n4. Extracting and categorizing red flags...")
    red_flags = extract_red_flags(aggregated_sectors)
    logger.info(f"   Extracted {len(red_flags)} red flag categories")

    logger.info("\n5. Extracting research methodologies...")
    methodologies = extract_methodologies(mined_methodology)
    logger.info(f"   Extracted {len(methodologies)} methodology themes")

    logger.info("\n6. Extracting output types from routes...")
    output_types = extract_output_types(mined_routes)
    logger.info(f"   Found {len(output_types)} unique output types")

    # Merge everything
    logger.info("\n7. Merging with existing golden_lists.json...")
    result = merge_with_existing(existing_golden, inv_themes, genre_phenomena)
    result = add_red_flags_and_methods(result, red_flags, methodologies)

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Themes:       {len(result['themes']['categories'])} categories")
    logger.info(f"Phenomena:    {len(result['phenomena']['categories'])} categories")
    logger.info(f"Red Flags:    {len(result['red_flags']['categories'])} categories")
    logger.info(f"Methodologies:{len(result['methodologies']['categories'])} categories")

    # Save
    output_path = OUTPUT_DIR / "golden_lists_comprehensive.json"
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    logger.info(f"\nSaved to: {output_path}")
    logger.info("=" * 60)

    return result


if __name__ == "__main__":
    main()
