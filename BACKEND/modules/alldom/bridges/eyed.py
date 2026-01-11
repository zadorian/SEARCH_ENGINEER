"""
ALLDOM Bridge: EYE-D

DNS operations only. WHOIS moved to native alldom/bridges/whois.py (Jan 2026).
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def dns(domain: str, record_types: Optional[List[str]] = None, **kwargs) -> Dict[str, Any]:
    """
    DNS lookup for domain (dns:).
    """
    import socket

    if record_types is None:
        record_types = ["A", "AAAA", "MX", "NS", "TXT", "CNAME"]

    results = {"domain": domain, "records": {}, "success": True}

    try:
        import dns.resolver as dns_resolver

        for rtype in record_types:
            try:
                answers = dns_resolver.resolve(domain, rtype)
                results["records"][rtype] = [str(r) for r in answers]
            except Exception:
                results["records"][rtype] = []

    except ImportError:
        # Fallback to basic socket resolution
        try:
            results["records"]["A"] = list(socket.gethostbyname_ex(domain)[2])
        except Exception:
            results["records"]["A"] = []
        results["source"] = "socket"

    return results


async def dns_history(domain: str, **kwargs) -> List[Dict[str, Any]]:
    """
    Get historical DNS records (if available via SecurityTrails or similar).
    """
    # This would require SecurityTrails API or similar
    logger.warning("DNS history requires SecurityTrails API - not implemented")
    return []
