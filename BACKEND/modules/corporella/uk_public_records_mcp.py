#!/usr/bin/env python3
"""
UK Public Records MCP Server
Exposes UK Land Registry, Companies House, FCA NSM, and Aleph UK collections via MCP protocol
Based on uk_cli.py consolidated UK data toolkit + FCA NSM + Aleph integration
"""

import os
import sys
import json
import asyncio
import logging
import csv
import requests
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables from project root
from dotenv import load_dotenv
project_root = Path(__file__).resolve().parents[3]  # Go up to drill-search-app
env_path = project_root / '.env'
load_dotenv(env_path)

# MCP Server imports
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    LoggingLevel
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uk-public-records-mcp")

# Load API keys from .env
COMPANIES_HOUSE_API_KEY = os.getenv('COMPANIES_HOUSE_API_KEY')
FCA_API_KEY = os.getenv('FCA_API_KEY')
FCA_AUTH_EMAIL = os.getenv('FCA_AUTH_EMAIL')

# Default CSV path for Land Registry
DEFAULT_LAND_REGISTRY_CSV = os.getenv(
    'UK_LAND_REGISTRY_CSV',
    "/Users/attic/Library/Mobile Documents/com~apple~CloudDocs/01_ACTIVE_PROJECTS/Development/Search-Engineer.02/iv. LOCATION/a. KNOWN_UNKNOWN/SOURCE_CATEGORY/PUBLIC-RECORDS/LOCAL/LAND_REGISTRY/LAND_UK/CCOD_FULL_2025_08.csv"
)

# FCA NSM API Configuration
FCA_NSM_BASE_URL = "https://www.fca.org.uk/api/national-storage-mechanism/search"
FCA_NSM_HEADERS = {"User-Agent": "DRILL_SEARCH/1.0"}

# Aleph API Configuration
ALEPH_BASE_URL = "https://aleph.occrp.org/api/2"
ALEPH_UK_COLLECTIONS = [
    "uk_coh_disqualified",  # UK Companies House Disqualified Directors
    "uk_land_registry",     # UK Land Registry (CCOD/OCOD)
    "uk_parliament",        # UK Parliamentary Register of Interests
    "uk_courts",            # UK Court Records
    "pandora_papers_uk",    # Pandora Papers UK entities
    "paradise_papers_uk"    # Paradise Papers UK entities
]

# Initialize MCP server
app = Server("uk-public-records")


def _norm(s: str) -> str:
    """Normalize string for matching"""
    return (s or "").strip().lower()


def guess_columns(header: List[str]) -> Dict[str, Optional[str]]:
    """Auto-detect Land Registry CSV column mappings"""
    hnorm = [h.replace(" ", "").replace("_", "").lower() for h in header]

    def find(candidates: List[str]) -> Optional[str]:
        for cand in candidates:
            c = cand.replace(" ", "").replace("_", "").lower()
            for i, hn in enumerate(hnorm):
                if c == hn:
                    return header[i]
        for cand in candidates:
            c = cand.replace(" ", "").replace("_", "").lower()
            for i, hn in enumerate(hnorm):
                if c in hn:
                    return header[i]
        return None

    return {
        "title": find(["Title Number", "TITLE_NUMBER", "TitleNumber", "title"]),
        "tenure": find(["Tenure", "tenure"]),
        "address": find(["Property Address", "PROPERTY ADDRESS", "PropertyAddress", "address"]),
        "district": find(["District", "localdistrict"]),
        "county": find(["County", "localcounty"]),
        "region": find(["Region", "regionname"]),
        "postcode": find(["Postcode", "Post Code", "POSTCODE", "zip", "postalcode"]),
        "owner": find([
            "Proprietor Name",
            "Proprietor 1 Name",
            "Proprietor Name (1)",
            "Current Proprietor Name",
            "Owner",
            "Name",
        ]),
        "owner_address": find([
            "Proprietor Address",
            "Proprietor 1 Address",
            "Proprietor Address (1)",
            "Owner Address",
        ]),
        "local_authority": find(["Local Authority", "LocalAuthority"]),
        "date": find(["Last Update Date", "Date", "Entry Date", "\ufeffDate", "Registered Date"]),
    }


def row_matches(
    row: Dict[str, str],
    mapping: Dict[str, Optional[str]],
    query: Optional[str],
    postcode: Optional[str],
    owner: Optional[str],
    address: Optional[str],
) -> bool:
    """Check if a row matches the search criteria"""
    if postcode:
        col = mapping.get("postcode")
        if not col or _norm(postcode) not in _norm(row.get(col, "")):
            return False
    if owner:
        col = mapping.get("owner")
        if not col or _norm(owner) not in _norm(row.get(col, "")):
            return False
    if address:
        col = mapping.get("address")
        if not col or _norm(address) not in _norm(row.get(col, "")):
            return False
    if query:
        qn = _norm(query)
        hay = " ".join([_norm(v) for v in row.values()])
        if qn not in hay:
            return False
    return True


def search_land_registry(
    csv_path: str,
    query: Optional[str] = None,
    postcode: Optional[str] = None,
    owner: Optional[str] = None,
    address: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, str]]:
    """Search UK Land Registry CSV data"""
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    results = []

    with open(csv_path, 'r', encoding='utf-8', newline='') as f:
        reader = csv.reader(f)
        header = next(reader, [])
        if not header:
            return results

    mapping = guess_columns(header)

    with open(csv_path, 'r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for row_dict in reader:
            row = dict(row_dict)
            if row_matches(row, mapping, query, postcode, owner, address):
                # Extract key fields
                result = {
                    "title_number": row.get(mapping.get("title", ""), ""),
                    "tenure": row.get(mapping.get("tenure", ""), ""),
                    "address": row.get(mapping.get("address", ""), ""),
                    "postcode": row.get(mapping.get("postcode", ""), ""),
                    "owner": row.get(mapping.get("owner", ""), ""),
                    "owner_address": row.get(mapping.get("owner_address", ""), ""),
                    "district": row.get(mapping.get("district", ""), ""),
                    "county": row.get(mapping.get("county", ""), ""),
                    "region": row.get(mapping.get("region", ""), ""),
                    "local_authority": row.get(mapping.get("local_authority", ""), ""),
                    "date": row.get(mapping.get("date", ""), ""),
                }
                results.append(result)

                if len(results) >= limit:
                    break

    return results


def search_fca_nsm(keyword: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Search FCA National Storage Mechanism for company documents
    Returns prospectuses, annual reports, and regulatory filings
    """
    try:
        params = {
            "q": keyword,
            "start": 0,
            "length": min(limit, 100)
        }

        response = requests.get(
            FCA_NSM_BASE_URL,
            params=params,
            headers=FCA_NSM_HEADERS,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        results = data.get("results", [])
        return results[:limit]

    except Exception as e:
        logger.error(f"FCA NSM search error: {e}")
        raise


def search_aleph(query: str, limit: int = 50, collections: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Search Aleph (OCCRP) for UK-related entities
    Includes leaked documents, court records, and watchlist data
    """
    try:
        # Aleph API v2 requires schema parameter - search across all entity types
        search_params = {
            "q": query,
            "limit": limit,
            "schema": "Thing"  # Base schema that matches all entities
        }

        # Add collection filter if specified (using GET params, not JSON body)
        if collections:
            for collection in collections:
                search_params[f"filter:collection_id"] = collection

        response = requests.get(
            f"{ALEPH_BASE_URL}/search",
            params=search_params,
            headers={"Accept": "application/json"},
            timeout=30
        )
        response.raise_for_status()
        return response.json()

    except Exception as e:
        logger.error(f"Aleph search error: {e}")
        raise


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available UK public records tools"""
    return [
        Tool(
            name="search_uk_land_registry",
            description="Search UK Land Registry CCOD (Corporate and Commercial Ownership Dataset). Search by postcode, owner name, property address, or general query. Returns title numbers, ownership details, addresses, and registration dates. This is the authoritative source for UK property ownership by companies.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Full-text search across all fields (optional)"
                    },
                    "postcode": {
                        "type": "string",
                        "description": "Filter by postcode (substring match, optional)"
                    },
                    "owner": {
                        "type": "string",
                        "description": "Filter by owner/proprietor name (substring match, optional)"
                    },
                    "address": {
                        "type": "string",
                        "description": "Filter by property address (substring match, optional)"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of results to return (default: 50, max: 500)",
                        "default": 50
                    },
                    "csv_path": {
                        "type": "string",
                        "description": "Optional: Custom path to Land Registry CSV file (uses default if not provided)"
                    }
                }
            }
        ),
        Tool(
            name="search_uk_land_registry_by_company",
            description="Specialized search for finding all UK properties owned by a specific company. Optimized for corporate ownership lookup. Returns comprehensive property portfolio for the company.",
            inputSchema={
                "type": "object",
                "properties": {
                    "company_name": {
                        "type": "string",
                        "description": "Company name to search for (e.g., 'British Land', 'Tesco')"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of properties to return (default: 100)",
                        "default": 100
                    }
                },
                "required": ["company_name"]
            }
        ),
        Tool(
            name="search_uk_land_registry_by_postcode",
            description="Search for all properties in a specific UK postcode area. Useful for area analysis and neighborhood ownership patterns.",
            inputSchema={
                "type": "object",
                "properties": {
                    "postcode": {
                        "type": "string",
                        "description": "UK postcode or postcode area (e.g., 'SW1A 1AA', 'SW1A', 'EC2')"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of results (default: 100)",
                        "default": 100
                    }
                },
                "required": ["postcode"]
            }
        ),
        Tool(
            name="uk_data_sources_status",
            description="Check availability and status of UK official data sources including Land Registry (CCOD/OCOD/Leases), Companies House, FOI archives, FCA registers, and Court data. Returns which data sources are configured and ready to use.",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Filter by category (Property, Corporate, Transparency, Regulator, Courts)",
                        "enum": ["Property", "Corporate", "Transparency", "Regulator", "Courts"]
                    }
                }
            }
        ),
        Tool(
            name="search_fca_documents",
            description="Search FCA National Storage Mechanism for company prospectuses, annual reports, and regulatory filings. This is the official UK repository for all public company disclosures, IPO prospectuses, and financial statements. Essential for UK corporate due diligence.",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "Company name, ticker symbol, or search term"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of documents to return (default: 50, max: 100)",
                        "default": 50
                    }
                },
                "required": ["keyword"]
            }
        ),
        Tool(
            name="search_aleph_uk",
            description="Search Aleph (OCCRP) for UK-related entities across leaked documents, court records, disqualified directors, land registry, parliamentary interests, and watchlists. Includes Pandora Papers, Paradise Papers, and official UK datasets. Essential for investigative research.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Entity name (person or company) to search for"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of results (default: 50)",
                        "default": 50
                    },
                    "collections": {
                        "type": "array",
                        "description": "Optional: Specific collections to search (defaults to all UK collections)",
                        "items": {
                            "type": "string",
                            "enum": [
                                "uk_coh_disqualified",
                                "uk_land_registry",
                                "uk_parliament",
                                "uk_courts",
                                "pandora_papers_uk",
                                "paradise_papers_uk"
                            ]
                        }
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="search_uk_comprehensive",
            description="Comprehensive UK entity search across ALL available sources: Land Registry, Companies House, FCA NSM, and Aleph collections. Returns unified results from all databases. Best for complete due diligence when you need maximum coverage.",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "Company or person name to search across all UK databases"
                    },
                    "limit_per_source": {
                        "type": "number",
                        "description": "Maximum results per data source (default: 20)",
                        "default": 20
                    }
                },
                "required": ["entity_name"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls"""

    try:
        if name == "search_uk_land_registry":
            csv_path = arguments.get("csv_path", DEFAULT_LAND_REGISTRY_CSV)
            query = arguments.get("query")
            postcode = arguments.get("postcode")
            owner = arguments.get("owner")
            address = arguments.get("address")
            limit = min(arguments.get("limit", 50), 500)

            results = search_land_registry(
                csv_path=csv_path,
                query=query,
                postcode=postcode,
                owner=owner,
                address=address,
                limit=limit
            )

            response = {
                "total_found": len(results),
                "limit": limit,
                "search_params": {
                    "query": query,
                    "postcode": postcode,
                    "owner": owner,
                    "address": address
                },
                "properties": results
            }

            return [TextContent(
                type="text",
                text=json.dumps(response, indent=2)
            )]

        elif name == "search_uk_land_registry_by_company":
            company_name = arguments.get("company_name")
            limit = min(arguments.get("limit", 100), 500)

            if not company_name:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": "company_name parameter is required"})
                )]

            results = search_land_registry(
                csv_path=DEFAULT_LAND_REGISTRY_CSV,
                owner=company_name,
                limit=limit
            )

            response = {
                "company_name": company_name,
                "total_properties": len(results),
                "properties": results
            }

            return [TextContent(
                type="text",
                text=json.dumps(response, indent=2)
            )]

        elif name == "search_uk_land_registry_by_postcode":
            postcode = arguments.get("postcode")
            limit = min(arguments.get("limit", 100), 500)

            if not postcode:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": "postcode parameter is required"})
                )]

            results = search_land_registry(
                csv_path=DEFAULT_LAND_REGISTRY_CSV,
                postcode=postcode,
                limit=limit
            )

            response = {
                "postcode": postcode,
                "total_properties": len(results),
                "properties": results
            }

            return [TextContent(
                type="text",
                text=json.dumps(response, indent=2)
            )]

        elif name == "search_fca_documents":
            keyword = arguments.get("keyword")
            limit = min(arguments.get("limit", 50), 100)

            if not keyword:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": "keyword parameter is required"})
                )]

            try:
                documents = search_fca_nsm(keyword, limit)

                response = {
                    "keyword": keyword,
                    "total_documents": len(documents),
                    "documents": documents,
                    "source": "FCA National Storage Mechanism"
                }

                return [TextContent(
                    type="text",
                    text=json.dumps(response, indent=2)
                )]

            except Exception as e:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": str(e), "source": "FCA NSM"})
                )]

        elif name == "search_aleph_uk":
            query = arguments.get("query")
            limit = min(arguments.get("limit", 50), 100)
            collections = arguments.get("collections")

            if not query:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": "query parameter is required"})
                )]

            try:
                results = search_aleph(query, limit, collections)

                response = {
                    "query": query,
                    "total_results": results.get("total", 0),
                    "results": results.get("results", []),
                    "collections_searched": collections or ALEPH_UK_COLLECTIONS,
                    "source": "Aleph (OCCRP)"
                }

                return [TextContent(
                    type="text",
                    text=json.dumps(response, indent=2)
                )]

            except Exception as e:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": str(e), "source": "Aleph"})
                )]

        elif name == "search_uk_comprehensive":
            entity_name = arguments.get("entity_name")
            limit = arguments.get("limit_per_source", 20)

            if not entity_name:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": "entity_name parameter is required"})
                )]

            comprehensive_results = {
                "entity_name": entity_name,
                "search_timestamp": datetime.now().isoformat(),
                "sources": {}
            }

            # 1. Land Registry Search
            try:
                if os.path.isfile(DEFAULT_LAND_REGISTRY_CSV):
                    land_results = search_land_registry(
                        csv_path=DEFAULT_LAND_REGISTRY_CSV,
                        owner=entity_name,
                        limit=limit
                    )
                    comprehensive_results["sources"]["land_registry"] = {
                        "status": "success",
                        "count": len(land_results),
                        "results": land_results
                    }
                else:
                    comprehensive_results["sources"]["land_registry"] = {
                        "status": "unavailable",
                        "reason": "CSV file not found"
                    }
            except Exception as e:
                comprehensive_results["sources"]["land_registry"] = {
                    "status": "error",
                    "error": str(e)
                }

            # 2. FCA NSM Search
            try:
                fca_results = search_fca_nsm(entity_name, limit)
                comprehensive_results["sources"]["fca_nsm"] = {
                    "status": "success",
                    "count": len(fca_results),
                    "results": fca_results
                }
            except Exception as e:
                comprehensive_results["sources"]["fca_nsm"] = {
                    "status": "error",
                    "error": str(e)
                }

            # 3. Aleph Search
            try:
                aleph_results = search_aleph(entity_name, limit)
                comprehensive_results["sources"]["aleph"] = {
                    "status": "success",
                    "count": aleph_results.get("total", 0),
                    "results": aleph_results.get("results", [])
                }
            except Exception as e:
                comprehensive_results["sources"]["aleph"] = {
                    "status": "error",
                    "error": str(e)
                }

            # Calculate total matches
            total_matches = sum(
                source.get("count", 0)
                for source in comprehensive_results["sources"].values()
                if source.get("status") == "success"
            )
            comprehensive_results["total_matches_across_all_sources"] = total_matches

            return [TextContent(
                type="text",
                text=json.dumps(comprehensive_results, indent=2)
            )]

        elif name == "uk_data_sources_status":
            category_filter = arguments.get("category")

            sources = [
                {
                    "id": "land_registry",
                    "name": "UK Land Registry (CCOD/OCOD/Leases)",
                    "category": "Property",
                    "official": True,
                    "status": "available" if os.path.isfile(DEFAULT_LAND_REGISTRY_CSV) else "missing",
                    "description": "Corporate and overseas ownership plus lease datasets. Local CSV available.",
                    "csv_path": DEFAULT_LAND_REGISTRY_CSV,
                    "csv_exists": os.path.isfile(DEFAULT_LAND_REGISTRY_CSV)
                },
                {
                    "id": "companies_house",
                    "name": "Companies House API",
                    "category": "Corporate",
                    "official": True,
                    "status": "available" if os.getenv('COMPANIES_HOUSE_API_KEY') or os.getenv('CH_API_KEY') else "missing_key",
                    "description": "Official company profiles, filings, directors, and PSC data",
                    "api_key_set": bool(os.getenv('COMPANIES_HOUSE_API_KEY') or os.getenv('CH_API_KEY'))
                },
                {
                    "id": "fca_nsm",
                    "name": "FCA National Storage Mechanism",
                    "category": "Corporate",
                    "official": True,
                    "status": "available",
                    "description": "Public company disclosures, prospectuses, and regulatory filings"
                },
                {
                    "id": "aleph",
                    "name": "Aleph (OCCRP) UK Collections",
                    "category": "Transparency",
                    "official": False,
                    "status": "available",
                    "description": "Leaked documents, court records, disqualified directors, watchlists",
                    "collections": ALEPH_UK_COLLECTIONS
                },
                {
                    "id": "foi",
                    "name": "WhatDoTheyKnow FOI Archive",
                    "category": "Transparency",
                    "official": True,
                    "status": "not_implemented",
                    "description": "Freedom of Information requests and responses"
                },
                {
                    "id": "uk_court_data",
                    "name": "UK Court & CCJ Data",
                    "category": "Courts",
                    "official": False,
                    "status": "not_implemented",
                    "description": "BAILII, Registry Trust, GeoDS court and CCJ data (requires paid access)"
                }
            ]

            # Filter by category if provided
            if category_filter:
                sources = [s for s in sources if s["category"] == category_filter]

            response = {
                "total_sources": len(sources),
                "sources": sources,
                "notes": {
                    "land_registry": "Set UK_LAND_REGISTRY_CSV env var to use custom CSV path",
                    "companies_house": "Set COMPANIES_HOUSE_API_KEY or CH_API_KEY env var to enable API access",
                    "status_codes": {
                        "available": "Ready to use",
                        "missing": "Data file not found",
                        "missing_key": "API key not configured",
                        "not_implemented": "Planned but not yet implemented in this MCP server"
                    }
                }
            }

            return [TextContent(
                type="text",
                text=json.dumps(response, indent=2)
            )]

        else:
            return [TextContent(
                type="text",
                text=json.dumps({"error": f"Unknown tool: {name}"})
            )]

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return [TextContent(
            type="text",
            text=json.dumps({"error": str(e), "hint": "Check UK_LAND_REGISTRY_CSV path or provide csv_path parameter"})
        )]
    except Exception as e:
        logger.error(f"Tool call error: {e}", exc_info=True)
        return [TextContent(
            type="text",
            text=json.dumps({"error": str(e)})
        )]


async def main():
    """Run the MCP server"""
    logger.info("Starting UK Public Records MCP Server")
    logger.info(f"Land Registry CSV: {DEFAULT_LAND_REGISTRY_CSV}")
    logger.info(f"CSV exists: {os.path.isfile(DEFAULT_LAND_REGISTRY_CSV)}")

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
