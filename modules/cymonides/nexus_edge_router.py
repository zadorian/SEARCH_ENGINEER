#!/usr/bin/env python3
"""
NEXUS Edge Router
==================

Routes edges through NEXUS relationship nodes instead of direct connections.

Architecture:
    BEFORE: person --[director_of]--> company
    AFTER:  person --[uses_relationship]--> director_of --[connects_to]--> company

The NEXUS node (director_of) becomes a hub that:
- Lives in the graph as class="query", type="relationship"
- Appears in Column A when viewing /gridX in NEXUS mode
- Accumulates edges as more connections use this relationship
- Carries metadata about the relationship type from ontology

Usage:
    from cymonides.nexus_edge_router import NexusEdgeRouter

    router = NexusEdgeRouter()

    # Instead of creating edge directly:
    # edge = create_edge(person_node, company_node, 'director_of')

    # Route through NEXUS:
    edges = router.route_through_nexus(person_node, company_node, 'director_of')
    # Returns: [person->director_of edge, director_of->company edge]
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import asdict
from pathlib import Path
import json
import sys

# Add NEXUS to path
BACKEND_DIR = Path(__file__).resolve().parents[2]  # Go up to BACKEND/
sys.path.insert(0, str(BACKEND_DIR))

from elasticsearch import Elasticsearch
from modules.cymonides.models import C1Node, EmbeddedEdge

logger = logging.getLogger(__name__)

# NEXUS ontology path - canonical source of truth is cymonides/c1/relationships.json
ONTOLOGY_PATH = BACKEND_DIR / "modules/cymonides/c1/relationships.json"


class NexusEdgeRouter:
    """
    Routes edges through NEXUS relationship nodes.

    Transforms direct entity-to-entity edges into:
        entity -> NEXUS node -> entity

    NEXUS nodes are class="query", type="relationship" and follow the
    canonical ontology from ontology.json.
    """

    def __init__(
        self,
        es_client: Optional[Elasticsearch] = None,
        graph_index: str = "graph_nodes",
        auto_create_nexus: bool = True
    ):
        """
        Initialize router.

        Args:
            es_client: Elasticsearch client (optional, for node lookups)
            graph_index: Name of graph index
            auto_create_nexus: If True, auto-create missing NEXUS nodes
        """
        self.es = es_client
        self.graph_index = graph_index
        self.auto_create_nexus = auto_create_nexus
        self._ontology = None
        self._nexus_node_cache: Dict[str, C1Node] = {}

    @property
    def ontology(self) -> Dict:
        """Lazy load ontology."""
        if self._ontology is None:
            with open(ONTOLOGY_PATH, "r", encoding="utf-8") as f:
                self._ontology = json.load(f)
        return self._ontology

    def get_relationship_info(self, relation: str) -> Optional[Dict]:
        """
        Get relationship information from ontology.

        Args:
            relation: Canonical relationship name (e.g., 'director_of')

        Returns:
            Dict with relationship properties or None if not found
        """
        ont_rels = self.ontology.get("relationships", {})

        # Check root level
        if relation in ont_rels:
            return {
                **ont_rels[relation],
                "canonical": relation,
                "parent": None,
                "depth": 0
            }

        # Search subtypes recursively
        def find_in_subtypes(subtypes: Dict, parent: str, depth: int) -> Optional[Dict]:
            for subtype_name, subtype_data in subtypes.items():
                if subtype_name == relation:
                    return {
                        **subtype_data,
                        "canonical": subtype_name,
                        "parent": parent,
                        "depth": depth
                    }

                # Recurse deeper
                nested = subtype_data.get("subtypes", {})
                if nested:
                    result = find_in_subtypes(nested, subtype_name, depth + 1)
                    if result:
                        return result

            return None

        # Search all roots
        for root_name, root_data in ont_rels.items():
            subtypes = root_data.get("subtypes", {})
            if subtypes:
                result = find_in_subtypes(subtypes, root_name, 1)
                if result:
                    return result

        return None

    def get_or_create_nexus_node(
        self,
        relation: str,
        confidence: float = 1.0
    ) -> C1Node:
        """
        Get or create NEXUS relationship node.

        Args:
            relation: Canonical relationship name
            confidence: Confidence in this relationship (stored in metadata)

        Returns:
            C1Node for the NEXUS relationship
        """
        node_id = f"nexus:relationship:{relation}"

        # Check cache
        if node_id in self._nexus_node_cache:
            return self._nexus_node_cache[node_id]

        # Get relationship info from ontology
        rel_info = self.get_relationship_info(relation)
        if not rel_info:
            logger.warning(f"Relationship '{relation}' not found in ontology")
            rel_info = {
                "canonical": relation,
                "code": None,
                "description": f"Unknown relationship: {relation}",
                "parent": None,
                "depth": 0
            }

        # Create NEXUS node
        nexus_node = C1Node(
            id=node_id,
            node_class="query",  # NEXUS class
            type="relationship",
            label=relation,
            canonicalValue=relation,
            metadata={
                "nexus_type": "relationship",
                "relationship_code": rel_info.get("code"),
                "relationship_description": rel_info.get("description", ""),
                "parent_relationship": rel_info.get("parent"),
                "hierarchy_depth": rel_info.get("depth", 0),
                "is_root": rel_info.get("parent") is None,
                "aliases": rel_info.get("aliases", []),
                "source_types": rel_info.get("source_types", ["*"]),
                "target_types": rel_info.get("target_types", ["*"]),
                "inverse": rel_info.get("inverse"),
                "bidirectional": rel_info.get("bidirectional", False),
                "ontology_version": "3.0.0",
                "edge_confidence": confidence,  # Store confidence from original edge
                "provenance_source": "NEXUS canonical ontology",
                "auto_created": self.auto_create_nexus
            },
            embedded_edges=[],
            source_system="NEXUS"
        )

        # Cache it
        self._nexus_node_cache[node_id] = nexus_node

        return nexus_node

    def route_through_nexus(
        self,
        from_node: C1Node,
        to_node: C1Node,
        relation: str,
        confidence: float = 0.85,
        metadata: Optional[Dict] = None
    ) -> Tuple[EmbeddedEdge, EmbeddedEdge, C1Node]:
        """
        Route an edge through a NEXUS relationship node.

        Creates:
            1. from_node -> nexus_node (uses_relationship)
            2. nexus_node -> to_node (connects_to)

        Args:
            from_node: Source entity node
            to_node: Target entity node
            relation: Relationship type (canonical name)
            confidence: Confidence in this relationship
            metadata: Optional edge metadata

        Returns:
            Tuple of (edge1, edge2, nexus_node)
        """
        # Get or create NEXUS node for this relationship
        nexus_node = self.get_or_create_nexus_node(relation, confidence)

        # Create first edge: entity -> nexus
        edge1 = EmbeddedEdge(
            target_id=nexus_node.id,
            target_class="query",
            target_type="relationship",
            target_label=relation,
            relation="uses_relationship",  # Meta-relationship
            direction="outgoing",
            confidence=confidence,
            metadata={
                **(metadata or {}),
                "original_relation": relation,
                "routed_through_nexus": True,
                "final_target_id": to_node.id,
                "final_target_type": to_node.type
            }
        )

        # Create second edge: nexus -> entity
        edge2 = EmbeddedEdge(
            target_id=to_node.id,
            target_class=to_node.node_class,
            target_type=to_node.type,
            target_label=to_node.label,
            relation="connects_to",  # Meta-relationship
            direction="outgoing",
            confidence=confidence,
            metadata={
                **(metadata or {}),
                "relationship_type": relation,
                "routed_through_nexus": True,
                "original_source_id": from_node.id,
                "original_source_type": from_node.type
            }
        )

        # Add edges to nodes
        from_node.embedded_edges.append(asdict(edge1))
        nexus_node.embedded_edges.append(asdict(edge2))

        logger.debug(
            f"Routed edge through NEXUS: {from_node.label} -> "
            f"[{relation}] -> {to_node.label}"
        )

        return edge1, edge2, nexus_node

    def should_route_through_nexus(
        self,
        from_type: str,
        to_type: str,
        relation: str
    ) -> bool:
        """
        Determine if an edge should be routed through NEXUS.

        Criteria:
            - Relationship exists in canonical ontology
            - Not a meta-relationship (uses_relationship, connects_to)
            - Both nodes are entity/source nodes (not internal system nodes)

        Args:
            from_type: Source node type
            to_type: Target node type
            relation: Relationship type

        Returns:
            True if edge should route through NEXUS
        """
        # Don't route meta-relationships
        if relation in ["uses_relationship", "connects_to", "tagged_with", "extracted_from"]:
            return False

        # Check if relationship exists in ontology
        rel_info = self.get_relationship_info(relation)
        if not rel_info:
            logger.warning(f"Unknown relationship '{relation}' - skipping NEXUS routing")
            return False

        # Check if source/target types are valid for this relationship
        allowed_sources = rel_info.get("source_types", ["*"])
        allowed_targets = rel_info.get("target_types", ["*"])

        if "*" not in allowed_sources and from_type not in allowed_sources:
            logger.debug(f"Source type '{from_type}' not valid for '{relation}'")
            return False

        if "*" not in allowed_targets and to_type not in allowed_targets:
            logger.debug(f"Target type '{to_type}' not valid for '{relation}'")
            return False

        return True

    def get_nexus_nodes_for_indexing(self) -> List[C1Node]:
        """
        Get all NEXUS nodes created during routing for bulk indexing.

        Returns:
            List of NEXUS relationship nodes to index
        """
        return list(self._nexus_node_cache.values())

    def clear_cache(self):
        """Clear the NEXUS node cache."""
        self._nexus_node_cache.clear()


# Convenience function for direct use
def route_edge_through_nexus(
    from_node: C1Node,
    to_node: C1Node,
    relation: str,
    confidence: float = 0.85,
    metadata: Optional[Dict] = None,
    es_client: Optional[Elasticsearch] = None
) -> Tuple[EmbeddedEdge, EmbeddedEdge, C1Node]:
    """
    Convenience function to route a single edge through NEXUS.

    Args:
        from_node: Source entity
        to_node: Target entity
        relation: Relationship type
        confidence: Relationship confidence
        metadata: Optional edge metadata
        es_client: Optional ES client

    Returns:
        Tuple of (edge1, edge2, nexus_node)
    """
    router = NexusEdgeRouter(es_client=es_client)
    return router.route_through_nexus(
        from_node, to_node, relation, confidence, metadata
    )


if __name__ == "__main__":
    # Demo usage
    import logging
    logging.basicConfig(level=logging.DEBUG)

    # Create sample nodes
    person = C1Node(
        id="person:12345",
        node_class="entity",
        type="person",
        label="John Smith",
        canonicalValue="john smith",
        metadata={},
        embedded_edges=[],
        provenance={}
    )

    company = C1Node(
        id="company:67890",
        node_class="entity",
        type="company",
        label="Acme Corp",
        canonicalValue="acme corp",
        metadata={},
        embedded_edges=[],
        provenance={}
    )

    # Route through NEXUS
    router = NexusEdgeRouter()

    print("=" * 60)
    print("NEXUS Edge Routing Demo")
    print("=" * 60)

    if router.should_route_through_nexus("person", "company", "director_of"):
        print("\n✓ Routing 'director_of' through NEXUS...")

        edge1, edge2, nexus = router.route_through_nexus(
            person, company, "director_of", confidence=0.95
        )

        print(f"\nCreated NEXUS node:")
        print(f"  ID: {nexus.id}")
        print(f"  Class: {nexus.node_class}")
        print(f"  Type: {nexus.type}")
        print(f"  Label: {nexus.label}")
        print(f"  Code: {nexus.metadata.get('relationship_code')}")
        print(f"  Parent: {nexus.metadata.get('parent_relationship')}")

        print(f"\nEdge 1: {person.label} -> {nexus.label}")
        print(f"  Relation: {edge1.relation}")
        print(f"  Confidence: {edge1.confidence}")

        print(f"\nEdge 2: {nexus.label} -> {company.label}")
        print(f"  Relation: {edge2.relation}")
        print(f"  Confidence: {edge2.confidence}")

        print(f"\n✅ Edges routed successfully through NEXUS")
    else:
        print("\n✗ Relationship should not be routed through NEXUS")
