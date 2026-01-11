#!/usr/bin/env python3
"""
LinkedIn Company Search Integration
Searches LinkedIn for company profiles and information
"""

import urllib.parse
import logging
from typing import Dict, List, Any, Optional
import asyncio
import sys
from pathlib import Path

# Add parent directory for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

logger = logging.getLogger(__name__)


class LinkedInCompanySearch:
    """
    Search LinkedIn for company profiles and information
    """

    # LinkedIn URL structures
    BASE_URL = "https://www.linkedin.com/uas/login?session_redirect="
    COMPANY_SEARCH_URL = "https://www.linkedin.com/search/results/companies/?"
    COMPANY_PROFILE_URL = "https://www.linkedin.com/company/"

    def __init__(self):
        """Initialize LinkedIn company search"""
        self.linkedin_engine = None
        try:
            # Try to import the LinkedIn search aggregator
            from Social_Media.linkedin_engine import LinkedInSearchAggregator
            self.linkedin_engine = LinkedInSearchAggregator()
            logger.info("LinkedIn search engine initialized")
        except ImportError:
            logger.warning("LinkedIn search engine not available")

    def build_company_search_url(self, company_name: str, **kwargs) -> str:
        """
        Build LinkedIn company search URL.

        Args:
            company_name: Company name to search
            **kwargs: Additional parameters like industry, location, size

        Returns:
            LinkedIn company search URL with login redirect
        """
        query_params = []

        # Main keywords parameter
        query_params.append(f"keywords={urllib.parse.quote(company_name)}")

        # Add industry filter if specified
        if kwargs.get('industry'):
            query_params.append(f"industry={urllib.parse.quote(kwargs['industry'])}")

        # Add location filter if specified
        if kwargs.get('location'):
            query_params.append(f"location={urllib.parse.quote(kwargs['location'])}")

        # Add company size filter if specified
        if kwargs.get('size'):
            # LinkedIn uses codes like B (1-10), C (11-50), D (51-200), E (201-500), F (501-1000), etc.
            size_map = {
                'small': 'B,C',  # 1-50 employees
                'medium': 'D,E',  # 51-500 employees
                'large': 'F,G,H',  # 500+ employees
            }
            if kwargs['size'].lower() in size_map:
                query_params.append(f"companySize={size_map[kwargs['size'].lower()]}")

        # Build the search URL
        search_params = "&".join(query_params)
        full_search_url = self.COMPANY_SEARCH_URL + search_params

        # URL encode the redirect URL for the login page
        encoded_redirect = urllib.parse.quote(full_search_url, safe='')

        final_url = self.BASE_URL + encoded_redirect

        logger.info(f"Built LinkedIn company search URL for: {company_name}")
        logger.debug(f"Final URL: {final_url}")

        return final_url

    def build_company_profile_url(self, company_slug: str) -> str:
        """
        Build direct LinkedIn company profile URL.

        Args:
            company_slug: LinkedIn company slug (e.g., 'microsoft', 'apple')

        Returns:
            Direct LinkedIn company profile URL
        """
        return f"{self.COMPANY_PROFILE_URL}{company_slug}"

    async def search_company_profiles(self, company_name: str, limit: int = 20) -> Dict[str, Any]:
        """
        Search for company profiles on LinkedIn using search engines.

        Args:
            company_name: Company name to search for
            limit: Maximum number of results

        Returns:
            Dictionary with search results
        """
        results = {
            'company_profiles': [],
            'related_pages': [],
            'total_results': 0,
            'search_url': self.build_company_search_url(company_name)
        }

        if not self.linkedin_engine:
            logger.warning("LinkedIn engine not available, returning search URL only")
            return results

        try:
            # Search for LinkedIn company pages
            search_results = await self.linkedin_engine.search_linkedin(
                f"{company_name} company about",
                max_results_per_engine=limit
            )

            # Process and categorize results
            for result in search_results:
                url = result.get('url', '')
                title = result.get('title', '')
                snippet = result.get('snippet', '')

                # Categorize LinkedIn URLs
                if '/company/' in url:
                    # Company profile page
                    results['company_profiles'].append({
                        'url': url,
                        'title': title,
                        'snippet': snippet,
                        'type': 'company_profile',
                        'source': result.get('source', 'linkedin')
                    })
                elif '/in/' in url:
                    # Skip people profiles in company search
                    continue
                elif 'linkedin.com' in url:
                    # Other LinkedIn pages (posts, articles, etc.)
                    results['related_pages'].append({
                        'url': url,
                        'title': title,
                        'snippet': snippet,
                        'type': 'related',
                        'source': result.get('source', 'linkedin')
                    })

            results['total_results'] = len(results['company_profiles']) + len(results['related_pages'])

            logger.info(f"Found {len(results['company_profiles'])} company profiles for: {company_name}")

        except Exception as e:
            logger.error(f"Error searching LinkedIn company profiles: {e}")

        return results

    def extract_company_slug(self, company_name: str) -> str:
        """
        Try to generate a LinkedIn company slug from company name.

        Args:
            company_name: Company name

        Returns:
            Probable LinkedIn slug
        """
        # Common company slug patterns
        slug = company_name.lower()

        # Remove common suffixes
        suffixes = [' inc', ' inc.', ' incorporated', ' corp', ' corp.', ' corporation',
                   ' ltd', ' ltd.', ' limited', ' llc', ' l.l.c.', ' plc', ' p.l.c.',
                   ' gmbh', ' ag', ' sa', ' s.a.', ' nv', ' n.v.', ' bv', ' b.v.']

        for suffix in suffixes:
            if slug.endswith(suffix):
                slug = slug[:-len(suffix)]
                break

        # Replace spaces and special characters
        slug = slug.replace(' & ', '-')
        slug = slug.replace('&', '-')
        slug = slug.replace(' ', '-')
        slug = slug.replace('.', '')
        slug = slug.replace(',', '')
        slug = slug.replace("'", '')

        # Remove multiple dashes
        while '--' in slug:
            slug = slug.replace('--', '-')

        # Remove leading/trailing dashes
        slug = slug.strip('-')

        return slug

    def generate_linkedin_urls(self, company_name: str) -> List[str]:
        """
        Generate multiple possible LinkedIn URLs for a company.

        Args:
            company_name: Company name

        Returns:
            List of possible LinkedIn URLs
        """
        urls = []

        # Add search URL
        urls.append(self.build_company_search_url(company_name))

        # Generate possible profile URLs
        slug = self.extract_company_slug(company_name)
        if slug:
            urls.append(self.build_company_profile_url(slug))

            # Try variations
            if '-' in slug:
                # Try without dashes
                urls.append(self.build_company_profile_url(slug.replace('-', '')))

            # Try first word only for simple names
            first_word = slug.split('-')[0]
            if first_word != slug:
                urls.append(self.build_company_profile_url(first_word))

        return urls

    def format_for_corporate_search(self, results: Dict[str, Any]) -> List[Dict]:
        """
        Format LinkedIn results for integration with corporate search.

        Args:
            results: Raw LinkedIn search results

        Returns:
            Formatted list for corporate search integration
        """
        formatted = []

        # Format company profiles
        for profile in results.get('company_profiles', []):
            formatted.append({
                'type': 'social_profile',
                'platform': 'LinkedIn',
                'profile_type': 'Company',
                'url': profile.get('url'),
                'title': profile.get('title', ''),
                'description': profile.get('snippet', ''),
                'confidence': 0.9 if '/company/' in profile.get('url', '') else 0.7,
                'data_source': 'LinkedIn Company Search'
            })

        # Add direct search URL as a result
        if results.get('search_url'):
            formatted.append({
                'type': 'search_link',
                'platform': 'LinkedIn',
                'search_type': 'Company Search',
                'url': results.get('search_url'),
                'title': "LinkedIn Company Search",
                'description': "Direct LinkedIn search for company profiles",
                'confidence': 1.0,
                'data_source': 'LinkedIn URL Builder'
            })

        return formatted


def test_linkedin_company_search():
    """Test the LinkedIn company search functionality"""

    searcher = LinkedInCompanySearch()

    test_companies = ["Apple", "Microsoft", "Tesla", "OpenAI"]

    for company in test_companies:
        print(f"\n{'='*60}")
        print(f"Testing LinkedIn search for: {company}")
        print('='*60)

        # Test URL building
        search_url = searcher.build_company_search_url(company)
        print(f"\nSearch URL: {search_url}")

        # Test slug extraction
        slug = searcher.extract_company_slug(company)
        print(f"Company slug: {slug}")
        profile_url = searcher.build_company_profile_url(slug)
        print(f"Profile URL: {profile_url}")

        # Test URL generation
        urls = searcher.generate_linkedin_urls(company)
        print(f"\nGenerated URLs:")
        for url in urls:
            print(f"  - {url}")

        # Test async search (if engine available)
        if searcher.linkedin_engine:
            print(f"\nSearching for profiles...")
            loop = asyncio.get_event_loop()
            results = loop.run_until_complete(
                searcher.search_company_profiles(company, limit=5)
            )

            print(f"Found {results['total_results']} results")
            if results['company_profiles']:
                print(f"\nCompany Profiles:")
                for profile in results['company_profiles'][:3]:
                    print(f"  - {profile['title']}")
                    print(f"    {profile['url']}")

    print("\n" + '='*60)
    print("LinkedIn Company Search Test Complete")
    print("="*60)


if __name__ == "__main__":
    test_linkedin_company_search()
