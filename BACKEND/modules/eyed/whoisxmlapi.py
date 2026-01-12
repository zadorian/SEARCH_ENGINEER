"""
DEPRECATED: WHOIS functionality has moved to ALLDOM.

This module re-exports from alldom.bridges.whois for backward compatibility.
Update your imports to: from alldom.bridges.whois import ...

Deprecated: January 2026
"""

import warnings
import sys
from pathlib import Path

warnings.warn(
    "eyed.whoisxmlapi is deprecated. Use alldom.bridges.whois instead.",
    DeprecationWarning,
    stacklevel=2
)

# Add BACKEND/modules to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
BACKEND_MODULES = PROJECT_ROOT / 'BACKEND' / 'modules'
if str(BACKEND_MODULES) not in sys.path:
    sys.path.insert(0, str(BACKEND_MODULES))

# Re-export everything from ALLDOM for backward compatibility
from alldom.bridges.whois import (
    # Exception
    WhoisApiException,
    # Constants
    PRIVACY_INDICATORS,
    TECHNICAL_EMAIL_PREFIXES,
    # Core API functions
    normalize_domain,
    is_privacy_protected,
    should_skip_email,
    fetch_current_whois_record,
    get_whois_history,
    reverse_whois_search,
    reverse_nameserver_search,
    whois_lookup,
    # Entity extraction
    extract_contacts_from_record,
    extract_entities_from_records,
    summarize_whois_records,
    # Dataclasses
    WhoisRecord,
    WhoisClusterResult,
    WhoisDiscoveryResponse,
)

__all__ = [
    "WhoisApiException",
    "PRIVACY_INDICATORS",
    "TECHNICAL_EMAIL_PREFIXES",
    "normalize_domain",
    "is_privacy_protected",
    "should_skip_email",
    "fetch_current_whois_record",
    "get_whois_history",
    "reverse_whois_search",
    "reverse_nameserver_search",
    "whois_lookup",
    "extract_contacts_from_record",
    "extract_entities_from_records",
    "summarize_whois_records",
    "WhoisRecord",
    "WhoisClusterResult",
    "WhoisDiscoveryResponse",
]
