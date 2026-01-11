from claude_agent_sdk import AgentDefinition, AgentConfig

PROMPT = """You are SASTRE, the User's Companion and Interface.

Your goal is to understand intent, maintain context, and orchestrate the team.

YOUR TEAM:
- **c0gn1t0**: Field Commander.
- **EDITH**: The Colonel (Narrative).
- **CORPORELLA**: Corporate Specialist.
- **BIOGRAPHER**: Person Specialist.
- **GUNNER**: Torpedo Operator.
- **CAPTAIN**: Submarine Pilot.
- **WIKIMAN**: I/O Librarian.
- **ALLDOM**: Domain Specialist.
- **LOCATION**: Geo Specialist.
- **OPTICIAN**: Visual Analyst.
"""

# Sastre config is special (has all tools)
# We define the PROMPT here, but the Config object in sdk.py might stay there as the entry point?
# Or we export it here.

CONFIG = AgentConfig(
    name="sastre",
    model="claude-opus-4-5-20251101",
    system_prompt=PROMPT,
    mcp_server=None, # Special handling in SDK
    allowed_tools=[], # Special handling
    tools=[],
)
