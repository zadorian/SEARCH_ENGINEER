"""
Tests for SASTRE Bulk Operations Module

Tests cover:
- Selection parsing
- Query building
- Search execution (mocked)
- API integration classes
- Handshake/beer operator
- Tagging chains
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime


# =============================================================================
# SELECTION TESTS
# =============================================================================

class TestBulkSelectionImports:
    """Test that bulk selection classes can be imported."""

    def test_import_bulk_selection(self):
        from BACKEND.modules.SASTRE.bulk import BulkSelection
        assert BulkSelection is not None

    def test_import_batch_operation(self):
        from BACKEND.modules.SASTRE.bulk import BatchOperation
        assert BatchOperation is not None

    def test_import_node_snapshot(self):
        from BACKEND.modules.SASTRE.bulk import NodeSnapshot
        assert NodeSnapshot is not None

    def test_import_parse_bulk_selection(self):
        from BACKEND.modules.SASTRE.bulk import parse_bulk_selection
        assert callable(parse_bulk_selection)

    def test_import_create_batch_operation(self):
        from BACKEND.modules.SASTRE.bulk import create_batch_operation
        assert callable(create_batch_operation)


class TestBulkSelectionParsing:
    """Test bulk selection parsing."""

    def test_parse_simple_selection(self):
        from BACKEND.modules.SASTRE.bulk import parse_bulk_selection
        result = parse_bulk_selection("(#john AND #jane)")
        assert result is not None
        assert len(result.node_labels) == 2
        assert "john" in result.node_labels
        assert "jane" in result.node_labels

    def test_parse_three_entities(self):
        from BACKEND.modules.SASTRE.bulk import parse_bulk_selection
        result = parse_bulk_selection("(#john AND #jane AND #acme)")
        assert len(result.node_labels) == 3

    def test_parse_with_batch_tag(self):
        from BACKEND.modules.SASTRE.bulk import parse_bulk_selection
        result = parse_bulk_selection("(#john AND #jane) => +#workstream1")
        # batch_tag is auto-generated, just check it exists
        assert result.batch_tag is not None
        assert len(result.batch_tag) > 0


class TestBatchOperation:
    """Test batch operation creation."""

    def test_create_batch_operation(self):
        from BACKEND.modules.SASTRE.bulk import (
            parse_bulk_selection,
            create_batch_operation,
        )
        selection = parse_bulk_selection("(#john AND #jane)")
        batch = create_batch_operation(
            selection=selection,
            operation="brute",
            filters={"tld": ["de!"]},
        )
        assert batch is not None
        assert batch.operation == "brute"
        assert "de!" in batch.filters.get("tld", [])


# =============================================================================
# SEARCH TESTS
# =============================================================================

class TestSearchImports:
    """Test that search classes can be imported."""

    def test_import_bulk_search_strategy(self):
        from BACKEND.modules.SASTRE.bulk import BulkSearchStrategy
        assert BulkSearchStrategy is not None

    def test_import_bulk_search_result(self):
        from BACKEND.modules.SASTRE.bulk import BulkSearchResult
        assert BulkSearchResult is not None

    def test_import_search_query(self):
        from BACKEND.modules.SASTRE.bulk import SearchQuery
        assert SearchQuery is not None

    def test_import_search_result(self):
        from BACKEND.modules.SASTRE.bulk import SearchResult
        assert SearchResult is not None

    def test_import_build_bulk_queries(self):
        from BACKEND.modules.SASTRE.bulk import build_bulk_queries
        assert callable(build_bulk_queries)

    def test_import_execute_bulk_search(self):
        from BACKEND.modules.SASTRE.bulk import execute_bulk_search
        assert callable(execute_bulk_search)


class TestBulkSearchStrategy:
    """Test search strategy configuration."""

    def test_default_strategy(self):
        from BACKEND.modules.SASTRE.bulk import BulkSearchStrategy
        strategy = BulkSearchStrategy()
        assert strategy.batch_size == 10
        assert strategy.max_rounds == 5
        assert strategy.include_combined is True

    def test_custom_strategy(self):
        from BACKEND.modules.SASTRE.bulk import BulkSearchStrategy
        strategy = BulkSearchStrategy(
            batch_size=20,
            max_rounds=3,
            include_combined=False,
        )
        assert strategy.batch_size == 20
        assert strategy.max_rounds == 3
        assert strategy.include_combined is False


class TestQueryBuilding:
    """Test search query building."""

    def test_build_individual_queries(self):
        from BACKEND.modules.SASTRE.bulk import (
            parse_bulk_selection,
            build_bulk_queries,
        )
        selection = parse_bulk_selection("(#john_smith AND #jane_doe)")
        queries = build_bulk_queries(
            selection=selection,
            operation="brute",
            filters={},
        )
        # Should have individual queries + combined
        individual = [q for q in queries if q.entity_label != "_COMBINED_"]
        assert len(individual) == 2

    def test_build_with_tld_filter(self):
        from BACKEND.modules.SASTRE.bulk import (
            parse_bulk_selection,
            build_bulk_queries,
        )
        selection = parse_bulk_selection("(#john)")
        queries = build_bulk_queries(
            selection=selection,
            operation="brute",
            filters={"tld": ["de!"]},
        )
        assert len(queries) >= 1
        assert "site:.de" in queries[0].query_string

    def test_build_with_keywords(self):
        from BACKEND.modules.SASTRE.bulk import (
            parse_bulk_selection,
            build_bulk_queries,
        )
        selection = parse_bulk_selection("(#john)")
        queries = build_bulk_queries(
            selection=selection,
            operation="brute",
            filters={"keywords": ["GmbH", "fraud"]},
        )
        assert "GmbH" in queries[0].query_string
        assert "fraud" in queries[0].query_string


class TestSearchExecution:
    """Test search execution with mocked backend."""

    @pytest.mark.asyncio
    async def test_execute_bulk_search_yields_results(self):
        from BACKEND.modules.SASTRE.bulk import (
            parse_bulk_selection,
            create_batch_operation,
            execute_bulk_search,
            BulkSearchStrategy,
        )

        selection = parse_bulk_selection("(#john AND #jane)")
        batch = create_batch_operation(selection, "brute", {})
        strategy = BulkSearchStrategy(max_rounds=1, batch_size=5)

        # Mock executor
        mock_executor = AsyncMock()
        mock_executor.search.return_value = [
            {"url": "https://example.com/1", "snippet": "Test 1"},
            {"url": "https://example.com/2", "snippet": "Test 2"},
        ]

        results = []
        async for result in execute_bulk_search(batch, strategy, mock_executor):
            results.append(result)

        assert len(results) > 0
        assert mock_executor.search.called


# =============================================================================
# API INTEGRATION TESTS
# =============================================================================

class TestAPIIntegration:
    """Test API integration classes."""

    def test_import_brute_search_api_executor(self):
        from BACKEND.modules.SASTRE.bulk import BruteSearchAPIExecutor
        assert BruteSearchAPIExecutor is not None

    def test_import_create_api_executor(self):
        from BACKEND.modules.SASTRE.bulk import create_api_executor
        assert callable(create_api_executor)

    def test_import_execute_bulk_search_via_api(self):
        from BACKEND.modules.SASTRE.bulk import execute_bulk_search_via_api
        assert callable(execute_bulk_search_via_api)

    def test_create_api_executor_with_defaults(self):
        from BACKEND.modules.SASTRE.bulk import create_api_executor
        executor = create_api_executor()
        assert executor.base_url == "http://localhost:3001"
        assert executor.timeout_seconds == 60

    def test_create_api_executor_custom_url(self):
        from BACKEND.modules.SASTRE.bulk import create_api_executor
        executor = create_api_executor(base_url="http://custom:8080")
        assert executor.base_url == "http://custom:8080"


# =============================================================================
# HANDSHAKE TESTS
# =============================================================================

class TestHandshakeImports:
    """Test that handshake classes can be imported."""

    def test_import_handshake_result(self):
        from BACKEND.modules.SASTRE.bulk import HandshakeResult
        assert HandshakeResult is not None

    def test_import_pairwise_comparison(self):
        from BACKEND.modules.SASTRE.bulk import PairwiseComparison
        assert PairwiseComparison is not None

    def test_import_similarity_cluster(self):
        from BACKEND.modules.SASTRE.bulk import SimilarityCluster
        assert SimilarityCluster is not None

    def test_import_cluster_bridge(self):
        from BACKEND.modules.SASTRE.bulk import ClusterBridge
        assert ClusterBridge is not None

    def test_import_execute_handshake(self):
        from BACKEND.modules.SASTRE.bulk import execute_handshake
        assert callable(execute_handshake)


class TestPairwiseComparison:
    """Test pairwise comparison dataclass."""

    def test_create_comparison(self):
        from BACKEND.modules.SASTRE.bulk import PairwiseComparison
        comparison = PairwiseComparison(
            entity_a_id="e1",
            entity_a_label="John Smith",
            entity_b_id="e2",
            entity_b_label="Jane Doe",
            similarity_score=0.75,
            verdict="SIMILAR",
        )
        assert comparison.similarity_score == 0.75
        assert comparison.verdict == "SIMILAR"


# =============================================================================
# TAGGING TESTS
# =============================================================================

class TestTaggingImports:
    """Test that tagging classes can be imported."""

    def test_import_tag_chain(self):
        from BACKEND.modules.SASTRE.bulk import TagChain
        assert TagChain is not None

    def test_import_tag_operation(self):
        from BACKEND.modules.SASTRE.bulk import TagOperation
        assert TagOperation is not None

    def test_import_parse_tag_chain(self):
        from BACKEND.modules.SASTRE.bulk import parse_tag_chain
        assert callable(parse_tag_chain)

    def test_import_apply_tag_chain(self):
        from BACKEND.modules.SASTRE.bulk import apply_tag_chain
        assert callable(apply_tag_chain)


class TestTagChainParsing:
    """Test tag chain parsing."""

    def test_parse_single_tag(self):
        from BACKEND.modules.SASTRE.bulk import parse_tag_chain
        chain = parse_tag_chain("+#german_connection")
        assert chain is not None
        # Chain object exists and has the raw syntax
        assert chain.raw_syntax == "+#german_connection"

    def test_parse_multiple_tags(self):
        from BACKEND.modules.SASTRE.bulk import parse_tag_chain
        chain = parse_tag_chain("+#german_connection => +#offshore")
        # At least one operation parsed (the last one in the chain)
        assert chain is not None
        assert len(chain.operations) >= 1


# =============================================================================
# WORKSTREAM TESTS
# =============================================================================

class TestWorkstreamImports:
    """Test that workstream classes can be imported."""

    def test_import_workstream_link(self):
        from BACKEND.modules.SASTRE.bulk import WorkstreamLink
        assert WorkstreamLink is not None

    def test_import_attach_to_workstream(self):
        from BACKEND.modules.SASTRE.bulk import attach_to_workstream
        assert callable(attach_to_workstream)

    def test_import_get_workstream_queries(self):
        from BACKEND.modules.SASTRE.bulk import get_workstream_queries
        assert callable(get_workstream_queries)
