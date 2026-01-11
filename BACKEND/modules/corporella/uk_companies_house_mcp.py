#!/usr/bin/env python3
"""
UK Companies House MCP Server
Exposes Companies House search, PSC, and officers lookup via MCP protocol
"""

import os
import sys
import json
import asyncio
import logging
import base64
import requests
from typing import Dict, List, Any, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables from project root
from dotenv import load_dotenv
from pathlib import Path
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
logger = logging.getLogger("uk-companies-house-mcp")

# API Configuration - load from .env
COMPANIES_HOUSE_API_KEY = os.getenv('COMPANIES_HOUSE_API_KEY') or os.getenv('CH_API_KEY')
BASE_URL = "https://api.company-information.service.gov.uk"

# Initialize MCP server
app = Server("uk-companies-house")


class CompaniesHouseClient:
    """Client for UK Companies House API"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = BASE_URL
        auth_string = base64.b64encode(f"{api_key}:".encode('utf-8')).decode('utf-8')
        self.headers = {'Authorization': f'Basic {auth_string}'}

    def search_companies(self, query: str, items_per_page: int = 20) -> Dict[str, Any]:
        """Search for companies by name"""
        url = f"{self.base_url}/search/companies"
        params = {
            'q': query,
            'items_per_page': items_per_page
        }

        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()

    def get_company_profile(self, company_number: str) -> Dict[str, Any]:
        """Get detailed company profile"""
        url = f"{self.base_url}/company/{company_number}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def get_company_officers(self, company_number: str, items_per_page: int = 50) -> Dict[str, Any]:
        """Get company officers (directors)"""
        url = f"{self.base_url}/company/{company_number}/officers"
        params = {'items_per_page': items_per_page}
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()

    def get_company_psc(self, company_number: str) -> Dict[str, Any]:
        """Get Persons with Significant Control (beneficial owners)"""
        url = f"{self.base_url}/company/{company_number}/persons-with-significant-control"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def get_company_filing_history(self, company_number: str, items_per_page: int = 25) -> Dict[str, Any]:
        """Get company filing history"""
        url = f"{self.base_url}/company/{company_number}/filing-history"
        params = {'items_per_page': items_per_page}
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()


# Initialize client
ch_client = CompaniesHouseClient(COMPANIES_HOUSE_API_KEY)


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available Companies House tools"""
    return [
        Tool(
            name="search_uk_companies",
            description="Search for UK companies by name in Companies House register. Returns basic company information including company number, status, incorporation date, and registered office address.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Company name to search for"
                    },
                    "items_per_page": {
                        "type": "number",
                        "description": "Number of results to return (default: 20, max: 100)",
                        "default": 20
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_uk_company_profile",
            description="Get detailed profile of a UK company using its company number. Returns full company details including SIC codes, previous names, confirmation statement, and registered office address.",
            inputSchema={
                "type": "object",
                "properties": {
                    "company_number": {
                        "type": "string",
                        "description": "UK Companies House company number (e.g., '00000006')"
                    }
                },
                "required": ["company_number"]
            }
        ),
        Tool(
            name="get_uk_company_officers",
            description="Get current and resigned officers (directors, secretaries) of a UK company. Returns names, roles, appointment dates, nationalities, and occupations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "company_number": {
                        "type": "string",
                        "description": "UK Companies House company number"
                    },
                    "items_per_page": {
                        "type": "number",
                        "description": "Number of officers to return (default: 50)",
                        "default": 50
                    }
                },
                "required": ["company_number"]
            }
        ),
        Tool(
            name="get_uk_company_psc",
            description="Get Persons with Significant Control (PSC) - beneficial owners of a UK company. Returns ultimate beneficial owners with their control percentages, nationalities, and natures of control. This is the most authoritative source for UK beneficial ownership data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "company_number": {
                        "type": "string",
                        "description": "UK Companies House company number"
                    }
                },
                "required": ["company_number"]
            }
        ),
        Tool(
            name="get_uk_company_filings",
            description="Get filing history for a UK company including annual returns, confirmation statements, accounts, and other statutory filings.",
            inputSchema={
                "type": "object",
                "properties": {
                    "company_number": {
                        "type": "string",
                        "description": "UK Companies House company number"
                    },
                    "items_per_page": {
                        "type": "number",
                        "description": "Number of filings to return (default: 25)",
                        "default": 25
                    }
                },
                "required": ["company_number"]
            }
        ),
        Tool(
            name="get_uk_company_full_profile",
            description="Get comprehensive company intelligence including profile, officers, PSC (beneficial owners), and recent filings. This is the most complete view of a UK company available. Use this when you need full corporate intelligence on a UK entity.",
            inputSchema={
                "type": "object",
                "properties": {
                    "company_number": {
                        "type": "string",
                        "description": "UK Companies House company number"
                    }
                },
                "required": ["company_number"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls"""

    try:
        if name == "search_uk_companies":
            query = arguments.get("query")
            items_per_page = arguments.get("items_per_page", 20)

            if not query:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": "Query parameter is required"})
                )]

            result = ch_client.search_companies(query, items_per_page)

            # Format results for readability
            formatted_results = {
                "total_results": result.get("total_results", 0),
                "items_per_page": result.get("items_per_page", 0),
                "companies": []
            }

            for item in result.get("items", []):
                formatted_results["companies"].append({
                    "company_name": item.get("title"),
                    "company_number": item.get("company_number"),
                    "company_status": item.get("company_status"),
                    "company_type": item.get("company_type"),
                    "date_of_creation": item.get("date_of_creation"),
                    "address": item.get("address", {})
                })

            return [TextContent(
                type="text",
                text=json.dumps(formatted_results, indent=2)
            )]

        elif name == "get_uk_company_profile":
            company_number = arguments.get("company_number")

            if not company_number:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": "company_number parameter is required"})
                )]

            result = ch_client.get_company_profile(company_number)

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "get_uk_company_officers":
            company_number = arguments.get("company_number")
            items_per_page = arguments.get("items_per_page", 50)

            if not company_number:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": "company_number parameter is required"})
                )]

            result = ch_client.get_company_officers(company_number, items_per_page)

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "get_uk_company_psc":
            company_number = arguments.get("company_number")

            if not company_number:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": "company_number parameter is required"})
                )]

            result = ch_client.get_company_psc(company_number)

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "get_uk_company_filings":
            company_number = arguments.get("company_number")
            items_per_page = arguments.get("items_per_page", 25)

            if not company_number:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": "company_number parameter is required"})
                )]

            result = ch_client.get_company_filing_history(company_number, items_per_page)

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "get_uk_company_full_profile":
            company_number = arguments.get("company_number")

            if not company_number:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": "company_number parameter is required"})
                )]

            # Gather all data
            full_profile = {
                "company_number": company_number,
                "profile": {},
                "officers": {},
                "psc": {},
                "recent_filings": {}
            }

            try:
                full_profile["profile"] = ch_client.get_company_profile(company_number)
            except Exception as e:
                full_profile["profile"] = {"error": str(e)}

            try:
                full_profile["officers"] = ch_client.get_company_officers(company_number, 50)
            except Exception as e:
                full_profile["officers"] = {"error": str(e)}

            try:
                full_profile["psc"] = ch_client.get_company_psc(company_number)
            except Exception as e:
                full_profile["psc"] = {"error": str(e)}

            try:
                full_profile["recent_filings"] = ch_client.get_company_filing_history(company_number, 10)
            except Exception as e:
                full_profile["recent_filings"] = {"error": str(e)}

            return [TextContent(
                type="text",
                text=json.dumps(full_profile, indent=2)
            )]

        else:
            return [TextContent(
                type="text",
                text=json.dumps({"error": f"Unknown tool: {name}"})
            )]

    except Exception as e:
        logger.error(f"Tool call error: {e}", exc_info=True)
        return [TextContent(
            type="text",
            text=json.dumps({"error": str(e)})
        )]


async def main():
    """Run the MCP server"""
    logger.info("Starting UK Companies House MCP Server")

    if not COMPANIES_HOUSE_API_KEY:
        logger.error("CH_API_KEY environment variable not set!")
        sys.exit(1)

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
