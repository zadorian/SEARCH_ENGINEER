"""
CRSearcher - Corporate Registry Searcher

Searches corporate registries by jurisdiction using templates from sources.json.

Usage:
    from TORPEDO.cr_searcher import CRSearcher

    cr = CRSearcher()
    await cr.load_sources()

    # Search UK corporate registries
    results = await cr.search("Acme Ltd", "UK")

    # Get available jurisdictions
    jurs = cr.get_jurisdictions()
"""

import json
import logging
import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional
from urllib.parse import quote_plus

from .base_searcher import BaseSearcher

logger = logging.getLogger("Torpedo.CRSearcher")

from ..paths import corporate_registries_sources_path as _default_cr_sources_path
from ..paths import io_matrix_dir as _io_matrix_dir

DEFAULT_CR_SOURCES_PATH = _default_cr_sources_path()
DEFAULT_SOURCES_JSON_PATH = _io_matrix_dir() / "sources.json"  # Fallback (large)


class CRSearcher(BaseSearcher):
    """Corporate Registry Searcher - searches registries by jurisdiction."""

    def __init__(self):
        super().__init__()
        self.sources: Dict[str, List[Dict[str, Any]]] = {}  # jurisdiction -> sources
        self.loaded = False

    async def load_sources(self, sources_path: Optional[str | Path] = None) -> int:
        """
        Load corporate registry sources from sources/corporate_registries.json.

        Falls back to sources.json if category file doesn't exist.

        Returns: Number of sources loaded.
        """
        if self.loaded:
            return sum(len(s) for s in self.sources.values())

        try:
            candidate = Path(sources_path) if sources_path else DEFAULT_CR_SOURCES_PATH
            if candidate.exists():
                source_file = candidate
                logger.info(f"Loading from {source_file}")
            else:
                source_file = DEFAULT_SOURCES_JSON_PATH
                logger.info(f"Fallback to {source_file}")

            with open(source_file) as f:
                data = json.load(f)

            # Format A: jurisdiction-keyed dict of lists (preferred)
            if isinstance(data, dict) and data and all(isinstance(v, list) for v in data.values()):
                for jur_key, sources_list in data.items():
                    if not isinstance(sources_list, list):
                        continue
                    jur_key = jur_key.upper()
                    if jur_key == "GB":
                        jur_key = "UK"

                    for source in sources_list:
                        if not isinstance(source, dict):
                            continue

                        template = source.get("search_template") or source.get("search_url")
                        if not template or "{q}" not in template:
                            continue

                        jur = (source.get("jurisdiction") or jur_key or "GLOBAL").upper()
                        if jur == "GB":
                            jur = "UK"

                        self.sources.setdefault(jur, []).append({
                            "domain": source.get("domain", ""),
                            "name": source.get("name", source.get("domain", "")),
                            "search_template": template,
                            "friction": source.get("friction", source.get("access", "public")),
                            "type": source.get("type", source.get("source_type", "corporate_registry")),
                            "scrape_method": source.get("scrape_method"),
                            "needs_js": bool(source.get("needs_js", False)),
                            "source_id": source.get("id") or source.get("source_id"),
                        })

                self.loaded = True
                total = sum(len(s) for s in self.sources.values())
                logger.info(f"Loaded {total} CR sources across {len(self.sources)} jurisdictions")
                return total

            # Format B: wrapper dict with "sources"
            sources_list = data.get("sources", [])

            # Handle both list (new) and dict (legacy) formats
            if isinstance(sources_list, list):
                # New format: sources/corporate_registries.json has sources as list
                for source in sources_list:
                    template = source.get("search_template") or source.get("search_url")
                    if not template or "{q}" not in template:
                        continue

                    jur = source.get("jurisdiction_primary") or source.get("jurisdiction", "GLOBAL")
                    if jur == "GB":
                        jur = "UK"

                    if jur not in self.sources:
                        self.sources[jur] = []

                    self.sources[jur].append({
                        "domain": source.get("domain", ""),
                        "name": source.get("name", source.get("domain", "")),
                        "search_template": template,
                        "friction": source.get("friction", "public"),
                        "type": source.get("source_type", "corporate_registry"),
                        "scrape_method": source.get("scrape_method"),
                        "needs_js": source.get("needs_js", False)
                    })
            else:
                # Legacy format: sources.json has sources as dict keyed by domain
                for domain, source in sources_list.items():
                    cat = source.get("category", "").lower()
                    typ = source.get("type", "").lower()
                    section = source.get("section", "").lower()

                    is_cr = (
                        "cr" in cat or
                        "registry" in typ or
                        "corporate" in typ or
                        section == "cr"
                    )

                    if not is_cr:
                        continue

                    template = source.get("search_template") or source.get("search_url")
                    if not template or "{q}" not in template:
                        continue

                    jur = source.get("jurisdiction", "GLOBAL")
                    if jur == "GB":
                        jur = "UK"

                    if jur not in self.sources:
                        self.sources[jur] = []

                    self.sources[jur].append({
                        "domain": domain,
                        "name": source.get("name", domain),
                        "search_template": template,
                        "friction": source.get("friction", "public"),
                        "type": source.get("type", "corporate_registry"),
                        "scrape_method": source.get("scrape_method"),
                        "needs_js": source.get("needs_js", False)
                    })

            self.loaded = True
            total = sum(len(s) for s in self.sources.values())
            logger.info(f"Loaded {total} CR sources across {len(self.sources)} jurisdictions")
            return total

        except Exception as e:
            logger.error(f"Failed to load sources: {e}")
            return 0

    def get_jurisdictions(self) -> List[str]:
        """Get list of available jurisdictions."""
        return sorted(self.sources.keys())

    def get_sources_for_jurisdiction(self, jurisdiction: str) -> List[Dict[str, Any]]:
        """Get all CR sources for a jurisdiction."""
        # Normalize UK/GB
        if jurisdiction == "GB":
            jurisdiction = "UK"
        return self.sources.get(jurisdiction.upper(), [])

    async def search(
        self,
        query: str,
        jurisdiction: str,
        max_sources: int = 5,
        use_brightdata: bool = False,
        limit: Optional[int] = None  # Alias for max_sources (CLI compatibility)
    ) -> Dict[str, Any]:
        """
        Search corporate registries for a jurisdiction.

        Args:
            query: Company name to search
            jurisdiction: 2-letter jurisdiction code (e.g., "UK", "DE")
            max_sources: Maximum number of sources to query
            use_brightdata: Use BrightData proxy for blocked sites

        Returns:
            {
                "jurisdiction": str,
                "query": str,
                "sources_queried": int,
                "results": [
                    {
                        "source": str,
                        "domain": str,
                        "url": str,
                        "success": bool,
                        "html": str | None,
                        "error": str | None
                    }
                ],
                "errors": []
            }
        """
        if limit is not None:
            max_sources = limit

        if not self.loaded:
            await self.load_sources()

        # Normalize UK/GB
        if jurisdiction == "GB":
            jurisdiction = "UK"

        sources = self.get_sources_for_jurisdiction(jurisdiction)

        if not sources:
            return {
                "jurisdiction": jurisdiction,
                "query": query,
                "sources_queried": 0,
                "results": [],
                "errors": [f"No CR sources found for jurisdiction: {jurisdiction}"]
            }

        # Limit sources
        sources_to_query = sources[:max_sources]

        # Build search URLs
        results = []
        errors = []

        # Execute searches in parallel
        async def search_source(source: Dict[str, Any]) -> Dict[str, Any]:
            template = source["search_template"]
            url = template.replace("{q}", quote_plus(query))

            # Use pre-classified scrape_method if available
            scrape_method = source.get("scrape_method")
            response = await self.fetch_url(
                url,
                scrape_method=scrape_method,
                use_brightdata=use_brightdata
            )

            return {
                "source": source["name"],
                "domain": source["domain"],
                "url": url,
                "success": response["success"],
                "html": response["html"],
                "json": response.get("json"),
                "status_code": response["status_code"],
                "method_used": response.get("method_used"),
                "error": response["error"]
            }

        tasks = [search_source(s) for s in sources_to_query]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        final_results = []
        for r in results:
            if isinstance(r, Exception):
                errors.append(str(r))
            else:
                final_results.append(r)

        return {
            "jurisdiction": jurisdiction,
            "query": query,
            "sources_queried": len(sources_to_query),
            "results": final_results,
            "errors": errors
        }

    async def search_all(
        self,
        query: str,
        jurisdictions: List[str],
        max_sources_per_jur: int = 3
    ) -> Dict[str, Any]:
        """
        Search across multiple jurisdictions.

        Returns combined results from all jurisdictions.
        """
        if not self.loaded:
            await self.load_sources()

        all_results = {}
        all_errors = []

        for jur in jurisdictions:
            result = await self.search(query, jur, max_sources=max_sources_per_jur)
            all_results[jur] = result["results"]
            all_errors.extend(result["errors"])

        return {
            "query": query,
            "jurisdictions": jurisdictions,
            "results": all_results,
            "errors": all_errors
        }
