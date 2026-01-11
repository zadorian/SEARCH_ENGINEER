import asyncio
import logging
import json
import os
import sys
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

# Add backend root to sys.path
BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

try:
    from modules.LINKLATER.linklater_cli import KeywordVariationsSearch
    LINKLATER_AVAILABLE = True
except ImportError:
    LINKLATER_AVAILABLE = False

from elastic_manager import ElasticManager
import aiohttp

logger = logging.getLogger("Jester.Harvester")

class Harvester:
    """
    The Researcher component of Jester.
    Finds and downloads content for a given query.
    """
    def __init__(self):
        self.firecrawl_key = os.getenv("FIRECRAWL_API_KEY")
        self.firecrawl_url = os.getenv("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev/v1")
        self.elastic = ElasticManager() # For Graph Access

    async def harvest(self, query: str, limit: int = 10, project_id: str = None) -> List[Dict[str, Any]]:
        """
        Search and fetch content for a query.
        Combines Live Search (Firecrawl), Archive Search (Linklater), and Knowledge Graph (Cymonides).
        """
        logger.info(f"Harvesting content for query: {query}")
        
        results = []
        
        # 0. Knowledge Graph (Internal Memory)
        try:
            grid_results = await self.fetch_from_grid(query, limit=limit, project_id=project_id)
            results.extend(grid_results)
            logger.info(f"Knowledge Graph found {len(grid_results)} nodes")
        except Exception as e:
            logger.error(f"Graph search failed: {e}")

        # 1. Live Search via Firecrawl
        if self.firecrawl_key:
            try:
                live_results = await self._search_firecrawl(query, limit=limit)
                results.extend(live_results)
                logger.info(f"Firecrawl found {len(live_results)} results")
            except Exception as e:
                logger.error(f"Firecrawl search failed: {e}")
        
        # 2. Archive Search via Linklater
        if LINKLATER_AVAILABLE:
            try:
                archive_results = await self._search_linklater(query, limit=limit)
                results.extend(archive_results)
                logger.info(f"Linklater found {len(archive_results)} results")
            except Exception as e:
                logger.error(f"Linklater search failed: {e}")
        
        # Deduplicate by URL
        unique_results = []
        seen_urls = set()
        for r in results:
            if r['url'] not in seen_urls:
                seen_urls.add(r['url'])
                unique_results.append(r)
                
        # Sort by date (newest first) if available, else relevance (preserved order)
        # Simple heuristic: Prefer results with content
        unique_results.sort(key=lambda x: len(x.get('content', '')), reverse=True)
        
        return unique_results[:limit]

    async def fetch_from_grid(self, query: str, limit: int = 5, project_id: str = None) -> List[Dict[str, Any]]:
        """
        Fetch content from existing Grid source nodes (Elasticsearch).
        """
        # Sync call to ElasticManager (it uses requests under the hood, essentially sync)
        # In a truly async app we might want to thread this, but for now direct call is fine.
        nodes = self.elastic.search_knowledge_graph(query, limit=limit, project_id=project_id)
        
        processed = []
        for node in nodes:
            # Prefer URL, fall back to canonicalValue, then ID
            url = node.get('url') or node.get('canonicalValue') or f"node:{node.get('id')}"
            
            # Prefer content, fall back to description/snippet
            content = node.get('content')
            if not content:
                meta = node.get('metadata', {})
                content = meta.get('description') or meta.get('snippet') or str(meta)
            
            processed.append({
                "url": url,
                "title": f"[Graph] {node.get('label', 'Unknown Node')}",
                "content": content or "",
                "source": "knowledge_graph",
                "timestamp": node.get('timestamp') or datetime.now().isoformat()
            })
            
        return processed

    async def _search_firecrawl(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Use Firecrawl /search endpoint"""
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {self.firecrawl_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "query": query,
                "limit": limit,
                "scrapeOptions": {"formats": ["markdown"]}
            }
            
            async with session.post(f"{self.firecrawl_url}/search", json=payload, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"Firecrawl error {resp.status}: {text}")
                
                data = await resp.json()
                if not data.get("success"):
                    raise Exception(data.get("error", "Unknown error"))
                
                processed = []
                for item in data.get("data", []):
                    processed.append({
                        "url": item.get("url"),
                        "title": item.get("title"),
                        "content": item.get("markdown", ""),
                        "source": "firecrawl_live",
                        "timestamp": datetime.now().isoformat()
                    })
                return processed

    async def _search_linklater(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Use Linklater KeywordVariationsSearch"""
        searcher = KeywordVariationsSearch(max_results_per_source=limit, verify_snippets=True)
        result = await searcher.search(keyword=query, max_concurrent=5)
        await searcher.close()
        
        processed = []
        # Linklater returns matches with snippets, but we need full content for Jester ideally.
        # For now, we use the snippets/verified content.
        
        # Combine wayback and cc hits
        all_hits = result.wayback_hits + result.cc_hits
        
        for hit in all_hits:
            processed.append({
                "url": hit.url,
                "title": f"Archive: {hit.url}",
                "content": hit.content or hit.snippet or "",
                "source": f"archive_{hit.source}",
                "timestamp": hit.timestamp
            })
            
        return processed
