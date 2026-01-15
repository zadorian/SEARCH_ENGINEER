#!/usr/bin/env python3
"""
BIOGRAPHER ↔ SASTRE Disambiguator Bridge

Integrates the SASTRE disambiguation system into biographer's node consolidation.

The disambiguator resolves entity collisions using:
1. PASSIVE checks - automatic identifier/temporal/geographic comparisons
2. ACTIVE checks - wedge queries to split ambiguous entities

This bridge:
1. Converts biographer Nodes to SASTRE Entity objects
2. Calls the disambiguator's passive/active checks
3. Returns resolution decisions for each node pair
4. Generates wedge queries when disambiguation is inconclusive

Resolution outcomes (from contracts.DisambiguationAction):
- FUSE: Same entity - merge into primary
- REPEL: Different entities - keep separate, create negative edge
- BINARY_STAR: Ambiguous - orbit and watch, pending wedge query results
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum
from datetime import datetime
import hashlib
import logging
import time

from .nodes import Node, BiographerNodeSet

# Import SASTRE disambiguation components
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# =============================================================================
# CACHING
# =============================================================================

# Cache for disambiguation results (node pair -> resolution)
_DISAMBIGUATION_CACHE: Dict[str, Tuple[Any, float]] = {}
_CACHE_TTL = 3600  # 1 hour

def _make_cache_key(node_a_id: str, node_b_id: str) -> str:
    """Create a consistent cache key for a node pair."""
    ids = sorted([node_a_id, node_b_id])
    return hashlib.md5(f"{ids[0]}:{ids[1]}".encode()).hexdigest()

def _get_cached_resolution(node_a_id: str, node_b_id: str):
    """Get cached resolution if fresh."""
    key = _make_cache_key(node_a_id, node_b_id)
    if key in _DISAMBIGUATION_CACHE:
        resolution, timestamp = _DISAMBIGUATION_CACHE[key]
        if time.time() - timestamp < _CACHE_TTL:
            logger.debug(f"Cache hit: {node_a_id[:12]}↔{node_b_id[:12]}")
            return resolution
    return None

def _cache_resolution(node_a_id: str, node_b_id: str, resolution):
    """Cache a resolution result."""
    key = _make_cache_key(node_a_id, node_b_id)
    _DISAMBIGUATION_CACHE[key] = (resolution, time.time())

def clear_disambiguation_cache():
    """Clear the disambiguation cache."""
    global _DISAMBIGUATION_CACHE
    _DISAMBIGUATION_CACHE = {}
    logger.info("Disambiguation cache cleared")


# =============================================================================
# WEDGE QUERY PERSISTENCE
# =============================================================================

import json
import os

_WEDGE_STORAGE_DIR = Path.home() / ".biographer" / "wedge_queries"

def _get_wedge_file(project_id: str = "default") -> Path:
    """Get the wedge query storage file for a project."""
    _WEDGE_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    return _WEDGE_STORAGE_DIR / f"{project_id}_wedges.json"

def save_wedge_queries(
    wedge_queries: List[Dict[str, Any]],
    project_id: str = "default"
) -> int:
    """
    Save pending wedge queries to persistent storage.

    Args:
        wedge_queries: List of wedge query dicts
        project_id: Project identifier

    Returns:
        Number of queries saved
    """
    if not wedge_queries:
        return 0

    filepath = _get_wedge_file(project_id)

    # Load existing queries
    existing = load_wedge_queries(project_id)

    # Add new queries with timestamps
    for wq in wedge_queries:
        wq["_created_at"] = datetime.now().isoformat()
        wq["_status"] = "pending"
        wq["_project_id"] = project_id
        existing.append(wq)

    # Save
    with open(filepath, 'w') as f:
        json.dump(existing, f, indent=2, default=str)

    logger.info(f"Saved {len(wedge_queries)} wedge queries to {filepath}")
    return len(wedge_queries)

def load_wedge_queries(
    project_id: str = "default",
    status: str = None
) -> List[Dict[str, Any]]:
    """
    Load wedge queries from persistent storage.

    Args:
        project_id: Project identifier
        status: Filter by status ('pending', 'executed', 'resolved')

    Returns:
        List of wedge query dicts
    """
    filepath = _get_wedge_file(project_id)

    if not filepath.exists():
        return []

    try:
        with open(filepath, 'r') as f:
            queries = json.load(f)

        if status:
            queries = [q for q in queries if q.get("_status") == status]

        return queries
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Failed to load wedge queries: {e}")
        return []

def record_wedge_result(
    wedge_query: Dict[str, Any],
    result: Dict[str, Any],
    project_id: str = "default"
) -> bool:
    """
    Record the result of executing a wedge query.

    Args:
        wedge_query: The original wedge query dict
        result: Search results and analysis
        project_id: Project identifier

    Returns:
        True if updated successfully
    """
    filepath = _get_wedge_file(project_id)
    queries = load_wedge_queries(project_id)

    # Find matching query and update it
    query_str = wedge_query.get("query", "")
    updated = False

    for q in queries:
        if q.get("query") == query_str and q.get("_status") == "pending":
            q["_status"] = "executed"
            q["_executed_at"] = datetime.now().isoformat()
            q["_result"] = result
            updated = True
            break

    if updated:
        with open(filepath, 'w') as f:
            json.dump(queries, f, indent=2, default=str)
        logger.info(f"Recorded result for wedge query: {query_str[:50]}...")

    return updated

def get_pending_wedge_count(project_id: str = "default") -> int:
    """Get count of pending wedge queries."""
    return len(load_wedge_queries(project_id, status="pending"))

def clear_wedge_queries(project_id: str = "default") -> bool:
    """Clear all wedge queries for a project."""
    filepath = _get_wedge_file(project_id)
    if filepath.exists():
        filepath.unlink()
        logger.info(f"Cleared wedge queries for project: {project_id}")
        return True
    return False


# Try to import sastre disambiguation modules
_sastre_path = Path(__file__).parent.parent / "sastre"
sys.path.insert(0, str(_sastre_path.parent))

try:
    from sastre.disambiguation import Disambiguator
    from sastre.disambiguation.passive import PassiveChecker, PassiveCheckResult
    from sastre.disambiguation.wedge import WedgeQueryGenerator, WedgeQuery, WedgeType
    from sastre.disambiguation.resolution import ResolutionEngine
    from sastre.contracts import (
        DisambiguationAction,
        Entity as SastreEntity,
        EntityAttributes,
        Collision,
        CollisionType,
        BinaryStar,
        WedgeQuery as ContractWedgeQuery,
        DisambiguationResult,
    )
    from sastre.core.state import Entity, EntityType, Attribute, DisambiguationState
    DISAMBIGUATOR_AVAILABLE = True
except ImportError as e:
    logger.warning(f"SASTRE disambiguator not available: {e}")
    DISAMBIGUATOR_AVAILABLE = False
    # Create stubs for type hints
    DisambiguationAction = None
    Entity = None
    EntityType = None


# =============================================================================
# RESOLUTION DECISION
# =============================================================================

class ResolutionOutcome(Enum):
    """Outcome of disambiguation between two nodes."""
    FUSE = "fuse"           # Same entity - merge
    REPEL = "repel"         # Different entities - keep separate
    BINARY_STAR = "binary_star"  # Uncertain - needs wedge queries
    ERROR = "error"         # Could not determine


@dataclass
class NodeResolution:
    """
    Resolution decision for a pair of secondary nodes.
    """
    node_a_id: str
    node_b_id: str
    outcome: ResolutionOutcome
    confidence: float = 0.0
    reason: str = ""

    # If FUSE - which node's data takes precedence
    primary_node_id: Optional[str] = None

    # If REPEL - evidence for difference
    repel_evidence: List[str] = field(default_factory=list)

    # If BINARY_STAR - wedge queries to resolve
    wedge_queries: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_a_id": self.node_a_id,
            "node_b_id": self.node_b_id,
            "outcome": self.outcome.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "primary_node_id": self.primary_node_id,
            "repel_evidence": self.repel_evidence,
            "wedge_queries": self.wedge_queries,
        }


@dataclass
class DisambiguationContext:
    """
    Context for disambiguation decisions.

    Pre-populated from biographer's DisambiguationAnchors.
    """
    subject_name: str
    jurisdictions: List[str] = field(default_factory=list)
    countries: List[str] = field(default_factory=list)
    cities: List[str] = field(default_factory=list)
    industries: List[str] = field(default_factory=list)
    date_of_birth: Optional[str] = None
    year_of_birth: Optional[int] = None
    related_companies: List[str] = field(default_factory=list)
    related_persons: List[str] = field(default_factory=list)


# =============================================================================
# NODE ↔ ENTITY CONVERSION
# =============================================================================

def node_to_sastre_entity(node: Node) -> Optional['Entity']:
    """
    Convert a biographer Node to a SASTRE Entity.

    Maps:
    - node.props → entity.core/shell/halo attributes
    - node.metadata["source"] → entity.sources
    - node.label → entity.name
    """
    if not DISAMBIGUATOR_AVAILABLE:
        return None

    # Determine entity type from node_type
    entity_type_map = {
        "person": EntityType.PERSON,
        "company": EntityType.COMPANY,
        "domain": EntityType.DOMAIN,
    }
    entity_type = entity_type_map.get(node.node_type, EntityType.UNKNOWN)

    # Create entity
    entity = Entity.create(
        name=node.label,
        entity_type=entity_type
    )
    entity.id = node.node_id

    # Map props to Core/Shell/Halo layers
    props = node.props

    # CORE: Hard identifiers
    core_fields = ["national_id", "passport_id", "tax_id", "ssn", "registration_number", "lei"]
    for field_name in core_fields:
        if props.get(field_name):
            entity.core[field_name] = Attribute(
                name=field_name,
                value=props[field_name],
                confidence=0.95,
                source=node.metadata.get("source", "unknown")
            )

    # Also add DOB to core if present (temporal anchor)
    if props.get("date_of_birth"):
        entity.core["dob"] = Attribute(
            name="dob",
            value=props["date_of_birth"],
            confidence=0.9,
            source=node.metadata.get("source", "unknown")
        )

    # SHELL: Contextual data
    shell_fields = [
        "names", "emails", "phones", "addresses", "linkedin_url",
        "corporate_roles", "employment", "nationalities"
    ]
    for field_name in shell_fields:
        if props.get(field_name):
            entity.shell[field_name] = Attribute(
                name=field_name,
                value=props[field_name],
                confidence=0.7,
                source=node.metadata.get("source", "unknown")
            )

    # HALO: Circumstantial associations
    halo_fields = ["breach_exposure", "social_profiles", "litigation"]
    for field_name in halo_fields:
        if props.get(field_name):
            entity.halo[field_name] = Attribute(
                name=field_name,
                value=props[field_name],
                confidence=0.5,
                source=node.metadata.get("source", "unknown")
            )

    # Set source
    if node.metadata.get("source"):
        entity.sources = [node.metadata["source"]]

    return entity


def sastre_entity_to_node_props(entity: 'Entity') -> Dict[str, Any]:
    """
    Extract props from a SASTRE Entity back to biographer format.

    Used when merging FUSED entities.
    """
    if not DISAMBIGUATOR_AVAILABLE or entity is None:
        return {}

    props = {}

    # Merge all layers
    for layer in [entity.core, entity.shell, entity.halo]:
        for attr_name, attr in layer.items():
            props[attr_name] = attr.value

    return props


# =============================================================================
# PASSIVE DISAMBIGUATION
# =============================================================================

def run_passive_checks(
    node_a: Node,
    node_b: Node,
    context: Optional[DisambiguationContext] = None
) -> NodeResolution:
    """
    Run passive disambiguation checks between two nodes.

    Passive checks use existing data without generating new queries:
    1. Hard identifier collision (SSN, passport, tax ID)
    2. Temporal impossibility (DOB conflicts)
    3. Geographic exclusivity
    4. Age impossibility

    Returns resolution decision.
    """
    # Check cache first
    cached = _get_cached_resolution(node_a.node_id, node_b.node_id)
    if cached is not None:
        return cached

    if not DISAMBIGUATOR_AVAILABLE:
        # Fallback: simple name + source comparison
        result = _fallback_passive_check(node_a, node_b)
        _cache_resolution(node_a.node_id, node_b.node_id, result)
        return result

    # Convert to SASTRE entities
    entity_a = node_to_sastre_entity(node_a)
    entity_b = node_to_sastre_entity(node_b)

    if not entity_a or not entity_b:
        return NodeResolution(
            node_a_id=node_a.node_id,
            node_b_id=node_b.node_id,
            outcome=ResolutionOutcome.ERROR,
            reason="Failed to convert nodes to entities"
        )

    # Run passive checker
    try:
        checker = PassiveChecker()
        check_result = checker.check(entity_a, entity_b)

        # Map result to NodeResolution
        if check_result.action == DisambiguationAction.FUSE:
            resolution = NodeResolution(
                node_a_id=node_a.node_id,
                node_b_id=node_b.node_id,
                outcome=ResolutionOutcome.FUSE,
                confidence=check_result.confidence,
                reason=check_result.reason,
                primary_node_id=node_a.node_id
            )
        elif check_result.action == DisambiguationAction.REPEL:
            resolution = NodeResolution(
                node_a_id=node_a.node_id,
                node_b_id=node_b.node_id,
                outcome=ResolutionOutcome.REPEL,
                confidence=check_result.confidence,
                reason=check_result.reason,
                repel_evidence=[check_result.reason] if check_result.reason else []
            )
        else:  # BINARY_STAR or uncertain
            resolution = NodeResolution(
                node_a_id=node_a.node_id,
                node_b_id=node_b.node_id,
                outcome=ResolutionOutcome.BINARY_STAR,
                confidence=check_result.confidence,
                reason=check_result.reason or "Passive checks inconclusive"
            )
        _cache_resolution(node_a.node_id, node_b.node_id, resolution)
        return resolution
    except Exception as e:
        logger.warning(f"Passive check failed: {e}")
        resolution = _fallback_passive_check(node_a, node_b)
        _cache_resolution(node_a.node_id, node_b.node_id, resolution)
        return resolution


def _get_node_value(node: Node, field: str) -> Any:
    """
    Get a field value from node, checking both props and raw_data.

    Some fields are extracted to props during node creation, others remain
    in metadata['raw_data']. This helper checks both locations.
    """
    # First check props
    val = node.props.get(field)
    if val:
        return val

    # Then check raw_data in metadata
    raw_data = node.metadata.get("raw_data", {})
    if raw_data:
        val = raw_data.get(field)
        if val:
            return val

    return None


def _fallback_passive_check(node_a: Node, node_b: Node) -> NodeResolution:
    """
    Fallback passive check when SASTRE is unavailable.

    Uses simple heuristics:
    - Same email/phone → FUSE
    - Different DOB → REPEL
    - Same source, same name → FUSE
    - Different sources, same name → BINARY_STAR
    """
    # Check for hard identifier matches
    for field in ["national_id", "passport_id", "tax_id", "ssn"]:
        val_a = _get_node_value(node_a, field)
        val_b = _get_node_value(node_b, field)
        if val_a and val_b:
            if val_a == val_b:
                return NodeResolution(
                    node_a_id=node_a.node_id,
                    node_b_id=node_b.node_id,
                    outcome=ResolutionOutcome.FUSE,
                    confidence=0.95,
                    reason=f"Matching {field}",
                    primary_node_id=node_a.node_id
                )
            else:
                return NodeResolution(
                    node_a_id=node_a.node_id,
                    node_b_id=node_b.node_id,
                    outcome=ResolutionOutcome.REPEL,
                    confidence=0.95,
                    reason=f"Conflicting {field}: {val_a} vs {val_b}",
                    repel_evidence=[f"{field} mismatch"]
                )

    # Check email matches (from props or raw_data)
    emails_a = set(_get_node_value(node_a, "emails") or [])
    emails_b = set(_get_node_value(node_b, "emails") or [])
    # Also check single email field
    email_a = _get_node_value(node_a, "email")
    email_b = _get_node_value(node_b, "email")
    if email_a:
        emails_a.add(email_a)
    if email_b:
        emails_b.add(email_b)

    if emails_a and emails_b and emails_a & emails_b:
        return NodeResolution(
            node_a_id=node_a.node_id,
            node_b_id=node_b.node_id,
            outcome=ResolutionOutcome.FUSE,
            confidence=0.85,
            reason=f"Matching email: {emails_a & emails_b}",
            primary_node_id=node_a.node_id
        )

    # Check phone matches
    phones_a = set(_get_node_value(node_a, "phones") or [])
    phones_b = set(_get_node_value(node_b, "phones") or [])
    phone_a = _get_node_value(node_a, "phone")
    phone_b = _get_node_value(node_b, "phone")
    if phone_a:
        phones_a.add(phone_a)
    if phone_b:
        phones_b.add(phone_b)

    if phones_a and phones_b and phones_a & phones_b:
        return NodeResolution(
            node_a_id=node_a.node_id,
            node_b_id=node_b.node_id,
            outcome=ResolutionOutcome.FUSE,
            confidence=0.80,
            reason=f"Matching phone: {phones_a & phones_b}",
            primary_node_id=node_a.node_id
        )

    # Check DOB conflict (critical for person disambiguation)
    dob_a = _get_node_value(node_a, "date_of_birth")
    dob_b = _get_node_value(node_b, "date_of_birth")
    if dob_a and dob_b and dob_a != dob_b:
        return NodeResolution(
            node_a_id=node_a.node_id,
            node_b_id=node_b.node_id,
            outcome=ResolutionOutcome.REPEL,
            confidence=0.90,
            reason=f"Conflicting DOB: {dob_a} vs {dob_b}",
            repel_evidence=["DOB mismatch"]
        )

    # CROSS-ENTITY CHECK: Use corporate role overlap for disambiguation
    # If both persons have corporate roles, check for company overlap
    cross_entity_result = _check_corporate_role_overlap(node_a, node_b)
    if cross_entity_result:
        return cross_entity_result

    # Uncertain - needs wedge queries
    return NodeResolution(
        node_a_id=node_a.node_id,
        node_b_id=node_b.node_id,
        outcome=ResolutionOutcome.BINARY_STAR,
        confidence=0.5,
        reason="No definitive match or conflict found"
    )


def _check_corporate_role_overlap(node_a: Node, node_b: Node) -> Optional[NodeResolution]:
    """
    Check if corporate role overlap can disambiguate two person nodes.

    If both persons claim roles at the same company:
    - Same company + same role → likely same person → FUSE
    - Same company + different roles → might be same person → weak FUSE
    - No overlap but both have corporate roles → could be different people

    This enables BIOGRAPHER to use COMPANYGRAPH data for disambiguation.
    """
    roles_a = node_a.props.get("corporate_roles", [])
    roles_b = node_b.props.get("corporate_roles", [])

    if not roles_a or not roles_b:
        return None  # Can't compare without data

    # Extract company names
    companies_a = {}
    companies_b = {}

    for role in roles_a:
        if isinstance(role, dict):
            company = (role.get("company") or role.get("company_name") or "").lower().strip()
            role_type = role.get("role") or role.get("position") or ""
            if company:
                companies_a[company] = role_type

    for role in roles_b:
        if isinstance(role, dict):
            company = (role.get("company") or role.get("company_name") or "").lower().strip()
            role_type = role.get("role") or role.get("position") or ""
            if company:
                companies_b[company] = role_type

    if not companies_a or not companies_b:
        return None

    # Find shared companies
    shared_companies = set(companies_a.keys()) & set(companies_b.keys())

    if shared_companies:
        # They share at least one company - strong FUSE signal
        evidence = []
        for company in shared_companies:
            role_a = companies_a[company]
            role_b = companies_b[company]
            if role_a and role_b and role_a.lower() == role_b.lower():
                evidence.append(f"Same role ({role_a}) at {company}")
            else:
                evidence.append(f"Both at {company} (roles: {role_a or 'unknown'} vs {role_b or 'unknown'})")

        return NodeResolution(
            node_a_id=node_a.node_id,
            node_b_id=node_b.node_id,
            outcome=ResolutionOutcome.FUSE,
            confidence=0.75 + (0.05 * len(shared_companies)),  # Higher with more overlap
            reason=f"Corporate role overlap: {', '.join(evidence)}",
            primary_node_id=node_a.node_id
        )

    # No overlap - but both have corporate data, could still be different people
    # This is a weak signal, not definitive enough to REPEL
    return None


# =============================================================================
# WEDGE QUERY GENERATION
# =============================================================================

def generate_wedge_queries(
    node_a: Node,
    node_b: Node,
    context: Optional[DisambiguationContext] = None
) -> List[Dict[str, Any]]:
    """
    Generate wedge queries to disambiguate two nodes.

    Wedge queries are designed to SPLIT entities - they test hypotheses
    that would be true for one entity but not another.

    Types:
    - TEMPORAL: "John Smith" "Acme Corp" 2015
    - GEOGRAPHIC: "John Smith" site:*.cy OR "Cyprus"
    - NETWORK: "John Smith" AND "Jane Doe" (spouse)
    - PROFESSIONAL: "John Smith" "lawyer" vs "accountant"
    - ORGANIZATIONAL: "John Smith" "director" "Barclays"

    Returns list of wedge query specs.
    """
    if not DISAMBIGUATOR_AVAILABLE:
        return _fallback_wedge_queries(node_a, node_b, context)

    # Convert to SASTRE entities
    entity_a = node_to_sastre_entity(node_a)
    entity_b = node_to_sastre_entity(node_b)

    if not entity_a or not entity_b:
        return _fallback_wedge_queries(node_a, node_b, context)

    try:
        generator = WedgeQueryGenerator()
        wedges = generator.generate(entity_a, entity_b)

        # Convert to dict format
        return [
            {
                "query": w.query_string,
                "wedge_type": w.wedge_type.value if hasattr(w.wedge_type, 'value') else str(w.wedge_type),
                "entity_a_id": node_a.node_id,
                "entity_b_id": node_b.node_id,
                "expected_if_same": w.expected_if_same,
                "expected_if_different": w.expected_if_different,
            }
            for w in wedges
        ]
    except Exception as e:
        logger.warning(f"Wedge query generation failed: {e}")
        return _fallback_wedge_queries(node_a, node_b, context)


def _fallback_wedge_queries(
    node_a: Node,
    node_b: Node,
    context: Optional[DisambiguationContext] = None
) -> List[Dict[str, Any]]:
    """
    Generate wedge queries without SASTRE.

    Uses simple templates based on available data.
    """
    wedges = []
    name = node_a.label.split("(")[0].strip()  # Remove suffix if present

    props_a = node_a.props
    props_b = node_b.props

    # TEMPORAL wedge - use employment/roles if available
    roles_a = props_a.get("corporate_roles", [])
    roles_b = props_b.get("corporate_roles", [])

    if roles_a:
        for role in roles_a[:2]:  # Limit to 2
            if isinstance(role, dict):
                company = role.get("company", "")
                year = role.get("appointed", "")[:4] if role.get("appointed") else ""
                if company:
                    wedges.append({
                        "query": f'"{name}" "{company}" {year}'.strip(),
                        "wedge_type": "temporal",
                        "entity_a_id": node_a.node_id,
                        "entity_b_id": node_b.node_id,
                        "expected_if_same": f"Results showing {name} at {company}",
                        "expected_if_different": "No results or different person",
                    })

    # GEOGRAPHIC wedge - use jurisdiction from context
    if context and context.jurisdictions:
        for jur in context.jurisdictions[:2]:
            wedges.append({
                "query": f'"{name}" site:*.{jur.lower()} OR "{jur}"',
                "wedge_type": "geographic",
                "entity_a_id": node_a.node_id,
                "entity_b_id": node_b.node_id,
                "expected_if_same": f"Results from {jur}",
                "expected_if_different": "No results from this jurisdiction",
            })

    # NETWORK wedge - use related persons from context
    if context and context.related_persons:
        for person in context.related_persons[:2]:
            wedges.append({
                "query": f'"{name}" AND "{person}"',
                "wedge_type": "network",
                "entity_a_id": node_a.node_id,
                "entity_b_id": node_b.node_id,
                "expected_if_same": f"Results showing connection to {person}",
                "expected_if_different": "No connection found",
            })

    # ORGANIZATIONAL wedge - use LinkedIn data
    linkedin_a = props_a.get("linkedin_url")
    linkedin_b = props_b.get("linkedin_url")

    if linkedin_a and linkedin_b and linkedin_a != linkedin_b:
        # Different LinkedIn profiles - strong REPEL signal
        # Generate query to verify which profile is correct
        wedges.append({
            "query": f'site:linkedin.com/in "{name}"',
            "wedge_type": "organizational",
            "entity_a_id": node_a.node_id,
            "entity_b_id": node_b.node_id,
            "expected_if_same": "Single LinkedIn profile",
            "expected_if_different": "Multiple LinkedIn profiles",
        })

    # CROSS-ENTITY wedges - use COMPANYGRAPH to verify corporate roles
    # For each company in person's roles, query company officer lists
    all_companies = set()
    for role in roles_a + roles_b:
        if isinstance(role, dict):
            company = role.get("company") or role.get("company_name")
            if company:
                all_companies.add(company)

    for company in list(all_companies)[:3]:  # Limit to 3 companies
        wedges.append({
            "query": f'c: "{company}"',
            "wedge_type": "cross_entity_company",
            "entity_a_id": node_a.node_id,
            "entity_b_id": node_b.node_id,
            "expected_if_same": f"{name} appears in {company} officer list",
            "expected_if_different": f"{name} does NOT appear in {company} officer list",
            "verification_target": {
                "person_name": name,
                "company_name": company,
                "action": "verify_officer_membership"
            }
        })

    return wedges


# =============================================================================
# FULL DISAMBIGUATION PIPELINE
# =============================================================================

@dataclass
class DisambiguationPipelineResult:
    """
    Result of running disambiguation on a node set.
    """
    # Resolution decisions
    resolutions: List[NodeResolution] = field(default_factory=list)

    # Nodes confirmed as same entity (should be merged)
    fused_pairs: List[Tuple[str, str]] = field(default_factory=list)

    # Nodes confirmed as different entities
    repelled_pairs: List[Tuple[str, str]] = field(default_factory=list)

    # Nodes still ambiguous
    binary_stars: List[Tuple[str, str]] = field(default_factory=list)

    # Wedge queries to execute
    pending_wedge_queries: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resolutions": [r.to_dict() for r in self.resolutions],
            "fused_pairs": self.fused_pairs,
            "repelled_pairs": self.repelled_pairs,
            "binary_stars": self.binary_stars,
            "pending_wedge_queries": self.pending_wedge_queries,
            "summary": {
                "total_pairs": len(self.resolutions),
                "fused": len(self.fused_pairs),
                "repelled": len(self.repelled_pairs),
                "uncertain": len(self.binary_stars),
            }
        }


def disambiguate_node_set(
    node_set: BiographerNodeSet,
    context: Optional[DisambiguationContext] = None,
    generate_wedges: bool = True
) -> DisambiguationPipelineResult:
    """
    Run disambiguation on all secondary nodes in a BiographerNodeSet.

    Compares each pair of secondary nodes and determines if they
    represent the same or different entities.

    Args:
        node_set: BiographerNodeSet with secondary nodes to disambiguate
        context: DisambiguationContext with anchors
        generate_wedges: If True, generate wedge queries for BINARY_STAR cases

    Returns:
        DisambiguationPipelineResult with all resolution decisions
    """
    result = DisambiguationPipelineResult()

    secondaries = node_set.secondary_nodes
    if len(secondaries) < 2:
        # Nothing to disambiguate
        return result

    # Compare all pairs
    for i, node_a in enumerate(secondaries):
        for node_b in secondaries[i + 1:]:
            # Run passive checks
            resolution = run_passive_checks(node_a, node_b, context)
            result.resolutions.append(resolution)

            # Categorize outcome
            if resolution.outcome == ResolutionOutcome.FUSE:
                result.fused_pairs.append((node_a.node_id, node_b.node_id))
            elif resolution.outcome == ResolutionOutcome.REPEL:
                result.repelled_pairs.append((node_a.node_id, node_b.node_id))
            elif resolution.outcome == ResolutionOutcome.BINARY_STAR:
                result.binary_stars.append((node_a.node_id, node_b.node_id))

                # Generate wedge queries if requested
                if generate_wedges:
                    wedges = generate_wedge_queries(node_a, node_b, context)
                    resolution.wedge_queries = wedges
                    result.pending_wedge_queries.extend(wedges)

    return result


def apply_disambiguation_to_consolidation(
    node_set: BiographerNodeSet,
    disambiguation_result: DisambiguationPipelineResult
) -> Dict[str, Any]:
    """
    Apply disambiguation results to node consolidation.

    Returns a consolidation plan:
    - nodes_to_merge: List of node IDs that should be merged into primary
    - nodes_to_exclude: List of node IDs that are REPELLED (different entity)
    - nodes_uncertain: List of node IDs still in BINARY_STAR state

    For REPELLED nodes, they should NOT be merged into the primary node.
    Instead, they represent a DIFFERENT entity and should be:
    1. Flagged in the output
    2. Potentially spawned as separate investigation subjects

    IMPORTANT: A node can be in FUSE with some nodes and REPEL with others.
    In this case, we find the largest FUSE cluster and include those nodes.
    Nodes that are REPELLED from the main cluster are excluded.
    """
    from collections import defaultdict

    all_secondary_ids = {n.node_id for n in node_set.secondary_nodes}

    # Build graph of fused nodes
    fuse_graph = defaultdict(set)
    for a, b in disambiguation_result.fused_pairs:
        fuse_graph[a].add(b)
        fuse_graph[b].add(a)

    # Build repel relationships
    repel_graph = defaultdict(set)
    for a, b in disambiguation_result.repelled_pairs:
        repel_graph[a].add(b)
        repel_graph[b].add(a)

    # Find connected components via FUSE (groups that should be merged)
    visited = set()
    fuse_clusters = []

    def dfs(node_id: str, group: set):
        if node_id in visited:
            return
        visited.add(node_id)
        group.add(node_id)
        for neighbor in fuse_graph[node_id]:
            dfs(neighbor, group)

    for node_id in fuse_graph:
        if node_id not in visited:
            group = set()
            dfs(node_id, group)
            if group:
                fuse_clusters.append(group)

    # Score each node: FUSE connections vs REPEL connections
    # Nodes with more FUSE than REPEL are likely the "main" entity
    node_scores = {}
    for nid in all_secondary_ids:
        fuse_count = len(fuse_graph.get(nid, set()))
        repel_count = len(repel_graph.get(nid, set()))
        node_scores[nid] = fuse_count - repel_count

    # Find the "main" cluster - the one with highest total score
    # or if no clusters, use all nodes not in repel pairs
    main_cluster = set()
    if fuse_clusters:
        # Choose cluster with highest total score
        best_score = float('-inf')
        for cluster in fuse_clusters:
            cluster_score = sum(node_scores.get(nid, 0) for nid in cluster)
            if cluster_score > best_score:
                best_score = cluster_score
                main_cluster = cluster

    # Nodes to exclude: those that REPEL from the main cluster
    nodes_to_exclude = set()
    for nid in all_secondary_ids:
        if nid in main_cluster:
            continue
        # Check if this node repels any node in main cluster
        repels_main = repel_graph.get(nid, set()) & main_cluster
        if repels_main:
            nodes_to_exclude.add(nid)

    # Nodes to merge: main cluster + uninvolved nodes
    involved_ids = set()
    for a, b in (disambiguation_result.fused_pairs +
                 disambiguation_result.repelled_pairs +
                 disambiguation_result.binary_stars):
        involved_ids.add(a)
        involved_ids.add(b)

    uninvolved = all_secondary_ids - involved_ids

    nodes_to_merge = main_cluster | uninvolved

    # Handle BINARY_STAR nodes: include them tentatively (with warning)
    uncertain_ids = set()
    for a, b in disambiguation_result.binary_stars:
        uncertain_ids.add(a)
        uncertain_ids.add(b)

    # Include uncertain nodes that aren't excluded
    nodes_to_merge.update(uncertain_ids - nodes_to_exclude)

    return {
        "nodes_to_merge": list(nodes_to_merge),
        "nodes_to_exclude": list(nodes_to_exclude),
        "nodes_uncertain": list(uncertain_ids - nodes_to_exclude),
        "merge_groups": [list(c) for c in fuse_clusters],
        "pending_wedge_queries": disambiguation_result.pending_wedge_queries,
    }


# =============================================================================
# INTEGRATION HELPER
# =============================================================================

def disambiguate_before_consolidation(
    node_set: BiographerNodeSet,
    anchors: Optional[Dict[str, Any]] = None
) -> Tuple[List[Node], List[Node], List[Dict[str, Any]]]:
    """
    Run disambiguation and return nodes ready for consolidation.

    This is the main entry point for verification.py integration.

    Args:
        node_set: BiographerNodeSet with secondary nodes
        anchors: Dict from DisambiguationAnchors.to_dict()

    Returns:
        Tuple of:
        - nodes_to_merge: Nodes that should be merged into primary
        - nodes_excluded: Nodes confirmed as different entity (REPEL)
        - wedge_queries: Queries to run for uncertain cases
    """
    # Build context from anchors
    context = None
    if anchors:
        context = DisambiguationContext(
            subject_name=anchors.get("subject", {}).get("name", ""),
            jurisdictions=anchors.get("location", {}).get("jurisdictions", []),
            countries=anchors.get("location", {}).get("countries", []),
            cities=anchors.get("location", {}).get("cities", []),
            industries=anchors.get("industry", {}).get("industries", []),
            date_of_birth=anchors.get("temporal", {}).get("date_of_birth"),
            year_of_birth=anchors.get("temporal", {}).get("year_of_birth"),
            related_companies=anchors.get("related_entities", {}).get("companies", []),
            related_persons=anchors.get("related_entities", {}).get("persons", []),
        )

    # Run disambiguation
    result = disambiguate_node_set(node_set, context, generate_wedges=True)

    # Apply to get consolidation plan
    plan = apply_disambiguation_to_consolidation(node_set, result)

    # Map back to nodes
    node_map = {n.node_id: n for n in node_set.secondary_nodes}

    nodes_to_merge = [node_map[nid] for nid in plan["nodes_to_merge"] if nid in node_map]
    nodes_excluded = [node_map[nid] for nid in plan["nodes_to_exclude"] if nid in node_map]
    wedge_queries = plan["pending_wedge_queries"]

    return nodes_to_merge, nodes_excluded, wedge_queries


# =============================================================================
# CLI TESTING
# =============================================================================

if __name__ == "__main__":
    import json
    from .nodes import create_biographer_node_set, create_secondary_person_node, get_suffix_for_source

    print("=" * 60)
    print("DISAMBIGUATOR BRIDGE TEST")
    print("=" * 60)
    print()

    # Create test node set
    node_set = create_biographer_node_set(
        name="John Smith",
        raw_input="p: John Smith"
    )

    # Add conflicting secondaries (different people)
    eyed_data = {
        "email": "john.smith@gmail.com",
        "phone": "+1234567890",
        "date_of_birth": "1975-03-15",
    }
    eyed_node = create_secondary_person_node(
        name="John Smith",
        suffix=get_suffix_for_source("eyed"),
        source="eyed",
        query_node_id=node_set.query_node.node_id,
        source_data=eyed_data
    )
    node_set.add_secondary(eyed_node)

    corp_data = {
        "email": "jsmith@acme.com",
        "date_of_birth": "1982-07-22",  # Different DOB!
        "officers": [{"company": "Acme Corp", "position": "Director"}]
    }
    corp_node = create_secondary_person_node(
        name="John Smith",
        suffix=get_suffix_for_source("corporella"),
        source="corporella",
        query_node_id=node_set.query_node.node_id,
        source_data=corp_data
    )
    node_set.add_secondary(corp_node)

    # Run disambiguation
    print("Running disambiguation...")
    nodes_merge, nodes_exclude, wedges = disambiguate_before_consolidation(node_set)

    print(f"\nNodes to MERGE into primary: {len(nodes_merge)}")
    for n in nodes_merge:
        print(f"  - {n.label} (source: {n.metadata.get('source')})")

    print(f"\nNodes EXCLUDED (different entity): {len(nodes_exclude)}")
    for n in nodes_exclude:
        print(f"  - {n.label} (source: {n.metadata.get('source')})")

    print(f"\nPending wedge queries: {len(wedges)}")
    for w in wedges[:3]:
        print(f"  - [{w['wedge_type']}] {w['query']}")

    print()
    print("DISAMBIGUATOR_AVAILABLE:", DISAMBIGUATOR_AVAILABLE)
