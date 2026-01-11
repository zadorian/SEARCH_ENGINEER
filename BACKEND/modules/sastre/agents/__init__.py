"""
SASTRE Agents Module - Claude Agent SDK Definitions

Contains specialized agents for investigation tasks:
- orchestrator: Coordinates the investigation loop
- io_executor: Executes IO queries (p:, c:, e:, d:, bl?, ent?)
- disambiguator: Resolves entity collisions (FUSE/REPEL/BINARY_STAR)
- similarity_engine: Handles =? operations for identity/similarity
- writer: Streams findings to document sections
- grid_assessor: Evaluates completeness from 4 centricities
- query_lab: Fuses intent + axes into executable queries
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Any, Callable, Optional


class AgentRole(Enum):
    """Agent roles in SASTRE system."""
    ORCHESTRATOR = "orchestrator"
    IO_EXECUTOR = "io_executor"
    DISAMBIGUATOR = "disambiguator"
    SIMILARITY_ENGINE = "similarity_engine"
    WRITER = "writer"
    GRID_ASSESSOR = "grid_assessor"
    QUERY_LAB = "query_lab"
    # Direct agent addressing bridges
    WIKIMAN = "wikiman"
    EDITH = "edith"
    CYMONIDES = "cymonides"
    LINKLATER = "linklater"
    CORPORELLA = "corporella"
    PACMAN = "pacman"
    TORPEDO = "torpedo"
    BRUTE = "brute"
    SERDAVOS = "serdavos"
    BACKDRILL = "backdrill"


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


# Import agent creation functions
from .orchestrator import create_orchestrator_agent
from .io_executor import create_io_executor_agent
from .disambiguator import create_disambiguator_agent
from .similarity_engine import create_similarity_engine_agent
from .writer import create_writer_agent
from .grid_assessor import create_grid_assessor_agent
from .query_lab import create_query_lab_agent

# Import direct agent addressing bridges
from .wikiman_bridge import execute_wikiman_query
from .edith_bridge import execute_edith_search, search_jurisdiction, get_genre_template


# Agent factory with mined intelligence context support
def create_agent(
    role: AgentRole,
    jurisdiction: str = None,
    entity: str = None,
    entity_type: str = "company",
    action_types: List[str] = None,
    found_red_flags: List[str] = None,
    section_type: str = None,
    **extra_context
):
    """
    Create an agent by role with optional mined intelligence context.

    Args:
        role: The agent role to create
        jurisdiction: Target jurisdiction (e.g., "HU", "CH") - enables mined context
        entity: Entity being investigated
        entity_type: Type of entity ("company" or "person")
        action_types: List of action types for arbitrage routing
        found_red_flags: Red flags already discovered (for propagation)
        section_type: Section type for writer exemplars
        **extra_context: Additional context for specific agents

    When jurisdiction is provided, agents receive:
    - Dead-end warnings (queries known to fail)
    - Arbitrage alternatives (cross-jurisdictional shortcuts)
    - Methodology recommendations (what worked before)
    - Red flag predictions (for orchestrator)
    - Writing exemplars (for writer)
    """
    factories = {
        AgentRole.ORCHESTRATOR: lambda: create_orchestrator_agent(
            entity=entity,
            entity_type=entity_type,
            jurisdiction=jurisdiction,
            found_red_flags=found_red_flags
        ),
        AgentRole.IO_EXECUTOR: lambda: create_io_executor_agent(
            jurisdiction=jurisdiction,
            action_types=action_types
        ),
        AgentRole.DISAMBIGUATOR: create_disambiguator_agent,
        AgentRole.SIMILARITY_ENGINE: create_similarity_engine_agent,
        AgentRole.WRITER: create_writer_agent,  # Writer uses sdk.py which has its own context
        AgentRole.GRID_ASSESSOR: create_grid_assessor_agent,
        AgentRole.QUERY_LAB: create_query_lab_agent,
    }
    factory = factories.get(role)
    if factory:
        return factory()
    raise ValueError(f"Unknown agent role: {role}")


# Agent definitions for reference
AGENT_DEFINITIONS = {
    AgentRole.ORCHESTRATOR: AgentDefinition(
        role=AgentRole.ORCHESTRATOR,
        name="orchestrator",
        model="claude-opus-4-5-20251101",
        system_prompt="Coordinates the investigation loop.",
        tools=["search_corpus", "get_grid_assessment", "delegate"],
        can_delegate_to=[AgentRole.IO_EXECUTOR, AgentRole.DISAMBIGUATOR,
                         AgentRole.SIMILARITY_ENGINE, AgentRole.WRITER, AgentRole.GRID_ASSESSOR,
                         AgentRole.QUERY_LAB],
    ),
    AgentRole.IO_EXECUTOR: AgentDefinition(
        role=AgentRole.IO_EXECUTOR,
        name="io_executor",
        model="claude-opus-4-5-20251101",
        system_prompt="Executes IO queries.",
        tools=["execute_io", "search_corpus", "extract_entities"],
    ),
    AgentRole.DISAMBIGUATOR: AgentDefinition(
        role=AgentRole.DISAMBIGUATOR,
        name="disambiguator",
        model="claude-sonnet-4-5-20250929",
        system_prompt="Resolves entity collisions.",
        tools=["compare_entities", "execute_wedge_query", "resolve_collision"],
    ),
    AgentRole.SIMILARITY_ENGINE: AgentDefinition(
        role=AgentRole.SIMILARITY_ENGINE,
        name="similarity_engine",
        model="claude-opus-4-5-20251101",
        system_prompt="Handles =? operations for identity/similarity.",
        tools=["compare_specific", "similarity_search", "cluster_entities",
               "find_bridges", "compute_expectations"],
    ),
    AgentRole.WRITER: AgentDefinition(
        role=AgentRole.WRITER,
        name="writer",
        model="claude-sonnet-4-5-20250929",
        system_prompt="Streams findings to document sections.",
        tools=["get_active_watchers", "stream_finding", "add_footnote", "format_finding"],
    ),
    AgentRole.GRID_ASSESSOR: AgentDefinition(
        role=AgentRole.GRID_ASSESSOR,
        name="grid_assessor",
        model="claude-sonnet-4-5-20250929",
        system_prompt="Evaluates completeness from 4 centricities.",
        tools=["assess_narrative", "assess_subjects", "assess_locations",
               "assess_nexus", "get_full_assessment", "suggest_next_queries"],
    ),
    AgentRole.QUERY_LAB: AgentDefinition(
        role=AgentRole.QUERY_LAB,
        name="query_lab",
        model="claude-sonnet-4-5-20250929",
        system_prompt="Fuses intent + axes into executable queries.",
        tools=["build_fused_query"],
    ),
}


def get_agent_system_prompt(role: AgentRole) -> str:
    """Get system prompt for an agent role."""
    defn = AGENT_DEFINITIONS.get(role)
    return defn.system_prompt if defn else ""


def get_all_agent_definitions() -> Dict[AgentRole, AgentDefinition]:
    """Get all agent definitions."""
    return AGENT_DEFINITIONS


# Re-export from agents_legacy for backwards compatibility
from ..agents_legacy import SastreTools, AgentRunner


__all__ = [
    # Enums
    'AgentRole',
    # Types
    'AgentDefinition',
    'Tool',
    # Agent creation
    'create_agent',
    'create_orchestrator_agent',
    'create_io_executor_agent',
    'create_disambiguator_agent',
    'create_similarity_engine_agent',
    'create_writer_agent',
    'create_grid_assessor_agent',
    'create_query_lab_agent',
    # Direct agent addressing bridges
    'execute_wikiman_query',
    'execute_edith_search',
    'search_jurisdiction',
    'get_genre_template',
    # Definitions
    'AGENT_DEFINITIONS',
    # Helpers
    'get_agent_system_prompt',
    'get_all_agent_definitions',
    # Legacy compatibility
    'SastreTools',
    'AgentRunner',
]
