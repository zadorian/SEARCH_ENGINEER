import aiohttp
import asyncio
import requests
import json
from typing import List, Dict, Set, Tuple
from dataclasses import dataclass
from urllib.parse import urlparse
from datetime import datetime
from collections import defaultdict

@dataclass
class DomainResult:
    url: str
    title: str = ""
    description: str = ""
    source: str = ""
    score: float = 0.0
    first_seen: str = ""
    registrant: str = ""
    whois_data: dict = None
    confidence: str = "low"

class ComprehensiveDomainAnalyzer:
    def __init__(self):
        # API Keys
        self.brave_key = "BSABLdUy84zL4T-Z_JNHIFxjdF2src9"
        self.whois_key = "at_3TTfpXdTV2Gv7iiiOkZjm8cCobMib"
        
        # Results storage
        self.results: Dict[str, DomainResult] = {}
        
    async def analyze_domain(self, domain: str):
        """Main analysis function"""
        async with aiohttp.ClientSession() as session:
            # Run all searches in parallel
            await asyncio.gather(
                self.search_wayback(session, domain),
                self.search_whois(domain),
                self.search_brave(domain)
            )

    async def search_wayback(self, session: aiohttp.ClientSession, domain: str):
        """Search Wayback Machine"""
        cdx_url = "https://web.archive.org/cdx/search/cdx"
        params = {
            'url': domain,
            'matchType': 'domain',
            'output': 'json',
            'fl': 'original,timestamp',
            'collapse': 'timestamp:8'
        }

        try:
            async with session.get(cdx_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if len(data) > 1:  # Skip header row
                        for row in data[1:]:
                            original_url, timestamp = row
                            parsed_url = urlparse(original_url)
                            domain = parsed_url.netloc.lower()
                            if domain.startswith('www.'):
                                domain = domain[4:]

                            # Create or update result
                            if domain not in self.results:
                                self.results[domain] = DomainResult(url=domain)
                            
                            # Update first seen date
                            date_obj = datetime.strptime(timestamp[:8], '%Y%m%d')
                            first_seen = date_obj.strftime('%-d %b %Y')
                            self.results[domain].first_seen = first_seen
                            self.results[domain].score += 5  # Bonus for historical presence

        except Exception as e:
            print(f"Wayback error: {str(e)}")

    def search_whois(self, domain: str):
        """Search WHOIS data"""
        url = f"https://www.whoisxmlapi.com/whoisserver/WhoisService"
        params = {
            "apiKey": self.whois_key,
            "domainName": domain,
            "outputFormat": "JSON"
        }

        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                whois_data = data.get("WhoisRecord", {})
                
                # Extract registrant info
                registrant = whois_data.get("registrant", {})
                org = registrant.get("organization", "")
                
                # Update or create result
                if domain not in self.results:
                    self.results[domain] = DomainResult(url=domain)
                
                self.results[domain].whois_data = whois_data
                self.results[domain].registrant = org
                self.results[domain].score += 10  # Bonus for WHOIS data

        except Exception as e:
            print(f"WHOIS error: {str(e)}")

    async def search_brave(self, domain: str):
        """Search using Brave"""
        queries = [
            f'"{domain}" corporate website',
            f'"{domain}" company headquarters',
            f'"{domain}" about us official'
        ]

        for query in queries:
            try:
                response = {
                    "function_calls": [
                        {
                            "name": "brave_web_search",
                            "parameters": {
                                "query": query,
                                "count": 10
                            }
                        }
                    ]
                }
                
                results = response.get("results", [])
                for result in results:
                    url = result.get('url', '')
                    parsed_url = urlparse(url)
                    result_domain = parsed_url.netloc.lower()
                    
                    if domain in result_domain:
                        if result_domain not in self.results:
                            self.results[result_domain] = DomainResult(
                                url=url,
                                title=result.get('title', ''),
                                description=result.get('description', ''),
                                source='brave'
                            )
                        
                        # Update score based on content
                        self._update_score(self.results[result_domain])

            except Exception as e:
                print(f"Brave search error: {str(e)}")

    def _update_score(self, result: DomainResult):
        """Update confidence score based on various factors"""
        score = result.score
        
        # URL factors
        url_lower = result.url.lower()
        if "corporate" in url_lower: score += 10
        if "about" in url_lower: score += 5
        if "company" in url_lower: score += 5
        
        # Title/description factors
        text = f"{result.title} {result.description}".lower()
        if "official" in text: score += 15
        if "corporate" in text: score += 10
        if "headquarters" in text: score += 8
        
        # Historical data bonus
        if result.first_seen: score += 5
        if result.registrant: score += 10
        
        result.score = score
        
        # Set confidence level
        if score >= 40:
            result.confidence = "high"
        elif score >= 20:
            result.confidence = "medium"
        else:
            result.confidence = "low"

    def get_results(self) -> List[DomainResult]:
        """Get sorted results"""
        return sorted(
            self.results.values(),
            key=lambda x: x.score,
            reverse=True
        )

async def main():
    analyzer = ComprehensiveDomainAnalyzer()
    domain = input("Enter domain to analyze: ")
    
    print(f"\nAnalyzing {domain}...")
    await analyzer.analyze_domain(domain)
    
    print("\nResults:")
    for result in analyzer.get_results():
        print(f"\nURL: {result.url}")
        if result.title:
            print(f"Title: {result.title}")
        if result.first_seen:
            print(f"First seen: {result.first_seen}")
        if result.registrant:
            print(f"Registrant: {result.registrant}")
        print(f"Confidence: {result.confidence} (Score: {result.score})")
        print("-" * 80)

if __name__ == "__main__":
    asyncio.run(main())