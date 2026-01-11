"""
Narrative HTTP Client - Calls Node API narrative/notes endpoints.

Endpoints from narrativesRouter.ts and graphRouter.ts:
- GET/POST /api/narratives/projects/:projectId/documents
- GET/PUT /api/narratives/documents/:documentId
- POST/GET /api/graph/notes
- POST /api/graph/narratives/:narrativeId/detect-entities
"""

import os
import logging
import aiohttp
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

NODE_API_BASE_URL = os.getenv("NODE_API_BASE_URL", "http://localhost:3000")


class NarrativeBridge:
    """
    HTTP client to narrative/notes system.

    NOT a bridge to a module - this calls Node API endpoints.
    """

    def __init__(self, base_url: str = NODE_API_BASE_URL):
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

    # =========================================================================
    # DOCUMENT OPERATIONS
    # =========================================================================

    async def list_documents(self, project_id: str) -> List[Dict]:
        """Get all documents in a project."""
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/api/narratives/projects/{project_id}/documents",
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status >= 400:
                    return []
                data = await resp.json()
                return data.get("documents", [])
        except Exception as e:
            logger.error(f"List documents error: {e}")
            return []

    async def create_document(
        self,
        project_id: str,
        title: str
    ) -> Dict[str, Any]:
        """
        Create new document.

        Note: Initial content should be set via update_document() after creation.
        """
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/narratives/projects/{project_id}/documents",
                json={"title": title},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text()}
                return await resp.json()
        except Exception as e:
            logger.error(f"Create document error: {e}")
            return {"error": str(e)}

    async def get_document(self, document_id: str) -> Dict[str, Any]:
        """Get document by ID."""
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/api/narratives/documents/{document_id}",
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text()}
                return await resp.json()
        except Exception as e:
            logger.error(f"Get document error: {e}")
            return {"error": str(e)}

    async def update_document(
        self,
        document_id: str,
        title: str = None,
        markdown: str = None
    ) -> Dict[str, Any]:
        """Update document."""
        payload = {}
        if title:
            payload["title"] = title
        if markdown:
            payload["markdown"] = markdown

        try:
            session = await self._get_session()
            async with session.put(
                f"{self.base_url}/api/narratives/documents/{document_id}",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text()}
                return await resp.json()
        except Exception as e:
            logger.error(f"Update document error: {e}")
            return {"error": str(e)}

    # =========================================================================
    # NOTE OPERATIONS
    # =========================================================================

    async def get_project_notes(self, project_id: str) -> List[Dict]:
        """Get all notes for a project."""
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/api/graph/project-notes",
                params={"projectId": project_id},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status >= 400:
                    return []
                data = await resp.json()
                return data.get("notes", [])
        except Exception as e:
            logger.error(f"Get project notes error: {e}")
            return []

    async def create_note(
        self,
        project_id: str,
        label: str,
        content: str = ""
    ) -> Dict[str, Any]:
        """Create a narrative note."""
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/graph/notes",
                json={
                    "label": label,
                    "content": content,
                    "projectId": project_id
                },
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text()}
                return await resp.json()
        except Exception as e:
            logger.error(f"Create note error: {e}")
            return {"error": str(e)}

    async def update_note(
        self,
        note_id: str,
        label: str = None,
        content: str = None
    ) -> Dict[str, Any]:
        """Update a note."""
        payload = {}
        if label:
            payload["label"] = label
        if content:
            payload["content"] = content

        try:
            session = await self._get_session()
            async with session.put(
                f"{self.base_url}/api/graph/notes/{note_id}",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text()}
                return await resp.json()
        except Exception as e:
            logger.error(f"Update note error: {e}")
            return {"error": str(e)}

    # =========================================================================
    # ENTITY DETECTION
    # =========================================================================

    async def detect_entities_in_narrative(
        self,
        narrative_id: str
    ) -> Dict[str, Any]:
        """Detect entities in a narrative document."""
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/graph/narratives/{narrative_id}/detect-entities",
                json={},
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text()}
                return await resp.json()
        except Exception as e:
            logger.error(f"Detect entities error: {e}")
            return {"error": str(e)}


__all__ = ['NarrativeBridge']
