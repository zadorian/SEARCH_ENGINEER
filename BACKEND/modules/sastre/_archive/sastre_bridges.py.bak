"""
SASTRE Bridges - Integration with Existing Infrastructure

Bridges to:
- Cymonides/WDC: Unknown Knowns check (corpus search before external)
- Linklater: Link intelligence, backlinks, entity extraction
- Watchers: Headers <-> prompts bidirectional (TypeScript)
- IO Matrix: 5,620+ rules for investigation routing
"""

import sys
import os
import asyncio
import aiohttp
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

# Add paths for imports
SASTRE_DIR = Path(__file__).parent
BACKEND_PATH = SASTRE_DIR.parent.parent
MODULES_PATH = SASTRE_DIR.parent

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))
if str(MODULES_PATH) not in sys.path:
    sys.path.insert(0, str(MODULES_PATH))

NODE_API_BASE_URL = os.getenv("NODE_API_BASE_URL", "http://localhost:3000")
PYTHON_API_BASE_URL = os.getenv("PYTHON_API_BASE_URL", "http://localhost:8000")


# =============================================================================
# CYMONIDES BRIDGE (Unknown Knowns Check)
# =============================================================================

class CymonidesBridge:
    """
    Bridge to Cymonides entity storage and WDC indices.

    This is the UNKNOWN KNOWNS check - search what we already have
    before going to external sources.

    Uses:
    - wdc-person-entities: Person records from Schema.org
    - wdc-organization-entities: Company/org records
    - wdc-localbusiness-entities: Local business records
    - wdc-product-entities: Product records
    """

    def __init__(self):
        self._wdc_service = None
        self._loaded = False

    def _lazy_load(self):
        """Lazy load WDC service."""
        if self._loaded:
            return

        try:
            from DEFINITIONAL.wdc_query import (
                WDCQueryService,
                search_person_entities,
                search_organization_entities,
                search_localbusiness_entities,
                search_product_entities,
            )
            self._wdc_service = WDCQueryService()
            self._search_person = search_person_entities
            self._search_org = search_organization_entities
            self._search_local = search_localbusiness_entities
            self._search_product = search_product_entities
            self._loaded = True
            print("✓ Cymonides/WDC bridge loaded")
        except ImportError as e:
            print(f"Warning: Could not import WDC service: {e}")
            self._loaded = True  # Don't retry

    def check_unknown_knowns(
        self,
        entity_type: str,
        value: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Check corpus for existing knowledge about an entity.

        This is the UNKNOWN KNOWNS check - we might already have
        relevant data in our indices.

        Args:
            entity_type: Type of entity ('person', 'company', 'email', etc.)
            value: Entity value to search for
            limit: Max results

        Returns:
            List of matching entities from corpus
        """
        self._lazy_load()

        if not self._wdc_service:
            return []

        try:
            if entity_type in ('person', 'p:'):
                return self._search_person(name=value, limit=limit)
            elif entity_type in ('company', 'c:', 'organization'):
                return self._search_org(name=value, limit=limit)
            elif entity_type in ('email', 'e:'):
                # Search by email across indices
                return self._wdc_service.search_by_email(value, exact=False, limit=limit)
            elif entity_type in ('phone', 't:'):
                return self._wdc_service.search_by_phone(value, limit=limit)
            elif entity_type in ('domain', 'd:'):
                return self._wdc_service.find_by_domain(value, limit=limit).get('results', [])
            else:
                # Generic search
                return self._wdc_service.search_entities(value, limit=limit).get('results', [])
        except Exception as e:
            print(f"Unknown Knowns check error: {e}")
            return []

    def search_by_email(self, email: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Search corpus by email address."""
        self._lazy_load()
        if self._wdc_service:
            try:
                result = self._wdc_service.search_by_email(email, exact=False, limit=limit)
                return result if isinstance(result, list) else []
            except Exception as e:
                print(f"Email search error: {e}")
        return []

    def search_by_phone(self, phone: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Search corpus by phone number."""
        self._lazy_load()
        if self._wdc_service:
            try:
                result = self._wdc_service.search_by_phone(phone, limit=limit)
                return result if isinstance(result, list) else []
            except Exception as e:
                print(f"Phone search error: {e}")
        return []

    def get_domains_with_entity_type(
        self,
        entity_type: str,
        geo: Optional[str] = None,
        limit: int = 1000
    ) -> List[str]:
        """
        Get domains that have entities of a specific type.

        Useful for targeted searches - find where to look first.
        """
        self._lazy_load()
        if self._wdc_service:
            try:
                result = self._wdc_service.get_domains_by_type(entity_type, geo=geo, limit=limit)
                return result if isinstance(result, list) else []
            except Exception as e:
                print(f"Get domains error: {e}")
        return []


# =============================================================================
# LINKLATER BRIDGE (Link Intelligence)
# =============================================================================

class LinklaterBridge:
    """
    Bridge to Linklater link intelligence system.

    Provides:
    - Backlinks (domains linking TO target)
    - Outlinks (domains linked FROM target)
    - Entity extraction (AI-powered)
    - Archive scraping (CC -> Wayback -> Firecrawl)
    - Co-citation (related sites)
    - WHOIS clustering (ownership-linked domains)
    """

    def __init__(self):
        self._linklater = None
        self._loaded = False

    def _lazy_load(self):
        """Lazy load Linklater API."""
        if self._loaded:
            return

        try:
            # Linklater requires async context for initialization
            # Mark as loaded but defer actual init to async methods
            self._loaded = True
            print("✓ Linklater bridge available (lazy init)")
        except Exception as e:
            print(f"Warning: Linklater setup error: {e}")
            self._loaded = True

    async def _ensure_linklater(self):
        """Ensure Linklater is initialized (must be called from async context)."""
        if self._linklater is not None:
            return self._linklater

        try:
            from modules.LINKLATER.api import get_linklater
            self._linklater = get_linklater()
            return self._linklater
        except Exception as e:
            print(f"Warning: Could not initialize Linklater: {e}")
            return None

    @property
    def api(self):
        """Get Linklater API instance (may be None until async init)."""
        self._lazy_load()
        return self._linklater

    async def get_backlinks(self, domain: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get backlinks (domains linking TO this domain).

        Uses CC Web Graph (157M domains, 2.1B edges) + GlobalLinks.
        """
        linklater = await self._ensure_linklater()
        if not linklater:
            return []

        try:
            records = await linklater.get_backlinks(domain, limit=limit)
            return [
                {
                    'source_domain': getattr(r, 'source_domain', str(r)),
                    'target_domain': domain,
                    'link_type': 'backlink',
                }
                for r in records
            ]
        except Exception as e:
            print(f"Backlinks error: {e}")
            return []

    async def get_outlinks(self, domain: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get outlinks (domains this domain links TO).
        """
        linklater = await self._ensure_linklater()
        if not linklater:
            return []

        try:
            records = await linklater.get_outlinks(domain, limit=limit)
            return [
                {
                    'source_domain': domain,
                    'target_domain': getattr(r, 'target_domain', str(r)),
                    'link_type': 'outlink',
                }
                for r in records
            ]
        except Exception as e:
            print(f"Outlinks error: {e}")
            return []

    async def get_related_sites(self, domain: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get co-cited/related domains (Majestic).

        Finds domains frequently mentioned alongside target.
        """
        linklater = await self._ensure_linklater()
        if not linklater:
            return []

        try:
            return await linklater.get_related_links(domain, max_results=limit)
        except Exception as e:
            print(f"Related sites error: {e}")
            return []

    async def get_ownership_linked(self, domain: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get domains linked through common ownership (WHOIS).
        """
        linklater = await self._ensure_linklater()
        if not linklater:
            return []

        try:
            return await linklater.get_ownership_linked(domain, max_results=limit)
        except Exception as e:
            print(f"Ownership linked error: {e}")
            return []

    async def extract_entities(
        self,
        text: str,
        url: str = "",
        backend: str = "auto"
    ) -> Dict[str, List]:
        """
        Extract entities from text using AI-powered extraction.

        Backends: auto (best available), gemini, gpt, gliner, regex
        """
        linklater = await self._ensure_linklater()
        if not linklater:
            return {"persons": [], "companies": [], "emails": [], "phones": []}

        try:
            return await linklater.extract_entities(text, url, backend=backend)
        except Exception as e:
            print(f"Entity extraction error: {e}")
            return {"persons": [], "companies": [], "emails": [], "phones": []}

    async def scrape_url(self, url: str) -> Optional[str]:
        """
        Scrape URL with 3-tier fallback (CC -> Wayback -> Firecrawl).
        """
        linklater = await self._ensure_linklater()
        if not linklater:
            return None

        try:
            result = await linklater.scrape_url(url)
            return result.content if result else None
        except Exception as e:
            print(f"Scrape error: {e}")
            return None


# =============================================================================
# WATCHER BRIDGE (Headers <-> Prompts)
# =============================================================================

class WatcherBridge:
    """
    Bridge to TypeScript watcher system - ALL 15 procedures.

    Watchers are bidirectional:
    - Header → Watcher: Document header triggers investigation query
    - Finding → Section: New findings stream back to document sections

    tRPC endpoints from watcherRouter.ts:
    1. create - Basic watcher creation
    2. createEvent - Event watcher (ET3)
    3. createTopic - Topic watcher (ET3)
    4. createEntity - Entity watcher
    5. addContext - Add context node
    6. removeContext - Remove context node
    7. updateDirective - Update watcher directive note
    8. getContext - Get watcher context nodes
    9. list - List all watchers
    10. listActive - List active watchers
    11. listForDocument - Get watchers for a document
    12. get - Get watcher by ID
    13. updateStatus - Update watcher status
    14. delete - Delete watcher
    15. toggle - Toggle watcher active status
    """

    def __init__(self, base_url: str = NODE_API_BASE_URL):
        self.base_url = base_url
        self._session = None

    async def _get_session(self):
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

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
            return {"error": str(e)}

    async def _trpc_query(self, procedure: str, input_data: Dict) -> Dict[str, Any]:
        """Execute a tRPC query."""
        try:
            session = await self._get_session()
            import json
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
            return {"error": str(e)}

    # =========================================================================
    # 1. create - Basic watcher creation
    # =========================================================================

    async def create(
        self,
        name: str,
        project_id: str,
        query: str = None,
        parent_document_id: str = None
    ) -> Dict[str, Any]:
        """
        Create a new watcher (graph-based).

        tRPC: watcher.create
        """
        payload = {"name": name, "projectId": project_id}
        if query:
            payload["query"] = query
        if parent_document_id:
            payload["parentDocumentId"] = parent_document_id
        return await self._trpc_mutation("create", payload)

    # =========================================================================
    # 2. createEvent - Event watcher (ET3)
    # =========================================================================

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
        """
        Create an Event Watcher (ET3).

        Monitors for specific event type occurrences (IPO, Lawsuit, Data Breach, etc.)

        tRPC: watcher.createEvent
        """
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

    # =========================================================================
    # 3. createTopic - Topic watcher (ET3)
    # =========================================================================

    async def create_topic_watcher(
        self,
        project_id: str,
        label: str,
        monitored_topic: str,
        monitored_entities: List[str] = None,
        jurisdiction_filter: List[str] = None,
        parent_document_id: str = None
    ) -> Dict[str, Any]:
        """
        Create a Topic Watcher (ET3).

        Monitors for specific topic mentions (Sanctions, Compliance, Investigation, etc.)

        tRPC: watcher.createTopic
        """
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

    # =========================================================================
    # 4. createEntity - Entity watcher
    # =========================================================================

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
        """
        Create an Entity Watcher (Unified Extraction).

        Monitors for specific entity types (person, company, email) or named entities.

        tRPC: watcher.createEntity
        """
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

    # =========================================================================
    # 5. addContext - Add context node
    # =========================================================================

    async def add_context(
        self,
        watcher_id: str,
        node_id: str,
        project_id: str
    ) -> Dict[str, Any]:
        """Add context node to watcher. tRPC: watcher.addContext"""
        return await self._trpc_mutation("addContext", {
            "watcherId": watcher_id,
            "nodeId": node_id,
            "projectId": project_id
        })

    # =========================================================================
    # 6. removeContext - Remove context node
    # =========================================================================

    async def remove_context(
        self,
        watcher_id: str,
        node_id: str,
        project_id: str
    ) -> Dict[str, Any]:
        """Remove context node from watcher. tRPC: watcher.removeContext"""
        return await self._trpc_mutation("removeContext", {
            "watcherId": watcher_id,
            "nodeId": node_id,
            "projectId": project_id
        })

    # =========================================================================
    # 7. updateDirective - Update watcher directive note
    # =========================================================================

    async def update_directive(
        self,
        watcher_id: str,
        content: str,
        project_id: str
    ) -> Dict[str, Any]:
        """Update watcher directive note. tRPC: watcher.updateDirective"""
        return await self._trpc_mutation("updateDirective", {
            "watcherId": watcher_id,
            "content": content,
            "projectId": project_id
        })

    # =========================================================================
    # 8. getContext - Get watcher context nodes
    # =========================================================================

    async def get_context(self, watcher_id: str) -> Dict[str, Any]:
        """Get watcher context nodes. tRPC: watcher.getContext"""
        return await self._trpc_query("getContext", {"watcherId": watcher_id})

    # =========================================================================
    # 9. list - List all watchers
    # =========================================================================

    async def list_all(self, project_id: str) -> List[Dict[str, Any]]:
        """List all watchers for a project. tRPC: watcher.list"""
        result = await self._trpc_query("list", {"projectId": project_id})
        if isinstance(result, list):
            return result
        return result.get("watchers", []) if isinstance(result, dict) else []

    # =========================================================================
    # 10. listActive - List active watchers
    # =========================================================================

    async def list_active(self, project_id: str) -> List[Dict[str, Any]]:
        """List active watchers for a project. tRPC: watcher.listActive"""
        result = await self._trpc_query("listActive", {"projectId": project_id})
        if isinstance(result, list):
            return result
        return result.get("watchers", []) if isinstance(result, dict) else []

    # =========================================================================
    # 11. listForDocument - Get watchers for a document
    # =========================================================================

    async def list_for_document(self, document_id: str) -> List[Dict[str, Any]]:
        """Get watchers for a specific document. tRPC: watcher.listForDocument"""
        result = await self._trpc_query("listForDocument", {"documentId": document_id})
        if isinstance(result, list):
            return result
        return result.get("watchers", []) if isinstance(result, dict) else []

    # =========================================================================
    # 12. get - Get watcher by ID
    # =========================================================================

    async def get(self, watcher_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific watcher by ID. tRPC: watcher.get"""
        result = await self._trpc_query("get", {"id": watcher_id})
        return result if result and not result.get("error") else None

    # =========================================================================
    # 13. updateStatus - Update watcher status
    # =========================================================================

    async def update_status(
        self,
        watcher_id: str,
        status: str
    ) -> Dict[str, Any]:
        """
        Update watcher status.

        Status: 'active', 'paused', 'completed'

        tRPC: watcher.updateStatus
        """
        return await self._trpc_mutation("updateStatus", {
            "id": watcher_id,
            "status": status
        })

    # =========================================================================
    # 14. delete - Delete watcher
    # =========================================================================

    async def delete(self, watcher_id: str) -> Dict[str, Any]:
        """Delete a watcher. tRPC: watcher.delete"""
        return await self._trpc_mutation("delete", {"id": watcher_id})

    # =========================================================================
    # 15. toggle - Toggle watcher active status
    # =========================================================================

    async def toggle(self, watcher_id: str) -> Dict[str, Any]:
        """Toggle watcher active status. tRPC: watcher.toggle"""
        return await self._trpc_mutation("toggle", {"id": watcher_id})

    # =========================================================================
    # 16. execute - Execute watchers against results
    # =========================================================================

    async def execute(
        self,
        project_id: str,
        results: List[Dict[str, Any]],
        query: str = None,
        query_node_id: str = None,
    ) -> Dict[str, Any]:
        """
        Execute watchers against provided results.

        This is the key integration point for SASTRE:
        - After action handlers return results, call this method
        - Watcher executor evaluates results against active watchers
        - Findings are routed to document sections

        Args:
            project_id: Graph project ID
            results: List of search results to evaluate
                Each result should have: title, url, content/snippet
            query: Original query (optional, for context)
            query_node_id: Query node ID (optional, for graph edges)

        Returns:
            Dict with findings summary:
            {
                "success": true,
                "findings": {
                    "header": 5,
                    "event": 2,
                    "topic": 3,
                    "entity": 10,
                    "total": 20
                }
            }

        tRPC: watcher.execute
        """
        # Normalize results to expected format
        normalized_results = []
        for r in results:
            normalized_results.append({
                "title": r.get("title", r.get("name", "Untitled")),
                "url": r.get("url", r.get("source", "")),
                "content": r.get("content", r.get("description", "")),
                "snippet": r.get("snippet", r.get("excerpt", "")),
                "sourceId": r.get("sourceId", r.get("id", "")),
                "datePublished": r.get("datePublished", r.get("date", "")),
                "dateDiscovered": r.get("dateDiscovered", ""),
            })

        payload = {
            "projectId": project_id,
            "results": normalized_results,
        }
        if query:
            payload["query"] = query
        if query_node_id:
            payload["queryNodeId"] = query_node_id

        return await self._trpc_mutation("execute", payload)

    # =========================================================================
    # LEGACY METHODS (graphRouter.ts endpoints - keep for backwards compat)
    # =========================================================================

    async def create_watchers_from_document(
        self,
        note_id: str
    ) -> List[Dict[str, Any]]:
        """
        Create watchers from all headers in a document.

        Calls: POST /api/graph/watchers/create-from-document
        Maps to: createWatchersFromDocument() in watcherService.ts
        """
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/graph/watchers/create-from-document",
                json={"noteId": note_id},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('watchers', [])
                else:
                    print(f"Create watchers failed: {response.status}")
                    return []
        except Exception as e:
            print(f"Create watchers error: {e}")
            return []

    async def create_watcher_from_header(
        self,
        note_id: str,
        header: str,
        entity_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create a single watcher from a document header.

        Calls: POST /api/graph/watchers/create-from-header
        """
        try:
            session = await self._get_session()
            payload = {
                "noteId": note_id,
                "header": header,
            }
            if entity_name:
                payload["entityName"] = entity_name

            async with session.post(
                f"{self.base_url}/api/graph/watchers/create-from-header",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return None
        except Exception as e:
            print(f"Create watcher error: {e}")
            return None

    # NOTE: add_finding() removed - endpoint /api/graph/watchers/test-add-finding does not exist
    # Use stream_finding_to_section() for document updates instead

    async def get_active_watchers(self) -> List[Dict[str, Any]]:
        """
        Get all active watchers.

        Calls: GET /api/graph/watchers/active
        """
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/api/graph/watchers/active",
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('watchers', [])
                else:
                    return []
        except Exception as e:
            print(f"Get active watchers error: {e}")
            return []

    async def get_watcher(self, watcher_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single watcher by ID.

        Calls: GET /api/graph/watchers/:watcherId
        """
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/api/graph/watchers/{watcher_id}",
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return None
        except Exception as e:
            print(f"Get watcher error: {e}")
            return None

    async def update_watcher_status(
        self,
        watcher_id: str,
        status: str
    ) -> bool:
        """
        Update watcher status.

        Calls: PATCH /api/graph/watchers/:watcherId/status

        Status: 'active', 'paused', 'completed', 'archived'
        """
        try:
            session = await self._get_session()
            async with session.patch(
                f"{self.base_url}/api/graph/watchers/{watcher_id}/status",
                json={"status": status},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                return response.status == 200
        except Exception as e:
            print(f"Update watcher status error: {e}")
            return False

    async def run_et3_extraction(
        self,
        watcher_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Run ET3 (Event/Topic/Entity) extraction on watchers.

        Calls: POST /api/graph/watchers/run-extraction
        """
        try:
            session = await self._get_session()
            payload = {}
            if watcher_ids:
                payload["watcherIds"] = watcher_ids

            async with session.post(
                f"{self.base_url}/api/graph/watchers/run-extraction",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {"error": f"Status {response.status}"}
        except Exception as e:
            print(f"ET3 extraction error: {e}")
            return {"error": str(e)}

    # =========================================================================
    # DOCUMENT SECTION MANAGEMENT (edithRouter.ts endpoints)
    # =========================================================================

    async def get_sections(self, document_id: str) -> List[Dict[str, Any]]:
        """
        Get all sections (virtual boxes) from a document.

        Calls: GET /narratives/documents/:documentId/sections
        """
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/narratives/documents/{document_id}/sections",
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('sections', [])
                else:
                    return []
        except Exception as e:
            print(f"Get sections error: {e}")
            return []

    async def update_section(
        self,
        document_id: str,
        section_title: str,
        content: str,
        operation: str = 'append'
    ) -> bool:
        """
        Update a document section.

        Calls: POST /narratives/documents/:documentId/sections

        Args:
            document_id: Document ID
            section_title: Header text (e.g., "## Corporate History")
            content: New content to add
            operation: 'replace', 'append', or 'prepend'
        """
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/narratives/documents/{document_id}/sections",
                json={
                    "sectionTitle": section_title,
                    "content": content,
                    "operation": operation,
                },
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                return response.status == 200
        except Exception as e:
            print(f"Update section error: {e}")
            return False

    async def create_footnote(
        self,
        document_id: str,
        footnote_number: int,
        footnote_content: str,
        source_url: Optional[str] = None,
        source_title: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create a footnote with optional source linking.

        Calls: POST /narratives/documents/:documentId/footnotes/create

        Args:
            document_id: Document ID
            footnote_number: Footnote number (e.g., 1 for [^1])
            footnote_content: Footnote text content
            source_url: Optional source URL
            source_title: Optional source title

        Returns footnote reference (e.g., [^1]) and creates source node + edge.
        """
        try:
            session = await self._get_session()
            payload = {
                "footnoteNumber": footnote_number,
                "content": footnote_content
            }
            if source_url:
                payload["sourceUrl"] = source_url
            if source_title:
                payload["sourceTitle"] = source_title

            async with session.post(
                f"{self.base_url}/narratives/documents/{document_id}/footnotes/create",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return None
        except Exception as e:
            print(f"Create footnote error: {e}")
            return None

    # =========================================================================
    # EVALUATION (Local fallback when TypeScript unavailable)
    # =========================================================================

    def _local_evaluate(
        self,
        results: Dict[str, Any],
        watchers: Dict[str, Dict]
    ) -> List[Dict[str, Any]]:
        """
        Local fallback evaluation when TypeScript unavailable.

        Simple keyword matching against watcher targets.
        """
        findings = []

        for header, config in watchers.items():
            target = config.get('target', '')
            if not target:
                continue

            results_str = str(results).lower()
            target_words = target.lower().split()

            if any(word in results_str for word in target_words):
                findings.append({
                    'header': header,
                    'matched': True,
                    'results': results,
                    'match_type': 'keyword',
                })

        return findings

    async def evaluate_against_watchers(
        self,
        results: Dict[str, Any],
        watchers: List[Dict]
    ) -> List[Dict[str, Any]]:
        """
        Evaluate results against active watchers.

        First attempts TypeScript evaluation, falls back to local.
        """
        # Convert list to dict for local evaluation
        watchers_dict = {w.get('header', ''): w for w in watchers if w.get('header')}
        return self._local_evaluate(results, watchers_dict)

    # =========================================================================
    # CONVENIENCE METHODS (High-level operations)
    # =========================================================================

    async def stream_finding_to_section(
        self,
        document_id: str,
        section_title: str,
        finding_text: str,
        footnote_number: int = None,
        source_url: Optional[str] = None
    ) -> bool:
        """
        Stream a finding to a document section with footnote.

        Combines section update + footnote creation.

        Args:
            document_id: Document ID
            section_title: Section header to update
            finding_text: Content to add
            footnote_number: Footnote number to create (optional)
            source_url: Source URL for footnote
        """
        # Create footnote first to get reference
        footnote = None
        if source_url and footnote_number:
            footnote = await self.create_footnote(
                document_id,
                footnote_number=footnote_number,
                footnote_content=finding_text[:100],
                source_url=source_url
            )

        # Append to section
        content = finding_text
        if footnote and footnote.get('reference'):
            content = f"{finding_text} {footnote['reference']}"

        return await self.update_section(
            document_id, section_title, content, operation='append'
        )


# =============================================================================
# IO MATRIX BRIDGE (Investigation Routing)
# =============================================================================

class IOBridge:
    """
    Bridge to IO Matrix system (5,620+ rules).

    Routes investigations through the correct modules based on:
    - Input type (company name, email, domain, etc.)
    - Desired output (officers, shareholders, backlinks, etc.)
    - Jurisdiction
    """

    def __init__(self):
        self._router = None
        self._executor = None
        self._chain_executor = None
        self._loaded = False

    def _lazy_load(self):
        """Lazy load IO system."""
        if self._loaded:
            return

        try:
            # Try to import from io_cli in matrix folder
            matrix_path = SASTRE_DIR.parent.parent.parent / "input_output" / "matrix"
            if str(matrix_path) not in sys.path:
                sys.path.insert(0, str(matrix_path))

            from io_cli import IORouter, IOExecutor
            self._router = IORouter()
            self._executor = IOExecutor(self._router)

            # Also load ChainExecutor for recursive chains
            try:
                from chain_executor import ChainExecutor
                self._chain_executor = ChainExecutor(self._executor)
                print(f"✓ IO Matrix loaded: {len(self._router.rules)} rules, {len(self._router.playbooks)} playbooks + ChainExecutor")
            except ImportError:
                print(f"✓ IO Matrix loaded: {len(self._router.rules)} rules, {len(self._router.playbooks)} playbooks (no ChainExecutor)")

            self._loaded = True
        except ImportError as e:
            print(f"Warning: Could not import IO system: {e}")
            self._loaded = True

    @property
    def router(self):
        """Get IO router instance."""
        self._lazy_load()
        return self._router

    @property
    def executor(self):
        """Get IO executor instance."""
        self._lazy_load()
        return self._executor

    @property
    def chain_executor(self):
        """Get ChainExecutor for recursive chain rules."""
        self._lazy_load()
        return self._chain_executor

    async def execute_chain(
        self,
        chain_rule_id: str,
        initial_value: str,
        jurisdiction: str = None
    ) -> Dict[str, Any]:
        """
        Execute a recursive chain rule.

        Chain rules expand entities recursively using strategies like:
        - recursive_expansion: Follow ownership chains
        - clustering_network: Build entity clusters
        - hierarchical_expansion: Build tree structures

        Args:
            chain_rule_id: ID of chain rule (e.g., 'CHAIN_COMPANY_OWNERSHIP')
            initial_value: Starting entity value
            jurisdiction: Optional jurisdiction filter

        Returns:
            Dict with all discovered entities and relationships
        """
        self._lazy_load()
        if self._chain_executor:
            try:
                # Find the chain rule
                chain_rule = None
                for rule in self._chain_executor.chain_rules:
                    if rule.get('id') == chain_rule_id:
                        chain_rule = rule
                        break

                if not chain_rule:
                    return {"error": f"Chain rule not found: {chain_rule_id}"}

                initial_input = {'value': initial_value, 'type': 'entity'}
                return await self._chain_executor.execute_chain(
                    chain_rule, initial_input, jurisdiction
                )
            except Exception as e:
                return {"error": str(e)}
        return {"error": "ChainExecutor not available"}

    async def execute(
        self,
        entity_type: str,
        value: str,
        jurisdiction: str = None
    ) -> Dict[str, Any]:
        """
        Execute IO investigation.

        Args:
            entity_type: Type prefix (p:, c:, e:, d:, t:)
            value: Entity value
            jurisdiction: Optional jurisdiction code

        Returns:
            Investigation results
        """
        self._lazy_load()
        if self._executor:
            try:
                return await self._executor.execute(entity_type, value, jurisdiction)
            except Exception as e:
                return {"error": str(e)}
        return {"error": "IO system not available"}

    def find_route(self, have: str, want: str) -> Dict[str, Any]:
        """
        Find route from input type to output type.

        Args:
            have: What we have (e.g., 'company_name')
            want: What we want (e.g., 'company_officers')

        Returns:
            Route configuration
        """
        self._lazy_load()
        if self._router:
            try:
                return self._router.find_route(have, want)
            except Exception:
                pass
        return {"error": "IO router not available"}

    # NOTE: get_routes_for_input() removed - IORouter.get_routes_for_input() does not exist
    # Use find_route(have, want) for route lookup instead

    def recommend_playbooks(
        self,
        entity_type: str,
        jurisdiction: str = None,
        top_n: int = 5,
        min_success_rate: float = 0.0,
        prefer_friction: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get playbook recommendations for an entity type.

        Uses IORouter's smart recommendation engine with:
        - Regional jurisdiction groups (EU, LATAM, MENA, APAC)
        - Output richness scoring
        - Friction preference matching
        - Success rate filtering

        Args:
            entity_type: "company", "person", "domain", "email", "phone"
            jurisdiction: Optional jurisdiction code (HU, GB, US, etc.)
            top_n: Number of recommendations (default: 5)
            min_success_rate: Minimum success rate filter (0.0-1.0)
            prefer_friction: Optional preferred friction level

        Returns:
            List of recommended playbooks with scores
        """
        self._lazy_load()
        if self._router and hasattr(self._router, 'recommend_playbooks'):
            try:
                return self._router.recommend_playbooks(
                    entity_type,
                    jurisdiction=jurisdiction,
                    top_n=top_n,
                    min_success_rate=min_success_rate,
                    prefer_friction=prefer_friction
                )
            except Exception as e:
                print(f"Playbook recommendation error: {e}")
                return []
        return []

    async def execute_playbook_chain(
        self,
        chain_id: str,
        value: str,
        jurisdiction: str = None,
        playbook_categories: List[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a playbook-based chain rule.

        Playbook chains use playbooks as "macro-steps" that execute
        multiple rules at once, providing strategic execution paths.

        Chain types supported:
        - playbook_cascade: Auto-select jurisdiction playbooks
        - multi_jurisdiction_sweep: Parallel multi-jurisdiction execution
        - domain_to_corporate_pivot: Domain -> registrant -> corporate
        - compliance_stack: Stacked COMPLIANCE + LEGAL playbooks
        - media_aggregation: Parallel MEDIA playbooks

        Args:
            chain_id: Chain rule ID (e.g., 'CHAIN_PLAYBOOK_FULL_COMPANY_INTEL')
            value: Input value (company name, person name, domain, etc.)
            jurisdiction: Optional jurisdiction code
            playbook_categories: Optional list of categories (REGISTRY, LEGAL, etc.)

        Returns:
            Dict with chain execution results including aggregated data
        """
        self._lazy_load()
        if self._chain_executor:
            try:
                # Import execute_playbook_chain from chain_executor
                from chain_executor import execute_playbook_chain as exec_pb_chain

                result = await exec_pb_chain(
                    chain_id,
                    value,
                    jurisdiction=jurisdiction,
                    playbook_categories=playbook_categories
                )
                return result
            except Exception as e:
                return {"error": str(e)}
        return {"error": "ChainExecutor not available"}

    def get_best_playbook_for_entity(
        self,
        entity_type: str,
        jurisdiction: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get the single best playbook for an entity type.

        Convenience method that returns only the top recommendation.

        Args:
            entity_type: "company", "person", "domain", "email", "phone"
            jurisdiction: Optional jurisdiction code

        Returns:
            Best matching playbook or None
        """
        recommendations = self.recommend_playbooks(
            entity_type,
            jurisdiction=jurisdiction,
            top_n=1
        )
        return recommendations[0] if recommendations else None

    async def execute_rule(
        self,
        rule_id: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a specific IO rule by ID.

        Args:
            rule_id: Rule identifier (e.g., 'corporella', 'eye-d')
            context: Execution context with parameters

        Returns:
            Rule execution results
        """
        self._lazy_load()
        if self._executor:
            try:
                # Map rule IDs to modules
                module_map = {
                    'corporella': ('company', context.get('search_term', '')),
                    'eye-d': ('email', context.get('search_term', '')),
                    'red_flag': ('person', context.get('search_term', '')),
                    'linklater': ('domain', context.get('domains', [None])[0] or ''),
                }

                if rule_id in module_map:
                    entity_type, value = module_map[rule_id]
                    return await self._executor.execute(entity_type, value)
                else:
                    return {"error": f"Unknown rule: {rule_id}"}
            except Exception as e:
                return {"error": str(e)}
        return {"error": "IO system not available"}


# =============================================================================
# UNIFIED INFRASTRUCTURE INTERFACE
# =============================================================================

@dataclass
class InfrastructureStatus:
    """Status of all infrastructure components."""
    cymonides_available: bool = False
    linklater_available: bool = False
    watchers_available: bool = False
    io_matrix_available: bool = False
    io_rules_count: int = 0


class SastreInfrastructure:
    """
    Unified interface to all SASTRE infrastructure.

    Single entry point for:
    - Unknown Knowns check (Cymonides/WDC)
    - Link intelligence (Linklater)
    - Watcher evaluation (TypeScript)
    - IO routing (Matrix)
    """

    def __init__(self, watcher_url: str = NODE_API_BASE_URL):
        self.cymonides = CymonidesBridge()
        self.linklater = LinklaterBridge()
        self.watchers = WatcherBridge(watcher_url)
        self.io = IOBridge()

    def get_status(self) -> InfrastructureStatus:
        """Get status of all infrastructure components."""
        # Force lazy loading to check availability
        self.cymonides._lazy_load()
        self.linklater._lazy_load()
        self.io._lazy_load()

        return InfrastructureStatus(
            cymonides_available=self.cymonides._wdc_service is not None,
            linklater_available=self.linklater._linklater is not None,
            watchers_available=True,  # Always available (fallback exists)
            io_matrix_available=self.io._router is not None,
            io_rules_count=len(self.io._router.rules) if self.io._router else 0,
        )

    async def unknown_knowns_check(
        self,
        entity_type: str,
        value: str
    ) -> List[Dict[str, Any]]:
        """
        Check what we already know (corpus search).

        This should be called BEFORE external searches to avoid
        redundant lookups.
        """
        return self.cymonides.check_unknown_knowns(entity_type, value)

    async def investigate_entity(
        self,
        entity_type: str,
        value: str,
        jurisdiction: str = None
    ) -> Dict[str, Any]:
        """
        Full entity investigation via IO system.
        """
        return await self.io.execute(entity_type, value, jurisdiction)

    async def get_link_intelligence(
        self,
        domain: str
    ) -> Dict[str, Any]:
        """
        Get comprehensive link intelligence for a domain.
        """
        backlinks = await self.linklater.get_backlinks(domain)
        outlinks = await self.linklater.get_outlinks(domain)
        related = await self.linklater.get_related_sites(domain)
        ownership = await self.linklater.get_ownership_linked(domain)

        return {
            'domain': domain,
            'backlinks': backlinks,
            'outlinks': outlinks,
            'related_sites': related,
            'ownership_linked': ownership,
        }

    async def close(self):
        """Clean up resources."""
        await self.watchers.close()


# =============================================================================
# TORPEDO BRIDGE (Company Profiles)
# =============================================================================

class TorpedoBridge:
    """
    Bridge to Torpedo company profile fetcher.

    Fetches structured company data from 30+ corporate registries worldwide.
    Self-learning CSS extraction with GPT-5-nano validation.

    Endpoints:
    - POST /api/seekleech/torpedo/profile
    - tRPC: seekleech.fetchCompanyProfile
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

    async def fetch_profile(
        self,
        company_name: str,
        jurisdiction: str,
        profile_url: str = None,
        max_attempts: int = 3
    ) -> Dict[str, Any]:
        """
        Fetch company profile from registry.

        Args:
            company_name: Company name to search
            jurisdiction: 2-letter country code (HR, RS, GB, etc.)
            profile_url: Optional direct URL (skips search)
            max_attempts: Retry with recipe improvement

        Returns:
            {
                "success": bool,
                "profile": {...},  # Extracted fields
                "profile_url": str,
                "source": {...},
                "completeness_score": float
            }
        """
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/seekleech/torpedo/profile",
                json={
                    "query": company_name,
                    "jurisdiction": jurisdiction,
                    "profile_url": profile_url,
                    "max_attempts": max_attempts
                },
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status >= 400:
                    return {"success": False, "error": await resp.text()}
                return await resp.json()
        except Exception as e:
            return {"success": False, "error": str(e)}


# =============================================================================
# JESTER BRIDGE (Document Assembly / FactAssembler)
# =============================================================================

class JesterBridge:
    """
    Bridge to Jester/FactAssembler document assembly.

    Fills document sections via Phase 0-5 pipeline:
    - Phase 0: Source discovery (BruteSearch)
    - Phase 1: Fact extraction
    - Phase 2: Classification
    - Phase 3: Synthesis
    - Phase 4: Verification
    - Phase 5: Formatting

    Endpoints:
    - POST /jester/run
    - GET /jester/stream/{jobId} (SSE)
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

    async def fill_section(
        self,
        section_header: str,
        query: str,
        context_content: str = "",
        jurisdiction: str = None,
        tier: str = "smart"
    ) -> str:
        """
        Fill a narrative section using FactAssembler.

        Args:
            section_header: The section to fill (e.g., "## Corporate History")
            query: Search/extraction goal
            context_content: Existing document context
            jurisdiction: For terrain-aware search
            tier: "fast" or "smart"

        Returns:
            job_id to track progress via stream_result()
        """
        micro_content = f"# Context\n\n{context_content}\n\n{section_header}\n"

        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/jester/run",
                json={
                    "mode": "fill_section",
                    "content": micro_content,
                    "query": query,
                    "config": {
                        "context": section_header,
                        "tier": tier,
                        "verify": True,
                        "directory_jurisdiction": jurisdiction or ""
                    }
                },
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status >= 400:
                    return ""
                data = await resp.json()
                return data.get("jobId", "")
        except Exception as e:
            print(f"Jester fill_section error: {e}")
            return ""

    async def stream_result(self, job_id: str):
        """
        Stream job progress and final result via SSE.

        Yields:
            {"type": "status", "status": "running"}
            {"text": "Phase 1: Extracting..."}
            {"type": "result", "result": "# Final markdown"}
        """
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/jester/stream/{job_id}",
                timeout=aiohttp.ClientTimeout(total=600)
            ) as resp:
                async for line in resp.content:
                    if line.startswith(b"data:"):
                        text = line[5:].decode().strip()
                        if text:
                            import json
                            yield json.loads(text)
        except Exception as e:
            yield {"type": "error", "error": str(e)}

    async def mine_document(
        self,
        content: str,
        topics: List[str] = None,
        inspector: bool = True,
        verify: bool = True
    ) -> str:
        """
        Mine a document for facts using Jester.

        Args:
            content: Document text or file path
            topics: Manual topics (or auto-discover if inspector=True)
            inspector: Auto-discover topics
            verify: Run fact verification

        Returns:
            job_id
        """
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/jester/run",
                json={
                    "mode": "mine_document",
                    "content": content,
                    "config": {
                        "topics": topics or [],
                        "inspector": inspector,
                        "verify": verify,
                        "tier": "smart"
                    }
                },
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status >= 400:
                    return ""
                data = await resp.json()
                return data.get("jobId", "")
        except Exception as e:
            print(f"Jester mine_document error: {e}")
            return ""


# =============================================================================
# CORPORELLA BRIDGE (Company Intelligence)
# =============================================================================

class CorporellaBridge:
    """
    Bridge to Corporella company intelligence.

    Provides:
    - Officers (directors, CEOs)
    - Shareholders
    - Beneficial owners
    - Company status
    - Filing history

    Sources: OpenCorporates, OCCRP Aleph, jurisdiction-specific registries

    Endpoints:
    - POST /api/company-enrichment/enrich
    - POST /api/company-search/execute
    - POST /api/company-registries/search
    - tRPC: corporella.*
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

    async def enrich_company(
        self,
        company_name: str,
        jurisdiction: str = None,
        company_number: str = None,
        node_id: str = None
    ) -> Dict[str, Any]:
        """
        Enrich company with officers, shareholders, etc.

        Calls populator.py subprocess for full enrichment.
        """
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/corporella/enrichment/enrich",
                json={
                    "companyName": company_name,
                    "jurisdiction": jurisdiction,
                    "companyNumber": company_number,
                    "nodeId": node_id
                },
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text()}
                return await resp.json()
        except Exception as e:
            return {"error": str(e)}

    async def search_company(
        self,
        query: str,
        jurisdiction: str = None,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Search for companies and auto-create graph nodes.
        """
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/corporella/search/execute",
                json={
                    "query": query,
                    "jurisdiction": jurisdiction,
                    "limit": limit
                },
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text()}
                return await resp.json()
        except Exception as e:
            return {"error": str(e)}

    async def search_registry(
        self,
        query: str,
        jurisdiction: str,
        include_officers: bool = True
    ) -> Dict[str, Any]:
        """
        Search country-specific registry with officer data.
        """
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/corporella/country/search",
                json={
                    "query": query,
                    "jurisdiction": jurisdiction,
                    "entryTypes": ["company", "officer"] if include_officers else ["company"],
                    "includeOfficers": include_officers
                },
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text()}
                return await resp.json()
        except Exception as e:
            return {"error": str(e)}

    async def get_officers(self, company_name: str, jurisdiction: str = None) -> List[Dict]:
        """Get company officers."""
        result = await self.enrich_company(company_name, jurisdiction)
        return result.get("officers", [])

    async def get_shareholders(self, company_name: str, jurisdiction: str = None) -> List[Dict]:
        """Get company shareholders."""
        result = await self.enrich_company(company_name, jurisdiction)
        return result.get("shareholders", [])


# =============================================================================
# SEARCH BRIDGE (BruteSearch - 40+ Engines)
# =============================================================================

class SearchBridge:
    """
    Bridge to BruteSearch multi-engine search.

    40+ search engines in 8-wave progressive execution:
    - Tier 0: Elastic Corpus, Sastre InURL
    - Tier 1: Google, Bing, Brave, Perplexity, Exa, Archive.org, etc.
    - Tier 2: DuckDuckGo, Yandex, NewsAPI, GDELT, Wikipedia, etc.
    - Tier 3: Semantic Scholar, PubMed, ArXiv, etc.

    Endpoints:
    - tRPC: search.search (streaming)
    - tRPC: drillSearch.advancedSearch
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

    async def broad_search(
        self,
        query: str,
        limit: int = 100,
        include_filetype_discovery: bool = True
    ) -> Dict[str, Any]:
        """
        Run broad search across 40+ engines.

        Args:
            query: Search query
            limit: Max results
            include_filetype_discovery: Include filetype discovery pass

        Returns:
            {
                "results": [...],
                "metadata": {
                    "enginesUsed": [...],
                    "tier1Results": int,
                    "multiHitResults": int,
                    ...
                }
            }
        """
        try:
            session = await self._get_session()
            # Call tRPC mutation
            async with session.post(
                f"{self.base_url}/api/trpc/search.search",
                params={"batch": "1"},
                json={
                    "0": {
                        "json": {
                            "query": query,
                            "limit": limit,
                            "includeFiletypeDiscovery": include_filetype_discovery
                        }
                    }
                },
                timeout=aiohttp.ClientTimeout(total=300)  # 5 min for full search
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text(), "results": []}
                result = await resp.json()
                if isinstance(result, list) and result:
                    return result[0].get("result", {}).get("data", {})
                return {"error": "Invalid response", "results": []}
        except Exception as e:
            return {"error": str(e), "results": []}

    async def advanced_search(
        self,
        query: str,
        collapse_digest: bool = True
    ) -> Dict[str, Any]:
        """
        Advanced search with deduplication.

        Args:
            query: Search query
            collapse_digest: Collapse duplicate results by content digest
        """
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/trpc/drillSearch.advancedSearch",
                params={"batch": "1"},
                json={
                    "0": {
                        "json": {
                            "query": query,
                            "collapseDigest": collapse_digest
                        }
                    }
                },
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text(), "results": []}
                result = await resp.json()
                if isinstance(result, list) and result:
                    return result[0].get("result", {}).get("data", {})
                return {"error": "Invalid response", "results": []}
        except Exception as e:
            return {"error": str(e), "results": []}


# =============================================================================
# DOMAIN INTEL BRIDGE (Backlinks, WHOIS, etc.)
# =============================================================================

class DomainIntelBridge:
    """
    Bridge to domain intelligence endpoints.

    14 routers with 40+ endpoints:
    - allDomainRouter: Firecrawl, CC, Wayback, 15+ sources
    - ccBacklinksRouter: Common Crawl Web Graph
    - majesticRouter: 16 Majestic API commands
    - whoisRouter: WHOIS + reverse WHOIS
    - websiteIntelRouter: Firecrawl + LLM analysis
    - domainSignalRouter: Cloudflare Radar, Tranco, CrUX
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

    async def get_backlinks(
        self,
        domain: str,
        limit: int = 100,
        enriched: bool = True
    ) -> Dict[str, Any]:
        """
        Get backlinks from CC Web Graph + GlobalLinks.

        Args:
            domain: Target domain
            limit: Max results
            enriched: Include authority signals (Tranco, OPR, etc.)
        """
        try:
            session = await self._get_session()
            endpoint = "getEnrichedBacklinks" if enriched else "getInboundBacklinks"
            async with session.post(
                f"{self.base_url}/api/trpc/ccBacklinks.{endpoint}",
                params={"batch": "1"},
                json={"0": {"json": {"domain": domain, "limit": limit}}},
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text(), "backlinks": []}
                result = await resp.json()
                if isinstance(result, list) and result:
                    return result[0].get("result", {}).get("data", {})
                return {"backlinks": []}
        except Exception as e:
            return {"error": str(e), "backlinks": []}

    async def get_outlinks(self, domain: str, limit: int = 100) -> Dict[str, Any]:
        """Get outbound links."""
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/trpc/ccBacklinks.getOutboundLinks",
                params={"batch": "1"},
                json={"0": {"json": {"domain": domain, "limit": limit}}},
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text(), "outlinks": []}
                result = await resp.json()
                if isinstance(result, list) and result:
                    return result[0].get("result", {}).get("data", {})
                return {"outlinks": []}
        except Exception as e:
            return {"error": str(e), "outlinks": []}

    async def whois_lookup(self, domain: str) -> Dict[str, Any]:
        """
        WHOIS lookup with automatic graph persistence.

        Creates domain node + registrant entities + edges.
        """
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/enrichment/whois",
                json={"domain": domain},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text()}
                return await resp.json()
        except Exception as e:
            return {"error": str(e)}

    async def reverse_whois(
        self,
        query: str,
        query_type: str = "email"
    ) -> Dict[str, Any]:
        """
        Reverse WHOIS search.

        Args:
            query: Search value (email, name, phone, etc.)
            query_type: "domain", "email", "name", "phone", "company"
        """
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/trpc/whois.reverseSearch",
                params={"batch": "1"},
                json={"0": {"json": {"query": query, "type": query_type}}},
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text(), "results": []}
                result = await resp.json()
                if isinstance(result, list) and result:
                    return result[0].get("result", {}).get("data", {})
                return {"results": []}
        except Exception as e:
            return {"error": str(e), "results": []}

    async def majestic_backlinks(
        self,
        domain: str,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Get backlinks via Majestic API."""
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/trpc/majestic.getBackLinks",
                params={"batch": "1"},
                json={"0": {"json": {"domain": domain, "limit": limit}}},
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text(), "backlinks": []}
                result = await resp.json()
                if isinstance(result, list) and result:
                    return result[0].get("result", {}).get("data", {})
                return {"backlinks": []}
        except Exception as e:
            return {"error": str(e), "backlinks": []}

    async def discover_subdomains(self, domain: str) -> Dict[str, Any]:
        """
        Discover subdomains via crt.sh, WhoisXML, Sublist3r.
        """
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/trpc/subdomains.discover",
                params={"batch": "1"},
                json={"0": {"json": {"domain": domain}}},
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text(), "subdomains": []}
                result = await resp.json()
                if isinstance(result, list) and result:
                    return result[0].get("result", {}).get("data", {})
                return {"subdomains": []}
        except Exception as e:
            return {"error": str(e), "subdomains": []}

    async def analyze_website(
        self,
        domain: str,
        max_pages: int = 10
    ) -> Dict[str, Any]:
        """
        Full website analysis with Firecrawl + LLM.
        """
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/trpc/websiteIntel.analyzeDomain",
                params={"batch": "1"},
                json={"0": {"json": {"domain": domain, "maxPages": max_pages}}},
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text()}
                result = await resp.json()
                if isinstance(result, list) and result:
                    return result[0].get("result", {}).get("data", {})
                return {}
        except Exception as e:
            return {"error": str(e)}


# =============================================================================
# NARRATIVE BRIDGE (Notes and Documents)
# =============================================================================

class NarrativeBridge:
    """
    Bridge to narrative/notes system.

    Endpoints from narrativesRouter.ts and graphRouter.ts:
    - GET /api/narratives/projects/:projectId/documents
    - POST /api/narratives/projects/:projectId/documents
    - PUT /api/narratives/documents/:documentId
    - POST /api/graph/narrative-notes
    - GET /api/graph/project-notes
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
            print(f"List documents error: {e}")
            return []

    async def create_document(
        self,
        project_id: str,
        title: str
    ) -> Dict[str, Any]:
        """
        Create new document.

        Note: Initial content should be set via update_document() after creation.
        The create endpoint only accepts title.
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
            return {"error": str(e)}

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
            print(f"Get project notes error: {e}")
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
            return {"error": str(e)}

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
            return {"error": str(e)}


# =============================================================================
# EYE-D BRIDGE (Entity Extraction - Direct)
# =============================================================================

class EyedBridge:
    """
    Bridge to EYE-D entity extraction.

    Direct extraction (not via Linklater):
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
            print(f"EYE-D extraction error: {e}")
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
            print(f"Haiku extraction error: {e}")
            return {"persons": [], "companies": [], "emails": [], "phones": [], "edges": []}


# =============================================================================
# EXTENDED LINKLATER BRIDGE (Full 60+ endpoints)
# =============================================================================

class ExtendedLinklaterBridge(LinklaterBridge):
    """
    Extended Linklater bridge with all 60+ endpoints.

    Adds to base LinklaterBridge:
    - Archive operations
    - GA tracker
    - Discovery operations
    - Temporal analysis
    - Link pipeline
    """

    def __init__(self, base_url: str = PYTHON_API_BASE_URL):
        super().__init__()
        self.http_base = base_url
        self._http_session = None

    async def _get_http_session(self):
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    async def close(self):
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()

    async def search_archives(
        self,
        domain: str,
        keyword: str = None,
        year: int = None
    ) -> Dict[str, Any]:
        """Search Wayback + Common Crawl archives."""
        try:
            session = await self._get_http_session()
            async with session.post(
                f"{self.http_base}/api/linklater/historical-search",
                json={
                    "domain": domain,
                    "keyword": keyword,
                    "year": year
                },
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status >= 400:
                    return {"results": []}
                return await resp.json()
        except Exception as e:
            return {"error": str(e), "results": []}

    async def discover_ga_codes(self, domain: str) -> Dict[str, Any]:
        """Discover Google Analytics/GTM codes on domain."""
        try:
            session = await self._get_http_session()
            async with session.post(
                f"{self.http_base}/api/linklater/ga/discover",
                json={"domain": domain},
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status >= 400:
                    return {"codes": []}
                return await resp.json()
        except Exception as e:
            return {"error": str(e), "codes": []}

    async def reverse_ga_lookup(self, ga_code: str) -> Dict[str, Any]:
        """Find all domains using a specific GA/GTM code."""
        try:
            session = await self._get_http_session()
            async with session.post(
                f"{self.http_base}/api/linklater/ga/reverse-lookup",
                json={"code": ga_code},
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status >= 400:
                    return {"domains": []}
                return await resp.json()
        except Exception as e:
            return {"error": str(e), "domains": []}

    async def get_link_timeline(
        self,
        source_domain: str,
        target_domain: str
    ) -> Dict[str, Any]:
        """Get timeline of when source started linking to target."""
        try:
            session = await self._get_http_session()
            async with session.post(
                f"{self.http_base}/api/linklater/links/timeline",
                json={
                    "sourceDomain": source_domain,
                    "targetDomain": target_domain
                },
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status >= 400:
                    return {"timeline": []}
                return await resp.json()
        except Exception as e:
            return {"error": str(e), "timeline": []}

    async def find_shared_link_targets(
        self,
        domains: List[str]
    ) -> Dict[str, Any]:
        """Find domains that multiple sources link to."""
        try:
            session = await self._get_http_session()
            async with session.post(
                f"{self.http_base}/api/linklater/links/shared-targets",
                json={"domains": domains},
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status >= 400:
                    return {"sharedTargets": []}
                return await resp.json()
        except Exception as e:
            return {"error": str(e), "sharedTargets": []}

    async def get_archive_changes(
        self,
        url: str,
        since_date: str = None
    ) -> Dict[str, Any]:
        """Find content change events for a URL."""
        try:
            session = await self._get_http_session()
            async with session.post(
                f"{self.http_base}/api/linklater/archive/changes",
                json={"url": url, "sinceDate": since_date},
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status >= 400:
                    return {"changes": []}
                return await resp.json()
        except Exception as e:
            return {"error": str(e), "changes": []}

    async def gather_intelligence(self, domain: str) -> Dict[str, Any]:
        """Gather pre-flight domain intelligence (backlinks, outlinks, categories)."""
        try:
            session = await self._get_http_session()
            async with session.post(
                f"{self.http_base}/api/linklater/intelligence/gather",
                json={"domain": domain},
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status >= 400:
                    return {}
                return await resp.json()
        except Exception as e:
            return {"error": str(e)}


# =============================================================================
# UPDATED UNIFIED INFRASTRUCTURE
# =============================================================================

@dataclass
class FullInfrastructureStatus:
    """Status of ALL infrastructure components."""
    cymonides_available: bool = False
    linklater_available: bool = False
    watchers_available: bool = False
    io_matrix_available: bool = False
    torpedo_available: bool = False
    jester_available: bool = False
    corporella_available: bool = False
    search_available: bool = False
    domain_intel_available: bool = False
    narrative_available: bool = False
    eyed_available: bool = False
    io_rules_count: int = 0


class FullSastreInfrastructure:
    """
    COMPLETE interface to ALL SASTRE infrastructure.

    This is the REAL autopilot - controls everything:
    - Cymonides/WDC (corpus)
    - Linklater (link intelligence)
    - Watchers (document surveillance)
    - IO Matrix (routing)
    - Torpedo (company profiles)
    - Jester (document assembly)
    - Corporella (company intel)
    - Search (40+ engines)
    - Domain Intel (backlinks, WHOIS)
    - Narrative (notes/documents)
    - EYE-D (entity extraction)
    """

    def __init__(
        self,
        node_url: str = NODE_API_BASE_URL,
        python_url: str = PYTHON_API_BASE_URL
    ):
        # Original bridges
        self.cymonides = CymonidesBridge()
        self.linklater = ExtendedLinklaterBridge(python_url)
        self.watchers = WatcherBridge(node_url)
        self.io = IOBridge()

        # NEW bridges
        self.torpedo = TorpedoBridge(python_url)
        self.jester = JesterBridge(python_url)
        self.corporella = CorporellaBridge(node_url)
        self.search = SearchBridge(node_url)
        self.domain_intel = DomainIntelBridge(node_url)
        self.narrative = NarrativeBridge(node_url)
        self.eyed = EyedBridge(python_url)

    async def close(self):
        """Clean up all resources."""
        await self.watchers.close()
        await self.torpedo.close()
        await self.jester.close()
        await self.corporella.close()
        await self.search.close()
        await self.domain_intel.close()
        await self.narrative.close()
        await self.eyed.close()
        await self.linklater.close()

    # ==========================================================================
    # HIGH-LEVEL INVESTIGATION METHODS
    # ==========================================================================

    async def investigate_person(
        self,
        name: str,
        email: str = None,
        phone: str = None
    ) -> Dict[str, Any]:
        """Full person investigation."""
        results = {
            "name": name,
            "corpus_hits": [],
            "io_results": {},
            "entities_extracted": []
        }

        # Unknown Knowns check
        results["corpus_hits"] = self.cymonides.check_unknown_knowns("person", name)

        # IO execution
        results["io_results"] = await self.io.execute("person", name)

        # Extract entities from results
        if results["io_results"].get("content"):
            results["entities_extracted"] = await self.eyed.extract(
                text=str(results["io_results"])
            )

        return results

    async def investigate_company(
        self,
        name: str,
        jurisdiction: str = None
    ) -> Dict[str, Any]:
        """Full company investigation."""
        results = {
            "name": name,
            "jurisdiction": jurisdiction,
            "corpus_hits": [],
            "profile": {},
            "officers": [],
            "shareholders": [],
            "io_results": {}
        }

        # Unknown Knowns check
        results["corpus_hits"] = self.cymonides.check_unknown_knowns("company", name)

        # Torpedo profile
        if jurisdiction:
            results["profile"] = await self.torpedo.fetch_profile(name, jurisdiction)

        # Corporella enrichment
        enrichment = await self.corporella.enrich_company(name, jurisdiction)
        results["officers"] = enrichment.get("officers", [])
        results["shareholders"] = enrichment.get("shareholders", [])

        # IO execution
        results["io_results"] = await self.io.execute("company", name, jurisdiction)

        return results

    async def investigate_domain(
        self,
        domain: str
    ) -> Dict[str, Any]:
        """Full domain investigation."""
        results = {
            "domain": domain,
            "backlinks": [],
            "outlinks": [],
            "whois": {},
            "subdomains": [],
            "ga_codes": [],
            "intelligence": {}
        }

        # Backlinks
        bl = await self.domain_intel.get_backlinks(domain)
        results["backlinks"] = bl.get("backlinks", [])

        # Outlinks
        ol = await self.domain_intel.get_outlinks(domain)
        results["outlinks"] = ol.get("outlinks", [])

        # WHOIS
        results["whois"] = await self.domain_intel.whois_lookup(domain)

        # Subdomains
        sd = await self.domain_intel.discover_subdomains(domain)
        results["subdomains"] = sd.get("subdomains", [])

        # GA codes
        results["ga_codes"] = await self.linklater.discover_ga_codes(domain)

        # Full intelligence
        results["intelligence"] = await self.linklater.gather_intelligence(domain)

        return results

    async def fill_document_section(
        self,
        document_id: str,
        section_header: str,
        query: str,
        jurisdiction: str = None
    ) -> str:
        """Fill a document section using Jester."""
        # Get document context
        doc = await self.narrative.get_document(document_id)
        context = doc.get("markdown", "")

        # Start Jester job
        job_id = await self.jester.fill_section(
            section_header=section_header,
            query=query,
            context_content=context,
            jurisdiction=jurisdiction
        )

        if not job_id:
            return ""

        # Stream and collect result
        final_content = ""
        async for event in self.jester.stream_result(job_id):
            if event.get("type") == "result":
                final_content = event.get("result", "")

        # Update document
        if final_content:
            new_markdown = context.replace(
                section_header,
                f"{section_header}\n\n{final_content}"
            )
            await self.narrative.update_document(document_id, markdown=new_markdown)

        return final_content

    async def broad_search(
        self,
        query: str,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Run broad search across 40+ engines."""
        return await self.search.broad_search(query, limit)

    # ==========================================================================
    # PLAYBOOK-BASED INVESTIGATION METHODS (Smart Autopilot)
    # ==========================================================================

    def recommend_playbooks(
        self,
        entity_type: str,
        jurisdiction: str = None,
        top_n: int = 5,
        min_success_rate: float = 0.0,
        prefer_friction: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get smart playbook recommendations for an entity type.

        Uses IORouter's recommendation engine with:
        - Regional jurisdiction groups (EU, LATAM, MENA, APAC)
        - Output richness scoring
        - Friction preference matching
        - Success rate filtering

        Args:
            entity_type: "company", "person", "domain", "email", "phone"
            jurisdiction: Optional jurisdiction code (HU, GB, US, etc.)
            top_n: Number of recommendations (default: 5)
            min_success_rate: Minimum success rate filter (0.0-1.0)
            prefer_friction: Optional preferred friction level

        Returns:
            List of recommended playbooks with scores
        """
        return self.io.recommend_playbooks(
            entity_type,
            jurisdiction=jurisdiction,
            top_n=top_n,
            min_success_rate=min_success_rate,
            prefer_friction=prefer_friction
        )

    async def execute_playbook_chain(
        self,
        chain_id: str,
        value: str,
        jurisdiction: str = None,
        playbook_categories: List[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a playbook-based investigation chain.

        Playbook chains are strategic execution paths that:
        - Auto-select jurisdiction-appropriate playbooks
        - Execute multiple playbooks in sequence or parallel
        - Aggregate results from all playbook executions

        Args:
            chain_id: Chain rule ID (e.g., 'CHAIN_PLAYBOOK_FULL_COMPANY_INTEL')
            value: Entity value to investigate
            jurisdiction: Optional jurisdiction code
            playbook_categories: Optional category filter (REGISTRY, LEGAL, etc.)

        Returns:
            Dict with aggregated chain execution results
        """
        return await self.io.execute_playbook_chain(
            chain_id,
            value,
            jurisdiction=jurisdiction,
            playbook_categories=playbook_categories
        )

    async def smart_investigate(
        self,
        entity_type: str,
        value: str,
        jurisdiction: str = None,
        use_best_playbook: bool = True
    ) -> Dict[str, Any]:
        """
        Smart investigation using recommended playbooks.

        This is the AUTOPILOT method - automatically selects the best
        investigation strategy based on entity type and jurisdiction.

        Process:
        1. Get playbook recommendations
        2. Execute best matching playbook
        3. Aggregate results with standard investigation

        Args:
            entity_type: "company", "person", "domain", "email", "phone"
            value: Entity value to investigate
            jurisdiction: Optional jurisdiction code
            use_best_playbook: If True, use recommended playbook instead of default IO

        Returns:
            Dict with investigation results
        """
        results = {
            "entity_type": entity_type,
            "value": value,
            "jurisdiction": jurisdiction,
            "playbook_used": None,
            "corpus_hits": [],
            "investigation_results": {}
        }

        # Unknown Knowns check first
        results["corpus_hits"] = self.cymonides.check_unknown_knowns(entity_type, value)

        if use_best_playbook:
            # Get best playbook recommendation
            playbook = self.io.get_best_playbook_for_entity(entity_type, jurisdiction)

            if playbook:
                results["playbook_used"] = {
                    "id": playbook.get("id"),
                    "label": playbook.get("label"),
                    "score": playbook.get("score"),
                    "success_rate": playbook.get("success_rate")
                }

                # Execute playbook through chain system
                chain_result = await self.io.execute_playbook_chain(
                    f"CHAIN_PLAYBOOK_{entity_type.upper()}_INTEL",
                    value,
                    jurisdiction=jurisdiction
                )
                results["investigation_results"] = chain_result
            else:
                # Fallback to standard IO execution
                results["investigation_results"] = await self.io.execute(
                    entity_type, value, jurisdiction
                )
        else:
            # Standard IO execution
            results["investigation_results"] = await self.io.execute(
                entity_type, value, jurisdiction
            )

        return results

    async def full_company_intel(
        self,
        company_name: str,
        jurisdiction: str = None,
        include_officers: bool = True,
        include_compliance: bool = True,
        include_media: bool = True
    ) -> Dict[str, Any]:
        """
        Full company intelligence using playbook chains.

        Executes multiple playbook chains:
        1. REGISTRY playbook - Corporate registry data
        2. LEGAL playbook - Legal/court records
        3. COMPLIANCE playbook - Sanctions/PEP screening
        4. MEDIA playbook - News/adverse media

        Args:
            company_name: Company name to investigate
            jurisdiction: Optional jurisdiction code
            include_officers: Include officer-level screening
            include_compliance: Include compliance checks
            include_media: Include media monitoring

        Returns:
            Comprehensive company intelligence dict
        """
        results = {
            "company_name": company_name,
            "jurisdiction": jurisdiction,
            "registry": {},
            "officers": [],
            "compliance": {},
            "media": [],
            "playbooks_executed": []
        }

        # Get recommendations for strategic path
        recommendations = self.recommend_playbooks(
            "company",
            jurisdiction=jurisdiction,
            top_n=5,
            min_success_rate=0.75
        )
        results["recommendations"] = [
            {"id": r["id"], "score": r["score"]} for r in recommendations
        ]

        # Execute full company intel chain
        chain_result = await self.execute_playbook_chain(
            "CHAIN_PLAYBOOK_FULL_COMPANY_INTEL",
            company_name,
            jurisdiction=jurisdiction
        )

        if chain_result.get("status") == "success":
            results["registry"] = chain_result.get("aggregated_data", {})
            results["playbooks_executed"] = chain_result.get("results", [])

        # Additional compliance if requested
        if include_compliance:
            compliance_chain = await self.execute_playbook_chain(
                "CHAIN_PLAYBOOK_COMPLIANCE_DEEP_DIVE",
                company_name,
                jurisdiction=jurisdiction
            )
            if compliance_chain.get("status") == "success":
                results["compliance"] = compliance_chain.get("compliance_findings", {})

        # Additional media if requested
        if include_media:
            media_chain = await self.execute_playbook_chain(
                "CHAIN_PLAYBOOK_MEDIA_INTELLIGENCE",
                company_name,
                jurisdiction=jurisdiction
            )
            if media_chain.get("status") == "success":
                results["media"] = media_chain.get("media_items", [])

        return results


# Convenience function - UPDATED
def get_infrastructure() -> SastreInfrastructure:
    """Get basic infrastructure instance (legacy)."""
    return SastreInfrastructure()


def get_full_infrastructure() -> FullSastreInfrastructure:
    """Get FULL infrastructure instance with ALL bridges."""
    return FullSastreInfrastructure()
