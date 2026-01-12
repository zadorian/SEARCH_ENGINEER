from claude_agent_sdk import AgentDefinition, AgentConfig

PROMPT = """You are PACMAN, the Extraction Planner.

You decide WHAT to extract and HOW (Pattern vs Haiku).

CAPABILITIES:
1. **Plan**: Analyze volume and target type.
2. **Mode**: Choose between `builtin` (cheap/fast) and `haiku` (smart/costly).
"""

DEFINITION = AgentDefinition(
    description="Extraction Planner - Decides extraction targets and modes.",
    prompt=PROMPT,
    tools=[], # PACMAN logic is internal to the Watcher system usually
    model="sonnet",
)

CONFIG = AgentConfig(
    name="pacman",
    model="claude-sonnet-4-5-20250929",
    system_prompt=PROMPT,
    mcp_server=None,
    allowed_tools=DEFINITION.tools,
    tools=[],
)
