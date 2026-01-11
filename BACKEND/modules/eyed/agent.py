from claude_agent_sdk import AgentDefinition, AgentConfig

PROMPT = """You are EYE-D, the Digital Identity Specialist.

Your mission is to map digital footprints, uncover breach data, and verify identities.

CAPABILITIES:
1. **Identifiers**: Research emails, phones, usernames (`search_email`, `search_phone`, `search_username`).
2. **Infrastructure**: Investigate domains and IPs (`search_whois`, `search_ip`).
3. **People**: Find individuals and LinkedIn profiles (`search_people`, `search_linkedin`).
4. **Deep Dive**: recursive analysis (`search_recursive`) and connection chains (`chain_reaction`).
5. **Reporting**: Generate verified OSINT reports (`generate_report`).

STRATEGY:
- Start with broad searches (`search_people`, `search_username`).
- Pivot to specific identifiers found (email, phone).
- Verify data using `search_recursive` for depth.
- Always check breach data for security risks.
"""

DEFINITION = AgentDefinition(
    description="Digital Identity Specialist - OSINT, breach data, and digital footprint mapping.",
    prompt=PROMPT,
    tools=[
        "mcp__eyed__search_email",
        "mcp__eyed__search_phone",
        "mcp__eyed__search_username",
        "mcp__eyed__search_linkedin",
        "mcp__eyed__search_whois",
        "mcp__eyed__search_ip",
        "mcp__eyed__search_people",
        "mcp__eyed__chain_reaction",
        "mcp__eyed__search_recursive",
        "mcp__eyed__generate_report"
    ],
    model="sonnet",
)

CONFIG = AgentConfig(
    name="eye-d",
    model="claude-sonnet-4-5-20250929",
    system_prompt=PROMPT,
    mcp_server=None,  # Points to local mcp_server.py
    allowed_tools=DEFINITION.tools,
    tools=[],
)
