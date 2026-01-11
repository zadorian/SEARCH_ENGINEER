"""
SASTRE Query Lab Agent

Builds fused queries by matching knowns and testing unknowns.
"""

from ..sdk import Agent, Tool
from ..tools import query_lab_tools


SYSTEM_PROMPT = """You are the SASTRE Query Lab Agent.

You take intent + knowns/unknowns and construct fused queries.

Process:
1. MATCH: Correlate subject/location terms (overlap)
2. TEST: Add hypothesis terms (expected nexus)
3. FUSE: Combine with intent-selected operators

Return:
- Primary query
- Variations (free OR expansions)
"""


def create_query_lab_agent() -> Agent:
    return Agent(
        name="query_lab",
        model="claude-sonnet-4-5-20250929",
        system_prompt=SYSTEM_PROMPT,
        tools=[
            Tool(
                name="build_fused_query",
                description="Construct a fused query from intent and axes",
                handler=query_lab_tools.build_fused_query_handler,
            ),
        ],
    )
