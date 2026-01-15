"""
Search Engine TIERS
===================

Defines WHICH ENGINES to use for a search.

TIERS are about engine selection, not search intensity.
For search intensity (how hard), see layers.py.

Tier 1 = Fast engines only (GO, BI, BR, DD, EX, CY)
Tier 2 = All standard engines (Tier 1 + YA, QW, GR, NA, GD, AL)
Tier 3 = All engines including slow (Tier 2 + AR, YE, PW)
"""

from enum import IntEnum
from typing import Dict, List, Optional
from dataclasses import dataclass


class SearchTier(IntEnum):
    """
    Engine group tiers - which engines to use.

    Base tiers (1-4):
      t1 = fast engines
      t2 = all standard engines
      t3 = all engines including slow
      t4 = all + LINKLATER (link analysis, requires scraping)

    No-scrape modifier (+0):
      t10 = fast + no scrape
      t20 = all + no scrape
      t30 = all+slow + no scrape
      (t40 not valid - link analysis requires scraping)
    """
    TIER_1 = 1    # Fast engines only
    TIER_2 = 2    # All standard engines
    TIER_3 = 3    # All engines including slow
    TIER_4 = 4    # All engines + LINKLATER (link analysis)
    # No-scrape variants
    TIER_10 = 10  # Fast + no scrape
    TIER_20 = 20  # All + no scrape
    TIER_30 = 30  # All+slow + no scrape


# Engine codes and descriptions
ENGINE_REGISTRY = {
    # Fast engines (Tier 1)
    "GO": {"name": "Google", "tier": 1, "speed": "fast"},
    "BI": {"name": "Bing", "tier": 1, "speed": "fast"},
    "BR": {"name": "Brave", "tier": 1, "speed": "fast"},
    "DD": {"name": "DuckDuckGo", "tier": 1, "speed": "fast"},
    "EX": {"name": "Exa", "tier": 1, "speed": "fast"},
    "CY": {"name": "CYMONIDES (ES)", "tier": 1, "speed": "instant"},

    # Standard engines (Tier 2)
    "YA": {"name": "Yandex", "tier": 2, "speed": "medium"},
    "QW": {"name": "Qwant", "tier": 2, "speed": "medium"},
    "GR": {"name": "Grok", "tier": 2, "speed": "medium"},
    "NA": {"name": "Nature", "tier": 2, "speed": "medium"},
    "GD": {"name": "GDELT", "tier": 2, "speed": "medium"},
    "AL": {"name": "Aleph (OCCRP)", "tier": 2, "speed": "medium"},

    # Slow engines (Tier 3)
    "AR": {"name": "Archive.org", "tier": 3, "speed": "slow"},
    "YE": {"name": "Yep", "tier": 3, "speed": "slow"},
    "PW": {"name": "PublicWWW", "tier": 3, "speed": "slow"},

    # Specialized - LINKLATER (backlink/anchor search)
    "WG": {"name": "Webgraph (ES)", "tier": "link", "speed": "instant"},
    "MJ": {"name": "Majestic", "tier": "link", "speed": "medium"},
    "BD": {"name": "BacklinkDiscovery", "tier": "link", "speed": "medium"},
    "GL": {"name": "GlobalLinks (CC)", "tier": "link", "speed": "slow"},
}


# Engine groups by tier
TIER_ENGINES: Dict[int, List[str]] = {
    # Base tiers
    1: ["GO", "BI", "BR", "DD", "EX", "CY"],
    2: ["GO", "BI", "BR", "DD", "EX", "CY", "YA", "QW", "GR", "NA", "GD", "AL"],
    3: ["GO", "BI", "BR", "DD", "EX", "CY", "YA", "QW", "GR", "NA", "GD", "AL", "AR", "YE", "PW"],
    4: ["GO", "BI", "BR", "DD", "EX", "CY", "YA", "QW", "GR", "NA", "GD", "AL", "AR", "YE", "PW", "WG", "MJ", "BD", "GL"],
    # No-scrape variants (same engines, different scrape flag)
    10: ["GO", "BI", "BR", "DD", "EX", "CY"],
    20: ["GO", "BI", "BR", "DD", "EX", "CY", "YA", "QW", "GR", "NA", "GD", "AL"],
    30: ["GO", "BI", "BR", "DD", "EX", "CY", "YA", "QW", "GR", "NA", "GD", "AL", "AR", "YE", "PW"],
}

# LINKLATER engines (backlink/anchor text search)
LINKLATER_ENGINES = ["WG", "MJ", "BD", "GL"]

# Convenience alias for external consumers
TIERS = TIER_ENGINES


# Named engine groups for convenience
ENGINE_GROUPS = {
    "fast": TIER_ENGINES[1],
    "all": TIER_ENGINES[2],
    "all+slow": TIER_ENGINES[3],
    "all+link": TIER_ENGINES[4],  # All + LINKLATER
    # Specialized groups
    "linklater": LINKLATER_ENGINES,
    "local": ["CY", "WG"],  # Local ES indices (instant)
    "academic": ["NA", "AX", "PM", "OA", "SS", "CR", "JS"],
    "news": ["GD", "NW"],
}


@dataclass
class TierConfig:
    """Configuration for a search tier (engine group)."""
    name: str
    description: str
    engines: List[str]
    scrape: bool = True  # Whether to scrape results (t0 = no scraping)


# Tier configurations - WHICH ENGINES we use
TIER_CONFIGS: Dict[SearchTier, TierConfig] = {
    # Base tiers (with scraping)
    SearchTier.TIER_1: TierConfig(
        name="t1 - Fast",
        description="Fast engines only - Google, Bing, Brave, DDG, Exa, Cymonides",
        engines=TIER_ENGINES[1],
    ),
    SearchTier.TIER_2: TierConfig(
        name="t2 - Standard",
        description="All standard engines - adds Yandex, Qwant, Grok, Nature, GDELT, Aleph",
        engines=TIER_ENGINES[2],
    ),
    SearchTier.TIER_3: TierConfig(
        name="t3 - Comprehensive",
        description="All engines including slow - adds Archive.org, Yep, PublicWWW",
        engines=TIER_ENGINES[3],
    ),
    SearchTier.TIER_4: TierConfig(
        name="t4 - Link Analysis",
        description="All engines + LINKLATER - Webgraph, Majestic, BacklinkDiscovery, GlobalLinks (requires scraping)",
        engines=TIER_ENGINES[4],
    ),
    # No-scrape variants (raw results only)
    SearchTier.TIER_10: TierConfig(
        name="t10 - Fast (no scrape)",
        description="Fast engines, raw results only",
        engines=TIER_ENGINES[10],
        scrape=False,
    ),
    SearchTier.TIER_20: TierConfig(
        name="t20 - Standard (no scrape)",
        description="All standard engines, raw results only",
        engines=TIER_ENGINES[20],
        scrape=False,
    ),
    SearchTier.TIER_30: TierConfig(
        name="t30 - Comprehensive (no scrape)",
        description="All engines including slow, raw results only",
        engines=TIER_ENGINES[30],
        scrape=False,
    ),
}


def get_tier_config(tier: int) -> TierConfig:
    """Get configuration for a tier level."""
    try:
        return TIER_CONFIGS[SearchTier(tier)]
    except ValueError:
        raise ValueError(f"Invalid tier {tier}. Valid tiers: 1-3")


def get_engines_for_tier(tier: int) -> List[str]:
    """Get engine codes for a tier level."""
    return TIER_ENGINES.get(tier, TIER_ENGINES[1])


def get_engine_info(code: str) -> Optional[Dict]:
    """Get info for an engine by code."""
    return ENGINE_REGISTRY.get(code)


def tier_to_name(tier: int) -> str:
    """Map tier number to name."""
    mapping = {
        1: 'fast',
        2: 'all',
        3: 'all+slow',
        4: 'all+link',
        10: 'fast (no scrape)',
        20: 'all (no scrape)',
        30: 'all+slow (no scrape)',
    }
    return mapping.get(tier, 'all')


def name_to_tier(name: str) -> int:
    """Map tier name to number."""
    mapping = {
        'fast': 1,
        'all': 2,
        'all+slow': 3,
        'all+link': 4,
        'medium': 2,  # Alias
        'link': 4,    # Alias
    }
    return mapping.get(name.lower(), 2)


def should_scrape(tier: int) -> bool:
    """Check if results should be scraped for this tier."""
    try:
        config = TIER_CONFIGS[SearchTier(tier)]
        return config.scrape
    except (ValueError, KeyError):
        # If tier > 10, it's a no-scrape variant
        return tier < 10


def get_base_tier(tier: int) -> int:
    """Get the base tier (without no-scrape modifier)."""
    if tier >= 10:
        return tier // 10
    return tier


def parse_tier(tier_str: str) -> int:
    """
    Parse tier string to number.

    Examples:
        "t1" -> 1
        "t10" -> 10 (fast + no scrape)
        "t4" -> 4
    """
    if tier_str.lower().startswith('t'):
        tier_str = tier_str[1:]
    return int(tier_str)
