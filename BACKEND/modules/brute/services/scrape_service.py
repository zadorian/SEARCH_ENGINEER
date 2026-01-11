import asyncio
import logging
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
import json
from dotenv import load_dotenv

# Load env from root to ensure Firecrawl Key is found
load_dotenv("/Users/attic/DRILL_SEARCH/drill-search-app/.env")

# Imports
from brute.scraper.scraper import scraper as ScrapeR
from brute.services.elastic_service import get_elastic_service
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

class ScrapeService:
    def __init__(self):
        self.scraper = ScrapeR()
        self.elastic = get_elastic_service()
        self.db_url = os.getenv("DATABASE_URL") or "postgresql://attic@localhost:5432/search_engineer_db"

    async def scrape_and_index(self, urls: List[str], project_id: str = None, user_id: int = None) -> Dict[str, Any]:
        """
        Scrapes a list of URLs, saves to SQL 'corpus', and indexes to Elastic.
        """
        if not urls:
            return {"success": False, "message": "No URLs provided"}

        # 1. Scrape
        logger.info(f"Scraping {len(urls)} URLs...")
        # Use batching if > 100 (handled by ScrapeR logic or here)
        # ScrapeR.search is for queries. We need a direct URL scrape method.
        # ScrapeR has _scrape_urls but it's internal. 
        # I will access the firecrawl client directly or use _scrape_urls.
        
        # Note: ScrapeR._scrape_urls is async and returns a dict of results
        scrape_results = await self.scraper._scrape_urls(urls)
        
        success_count = 0
        failed_count = 0
        
        # 2. Process Results
        conn = None
        try:
            conn = psycopg2.connect(self.db_url)
            cur = conn.cursor()
            
            for url, result in scrape_results.items():
                if result.success and result.markdown:
                    # A. Save to Postgres (Nodes & Corpus)
                    # First, find or create the node
                    node_id = self._ensure_node_exists(cur, url, result.title, project_id, user_id)
                    
                    # Save to Corpus table
                    cur.execute("""
                        INSERT INTO corpus (id, \"nodeId\", url, title, content, \"dateAdded\")
                        VALUES (DEFAULT, %s, %s, %s, %s, NOW())
                        RETURNING id
                    """, (node_id, url, result.title, result.markdown))
                    
                    # Update Node metadata
                    cur.execute("""
                        UPDATE nodes 
                        SET metadata = jsonb_set(
                            COALESCE(metadata, '{}'), 
                            '{scraped}', 'true'
                        )
                        WHERE id = %s
                    """, (node_id,))
                    
                    # B. Index to Elastic
                    # We fetch the full node to ensure we have all class/type info
                    # But for speed, we construct the doc here
                    doc = {
                        "id": node_id,
                        "url": url,
                        "label": result.title or url,
                        "content": result.markdown, # Full content for indexing
                        "class": "source",
                        "type": "web_page",
                        "metadata": result.metadata or {},
                        "is_corpus": True, # Flag for "Orangy" highlight
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    await self.elastic.index_document(doc)
                    
                    success_count += 1
                else:
                    failed_count += 1
                    logger.warning(f"Failed to scrape {url}: {result.error}")

            conn.commit()
            cur.close()
            conn.close()
            
        except Exception as e:
            logger.error(f"Database error during scrape save: {e}")
            if conn: conn.rollback()
            return {"success": False, "error": str(e)}

        return {
            "success": True,
            "scraped": success_count,
            "failed": failed_count,
            "total": len(urls)
        }

    def _ensure_node_exists(self, cur, url, title, project_id, user_id):
        """Finds a node by URL or creates it."""
        # Try finding by canonical value (URL)
        # Simple normalization: remove protocol and www
        # But strict match is better for exact URL
        
        # We'll try matching 'canonicalValue'
        cur.execute('SELECT id FROM nodes WHERE "canonicalValue" = %s', (url,))
        res = cur.fetchone()
        if res:
            return res[0]
            
        # Create new node
        import uuid
        new_id = str(uuid.uuid4()).replace('-', '')
        
        # Get Source class ID (usually 1, but let's be safe)
        cur.execute("SELECT id FROM \"nodeClasses\" WHERE name = 'source'")
        class_res = cur.fetchone()
        class_id = class_res[0] if class_res else 1
        
        # Get URL type ID
        cur.execute("SELECT id FROM \"nodeTypes\" WHERE name = 'url'")
        type_res = cur.fetchone()
        type_id = type_res[0] if type_res else 1
        
        cur.execute("""
            INSERT INTO nodes (id, label, \"classId\", \"typeId\", \"canonicalValue\", \"valueHash\", \"userId\", \"projectId\", status, \"createdAt\", \"updatedAt\")
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active', NOW(), NOW())
            RETURNING id
        """, (
            new_id, 
            title or url, 
            class_id, 
            type_id, 
            url, 
            hash(url), # Simple hash
            user_id, 
            project_id
        ))
        return cur.fetchone()[0]

# Singleton
_scrape_service = None
def get_scrape_service():
    global _scrape_service
    if _scrape_service is None:
        _scrape_service = ScrapeService()
    return _scrape_service
