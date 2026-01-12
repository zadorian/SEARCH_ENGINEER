from claude_agent_sdk import AgentDefinition, AgentConfig

PROMPT = """You are WIKIMAN, the Keeper of the I/O Library.

You provide research advice and execute chain reactions.

CAPABILITIES:
1. **Matrix**: `TYPE=>[?]`
2. **Chain**: `chain:`
"""

DEFINITION = AgentDefinition(
    description="Keeper of the I/O Library - Research advice and chain execution.",
    prompt=PROMPT,
    tools=["mcp__nexus__execute"],
    model="sonnet",
)

CONFIG = AgentConfig(
    name="wikiman",
    model="claude-sonnet-4-5-20250929",
    system_prompt=PROMPT,
    mcp_server=None,
    allowed_tools=DEFINITION.tools,
    tools=[],
)
