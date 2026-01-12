#!/usr/bin/env python3
"""
Graph Persister - Deterministic node/edge creation from IO output codes.

Implements the PIVOT PRINCIPLE:
- If you can pivot from it (search FROM it), it's a NODE
- If it describes, it's METADATA on a node or edge

Uses output_graph_rules.json as the single source of truth.

The flow:
1. IOExecutor returns data with field codes
2. GraphPersister reads output_graph_rules.json
3. For each field code in data:
   - If node_creating_code → CREATE_NODE
   - If edge_creating_code → CREATE_EDGE
   - If metadata_code → SET_PROPERTY on node/edge
4. Persist to Elasticsearch (cymonides-1-{project_id})

For TORPEDO specifically:
1. Haiku extracts fields from scraped HTML
2. Field names get mapped to codes via field_name_to_code()
3. Codes trigger deterministic graph creation
4. If Haiku finds new fields → extend country JSON → reflect in output_graph_rules

Usage:
    persister = GraphPersister(project_id="abc123")
    ops = await persister.persist(io_result)
    # ops = [CreateNode(...), CreateEdge(...), SetProperty(...)]
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)

MATRIX_DIR = Path(__file__).parent


# =============================================================================
# GRAPH OPERATION TYPES
# =============================================================================

class GraphOpType(Enum):
    CREATE_NODE = "create_node"
    CREATE_EDGE = "create_edge"
    SET_PROPERTY = "set_property"
    RESOLVE_NODE = "resolve_node"  # Find existing or create


@dataclass
class GraphOperation:
    """A single graph operation to execute."""
    op_type: GraphOpType
    node_type: Optional[str] = None
    edge_type: Optional[str] = None
    source_node_id: Optional[str] = None
    target_node_id: Optional[str] = None
    label: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)
    field_code: int = 0
    confidence: float = 1.0
    source_url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "op_type": self.op_type.value,
            "node_type": self.node_type,
            "edge_type": self.edge_type,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "label": self.label,
            "properties": self.properties,
            "field_code": self.field_code,
            "confidence": self.confidence,
            "source_url": self.source_url,
        }


# =============================================================================
# FIELD NAME TO CODE MAPPER
# =============================================================================

class FieldCodeMapper:
    """
    Maps extracted field names to output codes.

    This is the bridge between:
    - Torpedo/Haiku extracted field names (e.g., "company_name", "oib", "directors")
    - Output codes in output_graph_rules.json (e.g., 13, 14, 58)

    The mapping is bidirectional and extensible.
    """

    def __init__(self):
        self._graph_rules = self._load_graph_rules()
        self._legend = self._graph_rules.get("legend", {})
        self._name_to_code = self._build_name_to_code_map()

    def _load_graph_rules(self) -> Dict:
        """Load output_graph_rules.json."""
        rules_path = MATRIX_DIR / "output_graph_rules.json"
        if not rules_path.exists():
            logger.warning(f"output_graph_rules.json not found at {rules_path}")
            return {}
        with open(rules_path) as f:
            return json.load(f)

    def _build_name_to_code_map(self) -> Dict[str, int]:
        """Build field_name → code mapping from legend."""
        mapping = {}

        # From legend in output_graph_rules.json
        for code_str, name in self._legend.items():
            try:
                code = int(code_str)
                mapping[name.lower()] = code
                # Also map without underscores
                mapping[name.lower().replace("_", "")] = code
            except ValueError:
                continue

        # Common aliases (extracted field names → standard codes)
        aliases = {
            # Company identifiers
            "company_name": 13,
            "name": 13,
            "company": 13,
            "company_reg_id": 14,
            "reg_id": 14,
            "registration_number": 14,
            "company_number": 14,
            "oib": 14,  # Croatian
            "mbs": 14,  # Croatian
            "pib": 14,  # Serbian
            "mb": 14,   # Serbian
            "ico": 14,  # Czech
            "krs": 14,  # Polish
            "vat_id": 15,
            "vat": 15,

            # Company metadata
            "status": 49,
            "company_status": 49,
            "incorporation_date": 50,
            "founded_date": 50,
            "founded": 50,
            "dissolution_date": 51,
            "company_type": 52,
            "type": 52,
            "legal_form": 52,
            "sic_code": 53,
            "industry": 53,
            "nkd": 53,  # Croatian industry code
            "activity": 53,

            # Contact
            "email": 44,
            "company_email": 44,
            "phone": 45,
            "company_phone": 45,
            "telephone": 45,
            "website": 46,
            "company_website": 46,
            "web": 46,
            "address": 47,
            "company_address": 47,
            "registered_address": 47,

            # Officers (composite)
            "officers": 58,
            "company_officers": 58,
            "directors": 58,
            "management": 58,
            "uprava": 58,  # Croatian

            # Officer details (within composite)
            "officer_name": 59,
            "director_name": 59,
            "zastupnik": 59,  # Croatian
            "officer_role": 60,
            "role": 60,
            "position": 60,
            "appointment_date": 61,
            "resignation_date": 62,

            # Beneficial owners (composite)
            "beneficial_owners": 66,
            "owners": 66,
            "vlasnik": 66,  # Croatian
            "owner_name": 67,
            "ownership_pct": 68,
            "ownership_percent": 68,

            # Shareholders (composite)
            "shareholders": 71,
            "shareholder_name": 72,
            "shareholder_company": 73,
            "shares": 76,
            "share_class": 77,

            # Financial
            "capital": 56,
            "share_capital": 56,
            "revenue": 54,
            "ukupni_prihodi": 54,  # Croatian
            "employees": 212,  # Custom code
            "broj_zaposlenih": 212,  # Croatian

            # Credit/Rating (custom)
            "credit_rating": 250,
            "bonitetna_ocena": 250,  # Serbian
            "bonitetna_ocjena": 250,  # Croatian
        }

        # Merge aliases (aliases take precedence for common names)
        for name, code in aliases.items():
            mapping[name.lower()] = code
            mapping[name.lower().replace("_", "")] = code

        return mapping

    def name_to_code(self, field_name: str) -> int:
        """Get code for a field name. Returns 0 if not found."""
        normalized = field_name.lower().strip().replace("-", "_").replace(" ", "_")
        return self._name_to_code.get(normalized, 0)

    def code_to_name(self, code: int) -> str:
        """Get canonical name for a code."""
        return self._legend.get(str(code), f"unknown_{code}")

    def is_node_creating(self, code: int) -> bool:
        """Check if this code creates a node."""
        node_codes = self._graph_rules.get("node_creating_codes", {})
        return str(code) in node_codes

    def is_edge_creating(self, code: int) -> bool:
        """Check if this code creates an edge."""
        edge_codes = self._graph_rules.get("edge_creating_codes", {})
        return str(code) in edge_codes

    def is_metadata(self, code: int) -> bool:
        """Check if this code is metadata."""
        metadata_codes = self._graph_rules.get("metadata_codes", {})
        return str(code) in metadata_codes

    def get_node_type(self, code: int) -> Optional[str]:
        """Get node type for a node-creating code."""
        node_codes = self._graph_rules.get("node_creating_codes", {})
        rule = node_codes.get(str(code), {})
        return rule.get("node_type")

    def get_edge_rule(self, code: int) -> Optional[Dict]:
        """Get edge creation rule for an edge-creating code."""
        edge_codes = self._graph_rules.get("edge_creating_codes", {})
        return edge_codes.get(str(code))

    def get_metadata_rule(self, code: int) -> Optional[Dict]:
        """Get metadata rule."""
        metadata_codes = self._graph_rules.get("metadata_codes", {})
        return metadata_codes.get(str(code))

    def get_composite_rule(self, code: int) -> Optional[Dict]:
        """Get composite rule for array fields like officers, shareholders."""
        composite_rules = self._graph_rules.get("composite_rules", {})
        return composite_rules.get(str(code))


# =============================================================================
# GRAPH PERSISTER
# =============================================================================

class GraphPersister:
    """
    Persists IOResult data to graph based on output_graph_rules.json.

    The PIVOT PRINCIPLE in action:
    - Node-creating codes (7, 13, 59, etc.) → Create nodes
    - Edge-creating codes (32, 44, 59, etc.) → Create edges between nodes
    - Metadata codes (49, 50, 60, etc.) → Properties on nodes/edges
    - Composite codes (58, 66, 71) → Iterate arrays, create nodes+edges per item
    """

    def __init__(self, project_id: str = None):
        self.project_id = project_id
        self.mapper = FieldCodeMapper()
        self._graph_rules = self.mapper._graph_rules
        self._created_nodes: Dict[str, str] = {}  # value → node_id

    def _generate_node_id(self, node_type: str, value: str, jurisdiction: str = None) -> str:
        """Generate deterministic node ID."""
        # Normalize value
        normalized = value.lower().strip()
        jur_part = f"_{jurisdiction.lower()}" if jurisdiction else ""
        return f"{node_type}{jur_part}_{hash(normalized) % 10000000:07d}"

    def _resolve_or_create_node(
        self,
        node_type: str,
        value: str,
        field_code: int,
        source_url: str,
        jurisdiction: str = None,
        properties: Dict = None
    ) -> Tuple[GraphOperation, str]:
        """
        Resolve existing node or create new one.
        Returns (operation, node_id).
        """
        node_id = self._generate_node_id(node_type, value, jurisdiction)

        # Check if we already created this node in this session
        cache_key = f"{node_type}:{value.lower()}"
        if cache_key in self._created_nodes:
            return None, self._created_nodes[cache_key]

        self._created_nodes[cache_key] = node_id

        op = GraphOperation(
            op_type=GraphOpType.RESOLVE_NODE,
            node_type=node_type,
            label=value,
            field_code=field_code,
            source_url=source_url,
            properties=properties or {},
        )
        op.properties["_node_id"] = node_id

        return op, node_id

    def process_field(
        self,
        field_name: str,
        value: Any,
        source_url: str,
        jurisdiction: str = None,
        parent_node_id: str = None,
        parent_node_type: str = None,
    ) -> List[GraphOperation]:
        """
        Process a single field and return graph operations.

        Args:
            field_name: Extracted field name (e.g., "company_name")
            value: Field value
            source_url: URL for attribution
            jurisdiction: Jurisdiction code
            parent_node_id: ID of parent node (for edges)
            parent_node_type: Type of parent node

        Returns:
            List of GraphOperations to execute
        """
        if value is None or value == "":
            return []

        ops = []
        code = self.mapper.name_to_code(field_name)

        if code == 0:
            # Unknown field - log but don't fail
            logger.debug(f"Unknown field: {field_name} (no code mapping)")
            return []

        # Check for composite (array) fields
        composite_rule = self.mapper.get_composite_rule(code)
        if composite_rule and isinstance(value, list):
            return self._process_composite(
                code, value, source_url, jurisdiction,
                parent_node_id, parent_node_type
            )

        # Node-creating code
        if self.mapper.is_node_creating(code):
            node_type = self.mapper.get_node_type(code)
            if node_type and isinstance(value, str):
                op, node_id = self._resolve_or_create_node(
                    node_type, value, code, source_url, jurisdiction
                )
                if op:
                    ops.append(op)

                # If we have a parent, create edge
                if parent_node_id and self.mapper.is_edge_creating(code):
                    edge_rule = self.mapper.get_edge_rule(code)
                    if edge_rule:
                        edge_op = GraphOperation(
                            op_type=GraphOpType.CREATE_EDGE,
                            edge_type=edge_rule.get("edge_type"),
                            source_node_id=node_id,
                            target_node_id=parent_node_id,
                            field_code=code,
                            source_url=source_url,
                        )
                        ops.append(edge_op)

        # Edge-creating code (without node)
        elif self.mapper.is_edge_creating(code) and parent_node_id:
            edge_rule = self.mapper.get_edge_rule(code)
            if edge_rule:
                # The edge source is the value, target is parent
                # Need to resolve the source node first
                source_type = edge_rule.get("source_type", "unknown")
                if isinstance(value, str):
                    _, source_id = self._resolve_or_create_node(
                        source_type, value, code, source_url, jurisdiction
                    )
                    edge_op = GraphOperation(
                        op_type=GraphOpType.CREATE_EDGE,
                        edge_type=edge_rule.get("edge_type"),
                        source_node_id=source_id,
                        target_node_id=parent_node_id,
                        field_code=code,
                        source_url=source_url,
                    )
                    ops.append(edge_op)

        # Metadata code
        elif self.mapper.is_metadata(code) and parent_node_id:
            meta_rule = self.mapper.get_metadata_rule(code)
            if meta_rule:
                prop_name = meta_rule.get("property", field_name)
                attach_to = meta_rule.get("attach_to")

                ops.append(GraphOperation(
                    op_type=GraphOpType.SET_PROPERTY,
                    source_node_id=parent_node_id,
                    field_code=code,
                    properties={prop_name: value},
                    source_url=source_url,
                ))

        return ops

    def _process_composite(
        self,
        code: int,
        items: List[Any],
        source_url: str,
        jurisdiction: str = None,
        parent_node_id: str = None,
        parent_node_type: str = None,
    ) -> List[GraphOperation]:
        """
        Process composite field (array of officers, shareholders, etc.).

        Each item in the array creates:
        1. A node (person or company)
        2. An edge to the parent (company)
        3. Metadata on the edge (role, shares, etc.)
        """
        ops = []
        composite_rule = self.mapper.get_composite_rule(code)

        if not composite_rule:
            return ops

        per_item_ops = composite_rule.get("per_item_operations", [])
        child_codes = composite_rule.get("child_codes", [])

        for item in items:
            if not isinstance(item, dict):
                # Simple string item
                item = {"name": item}

            item_ops = []
            item_node_id = None

            # Process each operation defined for composite items
            for op_def in per_item_ops:
                action = op_def.get("action")

                if action == "CREATE_NODE":
                    from_code = op_def.get("from_code")
                    node_type = op_def.get("type")

                    # Find the value for this code in item
                    field_name = self.mapper.code_to_name(from_code)
                    value = item.get(field_name) or item.get("name") or item.get("value")

                    if value:
                        op, node_id = self._resolve_or_create_node(
                            node_type, str(value), from_code, source_url, jurisdiction
                        )
                        if op:
                            item_ops.append(op)
                        item_node_id = node_id

                elif action == "CREATE_EDGE" and item_node_id and parent_node_id:
                    edge_type = op_def.get("type")
                    item_ops.append(GraphOperation(
                        op_type=GraphOpType.CREATE_EDGE,
                        edge_type=edge_type,
                        source_node_id=item_node_id,
                        target_node_id=parent_node_id,
                        field_code=code,
                        source_url=source_url,
                    ))

                elif action == "SET_EDGE_METADATA" and item_node_id:
                    metadata_codes = op_def.get("codes", [])
                    metadata = {}
                    for meta_code in metadata_codes:
                        meta_name = self.mapper.code_to_name(meta_code)
                        if meta_name in item:
                            rule = self.mapper.get_metadata_rule(meta_code)
                            prop_name = rule.get("property", meta_name) if rule else meta_name
                            metadata[prop_name] = item[meta_name]

                    if metadata:
                        item_ops.append(GraphOperation(
                            op_type=GraphOpType.SET_PROPERTY,
                            source_node_id=item_node_id,
                            target_node_id=parent_node_id,
                            field_code=code,
                            properties=metadata,
                            source_url=source_url,
                        ))

            ops.extend(item_ops)

        return ops

    def persist(
        self,
        data: Dict[str, Any],
        entity: str,
        entity_type: str,
        jurisdiction: str = None,
        source_url: str = "",
    ) -> List[GraphOperation]:
        """
        Process all fields in data and return graph operations.

        Args:
            data: Extracted data dict (field_name → value)
            entity: Primary entity value (e.g., "Podravka d.d.")
            entity_type: Type of primary entity (e.g., "company")
            jurisdiction: Jurisdiction code
            source_url: Source URL for attribution

        Returns:
            List of GraphOperations to execute
        """
        self._created_nodes = {}  # Reset cache
        ops = []

        # First, create the primary entity node
        primary_code = 13 if entity_type == "company" else 7  # company_name or person_name
        primary_op, primary_node_id = self._resolve_or_create_node(
            entity_type, entity, primary_code, source_url, jurisdiction
        )
        if primary_op:
            ops.append(primary_op)

        # Process all fields
        for field_name, value in data.items():
            field_ops = self.process_field(
                field_name=field_name,
                value=value,
                source_url=source_url,
                jurisdiction=jurisdiction,
                parent_node_id=primary_node_id,
                parent_node_type=entity_type,
            )
            ops.extend(field_ops)

        return ops

    async def persist_to_elastic(
        self,
        ops: List[GraphOperation],
        index_name: str = None,
    ) -> Dict[str, int]:
        """
        Execute graph operations against Elasticsearch.

        Returns stats: {"nodes_created": N, "edges_created": N, "properties_set": N}
        """
        if not index_name:
            index_name = f"cymonides-1-{self.project_id}" if self.project_id else "cymonides-1"

        stats = {"nodes_created": 0, "edges_created": 0, "properties_set": 0}

        # TODO: Implement actual Elasticsearch operations
        # For now, just count operations
        for op in ops:
            if op.op_type in (GraphOpType.CREATE_NODE, GraphOpType.RESOLVE_NODE):
                stats["nodes_created"] += 1
            elif op.op_type == GraphOpType.CREATE_EDGE:
                stats["edges_created"] += 1
            elif op.op_type == GraphOpType.SET_PROPERTY:
                stats["properties_set"] += 1

        logger.info(f"Graph persistence: {stats}")
        return stats


# =============================================================================
# CONVENIENCE FUNCTION FOR IO EXECUTOR
# =============================================================================

async def persist_io_result(
    io_result,  # IOResult from io_result.py
    project_id: str = None,
) -> Dict[str, int]:
    """
    Persist an IOResult to the graph.

    This is the main entry point for io_executor.py.

    Usage:
        from graph_persister import persist_io_result

        result = await executor.execute("COMPANY_OFFICERS", "Podravka", "HR")
        stats = await persist_io_result(result, project_id="abc123")
    """
    persister = GraphPersister(project_id=project_id)

    # Determine entity type from route_id
    entity_type = "company"
    if "PERSON" in io_result.route_id.upper():
        entity_type = "person"
    elif "DOMAIN" in io_result.route_id.upper():
        entity_type = "domain"

    ops = persister.persist(
        data=io_result.data,
        entity=io_result.entity,
        entity_type=entity_type,
        jurisdiction=io_result.jurisdiction,
        source_url=io_result.source_url,
    )

    return await persister.persist_to_elastic(ops)


# =============================================================================
# CLI FOR TESTING
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test graph persister")
    parser.add_argument("--test", action="store_true", help="Run test with sample data")
    args = parser.parse_args()

    if args.test:
        # Sample Croatian company data
        sample_data = {
            "company_name": "PODRAVKA d.d.",
            "oib": "18928523252",
            "mbs": "010006549",
            "status": "Aktivan",
            "address": "Ulica Ante Starčevića 32, Koprivnica",
            "founded_date": "01.10.1993",
            "employees": "3333",
            "revenue": "395.216.937,39",
            "phone": "048651144",
            "email": "tajnistvo@podravka.hr",
            "website": "www.podravka.hr",
            "directors": [
                {"name": "Martina Dalić", "role": "Predsjednica Uprave"},
                {"name": "Davor Doko", "role": "Član Uprave"},
            ],
            "owners": [
                {"name": "REPUBLIKA HRVATSKA", "ownership_pct": "16.68%"},
                {"name": "EASTERN CROATIA FUND", "ownership_pct": "10.52%"},
            ]
        }

        persister = GraphPersister(project_id="test")
        ops = persister.persist(
            data=sample_data,
            entity="PODRAVKA d.d.",
            entity_type="company",
            jurisdiction="HR",
            source_url="https://companywall.hr/podravka",
        )

        print(f"\n{'='*60}")
        print(f"GRAPH OPERATIONS: {len(ops)}")
        print(f"{'='*60}\n")

        for i, op in enumerate(ops, 1):
            print(f"{i}. {op.op_type.value.upper()}")
            if op.node_type:
                print(f"   Node Type: {op.node_type}")
            if op.edge_type:
                print(f"   Edge Type: {op.edge_type}")
            if op.label:
                print(f"   Label: {op.label}")
            if op.properties:
                print(f"   Properties: {op.properties}")
            print()
