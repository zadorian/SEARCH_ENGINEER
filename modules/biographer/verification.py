#!/usr/bin/env python3
"""
BIOGRAPHER Verification System

Handles verification tag nodes and cross-source comparison logic.

Verification Tags:
- VERIFIED: Data appears in 2+ sources (corroborated)
- UNVERIFIED: Data appears in only 1 source (uncorroborated)
- CONTRADICTION: Sources disagree on a field/relationship

Edge Types for Verification:
- verified: Data/Edge -> verified tag node
- unverified: Data/Edge -> unverified tag node
- contradiction: Data/Edge -> contradiction tag node
"""

from dataclasses import dataclass, field as dataclass_field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple, Set
from enum import Enum

from .nodes import Node, Edge, generate_id, BiographerNodeSet

# Import disambiguator bridge (lazy load to avoid circular imports)
_disambiguator_bridge = None

def _get_disambiguator_bridge():
    """Lazy load disambiguator bridge."""
    global _disambiguator_bridge
    if _disambiguator_bridge is None:
        try:
            from . import disambiguator_bridge
            _disambiguator_bridge = disambiguator_bridge
        except ImportError:
            _disambiguator_bridge = False  # Mark as unavailable
    return _disambiguator_bridge if _disambiguator_bridge else None


class VerificationStatus(Enum):
    """Verification status types."""
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    CONTRADICTION = "contradiction"
    REJECTED = "rejected"  # Rejected by biographer_ai with reasoning


# =============================================================================
# VERIFICATION TAG NODES
# =============================================================================

def create_verification_tag(status: VerificationStatus) -> Node:
    """
    Create a verification tag node.

    These are singleton-like nodes that serve as targets for verification edges.
    In practice, you'd create these once per project or use global IDs.

    Args:
        status: The verification status type

    Returns:
        Node with class=NARRATIVE, type=verification_tag
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    return Node(
        node_id=generate_id(f"vtag_{status.value}_"),
        node_class="NARRATIVE",
        node_type="verification_tag",
        label=status.value,
        props={
            "status": status.value,
            "created_at": timestamp
        },
        metadata={
            "source": "biographer_verification"
        }
    )


# Global verification tag node IDs (would be persisted in real system)
VERIFICATION_TAGS = {
    VerificationStatus.VERIFIED: "vtag_verified_global",
    VerificationStatus.UNVERIFIED: "vtag_unverified_global",
    VerificationStatus.CONTRADICTION: "vtag_contradiction_global",
    VerificationStatus.REJECTED: "vtag_rejected_global"
}


def get_verification_tag_id(status: VerificationStatus) -> str:
    """Get the global verification tag node ID for a status."""
    return VERIFICATION_TAGS[status]


# =============================================================================
# BIOGRAPHER DECISION SYSTEM
# =============================================================================

class DecisionAction(Enum):
    """Actions biographer_ai can take on incoming content."""
    ADD_VERIFIED = "add_verified"      # Corroborated data - add to primary
    ADD_UNVERIFIED = "add_unverified"  # Single source - add but mark uncertain
    REJECT = "reject"                   # Don't add - with reasoning


@dataclass
class BiographerDecision:
    """
    Decision made by biographer_ai on incoming watcher content.

    When watcher triggers with new content, biographer_ai decides:
    - ADD_VERIFIED: Content corroborates existing data, add with verified tag
    - ADD_UNVERIFIED: New data from single source, add with unverified tag
    - REJECT: Content rejected - MUST include reasoning in reject_reason

    The reject_reason is stored in the reject tag's comment field.
    """
    action: DecisionAction
    field_name: str
    value: Any
    source: str
    watcher_id: str
    reject_reason: Optional[str] = None  # REQUIRED if action is REJECT
    confidence: float = 1.0
    timestamp: str = dataclass_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self):
        """Validate that REJECT decisions have reasoning."""
        if self.action == DecisionAction.REJECT and not self.reject_reason:
            raise ValueError("REJECT decisions MUST include reject_reason")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "field_name": self.field_name,
            "value": self.value,
            "source": self.source,
            "watcher_id": self.watcher_id,
            "reject_reason": self.reject_reason,
            "confidence": self.confidence,
            "timestamp": self.timestamp
        }


@dataclass
class RejectionRecord:
    """
    Record of a rejection decision.

    Stored in the reject tag node's comment field for audit trail.
    """
    field_name: str
    value: Any
    source: str
    reason: str
    watcher_id: str
    timestamp: str
    primary_node_id: str

    def to_comment(self) -> str:
        """Format as comment for reject tag."""
        return (
            f"REJECTED: {self.field_name}='{self.value}' from {self.source}\n"
            f"Reason: {self.reason}\n"
            f"Watcher: {self.watcher_id}\n"
            f"Time: {self.timestamp}"
        )


def create_rejection_node(
    decision: BiographerDecision,
    primary_node_id: str
) -> Node:
    """
    Create a rejection record node.

    This node is linked to the reject tag and contains the reasoning.
    """
    record = RejectionRecord(
        field_name=decision.field_name,
        value=decision.value,
        source=decision.source,
        reason=decision.reject_reason,
        watcher_id=decision.watcher_id,
        timestamp=decision.timestamp,
        primary_node_id=primary_node_id
    )

    return Node(
        node_id=generate_id("rej_"),
        node_class="NARRATIVE",
        node_type="rejection_record",
        label=f"Rejected: {decision.field_name}",
        props={
            "field_name": decision.field_name,
            "rejected_value": decision.value,
            "source": decision.source,
            "reason": decision.reject_reason,
            "watcher_id": decision.watcher_id,
            "created_at": decision.timestamp
        },
        metadata={
            "comment": record.to_comment(),
            "primary_node_id": primary_node_id
        },
        embedded_edges=[
            Edge(
                edge_type="rejected",
                target_id=get_verification_tag_id(VerificationStatus.REJECTED),
                props={"reason": decision.reject_reason}
            )
        ]
    )


def apply_decision(
    primary_node: Node,
    decision: BiographerDecision
) -> Tuple[Node, Optional[Node]]:
    """
    Apply a biographer decision to the primary node.

    Args:
        primary_node: The primary person node
        decision: The decision to apply

    Returns:
        Tuple of (updated_primary, rejection_node_or_None)
    """
    rejection_node = None

    if decision.action == DecisionAction.REJECT:
        # Create rejection record, don't modify primary
        rejection_node = create_rejection_node(decision, primary_node.node_id)
        return primary_node, rejection_node

    # ADD_VERIFIED or ADD_UNVERIFIED
    # Update the field
    field_name = decision.field_name
    value = decision.value

    # Handle list fields
    if field_name in ["emails", "phones", "social_profiles", "corporate_roles", "breach_exposure"]:
        existing = primary_node.props.get(field_name, [])
        if isinstance(value, list):
            existing.extend(value)
        else:
            existing.append(value)
        primary_node.props[field_name] = existing
    else:
        primary_node.props[field_name] = value

    # Add verification edge
    if decision.action == DecisionAction.ADD_VERIFIED:
        status = VerificationStatus.VERIFIED
    else:
        status = VerificationStatus.UNVERIFIED

    primary_node.add_edge(
        edge_type=status.value,
        target_id=get_verification_tag_id(status),
        props={
            "field": field_name,
            "source": decision.source,
            "watcher_id": decision.watcher_id,
            "confidence": decision.confidence,
            "added_at": decision.timestamp
        }
    )

    primary_node.props["updated_at"] = decision.timestamp

    return primary_node, rejection_node


# =============================================================================
# DATA COMPARISON
# =============================================================================

@dataclass
class FieldValue:
    """A field value with its source."""
    field_name: str
    value: Any
    source: str
    confidence: float = 1.0


@dataclass
class VerificationResult:
    """Result of verifying a field across sources."""
    field_name: str
    status: VerificationStatus
    final_value: Any
    sources: List[str]
    values_by_source: Dict[str, Any]
    confidence: float
    notes: str = ""


def normalize_value(value: Any) -> Any:
    """Normalize a value for comparison."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip().lower()
    if isinstance(value, list):
        return sorted([normalize_value(v) for v in value if v])
    if isinstance(value, dict):
        return {k: normalize_value(v) for k, v in value.items()}
    return value


def values_match(v1: Any, v2: Any, fuzzy: bool = False) -> bool:
    """
    Check if two values match.

    Args:
        v1: First value
        v2: Second value
        fuzzy: Use fuzzy matching for strings

    Returns:
        True if values match
    """
    n1 = normalize_value(v1)
    n2 = normalize_value(v2)

    if n1 == n2:
        return True

    if fuzzy and isinstance(n1, str) and isinstance(n2, str):
        # Simple fuzzy: check if one contains the other or high overlap
        if n1 in n2 or n2 in n1:
            return True
        # Could add Levenshtein distance here

    return False


def compare_field(
    field_name: str,
    values_by_source: Dict[str, Any],
    fuzzy: bool = False
) -> VerificationResult:
    """
    Compare a field across sources and determine verification status.

    Rules:
    - If 2+ sources have matching values -> VERIFIED
    - If only 1 source has value -> UNVERIFIED
    - If sources disagree -> CONTRADICTION (both values kept, both marked unverified)

    Args:
        field_name: Name of the field being compared
        values_by_source: Dict mapping source name to value
        fuzzy: Use fuzzy matching

    Returns:
        VerificationResult with status and final value
    """
    # Filter out None/empty values
    non_empty = {s: v for s, v in values_by_source.items()
                 if v is not None and v != "" and v != []}

    if not non_empty:
        return VerificationResult(
            field_name=field_name,
            status=VerificationStatus.UNVERIFIED,
            final_value=None,
            sources=[],
            values_by_source=values_by_source,
            confidence=0.0,
            notes="No values found"
        )

    sources = list(non_empty.keys())
    values = list(non_empty.values())

    if len(non_empty) == 1:
        # Only one source has data
        return VerificationResult(
            field_name=field_name,
            status=VerificationStatus.UNVERIFIED,
            final_value=values[0],
            sources=sources,
            values_by_source=values_by_source,
            confidence=0.5,
            notes=f"Single source: {sources[0]}"
        )

    # Multiple sources - check for agreement
    # Group matching values
    value_groups: List[Tuple[Any, List[str]]] = []

    for source, value in non_empty.items():
        matched = False
        for group_val, group_sources in value_groups:
            if values_match(value, group_val, fuzzy):
                group_sources.append(source)
                matched = True
                break
        if not matched:
            value_groups.append((value, [source]))

    if len(value_groups) == 1:
        # All sources agree
        return VerificationResult(
            field_name=field_name,
            status=VerificationStatus.VERIFIED,
            final_value=value_groups[0][0],
            sources=value_groups[0][1],
            values_by_source=values_by_source,
            confidence=len(value_groups[0][1]) / len(sources),
            notes=f"Corroborated by {len(value_groups[0][1])} sources"
        )

    # Check if any group has 2+ sources
    largest_group = max(value_groups, key=lambda g: len(g[1]))
    if len(largest_group[1]) >= 2:
        # Majority agrees, but there's contradiction
        return VerificationResult(
            field_name=field_name,
            status=VerificationStatus.CONTRADICTION,
            final_value=largest_group[0],  # Use majority value
            sources=sources,
            values_by_source=values_by_source,
            confidence=len(largest_group[1]) / len(sources),
            notes=f"Majority ({len(largest_group[1])}) agrees, but {len(sources) - len(largest_group[1])} sources disagree"
        )

    # All sources disagree
    return VerificationResult(
        field_name=field_name,
        status=VerificationStatus.CONTRADICTION,
        final_value=values,  # Keep all values
        sources=sources,
        values_by_source=values_by_source,
        confidence=1.0 / len(sources),
        notes=f"All {len(sources)} sources disagree"
    )


# =============================================================================
# CONSOLIDATION
# =============================================================================

@dataclass
class ConsolidationResult:
    """Result of consolidating secondary nodes into primary."""
    primary_updates: Dict[str, Any]
    verification_results: List[VerificationResult]
    edges_to_add: List[Dict[str, Any]]
    confidence_score: float
    summary: str

    # Disambiguation results (new)
    disambiguated: bool = False
    excluded_nodes: List[str] = dataclass_field(default_factory=list)  # REPELLED node IDs
    uncertain_nodes: List[str] = dataclass_field(default_factory=list)  # BINARY_STAR node IDs
    pending_wedge_queries: List[Dict[str, Any]] = dataclass_field(default_factory=list)


def consolidate_secondaries(
    primary_node: Node,
    secondary_nodes: List[Node],
    fuzzy_match: bool = False
) -> ConsolidationResult:
    """
    Consolidate data from secondary nodes into the primary node.

    This is the core biographer_ai consolidation logic.

    Args:
        primary_node: The primary person node to populate
        secondary_nodes: List of secondary nodes from sources
        fuzzy_match: Use fuzzy matching for comparisons

    Returns:
        ConsolidationResult with updates and verification results
    """
    # Fields to consolidate
    FIELDS_TO_CHECK = [
        "emails", "phones", "linkedin_url", "social_profiles",
        "corporate_roles", "employment", "breach_exposure",
        "nationalities", "addresses"
    ]

    verification_results = []
    primary_updates = {}
    edges_to_add = []

    # Build field values by source
    for field_name in FIELDS_TO_CHECK:
        values_by_source = {}
        for sec in secondary_nodes:
            source = sec.metadata.get("source", "unknown")
            value = sec.props.get(field_name)
            if value:
                values_by_source[source] = value

        if values_by_source:
            result = compare_field(field_name, values_by_source, fuzzy_match)
            verification_results.append(result)

            if result.final_value is not None:
                primary_updates[field_name] = result.final_value

                # Add verification edge
                edges_to_add.append({
                    "field": field_name,
                    "edge_type": result.status.value,
                    "target": get_verification_tag_id(result.status),
                    "sources": result.sources,
                    "confidence": result.confidence,
                    "notes": result.notes
                })

    # Calculate overall confidence
    if verification_results:
        total_confidence = sum(r.confidence for r in verification_results)
        avg_confidence = total_confidence / len(verification_results)
        verified_count = sum(1 for r in verification_results
                           if r.status == VerificationStatus.VERIFIED)
        confidence_score = (avg_confidence + verified_count / len(verification_results)) / 2
    else:
        confidence_score = 0.0

    # Generate summary
    status_counts = {}
    for r in verification_results:
        status_counts[r.status.value] = status_counts.get(r.status.value, 0) + 1

    summary_parts = [f"{count} {status}" for status, count in status_counts.items()]
    summary = f"Consolidated {len(secondary_nodes)} sources: " + ", ".join(summary_parts)

    return ConsolidationResult(
        primary_updates=primary_updates,
        verification_results=verification_results,
        edges_to_add=edges_to_add,
        confidence_score=confidence_score,
        summary=summary
    )


def consolidate_with_disambiguation(
    node_set: BiographerNodeSet,
    anchors: Optional[Dict[str, Any]] = None,
    fuzzy_match: bool = False
) -> ConsolidationResult:
    """
    Consolidate secondary nodes with disambiguation.

    This is the RECOMMENDED entry point for biographer consolidation.
    It runs the SASTRE disambiguator first to detect entity collisions,
    then only consolidates nodes confirmed to be the same entity.

    Process:
    1. Run passive disambiguation checks on all node pairs
    2. FUSE nodes are merged into primary
    3. REPEL nodes are excluded (different entity!)
    4. BINARY_STAR nodes generate wedge queries for follow-up

    Args:
        node_set: BiographerNodeSet with primary and secondary nodes
        anchors: DisambiguationAnchors.to_dict() - context for disambiguation
        fuzzy_match: Use fuzzy matching for field comparisons

    Returns:
        ConsolidationResult with disambiguation info
    """
    bridge = _get_disambiguator_bridge()

    if bridge is None or len(node_set.secondary_nodes) < 2:
        # Fallback to simple consolidation if disambiguator unavailable
        # or only 0-1 secondary nodes
        result = consolidate_secondaries(
            node_set.primary_node,
            node_set.secondary_nodes,
            fuzzy_match
        )
        result.disambiguated = False
        return result

    # Run disambiguation
    nodes_to_merge, nodes_excluded, wedge_queries = bridge.disambiguate_before_consolidation(
        node_set,
        anchors
    )

    # Consolidate only the nodes that should be merged
    result = consolidate_secondaries(
        node_set.primary_node,
        nodes_to_merge,
        fuzzy_match
    )

    # Add disambiguation metadata
    result.disambiguated = True
    result.excluded_nodes = [n.node_id for n in nodes_excluded]
    result.uncertain_nodes = []  # BINARY_STAR nodes are included in merge for now
    result.pending_wedge_queries = wedge_queries

    # Update summary with disambiguation info
    if nodes_excluded:
        excluded_sources = [n.metadata.get("source", "unknown") for n in nodes_excluded]
        result.summary += f" | DISAMBIGUATION: {len(nodes_excluded)} nodes excluded (REPEL: {', '.join(excluded_sources)})"

    if wedge_queries:
        result.summary += f" | {len(wedge_queries)} wedge queries pending"

    return result


def apply_consolidation(
    primary_node: Node,
    consolidation: ConsolidationResult
) -> Node:
    """
    Apply consolidation results to the primary node.

    Args:
        primary_node: The primary node to update
        consolidation: The consolidation result

    Returns:
        Updated primary node
    """
    # Update props
    for field, value in consolidation.primary_updates.items():
        primary_node.props[field] = value

    # Update metadata
    primary_node.metadata["consolidation_status"] = "completed"
    primary_node.metadata["confidence_score"] = consolidation.confidence_score
    primary_node.metadata["consolidation_summary"] = consolidation.summary
    primary_node.props["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Add verification edges
    for edge_info in consolidation.edges_to_add:
        primary_node.add_edge(
            edge_type=edge_info["edge_type"],
            target_id=edge_info["target"],
            props={
                "field": edge_info["field"],
                "sources": edge_info["sources"],
                "confidence": edge_info["confidence"],
                "notes": edge_info["notes"]
            }
        )

    return primary_node


if __name__ == "__main__":
    # Example usage
    import json
    from .nodes import create_biographer_node_set, create_secondary_person_node, get_suffix_for_source

    print("=" * 70)
    print("BIOGRAPHER VERIFICATION + DISAMBIGUATION TEST")
    print("=" * 70)

    # Create initial node set
    node_set = create_biographer_node_set(
        name="John Smith",
        raw_input="p: John Smith"
    )

    # Add secondaries with test data
    # EYE-D data - Person A
    eyed_data = {
        "email": "john.smith@example.com",
        "phone": "+1234567890",
        "linkedin_url": "https://linkedin.com/in/johnsmith",
        "date_of_birth": "1975-03-15"  # DOB for disambiguation
    }
    eyed_node = create_secondary_person_node(
        name="John Smith",
        suffix=get_suffix_for_source("eyed"),
        source="eyed",
        query_node_id=node_set.query_node.node_id,
        source_data=eyed_data
    )
    node_set.add_secondary(eyed_node)

    # CORPORELLA data - DIFFERENT PERSON (different DOB = REPEL)
    corp_data = {
        "email": "jsmith@acmecorp.com",
        "date_of_birth": "1982-07-22",  # Different DOB! -> REPEL
        "corporate_roles": [{"type": "director", "company": "Acme Corp"}]
    }
    corp_node = create_secondary_person_node(
        name="John Smith",
        suffix=get_suffix_for_source("corporella"),
        source="corporella",
        query_node_id=node_set.query_node.node_id,
        source_data=corp_data
    )
    node_set.add_secondary(corp_node)

    # SOCIALITE data - SAME PERSON (same email as EYE-D = FUSE)
    social_data = {
        "email": "john.smith@example.com",  # Same as EYE-D -> FUSE
        "social_profiles": [{"platform": "Twitter", "handle": "@johnsmith"}]
    }
    social_node = create_secondary_person_node(
        name="John Smith",
        suffix=get_suffix_for_source("socialite"),
        source="socialite",
        query_node_id=node_set.query_node.node_id,
        source_data=social_data
    )
    node_set.add_secondary(social_node)

    print("\n--- Test 1: Simple Consolidation (no disambiguation) ---")
    result_simple = consolidate_secondaries(
        node_set.primary_node,
        node_set.secondary_nodes
    )
    print(f"  Summary: {result_simple.summary}")
    print(f"  Confidence: {result_simple.confidence_score:.2%}")
    print(f"  Disambiguated: {result_simple.disambiguated}")

    print("\n--- Test 2: Consolidation WITH Disambiguation ---")
    # Create disambiguation anchors
    anchors = {
        "subject": {"name": "John Smith"},
        "location": {"jurisdictions": ["US"], "countries": ["United States"]},
        "temporal": {"year_of_birth": 1975},
        "related_entities": {"companies": [], "persons": []}
    }

    result_disamb = consolidate_with_disambiguation(
        node_set,
        anchors=anchors
    )
    print(f"  Summary: {result_disamb.summary}")
    print(f"  Confidence: {result_disamb.confidence_score:.2%}")
    print(f"  Disambiguated: {result_disamb.disambiguated}")
    print(f"  Excluded Nodes: {result_disamb.excluded_nodes}")
    print(f"  Wedge Queries Pending: {len(result_disamb.pending_wedge_queries)}")

    print("\nVerification Results:")
    for vr in result_disamb.verification_results:
        print(f"  {vr.field_name}: {vr.status.value} ({vr.notes})")

    if result_disamb.pending_wedge_queries:
        print("\nPending Wedge Queries:")
        for wq in result_disamb.pending_wedge_queries[:3]:
            print(f"  [{wq['wedge_type']}] {wq['query']}")

    # Apply to primary
    updated_primary = apply_consolidation(node_set.primary_node, result_disamb)
    print(f"\nUpdated Primary Node Props:")
    for k, v in updated_primary.props.items():
        if v and k not in ["created_at", "updated_at"]:
            print(f"  {k}: {v}")
