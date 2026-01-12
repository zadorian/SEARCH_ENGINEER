from claude_agent_sdk import AgentDefinition, AgentConfig

PROMPT = """You are SOCIALITE, the Social Network Analyst.

You map social graphs and analyze influence.

CAPABILITIES:
1. **Graph**: `map_social_network`
2. **Influence**: `analyze_influence`
"""

DEFINITION = AgentDefinition(
    description="Social Network Analyst - Graphs and influence.",
    prompt=PROMPT,
    tools=[
        "mcp__socialite__map_social_network",
        "mcp__socialite__analyze_influence"
    ],
    model="sonnet",
)

CONFIG = AgentConfig(
    name="socialite",
    model="claude-sonnet-4-5-20250929",
    system_prompt=PROMPT,
    mcp_server=None,
    allowed_tools=DEFINITION.tools,
    tools=[],
)
