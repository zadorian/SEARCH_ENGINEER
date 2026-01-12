"""
C3 Bridge for BACKDRILL - Query interface to Cymonides-3 (Entity Superindex).

Pre-indexed CommonCrawl-derived data:
- wdc-organization-entities (9.6M docs, 2023)
- wdc-person-entities (6.8M docs, 2023)
- wdc-product-entities (20.3M docs, 2023)
- cc_web_graph_host_edges (421M edges, 2024)
- cc_host_vertices (42.4M hosts, 2024)
- domains_unified (180M domains, 2020-2024)
- cc_pdfs (67K+ PDFs, 2025)

Usage:
    from modules.backdrill.c3_bridge import C3Bridge

    bridge = C3Bridge()
    orgs = await bridge.search_wdc_orgs("Deutsche Bank")
    edges = await bridge.search_webgraph("example.com")
"""

from .bridge import C3Bridge

__all__ = ["C3Bridge"]
