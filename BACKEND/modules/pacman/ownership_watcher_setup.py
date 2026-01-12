#!/usr/bin/env python3
"""
Ownership/Subsidiary/Partnership Watcher Setup for PACMAN

Uses PACMAN's existing patterns to auto-detect:
- Company ownership (all levels)
- Subsidiaries
- Parent companies
- Partnerships/activities
- Beneficial owners

NO FRICTION: Just keyword enumeration + semantic similarity
"""

from PACMAN.watcher_registry import WatcherSpec, ExtractionTarget, save_registry, load_registry


# ==========================================
# OWNERSHIP PATTERNS (Built into PACMAN)
# ==========================================

OWNERSHIP_PATTERNS = {
    # Direct ownership terms
    "owns": r'\b(?:owns?|owned|ownership|owning)\s+(?:by\s+)?([A-Z][^\.,;]+(?:Ltd|LLC|Inc|Corp|GmbH|AG|SA|BV)?)',
    "subsidiary": r'\b(?:subsidiary|subsidiar(?:y|ies))\s+(?:of\s+)?([A-Z][^\.,;]+)',
    "parent": r'\b(?:parent\s+company|parent\s+firm|holding\s+company|holding\s+firm)\s+(?:is\s+)?([A-Z][^\.,;]+)',
    "controlled": r'\b(?:controlled\s+by|under\s+control\s+of)\s+([A-Z][^\.,;]+)',
    "wholly_owned": r'\bwholly[- ]owned\s+(?:subsidiary\s+)?(?:of\s+)?([A-Z][^\.,;]+)',

    # Beneficial ownership
    "beneficial_owner": r'\b(?:beneficial\s+owner|ultimate\s+beneficial\s+owner|UBO)[\s:]*([A-Z][^\.,;]+)',
    "shareholder": r'\b(?:shareholder|stockholder|equity\s+holder)[\s:]*([A-Z][^\.,;]+)',
    "stake": r'\b(?:holds?|holding|owns?)\s+(?:a\s+)?(\d+(?:\.\d+)?%)\s+stake',

    # Corporate structure
    "intermediate_holding": r'\b(?:intermediate\s+holding|intermediate\s+parent|holding\s+structure)[\s:]*([A-Z][^\.,;]+)',
    "group_structure": r'\b(?:group\s+structure|corporate\s+group|group\s+company)[\s:]*([A-Z][^\.,;]+)',

    # Partnerships
    "partnership": r'\b(?:partnership|partner|joint\s+venture|JV)\s+(?:with\s+)?([A-Z][^\.,;]+)',
    "collaboration": r'\b(?:collaboration|collaborat(?:ing|es|ed)|working\s+with)\s+([A-Z][^\.,;]+)',
    "alliance": r'\b(?:strategic\s+alliance|alliance|strategic\s+partnership)\s+(?:with\s+)?([A-Z][^\.,;]+)',

    # Activities/Transactions
    "acquired": r'\b(?:acquired|acquisition\s+of|purchased)\s+([A-Z][^\.,;]+)',
    "merged": r'\b(?:merged\s+with|merger\s+with)\s+([A-Z][^\.,;]+)',
    "divested": r'\b(?:divested|divestiture|sold)\s+([A-Z][^\.,;]+)',
    "invested": r'\b(?:invested\s+in|investment\s+in)\s+([A-Z][^\.,;]+)',
}

# Trigger phrases - if page contains ANY of these, run extraction
OWNERSHIP_TRIGGERS = [
    "ownership structure",
    "corporate structure",
    "parent company",
    "subsidiary",
    "holding company",
    "beneficial owner",
    "shareholder",
    "stake",
    "partnership",
    "joint venture",
    "acquisition",
    "merger",
    "divest",
    "investment",
]


# ==========================================
# WATCHER SETUP
# ==========================================

def create_ownership_watcher(watcher_id: str = "ownership_auto_detect") -> WatcherSpec:
    """
    Create watcher for auto-detecting ownership/subsidiaries/partnerships

    This watcher uses PACMAN's pattern matching - no LLM required
    """

    targets = []

    # Add all ownership patterns as regex targets
    for name, pattern in OWNERSHIP_PATTERNS.items():
        targets.append(ExtractionTarget(
            name=name,
            mode="regex",
            pattern=pattern,
            flags="i",  # Case insensitive
            group=1,    # Capture group 1 (the company name)
            max_hits=20,
            # Only trigger if page contains ownership terms
            trigger="|".join(OWNERSHIP_TRIGGERS)
        ))

    # Add builtin company extraction (always runs)
    targets.append(ExtractionTarget(
        name="all_companies",
        mode="builtin",  # Uses PACMAN's built-in company extractor
        max_hits=50
    ))

    # Add builtin person extraction (for beneficial owners)
    targets.append(ExtractionTarget(
        name="all_persons",
        mode="builtin",  # Uses PACMAN's built-in person extractor
        max_hits=30
    ))

    # Create watcher spec
    watcher = WatcherSpec(
        watcher_id=watcher_id,
        submarine_order="ownership_intelligence",  # Your order ID
        ttl_seconds=24 * 60 * 60,  # 24 hours
        targets=targets
    )

    return watcher


def register_ownership_watcher():
    """
    Register the ownership watcher in PACMAN's registry
    """
    print("=" * 60)
    print("OWNERSHIP WATCHER SETUP")
    print("=" * 60)
    print()

    # Load existing registry
    registry = load_registry()
    print(f"Current watchers: {len(registry)}")

    # Create ownership watcher
    watcher = create_ownership_watcher()

    # Register it
    registry[watcher.watcher_id] = watcher

    # Save
    save_registry(registry)

    print(f"✅ Registered watcher: {watcher.watcher_id}")
    print(f"   Targets: {len(watcher.targets)}")
    print(f"   TTL: {watcher.ttl_seconds / 3600:.0f} hours")
    print()

    print("Extraction targets:")
    for target in watcher.targets:
        print(f"  - {target.name} ({target.mode})")
    print()

    print("=" * 60)
    print("WATCHER ACTIVE")
    print("=" * 60)
    print()
    print("Now any page crawled by PACMAN will auto-extract:")
    print("  ✓ Company ownership mentions")
    print("  ✓ Subsidiary relationships")
    print("  ✓ Parent company references")
    print("  ✓ Partnerships and collaborations")
    print("  ✓ Beneficial owners")
    print("  ✓ Acquisitions/mergers/investments")
    print()
    print("Results will be stored in PACMAN's extraction cache")
    print()


# ==========================================
# TEST WITH EXAMPLE TEXT
# ==========================================

def test_ownership_detection():
    """
    Test ownership detection on sample text
    """
    print("=" * 60)
    print("TESTING OWNERSHIP DETECTION")
    print("=" * 60)
    print()

    test_text = """
    Acme Corporation is a wholly owned subsidiary of Global Holdings Inc.
    The company is controlled by its parent, International Ventures Ltd,
    which holds a 75% stake. The beneficial owner is John Smith, who also
    serves as chairman.

    In 2024, Acme formed a strategic partnership with TechCorp AG for
    AI development. The companies previously collaborated on blockchain
    initiatives. Global Holdings also acquired DataSystems LLC and merged
    with Analytics Partners.

    The group structure includes subsidiaries in Germany (Acme GmbH) and
    France (Acme SA). The intermediate holding company is registered in
    the Netherlands.
    """

    import re

    print("Sample Text:")
    print("-" * 60)
    print(test_text[:200] + "...")
    print()

    print("Detected Patterns:")
    print("-" * 60)

    for name, pattern in OWNERSHIP_PATTERNS.items():
        matches = re.findall(pattern, test_text, re.IGNORECASE)
        if matches:
            print(f"✓ {name}:")
            for match in matches[:5]:
                print(f"    - {match}")

    print()
    print("=" * 60)


# ==========================================
# CLI
# ==========================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Setup Ownership Watcher for PACMAN")
    parser.add_argument("--test", action="store_true", help="Test pattern matching")
    parser.add_argument("--register", action="store_true", help="Register watcher")
    parser.add_argument("--list", action="store_true", help="List registered watchers")

    args = parser.parse_args()

    if args.test:
        test_ownership_detection()

    elif args.register:
        register_ownership_watcher()

    elif args.list:
        registry = load_registry()
        print(f"Registered watchers: {len(registry)}")
        for watcher_id, spec in registry.items():
            print(f"  - {watcher_id}: {len(spec.targets)} targets")

    else:
        print("Usage:")
        print("  Test patterns:       python3 ownership_watcher_setup.py --test")
        print("  Register watcher:    python3 ownership_watcher_setup.py --register")
        print("  List watchers:       python3 ownership_watcher_setup.py --list")
