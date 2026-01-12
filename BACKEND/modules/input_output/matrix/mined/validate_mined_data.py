#!/usr/bin/env python3
"""
Mined Intelligence Data Validator

CRITICAL: These files are NOT generated/cache data. They are core intelligence
containing 636K+ lines of investigation patterns mined from years of work.

This script validates that all required mined data files exist.
Run it:
  - On startup
  - Before merging branches
  - In CI/CD pipelines

If files are missing, restore from backup:
  cp input_output/matrix_backup_20251125/mined/*.json input_output/matrix/mined/
"""

import sys
from pathlib import Path

# Required mined intelligence files - DO NOT REMOVE FROM THIS LIST
REQUIRED_FILES = [
    "mined_methodology.json",      # 6,126 investigation patterns
    "mined_arbitrage.json",        # 859 cross-jurisdictional shortcuts
    "mined_dead_ends.json",        # Known failing queries by jurisdiction
    "mined_routes.json",           # Working data routes
    "mined_section_templates.json", # 4,568 report section templates
    "mined_writing_styles.json",   # Voice and attribution patterns
    "mined_jurisdictions.json",    # Jurisdiction metadata
    "mined_genres.json",           # Report genre definitions
    "mined_sectors.json",          # Industry sector patterns
    "mined_registry_domains.json", # Registry domain mappings
    "aggregated_sectors.json",     # Consolidated sector data
]

# Optional files (nice to have, won't fail validation)
OPTIONAL_FILES = [
    "generated_chains.json",       # Auto-generated from mined_methodology
    "methodology_mappings.json",   # IO Matrix code mappings
]

MINED_DIR = Path(__file__).parent
BACKUP_DIR = MINED_DIR.parent.parent / "matrix_backup_20251125" / "mined"


def validate(auto_restore: bool = False) -> bool:
    """
    Validate that all required mined data files exist.

    Args:
        auto_restore: If True, attempt to restore missing files from backup

    Returns:
        True if all required files exist (or were restored), False otherwise
    """
    missing = []
    restored = []

    for filename in REQUIRED_FILES:
        filepath = MINED_DIR / filename
        if not filepath.exists():
            if auto_restore:
                backup_path = BACKUP_DIR / filename
                if backup_path.exists():
                    import shutil
                    shutil.copy2(backup_path, filepath)
                    restored.append(filename)
                    print(f"  [RESTORED] {filename}")
                else:
                    missing.append(filename)
                    print(f"  [MISSING]  {filename} (no backup available)")
            else:
                missing.append(filename)
                print(f"  [MISSING]  {filename}")
        else:
            size_kb = filepath.stat().st_size / 1024
            print(f"  [OK]       {filename} ({size_kb:.0f} KB)")

    if restored:
        print(f"\n  Restored {len(restored)} files from backup")

    if missing:
        print(f"\n  ERROR: {len(missing)} required files missing!")
        print(f"\n  To restore from backup:")
        print(f"    cp {BACKUP_DIR}/*.json {MINED_DIR}/")
        return False

    return True


def main():
    print("\n" + "=" * 60)
    print("  MINED INTELLIGENCE DATA VALIDATION")
    print("=" * 60)
    print(f"\n  Directory: {MINED_DIR}")
    print(f"  Backup:    {BACKUP_DIR}")
    print(f"\n  Checking {len(REQUIRED_FILES)} required files...\n")

    # Check for --restore flag
    auto_restore = "--restore" in sys.argv

    if validate(auto_restore=auto_restore):
        print("\n  " + "-" * 40)
        print("  ALL MINED DATA PRESENT")
        print("  " + "-" * 40 + "\n")
        return 0
    else:
        print("\n  " + "-" * 40)
        print("  VALIDATION FAILED - MINED DATA MISSING")
        print("  " + "-" * 40)
        print("\n  Run with --restore to auto-restore from backup:")
        print(f"    python {__file__} --restore\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
