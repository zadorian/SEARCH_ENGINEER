"""
Temporal Bridge - Connects date extraction to hierarchical node creation.

Bridges GLiNER date extraction to TemporalManager for creating
hierarchical temporal nodes: Day -> Month -> Year

Philosophy: Time is a LOCATION class (static axis).
Each date mention creates hierarchical nodes with 'part_of' edges:
- Day node --part_of--> Month node --part_of--> Year node

Usage:
    from linklater.extraction.temporal_bridge import TemporalBridge

    bridge = TemporalBridge(state)
    node_ids = await bridge.process_extracted_dates(gliner_dates, source_node_id)

    # Or process a single date:
    day_id = await bridge.create_date_hierarchy("2024-01-15")
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class TemporalBridge:
    """
    Connects date extraction to graph node creation.

    Creates hierarchical temporal nodes following the fractal container model:
    Day (time_point) --> Month (time_span) --> Year (time_span)
    """

    def __init__(self, state):
        """
        Initialize bridge with investigation state.

        Args:
            state: InvestigationState with create_node() and create_edge() methods
        """
        self.state = state
        self._year_cache = {}   # year_str -> node_id
        self._month_cache = {}  # "YYYY-MM" -> node_id

    async def create_date_hierarchy(self, iso_date: str) -> Optional[str]:
        """
        Create full hierarchical cluster for a date.

        Args:
            iso_date: ISO format date string (YYYY-MM-DD, YYYY-MM, or YYYY)

        Returns:
            Most granular node ID (day if available, else month, else year)
        """
        try:
            # Parse the date string
            parts = iso_date.split('-')
            year = int(parts[0])
            month = int(parts[1]) if len(parts) > 1 else None
            day = int(parts[2]) if len(parts) > 2 else None

            # Create Year node (always)
            year_id = await self._ensure_year_node(year)

            if month is None:
                return year_id

            # Create Month node
            month_id = await self._ensure_month_node(year, month, year_id)

            if day is None:
                return month_id

            # Create Day node
            day_id = await self._ensure_day_node(year, month, day, month_id)

            return day_id

        except Exception as e:
            logger.error(f"Failed to create date hierarchy for {iso_date}: {e}")
            return None

    async def _ensure_year_node(self, year: int) -> str:
        """Get or create Year node."""
        year_str = str(year)

        if year_str in self._year_cache:
            return self._year_cache[year_str]

        year_id = await self.state.create_node(
            label=year_str,
            class_name="location",
            type_name="time_span",
            properties={
                "resolution": "year",
                "value": year,
                "start_date": f"{year}-01-01",
                "end_date": f"{year}-12-31"
            }
        )

        self._year_cache[year_str] = year_id
        logger.debug(f"Created year node: {year_str}")
        return year_id

    async def _ensure_month_node(self, year: int, month: int, year_id: str) -> str:
        """Get or create Month node linked to Year."""
        month_key = f"{year}-{month:02d}"

        if month_key in self._month_cache:
            return self._month_cache[month_key]

        # Create readable label
        dt = datetime(year, month, 1)
        month_label = dt.strftime("%B %Y")

        # Calculate month end date
        if month == 12:
            end_date = f"{year}-12-31"
        else:
            next_month = datetime(year, month + 1, 1)
            from datetime import timedelta
            end_dt = next_month - timedelta(days=1)
            end_date = end_dt.strftime("%Y-%m-%d")

        month_id = await self.state.create_node(
            label=month_label,
            class_name="location",
            type_name="time_span",
            properties={
                "resolution": "month",
                "value": month,
                "year": year,
                "start_date": f"{year}-{month:02d}-01",
                "end_date": end_date
            }
        )

        # Link month to year
        await self.state.create_edge(month_id, year_id, "part_of")

        self._month_cache[month_key] = month_id
        logger.debug(f"Created month node: {month_label}")
        return month_id

    async def _ensure_day_node(self, year: int, month: int, day: int, month_id: str) -> str:
        """Create Day node linked to Month."""
        iso_date = f"{year}-{month:02d}-{day:02d}"

        # Day nodes are always created fresh (no caching needed - dedup happens at state level)
        day_id = await self.state.create_node(
            label=iso_date,
            class_name="location",
            type_name="time_point",
            properties={
                "resolution": "day",
                "value": iso_date,
                "year": year,
                "month": month,
                "day": day
            }
        )

        # Link day to month
        await self.state.create_edge(day_id, month_id, "part_of")

        logger.debug(f"Created day node: {iso_date}")
        return day_id

    async def process_extracted_dates(
        self,
        dates: List[Dict[str, Any]],
        source_node_id: Optional[str] = None,
        edge_type: str = "mentioned_at"
    ) -> Dict[str, str]:
        """
        Process dates from GLiNER extraction and create hierarchical nodes.

        Args:
            dates: List of date dicts from GLiNER with 'parsed' containing iso_date
            source_node_id: Optional node to link dates to (e.g., document, event)
            edge_type: Edge type for linking source to date nodes

        Returns:
            Dict mapping iso_date -> most granular node_id created
        """
        results = {}

        for date_info in dates:
            parsed = date_info.get('parsed', {})
            iso_date = parsed.get('iso_date')

            if not iso_date:
                continue

            # Create hierarchical nodes
            node_id = await self.create_date_hierarchy(iso_date)

            if node_id:
                results[iso_date] = node_id

                # Link source to this date if provided
                if source_node_id:
                    await self.state.create_edge(source_node_id, node_id, edge_type)

        logger.info(f"Processed {len(results)} dates into hierarchical nodes")
        return results


# Convenience function for standalone use
async def create_temporal_nodes(
    state,
    dates: List[Dict[str, Any]],
    source_node_id: Optional[str] = None
) -> Dict[str, str]:
    """
    Create temporal hierarchy nodes from extracted dates.

    Args:
        state: InvestigationState or compatible object
        dates: List of dates from GLiNER extraction
        source_node_id: Optional source to link dates to

    Returns:
        Dict mapping iso_date -> node_id
    """
    bridge = TemporalBridge(state)
    return await bridge.process_extracted_dates(dates, source_node_id)
