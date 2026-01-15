"""
Domain Filters for Discovery
=============================

Imports discovery CLIs from categorizer-filterer and wraps them for LinkLater.

This module does NOT duplicate CLI code - it imports from categorizer-filterer.
"""

import sys
from pathlib import Path
from typing import List, Dict, Optional, AsyncIterator
import asyncio

# Add categorizer-filterer to path
CATEGORIZER_PATH = (lambda: Path(__file__).resolve().parents[4] if len(Path(__file__).resolve().parents) > 4 else Path("/nonexistent"))() / "categorizer-filterer"
if str(CATEGORIZER_PATH) not in sys.path:
    sys.path.insert(0, str(CATEGORIZER_PATH))

# Import CLIs from categorizer-filterer
try:
    from bigquery_cli import BigQueryAPI
    BIGQUERY_AVAILABLE = True
except ImportError:
    BIGQUERY_AVAILABLE = False

try:
    from openpagerank_cli import OpenPageRankAPI
    OPENPAGERANK_AVAILABLE = True
except ImportError:
    OPENPAGERANK_AVAILABLE = False

try:
    from tranco_cli import TrancoAPI
    TRANCO_AVAILABLE = True
except ImportError:
    TRANCO_AVAILABLE = False

try:
    from cloudflare_radar_cli import CloudflareRadarAPI
    CLOUDFLARE_AVAILABLE = True
except ImportError:
    CLOUDFLARE_AVAILABLE = False


class BigQueryDiscovery:
    """
    BigQuery domain discovery wrapper.

    Queries BigQuery public datasets:
    - Chrome UX Report (CrUX) - Real user data
    - HTTP Archive - Technology stacks

    Cost: Free (with billing limits)
    """

    def __init__(self, project_id: Optional[str] = None):
        if not BIGQUERY_AVAILABLE:
            raise ImportError("BigQuery CLI not available. Check categorizer-filterer/bigquery_cli.py")

        self.api = BigQueryAPI(project_id)

    def discover_domains_by_country(self, country: str, form_factor: str = 'desktop', limit: int = 1000) -> Dict:
        """
        Discover domains from Chrome UX Report by country.

        Args:
            country: 2-letter country code (e.g., 'US', 'GB', 'LY')
            form_factor: 'desktop', 'mobile', or 'tablet'
            limit: Max domains to return

        Returns:
            Dict with success, results, table_used, month
        """
        return self.api.get_crux_domains(country, form_factor, limit)

    def discover_by_technology(self, technology: str, limit: int = 1000) -> Dict:
        """
        Discover domains using specific technology.

        Args:
            technology: Technology name (e.g., 'WordPress', 'React', 'Drupal')
            limit: Max domains to return

        Returns:
            Dict with success, results (domain, app, category)
        """
        return self.api.get_httparchive_technologies(technology, limit)

    def discover_popular_domains(self, limit: int = 1000, country: Optional[str] = None) -> Dict:
        """
        Discover popular domains from CrUX measurement volume.

        Args:
            limit: Max domains to return
            country: Optional country filter

        Returns:
            Dict with success, results (origin, measurement_count)
        """
        return self.api.get_popular_domains_crux(limit, country)

    def run_custom_query(self, query: str, max_results: int = 1000) -> Dict:
        """
        Run custom BigQuery SQL query.

        Args:
            query: BigQuery SQL query
            max_results: Max results to return

        Returns:
            Dict with success, results, bytes_processed, cache_hit
        """
        return self.api.run_query(query, max_results)


class OpenPageRankFilter:
    """
    OpenPageRank domain authority filter.

    Free tier: 200,000 requests/month
    Returns: PageRank scores (0-10 scale)

    Use for: Filtering domains by authority/quality
    """

    def __init__(self, api_key: Optional[str] = None):
        if not OPENPAGERANK_AVAILABLE:
            raise ImportError("OpenPageRank CLI not available. Check categorizer-filterer/openpagerank_cli.py")

        self.api = OpenPageRankAPI(api_key)

    def filter_by_pagerank(self, domains: List[str], min_pagerank: float = 2.0) -> List[Dict]:
        """
        Filter domains by minimum PageRank score.

        Args:
            domains: List of domains to check
            min_pagerank: Minimum PageRank threshold (0-10 scale)

        Returns:
            List of domains that meet the threshold with their scores
        """
        # Batch process in groups of 100 (API limit)
        results = []

        for i in range(0, len(domains), 100):
            batch = domains[i:i+100]
            response = self.api.get_pagerank(batch)

            if response['success']:
                for item in response['results']:
                    pr_score = item.get('page_rank_decimal')
                    if pr_score is not None and pr_score >= min_pagerank:
                        results.append({
                            'domain': item['domain'],
                            'page_rank_decimal': pr_score,
                            'page_rank_integer': item.get('page_rank_integer'),
                            'rank': item.get('rank')
                        })

        # Sort by PageRank (descending)
        results.sort(key=lambda x: x['page_rank_decimal'], reverse=True)
        return results

    def get_pagerank_scores(self, domains: List[str]) -> Dict:
        """
        Get PageRank scores for domains (no filtering).

        Args:
            domains: List of domains (max 100 per call)

        Returns:
            Dict with success, results, credits_used, credits_remaining
        """
        return self.api.get_pagerank(domains)

    def categorize_by_authority(self, domains: List[str]) -> Dict[str, List[str]]:
        """
        Categorize domains by authority level.

        Args:
            domains: List of domains to categorize

        Returns:
            Dict with categories:
                - extremely_high (8.0+)
                - very_high (6.0-7.9)
                - high (4.0-5.9)
                - moderate (2.0-3.9)
                - low (1.0-1.9)
                - very_low (0.1-0.9)
                - no_data (None/0)
        """
        categories = {
            'extremely_high': [],
            'very_high': [],
            'high': [],
            'moderate': [],
            'low': [],
            'very_low': [],
            'no_data': []
        }

        # Process in batches
        for i in range(0, len(domains), 100):
            batch = domains[i:i+100]
            response = self.api.get_pagerank(batch)

            if response['success']:
                for item in response['results']:
                    domain = item['domain']
                    score = item.get('page_rank_decimal')

                    if score is None or score == 0:
                        categories['no_data'].append(domain)
                    elif score >= 8.0:
                        categories['extremely_high'].append(domain)
                    elif score >= 6.0:
                        categories['very_high'].append(domain)
                    elif score >= 4.0:
                        categories['high'].append(domain)
                    elif score >= 2.0:
                        categories['moderate'].append(domain)
                    elif score >= 1.0:
                        categories['low'].append(domain)
                    else:
                        categories['very_low'].append(domain)

        return categories


class TrancoRankingFilter:
    """
    Tranco top sites ranking filter.

    Free, research-oriented ranking that combines multiple top lists.

    Use for: Getting top N domains, checking if domain is in top rankings
    """

    def __init__(self):
        if not TRANCO_AVAILABLE:
            raise ImportError("Tranco CLI not available. Check categorizer-filterer/tranco_cli.py")

        self.api = TrancoAPI()

    def get_top_domains(self, count: int = 1000, list_id: Optional[str] = None) -> Dict:
        """
        Get top N domains from Tranco ranking.

        Args:
            count: Number of domains to return
            list_id: Optional specific list ID (defaults to latest)

        Returns:
            Dict with success, domains, list_id, date
        """
        return self.api.get_top_domains(count, list_id)

    def filter_by_ranking(self, domains: List[str], max_rank: int = 10000) -> List[Dict]:
        """
        Filter domains by maximum ranking threshold.

        Args:
            domains: List of domains to check
            max_rank: Maximum acceptable rank (lower is better)

        Returns:
            List of domains within threshold with their ranks
        """
        results = []

        for domain in domains:
            response = self.api.get_domain_rank(domain)

            if response['success'] and response['rank']:
                if response['rank'] <= max_rank:
                    results.append({
                        'domain': domain,
                        'rank': response['rank'],
                        'list_id': response.get('list_id'),
                        'date': response.get('date')
                    })

        # Sort by rank (ascending - lower is better)
        results.sort(key=lambda x: x['rank'])
        return results

    def check_domain_rank(self, domain: str, list_id: Optional[str] = None) -> Dict:
        """
        Check ranking for a single domain.

        Args:
            domain: Domain to check
            list_id: Optional specific list ID

        Returns:
            Dict with success, domain, rank, list_id, date
        """
        return self.api.get_domain_rank(domain, list_id)

    def search_domains(self, query: str, list_id: Optional[str] = None) -> Dict:
        """
        Search for domains containing keyword.

        Args:
            query: Search keyword
            list_id: Optional specific list ID

        Returns:
            Dict with success, query, results, total_found
        """
        return self.api.search_domains(query, list_id)


class CloudflareRadarFilter:
    """
    Cloudflare Radar domain intelligence filter.

    Provides internet traffic insights and domain rankings.

    Note: Some features require API token (free)
    """

    def __init__(self, api_token: Optional[str] = None):
        if not CLOUDFLARE_AVAILABLE:
            raise ImportError("Cloudflare Radar CLI not available. Check categorizer-filterer/cloudflare_radar_cli.py")

        self.api = CloudflareRadarAPI(api_token)

    def get_top_domains(self, limit: int = 100, location: Optional[str] = None,
                       date_range: Optional[str] = None) -> Dict:
        """
        Get top domains by traffic.

        Args:
            limit: Number of domains (max 1000)
            location: 2-letter country code (e.g., 'US', 'LY')
            date_range: Date range filter

        Returns:
            Dict with success, domains, meta, location
        """
        return self.api.get_top_domains(limit, location, date_range)

    def get_domain_info(self, domain: str) -> Dict:
        """
        Get information about specific domain.

        Args:
            domain: Domain to analyze

        Returns:
            Dict with success, domain, data (popularity, categories, security)
        """
        return self.api.get_domain_info(domain)

    def get_trending_domains(self, limit: int = 50) -> Dict:
        """
        Get trending domains.

        Args:
            limit: Number of trending domains

        Returns:
            Dict with success, domains, total_returned
        """
        return self.api.get_trending_domains(limit)

    def filter_by_traffic_rank(self, domains: List[str], max_rank: int = 10000) -> List[Dict]:
        """
        Filter domains by traffic ranking.

        Args:
            domains: List of domains to check
            max_rank: Maximum acceptable rank

        Returns:
            List of domains within threshold
        """
        results = []

        for domain in domains:
            response = self.api.get_domain_info(domain)

            if response['success']:
                data = response.get('data', {})
                if 'popularity' in data:
                    rank = data['popularity'].get('rank')
                    if rank and rank <= max_rank:
                        results.append({
                            'domain': domain,
                            'rank': rank,
                            'traffic_score': data['popularity'].get('score'),
                            'categories': data.get('categories', [])
                        })

        # Sort by rank (ascending)
        results.sort(key=lambda x: x['rank'])
        return results


class DomainFilters:
    """
    Unified domain filtering interface.

    Aggregates all discovery CLIs into a single interface for filtering domains.
    """

    def __init__(self,
                 bigquery_project_id: Optional[str] = None,
                 openpagerank_api_key: Optional[str] = None,
                 cloudflare_api_token: Optional[str] = None):
        """
        Initialize domain filters with API credentials.

        Args:
            bigquery_project_id: Google Cloud project ID for BigQuery
            openpagerank_api_key: OpenPageRank API key (200K free/month)
            cloudflare_api_token: Cloudflare API token (free)
        """
        # Try to initialize each service, gracefully handle missing dependencies
        try:
            self.bigquery = BigQueryDiscovery(bigquery_project_id) if BIGQUERY_AVAILABLE else None
        except ImportError:
            self.bigquery = None

        try:
            self.pagerank = OpenPageRankFilter(openpagerank_api_key) if OPENPAGERANK_AVAILABLE else None
        except ImportError:
            self.pagerank = None

        try:
            self.tranco = TrancoRankingFilter() if TRANCO_AVAILABLE else None
        except ImportError:
            self.tranco = None

        try:
            self.cloudflare = CloudflareRadarFilter(cloudflare_api_token) if CLOUDFLARE_AVAILABLE else None
        except ImportError:
            self.cloudflare = None

    async def discover_domains_parallel(self,
                                       tlds: Optional[List[str]] = None,
                                       keywords: Optional[List[str]] = None,
                                       min_pagerank: float = 2.0,
                                       max_tranco_rank: int = 100000,
                                       limit_per_source: int = 1000) -> Dict[str, List[Dict]]:
        """
        Run all discovery sources in parallel.

        Args:
            tlds: TLD filters (e.g., ['.ly', '.ru'])
            keywords: Keyword filters
            min_pagerank: Minimum PageRank threshold
            max_tranco_rank: Maximum Tranco rank
            limit_per_source: Max results per source

        Returns:
            Dict with results from each source:
                - bigquery: List of domains from BigQuery
                - tranco: List of top domains
                - cloudflare: List of traffic-ranked domains
                - filtered_by_pagerank: Domains meeting PR threshold
        """
        results = {
            'bigquery': [],
            'tranco': [],
            'cloudflare': [],
            'filtered_by_pagerank': []
        }

        tasks = []

        # Tranco top domains (always free)
        if self.tranco:
            tasks.append(self._get_tranco_domains(limit_per_source))

        # Cloudflare top domains (free with token)
        if self.cloudflare:
            tasks.append(self._get_cloudflare_domains(limit_per_source))

        # BigQuery discovery (requires project setup)
        if self.bigquery and keywords:
            for keyword in keywords:
                tasks.append(self._get_bigquery_tech_domains(keyword, limit_per_source))

        # Run all discovery sources in parallel
        if tasks:
            parallel_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Aggregate results
            for result in parallel_results:
                if isinstance(result, dict) and 'source' in result:
                    source = result['source']
                    if source in results:
                        results[source].extend(result.get('domains', []))

        # Filter by PageRank if available
        if self.pagerank:
            all_domains = []
            for source_domains in results.values():
                all_domains.extend([d.get('domain', d) if isinstance(d, dict) else d for d in source_domains])

            # Deduplicate
            unique_domains = list(set(all_domains))

            # Filter by PageRank
            pr_filtered = self.pagerank.filter_by_pagerank(unique_domains, min_pagerank)
            results['filtered_by_pagerank'] = pr_filtered

        return results

    async def _get_tranco_domains(self, limit: int) -> Dict:
        """Get top domains from Tranco."""
        await asyncio.sleep(0)  # Make async
        result = self.tranco.get_top_domains(limit)

        if result['success']:
            return {
                'source': 'tranco',
                'domains': [{'domain': d, 'rank': i+1} for i, d in enumerate(result.get('domains', []))]
            }
        return {'source': 'tranco', 'domains': []}

    async def _get_cloudflare_domains(self, limit: int) -> Dict:
        """Get top domains from Cloudflare Radar."""
        await asyncio.sleep(0)  # Make async
        result = self.cloudflare.get_top_domains(limit)

        if result['success']:
            return {
                'source': 'cloudflare',
                'domains': result.get('domains', [])
            }
        return {'source': 'cloudflare', 'domains': []}

    async def _get_bigquery_tech_domains(self, technology: str, limit: int) -> Dict:
        """Get domains using specific technology from BigQuery."""
        await asyncio.sleep(0)  # Make async
        result = self.bigquery.discover_by_technology(technology, limit)

        if result['success']:
            return {
                'source': 'bigquery',
                'domains': result.get('results', [])
            }
        return {'source': 'bigquery', 'domains': []}
