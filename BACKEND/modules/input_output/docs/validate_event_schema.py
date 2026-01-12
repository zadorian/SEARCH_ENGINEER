#!/usr/bin/env python3
"""
Validate event schema consistency for templates, anchors, and event edges.
"""

import json
import sys
from pathlib import Path


def load_json(path: Path):
    with open(path, "r") as f:
        return json.load(f)


def main() -> int:
    io_root = Path(__file__).resolve().parents[1]
    schema_dir = io_root / "matrix" / "schema"
    ontology_dir = io_root / "ontology"

    nodes_spatial = load_json(schema_dir / "nodes_spatial.json")
    nodes_temporal = load_json(schema_dir / "nodes_temporal.json")
    event_templates = load_json(schema_dir / "event_templates.json")
    relationships = load_json(ontology_dir / "relationships_events.json")

    node_classes = set()
    for doc in (nodes_spatial, nodes_temporal):
        for node in (doc.get("nodes") or {}).values():
            cls = node.get("class")
            if cls:
                node_classes.add(cls)

    event_edges = set((relationships.get("event_edges") or {}).keys())
    seen_ids = set()
    errors = []

    for template in event_templates.get("event_templates", []):
        template_id = template.get("id")
        if not template_id:
            errors.append("template missing id")
            continue
        if template_id in seen_ids:
            errors.append(f"duplicate template id: {template_id}")
        seen_ids.add(template_id)

        anchors = template.get("anchors") or {}
        for anchor_name, anchor_def in anchors.items():
            cls = anchor_def.get("class")
            if not cls:
                errors.append(f"{template_id} anchor '{anchor_name}' missing class")
                continue
            if cls not in node_classes:
                errors.append(f"{template_id} anchor '{anchor_name}' class '{cls}' not in node schemas")

        roles = template.get("roles") or {}
        for role_name, role_def in roles.items():
            edge_type = role_def.get("edge_type")
            if not edge_type:
                errors.append(f"{template_id} role '{role_name}' missing edge_type")
                continue
            if edge_type not in event_edges:
                errors.append(f"{template_id} role '{role_name}' edge_type '{edge_type}' not in event_edges")

    if errors:
        print("Event schema validation failed:")
        for err in errors:
            print(f"- {err}")
        return 1

    print("Event schema validation ok.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
