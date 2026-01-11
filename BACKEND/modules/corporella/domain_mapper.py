import asyncio
import json
from urllib.parse import urlparse, parse_qsl, urlencode
import aiohttp
import os
import logging
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UnifiedDomainMapper:
    def __init__(self, domain):
        self.domain = self.normalize_domain(domain)
        self.domain_name = urlparse(self.domain).netloc
        self.paths = defaultdict(lambda: {
            'internal_links': set(),
            'external_links': set(),
            'backlinks': set(),
            'archives': set(),
            'wayback_dates': set()
        })
        # API keys from environment variables
        self.firecrawl_key = os.getenv("FIRECRAWL_API_KEY")
        self.ahrefs_key = os.getenv("AHREFS_API_KEY")

    def normalize_domain(self, domain):
        if not domain.startswith(('http://', 'https://')):
            domain = 'https://' + domain
        return domain

    def normalize_path(self, url):
        parsed = urlparse(url)
        path = parsed.path or '/'
        # Include query parameters if needed
        query = '?' + urlencode(sorted(parse_qsl(parsed.query))) if parsed.query else ''
        return path + query

    async def collect_firecrawl_data(self):
        """Collect current internal structure using Firecrawl"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.firecrawl.dev/v1/map",
                    headers={
                        "Authorization": f"Bearer {self.firecrawl_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "url": self.domain,
                        "ignoreSitemap": False,
                        "includeSubdomains": True,
                        "limit": 5000
                    }
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        for url in data.get('links', []):
                            if self.domain_name in url:
                                from_path = self.normalize_path(url)

                                # Scrape individual page for its links
                                async with session.post(
                                    "https://api.firecrawl.dev/v1/crawl",
                                    headers={
                                        "Authorization": f"Bearer {self.firecrawl_key}",
                                        "Content-Type": "application/json"
                                    },
                                    json={
                                        "url": url,
                                        "scrapeOptions": {"formats": ["links"]}
                                    }
                                ) as page_response:
                                    if page_response.status == 200:
                                        page_data = await page_response.json()
                                        for link in page_data.get('links', []):
                                            if self.domain_name in link:
                                                to_path = self.normalize_path(link)
                                                self.paths[from_path]['internal_links'].add(to_path)
                                            else:
                                                self.paths[from_path]['external_links'].add(link)

        except Exception as e:
            logger.error(f"Firecrawl error: {str(e)}")

    async def collect_commoncrawl_data(self):
        """Collect historical data from CommonCrawl"""
        crawls = await self.get_crawl_indexes()

        async with aiohttp.ClientSession() as session:
            for crawl in crawls[:5]:  # Limit to recent crawls
                try:
                    async with session.get(
                        f"https://index.commoncrawl.org/{crawl}-index?url=*.{self.domain_name}&output=json"
                    ) as response:
                        if response.status == 200:
                            async for line in response.content:
                                if line:
                                    data = json.loads(line.decode('utf-8'))
                                    path = self.normalize_path(data['url'])
                                    self.paths[path]['archives'].add(crawl)

                except Exception as e:
                    logger.error(f"CommonCrawl error for {crawl}: {str(e)}")

    async def get_crawl_indexes(self):
        """Get list of CommonCrawl indexes"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://index.commoncrawl.org/collinfo.json") as response:
                    if response.status == 200:
                        data = await response.json()
                        return [crawl['id'] for crawl in data]
        except Exception as e:
            logger.error(f"Error getting crawl indexes: {str(e)}")
            return []

    async def collect_wayback_data(self):
        """Collect Wayback Machine archives"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://web.archive.org/cdx/search/cdx?url={self.domain_name}/*&output=json"
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        for item in data[1:]:  # Skip header row
                            path = self.normalize_path(item[2])
                            timestamp = item[1]
                            self.paths[path]['wayback_dates'].add(timestamp)

        except Exception as e:
            logger.error(f"Wayback error: {str(e)}")

    async def collect_backlinks_data(self):
        """Collect backlinks data from Ahrefs"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://apiv2.ahrefs.com",
                    params={
                        'from': 'backlinks_new_lost',
                        'target': self.domain_name,
                        'token': self.ahrefs_key,
                        'limit': 1000,
                        'output': 'json',
                    }
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        for item in data.get('refpages', []):
                            target_path = self.normalize_path(item['url_to'])
                            self.paths[target_path]['backlinks'].add(item['url_from'])

        except Exception as e:
            logger.error(f"Ahrefs error: {str(e)}")

    async def collect_all_data(self):
        """Collect all data"""
        tasks = [
            self.collect_firecrawl_data(),
            self.collect_commoncrawl_data(),
            self.collect_wayback_data(),
            self.collect_backlinks_data()
        ]
        await asyncio.gather(*tasks)

    def get_visualization_data(self):
        """Convert collected data to visualization format"""
        nodes = []
        edges = []

        # Add nodes
        for path in self.paths:
            nodes.append({
                'id': path,
                'label': path,
                'archives': len(self.paths[path]['archives']),
                'wayback': len(self.paths[path]['wayback_dates']),
                'backlinks': len(self.paths[path]['backlinks'])
            })

        # Add edges
        for from_path in self.paths:
            # Internal links
            for to_path in self.paths[from_path]['internal_links']:
                edges.append({
                    'from': from_path,
                    'to': to_path,
                    'type': 'internal'
                })

            # External links (simplified)
            if self.paths[from_path]['external_links']:
                edges.append({
                    'from': from_path,
                    'to': f"{from_path}_external",
                    'type': 'external'
                })
                nodes.append({
                    'id': f"{from_path}_external",
                    'label': f"External Links ({len(self.paths[from_path]['external_links'])})",
                    'type': 'external'
                })

        return {'nodes': nodes, 'edges': edges}

async def main():
    domain = input("Enter domain to analyze: ")
    mapper = UnifiedDomainMapper(domain)
    await mapper.collect_all_data()

    # Save data for visualization
    with open('domain_map_data.json', 'w') as f:
        json.dump(mapper.get_visualization_data(), f, indent=2)

    print("Data collection complete. Run the visualization component to view results.")

if __name__ == "__main__":
    asyncio.run(main())