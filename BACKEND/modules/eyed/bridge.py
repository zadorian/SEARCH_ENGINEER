"""
EYE-D Bridge - Interface for SASTRE and other modules

Bridge to EYE-D entity extraction.
Direct extraction (not via Linklater):
- Backends: regex, gliner, haiku, gemini, gpt
"""

import os
import logging
import aiohttp
from typing import Dict, Any

logger = logging.getLogger(__name__)

PYTHON_API_BASE_URL = os.getenv("PYTHON_API_BASE_URL", "http://localhost:8000")


class EyedBridge:
    """
    Bridge to EYE-D entity extraction.

    Endpoints:
    - POST /api/linklater/extraction/extract
    - POST /api/linklater/extraction/extract-entities-haiku

    Backends: regex, gliner, haiku, gemini, gpt
    """

    def __init__(self, base_url: str = PYTHON_API_BASE_URL):
        self.base_url = base_url
        self._session = None

    async def _get_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def extract(
        self,
        text: str = None,
        html: str = None,
        url: str = "",
        backend: str = "auto",
        extract_relationships: bool = True
    ) -> Dict[str, Any]:
        """
        Extract entities from text/HTML.

        Args:
            text: Plain text (converted to html internally)
            html: Raw HTML
            url: Source URL
            backend: "auto", "regex", "gliner", "haiku", "gemini", "gpt"
            extract_relationships: Also extract relationships/edges

        Returns:
            {
                "persons": [...],
                "companies": [...],
                "emails": [...],
                "phones": [...],
                "edges": [...]  # Relationships
            }
        """
        try:
            session = await self._get_session()
            payload = {
                "url": url,
                "backend": backend,
                "extract_relationships": extract_relationships
            }
            if html:
                payload["html"] = html
            elif text:
                payload["html"] = f"<body>{text}</body>"

            async with session.post(
                f"{self.base_url}/api/linklater/extraction/extract",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status >= 400:
                    return {"persons": [], "companies": [], "emails": [], "phones": [], "edges": []}
                return await resp.json()
        except Exception as e:
            logger.error(f"EYE-D extraction error: {e}")
            return {"persons": [], "companies": [], "emails": [], "phones": [], "edges": []}

    async def extract_with_haiku(
        self,
        text: str,
        url: str = ""
    ) -> Dict[str, Any]:
        """Extract using Haiku 4.5 specifically (includes relationships)."""
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/linklater/extraction/extract-entities-haiku",
                json={"text": text, "url": url},
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status >= 400:
                    return {"persons": [], "companies": [], "emails": [], "phones": [], "edges": []}
                return await resp.json()
        except Exception as e:
            logger.error(f"Haiku extraction error: {e}")
            return {"persons": [], "companies": [], "emails": [], "phones": [], "edges": []}


__all__ = ['EyedBridge']
