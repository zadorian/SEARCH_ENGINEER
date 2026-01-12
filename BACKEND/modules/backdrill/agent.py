#!/usr/bin/env python3
"""
BACKDRILL Agent - Archive Intelligence Expert

The ABSOLUTE EXPERT on all things archive search, version comparison, and
domain history. Uses Claude to provide intelligent analysis and summaries.

Capabilities:
- URL mapping with intelligent source selection
- Version comparison with semantic diff analysis
- Domain evolution tracking with change summarization
- Content change detection with context analysis
- C3 entity queries with result synthesis

This agent is designed to be called by SASTRE when archive intelligence
is needed for investigations.

Architecture:
- Uses Claude Agent SDK for AI-powered analysis
- Delegates raw operations to BACKDRILL MCP tools
- Synthesizes results into actionable intelligence

Usage:
    from modules.backdrill.agent import BackdrillAgent

    agent = BackdrillAgent()

    # Analyze domain evolution
    analysis = await agent.analyze_domain_history("example.com")

    # Compare periods with summary
    changes = await agent.compare_with_summary("example.com", "2020", "2024")

    # Find when content changed
    finding = await agent.find_content_timeline("example.com", "John Smith")
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
_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

# Import official Claude Agent SDK
try:
    from claude_agent_sdk import (
        ClaudeSDKClient,
        ClaudeAgentOptions,
        AgentDefinition,
        AssistantMessage,
        TextBlock,
        ToolUseBlock,
        ResultMessage,
    )
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False
    # Define dummy class for type hints
    class ClaudeAgentOptions: pass
    class ClaudeSDKClient: pass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backdrill-agent")


@dataclass
class ArchiveAnalysis:
    """Result of archive analysis."""
    domain: str
    analysis_type: str  # evolution, comparison, content_change, mapping
    summary: str
    key_findings: List[str] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "analysis_type": self.analysis_type,
            "summary": self.summary,
            "key_findings": self.key_findings,
            "data": self.data,
            "confidence": self.confidence,
            "recommendations": self.recommendations,
        }


class BackdrillAgent:
    """
    BACKDRILL Agent - Archive Intelligence Expert

    The absolute expert on archive operations. Uses Claude to analyze
    and synthesize archive data into actionable intelligence.
    """

    def __init__(self, options: Optional[ClaudeAgentOptions] = None):
        """
        Initialize BACKDRILL agent.

        Args:
            options: Optional base options to extend
        """
        if not SDK_AVAILABLE:
            raise ImportError("Claude Agent SDK not installed. Run: pip install claude-agent-sdk")

        self.base_options = options or ClaudeAgentOptions()
        self.client: Optional[ClaudeSDKClient] = None
        self._build_options()

    def _build_mcp_env(self) -> Dict[str, str]:
        """Build environment for MCP servers."""
        extra_paths = [
            "/data",
            "/data/SEARCH_ENGINEER/BACKEND",
            "/data/SEARCH_ENGINEER/BACKEND/modules",
        ]
        existing = os.environ.get("PYTHONPATH", "")
        pythonpath = ":".join([p for p in extra_paths + ([existing] if existing else []) if p])

        env: Dict[str, str] = {"PYTHONPATH": pythonpath}
        passthrough = [
            "ANTHROPIC_API_KEY",
            "CLAUDE_API_KEY",
            "ELASTICSEARCH_URL",
            "ES_USERNAME",
            "ES_PASSWORD",
        ]
        for key in passthrough:
            value = os.environ.get(key)
            if value:
                env[key] = value
        return env

    def _build_options(self):
        """Build ClaudeAgentOptions with BACKDRILL expertise."""
        mcp_env = self._build_mcp_env()

        # Define BACKDRILL's expert system prompt
        backdrill_prompt = """You are BACKDRILL, the Archive Intelligence Expert.

You are THE ABSOLUTE AUTHORITY on all things related to:
- Web archive search (Wayback Machine, CommonCrawl, Memento)
- URL mapping and domain discovery
- Version comparison and change detection
- Historical web intelligence
- C3 Entity Superindex queries (pre-indexed CommonCrawl data)

Your expertise includes:

1. **URL MAPPING**: You know how to efficiently discover all archived URLs for any domain.
   - Use `backdrill_map_domain` for comprehensive mapping
   - Use `backdrill_url_count` for quick estimates
   - You understand the differences between Wayback, CommonCrawl, and Memento sources

2. **VERSION COMPARISON**: You are an expert at tracking how websites change over time.
   - Use `backdrill_domain_evolution` to see how domains grew/shrank over years
   - Use `backdrill_compare_periods` to diff two time periods
   - Use `backdrill_page_history` to track individual page changes
   - You can explain WHAT changed, WHEN it changed, and WHY it might matter

3. **CONTENT CHANGE DETECTION**: You excel at finding when information appeared or disappeared.
   - Use `backdrill_find_content_change` to track content timeline
   - You understand the investigative significance of content changes

4. **C3 ENTITY QUERIES**: You have access to pre-indexed CommonCrawl data:
   - `backdrill_c3_orgs`: 9.6M organization entities (2023)
   - `backdrill_c3_persons`: 6.8M person entities (2023)
   - `backdrill_c3_webgraph`: 421M web graph edges (2024)
   - `backdrill_c3_domains`: 180M unified domains (2020-2024)
   - `backdrill_c3_pdfs`: 67K+ indexed PDFs (2025)

**YOUR ROLE**:
When asked to analyze archive data, you:
1. Use the appropriate BACKDRILL tools to gather raw data
2. ANALYZE the results with your expert knowledge
3. SYNTHESIZE findings into clear, actionable intelligence
4. EXPLAIN what the data means for the investigation
5. RECOMMEND next steps based on findings

**OUTPUT FORMAT**:
Always provide structured analysis with:
- **Summary**: One-paragraph overview of findings
- **Key Findings**: Bullet points of important discoveries
- **Data Context**: What the numbers/dates mean
- **Recommendations**: What to investigate next

You are called by SASTRE when archive intelligence is needed.
Be thorough, accurate, and insightful."""

        # Build options with BACKDRILL MCP server
        self.options = ClaudeAgentOptions(
            system_prompt=backdrill_prompt,
            model="sonnet",
            mcp_servers={
                "backdrill": {
                    "type": "stdio",
                    "command": "python3",
                    "args": ["-m", "modules.backdrill.mcp_server"],
                    "cwd": "/data/SEARCH_ENGINEER/BACKEND",
                    "env": mcp_env,
                }
            },
            allowed_tools=[
                "mcp__backdrill__backdrill_map_domain",
                "mcp__backdrill__backdrill_url_count",
                "mcp__backdrill__backdrill_snapshots",
                "mcp__backdrill__backdrill_domain_evolution",
                "mcp__backdrill__backdrill_compare_periods",
                "mcp__backdrill__backdrill_page_history",
                "mcp__backdrill__backdrill_find_content_change",
                "mcp__backdrill__backdrill_domain_snapshot",
                "mcp__backdrill__backdrill_c3_orgs",
                "mcp__backdrill__backdrill_c3_persons",
                "mcp__backdrill__backdrill_c3_webgraph",
                "mcp__backdrill__backdrill_c3_domains",
                "mcp__backdrill__backdrill_c3_pdfs",
                "mcp__backdrill__backdrill_c3_indices",
                "mcp__backdrill__backdrill_status",
            ],
            permission_mode="acceptEdits",
            include_partial_messages=True,
        )

    async def _execute_analysis(self, prompt: str) -> str:
        """Execute an analysis query and return the response."""
        full_response = ""

        async with ClaudeSDKClient(options=self.options) as client:
            await client.query(prompt)

            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            full_response += block.text
                        elif isinstance(block, ToolUseBlock):
                            logger.info(f"BACKDRILL using tool: {block.name}")

                if isinstance(message, ResultMessage):
                    logger.info(f"Analysis completed in {message.duration_ms}ms")
                    break

        return full_response

    def _parse_analysis(self, response: str, domain: str, analysis_type: str) -> ArchiveAnalysis:
        """Parse analysis response into structured result."""
        # Try to extract structured data if present
        data = {}
        if "```json" in response:
            try:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                data = json.loads(response[json_start:json_end].strip())
            except:
                pass

        # Extract key findings (bullet points)
        key_findings = []
        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("- ") or line.startswith("* "):
                key_findings.append(line[2:])
            elif line.startswith("• "):
                key_findings.append(line[2:])

        # Extract summary (first paragraph or up to Key Findings)
        summary = response
        if "**Key Findings**" in response:
            summary = response.split("**Key Findings**")[0]
        elif "Key Findings:" in response:
            summary = response.split("Key Findings:")[0]
        summary = summary.strip()[:1000]

        return ArchiveAnalysis(
            domain=domain,
            analysis_type=analysis_type,
            summary=summary,
            key_findings=key_findings[:10],
            data=data,
            confidence=0.85 if data else 0.7,
        )

    async def analyze_domain_history(self, domain: str) -> ArchiveAnalysis:
        """
        Comprehensive analysis of a domain's archive history.

        Args:
            domain: Target domain

        Returns:
            ArchiveAnalysis with evolution insights
        """
        prompt = f"""Analyze the complete archive history of: {domain}

Steps:
1. First use `backdrill_url_count` to get a quick estimate of archive coverage
2. Use `backdrill_domain_evolution` to see how the domain changed over time
3. Analyze the results and provide:
   - Summary of the domain's archive presence
   - Key milestones (when major changes happened)
   - Patterns in growth/decline
   - Notable pages added/removed
   - Recommendations for further investigation

Be thorough and insightful in your analysis."""

        response = await self._execute_analysis(prompt)
        return self._parse_analysis(response, domain, "evolution")

    async def compare_with_summary(
        self,
        domain: str,
        period1: str,
        period2: str,
    ) -> ArchiveAnalysis:
        """
        Compare two time periods with intelligent summarization.

        Args:
            domain: Target domain
            period1: First period (YYYY or YYYY-MM-DD)
            period2: Second period (YYYY or YYYY-MM-DD)

        Returns:
            ArchiveAnalysis with comparison insights
        """
        prompt = f"""Compare {domain} between {period1} and {period2}

Steps:
1. Use `backdrill_compare_periods` to get the raw comparison data
2. Analyze what changed:
   - How many URLs were added?
   - How many URLs were removed?
   - What types of pages changed?
   - Were there major structural changes?
3. Provide investigative insights:
   - What do these changes suggest about the organization?
   - Are there patterns (e.g., removing old content, adding new sections)?
   - What content disappearances might be significant?
4. Recommend follow-up:
   - Which specific pages deserve deeper investigation?
   - Should we examine content changes?

Be specific about what the changes mean."""

        response = await self._execute_analysis(prompt)
        return self._parse_analysis(response, domain, "comparison")

    async def find_content_timeline(
        self,
        domain: str,
        search_text: str,
    ) -> ArchiveAnalysis:
        """
        Find when specific content appeared or disappeared with analysis.

        Args:
            domain: Target domain
            search_text: Text to track

        Returns:
            ArchiveAnalysis with timeline insights
        """
        prompt = f"""Track when "{search_text}" appeared or disappeared on {domain}

Steps:
1. Use `backdrill_find_content_change` with change_type="appeared" to find first appearance
2. Use `backdrill_find_content_change` with change_type="disappeared" to find removal (if applicable)
3. Analyze the timeline:
   - When did this content first appear?
   - Was it ever removed?
   - What was the context (surrounding text)?
4. Provide investigative significance:
   - Why might this content have been added?
   - Why might it have been removed?
   - What does this tell us about the subject?
5. Recommend follow-up:
   - Other terms to search
   - Related pages to examine

Be thorough in your timeline analysis."""

        response = await self._execute_analysis(prompt)
        return self._parse_analysis(response, domain, "content_change")

    async def map_domain_with_insights(
        self,
        domain: str,
        focus_area: Optional[str] = None,
    ) -> ArchiveAnalysis:
        """
        Map domain URLs with intelligent categorization.

        Args:
            domain: Target domain
            focus_area: Optional area to focus on (e.g., "documents", "team", "products")

        Returns:
            ArchiveAnalysis with mapping insights
        """
        focus_instruction = ""
        if focus_area:
            focus_instruction = f"\nPay special attention to URLs related to: {focus_area}"

        prompt = f"""Map all archived URLs for {domain} and analyze the site structure
{focus_instruction}

Steps:
1. Use `backdrill_map_domain` to get all URLs
2. Categorize the URLs:
   - Document pages (PDFs, reports, filings)
   - Team/people pages
   - Product/service pages
   - News/blog posts
   - Contact information
3. Analyze coverage:
   - Which archive sources have the best coverage?
   - What time periods are well-archived?
   - Are there gaps in the archive history?
4. Identify high-value pages:
   - Which pages are most frequently archived?
   - Which might contain valuable information?
5. Provide recommendations:
   - Which specific URLs to examine in detail
   - Which time periods to focus on

Be specific about what you found."""

        response = await self._execute_analysis(prompt)
        return self._parse_analysis(response, domain, "mapping")

    async def search_c3_entities(
        self,
        query: str,
        entity_type: str = "all",
    ) -> ArchiveAnalysis:
        """
        Search C3 pre-indexed entities with synthesis.

        Args:
            query: Search query
            entity_type: "orgs", "persons", "all"

        Returns:
            ArchiveAnalysis with entity findings
        """
        prompt = f"""Search for "{query}" in C3 pre-indexed CommonCrawl data

Steps:
1. Based on entity_type="{entity_type}":
   - If "orgs" or "all": Use `backdrill_c3_orgs` to find organizations
   - If "persons" or "all": Use `backdrill_c3_persons` to find people
2. Analyze the results:
   - How many entities match?
   - What are the key entities found?
   - What websites mention them?
3. Cross-reference findings:
   - Are there connections between entities?
   - What industries/sectors are represented?
4. Provide synthesis:
   - Summary of who/what was found
   - Confidence in the matches
   - Potential false positives to filter out
5. Recommend follow-up:
   - Which entities deserve deeper investigation
   - Additional searches to run

Be specific about the entity findings."""

        response = await self._execute_analysis(prompt)
        return self._parse_analysis(response, query, "c3_search")

    async def analyze_backlinks(
        self,
        domain: str,
    ) -> ArchiveAnalysis:
        """
        Analyze domain backlinks from C3 web graph.

        Args:
            domain: Target domain

        Returns:
            ArchiveAnalysis with link analysis
        """
        prompt = f"""Analyze the backlink profile for {domain} using C3 web graph data

Steps:
1. Use `backdrill_c3_webgraph` with direction="inbound" to find who links TO this domain
2. Use `backdrill_c3_webgraph` with direction="outbound" to find who this domain links TO
3. Analyze the link profile:
   - What types of sites link to this domain?
   - Are there suspicious or noteworthy referring domains?
   - What does the outlink profile suggest about partnerships/affiliations?
4. Identify patterns:
   - Industry connections
   - Geographic patterns
   - Potentially related entities
5. Provide link intelligence:
   - High-value backlinks to investigate
   - Suspicious link patterns
   - Recommended domains to examine

Focus on investigative significance."""

        response = await self._execute_analysis(prompt)
        return self._parse_analysis(response, domain, "backlinks")


# Convenience functions for SASTRE integration
async def analyze_domain(domain: str) -> Dict[str, Any]:
    """Quick domain analysis for SASTRE."""
    agent = BackdrillAgent()
    result = await agent.analyze_domain_history(domain)
    return result.to_dict()


async def compare_periods(domain: str, period1: str, period2: str) -> Dict[str, Any]:
    """Quick period comparison for SASTRE."""
    agent = BackdrillAgent()
    result = await agent.compare_with_summary(domain, period1, period2)
    return result.to_dict()


async def find_content(domain: str, search_text: str) -> Dict[str, Any]:
    """Quick content search for SASTRE."""
    agent = BackdrillAgent()
    result = await agent.find_content_timeline(domain, search_text)
    return result.to_dict()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="BACKDRILL - Archive Intelligence Expert")
    parser.add_argument("command", choices=["analyze", "compare", "find", "map", "entities", "backlinks"])
    parser.add_argument("target", help="Domain or query")
    parser.add_argument("--period1", help="First period for comparison")
    parser.add_argument("--period2", help="Second period for comparison")
    parser.add_argument("--text", help="Text to search for")
    parser.add_argument("--focus", help="Focus area for mapping")
    parser.add_argument("--type", choices=["orgs", "persons", "all"], default="all")
    args = parser.parse_args()

    async def run():
        agent = BackdrillAgent()

        if args.command == "analyze":
            result = await agent.analyze_domain_history(args.target)
        elif args.command == "compare":
            if not args.period1 or not args.period2:
                print("Error: --period1 and --period2 required for compare")
                return
            result = await agent.compare_with_summary(args.target, args.period1, args.period2)
        elif args.command == "find":
            if not args.text:
                print("Error: --text required for find")
                return
            result = await agent.find_content_timeline(args.target, args.text)
        elif args.command == "map":
            result = await agent.map_domain_with_insights(args.target, focus_area=args.focus)
        elif args.command == "entities":
            result = await agent.search_c3_entities(args.target, entity_type=args.type)
        elif args.command == "backlinks":
            result = await agent.analyze_backlinks(args.target)

        print(json.dumps(result.to_dict(), indent=2))

    asyncio.run(run())
