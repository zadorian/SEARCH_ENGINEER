#!/usr/bin/env python3
"""
Corporella MCP Server - Company Intelligence (v2.0)

Direct Python integration with CORPORELLA modules:
- UltimateCorporateSearch: Multi-source search with AI consolidation
- CompaniesHouseAPI: UK company registry with PSC/officers
- AlephSearcher: OCCRP Aleph async search
- SmartRouter: Intelligent source selection
- OpenSanctions: Sanctions screening

No external HTTP dependencies - all searches run directly.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add corporella to path
CORPORELLA_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(CORPORELLA_ROOT))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("corporella-mcp")

try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
    import mcp.server.stdio
except ImportError:
    logger.error("MCP SDK not installed. Run: pip install mcp")
    sys.exit(1)

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv(CORPORELLA_ROOT / ".env")
    load_dotenv(CORPORELLA_ROOT.parent / "SASTRE" / ".env")
except ImportError:
    pass

# Import CORPORELLA modules
MODULES_AVAILABLE = {
    "corporate_search": False,
    "companies_house": False,
    "aleph": False,
    "opensanctions": False,
    "smart_router": False,
}

try:
    from corporate_search import UltimateCorporateSearch
    MODULES_AVAILABLE["corporate_search"] = True
    logger.info("UltimateCorporateSearch loaded")
except ImportError as e:
    logger.warning(f"UltimateCorporateSearch not available: {e}")
    UltimateCorporateSearch = None

try:
    from occrp_aleph import AlephSearcher, search_occrp
    MODULES_AVAILABLE["aleph"] = True
    logger.info("AlephSearcher loaded")
except ImportError as e:
    logger.warning(f"AlephSearcher not available: {e}")
    AlephSearcher = None
    search_occrp = None

try:
    from opensanctions import opensanctions_search
    MODULES_AVAILABLE["opensanctions"] = True
    logger.info("OpenSanctions search loaded")
except ImportError as e:
    logger.warning(f"OpenSanctions not available: {e}")
    opensanctions_search = None

try:
    from smart_router import SmartRouter, UserInput, TargetType
    MODULES_AVAILABLE["smart_router"] = True
    logger.info("SmartRouter loaded")
except ImportError as e:
    logger.warning(f"SmartRouter not available: {e}")
    SmartRouter = None


class CorporellaMCP:
    """Corporella MCP Server - Company Intelligence (v2.0)"""

    def __init__(self):
        self.server = Server("corporella")

        # Initialize available modules with error handling
        self.corporate_searcher = None
        self.ch_api = None
        self.aleph_searcher = None
        self.smart_router = None

        if UltimateCorporateSearch:
            try:
                self.corporate_searcher = UltimateCorporateSearch()
            except Exception as e:
                logger.warning(f"Could not initialize UltimateCorporateSearch: {e}")

        if CompaniesHouseAPI:
            try:
                self.ch_api = CompaniesHouseAPI()
            except Exception as e:
                logger.warning(f"Could not initialize CompaniesHouseAPI: {e}")

        if AlephSearcher:
            try:
                self.aleph_searcher = AlephSearcher()
            except Exception as e:
                logger.warning(f"Could not initialize AlephSearcher: {e}")

        if SmartRouter:
            try:
                self.smart_router = SmartRouter()
            except Exception as e:
                logger.warning(f"Could not initialize SmartRouter: {e}")

        self._register_handlers()

    def _register_handlers(self):
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            tools = [
                Tool(
                    name="search_company",
                    description="Search for companies by name across multiple sources (OpenCorporates, OCCRP Aleph, Companies House). Returns matching companies with basic info.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Company name to search"},
                            "jurisdiction": {"type": "string", "description": "ISO country code (e.g., GB, US, DE, CY)"},
                            "limit": {"type": "integer", "default": 20, "description": "Max results to return"}
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="enrich_company",
                    description="Full company enrichment with AI consolidation. Searches OpenCorporates, OCCRP Aleph, OpenSanctions, Companies House (UK), and SEC EDGAR (US). Uses GPT to consolidate and identify beneficial owners, officers, risk factors.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "company_name": {"type": "string", "description": "Company name"},
                            "jurisdiction": {"type": "string", "description": "ISO country code (helps focus search)"},
                        },
                        "required": ["company_name"]
                    }
                ),
                Tool(
                    name="search_registry",
                    description="Search UK Companies House registry. Returns official records with company details, officers, and PSC (beneficial ownership) data.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Company name or number"},
                            "jurisdiction": {"type": "string", "description": "Currently only GB/UK supported"},
                            "include_officers": {"type": "boolean", "default": True, "description": "Include officer data"},
                            "include_psc": {"type": "boolean", "default": True, "description": "Include PSC (beneficial ownership) data"}
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="get_officers",
                    description="Get company officers (directors, secretaries, executives) from UK Companies House.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "company_name": {"type": "string", "description": "Company name"},
                            "company_number": {"type": "string", "description": "UK company number (if known)"},
                            "jurisdiction": {"type": "string", "description": "ISO country code (GB for UK)"}
                        },
                        "required": ["company_name"]
                    }
                ),
                Tool(
                    name="get_shareholders",
                    description="Get company shareholders and ownership structure from UK Companies House PSC data.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "company_name": {"type": "string", "description": "Company name"},
                            "company_number": {"type": "string", "description": "UK company number (if known)"},
                            "jurisdiction": {"type": "string", "description": "ISO country code"}
                        },
                        "required": ["company_name"]
                    }
                ),
                Tool(
                    name="get_beneficial_owners",
                    description="Get beneficial owners (PSC - Persons with Significant Control) from UK Companies House. Shows who ultimately controls the company.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "company_name": {"type": "string", "description": "Company name"},
                            "company_number": {"type": "string", "description": "UK company number (if known)"},
                            "jurisdiction": {"type": "string", "description": "ISO country code (GB for UK)"}
                        },
                        "required": ["company_name"]
                    }
                ),
                Tool(
                    name="get_filings",
                    description="Get company filing history (annual returns, accounts, changes) from UK Companies House.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "company_name": {"type": "string", "description": "Company name"},
                            "company_number": {"type": "string", "description": "UK company number (if known)"},
                            "jurisdiction": {"type": "string", "description": "ISO country code"},
                            "limit": {"type": "integer", "default": 20, "description": "Max filings to return"}
                        },
                        "required": ["company_name"]
                    }
                ),
                Tool(
                    name="find_common_links",
                    description="Find common directors/shareholders between two companies.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "company_a": {"type": "string", "description": "First company name"},
                            "company_b": {"type": "string", "description": "Second company name"},
                            "jurisdiction": {"type": "string", "description": "ISO country code (optional)"}
                        },
                        "required": ["company_a", "company_b"]
                    }
                ),
                Tool(
                    name="search_aleph",
                    description="Search OCCRP Aleph database for entities, documents, and leaked data. Great for investigative journalism sources.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "schema": {"type": "string", "description": "Entity type: Company, Person, Document, LegalEntity", "default": "Company"},
                            "max_results": {"type": "integer", "default": 50, "description": "Max results"}
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="search_sanctions",
                    description="Search OpenSanctions database for sanctions, watchlists, and PEP data.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Name to search (person or company)"},
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="search_person",
                    description="Search for a person across corporate registries, sanctions lists, and leaks (Aleph + OpenSanctions).",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Person name to search"},
                            "jurisdiction": {"type": "string", "description": "ISO country code (optional)"}
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="smart_route",
                    description="Get intelligent routing recommendations for a corporate search. Returns prioritized list of sources to query based on jurisdiction and search target.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "company_name": {"type": "string", "description": "Company name (optional)"},
                            "person_name": {"type": "string", "description": "Person name (optional)"},
                            "country": {"type": "string", "description": "ISO country code"},
                            "target": {
                                "type": "string",
                                "description": "Search target type",
                                "enum": ["company_profile", "ownership", "person_dd", "regulatory", "sanctions", "political_exposure", "generic"]
                            }
                        },
                        "required": ["country"]
                    }
                ),
            ]
            return tools

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Any) -> list[TextContent]:
            try:
                result = await self._handle_tool(name, arguments)
                return [TextContent(type="text", text=json.dumps(result, default=str, indent=2))]
            except Exception as e:
                logger.error(f"Tool {name} error: {e}", exc_info=True)
                return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    async def _handle_tool(self, name: str, arguments: dict) -> dict:
        """Route tool calls to appropriate handlers."""

        if name == "search_company":
            return await self._search_company(
                arguments["query"],
                arguments.get("jurisdiction"),
                arguments.get("limit", 20)
            )

        elif name == "enrich_company":
            return await self._enrich_company(
                arguments["company_name"],
                arguments.get("jurisdiction")
            )

        elif name == "search_registry":
            return await self._search_registry(
                arguments["query"],
                arguments.get("jurisdiction", "GB"),
                arguments.get("include_officers", True),
                arguments.get("include_psc", True)
            )

        elif name == "get_officers":
            return await self._get_officers(
                arguments["company_name"],
                arguments.get("company_number"),
                arguments.get("jurisdiction")
            )

        elif name == "get_shareholders":
            return await self._get_shareholders(
                arguments["company_name"],
                arguments.get("company_number"),
                arguments.get("jurisdiction")
            )

        elif name == "get_beneficial_owners":
            return await self._get_beneficial_owners(
                arguments["company_name"],
                arguments.get("company_number"),
                arguments.get("jurisdiction")
            )

        elif name == "get_filings":
            return await self._get_filings(
                arguments["company_name"],
                arguments.get("company_number"),
                arguments.get("jurisdiction"),
                arguments.get("limit", 20)
            )

        elif name == "find_common_links":
            return await self._find_common_links(
                arguments["company_a"],
                arguments["company_b"],
                arguments.get("jurisdiction")
            )

        elif name == "search_aleph":
            return await self._search_aleph(
                arguments["query"],
                arguments.get("schema", "Company"),
                arguments.get("max_results", 50)
            )

        elif name == "search_sanctions":
            return await self._search_sanctions(arguments["query"])

        elif name == "search_person":
            return await self._search_person(
                arguments["query"],
                arguments.get("jurisdiction")
            )

        elif name == "smart_route":
            return await self._smart_route(
                arguments.get("company_name"),
                arguments.get("person_name"),
                arguments.get("country"),
                arguments.get("target", "generic")
            )

        else:
            return {"error": f"Unknown tool: {name}"}

    # =========================================================================
    # TOOL IMPLEMENTATIONS
    # =========================================================================

    async def _search_company(self, query: str, jurisdiction: str = None, limit: int = 20) -> dict:
        """Search for companies across multiple sources."""
        results = {
            "query": query,
            "jurisdiction": jurisdiction,
            "sources_searched": [],
            "results": []
        }

        # Search OCCRP Aleph
        if self.aleph_searcher:
            try:
                aleph_result = self.aleph_searcher.search_company(query, jurisdiction)
                if aleph_result.get("success") and aleph_result.get("data"):
                    results["sources_searched"].append("occrp_aleph")
                    for item in aleph_result["data"][:limit//2]:
                        results["results"].append({
                            "name": item.get("name"),
                            "jurisdiction": item.get("jurisdiction"),
                            "registration_number": item.get("registration_number"),
                            "source": "occrp_aleph",
                            "url": item.get("url")
                        })
            except Exception as e:
                logger.warning(f"Aleph search error: {e}")

        # Search UK Companies House if jurisdiction is GB/UK
        if self.ch_api and (not jurisdiction or jurisdiction.upper() in ["GB", "UK"]):
            try:
                ch_results = self.ch_api.search_company(query, limit)
                if ch_results:
                    results["sources_searched"].append("companies_house")
                    for item in ch_results[:limit//2]:
                        results["results"].append({
                            "name": item.get("title"),
                            "jurisdiction": "GB",
                            "registration_number": item.get("company_number"),
                            "status": item.get("company_status"),
                            "type": item.get("company_type"),
                            "incorporation_date": item.get("date_of_creation"),
                            "source": "companies_house",
                            "address": item.get("address_snippet")
                        })
            except Exception as e:
                logger.warning(f"Companies House search error: {e}")

        results["total_results"] = len(results["results"])
        return results

    async def _enrich_company(self, company_name: str, jurisdiction: str = None) -> dict:
        """Full company enrichment with AI consolidation."""
        if not self.corporate_searcher:
            return {"error": "UltimateCorporateSearch module not available"}

        try:
            # Run the full search and consolidation (this is synchronous but comprehensive)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self.corporate_searcher.search_and_consolidate,
                company_name
            )
            return result
        except Exception as e:
            logger.error(f"Enrich company error: {e}")
            return {"error": str(e)}

    async def _search_registry(self, query: str, jurisdiction: str = "GB",
                               include_officers: bool = True, include_psc: bool = True) -> dict:
        """Search UK Companies House registry."""
        if jurisdiction.upper() not in ["GB", "UK"]:
            return {"error": f"Registry search only supports GB/UK, got: {jurisdiction}"}

        if not search_uk_company:
            return {"error": "CompaniesHouseAPI module not available"}

        try:
            result = search_uk_company(query, include_psc=include_psc, include_officers=include_officers)
            return result
        except Exception as e:
            logger.error(f"Registry search error: {e}")
            return {"error": str(e)}

    async def _get_officers(self, company_name: str, company_number: str = None,
                           jurisdiction: str = None) -> dict:
        """Get company officers."""
        if not self.ch_api:
            return {"error": "CompaniesHouseAPI module not available"}

        try:
            # If no company number, search first
            if not company_number:
                companies = self.ch_api.search_company(company_name, 5)
                if not companies:
                    return {"error": f"No company found for: {company_name}"}
                company_number = companies[0].get("company_number")

            officers = self.ch_api.get_company_officers(company_number)
            return {
                "company_number": company_number,
                "officers": officers,
                "total": len(officers)
            }
        except Exception as e:
            logger.error(f"Get officers error: {e}")
            return {"error": str(e)}

    async def _get_shareholders(self, company_name: str, company_number: str = None,
                                jurisdiction: str = None) -> dict:
        """Get company shareholders (PSC data)."""
        return await self._get_beneficial_owners(company_name, company_number, jurisdiction)

    async def _get_beneficial_owners(self, company_name: str, company_number: str = None,
                                     jurisdiction: str = None) -> dict:
        """Get beneficial owners (PSC - Persons with Significant Control)."""
        if not self.ch_api:
            return {"error": "CompaniesHouseAPI module not available"}

        try:
            # If no company number, search first
            if not company_number:
                companies = self.ch_api.search_company(company_name, 5)
                if not companies:
                    return {"error": f"No company found for: {company_name}"}
                company_number = companies[0].get("company_number")

            psc_data = self.ch_api.get_psc_data(company_number)
            return {
                "company_number": company_number,
                "beneficial_owners": psc_data,
                "total": len(psc_data)
            }
        except Exception as e:
            logger.error(f"Get beneficial owners error: {e}")
            return {"error": str(e)}

    async def _get_filings(self, company_name: str, company_number: str = None,
                          jurisdiction: str = None, limit: int = 20) -> dict:
        """Get company filing history."""
        if not self.ch_api:
            return {"error": "CompaniesHouseAPI module not available"}

        try:
            # If no company number, search first
            if not company_number:
                companies = self.ch_api.search_company(company_name, 5)
                if not companies:
                    return {"error": f"No company found for: {company_name}"}
                company_number = companies[0].get("company_number")

            filings = self.ch_api.get_filing_history(company_number, items_per_page=limit)
            return {
                "company_number": company_number,
                "filings": filings.get("items", []) if filings else [],
                "total": filings.get("total_count", 0) if filings else 0
            }
        except Exception as e:
            logger.error(f"Get filings error: {e}")
            return {"error": str(e)}

    async def _find_common_links(self, company_a: str, company_b: str,
                                 jurisdiction: str = None) -> dict:
        """Find common directors/shareholders between two companies."""
        if not self.ch_api:
            return {"error": "CompaniesHouseAPI module not available"}

        try:
            # Get officers for both companies
            officers_a_result = await self._get_officers(company_a, jurisdiction=jurisdiction)
            officers_b_result = await self._get_officers(company_b, jurisdiction=jurisdiction)

            if "error" in officers_a_result or "error" in officers_b_result:
                return {
                    "error": "Could not retrieve officers for one or both companies",
                    "company_a_error": officers_a_result.get("error"),
                    "company_b_error": officers_b_result.get("error")
                }

            # Extract officer names
            officers_a = {o.get("name", "").lower() for o in officers_a_result.get("officers", []) if o.get("name")}
            officers_b = {o.get("name", "").lower() for o in officers_b_result.get("officers", []) if o.get("name")}

            # Get PSC for both
            psc_a_result = await self._get_beneficial_owners(company_a, jurisdiction=jurisdiction)
            psc_b_result = await self._get_beneficial_owners(company_b, jurisdiction=jurisdiction)

            psc_a = {p.get("name", "").lower() for p in psc_a_result.get("beneficial_owners", []) if p.get("name")}
            psc_b = {p.get("name", "").lower() for p in psc_b_result.get("beneficial_owners", []) if p.get("name")}

            return {
                "company_a": company_a,
                "company_b": company_b,
                "common_officers": list(officers_a & officers_b),
                "common_shareholders": list(psc_a & psc_b),
                "company_a_officers": len(officers_a),
                "company_b_officers": len(officers_b),
                "company_a_psc": len(psc_a),
                "company_b_psc": len(psc_b)
            }
        except Exception as e:
            logger.error(f"Find common links error: {e}")
            return {"error": str(e)}

    async def _search_aleph(self, query: str, schema: str = "Company", max_results: int = 50) -> dict:
        """Search OCCRP Aleph database."""
        if not self.aleph_searcher:
            return {"error": "AlephSearcher module not available"}

        try:
            result = self.aleph_searcher.search_sync(query, max_results, schema)
            return result
        except Exception as e:
            logger.error(f"Aleph search error: {e}")
            return {"error": str(e)}

    async def _search_sanctions(self, query: str) -> dict:
        """Search OpenSanctions database."""
        if not opensanctions_search:
            return {"error": "OpenSanctions module not available"}

        try:
            result = opensanctions_search(query)
            return {
                "query": query,
                "source": "opensanctions",
                "results": result.get("results", []),
                "total": result.get("total", len(result.get("results", [])))
            }
        except Exception as e:
            logger.error(f"Sanctions search error: {e}")
            return {"error": str(e)}

    async def _search_person(self, query: str, jurisdiction: str = None) -> dict:
        """Search for a person across Aleph and Sanctions."""
        results = {
            "query": query,
            "jurisdiction": jurisdiction,
            "results": [],
            "total_results": 0
        }

        # Run searches in parallel
        tasks = []
        
        # Aleph search (schema=Person)
        tasks.append(self._search_aleph(query, schema="Person"))
        
        # Sanctions search
        tasks.append(self._search_sanctions(query))
        
        # Execute
        search_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process Aleph results
        aleph_res = search_results[0]
        if isinstance(aleph_res, dict) and not aleph_res.get("error"):
            data = aleph_res.get("data", [])
            for item in data:
                # Filter by jurisdiction if provided
                if jurisdiction:
                    # Aleph items might have 'countries' list
                    countries = item.get("countries", [])
                    if jurisdiction.lower() not in [c.lower() for c in countries]:
                        continue
                        
                results["results"].append({
                    "name": item.get("name"),
                    "type": "person",
                    "source": "occrp_aleph",
                    "dataset": item.get("collection", {}).get("label"),
                    "countries": item.get("countries", []),
                    "properties": item.get("properties", {}),
                    "url": item.get("links", {}).get("ui")
                })

        # Process Sanctions results
        sanc_res = search_results[1]
        if isinstance(sanc_res, dict) and not sanc_res.get("error"):
            data = sanc_res.get("results", [])
            for item in data:
                if jurisdiction:
                    countries = item.get("country", [])
                    if isinstance(countries, str): countries = [countries]
                    if jurisdiction.lower() not in [c.lower() for c in countries]:
                        continue

                results["results"].append({
                    "name": item.get("caption") or item.get("name"),
                    "type": "sanctioned_entity",
                    "source": "opensanctions",
                    "dataset": item.get("dataset"),
                    "countries": item.get("country", []),
                    "properties": item.get("properties", {}),
                    "id": item.get("id")
                })

        results["total_results"] = len(results["results"])
        return results

    async def _smart_route(self, company_name: str = None, person_name: str = None,
                          country: str = None, target: str = "generic") -> dict:
        """Get intelligent routing recommendations."""
        if not self.smart_router:
            return {"error": "SmartRouter module not available"}

        try:
            # Map target string to enum
            target_map = {
                "company_profile": TargetType.COMPANY_PROFILE,
                "ownership": TargetType.BENEFICIAL_OWNERSHIP,
                "person_dd": TargetType.PERSON_DUE_DILIGENCE,
                "regulatory": TargetType.REGULATORY_CHECK,
                "sanctions": TargetType.SANCTIONS_CHECK,
                "political_exposure": TargetType.POLITICAL_EXPOSURE,
                "generic": TargetType.GENERIC_SEARCH
            }

            user_input = UserInput(
                company_name=company_name,
                person_name=person_name,
                country=country,
                target=target_map.get(target, TargetType.GENERIC_SEARCH)
            )

            tasks = self.smart_router.route(user_input)

            return {
                "routing_plan": [
                    {
                        "priority": t.priority,
                        "country": t.country,
                        "collection": t.collection_name,
                        "collection_id": t.collection_id,
                        "input_type": t.input_type.value,
                        "query_value": t.query_value,
                        "expected_schema": t.expected_schema.value
                    }
                    for t in tasks
                ],
                "total_tasks": len(tasks)
            }
        except Exception as e:
            logger.error(f"Smart route error: {e}")
            return {"error": str(e)}

    async def run(self):
        """Run the MCP server."""
        logger.info(f"Starting Corporella MCP Server v2.0")
        logger.info(f"Modules available: {MODULES_AVAILABLE}")

        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )


def main():
    """Entry point."""
    server = CorporellaMCP()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
