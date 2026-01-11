from typing import Any, Dict, List, Optional
from ..sdk import Agent, Tool
from ..core.state import InvestigationState, InvestigationPhase
from ..tools import grid_tools, writer_tools

# Mined intelligence context injection
try:
    from ..mined_context import get_orchestrator_context, enrich_prompt
    MINED_CONTEXT_AVAILABLE = True
except ImportError:
    MINED_CONTEXT_AVAILABLE = False

# We need a way to dispatch to other agents.
# In a monolithic runner, the Orchestrator can just call the other agents directly
# or return a "Delegate" action.

BASE_SYSTEM_PROMPT = """You are the SASTRE Orchestrator (Opus 4.5).
Your job is to coordinate an autonomous investigation loop.

1. ASSESS: Use the Grid to assess current state from four perspectives.
2. PRIORITIZE: Compile priority actions from assessment.
3. DELEGATE: Assign actions to subagents (returned as tools/commands).
4. CHECK SUFFICIENCY: Can we answer the question?

You operate on the `InvestigationState`.

Tools available:
- assess_grid: Run full Grid assessment.
- check_sufficiency: Check if investigation is complete.
- delegate: Delegate a task to a subagent (io_executor, disambiguator, writer).

When delegating, be specific about the task.

IMPORTANT: Use mined intelligence to:
- Avoid dead-end queries (known failures for this jurisdiction)
- Predict related red flags from patterns found
- Choose optimal methodology based on similar past investigations
"""


def build_orchestrator_prompt(
    entity: str = None,
    entity_type: str = "company",
    jurisdiction: str = None,
    found_red_flags: List[str] = None
) -> str:
    """Build Orchestrator prompt enriched with mined intelligence."""
    if not MINED_CONTEXT_AVAILABLE or not jurisdiction:
        return BASE_SYSTEM_PROMPT

    context = get_orchestrator_context(
        entity=entity or "",
        entity_type=entity_type,
        jurisdiction=jurisdiction,
        found_red_flags=found_red_flags
    )
    return enrich_prompt(BASE_SYSTEM_PROMPT, context)


def create_orchestrator_agent(
    entity: str = None,
    entity_type: str = "company",
    jurisdiction: str = None,
    found_red_flags: List[str] = None
) -> Agent:
    """
    Create Orchestrator agent with optional mined intelligence injection.

    Args:
        entity: Entity being investigated
        entity_type: Type of entity (company/person)
        jurisdiction: Primary jurisdiction for mined context
        found_red_flags: Any red flags already found (for propagation)
    """
    # Build prompt with mined intelligence context
    prompt = build_orchestrator_prompt(entity, entity_type, jurisdiction, found_red_flags)

    return Agent(
        name="sastre_orchestrator",
        model="claude-opus-4-5-20251101",
        system_prompt=prompt,
        tools=[
            Tool(
                name="assess_grid",
                description="Run full Grid assessment",
                handler=grid_tools.full_assessment_handler
            ),
            # delegate and check_sufficiency will be handled by the runner loop
            # or implemented as tools that update state/return special signals
        ]
    )
