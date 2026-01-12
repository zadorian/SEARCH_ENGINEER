"""
PACMAN Classifiers
Tier classification and red flag detection
"""

from .tier import (
    Tier,
    TierResult,
    classify_url,
    classify_content,
    batch_classify,
    HIGH_VALUE_DOMAINS,
    SKIP_DOMAINS,
)

from .tripwire import (
    TripwireCategory,
    TripwireHit,
    TripwireScanner,
    scan_content,
    has_red_flags,
    get_scanner,
)

__all__ = [
    # Tier classification
    'Tier',
    'TierResult',
    'classify_url',
    'classify_content',
    'batch_classify',
    'HIGH_VALUE_DOMAINS',
    'SKIP_DOMAINS',
    
    # Tripwire/red flags
    'TripwireCategory',
    'TripwireHit',
    'TripwireScanner',
    'scan_content',
    'has_red_flags',
    'get_scanner',
]
