"""
Version differ and timeline tools for BACKDRILL.

- DomainDiffer: Track how a domain changed over time (domain-level)
- Timeline builder: all snapshots for a URL across archives (URL-level)
- Version differ: compare two snapshots, compute diffs
- Change detector: find when content changed

FOLDER RENAMED: historical/ → differ/ (2025-01-06)
  Reason: "historical" is meaningless in archive search - everything is historical

Usage:
    from modules.backdrill.differ import DomainDiffer

    async with DomainDiffer() as differ:
        # Domain-level evolution
        evolution = await differ.domain_evolution("example.com")

        # Compare two time periods
        changes = await differ.compare_periods("example.com", "2020", "2024")

        # Find when content appeared
        appearance = await differ.find_content_change(
            "example.com",
            "John Smith",
            change_type="appeared"
        )
"""

# Domain-level comparison (NEW)
from .domain_differ import (
    DomainDiffer,
    PageVersion,
    PageChange,
    DomainChange,
    DomainEvolution,
    PeriodComparison,
    PageHistory,
    ContentAppearance,
    compare_domain_periods,
    get_domain_evolution,
)

# URL-level comparison (legacy functions)
from .timeline_differ import (
    build_timeline,
    diff_versions,
    detect_changes,
    find_first_appearance,
    find_last_appearance,
    compute_similarity,
)

__all__ = [
    # Domain-level (primary)
    "DomainDiffer",
    "PageVersion",
    "PageChange",
    "DomainChange",
    "DomainEvolution",
    "PeriodComparison",
    "PageHistory",
    "ContentAppearance",
    "compare_domain_periods",
    "get_domain_evolution",
    # URL-level (legacy)
    "build_timeline",
    "diff_versions",
    "detect_changes",
    "find_first_appearance",
    "find_last_appearance",
    "compute_similarity",
]
