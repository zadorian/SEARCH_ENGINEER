"""
SASTRE Bulk Search Execution

Executes bulk entity searches with:
- Round-robin execution for fair distribution and rate limit spreading
- Combined AND searches for co-occurrence detection
- TLD and keyword filter application
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional, AsyncGenerator
from enum import Enum

from .selection import BulkSelection, BatchOperation


class SearchPhase(Enum):
    """Phases of bulk search execution."""
    INDIVIDUAL = "individual"     # Each entity searched separately
    COMBINED = "combined"         # All entities AND'd together


@dataclass
class SearchQuery:
    """A single search query to execute."""
    id: str
    entity_label: str                     # Which entity this is for
    query_string: str                     # Actual search query
    phase: SearchPhase
    batch_number: int = 0                 # For round-robin: which batch
    tld_filters: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)


@dataclass
class SearchResult:
    """Result from a single search query."""
    query_id: str
    entity_label: str
    urls: List[str] = field(default_factory=list)
    snippets: Dict[str, str] = field(default_factory=dict)  # url -> snippet
    engine: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class BulkSearchResult:
    """Aggregated results from bulk search."""
    batch_operation_id: str
    total_results: int = 0
    results_per_entity: Dict[str, int] = field(default_factory=dict)
    combined_results: int = 0
    all_urls: List[str] = field(default_factory=list)
    url_to_entities: Dict[str, List[str]] = field(default_factory=dict)  # Which entities appear
    search_results: List[SearchResult] = field(default_factory=list)


@dataclass
class BulkSearchStrategy:
    """Configuration for bulk search execution."""
    batch_size: int = 10                  # Results per entity per round
    max_rounds: int = 5                   # Maximum round-robin rounds
    inter_round_delay_ms: int = 500       # Delay between rounds (rate limiting)
    inter_entity_delay_ms: int = 100      # Delay between entities within round
    include_combined: bool = True          # Also search entities combined (AND)
    combined_after_round: int = 1          # Run combined search after this round


# =============================================================================
# QUERY BUILDING
# =============================================================================

def build_bulk_queries(
    selection: BulkSelection,
    operation: str,
    filters: Dict[str, Any],
    variations_provider: Any = None,
) -> List[SearchQuery]:
    """
    Build search queries for bulk execution.

    Args:
        selection: The bulk selection with node labels
        operation: "brute" or "brute!"
        filters: {"keywords": [...], "tld": [...]}
        variations_provider: Optional provider for name variations

    Returns:
        List of SearchQuery objects ready for execution
    """
    queries = []
    keywords = filters.get("keywords", [])
    tld_filters = filters.get("tld", [])

    # Build individual queries for each entity
    for i, label in enumerate(selection.node_labels):
        # Get entity name (label or resolved from provider)
        entity_name = label.replace("_", " ").title()  # Basic: john_smith -> John Smith

        # Get variations if provider available
        variations = [entity_name]
        if variations_provider:
            variations = variations_provider.get_variations(entity_name)

        # Build query string
        query_parts = []

        # Entity variations as OR group
        if len(variations) > 1:
            var_group = " OR ".join(f'"{v}"' for v in variations)
            query_parts.append(f"({var_group})")
        else:
            query_parts.append(f'"{variations[0]}"')

        # Add keywords
        for kw in keywords:
            query_parts.append(f'"{kw}"')

        # Add TLD filters
        for tld in tld_filters:
            site_filter = _tld_to_site_filter(tld)
            if site_filter:
                query_parts.append(site_filter)

        query_string = " ".join(query_parts)

        queries.append(SearchQuery(
            id=f"sq_{selection.id}_{i}",
            entity_label=label,
            query_string=query_string,
            phase=SearchPhase.INDIVIDUAL,
            tld_filters=tld_filters,
            keywords=keywords,
        ))

    # Build combined query (all entities AND'd)
    if len(selection.node_labels) > 1:
        combined_parts = []
        for label in selection.node_labels:
            entity_name = label.replace("_", " ").title()
            combined_parts.append(f'"{entity_name}"')

        # AND all entities
        combined_query = " AND ".join(combined_parts)

        # Add keywords
        for kw in keywords:
            combined_query += f' "{kw}"'

        # Add TLD filters
        for tld in tld_filters:
            site_filter = _tld_to_site_filter(tld)
            if site_filter:
                combined_query += f" {site_filter}"

        queries.append(SearchQuery(
            id=f"sq_{selection.id}_combined",
            entity_label="_COMBINED_",
            query_string=combined_query,
            phase=SearchPhase.COMBINED,
            tld_filters=tld_filters,
            keywords=keywords,
        ))

    return queries


def _tld_to_site_filter(tld: str) -> str:
    """Convert TLD operator to site: filter."""
    TLD_MAP = {
        "de!": "site:.de",
        "uk!": "(site:.uk OR site:.co.uk)",
        "us!": "(site:.us OR site:.gov)",
        "com!": "site:.com",
        "gov!": "site:.gov",
        "ru!": "site:.ru",
        "cy!": "(site:.cy OR site:.com.cy)",
    }
    return TLD_MAP.get(tld, "")


# =============================================================================
# ROUND-ROBIN EXECUTION
# =============================================================================

async def execute_bulk_search(
    batch: BatchOperation,
    strategy: BulkSearchStrategy,
    search_executor: Any,
) -> AsyncGenerator[SearchResult, None]:
    """
    Execute bulk search with round-robin strategy.

    Yields results as they come in for streaming to frontend.

    Args:
        batch: The batch operation
        strategy: Execution strategy configuration
        search_executor: Actual search backend (BruteSearch bridge)

    Yields:
        SearchResult objects as searches complete
    """
    queries = build_bulk_queries(
        batch.selection,
        batch.operation,
        batch.filters,
    )

    # Separate individual and combined queries
    individual_queries = [q for q in queries if q.phase == SearchPhase.INDIVIDUAL]
    combined_queries = [q for q in queries if q.phase == SearchPhase.COMBINED]

    # Round-robin execution
    for round_num in range(strategy.max_rounds):
        # Execute one batch for each entity (round-robin)
        for query in individual_queries:
            query.batch_number = round_num

            # Execute search
            try:
                results = await search_executor.search(
                    query.query_string,
                    offset=round_num * strategy.batch_size,
                    limit=strategy.batch_size,
                )

                search_result = SearchResult(
                    query_id=query.id,
                    entity_label=query.entity_label,
                    urls=[r.get("url", "") for r in results],
                    snippets={r.get("url", ""): r.get("snippet", "") for r in results},
                    engine="brute",
                )
                yield search_result

            except Exception as e:
                # Log error but continue with other entities
                print(f"Search error for {query.entity_label}: {e}")

            # Inter-entity delay
            await asyncio.sleep(strategy.inter_entity_delay_ms / 1000)

        # Run combined search after configured round
        if round_num == strategy.combined_after_round and strategy.include_combined:
            for query in combined_queries:
                try:
                    results = await search_executor.search(
                        query.query_string,
                        limit=strategy.batch_size * 2,  # Combined gets more
                    )

                    search_result = SearchResult(
                        query_id=query.id,
                        entity_label="_COMBINED_",
                        urls=[r.get("url", "") for r in results],
                        snippets={r.get("url", ""): r.get("snippet", "") for r in results},
                        engine="brute",
                    )
                    yield search_result

                except Exception as e:
                    print(f"Combined search error: {e}")

        # Inter-round delay (rate limiting)
        await asyncio.sleep(strategy.inter_round_delay_ms / 1000)


async def execute_bulk_search_sync(
    batch: BatchOperation,
    strategy: BulkSearchStrategy,
    search_executor: Any,
) -> BulkSearchResult:
    """
    Execute bulk search and return aggregated results (non-streaming).

    Args:
        batch: The batch operation
        strategy: Execution strategy
        search_executor: Search backend

    Returns:
        BulkSearchResult with aggregated data
    """
    result = BulkSearchResult(batch_operation_id=batch.id)
    seen_urls = set()

    async for search_result in execute_bulk_search(batch, strategy, search_executor):
        result.search_results.append(search_result)

        for url in search_result.urls:
            if url and url not in seen_urls:
                seen_urls.add(url)
                result.all_urls.append(url)

                # Track which entities this URL relates to
                if url not in result.url_to_entities:
                    result.url_to_entities[url] = []
                if search_result.entity_label != "_COMBINED_":
                    result.url_to_entities[url].append(search_result.entity_label)

        # Update per-entity counts
        if search_result.entity_label == "_COMBINED_":
            result.combined_results += len(search_result.urls)
        else:
            label = search_result.entity_label
            result.results_per_entity[label] = result.results_per_entity.get(label, 0) + len(search_result.urls)

    result.total_results = len(result.all_urls)
    return result


# =============================================================================
# URL TO NODE CONVERSION
# =============================================================================

def results_to_source_nodes(
    bulk_result: BulkSearchResult,
    batch: BatchOperation,
) -> List[Dict[str, Any]]:
    """
    Convert search results to source nodes for graph.

    Returns nodes with edges to originating entities.
    """
    nodes = []

    for url in bulk_result.all_urls:
        # Find snippet
        snippet = ""
        for sr in bulk_result.search_results:
            if url in sr.snippets:
                snippet = sr.snippets[url]
                break

        # Which entities does this URL mention?
        mentioned_entities = bulk_result.url_to_entities.get(url, [])

        node = {
            "id": f"src_{hash(url) % 100000000}",
            "type": "url",
            "class": "source",
            "label": url.split("/")[2] if "/" in url else url,  # Domain as label
            "properties": {
                "url": url,
                "snippet": snippet,
                "discovered_via": "brute",
                "batch_id": batch.id,
                "batch_tag": batch.selection.batch_tag,
                "mentioned_entities": mentioned_entities,
                "discovered_at": datetime.now().isoformat(),
            }
        }
        nodes.append(node)

    return nodes


def results_to_edges(
    bulk_result: BulkSearchResult,
    batch: BatchOperation,
    source_nodes: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Create edges from entity nodes to discovered source nodes.

    Edge type: mentioned_on (entity -> source where entity appears)
    """
    edges = []
    source_by_url = {n["properties"]["url"]: n["id"] for n in source_nodes}

    for url, entity_labels in bulk_result.url_to_entities.items():
        source_id = source_by_url.get(url)
        if not source_id:
            continue

        for label in entity_labels:
            # Find the entity node ID from the batch selection
            if label in batch.selection.node_labels:
                idx = batch.selection.node_labels.index(label)
                if idx < len(batch.selection.node_ids):
                    entity_id = batch.selection.node_ids[idx]

                    edges.append({
                        "source": entity_id,
                        "target": source_id,
                        "type": "mentioned_on",
                        "properties": {
                            "batch_id": batch.id,
                            "discovered_at": datetime.now().isoformat(),
                        }
                    })

    return edges


# =============================================================================
# API INTEGRATION - Connects to localhost:3001 backend
# =============================================================================

class BruteSearchAPIExecutor:
    """
    Search executor that calls the BruteSearch API.

    Connects bulk search to the actual backend API per SASTRE integration rules
    (MUST call existing APIs at http://localhost:3001, not reimplement).
    """

    def __init__(
        self,
        base_url: str = "http://localhost:3001",
        timeout_seconds: int = 60,
    ):
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    async def search(
        self,
        query: str,
        offset: int = 0,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Execute search via /api/search/stream/brute endpoint.

        Collects SSE stream results into a list.
        """
        import aiohttp
        import json

        params = {
            "query": query,
            "maxResults": str(limit),
            "timeoutSeconds": str(self.timeout_seconds),
            "skipPersist": "1",  # Bulk operations handle their own persistence
        }

        results = []

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/search/stream/brute",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.timeout_seconds + 30)
                ) as response:
                    async for line in response.content:
                        line_str = line.decode('utf-8').strip()
                        if line_str.startswith('data:'):
                            try:
                                data = json.loads(line_str[5:].strip())
                                if data.get("type") == "result":
                                    result = data.get("result", {})
                                    results.append({
                                        "url": result.get("url", ""),
                                        "title": result.get("title", ""),
                                        "snippet": result.get("snippet", ""),
                                        "engine": result.get("engine", ""),
                                    })
                                    # Stop if we hit limit
                                    if len(results) >= limit:
                                        break
                            except json.JSONDecodeError:
                                continue

        except Exception as e:
            print(f"BruteSearch API error: {e}")
            return []

        return results


def create_api_executor(
    base_url: str = "http://localhost:3001",
    timeout_seconds: int = 60,
) -> BruteSearchAPIExecutor:
    """
    Create a search executor connected to the backend API.

    Usage:
        executor = create_api_executor()
        async for result in execute_bulk_search(batch, strategy, executor):
            print(result)
    """
    return BruteSearchAPIExecutor(base_url=base_url, timeout_seconds=timeout_seconds)


async def execute_bulk_search_via_api(
    batch: BatchOperation,
    strategy: BulkSearchStrategy = None,
    base_url: str = "http://localhost:3001",
) -> BulkSearchResult:
    """
    Execute bulk search using the backend API.

    This is the production entry point that:
    1. Creates a search executor connected to localhost:3001
    2. Executes round-robin across all entities
    3. Returns aggregated results

    Args:
        batch: The batch operation to execute
        strategy: Optional strategy (uses defaults if not provided)
        base_url: Backend API URL

    Returns:
        BulkSearchResult with all results
    """
    if strategy is None:
        strategy = BulkSearchStrategy()

    executor = create_api_executor(base_url=base_url)
    return await execute_bulk_search_sync(batch, strategy, executor)
