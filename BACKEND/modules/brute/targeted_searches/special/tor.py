#!/usr/bin/env python3
"""
Tor/Onion search type: searches across Tor hidden services
Handles the tor: operator for deep web searches

Features:
- Search URL generation for 9+ onion search engines
- Ahmia API integration (clearnet, no Tor required)
- Local Elasticsearch index search (crawled onion pages)
- Unified search combining all sources
"""

from typing import List, Dict, Optional, Any
from urllib.parse import quote
import logging
import os
import hashlib
import aiohttp
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

# Elasticsearch settings
ES_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
ES_ONION_INDEX = os.getenv("ES_ONION_INDEX", "onion-pages")

# Ahmia API (clearnet - no Tor required)
AHMIA_API_URL = "https://ahmia.fi/search/"
AHMIA_SEARCH_URL = "https://ahmia.fi/search/?q="

# Tor search engines with their query patterns
TOR_SEARCH_ENGINES = [
    {
        "name": "Tor66",
        "url_template": "http://www.tor66sewebgixwhcqfnp5inzp5x5uohhdy3kvtnyfxc2e5mxiuh34iid.onion/search?q={query}",
        "description": "Tor66 Fresh Onions search engine"
    },
    {
        "name": "Ahmia",
        "url_template": "http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion/search/?q={query}",
        "description": "Ahmia Tor search engine"
    },
    {
        "name": "GDark",
        "url_template": "http://zb2jtkhnbvhkya3d46twv3g7lkobi4s62tjffqmafjibixk6pmq75did.onion/gdark/search.php?query={query}&search=1",
        "description": "GDark search engine"
    },
    {
        "name": "Candle",
        "url_template": "http://u5lyidiw4lpkonoctpqzxgyk6xop7w7w3oho4dzzsi272rwnjhyx7ayd.onion/?s={query}",
        "description": "Candle dark web search"
    },
    {
        "name": "DuckDuckGo Onion",
        "url_template": "http://3bbad7fauom4d6sgppalyqddsqbf5u5p56b5k5uk2zxsy3d6ey2jobad.onion/search?q={query}",
        "description": "DuckDuckGo's onion service"
    },
    {
        "name": "Phobos",
        "url_template": "http://no6m4wzdexe3auiupv2zwif7rm6qwxcyhslkcnzisxgeiw6pvjsgafad.onion/search.php?term={query}",
        "description": "Phobos search engine"
    },
    {
        "name": "Excavator",
        "url_template": "http://searchgf7gdtauh7bhnbyed4ivxqmuoat3nm6zfrg3ymkq6mtnpye3ad.onion/search?q={query}",
        "description": "Excavator dark web search"
    },
    {
        "name": "Space",
        "url_template": "http://5qqrlc7hw3tsgokkqifb33p3mrlpnleka2bjg7n46vih2synghb6ycid.onion/index.php?a=search&q={query}",
        "description": "Space search engine"
    },
    {
        "name": "Fresh Onions",
        "url_template": "http://freshonifyfe4rmuh6qwpsexfhdrww7wnt5qmkoertwxmcuvm4woo4ad.onion/?query={query}",
        "description": "Fresh Onions directory search"
    }
]

def search(query: str) -> List[Dict]:
    """
    Search across Tor hidden services using multiple onion search engines
    This handles the tor: operator
    
    Args:
        query: The search query (can include tor: prefix)
    
    Returns:
        List of search result URLs for Tor search engines
    """
    # Clean the query - remove tor: prefix if present
    if query.lower().startswith('tor:'):
        query = query[4:].strip()
    
    results = []
    
    # Generate search URLs for all Tor search engines
    for engine in TOR_SEARCH_ENGINES:
        # URL encode the query for safety
        encoded_query = quote(query)
        
        # Build the search URL
        search_url = engine["url_template"].format(query=encoded_query)
        
        results.append({
            "title": f"{engine['name']}: {query}",
            "url": search_url,
            "search_engine": engine['name'].lower().replace(' ', '_'),
            "engine_badge": engine['name'][:2].upper(),
            "description": engine['description'],
            "is_onion": True,
            "requires_tor": True,
            "category": "tor",
            "url_subtype": "tor"
        })
    
    # Add a notice about Tor requirement
    results.insert(0, {
        "title": "⚠️ Tor Browser Required",
        "url": "tor://launch",
        "description": "These links require Tor Browser or Chrome with Tor proxy. Use 'Tor Chrome Safe' launcher on Desktop.",
        "is_notice": True
    })
    
    return results

def search_with_category(query: str, category: Optional[str] = None) -> List[Dict]:
    """
    Search Tor with optional category focus
    
    Categories could include:
    - markets (darknet markets)
    - forums (discussion boards)  
    - wikis (hidden wikis and directories)
    - general (all categories)
    
    Args:
        query: Search query
        category: Optional category filter
    
    Returns:
        List of categorized Tor search results
    """
    base_results = search(query)
    
    # In the future, we could filter engines by category
    # For now, return all results
    return base_results

def get_popular_onion_sites() -> List[Dict]:
    """
    Return a list of popular/useful onion sites for reference
    """
    return [
        {
            "title": "The Hidden Wiki",
            "url": "http://wikiv3zz2aqfqkgyy7theqvjfviihshydw6vd52i6rznuaddylle6id.onion",
            "description": "Directory of onion sites",
            "category": "directory"
        },
        {
            "title": "ProtonMail (Onion)",
            "url": "https://protonmailrmez3lotccipshtkleegetolb73fuirgj7r4o4vfu7ozyd.onion",
            "description": "Secure email service",
            "category": "email"
        },
        {
            "title": "DuckDuckGo (Onion)",
            "url": "https://duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion",
            "description": "Privacy-focused search engine",
            "category": "search"
        },
        {
            "title": "BBC News (Onion)",
            "url": "https://www.bbcnewsd73hkzno2ini43t4gblxvycyac5aw4gnv7t2rccijh7745uqd.onion",
            "description": "BBC News Tor mirror",
            "category": "news"
        },
        {
            "title": "Facebook (Onion)",
            "url": "https://www.facebookcorewwwi.onion",
            "description": "Facebook's official onion site",
            "category": "social"
        }
    ]


# =============================================================================
# AHMIA API CLIENT (clearnet - no Tor required)
# =============================================================================

async def search_ahmia_api(query: str, max_results: int = 50) -> List[Dict[str, Any]]:
    """
    Search Ahmia's index via their clearnet API.
    No Tor required - queries their public search endpoint.

    Note: Ahmia filters illegal content by design.

    Args:
        query: Search query
        max_results: Maximum results to return

    Returns:
        List of search results from Ahmia
    """
    results = []

    try:
        # Ahmia uses standard HTML search, we scrape the results
        # Their API endpoint returns HTML, not JSON
        async with aiohttp.ClientSession() as session:
            url = f"{AHMIA_SEARCH_URL}{quote(query)}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0",
                "Accept": "text/html,application/xhtml+xml",
            }

            async with session.get(url, headers=headers, timeout=30) as resp:
                if resp.status != 200:
                    logger.warning(f"Ahmia API returned status {resp.status}")
                    return results

                html = await resp.text()

                # Parse results from HTML (Ahmia uses specific structure)
                # Results are in <li class="result"> elements
                import re

                # Extract result blocks
                result_pattern = re.compile(
                    r'<li[^>]*class="[^"]*result[^"]*"[^>]*>.*?'
                    r'<a[^>]*href="([^"]+)"[^>]*>([^<]*)</a>.*?'
                    r'<p[^>]*>([^<]*)</p>',
                    re.DOTALL | re.IGNORECASE
                )

                # Simpler pattern for onion links
                onion_pattern = re.compile(
                    r'href="(https?://[a-z2-7]{56}\.onion[^"]*)"[^>]*>([^<]+)</a>',
                    re.IGNORECASE
                )

                matches = onion_pattern.findall(html)

                for url_match, title in matches[:max_results]:
                    results.append({
                        "title": title.strip() or "Untitled",
                        "url": url_match,
                        "snippet": f"Found via Ahmia search for: {query}",
                        "source": "ahmia_api",
                        "engine_badge": "AH",
                        "is_onion": True,
                        "requires_tor": True,
                        "category": "tor",
                        "fetched_at": datetime.utcnow().isoformat(),
                    })

    except asyncio.TimeoutError:
        logger.warning("Ahmia API request timed out")
    except Exception as e:
        logger.error(f"Ahmia API error: {e}")

    return results


def search_ahmia_api_sync(query: str, max_results: int = 50) -> List[Dict[str, Any]]:
    """Synchronous wrapper for search_ahmia_api."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're in an async context, use run_coroutine_threadsafe
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, search_ahmia_api(query, max_results))
                return future.result(timeout=60)
        else:
            return loop.run_until_complete(search_ahmia_api(query, max_results))
    except Exception as e:
        logger.error(f"Ahmia sync search error: {e}")
        return []


# =============================================================================
# LOCAL ELASTICSEARCH INDEX SEARCH (crawled onion pages)
# =============================================================================

async def search_local_onion_index(
    query: str,
    max_results: int = 50,
    index: str = None,
    source_filter: Optional[str] = None,  # Filter by source: "local_crawler", "ahmia", etc.
) -> List[Dict[str, Any]]:
    """
    Search locally crawled onion pages in Elasticsearch (unified schema).

    Args:
        query: Search query
        max_results: Maximum results
        index: ES index name (default: onion-pages)
        source_filter: Optional filter by source field

    Returns:
        List of matching crawled pages
    """
    results = []
    target_index = index or ES_ONION_INDEX

    try:
        # Build query with optional source filter
        must_clauses = [
            {
                "multi_match": {
                    "query": query,
                    "fields": [
                        "title^3",
                        "h1^2",
                        "meta^1.5",
                        "content",
                        "url^2",
                        "domain"
                    ],
                    "type": "best_fields",
                    "fuzziness": "AUTO"
                }
            }
        ]

        if source_filter:
            must_clauses.append({"term": {"source": source_filter}})

        es_query = {
            "query": {
                "bool": {
                    "must": must_clauses
                }
            },
            "highlight": {
                "fields": {
                    "content": {"fragment_size": 200, "number_of_fragments": 2},
                    "title": {},
                    "meta": {"fragment_size": 150}
                },
                "pre_tags": ["<mark>"],
                "post_tags": ["</mark>"]
            },
            "size": max_results,
            "_source": [
                "url", "domain", "title", "h1", "meta", "content",
                "fetched_at", "updated_on", "content_length", "source",
                "depth", "links_found", "tags", "flagged"
            ]
        }

        async with aiohttp.ClientSession() as session:
            url = f"{ES_URL}/{target_index}/_search"
            async with session.post(
                url,
                json=es_query,
                headers={"Content-Type": "application/json"},
                timeout=30
            ) as resp:
                if resp.status != 200:
                    logger.debug(f"ES search returned {resp.status} - index may not exist")
                    return results

                data = await resp.json()

                for hit in data.get("hits", {}).get("hits", []):
                    source = hit.get("_source", {})
                    highlight = hit.get("highlight", {})

                    # Get snippet from highlight or content/meta
                    snippet = ""
                    if "content" in highlight:
                        snippet = " ... ".join(highlight["content"])
                    elif "meta" in highlight:
                        snippet = highlight["meta"][0]
                    elif source.get("meta"):
                        snippet = source["meta"][:200]
                    elif source.get("content"):
                        snippet = source["content"][:200] + "..."

                    # Determine badge based on source
                    data_source = source.get("source", "unknown")
                    badge_map = {
                        "local_crawler": "LC",
                        "ahmia": "AH",
                        "ahmia_import": "AI",
                        "ahmia_reindex": "AR",
                        "manual": "MN",
                    }
                    badge = badge_map.get(data_source, "ON")

                    results.append({
                        "title": source.get("title") or source.get("h1") or source.get("domain") or "Untitled",
                        "url": source.get("url"),
                        "snippet": snippet,
                        "domain": source.get("domain"),
                        "source": f"local_onion_index:{data_source}",
                        "engine_badge": badge,
                        "is_onion": True,
                        "requires_tor": True,
                        "category": "tor",
                        "fetched_at": source.get("fetched_at") or source.get("updated_on"),
                        "score": hit.get("_score", 0),
                        # Extra unified fields
                        "depth": source.get("depth"),
                        "links_found": source.get("links_found"),
                        "tags": source.get("tags", []),
                        "flagged": source.get("flagged", False),
                    })

    except Exception as e:
        logger.debug(f"Local onion index search error: {e}")

    return results


def search_local_onion_index_sync(
    query: str,
    max_results: int = 50,
    index: str = None
) -> List[Dict[str, Any]]:
    """Synchronous wrapper for search_local_onion_index."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    search_local_onion_index(query, max_results, index)
                )
                return future.result(timeout=60)
        else:
            return loop.run_until_complete(
                search_local_onion_index(query, max_results, index)
            )
    except Exception as e:
        logger.error(f"Local onion index sync search error: {e}")
        return []


# =============================================================================
# UNIFIED SEARCH (combines all sources)
# =============================================================================

async def search_unified(
    query: str,
    max_results: int = 100,
    include_portals: bool = True,
    include_ahmia: bool = True,
    include_local: bool = True,
) -> Dict[str, Any]:
    """
    Unified Tor search combining multiple sources:
    1. Portal URLs (search engine links)
    2. Ahmia API results (actual indexed pages)
    3. Local ES index (your crawled pages)

    Args:
        query: Search query
        max_results: Max results per source
        include_portals: Include search engine portal URLs
        include_ahmia: Query Ahmia's API
        include_local: Search local ES index

    Returns:
        Dict with results grouped by source and metadata
    """
    results = {
        "query": query,
        "sources": {},
        "all_results": [],
        "total": 0,
        "searched_at": datetime.utcnow().isoformat(),
    }

    # Clean query
    if query.lower().startswith("tor:"):
        query = query[4:].strip()

    tasks = []

    # Ahmia API
    if include_ahmia:
        tasks.append(("ahmia", search_ahmia_api(query, max_results)))

    # Local ES index
    if include_local:
        tasks.append(("local", search_local_onion_index(query, max_results)))

    # Run async searches in parallel
    if tasks:
        gathered = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
        for i, (source_name, _) in enumerate(tasks):
            result = gathered[i]
            if isinstance(result, Exception):
                logger.error(f"Search source {source_name} failed: {result}")
                results["sources"][source_name] = []
            else:
                results["sources"][source_name] = result
                results["all_results"].extend(result)

    # Portal URLs (synchronous, just URL generation)
    if include_portals:
        portal_results = search(query)
        # Remove the notice item
        portal_results = [r for r in portal_results if not r.get("is_notice")]
        results["sources"]["portals"] = portal_results
        results["all_results"].extend(portal_results)

    # Deduplicate by URL
    seen_urls = set()
    unique_results = []
    for item in results["all_results"]:
        url = item.get("url", "").lower()
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_results.append(item)

    results["all_results"] = unique_results
    results["total"] = len(unique_results)

    return results


def search_unified_sync(
    query: str,
    max_results: int = 100,
    include_portals: bool = True,
    include_ahmia: bool = True,
    include_local: bool = True,
) -> Dict[str, Any]:
    """Synchronous wrapper for search_unified."""
    try:
        return asyncio.run(search_unified(
            query, max_results, include_portals, include_ahmia, include_local
        ))
    except Exception as e:
        logger.error(f"Unified search error: {e}")
        return {"query": query, "sources": {}, "all_results": [], "total": 0, "error": str(e)}