"""
LinkLater Backlinks Discovery - Re-export Module

This is a thin wrapper for backward compatibility.
The actual implementation is in linkgraph/backlinks.py.

Usage:
    from modules.linklater.backlinks import BacklinkDiscovery, backlinks
    # or
    from modules.linklater.linkgraph import BacklinkDiscovery, backlinks

Deterministic functions for backlink discovery with 4 query modes:
- ?bl !domain   → Referring domains only (FAST - 100ms)
- bl? !domain   → Referring pages with full enrichment (RICH - 30-60s)
- ?bl domain!   → Referring domains to specific URL
- bl? domain!   → Referring pages to specific URL with enrichment
"""

# Re-export from canonical location
from modules.linklater.linkgraph.backlinks import (
    BacklinkDiscovery,
    get_backlinks_domains,
    get_backlinks_pages,
    backlinks,
)

__all__ = [
    'BacklinkDiscovery',
    'get_backlinks_domains',
    'get_backlinks_pages',
    'backlinks',
]

# CLI support
if __name__ == "__main__":
    import asyncio
    from modules.linklater.linkgraph.backlinks import main
    asyncio.run(main())
