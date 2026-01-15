"""
SeekLeech Engine v2.0 - Execution Module

Executes searches across Matrix sources and returns structured data.

Given an entity + jurisdiction + thematic filter:
1. Select appropriate sources from Matrix (scored by reliability)
2. Execute queries in parallel with timeout
3. Extract structured data using learned output_schema
4. Merge and deduplicate results

Usage:
    from executor import SeekLeechExecutor

    exec = SeekLeechExecutor()
    await exec.load_sources("sources_v3.json")

    results = await exec.search(
        query="Acme Corp",
        input_type="company_name",
        jurisdiction="HU",
        thematic_filter=["corporate_registry", "officers"]
    )
"""

import asyncio
import json
import re
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
import httpx
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

from .schemas import (
    EnhancedSource, InputSchema, OutputSchema, OutputField,
    StructuredResult, SearchResponse, ReliabilityMetrics,
    FIELD_CODES, get_field_code
)
from .taxonomy import (
    THEMATIC_TAXONOMY, get_category_for_tag, get_tags_for_category,
    TAG_TO_CATEGORY, ALL_THEMATIC_TAGS
)

logger = logging.getLogger("SeekLeech.Executor")


# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_SOURCES = 5
DEFAULT_MAX_RESULTS_PER_SOURCE = 50


# ─────────────────────────────────────────────────────────────
# SeekLeech Executor
# ─────────────────────────────────────────────────────────────

class SeekLeechExecutor:
    """
    Execute searches across Matrix sources and return structured data.
    """

    def __init__(self, firecrawl_api_key: str = None):
        import os
        self.firecrawl_api_key = firecrawl_api_key or os.getenv("FIRECRAWL_API_KEY")
        self.firecrawl_url = os.getenv("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev/v1")

        self.http = httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        )

        # Source index
        self.sources: List[EnhancedSource] = []
        self.sources_by_id: Dict[str, EnhancedSource] = {}
        self.sources_by_jurisdiction: Dict[str, List[EnhancedSource]] = {}
        self.sources_by_input_type: Dict[str, List[EnhancedSource]] = {}
        self.sources_by_thematic: Dict[str, List[EnhancedSource]] = {}

    async def close(self):
        await self.http.aclose()

    # ─────────────────────────────────────────────────────────────
    # Source Loading & Indexing
    # ─────────────────────────────────────────────────────────────

    async def load_sources(self, sources_path: Path):
        """
        Load sources from JSON and build indexes.
        Supports both sources_v2.json (dict by jurisdiction) and
        sources_v3.json (list with enhanced schema) formats.
        """
        with open(sources_path) as f:
            data = json.load(f)

        self.sources = []
        self.sources_by_id = {}
        self.sources_by_jurisdiction = {}
        self.sources_by_input_type = {}
        self.sources_by_thematic = {}

        # Handle both formats
        if isinstance(data, dict):
            # sources_v2.json format: {jurisdiction: [sources]}
            for jur, entries in data.items():
                for entry in entries:
                    entry["jurisdiction"] = jur  # Ensure jurisdiction is set
                    source = EnhancedSource.from_dict(entry)
                    self._index_source(source)
        elif isinstance(data, list):
            # sources_v3.json format: [sources]
            for entry in data:
                source = EnhancedSource.from_dict(entry)
                self._index_source(source)

        logger.info(f"Loaded {len(self.sources)} sources across {len(self.sources_by_jurisdiction)} jurisdictions")

    def _index_source(self, source: EnhancedSource):
        """Add source to all indexes."""
        # Only index sources with templates
        if not source.search_template:
            return

        self.sources.append(source)
        self.sources_by_id[source.id] = source

        # By jurisdiction
        jur = source.jurisdiction or "GLOBAL"
        if jur not in self.sources_by_jurisdiction:
            self.sources_by_jurisdiction[jur] = []
        self.sources_by_jurisdiction[jur].append(source)

        # By input type
        input_type = "company_name"  # Default
        if source.input_schema:
            input_type = source.input_schema.input_type
        if input_type not in self.sources_by_input_type:
            self.sources_by_input_type[input_type] = []
        self.sources_by_input_type[input_type].append(source)

        # By thematic tag
        for tag in source.thematic_tags:
            if tag not in self.sources_by_thematic:
                self.sources_by_thematic[tag] = []
            self.sources_by_thematic[tag].append(source)

    def load_sources_sync(self, sources_path: Path):
        """Synchronous source loading for use outside async context."""
        asyncio.get_event_loop().run_until_complete(self.load_sources(sources_path))

    # ─────────────────────────────────────────────────────────────
    # Source Selection
    # ─────────────────────────────────────────────────────────────

    def select_sources(
        self,
        input_type: str,
        jurisdiction: str,
        thematic_filter: List[str] = None,
        max_sources: int = DEFAULT_MAX_SOURCES,
        include_global: bool = True
    ) -> List[EnhancedSource]:
        """
        Select best sources for a query using Matrix intelligence.

        Scoring:
        - Reliability score (success_rate / latency)
        - Input type match
        - Thematic tag match
        - Jurisdiction match
        """
        candidates: List[Tuple[float, EnhancedSource]] = []

        # Get sources for jurisdiction
        jur_sources = self.sources_by_jurisdiction.get(jurisdiction, [])

        # Include GLOBAL sources if requested
        if include_global and jurisdiction != "GLOBAL":
            global_sources = self.sources_by_jurisdiction.get("GLOBAL", [])
            jur_sources = jur_sources + global_sources

        for source in jur_sources:
            # Input type match (if schema exists)
            if source.input_schema:
                if source.input_schema.input_type != input_type:
                    # Allow company_name for keyword searches
                    if not (input_type == "keyword" and source.input_schema.input_type == "company_name"):
                        continue

            # Thematic filter
            if thematic_filter:
                source_tags = set(source.thematic_tags)
                filter_tags = set(thematic_filter)
                if not source_tags.intersection(filter_tags):
                    continue

            # Calculate score - pass jurisdiction for local boost
            score = self._score_source(source, input_type, thematic_filter, jurisdiction)
            candidates.append((score, source))

        # Sort by score descending
        candidates.sort(key=lambda x: -x[0])

        # Return top N
        selected = [s for _, s in candidates[:max_sources]]

        logger.debug(f"Selected {len(selected)} sources for {input_type}/{jurisdiction}")
        return selected

    def _score_source(
        self,
        source: EnhancedSource,
        input_type: str,
        thematic_filter: List[str] = None,
        target_jurisdiction: str = None
    ) -> float:
        """
        Calculate source quality score for ranking.
        Higher is better.

        IMPORTANT: Local (jurisdiction-specific) sources get a 10x boost
        over GLOBAL sources to ensure relevant results.
        """
        score = 0.5  # Base score

        # Reliability score (if available)
        if source.reliability:
            # Success rate is most important
            score = source.reliability.success_rate

            # Penalize slow sources
            if source.reliability.avg_latency > 5.0:
                score *= 0.8
            elif source.reliability.avg_latency > 10.0:
                score *= 0.5

            # Penalize consecutive failures
            if source.reliability.consecutive_failures > 3:
                score *= 0.5
            elif source.reliability.consecutive_failures > 5:
                score *= 0.1

        # MAJOR BOOST for jurisdiction-specific sources (10x multiplier)
        # Local registries are far more relevant than global aggregators
        if target_jurisdiction and source.jurisdiction == target_jurisdiction:
            score *= 10.0
        elif source.jurisdiction == "GLOBAL":
            # GLOBAL sources only get base score - no penalty, but no boost
            pass

        # Boost for exact input type match
        if source.input_schema and source.input_schema.input_type == input_type:
            score *= 1.2

        # Boost for thematic match
        if thematic_filter and source.thematic_tags:
            match_count = len(set(source.thematic_tags).intersection(set(thematic_filter)))
            score *= (1 + 0.1 * match_count)

        # Boost for output schema (learned structure)
        if source.output_schema and source.output_schema.fields:
            score *= 1.3

        # Boost for public access (vs paywalled)
        if source.access == "public":
            score *= 1.1

        return score

    def get_sources_for_entity(
        self,
        entity_type: str,
        jurisdiction: str,
        thematic_filter: List[str] = None,
        max_sources: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get available sources for an entity type and jurisdiction.
        Returns source metadata suitable for UI display.
        """
        # Map entity type to input type
        entity_to_input = {
            "company": "company_name",
            "company_name": "company_name",
            "person": "person_name",
            "person_name": "person_name",
            "reg_id": "company_reg_id",
            "company_reg_id": "company_reg_id",
            "case_number": "case_number",
            "address": "property_address",
            "keyword": "keyword"
        }
        input_type = entity_to_input.get(entity_type, "company_name")

        sources = self.select_sources(
            input_type=input_type,
            jurisdiction=jurisdiction,
            thematic_filter=thematic_filter,
            max_sources=max_sources
        )

        return [
            {
                "id": s.id,
                "domain": s.domain,
                "name": s.name or s.domain,
                "jurisdiction": s.jurisdiction,
                "thematic_tags": s.thematic_tags,
                "reliability": s.reliability.success_rate if s.reliability else None,
                "latency": s.reliability.avg_latency if s.reliability else None,
                "has_output_schema": s.output_schema is not None,
                "access": s.access
            }
            for s in sources
        ]

    # ─────────────────────────────────────────────────────────────
    # Scraping
    # ─────────────────────────────────────────────────────────────

    async def _scrape(self, url: str, timeout: float = DEFAULT_TIMEOUT) -> Tuple[Optional[str], float]:
        """
        Scrape URL with fallback and timing.
        Returns (html, latency) or (None, latency).
        """
        start = time.time()

        # Try direct first
        try:
            resp = await self.http.get(url, timeout=timeout)
            if resp.status_code == 200 and len(resp.text) > 100:
                return resp.text, time.time() - start
        except Exception as e:
            logger.debug(f"Direct scrape failed for {url}: {e}")

        # Firecrawl fallback
        if self.firecrawl_api_key:
            try:
                resp = await self.http.post(
                    f"{self.firecrawl_url}/scrape",
                    headers={
                        "Authorization": f"Bearer {self.firecrawl_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={"url": url, "formats": ["html"]},
                    timeout=timeout
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success") and data.get("data", {}).get("html"):
                        return data["data"]["html"], time.time() - start
            except Exception as e:
                logger.debug(f"Firecrawl failed for {url}: {e}")

        return None, time.time() - start

    # ─────────────────────────────────────────────────────────────
    # Structured Extraction
    # ─────────────────────────────────────────────────────────────

    def _extract_structured(
        self,
        html: str,
        source: EnhancedSource,
        query: str
    ) -> List[StructuredResult]:
        """
        Extract structured data using learned output_schema.
        Falls back to basic extraction if no schema.
        """
        if not source.output_schema:
            return self._extract_basic(html, source, query)

        schema = source.output_schema
        results = []

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Find results container
            container = soup
            if schema.results_container:
                found = soup.select_one(schema.results_container)
                if found:
                    container = found

            # Find rows
            rows = []
            if schema.row_selector:
                rows = container.select(schema.row_selector)
            elif schema.result_type == "table":
                # Try common table patterns
                rows = container.select("tr:has(td)")
            elif schema.result_type == "list":
                rows = container.select("li")
            elif schema.result_type == "cards":
                rows = container.select(".card, .result, .item")

            if not rows:
                # Fall back to basic
                return self._extract_basic(html, source, query)

            for i, row in enumerate(rows[:DEFAULT_MAX_RESULTS_PER_SOURCE]):
                fields = {}
                field_codes = {}

                for field_def in schema.fields:
                    value = None

                    if field_def.css_selector:
                        cell = row.select_one(field_def.css_selector)
                        if cell:
                            value = cell.get_text(strip=True)

                    if value:
                        fields[field_def.name] = value
                        if field_def.field_code:
                            field_codes[field_def.name] = field_def.field_code

                if fields:
                    # Calculate match score
                    match_score = self._calculate_match_score(query, fields)

                    result = StructuredResult(
                        source_id=source.id,
                        source_url=source.url,
                        query=query,
                        fields=fields,
                        field_codes=field_codes,
                        confidence=0.9 if len(fields) > 2 else 0.7,
                        match_score=match_score,
                        extracted_at=datetime.now().isoformat()
                    )
                    results.append(result)

        except Exception as e:
            logger.debug(f"Structured extraction failed: {e}")
            return self._extract_basic(html, source, query)

        return results

    def _extract_basic(
        self,
        html: str,
        source: EnhancedSource,
        query: str
    ) -> List[StructuredResult]:
        """
        Basic extraction without schema - just find tables or lists.
        """
        results = []

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Remove navigation, scripts
            for tag in soup(['script', 'style', 'nav', 'footer']):
                tag.decompose()

            # Try to find main content table
            tables = soup.find_all('table')
            for table in tables[:2]:  # Max 2 tables
                rows = table.find_all('tr')
                headers = []

                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if not cells:
                        continue

                    # First row might be headers
                    if not headers and row.find_all('th'):
                        headers = [th.get_text(strip=True).lower()[:30] for th in cells]
                        continue

                    # Data row
                    if not headers:
                        headers = [f"col_{i}" for i in range(len(cells))]

                    fields = {}
                    for i, cell in enumerate(cells):
                        if i < len(headers):
                            value = cell.get_text(strip=True)
                            if value:
                                fields[headers[i]] = value

                    if fields:
                        match_score = self._calculate_match_score(query, fields)
                        result = StructuredResult(
                            source_id=source.id,
                            source_url=source.url,
                            query=query,
                            fields=fields,
                            field_codes={},  # Can't map without schema
                            confidence=0.5,  # Lower confidence for basic extraction
                            match_score=match_score,
                            extracted_at=datetime.now().isoformat()
                        )
                        results.append(result)

        except Exception as e:
            logger.debug(f"Basic extraction failed: {e}")

        return results

    def _calculate_match_score(self, query: str, fields: Dict[str, Any]) -> float:
        """
        Calculate how well the result matches the query.
        0.0 = no match, 1.0 = perfect match
        """
        query_lower = query.lower()
        query_tokens = set(query_lower.split())

        max_score = 0.0

        for key, value in fields.items():
            if not value:
                continue

            value_lower = str(value).lower()
            value_tokens = set(value_lower.split())

            # Exact match
            if query_lower == value_lower:
                return 1.0

            # Substring match
            if query_lower in value_lower:
                max_score = max(max_score, 0.9)
            elif value_lower in query_lower:
                max_score = max(max_score, 0.8)

            # Token overlap
            overlap = len(query_tokens.intersection(value_tokens))
            if overlap > 0:
                token_score = overlap / max(len(query_tokens), len(value_tokens))
                max_score = max(max_score, token_score * 0.7)

        return max_score

    # ─────────────────────────────────────────────────────────────
    # Main Search Method
    # ─────────────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        input_type: str,
        jurisdiction: str,
        thematic_filter: List[str] = None,
        source_ids: List[str] = None,
        max_sources: int = DEFAULT_MAX_SOURCES,
        timeout: float = DEFAULT_TIMEOUT
    ) -> SearchResponse:
        """
        Execute search across Matrix sources and return structured data.

        Args:
            query: Search query (company name, person name, etc.)
            input_type: Type of query (company_name, person_name, reg_id, etc.)
            jurisdiction: Two-letter country code (HU, DE, US, GB, etc.)
            thematic_filter: Optional list of thematic tags to filter sources
            source_ids: Optional specific source IDs to use (bypasses selection)
            max_sources: Maximum number of sources to query
            timeout: Timeout per source in seconds

        Returns:
            SearchResponse with structured results from all sources
        """
        start_time = datetime.now()

        response = SearchResponse(
            query=query,
            input_type=input_type,
            jurisdiction=jurisdiction,
            started_at=start_time.isoformat()
        )

        # Select or use specified sources
        if source_ids:
            sources = [
                self.sources_by_id[sid]
                for sid in source_ids
                if sid in self.sources_by_id
            ]
        else:
            sources = self.select_sources(
                input_type=input_type,
                jurisdiction=jurisdiction,
                thematic_filter=thematic_filter,
                max_sources=max_sources
            )

        if not sources:
            response.completed_at = datetime.now().isoformat()
            response.errors.append({
                "type": "no_sources",
                "message": f"No sources available for {input_type}/{jurisdiction}"
            })
            return response

        response.sources_queried = len(sources)

        # URL-encode query
        encoded_query = quote_plus(query)

        # Execute in parallel
        async def query_source(source: EnhancedSource) -> Tuple[EnhancedSource, List[StructuredResult], Optional[str]]:
            """Query a single source and extract results."""
            try:
                # Build URL
                url = source.search_template.replace("{q}", encoded_query)

                # Scrape
                html, latency = await self._scrape(url, timeout)

                if not html:
                    return source, [], f"Failed to scrape {source.domain}"

                # Update reliability metrics (in-memory only)
                if source.reliability:
                    source.reliability.record_success(latency)
                else:
                    source.reliability = ReliabilityMetrics()
                    source.reliability.record_success(latency)

                # Extract structured data
                results = self._extract_structured(html, source, query)

                return source, results, None

            except asyncio.TimeoutError:
                return source, [], f"Timeout querying {source.domain}"
            except Exception as e:
                return source, [], f"Error querying {source.domain}: {str(e)}"

        # Run all queries
        tasks = [query_source(s) for s in sources]
        task_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        all_results: List[StructuredResult] = []

        for result in task_results:
            if isinstance(result, Exception):
                response.errors.append({
                    "type": "exception",
                    "message": str(result)
                })
                continue

            source, results, error = result
            if error:
                response.errors.append({
                    "type": "source_error",
                    "source_id": source.id,
                    "message": error
                })
            else:
                response.sources_succeeded += 1
                all_results.extend(results)

        # Merge and deduplicate
        response.results = self._merge_results(all_results)
        response.total_results = len(response.results)

        response.completed_at = datetime.now().isoformat()
        response.total_latency = (datetime.now() - start_time).total_seconds()

        logger.info(
            f"Search '{query}' ({input_type}/{jurisdiction}): "
            f"{response.total_results} results from {response.sources_succeeded}/{response.sources_queried} sources "
            f"in {response.total_latency:.2f}s"
        )

        return response

    async def search_single_source(
        self,
        query: str,
        source_id: str,
        timeout: float = DEFAULT_TIMEOUT
    ) -> SearchResponse:
        """
        Execute search on a single specific source.
        """
        source = self.sources_by_id.get(source_id)
        if not source:
            return SearchResponse(
                query=query,
                input_type="unknown",
                jurisdiction="unknown",
                errors=[{"type": "not_found", "message": f"Source {source_id} not found"}]
            )

        return await self.search(
            query=query,
            input_type=source.input_schema.input_type if source.input_schema else "company_name",
            jurisdiction=source.jurisdiction,
            source_ids=[source_id],
            timeout=timeout
        )

    def _merge_results(self, results: List[StructuredResult]) -> List[StructuredResult]:
        """
        Merge and deduplicate results from multiple sources.
        Keeps highest confidence/match_score for duplicates.
        """
        if not results:
            return []

        # Group by key fields (company name + reg id if available)
        seen: Dict[str, StructuredResult] = {}

        for result in results:
            # Build dedup key
            key_parts = []

            # Use company name if available
            for name_field in ["company_name", "name", "col_0"]:
                if name_field in result.fields:
                    key_parts.append(str(result.fields[name_field]).lower().strip())
                    break

            # Use reg ID if available
            for id_field in ["registration_number", "reg_id", "company_reg_id", "col_1"]:
                if id_field in result.fields:
                    key_parts.append(str(result.fields[id_field]).lower().strip())
                    break

            if not key_parts:
                # No dedup key, keep all
                key = f"_unique_{len(seen)}"
            else:
                key = "|".join(key_parts)

            # Keep best match
            if key not in seen:
                seen[key] = result
            else:
                existing = seen[key]
                # Prefer higher match score, then confidence
                if (result.match_score, result.confidence) > (existing.match_score, existing.confidence):
                    seen[key] = result

        # Sort by match score
        merged = sorted(seen.values(), key=lambda r: (-r.match_score, -r.confidence))

        return merged

    # ─────────────────────────────────────────────────────────────
    # Convenience Methods
    # ─────────────────────────────────────────────────────────────

    async def search_company(
        self,
        company_name: str,
        jurisdiction: str,
        include_officers: bool = True,
        include_filings: bool = False
    ) -> SearchResponse:
        """
        Convenience method for company searches.
        """
        thematic_filter = ["corporate_registry"]
        if include_officers:
            thematic_filter.append("officers")
        if include_filings:
            thematic_filter.append("filings")

        return await self.search(
            query=company_name,
            input_type="company_name",
            jurisdiction=jurisdiction,
            thematic_filter=thematic_filter
        )

    async def search_person(
        self,
        person_name: str,
        jurisdiction: str,
        include_roles: bool = True
    ) -> SearchResponse:
        """
        Convenience method for person searches.
        """
        thematic_filter = []
        if include_roles:
            thematic_filter.extend(["officers", "beneficial_ownership"])

        return await self.search(
            query=person_name,
            input_type="person_name",
            jurisdiction=jurisdiction,
            thematic_filter=thematic_filter if thematic_filter else None
        )

    async def search_court_records(
        self,
        query: str,
        jurisdiction: str
    ) -> SearchResponse:
        """
        Convenience method for court/litigation searches.
        """
        return await self.search(
            query=query,
            input_type="keyword",
            jurisdiction=jurisdiction,
            thematic_filter=["court_records", "litigation", "judgments"]
        )

    async def search_property(
        self,
        address_or_parcel: str,
        jurisdiction: str
    ) -> SearchResponse:
        """
        Convenience method for property searches.
        """
        return await self.search(
            query=address_or_parcel,
            input_type="property_address",
            jurisdiction=jurisdiction,
            thematic_filter=["land_registry", "cadastre", "property"]
        )


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S"
    )

    parser = argparse.ArgumentParser(description="Execute SeekLeech searches")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--sources", required=True, help="Path to sources JSON")
    parser.add_argument("--jurisdiction", "-j", default="GLOBAL", help="Jurisdiction code (HU, DE, US, etc.)")
    parser.add_argument("--input-type", "-t", default="company_name", help="Input type")
    parser.add_argument("--thematic", "-f", nargs="*", help="Thematic filters")
    parser.add_argument("--max-sources", type=int, default=5, help="Max sources to query")
    parser.add_argument("--timeout", type=float, default=30.0, help="Timeout per source")
    parser.add_argument("--output", "-o", help="Output JSON file")

    args = parser.parse_args()

    async def main():
        executor = SeekLeechExecutor()
        await executor.load_sources(Path(args.sources))

        response = await executor.search(
            query=args.query,
            input_type=args.input_type,
            jurisdiction=args.jurisdiction,
            thematic_filter=args.thematic,
            max_sources=args.max_sources,
            timeout=args.timeout
        )

        print(f"\n{'='*60}")
        print(f"Query: {args.query}")
        print(f"Input Type: {args.input_type}")
        print(f"Jurisdiction: {args.jurisdiction}")
        print(f"Sources: {response.sources_succeeded}/{response.sources_queried}")
        print(f"Results: {response.total_results}")
        print(f"Latency: {response.total_latency:.2f}s")
        print(f"{'='*60}\n")

        if response.results:
            print("Results:")
            for i, result in enumerate(response.results[:10], 1):
                print(f"\n[{i}] Source: {result.source_id}")
                print(f"    Match: {result.match_score:.2f} | Confidence: {result.confidence:.2f}")
                for field, value in result.fields.items():
                    print(f"    {field}: {value}")

        if response.errors:
            print("\nErrors:")
            for err in response.errors:
                print(f"  - {err.get('message')}")

        if args.output:
            with open(args.output, 'w') as f:
                json.dump(response.to_dict(), f, indent=2)
            print(f"\nResults saved to {args.output}")

        await executor.close()

    asyncio.run(main())
