#!/usr/bin/env python3
"""
Merge duplicate source files according to the plan.

Merges:
    multimedia.json → media.json
    asset_tracing.json → assets.json
    library.json → libraries.json
    miscellaneous.json → misc.json
    uncategorized.json → misc.json
    tracking.json → osint.json
"""

import json
from pathlib import Path
from datetime import datetime
import shutil

SOURCES_DIR = Path(__file__).parent / "sources"

# Define merges: (from_file, to_file)
MERGES = [
    ("multimedia.json", "media.json"),
    ("asset_tracing.json", "assets.json"),
    ("library.json", "libraries.json"),
    ("miscellaneous.json", "misc.json"),
    ("uncategorized.json", "misc.json"),
    ("tracking.json", "osint.json"),
]


def load_sources(filepath: Path) -> dict:
    """Load a source file."""
    if not filepath.exists():
        return {"meta": {}, "sources": []}
    with open(filepath) as f:
        data = json.load(f)
    # Ensure required keys exist
    if "meta" not in data:
        data["meta"] = {}
    if "sources" not in data:
        data["sources"] = []
    return data


def merge_sources(target: dict, source: dict) -> int:
    """Merge source into target, avoiding duplicates. Returns count of new sources."""
    existing_ids = {s.get("id") for s in target.get("sources", [])}
    new_count = 0

    for src in source.get("sources", []):
        src_id = src.get("id")
        if src_id and src_id not in existing_ids:
            target.get("sources", []).append(src)
            existing_ids.add(src_id)
            new_count += 1

    return new_count


def main():
    print("Source File Merge Utility")
    print("=" * 60)

    for from_file, to_file in MERGES:
        from_path = SOURCES_DIR / from_file
        to_path = SOURCES_DIR / to_file

        if not from_path.exists():
            print(f"\nSkipping {from_file} (not found)")
            continue

        print(f"\nMerging {from_file} → {to_file}")

        # Load both files
        source_data = load_sources(from_path)
        target_data = load_sources(to_path)

        source_count = len(source_data.get("sources", []))
        target_count_before = len(target_data.get("sources", []))

        # Merge
        new_count = merge_sources(target_data, source_data)
        target_count_after = len(target_data.get("sources", []))

        print(f"  Source file: {source_count} sources")
        print(f"  Target before: {target_count_before} sources")
        print(f"  Added: {new_count} new sources")
        print(f"  Target after: {target_count_after} sources")

        # Update metadata
        target_data["meta"]["count"] = target_count_after
        target_data["meta"]["merged_at"] = datetime.utcnow().isoformat()
        target_data["meta"]["merged_from"] = target_data["meta"].get("merged_from", [])
        if from_file not in target_data["meta"]["merged_from"]:
            target_data["meta"]["merged_from"].append(from_file)

        # Save merged file
        with open(to_path, "w") as f:
            json.dump(target_data, f, indent=2)
        print(f"  Saved: {to_path}")

        # Archive the source file
        archive_path = from_path.with_suffix(".merged.json.bak")
        shutil.move(from_path, archive_path)
        print(f"  Archived: {from_file} → {archive_path.name}")

    print("\n" + "=" * 60)
    print("Merge complete!")


if __name__ == "__main__":
    main()
