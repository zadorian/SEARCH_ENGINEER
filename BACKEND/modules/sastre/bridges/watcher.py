"""
Watcher HTTP Client - Calls TypeScript watcher system.

All 15 tRPC procedures from watcherRouter.ts:
- create, createEvent, createTopic, createEntity
- addContext, removeContext, updateDirective, getContext
- list, listActive, listForDocument, get
- updateStatus, delete, toggle
"""

import os
import json
import logging
import aiohttp
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

NODE_API_BASE_URL = os.getenv("NODE_API_BASE_URL", "http://localhost:3000")


class WatcherBridge:
    """
    HTTP client to TypeScript watcher system.

    Watchers are bidirectional:
    - Header → Watcher: Document header triggers investigation query
    - Finding → Section: New findings stream back to document sections
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

    async def _trpc_mutation(self, procedure: str, input_data: Dict) -> Dict[str, Any]:
        """Execute a tRPC mutation."""
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/trpc/watcher.{procedure}",
                params={"batch": "1"},
                json={"0": {"json": input_data}},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text()}
                result = await resp.json()
                if isinstance(result, list) and result:
                    return result[0].get("result", {}).get("data", {})
                return {}
        except Exception as e:
            logger.error(f"Watcher mutation error: {e}")
            return {"error": str(e)}

    async def _trpc_query(self, procedure: str, input_data: Dict) -> Dict[str, Any]:
        """Execute a tRPC query."""
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/api/trpc/watcher.{procedure}",
                params={"batch": "1", "input": json.dumps({"0": {"json": input_data}})},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text()}
                result = await resp.json()
                if isinstance(result, list) and result:
                    return result[0].get("result", {}).get("data", {})
                return {}
        except Exception as e:
            logger.error(f"Watcher query error: {e}")
            return {"error": str(e)}

    # =========================================================================
    # CREATE OPERATIONS
    # =========================================================================

    async def create(
        self,
        name: str,
        project_id: str,
        query: str = None,
        parent_document_id: str = None,
        trigger: str = None
    ) -> Dict[str, Any]:
        """Create a new watcher (graph-based)."""
        payload = {"name": name, "projectId": project_id}
        if query:
            payload["query"] = query
        if parent_document_id:
            payload["parentDocumentId"] = parent_document_id
        if trigger:
            payload["trigger"] = trigger
        return await self._trpc_mutation("create", payload)

    async def create_event_watcher(
        self,
        project_id: str,
        monitored_event: str,
        label: str = None,
        monitored_entities: List[str] = None,
        alert_on_any_match: bool = False,
        temporal_window: Dict = None,
        parent_document_id: str = None
    ) -> Dict[str, Any]:
        """Create an Event Watcher (ET3)."""
        payload = {"projectId": project_id, "monitoredEvent": monitored_event}
        if label:
            payload["label"] = label
        if monitored_entities:
            payload["monitoredEntities"] = monitored_entities
        if alert_on_any_match:
            payload["alertOnAnyMatch"] = alert_on_any_match
        if temporal_window:
            payload["temporalWindow"] = temporal_window
        if parent_document_id:
            payload["parentDocumentId"] = parent_document_id
        return await self._trpc_mutation("createEvent", payload)

    async def create_topic_watcher(
        self,
        project_id: str,
        label: str,
        monitored_topic: str,
        monitored_entities: List[str] = None,
        jurisdiction_filter: List[str] = None,
        parent_document_id: str = None
    ) -> Dict[str, Any]:
        """Create a Topic Watcher (ET3)."""
        payload = {
            "projectId": project_id,
            "label": label,
            "monitoredTopic": monitored_topic
        }
        if monitored_entities:
            payload["monitoredEntities"] = monitored_entities
        if jurisdiction_filter:
            payload["jurisdictionFilter"] = jurisdiction_filter
        if parent_document_id:
            payload["parentDocumentId"] = parent_document_id
        return await self._trpc_mutation("createTopic", payload)

    async def create_entity_watcher(
        self,
        project_id: str,
        label: str = None,
        monitored_types: List[str] = None,
        monitored_names: List[str] = None,
        role_filter: List[str] = None,
        jurisdiction_filter: List[str] = None,
        alert_on_any_match: bool = False,
        parent_document_id: str = None
    ) -> Dict[str, Any]:
        """Create an Entity Watcher (Unified Extraction)."""
        payload = {"projectId": project_id}
        if label:
            payload["label"] = label
        if monitored_types:
            payload["monitoredTypes"] = monitored_types
        if monitored_names:
            payload["monitoredNames"] = monitored_names
        if role_filter:
            payload["roleFilter"] = role_filter
        if jurisdiction_filter:
            payload["jurisdictionFilter"] = jurisdiction_filter
        if alert_on_any_match:
            payload["alertOnAnyMatch"] = alert_on_any_match
        if parent_document_id:
            payload["parentDocumentId"] = parent_document_id
        return await self._trpc_mutation("createEntity", payload)

    async def create_watchers_from_document(
        self,
        document_id: str
    ) -> List[Dict[str, Any]]:
        """
        Create watchers from all headers in a document.
        
        This converts every header (## Section) into a watcher,
        using the header text as the watcher query.
        """
        try:
            # This endpoint is specific to the Graph API, not tRPC
            # We use the base_url which is usually http://localhost:3000
            # But the graph API might be at http://localhost:3001
            # Let's check if we need to adjust the URL or if the bridge handles it.
            # The bridge uses NODE_API_BASE_URL.
            
            # The endpoint path from legacy code was /api/graph/watchers/create-from-document
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/graph/watchers/create-from-document",
                json={"noteId": document_id},
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status >= 400:
                    logger.error(f"Failed to create watchers from document: {await resp.text()}")
                    return []
                result = await resp.json()
                return result.get("watchers", [])
        except Exception as e:
            logger.error(f"Error creating watchers from document: {e}")
            return []

    # =========================================================================
    # CONTEXT OPERATIONS
    # =========================================================================

    async def add_context(
        self,
        watcher_id: str,
        node_id: str
    ) -> Dict[str, Any]:
        """Add context node to watcher."""
        return await self._trpc_mutation("addContext", {
            "watcherId": watcher_id,
            "nodeId": node_id
        })

    async def remove_context(
        self,
        watcher_id: str,
        node_id: str
    ) -> Dict[str, Any]:
        """Remove context node from watcher."""
        return await self._trpc_mutation("removeContext", {
            "watcherId": watcher_id,
            "nodeId": node_id
        })

    async def get_context(self, watcher_id: str) -> Dict[str, Any]:
        """Get watcher context nodes."""
        return await self._trpc_query("getContext", {"watcherId": watcher_id})

    async def update_directive(
        self,
        watcher_id: str,
        directive: str
    ) -> Dict[str, Any]:
        """Update watcher directive note."""
        return await self._trpc_mutation("updateDirective", {
            "watcherId": watcher_id,
            "directive": directive
        })

    # =========================================================================
    # LIST/GET OPERATIONS
    # =========================================================================

    async def list_all(self, project_id: str) -> List[Dict]:
        """List all watchers in project."""
        result = await self._trpc_query("list", {"projectId": project_id})
        return result.get("watchers", []) if isinstance(result, dict) else []

    async def list_active(self, project_id: str) -> List[Dict]:
        """List active watchers in project."""
        result = await self._trpc_query("listActive", {"projectId": project_id})
        return result.get("watchers", []) if isinstance(result, dict) else []

    async def list_for_document(self, document_id: str) -> List[Dict]:
        """Get watchers for a document."""
        result = await self._trpc_query("listForDocument", {"documentId": document_id})
        return result.get("watchers", []) if isinstance(result, dict) else []

    async def get(self, watcher_id: str) -> Dict[str, Any]:
        """Get watcher by ID."""
        return await self._trpc_query("get", {"watcherId": watcher_id})

    # =========================================================================
    # UPDATE/DELETE OPERATIONS
    # =========================================================================

    async def update_status(
        self,
        watcher_id: str,
        status: str
    ) -> Dict[str, Any]:
        """Update watcher status."""
        return await self._trpc_mutation("updateStatus", {
            "watcherId": watcher_id,
            "status": status
        })

    async def delete(self, watcher_id: str) -> Dict[str, Any]:
        """Delete watcher."""
        return await self._trpc_mutation("delete", {"watcherId": watcher_id})

    async def toggle(self, watcher_id: str) -> Dict[str, Any]:
        """Toggle watcher active status."""
        return await self._trpc_mutation("toggle", {"watcherId": watcher_id})


__all__ = ['WatcherBridge']
