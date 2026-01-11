import logging
from typing import List, Tuple, Dict, Optional, Set
from ..orchestrator.graph import InvestigationGraph, Entity, EntityType, EdgeType

logger = logging.getLogger(__name__)

class DisambiguationService:
    """
    Service for resolving entity collisions within an InvestigationGraph.
    
    Implements FUSE/REPEL logic based on the "Physics of Identity".
    """
    
    def __init__(self):
        self.hard_identifiers = {
            "registration_number", "tax_id", "passport", "social_security", "vat_id"
        }

    def resolve_graph(self, graph: InvestigationGraph) -> int:
        """
        Scan the graph for collisions and resolve them.
        Returns the number of entities merged (FUSE operations).
        """
        collisions = self._detect_collisions(graph)
        merged_count = 0
        
        for entity_a_id, entity_b_id, reason, action in collisions:
            if action == "FUSE":
                self._fuse_entities(graph, entity_a_id, entity_b_id, reason)
                merged_count += 1
            elif action == "REPEL":
                self._repel_entities(graph, entity_a_id, entity_b_id, reason)
                
        return merged_count

    def _detect_collisions(self, graph: InvestigationGraph) -> List[Tuple[str, str, str, str]]:
        """
        Detect entity pairs that might be the same.
        Returns list of (id_a, id_b, reason, action) tuples.
        """
        collisions = []
        entities = list(graph.all_entities())
        checked_pairs = set()

        # O(N^2) comparison - acceptable for small graphs (<1000 nodes), 
        # for larger graphs we'd need a blocking strategy (e.g. by name hash)
        
        for i, entity_a in enumerate(entities):
            for entity_b in entities[i+1:]:
                # Only check same types
                if entity_a.type != entity_b.type:
                    continue
                    
                pair_key = tuple(sorted([entity_a.id, entity_b.id]))
                if pair_key in checked_pairs:
                    continue
                checked_pairs.add(pair_key)
                
                # Check logic
                action, reason = self._evaluate_pair(entity_a, entity_b)
                if action:
                    collisions.append((entity_a.id, entity_b.id, reason, action))
                    
        return collisions

    def _evaluate_pair(self, a: Entity, b: Entity) -> Tuple[Optional[str], str]:
        """
        Evaluate two entities for FUSE/REPEL/BINARY_STAR.
        """
        # 1. HARD IDENTIFIER CHECK (Strong Signal)
        # If they share a unique ID -> FUSE
        # If they have conflicting unique IDs -> REPEL
        for identifier in self.hard_identifiers:
            val_a = a.metadata.get(identifier) or a.enrichments.get(identifier)
            val_b = b.metadata.get(identifier) or b.enrichments.get(identifier)
            
            if val_a and val_b:
                if val_a == val_b:
                    return "FUSE", f"Shared {identifier}: {val_a}"
                else:
                    return "REPEL", f"Conflicting {identifier}: {val_a} vs {val_b}"

        # 2. NAME MATCH CHECK (Weak Signal)
        if self._names_match(a.value, b.value):
            # Same name, check context
            # Do they share any edges? (e.g. both officers of same company)
            # This requires access to graph structure, but here we just have entities.
            # We'll assume name match is a candidate for BINARY_STAR (Park) 
            # unless we find more evidence.
            
            # For now, let's be conservative: 
            # If strict name match and same type -> BINARY_STAR (needs human or query)
            # But if we want to auto-fuse purely on name (risky), we wouldn't do it here.
            pass
            
        return None, ""

    def _names_match(self, name_a: str, name_b: str) -> bool:
        """Fuzzy name matching."""
        return name_a.lower().strip() == name_b.lower().strip()

    def _fuse_entities(self, graph: InvestigationGraph, id_a: str, id_b: str, reason: str):
        """
        Merge entity B into entity A.
        """
        entity_a = graph.get_entity(id_a)
        entity_b = graph.get_entity(id_b)
        
        if not entity_a or not entity_b:
            return

        logger.info(f"FUSING {entity_b.value} -> {entity_a.value} ({reason})")

        # 1. Move edges from B to A
        edges_from = graph.get_edges_from(id_b)
        for edge in edges_from:
            # Create new edge from A to target
            graph.add_edge(
                entity_a.value, entity_a.type,
                graph.get_entity(edge.target_id).value, graph.get_entity(edge.target_id).type,
                edge.type,
                discovered_by=f"fuse:{edge.discovered_by}",
                metadata=edge.metadata
            )
            # (In a real DB we'd delete the old edge, here we just leave it or strictly remove it)

        edges_to = graph.get_edges_to(id_b)
        for edge in edges_to:
            # Create new edge from source to A
            graph.add_edge(
                graph.get_entity(edge.source_id).value, graph.get_entity(edge.source_id).type,
                entity_a.value, entity_a.type,
                edge.type,
                discovered_by=f"fuse:{edge.discovered_by}",
                metadata=edge.metadata
            )

        # 2. Merge metadata/enrichments
        entity_a.metadata.update(entity_b.metadata)
        entity_a.enrichments.update(entity_b.enrichments)
        
        # 3. Mark B as merged (soft delete or flag)
        entity_b.metadata["merged_into"] = id_a
        
        # In a strict graph impl, we might remove B from _entities, 
        # but InvestigationGraph doesn't support deletion easily.
        # We'll rely on "merged_into" flag for filters.

    def _repel_entities(self, graph: InvestigationGraph, id_a: str, id_b: str, reason: str):
        """
        Create a negative edge between A and B.
        """
        # InvestigationGraph doesn't have explicit negative edges in EdgeType enum yet.
        # We can use RELATED_TO with metadata={"negative": True} or similar.
        # Or ideally, add a DIFFERENT_FROM edge type.
        pass
