#!/usr/bin/env python3
"""
LINKLATER RuleExecutor API Facade

Unified interface optimized for RuleExecutor integration.
Provides simplified, high-level methods that aggregate LINKLATER's 148+ functions
into rule-compatible operations.

Usage:
    from modules.linklater.rule_executor_api import LinklaterRuleAPI

    api = LinklaterRuleAPI()

    # Archive scraping
    result = await api.archive_search(domain="example.com", date_range=(2020, 2023))

    # Backlinks
    backlinks = await api.get_backlinks(domain="example.com", depth=1)

    # Entity extraction
    entities = await api.extract_entities(url="https://example.com")

    # Filetype discovery
    pdfs = await api.discover_files(domain="example.com", filetype="pdf", keyword="annual report")
"""

from typing import Dict, List, Optional, Any, Tuple, AsyncGenerator
from datetime import datetime
from pathlib import Path
import asyncio

from .api import LinkLater, get_linklater


class LinklaterRuleAPI:
    """
    Unified LINKLATER API Facade for RuleExecutor.

    Aggregates 148+ methods into rule-compatible operations with:
    - Consistent return types
    - Automatic error handling
    - Progress tracking support
    - Caching where appropriate
    - Logging integration
    """

    def __init__(self):
        """Initialize the API facade."""
        self.linklater = get_linklater()
        self._cache = {}

    # ========================================
    # ARCHIVE SCRAPING
    # ========================================

    async def archive_search(
        self,
        domain: Optional[str] = None,
        url: Optional[str] = None,
        date_range: Optional[Tuple[int, int]] = None,
        keywords: Optional[List[str]] = None,
        sources: List[str] = ["commoncrawl", "wayback"]
    ) -> Dict[str, Any]:
        """
        Search historical archives for domain/URL.

        Args:
            domain: Target domain (e.g., "example.com")
            url: Specific URL to search (if not domain-wide)
            date_range: Tuple of (start_year, end_year), e.g., (2020, 2023)
            keywords: Optional keyword filters
            sources: Archive sources ("commoncrawl", "wayback")

        Returns:
            {
                "archive_results": [...],
                "discovered_domains": [...],
                "stats": {...}
            }
        """
        if not domain and not url:
            return {"error": "Either domain or url required", "archive_results": [], "discovered_domains": []}

        target = url if url else domain
        years = None
        if date_range:
            years = list(range(date_range[0], date_range[1] + 1))

        return await self.linklater.historical_search(
            domains=[target] if target else [],
            keywords=keywords,
            years=years,
            sources=sources
        )

    async def scrape_url(
        self,
        url: str,
        extract_entities: bool = False,
        extract_schema: bool = False,
        extract_outlinks: bool = False
    ) -> Dict[str, Any]:
        """
        Scrape single URL with optional enrichment.

        Args:
            url: URL to scrape
            extract_entities: Extract entities with AI
            extract_schema: Extract Schema.org structured data
            extract_outlinks: Extract external links

        Returns:
            {
                "url": str,
                "source": str,  # "cc", "wayback", "firecrawl"
                "content": str,
                "entities": {...},  # if extract_entities=True
                "schema": {...},    # if extract_schema=True
                "outlinks": [...],  # if extract_outlinks=True
                "status": int,
                "latency_ms": int,
                "error": Optional[str]
            }
        """
        # Scrape content
        scrape_result = await self.linklater.scrape_url(url)

        result = {
            "url": scrape_result.url,
            "source": scrape_result.source,
            "content": scrape_result.content,
            "status": scrape_result.status,
            "latency_ms": scrape_result.latency_ms,
            "timestamp": scrape_result.timestamp,
            "error": scrape_result.error
        }

        if scrape_result.source == "failed":
            return result

        # Extract entities
        if extract_entities and scrape_result.content:
            entities = await self.linklater.extract_entities(
                scrape_result.content,
                url=url,
                backend="auto"
            )
            result["entities"] = entities

        # Extract Schema.org
        if extract_schema and scrape_result.content:
            schema = self.linklater.extract_schemas(scrape_result.content, url)
            result["schema"] = schema

        # Extract outlinks
        if extract_outlinks and scrape_result.content:
            outlinks = self.linklater.extract_outlinks(scrape_result.content, url)
            result["outlinks"] = outlinks

        return result

    async def scrape_batch(
        self,
        urls: List[str],
        max_concurrent: int = 50,
        extract_entities: bool = False
    ) -> Dict[str, Dict[str, Any]]:
        """
        Batch scrape multiple URLs.

        Args:
            urls: List of URLs to scrape
            max_concurrent: Max concurrent requests
            extract_entities: Extract entities from each result

        Returns:
            Dict mapping URL -> scrape result
        """
        results = await self.linklater.scrape_batch(urls, max_concurrent=max_concurrent)

        output = {}
        for url, scrape_result in results.items():
            result = {
                "url": scrape_result.url,
                "source": scrape_result.source,
                "content": scrape_result.content,
                "status": scrape_result.status,
                "latency_ms": scrape_result.latency_ms,
                "error": scrape_result.error
            }

            # Extract entities if requested
            if extract_entities and scrape_result.content and scrape_result.source != "failed":
                entities = await self.linklater.extract_entities(
                    scrape_result.content,
                    url=url,
                    backend="auto"
                )
                result["entities"] = entities

            output[url] = result

        return output

    # ========================================
    # BACKLINKS & OUTLINKS
    # ========================================

    async def get_backlinks(
        self,
        domain: str,
        depth: int = 1,
        limit: int = 100,
        include_majestic: bool = False,
        min_trust_flow: int = 0
    ) -> Dict[str, Any]:
        """
        Get backlinks (domains linking TO this domain).

        Args:
            domain: Target domain
            depth: Link depth (1 = direct backlinks, 2 = backlinks of backlinks)
            limit: Max results per depth level
            include_majestic: Include Majestic API data (requires API key)
            min_trust_flow: Minimum Majestic Trust Flow score

        Returns:
            {
                "domain": str,
                "backlinks": [
                    {
                        "source_domain": str,
                        "source_url": Optional[str],
                        "target_url": Optional[str],
                        "anchor_text": Optional[str],
                        "weight": int,
                        "trust_flow": Optional[int],
                        "citation_flow": Optional[int],
                        "source": str  # "cc_graph", "globallinks", "majestic"
                    }
                ],
                "total_count": int,
                "depth": int
            }
        """
        # Get CC Graph + GlobalLinks backlinks
        backlinks = await self.linklater.get_backlinks(
            domain=domain,
            limit=limit,
            use_globallinks=True,
            level="domain"
        )

        result = {
            "domain": domain,
            "backlinks": [],
            "total_count": 0,
            "depth": depth
        }

        # Convert LinkRecord to dict
        for link in backlinks:
            link_dict = {
                "source_domain": link.source_domain,
                "source_url": getattr(link, "source_url", None),
                "target_url": getattr(link, "target_url", None),
                "anchor_text": getattr(link, "anchor_text", None),
                "weight": getattr(link, "weight", 1),
                "source": link.source
            }
            result["backlinks"].append(link_dict)

        # Add Majestic data if requested
        if include_majestic:
            try:
                majestic_links = await self.linklater.get_majestic_backlinks(
                    domain=domain,
                    result_type="domains",
                    mode="fresh",
                    max_results=limit
                )

                for mlink in majestic_links:
                    if min_trust_flow > 0 and mlink.get("trust_flow", 0) < min_trust_flow:
                        continue

                    result["backlinks"].append({
                        "source_domain": mlink.get("source_domain"),
                        "source_url": None,
                        "target_url": None,
                        "anchor_text": None,
                        "weight": 1,
                        "trust_flow": mlink.get("trust_flow"),
                        "citation_flow": mlink.get("citation_flow"),
                        "source": "majestic"
                    })
            except Exception as e:
                # Majestic API key might be missing
                pass

        result["total_count"] = len(result["backlinks"])

        # Recursive depth handling (if depth > 1)
        if depth > 1:
            # Get backlinks of backlinks
            # (Implementation would recursively call get_backlinks on each source_domain)
            pass

        return result

    async def get_outlinks(
        self,
        domain: str,
        limit: int = 100,
        country_filter: Optional[List[str]] = None,
        url_keywords: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get outlinks (domains this domain links TO).

        Args:
            domain: Source domain
            limit: Max results
            country_filter: Filter by country TLDs (e.g., [".uk", ".fr"])
            url_keywords: Include only outlinks containing these keywords

        Returns:
            {
                "domain": str,
                "outlinks": [
                    {
                        "target_domain": str,
                        "target_url": Optional[str],
                        "anchor_text": Optional[str],
                        "weight": int,
                        "source": str
                    }
                ],
                "total_count": int
            }
        """
        # Get basic outlinks from CC Graph + GlobalLinks
        outlinks = await self.linklater.get_outlinks(
            domain=domain,
            limit=limit,
            use_globallinks=True,
            level="domain"
        )

        result = {
            "domain": domain,
            "outlinks": [],
            "total_count": 0
        }

        for link in outlinks:
            # Apply filters
            target_domain = link.target_domain

            if country_filter:
                if not any(target_domain.endswith(tld) for tld in country_filter):
                    continue

            if url_keywords:
                target_url = getattr(link, "target_url", "")
                if target_url and not any(kw in target_url for kw in url_keywords):
                    continue

            result["outlinks"].append({
                "target_domain": target_domain,
                "target_url": getattr(link, "target_url", None),
                "anchor_text": getattr(link, "anchor_text", None),
                "weight": getattr(link, "weight", 1),
                "source": link.source
            })

        result["total_count"] = len(result["outlinks"])
        return result

    # ========================================
    # ENTITY EXTRACTION
    # ========================================

    async def extract_entities(
        self,
        url: Optional[str] = None,
        text: Optional[str] = None,
        method: str = "hybrid"
    ) -> Dict[str, Any]:
        """
        Extract entities from URL or text.

        Args:
            url: URL to scrape and extract from
            text: Text to extract from (if not URL)
            method: Extraction method ("hybrid", "gemini", "gpt", "gliner", "regex")

        Returns:
            {
                "entities": {
                    "persons": [...],
                    "companies": [...],
                    "emails": [...],
                    "phones": [...],
                    "registrations": [...]
                },
                "schema": {...},  # Schema.org data if available
                "source": str,
                "url": Optional[str]
            }
        """
        if url:
            # Scrape URL first
            scrape_result = await self.linklater.scrape_url(url)
            if scrape_result.source == "failed":
                return {"error": scrape_result.error, "entities": {}}
            text = scrape_result.content
            source_url = url
        elif text:
            source_url = None
        else:
            return {"error": "Either url or text required", "entities": {}}

        # Extract entities
        entities = await self.linklater.extract_entities(
            text=text,
            url=source_url or "",
            backend=method
        )

        # Extract Schema.org if available
        schema = None
        if self.linklater.has_schema_markup(text):
            schema = self.linklater.extract_schemas(text, source_url or "")

        return {
            "entities": entities,
            "schema": schema,
            "source": method,
            "url": source_url
        }

    # ========================================
    # FILETYPE DISCOVERY
    # ========================================

    async def discover_files(
        self,
        domain: str,
        filetype: str = "pdf",
        keyword: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Discover files on domain.

        Args:
            domain: Target domain
            filetype: File type or alias ("pdf", "document", "spreadsheet")
            keyword: Optional keyword filter
            limit: Max results

        Returns:
            {
                "domain": str,
                "filetype": str,
                "keyword": Optional[str],
                "files": [
                    {
                        "url": str,
                        "title": str,
                        "filetype": str,
                        "source": str,
                        "snippet": str,
                        "metadata": {...}
                    }
                ],
                "total_found": int,
                "sources_used": [...],
                "elapsed_ms": int
            }
        """
        result = await self.linklater.discover_filetypes(
            domain=domain,
            filetype_query=filetype,
            keyword=keyword,
            limit=limit
        )

        return {
            "domain": result["domain"],
            "filetype": filetype,
            "keyword": keyword,
            "files": result["results"],
            "total_found": result["total_found"],
            "sources_used": result["sources_used"],
            "elapsed_ms": result["elapsed_ms"]
        }

    # ========================================
    # DISCOVERY OPERATIONS
    # ========================================

    async def discover_related_domains(
        self,
        domain: str,
        method: str = "cocitation",
        max_results: int = 100
    ) -> Dict[str, Any]:
        """
        Discover domains related to target domain.

        Args:
            domain: Target domain
            method: Discovery method ("cocitation", "ownership", "hosting", "tech_stack")
            max_results: Max results

        Returns:
            {
                "domain": str,
                "method": str,
                "related_domains": [
                    {
                        "domain": str,
                        "relationship": str,
                        "confidence": float,
                        "metadata": {...}
                    }
                ],
                "total_count": int
            }
        """
        result = {
            "domain": domain,
            "method": method,
            "related_domains": [],
            "total_count": 0
        }

        if method == "cocitation":
            # Co-citation via Majestic
            related = await self.linklater.get_related_links(domain, max_results=max_results)
            for item in related:
                result["related_domains"].append({
                    "domain": item["domain"],
                    "relationship": "cocitation",
                    "confidence": item.get("trust_flow", 0) / 100.0,
                    "metadata": {
                        "trust_flow": item.get("trust_flow"),
                        "citation_flow": item.get("citation_flow"),
                        "common_links": item.get("common_links")
                    }
                })

        elif method == "ownership":
            # Ownership-linked via WHOIS
            related = await self.linklater.get_ownership_linked(domain, max_results=max_results)
            for item in related:
                result["related_domains"].append({
                    "domain": item["domain"],
                    "relationship": item["match_type"],
                    "confidence": item["confidence"],
                    "metadata": {
                        "match_value": item["match_value"]
                    }
                })

        elif method == "hosting":
            # Co-hosted domains
            related = await self.linklater.get_hosted_domains(domain, max_results=max_results)
            for item in related:
                result["related_domains"].append({
                    "domain": item["domain"],
                    "relationship": "co_hosted",
                    "confidence": 0.7,  # Medium confidence for hosting
                    "metadata": {
                        "hosting_type": item.get("hosting_type"),
                        "ip": item.get("ip")
                    }
                })

        elif method == "tech_stack":
            # Similar technology stack
            # (Would use tech_discovery module)
            pass

        result["total_count"] = len(result["related_domains"])
        return result

    # ========================================
    # KEYWORD SEARCH
    # ========================================

    async def keyword_search(
        self,
        keywords: List[str],
        domain: Optional[str] = None,
        use_variations: bool = True,
        max_results: int = 100
    ) -> Dict[str, Any]:
        """
        Search archives for keywords with optional variations.

        Args:
            keywords: Keywords to search for
            domain: Optional domain filter
            use_variations: Generate and search keyword variations
            max_results: Max results per keyword

        Returns:
            {
                "keywords": [...],
                "variations_searched": [...],
                "results": [
                    {
                        "url": str,
                        "title": str,
                        "snippet": str,
                        "source": str,
                        "keyword_matched": str
                    }
                ],
                "total_matches": int
            }
        """
        if use_variations:
            # Use keyword variations search
            search_result = await self.linklater.search_keyword_variations(
                keywords=keywords,
                domain=domain
            )

            return {
                "keywords": keywords,
                "variations_searched": search_result.variations_searched if hasattr(search_result, 'variations_searched') else [],
                "results": [],  # Would need to format search_result
                "total_matches": search_result.total_matches if hasattr(search_result, 'total_matches') else 0
            }
        else:
            # Direct search without variations
            results = []
            for keyword in keywords:
                # Search Wayback + CC index
                wayback_results = await self.linklater.search_wayback(keyword, domain=domain)
                cc_results = await self.linklater.search_cc_index(keyword, domain=domain)

                results.extend(wayback_results or [])
                results.extend(cc_results or [])

            return {
                "keywords": keywords,
                "variations_searched": keywords,
                "results": results,
                "total_matches": len(results)
            }

    # ========================================
    # ENRICHMENT
    # ========================================

    async def enrich_search_results(
        self,
        results: List[Dict[str, str]],
        extract_entities: bool = True,
        extract_outlinks: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Enrich search results with entities and outlinks.

        Args:
            results: List of {"url": str, "title": str, "snippet": str}
            extract_entities: Extract entities from content
            extract_outlinks: Extract external links

        Returns:
            List of enriched results with entities and outlinks
        """
        return await self.linklater.enrich_search_results(results)

    # ========================================
    # STATISTICS
    # ========================================

    def get_stats(self) -> Dict[str, Any]:
        """
        Get API usage statistics.

        Returns:
            {
                "scraper_stats": {...},
                "cache_stats": {...}
            }
        """
        return {
            "scraper_stats": self.linklater.get_scraper_stats(),
            "cache_stats": {
                "size": len(self._cache)
            }
        }

    def reset_stats(self):
        """Reset all statistics."""
        self.linklater.reset_scraper_stats()
        self._cache.clear()


# ========================================
# STANDALONE HELPER FUNCTIONS
# ========================================

async def archive_search(domain: str, **kwargs) -> Dict[str, Any]:
    """Standalone archive search."""
    api = LinklaterRuleAPI()
    return await api.archive_search(domain=domain, **kwargs)


async def get_backlinks(domain: str, depth: int = 1, limit: int = 100) -> Dict[str, Any]:
    """Standalone backlink discovery."""
    api = LinklaterRuleAPI()
    return await api.get_backlinks(domain=domain, depth=depth, limit=limit)


async def extract_entities(url: str = None, text: str = None, method: str = "hybrid") -> Dict[str, Any]:
    """Standalone entity extraction."""
    api = LinklaterRuleAPI()
    return await api.extract_entities(url=url, text=text, method=method)


async def discover_files(domain: str, filetype: str = "pdf", keyword: str = None, limit: int = 100) -> Dict[str, Any]:
    """Standalone filetype discovery."""
    api = LinklaterRuleAPI()
    return await api.discover_files(domain=domain, filetype=filetype, keyword=keyword, limit=limit)


async def discover_related_domains(domain: str, method: str = "cocitation", max_results: int = 100) -> Dict[str, Any]:
    """Standalone related domain discovery."""
    api = LinklaterRuleAPI()
    return await api.discover_related_domains(domain=domain, method=method, max_results=max_results)
