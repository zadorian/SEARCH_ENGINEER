from typing import Dict, Any, List
from ..grid.assessor import EnhancedGridAssessor
from ..core.state import InvestigationState

async def narrative_assessment_handler(context: InvestigationState) -> Dict[str, Any]:
    """Run narrative-centric assessment."""
    assessor = EnhancedGridAssessor(context)
    assessment = assessor.narrative_mode()
    return {
        "unanswered": [n.question for n in assessment.unanswered],
        "partial": [n.question for n in assessment.partial],
        "gaps": [g.description for g in assessment.gaps]
    }

async def subject_assessment_handler(context: InvestigationState) -> Dict[str, Any]:
    """Run subject-centric assessment."""
    assessor = EnhancedGridAssessor(context)
    assessment = assessor.subject_mode()
    return {
        "incomplete_core": [e.name for e in assessment.incomplete_core],
        "incomplete_shell": [e.name for e in assessment.incomplete_shell],
        "needs_disambiguation": [e.name for e in assessment.needs_disambiguation],
        "gaps": [g.description for g in assessment.gaps]
    }

async def location_assessment_handler(context: InvestigationState) -> Dict[str, Any]:
    """Run location-centric assessment."""
    assessor = EnhancedGridAssessor(context)
    assessment = assessor.location_mode()
    return {
        "unchecked_sources": len(assessment.unchecked_sources),
        "gaps": [g.description for g in assessment.gaps]
    }

async def nexus_assessment_handler(context: InvestigationState) -> Dict[str, Any]:
    """Run nexus-centric assessment."""
    assessor = EnhancedGridAssessor(context)
    assessment = assessor.nexus_mode()
    return {
        "unconfirmed_connections": len(assessment.unconfirmed_connections),
        "gaps": [g.description for g in assessment.gaps]
    }

async def cross_pollinate_handler(context: InvestigationState) -> List[Dict[str, Any]]:
    """Run cross-pollination analysis."""
    assessor = EnhancedGridAssessor(context)
    actions = assessor.cross_pollinate()
    return [
        {
            "from": a.from_mode,
            "to": a.to_mode,
            "insight": a.insight,
            "action": a.action,
            "priority": a.priority.name
        }
        for a in actions
    ]

async def full_assessment_handler(context: InvestigationState) -> Dict[str, Any]:
    """Run full enhanced assessment."""
    assessor = EnhancedGridAssessor(context)
    assessment = assessor.full_assessment()
    priorities = assessor.get_priority_actions(assessment)
    
    return {
        "narrative_gaps": len(assessment.narrative.gaps),
        "subject_gaps": len(assessment.subject.gaps),
        "location_gaps": len(assessment.location.gaps),
        "nexus_gaps": len(assessment.nexus.gaps),
        "cross_pollinated_actions": len(assessment.cross_pollinated),
        "priority_actions": [
            {
                "type": a.type,
                "target": str(a.target),
                "reason": a.reason,
                "priority": a.priority.name
            }
            for a in priorities[:10] # Top 10
        ]
    }
