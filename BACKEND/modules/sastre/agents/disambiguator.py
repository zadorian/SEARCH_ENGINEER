from ..sdk import Agent, Tool
from ..tools import disambig_tools

SYSTEM_PROMPT = """You are the Disambiguator. You resolve entity collisions.

When the same name appears in multiple sources, you determine:
- FUSE: Same person, merge attributes
- REPEL: Different people, keep separate
- BINARY_STAR: Can't tell yet, track both

Your process:
1. PASSIVE checks (automatic)
2. ACTIVE checks (wedge queries)
3. RESOLUTION (fuse/repel)
"""

def create_disambiguator_agent() -> Agent:
    return Agent(
        name="disambiguator",
        model="claude-opus-4-5-20251101",
        system_prompt=SYSTEM_PROMPT,
        tools=[
            Tool(name="check_passive_constraints", description="Check hard constraints", handler=disambig_tools.check_passive_constraints_handler),
            Tool(name="generate_wedge_queries", description="Generate wedge queries", handler=disambig_tools.generate_wedge_queries_handler),
            Tool(name="apply_resolution", description="Apply resolution decision", handler=disambig_tools.apply_resolution_handler),
        ]
    )
