from ..sdk import Agent, Tool
from ..tools import io_tools

# Mined intelligence context injection
try:
    from ..mined_context import get_io_executor_context, enrich_prompt
    MINED_CONTEXT_AVAILABLE = True
except ImportError:
    MINED_CONTEXT_AVAILABLE = False

BASE_SYSTEM_PROMPT = """You are the IO Executor. You run investigations using existing infrastructure.

You receive tasks like:
- "Run query X against sources Y, Z"
- "Enrich entity X using routes Y, Z"
- "Check sources X in jurisdiction Y"

You use the IO Matrix via the `execute_macro` tool.

IMPORTANT: Check mined intelligence for dead ends before executing queries.
If a query is a known dead end, use arbitrage alternatives instead.
"""


def build_io_executor_prompt(jurisdiction: str = None, action_types: list = None) -> str:
    """Build IO Executor prompt enriched with mined intelligence."""
    if not MINED_CONTEXT_AVAILABLE or not jurisdiction:
        return BASE_SYSTEM_PROMPT

    context = get_io_executor_context(jurisdiction, action_types or [])
    return enrich_prompt(BASE_SYSTEM_PROMPT, context)


def create_io_executor_agent(jurisdiction: str = None, action_types: list = None) -> Agent:
    """
    Create IO Executor agent with optional mined intelligence injection.

    Args:
        jurisdiction: If provided, injects jurisdiction-specific dead ends and arbitrage routes
        action_types: List of action types to get arbitrage alternatives for
    """
    # Build prompt with mined intelligence context
    prompt = build_io_executor_prompt(jurisdiction, action_types)

    return Agent(
        name="io_executor",
        model="claude-opus-4-5-20251101",
        system_prompt=prompt,
        tools=[
            Tool(name="execute_macro", description="Execute investigation query", handler=io_tools.execute_macro_handler),
            Tool(name="expand_variations", description="Generate name variations", handler=io_tools.expand_variations_handler),
            Tool(name="check_source", description="Check source status", handler=io_tools.check_source_handler),
        ]
    )
