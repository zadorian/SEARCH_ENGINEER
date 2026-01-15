#!/usr/bin/env python3
"""
Social Media Search Operator - Searches social platforms and profiles
Supports social:, profile:, sm: operators
Leverages sources/social_media.json with TORPEDO + BrightData Archive cat{social}!
"""

import sys
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from urllib.parse import quote_plus

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import event streaming
try:
    from brute.infrastructure.base_streamer import SearchTypeEventEmitter
    STREAMING_AVAILABLE = True
except ImportError:
    STREAMING_AVAILABLE = False
    logging.warning("Event streaming not available for social search")

# BrightData Archive - native cat{social}! support
try:
    from backdrill.brightdata import BrightDataArchive, search_by_category
    BRIGHTDATA_ARCHIVE_AVAILABLE = True
except ImportError:
    BRIGHTDATA_ARCHIVE_AVAILABLE = False
    BrightDataArchive = None
    search_by_category = None

# TORPEDO integration
try:
    from torpedo.EXECUTION.base_searcher import BaseSearcher
    from torpedo.paths import io_sources_dir
    TORPEDO_AVAILABLE = True
except ImportError:
    TORPEDO_AVAILABLE = False
    BaseSearcher = None
    io_sources_dir = None

# Social search engines
SOCIAL_ENGINES = [
    'GO',  # Google
    'BI',  # Bing
    'BR',  # Brave
    'DD',  # DuckDuckGo
]

# Major social platforms for site-specific searches
SOCIAL_PLATFORMS = {
    'twitter': 'site:twitter.com OR site:x.com',
    'linkedin': 'site:linkedin.com',
    'facebook': 'site:facebook.com',
    'instagram': 'site:instagram.com',
    'tiktok': 'site:tiktok.com',
    'youtube': 'site:youtube.com',
    'reddit': 'site:reddit.com',
    'pinterest': 'site:pinterest.com',
    'snapchat': 'site:snapchat.com',
    'telegram': 'site:t.me',
    'discord': 'site:discord.com',
    'github': 'site:github.com',
    'mastodon': 'site:mastodon.social',
    'threads': 'site:threads.net',
    'bluesky': 'site:bsky.app',
}

# Profile search patterns
PROFILE_PATTERNS = [
    'profile', 'user', 'account', '@{q}', 'u/{q}',
]


class SocialSearcher:
    """
    Social media search implementation using TORPEDO + BrightData Archive.
    Routes searches to social platforms from I/O matrix.
    """

    def __init__(self, event_emitter=None):
        """Initialize social search."""
        self.event_emitter = event_emitter
        self.sources: List[Dict[str, Any]] = []
        self.sources_loaded = False
        self.base_scraper = BaseSearcher() if TORPEDO_AVAILABLE else None

        if STREAMING_AVAILABLE and event_emitter:
            self.streamer = SearchTypeEventEmitter(event_emitter)
        else:
            self.streamer = None

    async def load_sources(self) -> int:
        """Load social media sources from sources/social_media.json."""
        if self.sources_loaded:
            return len(self.sources)

        try:
            if io_sources_dir:
                social_path = io_sources_dir() / "social_media.json"
            else:
                social_path = Path("/data/SEARCH_ENGINEER/modules/input_output/matrix/sources/social_media.json")

            if not social_path.exists():
                logger.warning(f"Social media sources not found at {social_path}")
                return 0

            with open(social_path) as f:
                data = json.load(f)

            sources_list = data.get("sources", [])

            for source in sources_list:
                template = source.get("search_template") or source.get("search_url")
                if not template or "{q}" not in template:
                    continue

                self.sources.append({
                    "id": source.get("id", ""),
                    "domain": source.get("domain", ""),
                    "name": source.get("name", source.get("domain", "")),
                    "search_template": template,
                    "friction": source.get("friction", "public"),
                    "source_type": source.get("source_type", "social_media"),
                })

            self.sources_loaded = True
            logger.info(f"Loaded {len(self.sources)} social media sources")
            return len(self.sources)

        except Exception as e:
            logger.error(f"Failed to load social media sources: {e}")
            return 0

    async def search_source(
        self,
        source: Dict[str, Any],
        query: str,
        max_results: int = 8
    ) -> List[Dict[str, Any]]:
        """Search a single social source using its template."""
        template = source.get("search_template", "")
        if not template or "{q}" not in template:
            return []

        url = template.replace("{q}", quote_plus(query))
        results = []

        try:
            if self.base_scraper:
                response = await self.base_scraper.fetch_url(
                    url,
                    use_brightdata=False
                )

                if response.get("success") and response.get("html"):
                    soup = self.base_scraper.parse_html(response["html"])

                    # Extract links/profiles from page
                    for link in soup.select("a[href]")[:max_results * 2]:
                        href = link.get("href", "")
                        title = link.get_text(strip=True)

                        if not href or href.startswith("#") or not title:
                            continue
                        if len(title) < 3:
                            continue

                        # Make absolute URL
                        if href.startswith("/"):
                            domain = source.get("domain", "")
                            href = f"https://{domain}{href}"

                        results.append({
                            "title": title[:200],
                            "url": href,
                            "source": source.get("name", source.get("domain", "")),
                            "source_domain": source.get("domain", ""),
                            "search_type": "social",
                            "method": "torpedo",
                        })

                        if len(results) >= max_results:
                            break

        except Exception as e:
            logger.debug(f"Source search failed for {source.get('domain')}: {e}")

        return results

    def _build_social_queries(
        self,
        query: str,
        platforms: Optional[List[str]] = None,
        search_type: str = "general"
    ) -> List[str]:
        """Build comprehensive social media search queries."""
        queries = []

        # Base queries
        queries.append(f'"{query}" profile')
        queries.append(f'"{query}" social media')

        # Platform-specific searches
        target_platforms = platforms if platforms else list(SOCIAL_PLATFORMS.keys())[:6]
        for platform in target_platforms:
            if platform in SOCIAL_PLATFORMS:
                queries.append(f'{SOCIAL_PLATFORMS[platform]} "{query}"')

        # Profile-specific patterns
        if search_type == "profile":
            queries.extend([
                f'"@{query}"',
                f'"{query}" account',
                f'"{query}" user',
            ])

        # Username patterns
        queries.extend([
            f'inurl:/{query}',
            f'"{query}" bio',
            f'"{query}" posts',
        ])

        return queries

    async def search(
        self,
        query: str,
        platforms: Optional[List[str]] = None,
        search_type: str = "general",
        max_results: int = 100,
        max_sources: int = 15,
        max_concurrent: int = 6
    ) -> List[Dict[str, Any]]:
        """
        Search social media platforms.

        Args:
            query: Username, name, or search term
            platforms: Optional list of platforms to search
            search_type: "general" or "profile"
            max_results: Maximum total results
            max_sources: Maximum I/O sources to query
            max_concurrent: Max concurrent requests

        Returns:
            List of social media search results
        """
        query = query.strip()

        logger.info(f"Starting social search for: '{query}' (platforms={platforms}, type={search_type})")

        if self.streamer:
            await self.streamer.emit_search_started('social', query, ['TORPEDO', 'BD_ARCHIVE'])

        await self.load_sources()

        all_results = []
        seen_urls = set()

        # TORPEDO: Search I/O sources
        if self.sources and self.base_scraper:
            sources_to_search = self.sources[:max_sources]
            semaphore = asyncio.Semaphore(max_concurrent)

            async def fetch_source(source):
                async with semaphore:
                    return await self.search_source(source, query, max_results=6)

            try:
                source_batches = await asyncio.gather(
                    *(fetch_source(s) for s in sources_to_search),
                    return_exceptions=True
                )

                for batch in source_batches:
                    if isinstance(batch, Exception):
                        continue
                    for result in batch:
                        url = result.get("url", "")
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            all_results.append(result)

                logger.info(f"TORPEDO: {len(all_results)} results from {len(sources_to_search)} social sources")

            except Exception as e:
                logger.warning(f"TORPEDO social search failed: {e}")

        # BrightData Archive: Native cat{social}! support
        if BRIGHTDATA_ARCHIVE_AVAILABLE and search_by_category:
            try:
                bd_limit = max(max_results // 3, 25)
                bd_results = await search_by_category(
                    category="social",
                    limit=bd_limit,
                )

                for r in bd_results:
                    url = r.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        r['source'] = 'brightdata_archive'
                        r['search_type'] = 'social'
                        r['method'] = 'brightdata_archive'
                        all_results.append(r)

                logger.info(f"BrightData Archive added {len(bd_results)} social results")

            except Exception as e:
                logger.warning(f"BrightData Archive social search failed: {e}")

        # General search with platform filters
        social_queries = self._build_social_queries(query, platforms, search_type)

        try:
            from brute.targeted_searches.brute import BruteSearchEngine

            for social_query in social_queries[:6]:
                logger.info(f"Searching with query: '{social_query}'")

                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                output_file = f"results/social_{timestamp}.json"

                searcher = BruteSearchEngine(
                    keyword=social_query,
                    output_file=output_file,
                    engines=SOCIAL_ENGINES,
                    max_workers=min(len(SOCIAL_ENGINES), 4),
                    event_emitter=self.event_emitter,
                    return_results=True
                )

                searcher.search()

                if hasattr(searcher, 'final_results'):
                    for result in searcher.final_results:
                        url = result.get('url', '')
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            result['search_type'] = 'social'
                            result['query_variant'] = social_query
                            result['method'] = 'brute_search'
                            all_results.append(result)

                if len(all_results) >= max_results:
                    break

        except ImportError as e:
            logger.error(f"Failed to import BruteSearchEngine: {e}")
        except Exception as e:
            logger.error(f"Social search failed: {e}")

        # Score and sort results
        scored_results = self._score_social_results(all_results, query, platforms)

        if self.streamer:
            await self.streamer.emit_search_completed('social', len(scored_results))

        logger.info(f"Social search completed with {len(scored_results)} results")

        return scored_results[:max_results]

    def _score_social_results(
        self,
        results: List[Dict],
        query: str,
        platforms: Optional[List[str]] = None
    ) -> List[Dict]:
        """Score and sort social results by relevance."""
        query_lower = query.lower()

        def score_result(result):
            score = 0
            url = result.get('url', '').lower()
            title = result.get('title', '').lower()

            # Major social platform domains
            major_platforms = ['twitter.com', 'x.com', 'linkedin.com', 'facebook.com',
                             'instagram.com', 'youtube.com', 'tiktok.com', 'reddit.com']
            for platform in major_platforms:
                if platform in url:
                    score += 50
                    break

            # Professional platforms bonus
            if 'linkedin.com' in url:
                score += 20

            # Profile patterns in URL
            profile_patterns = ['/user/', '/u/', '/profile/', '/@', '/people/']
            for pattern in profile_patterns:
                if pattern in url:
                    score += 30
                    break

            # Username in URL
            if f'/{query_lower}' in url or f'@{query_lower}' in url:
                score += 40

            # Query match in title
            if query_lower in title:
                score += 25

            # TORPEDO source
            if result.get('method') == 'torpedo':
                score += 20

            # BrightData Archive
            if result.get('source') == 'brightdata_archive':
                score += 15

            # Social keywords
            social_keywords = ['profile', 'posts', 'followers', 'following', 'bio']
            for keyword in social_keywords:
                if keyword in title:
                    score += 10
                    break

            return score

        for result in results:
            result['social_score'] = score_result(result)

        results.sort(key=lambda x: x.get('social_score', 0), reverse=True)

        return results

    def search_sync(self, query: str, platforms: Optional[List[str]] = None,
                   max_results: int = 100) -> List[Dict[str, Any]]:
        """Synchronous wrapper for search method."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.search(query, platforms, max_results=max_results))
        finally:
            loop.close()


def detect_social_query(query: str) -> bool:
    """Detect if a query should be routed to social search."""
    query_lower = query.lower()

    social_patterns = [
        'social:',
        'profile:',
        'sm:',
        'twitter:',
        'linkedin:',
        'facebook:',
        'instagram:',
    ]

    for pattern in social_patterns:
        if pattern in query_lower:
            return True

    return False


def extract_social_query(query: str) -> str:
    """Extract the actual search query from a social search query."""
    query = query.strip()

    prefixes = [
        'social:', 'profile:', 'sm:', 'twitter:', 'linkedin:', 'facebook:', 'instagram:',
        'Social:', 'Profile:', 'SM:', 'Twitter:', 'LinkedIn:', 'Facebook:', 'Instagram:'
    ]

    for prefix in prefixes:
        if query.startswith(prefix):
            query = query[len(prefix):].strip()
            if query.startswith('"') and query.endswith('"'):
                query = query[1:-1]
            elif query.startswith("'") and query.endswith("'"):
                query = query[1:-1]
            return query

    return query.strip()


async def run_social_search(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """Main entry point for social search."""
    clean_query = extract_social_query(query)
    searcher = SocialSearcher(event_emitter)
    return await searcher.search(clean_query)


def run_social_search_sync(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """Synchronous wrapper for social search."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(run_social_search(query, event_emitter))
    finally:
        loop.close()


def search(query: str, max_results: int = 100) -> List[Dict[str, Any]]:
    """Synchronous search function for web API compatibility."""
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, run_social_search(query))
            return future.result()
    except RuntimeError:
        return asyncio.run(run_social_search(query))


def main():
    """Main entry point for Social media search - compatible with SearchRouter"""
    import argparse

    parser = argparse.ArgumentParser(description='Social media search')
    parser.add_argument('-q', '--query', required=True, help='Username or search term')
    parser.add_argument('-p', '--platforms', nargs='+', help='Platforms to search')
    args = parser.parse_args()

    query = args.query

    if ':' in query:
        clean_query = query.split(':', 1)[1].strip()
    else:
        clean_query = query

    print(f"\n🔍 Social media search: {clean_query}")
    if args.platforms:
        print(f"   Platforms: {', '.join(args.platforms)}")

    results = run_social_search_sync(clean_query)

    if results:
        print(f"\nFound {len(results)} results:")
        for i, result in enumerate(results[:10], 1):
            print(f"\n{i}. {result.get('title', 'No Title')}")
            print(f"   URL: {result.get('url')}")
            print(f"   Source: {result.get('source', 'Unknown')}")
    else:
        print("\nNo results found.")

    return results


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        test_query = ' '.join(sys.argv[1:])
    else:
        test_query = "social:john_doe"

    print(f"Testing social search with: {test_query}")

    if detect_social_query(test_query):
        print("Social query detected!")
        clean_query = extract_social_query(test_query)
        print(f"Extracted query: '{clean_query}'")

        results = run_social_search_sync(test_query)

        print(f"\nFound {len(results)} social results:")
        for i, result in enumerate(results[:10], 1):
            print(f"\n{i}. {result.get('title', 'No title')}")
            print(f"   URL: {result.get('url', 'No URL')}")
            print(f"   Method: {result.get('method', 'Unknown')}")
    else:
        print("Not a social query")
