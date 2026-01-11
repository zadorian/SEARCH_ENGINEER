from typing import List, Dict, Any
from dataclasses import dataclass
from ..orchestrator.graph import InvestigationGraph, EntityType, EdgeType

@dataclass
class Gap:
    """A gap in the investigation that needs to be filled."""
    entity_id: str
    entity_value: str
    gap_type: str  # e.g., "missing_officers", "missing_email"
    priority: str  # "high", "medium", "low"
    suggested_action: str

class GraphAssessor:
    """
    Analyzes InvestigationGraph for completeness gaps.
    Implements the 'Grid Assessment' logic from SASTRE spec.
    """
    
    def assess(self, graph: InvestigationGraph) -> List[Gap]:
        """Run full assessment on the graph."""
        gaps = []
        gaps.extend(self._assess_companies(graph))
        gaps.extend(self._assess_people(graph))
        gaps.extend(self._assess_domains(graph))
        return gaps

    def _assess_companies(self, graph: InvestigationGraph) -> List[Gap]:
        """Check for missing corporate data."""
        gaps = []
        companies = graph.get_entities(entity_type=EntityType.COMPANY)
        
        for company in companies:
            # Check for officers
            edges = graph.get_edges_to(company.id)
            has_officers = any(
                e.type in [EdgeType.OFFICER_OF, EdgeType.DIRECTOR_OF] 
                for e in edges
            )
            
            if not has_officers:
                gaps.append(Gap(
                    entity_id=company.id,
                    entity_value=company.value,
                    gap_type="missing_officers",
                    priority="high",
                    suggested_action=f"Find officers for {company.value}"
                ))
                
        return gaps

    def _assess_people(self, graph: InvestigationGraph) -> List[Gap]:
        """Check for missing personal identifiers/contact info."""
        gaps = []
        people = graph.get_entities(entity_type=EntityType.PERSON)
        
        for person in people:
            # Check for email (via edge or metadata)
            # Simple check: do we have an edge to an EMAIL entity?
            edges = graph.get_edges_from(person.id)
            has_email = any(
                graph.get_entity(e.target_id).type == EntityType.EMAIL 
                for e in edges
            )
            
            if not has_email:
                gaps.append(Gap(
                    entity_id=person.id,
                    entity_value=person.value,
                    gap_type="missing_email",
                    priority="medium",
                    suggested_action=f"Find email for {person.value}"
                ))
                
        return gaps

    def _assess_domains(self, graph: InvestigationGraph) -> List[Gap]:
        """Check for missing link intelligence."""
        gaps = []
        domains = graph.get_entities(entity_type=EntityType.DOMAIN)
        
        for domain in domains:
            # Check if backlink analysis ran (via enrichment flag or edge presence)
            if "linklater" not in domain.enrichments:
                 gaps.append(Gap(
                    entity_id=domain.id,
                    entity_value=domain.value,
                    gap_type="missing_backlinks",
                    priority="medium",
                    suggested_action=f"Analyze backlinks for {domain.value}"
                ))
                
        return gaps
