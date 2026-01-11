#!/usr/bin/env python3
"""
ALLDOM Agent - Domain Intelligence Aggregator

This is a complete implementation of the ALLDOM agent using the official
Claude Agent SDK. ALLDOM specializes in building comprehensive domain profiles
by coordinating multiple domain intelligence specialists.

Architecture:
- Uses ClaudeSDKClient for continuous conversations
- Delegates to: LINKLATER, BACKDRILL, JESTER (MAPPER), EYE-D subagents
- ALLDOM has NO direct tool access - only delegation

Usage:
    from alldom.agent import AlldomAgent

    agent = AlldomAgent()
    await agent.investigate("example.com")
"""

import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add paths for imports
_repo_root = Path(__file__).resolve().parents[4]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

# Import official Claude Agent SDK
from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AgentDefinition,
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
    ResultMessage,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("alldom-agent")


@dataclass
class DomainProfile:
    """Structured domain profile output."""

    domain: str
    whois: Dict[str, Any] = field(default_factory=dict)
    dns: Dict[str, Any] = field(default_factory=dict)
    tech_stack: List[str] = field(default_factory=list)
    subdomains: List[str] = field(default_factory=list)
    backlinks: List[Dict[str, Any]] = field(default_factory=list)
    archive_history: List[Dict[str, Any]] = field(default_factory=list)
    entities_extracted: Dict[str, List[str]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    confidence_score: float = 0.0
    sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "domain": self.domain,
            "whois": self.whois,
            "dns": self.dns,
            "tech_stack": self.tech_stack,
            "subdomains": self.subdomains,
            "backlinks": self.backlinks,
            "archive_history": self.archive_history,
            "entities_extracted": self.entities_extracted,
            "metadata": self.metadata,
            "confidence_score": self.confidence_score,
            "sources": self.sources,
        }


class AlldomAgent:
    """
    ALLDOM Agent - Domain Intelligence Aggregator

    Coordinates specialists to build complete domain profiles.
    """

    def __init__(self, options: Optional[ClaudeAgentOptions] = None):
        """
        Initialize ALLDOM agent.

        Args:
            options: Optional base options to extend
        """
        self.base_options = options or ClaudeAgentOptions()
        self.client: Optional[ClaudeSDKClient] = None
        self._build_options()

    def _build_mcp_env(self) -> Dict[str, str]:
        """Build environment for MCP servers."""
        extra_paths = [
            "/data",
            "/data/CLASSES",
            "/data/SEARCH_ENGINEER/BACKEND",
            "/data/SEARCH_ENGINEER/BACKEND/modules",
        ]
        existing = os.environ.get("PYTHONPATH", "")
        pythonpath = ":".join([p for p in extra_paths + ([existing] if existing else []) if p])

        env: Dict[str, str] = {"PYTHONPATH": pythonpath}
        passthrough = [
            "ANTHROPIC_API_KEY",
            "CLAUDE_API_KEY",
            "OPENAI_API_KEY",
            "ELASTICSEARCH_URL",
        ]
        for key in passthrough:
            value = os.environ.get(key)
            if value:
                env[key] = value
        return env

    def _build_options(self):
        """Build ClaudeAgentOptions with subagent definitions."""
        mcp_env = self._build_mcp_env()

        # Define ALLDOM's system prompt (orchestrator)
        alldom_prompt = """You are ALLDOM, the domain intelligence specialist.

Your mission: Build complete domain profiles by coordinating specialized subagents.

You have FOUR specialist subagents:
1. **linklater** - Backlink and link analysis specialist.
2. **backdrill** - Historical archive specialist (Wayback, CommonCrawl).
3. **mapper** - Discovery specialist (subdomains, sitemaps, URL mapping).
4. **analyzer** - WHOIS, DNS, and Tech stack specialist.

Your workflow:
1. Receive target domain or URL.
2. Delegate WHOIS/DNS/Tech lookups to **analyzer** for basic footprint.
3. Delegate subdomain discovery to **mapper**.
4. Delegate link analysis to **linklater** for reputation and network mapping.
5. Delegate historical research to **backdrill** for temporal context.
6. Extract and synthesize:
   - Ownership and registration (WHOIS)
   - Infrastructure (DNS, IP)
   - Technology used (Tech stack)
   - Scale and structure (Subdomains, Sitemap)
   - Authority and network (Backlinks)
   - History and evolution (Archives)
7. Synthesize complete profile with confidence score.
8. Return structured DomainProfile.

You make ALL decisions about:
- Which specialist to query next.
- How to prioritize findings.
- When the profile is sufficiently complete.

IMPORTANT: You have NO direct tool access. You can ONLY delegate to subagents.
Never attempt direct searches. Always delegate."""

        # Define LinkLater subagent
        linklater_agent = AgentDefinition(
            description="Link analysis specialist for backlinks and referring domains",
            prompt="""You are LINKLATER, the link analysis specialist.

You analyze:
- Backlinks (referring pages)
- Referring domains
- Anchor text
- Link authority

You have access to:
- linklater_backlinks (syntax: ?bl !domain for fast domains, bl? !domain for rich pages)

Execute analysis, return detailed results.""",
            tools=["mcp__linklater__linklater_backlinks"],
            model="sonnet"
        )

        # Define Analyzer subagent (using ALLDOM MCP's tools)
        analyzer_agent = AgentDefinition(
            description="Analyzer - Footprint specialist for WHOIS, DNS, and Tech stack",
            prompt="""You are the Footprint Analyzer.

You perform:
- WHOIS lookups
- DNS records analysis
- Technology stack identification (tech!)
- Domain age calculation (age!)

You have access to:
- alldom_execute (operators: whois:, dns:, tech!, age!, ga!)

Execute lookups, return detailed results.""",
            tools=["mcp__alldom__alldom_execute"],
            model="sonnet"
        )

        # Define Mapper subagent (using ALLDOM MCP's tools)
        mapper_agent = AgentDefinition(
            description="Mapper - Discovery specialist for subdomains and URL mapping",
            prompt="""You are the MAPPER specialist.

You discover:
- Subdomains (sub!)
- Sitemaps (sitemap:)
- URL structures (map!)

You have access to:
- alldom_execute (operators: map!, sub!, sitemap:)

Execute discovery, return detailed results.""",
            tools=["mcp__alldom__alldom_execute"],
            model="sonnet"
        )

        # Define Backdrill subagent (using ALLDOM MCP's tools)
        backdrill_agent = AgentDefinition(
            description="Historical specialist for archive lookups",
            prompt="""You are BACKDRILL, the historical archive specialist.

You retrieve:
- Wayback Machine snapshots (wb:)
- CommonCrawl data (cc:)
- Historical content fetching (<-!)

You have access to:
- alldom_execute (operators: wb:, cc:, <-!)

Execute historical lookups, return temporal data.""",
            tools=["mcp__alldom__alldom_execute"],
            model="sonnet"
        )

        # Build options with subagents
        self.options = ClaudeAgentOptions(
            system_prompt=alldom_prompt,
            model="sonnet",
            agents={
                "linklater": linklater_agent,
                "analyzer": analyzer_agent,
                "mapper": mapper_agent,
                "backdrill": backdrill_agent,
            },
            mcp_servers={
                "linklater": {
                    "type": "stdio",
                    "command": "python3",
                    "args": ["-m", "SEARCH_ENGINEER.BACKEND.modules.linklater.mcp_server"],
                    "env": mcp_env,
                },
                "alldom": {
                    "type": "stdio",
                    "command": "python3",
                    "args": ["-m", "SEARCH_ENGINEER.BACKEND.modules.alldom.mcp_server"],
                    "env": mcp_env,
                },
            },
            allowed_tools=[],
            permission_mode="acceptEdits",
            include_partial_messages=True,
        )

    async def investigate(self, domain: str) -> DomainProfile:
        """
        Investigate a domain and build complete profile.

        Args:
            domain: Target domain

        Returns:
            DomainProfile with all gathered information
        """
        logger.info(f"Starting ALLDOM investigation: {domain}")

        investigation_prompt = f"""Build a complete domain profile for: {domain}

Follow this workflow:
1. Use **analyzer** to get WHOIS, DNS, and Tech stack.
2. Use **mapper** to discover subdomains and structure.
3. Use **linklater** to analyze backlinks and authority.
4. Use **backdrill** to check historical snapshots.
5. Synthesize all findings into a structured profile.

Return the complete profile as JSON with this structure:
{{
    "domain": "example.com",
    "whois": {{...}},
    "dns": {{...}},
    "tech_stack": ["...", "..."],
    "subdomains": ["...", "..."],
    "backlinks": [{{...}}, {{...}}],
    "archive_history": [{{...}}, {{...}}],
    "entities_extracted": {{"emails": [...], "persons": [...]}},
    "metadata": {{...}},
    "confidence_score": 0.9,
    "sources": ["analyzer", "mapper", "linklater", "backdrill"]
}}"""

        async with ClaudeSDKClient(options=self.options) as client:
            await client.query(investigation_prompt)

            full_response = ""
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            full_response += block.text
                        elif isinstance(block, ToolUseBlock):
                            logger.info(f"ALLDOM delegating to: {block.name}")

                if isinstance(message, ResultMessage):
                    logger.info(f"Investigation completed in {message.duration_ms}ms")
                    break

            profile = self._parse_profile(full_response, domain)
            return profile

    def _parse_profile(self, response: str, domain: str) -> DomainProfile:
        """Parse DomainProfile from agent response."""
        try:
            # Extract JSON
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                json_str = response[json_start:json_end].strip()
            elif "{" in response and "}" in response:
                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                json_str = response[json_start:json_end]
            else:
                return DomainProfile(domain=domain, sources=["ALLDOM"])

            data = json.loads(json_str)

            return DomainProfile(
                domain=data.get("domain", domain),
                whois=data.get("whois", {}),
                dns=data.get("dns", {}),
                tech_stack=data.get("tech_stack", []),
                subdomains=data.get("subdomains", []),
                backlinks=data.get("backlinks", []),
                archive_history=data.get("archive_history", []),
                entities_extracted=data.get("entities_extracted", {}),
                metadata=data.get("metadata", {}),
                confidence_score=data.get("confidence_score", 0.0),
                sources=data.get("sources", ["ALLDOM"]),
            )
        except Exception as e:
            logger.error(f"Error parsing domain profile: {e}")
            return DomainProfile(domain=domain, sources=["ALLDOM"])


async def investigate_domain(domain: str) -> DomainProfile:
    """Quick function to investigate a domain."""
    agent = AlldomAgent()
    return await agent.investigate(domain)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ALLDOM - Domain Intelligence Aggregator")
    parser.add_argument("domain", help="Target domain")
    args = parser.parse_args()

    async def run():
        profile = await investigate_domain(args.domain)
        print(json.dumps(profile.to_dict(), indent=2))

    asyncio.run(run())