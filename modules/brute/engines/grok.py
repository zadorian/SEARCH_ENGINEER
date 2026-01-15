"""
Grok Search Engine Runner

Uses xAI Grok API for AI-powered web search with live internet access.
Grok 4 has real-time web search capabilities via its "Live Search" feature.
"""

import os
import asyncio
import logging
import requests
import re
from typing import List, Dict, Any, Optional, AsyncGenerator
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class GrokSearch:
    """Grok search client using xAI API"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY")
        if not self.api_key:
            logger.warning("XAI_API_KEY not set - Grok search unavailable")

        self.api_url = "https://api.x.ai/v1/chat/completions"
        self.model = "grok-4"  # Latest Grok model with web search

    def search(self, query: str, max_results: int = 10) -> List[Dict]:
        """
        Search using Grok with live web search.

        Grok 4 has real-time internet access and returns citations/sources.
        """
        if not self.api_key:
            return []

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            # Grok with web search prompt
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a search assistant. Search the web and return relevant URLs with descriptions. Format each result as: URL: [full_url] | TITLE: [title] | SNIPPET: [description]. One result per line."
                    },
                    {
                        "role": "user",
                        "content": f"Search the web for: {query}. Find {max_results} relevant web pages. Return URLs with titles and descriptions."
                    }
                ],
                "temperature": 0,
                "max_tokens": 2000,
                "search": True  # Enable Grok live search
            }

            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=60
            )

            if response.status_code != 200:
                logger.error(f"Grok API error: {response.status_code} - {response.text[:200]}")
                return []

            data = response.json()
            results = []

            # Parse response content
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Also extract any citations/sources from the API response
            citations = data.get("citations", [])
            for cite in citations:
                if isinstance(cite, dict):
                    results.append({
                        "url": cite.get("url", ""),
                        "title": cite.get("title", ""),
                        "snippet": cite.get("text", ""),
                        "engine": "Grok",
                        "source": "grok_citation"
                    })
                elif isinstance(cite, str):
                    results.append({
                        "url": cite,
                        "title": "",
                        "snippet": "",
                        "engine": "Grok",
                        "source": "grok_citation"
                    })

            # Parse text response for URLs
            for line in content.split("\n"):
                line = line.strip()
                if not line or not ("http://" in line or "https://" in line):
                    continue

                # Parse format: URL: [url] | TITLE: [title] | SNIPPET: [description]
                url = ""
                title = ""
                snippet = ""

                if "URL:" in line:
                    parts = line.split("|")
                    for part in parts:
                        part = part.strip()
                        if part.startswith("URL:"):
                            url = part[4:].strip()
                        elif part.startswith("TITLE:"):
                            title = part[6:].strip()
                        elif part.startswith("SNIPPET:"):
                            snippet = part[8:].strip()
                else:
                    # Try to extract URL from line
                    urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', line)
                    if urls:
                        url = urls[0]
                        snippet = line.replace(url, "").strip(" -:|")

                if url and url not in [r["url"] for r in results]:
                    results.append({
                        "url": url,
                        "title": title or (snippet[:50] if snippet else url.split("/")[-1]),
                        "snippet": snippet,
                        "engine": "Grok",
                        "source": "grok_search"
                    })

            logger.info(f"Grok returned {len(results)} results")
            return results[:max_results]

        except Exception as e:
            logger.error(f"Grok search error: {e}")
            return []


class ExactPhraseRecallRunnerGrok:
    """
    Grok search runner following standard ExactPhraseRecallRunner pattern.
    Uses Grok 4 with live web search for AI-powered results.
    """

    def __init__(self, keyword: str = None, phrase: str = None,
                 max_results: int = 50, event_emitter=None):
        self.keyword = keyword or phrase
        self.phrase = phrase or keyword
        self.max_results = max_results
        self.event_emitter = event_emitter
        self.results = []
        self.grok = GrokSearch()

    def run(self) -> List[Dict[str, Any]]:
        """Synchronous run"""
        if not self.grok.api_key:
            logger.warning("Grok API key not configured")
            return []

        # Search variations for max recall
        # GR1-GR4 variations for max recall
        quoted = f'"{self.phrase}"' if not self.phrase.startswith('"') else self.phrase
        queries = [
            quoted,  # GR1: Exact phrase
            f"{quoted} filetype:pdf",  # GR2: PDF
            f"{quoted} filetype:doc",  # GR2: Doc
            f"intitle:{quoted}",  # GR3: Title
            f"inurl:{quoted}",  # GR4: URL
            self.phrase,  # Natural query
        ]

        all_results = []
        seen_urls = set()

        for query in queries:
            results = self.grok.search(query, max_results=self.max_results)
            for r in results:
                url = r.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append(r)

                    # Emit if streaming
                    if self.event_emitter:
                        try:
                            self.event_emitter(r)
                        except:
                            pass

        self.results = all_results[:self.max_results]
        return self.results

    async def run_async(self) -> List[Dict[str, Any]]:
        """Async run using thread pool"""
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=1) as executor:
            return await loop.run_in_executor(executor, self.run)

    async def run_with_streaming(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Run with streaming support"""
        results = await self.run_async()
        for result in results:
            yield result


# Convenience aliases
GrokSearchEngine = GrokSearch
__all__ = ["GrokSearch", "GrokSearchEngine", "ExactPhraseRecallRunnerGrok"]
