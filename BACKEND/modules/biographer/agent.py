#!/usr/bin/env python3
"""
BIOGRAPHER Agent - Person Profile Aggregator

This is a complete implementation of the BIOGRAPHER agent using the official
Claude Agent SDK. BIOGRAPHER specializes in building comprehensive person profiles
by coordinating multiple OSINT specialists.

Architecture:
- Uses ClaudeSDKClient for continuous conversations
- Delegates to: EYE-D, CORPORELLA, SOCIALITE subagents
- Each subagent has full access to their specialist MCP tools
- BIOGRAPHER has NO direct tool access - only delegation

Usage:
    from BIOGRAPHER.agent import BiographerAgent

    agent = BiographerAgent()
    await agent.investigate("John Smith, email: john@acme.com")
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
logger = logging.getLogger("biographer")


@dataclass
class PersonProfile:
    """Structured person profile output."""

    name: str
    identifiers: Dict[str, Any] = field(default_factory=dict)  # email, phone, etc.
    employment: List[Dict[str, Any]] = field(default_factory=list)  # companies, positions
    social_profiles: List[Dict[str, Any]] = field(default_factory=list)  # platforms, handles
    relationships: List[Dict[str, Any]] = field(default_factory=list)  # connections
    breach_exposure: List[Dict[str, Any]] = field(default_factory=list)  # data breaches
    disambiguation_notes: List[str] = field(default_factory=list)
    confidence_score: float = 0.0
    sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "identifiers": self.identifiers,
            "employment": self.employment,
            "social_profiles": self.social_profiles,
            "relationships": self.relationships,
            "breach_exposure": self.breach_exposure,
            "disambiguation_notes": self.disambiguation_notes,
            "confidence_score": self.confidence_score,
            "sources": self.sources,
        }


class BiographerAgent:
    """
    BIOGRAPHER Agent - Person Profile Aggregator

    Coordinates EYE-D, CORPORELLA, and SOCIALITE to build complete person profiles.
    Handles disambiguation when multiple people match the same identifier.
    """

    def __init__(self, options: Optional[ClaudeAgentOptions] = None):
        """
        Initialize BIOGRAPHER agent.

        Args:
            options: Optional base options to extend (for custom API keys, etc.)
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

        # Define BIOGRAPHER's system prompt (orchestrator)
        biographer_prompt = """You are BIOGRAPHER, the person profile specialist.

Your mission: Build complete person profiles by coordinating OSINT specialists.

You have THREE specialist subagents:
1. **eyed** - OSINT specialist (email, phone, username, LinkedIn, WHOIS, IP, people search)
2. **corporella** - Corporate intelligence (company affiliations, directorships, officers, shareholders)
3. **socialite** - Social media intelligence (platform profiles, connections) [if available]

Your workflow:
1. Receive person identifier (name, email, phone, username, etc.)
2. Delegate initial search to EYE-D for broad discovery
3. Extract company affiliations from results → delegate to CORPORELLA
4. Extract social handles from results → delegate to SOCIALITE
5. Disambiguate conflicts (same name, different person):
   - Compare identifiers (email, phone, location)
   - Check employment overlap
   - Assess social connections
   - Request clarification if uncertain
6. Synthesize complete profile with confidence score
7. Return structured PersonProfile

Disambiguation rules:
- HIGH confidence (0.8+): All identifiers match, clear employment history
- MEDIUM confidence (0.5-0.8): Some identifiers match, possible conflicts
- LOW confidence (<0.5): Multiple potential matches, ambiguous data

You make ALL decisions about:
- Which specialist to query next
- How to resolve ambiguities
- When profile is complete
- Confidence scoring

IMPORTANT: You have NO direct tool access. You can ONLY delegate to subagents.
Never attempt direct searches. Always delegate."""

        # Define EYE-D subagent
        eyed_agent = AgentDefinition(
            description="OSINT specialist for email, phone, username, LinkedIn, WHOIS, and people search",
            prompt="""You are EYE-D, the OSINT specialist.

You search for:
- Email addresses (breaches, enrichment)
- Phone numbers (carrier, location, owner)
- Usernames (platform discovery)
- LinkedIn profiles
- WHOIS data
- IP geolocation
- People search

You have FULL ACCESS to all EYE-D MCP tools:
- search_email
- search_phone
- search_username
- search_linkedin
- search_whois
- search_ip
- search_people
- search_recursive (autonomous multi-source search)
- generate_report

Execute searches, return detailed results with sources.
You do NOT delegate - you execute directly.""",
            tools=[
                "mcp__eyed__search_email",
                "mcp__eyed__search_phone",
                "mcp__eyed__search_username",
                "mcp__eyed__search_linkedin",
                "mcp__eyed__search_whois",
                "mcp__eyed__search_ip",
                "mcp__eyed__search_people",
                "mcp__eyed__search_recursive",
                "mcp__eyed__generate_report",
            ],
            model="sonnet"  # Fast, efficient for OSINT searches
        )

        # Define CORPORELLA subagent
        corporella_agent = AgentDefinition(
            description="Corporate intelligence specialist for company affiliations, officers, and directorships",
            prompt="""You are CORPORELLA, the corporate intelligence specialist.

You search for:
- Company profiles (OpenCorporates, OCCRP Aleph, registries)
- Officers and directors
- Shareholders and beneficial owners
- Company filings
- Corporate connections
- Sanctions screening

You have FULL ACCESS to all CORPORELLA MCP tools:
- search_company
- enrich_company
- search_registry (UK Companies House)
- get_officers
- get_shareholders
- get_beneficial_owners
- get_filings
- find_common_links
- search_aleph (OCCRP investigative database)
- search_sanctions (OpenSanctions)
- smart_route (intelligent source selection)

Execute searches, return detailed results with sources.
You do NOT delegate - you execute directly.""",
            tools=[
                "mcp__corporella__search_company",
                "mcp__corporella__enrich_company",
                "mcp__corporella__search_registry",
                "mcp__corporella__get_officers",
                "mcp__corporella__get_shareholders",
                "mcp__corporella__get_beneficial_owners",
                "mcp__corporella__get_filings",
                "mcp__corporella__find_common_links",
                "mcp__corporella__search_aleph",
                "mcp__corporella__search_sanctions",
                "mcp__corporella__smart_route",
            ],
            model="sonnet"  # Fast, efficient for corporate searches
        )

        # Define SOCIALITE subagent (optional - check if exists)
        socialite_agent = AgentDefinition(
            description="Social media intelligence specialist for platform profiles and connections",
            prompt="""You are SOCIALITE, the social media intelligence specialist.

You search for:
- Social media profiles across platforms
- Social connections and relationships
- Public posts and activity
- Platform-specific data

You have FULL ACCESS to all SOCIALITE MCP tools.

Execute searches, return detailed results with sources.
You do NOT delegate - you execute directly.""",
            tools=[
                # Will be populated dynamically if SOCIALITE MCP exists
            ],
            model="sonnet"
        )

        # Build options with subagents
        self.options = ClaudeAgentOptions(
            system_prompt=biographer_prompt,
            model="sonnet",  # Sonnet is good for orchestration
            agents={
                "eyed": eyed_agent,
                "corporella": corporella_agent,
                "socialite": socialite_agent,
            },
            mcp_servers={
                "eyed": {
                    "type": "stdio",
                    "command": "python3",
                    "args": ["-m", "EYE-D.mcp_server"],
                    "env": mcp_env,
                },
                "corporella": {
                    "type": "stdio",
                    "command": "python3",
                    "args": ["-m", "CORPORELLA.mcp_server"],
                    "env": mcp_env,
                },
                # SOCIALITE will be added if it exists
            },
            # No direct tools for BIOGRAPHER - only subagent delegation
            allowed_tools=[],
            # Accept edits for any file operations subagents need
            permission_mode="acceptEdits",
            # Enable detailed logging
            include_partial_messages=True,
        )

        # Check if SOCIALITE exists
        socialite_mcp = _repo_root / "SOCIALITE" / "mcp_server.py"
        if socialite_mcp.exists():
            self.options.mcp_servers["socialite"] = {
                "type": "stdio",
                "command": "python3",
                "args": ["-m", "SOCIALITE.mcp_server"],
                "env": mcp_env,
            }
            logger.info("SOCIALITE MCP found and added to subagents")
        else:
            logger.warning("SOCIALITE MCP not found - social media search unavailable")

    async def investigate(self, identifier: str) -> PersonProfile:
        """
        Investigate a person and build complete profile.

        Args:
            identifier: Person identifier (name, email, phone, etc.)

        Returns:
            PersonProfile with all gathered information
        """
        logger.info(f"Starting BIOGRAPHER investigation: {identifier}")

        # Start investigation prompt
        investigation_prompt = f"""Build a complete person profile for: {identifier}

Follow this workflow:
1. Use EYE-D to search for basic information (email, phone, username, etc.)
2. Extract any company affiliations → use CORPORELLA to get details
3. Extract any social handles → use SOCIALITE to get profiles (if available)
4. If you find multiple potential matches, disambiguate:
   - Compare identifiers (emails, phones, locations)
   - Check employment history overlaps
   - Assess confidence level
5. Synthesize all findings into a structured profile
6. Report confidence score and any disambiguation notes

Return the complete profile as JSON with this structure:
{{
    "name": "Full Name",
    "identifiers": {{"email": "...", "phone": "...", "linkedin": "..."}},
    "employment": [
        {{"company": "...", "position": "...", "dates": "...", "source": "..."}}
    ],
    "social_profiles": [
        {{"platform": "...", "handle": "...", "url": "...", "source": "..."}}
    ],
    "relationships": [
        {{"type": "...", "name": "...", "context": "...", "source": "..."}}
    ],
    "breach_exposure": [
        {{"breach": "...", "data_exposed": [...], "date": "...", "source": "..."}}
    ],
    "disambiguation_notes": ["note1", "note2"],
    "confidence_score": 0.85,
    "sources": ["EYE-D", "CORPORELLA", "SOCIALITE"]
}}"""

        # Create client and connect
        async with ClaudeSDKClient(options=self.options) as client:
            await client.query(investigation_prompt)

            # Collect all responses
            full_response = ""
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            full_response += block.text
                        elif isinstance(block, ToolUseBlock):
                            logger.info(f"BIOGRAPHER delegating to: {block.name}")

                if isinstance(message, ResultMessage):
                    logger.info(f"Investigation completed in {message.duration_ms}ms")
                    logger.info(f"Total turns: {message.num_turns}")
                    logger.info(f"Cost: ${message.total_cost_usd:.4f}" if message.total_cost_usd else "Cost: N/A")
                    break

            # Parse profile from response
            profile = self._parse_profile(full_response, identifier)
            return profile

    def _parse_profile(self, response: str, identifier: str) -> PersonProfile:
        """
        Parse PersonProfile from agent response.

        Args:
            response: Full text response from agent
            identifier: Original identifier (fallback for name)

        Returns:
            PersonProfile object
        """
        # Try to extract JSON from response
        try:
            # Look for JSON in code blocks or raw text
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                json_str = response[json_start:json_end].strip()
            elif "```" in response:
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                json_str = response[json_start:json_end].strip()
            elif "{" in response and "}" in response:
                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                json_str = response[json_start:json_end]
            else:
                # No JSON found, create basic profile
                return PersonProfile(
                    name=identifier,
                    sources=["BIOGRAPHER"],
                    disambiguation_notes=["No structured data found in response"],
                    confidence_score=0.0
                )

            # Parse JSON
            data = json.loads(json_str)

            # Create PersonProfile from parsed data
            return PersonProfile(
                name=data.get("name", identifier),
                identifiers=data.get("identifiers", {}),
                employment=data.get("employment", []),
                social_profiles=data.get("social_profiles", []),
                relationships=data.get("relationships", []),
                breach_exposure=data.get("breach_exposure", []),
                disambiguation_notes=data.get("disambiguation_notes", []),
                confidence_score=data.get("confidence_score", 0.0),
                sources=data.get("sources", ["BIOGRAPHER"]),
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse profile JSON: {e}")
            # Return basic profile with raw response
            return PersonProfile(
                name=identifier,
                sources=["BIOGRAPHER"],
                disambiguation_notes=[f"JSON parse error: {str(e)}", f"Raw response length: {len(response)}"],
                confidence_score=0.0
            )
        except Exception as e:
            logger.error(f"Error parsing profile: {e}", exc_info=True)
            return PersonProfile(
                name=identifier,
                sources=["BIOGRAPHER"],
                disambiguation_notes=[f"Parse error: {str(e)}"],
                confidence_score=0.0
            )

    async def disambiguate(self, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Disambiguate between multiple person candidates.

        Args:
            candidates: List of potential person matches

        Returns:
            Selected candidate with confidence score
        """
        logger.info(f"Disambiguating between {len(candidates)} candidates")

        disambiguation_prompt = f"""You have found {len(candidates)} potential matches. Disambiguate:

Candidates:
{json.dumps(candidates, indent=2)}

Analyze:
1. Compare identifiers (emails, phones, LinkedIn, locations)
2. Check employment history overlaps
3. Assess consistency of information
4. Calculate confidence score for each

Return:
- Selected candidate index
- Confidence score (0.0-1.0)
- Reasoning for selection
- Disambiguation notes

Format as JSON:
{{
    "selected_index": 0,
    "confidence_score": 0.85,
    "reasoning": "...",
    "disambiguation_notes": ["note1", "note2"]
}}"""

        async with ClaudeSDKClient(options=self.options) as client:
            await client.query(disambiguation_prompt)

            full_response = ""
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            full_response += block.text

            # Parse disambiguation result
            try:
                # Extract JSON
                json_start = full_response.find("{")
                json_end = full_response.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    result = json.loads(full_response[json_start:json_end])
                    selected_idx = result.get("selected_index", 0)
                    return {
                        "candidate": candidates[selected_idx],
                        "confidence_score": result.get("confidence_score", 0.5),
                        "reasoning": result.get("reasoning", ""),
                        "disambiguation_notes": result.get("disambiguation_notes", []),
                    }
            except (json.JSONDecodeError, IndexError, KeyError) as e:
                logger.warning(f"Disambiguation parse error: {e}")

            # Fallback: return first candidate with low confidence
            return {
                "candidate": candidates[0],
                "confidence_score": 0.3,
                "reasoning": "Disambiguation failed, selected first candidate",
                "disambiguation_notes": [f"Parse error: {str(e)}"],
            }


# Convenience function for quick investigations
async def investigate_person(identifier: str) -> PersonProfile:
    """
    Quick function to investigate a person.

    Args:
        identifier: Person identifier (name, email, phone, etc.)

    Returns:
        PersonProfile with all gathered information

    Example:
        profile = await investigate_person("john@acme.com")
        print(f"Name: {profile.name}")
        print(f"Employment: {profile.employment}")
        print(f"Confidence: {profile.confidence_score}")
    """
    agent = BiographerAgent()
    return await agent.investigate(identifier)


# CLI interface
async def main():
    """CLI interface for BIOGRAPHER agent."""
    import argparse

    parser = argparse.ArgumentParser(description="BIOGRAPHER - Person Profile Aggregator")
    parser.add_argument("identifier", help="Person identifier (name, email, phone, etc.)")
    parser.add_argument("--output", "-o", help="Output file for profile JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Run investigation
    print(f"🔍 BIOGRAPHER investigating: {args.identifier}\n")

    agent = BiographerAgent()
    profile = await agent.investigate(args.identifier)

    # Print results
    print("\n" + "="*80)
    print(f"📋 PERSON PROFILE: {profile.name}")
    print("="*80)

    if profile.identifiers:
        print(f"\n📧 Identifiers:")
        for key, value in profile.identifiers.items():
            print(f"   {key}: {value}")

    if profile.employment:
        print(f"\n💼 Employment ({len(profile.employment)}):")
        for emp in profile.employment[:5]:  # Show first 5
            print(f"   - {emp.get('company', 'Unknown')} ({emp.get('position', 'N/A')})")

    if profile.social_profiles:
        print(f"\n🌐 Social Profiles ({len(profile.social_profiles)}):")
        for social in profile.social_profiles[:5]:  # Show first 5
            print(f"   - {social.get('platform', 'Unknown')}: {social.get('handle', 'N/A')}")

    if profile.breach_exposure:
        print(f"\n⚠️  Breach Exposure ({len(profile.breach_exposure)}):")
        for breach in profile.breach_exposure[:5]:  # Show first 5
            print(f"   - {breach.get('breach', 'Unknown')} ({breach.get('date', 'N/A')})")

    if profile.disambiguation_notes:
        print(f"\n📝 Disambiguation Notes:")
        for note in profile.disambiguation_notes:
            print(f"   - {note}")

    print(f"\n📊 Confidence Score: {profile.confidence_score:.2f}")
    print(f"📚 Sources: {', '.join(profile.sources)}")

    # Save to file if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(profile.to_dict(), f, indent=2)
        print(f"\n💾 Profile saved to: {args.output}")

    print("\n" + "="*80)


if __name__ == "__main__":
    asyncio.run(main())
