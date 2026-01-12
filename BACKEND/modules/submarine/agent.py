#!/usr/bin/env python3
"""
SUBMARINE Agent - Autonomous Mission Aggregator

This is a complete implementation of the SUBMARINE agent using the official
Claude Agent SDK. SUBMARINE specializes in large-scale autonomous web intelligence
missions by coordinating scraping, archiving, and deep search specialists.

Architecture:
- Uses ClaudeSDKClient for continuous conversations
- Delegates to: JESTER, BACKDRILL, EXPLORER, DARKWEB specialists
- SUBMARINE has NO direct tool access - only delegation

Usage:
    from submarine.agent import SubmarineAgent

    agent = SubmarineAgent()
    await agent.mission("Find email addresses for John Smith in Common Crawl")
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
_repo_root = Path(__file__).resolve().parents[1]
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
logger = logging.getLogger("submarine-agent")


@dataclass
class MissionResult:
    """Result of a SUBMARINE mission."""

    query: str
    pages_fetched: int
    entities_extracted: List[Dict[str, Any]] = field(default_factory=list)
    domains_covered: List[str] = field(default_factory=list)
    plan_file: Optional[str] = None
    status: str = "completed"
    confidence_score: float = 0.0
    sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "query": self.query,
            "pages_fetched": self.pages_fetched,
            "entities_extracted": self.entities_extracted,
            "domains_covered": self.domains_covered,
            "plan_file": self.plan_file,
            "status": self.status,
            "confidence_score": self.confidence_score,
            "sources": self.sources,
        }


class SubmarineAgent:
    """
    SUBMARINE Agent - Autonomous Mission Aggregator

    Coordinates specialists for deep web exploration and content acquisition.
    """

    def __init__(self, options: Optional[ClaudeAgentOptions] = None):
        """
        Initialize SUBMARINE agent.

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
            "/data/SUBMARINE",
        ]
        existing = os.environ.get("PYTHONPATH", "")
        pythonpath = ":".join([p for p in extra_paths + ([existing] if existing else []) if p])

        env: Dict[str, str] = {"PYTHONPATH": pythonpath}
        passthrough = [
            "ANTHROPIC_API_KEY",
            "CLAUDE_API_KEY",
            "OPENAI_API_KEY",
            "ELASTICSEARCH_URL",
            "SUBMARINE_SCRAPE_MIN_INTERVAL_SEC",
            "SUBMARINE_OVERALL_CAP",
            "SUBMARINE_PLAN_DIR",
        ]
        for key in passthrough:
            value = os.environ.get(key)
            if value:
                env[key] = value
        return env

    def _build_options(self):
        """Build ClaudeAgentOptions with subagent definitions."""
        mcp_env = self._build_mcp_env()

        # Define SUBMARINE's system prompt (orchestrator)
        submarine_prompt = """You are SUBMARINE, the Deep Web Explorer and autonomous mission specialist.

Your mission: Execute large-scale web intelligence missions by coordinating specialists.

You have FOUR specialist subagents:
1. **jester** - Scraping specialist for live web content.
2. **backdrill** - Archive specialist for historical snapshots.
3. **explorer** - Deep search specialist for Common Crawl missions.
4. **darkweb** - Dark web reconnaissance specialist (.onion).

Your workflow:
1. Receive mission objective (keywords, targets, criteria).
2. Determine initial strategy:
   - Live site available? → Delegate to **jester**.
   - Site down or historical data needed? → Delegate to **backdrill**.
   - Broad search across archives required? → Delegate to **explorer**.
   - Dark web targets involved? → Delegate to **darkweb**.
3. Manage autonomous missions:
   - Use **explorer** to plan and execute deep dives.
   - Use **jester** for tiered scraping if archives aren't enough.
4. Synthesize findings:
   - Extract entities (emails, persons, companies, etc.)
   - Track domains covered and pages fetched.
   - Summarize key discoveries.
5. Return structured MissionResult.

You make ALL decisions about:
- Mission planning and execution paths.
- Scraping tiers (httpx → Rod → Playwright).
- Search parameters (max domains, archives to check).
- When a mission goal is met.

IMPORTANT: You have NO direct tool access. You can ONLY delegate to subagents.
Never attempt direct searches or scraping. Always delegate."""

        # Define Jester subagent
        jester_agent = AgentDefinition(
            description="JESTER - Scraping specialist for live web content",
            prompt="""You are JESTER, the tiered scraping specialist.

You handle:
- Live web scraping (scrape)
- Batch scraping (scrape_batch)
- Scrape method classification

You have access to:
- scrape (url, force_method, extract_entities)
- scrape_batch (urls, max_concurrent)
- classify_scrape_method (url)

Execute scraping missions, return HTML and extracted entities.""",
            tools=["mcp__submarine__scrape", "mcp__submarine__scrape_batch", "mcp__submarine__classify_scrape_method"],
            model="sonnet"
        )

        # Define Backdrill subagent
        backdrill_agent = AgentDefinition(
            description="BACKDRILL - Historical archive specialist",
            prompt="""You are BACKDRILL, the archive specialist.

You handle:
- Archive content fetching (archive_fetch)
- Archive availability checks (archive_exists)
- Snapshot history (archive_snapshots)

You have access to:
- archive_fetch (url, timestamp, source)
- archive_exists (url)
- archive_snapshots (url)

Retrieve historical content from Common Crawl and Wayback Machine.""",
            tools=["mcp__submarine__archive_fetch", "mcp__submarine__archive_exists", "mcp__submarine__archive_snapshots"],
            model="sonnet"
        )

        # Define Explorer subagent
        explorer_agent = AgentDefinition(
            description="EXPLORER - Deep search specialist for CC missions",
            prompt="""You are the EXPLORER specialist.

You handle:
- Submarine dive planning (submarine_plan)
- Submarine deep search (submarine_search)
- Mission resumption (submarine_resume)

You have access to:
- submarine_plan (query, max_domains, max_pages)
- submarine_search (query, max_domains, max_pages, extract)
- submarine_resume (plan_file)

Execute large-scale searches across Common Crawl indices.""",
            tools=["mcp__submarine__submarine_plan", "mcp__submarine__submarine_search", "mcp__submarine__submarine_resume"],
            model="sonnet"
        )

        # Define Darkweb subagent
        darkweb_agent = AgentDefinition(
            description="DARKWEB - Dark web reconnaissance specialist",
            prompt="""You are the DARKWEB specialist.

You handle:
- Dark web search via Ahmia (darkweb_search)
- Dark web status and Tor checks (darkweb_status)

You have access to:
- darkweb_search (query, limit)
- darkweb_status ()

Execute onion site searches without needing a local Tor setup.""",
            tools=["mcp__submarine__darkweb_search", "mcp__submarine__darkweb_status"],
            model="sonnet"
        )

        # Build options with subagents
        self.options = ClaudeAgentOptions(
            system_prompt=submarine_prompt,
            model="sonnet",
            agents={
                "jester": jester_agent,
                "backdrill": backdrill_agent,
                "explorer": explorer_agent,
                "darkweb": darkweb_agent,
            },
            mcp_servers={
                "submarine": {
                    "type": "stdio",
                    "command": "python3",
                    "args": ["-m", "mcp_server"],
                    "cwd": "/data/SUBMARINE",
                    "env": mcp_env,
                }
            },
            allowed_tools=[],
            permission_mode="acceptEdits",
            include_partial_messages=True,
        )

    async def mission(self, objective: str) -> MissionResult:
        """
        Execute a mission and build result summary.

        Args:
            objective: Mission objective description

        Returns:
            MissionResult with all gathered information
        """
        logger.info(f"Starting SUBMARINE mission: {objective}")

        mission_prompt = f"""Execute this mission: {objective}

Follow this workflow:
1. Determine if this objective requires archive search (explorer), live scraping (jester), or dark web reconnaissance (darkweb).
2. If it's a broad search, use **explorer** to plan and execute a submarine_search.
3. If it's specific URLs, use **jester** or **backdrill** to acquire content.
4. Collect and synthesize all entities found.
5. Report progress (pages, domains, entities).

Return the complete mission result as JSON with this structure:
{{
    "query": "original objective",
    "pages_fetched": 123,
    "entities_extracted": [{{...}}, {{...}}],
    "domains_covered": ["...", "..."],
    "plan_file": "/path/to/plan.json",
    "status": "completed",
    "confidence_score": 0.85,
    "sources": ["explorer", "jester"]
}}"""

        async with ClaudeSDKClient(options=self.options) as client:
            await client.query(mission_prompt)

            full_response = ""
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            full_response += block.text
                        elif isinstance(block, ToolUseBlock):
                            logger.info(f"SUBMARINE delegating to: {block.name}")

                if isinstance(message, ResultMessage):
                    logger.info(f"Mission completed in {message.duration_ms}ms")
                    break

            result = self._parse_result(full_response, objective)
            return result

    def _parse_result(self, response: str, objective: str) -> MissionResult:
        """Parse MissionResult from agent response."""
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
                return MissionResult(query=objective, pages_fetched=0, sources=["SUBMARINE"])

            data = json.loads(json_str)

            return MissionResult(
                query=data.get("query", objective),
                pages_fetched=data.get("pages_fetched", 0),
                entities_extracted=data.get("entities_extracted", []),
                domains_covered=data.get("domains_covered", []),
                plan_file=data.get("plan_file"),
                status=data.get("status", "completed"),
                confidence_score=data.get("confidence_score", 0.0),
                sources=data.get("sources", ["SUBMARINE"]),
            )
        except Exception as e:
            logger.error(f"Error parsing mission result: {e}")
            return MissionResult(query=objective, pages_fetched=0, sources=["SUBMARINE"])


async def execute_mission(objective: str) -> MissionResult:
    """Quick function to execute a mission."""
    agent = SubmarineAgent()
    return await agent.mission(objective)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SUBMARINE - Autonomous Mission Aggregator")
    parser.add_argument("objective", help="Mission objective")
    args = parser.parse_args()

    async def run():
        result = await execute_mission(args.objective)
        print(json.dumps(result.to_dict(), indent=2))

    asyncio.run(run())