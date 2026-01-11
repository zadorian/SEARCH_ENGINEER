#!/usr/bin/env python3
"""
OCCRP Aleph Unified Client (corporella/occrp_aleph.py)
======================================================

Unified OCCRP Aleph searcher combining async and sync capabilities.
This is the canonical Aleph module for the entire codebase.

Features:
- Async methods for concurrent searches (search, search_entities, search_parallel)
- Sync wrapper for simple lookups (search_sync)
- Section-aware filtering (cr, lit, reg, ass, leak, news)
- Collection-based jurisdiction filtering
- Exact phrase search support
- Document and entity extraction

Usage:
    # Async usage
    from corporella.occrp_aleph import AlephSearcher

    searcher = AlephSearcher()
    results = await searcher.search("Company Name")

    # Sync usage
    results = searcher.search_sync("Company Name")

    # Section-filtered search
    results = await searcher.search_by_section("Company Name", "GB", "cr")

API Reference: https://aleph.occrp.org/api/2
"""

import os
import asyncio
import aiohttp
import requests
import json
import re
import logging
from typing import List, Dict, Optional, Any, Set
from pathlib import Path
from dataclasses import dataclass, field

# Load environment
try:
    from dotenv import load_dotenv
    PROJECT_ROOT = Path(__file__).resolve().parents[4]
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

logger = logging.getLogger(__name__)


# Section to category mapping (from aleph_collections.json)
SECTION_MAPPING = {
    "cr": {
        "name": "Corporate Registry",
        "categories": ["company", "gazette"],
        "description": "Company registrations, filings, beneficial ownership"
    },
    "lit": {
        "name": "Litigation",
        "categories": ["court"],
        "description": "Court cases, lawsuits, judgments, indictments"
    },
    "reg": {
        "name": "Regulatory",
        "categories": ["regulatory", "sanctions", "license", "procurement", "poi"],
        "description": "Regulatory filings, sanctions, licenses, enforcement actions"
    },
    "ass": {
        "name": "Assets",
        "categories": ["land", "finance", "transport"],
        "description": "Property, real estate, financial records, vehicles"
    },
    "leak": {
        "name": "Leaks & Grey Literature",
        "categories": ["leak", "grey", "library"],
        "description": "Leaked documents, FOIA, investigative archives"
    },
    "news": {
        "name": "News & Media",
        "categories": ["news"],
        "description": "News articles, press releases"
    }
}


@dataclass
class AlephResult:
    """Structured Aleph search result."""
    title: str
    url: str
    snippet: str = ""
    source: str = "aleph"
    schema: str = ""
    properties: Dict = field(default_factory=dict)
    source_url: Optional[str] = None
    pdf_url: Optional[str] = None
    file_url: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    processing_status: Optional[str] = None
    collection_id: Optional[int] = None
    collection_label: Optional[str] = None
    category: Optional[str] = None
    exact_phrase_search: bool = False


class AlephSearcher:
    """
    Unified OCCRP Aleph searcher for investigative data.

    Aleph stores documents, entities, and structured datasets acquired
    from public sources like leaks, investigations, and government records.
    """

    BASE_URL = "https://aleph.occrp.org/api/2"

    def __init__(self, api_key: str = None, collections_path: Path = None):
        """
        Initialize with optional API key override.

        Args:
            api_key: OCCRP Aleph API key (defaults to ALEPH_API_KEY env var)
            collections_path: Path to aleph_collections.json for jurisdiction filtering
        """
        # Try to get API key from environment
        if not api_key:
            api_key = os.getenv("ALEPH_API_KEY")

        self.api_key = api_key
        self.collections = None

        # Set up headers
        if self.api_key:
            self.headers = {
                "Authorization": f"ApiKey {self.api_key}",
                "Accept": "application/json"
            }
            logger.info("Aleph API initialized with API key")
        else:
            self.headers = {"Accept": "application/json"}
            logger.warning("No ALEPH_API_KEY provided. Some features may be limited.")

        # Load collections if path provided
        if collections_path and collections_path.exists():
            try:
                with open(collections_path, 'r') as f:
                    self.collections = json.load(f)
                logger.info(f"Loaded Aleph collections: {self.collections.get('meta', {}).get('total_collections', 0)} collections")
            except Exception as e:
                logger.error(f"Failed to load collections: {e}")

    def has_credentials(self) -> bool:
        """Check if API credentials are configured."""
        return bool(self.api_key)

    # =========================================================================
    # ASYNC SEARCH METHODS
    # =========================================================================

    async def search(
        self,
        query: str,
        max_results: int = 100,
        schemas: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Search the Aleph database for entities and documents.

        Args:
            query: Search query (quotes preserved for exact phrase)
            max_results: Maximum number of results to return (default 100)
            schemas: List of schemas to search (default: Document, LegalEntity, Company, Person)

        Returns:
            List of search results with title, URL, and snippet
        """
        results = []

        if not self.api_key:
            logger.warning("ALEPH_API_KEY not set. Add it to your .env file.")
            return []

        # Handle exact phrase search
        search_query, is_exact_phrase = self._prepare_query(query)

        logger.info(f"Searching Aleph: {search_query} (exact={is_exact_phrase})")

        # Default schemas
        if schemas is None:
            schemas = ["Document", "LegalEntity", "Company", "Person"]

        async with aiohttp.ClientSession() as session:
            for schema in schemas:
                if len(results) >= max_results:
                    break

                schema_results = await self._search_schema(
                    session, search_query, schema,
                    min(30, max_results - len(results)),
                    is_exact_phrase
                )
                results.extend(schema_results)

        logger.info(f"Found {len(results)} results from Aleph")
        return results[:max_results]

    async def search_parallel(
        self,
        query: str,
        max_results: int = 100,
        schemas: Optional[List[str]] = None,
        max_concurrent: int = 6
    ) -> List[Dict]:
        """
        PARALLEL search - searches multiple schemas concurrently for faster results.

        Args:
            query: Search query
            max_results: Maximum results across all schemas
            schemas: Schemas to search (default: Document, LegalEntity, Company, Person)
            max_concurrent: Maximum concurrent schema searches

        Returns:
            List of search results
        """
        results = []

        if not self.api_key:
            logger.warning("ALEPH_API_KEY not set.")
            return []

        search_query, is_exact_phrase = self._prepare_query(query)

        logger.info(f"Parallel Aleph search: {search_query}")

        if schemas is None:
            schemas = ["Document", "LegalEntity", "Company", "Person"]

        # Split schemas into batches
        schema_batches = [schemas[i:i+max_concurrent] for i in range(0, len(schemas), max_concurrent)]

        async with aiohttp.ClientSession() as session:
            for schema_batch in schema_batches:
                if len(results) >= max_results:
                    break

                # Create tasks for parallel execution
                tasks = []
                for schema in schema_batch:
                    if len(results) >= max_results:
                        break
                    task = self._search_schema(
                        session, search_query, schema,
                        min(50, max_results - len(results)),
                        is_exact_phrase
                    )
                    tasks.append(task)

                if tasks:
                    batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                    for schema_results in batch_results:
                        if isinstance(schema_results, Exception):
                            logger.error(f"Error in parallel search: {schema_results}")
                            continue
                        if schema_results:
                            results.extend(schema_results)

        return results[:max_results]

    async def search_entities(
        self,
        query: str,
        entity_types: Optional[List[str]] = None,
        max_results: int = 100
    ) -> List[Dict]:
        """
        Search specifically for entities in Aleph.

        Args:
            query: Search query
            entity_types: List of entity types (e.g., ["Person", "Company"])
            max_results: Maximum number of results

        Returns:
            List of entity results
        """
        search_query, is_exact_phrase = self._prepare_query(query)

        # Add schema filter
        if entity_types:
            schema_filter = " OR ".join([f"schema:{t}" for t in entity_types])
            search_query = f"({search_query}) AND ({schema_filter})"

        params = {
            "q": search_query,
            "limit": min(30, max_results),
            "offset": 0,
        }

        results = []

        async with aiohttp.ClientSession() as session:
            while len(results) < max_results:
                try:
                    async with session.get(
                        f"{self.BASE_URL}/entities",
                        headers=self.headers,
                        params=params
                    ) as response:
                        if response.status != 200:
                            break

                        data = await response.json()
                        items = data.get("results", [])

                        if not items:
                            break

                        for item in items:
                            result = self._parse_entity(item, is_exact_phrase)
                            results.append(result)

                            if len(results) >= max_results:
                                break

                        # Check pagination
                        if len(items) < params["limit"] or not data.get("next_offset"):
                            break

                        params["offset"] = data.get("next_offset")

                except Exception as e:
                    logger.error(f"Error searching Aleph entities: {e}")
                    break

        return results

    async def search_by_section(
        self,
        query: str,
        jurisdiction: str,
        section: str,
        max_results: int = 50
    ) -> List[Dict]:
        """
        Search filtered by jurisdiction and wiki section (cr, lit, reg, ass, leak, news).

        Args:
            query: Search query
            jurisdiction: 2-letter jurisdiction code (e.g., "GB", "US")
            section: Section code (cr, lit, reg, ass, leak, news)
            max_results: Maximum results

        Returns:
            Filtered search results
        """
        # Get allowed categories for this section
        section_info = SECTION_MAPPING.get(section.lower(), {})
        allowed_categories = section_info.get("categories", [])

        if not allowed_categories:
            logger.warning(f"Unknown section: {section}")
            return []

        # Get jurisdiction-specific collections
        collection_ids = []
        if self.collections:
            jurisdiction_data = self.collections.get("by_jurisdiction", {}).get(jurisdiction.upper(), {})
            for collection in jurisdiction_data.get("collections", []):
                if collection.get("category") in allowed_categories:
                    collection_ids.append(collection.get("id"))

        # Also add global collections for this category
        if self.collections:
            for collection in self.collections.get("global_collections", {}).get("collections", []):
                if collection.get("category") in allowed_categories:
                    if jurisdiction.upper() in collection.get("jurisdictions", []) or "GLOBAL" in collection.get("jurisdictions", []):
                        collection_ids.append(collection.get("id"))

        # Search with collection filter if available
        if collection_ids:
            logger.info(f"Searching {len(collection_ids)} collections for {jurisdiction}/{section}")
            return await self._search_with_collections(query, collection_ids, max_results)
        else:
            # Fallback to category-based filtering of results
            results = await self.search(query, max_results * 2)  # Get more to filter
            filtered = [r for r in results if self._matches_categories(r, allowed_categories)]
            return filtered[:max_results]

    async def _search_with_collections(
        self,
        query: str,
        collection_ids: List[int],
        max_results: int
    ) -> List[Dict]:
        """Search within specific collections."""
        search_query, is_exact_phrase = self._prepare_query(query)

        results = []

        async with aiohttp.ClientSession() as session:
            params = {
                "q": search_query,
                "limit": min(30, max_results),
                "offset": 0,
            }

            # Add collection filter
            for coll_id in collection_ids[:10]:  # Limit to 10 collections per query
                params[f"filter:collection_id"] = coll_id

            try:
                async with session.get(
                    f"{self.BASE_URL}/entities",
                    headers=self.headers,
                    params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        for item in data.get("results", []):
                            result = self._parse_entity(item, is_exact_phrase)
                            results.append(result)
                            if len(results) >= max_results:
                                break
            except Exception as e:
                logger.error(f"Error searching collections: {e}")

        return results

    async def _search_schema(
        self,
        session: aiohttp.ClientSession,
        search_query: str,
        schema: str,
        max_results: int,
        is_exact_phrase: bool
    ) -> List[Dict]:
        """Search a single schema with pagination."""
        results = []
        current_offset = 0

        while len(results) < max_results:
            params = {
                "q": search_query,
                "limit": min(30, max_results - len(results)),
                "offset": current_offset,
                "filter:schema": schema,
            }

            try:
                async with session.get(
                    f"{self.BASE_URL}/entities",
                    headers=self.headers,
                    params=params
                ) as response:
                    if response.status != 200:
                        break

                    data = await response.json()
                    items = data.get("results", [])

                    if not items:
                        break

                    for item in items:
                        result = self._parse_entity(item, is_exact_phrase)
                        result["schema"] = schema
                        results.append(result)

                        if len(results) >= max_results:
                            break

                    # Check pagination
                    if len(items) < params["limit"]:
                        break

                    if data.get("next_offset"):
                        current_offset = data["next_offset"]
                    else:
                        current_offset += params["limit"]

            except Exception as e:
                logger.error(f"Error searching schema {schema}: {e}")
                break

        return results

    # =========================================================================
    # SYNC SEARCH METHODS
    # =========================================================================

    def search_sync(
        self,
        query: str,
        max_results: int = 50,
        schema: str = "Company"
    ) -> Dict[str, Any]:
        """
        Synchronous search for simple lookups.

        Args:
            query: Search query
            max_results: Maximum results
            schema: Schema to filter by (default: Company)

        Returns:
            Dict with success status and results or error
        """
        if not self.api_key:
            return {
                "success": False,
                "error": "No ALEPH_API_KEY configured"
            }

        try:
            params = {
                "q": query,
                "filter:schema": schema,
                "limit": min(max_results, 30),
            }

            headers = {
                "Authorization": f"ApiKey {self.api_key}",
                "Accept": "application/json"
            }

            response = requests.get(
                f"{self.BASE_URL}/entities",
                params=params,
                headers=headers,
                timeout=20
            )

            response.raise_for_status()
            data = response.json()

            results = []
            for item in data.get("results", []):
                results.append(self._parse_entity_sync(item))

            return {
                "success": True,
                "data": results,
                "total": data.get("total", len(results))
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"Aleph sync search error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        except ValueError as e:
            return {
                "success": False,
                "error": f"Invalid JSON response: {e}"
            }

    def search_company(self, company_name: str, jurisdiction: str = None) -> Dict[str, Any]:
        """
        Search for a company with optional jurisdiction filter.

        Args:
            company_name: Company name to search
            jurisdiction: Optional 2-letter jurisdiction code

        Returns:
            Dict with success status and results
        """
        query = company_name

        # Add jurisdiction to query if provided
        if jurisdiction:
            query = f"{company_name} jurisdiction:{jurisdiction}"

        return self.search_sync(query, schema="Company")

    def search_person(self, person_name: str) -> Dict[str, Any]:
        """
        Search for a person.

        Args:
            person_name: Person name to search

        Returns:
            Dict with success status and results
        """
        return self.search_sync(person_name, schema="Person")

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _prepare_query(self, query: str) -> tuple:
        """
        Prepare search query, detecting exact phrase and intitle searches.

        Returns:
            Tuple of (prepared_query, is_exact_phrase)
        """
        is_exact_phrase = False
        search_query = query

        # Check for intitle: prefix
        intitle_match = re.match(r'^"?intitle:(.*?)"?$', query, re.IGNORECASE)
        if intitle_match:
            keyword_part = intitle_match.group(1).strip()
            if ' ' in keyword_part:
                search_query = f'title:"{keyword_part}"'
            else:
                search_query = f'title:{keyword_part}'
            logger.info(f"intitle search: {search_query}")
        else:
            # Check for exact phrase (quoted)
            if query.startswith('"') and query.endswith('"') and len(query) > 2:
                is_exact_phrase = True
                # Preserve quotes for Aleph API
                search_query = query
                logger.info(f"Exact phrase search: {search_query}")

        return search_query, is_exact_phrase

    def _parse_entity(self, item: Dict, is_exact_phrase: bool = False) -> Dict:
        """Parse an Aleph entity response into a standardized result."""
        props = item.get("properties", {})

        # Extract title
        title = (
            item.get("caption") or
            item.get("name") or
            self._get_prop(props, "title") or
            self._get_prop(props, "name") or
            self._get_prop(props, "label") or
            "Unknown"
        )

        # Extract snippet
        snippet = (
            item.get("summary") or
            item.get("description") or
            self._get_prop(props, "text") or
            ""
        )

        result = {
            "title": title,
            "url": f"https://aleph.occrp.org/entities/{item.get('id')}",
            "snippet": snippet,
            "source": "aleph",
            "schema": item.get("schema", ""),
            "properties": props,
            "exact_phrase_search": is_exact_phrase
        }

        # Add source URL
        source_url = props.get("sourceUrl")
        if source_url:
            result["source_url"] = source_url[0] if isinstance(source_url, list) else source_url

        # Add document metadata
        if item.get("schema") == "Document":
            self._add_document_metadata(result, item, props)

        # Add collection info
        collection = item.get("collection")
        if collection:
            result["collection_id"] = collection.get("id")
            result["collection_label"] = collection.get("label")
            result["category"] = collection.get("category")

        return result

    def _parse_entity_sync(self, item: Dict) -> Dict:
        """Parse entity for sync search - simpler format."""
        props = item.get("properties", {})

        name = (
            item.get("caption") or
            item.get("name") or
            self._get_prop(props, "name") or
            self._get_prop(props, "legalName") or
            "Unknown"
        )

        return {
            "name": name,
            "url": f"https://aleph.occrp.org/entities/{item.get('id')}",
            "schema": item.get("schema", ""),
            "jurisdiction": self._get_prop(props, "jurisdiction"),
            "registration_number": self._get_prop(props, "registrationNumber"),
            "source": "aleph"
        }

    def _get_prop(self, props: Dict, key: str) -> Optional[str]:
        """Safely get a property value."""
        val = props.get(key)
        if isinstance(val, list):
            return val[0] if val else None
        return val

    def _add_document_metadata(self, result: Dict, item: Dict, props: Dict):
        """Add document-specific metadata to result."""
        # Check for PDF URL
        pdf_url = None
        file_url = item.get("file_url")
        if file_url and isinstance(file_url, str) and file_url.lower().endswith(".pdf"):
            pdf_url = file_url

        if not pdf_url:
            for field in ["fileUrl", "documentUrl", "sourceUrl", "url"]:
                if field in props:
                    url_value = props[field]
                    if isinstance(url_value, str) and url_value.lower().endswith(".pdf"):
                        pdf_url = url_value
                        break
                    elif isinstance(url_value, list):
                        pdf_urls = [u for u in url_value if isinstance(u, str) and u.lower().endswith(".pdf")]
                        if pdf_urls:
                            pdf_url = pdf_urls[0]
                            break

        # Add processing status
        result["processing_status"] = self._get_prop(props, "processingStatus") or "unknown"
        if props.get("processingError"):
            result["processing_error"] = self._get_prop(props, "processingError")

        if pdf_url:
            result["pdf_url"] = pdf_url

        # Add file metadata
        if props.get("fileSize"):
            result["file_size"] = self._get_prop(props, "fileSize")
        if props.get("mimeType"):
            result["mime_type"] = self._get_prop(props, "mimeType")

    def _matches_categories(self, result: Dict, allowed_categories: List[str]) -> bool:
        """Check if result matches allowed categories."""
        category = result.get("category", "").lower()
        schema = result.get("schema", "").lower()

        # Map schemas to categories
        schema_to_category = {
            "company": "company",
            "legalentity": "company",
            "document": "grey",
            "person": "poi",
        }

        if category in allowed_categories:
            return True

        inferred_category = schema_to_category.get(schema)
        if inferred_category and inferred_category in allowed_categories:
            return True

        return False


# =========================================================================
# CONVENIENCE FUNCTIONS
# =========================================================================

def search_occrp(query: str, max_results: int = 50) -> Dict[str, Any]:
    """
    Simple sync search function for quick lookups.

    Args:
        query: Search query
        max_results: Maximum results

    Returns:
        Dict with success status and results
    """
    searcher = AlephSearcher()
    return searcher.search_sync(query, max_results)


async def search_occrp_async(
    query: str,
    max_results: int = 100,
    jurisdiction: str = None,
    section: str = None
) -> List[Dict]:
    """
    Async search function with optional filtering.

    Args:
        query: Search query
        max_results: Maximum results
        jurisdiction: Optional 2-letter jurisdiction code
        section: Optional section code (cr, lit, reg, ass, leak, news)

    Returns:
        List of search results
    """
    # Try to load collections
    collections_path = None
    try:
        from pathlib import Path
        matrix_dir = Path(__file__).resolve().parents[3] / "input_output" / "matrix"
        collections_path = matrix_dir / "aleph_collections.json"
    except:
        pass

    searcher = AlephSearcher(collections_path=collections_path)

    if jurisdiction and section:
        return await searcher.search_by_section(query, jurisdiction, section, max_results)
    else:
        return await searcher.search(query, max_results)


# =========================================================================
# CLI INTERFACE
# =========================================================================

def main():
    """Interactive CLI for OCCRP Aleph searches."""
    import argparse

    parser = argparse.ArgumentParser(description="OCCRP Aleph Search CLI")
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("--max-results", "-n", type=int, default=50, help="Max results")
    parser.add_argument("--jurisdiction", "-j", help="2-letter jurisdiction code (e.g., GB, US)")
    parser.add_argument("--section", "-s", choices=["cr", "lit", "reg", "ass", "leak", "news"],
                        help="Wiki section filter")
    parser.add_argument("--output", "-o", choices=["json", "table"], default="table",
                        help="Output format")

    args = parser.parse_args()

    if not args.query:
        # Interactive mode
        print("=" * 60)
        print("OCCRP ALEPH SEARCH")
        print("=" * 60)

        searcher = AlephSearcher()

        while True:
            query = input("\nSearch query (or 'exit'): ").strip()
            if query.lower() == 'exit':
                break

            result = searcher.search_sync(query)

            if result.get("success"):
                print(f"\nFound {len(result['data'])} results:")
                for i, item in enumerate(result['data'][:10], 1):
                    print(f"\n{i}. {item.get('name', 'Unknown')}")
                    if item.get('jurisdiction'):
                        print(f"   Jurisdiction: {item['jurisdiction']}")
                    if item.get('registration_number'):
                        print(f"   Reg #: {item['registration_number']}")
                    print(f"   URL: {item.get('url', '')}")
            else:
                print(f"Error: {result.get('error')}")
    else:
        # Command-line mode
        if args.jurisdiction and args.section:
            results = asyncio.run(search_occrp_async(
                args.query,
                args.max_results,
                args.jurisdiction,
                args.section
            ))
        else:
            searcher = AlephSearcher()
            result = searcher.search_sync(args.query, args.max_results)
            results = result.get("data", []) if result.get("success") else []

        if args.output == "json":
            print(json.dumps(results, indent=2))
        else:
            print(f"\nFound {len(results)} results:")
            for i, item in enumerate(results[:20], 1):
                name = item.get('name') or item.get('title', 'Unknown')
                print(f"{i}. {name}")


if __name__ == "__main__":
    main()
