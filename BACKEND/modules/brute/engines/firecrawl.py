#!/usr/bin/env python3
"""
Firecrawl Search Engine for Search_Engineer
Uses Firecrawl API for web content scraping and search
"""

import os
import sys
import requests
from typing import List, Dict
from pathlib import Path

# Add C0GN1T0 to path for Firecrawl service
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

try:
    from parallel_firecrawl_service import ParallelFirecrawlService
    PARALLEL_FIRECRAWL_AVAILABLE = True
except ImportError:
    ParallelFirecrawlService = None
    PARALLEL_FIRECRAWL_AVAILABLE = False

class FirecrawlSearch:
    """Firecrawl search client"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('FIRECRAWL_API_KEY')
        if not self.api_key:
            raise ValueError("FIRECRAWL_API_KEY not set")

        self.service = ParallelFirecrawlService(api_key=self.api_key) if PARALLEL_FIRECRAWL_AVAILABLE else None
        self.api_url = "https://api.firecrawl.dev/v1"

    def search(self, query: str, max_results: int = 10) -> List[Dict]:
        """
        Search using Firecrawl's search endpoint
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            response = requests.post(
                f"{self.api_url}/search",
                headers=headers,
                json={
                    "query": query,
                    "limit": max_results
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                results = []

                for item in data.get("data", []):
                    results.append({
                        "url": item.get("url"),
                        "title": item.get("title", ""),
                        "snippet": item.get("description", ""),
                        "engine": "firecrawl"
                    })

                return results
            else:
                print(f"Firecrawl search error: {response.status_code}")
                return []

        except Exception as e:
            print(f"Firecrawl search exception: {e}")
            return []


class ExactPhraseRecallRunnerFirecrawl:
    """
    Firecrawl Exact Phrase Recall Runner
    Tier 1: Native search API
    Tier 2: Search + scrape top results
    Tier 3: Aggressive search with content analysis
    """

    def __init__(self, firecrawl: FirecrawlSearch = None):
        self.client = firecrawl or FirecrawlSearch()

    def run(self, phrase: str, tier: int = 1) -> List[Dict]:
        """
        Execute search based on tier
        """
        if tier == 1:
            # Tier 1: Simple search
            return self.client.search(phrase, max_results=10)

        elif tier == 2:
            # Tier 2: Search + scrape
            results = self.client.search(phrase, max_results=20)
            # Filter results containing exact phrase in title/snippet
            return [r for r in results if phrase.lower() in (r['title'] + r['snippet']).lower()]

        else:  # tier == 3
            # Tier 3: Maximum recall with variations
            all_results = []

            # Original query
            all_results.extend(self.client.search(phrase, max_results=50))

            # Quoted query
            all_results.extend(self.client.search(f'"{phrase}"', max_results=50))

            # Deduplicate by URL
            seen = set()
            unique_results = []
            for r in all_results:
                if r['url'] not in seen:
                    seen.add(r['url'])
                    unique_results.append(r)

            return unique_results
