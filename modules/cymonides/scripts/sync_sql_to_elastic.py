#!/usr/bin/env python3
"""
Sync Postgres to Elasticsearch
Reads all nodes from the Drill Search SQL database and indexes them into Elasticsearch.
This ensures the new Grid/Graph can see existing project data.
"""

import os
import sys
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime

# Add parent directory to path
CURRENT_DIR = Path(__file__).parent
MCP_ROOT = CURRENT_DIR.parent
sys.path.insert(0, str(MCP_ROOT))

from brute.services.elastic_service import get_elastic_service

# Database connection
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("Error: psycopg2 not installed. Please install it.")
    sys.exit(1)

# Load env
from dotenv import load_dotenv
# Try absolute paths
load_dotenv("/Users/attic/DRILL_SEARCH/drill-search-app/.env")
load_dotenv("/Users/attic/DRILL_SEARCH/drill-search-app/python-backend/.env")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

async def sync_nodes():
    # Hardcoded for immediate sync fix
    db_url = "postgresql://attic@localhost:5432/search_engineer_db" 
    if not db_url:
        logger.error("DATABASE_URL not found in environment")
        return

    logger.info("Connecting to Postgres...")
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor(cursor_factory=RealDictCursor)
    except Exception as e:
        logger.error(f"Failed to connect to DB: {e}")
        return

    elastic = get_elastic_service()
    await elastic.initialize()

    logger.info("Fetching nodes...")
    # Fetch nodes with class and type names - quoted identifiers for Postgres/Drizzle
    query = """
    SELECT 
        n.id, n.label, n.metadata, n."createdAt", n."userId",
        nc.name as "class", nt.name as "type",
        n."canonicalValue" as "url",
        n."projectId"
    FROM "nodes" n
    LEFT JOIN "nodeClasses" nc ON n."classId" = nc.id
    LEFT JOIN "nodeTypes" nt ON n."typeId" = nt.id
    WHERE n.status = 'active'
    ORDER BY n."createdAt" DESC
    LIMIT 5000
    """
    
    cur.execute(query)
    logger.info("Query executed, processing recent items...")

    batch = []
    count = 0
    
    while True:
        rows = cur.fetchmany(1000)
        if not rows:
            break
            
        for row in rows:
            # Prepare doc
            doc = {
                "id": row['id'],
                "label": row['label'],
                "url": row['url'] or row['label'], # Fallback
                "class": row['class'],
                "type": row['type'],
                "userId": row.get('userId'),
                "projectId": row['projectId'], # Sync Project ID
                "metadata": row['metadata'] or {},
                "timestamp": row['createdAt'].isoformat() if row['createdAt'] else datetime.utcnow().isoformat(),
                "query": "", # Existing nodes might not have a query source
                "content": "" # Metadata snippet?
            }
            
            # Extract snippet from metadata if available
            if doc['metadata'].get('snippet'):
                doc['content'] = doc['metadata']['snippet']
            elif doc['metadata'].get('description'):
                doc['content'] = doc['metadata']['description']
                
            batch.append(doc)
            count += 1
            
            if len(batch) >= 500:
                await elastic.index_batch(batch)
                logger.info(f"Indexed {count} nodes...")
                batch = []

    if batch:
        await elastic.index_batch(batch)
        logger.info(f"Indexed final {len(batch)} nodes.")

    logger.info("Sync complete.")
    cur.close()
    conn.close()
    await elastic.close()

if __name__ == "__main__":
    asyncio.run(sync_nodes())
