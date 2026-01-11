"""
Search Intensity Tiers
======================

Defines the search intensity levels for query execution.
Higher tiers = more aggressive discovery, more results, longer runtime.

Tiers are about HOW HARD we search, not result quality scoring.
"""

from enum import IntEnum
from typing import Dict, Any, List, Optional
from dataclasses import dataclass


class SearchTier(IntEnum):
    """Search intensity levels."""
    NATIVE = 1      # Fast, clean - native engine capabilities only
    ENHANCED = 2    # Balanced - clever workarounds and expansions
    BRUTE = 3       # Maximum recall - all engines, all variations
    NUCLEAR = 4     # Brute + recursive link expansion (outlinks + backlinks)


@dataclass
class TierConfig:
    """Configuration for a search tier."""
    name: str
    description: str
    engines: str  # 'fast', 'all', 'all+slow'
    query_expansion: bool
    max_results_per_engine: int
    timeout_seconds: int
    # Nuclear-specific
    extract_outlinks: bool = False
    outlinks_per_result: int = 0
    extract_backlinks: bool = False
    backlinks_per_result: int = 0
    scrape_discovered_urls: bool = False


# Tier configurations
TIER_CONFIGS: Dict[SearchTier, TierConfig] = {
    SearchTier.NATIVE: TierConfig(
        name="Native",
        description="Fast, clean results using native engine capabilities",
        engines="fast",  # GO, BI, BR, DD, EX
        query_expansion=False,
        max_results_per_engine=50,
        timeout_seconds=30,
    ),

    SearchTier.ENHANCED: TierConfig(
        name="Enhanced",
        description="Balanced approach with clever workarounds and query expansion",
        engines="all",
        query_expansion=True,
        max_results_per_engine=100,
        timeout_seconds=60,
    ),

    SearchTier.BRUTE: TierConfig(
        name="Brute",
        description="Maximum recall - all engines, all variations, aggressive expansion",
        engines="all+slow",
        query_expansion=True,
        max_results_per_engine=200,
        timeout_seconds=120,
    ),

    SearchTier.NUCLEAR: TierConfig(
        name="Nuclear",
        description="Brute + recursive link expansion: extract outlinks and backlinks from each result, scrape all, scan for query terms",
        engines="all+slow",
        query_expansion=True,
        max_results_per_engine=200,
        timeout_seconds=300,  # 5 minutes - this takes time
        # Nuclear-specific settings
        extract_outlinks=True,
        outlinks_per_result=10,
        extract_backlinks=True,
        backlinks_per_result=10,
        scrape_discovered_urls=True,
    ),
}


# Engine groups for tier selection
ENGINE_GROUPS = {
    "fast": ["GO", "BI", "BR", "DD", "EX", "CY"],  # CY = CYMONIDES (local ES, instant)
    "all": ["GO", "BI", "BR", "DD", "EX", "CY", "YA", "QW", "GR", "NA", "GD", "AL"],
    "all+slow": ["GO", "BI", "BR", "DD", "EX", "CY", "YA", "QW", "GR", "NA", "GD", "AL", "AR", "YE", "PW"],
    # LINKLATER engines for anchor text / backlink searches
    # WG is fast (local ES), MJ/BD are medium (API calls), GL is slow but most comprehensive
    "linklater": ["WG", "MJ", "BD", "GL"],
    # Local ES indices (fastest possible)
    "local": ["CY", "WG"],
}


def get_tier_config(tier: int) -> TierConfig:
    """Get configuration for a tier level."""
    try:
        return TIER_CONFIGS[SearchTier(tier)]
    except ValueError:
        raise ValueError(f"Invalid tier {tier}. Valid tiers: 1-4")


def get_engines_for_tier(tier: int) -> List[str]:
    """Get engine codes for a tier level."""
    config = get_tier_config(tier)
    return ENGINE_GROUPS.get(config.engines, ENGINE_GROUPS["fast"])


def is_nuclear(tier: int) -> bool:
    """Check if tier is Nuclear (requires link expansion)."""
    return tier == SearchTier.NUCLEAR


class NuclearExpander:
    """
    Handles Tier 4 Nuclear link expansion.

    For each search result:
    1. Extract up to N outlinks from the page
    2. Fetch up to N backlinks pointing to the domain
    3. Scrape all discovered URLs
    4. Scan scraped content for original query terms
    """

    def __init__(
        self,
        outlinks_per_result: int = 10,
        backlinks_per_result: int = 10,
        max_concurrent_scrapes: int = 100,  # Match Firecrawl subscription
    ):
        self.outlinks_per_result = outlinks_per_result
        self.backlinks_per_result = backlinks_per_result
        self.max_concurrent_scrapes = max_concurrent_scrapes

    async def expand_results(
        self,
        results: List[Dict[str, Any]],
        query: str,
        jester_scraper=None,
        backlink_fetcher=None,
    ) -> Dict[str, Any]:
        """
        Expand search results with outlinks and backlinks.

        Args:
            results: Initial search results from Brute search
            query: Original search query (for content scanning)
            jester_scraper: JESTER scraper instance for scraping/outlink extraction
            backlink_fetcher: LINKLATER/CC backlink fetcher

        Returns:
            Dict with expanded results, discovered URLs, and scan matches
        """
        from urllib.parse import urlparse

        discovered_urls = set()
        result_urls = []

        for result in results:
            url = result.get("url", "")
            if not url:
                continue
            result_urls.append(url)

            # Extract domain for backlink lookup
            try:
                domain = urlparse(url).netloc
            except:
                domain = None

            # 1. Extract outlinks from this result
            if jester_scraper:
                try:
                    outlinks = await self._extract_outlinks(url, jester_scraper)
                    for link in outlinks[:self.outlinks_per_result]:
                        discovered_urls.add(link)
                except Exception as e:
                    pass  # Continue on error

            # 2. Fetch backlinks to this domain
            if backlink_fetcher and domain:
                try:
                    backlinks = await self._fetch_backlinks(domain, backlink_fetcher)
                    for link in backlinks[:self.backlinks_per_result]:
                        discovered_urls.add(link)
                except Exception as e:
                    pass  # Continue on error

        # Remove original result URLs from discovered (avoid duplicates)
        discovered_urls -= set(result_urls)
        discovered_list = list(discovered_urls)

        # 3. Scrape all discovered URLs
        scraped_content = {}
        if jester_scraper and discovered_list:
            try:
                scraped_content = await self._scrape_batch(
                    discovered_list,
                    jester_scraper
                )
            except Exception as e:
                pass

        # 4. Scan scraped content for query terms
        matches = self._scan_for_query(scraped_content, query)

        return {
            "original_results": results,
            "discovered_urls": discovered_list,
            "scraped_count": len(scraped_content),
            "query_matches": matches,
            "total_urls_processed": len(result_urls) + len(discovered_list),
        }

    async def _extract_outlinks(self, url: str, scraper) -> List[str]:
        """Extract outlinks from a URL using JESTER."""
        try:
            result = await scraper.scrape(url)
            if result and hasattr(result, 'links'):
                return result.links[:self.outlinks_per_result]
            return []
        except:
            return []

    async def _fetch_backlinks(self, domain: str, fetcher) -> List[str]:
        """Fetch backlinks to a domain using LINKLATER/CC webgraph."""
        try:
            backlinks = await fetcher.get_backlinks(domain, limit=self.backlinks_per_result)
            return [b.get("source_url", b.get("url", "")) for b in backlinks]
        except:
            return []

    async def _scrape_batch(self, urls: List[str], scraper) -> Dict[str, str]:
        """Batch scrape URLs using JESTER with max concurrency."""
        try:
            results = await scraper.scrape_batch(
                urls,
                max_concurrent=self.max_concurrent_scrapes
            )
            return {r.url: r.text for r in results if r and hasattr(r, 'text')}
        except:
            return {}

    def _scan_for_query(self, content: Dict[str, str], query: str) -> List[Dict[str, Any]]:
        """Scan scraped content for query term matches."""
        import re

        matches = []
        query_terms = query.lower().split()
        query_pattern = re.compile(r'\b(' + '|'.join(re.escape(t) for t in query_terms) + r')\b', re.I)

        for url, text in content.items():
            if not text:
                continue

            found_terms = set(query_pattern.findall(text.lower()))
            if found_terms:
                # Find snippet around first match
                match = query_pattern.search(text)
                if match:
                    start = max(0, match.start() - 100)
                    end = min(len(text), match.end() + 100)
                    snippet = text[start:end].strip()
                else:
                    snippet = text[:200]

                matches.append({
                    "url": url,
                    "matched_terms": list(found_terms),
                    "term_count": len(found_terms),
                    "snippet": snippet,
                })

        # Sort by number of matched terms
        matches.sort(key=lambda x: x["term_count"], reverse=True)
        return matches
