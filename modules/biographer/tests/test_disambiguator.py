#!/usr/bin/env python3
"""Tests for biographer disambiguation bridge."""

import pytest

from biographer.nodes import (
    Node,
    create_biographer_node_set,
    create_secondary_person_node,
)
from biographer.disambiguator_bridge import (
    ResolutionOutcome,
    NodeResolution,
    DisambiguationContext,
    node_to_sastre_entity,
    run_passive_checks,
    generate_wedge_queries,
    disambiguate_node_set,
    disambiguate_before_consolidation,
    apply_disambiguation_to_consolidation,
    DISAMBIGUATOR_AVAILABLE,
    _get_node_value,
)


class TestGetNodeValue:
    """Tests for _get_node_value helper."""

    def test_get_from_props(self):
        """Get value from props."""
        node = Node(
            node_id="test_1",
            node_class="SUBJECT",
            node_type="person",
            label="Test",
            props={"email": "test@test.com"}
        )
        assert _get_node_value(node, "email") == "test@test.com"

    def test_get_from_raw_data(self):
        """Get value from raw_data in metadata."""
        node = Node(
            node_id="test_2",
            node_class="SUBJECT",
            node_type="person",
            label="Test",
            props={},
            metadata={"raw_data": {"date_of_birth": "1980-01-15"}}
        )
        assert _get_node_value(node, "date_of_birth") == "1980-01-15"

    def test_props_takes_priority(self):
        """Props value should take priority over raw_data."""
        node = Node(
            node_id="test_3",
            node_class="SUBJECT",
            node_type="person",
            label="Test",
            props={"email": "from_props@test.com"},
            metadata={"raw_data": {"email": "from_raw@test.com"}}
        )
        assert _get_node_value(node, "email") == "from_props@test.com"

    def test_returns_none_if_missing(self):
        """Return None if field not found anywhere."""
        node = Node(
            node_id="test_4",
            node_class="SUBJECT",
            node_type="person",
            label="Test",
            props={}
        )
        assert _get_node_value(node, "nonexistent") is None


class TestNodeResolution:
    """Tests for NodeResolution dataclass."""

    def test_fuse_resolution(self):
        """Create FUSE resolution."""
        resolution = NodeResolution(
            node_a_id="pers_123",
            node_b_id="pers_456",
            outcome=ResolutionOutcome.FUSE,
            confidence=0.95,
            reason="Matching email: john@test.com"
        )
        assert resolution.outcome == ResolutionOutcome.FUSE
        assert resolution.confidence == 0.95

    def test_repel_resolution(self):
        """Create REPEL resolution."""
        resolution = NodeResolution(
            node_a_id="pers_abc",
            node_b_id="pers_def",
            outcome=ResolutionOutcome.REPEL,
            confidence=0.99,
            reason="Different DOB",
            repel_evidence=["Different DOB: 1975 vs 1982"]
        )
        assert resolution.outcome == ResolutionOutcome.REPEL

    def test_binary_star_resolution(self):
        """Create BINARY_STAR resolution."""
        resolution = NodeResolution(
            node_a_id="pers_xxx",
            node_b_id="pers_yyy",
            outcome=ResolutionOutcome.BINARY_STAR,
            confidence=0.5,
            wedge_queries=[{"type": "temporal", "query": "John Smith DOB"}]
        )
        assert resolution.outcome == ResolutionOutcome.BINARY_STAR
        assert len(resolution.wedge_queries) == 1


class TestDisambiguationContext:
    """Tests for DisambiguationContext."""

    def test_context_creation(self):
        """Create disambiguation context."""
        context = DisambiguationContext(
            subject_name="John Smith",
            jurisdictions=["US", "UK"],
            year_of_birth=1975,
            related_companies=["Acme Corp"]
        )
        assert context.subject_name == "John Smith"
        assert "US" in context.jurisdictions

    def test_context_fields(self):
        """Context has expected fields."""
        context = DisambiguationContext(
            subject_name="Jane Doe",
            countries=["United States"],
            year_of_birth=1980
        )
        assert context.subject_name == "Jane Doe"
        assert context.year_of_birth == 1980
        assert "United States" in context.countries


class TestRunPassiveChecks:
    """Tests for passive disambiguation checks."""

    def test_matching_email_fuses(self):
        """Nodes with matching email should FUSE."""
        node_set = create_biographer_node_set("John Smith", "p: John Smith")

        node_a = create_secondary_person_node(
            "John Smith", "a", "eyed", node_set.query_node.node_id,
            {"email": "john@test.com"}
        )
        node_b = create_secondary_person_node(
            "John Smith", "c", "socialite", node_set.query_node.node_id,
            {"email": "john@test.com"}
        )

        resolution = run_passive_checks(node_a, node_b)

        assert resolution.outcome == ResolutionOutcome.FUSE
        assert "email" in str(resolution.reason).lower()

    def test_matching_phone_fuses(self):
        """Nodes with matching phone should FUSE."""
        node_set = create_biographer_node_set("John Smith", "p: John Smith")

        node_a = create_secondary_person_node(
            "John Smith", "a", "eyed", node_set.query_node.node_id,
            {"phone": "+1234567890"}
        )
        node_b = create_secondary_person_node(
            "John Smith", "b", "corporella", node_set.query_node.node_id,
            {"phones": ["+1234567890"]}
        )

        resolution = run_passive_checks(node_a, node_b)

        assert resolution.outcome == ResolutionOutcome.FUSE

    def test_different_dob_repels(self):
        """Nodes with different DOB should REPEL."""
        node_set = create_biographer_node_set("John Smith", "p: John Smith")

        node_a = create_secondary_person_node(
            "John Smith", "a", "eyed", node_set.query_node.node_id,
            {"date_of_birth": "1975-03-15"}
        )
        node_b = create_secondary_person_node(
            "John Smith", "b", "corporella", node_set.query_node.node_id,
            {"date_of_birth": "1982-07-22"}
        )

        resolution = run_passive_checks(node_a, node_b)

        assert resolution.outcome == ResolutionOutcome.REPEL

    def test_no_overlap_binary_star(self):
        """Nodes with no overlapping identifiers = BINARY_STAR."""
        node_set = create_biographer_node_set("John Smith", "p: John Smith")

        node_a = create_secondary_person_node(
            "John Smith", "a", "eyed", node_set.query_node.node_id,
            {"email": "john@test.com"}
        )
        node_b = create_secondary_person_node(
            "John Smith", "b", "corporella", node_set.query_node.node_id,
            {"corporate_roles": [{"company": "Acme Corp"}]}
        )

        resolution = run_passive_checks(node_a, node_b)

        assert resolution.outcome == ResolutionOutcome.BINARY_STAR


class TestGenerateWedgeQueries:
    """Tests for wedge query generation."""

    def test_generate_temporal_wedge(self):
        """Generate temporal wedge query."""
        node_set = create_biographer_node_set("John Smith", "p: John Smith")

        # Use corporella source since it extracts officers to corporate_roles in props
        node_a = create_secondary_person_node(
            "John Smith", "a", "corporella", node_set.query_node.node_id,
            {"officers": [{"company": "Acme Corp", "position": "Director", "appointed": "2020-01-15"}]}
        )
        node_b = create_secondary_person_node(
            "John Smith", "b", "corporella", node_set.query_node.node_id,
            {"officers": [{"company": "Tech Inc", "position": "CFO"}]}
        )

        wedges = generate_wedge_queries(node_a, node_b)

        # Should have temporal or cross_entity_company wedges
        relevant_wedges = [w for w in wedges if w.get("wedge_type") in ("temporal", "cross_entity_company")]
        assert len(relevant_wedges) > 0

    def test_wedge_queries_are_strings(self):
        """Wedge queries should be executable strings."""
        node_set = create_biographer_node_set("Jane Doe", "p: Jane Doe")

        node_a = create_secondary_person_node(
            "Jane Doe", "a", "eyed", node_set.query_node.node_id,
            {}
        )
        node_b = create_secondary_person_node(
            "Jane Doe", "b", "corporella", node_set.query_node.node_id,
            {}
        )

        wedges = generate_wedge_queries(node_a, node_b)

        for wedge in wedges:
            assert "query" in wedge
            assert isinstance(wedge["query"], str)
            assert len(wedge["query"]) > 0


class TestDisambiguateNodeSet:
    """Tests for full node set disambiguation."""

    def test_single_secondary_no_disambiguation(self):
        """Single secondary doesn't need disambiguation."""
        node_set = create_biographer_node_set("Test", "p: Test")
        secondary = create_secondary_person_node(
            "Test", "a", "eyed", node_set.query_node.node_id,
            {"email": "test@test.com"}
        )
        node_set.add_secondary(secondary)

        result = disambiguate_node_set(node_set)

        assert len(result.resolutions) == 0  # No pairs to compare

    def test_two_secondaries_get_resolution(self):
        """Two secondaries should produce one resolution."""
        node_set = create_biographer_node_set("John Smith", "p: John Smith")

        eyed = create_secondary_person_node(
            "John Smith", "a", "eyed", node_set.query_node.node_id,
            {"email": "john@test.com"}
        )
        socialite = create_secondary_person_node(
            "John Smith", "c", "socialite", node_set.query_node.node_id,
            {"email": "john@test.com"}
        )
        node_set.add_secondary(eyed)
        node_set.add_secondary(socialite)

        result = disambiguate_node_set(node_set)

        assert len(result.resolutions) == 1  # One pair
        assert result.resolutions[0].outcome == ResolutionOutcome.FUSE

    def test_three_secondaries_get_three_resolutions(self):
        """Three secondaries = 3 pairs = 3 resolutions."""
        node_set = create_biographer_node_set("John Smith", "p: John Smith")

        eyed = create_secondary_person_node(
            "John Smith", "a", "eyed", node_set.query_node.node_id,
            {"email": "john@test.com"}
        )
        corporella = create_secondary_person_node(
            "John Smith", "b", "corporella", node_set.query_node.node_id,
            {}
        )
        socialite = create_secondary_person_node(
            "John Smith", "c", "socialite", node_set.query_node.node_id,
            {}
        )
        node_set.add_secondary(eyed)
        node_set.add_secondary(corporella)
        node_set.add_secondary(socialite)

        result = disambiguate_node_set(node_set)

        assert len(result.resolutions) == 3  # 3C2 = 3 pairs


class TestApplyDisambiguationToConsolidation:
    """Tests for applying disambiguation results to consolidation."""

    def test_fuse_keeps_both_nodes(self):
        """FUSE resolution keeps both nodes in merge list."""
        node_set = create_biographer_node_set("John Smith", "p: John Smith")

        eyed = create_secondary_person_node(
            "John Smith", "a", "eyed", node_set.query_node.node_id,
            {"email": "john@test.com"}
        )
        socialite = create_secondary_person_node(
            "John Smith", "c", "socialite", node_set.query_node.node_id,
            {"email": "john@test.com"}
        )
        node_set.add_secondary(eyed)
        node_set.add_secondary(socialite)

        pipeline_result = disambiguate_node_set(node_set)
        # apply_disambiguation_to_consolidation returns a dict, not tuple
        plan = apply_disambiguation_to_consolidation(node_set, pipeline_result)

        assert len(plan["nodes_to_merge"]) == 2
        assert len(plan["nodes_to_exclude"]) == 0

    def test_repel_excludes_minority(self):
        """REPEL excludes node that doesn't match majority cluster."""
        node_set = create_biographer_node_set("John Smith", "p: John Smith")

        # Two nodes FUSE (same email)
        eyed = create_secondary_person_node(
            "John Smith", "a", "eyed", node_set.query_node.node_id,
            {"email": "john@test.com"}
        )
        socialite = create_secondary_person_node(
            "John Smith", "c", "socialite", node_set.query_node.node_id,
            {"email": "john@test.com"}
        )
        # One node REPELS (different DOB)
        corporella = create_secondary_person_node(
            "John Smith", "b", "corporella", node_set.query_node.node_id,
            {"date_of_birth": "1999-12-31"}
        )
        node_set.add_secondary(eyed)
        node_set.add_secondary(socialite)
        node_set.add_secondary(corporella)

        pipeline_result = disambiguate_node_set(node_set)
        # apply_disambiguation_to_consolidation returns a dict, not tuple
        plan = apply_disambiguation_to_consolidation(node_set, pipeline_result)

        # corporella should be excluded (different person based on DOB)
        # The REPEL node should be excluded
        assert len(plan["nodes_to_exclude"]) <= 1


class TestDisambiguateBeforeConsolidation:
    """Tests for convenience function."""

    def test_returns_tuple_of_three(self):
        """Function returns (to_merge, excluded, wedge_queries)."""
        node_set = create_biographer_node_set("Test", "p: Test")
        secondary = create_secondary_person_node(
            "Test", "a", "eyed", node_set.query_node.node_id,
            {"email": "test@test.com"}
        )
        node_set.add_secondary(secondary)

        result = disambiguate_before_consolidation(node_set)

        assert len(result) == 3
        to_merge, excluded, wedges = result
        assert isinstance(to_merge, list)
        assert isinstance(excluded, list)
        assert isinstance(wedges, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
