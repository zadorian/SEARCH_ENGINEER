#!/usr/bin/env python3
"""
Entities API: per-URL staged entities
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field
import os
import json
import hashlib
import sys
from pathlib import Path

# Add project root to path
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    import asyncpg  # type: ignore
except Exception:
    asyncpg = None  # type: ignore

try:
    import redis
    redis_client = redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379'))
except Exception:
    redis_client = None

# Import EntityGraphStorageV2
try:
    from Indexer.entity_graph_storage_v2 import EntityGraphStorageV2
except ImportError:
    EntityGraphStorageV2 = None

router = APIRouter()


# Mount with prefix in main app ("/api/v1"); define route path once here
@router.get("/entities/by_url")
async def entities_by_url(url: str = Query(...)) -> Dict[str, Any]:
    if asyncpg is None:
        return {"success": False, "error": "asyncpg not installed"}
    conn = await asyncpg.connect(os.getenv("SUPABASE_PG_CONN"))
    try:
        rows = await conn.fetch(
            "SELECT name, type, pos, created_at FROM staging_entities WHERE url=$1 ORDER BY created_at DESC LIMIT 500",
            url,
        )
        ents = [dict(r) for r in rows]
        return {"success": True, "url": url, "entities": ents}
    finally:
        await conn.close()


@router.get("/entities/for-url")
async def get_entities_for_url(url: str = Query(...)) -> Dict[str, Any]:
    """Get entities connected to a URL for highlighting purposes.
    Uses EntityGraphStorageV2 to find all entities linked to a URL node.
    Results are cached in Redis for performance."""
    
    # Check Redis cache first
    if redis_client:
        try:
            cache_key = f"url_entities:{hashlib.md5(url.encode()).hexdigest()}"
            cached = redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            print(f"Redis cache error: {e}")
    
    # Fall back to database query
    if not EntityGraphStorageV2:
        return {"success": False, "error": "EntityGraphStorageV2 not available"}
    
    try:
        storage = EntityGraphStorageV2()
        
        # Get entities linked to this URL
        entities = storage.get_entities_for_url(url)
        
        # Format for highlighting
        result = {
            "success": True,
            "url": url,
            "entities": entities,
            "count": len(entities)
        }
        
        # Cache the result
        if redis_client:
            try:
                redis_client.setex(
                    cache_key, 
                    3600,  # 1 hour TTL
                    json.dumps(result)
                )
            except Exception as e:
                print(f"Redis cache write error: {e}")
        
        return result
        
    except Exception as e:
        return {"success": False, "error": str(e)}


class EntitySearchRequest(BaseModel):
    entity_type: str = Field(..., description="person | company | email | phone | linkedin | whois")
    query: str = Field(..., min_length=1)
    limit: Optional[int] = Field(50, ge=1, le=500)


@router.post("/entities/search")
async def entity_search(body: EntitySearchRequest):
    try:
        from Search_Types.subject.entities.router import search as entities_search
        return entities_search(body.entity_type, body.query, limit=body.limit or 50)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


