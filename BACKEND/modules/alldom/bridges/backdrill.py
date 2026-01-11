"""
ALLDOM Bridge: BACKDRILL

Thin wrapper for archive operations (CommonCrawl, Wayback, Memento).
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def fetch(url: str, **kwargs) -> Dict[str, Any]:
    """
    Fetch URL from archives (<-!).

    Races all archive sources, returns first successful result.
    """
    try:
        from modules.BACKDRILL.backdrill import Backdrill

        bd = Backdrill()
        result = await bd.fetch(url, **kwargs)

        if result.success:
            return {
                "url": result.url,
                "content": result.content,
                "html": result.html,
                "timestamp": result.timestamp.isoformat() if result.timestamp else None,
                "source": result.source.value if result.source else None,
                "status_code": result.status_code,
                "mime_type": result.mime_type,
                "success": True,
            }
        return {"url": url, "success": False, "error": "No archive found"}
    except ImportError:
        logger.warning("BACKDRILL not available")
        return {"url": url, "success": False, "error": "BACKDRILL not installed"}
    except Exception as e:
        logger.error(f"Backdrill fetch error: {e}")
        return {"url": url, "success": False, "error": str(e)}


async def wayback(url: str, **kwargs) -> Dict[str, Any]:
    """
    Fetch from Wayback Machine specifically (wb:).
    """
    try:
        from modules.BACKDRILL.backdrill import Backdrill, ArchiveSource

        bd = Backdrill()
        result = await bd.fetch(url, sources=[ArchiveSource.WAYBACK_CDX, ArchiveSource.WAYBACK_DATA])

        if result.success:
            return {
                "url": result.url,
                "content": result.content,
                "timestamp": result.timestamp.isoformat() if result.timestamp else None,
                "source": "wayback",
                "success": True,
            }
        return {"url": url, "success": False, "error": "Not in Wayback"}
    except Exception as e:
        logger.error(f"Wayback fetch error: {e}")
        return {"url": url, "success": False, "error": str(e)}


async def commoncrawl(url: str, **kwargs) -> Dict[str, Any]:
    """
    Fetch from CommonCrawl specifically (cc:).
    """
    try:
        from modules.BACKDRILL.backdrill import Backdrill, ArchiveSource

        bd = Backdrill()
        result = await bd.fetch(
            url,
            sources=[
                ArchiveSource.COMMONCRAWL_INDEX,
                ArchiveSource.COMMONCRAWL_DATA,
                ArchiveSource.COMMONCRAWL_WAT,
            ]
        )

        if result.success:
            return {
                "url": result.url,
                "content": result.content,
                "timestamp": result.timestamp.isoformat() if result.timestamp else None,
                "source": "commoncrawl",
                "success": True,
            }
        return {"url": url, "success": False, "error": "Not in CommonCrawl"}
    except Exception as e:
        logger.error(f"CommonCrawl fetch error: {e}")
        return {"url": url, "success": False, "error": str(e)}


async def fetch_batch(urls: List[str], concurrent: int = 50, **kwargs) -> List[Dict[str, Any]]:
    """
    Batch fetch from archives.
    """
    try:
        from modules.BACKDRILL.backdrill import Backdrill

        bd = Backdrill()
        results = await bd.fetch_batch(urls, concurrent=concurrent)

        return [
            {
                "url": r.url,
                "content": r.content,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "source": r.source.value if r.source else None,
                "success": r.success,
            }
            for r in results
        ]
    except Exception as e:
        logger.error(f"Backdrill batch error: {e}")
        return [{"url": u, "success": False, "error": str(e)} for u in urls]


async def search(domain: str, query: str = "*", limit: int = 100, **kwargs) -> List[Dict[str, Any]]:
    """
    Search archives for domain content.
    """
    try:
        from modules.BACKDRILL.backdrill import Backdrill

        bd = Backdrill()
        results = await bd.search(domain, query=query, limit=limit, **kwargs)

        return [
            {
                "url": r.url,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "source": r.source.value if r.source else None,
            }
            for r in results
        ]
    except Exception as e:
        logger.error(f"Backdrill search error: {e}")
        return []
