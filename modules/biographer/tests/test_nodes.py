#!/usr/bin/env python3
"""Tests for biographer node model."""

import pytest
import json
from datetime import datetime

from biographer.nodes import (
    Node,
    Edge,
    generate_id,
    create_query_node,
    create_primary_person_node,
    create_secondary_person_node,
    create_biographer_node_set,
    BiographerNodeSet,
    get_suffix_for_source,
    SOURCE_SUFFIXES,
    NodeValidationError,
    VALID_NODE_CLASSES,
)


class TestGenerateId:
    """Tests for ID generation."""

    def test_generates_unique_ids(self):
        """Each call should produce a unique ID."""
        ids = [generate_id("test_") for _ in range(100)]
        assert len(set(ids)) == 100

    def test_uses_prefix(self):
        """ID should start with given prefix."""
        id1 = generate_id("qry_")
        id2 = generate_id("pers_")
        assert id1.startswith("qry_")
        assert id2.startswith("pers_")

    def test_id_length(self):
        """ID should be prefix + 12 hex chars."""
        id1 = generate_id("test_")
        assert len(id1) == len("test_") + 12


class TestEdge:
    """Tests for Edge dataclass."""

    def test_basic_edge(self):
        """Create basic edge."""
        edge = Edge(edge_type="searched", target_id="qry_123")
        assert edge.edge_type == "searched"
        assert edge.target_id == "qry_123"
        assert edge.props == {}

    def test_edge_with_props(self):
        """Create edge with properties."""
        edge = Edge(
            edge_type="verified",
            target_id="vtag_123",
            props={"confidence": 0.95, "source": "eyed"}
        )
        assert edge.props["confidence"] == 0.95

    def test_edge_to_dict(self):
        """Edge serialization."""
        edge = Edge(edge_type="found", target_id="qry_456", props={"source": "corporella"})
        d = edge.to_dict()
        assert d["type"] == "found"
        assert d["target"] == "qry_456"
        assert d["props"]["source"] == "corporella"


class TestNode:
    """Tests for Node dataclass."""

    def test_basic_node(self):
        """Create basic node."""
        node = Node(
            node_id="test_123",
            node_class="SUBJECT",
            node_type="person",
            label="John Smith"
        )
        assert node.node_id == "test_123"
        assert node.node_class == "SUBJECT"
        assert node.props == {}
        assert node.embedded_edges == []

    def test_node_with_props(self):
        """Create node with properties."""
        node = Node(
            node_id="test_456",
            node_class="SUBJECT",
            node_type="person",
            label="Jane Doe",
            props={"emails": ["jane@example.com"], "phones": ["+1234567890"]}
        )
        assert node.props["emails"] == ["jane@example.com"]

    def test_add_edge(self):
        """Add edge to node."""
        node = Node(
            node_id="test_789",
            node_class="NARRATIVE",
            node_type="query",
            label="p: John Smith"
        )
        node.add_edge("searched", "qry_123", {"created_at": "2024-01-01"})
        assert len(node.embedded_edges) == 1
        assert node.embedded_edges[0].edge_type == "searched"

    def test_node_to_dict(self):
        """Node serialization."""
        node = Node(
            node_id="test_abc",
            node_class="SUBJECT",
            node_type="person",
            label="Test Person",
            props={"name": "Test"},
            metadata={"source": "test"}
        )
        node.add_edge("verified", "vtag_123")

        d = node.to_dict()
        assert d["node_id"] == "test_abc"
        assert d["node_class"] == "SUBJECT"
        assert d["props"]["name"] == "Test"
        assert len(d["embedded_edges"]) == 1

    def test_node_serializable(self):
        """Node should be JSON serializable."""
        node = Node(
            node_id="test_json",
            node_class="SUBJECT",
            node_type="person",
            label="JSON Test"
        )
        # Should not raise
        json_str = json.dumps(node.to_dict())
        assert "test_json" in json_str

    def test_validation_empty_node_id(self):
        """Empty node_id should raise validation error."""
        with pytest.raises(NodeValidationError, match="node_id cannot be empty"):
            Node(node_id="", node_class="SUBJECT", node_type="person", label="Test")

    def test_validation_invalid_node_class(self):
        """Invalid node_class should raise validation error."""
        with pytest.raises(NodeValidationError, match="Invalid node_class"):
            Node(node_id="test", node_class="INVALID", node_type="person", label="Test")

    def test_validation_empty_label(self):
        """Empty label should raise validation error."""
        with pytest.raises(NodeValidationError, match="label cannot be empty"):
            Node(node_id="test", node_class="SUBJECT", node_type="person", label="")

    def test_validation_valid_node_classes(self):
        """All valid node classes should work."""
        for node_class in VALID_NODE_CLASSES:
            node = Node(
                node_id="test",
                node_class=node_class,
                node_type="person",
                label="Test"
            )
            assert node.node_class == node_class


class TestQueryNode:
    """Tests for query node creation."""

    def test_create_query_node(self):
        """Create query node."""
        node = create_query_node("p: John Smith", operator="p:")
        assert node.node_class == "NARRATIVE"
        assert node.node_type == "query"
        assert node.label == "p: John Smith"
        assert node.props["raw_input"] == "p: John Smith"
        assert node.props["operator"] == "p:"
        assert "created_at" in node.props

    def test_query_node_with_project(self):
        """Create query node with project ID."""
        node = create_query_node("p: Jane Doe", project_id="proj_123")
        assert node.metadata["project_id"] == "proj_123"


class TestPrimaryPersonNode:
    """Tests for primary person node creation."""

    def test_create_primary_person_node(self):
        """Create primary person node."""
        node = create_primary_person_node("John Smith", "qry_123")
        assert node.node_class == "SUBJECT"
        assert node.node_type == "person"
        assert node.label == "John Smith"
        assert node.metadata["is_primary"] is True
        assert node.metadata["consolidation_status"] == "pending"

    def test_primary_has_searched_edge(self):
        """Primary node should have searched edge to query."""
        node = create_primary_person_node("Jane Doe", "qry_456")
        assert len(node.embedded_edges) == 1
        assert node.embedded_edges[0].edge_type == "searched"
        assert node.embedded_edges[0].target_id == "qry_456"

    def test_primary_has_empty_fields(self):
        """Primary node should have empty field lists."""
        node = create_primary_person_node("Test Person", "qry_789")
        assert node.props["names"] == []
        assert node.props["emails"] == []
        assert node.props["phones"] == []


class TestSecondaryPersonNode:
    """Tests for secondary person node creation."""

    def test_create_secondary_person_node(self):
        """Create secondary person node."""
        node = create_secondary_person_node(
            name="John Smith",
            suffix="a",
            source="eyed",
            query_node_id="qry_123",
            source_data={"email": "john@example.com"}
        )
        assert node.label == "John Smith (a)"
        assert node.metadata["is_primary"] is False
        assert node.metadata["suffix"] == "a"
        assert node.metadata["source"] == "eyed"

    def test_secondary_has_found_edge(self):
        """Secondary should have found edge to query."""
        node = create_secondary_person_node(
            name="Jane Doe",
            suffix="b",
            source="corporella",
            query_node_id="qry_456",
            source_data={}
        )
        assert len(node.embedded_edges) == 1
        assert node.embedded_edges[0].edge_type == "found"
        assert node.embedded_edges[0].props["source"] == "corporella"

    def test_secondary_extracts_eyed_fields(self):
        """Secondary should extract EYE-D specific fields."""
        node = create_secondary_person_node(
            name="Test",
            suffix="a",
            source="eyed",
            query_node_id="qry_123",
            source_data={
                "email": "test@test.com",
                "linkedin": "https://linkedin.com/in/test",
                "breaches": [{"name": "Test Breach"}]
            }
        )
        assert node.props["emails"] == ["test@test.com"]
        assert node.props["linkedin_url"] == "https://linkedin.com/in/test"
        assert node.props["breach_exposure"] == [{"name": "Test Breach"}]

    def test_secondary_extracts_corporella_fields(self):
        """Secondary should extract CORPORELLA specific fields."""
        node = create_secondary_person_node(
            name="Test",
            suffix="b",
            source="corporella",
            query_node_id="qry_123",
            source_data={
                "officers": [{"company": "Acme Corp", "position": "Director"}]
            }
        )
        assert len(node.props["corporate_roles"]) == 1
        assert node.props["corporate_roles"][0]["type"] == "officer"


class TestSuffixManagement:
    """Tests for source suffix mapping."""

    def test_known_suffixes(self):
        """Known sources should have assigned suffixes."""
        assert get_suffix_for_source("eyed") == "a"
        assert get_suffix_for_source("corporella") == "b"
        assert get_suffix_for_source("socialite") == "c"

    def test_unknown_source_suffix(self):
        """Unknown source should get next available suffix."""
        suffix = get_suffix_for_source("unknown_source")
        # Should be next letter after existing sources
        assert suffix == chr(ord('a') + len(SOURCE_SUFFIXES))


class TestBiographerNodeSet:
    """Tests for BiographerNodeSet."""

    def test_create_node_set(self):
        """Create initial node set."""
        node_set = create_biographer_node_set(
            name="John Smith",
            raw_input="p: John Smith"
        )
        assert node_set.query_node is not None
        assert node_set.primary_node is not None
        assert node_set.secondary_nodes == []

    def test_add_secondary(self):
        """Add secondary node to set."""
        node_set = create_biographer_node_set("Test", "p: Test")
        secondary = create_secondary_person_node(
            "Test", "a", "eyed", node_set.query_node.node_id, {}
        )
        node_set.add_secondary(secondary)
        assert len(node_set.secondary_nodes) == 1

    def test_get_all_nodes(self):
        """Get all nodes from set."""
        node_set = create_biographer_node_set("Test", "p: Test")
        secondary = create_secondary_person_node(
            "Test", "a", "eyed", node_set.query_node.node_id, {}
        )
        node_set.add_secondary(secondary)

        all_nodes = node_set.get_all_nodes()
        assert len(all_nodes) == 3  # query + primary + 1 secondary

    def test_node_set_to_dict(self):
        """Node set serialization."""
        node_set = create_biographer_node_set("Test", "p: Test")
        d = node_set.to_dict()
        assert "query" in d
        assert "primary" in d
        assert "secondaries" in d
        assert "node_ids" in d


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
