"""
BACKDRILL - Unified Archive Search Module

Single interface for all archive operations:
- Common Crawl index + data
- Wayback Machine CDX + data
- Racing (first source wins)
- C3 Entity Superindex queries
- Version comparison and domain evolution

Usage:
    from BACKDRILL import Backdrill

    bd = Backdrill()
    result = await bd.fetch("https://example.com")
    results = await bd.fetch_batch(urls, concurrent=50)

    # Just check if archived (no fetch)
    exists = await bd.exists("https://example.com")

    # Get all snapshots
    snapshots = await bd.list_snapshots("https://example.com")

    # Map all URLs for a domain across archives
    from BACKDRILL import BackdrillMapper
    mapper = BackdrillMapper()
    domain_map = await mapper.map_domain("example.com")

    # Version comparison
    from BACKDRILL import DomainDiffer
    async with DomainDiffer() as differ:
        evolution = await differ.domain_evolution("example.com")
        changes = await differ.compare_periods("example.com", "2020", "2024")

    # AI-powered analysis (requires Claude Agent SDK)
    from BACKDRILL import BackdrillAgent
    agent = BackdrillAgent()
    analysis = await agent.analyze_domain_history("example.com")

MCP Server:
    python -m modules.backdrill.mcp_server

Agent CLI:
    python -m modules.backdrill.agent analyze example.com
    python -m modules.backdrill.agent compare example.com --period1 2020 --period2 2024
"""

from .backdrill import (
    Backdrill,
    BackdrillResult,
    BackdrillStats,
    ArchiveSource,
)

from .mapper import (
    BackdrillMapper,
    MappedURL,
    DomainMap,
    map_domain,
)

from .c3_bridge import C3Bridge

from .differ import (
    DomainDiffer,
    DomainEvolution,
    PeriodComparison,
    PageHistory,
    compare_domain_periods,
    get_domain_evolution,
)

# Agent (optional - requires Claude Agent SDK)
try:
    from .agent import (
        BackdrillAgent,
        ArchiveAnalysis,
        analyze_domain,
        compare_periods,
        find_content,
    )
    AGENT_AVAILABLE = True
except ImportError:
    BackdrillAgent = None
    ArchiveAnalysis = None
    analyze_domain = None
    compare_periods = None
    find_content = None
    AGENT_AVAILABLE = False

__all__ = [
    # Core
    "Backdrill",
    "BackdrillResult",
    "BackdrillStats",
    "ArchiveSource",
    # Mapper
    "BackdrillMapper",
    "MappedURL",
    "DomainMap",
    "map_domain",
    # Differ
    "DomainDiffer",
    "DomainEvolution",
    "PeriodComparison",
    "PageHistory",
    "compare_domain_periods",
    "get_domain_evolution",
    # C3 Bridge
    "C3Bridge",
    # Agent (optional)
    "BackdrillAgent",
    "ArchiveAnalysis",
    "analyze_domain",
    "compare_periods",
    "find_content",
    "AGENT_AVAILABLE",
]
