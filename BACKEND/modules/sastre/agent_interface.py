import asyncio
import logging
from typing import Dict, Any, List

# Core Infrastructure
from ..orchestrator.investigation_engine import InvestigationOrchestrator
from ..orchestrator.graph import InvestigationGraph

# SASTRE Services (The new reasoning layer)
from .services.graph_assessor import GraphAssessor, Gap
from .services.disambiguation import DisambiguationService

logger = logging.getLogger(__name__)

class SastreAgent:
    """
    SASTRE Agent Interface.
    
    This is the "Brain" that drives the "Body" (InvestigationOrchestrator).
    It implements the OODA Loop:
    1. Observe (Load Graph)
    2. Orient (Assess Gaps, Disambiguate)
    3. Decide (Prioritize Gaps)
    4. Act (Call Orchestrator)
    """
    
    def __init__(self):
        self.orchestrator = InvestigationOrchestrator()
        self.assessor = GraphAssessor()
        self.disambiguator = DisambiguationService()
        self.graph = None 

    async def run_investigation(self, seed: str, max_iterations: int = 3) -> Dict[str, Any]:
        """
        Run a full autonomous investigation loop.
        """
        logger.info(f"SASTRE: Starting investigation on '{seed}'")
        
        # 1. INITIALIZE (Run initial search to populate graph)
        # We assume the Orchestrator's investigate() method returns the result including the graph.
        # But wait, Orchestrator.investigate() runs its OWN loop (depth/breadth).
        # We want to INTERCEPT that loop or Wrap it.
        # Ideally, we run Orchestrator with depth=1, then assess, then run again.
        
        # Iteration 1: Bootstrap
        result = await self.orchestrator.investigate(seed, depth=1)
        self.graph = result.graph
        
        for i in range(max_iterations - 1):
            logger.info(f"SASTRE: Iteration {i+2}/{max_iterations}")
            
            # 2. DISAMBIGUATE (Clean the data)
            merged = self.disambiguator.resolve_graph(self.graph)
            if merged > 0:
                logger.info(f"SASTRE: Merged {merged} entities")
            
            # 3. ASSESS (Find gaps)
            gaps = self.assessor.assess(self.graph)
            if not gaps:
                logger.info("SASTRE: No gaps found. Investigation complete.")
                break
                
            logger.info(f"SASTRE: Found {len(gaps)} gaps")
            
            # 4. DECIDE & ACT (Fill gaps)
            # We need to map Gaps -> Orchestrator Actions.
            # The Orchestrator exposes phases (search, extract, etc.) but via the `investigate` loop.
            # To be surgical, we might need to call specific phase methods or just run a new investigation
            # seeded with the gap target.
            
            await self._act_on_gaps(gaps)
            
        return {
            "graph": self.graph.to_dict(),
            "final_stats": self.graph.get_statistics()
        }

    async def _act_on_gaps(self, gaps: List[Gap]):
        """
        Translate gaps into Orchestrator calls.
        """
        # Sort by priority
        gaps.sort(key=lambda g: 0 if g.priority == "high" else 1)
        
        # Process top 5 gaps per iteration to avoid explosion
        for gap in gaps[:5]:
            logger.info(f"SASTRE: Fixing gap '{gap.gap_type}' for {gap.entity_value}")
            
            if gap.gap_type == "missing_officers":
                # Call Corporella via Orchestrator
                # Note: Orchestrator._corporate_phase expects a list of Entities.
                # We can construct a mini-list.
                entity = self.graph.get_entity(gap.entity_id)
                if entity:
                    await self.orchestrator._corporate_phase(self.graph, [entity])
                    
            elif gap.gap_type == "missing_backlinks":
                # Call Linklater
                entity = self.graph.get_entity(gap.entity_id)
                if entity:
                    await self.orchestrator._link_phase(self.graph, [entity])
            
            elif gap.gap_type == "missing_email":
                # Call Brute search for email
                # We don't have a direct "find email" phase publicly exposed easily,
                # but we can run a search query.
                # Orchestrator._search_phase uses the frontier. 
                # We can manually trigger a search.
                pass # Placeholder for targeted search logic

    async def close(self):
        await self.orchestrator.close()
