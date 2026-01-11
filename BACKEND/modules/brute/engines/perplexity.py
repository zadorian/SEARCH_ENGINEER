#!/usr/bin/env python3
"""
Perplexity Search Engine for Search_Engineer
Uses Perplexity API for AI-powered web search (NOT Q&A mode)
"""

import os
import requests
from typing import List, Dict

class PerplexitySearch:
    """Perplexity search client (search mode, not chat)"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('PERPLEXITY_API_KEY')
        if not self.api_key:
            raise ValueError("PERPLEXITY_API_KEY not set")

        self.api_url = "https://api.perplexity.ai"

    def search(self, query: str, max_results: int = 10) -> List[Dict]:
        """
        Search using Perplexity's search-focused mode
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            # Use Perplexity with search_focus to get URLs (not Q&A)
            response = requests.post(
                f"{self.api_url}/chat/completions",
                headers=headers,
                json={
                    "model": "llama-3.1-sonar-small-128k-online",  # Online search model
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a search engine. Return only URLs and brief descriptions. Format: URL: [url] - [description]"
                        },
                        {
                            "role": "user",
                            "content": f"Find web pages about: {query}. List {max_results} relevant URLs with descriptions."
                        }
                    ],
                    "max_tokens": 1000,
                    "search_domain_filter": [],  # No filter
                    "return_citations": True,
                    "search_recency_filter": "month"
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                results = []

                # Extract citations (these are the actual web results)
                citations = data.get("citations", [])
                for cite in citations[:max_results]:
                    results.append({
                        "url": cite,
                        "title": cite.split("/")[-1] if "/" in cite else cite,
                        "snippet": f"Found via Perplexity search for: {query}",
                        "engine": "perplexity"
                    })

                return results
            else:
                print(f"Perplexity search error: {response.status_code}")
                return []

        except Exception as e:
            print(f"Perplexity search exception: {e}")
            return []


class ExactPhraseRecallRunnerPerplexity:
    """
    Perplexity Exact Phrase Recall Runner
    Tier 1: Native AI search
    Tier 2: Multiple search perspectives
    Tier 3: Comprehensive multi-angle search
    """

    def __init__(self, perplexity: PerplexitySearch = None):
        self.client = perplexity or PerplexitySearch()

    def run(self, phrase: str, tier: int = 1) -> List[Dict]:
        """
        Execute search based on tier
        """
        if tier == 1:
            # Tier 1: Direct search
            return self.client.search(phrase, max_results=10)

        elif tier == 2:
            # Tier 2: Multiple query angles
            all_results = []
            queries = [
                phrase,
                f'"{phrase}"',
                f"information about {phrase}",
                f"latest news {phrase}"
            ]

            for q in queries:
                all_results.extend(self.client.search(q, max_results=10))

            # Deduplicate
            seen = set()
            unique = []
            for r in all_results:
                if r['url'] not in seen:
                    seen.add(r['url'])
                    unique.append(r)

            return unique

        else:  # tier == 3
            # Tier 3: Maximum recall with temporal and perspective variations
            all_results = []

            # Base queries
            queries = [
                phrase,
                f'"{phrase}"',
                f"{phrase} official site",
                f"{phrase} news",
                f"{phrase} research",
                f"{phrase} analysis",
                f"{phrase} report",
                f"{phrase} data"
            ]

            for q in queries:
                all_results.extend(self.client.search(q, max_results=15))

            # Deduplicate
            seen = set()
            unique = []
            for r in all_results:
                if r['url'] not in seen:
                    seen.add(r['url'])
                    unique.append(r)

            return unique
