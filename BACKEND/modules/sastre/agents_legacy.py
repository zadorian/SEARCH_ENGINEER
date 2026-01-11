"""
SASTRE Agents Legacy - Agent definitions for backward compatibility.

The actual Agent SDK implementation is in sdk.py which uses Claude API with tools.
This file provides the legacy AgentRole/AgentDefinition types for modules that import them.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Callable, Optional
from enum import Enum


class AgentRole(Enum):
    """Agent roles in SASTRE system."""
    ORCHESTRATOR = "orchestrator"
    IO_EXECUTOR = "io_executor"
    DISAMBIGUATOR = "disambiguator"
    WRITER = "writer"
    GRID_ASSESSOR = "grid_assessor"


@dataclass
class Tool:
    """A tool available to an agent."""
    name: str
    description: str
    handler: Optional[Callable] = None
    input_schema: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentDefinition:
    """Definition of an agent's capabilities."""
    role: AgentRole
    name: str
    model: str
    system_prompt: str
    tools: List[str] = field(default_factory=list)
    can_delegate_to: List[AgentRole] = field(default_factory=list)


# Agent definitions
AGENT_DEFINITIONS = {
    AgentRole.ORCHESTRATOR: AgentDefinition(
        role=AgentRole.ORCHESTRATOR,
        name="orchestrator",
        model="claude-opus-4-5-20251101",
        system_prompt="You are the SASTRE Orchestrator. You coordinate the investigation loop.",
        tools=["search_corpus", "get_grid_assessment", "delegate_to_io_executor"],
        can_delegate_to=[AgentRole.IO_EXECUTOR, AgentRole.DISAMBIGUATOR, AgentRole.WRITER, AgentRole.GRID_ASSESSOR],
    ),
    AgentRole.IO_EXECUTOR: AgentDefinition(
        role=AgentRole.IO_EXECUTOR,
        name="io_executor",
        model="claude-opus-4-5-20251101",
        system_prompt="You are the IO Executor. You run investigation queries.",
        tools=["search_corpus", "execute_io_query", "extract_entities"],
    ),
    AgentRole.DISAMBIGUATOR: AgentDefinition(
        role=AgentRole.DISAMBIGUATOR,
        name="disambiguator",
        model="claude-sonnet-4-5-20250929",
        system_prompt="You are the Disambiguator. You resolve entity collisions.",
        tools=["search_corpus", "execute_io_query"],
    ),
    AgentRole.WRITER: AgentDefinition(
        role=AgentRole.WRITER,
        name="writer",
        model="claude-sonnet-4-5-20250929",
        system_prompt="You are the Writer. You format findings into Nardello-style prose.",
        tools=["get_active_watchers", "add_finding_to_watcher"],
    ),
    AgentRole.GRID_ASSESSOR: AgentDefinition(
        role=AgentRole.GRID_ASSESSOR,
        name="grid_assessor",
        model="claude-sonnet-4-5-20250929",
        system_prompt="You are the Grid Assessor. You evaluate completeness from 4 perspectives.",
        tools=["get_grid_assessment", "search_corpus"],
    ),
}


class SastreTools:
    """Tool registry for legacy compatibility."""
    _tools: Dict[str, Tool] = {}

    @classmethod
    def register(cls, tool: Tool):
        cls._tools[tool.name] = tool

    @classmethod
    def get(cls, name: str) -> Optional[Tool]:
        return cls._tools.get(name)


class AgentRunner:
    """
    Legacy agent runner - stub for backward compatibility.

    The actual implementation is in sdk.py using Claude API.
    """

    def __init__(self, role: AgentRole):
        self.role = role
        self.definition = AGENT_DEFINITIONS.get(role)

    async def run(self, task: str, context: Any = None) -> Dict[str, Any]:
        """Run agent - delegates to sdk.py implementation."""
        from .sdk import SastreAgent, AGENT_CONFIGS

        config = AGENT_CONFIGS.get(self.role.value)
        if not config:
            return {"error": f"Unknown agent role: {self.role}"}

        agent = SastreAgent(config)
        return await agent.run(task, context)


def get_agent_system_prompt(role: AgentRole) -> str:
    """Get system prompt for an agent role."""
    defn = AGENT_DEFINITIONS.get(role)
    return defn.system_prompt if defn else ""


def get_all_agent_definitions() -> Dict[AgentRole, AgentDefinition]:
    """Get all agent definitions."""
    return AGENT_DEFINITIONS
