import logging
from datetime import datetime
from typing import Dict, Any, Optional
from ...core.cymonides_state import InvestigationState

logger = logging.getLogger(__name__)

class TemporalManager:
    """
    Central manager for temporal hierarchy and auto-clustering.
    
    Philosophy: Time is a Fractal Container.
    Creating a TimePoint (Day) automatically 'bubbles up' parent nodes:
    Day -> Month -> Year
    """
    
    def __init__(self, state: InvestigationState):
        self.state = state

    async def upsert_temporal_hierarchy(self, date_str: str):
        """
        Creates a full hierarchical cluster for a specific date finding.
        
        Args:
            date_str: ISO format date string (YYYY-MM-DD)
        """
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception:
            logger.error(f"  [Temp] Invalid date format: {date_str}")
            return None

        year_label = str(dt.year)
        month_label = dt.strftime("%B %Y")
        day_label = dt.strftime("%Y-%m-%d")

        # 1. Create Year Node (Top Container)
        year_id = await self.state.create_node(
            label=year_label,
            class_name="location",
            type_name="time_span",
            properties={"resolution": "year", "value": dt.year}
        )
        logger.info(f"  [Temp] Ensured Year: {year_label}")

        # 2. Create Month Node (Container)
        month_id = await self.state.create_node(
            label=month_label,
            class_name="location",
            type_name="time_span",
            properties={"resolution": "month", "value": dt.month}
        )
        await self.state.create_edge(month_id, year_id, "part_of")
        logger.info(f"  [Temp] Ensured Month: {month_label}")

        # 3. Create Day Node (Atomic Leaf)
        day_id = await self.state.create_node(
            label=day_label,
            class_name="location",
            type_name="time_point",
            properties={"resolution": "day", "value": date_str}
        )
        await self.state.create_edge(day_id, month_id, "part_of")
        logger.info(f"  [Temp] Ensured Day: {day_label}")

        return day_id
