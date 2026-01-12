#!/usr/bin/env python3
"""
Extract EDITH templates and writing styles from mined files.

Moves 4,568 section templates and 1,245 writing styles to EDITH skill directory.
"""

import json
import shutil
from pathlib import Path
from datetime import datetime
from collections import defaultdict

MATRIX_DIR = Path(__file__).parent.parent
MINED_DIR = MATRIX_DIR.parent / "matrix_backup_20251125" / "mined"
EDITH_DIR = Path.home() / ".claude" / "skills" / "edith-templates"


def extract_templates():
    """Extract and organize EDITH templates."""

    # Ensure EDITH directories exist
    templates_dir = EDITH_DIR / "mined"
    templates_dir.mkdir(parents=True, exist_ok=True)

    stats = {
        "section_templates": 0,
        "writing_styles": 0,
        "section_types": defaultdict(int),
    }

    # Load and process section templates
    templates_file = MINED_DIR / "mined_section_templates.json"
    print(f"Loading {templates_file}...")
    with open(templates_file) as f:
        templates_data = json.load(f)

    templates = templates_data.get("templates", [])
    print(f"  Found {len(templates)} section templates")

    # Group templates by section_type
    by_type = defaultdict(list)
    for t in templates:
        section_type = t.get("section_type", "unknown")
        by_type[section_type].append(t)
        stats["section_types"][section_type] += 1

    # Write grouped templates
    section_templates_output = {
        "meta": {
            "description": "Mined section templates by type",
            "source": "report_library_ingestion",
            "extracted_at": datetime.now().isoformat(),
            "total_templates": len(templates),
            "unique_types": len(by_type),
        },
        "templates_by_type": {
            stype: {
                "count": len(items),
                "templates": items,
            }
            for stype, items in sorted(by_type.items())
        },
    }

    output_file = templates_dir / "section_templates.json"
    with open(output_file, "w") as f:
        json.dump(section_templates_output, f, indent=2, ensure_ascii=False)
    print(f"  Written: {output_file}")
    stats["section_templates"] = len(templates)

    # Load and process writing styles
    styles_file = MINED_DIR / "mined_writing_styles.json"
    print(f"\nLoading {styles_file}...")
    with open(styles_file) as f:
        styles_data = json.load(f)

    styles = styles_data.get("styles", [])
    print(f"  Found {len(styles)} writing styles")

    # Extract common patterns across styles
    voice_patterns = defaultdict(int)
    attribution_patterns = defaultdict(int)
    certainty_patterns = []

    for style in styles:
        vt = style.get("voice_and_tone", {})
        if vt.get("person"):
            voice_patterns[f"{vt['person']}_{vt.get('formality', 'unknown')}"] += 1

        ar = style.get("attribution_rules", {})
        if ar.get("style"):
            attribution_patterns[ar["style"]] += 1

        cc = style.get("certainty_calibration", {})
        if cc.get("verified_facts_pattern"):
            certainty_patterns.append(cc)

    # Write organized styles
    writing_styles_output = {
        "meta": {
            "description": "Mined writing style patterns",
            "source": "report_library_ingestion",
            "extracted_at": datetime.now().isoformat(),
            "total_styles": len(styles),
        },
        "pattern_summary": {
            "voice_patterns": dict(voice_patterns),
            "attribution_patterns": dict(attribution_patterns),
        },
        "styles": styles,
        "certainty_calibration_examples": certainty_patterns[:20],  # Sample
    }

    output_file = templates_dir / "writing_styles.json"
    with open(output_file, "w") as f:
        json.dump(writing_styles_output, f, indent=2, ensure_ascii=False)
    print(f"  Written: {output_file}")
    stats["writing_styles"] = len(styles)

    # Create a summary file for quick reference
    summary = {
        "meta": {
            "description": "Summary of mined EDITH templates",
            "extracted_at": datetime.now().isoformat(),
        },
        "section_templates": {
            "total": stats["section_templates"],
            "top_types": dict(
                sorted(stats["section_types"].items(), key=lambda x: -x[1])[:20]
            ),
        },
        "writing_styles": {
            "total": stats["writing_styles"],
            "voice_patterns": dict(voice_patterns),
            "attribution_patterns": dict(attribution_patterns),
        },
    }

    summary_file = templates_dir / "SUMMARY.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"  Written: {summary_file}")

    # Print stats
    print(f"\n=== EXTRACTION STATS ===")
    print(f"Section templates: {stats['section_templates']}")
    print(f"Writing styles: {stats['writing_styles']}")

    print(f"\nTop 10 section types:")
    for stype, count in sorted(stats["section_types"].items(), key=lambda x: -x[1])[:10]:
        print(f"  {stype}: {count}")

    print(f"\nVoice patterns:")
    for pattern, count in sorted(voice_patterns.items(), key=lambda x: -x[1]):
        print(f"  {pattern}: {count}")


if __name__ == "__main__":
    extract_templates()
