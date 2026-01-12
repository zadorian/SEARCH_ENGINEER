#!/usr/bin/env python3
"""
IO Result Contract - Standard structure for all IO route results.

Every IO route execution returns an IOResult with:
- source_url: URL of the actual data source (for footnotes)
- status: 'success' | 'wall' | 'error'
- data: Extracted data (dict/list)
- wall_info: If status='wall', info for manual retrieval

This is THE CONTRACT. All bridges, executors, and writers depend on this structure.
Footnotes are added DETERMINISTICALLY from source_url, never by AI.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from datetime import datetime
from enum import Enum
import json
import re


class IOStatus(Enum):
    SUCCESS = "success"     # Data fetched successfully
    WALL = "wall"          # Hit paywall/login/captcha
    ERROR = "error"        # Technical error
    PARTIAL = "partial"    # Some data, some walls


@dataclass
class WallInfo:
    """Information for manual retrieval when wall is hit."""
    wall_type: str              # 'paywall' | 'login' | 'captcha' | 'blocked' | 'rate_limit'
    closest_url: str            # URL as close to final result as possible
    instructions: str           # What user needs to do
    registry_name: str = ""     # Name of the registry/source
    subscription_info: str = "" # How to get access
    alternative_routes: List[str] = field(default_factory=list)  # Other ways to get this data


@dataclass
class IOResult:
    """
    Standard result from any IO route execution.

    This is used by:
    - chain_executor.py: Wraps all route results
    - io_cli.py: Returns to callers
    - Writer: Uses source_url for footnotes
    - Gap detector: Checks for walls

    CRITICAL: Implements "Sanctity of Source" pattern.
    - PUBLIC SIDE: source_name, source_display_name, source_category (visible to user)
    - EXECUTION SIDE: Internal details hidden (handlers, scripts, APIs)
    """
    route_id: str               # e.g., "COMPANY_OFFICERS_HU"
    entity: str                 # e.g., "Podravka d.d."
    jurisdiction: Optional[str] # e.g., "HU", "GB", None for global

    status: IOStatus
    source_url: str             # THE URL for footnotes (always present)

    data: Dict[str, Any] = field(default_factory=dict)  # Extracted data
    raw_response: Optional[str] = None  # Original response for debugging

    wall_info: Optional[WallInfo] = None  # Present if status == WALL
    error_message: Optional[str] = None   # Present if status == ERROR

    executed_at: datetime = field(default_factory=datetime.utcnow)
    execution_ms: int = 0       # How long the call took

    # Dedup tracking
    dedup_key: str = ""         # (entity, jurisdiction, route_id) hash

    # PUBLIC SIDE - "Sanctity of Source" (visible to user/report)
    # These translate internal execution details to user-friendly names
    source_name: str = ""           # e.g., "Hungarian Business Registry"
    source_display_name: str = ""   # e.g., "Company Officers (HU)"
    source_category: str = ""       # e.g., "corporate_registry"

    def __post_init__(self):
        """Generate dedup key if not provided."""
        if not self.dedup_key:
            self.dedup_key = f"{self.entity}|{self.jurisdiction}|{self.route_id}".lower()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        result = {
            "route_id": self.route_id,
            "entity": self.entity,
            "jurisdiction": self.jurisdiction,
            "status": self.status.value,
            "source_url": self.source_url,
            "data": self.data,
            "executed_at": self.executed_at.isoformat(),
            "execution_ms": self.execution_ms,
            "dedup_key": self.dedup_key,
            # PUBLIC SIDE - Sanctity of Source
            "source_name": self.source_name,
            "source_display_name": self.source_display_name,
            "source_category": self.source_category,
        }

        if self.wall_info:
            result["wall_info"] = {
                "wall_type": self.wall_info.wall_type,
                "closest_url": self.wall_info.closest_url,
                "instructions": self.wall_info.instructions,
                "registry_name": self.wall_info.registry_name,
                "subscription_info": self.wall_info.subscription_info,
                "alternative_routes": self.wall_info.alternative_routes,
            }

        if self.error_message:
            result["error_message"] = self.error_message

        return result

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'IOResult':
        """Create from dict."""
        wall_info = None
        if d.get("wall_info"):
            wi = d["wall_info"]
            wall_info = WallInfo(
                wall_type=wi.get("wall_type", "unknown"),
                closest_url=wi.get("closest_url", ""),
                instructions=wi.get("instructions", ""),
                registry_name=wi.get("registry_name", ""),
                subscription_info=wi.get("subscription_info", ""),
                alternative_routes=wi.get("alternative_routes", []),
            )

        return cls(
            route_id=d.get("route_id", ""),
            entity=d.get("entity", ""),
            jurisdiction=d.get("jurisdiction"),
            status=IOStatus(d.get("status", "error")),
            source_url=d.get("source_url", ""),
            data=d.get("data", {}),
            wall_info=wall_info,
            error_message=d.get("error_message"),
            executed_at=datetime.fromisoformat(d["executed_at"]) if d.get("executed_at") else datetime.utcnow(),
            execution_ms=d.get("execution_ms", 0),
            dedup_key=d.get("dedup_key", ""),
            # PUBLIC SIDE - Sanctity of Source
            source_name=d.get("source_name", ""),
            source_display_name=d.get("source_display_name", ""),
            source_category=d.get("source_category", ""),
        )


# =============================================================================
# FOOTNOTE INJECTOR - Deterministic, never AI
# =============================================================================

class FootnoteInjector:
    """
    Deterministically adds footnotes to markdown sections.

    This is NOT AI. This is programmatic:
    1. Track footnote numbers globally
    2. Find slots filled by IOResult
    3. Append [^N] after the slot value
    4. Add footnote definition at end of section

    Example:
        Input:  "**Podravka d.d.** has the following directors:"
        Result: "**Podravka d.d.**[^1] has the following directors:"

        With footnote: [^1]: https://sudreg.pravosudje.hr/...
    """

    def __init__(self):
        self.footnote_counter = 0
        self.footnotes: Dict[int, str] = {}  # num -> url

    def reset(self):
        """Reset for new document."""
        self.footnote_counter = 0
        self.footnotes = {}

    def add_footnote(self, url: str) -> int:
        """Add a footnote, return its number."""
        self.footnote_counter += 1
        self.footnotes[self.footnote_counter] = url
        return self.footnote_counter

    def inject_footnote_after_value(
        self,
        markdown: str,
        value: str,
        source_url: str,
        first_occurrence_only: bool = True
    ) -> str:
        """
        Inject footnote reference after a specific value in markdown.

        Args:
            markdown: The markdown text
            value: The value to find (e.g., company name)
            source_url: URL to use as footnote
            first_occurrence_only: Only mark first occurrence

        Returns:
            Modified markdown with [^N] inserted
        """
        if not value or not source_url:
            return markdown

        # Escape value for regex
        escaped_value = re.escape(value)

        # Pattern: **value** or just value (not already footnoted)
        pattern = rf'(\*\*{escaped_value}\*\*|\b{escaped_value}\b)(?!\[\^)'

        footnote_num = self.add_footnote(source_url)
        replacement = rf'\1[^{footnote_num}]'

        if first_occurrence_only:
            return re.sub(pattern, replacement, markdown, count=1)
        else:
            return re.sub(pattern, replacement, markdown)

    def inject_from_io_results(
        self,
        markdown: str,
        results: List[IOResult],
        slot_to_field_map: Dict[str, str]
    ) -> str:
        """
        Inject footnotes for all IOResults into markdown.

        Args:
            markdown: Section markdown
            results: List of IOResult objects
            slot_to_field_map: Maps slot names to data field names
                e.g., {"company_name": "name", "director_name": "officer_name"}

        Returns:
            Modified markdown with footnotes
        """
        for result in results:
            if result.status != IOStatus.SUCCESS:
                continue

            # For each field in data, try to inject footnote
            for slot_name, field_name in slot_to_field_map.items():
                value = result.data.get(field_name)
                if value and isinstance(value, str):
                    markdown = self.inject_footnote_after_value(
                        markdown, value, result.source_url
                    )

            # Handle lists of items
            for key, items in result.data.items():
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            for field_name in item.keys():
                                value = item.get(field_name)
                                if value and isinstance(value, str):
                                    markdown = self.inject_footnote_after_value(
                                        markdown, value, result.source_url
                                    )

        return markdown

    def render_footnotes(self) -> str:
        """Render all footnotes as markdown."""
        if not self.footnotes:
            return ""

        lines = ["\n---\n"]
        for num in sorted(self.footnotes.keys()):
            url = self.footnotes[num]
            lines.append(f"[^{num}]: {url}")

        return "\n".join(lines)


# =============================================================================
# WALL SURFACER - Present walls to user
# =============================================================================

class WallSurfacer:
    """
    Format walls for user presentation.

    When an IO route hits a wall, we need to:
    1. Show the closest URL we could reach
    2. Explain what the user needs to do
    3. Suggest alternatives if available
    """

    @staticmethod
    def format_wall_for_user(result: IOResult) -> str:
        """
        Format a wall result for display to user.

        Returns markdown block explaining the wall and how to proceed.
        """
        if result.status != IOStatus.WALL or not result.wall_info:
            return ""

        wi = result.wall_info

        lines = [
            f"### Manual Retrieval Required: {result.route_id}",
            "",
            f"**Source:** {wi.registry_name or 'Unknown registry'}",
            f"**Entity:** {result.entity}",
            f"**Barrier:** {wi.wall_type}",
            "",
            f"**Closest URL:** [{wi.closest_url}]({wi.closest_url})",
            "",
            f"**Instructions:** {wi.instructions}",
        ]

        if wi.subscription_info:
            lines.extend([
                "",
                f"**Access:** {wi.subscription_info}",
            ])

        if wi.alternative_routes:
            lines.extend([
                "",
                "**Alternatives:**",
            ])
            for alt in wi.alternative_routes:
                lines.append(f"- {alt}")

        return "\n".join(lines)

    @staticmethod
    def collect_walls(results: List[IOResult]) -> List[IOResult]:
        """Get all wall results from a list."""
        return [r for r in results if r.status == IOStatus.WALL]

    @staticmethod
    def format_all_walls(results: List[IOResult]) -> str:
        """Format all walls as a single markdown section."""
        walls = WallSurfacer.collect_walls(results)
        if not walls:
            return ""

        lines = [
            "## Manual Retrieval Required",
            "",
            f"The following {len(walls)} source(s) require manual access:",
            "",
        ]

        for wall in walls:
            lines.append(WallSurfacer.format_wall_for_user(wall))
            lines.append("")

        return "\n".join(lines)


# =============================================================================
# RESULT AGGREGATOR - Combine multiple IOResults
# =============================================================================

class ResultAggregator:
    """
    Aggregate IOResults into structured JSON for section filling.

    Takes multiple IOResults, deduplicates, and produces:
    1. Merged data dict for slot filling
    2. All source_urls for footnotes
    3. All walls for surfacing
    """

    def __init__(self):
        self.results: List[IOResult] = []
        self.seen_dedup_keys: set = set()

    def add(self, result: IOResult) -> bool:
        """
        Add a result, return True if it was new.
        """
        if result.dedup_key in self.seen_dedup_keys:
            return False

        self.seen_dedup_keys.add(result.dedup_key)
        self.results.append(result)
        return True

    def get_merged_data(self) -> Dict[str, Any]:
        """
        Merge all successful results' data.

        Lists are concatenated, dicts are merged (later values win).
        """
        merged = {}

        for result in self.results:
            if result.status not in (IOStatus.SUCCESS, IOStatus.PARTIAL):
                continue

            for key, value in result.data.items():
                if key not in merged:
                    merged[key] = value
                elif isinstance(value, list) and isinstance(merged[key], list):
                    merged[key].extend(value)
                elif isinstance(value, dict) and isinstance(merged[key], dict):
                    merged[key].update(value)
                else:
                    merged[key] = value

        return merged

    def get_source_urls(self) -> List[Dict[str, str]]:
        """
        Get all source URLs with their route IDs.

        Returns list of {"route_id": ..., "url": ..., "entity": ...}
        """
        urls = []
        for result in self.results:
            if result.source_url:
                urls.append({
                    "route_id": result.route_id,
                    "url": result.source_url,
                    "entity": result.entity,
                    "status": result.status.value,
                })
        return urls

    def get_walls(self) -> List[IOResult]:
        """Get all wall results."""
        return [r for r in self.results if r.status == IOStatus.WALL]

    def get_successes(self) -> List[IOResult]:
        """Get all successful results."""
        return [r for r in self.results if r.status == IOStatus.SUCCESS]

    def to_section_json(self) -> Dict[str, Any]:
        """
        Export as JSON structure for section filling.

        This is what gets passed to Writer:
        {
            "data": {...merged data...},
            "sources": [...source urls with routes...],
            "walls": [...wall info for manual retrieval...],
            "stats": {...execution stats...}
        }
        """
        walls_info = []
        for w in self.get_walls():
            if w.wall_info:
                walls_info.append({
                    "route_id": w.route_id,
                    "entity": w.entity,
                    "wall_type": w.wall_info.wall_type,
                    "closest_url": w.wall_info.closest_url,
                    "instructions": w.wall_info.instructions,
                    "registry_name": w.wall_info.registry_name,
                })

        return {
            "data": self.get_merged_data(),
            "sources": self.get_source_urls(),
            "walls": walls_info,
            "stats": {
                "total_routes": len(self.results),
                "successes": len(self.get_successes()),
                "walls": len(self.get_walls()),
                "errors": len([r for r in self.results if r.status == IOStatus.ERROR]),
            }
        }
