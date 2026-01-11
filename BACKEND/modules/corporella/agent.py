from claude_agent_sdk import AgentDefinition, AgentConfig

PROMPT = """You are CORPORELLA, the Corporate Intelligence Engine.

Your mission is deep corporate due diligence.

CAPABILITIES:
1. **Search**: Find companies globally (`search_company`, `search_registry`).
2. **Enrich**: Full dossier with officers, shareholders, PSC (`enrich_company`).
3. **Officers**: Directors, secretaries (`get_officers`).
4. **Ownership**: Shareholders (`get_shareholders`) and UBOs (`get_beneficial_owners`).
5. **Filings**: Financials, annual returns (`get_filings`).
6. **Network**: Common links (`find_common_links`).

STRATEGY:
- Start with `enrich_company`.
- Use `search_registry` for official data.
"""

DEFINITION = AgentDefinition(
    description="Corporate Intelligence Engine - Deep due diligence, officers, shareholders, filings.",
    prompt=PROMPT,
    tools=[
        "mcp__corporella__search_company",
        "mcp__corporella__enrich_company",
        "mcp__corporella__search_registry",
        "mcp__corporella__get_officers",
        "mcp__corporella__get_shareholders",
        "mcp__corporella__get_beneficial_owners",
        "mcp__corporella__get_filings",
        "mcp__corporella__find_common_links",
        "mcp__nexus__execute",
    ],
    model="sonnet",
)

CONFIG = AgentConfig(
    name="corporella",
    model="claude-sonnet-4-5-20250929",
    system_prompt=PROMPT,
    mcp_server=None,
    allowed_tools=DEFINITION.tools,
    tools=[],
)
