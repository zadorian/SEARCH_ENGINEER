"""
LinkLater Graph Module

Backlinks, outlinks, and graph traversal using CC Web Graph, GlobalLinks, and Tor bridges.

Main exports:
- BacklinkDiscovery: Unified backlink discovery engine
- backlinks(): Unified function with syntax support (?bl, bl?)
- get_backlinks_domains(): Fast domain-only discovery
- get_backlinks_pages(): Rich page-level discovery with anchor text
"""

from .cc_graph import CCGraphClient, get_backlinks_cc_graph, get_outlinks_cc_graph
from .cc_graph_es import CCGraphESClient, get_backlinks_cc_graph_es, get_outlinks_cc_graph_es
from .globallinks import GlobalLinksClient, find_globallinks_binary
from .tor_bridges import TorBridgesClient, get_bridges_for_onion, get_onions_linking_to, get_bridge_statistics
from .models import LinkRecord

# Core backlink discovery (consolidated from 3 implementations)
from .backlinks import (
    BacklinkDiscovery,
    get_backlinks_domains,
    get_backlinks_pages,
    backlinks,
)

__all__ = [
    # Core backlink discovery (MAIN INTERFACE)
    'BacklinkDiscovery',
    'get_backlinks_domains',
    'get_backlinks_pages',
    'backlinks',
    # Graph clients
    'CCGraphClient',
    'CCGraphESClient',
    'GlobalLinksClient',
    'TorBridgesClient',
    'LinkRecord',
    # Legacy functions
    'get_backlinks_cc_graph',
    'get_outlinks_cc_graph',
    'get_backlinks_cc_graph_es',
    'get_outlinks_cc_graph_es',
    'find_globallinks_binary',
    'get_bridges_for_onion',
    'get_onions_linking_to',
    'get_bridge_statistics',
]
