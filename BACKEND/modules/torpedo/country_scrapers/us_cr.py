"""US corporate registry router (state-aware)."""

import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

from ..us_sources import get_state_sources, build_source_link
from ..us_state_data import US_STATE_CODES

logger = logging.getLogger("us_company_registry")

PROJECT_ROOT = Path(__file__).resolve().parents[5]
BACKEND_PATH = PROJECT_ROOT / "BACKEND" / "modules"
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))


class USCompanyRegistry:
    """State-aware corporate registry routing with OpenCorporates fallback."""

    def __init__(self) -> None:
        self._torpedo = None

    def _get_torpedo(self):
        if self._torpedo is None:
            from TORPEDO.torpedo import Torpedo
            self._torpedo = Torpedo()
        return self._torpedo

    async def search_company(self, query: str, state_code: Optional[str] = None) -> Dict:
        if state_code and state_code not in US_STATE_CODES:
            raise ValueError(f"Unsupported US state code: {state_code}")

        jurisdiction = f"US_{state_code}" if state_code else "US"
        sources = get_state_sources(state_code, section="cr")
        links = [build_source_link(source, query, jurisdiction, "cr") for source in sources]

        opencorporates: Dict = {}
        companies: List[Dict] = []
        if query:
            try:
                opencorporates = await self._get_torpedo().fetch_opencorporates(query, jurisdiction)
            except Exception as exc:
                opencorporates = {"success": False, "error": str(exc)}
            if isinstance(opencorporates, dict):
                companies = opencorporates.get("companies", []) or []

        return {
            "links": links,
            "opencorporates": opencorporates,
            "companies": companies,
        }
