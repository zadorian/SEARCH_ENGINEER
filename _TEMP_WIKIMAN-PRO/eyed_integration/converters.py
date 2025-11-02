"""
Data Format Converters
Converts WIKIMAN unified entity format to vis-network format for EYE-D
"""

from typing import Dict, List, Any


def unified_to_vis_node(entity: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert WIKIMAN unified entity to vis-network node

    WIKIMAN Entity Format:
    {
        "id": "person_123",
        "type": "person",
        "name": "John Smith",
        "properties": {...},
        "metadata": {...}
    }

    vis-network Node Format:
    {
        "id": "person_123",
        "label": "John Smith",
        "group": "person",
        "title": "Tooltip HTML",
        "data": {...}
    }
    """
    entity_type = entity.get("type", "unknown")
    entity_id = entity.get("id", "")
    name = entity.get("name", "Unknown")

    # Map entity type to vis-network group (for coloring/styling)
    type_mapping = {
        "person": "person",
        "company": "company",
        "address": "address",
        "document": "document",
        "email": "email",
        "phone": "phone",
        "website": "website"
    }

    group = type_mapping.get(entity_type, "unknown")

    # Create tooltip HTML
    properties = entity.get("properties", {})
    tooltip_lines = [f"<strong>{name}</strong>", f"<em>{entity_type}</em>"]

    for key, value in list(properties.items())[:5]:  # Show first 5 properties
        tooltip_lines.append(f"{key}: {value}")

    tooltip = "<br/>".join(tooltip_lines)

    # Build vis-network node
    node = {
        "id": entity_id,
        "label": name,
        "group": group,
        "title": tooltip,
        "data": {
            "type": entity_type,
            "properties": properties,
            "metadata": entity.get("metadata", {})
        }
    }

    return node


def unified_to_vis_edges(relationships: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert WIKIMAN unified relationships to vis-network edges

    WIKIMAN Relationship Format:
    {
        "from_id": "person_123",
        "to_id": "company_456",
        "type": "director_of",
        "properties": {...}
    }

    vis-network Edge Format:
    {
        "from": "person_123",
        "to": "company_456",
        "label": "director of",
        "arrows": "to",
        "data": {...}
    }
    """
    edges = []

    for relationship in relationships:
        from_id = relationship.get("from_id", "")
        to_id = relationship.get("to_id", "")
        rel_type = relationship.get("type", "related_to")

        # Format relationship type for display
        label = rel_type.replace("_", " ")

        edge = {
            "from": from_id,
            "to": to_id,
            "label": label,
            "arrows": "to",  # Directed edge
            "data": {
                "type": rel_type,
                "properties": relationship.get("properties", {}),
                "confidence": relationship.get("confidence", 1.0)
            }
        }

        edges.append(edge)

    return edges


def vis_to_unified_node(vis_node: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert vis-network node back to WIKIMAN unified entity format

    Useful for round-trip conversions and updates
    """
    node_id = vis_node.get("id", "")
    label = vis_node.get("label", "Unknown")
    node_data = vis_node.get("data", {})

    entity = {
        "id": node_id,
        "type": node_data.get("type", "unknown"),
        "name": label,
        "properties": node_data.get("properties", {}),
        "metadata": node_data.get("metadata", {})
    }

    return entity


def vis_to_unified_edge(vis_edge: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert vis-network edge back to WIKIMAN unified relationship format
    """
    edge_data = vis_edge.get("data", {})

    relationship = {
        "from_id": vis_edge.get("from", ""),
        "to_id": vis_edge.get("to", ""),
        "type": edge_data.get("type", "related_to"),
        "properties": edge_data.get("properties", {}),
        "confidence": edge_data.get("confidence", 1.0)
    }

    return relationship
