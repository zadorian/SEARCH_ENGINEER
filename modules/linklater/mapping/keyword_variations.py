"""
Keyword Variations Search - URL/Domain discovery via Wayback & Common Crawl

Generates variations of search keywords and queries:
1. Wayback Machine CDX API (URL patterns)
2. Common Crawl Index API (URL patterns)

Variations generated:
- Original: "john smith"
- Words swapped: "smith john"
- Dash separated: "john-smith", "smith-john"
- Dot separated: "john.smith", "smith.john"
- No spaces: "johnsmith", "smithjohn"
- Underscore: "john_smith", "smith_john"

Usage:
    from modules.cc_content import KeywordVariationsSearch

    searcher = KeywordVariationsSearch()
    results = await searcher.search("john smith", verify_snippets=True)
"""

import asyncio
import aiohttp
import json
import re
import logging
import os
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import quote, urlparse
from itertools import permutations
from pathlib import Path
from dotenv import load_dotenv

# Centralized CC config
from ..cc_config import CC_INDEX_BASE, get_default_archive

# Load environment for API keys
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(PROJECT_ROOT / '.env')

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

logger = logging.getLogger(__name__)


@dataclass
class VariationMatch:
    """A URL match from variation search."""
    url: str
    source: str  # 'wayback' or 'cc'
    variation_matched: str
    original_keyword: str
    timestamp: Optional[str] = None
    mime_type: Optional[str] = None
    status_code: Optional[int] = None
    snippet_verified: bool = False
    snippet: Optional[str] = None
    content_available: bool = False


@dataclass
class VariationSearchResult:
    """Results from a keyword variations search."""
    keyword: str
    variations_searched: List[str]
    total_matches: int
    unique_urls: int
    wayback_hits: int
    cc_hits: int
    verified_hits: int
    matches: List[VariationMatch]
    elapsed_seconds: float


class KeywordVariationsSearch:
    """
    Search Wayback Machine and Common Crawl indices for keyword variations.

    Generates URL patterns from keywords and searches archive indices
    to find pages that may contain the keyword in their URL or path.
    """

    # API endpoints
    WAYBACK_CDX_URL = "https://web.archive.org/cdx/search/cdx"
    # CC constants now imported from centralized cc_config.py

    def __init__(
        self,
        timeout: float = 30.0,
        max_results_per_source: int = 100,
        verify_snippets: bool = True,
    ):
        """
        Initialize the keyword variations search.

        Args:
            timeout: Request timeout in seconds
            max_results_per_source: Max results per source per variation
            verify_snippets: Whether to verify keywords appear in page content
        """
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_results = max_results_per_source
        self.verify_snippets = verify_snippets
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def close(self):
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def generate_variations_llm(self, keyword: str) -> List[str]:
        """
        Generate variations using LLM (Gemini Flash / Llama via OpenRouter).
        Falls back to heuristic generation if LLM fails.
        """
        # 1. Define Candidates (Free Priority)
        candidates = []
        
        if OPENROUTER_API_KEY:
            candidates.append({
                'model': 'google/gemini-2.0-flash-exp:free', # Priority 1: Speed & Quality
                'key': OPENROUTER_API_KEY,
                'url': 'https://openrouter.ai/api/v1/chat/completions'
            })
            candidates.append({
                'model': 'meta-llama/llama-3.3-70b-instruct:free',
                'key': OPENROUTER_API_KEY,
                'url': 'https://openrouter.ai/api/v1/chat/completions'
            })
            candidates.append({
                'model': 'mistralai/mistral-small-24b-instruct-2501:free',
                'key': OPENROUTER_API_KEY,
                'url': 'https://openrouter.ai/api/v1/chat/completions'
            })

        if OPENAI_API_KEY:
            candidates.append({
                'model': 'gpt-5-nano', 
                'key': OPENAI_API_KEY,
                'url': 'https://api.openai.com/v1/chat/completions'
            })

        if not candidates:
            return self.generate_variations(keyword) # Heuristic fallback

        # 2. Construct Prompt
        prompt = f"""Generate 8 keyword variations for: "{keyword}".
        Include:
        - Common misspellings
        - Phonetic spellings
        - Related terms
        - Joined words (e.g. "johnsmith")
        - Separated words (e.g. "john-smith")
        
        Return ONLY a JSON array of strings.
        Example: ["variation1", "variation2"]"""

        # 3. Execute with Fallback
        session = await self._get_session()
        
        for candidate in candidates:
            try:
                async with session.post(
                    candidate['url'],
                    headers={
                        'Authorization': f'Bearer {candidate["key"]}',
                        'Content-Type': 'application/json',
                        'HTTP-Referer': 'https://drill-search.app', 
                        'X-Title': 'Drill Search',
                    },
                    json={
                        'model': candidate['model'],
                        'messages': [{'role': 'user', 'content': prompt}],
                        'max_tokens': 150,
                        'temperature': 0.7,
                    },
                    timeout=aiohttp.ClientTimeout(total=10.0)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content = data.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
                        
                        # Parse JSON response
                        try:
                            # Clean markdown blocks if present
                            content = content.replace('```json', '').replace('```', '').strip()
                            variations = json.loads(content)
                            if isinstance(variations, list) and len(variations) > 0:
                                # Merge with heuristic variations to be safe
                                heuristic = self.generate_variations(keyword)
                                return list(set(variations + heuristic))
                        except Exception as e:

                            print(f"[LINKLATER] Error: {e}")

                            pass
                            
            except Exception:
                continue

        return self.generate_variations(keyword) # Fallback

    def generate_variations(self, keyword: str) -> List[str]:
        """
        Generate all variations of a keyword (Heuristic).

        Args:
            keyword: Original search keyword (e.g., "john smith")

        Returns:
            List of variations including swapped words, different separators
        """
        # Split into words
        words = keyword.lower().strip().split()

        if len(words) == 1:
            # Single word - just return it
            return [words[0]]

        variations = set()

        # Generate permutations for multi-word keywords
        word_perms = list(permutations(words))

        for perm in word_perms:
            # Original order with spaces (for reference)
            variations.add(' '.join(perm))

            # Dash separated: john-smith
            variations.add('-'.join(perm))

            # Dot separated: john.smith
            variations.add('.'.join(perm))

            # No separator: johnsmith
            variations.add(''.join(perm))

            # Underscore: john_smith
            variations.add('_'.join(perm))

            # Plus sign: john+smith (URL encoding)
            variations.add('+'.join(perm))

        # Also add original with common URL encodings
        original_encoded = keyword.replace(' ', '%20')
        variations.add(original_encoded)

        return list(variations)

    async def search_wayback(
        self,
        variation: str,
        original_keyword: str,
    ) -> List[VariationMatch]:
        """
        Search Wayback Machine CDX API for URLs containing the variation.

        Args:
            variation: The keyword variation to search
            original_keyword: Original keyword for reference

        Returns:
            List of VariationMatch objects
        """
        session = await self._get_session()
        matches = []

        # Build CDX API query - search for URLs containing this variation
        # Use matchType=domain to get broad results, then filter
        params = {
            'url': f'*/*{variation}*',  # Wildcard pattern
            'matchType': 'prefix',
            'output': 'json',
            'limit': str(self.max_results),
            'fl': 'original,timestamp,mimetype,statuscode',
            'filter': 'statuscode:200',  # Only successful pages
        }

        try:
            async with session.get(self.WAYBACK_CDX_URL, params=params) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    if text.strip():
                        lines = text.strip().split('\n')
                        # First line is header
                        if len(lines) > 1:
                            for line in lines[1:]:  # Skip header
                                try:
                                    parts = json.loads(line) if line.startswith('[') else line.split()
                                    if len(parts) >= 4:
                                        url, timestamp, mime, status = parts[0], parts[1], parts[2], parts[3]

                                        # Verify variation appears in URL
                                        if variation.lower() in url.lower():
                                            matches.append(VariationMatch(
                                                url=url,
                                                source='wayback',
                                                variation_matched=variation,
                                                original_keyword=original_keyword,
                                                timestamp=timestamp,
                                                mime_type=mime,
                                                status_code=int(status) if status.isdigit() else None,
                                            ))
                                except Exception as e:
                                    logger.debug(f"Failed to parse wayback line: {e}")
                                    continue
        except asyncio.TimeoutError:
            logger.warning(f"Wayback timeout for variation: {variation}")
        except Exception as e:
            logger.error(f"Wayback search error: {e}")

        return matches

    async def search_wayback_domain_url(
        self,
        variation: str,
        original_keyword: str,
    ) -> List[VariationMatch]:
        """
        Alternative: Search Wayback for domains/URLs containing variation.
        Uses simpler query structure.
        """
        session = await self._get_session()
        matches = []

        # Search for the variation in URLs
        encoded = quote(variation, safe='')
        url = f"{self.WAYBACK_CDX_URL}?url=*{encoded}*&output=json&limit={self.max_results}&filter=statuscode:200"

        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # CDX returns array of arrays, first is header
                    if data and len(data) > 1:
                        headers = data[0]
                        url_idx = headers.index('original') if 'original' in headers else 0
                        ts_idx = headers.index('timestamp') if 'timestamp' in headers else 1
                        mime_idx = headers.index('mimetype') if 'mimetype' in headers else 2
                        status_idx = headers.index('statuscode') if 'statuscode' in headers else 3

                        for row in data[1:]:
                            try:
                                matches.append(VariationMatch(
                                    url=row[url_idx],
                                    source='wayback',
                                    variation_matched=variation,
                                    original_keyword=original_keyword,
                                    timestamp=row[ts_idx] if ts_idx < len(row) else None,
                                    mime_type=row[mime_idx] if mime_idx < len(row) else None,
                                    status_code=int(row[status_idx]) if status_idx < len(row) and str(row[status_idx]).isdigit() else None,
                                ))
                            except Exception as e:
                                continue
        except Exception as e:
            logger.debug(f"Wayback domain search error: {e}")

        return matches

    async def search_cc_index(
        self,
        variation: str,
        original_keyword: str,
    ) -> List[VariationMatch]:
        """
        Search Common Crawl Index for URLs containing the variation.

        Args:
            variation: The keyword variation to search
            original_keyword: Original keyword for reference

        Returns:
            List of VariationMatch objects
        """
        session = await self._get_session()
        matches = []

        # CC Index URL pattern search (using centralized config)
        index_url = f"{CC_INDEX_BASE}/{get_default_archive()}-index"
        encoded = quote(f'*{variation}*', safe='')

        params = {
            'url': f'*{variation}*',
            'output': 'json',
            'limit': str(self.max_results),
        }

        try:
            async with session.get(index_url, params=params) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    if text.strip():
                        # CC returns JSONL (one JSON per line)
                        for line in text.strip().split('\n'):
                            try:
                                record = json.loads(line)
                                url = record.get('url', '')

                                # Verify variation in URL
                                if variation.lower() in url.lower():
                                    matches.append(VariationMatch(
                                        url=url,
                                        source='cc',
                                        variation_matched=variation,
                                        original_keyword=original_keyword,
                                        timestamp=record.get('timestamp'),
                                        mime_type=record.get('mime'),
                                        status_code=int(record.get('status', 0)) or None,
                                        content_available=True,  # CC has the content
                                    ))
                            except json.JSONDecodeError:
                                continue
        except asyncio.TimeoutError:
            logger.warning(f"CC Index timeout for variation: {variation}")
        except Exception as e:
            logger.error(f"CC Index search error: {e}")

        return matches

    async def verify_snippet(
        self,
        match: VariationMatch,
        keyword: str,
    ) -> VariationMatch:
        """
        Verify keyword appears in page content by fetching from CC.

        Args:
            match: The match to verify
            keyword: Original keyword to search for

        Returns:
            Updated match with verification status
        """
        # Import cc_first_scraper for content fetching
        try:
            from .cc_first_scraper import CCFirstScraper

            scraper = CCFirstScraper(cc_only=True)
            result = await scraper.get_content(match.url)

            if result.content:
                # Check if keyword (or words) appear in content
                content_lower = result.content.lower()
                keyword_lower = keyword.lower()
                words = keyword_lower.split()

                # Check for exact match or all words present
                if keyword_lower in content_lower:
                    match.snippet_verified = True
                    # Extract snippet around match
                    idx = content_lower.find(keyword_lower)
                    start = max(0, idx - 100)
                    end = min(len(result.content), idx + len(keyword) + 100)
                    match.snippet = result.content[start:end]
                elif all(word in content_lower for word in words):
                    match.snippet_verified = True
                    match.snippet = f"All words found: {', '.join(words)}"

            await scraper.close()
        except Exception as e:
            logger.debug(f"Snippet verification failed for {match.url}: {e}")

        return match

    async def search(
        self,
        keyword: str,
        verify_snippets: Optional[bool] = None,
        max_concurrent: int = 10,
    ) -> VariationSearchResult:
        """
        Search for keyword variations across Wayback and CC.

        Args:
            keyword: Original search keyword
            verify_snippets: Override instance setting for snippet verification
            max_concurrent: Max concurrent requests

        Returns:
            VariationSearchResult with all matches
        """
        start_time = datetime.now()
        do_verify = verify_snippets if verify_snippets is not None else self.verify_snippets

        # Generate variations using LLM (with fallback)
        variations = await self.generate_variations_llm(keyword)
        logger.info(f"Generated {len(variations)} variations for '{keyword}'")

        all_matches: List[VariationMatch] = []
        seen_urls: Set[str] = set()
        wayback_count = 0
        cc_count = 0

        # Create tasks for all variations
        semaphore = asyncio.Semaphore(max_concurrent)

        async def search_variation(variation: str) -> List[VariationMatch]:
            async with semaphore:
                results = []

                # Search both sources
                wb_matches = await self.search_wayback_domain_url(variation, keyword)
                cc_matches = await self.search_cc_index(variation, keyword)

                results.extend(wb_matches)
                results.extend(cc_matches)

                return results

        # Run all variation searches in parallel
        tasks = [search_variation(v) for v in variations]
        variation_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect and deduplicate
        for result in variation_results:
            if isinstance(result, Exception):
                logger.error(f"Variation search error: {result}")
                continue

            for match in result:
                # Normalize URL for deduplication
                normalized = match.url.lower().rstrip('/')
                if normalized not in seen_urls:
                    seen_urls.add(normalized)
                    all_matches.append(match)

                    if match.source == 'wayback':
                        wayback_count += 1
                    else:
                        cc_count += 1

        logger.info(f"Found {len(all_matches)} unique URLs ({wayback_count} Wayback, {cc_count} CC)")

        # Verify snippets if enabled
        verified_count = 0
        if do_verify and all_matches:
            logger.info(f"Verifying snippets for {len(all_matches)} matches...")

            async def verify_one(match: VariationMatch) -> VariationMatch:
                async with semaphore:
                    return await self.verify_snippet(match, keyword)

            verify_tasks = [verify_one(m) for m in all_matches]
            verified_matches = await asyncio.gather(*verify_tasks, return_exceptions=True)

            # Update matches with verification
            for i, result in enumerate(verified_matches):
                if isinstance(result, VariationMatch):
                    all_matches[i] = result
                    if result.snippet_verified:
                        verified_count += 1

        elapsed = (datetime.now() - start_time).total_seconds()

        return VariationSearchResult(
            keyword=keyword,
            variations_searched=variations,
            total_matches=wayback_count + cc_count,
            unique_urls=len(all_matches),
            wayback_hits=wayback_count,
            cc_hits=cc_count,
            verified_hits=verified_count,
            matches=all_matches,
            elapsed_seconds=elapsed,
        )

    def to_search_results(
        self,
        variation_result: VariationSearchResult,
        include_unverified: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Convert variation matches to standard search result format.

        Args:
            variation_result: The variation search result
            include_unverified: Include matches without snippet verification

        Returns:
            List of search result dicts compatible with BruteSearch
        """
        results = []

        for match in variation_result.matches:
            # Skip unverified if requested
            if not include_unverified and not match.snippet_verified:
                continue

            result = {
                'url': match.url,
                'title': f"[{match.source.upper()}] {match.variation_matched}",
                'snippet': match.snippet or f"URL contains variation: {match.variation_matched}",
                'description': match.snippet or f"Found in {match.source} archive",
                'source': match.source,
                'engines': [f'{match.source}_variation'],
                'metadata': {
                    'variation_matched': match.variation_matched,
                    'original_keyword': match.original_keyword,
                    'timestamp': match.timestamp,
                    'snippet_verified': match.snippet_verified,
                    'source_type': 'keyword_variation',
                },
            }

            if match.timestamp:
                result['date'] = match.timestamp

            results.append(result)

        return results


# Export
__all__ = ['KeywordVariationsSearch', 'VariationMatch', 'VariationSearchResult']


# CLI for testing
if __name__ == '__main__':
    import sys

    async def main():
        if len(sys.argv) < 2:
            print("Usage: python keyword_variations.py <keyword>")
            print("\nExample:")
            print("  python keyword_variations.py 'john smith'")
            return

        keyword = ' '.join(sys.argv[1:])
        searcher = KeywordVariationsSearch(verify_snippets=True)

        try:
            print(f"\n🔍 Searching variations for: '{keyword}'")
            result = await searcher.search(keyword)

            print(f"\n📊 Results:")
            print(f"   Variations searched: {len(result.variations_searched)}")
            print(f"   Total matches: {result.total_matches}")
            print(f"   Unique URLs: {result.unique_urls}")
            print(f"   Wayback hits: {result.wayback_hits}")
            print(f"   CC hits: {result.cc_hits}")
            print(f"   Verified: {result.verified_hits}")
            print(f"   Time: {result.elapsed_seconds:.2f}s")

            print(f"\n🎯 Variations:")
            for v in result.variations_searched:
                print(f"   - {v}")

            print(f"\n📄 Matches (first 10):")
            for match in result.matches[:10]:
                verified = "✓" if match.snippet_verified else "○"
                print(f"   {verified} [{match.source}] {match.url[:80]}...")
                print(f"      Variation: {match.variation_matched}")
                if match.snippet:
                    print(f"      Snippet: {match.snippet[:100]}...")

        finally:
            await searcher.close()

    asyncio.run(main())
