#!/usr/bin/env python3
"""
BIOGRAPHER Node Model

Node creation utilities for BIOGRAPHER's person profile aggregation.

Node Types:
- QUERY: User search request with timestamp
- PRIMARY: Consolidated person node (no suffix)
- SECONDARY: Source-specific person results (with a/b/c suffix)

Edge Types:
- searched: PRIMARY -> QUERY (this entity was searched for)
- found: SECONDARY -> QUERY (this result was found by query)
- verified/unverified/contradiction: Data -> verification tag

Follows graph_schema.json conventions.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass, field, asdict


# =============================================================================
# SCHEMA VALIDATION
# =============================================================================

VALID_NODE_CLASSES: Set[str] = {"SUBJECT", "NEXUS", "LOCATION", "NARRATIVE"}
VALID_NODE_TYPES: Set[str] = {
    "person", "company", "domain", "query", "verification_tag",
    "rejection_record", "watcher", "document", "address", "phone", "email"
}
VALID_EDGE_TYPES: Set[str] = {
    "searched", "found", "verified", "unverified", "contradiction",
    "rejected", "officer_of", "director_of", "shareholder_of",
    "related_to", "associated_with", "located_at"
}

class NodeValidationError(ValueError):
    """Raised when node validation fails."""
    pass


def generate_id(prefix: str) -> str:
    """Generate a unique ID with prefix."""
    return f"{prefix}{uuid.uuid4().hex[:12]}"


@dataclass
class Edge:
    """Edge/relationship between nodes."""
    edge_type: str
    target_id: str
    props: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate edge on creation."""
        if not self.edge_type:
            raise NodeValidationError("Edge type cannot be empty")
        if not self.target_id:
            raise NodeValidationError("Edge target_id cannot be empty")
        # Warn but don't fail on unknown edge types (extensible)
        if self.edge_type not in VALID_EDGE_TYPES:
            pass  # Allow custom edge types

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.edge_type,
            "target": self.target_id,
            "props": self.props
        }


@dataclass
class Node:
    """Base node structure following graph_schema.json."""
    node_id: str
    node_class: str  # SUBJECT, NEXUS, LOCATION, NARRATIVE
    node_type: str   # entity, query, verification_tag, etc.
    label: str       # Display name
    props: Dict[str, Any] = field(default_factory=dict)
    embedded_edges: List[Edge] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate node on creation."""
        if not self.node_id:
            raise NodeValidationError("node_id cannot be empty")
        if not self.node_class:
            raise NodeValidationError("node_class cannot be empty")
        if self.node_class not in VALID_NODE_CLASSES:
            raise NodeValidationError(
                f"Invalid node_class '{self.node_class}'. "
                f"Must be one of: {', '.join(VALID_NODE_CLASSES)}"
            )
        if not self.node_type:
            raise NodeValidationError("node_type cannot be empty")
        # Allow unknown node_types for extensibility but validate known ones
        if not self.label:
            raise NodeValidationError("label cannot be empty")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_class": self.node_class,
            "node_type": self.node_type,
            "label": self.label,
            "props": self.props,
            "embedded_edges": [e.to_dict() for e in self.embedded_edges],
            "metadata": self.metadata
        }

    def add_edge(self, edge_type: str, target_id: str, props: Dict[str, Any] = None):
        """Add an embedded edge to this node."""
        self.embedded_edges.append(Edge(
            edge_type=edge_type,
            target_id=target_id,
            props=props or {}
        ))


# =============================================================================
# QUERY NODE
# =============================================================================

def create_query_node(
    raw_input: str,
    operator: str = "p:",
    project_id: Optional[str] = None
) -> Node:
    """
    Create a Query Node capturing the user's search request.

    Args:
        raw_input: The raw user input (e.g., "p: John Smith")
        operator: The operator used (e.g., "p:")
        project_id: Optional project this query belongs to

    Returns:
        Node with class=NARRATIVE, type=query
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    return Node(
        node_id=generate_id("qry_"),
        node_class="NARRATIVE",
        node_type="query",
        label=raw_input,
        props={
            "raw_input": raw_input,
            "operator": operator,
            "created_at": timestamp
        },
        metadata={
            "timestamp": timestamp,
            "project_id": project_id,
            "source": "biographer_cli"
        }
    )


# =============================================================================
# PERSON NODES
# =============================================================================

def create_primary_person_node(
    name: str,
    query_node_id: str
) -> Node:
    """
    Create a Primary Person Node (empty fields, to be populated by biographer_ai).

    The primary node represents the consolidated view of a person.
    It links to the query with a 'searched' edge.

    Args:
        name: Clean person name (no suffix)
        query_node_id: ID of the query that triggered this search

    Returns:
        Node with class=SUBJECT, type=person
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    node = Node(
        node_id=generate_id("pers_"),
        node_class="SUBJECT",
        node_type="person",
        label=name,
        props={
            # Empty fields - to be populated by biographer_ai
            "names": [],
            "emails": [],
            "phones": [],
            "nationalities": [],
            "addresses": [],
            "created_at": timestamp,
            "updated_at": timestamp
        },
        metadata={
            "is_primary": True,
            "source": "biographer_cli",
            "consolidation_status": "pending"
        }
    )

    # Link to query with 'searched' edge
    node.add_edge("searched", query_node_id, {
        "created_at": timestamp
    })

    return node


def create_secondary_person_node(
    name: str,
    suffix: str,
    source: str,
    query_node_id: str,
    source_data: Dict[str, Any]
) -> Node:
    """
    Create a Secondary Person Node from a specific source.

    Secondary nodes have a suffix (a), (b), (c) and contain raw source data.
    They link to the query with a 'found' edge.

    Args:
        name: Person name
        suffix: Letter suffix (a, b, c)
        source: Source name (eyed, corporella, socialite)
        query_node_id: ID of the query that triggered this search
        source_data: Raw data from the source

    Returns:
        Node with class=SUBJECT, type=person
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    # Build label with suffix
    label = f"{name} ({suffix})"

    # Extract standard fields from source data
    props = {
        "names": [{"full": name}],
        "created_at": timestamp,
        "updated_at": timestamp
    }

    # Map source fields to standard person props
    # Common fields (all sources can provide these)
    if source_data.get("email"):
        props["emails"] = [source_data["email"]] if isinstance(source_data["email"], str) else source_data["email"]
    if source_data.get("emails"):
        props["emails"] = source_data["emails"]
    if source_data.get("phone"):
        props["phones"] = [source_data["phone"]] if isinstance(source_data["phone"], str) else source_data["phone"]
    if source_data.get("phones"):
        props["phones"] = source_data["phones"]

    # Source-specific fields
    if source == "eyed":
        if source_data.get("linkedin") or source_data.get("linkedin_url"):
            props["linkedin_url"] = source_data.get("linkedin") or source_data.get("linkedin_url")
        if source_data.get("breaches"):
            props["breach_exposure"] = source_data["breaches"]
        if source_data.get("social_profiles"):
            props["social_profiles"] = source_data["social_profiles"]

    elif source == "corporella":
        if source_data.get("officers"):
            props["corporate_roles"] = [
                {"type": "officer", **o} for o in source_data["officers"]
            ]
        if source_data.get("directors"):
            props["corporate_roles"] = props.get("corporate_roles", []) + [
                {"type": "director", **d} for d in source_data["directors"]
            ]
        if source_data.get("shareholders"):
            props["corporate_roles"] = props.get("corporate_roles", []) + [
                {"type": "shareholder", **s} for s in source_data["shareholders"]
            ]
        if source_data.get("employment"):
            props["employment"] = source_data["employment"]

    elif source == "socialite":
        if source_data.get("profiles"):
            props["social_profiles"] = source_data["profiles"]
        if source_data.get("social_profiles"):
            props["social_profiles"] = source_data["social_profiles"]

    node = Node(
        node_id=generate_id("pers_"),
        node_class="SUBJECT",
        node_type="person",
        label=label,
        props=props,
        metadata={
            "is_primary": False,
            "suffix": suffix,
            "source": source,
            "raw_data": source_data
        }
    )

    # Link to query with 'found' edge
    node.add_edge("found", query_node_id, {
        "source": source,
        "created_at": timestamp
    })

    return node


# =============================================================================
# SUFFIX MANAGEMENT
# =============================================================================

SOURCE_SUFFIXES = {
    "eyed": "a",
    "corporella": "b",
    "socialite": "c"
}

def get_suffix_for_source(source: str) -> str:
    """Get the suffix letter for a given source."""
    return SOURCE_SUFFIXES.get(source, chr(ord('a') + len(SOURCE_SUFFIXES)))


# =============================================================================
# NODE COLLECTION
# =============================================================================

@dataclass
class BiographerNodeSet:
    """Collection of nodes created during a biographer search."""
    query_node: Node
    primary_node: Node
    secondary_nodes: List[Node] = field(default_factory=list)
    verification_tags: List[Node] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query_node.to_dict(),
            "primary": self.primary_node.to_dict(),
            "secondaries": [n.to_dict() for n in self.secondary_nodes],
            "verification_tags": [n.to_dict() for n in self.verification_tags],
            "node_ids": {
                "query": self.query_node.node_id,
                "primary": self.primary_node.node_id,
                "secondaries": [n.node_id for n in self.secondary_nodes]
            }
        }

    def add_secondary(self, node: Node):
        """Add a secondary node to the collection."""
        self.secondary_nodes.append(node)

    def get_all_nodes(self) -> List[Node]:
        """Get all nodes in the collection."""
        return [self.query_node, self.primary_node] + self.secondary_nodes + self.verification_tags


def create_biographer_node_set(
    name: str,
    raw_input: str,
    operator: str = "p:",
    project_id: Optional[str] = None
) -> BiographerNodeSet:
    """
    Create the initial node set for a biographer search.

    Creates:
    - Query node with timestamp
    - Primary person node (empty, to be populated)

    Secondary nodes are added later as source CLIs return results.

    Args:
        name: Clean person name
        raw_input: Raw user input
        operator: Operator used
        project_id: Optional project ID

    Returns:
        BiographerNodeSet with query and primary nodes
    """
    query_node = create_query_node(raw_input, operator, project_id)
    primary_node = create_primary_person_node(name, query_node.node_id)

    return BiographerNodeSet(
        query_node=query_node,
        primary_node=primary_node
    )


if __name__ == "__main__":
    # Example usage
    import json

    # Create node set for "John Smith" search
    node_set = create_biographer_node_set(
        name="John Smith",
        raw_input="p: John Smith"
    )

    # Add secondary from EYE-D
    eyed_data = {
        "email": "john.smith@example.com",
        "phone": "+1234567890",
        "linkedin": "https://linkedin.com/in/johnsmith",
        "breaches": [{"name": "LinkedIn 2012", "date": "2012-06-05"}]
    }
    eyed_secondary = create_secondary_person_node(
        name="John Smith",
        suffix=get_suffix_for_source("eyed"),
        source="eyed",
        query_node_id=node_set.query_node.node_id,
        source_data=eyed_data
    )
    node_set.add_secondary(eyed_secondary)

    # Add secondary from CORPORELLA
    corp_data = {
        "officers": [{"company": "Acme Corp", "position": "Director", "appointed": "2020-01-15"}]
    }
    corp_secondary = create_secondary_person_node(
        name="John Smith",
        suffix=get_suffix_for_source("corporella"),
        source="corporella",
        query_node_id=node_set.query_node.node_id,
        source_data=corp_data
    )
    node_set.add_secondary(corp_secondary)

    # Print the result
    print(json.dumps(node_set.to_dict(), indent=2, default=str))
