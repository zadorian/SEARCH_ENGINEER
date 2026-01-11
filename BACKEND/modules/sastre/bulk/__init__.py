"""
SASTRE Bulk Operations Module

Handles bulk entity enrichment with:
- () selection syntax for multiple nodes
- Temporal snapshots of node state
- Combined AND individual searches
- => tagging chain for results
- Workstream linking to narrative notes
- Handshake/beer operator for N×N pairwise comparison
"""

from .selection import (
    BulkSelection,
    BatchOperation,
    NodeSnapshot,
    parse_bulk_selection,
    create_batch_operation,
)

from .search import (
    BulkSearchStrategy,
    BulkSearchResult,
    SearchQuery,
    SearchResult,
    SearchPhase,
    build_bulk_queries,
    execute_bulk_search,
    execute_bulk_search_sync,
    results_to_source_nodes,
    results_to_edges,
    # API Integration
    BruteSearchAPIExecutor,
    create_api_executor,
    execute_bulk_search_via_api,
)

from .tagging import (
    TagChain,
    TagOperation,
    parse_tag_chain,
    apply_tag_chain,
)

from .graph_provider import (
    GraphProvider,
    TagNode,
    Workstream,
    get_graph_provider,
    reset_graph_provider,
)

from .workstream import (
    WorkstreamLink,
    attach_to_workstream,
    get_workstream_queries,
)

from .handshake import (
    HandshakeResult,
    PairwiseComparison,
    SimilarityCluster,
    ClusterBridge,
    execute_handshake,
    compare_pair,
    handshake_to_graph_node,
    handshake_to_edges,
)


__all__ = [
    # Selection
    'BulkSelection',
    'BatchOperation',
    'NodeSnapshot',
    'parse_bulk_selection',
    'create_batch_operation',
    # Search
    'BulkSearchStrategy',
    'BulkSearchResult',
    'SearchQuery',
    'SearchResult',
    'SearchPhase',
    'build_bulk_queries',
    'execute_bulk_search',
    'execute_bulk_search_sync',
    'results_to_source_nodes',
    'results_to_edges',
    # API Integration (production)
    'BruteSearchAPIExecutor',
    'create_api_executor',
    'execute_bulk_search_via_api',
    # Tagging
    'TagChain',
    'TagOperation',
    'parse_tag_chain',
    'apply_tag_chain',
    # GraphProvider (for tagging operations)
    'GraphProvider',
    'TagNode',
    'Workstream',
    'get_graph_provider',
    'reset_graph_provider',
    # Workstream
    'WorkstreamLink',
    'attach_to_workstream',
    'get_workstream_queries',
    # Handshake (N×N comparison)
    'HandshakeResult',
    'PairwiseComparison',
    'SimilarityCluster',
    'ClusterBridge',
    'execute_handshake',
    'compare_pair',
    'handshake_to_graph_node',
    'handshake_to_edges',
]
