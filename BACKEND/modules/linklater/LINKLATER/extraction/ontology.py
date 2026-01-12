"""
Relationship Ontology Loader

Loads the authoritative relationship schema from:
    input_output/ontology/relationships.json

Provides dynamic filtering of relationship types based on entity types present
in the current extraction context.

This is the SINGLE SOURCE OF TRUTH for all relationship types in the system.
"""

import json
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional
from functools import lru_cache

# Find project root and ontology file
# Path: BACKEND/modules/LINKLATER/extraction/ontology.py
# Parents: extraction(1) -> LINKLATER(2) -> modules(3) -> BACKEND(4) -> drill-search-app(5)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
ONTOLOGY_PATH = PROJECT_ROOT / "input_output" / "ontology" / "relationships.json"


class RelationshipOntology:
    """
    Loads and indexes the relationship ontology for dynamic filtering.

    Usage:
        ontology = RelationshipOntology()

        # Get all relationship types valid between persons and companies
        rel_types = ontology.get_relationships_for_entity_types({"person", "company"})

        # Generate prompt text for Haiku
        prompt_section = ontology.generate_prompt_section({"person", "company"})
    """

    def __init__(self):
        self.raw_ontology: Dict = {}
        self.all_edges: List[Dict] = []
        self.all_relations: Set[str] = set()

        # Index: (source_type, target_type) -> [relationship_types]
        self.type_pair_index: Dict[Tuple[str, str], List[Dict]] = {}

        # Index: entity_type -> [relationship_defs where type can be source or target]
        self.entity_type_index: Dict[str, List[Dict]] = {}

        self._load_ontology()
        self._build_indexes()

    def _load_ontology(self):
        """Load relationships.json from the project ontology directory."""
        if not ONTOLOGY_PATH.exists():
            raise FileNotFoundError(
                f"Ontology file not found at {ONTOLOGY_PATH}. "
                "This file is required for relationship extraction."
            )

        with open(ONTOLOGY_PATH, 'r') as f:
            self.raw_ontology = json.load(f)

    def _build_indexes(self):
        """Build indexes for fast lookup by entity type pairs."""
        # Iterate through each node type's edge definitions
        for node_type, type_def in self.raw_ontology.items():
            if not isinstance(type_def, dict) or "edge_types" not in type_def:
                continue

            for edge_def in type_def.get("edge_types", []):
                rel_type = edge_def.get("relationship_type", "")
                source_types = edge_def.get("source_types", [])
                target_types = edge_def.get("target_types", [])

                if not rel_type:
                    continue

                self.all_relations.add(rel_type)

                # Build type pair index
                for src in source_types:
                    for tgt in target_types:
                        key = (src.lower(), tgt.lower())
                        if key not in self.type_pair_index:
                            self.type_pair_index[key] = []

                        edge_entry = {
                            "source": src.lower(),
                            "relation": rel_type,
                            "target": tgt.lower(),
                            "description": edge_def.get("description", ""),
                            "category": edge_def.get("category", ""),
                            "direction": edge_def.get("direction", "outgoing"),
                            "confidence_default": edge_def.get("confidence_default", 0.8),
                        }

                        # Avoid duplicates
                        if edge_entry not in self.type_pair_index[key]:
                            self.type_pair_index[key].append(edge_entry)
                            self.all_edges.append(edge_entry)

                # Build entity type index (for types that can be source)
                for src in source_types:
                    src_lower = src.lower()
                    if src_lower not in self.entity_type_index:
                        self.entity_type_index[src_lower] = []
                    self.entity_type_index[src_lower].append(edge_def)

                # Build entity type index (for types that can be target)
                for tgt in target_types:
                    tgt_lower = tgt.lower()
                    if tgt_lower not in self.entity_type_index:
                        self.entity_type_index[tgt_lower] = []
                    # Only add if not already there
                    if edge_def not in self.entity_type_index[tgt_lower]:
                        self.entity_type_index[tgt_lower].append(edge_def)

    def get_all_relations(self) -> List[str]:
        """Get all unique relationship type names."""
        return sorted(list(self.all_relations))

    def get_all_edges(self) -> List[Dict]:
        """Get all edge definitions as {source, relation, target} dicts."""
        return self.all_edges

    def get_relationships_between(self, source_type: str, target_type: str) -> List[Dict]:
        """
        Get valid relationship types between two specific entity types.

        Args:
            source_type: e.g., "person"
            target_type: e.g., "company"

        Returns:
            List of {source, relation, target, description} dicts
        """
        key = (source_type.lower(), target_type.lower())
        return self.type_pair_index.get(key, [])

    def get_relationships_for_entity_types(
        self,
        entity_types: Set[str],
        exclude_contact_edges: bool = True
    ) -> List[Dict]:
        """
        Get all valid relationship types for a set of entity types.

        This filters to only include relationships where BOTH source and target
        types are present in the provided set.

        Args:
            entity_types: Set of entity types present, e.g., {"person", "company"}
            exclude_contact_edges: If True, exclude has_email, has_phone, has_address
                                   (these are handled separately by regex/GLiNER)

        Returns:
            List of {source, relation, target, description} dicts
        """
        entity_types_lower = {t.lower() for t in entity_types}

        # Contact relations to exclude (handled by regex/GLiNER, not Haiku)
        contact_relations = {"has_email", "has_phone", "has_address"}

        valid_edges = []
        seen = set()  # Avoid duplicates

        for (src, tgt), edges in self.type_pair_index.items():
            # Only include if both source and target types are in our set
            if src in entity_types_lower and tgt in entity_types_lower:
                for edge in edges:
                    rel = edge["relation"]

                    # Skip contact edges if requested
                    if exclude_contact_edges and rel in contact_relations:
                        continue

                    # Dedupe by (source, relation, target)
                    key = (src, rel, tgt)
                    if key not in seen:
                        seen.add(key)
                        valid_edges.append(edge)

        return valid_edges

    def generate_prompt_section(
        self,
        entity_types: Set[str],
        exclude_contact_edges: bool = True
    ) -> str:
        """
        Generate the VALID RELATIONSHIP TYPES section for the Haiku prompt.

        Dynamically filters to only show relationship types relevant to the
        entity types present in the current extraction.

        Args:
            entity_types: Set of entity types present, e.g., {"person", "company"}
            exclude_contact_edges: Exclude has_email/phone/address

        Returns:
            Formatted string for the LLM prompt
        """
        edges = self.get_relationships_for_entity_types(
            entity_types,
            exclude_contact_edges=exclude_contact_edges
        )

        if not edges:
            return "No valid relationship types for the given entity types."

        lines = ["VALID RELATIONSHIP TYPES (use ONLY these):"]

        # Group by relation type for cleaner output
        by_relation: Dict[str, List[Dict]] = {}
        for edge in edges:
            rel = edge["relation"]
            if rel not in by_relation:
                by_relation[rel] = []
            by_relation[rel].append(edge)

        for rel_type in sorted(by_relation.keys()):
            edge_examples = by_relation[rel_type]
            # Get description from first example
            desc = edge_examples[0].get("description", "")

            # Build source->target examples
            pairs = [f"{e['source']}→{e['target']}" for e in edge_examples]
            pairs_str = ", ".join(sorted(set(pairs)))

            if desc:
                lines.append(f"- {rel_type}: {desc} ({pairs_str})")
            else:
                lines.append(f"- {rel_type}: ({pairs_str})")

        return "\n".join(lines)

    def is_valid_relation(self, relation: str) -> bool:
        """Check if a relation type exists in the ontology."""
        return relation.lower() in {r.lower() for r in self.all_relations}

    def is_valid_edge(
        self,
        source_type: str,
        relation: str,
        target_type: str
    ) -> bool:
        """
        Check if a specific edge (source_type, relation, target_type) is valid.
        """
        edges = self.get_relationships_between(source_type, target_type)
        return any(e["relation"].lower() == relation.lower() for e in edges)


# Singleton instance - loaded once at import time
_ontology_instance: Optional[RelationshipOntology] = None


def get_ontology() -> RelationshipOntology:
    """Get the singleton ontology instance."""
    global _ontology_instance
    if _ontology_instance is None:
        _ontology_instance = RelationshipOntology()
    return _ontology_instance


# Convenience functions
def get_valid_relations() -> List[str]:
    """Get all valid relationship types from the ontology."""
    return get_ontology().get_all_relations()


def get_valid_edges() -> List[Dict]:
    """Get all valid edge definitions from the ontology."""
    return get_ontology().get_all_edges()


def get_relationships_for_entity_types(
    entity_types: Set[str],
    exclude_contact_edges: bool = True
) -> List[Dict]:
    """Get valid relationships for a set of entity types."""
    return get_ontology().get_relationships_for_entity_types(
        entity_types,
        exclude_contact_edges
    )


def generate_prompt_section(
    entity_types: Set[str],
    exclude_contact_edges: bool = True
) -> str:
    """Generate prompt section for the given entity types."""
    return get_ontology().generate_prompt_section(
        entity_types,
        exclude_contact_edges
    )
