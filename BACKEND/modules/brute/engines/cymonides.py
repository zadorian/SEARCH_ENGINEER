"""
CYMONIDES Engine for Brute Search
==================================
Integrates CYMONIDES Elasticsearch unified search into brute's multi-engine system.

CYMONIDES searches 570M+ domains across local Elasticsearch indices.
This is LOCAL (instant) - no API calls, just ES queries.

Supports all operators from operators.json with engine: "cymonides":
- Definitional: "[German car manufacturer]"
- Location filters: fr! (shorthand for dom OR lang OR geo), dom{fr}!, lang{fr}!, geo{fr}!
- Rank: rank(<1000)
- Authority: authority(high)
- PDF corpus: pdf!
- Entity extraction: @ent? @p? @c?
"""

import logging
import time
from typing import Dict, List, Any, Iterator
from urllib.parse import urlparse

logger = logging.getLogger("cymonides_engine")


class CymonidesEngine:
    """
    Brute search engine adapter for CYMONIDES unified search.

    Code: CY
    Speed: FAST (local Elasticsearch)
    """

    code = "CY"
    name = "CYMONIDES"

    def __init__(self):
        """Initialize CYMONIDES search connection."""
        self.search_client = None
        self._init_client()

    def _init_client(self):
        """Lazy init of CYMONIDES search client."""
        try:
            from modules.CYMONIDES.cymonides_unified import CymonidesUnifiedSearch
            self.search_client = CymonidesUnifiedSearch()
            logger.info("CYMONIDES engine initialized")
        except ImportError as e:
            logger.warning(f"CYMONIDES import failed: {e}")
        except Exception as e:
            logger.error(f"CYMONIDES init error: {e}")

    def is_available(self) -> bool:
        """Check if CYMONIDES is ready."""
        return self.search_client is not None

    def search(
        self,
        query: str,
        max_results: int = 100,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Execute CYMONIDES search and return brute-compatible results.

        Args:
            query: Search query (supports all CYMONIDES operators)
            max_results: Maximum results to return

        Returns:
            List of results with url, title, snippet, source
        """
        if not self.search_client:
            self._init_client()
            if not self.search_client:
                logger.warning("CYMONIDES not available")
                return []

        start_time = time.time()

        try:
            # Execute CYMONIDES unified search
            result = self.search_client.search(query, limit=max_results)

            # Convert to brute format
            brute_results = []
            for r in result.results:
                brute_results.append(self._to_brute_format(r, query))

            elapsed = (time.time() - start_time) * 1000
            logger.info(f"[CY] Query '{query[:50]}...' returned {len(brute_results)} results in {elapsed:.0f}ms")

            return brute_results

        except Exception as e:
            logger.error(f"CYMONIDES search error: {e}")
            return []

    def search_stream(
        self,
        query: str,
        max_results: int = 100,
        **kwargs
    ) -> Iterator[Dict[str, Any]]:
        """
        Streaming search - yields results one by one.

        CYMONIDES is local ES so this is fast, but we still yield
        incrementally for compatibility with brute's streaming architecture.
        """
        results = self.search(query, max_results, **kwargs)
        for result in results:
            yield result

    def _to_brute_format(self, cy_result: Dict, query: str) -> Dict[str, Any]:
        """
        Convert CYMONIDES result to brute standard format for GRID display.

        The Grid expects:
        - url: URL for primary display
        - title: Title text
        - snippet/description: Middle cell content (searchable text)
        - metadata: Rich metadata for display (categories, entities, rank, etc.)
        - engines: Source codes for display

        CYMONIDES results come from multiple indices with different fields.
        We normalize them all to a consistent format.
        """
        domain = cy_result.get("domain", "")
        url = cy_result.get("url") or f"https://{domain}"

        # === BUILD TITLE ===
        categories = cy_result.get("categories", [])
        detected_sectors = cy_result.get("detected_sectors", [])

        if isinstance(categories, list) and categories:
            title = f"{domain} - {', '.join(categories[:2])}"
        elif isinstance(categories, str) and categories:
            title = f"{domain} - {categories}"
        elif detected_sectors:
            if isinstance(detected_sectors, list):
                title = f"{domain} - {', '.join(detected_sectors[:2])}"
            else:
                title = f"{domain} - {detected_sectors}"
        else:
            title = domain or urlparse(url).netloc

        # === BUILD SNIPPET (Middle Cell) ===
        # Aggregate relevant metadata into the snippet for display
        snippet_parts = []

        # Text preview if available
        text_preview = cy_result.get("text_preview", "")
        if text_preview:
            snippet_parts.append(text_preview[:300])

        # Rank info
        rank = cy_result.get("tranco_rank")
        if rank:
            snippet_parts.insert(0, f"[Rank: {rank:,}]")

        # Categories/sectors info if not in title
        if not categories and detected_sectors:
            if isinstance(detected_sectors, list):
                snippet_parts.append(f"Sectors: {', '.join(detected_sectors[:3])}")

        snippet = " ".join(snippet_parts) if snippet_parts else ""

        # === BUILD METADATA (for Grid display) ===
        # This goes into metadata for rich grid rendering
        metadata = {
            # Core fields
            "domain": domain,
            "url": url,
            "source_index": cy_result.get("source_index"),
            "score": cy_result.get("score"),

            # Classification
            "category": categories[0] if isinstance(categories, list) and categories else (
                categories if isinstance(categories, str) else None
            ),
            "categories": categories if isinstance(categories, list) else [categories] if categories else [],
            "detected_sectors": detected_sectors if isinstance(detected_sectors, list) else [detected_sectors] if detected_sectors else [],

            # Ranking
            "tranco_rank": rank,
            "authority_rank": cy_result.get("authority_rank"),

            # Entities (for Column C)
            "entities": cy_result.get("entities", []),
            "matched_entities": cy_result.get("matched_entities", []),

            # Geographic/language context
            "country": cy_result.get("country"),
            "language": cy_result.get("language") or cy_result.get("lang"),
            "jurisdiction": cy_result.get("jurisdiction"),

            # Company data if from atlas
            "company_name": cy_result.get("company_name"),
            "company_industry": cy_result.get("company_industry"),

            # Source tracking
            "engines": ["CY"],  # Grid displays this as source badges
        }

        # Clean None values from metadata
        metadata = {k: v for k, v in metadata.items() if v is not None}

        return {
            # Primary fields for Grid
            "url": url,
            "title": title,
            "snippet": snippet[:500] if snippet else "",
            "description": snippet[:500] if snippet else "",  # Alias for snippet

            # Source identification
            "source": "CY",
            "engine_code": "CY",
            "engine_name": "CYMONIDES",
            "engines": ["CY"],

            # Rich metadata for Grid display
            "metadata": metadata,

            # Top-level copies for compatibility
            "domain": domain,
            "categories": metadata.get("categories", []),
            "tranco_rank": rank,
            "entities": cy_result.get("entities", []),
        }


class CymonidesRunner:
    """
    Runner class for compatibility with brute's ExactPhraseRecallRunner pattern.

    This wrapper allows CYMONIDES to be used with the same interface as
    Google, Bing, Brave runners.
    """

    def __init__(self, **kwargs):
        """Initialize the CYMONIDES runner."""
        self.engine = CymonidesEngine()
        self.seen_urls = set()
        self._lock = None

        # Try to use threading lock for dedup
        try:
            import threading
            self._lock = threading.Lock()
        except:
            pass

    def run(
        self,
        phrase: str = None,
        query: str = None,
        max_results: int = 100,
        **kwargs
    ) -> Iterator[Dict[str, Any]]:
        """
        Generator that yields CYMONIDES results.

        Compatible with brute's streaming architecture.

        Args:
            phrase: Exact phrase to search (wrapped in quotes if needed)
            query: Full query (overrides phrase if provided)
            max_results: Maximum results

        Yields:
            Result dicts with url, title, snippet, source
        """
        # Use query if provided, else phrase
        search_query = query or phrase or ""
        if not search_query:
            return

        for result in self.engine.search_stream(search_query, max_results, **kwargs):
            url = result.get("url", "")

            # Deduplicate by URL
            if url in self.seen_urls:
                continue

            if self._lock:
                with self._lock:
                    self.seen_urls.add(url)
            else:
                self.seen_urls.add(url)

            yield result

    def run_batch(
        self,
        phrase: str = None,
        query: str = None,
        max_results: int = 100,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Batch mode - returns all results at once.
        """
        return list(self.run(phrase=phrase, query=query, max_results=max_results, **kwargs))


def create_cymonides_runner(**kwargs) -> CymonidesRunner:
    """Factory function for brute's ENGINE_CONFIG."""
    return CymonidesRunner(**kwargs)


# For direct imports
__all__ = ['CymonidesEngine', 'CymonidesRunner', 'create_cymonides_runner']
