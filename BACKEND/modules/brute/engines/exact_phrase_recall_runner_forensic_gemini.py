#!/usr/bin/env python3
"""
exact_phrase_recall_runner_forensic_gemini.py - Forensic Gemini Brute Search Engine
====================================================================================
Integrates the Forensic Gemini module into the brute search pipeline.

Features:
- Forensic search methodology with depth-prioritized scoring
- Rule-based query generation (no API needed)
- AI-powered investigation with Gemini (when API key available)
- Inverted authority scoring (page 1 = LOW value, page 4+ = HIGH)
- Mandatory operators: filetype:pdf, inurl:, before:/after:, site:web.archive.org
- URL authenticity validation
- Dynamic questioning and role expansion
- Negative fingerprinting

Usage in brute.py:
    ENGINE_CONFIG = {
        'AI-GI': {
            'name': 'AI-Gemini',
            'module': 'engines.exact_phrase_recall_runner_forensic_gemini',
            'class': 'ExactPhraseRecallRunnerForensicGemini',
            'supports_streaming': True
        }
    }

Engine Code: AI-GI (AI-Gemini)
"""

from __future__ import annotations

import os
import sys
import logging
import asyncio
import threading
from typing import Dict, List, Optional, Any, Iterable
from datetime import datetime
from urllib.parse import urlparse

from dotenv import load_dotenv
load_dotenv()

# Add necessary paths for imports
_current_dir = os.path.dirname(os.path.abspath(__file__))
_brute_dir = os.path.dirname(_current_dir)
_modules_dir = os.path.dirname(_brute_dir)
sys.path.insert(0, _modules_dir)
sys.path.insert(0, _brute_dir)
sys.path.insert(0, _current_dir)

logger = logging.getLogger("forensic_gemini_runner")

# Try to import the Forensic Gemini module
try:
    # Try relative import first (from within Forensic_Gemini directory)
    from Forensic_Gemini.forensic_gemini import (
        ForensicSearchAgent,
        ForensicScorer,
        AuthenticityValidator,
        ForensicGeminiClient,
        ForensicQueryBuilder,
        GEMINI_MODEL,
        MAX_OUTPUT_TOKENS,
        FORENSIC_MASTER_PROMPT
    )
    FORENSIC_GEMINI_AVAILABLE = True
    logger.info("Forensic Gemini module loaded successfully")
except ImportError:
    try:
        # Try absolute module path
        from modules.brute.engines.Forensic_Gemini.forensic_gemini import (
            ForensicSearchAgent,
            ForensicScorer,
            AuthenticityValidator,
            ForensicGeminiClient,
            ForensicQueryBuilder,
            GEMINI_MODEL,
            MAX_OUTPUT_TOKENS,
            FORENSIC_MASTER_PROMPT
        )
        FORENSIC_GEMINI_AVAILABLE = True
        logger.info("Forensic Gemini module loaded (absolute path)")
    except ImportError as e2:
        logger.warning(f"Forensic Gemini module not available: {e2}")
        FORENSIC_GEMINI_AVAILABLE = False

# Try to import Google Search for executing generated queries
try:
    from brute.engines.google import GoogleSearch
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

# Try to import Bing as fallback
try:
    from brute.engines.bing import BingSearch
    BING_AVAILABLE = True
except ImportError:
    BING_AVAILABLE = False


class ExactPhraseRecallRunnerForensicGemini:
    """
    Forensic Gemini search engine for brute search integration.

    This engine generates forensic search queries using AI or rules,
    then executes them via Google/Bing to find buried, low-authority sources.

    Key methodology:
    - Depth over authority (page 1 = penalty, page 4+ = bonus)
    - Mandatory operators (filetype:pdf, inurl:, before/after, archive)
    - Authenticity validation with hallucination detection
    - Dynamic role expansion and negative fingerprinting
    """

    def __init__(
        self,
        phrase: str,
        company: Optional[str] = None,
        role: Optional[str] = None,
        pivot: Optional[str] = None,
        location: Optional[str] = None,
        year_range: Optional[tuple] = None,
        max_results_per_query: int = 50,
        max_queries: int = 20,
        use_ai: bool = True,
        execute_queries: bool = True,
        polite_delay: float = 0.5,
        use_parallel: bool = True,
        max_workers: int = 10,
    ):
        """
        Initialize the Forensic Gemini runner.

        Args:
            phrase: Main search target (anchor)
            company: Optional company/organization context
            role: Optional job title/role (will be OR-expanded)
            pivot: Optional secondary identifier
            location: Optional geographic location
            year_range: Optional tuple of (start_year, end_year)
            max_results_per_query: Maximum results per executed query
            max_queries: Maximum number of queries to execute
            use_ai: Whether to use Gemini AI for query generation
            execute_queries: Whether to execute generated queries
            polite_delay: Delay between query executions
            use_parallel: Whether to execute queries in parallel
            max_workers: Max parallel workers
        """
        self.phrase = phrase.strip()
        self.company = company
        self.role = role
        self.pivot = pivot
        self.location = location
        self.year_range = year_range
        self.max_results_per_query = max_results_per_query
        self.max_queries = max_queries
        self.use_ai = use_ai
        self.execute_queries = execute_queries
        self.polite_delay = polite_delay
        self.use_parallel = use_parallel
        self.max_workers = max_workers

        self._lock = threading.Lock()
        self._store: Dict[str, Dict] = {}  # url -> result-dict

        # Initialize components
        self.agent = None
        self.scorer = None
        self.validator = None
        self.search_engine = None

        if FORENSIC_GEMINI_AVAILABLE:
            api_key = os.getenv("GOOGLE_API_KEY")
            self.agent = ForensicSearchAgent(api_key if use_ai else None)
            self.scorer = ForensicScorer()
            self.validator = AuthenticityValidator()
            logger.info(f"Forensic Gemini initialized (AI mode: {use_ai and bool(api_key)})")
        else:
            logger.warning("Forensic Gemini not available - using fallback query generation")

        # Initialize search engine for query execution
        if execute_queries:
            if GOOGLE_AVAILABLE:
                self.search_engine = GoogleSearch()
                logger.info("Using Google for query execution")
            elif BING_AVAILABLE:
                self.search_engine = BingSearch()
                logger.info("Using Bing for query execution")
            else:
                logger.warning("No search engine available for query execution")

    def _add_and_get_new(self, batch: Optional[List[Dict]], query_str: str) -> List[Dict]:
        """Thread-safe deduplication and storage."""
        if not batch:
            return []

        new_hits = []
        with self._lock:
            for hit in batch:
                url = hit.get("url")
                if url and isinstance(url, str) and url not in self._store:
                    # Validate URL authenticity if validator available
                    if self.validator:
                        is_valid, reason = self.validator.validate(url)
                        hit['authenticity_verified'] = is_valid
                        hit['authenticity_reason'] = reason
                        if not is_valid:
                            hit['forensic_score'] = 0
                            logger.debug(f"URL failed authenticity: {url} - {reason}")

                    hit['found_by_query'] = query_str
                    hit['source'] = 'forensic_gemini'
                    self._store[url] = hit
                    new_hits.append(hit)

        if new_hits:
            logger.debug(f"Added {len(new_hits)} new unique URLs for: {query_str[:50]}...")
        return new_hits

    def _generate_queries(self) -> List[Dict]:
        """Generate forensic queries using the agent."""
        if not self.agent:
            return self._fallback_queries()

        try:
            result = self.agent.build_queries(
                target=self.phrase,
                pivot=self.pivot,
                company=self.company,
                title=self.role,
                negative_fingerprints=None
            )

            queries = result.get('queries', [])
            logger.info(f"Generated {len(queries)} forensic queries")
            return queries[:self.max_queries]

        except Exception as e:
            logger.error(f"Query generation failed: {e}")
            return self._fallback_queries()

    def _fallback_queries(self) -> List[Dict]:
        """Generate basic queries when Forensic Gemini not available."""
        queries = []
        anchor = self.phrase

        # Basic queries following forensic methodology
        base_queries = [
            (f'"{anchor}" filetype:pdf', "Artifact PDF search", ["filetype"]),
            (f'"{anchor}" inurl:directory', "Directory search", ["inurl"]),
            (f'"{anchor}" inurl:staff', "Staff page search", ["inurl"]),
            (f'"{anchor}" site:web.archive.org', "Archive search", ["site:archive"]),
            (f'"{anchor}" -site:linkedin.com -site:wikipedia.org', "Low authority filter", ["exclusion"]),
        ]

        if self.company:
            base_queries.append((
                f'"{anchor}" "{self.company}"',
                "Company intersection",
                ["intersection"]
            ))

        if self.role:
            base_queries.append((
                f'"{anchor}" ("{self.role}" OR "director" OR "manager")',
                "Role expansion",
                ["role_or"]
            ))

        for q, logic, operators in base_queries:
            queries.append({
                'q': q,
                'tier': 'fallback',
                'logic': logic,
                'operators_used': operators,
                'forensic_value': 'medium',
                'rationale': 'Fallback query generation'
            })

        return queries

    def _execute_query(self, query: Dict) -> List[Dict]:
        """Execute a single query and return results."""
        if not self.search_engine:
            return []

        query_str = query.get('q', '')
        if not query_str:
            return []

        try:
            results = self.search_engine.search(
                query_str,
                max_results=self.max_results_per_query
            )

            # Add forensic metadata to results
            for i, result in enumerate(results):
                # Estimate page position based on result index
                if i < 10:
                    page_position = "page_1"
                elif i < 20:
                    page_position = "page_2"
                elif i < 30:
                    page_position = "page_3"
                else:
                    page_position = "page_4_plus"

                result['estimated_page_position'] = page_position
                result['query_tier'] = query.get('tier', 'unknown')
                result['query_operators'] = query.get('operators_used', [])

                # Score the result if scorer available
                if self.scorer:
                    source_type = self._detect_source_type(result.get('url', ''))
                    score, breakdown = self.scorer.score(
                        url=result.get('url', ''),
                        source_type=source_type,
                        page_position=page_position,
                        is_authentic=result.get('authenticity_verified', True)
                    )
                    result['forensic_score'] = score
                    result['score_breakdown'] = breakdown

            return results

        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            return []

    def _detect_source_type(self, url: str) -> str:
        """Detect source type from URL for scoring."""
        url_lower = url.lower()

        if url_lower.endswith('.pdf'):
            return 'pdf'
        elif 'forum' in url_lower or 'community' in url_lower or 'discuss' in url_lower:
            return 'forum'
        elif 'blog' in url_lower:
            return 'personal_blog'
        elif 'linkedin.com' in url_lower:
            return 'linkedin'
        elif 'wikipedia.org' in url_lower:
            return 'wikipedia'
        elif any(news in url_lower for news in ['reuters', 'bbc', 'cnn', 'nytimes', 'wsj']):
            return 'major_news'
        elif 'news' in url_lower:
            return 'local_news'
        elif 'directory' in url_lower or 'staff' in url_lower:
            return 'directory'
        else:
            return 'unknown'

    def run(self) -> Iterable[Dict]:
        """
        Run the forensic search and yield results as they become available.

        This is the main entry point for brute search integration.
        """
        logger.info(f"Starting Forensic Gemini search for: '{self.phrase}'")
        self._store.clear()

        # Step 1: Generate forensic queries
        queries = self._generate_queries()
        if not queries:
            logger.warning("No queries generated")
            return

        logger.info(f"Generated {len(queries)} forensic queries to execute")

        # Step 2: Return queries as results if not executing
        if not self.execute_queries or not self.search_engine:
            logger.info("Query execution disabled - returning query metadata only")
            for query in queries:
                yield {
                    'url': None,
                    'title': f"[QUERY] {query.get('tier', 'unknown')}",
                    'snippet': query.get('q', ''),
                    'query_metadata': query,
                    'source': 'forensic_gemini_query',
                    'type': 'query'
                }
            return

        # Step 3: Execute queries and stream results
        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if self.use_parallel and len(queries) > 1:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {executor.submit(self._execute_query, q): q for q in queries}
                for future in as_completed(futures):
                    query = futures[future]
                    try:
                        batch = future.result()
                        new_hits = self._add_and_get_new(batch, query.get('q', ''))
                        for hit in new_hits:
                            yield hit
                    except Exception as e:
                        logger.error(f"Query execution failed: {e}")
        else:
            for query in queries:
                try:
                    batch = self._execute_query(query)
                    new_hits = self._add_and_get_new(batch, query.get('q', ''))
                    for hit in new_hits:
                        yield hit
                    time.sleep(self.polite_delay)
                except Exception as e:
                    logger.error(f"Query execution failed: {e}")

        logger.info(f"Forensic Gemini search complete. Found {len(self._store)} unique URLs")

    def run_as_list(self) -> List[Dict]:
        """Convenience method to collect all results into a list."""
        return list(self.run())

    async def run_ai_investigation(self, context: Optional[str] = None) -> Dict[str, Any]:
        """
        Run AI-powered investigation using Gemini.

        This uses the Gemini API to generate sophisticated forensic queries.
        Requires GOOGLE_API_KEY to be set.
        """
        if not self.agent or not self.agent.gemini:
            raise ValueError("AI investigation requires Forensic Gemini with API key")

        return await self.agent.investigate_ai(self.phrase, context)


# Convenience functions for direct usage
def forensic_search(
    phrase: str,
    company: Optional[str] = None,
    role: Optional[str] = None,
    **kwargs
) -> List[Dict]:
    """Quick forensic search without explicit runner instantiation."""
    runner = ExactPhraseRecallRunnerForensicGemini(
        phrase=phrase,
        company=company,
        role=role,
        **kwargs
    )
    return runner.run_as_list()


def generate_forensic_queries(
    phrase: str,
    company: Optional[str] = None,
    role: Optional[str] = None
) -> List[Dict]:
    """Generate forensic queries without executing them."""
    runner = ExactPhraseRecallRunnerForensicGemini(
        phrase=phrase,
        company=company,
        role=role,
        execute_queries=False
    )
    return list(runner.run())


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    print("""
╔══════════════════════════════════════════════════════════════╗
║          FORENSIC GEMINI BRUTE SEARCH ENGINE                 ║
║                                                              ║
║   Max Recall methodology with depth-prioritized scoring      ║
╚══════════════════════════════════════════════════════════════╝
    """)

    if not FORENSIC_GEMINI_AVAILABLE:
        print("WARNING: Forensic Gemini module not available")
        print("Using fallback query generation")

    phrase = input("Enter search target: ").strip()
    if not phrase:
        print("No phrase provided. Exiting.")
        sys.exit(1)

    company = input("Company context (Enter to skip): ").strip() or None
    role = input("Role/title (Enter to skip): ").strip() or None

    # Ask about execution mode
    print("\nExecution mode:")
    print("1. Generate queries only (no execution)")
    print("2. Generate and execute queries")
    mode = input("Choose mode (1 or 2, default=1): ").strip()

    execute = mode == "2"

    runner = ExactPhraseRecallRunnerForensicGemini(
        phrase=phrase,
        company=company,
        role=role,
        execute_queries=execute,
        max_results_per_query=10 if execute else 0
    )

    print(f"\nStarting forensic search for: '{phrase}'")
    if company:
        print(f"Company context: {company}")
    if role:
        print(f"Role context: {role}")

    results = []
    for result in runner.run():
        results.append(result)
        if len(results) % 5 == 0:
            print(f"Processed {len(results)} results...")

    print(f"\n--- FORENSIC SEARCH COMPLETE ---")
    print(f"Found {len(results)} results")

    if results:
        print("\nSample results:")
        for i, res in enumerate(results[:5], 1):
            if res.get('type') == 'query':
                print(f"\n{i}. [QUERY] {res.get('title', 'N/A')}")
                print(f"   Query: {res.get('snippet', 'N/A')[:80]}...")
            else:
                print(f"\n{i}. Title: {res.get('title', 'N/A')[:60]}...")
                print(f"   URL: {res.get('url', 'N/A')}")
                print(f"   Score: {res.get('forensic_score', 'N/A')}")
                print(f"   Position: {res.get('estimated_page_position', 'N/A')}")
