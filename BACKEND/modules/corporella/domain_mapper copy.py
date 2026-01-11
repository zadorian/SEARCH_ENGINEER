import asyncio
import json
from urllib.parse import urlparse, parse_qsl, urlencode, urljoin
import aiohttp
import os
import logging
from collections import defaultdict
import sys
from graphviz import Digraph
import colorsys
from datetime import datetime
import re
import traceback
from pathlib import Path
from bs4 import BeautifulSoup
import time

def clean_url(url):
    """Clean the URL to be used as a node identifier in Graphviz."""
    return re.sub(r'\W+', '_', url)

# Add the project root to sys.path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

# Debug - Print directory contents
print("Files in current directory:")
print(os.listdir(project_root))

# Try to import
try:
    from firecrawl_outlinks import FirecrawlApp  # Try outlinks first
except ImportError:
    try:
        from firecrawl_indom2 import FirecrawlApp  # Try indom2
    except ImportError:
        print("\nDebug - Current sys.path:")
        print(sys.path)
        print(f"\nDebug - Looking for FirecrawlApp in: {project_root}")
        raise

# Rest of your imports
from allDom.alldom2 import collect_all_urls
from backlinks import fetch_backlinks
from outlinks import analyze_outlinks
from Output.outlinks_output import format_outlinks_results, clean_url

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UnifiedDomainMapper:
    def __init__(self, domain):
        self.domain = self.normalize_domain(domain)
        self.domain_name = urlparse(self.domain).netloc
        self.paths = defaultdict(lambda: {
            'internal_links': {
                'incoming': defaultdict(set),
                'outgoing': defaultdict(set)
            },
            'external_links': {
                'incoming': defaultdict(lambda: {'timestamp': '', 'status_code': 0}),
                'outgoing': {
                    'current': defaultdict(lambda: {'timestamp': '', 'status_code': 0}),
                    'historical': defaultdict(lambda: defaultdict(lambda: {'timestamp': '', 'status_code': 0}))
                }
            }
        })
        
        # Load API keys from environment or config file
        self.firecrawl_key = os.getenv("FIRECRAWL_API_KEY", "fc-64eb8af5ed3944d99bc1c0411ee12bc2")  # Default key
        self.ahrefs_key = os.getenv("AHREFS_API_KEY", "001VsvfrsqI3boNHFLs-XUTfgIkSm_jbrash5Cvh")  # Default key
        self.rate_limiter = asyncio.Semaphore(5)  # Limit to 5 concurrent requests

    def normalize_domain(self, domain):
        """Normalize domain name for consistency"""
        domain = domain.lower()  # Convert to lowercase
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
        """Collect current internal structure using Firecrawl with rate limiting"""
        try:
            async with aiohttp.ClientSession() as session:
                async with self.rate_limiter:  # Add rate limiting
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
                            timestamp = datetime.now().isoformat()
                            
                            for url in data.get('links', []):
                                if self.domain_name in url:
                                    from_path = self.normalize_path(url)
                                    
                                    try:
                                        async with self.rate_limiter:  # Rate limiting for each request
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
                                                        if self.domain_name not in link:
                                                            self.paths[from_path]['external_links']['outgoing']['current'][link] = {
                                                                'timestamp': timestamp,
                                                                'status_code': page_response.status
                                                            }
                                    except Exception as e:
                                        logger.error(f"Error crawling page {url}: {str(e)}")
                                        continue
                        else:
                            logger.error(f"Firecrawl API error: {response.status}")
        except Exception as e:
            logger.error(f"Firecrawl error: {str(e)}")

    async def collect_commoncrawl_data(self):
        """Collect historical data from CommonCrawl with specific URLs"""
        crawls = await self.get_crawl_indexes()

        async with aiohttp.ClientSession() as session:
            for crawl in crawls[:5]:
                try:
                    async with session.get(
                        f"https://index.commoncrawl.org/{crawl}-index?url=*.{self.domain_name}&output=json"
                    ) as response:
                        if response.status == 200:
                            async for line in response.content:
                                if line:
                                    data = json.loads(line.decode('utf-8'))
                                    source_url = data['url']
                                    
                                    # Get the actual page content to extract links
                                    if data.get('filename') and data.get('offset') and data.get('length'):
                                        content_url = f"https://data.commoncrawl.org/{data['filename']}"
                                        headers = {'Range': f"bytes={data['offset']}-{data['offset']+data['length']-1}"}
                                        
                                        async with session.get(content_url, headers=headers) as content_response:
                                            if content_response.status == 200:
                                                content = await content_response.text()
                                                links = self.extract_links_from_html(content)
                                                
                                                year = crawl.split('-')[1][:4]
                                                for link in links:
                                                    self.paths[source_url]['external_links']['outgoing']['historical'][year].add(link)
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

    def clean_url_for_display(self, url):
        """Clean URLs by removing wayback prefixes and normalizing"""
        url = url.lower().strip()
        
        # Handle wayback URLs
        if 'web.archive.org/web/' in url or '/web/20' in url:
            try:
                # Extract the actual URL after timestamp
                parts = url.split('/web/')[1]
                actual_url = parts[14:].split('/', 1)[1]
                return self.normalize_url(actual_url)
            except Exception as e:
                return url
        
        # Handle standard URLs
        if url.startswith(('http://', 'https://', 'www.')):
            parsed = urlparse(url)
            return parsed.netloc + parsed.path
        
        return url

    def clean_wayback_url(self, url):
        """Clean Wayback Machine URLs to get the actual target URL"""
        if 'web.archive.org/web/' in url:
            # Extract the actual URL after the timestamp
            parts = url.split('web.archive.org/web/')
            if len(parts) > 1:
                timestamp_and_url = parts[1]
                # Remove the timestamp (first 14 characters) and any http/https prefix
                actual_url = timestamp_and_url[14:].replace('http://', '').replace('https://', '')
                return actual_url
        return url

    def normalize_url(self, url):
        """Normalize URLs by removing www, http/https, and trailing slashes"""
        url = url.lower()
        url = url.replace('http://', '').replace('https://', '')
        url = url.replace('www.', '')
        url = url.rstrip('/')
        return url

    async def collect_wayback_data(self):
        """Collect Wayback Machine archives with proper encoding handling"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:  # Set a 60-second timeout
                async with session.get(
                    f"https://web.archive.org/cdx/search/cdx?url={self.domain_name}/*&output=json&fl=timestamp,original"
                ) as response:
                    if response.status == 200:
                        raw_data = await response.content.read()
                        try:
                            data = json.loads(raw_data.decode('utf-8'))
                        except UnicodeDecodeError:
                            data = json.loads(raw_data.decode('latin-1'))
                            
                        for item in data[1:]:  # Skip header row
                            timestamp, original_url = item[0], item[1]
                            clean_original_url = self.clean_url_for_display(original_url)
                            
                            # Get the actual links from this snapshot
                            snapshot_url = f"https://web.archive.org/web/{timestamp}/{original_url}"
                            try:
                                async with session.get(snapshot_url) as snapshot_response:
                                    if snapshot_response.status == 200:
                                        raw_html = await snapshot_response.content.read()
                                        try:
                                            html = raw_html.decode('utf-8')
                                        except UnicodeDecodeError:
                                            html = raw_html.decode('latin-1')
                                            
                                        links = self.extract_links_from_html(html)
                                        year = timestamp[:4]
                                        for link in links:
                                            clean_link = self.clean_url_for_display(link)
                                            if clean_link != self.domain_name:
                                                self.paths[clean_original_url]['external_links']['outgoing']['historical'][year][clean_link] = {
                                                    'timestamp': timestamp,
                                                    'status_code': snapshot_response.status
                                                }
                            except Exception as e:
                                logger.error(f"Error processing snapshot {snapshot_url}: {str(e)}")
                                continue
                            
        except Exception as e:
            logger.error(f"Wayback data collection error: {str(e)}")

    async def collect_backlinks_data(self):
        """Collect backlinks data with proper error handling"""
        try:
            backlinks_data, _ = fetch_backlinks(self.domain_name)
            for backlink in backlinks_data:
                source_url = backlink.get('source_url', '')
                if source_url:
                    clean_source = self.clean_url_for_display(source_url)
                    self.paths['/']['external_links']['incoming'][clean_source] = {
                        'domain_rating': backlink.get('domain_rating', 0),
                        'first_seen': backlink.get('first_seen', ''),
                        'timestamp': datetime.now().isoformat()
                    }
        except Exception as e:
            logger.error(f"Backlinks error: {str(e)}")

    async def collect_outlinks_data(self):
        """Collect outlinks data using outlinks.py"""
        try:
            outlinks_data = await analyze_outlinks(self.domain)
            if isinstance(outlinks_data, dict):  # Ensure it's a dict
                # Process current outlinks
                for path, links in outlinks_data.get('current', {}).items():
                    if isinstance(links, (list, set)):  # Ensure links is iterable
                        for link in links:
                            self.paths[path]['external_links']['outgoing']['current'][link] = set()
                
                # Process historical outlinks
                for path, years in outlinks_data.get('historical', {}).items():
                    if isinstance(years, dict):  # Ensure years is a dict
                        for year, links in years.items():
                            if isinstance(links, (list, set)):  # Ensure links is iterable
                                for link in links:
                                    self.paths[path]['external_links']['outgoing']['historical'][year].add(link)
        except Exception as e:
            logger.error(f"Outlinks error: {str(e)}")

    async def collect_related_urls(self):
        """Collect all related URLs using alldom2"""
        try:
            related_urls = collect_all_urls(self.domain)
            for url in related_urls:
                path = self.normalize_path(url)
                self.paths[path]['internal_links']['outgoing'][url] = set()
        except Exception as e:
            logger.error(f"Related URLs error: {str(e)}")

    async def collect_all_data(self):
        """Collect and save ALL relationships"""
        try:
            print("\n1. Collecting current site structure...")
            await self.collect_current_site_structure()
            
            print("\n2. Collecting backlinks...")
            await self.collect_backlinks_data()
            
            print("\n3. Collecting current outlinks...")
            await self.collect_outlinks_data()
            
            print("\n4. Collecting historical data...")
            await self.collect_wayback_data()
            
            print("\nSaving complete link data to JSON...")
            self.save_link_data()
            
            print("\nGenerating visualization...")
            self.visualize_from_json(self.paths)
            
            print("\nDone!")

        except Exception as e:
            print(f"Error: {str(e)}")
            traceback.print_exc()

    def get_summary(self):
        """Get a detailed summary of all link relationships"""
        summary = {
            'external_relationships': {
                'incoming': {},
                'outgoing': {
                    'current': defaultdict(set),
                    'historical': defaultdict(lambda: defaultdict(set))
                }
            }
        }

        # Process backlinks (incoming) with full details
        for domain, details in self.paths['/']['external_links']['incoming'].items():
            summary['external_relationships']['incoming'][domain] = {
                'domain': domain,
                'first_seen': next((d[1] for d in details), ''),
                'domain_rating': next((d[2] for d in details), 0),
                'paths': list(details)  # Include all paths where backlink appears
            }
        
        # Process current outlinks with source paths
        for path, data in self.paths.items():
            for target in data['external_links']['outgoing']['current']:
                summary['external_relationships']['outgoing']['current'][target].add(path)
        
        # Process historical outlinks with source paths and timestamps
        for path, data in self.paths.items():
            for year, links in data['external_links']['outgoing']['historical'].items():
                for link in links:
                    summary['external_relationships']['outgoing']['historical'][year][link].add(path)

        return summary

    def save_link_data(self):
        """Save ALL relationships to JSON"""
        data = {
            "nodes": [],
            "edges": []
        }
        
        # 1. Add current site structure
        for path in self.paths:
            data["nodes"].append({"id": path, "type": "current"})
        
        # 2. Add backlinks from Ahrefs
        if hasattr(self, 'backlinks_data'):
            for domain in self.backlinks_data.get("refdomains", []):
                ref_domain = domain["refdomain"]
                data["nodes"].append({"id": ref_domain, "type": "backlink"})
                data["edges"].append({
                    "source": ref_domain,
                    "target": self.domain_name,
                    "year": domain["first_seen"][:4],
                    "type": "backlink"
                })
        
        # 3. Add outlinks (both current and historical)
        if hasattr(self, 'outlinks_data'):
            for source_url, targets in self.outlinks_data.items():
                for target in targets:
                    if isinstance(target, dict):  # Historical data
                        data["edges"].append({
                            "source": source_url,
                            "target": target["url"],
                            "year": target["year"],
                            "type": "outlink"
                        })
                    else:  # Current data
                        data["edges"].append({
                            "source": source_url,
                            "target": target,
                            "year": "current",
                            "type": "outlink"
                        })
                    
        # Save to JSON
        with open(f"domain_map_data_{time.strftime('%Y%m%d_%H%M%S')}.json", 'w') as f:
            json.dump(data, f, indent=2)
        
        return data

    def format_results(self, json_data):
        """Format the results into a readable string and build complete JSON"""
        try:
            # Debug the incoming data structure
            print("\nDEBUG - Raw JSON structure:")
            print(json.dumps(json_data, indent=2))
            
            # Get the main domain
            target_urls = json_data.get("target_urls", {})
            if not target_urls:
                raise ValueError("No target URLs found in data")
            
            domain = list(target_urls.keys())[0]
            domain_data = target_urls[domain]
            
            # Initialize the complete JSON structure
            complete_json = {
                "domain": domain,
                "target_urls": {
                    domain: {
                        "internal_links": {
                            "current": domain_data.get("internal_links", {}).get("current", []),
                            "historical": domain_data.get("internal_links", {}).get("historical", [])
                        },
                        "external_outgoing": {
                            "current": [
                                [link["to"], {"date": link["date"]}] 
                                for link in domain_data.get("external_outgoing", {}).get("current", [])
                            ],
                            "historical": [
                                [link["to"], {"date": link["date"]}]
                                for link in domain_data.get("external_outgoing", {}).get("historical", [])
                            ]
                        },
                        "external_incoming": domain_data.get("external_incoming", {})
                    }
                }
            }
            
            return complete_json
            
        except Exception as e:
            print(f"Error in format_results: {str(e)}")
            traceback.print_exc()
            return None

    def visualize_from_json(self, paths):
        """Create visualization with ALL relationships"""
        dot = Digraph(comment='Domain Link Structure')
        
        # Graph settings
        dot.attr(rankdir='LR', size='30,30')
        dot.attr('node', shape='box', style='rounded,filled', fontsize='10')
        
        # Track added nodes to prevent duplicates
        added_nodes = set()
        
        # Add current site structure
        for path, data in paths.items():
            if path not in added_nodes:
                dot.node(path, fillcolor='lightblue', style='filled')
                added_nodes.add(path)
            
            # Add internal links
            for internal_link in data['internal_links']['outgoing']['current']:
                if internal_link not in added_nodes:
                    dot.node(internal_link, fillcolor='lightblue', style='filled')
                    added_nodes.add(internal_link)
                dot.edge(path, internal_link, color='blue')
            
            # Add current outgoing external links
            for ext_link in data['external_links']['outgoing']['current']:
                if ext_link not in added_nodes:
                    dot.node(ext_link, fillcolor='pink', style='filled')
                    added_nodes.add(ext_link)
                dot.edge(path, ext_link, color='red', label='current')
            
            # Add historical outgoing links
            for year, links in data['external_links']['outgoing']['historical'].items():
                for link in links:
                    if link not in added_nodes:
                        dot.node(link, fillcolor='lightgray', style='filled')
                        added_nodes.add(link)
                    dot.edge(path, link, color='gray', label=year)
        
        # Add backlinks
        for domain, details in paths['/']['external_links']['incoming'].items():
            if domain not in added_nodes:
                dot.node(domain, fillcolor='lightgreen', style='filled')
                added_nodes.add(domain)
            dot.edge(domain, self.domain_name, color='green', 
                    label=f"DR:{details.get('domain_rating', '0')}")
        
        # Save with timestamp
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        dot.render(f'domain_links_{timestamp}', view=True, format='pdf')

    def _get_dr_color(self, dr):
        """Generate color based on domain rating"""
        # Convert DR 0-100 to hue 0-120 (red to green)
        hue = min(dr * 1.2, 120) / 360.0
        rgb = colorsys.hsv_to_rgb(hue, 0.3, 0.95)
        return f"#{int(rgb[0]*255):02x}{int(rgb[1]*255):02x}{int(rgb[2]*255):02x}"

    def extract_links_from_html(self, html):
        """Extract all links from HTML content"""
        links = set()
        try:
            # Use 'html.parser' for HTML content or 'xml' for XML content
            soup = BeautifulSoup(html, 'xml')  # Change 'html.parser' to 'xml' if needed
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.startswith('http'):
                    links.add(href)
                elif href.startswith('/'):
                    links.add(f"https://{self.domain_name}{href}")
        except Exception as e:
            logger.error(f"HTML parsing error: {str(e)}")
        return links

    def generate_dot_file(self, output_file):
        """Generate DOT file with proper URL stadium shapes and formatting"""
        dot_content = [
            'digraph {',
            '    rankdir=LR;',
            '    node [style="rounded,filled", shape=rect, fontname="Arial"];',
            '    edge [fontname="Arial", fontsize=8];',
            
            # Set stadium shape for URLs
            '    node [shape=stadium, style=filled, fillcolor=lightblue] {',
        ]
        
        # Add all URLs with stadium shape
        for url in self.paths.keys():
            dot_content.append(f'        "{url}";')
        
        # Close URL node definitions
        dot_content.append('    }')
        
        # Add external domains with different shape/color
        dot_content.append('    node [shape=stadium, style=filled, fillcolor=lightgreen] {')
        for _, links in self.paths.items():
            for ext_link in links['external_links']['outgoing']['current']:
                dot_content.append(f'        "{ext_link}";')
        dot_content.append('    }')
        
        # Add relationships
        for source, links in self.paths.items():
            for target in links['external_links']['outgoing']['current']:
                dot_content.append(f'    "{source}" -> "{target}";')
        
        dot_content.append('}')
        
        # Write to file
        with open(output_file, 'w') as f:
            f.write('\n'.join(dot_content))

    async def collect_current_site_structure(self):
        """Collect complete current site structure by crawling all pages"""
        try:
            async with aiohttp.ClientSession() as session:
                # Start with root URL
                pages_to_crawl = {f"https://{self.domain_name}"}
                crawled_pages = set()
                
                while pages_to_crawl:
                    current_url = pages_to_crawl.pop()
                    if current_url in crawled_pages:
                        continue
                    
                    try:
                        async with session.get(current_url) as response:
                            if response.status == 200:
                                html = await response.text()
                                soup = BeautifulSoup(html, 'html.parser')
                                
                                # Get normalized path for current URL
                                current_path = self.normalize_path(current_url)
                                
                                # Find all internal links
                                for a in soup.find_all('a', href=True):
                                    href = a['href']
                                    full_url = urljoin(current_url, href)
                                    
                                    # Only process URLs from our domain
                                    if self.domain_name in full_url:
                                        clean_url = self.clean_url_for_display(full_url)
                                        normalized_path = self.normalize_path(clean_url)
                                        
                                        # Add to internal links
                                        self.paths[current_path]['internal_links']['outgoing']['current'].add(normalized_path)
                                        
                                        # Add to crawl queue if not seen
                                        if normalized_path not in crawled_pages:
                                            pages_to_crawl.add(full_url)
                                    
                                    # Process external links
                                    elif href.startswith('http'):
                                        clean_href = self.clean_url_for_display(href)
                                        self.paths[current_path]['external_links']['outgoing']['current'][clean_href] = {
                                            'timestamp': datetime.now().isoformat(),
                                            'status_code': response.status
                                        }
                                
                                crawled_pages.add(current_url)
                                
                    except Exception as e:
                        logger.error(f"Error crawling {current_url}: {str(e)}")
                        continue
                    
        except Exception as e:
            logger.error(f"Site structure error: {str(e)}")

async def main():
    """Main execution flow"""
    try:
        domain = input("Enter domain to analyze (without http/www/https): ")
        mapper = UnifiedDomainMapper(domain)
        
        # Collect all data
        await mapper.collect_all_data()
        
        # Save to JSON
        json_data = mapper.save_link_data()
        
        # Create visualization
        viz_file = mapper.visualize_from_json(json_data)
        
        print(f"\nAnalysis complete! Visualization saved as: {viz_file}.pdf")
        
    except Exception as e:
        print(f"Error in main execution: {str(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())