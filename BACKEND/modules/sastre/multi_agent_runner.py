"""
SASTRE Multi-Agent Runner - Orchestrator → Investigator → Writer Flow

Coordinates multiple specialized agents in an investigation loop:

FLOW:
    ┌─────────────────────────────────────────────────────────────┐
    │                     ORCHESTRATOR (Opus 4.5)                  │
    │  Assess state → Identify gaps → Delegate → Check sufficiency │
    └─────────────────┬───────────────────────────────┬───────────┘
                      │                               │
         ┌────────────▼────────────┐     ┌───────────▼───────────┐
         │  INVESTIGATOR (Opus)    │     │    WRITER (Sonnet)    │
         │  execute() queries      │     │  stream_finding()     │
         │  via IO syntax          │     │  to document sections │
         └────────────┬────────────┘     └───────────────────────┘
                      │
         ┌────────────▼────────────┐
         │ DISAMBIGUATOR (Sonnet)  │
         │ FUSE / REPEL / BINARY   │
         │ (when collisions found) │
         └─────────────────────────┘

Usage:
    from SASTRE.multi_agent_runner import MultiAgentRunner, run_investigation

    runner = MultiAgentRunner(project_id="mycase")
    result = await runner.run("Investigate John Smith, CEO of Acme Corp")

    # Or use the convenience function:
    result = await run_investigation("Who is John Smith?", project_id="mycase")
"""

import os
import json
import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Awaitable
from datetime import datetime
from enum import Enum

from anthropic import AsyncAnthropic

from .sdk import (
    TOOLS, TOOL_HANDLERS, AGENT_CONFIGS,
    handle_execute, handle_assess, handle_get_watchers,
    handle_stream_finding, handle_resolve,
)
from .contracts import (
    KUQuadrant, SufficiencyResult,
    derive_quadrant, get_completeness,
)
from .user_config import is_auto_scribe_enabled

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sastre.runner")

# =============================================================================
# AUTO-SCRIBE CAPTURE RULES
# =============================================================================

# Tools that are control-plane or write-plane actions; capturing them as "findings"
# creates feedback loops and adds noise.
AUTO_SCRIBE_SKIP_TOOLS = {
    "assess",
    "get_watchers",
    "create_watcher",
    "stream_finding",
    "resolve",
    "toggle_auto_scribe",
    "edith_rewrite",
    "edith_answer",
    "edith_edit_section",
    "edith_template_ops",
    "torpedo_template",
    "query_lab_build",
}

_URL_RE = re.compile(r"https?://[^\\s\\]\\)\\}\\\"\\']+")


def _extract_url_candidates(tool_name: str, tool_input: Dict[str, Any], tool_output: Any) -> List[str]:
    candidates: List[str] = []

    if isinstance(tool_input, dict):
        for key in ("url", "source_url"):
            value = tool_input.get(key)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                candidates.append(value)

    try:
        blob = json.dumps({"tool": tool_name, "input": tool_input, "output": tool_output}, ensure_ascii=False, default=str)
        candidates.extend(_URL_RE.findall(blob))
    except Exception:
        pass

    # De-dupe while preserving order
    seen = set()
    unique: List[str] = []
    for url in candidates:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique[:8]


def _should_capture_tool_result(tool_name: str) -> bool:
    return tool_name not in AUTO_SCRIBE_SKIP_TOOLS

# =============================================================================
# TOOLSETS (multi-agent runner uses legacy tool schema)
# =============================================================================

AGENT_TOOLSETS: Dict[str, List[str]] = {
    "orchestrator": ["assess", "execute", "get_watchers", "stream_finding", "resolve"],
    "investigator": ["assess", "execute"],
    "writer": ["get_watchers", "stream_finding"],
    "disambiguator": ["execute", "resolve"],
    # "torpedo" is treated as a specialized operator-syntax user in this runner
    "torpedo": ["execute"],
    # EDITH auto-scribe uses watcher writing tools in this runner
    "edith": ["get_watchers", "stream_finding"],
}

EDITH_AUTOSCRIBE_PROMPT = """You are EDITH Auto-Scribe for SASTRE.

Mission: Ingest intelligence and route it to the correct report sections (Watchers).

You have TWO tools:
1) get_watchers(project_id) - list active document sections (watchers) and their directives.
2) stream_finding(watcher_id, content, source_url) - write content to a section.

CORE RULES (The "Watcher Protocol"):
1. **ISOLATION:** Evaluate each piece of content against each watcher query in isolation. Do not cross-contaminate findings.
2. **VERBATIM EXTRACTION:** When you find a match, extract the relevant text VERBATIM (word-for-word quote). Do not summarize, synthesize, or hallucinate at this stage.
3. **DETERMINISTIC SOURCING:** You MUST attach the source URL to every finding you stream.

WORKFLOW:
1. Call get_watchers(project_id) to see active questions.
2. For each finding/source text:
   - Check if it answers any watcher question.
   - If match: Copy the relevant text exactly (verbatim).
   - stream_finding(watcher_id, content=verbatim_text, source_url=url).

Note: The final report writing (synthesis/prose) happens later or via a separate 'Write' task. Your job here is precise extraction and routing.
"""


# =============================================================================
# DELEGATION PROTOCOL
# =============================================================================

class DelegationType(Enum):
    """Types of delegation between agents."""
    INVESTIGATE = "investigate"      # Orchestrator → Investigator
    WRITE = "write"                  # Orchestrator → Writer
    DISAMBIGUATE = "disambiguate"    # Orchestrator → Disambiguator
    ASSESS = "assess"                # Any agent → Grid assessment
    TORPEDO = "torpedo"              # Orchestrator → Torpedo
    EDITH = "edith"                  # Orchestrator → Edith


@dataclass
class Delegation:
    """A delegation from one agent to another."""
    delegation_type: DelegationType
    task: str
    context: Dict[str, Any] = field(default_factory=dict)
    priority: int = 1  # 1=highest
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class DelegationResult:
    """Result of a delegation."""
    delegation: Delegation
    success: bool
    output: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0
    error: Optional[str] = None


# =============================================================================
# INVESTIGATION STATE (shared across agents)
# =============================================================================

@dataclass
class InvestigationSession:
    """Shared state for a multi-agent investigation session."""
    project_id: str
    tasking: str
    started_at: datetime = field(default_factory=datetime.now)

    # Investigation state
    iteration: int = 0
    max_iterations: int = 10
    ku_quadrant: KUQuadrant = KUQuadrant.DISCOVER

    # Findings and gaps
    findings: List[Dict[str, Any]] = field(default_factory=list)
    gaps: List[Dict[str, Any]] = field(default_factory=list)
    collisions: List[Dict[str, Any]] = field(default_factory=list)

    # Agent activity log
    delegations: List[DelegationResult] = field(default_factory=list)

    # Sufficiency tracking
    sufficiency_checks: List[SufficiencyResult] = field(default_factory=list)
    is_sufficient: bool = False

    def to_context(self) -> Dict[str, Any]:
        """Convert to context dict for agent prompts."""
        return {
            "project_id": self.project_id,
            "tasking": self.tasking,
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "ku_quadrant": self.ku_quadrant.value,
            "findings_count": len(self.findings),
            "gaps_count": len(self.gaps),
            "collisions_count": len(self.collisions),
            "is_sufficient": self.is_sufficient,
        }

    def add_finding(self, finding: Dict[str, Any]) -> None:
        """Add a finding from investigator."""
        finding["iteration"] = self.iteration
        finding["timestamp"] = datetime.now().isoformat()
        self.findings.append(finding)

    def add_gap(self, gap: Dict[str, Any]) -> None:
        """Add a gap from assessment."""
        gap["iteration"] = self.iteration
        self.gaps.append(gap)

    def add_collision(self, collision: Dict[str, Any]) -> None:
        """Add a collision for disambiguation."""
        collision["iteration"] = self.iteration
        self.collisions.append(collision)


# =============================================================================
# AGENT WRAPPER (with delegation support)
# =============================================================================

class DelegatingAgent:
    """
    Agent wrapper that can delegate tasks and return structured results.

    Extends SastreAgent with:
    - Delegation parsing from agent output
    - Structured result extraction
    - Session state awareness
    """

    def __init__(
        self,
        agent_type: str,
        session: InvestigationSession,
    ):
        self.agent_type = agent_type
        self.session = session
        if agent_type not in AGENT_CONFIGS:
            raise ValueError(f"Unknown agent_type: {agent_type}")
        self.config = AGENT_CONFIGS[agent_type]
        self.client = AsyncAnthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")
        )
        tool_names = AGENT_TOOLSETS.get(agent_type, [])
        self.tool_schemas = [TOOLS[name] for name in tool_names if name in TOOLS]

    async def run(self, task: str, extra_context: Dict = None) -> DelegationResult:
        """Run the agent and return structured result."""
        start_time = datetime.now()

        # Build context
        context = self.session.to_context()
        if extra_context:
            context.update(extra_context)

        # Build messages
        messages = [{
            "role": "user",
            "content": f"""Task: {task}

Session Context:
{json.dumps(context, indent=2, default=str)}

Execute your task and report findings. If you need to delegate to another agent,
indicate this clearly with:
- DELEGATE:investigate - for running queries
- DELEGATE:torpedo - for high-velocity source mining
- DELEGATE:edith - for report structure and styling
- DELEGATE:write - for document writing
- DELEGATE:disambiguate - for resolving entity collisions

When complete, provide your findings in a structured format."""
        }]

        logger.info(f"Agent [{self.agent_type}] starting: {task[:60]}...")

        # Run agent loop
        max_turns = 15
        final_output = ""
        delegations_requested = []
        findings = []

        for turn in range(max_turns):
            try:
                response = await self.client.messages.create(
                    model=self.config.model,
                    max_tokens=4096,
                    system=EDITH_AUTOSCRIBE_PROMPT if self.agent_type == "edith" else self.config.system_prompt,
                    messages=messages,
                    tools=self.tool_schemas if self.tool_schemas else None
                )
            except Exception as e:
                logger.error(f"Claude API error: {e}")
                return DelegationResult(
                    delegation=Delegation(DelegationType.INVESTIGATE, task),
                    success=False,
                    error=str(e),
                    duration_ms=(datetime.now() - start_time).total_seconds() * 1000,
                )

            # Build assistant message
            assistant_content = []
            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                    final_output = block.text

                    # Parse delegations from text
                    delegations_requested.extend(self._parse_delegations(block.text))

                    # Parse findings from text
                    findings.extend(self._parse_findings(block.text))

                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input
                    })

            messages.append({"role": "assistant", "content": assistant_content})

            # Handle tool use
            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = await self._execute_tool(block.name, block.input)

                        # === AUTO-SCRIBE INGESTION ===
                        # In Auto-Scribe mode, capture investigation tool outputs as findings so they
                        # can be routed/written into the report. Skip write/control-plane tools.
                        if is_auto_scribe_enabled() and _should_capture_tool_result(block.name):
                            payload = {"tool": block.name, "input": block.input, "output": result}
                            content = json.dumps(payload, ensure_ascii=False, default=str)
                            url_candidates = _extract_url_candidates(block.name, block.input, result)

                            if len(content) > 8000:
                                content = content[:8000] + "\n...[truncated]..."

                            findings.append({
                                "source": f"tool:{block.name}",
                                "content": content,
                                "url_candidates": url_candidates,
                            })
                        else:
                            # Legacy behavior: only capture execute() payloads as structured findings
                            if block.name == "execute" and isinstance(result, dict):
                                findings.append({
                                    "source": "execute",
                                    "query": block.input.get("query", ""),
                                    "data": result,
                                })

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, default=str)[:10000]
                        })

                messages.append({"role": "user", "content": tool_results})
            else:
                # Agent done
                break

        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        logger.info(f"Agent [{self.agent_type}] completed in {duration_ms:.0f}ms")

        return DelegationResult(
            delegation=Delegation(
                delegation_type=DelegationType.INVESTIGATE,
                task=task,
            ),
            success=True,
            output=final_output,
            data={
                "findings": findings,
                "delegations_requested": delegations_requested,
                "turns": turn + 1,
            },
            duration_ms=duration_ms,
        )

    async def _execute_tool(self, name: str, input_data: Dict) -> Any:
        """Execute tool handler."""
        logger.info(f"  Tool: {name}")

        if name in TOOL_HANDLERS:
            try:
                return await TOOL_HANDLERS[name](**input_data)
            except Exception as e:
                logger.error(f"Tool error [{name}]: {e}")
                return {"error": str(e)}

        return {"error": f"Unknown tool: {name}"}

    def _parse_delegations(self, text: str) -> List[Dict[str, Any]]:
        """Parse delegation requests from agent output."""
        delegations = []

        import re
        # Look for DELEGATE:type patterns
        pattern = r"DELEGATE:(\w+)\s*(?:-|:)?\s*(.+?)(?:\n|$)"
        matches = re.findall(pattern, text, re.IGNORECASE)

        for dtype, task in matches:
            dtype = dtype.lower()
            if dtype in ["investigate", "investigator"]:
                delegations.append({"type": "investigate", "task": task.strip()})
            elif dtype in ["write", "writer"]:
                delegations.append({"type": "write", "task": task.strip()})
            elif dtype in ["disambiguate", "disambiguator"]:
                delegations.append({"type": "disambiguate", "task": task.strip()})
            elif dtype in ["torpedo"]:
                delegations.append({"type": "torpedo", "task": task.strip()})
            elif dtype in ["edith"]:
                delegations.append({"type": "edith", "task": task.strip()})

        return delegations

    def _parse_findings(self, text: str) -> List[Dict[str, Any]]:
        """Parse findings from agent output."""
        findings = []

        import re
        # Look for FINDING: patterns
        pattern = r"FINDING:\s*(.+?)(?:\n\n|\n(?=FINDING:)|$)"
        matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)

        for finding in matches:
            findings.append({"content": finding.strip(), "source": "agent_output"})

        return findings


# =============================================================================
# MULTI-AGENT RUNNER
# =============================================================================

class MultiAgentRunner:
    """
    Coordinates multiple agents in the SASTRE investigation loop.

    Flow:
        1. ORCHESTRATOR assesses state, identifies gaps
        2. ORCHESTRATOR delegates to INVESTIGATOR for queries
        3. INVESTIGATOR executes queries, returns findings
        4. If collisions detected → DISAMBIGUATOR resolves
        5. ORCHESTRATOR delegates to WRITER for document streaming
        6. Check sufficiency → loop or finish

    Usage:
        runner = MultiAgentRunner(project_id="mycase")
        result = await runner.run("Investigate John Smith")
    """

    def __init__(
        self,
        project_id: str = "default",
        max_iterations: int = 10,
        on_finding: Optional[Callable[[Dict], Awaitable[None]]] = None,
        on_delegation: Optional[Callable[[DelegationResult], Awaitable[None]]] = None,
    ):
        self.project_id = project_id
        self.max_iterations = max_iterations
        self.on_finding = on_finding
        self.on_delegation = on_delegation

    async def run(self, tasking: str) -> Dict[str, Any]:
        """
        Run a multi-agent investigation.

        Args:
            tasking: What to investigate

        Returns:
            Investigation results with findings, gaps, and agent activity
        """
        logger.info(f"=== SASTRE Multi-Agent Investigation ===")
        logger.info(f"Project: {self.project_id}")
        logger.info(f"Tasking: {tasking[:80]}...")

        # Initialize session
        session = InvestigationSession(
            project_id=self.project_id,
            tasking=tasking,
            max_iterations=self.max_iterations,
        )

        # Run investigation loop
        while session.iteration < session.max_iterations and not session.is_sufficient:
            session.iteration += 1
            logger.info(f"\n--- Iteration {session.iteration}/{session.max_iterations} ---")

            # Phase 1: Orchestrator assesses and plans
            orchestrator = DelegatingAgent("orchestrator", session)
            orch_result = await orchestrator.run(
                f"Assess current state and plan next steps for: {tasking}"
            )
            session.delegations.append(orch_result)

            if self.on_delegation:
                await self.on_delegation(orch_result)

            # Extract delegations requested by orchestrator
            delegations = orch_result.data.get("delegations_requested", [])

            if not delegations:
                # Orchestrator didn't request delegations - run investigator directly
                delegations = [{"type": "investigate", "task": tasking}]

            # Phase 2: Execute delegations
            for delegation in delegations:
                dtype = delegation.get("type", "investigate")
                dtask = delegation.get("task", tasking)

                if dtype == "investigate":
                    result = await self._run_investigator(session, dtask)
                elif dtype == "write":
                    result = await self._run_writer(session, dtask)
                elif dtype == "disambiguate":
                    result = await self._run_disambiguator(session, dtask)
                elif dtype == "torpedo":
                    result = await self._run_torpedo(session, dtask)
                elif dtype == "edith":
                    result = await self._run_edith(session, dtask)
                else:
                    logger.warning(f"Unknown delegation type: {dtype}")
                    continue

                session.delegations.append(result)

                if self.on_delegation:
                    await self.on_delegation(result)

                # Add findings to session
                findings = result.data.get("findings", [])
                for finding in findings:
                    session.add_finding(finding)
                    if self.on_finding:
                        await self.on_finding(finding)

                # === AUTO-SCRIBE (WRITE-THROUGH) ===
                # If enabled, immediately route new findings into the report via the Writer agent.
                # Skip if this delegation already *is* writing/edith to avoid feedback loops.
                if is_auto_scribe_enabled() and findings and dtype not in {"write", "edith"}:
                    logger.info("✍️ AUTO-SCRIBE ACTIVE: Writing new findings to Watchers...")

                    def _format_finding(f: Dict[str, Any]) -> str:
                        urls = f.get("url_candidates") or []
                        url_line = f"URLS: {', '.join(urls)}\n" if urls else ""
                        content = f.get("content") or f.get("data") or ""
                        return f"SOURCE: {f.get('source')}\n{url_line}CONTENT: {content}"

                    findings_text = "\n\n".join([_format_finding(f) for f in findings])

                    writer_task = f"""
AUTO-SCRIBE TRIGGERED.

You have received new raw intelligence from tools/agents.

Goal:
1) Match each finding to the correct Watcher section.
2) Write it up in SASTRE/Nardello style (certainty calibrated).
3) For every streamed finding, include a real `source_url` (prefer URLS above; otherwise extract a URL from the content). If no URL exists, do not stream speculative prose.

RAW FINDINGS:
{findings_text}
"""

                    writer_result = await self._run_writer(session, writer_task)
                    session.delegations.append(writer_result)
                    if self.on_delegation:
                        await self.on_delegation(writer_result)
                # ============================

            # Phase 3: Check for collisions needing disambiguation
            if session.collisions:
                unresolved = [c for c in session.collisions if not c.get("resolved")]
                for collision in unresolved[:3]:  # Handle up to 3 per iteration
                    result = await self._run_disambiguator(
                        session,
                        f"Resolve collision: {collision}"
                    )
                    session.delegations.append(result)

            # Phase 4: Check sufficiency
            sufficiency = await self._check_sufficiency(session)
            session.sufficiency_checks.append(sufficiency)
            session.is_sufficient = sufficiency.is_complete

            if session.is_sufficient:
                logger.info("✓ Sufficiency reached - investigation complete")
                break

            # Update K-U quadrant based on what we've learned
            session.ku_quadrant = self._compute_ku_quadrant(session)

        # Final phase: Generate summary via writer
        if session.findings:
            writer_result = await self._run_writer(
                session,
                f"Summarize investigation findings for: {tasking}"
            )
            session.delegations.append(writer_result)

        # Build final result
        return self._build_result(session)

    async def _run_investigator(
        self,
        session: InvestigationSession,
        task: str
    ) -> DelegationResult:
        """Run the investigator agent."""
        logger.info(f"→ INVESTIGATOR: {task[:50]}...")
        agent = DelegatingAgent("investigator", session)
        return await agent.run(task)

    async def _run_writer(
        self,
        session: InvestigationSession,
        task: str
    ) -> DelegationResult:
        """Run the writer agent."""
        logger.info(f"→ WRITER: {task[:50]}...")
        agent = DelegatingAgent("writer", session)
        return await agent.run(task)

    async def _run_torpedo(
        self,
        session: InvestigationSession,
        task: str
    ) -> DelegationResult:
        """Run the torpedo agent."""
        logger.info(f"→ TORPEDO: {task[:50]}...")
        agent = DelegatingAgent("torpedo", session)
        return await agent.run(task)

    async def _run_edith(
        self,
        session: InvestigationSession,
        task: str
    ) -> DelegationResult:
        """Run the edith agent."""
        logger.info(f"→ EDITH: {task[:50]}...")
        agent = DelegatingAgent("edith", session)
        return await agent.run(task)

    async def _run_disambiguator(
        self,
        session: InvestigationSession,
        task: str
    ) -> DelegationResult:
        """Run the disambiguator agent."""
        logger.info(f"→ DISAMBIGUATOR: {task[:50]}...")
        agent = DelegatingAgent("disambiguator", session)
        return await agent.run(task)

    async def _check_sufficiency(self, session: InvestigationSession) -> SufficiencyResult:
        """Check if investigation is sufficient."""
        # Get current assessment
        try:
            assessment = await handle_assess(session.project_id, "all")
        except Exception:
            assessment = {}

        # Simple sufficiency check based on findings and gaps
        has_findings = len(session.findings) > 0
        critical_gaps_filled = len(session.gaps) < 3
        collisions_resolved = all(c.get("resolved", False) for c in session.collisions)

        return SufficiencyResult(
            core_fields_populated=has_findings,
            tasking_headers_addressed=has_findings,
            no_high_weight_absences=critical_gaps_filled,
            disambiguation_resolved=collisions_resolved,
            surprising_ands_processed=True,
        )

    def _compute_ku_quadrant(self, session: InvestigationSession) -> KUQuadrant:
        """Compute current K-U quadrant based on session state."""
        # If we have findings about a specific entity, we've moved from DISCOVER
        has_subject_info = any(
            f.get("data", {}).get("name") or f.get("data", {}).get("company_name")
            for f in session.findings
        )

        # Check if we have location/jurisdiction info
        has_location_info = any(
            f.get("data", {}).get("jurisdiction") or f.get("data", {}).get("country")
            for f in session.findings
        )

        return derive_quadrant(has_subject_info, has_location_info)

    def _build_result(self, session: InvestigationSession) -> Dict[str, Any]:
        """Build the final investigation result."""
        completed_at = datetime.now()
        duration_ms = (completed_at - session.started_at).total_seconds() * 1000

        return {
            "project_id": session.project_id,
            "tasking": session.tasking,
            "status": "complete" if session.is_sufficient else "incomplete",

            # Metrics
            "iterations": session.iteration,
            "duration_ms": duration_ms,
            "final_ku_quadrant": session.ku_quadrant.value,

            # Findings
            "findings_count": len(session.findings),
            "findings": session.findings,

            # Gaps remaining
            "gaps_count": len(session.gaps),
            "gaps": session.gaps[:10],  # Top 10

            # Collisions
            "collisions_count": len(session.collisions),
            "collisions_resolved": sum(1 for c in session.collisions if c.get("resolved")),

            # Agent activity
            "delegations": [
                {
                    "agent": d.delegation.delegation_type.value,
                    "success": d.success,
                    "duration_ms": d.duration_ms,
                }
                for d in session.delegations
            ],

            # Sufficiency
            "sufficiency": {
                "is_complete": session.is_sufficient,
                "checks": len(session.sufficiency_checks),
                "final_check": session.sufficiency_checks[-1].to_dict() if session.sufficiency_checks else None,
            } if hasattr(session.sufficiency_checks[-1] if session.sufficiency_checks else SufficiencyResult(), 'to_dict') else {
                "is_complete": session.is_sufficient,
                "checks": len(session.sufficiency_checks),
            },
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def run_investigation(
    tasking: str,
    project_id: str = "default",
    max_iterations: int = 10,
) -> Dict[str, Any]:
    """
    Run a multi-agent investigation.

    Example:
        result = await run_investigation(
            "Investigate John Smith, CEO of Acme Corp",
            project_id="case_123"
        )
    """
    runner = MultiAgentRunner(
        project_id=project_id,
        max_iterations=max_iterations,
    )
    return await runner.run(tasking)


async def investigate_entity(
    entity_name: str,
    entity_type: str = "person",
    jurisdiction: str = "UNKNOWN",
    project_id: str = "default",
) -> Dict[str, Any]:
    """
    Investigate a specific entity.

    Example:
        result = await investigate_entity(
            entity_name="John Smith",
            entity_type="person",
            jurisdiction="US",
        )
    """
    tasking = f"Investigate {entity_type}: {entity_name}"
    if jurisdiction != "UNKNOWN":
        tasking += f" in {jurisdiction}"

    return await run_investigation(tasking, project_id)


# =============================================================================
# CLI
# =============================================================================

def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="SASTRE Multi-Agent Investigation")
    parser.add_argument("tasking", nargs="?", help="Investigation tasking")
    parser.add_argument("--project", "-p", default="default", help="Project ID")
    parser.add_argument("--max-iterations", "-m", type=int, default=10)
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.tasking:
        result = asyncio.run(run_investigation(
            args.tasking,
            project_id=args.project,
            max_iterations=args.max_iterations,
        ))
        print(json.dumps(result, indent=2, default=str))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
