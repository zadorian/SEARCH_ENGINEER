#!/usr/bin/env python3
"""
SASTRE Action Handlers - Wire ALLOWED_ACTIONS to Real Data Sources

Maps the 24 ALLOWED_ACTIONS to actual data fetching implementations.
Each handler is async and returns List[Dict] of results.

Data Sources:
- OpenSanctions → SEARCH_SANCTIONS, SEARCH_PEP
- OpenCorporates → SEARCH_REGISTRY, SEARCH_OFFICERS, SEARCH_SHAREHOLDERS
- Corporella → Company enrichment
- BRUTE Search → SEARCH_NEWS, general web search
- Linklater → Archive searches, link intelligence
- Aleph/OCCRP → Investigative datasets

Usage:
    from SASTRE.bridges.action_handlers import ActionHandlerRegistry

    registry = ActionHandlerRegistry()
    results = await registry.execute("SEARCH_SANCTIONS", {
        "entity": "Test Company",
        "jurisdiction": "uk"
    })
"""

import asyncio
import aiohttp
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from abc import ABC, abstractmethod
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Add parent paths for imports
BACKEND_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

# Load .env from project root - THIS IS WHERE ALL KEYS LIVE
PROJECT_ROOT = Path("/Users/attic/01. DRILL_SEARCH/drill-search-app")
load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class ActionResult:
    """Result from an action handler."""
    action: str
    source: str
    success: bool
    results: List[Dict[str, Any]]
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    playbook_used: Optional[str] = None


class BaseActionHandler(ABC):
    """Base class for action handlers."""

    @property
    @abstractmethod
    def action(self) -> str:
        """The ALLOWED_ACTION this handler implements."""
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Name of the data source."""
        pass

    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Execute the action.

        Args:
            context: Dict with entity, jurisdiction, and other params

        Returns:
            List of result dicts
        """
        pass


# ============================================================================
# PLAYBOOK-AWARE BASE HANDLER
# ============================================================================

class PlaybookAwareHandler(BaseActionHandler):
    """
    Base handler that routes through the playbook system first.

    Each ALLOWED_ACTION maps to one or more playbook categories.
    The handler:
    1. Finds the best playbook for the jurisdiction
    2. Executes via IOBridge.execute_playbook_chain()
    3. Falls back to generic search if no playbook exists
    """

    # Override in subclasses: which playbook categories this action uses
    playbook_categories: List[str] = []

    # Override in subclasses: which chain rule to use
    chain_rule_id: Optional[str] = None

    def __init__(self):
        self._io_bridge = None

    def _get_io_bridge(self):
        """Lazy load IOBridge."""
        if self._io_bridge is None:
            try:
                # SASTRE/bridges.py contains IOBridge but there's a naming conflict
                # with SASTRE/bridges/ directory. Use direct file import.
                import importlib.util
                from pathlib import Path

                sastre_dir = Path(__file__).parent.parent
                bridges_file = sastre_dir / "bridges.py"

                spec = importlib.util.spec_from_file_location("bridges_module", bridges_file)
                bridges_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(bridges_module)

                IOBridge = bridges_module.IOBridge
                self._io_bridge = IOBridge()
                logger.debug("IOBridge loaded successfully")
            except Exception as e:
                logger.warning(f"IOBridge not available, using fallback: {e}")
        return self._io_bridge

    async def execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Execute action via playbook system, with fallback.

        Priority:
        1. Execute matching playbook chain if available
        2. Execute individual rules via IOBridge
        3. Fall back to generic implementation
        """
        entity = context.get("entity", "")
        jurisdiction = context.get("jurisdiction", "")

        if not entity:
            return []

        io_bridge = self._get_io_bridge()

        # Try playbook chain first
        if io_bridge and self.chain_rule_id:
            try:
                chain_result = await io_bridge.execute_playbook_chain(
                    self.chain_rule_id,
                    entity,
                    jurisdiction=jurisdiction,
                    playbook_categories=self.playbook_categories
                )

                if chain_result.get("status") == "success":
                    aggregated = chain_result.get("aggregated_data", {})
                    results_list = chain_result.get("results", [])

                    # Check if we have actual entity results
                    if results_list:
                        flat_results = []
                        for result in results_list:
                            if isinstance(result, dict) and result.get("data"):
                                data = result["data"]
                                if isinstance(data, list):
                                    flat_results.extend(data)
                                else:
                                    flat_results.append(data)
                        if flat_results:
                            return flat_results

                    # If chain only selected a playbook but didn't execute it,
                    # execute the selected playbook directly
                    if "selected_playbook" in aggregated and not results_list:
                        selected = aggregated["selected_playbook"]
                        logger.info(f"Chain selected playbook: {selected.get('id')}, executing directly")
                        # Execute via IOBridge with the selected playbook
                        result = await io_bridge.execute(
                            entity_type=context.get("entity_type", "c"),
                            value=entity,
                            jurisdiction=jurisdiction
                        )
                        if result and not result.get("error"):
                            return [result] if isinstance(result, dict) else result

                    # Flatten any remaining aggregated data
                    if isinstance(aggregated, dict):
                        flat_results = []
                        for key, value in aggregated.items():
                            if key == "selected_playbook":
                                continue  # Skip metadata
                            if isinstance(value, list):
                                flat_results.extend(value)
                            elif isinstance(value, dict):
                                flat_results.append(value)
                        if flat_results:
                            return flat_results
            except Exception as e:
                logger.warning(f"Playbook chain failed for {self.action}: {e}")

        # Try recommended playbook via IOBridge.execute()
        if io_bridge:
            try:
                # Use IOBridge.execute which handles playbook routing internally
                result = await io_bridge.execute(
                    entity_type=context.get("entity_type", "c"),
                    value=entity,
                    jurisdiction=jurisdiction
                )
                if result and not result.get("error"):
                    # Check for actual data in result
                    if result.get("results"):
                        return result["results"] if isinstance(result["results"], list) else [result["results"]]
                    return [result]
            except Exception as e:
                logger.warning(f"IOBridge execution failed for {self.action}: {e}")

        # Fall back to generic implementation
        return await self._fallback_execute(context)

    @abstractmethod
    async def _fallback_execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback implementation when playbooks unavailable."""
        pass


# ============================================================================
# SANCTIONS & PEP HANDLERS (Playbook-Aware)
# ============================================================================

class OpenSanctionsHandler(PlaybookAwareHandler):
    """Handler for OpenSanctions API searches - uses COMPLIANCE playbooks first."""

    API_URL = "https://api.opensanctions.org/search/default"

    # Playbook configuration - route through COMPLIANCE/SANCTIONS playbooks
    playbook_categories = ["COMPLIANCE", "SANCTIONS"]
    chain_rule_id = "CHAIN_PLAYBOOK_COMPLIANCE_DEEP_DIVE"

    def __init__(self):
        super().__init__()
        self.api_key = os.getenv("OPENSANCTIONS_API_KEY", "")

    @property
    def action(self) -> str:
        return "SEARCH_SANCTIONS"

    @property
    def source_name(self) -> str:
        return "opensanctions"

    async def _fallback_execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback to direct OpenSanctions API when playbooks unavailable."""
        entity = context.get("entity", "")
        if not entity:
            return []

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        params = {
            "q": entity,
            "nested": "true",
            "limit": 25,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.API_URL,
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = data.get("results", [])
                        return [
                            {
                                "name": r.get("caption", r.get("name", "")),
                                "schema": r.get("schema", ""),
                                "datasets": r.get("datasets", []),
                                "score": r.get("score", 0),
                                "properties": r.get("properties", {}),
                                "source": "opensanctions",
                                "source_url": f"https://opensanctions.org/entities/{r.get('id', '')}",
                            }
                            for r in results
                        ]
                    else:
                        logger.warning(f"OpenSanctions returned {resp.status}")
                        return []
        except Exception as e:
            logger.error(f"OpenSanctions search failed: {e}")
            return []


class PEPSearchHandler(PlaybookAwareHandler):
    """Handler for PEP (Politically Exposed Person) searches - uses COMPLIANCE/POLITICAL playbooks."""

    API_URL = "https://api.opensanctions.org/search/default"

    # Playbook configuration - route through COMPLIANCE/POLITICAL playbooks
    playbook_categories = ["COMPLIANCE", "POLITICAL", "PEP"]
    chain_rule_id = "CHAIN_PLAYBOOK_COMPLIANCE_DEEP_DIVE"

    def __init__(self):
        super().__init__()
        self.api_key = os.getenv("OPENSANCTIONS_API_KEY", "")

    @property
    def action(self) -> str:
        return "SEARCH_PEP"

    @property
    def source_name(self) -> str:
        return "opensanctions_pep"

    async def _fallback_execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback to direct OpenSanctions API filtered for PEP."""
        entity = context.get("entity", "")
        if not entity:
            return []

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        params = {
            "q": entity,
            "nested": "true",
            "limit": 25,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.API_URL,
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = data.get("results", [])
                        all_results = [
                            {
                                "name": r.get("caption", r.get("name", "")),
                                "schema": r.get("schema", ""),
                                "datasets": r.get("datasets", []),
                                "score": r.get("score", 0),
                                "properties": r.get("properties", {}),
                                "source": "opensanctions_pep",
                                "source_url": f"https://opensanctions.org/entities/{r.get('id', '')}",
                            }
                            for r in results
                        ]

                        # Filter for PEP-related results
                        pep_datasets = {"peps", "pep", "politically_exposed"}
                        pep_results = []
                        for r in all_results:
                            datasets = set(d.lower() for d in r.get("datasets", []))
                            if datasets & pep_datasets or "pep" in r.get("schema", "").lower():
                                pep_results.append(r)

                        return pep_results if pep_results else all_results[:5]
                    else:
                        logger.warning(f"OpenSanctions returned {resp.status}")
                        return []
        except Exception as e:
            logger.error(f"OpenSanctions PEP search failed: {e}")
            return []


# ============================================================================
# CORPORATE REGISTRY HANDLERS (Playbook-Aware)
# ============================================================================

class OpenCorporatesHandler(PlaybookAwareHandler):
    """Handler for OpenCorporates API searches - uses playbooks first."""

    API_URL = "https://api.opencorporates.com/v0.4"

    # Playbook configuration
    playbook_categories = ["REGISTRY", "CORPORATE"]
    chain_rule_id = "CHAIN_PLAYBOOK_FULL_COMPANY_INTEL"

    def __init__(self):
        super().__init__()
        self.api_key = os.getenv("OPENCORPORATES_API_KEY", "")

    @property
    def action(self) -> str:
        return "SEARCH_REGISTRY"

    @property
    def source_name(self) -> str:
        return "opencorporates"

    async def _fallback_execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback to direct OpenCorporates API when playbooks unavailable."""
        entity = context.get("entity", "")
        jurisdiction = context.get("jurisdiction", "")

        if not entity:
            return []

        params = {
            "q": entity,
            "per_page": 25,
        }

        if jurisdiction:
            # Map common jurisdiction codes
            jur_map = {
                "uk": "gb", "us": "us", "de": "de", "fr": "fr",
                "bvi": "vg", "ky": "ky", "ch": "ch", "nl": "nl",
            }
            params["jurisdiction_code"] = jur_map.get(jurisdiction.lower(), jurisdiction.lower())

        if self.api_key:
            params["api_token"] = self.api_key

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.API_URL}/companies/search",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        companies = data.get("results", {}).get("companies", [])
                        return [
                            {
                                "name": c.get("company", {}).get("name", ""),
                                "company_number": c.get("company", {}).get("company_number", ""),
                                "jurisdiction": c.get("company", {}).get("jurisdiction_code", ""),
                                "status": c.get("company", {}).get("current_status", ""),
                                "incorporation_date": c.get("company", {}).get("incorporation_date", ""),
                                "address": c.get("company", {}).get("registered_address_in_full", ""),
                                "source": "opencorporates",
                                "source_url": c.get("company", {}).get("opencorporates_url", ""),
                            }
                            for c in companies
                        ]
                    else:
                        logger.warning(f"OpenCorporates returned {resp.status}")
                        return []
        except Exception as e:
            logger.error(f"OpenCorporates search failed: {e}")
            return []


class OfficersSearchHandler(PlaybookAwareHandler):
    """Handler for company officers search - uses REGISTRY/OFFICERS playbooks."""

    API_URL = "https://api.opencorporates.com/v0.4"

    # Playbook configuration - route through REGISTRY/OFFICERS playbooks
    playbook_categories = ["REGISTRY", "OFFICERS", "CORPORATE"]
    chain_rule_id = "CHAIN_PLAYBOOK_FULL_COMPANY_INTEL"

    def __init__(self):
        super().__init__()
        self.api_key = os.getenv("OPENCORPORATES_API_KEY", "")

    @property
    def action(self) -> str:
        return "SEARCH_OFFICERS"

    @property
    def source_name(self) -> str:
        return "opencorporates_officers"

    async def _fallback_execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback to direct OpenCorporates officers API."""
        entity = context.get("entity", "")
        jurisdiction = context.get("jurisdiction", "")

        if not entity:
            return []

        # First find the company
        registry_handler = OpenCorporatesHandler()
        companies = await registry_handler._fallback_execute(context)
        if not companies:
            return []

        # Get officers for the first matching company
        company = companies[0]
        company_number = company.get("company_number", "")
        jur_code = company.get("jurisdiction", jurisdiction)

        if not company_number or not jur_code:
            return []

        params = {}
        if self.api_key:
            params["api_token"] = self.api_key

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.API_URL}/companies/{jur_code}/{company_number}/officers"
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        officers = data.get("results", {}).get("officers", [])
                        return [
                            {
                                "name": o.get("officer", {}).get("name", ""),
                                "position": o.get("officer", {}).get("position", ""),
                                "start_date": o.get("officer", {}).get("start_date", ""),
                                "end_date": o.get("officer", {}).get("end_date", ""),
                                "nationality": o.get("officer", {}).get("nationality", ""),
                                "company": company.get("name", ""),
                                "source": "opencorporates",
                                "source_url": o.get("officer", {}).get("opencorporates_url", ""),
                            }
                            for o in officers
                        ]
                    else:
                        return []
        except Exception as e:
            logger.error(f"Officers search failed: {e}")
            return []


class ShareholdersSearchHandler(PlaybookAwareHandler):
    """Handler for shareholders/ownership search - uses OWNERSHIP/PSC playbooks."""

    # Playbook configuration - route through OWNERSHIP playbooks
    playbook_categories = ["OWNERSHIP", "PSC", "REGISTRY"]
    chain_rule_id = "CHAIN_PLAYBOOK_FULL_COMPANY_INTEL"

    def __init__(self):
        super().__init__()

    @property
    def action(self) -> str:
        return "SEARCH_SHAREHOLDERS"

    @property
    def source_name(self) -> str:
        return "registry_psc"

    async def _fallback_execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback to direct API calls for shareholders."""
        # Shareholders often require jurisdiction-specific handling
        # For UK, use PSC register; for others, may need commercial providers
        jurisdiction = context.get("jurisdiction", "").lower()
        entity = context.get("entity", "")

        if jurisdiction in ("uk", "gb"):
            return await self._search_uk_psc(entity)
        else:
            # Fallback to OpenCorporates which has some ownership data
            handler = OpenCorporatesHandler()
            companies = await handler._fallback_execute(context)
            # Extract any ownership info from company data
            return [
                {**c, "data_type": "company_record", "note": "Ownership data may be limited"}
                for c in companies[:5]
            ]

    async def _search_uk_psc(self, entity: str) -> List[Dict[str, Any]]:
        """Search UK PSC (Persons with Significant Control) register."""
        api_key = os.getenv("COMPANIES_HOUSE_API_KEY", "")
        if not api_key:
            logger.warning("No Companies House API key configured")
            return []

        try:
            async with aiohttp.ClientSession() as session:
                # First search for company
                auth = aiohttp.BasicAuth(api_key, "")
                async with session.get(
                    f"https://api.company-information.service.gov.uk/search/companies",
                    params={"q": entity, "items_per_page": 5},
                    auth=auth,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    items = data.get("items", [])
                    if not items:
                        return []

                    company_number = items[0].get("company_number", "")

                # Get PSC data
                async with session.get(
                    f"https://api.company-information.service.gov.uk/company/{company_number}/persons-with-significant-control",
                    auth=auth,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    pscs = data.get("items", [])
                    return [
                        {
                            "name": p.get("name", ""),
                            "nature_of_control": p.get("natures_of_control", []),
                            "notified_on": p.get("notified_on", ""),
                            "nationality": p.get("nationality", ""),
                            "country_of_residence": p.get("country_of_residence", ""),
                            "source": "companies_house_psc",
                            "source_url": f"https://find-and-update.company-information.service.gov.uk/company/{company_number}/persons-with-significant-control",
                        }
                        for p in pscs
                    ]
        except Exception as e:
            logger.error(f"UK PSC search failed: {e}")
            return []


# ============================================================================
# NEWS & MEDIA HANDLERS (Playbook-Aware)
# ============================================================================

class NewsSearchHandler(PlaybookAwareHandler):
    """Handler for news/media searches - uses MEDIA/NEWS playbooks."""

    GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

    # Playbook configuration - route through MEDIA/NEWS playbooks
    playbook_categories = ["MEDIA", "NEWS", "ADVERSE_MEDIA"]
    chain_rule_id = "CHAIN_PLAYBOOK_MEDIA_INTELLIGENCE"

    def __init__(self):
        super().__init__()

    @property
    def action(self) -> str:
        return "SEARCH_NEWS"

    @property
    def source_name(self) -> str:
        return "gdelt"

    async def _fallback_execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback to direct GDELT/NewsAPI when playbooks unavailable."""
        entity = context.get("entity", "")
        if not entity:
            return []

        # Try GDELT first (free, no API key needed)
        results = await self._search_gdelt(entity)
        if results:
            return results

        # Fallback to NewsAPI if configured
        newsapi_key = os.getenv("NEWSAPI_KEY", "")
        if newsapi_key:
            return await self._search_newsapi(entity, newsapi_key)

        return []

    async def _search_gdelt(self, query: str) -> List[Dict[str, Any]]:
        """Search GDELT for news articles."""
        params = {
            "query": query,
            "mode": "artlist",
            "maxrecords": 25,
            "format": "json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.GDELT_URL,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        articles = data.get("articles", [])
                        return [
                            {
                                "title": a.get("title", ""),
                                "url": a.get("url", ""),
                                "source": a.get("domain", ""),
                                "date": a.get("seendate", ""),
                                "language": a.get("language", ""),
                                "source_type": "gdelt",
                            }
                            for a in articles
                        ]
                    return []
        except Exception as e:
            logger.error(f"GDELT search failed: {e}")
            return []

    async def _search_newsapi(self, query: str, api_key: str) -> List[Dict[str, Any]]:
        """Search NewsAPI for news articles."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://newsapi.org/v2/everything",
                    params={"q": query, "pageSize": 25, "apiKey": api_key},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        articles = data.get("articles", [])
                        return [
                            {
                                "title": a.get("title", ""),
                                "url": a.get("url", ""),
                                "source": a.get("source", {}).get("name", ""),
                                "date": a.get("publishedAt", ""),
                                "description": a.get("description", ""),
                                "source_type": "newsapi",
                            }
                            for a in articles
                        ]
                    return []
        except Exception as e:
            logger.error(f"NewsAPI search failed: {e}")
            return []


# ============================================================================
# COURT & LEGAL HANDLERS (Playbook-Aware)
# ============================================================================

class CourtSearchHandler(PlaybookAwareHandler):
    """Handler for court/litigation searches - uses LEGAL/LITIGATION playbooks."""

    # Playbook configuration - route through LEGAL/COURT playbooks
    playbook_categories = ["LEGAL", "LITIGATION", "COURT"]
    chain_rule_id = "CHAIN_PLAYBOOK_COMPLIANCE_DEEP_DIVE"

    def __init__(self):
        super().__init__()

    @property
    def action(self) -> str:
        return "SEARCH_COURT"

    @property
    def source_name(self) -> str:
        return "court_records"

    async def _fallback_execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback to direct court searches when playbooks unavailable."""
        entity = context.get("entity", "")
        jurisdiction = context.get("jurisdiction", "").lower()

        # Try jurisdiction-specific sources
        if jurisdiction in ("uk", "gb"):
            return await self._search_uk_courts(entity)
        elif jurisdiction in ("us", "usa"):
            return await self._search_pacer(entity)
        else:
            # Fallback to news search for litigation mentions
            news_handler = NewsSearchHandler()
            news_results = await news_handler._fallback_execute({
                "entity": f'"{entity}" AND (lawsuit OR litigation OR court OR sued)'
            })
            return [
                {**r, "search_type": "litigation_news"}
                for r in news_results[:10]
            ]

    async def _search_uk_courts(self, entity: str) -> List[Dict[str, Any]]:
        """Search UK court records (placeholder - would need actual API)."""
        # Note: Real implementation would use The National Archives or similar
        return [
            {
                "note": "UK court search requires manual lookup",
                "sources": [
                    "https://www.nationalarchives.gov.uk/",
                    "https://www.bailii.org/",
                ],
                "entity": entity,
                "source": "uk_courts_manual",
            }
        ]

    async def _search_pacer(self, entity: str) -> List[Dict[str, Any]]:
        """Search US PACER (placeholder - would need PACER credentials)."""
        return [
            {
                "note": "US federal court search requires PACER access",
                "sources": ["https://pacer.uscourts.gov/"],
                "entity": entity,
                "source": "pacer_manual",
            }
        ]


# ============================================================================
# FINANCIAL HANDLERS (Playbook-Aware)
# ============================================================================

class FinancialsSearchHandler(PlaybookAwareHandler):
    """Handler for company financial searches - uses FINANCIAL playbooks."""

    EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index"

    # Playbook configuration - route through FINANCIAL playbooks
    playbook_categories = ["FINANCIAL", "FILINGS", "CORPORATE"]
    chain_rule_id = "CHAIN_PLAYBOOK_FULL_COMPANY_INTEL"

    def __init__(self):
        super().__init__()

    @property
    def action(self) -> str:
        return "SEARCH_FINANCIALS"

    @property
    def source_name(self) -> str:
        return "sec_edgar"

    async def _fallback_execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback to direct EDGAR/OpenCorporates when playbooks unavailable."""
        entity = context.get("entity", "")
        jurisdiction = context.get("jurisdiction", "").lower()

        if not entity:
            return []

        # Try SEC EDGAR for US companies
        if jurisdiction in ("us", "usa", ""):
            results = await self._search_edgar(entity)
            if results:
                return results

        # Fallback to OpenCorporates filings endpoint
        return await self._search_opencorp_filings(entity, jurisdiction)

    async def _search_edgar(self, entity: str) -> List[Dict[str, Any]]:
        """Search SEC EDGAR for company filings."""
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    "q": entity,
                    "dateRange": "custom",
                    "startdt": "2019-01-01",
                    "enddt": "2025-12-31",
                }
                async with session.get(
                    "https://efts.sec.gov/LATEST/search-index",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30),
                    headers={"User-Agent": "SASTRE Investigation Tool contact@example.com"}
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        hits = data.get("hits", {}).get("hits", [])
                        return [
                            {
                                "company": h.get("_source", {}).get("entity", ""),
                                "form": h.get("_source", {}).get("form", ""),
                                "filed": h.get("_source", {}).get("filed", ""),
                                "cik": h.get("_source", {}).get("cik", ""),
                                "source": "sec_edgar",
                                "source_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={h.get('_source', {}).get('cik', '')}&type=&dateb=&owner=include&count=40",
                            }
                            for h in hits[:25]
                        ]
                    return []
        except Exception as e:
            logger.error(f"EDGAR search failed: {e}")
            return []

    async def _search_opencorp_filings(self, entity: str, jurisdiction: str) -> List[Dict[str, Any]]:
        """Search OpenCorporates for company filings."""
        handler = OpenCorporatesHandler()
        companies = await handler._fallback_execute({"entity": entity, "jurisdiction": jurisdiction})

        # Return with financial focus
        return [
            {
                **c,
                "data_type": "company_profile",
                "note": "Check company registry for financial filings",
            }
            for c in companies[:10]
        ]


class RegulatorySearchHandler(PlaybookAwareHandler):
    """Handler for regulatory database searches - uses REGULATORY/COMPLIANCE playbooks."""

    # Playbook configuration - route through REGULATORY playbooks
    playbook_categories = ["REGULATORY", "COMPLIANCE", "ENFORCEMENT"]
    chain_rule_id = "CHAIN_PLAYBOOK_COMPLIANCE_DEEP_DIVE"

    def __init__(self):
        super().__init__()

    @property
    def action(self) -> str:
        return "SEARCH_REGULATORY"

    @property
    def source_name(self) -> str:
        return "regulatory_databases"

    async def _fallback_execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback to direct regulatory searches when playbooks unavailable."""
        entity = context.get("entity", "")
        jurisdiction = context.get("jurisdiction", "").lower()

        if not entity:
            return []

        results = []

        # Try FCA for UK financial services
        if jurisdiction in ("uk", "gb", ""):
            fca_results = await self._search_fca(entity)
            results.extend(fca_results)

        # Try SEC enforcement for US
        if jurisdiction in ("us", "usa", ""):
            sec_results = await self._search_sec_enforcement(entity)
            results.extend(sec_results)

        # Fallback to news search for regulatory mentions
        if not results:
            news_handler = NewsSearchHandler()
            news = await news_handler._fallback_execute({
                "entity": f'"{entity}" AND (regulatory OR "fine" OR "enforcement" OR "sanction")'
            })
            results.extend([{**r, "search_type": "regulatory_news"} for r in news[:10]])

        return results

    async def _search_fca(self, entity: str) -> List[Dict[str, Any]]:
        """Search FCA register."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://register.fca.org.uk/s/search",
                    params={"q": entity, "type": "Firms"},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        return [{
                            "source": "fca_register",
                            "query": entity,
                            "note": "Check FCA register manually",
                            "source_url": f"https://register.fca.org.uk/s/search?q={entity}",
                        }]
                    return []
        except Exception as e:
            logger.error(f"FCA search failed: {e}")
            return []

    async def _search_sec_enforcement(self, entity: str) -> List[Dict[str, Any]]:
        """Search SEC enforcement actions."""
        return [{
            "source": "sec_enforcement",
            "query": entity,
            "note": "Check SEC enforcement actions",
            "source_url": f"https://www.sec.gov/cgi-bin/srch-ia?text={entity}&first=1&last=40",
        }]


class BankruptcySearchHandler(PlaybookAwareHandler):
    """Handler for bankruptcy/insolvency searches - uses INSOLVENCY/LEGAL playbooks."""

    # Playbook configuration - route through INSOLVENCY playbooks
    playbook_categories = ["INSOLVENCY", "BANKRUPTCY", "LEGAL"]
    chain_rule_id = "CHAIN_PLAYBOOK_COMPLIANCE_DEEP_DIVE"

    def __init__(self):
        super().__init__()

    @property
    def action(self) -> str:
        return "SEARCH_BANKRUPTCY"

    @property
    def source_name(self) -> str:
        return "insolvency_registers"

    async def _fallback_execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback to direct insolvency searches when playbooks unavailable."""
        entity = context.get("entity", "")
        jurisdiction = context.get("jurisdiction", "").lower()

        if not entity:
            return []

        results = []

        # UK Insolvency Register
        if jurisdiction in ("uk", "gb", ""):
            results.append({
                "source": "uk_insolvency_register",
                "query": entity,
                "source_url": f"https://www.insolvencydirect.bis.gov.uk/eiir/IIRSearch.asp",
                "note": "Search UK Individual Insolvency Register",
            })
            results.append({
                "source": "companies_house_insolvency",
                "query": entity,
                "source_url": f"https://find-and-update.company-information.service.gov.uk/search?q={entity}",
                "note": "Check Companies House for insolvency status",
            })

        # German Insolvency
        if jurisdiction in ("de", "germany"):
            results.append({
                "source": "insolvenzbekanntmachungen",
                "query": entity,
                "source_url": f"https://www.insolvenzbekanntmachungen.de/cgi-bin/bl_aufruf.pl",
                "note": "Search German insolvency announcements",
            })

        # US Bankruptcy
        if jurisdiction in ("us", "usa", ""):
            results.append({
                "source": "pacer_bankruptcy",
                "query": entity,
                "source_url": "https://pacer.uscourts.gov/",
                "note": "Search PACER for bankruptcy filings (account required)",
            })

        # Fallback to news
        if not results:
            news_handler = NewsSearchHandler()
            news = await news_handler._fallback_execute({
                "entity": f'"{entity}" AND (bankruptcy OR insolvency OR liquidation OR "wound up")'
            })
            results.extend([{**r, "search_type": "bankruptcy_news"} for r in news[:10]])

        return results


class PropertySearchHandler(PlaybookAwareHandler):
    """Handler for property/land registry searches - uses PROPERTY playbooks."""

    # Playbook configuration - route through PROPERTY playbooks
    playbook_categories = ["PROPERTY", "LAND_REGISTRY", "REAL_ESTATE"]
    chain_rule_id = "CHAIN_PLAYBOOK_FULL_COMPANY_INTEL"

    def __init__(self):
        super().__init__()

    @property
    def action(self) -> str:
        return "SEARCH_PROPERTY"

    @property
    def source_name(self) -> str:
        return "land_registries"

    async def _fallback_execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback to direct property searches when playbooks unavailable."""
        entity = context.get("entity", "")
        jurisdiction = context.get("jurisdiction", "").lower()

        if not entity:
            return []

        results = []

        # UK Land Registry
        if jurisdiction in ("uk", "gb", "england", "wales"):
            results.append({
                "source": "uk_land_registry",
                "query": entity,
                "source_url": "https://search-property-information.service.gov.uk/",
                "note": "Search UK Land Registry (fee applies)",
            })
            results.append({
                "source": "uk_overseas_entities",
                "query": entity,
                "source_url": f"https://find-and-update.company-information.service.gov.uk/register-an-overseas-entity?q={entity}",
                "note": "Check Register of Overseas Entities",
            })

        # US Property Records
        if jurisdiction in ("us", "usa", ""):
            results.append({
                "source": "us_property_records",
                "query": entity,
                "note": "US property records vary by county - check county assessor",
            })

        return results if results else [{
            "source": "property_search_manual",
            "query": entity,
            "note": f"Property records for {jurisdiction or 'unknown jurisdiction'} require manual lookup",
        }]


class CreditSearchHandler(PlaybookAwareHandler):
    """Handler for credit/financial standing searches - uses FINANCIAL/CREDIT playbooks."""

    # Playbook configuration - route through CREDIT playbooks
    playbook_categories = ["CREDIT", "FINANCIAL", "RATING"]
    chain_rule_id = "CHAIN_PLAYBOOK_FULL_COMPANY_INTEL"

    def __init__(self):
        super().__init__()

    @property
    def action(self) -> str:
        return "SEARCH_CREDIT"

    @property
    def source_name(self) -> str:
        return "credit_reports"

    async def _fallback_execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback to credit provider guidance when playbooks unavailable."""
        entity = context.get("entity", "")

        if not entity:
            return []

        # Credit data requires commercial providers
        return [
            {
                "source": "credit_search_note",
                "query": entity,
                "note": "Credit data requires commercial providers (D&B, Experian Business, Creditsafe)",
                "commercial_sources": [
                    "https://www.dnb.com/",
                    "https://www.experian.com/business/",
                    "https://www.creditsafe.com/",
                ],
            }
        ]


class CompetitorsSearchHandler(PlaybookAwareHandler):
    """Handler for competitor/industry analysis - uses MARKET/INDUSTRY playbooks."""

    # Playbook configuration - route through MARKET playbooks
    playbook_categories = ["MARKET", "INDUSTRY", "COMPETITORS"]
    chain_rule_id = "CHAIN_PLAYBOOK_FULL_COMPANY_INTEL"

    def __init__(self):
        super().__init__()

    @property
    def action(self) -> str:
        return "SEARCH_COMPETITORS"

    @property
    def source_name(self) -> str:
        return "industry_analysis"

    async def _fallback_execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback to news-based competitor analysis when playbooks unavailable."""
        entity = context.get("entity", "")

        if not entity:
            return []

        # Use news search for competitor analysis
        news_handler = NewsSearchHandler()
        results = await news_handler._fallback_execute({
            "entity": f'"{entity}" AND (competitor OR rival OR "market share" OR industry)'
        })

        return [
            {
                **r,
                "search_type": "competitor_analysis",
            }
            for r in results[:15]
        ]


class ContractsSearchHandler(PlaybookAwareHandler):
    """Handler for government contracts/procurement searches - uses PROCUREMENT playbooks."""

    # Playbook configuration - route through PROCUREMENT playbooks
    playbook_categories = ["PROCUREMENT", "CONTRACTS", "GOVERNMENT"]
    chain_rule_id = "CHAIN_PLAYBOOK_FULL_COMPANY_INTEL"

    def __init__(self):
        super().__init__()

    @property
    def action(self) -> str:
        return "SEARCH_CONTRACTS"

    @property
    def source_name(self) -> str:
        return "procurement_databases"

    async def _fallback_execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback to direct procurement searches when playbooks unavailable."""
        entity = context.get("entity", "")
        jurisdiction = context.get("jurisdiction", "").lower()

        if not entity:
            return []

        results = []

        # EU TED (Tenders Electronic Daily)
        if jurisdiction in ("eu", "uk", "de", "fr", "it", "es", "nl", ""):
            results.append({
                "source": "ted_europa",
                "query": entity,
                "source_url": f"https://ted.europa.eu/TED/search/search.do?query={entity}",
                "note": "EU public procurement database",
            })

        # US Federal Contracts
        if jurisdiction in ("us", "usa", ""):
            results.append({
                "source": "usaspending",
                "query": entity,
                "source_url": f"https://www.usaspending.gov/search?hash=&q={entity}",
                "note": "US federal spending and contracts",
            })
            results.append({
                "source": "sam_gov",
                "query": entity,
                "source_url": f"https://sam.gov/search/?q={entity}",
                "note": "System for Award Management",
            })

        # UK Government Contracts
        if jurisdiction in ("uk", "gb", ""):
            results.append({
                "source": "uk_contracts_finder",
                "query": entity,
                "source_url": f"https://www.contractsfinder.service.gov.uk/Search/Results?s={entity}",
                "note": "UK government contracts",
            })

        return results


class EnvironmentalSearchHandler(PlaybookAwareHandler):
    """Handler for environmental records/permits - uses ENVIRONMENTAL playbooks."""

    # Playbook configuration - route through ENVIRONMENTAL playbooks
    playbook_categories = ["ENVIRONMENTAL", "REGULATORY", "PERMITS"]
    chain_rule_id = "CHAIN_PLAYBOOK_FULL_COMPANY_INTEL"

    def __init__(self):
        super().__init__()

    @property
    def action(self) -> str:
        return "SEARCH_ENVIRONMENTAL"

    @property
    def source_name(self) -> str:
        return "environmental_registers"

    async def _fallback_execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback to direct environmental searches when playbooks unavailable."""
        entity = context.get("entity", "")
        jurisdiction = context.get("jurisdiction", "").lower()

        if not entity:
            return []

        results = []

        # US EPA
        if jurisdiction in ("us", "usa", ""):
            results.append({
                "source": "epa_echo",
                "query": entity,
                "source_url": f"https://echo.epa.gov/facilities/facility-search?s={entity}",
                "note": "EPA Enforcement and Compliance History",
            })

        # UK Environment Agency
        if jurisdiction in ("uk", "gb", "england"):
            results.append({
                "source": "uk_environment_agency",
                "query": entity,
                "source_url": "https://environment.data.gov.uk/public-register/view/search-all",
                "note": "UK Environment Agency public registers",
            })

        # EU Environmental Data
        if jurisdiction in ("eu", "de", "fr", ""):
            results.append({
                "source": "eu_prtr",
                "query": entity,
                "source_url": f"https://industry.eea.europa.eu/",
                "note": "EU Industrial Emissions Portal",
            })

        # Fallback to news
        if not results:
            news_handler = NewsSearchHandler()
            news = await news_handler._fallback_execute({
                "entity": f'"{entity}" AND (environmental OR pollution OR EPA OR permit)'
            })
            results.extend([{**r, "search_type": "environmental_news"} for r in news[:10]])

        return results


class TaxSearchHandler(PlaybookAwareHandler):
    """Handler for tax-related searches - uses FINANCIAL/TAX playbooks."""

    # Playbook configuration - route through TAX playbooks
    playbook_categories = ["TAX", "FINANCIAL", "FISCAL"]
    chain_rule_id = "CHAIN_PLAYBOOK_FULL_COMPANY_INTEL"

    def __init__(self):
        super().__init__()

    @property
    def action(self) -> str:
        return "SEARCH_TAX"

    @property
    def source_name(self) -> str:
        return "tax_records"

    async def _fallback_execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback to news-based tax search when playbooks unavailable."""
        entity = context.get("entity", "")

        if not entity:
            return []

        # Tax records are rarely public - search news for tax-related issues
        news_handler = NewsSearchHandler()
        results = await news_handler._fallback_execute({
            "entity": f'"{entity}" AND (tax OR HMRC OR IRS OR "tax evasion" OR "tax avoidance")'
        })

        return [
            {
                **r,
                "search_type": "tax_news",
                "note": "Tax records rarely public - news search for tax issues",
            }
            for r in results[:15]
        ]


class IntellectualPropertyHandler(PlaybookAwareHandler):
    """Handler for patents, trademarks, IP searches - uses IP playbooks."""

    # Playbook configuration - route through IP playbooks
    playbook_categories = ["IP", "PATENTS", "TRADEMARKS"]
    chain_rule_id = "CHAIN_PLAYBOOK_FULL_COMPANY_INTEL"

    def __init__(self):
        super().__init__()

    @property
    def action(self) -> str:
        return "SEARCH_INTELLECTUAL_PROPERTY"

    @property
    def source_name(self) -> str:
        return "ip_registries"

    async def _fallback_execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback to direct IP registry searches when playbooks unavailable."""
        entity = context.get("entity", "")

        if not entity:
            return []

        results = []

        # USPTO Patents
        results.append({
            "source": "uspto_patents",
            "query": entity,
            "source_url": f"https://patft.uspto.gov/netacgi/nph-Parser?Sect1=PTO2&Sect2=HITOFF&p=1&u=%2Fnetahtml%2FPTO%2Fsearch-bool.html&r=0&f=S&l=50&TERM1={entity}&FIELD1=ASNM&co1=AND&TERM2=&FIELD2=&d=PTXT",
            "note": "US Patent and Trademark Office",
        })

        # USPTO Trademarks
        results.append({
            "source": "uspto_trademarks",
            "query": entity,
            "source_url": f"https://tmsearch.uspto.gov/bin/showfield?f=toc&state=4801%3Ar38h01.1.1&p_search=searchss&p_L=50&BackReference=&p_plural=yes&p_s_PARA1=&p_taession=1&p_s_PARA2={entity}",
            "note": "US Trademark search",
        })

        # EPO Patents
        results.append({
            "source": "epo_espacenet",
            "query": entity,
            "source_url": f"https://worldwide.espacenet.com/searchResults?submitted=true&locale=en_EP&DB=EPODOC&ST=singleline&query={entity}",
            "note": "European Patent Office",
        })

        # WIPO Global Brand Database
        results.append({
            "source": "wipo_brands",
            "query": entity,
            "source_url": f"https://branddb.wipo.int/en/quicksearch?by=brandName&v={entity}",
            "note": "WIPO Global Brand Database",
        })

        return results


class EmployeeSearchHandler(PlaybookAwareHandler):
    """Handler for employee/workforce searches - uses HR/EMPLOYEE playbooks."""

    # Playbook configuration - route through HR playbooks
    playbook_categories = ["HR", "EMPLOYEE", "WORKFORCE"]
    chain_rule_id = "CHAIN_PLAYBOOK_FULL_COMPANY_INTEL"

    def __init__(self):
        super().__init__()

    @property
    def action(self) -> str:
        return "SEARCH_EMPLOYEE"

    @property
    def source_name(self) -> str:
        return "career_platforms"

    async def _fallback_execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback to LinkedIn/news search when playbooks unavailable."""
        entity = context.get("entity", "")  # Company name

        if not entity:
            return []

        results = []

        # LinkedIn company employees
        results.append({
            "source": "linkedin_employees",
            "query": entity,
            "source_url": f"https://www.linkedin.com/search/results/people/?currentCompany=%5B%22{entity}%22%5D",
            "note": "Search LinkedIn for current/former employees",
        })

        # News about employees
        news_handler = NewsSearchHandler()
        news = await news_handler._fallback_execute({
            "entity": f'"{entity}" AND (employee OR workforce OR staff OR hiring OR layoff)'
        })
        results.extend([{**r, "search_type": "employee_news"} for r in news[:10]])

        return results


class RelatedPartiesHandler(PlaybookAwareHandler):
    """Handler for related party/connected entity searches - uses NETWORK playbooks."""

    # Playbook configuration - route through NETWORK playbooks
    playbook_categories = ["NETWORK", "RELATED", "CONNECTIONS"]
    chain_rule_id = "CHAIN_PLAYBOOK_FULL_COMPANY_INTEL"

    def __init__(self):
        super().__init__()

    @property
    def action(self) -> str:
        return "SEARCH_RELATED_PARTIES"

    @property
    def source_name(self) -> str:
        return "graph_analysis"

    async def _fallback_execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback to multi-source related party search when playbooks unavailable."""
        entity = context.get("entity", "")

        if not entity:
            return []

        results = []

        # OpenCorporates for related companies
        handler = OpenCorporatesHandler()
        companies = await handler._fallback_execute(context)
        results.extend([{**c, "relationship": "corporate_registry"} for c in companies[:5]])

        # Officers for the same company
        officers_handler = OfficersSearchHandler()
        officers = await officers_handler._fallback_execute(context)
        results.extend([{**o, "relationship": "officer"} for o in officers[:10]])

        # News for related entities
        news_handler = NewsSearchHandler()
        news = await news_handler._fallback_execute({
            "entity": f'"{entity}" AND (subsidiary OR affiliate OR parent OR partner)'
        })
        results.extend([{**r, "relationship": "news_mention"} for r in news[:10]])

        return results


class CareerSearchHandler(PlaybookAwareHandler):
    """Handler for career/professional background searches - uses CAREER/PROFESSIONAL playbooks."""

    # Playbook configuration - route through CAREER playbooks
    playbook_categories = ["CAREER", "PROFESSIONAL", "LINKEDIN"]
    chain_rule_id = "CHAIN_PLAYBOOK_GLOBAL_PERSON_PROFILE"

    def __init__(self):
        super().__init__()

    @property
    def action(self) -> str:
        return "SEARCH_CAREER"

    @property
    def source_name(self) -> str:
        return "career_platforms"

    async def _fallback_execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback to career platform searches when playbooks unavailable."""
        entity = context.get("entity", "")  # Person name

        if not entity:
            return []

        results = []

        # LinkedIn profile search
        results.append({
            "source": "linkedin",
            "query": entity,
            "source_url": f"https://www.linkedin.com/search/results/people/?keywords={entity}",
            "note": "LinkedIn profile search",
        })

        # Other career platforms
        results.append({
            "source": "xing",
            "query": entity,
            "source_url": f"https://www.xing.com/search/members?keywords={entity}",
            "note": "XING (DACH region)",
        })

        # News for career mentions
        news_handler = NewsSearchHandler()
        news = await news_handler._fallback_execute({
            "entity": f'"{entity}" AND (appointed OR resigned OR CEO OR director OR executive)'
        })
        results.extend([{**r, "search_type": "career_news"} for r in news[:10]])

        return results


class EducationSearchHandler(PlaybookAwareHandler):
    """Handler for educational background searches - uses EDUCATION/ACADEMIC playbooks."""

    # Playbook configuration - route through EDUCATION playbooks
    playbook_categories = ["EDUCATION", "ACADEMIC", "UNIVERSITY"]
    chain_rule_id = "CHAIN_PLAYBOOK_GLOBAL_PERSON_PROFILE"

    def __init__(self):
        super().__init__()

    @property
    def action(self) -> str:
        return "SEARCH_EDUCATION"

    @property
    def source_name(self) -> str:
        return "education_records"

    async def _fallback_execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback to education-related searches when playbooks unavailable."""
        entity = context.get("entity", "")

        if not entity:
            return []

        results = []

        # Educational records mostly private - use public sources
        results.append({
            "source": "education_note",
            "query": entity,
            "note": "Educational records require consent or commercial providers",
            "alternatives": [
                "LinkedIn education section",
                "University alumni directories",
                "News/press releases",
            ],
        })

        # News search for educational mentions
        news_handler = NewsSearchHandler()
        news = await news_handler._fallback_execute({
            "entity": f'"{entity}" AND (university OR degree OR graduated OR MBA OR PhD)'
        })
        results.extend([{**r, "search_type": "education_news"} for r in news[:10]])

        return results


class FamilySearchHandler(PlaybookAwareHandler):
    """Handler for family/relationship searches - uses FAMILY/PERSONAL playbooks."""

    # Playbook configuration - route through FAMILY playbooks
    playbook_categories = ["FAMILY", "PERSONAL", "RELATIONSHIPS"]
    chain_rule_id = "CHAIN_PLAYBOOK_GLOBAL_PERSON_PROFILE"

    def __init__(self):
        super().__init__()

    @property
    def action(self) -> str:
        return "SEARCH_FAMILY"

    @property
    def source_name(self) -> str:
        return "public_records"

    async def _fallback_execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback to public records/news for family info when playbooks unavailable."""
        entity = context.get("entity", "")

        if not entity:
            return []

        results = []

        # Family records mostly private - use public sources
        results.append({
            "source": "family_note",
            "query": entity,
            "note": "Family records require consent or specific registries",
            "alternatives": [
                "Social media profiles",
                "News/society pages",
                "Company disclosures (for related-party transactions)",
            ],
        })

        # News search for family mentions
        news_handler = NewsSearchHandler()
        news = await news_handler._fallback_execute({
            "entity": f'"{entity}" AND (wife OR husband OR son OR daughter OR family OR married)'
        })
        results.extend([{**r, "search_type": "family_news"} for r in news[:10]])

        return results


class SocialMediaHandler(PlaybookAwareHandler):
    """Handler for social media searches - uses SOCIAL playbooks."""

    # Playbook configuration - route through SOCIAL playbooks
    playbook_categories = ["SOCIAL", "SOCIAL_MEDIA", "ONLINE"]
    chain_rule_id = "CHAIN_PLAYBOOK_GLOBAL_PERSON_PROFILE"

    def __init__(self):
        super().__init__()

    @property
    def action(self) -> str:
        return "SEARCH_SOCIAL"

    @property
    def source_name(self) -> str:
        return "social_media"

    async def _fallback_execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback to direct platform searches when playbooks unavailable."""
        entity = context.get("entity", "")

        if not entity:
            return []

        results = []

        # Direct platform searches
        platforms = [
            ("twitter", f"https://twitter.com/search?q={entity}"),
            ("facebook", f"https://www.facebook.com/search/top?q={entity}"),
            ("instagram", f"https://www.instagram.com/explore/tags/{entity.replace(' ', '')}"),
            ("tiktok", f"https://www.tiktok.com/search?q={entity}"),
            ("youtube", f"https://www.youtube.com/results?search_query={entity}"),
            ("reddit", f"https://www.reddit.com/search/?q={entity}"),
        ]

        for platform, url in platforms:
            results.append({
                "source": platform,
                "query": entity,
                "source_url": url,
                "note": f"Search {platform.title()} for mentions",
            })

        return results


# ============================================================================
# ARCHIVE HANDLERS
# ============================================================================

class ArchiveSearchHandler(PlaybookAwareHandler):
    """Handler for archive.org / Wayback Machine searches - uses ARCHIVE playbooks."""

    WAYBACK_API = "https://web.archive.org/cdx/search/cdx"

    # Playbook configuration - route through ARCHIVE/WEBSITE playbooks
    playbook_categories = ["ARCHIVE", "WEBSITE", "DOMAIN", "HISTORICAL"]
    chain_rule_id = "CHAIN_PLAYBOOK_DOMAIN_TO_CORPORATE"

    @property
    def action(self) -> str:
        return "SEARCH_WEBSITE"

    @property
    def source_name(self) -> str:
        return "wayback_machine"

    async def _fallback_execute(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback to direct Wayback API when playbooks unavailable."""
        entity = context.get("entity", "")
        domain = context.get("domain", "")

        if not domain and not entity:
            return []

        # If we have a domain, search Wayback
        if domain:
            return await self._search_wayback(domain)

        # Otherwise search for entity mentions in archived pages
        return []

    async def _search_wayback(self, domain: str) -> List[Dict[str, Any]]:
        """Search Wayback Machine for archived pages."""
        params = {
            "url": domain,
            "output": "json",
            "limit": 25,
            "fl": "timestamp,original,statuscode,mimetype",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.WAYBACK_API,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        lines = (await resp.text()).strip().split("\n")
                        if len(lines) < 2:
                            return []

                        results = []
                        for line in lines[1:]:  # Skip header
                            try:
                                parts = line.strip("[]").split(",")
                                if len(parts) >= 4:
                                    timestamp = parts[0].strip('" ')
                                    url = parts[1].strip('" ')
                                    results.append({
                                        "url": url,
                                        "timestamp": timestamp,
                                        "archive_url": f"https://web.archive.org/web/{timestamp}/{url}",
                                        "source": "wayback_machine",
                                    })
                            except:
                                continue
                        return results
                    return []
        except Exception as e:
            logger.error(f"Wayback search failed: {e}")
            return []


# ============================================================================
# HANDLER REGISTRY
# ============================================================================

class ActionHandlerRegistry:
    """
    Central registry of action handlers.

    Maps ALLOWED_ACTIONS to their handler implementations.
    Provides unified execution interface.
    """

    def __init__(self):
        self._handlers: Dict[str, BaseActionHandler] = {}
        self._register_defaults()

    def _register_defaults(self):
        """Register default handlers for ALL 24 ALLOWED_ACTIONS."""
        default_handlers = [
            # Sanctions & PEP (2)
            OpenSanctionsHandler(),
            PEPSearchHandler(),
            # Corporate Registry (3)
            OpenCorporatesHandler(),
            OfficersSearchHandler(),
            ShareholdersSearchHandler(),
            # Financial (4)
            FinancialsSearchHandler(),
            RegulatorySearchHandler(),
            BankruptcySearchHandler(),
            CreditSearchHandler(),
            TaxSearchHandler(),
            # Legal (1)
            CourtSearchHandler(),
            # Property & Contracts (3)
            PropertySearchHandler(),
            ContractsSearchHandler(),
            EnvironmentalSearchHandler(),
            # IP (1)
            IntellectualPropertyHandler(),
            # News & Media (2)
            NewsSearchHandler(),
            ArchiveSearchHandler(),
            # People/HR (4)
            EmployeeSearchHandler(),
            CareerSearchHandler(),
            EducationSearchHandler(),
            FamilySearchHandler(),
            # Social & Related (3)
            SocialMediaHandler(),
            RelatedPartiesHandler(),
            CompetitorsSearchHandler(),
        ]

        for handler in default_handlers:
            self.register(handler)

    def register(self, handler: BaseActionHandler):
        """Register a handler for its action."""
        self._handlers[handler.action] = handler
        logger.debug(f"Registered handler for {handler.action}: {handler.source_name}")

    def get_handler(self, action: str) -> Optional[BaseActionHandler]:
        """Get handler for an action."""
        return self._handlers.get(action)

    async def execute(
        self,
        action: str,
        context: Dict[str, Any]
    ) -> ActionResult:
        """
        Execute an action with its registered handler.

        Args:
            action: ALLOWED_ACTION name
            context: Execution context

        Returns:
            ActionResult with results or error
        """
        handler = self.get_handler(action)

        if not handler:
            return ActionResult(
                action=action,
                source="none",
                success=False,
                results=[],
                error=f"No handler registered for {action}",
            )

        try:
            results = await handler.execute(context)
            return ActionResult(
                action=action,
                source=handler.source_name,
                success=True,
                results=results,
            )
        except Exception as e:
            logger.error(f"Handler {action} failed: {e}")
            return ActionResult(
                action=action,
                source=handler.source_name,
                success=False,
                results=[],
                error=str(e),
            )

    def list_handlers(self) -> Dict[str, str]:
        """List all registered handlers."""
        return {
            action: handler.source_name
            for action, handler in self._handlers.items()
        }


# Create global registry instance
action_registry = ActionHandlerRegistry()


# Convenience function for ResilientExecutor integration
async def execute_action(action: str, context: Dict[str, Any]) -> List[Dict]:
    """Execute action via global registry."""
    result = await action_registry.execute(action, context)
    return result.results if result.success else []


if __name__ == "__main__":
    async def demo():
        print("=" * 60)
        print("SASTRE Action Handlers Demo")
        print("=" * 60)

        registry = ActionHandlerRegistry()
        print("\nRegistered handlers:")
        for action, source in registry.list_handlers().items():
            print(f"  {action}: {source}")

        # Test a few handlers
        test_cases = [
            ("SEARCH_SANCTIONS", {"entity": "Gazprom"}),
            ("SEARCH_REGISTRY", {"entity": "Apple Inc", "jurisdiction": "us"}),
            ("SEARCH_NEWS", {"entity": "Tesla"}),
        ]

        for action, context in test_cases:
            print(f"\n{'─' * 60}")
            print(f"Testing {action}: {context}")
            print(f"{'─' * 60}")

            result = await registry.execute(action, context)
            print(f"Success: {result.success}")
            print(f"Source: {result.source}")
            print(f"Results: {len(result.results)}")

            if result.results:
                for r in result.results[:3]:
                    name = r.get("name") or r.get("title") or str(r)[:50]
                    print(f"  - {name}")

            if result.error:
                print(f"Error: {result.error}")

    asyncio.run(demo())
