"""
Enrichment Profiles - Defines WHEN to Search vs. Watch (True TRAP)
================================================================

This module dictates the "physics" of enrichment.
It answers: "Is this data fleeting? Is it future-bound? Should we set a TRAP?"

Key Concepts:
- Profile: Metadata about an entity type or source type.
- Volatility: How often data changes (HIGH = Watcher candidate).
- Availability: Is data historical or real-time?
- Trap Condition: Logic that triggers a WATCH intent instead of SEARCH.

Usage:
    orchestrator checks `should_watch_instead_of_search(gap)`
    If True -> Creates Watcher (TRAP)
    If False -> Executes Search (SPEAR/NET)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum

class Volatility(Enum):
    STATIC = "static"           # e.g., Date of Birth (rarely changes)
    LOW = "low"                 # e.g., Corporate Officers (years)
    MEDIUM = "medium"           # e.g., Website Content (months)
    HIGH = "high"               # e.g., Stock Price, News (days/hours)
    STREAMING = "streaming"     # e.g., Social Feed (seconds)

@dataclass
class EnrichmentProfile:
    id: str
    target_type: str            # entity_type or source_type
    volatility: Volatility
    trap_keywords: List[str]    # Keywords that suggest a future/monitoring need
    default_strategy: str       # "search" or "watch"
    monitor_frequency: str      # "daily", "weekly", "realtime"

# =============================================================================
# PROFILE CATALOG
# =============================================================================

ENRICHMENT_PROFILES: Dict[str, EnrichmentProfile] = {
    "person": EnrichmentProfile(
        id="profile_person",
        target_type="person",
        volatility=Volatility.LOW,
        trap_keywords=["alert", "monitor", "track", "future", "upcoming", "new appointment"],
        default_strategy="search",
        monitor_frequency="weekly"
    ),
    "company": EnrichmentProfile(
        id="profile_company",
        target_type="company",
        volatility=Volatility.LOW,
        trap_keywords=["filing", "insolvency", "bankruptcy", "merger", "acquisition"],
        default_strategy="search",
        monitor_frequency="daily"
    ),
    "litigation": EnrichmentProfile(
        id="profile_litigation",
        target_type="litigation",
        volatility=Volatility.HIGH,
        trap_keywords=["ongoing", "pending", "judgment", "ruling", "appeal"],
        default_strategy="search",  # Search past first, then watch
        monitor_frequency="daily"
    ),
    "news": EnrichmentProfile(
        id="profile_news",
        target_type="news",
        volatility=Volatility.STREAMING,
        trap_keywords=["breaking", "latest", "developments"],
        default_strategy="watch",   # News is inherently a stream
        monitor_frequency="realtime"
    ),
    "social": EnrichmentProfile(
        id="profile_social",
        target_type="social_media",
        volatility=Volatility.HIGH,
        trap_keywords=["post", "tweet", "activity", "feed"],
        default_strategy="search",
        monitor_frequency="daily"
    ),
    "crypto": EnrichmentProfile(
        id="profile_crypto",
        target_type="crypto_wallet",
        volatility=Volatility.HIGH,
        trap_keywords=["transaction", "movement", "alert"],
        default_strategy="watch",
        monitor_frequency="realtime"
    )
}

# =============================================================================
# LOGIC
# =============================================================================

def get_profile_for_gap(gap: Any) -> Optional[EnrichmentProfile]:
    """Resolve the correct profile for a CognitiveGap."""
    # Check subject type
    subject = getattr(getattr(gap, "coordinates", None), "subject", None)
    if subject:
        etype = getattr(subject, "entity_type", "unknown")
        if etype in ENRICHMENT_PROFILES:
            return ENRICHMENT_PROFILES[etype]
    
    # Check narrative intent keywords against profiles
    intent = getattr(getattr(gap, "coordinates", None), "narrative_intent", "").lower()
    for profile in ENRICHMENT_PROFILES.values():
        if any(kw in intent for kw in profile.trap_keywords):
            return profile
            
    return None

def should_watch_instead_of_search(gap: Any) -> bool:
    """
    Determine if this gap requires a TRAP (Watcher) instead of a SPEAR (Search).
    
    Logic:
    1. If explicit "monitor" keywords are present -> WATCH
    2. If profile default is "watch" -> WATCH
    3. If volatility is HIGH/STREAMING and gap implies "new" info -> WATCH
    """
    profile = get_profile_for_gap(gap)
    if not profile:
        return False
        
    intent_text = getattr(getattr(gap, "coordinates", None), "narrative_intent", "").lower()
    description = getattr(gap, "description", "").lower()
    full_text = f"{intent_text} {description}"
    
    # 1. Explicit Keywords
    if any(kw in full_text for kw in ["monitor", "watch", "alert", "track", "future"]):
        return True
        
    # 2. Profile Default
    if profile.default_strategy == "watch":
        return True
        
    # 3. Volatility Check
    if profile.volatility in [Volatility.HIGH, Volatility.STREAMING]:
        # If looking for "current" or "new" info in a high-volatility domain
        if any(kw in full_text for kw in ["current", "new", "latest", "ongoing"]):
            return True
            
    return False
