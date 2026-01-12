#!/usr/bin/env python3
"""
Output Mapper - Unified I/O Matrix schema-driven mapping.

CONSOLIDATED VERSION - Loads from canonical sources:
- codes.json: THE LEGEND - 722+ field codes (what data types exist)
- relationship.json: 22 edge types (how entities connect)

Usage:
    from output_mapper import OutputMapper, get_codes, get_relationships

    codes = get_codes()
    mapper = get_mapper()

    # Map WHOIS result
    mapped = mapper.map_result("alldom_whois", whois_result, domain="example.com")
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

MATRIX_DIR = Path(__file__).parent
CODES_FILE = MATRIX_DIR / "codes.json"
RELATIONSHIPS_FILE = MATRIX_DIR / "relationship.json"

# Deprecated files - kept for backward compatibility
SCHEMA_FILE = MATRIX_DIR / "schema.json"
CLASSIFICATION_FILE = MATRIX_DIR / "output_classification.json"


# =============================================================================
# CANONICAL SOURCES - codes.json + relationship.json
# =============================================================================

_codes_cache = None
_relationships_cache = None

def get_codes() -> Dict[str, Any]:
    """Load and cache the codes.json - THE LEGEND."""
    global _codes_cache
    if _codes_cache is None:
        with open(CODES_FILE, 'r') as f:
            _codes_cache = json.load(f)
    return _codes_cache


def get_relationships() -> Dict[str, Any]:
    """Load and cache relationship.json - edge types."""
    global _relationships_cache
    if _relationships_cache is None:
        with open(RELATIONSHIPS_FILE, 'r') as f:
            data = json.load(f)
            _relationships_cache = data.get("relationships", {})
    return _relationships_cache


def get_code_info(code: int) -> Dict[str, Any]:
    """Get metadata for a specific field code from codes.json."""
    codes = get_codes()
    return codes.get("codes", {}).get(str(code), {})


def get_code_by_name(name: str) -> Optional[int]:
    """Find code number by name."""
    codes = get_codes()
    for code_str, info in codes.get("codes", {}).items():
        if info.get("name") == name:
            return int(code_str)
    return None


def get_code_type(code: int) -> str:
    """
    Get the type of a code.
    Returns: 'entity', 'attribute', 'nexus', 'aggregate', 'unknown'
    """
    return get_code_info(code).get("type", "unknown")


def creates_node(code: int) -> bool:
    """Does this code create a graph node?"""
    info = get_code_info(code)
    return info.get("creates") in ("node", "node_list", "node_collection")


def creates_metadata(code: int) -> bool:
    """Does this code create metadata (not a standalone node)?"""
    return get_code_info(code).get("creates") == "metadata"


def get_node_type(code: int) -> Optional[str]:
    """Get the node type this code creates (if entity)."""
    return get_code_info(code).get("node_type")


# =============================================================================
# RELATIONSHIP LOOKUPS
# =============================================================================

def get_relationship(rel_name: str) -> Dict[str, Any]:
    """Get relationship definition from relationship.json."""
    return get_relationships().get(rel_name, {})


def get_reified_code(rel_name: str) -> Optional[int]:
    """Get the nexus code for a relationship (600-621)."""
    return get_relationship(rel_name).get("reified_code")


def get_inverse_relationship(rel_name: str) -> Optional[str]:
    """Get the inverse relationship name."""
    return get_relationship(rel_name).get("inverse")


def validate_relationship(rel_type: str, from_type: str, to_type: str) -> bool:
    """Validate that a relationship is valid between two entity types."""
    rel = get_relationship(rel_type)
    if not rel:
        return False

    source_types = rel.get("source_type")
    if isinstance(source_types, str):
        source_types = [source_types]
    if source_types == "any":
        source_types = None  # Any type allowed

    target_types = rel.get("target_type")
    if isinstance(target_types, str):
        target_types = [target_types]
    if target_types == "any":
        target_types = None  # Any type allowed

    source_ok = source_types is None or from_type in source_types
    target_ok = target_types is None or to_type in target_types

    return source_ok and target_ok


def get_valid_relationships_for(from_type: str, to_type: str) -> List[str]:
    """Get valid relationship types between two entity types."""
    valid = []
    for rel_name in get_relationships():
        if validate_relationship(rel_name, from_type, to_type):
            valid.append(rel_name)
    return valid


# =============================================================================
# STRING OUTPUT → CODE/RELATIONSHIP MAPPINGS
# =============================================================================

# Maps string output names to field codes
OUTPUT_TO_CODE: Dict[str, int] = {
    # Officer outputs → code 59 (company_officer_name → person)
    "company_officers": 59,
    "officers": 59,
    "directors": 59,
    "director_positions": 59,
    "board_members": 59,
    "board_memberships": 59,
    "management_team": 59,
    "key_personnel": 59,
    "executives": 59,

    # Beneficial owner outputs → code 67 (company_beneficial_owner_name → person)
    "beneficial_owners": 67,
    "company_beneficial_owners": 67,
    "UBOs": 67,
    "PSCs": 67,
    "controlling_persons": 67,

    # Shareholder outputs → codes 72/73 (shareholder_name/shareholder_company)
    "shareholders": 72,
    "company_shareholders": 72,
    "shareholdings": 72,

    # Address outputs → code 47 (company_address)
    "company_address": 47,
    "registered_address": 47,
    "legal_address": 47,
    "business_address": 47,
    "head_office_address": 47,

    # Person address → code 35 (person_address)
    "person_address": 35,
    "address": 35,

    # Email outputs → code 1 (email) or 44 (company_email) or 32 (person_email)
    "email_address": 1,
    "email_addresses": 1,
    "company_email": 44,
    "person_email": 32,

    # Phone outputs → code 2 (phone) or 45 (company_phone) or 33 (person_phone)
    "phone_number": 2,
    "phone_numbers": 2,
    "company_phone": 45,
    "person_phone": 33,

    # Domain outputs → code 6 (domain_url)
    "domain": 6,
    "website": 6,
    "company_website": 46,

    # Registration IDs → code 14 (company_reg_id)
    "company_reg_id": 14,
    "registration_number": 14,
    "company_number": 14,

    # Subsidiary/parent → codes 422/423/424
    "parent_company": 422,
    "ultimate_parent": 423,
    "subsidiaries": 424,

    # WHOIS → codes 131-135
    "domain_registrant_person": 131,
    "domain_registrant_company": 132,
    "domain_registrant_email": 133,
    "domain_registrant_phone": 134,
    "domain_registrant_address": 135,
}

# Maps string output names to relationship types
OUTPUT_TO_RELATIONSHIP: Dict[str, str] = {
    # Officer relationships
    "company_officers": "officer_of",
    "officers": "officer_of",
    "directors": "officer_of",
    "director_positions": "officer_of",
    "board_members": "officer_of",
    "management_team": "officer_of",
    "key_personnel": "officer_of",
    "executives": "officer_of",

    # Beneficial owner relationships
    "beneficial_owners": "beneficial_owner_of",
    "company_beneficial_owners": "beneficial_owner_of",
    "UBOs": "beneficial_owner_of",
    "PSCs": "beneficial_owner_of",
    "controlling_persons": "beneficial_owner_of",

    # Shareholder relationships
    "shareholders": "shareholder_of",
    "company_shareholders": "shareholder_of",
    "shareholdings": "shareholder_of",

    # Address relationships
    "company_address": "has_address",
    "registered_address": "has_address",
    "legal_address": "has_address",
    "business_address": "has_address",
    "person_address": "has_address",
    "address": "has_address",

    # Email relationships
    "email_address": "has_email",
    "company_email": "has_email",
    "person_email": "has_email",

    # Phone relationships
    "phone_number": "has_phone",
    "company_phone": "has_phone",
    "person_phone": "has_phone",

    # Domain relationships
    "domain": "has_website",
    "website": "has_website",
    "company_website": "has_website",

    # Corporate structure
    "parent_company": "subsidiary_of",  # reverse direction
    "subsidiaries": "subsidiary_of",

    # WHOIS relationships
    "domain_registrant_person": "registrant_of",
    "domain_registrant_company": "registrant_of",
}


# =============================================================================
# ENTITY TYPE DERIVATION FROM CODES
# =============================================================================

def get_entity_types() -> Dict[str, Any]:
    """
    Derive entity types from codes.json.

    Returns a dict mapping entity type names to their metadata,
    derived from codes where type='entity' and creates='node'.
    """
    codes = get_codes()
    entity_types = {}

    # Find all unique node_types from entity codes
    for code_str, info in codes.get("codes", {}).items():
        if info.get("type") == "entity" and info.get("creates") == "node":
            node_type = info.get("node_type")
            if node_type and node_type not in entity_types:
                entity_types[node_type] = {
                    "description": f"Entity type: {node_type}",
                    "primary_code": int(code_str),
                    "field_codes": {}
                }

    # Group field codes by node_type
    for code_str, info in codes.get("codes", {}).items():
        if info.get("type") == "entity" and info.get("creates") == "node":
            node_type = info.get("node_type")
            if node_type and node_type in entity_types:
                entity_types[node_type]["field_codes"][info["name"]] = int(code_str)

    return entity_types


def get_field_code(entity_type: str, field_name: str = None) -> int:
    """
    Get the field code for an entity type or specific field.

    Maps entity type names to their primary codes.
    """
    # Direct mapping for common types
    type_to_code = {
        "email": 1,
        "phone": 2,
        "username": 3,
        "linkedin": 5,
        "domain": 6,
        "person": 7,
        "address": 20,
        "company": 13,
        "vehicle": 23,
        "vessel": 24,
        "aircraft": 25,
        "license": 26,
        "litigation": 17,
        "country": 48,  # company_country
        "registrar": 22,  # nameserver area
        "nameserver": 21,
        "ip_address": 8,
    }

    if entity_type in type_to_code:
        return type_to_code[entity_type]

    # Try to find from entity_types
    entity_types = get_entity_types()
    entity_def = entity_types.get(entity_type)
    if entity_def:
        if field_name:
            return entity_def["field_codes"].get(field_name, entity_def["primary_code"])
        return entity_def["primary_code"]

    return 0


# =============================================================================
# BACKWARD COMPATIBILITY - Deprecated functions
# =============================================================================

_schema_cache = None
_classification_cache = None

def get_schema() -> Dict[str, Any]:
    """
    DEPRECATED: Use get_codes() for I/O objects and get_relationships() for edges.

    This loads schema.json for backward compatibility.
    """
    global _schema_cache
    if _schema_cache is None:
        try:
            with open(SCHEMA_FILE, 'r') as f:
                _schema_cache = json.load(f)
        except FileNotFoundError:
            # Build a minimal schema from codes.json + relationship.json
            _schema_cache = {
                "meta": {"version": "2.0-derived", "description": "Derived from codes.json + relationship.json"},
                "entity_types": get_entity_types(),
                "relationships": {
                    name: {
                        "description": rel.get("description", ""),
                        "from_types": rel.get("source_type") if isinstance(rel.get("source_type"), list) else [rel.get("source_type")],
                        "to_type": rel.get("target_type"),
                        "direction": "outgoing",
                    }
                    for name, rel in get_relationships().items()
                },
                "resources": {}
            }
    return _schema_cache


def get_output_classification() -> Dict[str, Any]:
    """
    DEPRECATED: Classification logic is now in OUTPUT_TO_CODE and OUTPUT_TO_RELATIONSHIP.

    Loads output_classification.json for backward compatibility.
    """
    global _classification_cache
    if _classification_cache is None:
        try:
            with open(CLASSIFICATION_FILE, 'r') as f:
                _classification_cache = json.load(f)
        except FileNotFoundError:
            _classification_cache = {}
    return _classification_cache


def get_resources() -> Dict[str, Any]:
    """Get resource definitions from schema (deprecated)."""
    return get_schema().get("resources", {})


def get_field_codes() -> Dict[str, int]:
    """Build FIELD_CODES dict from codes.json."""
    codes = get_codes()
    result = {}
    for code_str, info in codes.get("codes", {}).items():
        result[info["name"]] = int(code_str)
    return result


def get_relationship_types() -> Dict[str, str]:
    """Build RELATIONSHIP_TYPES dict from relationship.json."""
    return {
        name: rel.get("description", name)
        for name, rel in get_relationships().items()
    }


# =============================================================================
# OUTPUT CLASSIFIER - Updated to use codes.json
# =============================================================================

@dataclass
class OutputClassification:
    """Result of classifying a source output field."""
    output_name: str
    category: str  # "relationship", "node", "attribute", "document", "complex", "unknown"

    # For relationships
    relationship_type: Optional[str] = None
    produces_entity: Optional[str] = None  # Entity type produced
    target_entity: Optional[str] = None  # Target of relationship
    direction: str = "normal"  # "normal" or "reverse"

    # For nodes
    entity_type: Optional[str] = None
    field_code: Optional[int] = None
    creates_relationship: Optional[str] = None  # Relationship to parent entity

    # For attributes
    attribute_of: Optional[str] = None

    # Properties this output carries
    properties: List[str] = field(default_factory=list)


class OutputClassifier:
    """
    Classifies source output fields into their correct category.

    Uses codes.json and OUTPUT_TO_CODE/OUTPUT_TO_RELATIONSHIP for classification.

    Categories:
    - relationship: Produces edges (e.g., "company_officers" -> officer_of relationship)
    - node: Produces separate nodes (e.g., "company_address" -> address node + has_address edge)
    - attribute: Properties of the main entity (e.g., "incorporation_date" -> company attribute)
    - document: Document/filing references (metadata)
    - complex: Nested data requiring decomposition
    - unknown: Not classified
    """

    def __init__(self):
        self._cache: Dict[str, OutputClassification] = {}
        self._codes = get_codes()

        # Build reverse lookup: code name -> code info
        self._name_to_code: Dict[str, Dict] = {}
        for code_str, info in self._codes.get("codes", {}).items():
            self._name_to_code[info["name"]] = {"code": int(code_str), **info}

    def classify(self, output_name: str) -> OutputClassification:
        """Classify a single output field."""
        if output_name in self._cache:
            return self._cache[output_name]

        output_lower = output_name.lower()

        # Check if it maps to a relationship
        if output_name in OUTPUT_TO_RELATIONSHIP:
            code = OUTPUT_TO_CODE.get(output_name)
            code_info = get_code_info(code) if code else {}
            rel_name = OUTPUT_TO_RELATIONSHIP[output_name]
            rel_info = get_relationship(rel_name)

            result = OutputClassification(
                output_name=output_name,
                category="relationship",
                relationship_type=rel_name,
                produces_entity=code_info.get("node_type"),
                target_entity=rel_info.get("target_type") if isinstance(rel_info.get("target_type"), str) else None,
                field_code=code,
            )
            self._cache[output_name] = result
            return result

        # Check if it maps to a code directly
        if output_name in OUTPUT_TO_CODE:
            code = OUTPUT_TO_CODE[output_name]
            code_info = get_code_info(code)

            if code_info.get("creates") == "node":
                result = OutputClassification(
                    output_name=output_name,
                    category="node",
                    entity_type=code_info.get("node_type"),
                    field_code=code,
                )
            else:
                result = OutputClassification(
                    output_name=output_name,
                    category="attribute",
                    field_code=code,
                    attribute_of=code_info.get("attaches_to"),
                )
            self._cache[output_name] = result
            return result

        # Check by code name
        if output_name in self._name_to_code:
            info = self._name_to_code[output_name]
            code = info["code"]

            if info.get("creates") == "node":
                result = OutputClassification(
                    output_name=output_name,
                    category="node",
                    entity_type=info.get("node_type"),
                    field_code=code,
                )
            elif info.get("creates") == "metadata":
                result = OutputClassification(
                    output_name=output_name,
                    category="attribute",
                    field_code=code,
                    attribute_of=info.get("attaches_to"),
                )
            else:
                result = OutputClassification(
                    output_name=output_name,
                    category="unknown",
                    field_code=code,
                )
            self._cache[output_name] = result
            return result

        # Unknown
        result = OutputClassification(
            output_name=output_name,
            category="unknown"
        )
        self._cache[output_name] = result
        return result

    def classify_all(self, outputs: List[str]) -> Dict[str, OutputClassification]:
        """Classify multiple outputs."""
        return {o: self.classify(o) for o in outputs}

    def get_relationships_from_outputs(self, outputs: List[str]) -> List[str]:
        """Get relationship types that will be produced from a list of outputs."""
        rels = []
        for o in outputs:
            c = self.classify(o)
            if c.category == "relationship" and c.relationship_type:
                rels.append(c.relationship_type)
            elif c.category == "node" and c.creates_relationship:
                rels.append(c.creates_relationship)
        return list(set(rels))

    def get_entity_types_from_outputs(self, outputs: List[str]) -> List[str]:
        """Get entity types that will be produced from a list of outputs."""
        types = []
        for o in outputs:
            c = self.classify(o)
            if c.category == "relationship" and c.produces_entity:
                if isinstance(c.produces_entity, list):
                    types.extend(c.produces_entity)
                else:
                    types.append(c.produces_entity)
            elif c.category == "node" and c.entity_type:
                types.append(c.entity_type)
        return list(set(types))


# Singleton classifier
_classifier = None

def get_classifier() -> OutputClassifier:
    """Get singleton OutputClassifier instance."""
    global _classifier
    if _classifier is None:
        _classifier = OutputClassifier()
    return _classifier


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class MappedEntity:
    """
    A node in the graph.

    - entity_type: The type (person, company, domain, email, etc.)
    - entity_code: The numeric field code from codes.json
    - value: The actual value
    - properties: Attributes OF this entity (not relationships)
    """
    entity_type: str
    entity_code: int
    value: Any
    properties: Dict[str, Any] = field(default_factory=dict)
    source_module: str = ""
    source_resource: str = ""
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MappedEdge:
    """
    An edge in the graph connecting two nodes.

    - from_type/from_value: Source node
    - to_type/to_value: Target node
    - relationship: The relationship type (must be valid per relationship.json)
    - properties: Edge attributes
    """
    from_type: str
    from_value: Any
    to_type: str
    to_value: Any
    relationship: str
    properties: Dict[str, Any] = field(default_factory=dict)
    source_resource: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def is_valid(self) -> bool:
        """Check if this edge is valid per relationship.json."""
        return validate_relationship(self.relationship, self.from_type, self.to_type)


@dataclass
class MappedOutput:
    """Result of mapping a resource output."""
    resource: str  # Resource ID (e.g., "alldom_whois")
    module: str
    operation: str
    input_type: str
    input_value: str
    nodes: List[MappedEntity] = field(default_factory=list)
    edges: List[MappedEdge] = field(default_factory=list)
    output_codes: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resource": self.resource,
            "module": self.module,
            "operation": self.operation,
            "input_type": self.input_type,
            "input_value": self.input_value,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "output_codes": self.output_codes,
        }

    def validate(self) -> List[str]:
        """Validate all edges against relationship.json. Returns list of errors."""
        errors = []
        for edge in self.edges:
            if not edge.is_valid():
                errors.append(
                    f"Invalid edge: {edge.from_type} --{edge.relationship}--> {edge.to_type}"
                )
        return errors


# =============================================================================
# OUTPUT MAPPER
# =============================================================================

class OutputMapper:
    """Schema-driven mapper for module outputs."""

    def __init__(self):
        self.codes = get_codes()
        self.relationships = get_relationships()
        self.field_codes = get_field_codes()

    def get_resource_def(self, resource_id: str) -> Optional[Dict]:
        """Get resource definition (deprecated - from schema.json)."""
        return get_schema().get("resources", {}).get(resource_id)

    def create_node(self, entity_type: str, value: Any,
                    properties: Dict = None, resource: str = "") -> MappedEntity:
        """Create a node with proper field code from codes.json."""
        code = get_field_code(entity_type)
        return MappedEntity(
            entity_type=entity_type,
            entity_code=code,
            value=value,
            properties=properties or {},
            source_resource=resource,
        )

    def create_edge(self, from_type: str, from_value: Any,
                    to_type: str, to_value: Any,
                    relationship: str, properties: Dict = None,
                    resource: str = "") -> MappedEdge:
        """Create an edge. Validates against relationship.json."""
        edge = MappedEdge(
            from_type=from_type,
            from_value=from_value,
            to_type=to_type,
            to_value=to_value,
            relationship=relationship,
            properties=properties or {},
            source_resource=resource,
        )
        if not edge.is_valid():
            logger.warning(f"Invalid edge created: {from_type} --{relationship}--> {to_type}")
        return edge

    def process_output(self, output_name: str, value: Any,
                       context_entity: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a raw output from a source into nodes and edges.

        This is the NEW unified processing method that uses codes.json
        and relationship.json.

        Args:
            output_name: String name like "company_officers"
            value: The data value(s)
            context_entity: The entity this output relates to
                           {"type": "company", "value": "Acme Corp"}

        Returns:
            {
                "nodes": [{"type": "person", "name": "...", "code": 59, ...}],
                "edges": [{"type": "officer_of", "source": {...}, "target": {...}, ...}]
            }
        """
        result = {"nodes": [], "edges": []}

        # Get field code for this output
        code = OUTPUT_TO_CODE.get(output_name)
        if not code:
            # Try to find by exact code name
            code = get_code_by_name(output_name)

        if not code:
            return result  # Unknown output

        code_info = get_code_info(code)

        # If this code creates a node, create it
        if code_info.get("creates") in ("node", "node_list"):
            # Handle list values
            values = value if isinstance(value, list) else [value]

            for v in values:
                if not v:
                    continue

                # Extract name if dict
                if isinstance(v, dict):
                    node_value = v.get("name") or v.get("value") or str(v)
                    node_props = {k: val for k, val in v.items() if k not in ("name", "value")}
                else:
                    node_value = v
                    node_props = {}

                node = {
                    "type": code_info.get("node_type", "unknown"),
                    "value": node_value,
                    "code": code,
                    "properties": node_props,
                }
                result["nodes"].append(node)

                # If there's a relationship implied, create the edge
                rel_name = OUTPUT_TO_RELATIONSHIP.get(output_name)
                if rel_name and context_entity:
                    rel_info = get_relationship(rel_name)

                    # Determine edge direction
                    # Most relationships are: produced_entity -> context_entity
                    # e.g., person officer_of company
                    source_type = node["type"]
                    target_type = context_entity.get("type", "unknown")

                    edge = {
                        "type": rel_name,
                        "source": {"type": source_type, "value": node_value},
                        "target": {"type": target_type, "value": context_entity.get("value")},
                        "reified_code": rel_info.get("reified_code"),
                        "properties": node_props,
                    }
                    result["edges"].append(edge)

        elif code_info.get("creates") == "metadata":
            # This is an attribute - attach to context entity
            # Don't create separate nodes, just record the data
            pass

        return result

    # =========================================================================
    # ALLDOM WHOIS
    # =========================================================================

    def map_whois_result(self, result: Dict[str, Any], domain: str) -> MappedOutput:
        """Map WHOIS result using codes.json definitions."""
        resource = "alldom_whois"
        output = MappedOutput(
            resource=resource,
            module="alldom",
            operation="whois",
            input_type="domain",
            input_value=domain,
        )

        if not result or result.get("status") == "error":
            return output

        # Domain node
        domain_node = self.create_node("domain", domain, resource=resource)
        domain_node.properties["creation_date"] = result.get("creation_date")
        domain_node.properties["expiry_date"] = result.get("expiry_date")
        domain_node.properties["updated_date"] = result.get("updated_date")
        domain_node.properties["status"] = result.get("status_codes")
        domain_node.properties["privacy_protected"] = result.get("privacy_protected")
        output.nodes.append(domain_node)
        output.output_codes.append(domain_node.entity_code)

        # Registrar
        if result.get("registrar"):
            node = self.create_node("registrar", result["registrar"], resource=resource)
            output.nodes.append(node)
            output.output_codes.append(node.entity_code)
            output.edges.append(self.create_edge(
                "domain", domain, "registrar", result["registrar"],
                "registered_via", resource=resource
            ))

        # Registrant (person)
        if result.get("registrant_name") and not result.get("privacy_protected"):
            node = self.create_node("person", result["registrant_name"], resource=resource)
            output.nodes.append(node)
            output.output_codes.append(node.entity_code)
            output.edges.append(self.create_edge(
                "person", result["registrant_name"], "domain", domain,
                "registrant_of", resource=resource
            ))

        # Registrant (company)
        if result.get("registrant_org") and not result.get("privacy_protected"):
            node = self.create_node("company", result["registrant_org"], resource=resource)
            output.nodes.append(node)
            output.output_codes.append(node.entity_code)
            output.edges.append(self.create_edge(
                "company", result["registrant_org"], "domain", domain,
                "registrant_of", resource=resource
            ))

        # Registrant email
        if result.get("registrant_email") and not result.get("privacy_protected"):
            node = self.create_node("email", result["registrant_email"], resource=resource)
            output.nodes.append(node)
            output.output_codes.append(node.entity_code)
            # Email belongs to registrant
            registrant = result.get("registrant_name") or result.get("registrant_org")
            if registrant:
                registrant_type = "person" if result.get("registrant_name") else "company"
                output.edges.append(self.create_edge(
                    registrant_type, registrant, "email", result["registrant_email"],
                    "has_email", resource=resource
                ))

        # Nameservers
        for ns in result.get("name_servers", []) or []:
            node = self.create_node("nameserver", ns, resource=resource)
            output.nodes.append(node)
            output.output_codes.append(node.entity_code)
            output.edges.append(self.create_edge(
                "domain", domain, "nameserver", ns,
                "uses_nameserver", resource=resource
            ))

        # Historic records
        if result.get("mode") == "historic" and result.get("historic_records"):
            for record in result["historic_records"]:
                if record.get("registrant_name"):
                    node = self.create_node("person", record["registrant_name"], resource=resource)
                    node.properties["whois_date"] = record.get("updated_date")
                    output.nodes.append(node)
                    output.edges.append(self.create_edge(
                        "person", record["registrant_name"], "domain", domain,
                        "registrant_of", {"date": record.get("updated_date"), "historic": True},
                        resource=resource
                    ))
                if record.get("registrant_org"):
                    node = self.create_node("company", record["registrant_org"], resource=resource)
                    node.properties["whois_date"] = record.get("updated_date")
                    output.nodes.append(node)
                    output.edges.append(self.create_edge(
                        "company", record["registrant_org"], "domain", domain,
                        "registrant_of", {"date": record.get("updated_date"), "historic": True},
                        resource=resource
                    ))

        output.output_codes = list(set(output.output_codes))
        return output

    # =========================================================================
    # ALLDOM BACKLINKS
    # =========================================================================

    def map_backlinks_result(self, result: Dict[str, Any], domain: str) -> MappedOutput:
        """Map backlinks - incoming links TO this domain."""
        resource = "alldom_backlinks"
        output = MappedOutput(
            resource=resource,
            module="alldom",
            operation="backlinks",
            input_type="domain",
            input_value=domain,
        )

        if not result:
            return output

        # Target domain
        target_node = self.create_node("domain", domain, resource=resource)
        output.nodes.append(target_node)
        output.output_codes.append(target_node.entity_code)

        for link in result.get("backlinks", []):
            source_domain = link.get("source_domain") or link.get("domain")
            if not source_domain:
                continue

            source_node = self.create_node("domain", source_domain, resource=resource)
            output.nodes.append(source_node)

            # Edge: target domain has backlink FROM source domain
            output.edges.append(self.create_edge(
                "domain", domain, "domain", source_domain,
                "backlink_from",
                {"source_url": link.get("url"), "anchor_text": link.get("anchor_text")},
                resource=resource
            ))

        return output

    # =========================================================================
    # ALLDOM OUTLINKS
    # =========================================================================

    def map_outlinks_result(self, result: Dict[str, Any], domain: str) -> MappedOutput:
        """Map outlinks - outgoing links FROM this domain."""
        resource = "alldom_outlinks"
        output = MappedOutput(
            resource=resource,
            module="alldom",
            operation="outlinks",
            input_type="domain",
            input_value=domain,
        )

        if not result:
            return output

        source_node = self.create_node("domain", domain, resource=resource)
        output.nodes.append(source_node)
        output.output_codes.append(source_node.entity_code)

        for link in result.get("outlinks", []):
            target_domain = link.get("target_domain") or link.get("domain")
            if not target_domain:
                continue

            target_node = self.create_node("domain", target_domain, resource=resource)
            output.nodes.append(target_node)

            # Edge: source domain links TO target domain
            output.edges.append(self.create_edge(
                "domain", domain, "domain", target_domain,
                "links_to",
                {"source_url": link.get("url"), "anchor_text": link.get("anchor_text")},
                resource=resource
            ))

        return output

    # =========================================================================
    # ALLDOM DNS
    # =========================================================================

    def map_dns_result(self, result: Dict[str, Any], domain: str) -> MappedOutput:
        """Map DNS resolution results."""
        resource = "alldom_dns"
        output = MappedOutput(
            resource=resource,
            module="alldom",
            operation="dns",
            input_type="domain",
            input_value=domain,
        )

        if not result:
            return output

        domain_node = self.create_node("domain", domain, resource=resource)
        output.nodes.append(domain_node)
        output.output_codes.append(domain_node.entity_code)

        # A records
        for ip in result.get("a_records", []):
            ip_node = self.create_node("ip_address", ip, resource=resource)
            output.nodes.append(ip_node)
            output.output_codes.append(ip_node.entity_code)
            output.edges.append(self.create_edge(
                "domain", domain, "ip_address", ip,
                "resolves_to", resource=resource
            ))

        # NS records
        for ns in result.get("ns_records", []):
            ns_node = self.create_node("nameserver", ns, resource=resource)
            output.nodes.append(ns_node)
            output.output_codes.append(ns_node.entity_code)
            output.edges.append(self.create_edge(
                "domain", domain, "nameserver", ns,
                "uses_nameserver", resource=resource
            ))

        output.output_codes = list(set(output.output_codes))
        return output

    # =========================================================================
    # CORPORELLA
    # =========================================================================

    def map_corporella_result(self, result: Dict[str, Any], company_name: str,
                               jurisdiction: str = None) -> MappedOutput:
        """Map Corporella company result."""
        resource = "corporella_company"
        output = MappedOutput(
            resource=resource,
            module="corporella",
            operation="company_search",
            input_type="company",
            input_value=company_name,
        )

        if not result or result.get("status") == "error":
            return output

        # Company node
        company_node = self.create_node("company", company_name, resource=resource)
        company_node.properties["status"] = result.get("status")
        company_node.properties["incorporation_date"] = result.get("incorporation_date")
        company_node.properties["dissolution_date"] = result.get("dissolution_date")
        company_node.properties["company_type"] = result.get("company_type")
        output.nodes.append(company_node)
        output.output_codes.append(company_node.entity_code)

        # Address
        if result.get("address"):
            addr_node = self.create_node("address", result["address"], resource=resource)
            output.nodes.append(addr_node)
            output.output_codes.append(addr_node.entity_code)
            output.edges.append(self.create_edge(
                "company", company_name, "address", result["address"],
                "has_address", resource=resource
            ))

        # Country
        country = result.get("country") or jurisdiction
        if country:
            country_node = self.create_node("country", country, resource=resource)
            output.nodes.append(country_node)
            output.output_codes.append(country_node.entity_code)
            output.edges.append(self.create_edge(
                "company", company_name, "country", country,
                "registered_in", resource=resource
            ))

        # Officers
        for officer in result.get("officers", []):
            if not officer.get("name"):
                continue
            person_node = self.create_node("person", officer["name"], resource=resource)
            output.nodes.append(person_node)
            output.output_codes.append(person_node.entity_code)
            output.edges.append(self.create_edge(
                "person", officer["name"], "company", company_name,
                "officer_of",
                {"role": officer.get("role"), "appointed_date": officer.get("appointed_date")},
                resource=resource
            ))

        # Shareholders
        for sh in result.get("shareholders", []):
            if not sh.get("name"):
                continue
            sh_type = "company" if sh.get("type") in ["company", "corporate"] else "person"
            sh_node = self.create_node(sh_type, sh["name"], resource=resource)
            output.nodes.append(sh_node)
            output.output_codes.append(sh_node.entity_code)
            output.edges.append(self.create_edge(
                sh_type, sh["name"], "company", company_name,
                "shareholder_of",
                {"shares": sh.get("shares"), "percentage": sh.get("percentage")},
                resource=resource
            ))

        # Beneficial owners
        for bo in result.get("beneficial_owners", []):
            if not bo.get("name"):
                continue
            bo_node = self.create_node("person", bo["name"], resource=resource)
            output.nodes.append(bo_node)
            output.output_codes.append(bo_node.entity_code)
            output.edges.append(self.create_edge(
                "person", bo["name"], "company", company_name,
                "beneficial_owner_of",
                {"percentage": bo.get("percentage")},
                resource=resource
            ))

        # Parent/subsidiaries
        if result.get("parent_company"):
            parent_node = self.create_node("company", result["parent_company"], resource=resource)
            output.nodes.append(parent_node)
            output.edges.append(self.create_edge(
                "company", company_name, "company", result["parent_company"],
                "subsidiary_of", resource=resource
            ))

        for sub in result.get("subsidiaries", []):
            sub_name = sub if isinstance(sub, str) else sub.get("name")
            if sub_name:
                sub_node = self.create_node("company", sub_name, resource=resource)
                output.nodes.append(sub_node)
                output.edges.append(self.create_edge(
                    "company", sub_name, "company", company_name,
                    "subsidiary_of", resource=resource
                ))

        output.output_codes = list(set(output.output_codes))
        return output

    # =========================================================================
    # EYE-D
    # =========================================================================

    def map_eyed_result(self, result: Dict[str, Any], query: str,
                        query_type: str = "person") -> MappedOutput:
        """Map EYE-D OSINT result."""
        resource = f"eyed_{query_type}"
        output = MappedOutput(
            resource=resource,
            module="eyed",
            operation=f"{query_type}_search",
            input_type=query_type,
            input_value=query,
        )

        if not result or result.get("status") == "error":
            return output

        # Primary entity
        primary_node = self.create_node(query_type, query, resource=resource)
        output.nodes.append(primary_node)
        output.output_codes.append(primary_node.entity_code)

        # Emails
        for email in result.get("emails", []):
            email_node = self.create_node("email", email, resource=resource)
            output.nodes.append(email_node)
            output.output_codes.append(email_node.entity_code)
            output.edges.append(self.create_edge(
                query_type, query, "email", email,
                "has_email", resource=resource
            ))

        # Phones
        for phone in result.get("phones", []):
            phone_node = self.create_node("phone", phone, resource=resource)
            output.nodes.append(phone_node)
            output.output_codes.append(phone_node.entity_code)
            output.edges.append(self.create_edge(
                query_type, query, "phone", phone,
                "has_phone", resource=resource
            ))

        # Usernames
        for username in result.get("usernames", []):
            username_node = self.create_node("username", username, resource=resource)
            output.nodes.append(username_node)
            output.output_codes.append(username_node.entity_code)
            if query_type == "person":
                output.edges.append(self.create_edge(
                    "person", query, "username", username,
                    "has_username", resource=resource
                ))

        # Addresses
        for addr in result.get("addresses", []):
            addr_node = self.create_node("address", addr, resource=resource)
            output.nodes.append(addr_node)
            output.output_codes.append(addr_node.entity_code)
            output.edges.append(self.create_edge(
                query_type, query, "address", addr,
                "has_address", resource=resource
            ))

        # Employers
        for employer in result.get("employers", []):
            if not employer.get("name"):
                continue
            company_node = self.create_node("company", employer["name"], resource=resource)
            output.nodes.append(company_node)
            output.output_codes.append(company_node.entity_code)
            if query_type == "person":
                output.edges.append(self.create_edge(
                    "person", query, "company", employer["name"],
                    "employed_by", {"role": employer.get("role")},
                    resource=resource
                ))

        output.output_codes = list(set(output.output_codes))
        return output

    # =========================================================================
    # SANCTIONS
    # =========================================================================

    def map_sanctions_result(self, result: Dict[str, Any], query: str,
                             query_type: str = "person") -> MappedOutput:
        """Map OpenSanctions result."""
        resource = "opensanctions"
        output = MappedOutput(
            resource=resource,
            module="opensanctions",
            operation="sanctions_check",
            input_type=query_type,
            input_value=query,
        )

        if not result or result.get("status") == "error":
            return output

        matches = result.get("matches", []) or result.get("results", [])
        if not matches:
            return output

        # Query entity
        query_node = self.create_node(query_type, query, resource=resource)
        output.nodes.append(query_node)
        output.output_codes.append(query_node.entity_code)

        for match in matches:
            entity_type = match.get("schema", "").lower()
            if entity_type in ["legalentity", "organization"]:
                entity_type = "company"
            elif entity_type != "person":
                continue

            match_name = match.get("caption") or match.get("name")
            match_node = self.create_node(entity_type, match_name, resource=resource)
            match_node.properties["sanctions_programs"] = match.get("datasets", [])
            match_node.properties["entity_id"] = match.get("id")
            output.nodes.append(match_node)
            output.output_codes.append(match_node.entity_code)

            output.edges.append(self.create_edge(
                query_type, query, entity_type, match_name,
                "sanctioned_match",
                {"score": match.get("score"), "datasets": match.get("datasets", [])},
                resource=resource
            ))

        output.output_codes = list(set(output.output_codes))
        return output


# =============================================================================
# SINGLETON
# =============================================================================

_mapper = None

def get_mapper() -> OutputMapper:
    """Get singleton OutputMapper instance."""
    global _mapper
    if _mapper is None:
        _mapper = OutputMapper()
    return _mapper


__all__ = [
    # NEW: Canonical source access
    "get_codes",
    "get_code_info",
    "get_code_by_name",
    "get_code_type",
    "creates_node",
    "creates_metadata",
    "get_node_type",
    # Relationships
    "get_relationships",
    "get_relationship",
    "get_reified_code",
    "get_inverse_relationship",
    "validate_relationship",
    "get_valid_relationships_for",
    # Mappings
    "OUTPUT_TO_CODE",
    "OUTPUT_TO_RELATIONSHIP",
    # Entity types (derived)
    "get_entity_types",
    "get_field_code",
    "get_field_codes",
    "get_relationship_types",
    # DEPRECATED: Schema access
    "get_schema",
    "get_resources",
    "get_output_classification",
    # Output classification
    "OutputClassification",
    "OutputClassifier",
    "get_classifier",
    # Mapping classes
    "OutputMapper",
    "MappedEntity",
    "MappedEdge",
    "MappedOutput",
    # Singletons
    "get_mapper",
]
