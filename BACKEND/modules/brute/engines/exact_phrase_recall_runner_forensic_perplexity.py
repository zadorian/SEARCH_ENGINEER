#!/usr/bin/env python3
"""
FORENSIC PERPLEXITY SEARCH ENGINE
=================================
Perplexity AI with forensic search methodology.
Same depth-prioritized scoring as Forensic Gemini.

Engine Code: AI-PX (AI-Perplexity)
"""

import os
import sys
import json
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Iterable
from dataclasses import dataclass

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'python-backend'))
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env')

# =============================================================================
# FORENSIC MASTER PROMPT (Same as Gemini)
# =============================================================================

FORENSIC_MASTER_PROMPT = '''SYSTEM OVERRIDE: FORENSIC SEARCH PROTOCOL ACTIVE.
Optimization Target: Max Recall & Forensic Probability.
Output Mode: MAXIMUM TOKENS - Comprehensive Discovery.
Constraint: Results on Google Page 1 are LOW VALUE - we seek what's BURIED.

## THE CORE PHILOSOPHY

You are the DETECTIVE, not the Spy.
- The Spy cares WHO is speaking (Authority)
- The Detective cares about RAW FACTS (buried witnesses)

A witness on page 47 has ZERO authority but 100% relevance.
Your job is to find page 47.

## FORENSIC SCORING (INVERTED + DEPTH PENALTY)

Base Scores:
- Forum/Community: 90 | PDF document: 95 | Personal blog: 85
- Obscure directory: 88 | Local news: 75 | Trade publication: 70
- LinkedIn: 40 | Major news: 25 | Wikipedia: 15

Depth Bonus (CRITICAL):
- Page 1 (1-10): -20 PENALTY
- Page 2 (11-20): +0
- Page 3 (21-30): +10
- Page 4+ (31+): +20
- Found via filetype/inurl only: +25

Authenticity Check:
- Hallucinated URL: SCORE = 0, EXCLUDE
- Non-resolving domain: SCORE = 0, EXCLUDE

## MANDATORY OPERATORS (ALWAYS INCLUDE)

1. filetype:pdf, filetype:xls, filetype:csv
2. inurl:directory, inurl:staff, inurl:team, inurl:admin
3. before:YYYY-MM-DD, after:YYYY-MM-DD
4. site:web.archive.org

## DYNAMIC QUESTIONING

For every query, probe:
- WHO else co-occurs? WHAT role variations?
- How ELSE referred to? (names, transliterations)
- What CONTEXT WORD appears nearby?
- What word appears in FALSE POSITIVES but NOT ours? (negative fingerprint)

## THE REDUCTION LADDER

Tier 0 (Net): "[Anchor]" AND ("[PivotA]" OR "[PivotB]")
Tier 1 (Intersect): "[Anchor]" AND [Unique Pivot]
Tier 2 (Phrase): "[Exact Full Name Title]"
Tier 3 (Filter): "[Anchor]" -site:linkedin.com -site:wikipedia.org
Tier 4 (Artifact): "[Anchor]" filetype:pdf | inurl:directory
Tier 5 (TimeMachine): "[Anchor]" before:2015 | site:web.archive.org
Tier 6 (Exclusion): "[Anchor]" -[negative_fingerprint]

## TOKEN UNIQUENESS

VERY HIGH (use alone): Unique terms like "Xylophigous"
HIGH: Uncommon surnames - minimal context
MEDIUM/LOW: Common names - aggressive OR-expansion required

## OUTPUT FORMAT

Return ONLY valid JSON with maximum results. Prioritize DEPTH over AUTHORITY.
If token-limited, show ONLY results from page 3+ or artifact searches.

{
  "meta": {...},
  "queries": [{tier, q, logic, operators_used, forensic_value, rationale}],
  "results": [{url, title, snippet, source_type, estimated_page_position, forensic_score, reasoning}]
}
'''

# =============================================================================
# Check for Perplexity availability
# =============================================================================

try:
    import requests
    PERPLEXITY_AVAILABLE = True
except ImportError:
    PERPLEXITY_AVAILABLE = False
    logger.warning("requests not available for Perplexity")

# =============================================================================
# FORENSIC SCORER (Same logic as Gemini)
# =============================================================================

@dataclass
class ForensicResult:
    url: str
    title: str
    snippet: str
    source_type: str
    estimated_page_position: str
    forensic_score: float
    reasoning: str
    query_used: str = ""
    engine: str = "AI-PX"


class ForensicScorer:
    """Score results using forensic methodology - depth over authority."""

    BASE_SCORES = {
        'pdf': 95, 'forum': 90, 'directory': 88, 'blog': 85,
        'local_news': 75, 'trade': 70, 'social': 40, 'linkedin': 40,
        'major_news': 25, 'wikipedia': 15, 'unknown': 50
    }

    DEPTH_MODIFIERS = {
        'page1': -20, 'page2': 0, 'page3': 10, 'page4plus': 20,
        'artifact_only': 25
    }

    HIGH_AUTHORITY_DOMAINS = [
        'linkedin.com', 'wikipedia.org', 'facebook.com', 'twitter.com',
        'nytimes.com', 'wsj.com', 'bbc.com', 'cnn.com', 'reuters.com',
        'bloomberg.com', 'forbes.com', 'ft.com'
    ]

    def classify_source(self, url: str) -> str:
        url_lower = url.lower()
        if '.pdf' in url_lower or 'filetype:pdf' in url_lower:
            return 'pdf'
        if any(x in url_lower for x in ['forum', 'community', 'discuss', 'board']):
            return 'forum'
        if any(x in url_lower for x in ['directory', 'staff', 'team', 'about']):
            return 'directory'
        if any(x in url_lower for x in ['blog', 'wordpress', 'medium.com', 'substack']):
            return 'blog'
        if 'linkedin.com' in url_lower:
            return 'linkedin'
        if 'wikipedia.org' in url_lower:
            return 'wikipedia'
        if any(d in url_lower for d in self.HIGH_AUTHORITY_DOMAINS):
            return 'major_news'
        return 'unknown'

    def estimate_depth(self, position: str) -> str:
        try:
            pos = int(position) if position.isdigit() else 50
            if pos <= 10: return 'page1'
            if pos <= 20: return 'page2'
            if pos <= 30: return 'page3'
            return 'page4plus'
        except Exception as e:
            return 'page3'  # Default to mid-depth

    def score(self, url: str, source_type: str = None, page_position: str = "30") -> Dict:
        if not source_type:
            source_type = self.classify_source(url)

        base = self.BASE_SCORES.get(source_type, 50)
        depth = self.estimate_depth(page_position)
        modifier = self.DEPTH_MODIFIERS.get(depth, 0)

        # Penalty for high-authority domains
        authority_penalty = 0
        for domain in self.HIGH_AUTHORITY_DOMAINS:
            if domain in url.lower():
                authority_penalty = -15
                break

        final_score = base + modifier + authority_penalty
        final_score = max(0, min(100, final_score))

        return {
            'score': final_score,
            'source_type': source_type,
            'depth': depth,
            'base_score': base,
            'depth_modifier': modifier,
            'authority_penalty': authority_penalty,
            'reasoning': f"Source: {source_type} ({base}), Depth: {depth} ({modifier:+d}), Authority: ({authority_penalty:+d})"
        }


# =============================================================================
# FORENSIC PERPLEXITY CLIENT
# =============================================================================

class ForensicPerplexityClient:
    """Perplexity client with forensic search methodology."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('PERPLEXITY_API_KEY')
        if not self.api_key:
            raise ValueError("PERPLEXITY_API_KEY not set")

        self.api_url = "https://api.perplexity.ai/chat/completions"
        self.scorer = ForensicScorer()

    def search_forensic(self, target: str, company: str = None, role: str = None,
                        max_results: int = 50) -> List[Dict]:
        """Execute forensic search with depth-prioritized scoring."""

        # Build context for forensic search
        context_parts = [target]
        if company:
            context_parts.append(company)
        if role:
            context_parts.append(role)

        context = " ".join(context_parts)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Use forensic prompt as system message
        payload = {
            "model": "llama-3.1-sonar-large-128k-online",
            "messages": [
                {
                    "role": "system",
                    "content": FORENSIC_MASTER_PROMPT
                },
                {
                    "role": "user",
                    "content": f"""Execute forensic search for: {target}

Context: {context}

IMPORTANT:
1. Find BURIED sources (page 3+, PDFs, directories, forums)
2. AVOID high-authority sources (LinkedIn, Wikipedia, major news)
3. Use mandatory operators: filetype:pdf, inurl:directory, before:, site:web.archive.org
4. Score by DEPTH not authority
5. Return {max_results} results with forensic scoring

For each result provide:
- url (exact, valid URL)
- title
- snippet
- source_type (pdf/forum/directory/blog/etc)
- estimated_page_position (number)
- forensic_score (0-100)
- reasoning

Return valid JSON array of results."""
                }
            ],
            "max_tokens": 4000,
            "return_citations": True,
            "search_recency_filter": "year"  # Cast wider net
        }

        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=60
            )

            if response.status_code == 200:
                data = response.json()
                results = []

                # Extract citations (actual web results)
                citations = data.get("citations", [])
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

                # Try to parse JSON from response
                try:
                    # Look for JSON array in response
                    if '[' in content and ']' in content:
                        json_start = content.find('[')
                        json_end = content.rfind(']') + 1
                        json_str = content[json_start:json_end]
                        parsed_results = json.loads(json_str)

                        for r in parsed_results[:max_results]:
                            url = r.get('url', '')
                            if not url:
                                continue

                            score_data = self.scorer.score(
                                url,
                                r.get('source_type'),
                                str(r.get('estimated_page_position', '30'))
                            )

                            results.append({
                                'url': url,
                                'title': r.get('title', url.split('/')[-1]),
                                'snippet': r.get('snippet', ''),
                                'source_type': score_data['source_type'],
                                'estimated_page_position': r.get('estimated_page_position', '30'),
                                'forensic_score': score_data['score'],
                                'reasoning': score_data['reasoning'],
                                'engine': 'AI-PX'
                            })
                except json.JSONDecodeError:
                    pass

                # Also add citations as results
                for i, cite in enumerate(citations[:max_results]):
                    if cite not in [r['url'] for r in results]:
                        score_data = self.scorer.score(cite, page_position=str(30 + i))
                        results.append({
                            'url': cite,
                            'title': cite.split('/')[-1] if '/' in cite else cite,
                            'snippet': f"Found via Perplexity forensic search for: {target}",
                            'source_type': score_data['source_type'],
                            'estimated_page_position': str(30 + i),
                            'forensic_score': score_data['score'],
                            'reasoning': score_data['reasoning'],
                            'engine': 'AI-PX'
                        })

                # Sort by forensic score (highest first)
                results.sort(key=lambda x: x.get('forensic_score', 0), reverse=True)
                return results[:max_results]

            else:
                logger.error(f"Perplexity API error: {response.status_code} - {response.text}")
                return []

        except Exception as e:
            logger.error(f"Perplexity forensic search error: {e}")
            return []


# =============================================================================
# MAIN RUNNER CLASS (Brute Search Interface)
# =============================================================================

class ExactPhraseRecallRunnerForensicPerplexity:
    """
    Forensic Perplexity Search Runner for Brute Search Integration.

    Engine Code: FP
    Uses same forensic methodology as Forensic Gemini.
    """

    def __init__(
        self,
        phrase: str = None,
        company: Optional[str] = None,
        role: Optional[str] = None,
        pivot: Optional[str] = None,
        location: Optional[str] = None,
        year_range: Optional[tuple] = None,
        use_ai: bool = True,
        execute_queries: bool = True,
        max_queries: int = 5,
        max_results_per_query: int = 50
    ):
        self.phrase = phrase or ""
        self.company = company
        self.role = role
        self.pivot = pivot
        self.location = location
        self.year_range = year_range
        self.use_ai = use_ai
        self.execute_queries = execute_queries
        self.max_queries = max_queries
        self.max_results_per_query = max_results_per_query

        self.seen_urls = set()
        self.results = []

        # Initialize client if available
        self.client = None
        if PERPLEXITY_AVAILABLE:
            try:
                self.client = ForensicPerplexityClient()
            except Exception as e:
                logger.warning(f"Could not initialize Perplexity client: {e}")

    def _generate_queries(self) -> List[Dict]:
        """Generate forensic query variations."""
        queries = []
        base = self.phrase

        # Tier 0: Net query with pivots
        if self.company or self.pivot:
            pivot = self.company or self.pivot
            queries.append({
                'q': f'"{base}" AND "{pivot}"',
                'tier': '0_Net',
                'forensic_value': 'high'
            })

        # Tier 2: Exact phrase
        queries.append({
            'q': f'"{base}"',
            'tier': '2_Phrase',
            'forensic_value': 'medium'
        })

        # Tier 3: Filter high-authority
        queries.append({
            'q': f'"{base}" -site:linkedin.com -site:wikipedia.org -site:facebook.com',
            'tier': '3_Filter',
            'forensic_value': 'high'
        })

        # Tier 4: Artifact search
        queries.append({
            'q': f'"{base}" filetype:pdf',
            'tier': '4_Artifact',
            'forensic_value': 'very_high'
        })

        # Tier 5: Time machine
        if self.year_range:
            queries.append({
                'q': f'"{base}" before:{self.year_range[1]}',
                'tier': '5_TimeMachine',
                'forensic_value': 'high'
            })
        else:
            queries.append({
                'q': f'"{base}" site:web.archive.org',
                'tier': '5_TimeMachine',
                'forensic_value': 'high'
            })

        return queries[:self.max_queries]

    def _add_unique(self, results: List[Dict]) -> List[Dict]:
        """Add results, filtering duplicates by URL hash."""
        new_results = []
        for r in results:
            url = r.get('url', '')
            url_hash = hashlib.md5(url.encode()).hexdigest()
            if url_hash not in self.seen_urls:
                self.seen_urls.add(url_hash)
                new_results.append(r)
                self.results.append(r)
        return new_results

    def run(self) -> Iterable[Dict]:
        """Generator that yields results as they're found."""
        if not self.client:
            logger.error("Perplexity client not available")
            return

        if not self.execute_queries:
            # Just return queries without executing
            for q in self._generate_queries():
                yield {'query': q, 'type': 'query_only'}
            return

        # Execute forensic search
        queries = self._generate_queries()

        for query_data in queries:
            try:
                results = self.client.search_forensic(
                    target=query_data['q'],
                    company=self.company,
                    role=self.role,
                    max_results=self.max_results_per_query
                )

                new_results = self._add_unique(results)
                for r in new_results:
                    r['query_used'] = query_data['q']
                    r['query_tier'] = query_data['tier']
                    yield r

            except Exception as e:
                logger.error(f"Query failed: {query_data['q']}: {e}")

    def run_as_list(self) -> List[Dict]:
        """Execute and return all results as a list."""
        return list(self.run())


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def forensic_search_perplexity(
    phrase: str,
    company: str = None,
    role: str = None,
    max_results: int = 100
) -> List[Dict]:
    """Quick forensic search using Perplexity."""
    runner = ExactPhraseRecallRunnerForensicPerplexity(
        phrase=phrase,
        company=company,
        role=role,
        max_results_per_query=max_results
    )
    return runner.run_as_list()


# For brute.py compatibility
FORENSIC_PERPLEXITY_AVAILABLE = PERPLEXITY_AVAILABLE


if __name__ == "__main__":
    # Test
    import sys
    if len(sys.argv) > 1:
        target = sys.argv[1]
        print(f"Forensic Perplexity search for: {target}")
        results = forensic_search_perplexity(target)
        for r in results[:10]:
            print(f"  [{r.get('forensic_score', 0)}] {r.get('url', 'N/A')}")
    else:
        print("Usage: python exact_phrase_recall_runner_forensic_perplexity.py <target>")
