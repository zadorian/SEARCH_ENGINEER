"""
SASTRE Cymonides State Adapter - Calls ACTUAL drill-search-app backend.

This is the CORRECT architecture: Uses YOUR existing backend endpoints.
NOT phantom APIs - the REAL endpoints from graphRouter.ts and tRPC.

Backend endpoints (VERIFIED from server/routers/graphRouter.ts):
- GET  /api/graph/rotate           - Grid rotation (params: primaryClassName, primaryTypeName, limit)
- GET  /api/graph/nodes/batch      - Get nodes by IDs (params: ids - comma separated)
- POST /api/graph/persist-entities - Persist entities (body: sourceNodeId, entities, projectId)
- POST /api/graph/nodes/merge      - Merge nodes (body: keepNodeId, mergeNodeId, newLabel?)
- GET  /api/graph/search/nodes     - Search nodes (params: term, size, classNames?, typeNames?)
- GET  /api/projects               - List projects
- POST /api/projects               - Create project (body: name, description?)

tRPC endpoints (VERIFIED from server/routers.ts):
- watchers.create     - Create watcher (input: name, projectId, query?, parentDocumentId?)
- watchers.listActive - Get active watchers (input: projectId) -- NOTE: NOT getActive!
- ioRouter.executeRoute - Execute IO route (input: routeId, input, type, context?)
"""

import os
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import aiohttp
import json

from ..document_interface import DocumentInterface
from ..contracts import (
    Document,
    Section,
    SectionState,
    Entity,
    EntityAttributes,
    BinaryStar,
)
from ..sufficiency import check_sufficiency as constraint_check

logger = logging.getLogger("sastre.cymonides")

# ACTUAL backend URL - the Node.js server
BACKEND_URL = os.getenv("DRILL_SEARCH_BACKEND", "http://localhost:3001")


class InvestigationPhase(Enum):
    """Investigation lifecycle phases."""
    INITIALIZING = "initializing"
    ASSESSING = "assessing"
    INVESTIGATING = "investigating"
    DISAMBIGUATING = "disambiguating"
    WRITING = "writing"
    CHECKING = "checking"
    FINALIZING = "finalizing"
    COMPLETE = "complete"
    FAILED = "failed"
    PAUSED = "paused"


@dataclass
class GridAssessmentResult:
    """Result from /api/graph/rotate endpoint."""
    rows: List[Dict]
    stats: Dict[str, Any]
    mode: str

    @property
    def unanswered_narratives(self) -> List[Dict]:
        """Get unanswered narrative items."""
        return [r for r in self.rows if r.get("state") == "unanswered"]

    @property
    def incomplete_entities(self) -> List[Dict]:
        """Get entities with incomplete core fields."""
        return [r for r in self.rows if not r.get("coreComplete", True)]

    @property
    def unchecked_sources(self) -> List[Dict]:
        """Get unchecked sources."""
        return [r for r in self.rows if r.get("state") == "unchecked"]

    @property
    def pending_collisions(self) -> List[Dict]:
        """Get entities with potential collisions (same name, need disambiguation)."""
        # Entities flagged with collision_suspects or matching labels
        collisions = []
        seen_labels = {}
        for r in self.rows:
            label = r.get("label", "").lower().strip()
            if label:
                if label in seen_labels:
                    # Both the original and duplicate are potential collisions
                    if seen_labels[label] not in collisions:
                        collisions.append(seen_labels[label])
                    collisions.append(r)
                else:
                    seen_labels[label] = r
        # Also include explicitly flagged collision suspects
        for r in self.rows:
            if r.get("collision_suspect") or r.get("needsDisambiguation"):
                if r not in collisions:
                    collisions.append(r)
        return collisions

    @property
    def unconfirmed_connections(self) -> List[Dict]:
        """Get connections/edges that haven't been verified."""
        unconfirmed = []
        for r in self.rows:
            edges = r.get("embedded_edges", [])
            for edge in edges:
                if not edge.get("confirmed", False) and edge.get("state") != "verified":
                    unconfirmed.append({
                        "source_id": r.get("id"),
                        "source_label": r.get("label"),
                        "edge": edge
                    })
        return unconfirmed


class CymonidesState:
    """
    Adapter over drill-search-app backend.

    Calls the ACTUAL endpoints from graphRouter.ts and tRPC.
    """

    def __init__(self, project_id: str, investigation_id: str = None):
        self.project_id = project_id
        self.investigation_id = investigation_id
        self._session: Optional[aiohttp.ClientSession] = None
        self._phase = InvestigationPhase.INITIALIZING
        self._iteration = 0

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=120),
                headers={"Content-Type": "application/json"}
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ─────────────────────────────────────────────────────────────
    # PROJECT MANAGEMENT (from /api/projects)
    # ─────────────────────────────────────────────────────────────

    async def ensure_project(self) -> str:
        """Ensure project exists, create if needed."""
        session = await self._get_session()

        # Check if project exists
        async with session.get(f"{BACKEND_URL}/api/projects") as resp:
            if resp.status == 200:
                projects = await resp.json()
                for p in projects.get("projects", []):
                    if p.get("id") == self.project_id:
                        return self.project_id

        # Create project if doesn't exist
        async with session.post(f"{BACKEND_URL}/api/projects", json={
            "name": self.project_id,
            "description": f"SASTRE Investigation - {self.project_id}"
        }) as resp:
            if resp.status >= 400:
                logger.warning(f"Could not create project: {await resp.text()}")
            else:
                result = await resp.json()
                return result.get("id", self.project_id)

        return self.project_id

    # ─────────────────────────────────────────────────────────────
    # INVESTIGATION NODE
    # ─────────────────────────────────────────────────────────────

    async def create_investigation(self, tasking: str) -> str:
        """
        Create investigation node via /api/graph/persist-entities.

        VERIFIED: Endpoint requires sourceNodeId and entities grouped by type.
        """
        session = await self._get_session()

        await self.ensure_project()

        investigation_data = {
            "className": "narrative",
            "typeName": "investigation",
            "label": tasking[:100],
            "metadata": {
                "tasking": tasking,
                "phase": InvestigationPhase.INITIALIZING.value,
                "iteration": 0,
                "created": datetime.utcnow().isoformat(),
            }
        }

        # VERIFIED format: sourceNodeId + entities grouped by type
        async with session.post(
            f"{BACKEND_URL}/api/graph/persist-entities",
            json={
                "sourceNodeId": "sastre_init",  # Initial source for investigation node
                "entities": {
                    "investigation": [investigation_data]  # Grouped by typeName
                },
                "projectId": self.project_id
            }
        ) as resp:
            if resp.status >= 400:
                raise Exception(f"Failed to create investigation: {await resp.text()}")
            result = await resp.json()
            # Response may have entities nested by type
            persisted = result.get("entities", result.get("persisted", {}))
            if isinstance(persisted, dict):
                inv_list = persisted.get("investigation", [])
                if inv_list:
                    self.investigation_id = inv_list[0].get("id")
            elif isinstance(persisted, list) and persisted:
                self.investigation_id = persisted[0].get("id")
            return self.investigation_id

    async def get_investigation(self) -> Dict[str, Any]:
        """Get investigation node."""
        if not self.investigation_id:
            return {}

        session = await self._get_session()
        # VERIFIED: /api/graph/nodes/batch only takes 'ids' param, NOT projectId
        async with session.get(
            f"{BACKEND_URL}/api/graph/nodes/batch",
            params={"ids": self.investigation_id}
        ) as resp:
            if resp.status >= 400:
                return {}
            result = await resp.json()
            nodes = result.get("nodes", [])
            return nodes[0] if nodes else {}

    async def update_phase(self, phase: InvestigationPhase, iteration: int = None):
        """Update investigation phase."""
        self._phase = phase
        if iteration is not None:
            self._iteration = iteration
        # Phase is tracked locally since we don't have a direct update endpoint

    @property
    def phase(self) -> InvestigationPhase:
        return self._phase

    @property
    def iteration(self) -> int:
        return self._iteration

    # ─────────────────────────────────────────────────────────────
    # GRID ROTATION (from /api/graph/rotate)
    # ─────────────────────────────────────────────────────────────

    async def get_grid_assessment(self, mode: str = "subject") -> GridAssessmentResult:
        """
        Get grid rotation from /api/graph/rotate.

        This is THE source of truth for investigation state.

        Modes: narrative, subject, location, nexus
        Maps to: primaryClassName parameter (NOT 'mode')
        """
        session = await self._get_session()

        # Map mode to primaryClassName (the actual parameter name)
        # VERIFIED: endpoint uses primaryClassName, NOT mode
        mode_to_class = {
            "narrative": "narrative",
            "subject": "subject",
            "location": "location",
            "nexus": "nexus",
        }
        primary_class = mode_to_class.get(mode)

        params = {"projectId": self.project_id, "limit": 100}
        if primary_class:
            params["primaryClassName"] = primary_class

        async with session.get(
            f"{BACKEND_URL}/api/graph/rotate",
            params=params
        ) as resp:
            if resp.status >= 400:
                logger.error(f"Grid rotation failed: {await resp.text()}")
                return GridAssessmentResult(rows=[], stats={}, mode=mode)

            result = await resp.json()
            return GridAssessmentResult(
                rows=result.get("rows", []),
                stats=result.get("stats", {}),
                mode=mode
            )

    async def get_subject_nodes(
        self,
        type_name: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """
        Fetch SUBJECT nodes (Abacus class) via /api/graph/rotate.

        NOTE: We use rotate because it returns full nodes (metadata + embedded edges).
        """
        session = await self._get_session()
        params: Dict[str, Any] = {
            "projectId": self.project_id,
            "primaryClassName": "subject",
            "limit": min(limit, 2000),
        }
        if type_name and str(type_name).strip():
            params["primaryTypeName"] = str(type_name).strip()

        async with session.get(
            f"{BACKEND_URL}/api/graph/rotate",
            params=params
        ) as resp:
            if resp.status >= 400:
                return []
            result = await resp.json()
            rows = result.get("rows", []) or []
            nodes: List[Dict[str, Any]] = []
            for row in rows:
                node = row.get("primaryNode") if isinstance(row, dict) else None
                if not node and isinstance(row, dict):
                    node = row
                if isinstance(node, dict):
                    nodes.append(node)
            return nodes

    async def get_all_grid_modes(self) -> Dict[str, GridAssessmentResult]:
        """Get all four grid rotation modes."""
        results = {}
        for mode in ["narrative", "subject", "location", "nexus"]:
            results[mode] = await self.get_grid_assessment(mode)
        return results

    async def get_narrative_notes(self, limit: int = 200) -> List[Dict[str, Any]]:
        """
        Get narrative note nodes for this project.

        Notes are:
          class=narrative, type=note

        We fetch via /api/graph/rotate and filter client-side because:
          - rotate returns full nodes (metadata/content)
          - it's a single, fast call and avoids extra endpoints
        """
        session = await self._get_session()
        params = {
            "projectId": self.project_id,
            "primaryClassName": "narrative",
            "primaryTypeName": "note",
            "limit": limit,
        }
        async with session.get(
            f"{BACKEND_URL}/api/graph/rotate",
            params=params
        ) as resp:
            if resp.status >= 400:
                return []
            result = await resp.json()
            rows = result.get("rows", []) or []
            notes = []
            for row in rows:
                # rotate returns GridRow objects: { primaryNode, relatedNodes, ... }
                node = row.get("primaryNode") if isinstance(row, dict) else None
                if not node and isinstance(row, dict):
                    node = row
                if isinstance(node, dict):
                    notes.append(node)
            return notes

    # ─────────────────────────────────────────────────────────────
    # ENTITY OPERATIONS (from /api/graph/*)
    # ─────────────────────────────────────────────────────────────

    async def get_entities(self, entity_type: str = None, limit: int = 100) -> List[Dict]:
        """Get entities via grid rotation (subject mode)."""
        result = await self.get_grid_assessment("subject")
        rows = result.rows

        if entity_type:
            rows = [r for r in rows if r.get("type") == entity_type]

        return rows[:limit]

    async def get_entity(self, entity_id: str) -> Dict[str, Any]:
        """Get single entity via /api/graph/nodes/batch."""
        session = await self._get_session()

        # VERIFIED: /api/graph/nodes/batch only takes 'ids' param, NOT projectId
        async with session.get(
            f"{BACKEND_URL}/api/graph/nodes/batch",
            params={"ids": entity_id}
        ) as resp:
            if resp.status >= 400:
                return {}
            result = await resp.json()
            nodes = result.get("nodes", [])
            return nodes[0] if nodes else {}

    async def get_nodes_by_ids(self, node_ids: List[str]) -> List[Dict[str, Any]]:
        """Get multiple nodes via /api/graph/nodes/batch."""
        if not node_ids:
            return []
        session = await self._get_session()
        ids_param = ",".join([nid for nid in node_ids if nid])
        if not ids_param:
            return []
        async with session.get(
            f"{BACKEND_URL}/api/graph/nodes/batch",
            params={"ids": ids_param}
        ) as resp:
            if resp.status >= 400:
                return []
            result = await resp.json()
            return result.get("nodes", []) or []

    async def persist_entities(
        self,
        entities: List[Any],
        source_node_id: str = None,
        source_url: str = None
    ) -> List[str]:
        """
        Persist entities via /api/graph/persist-entities.

        VERIFIED: Endpoint requires sourceNodeId and entities as object keyed by type.
        """
        session = await self._get_session()

        # If no source node, create a temporary one or use investigation
        if not source_node_id:
            source_node_id = self.investigation_id or "sastre_auto"

        # Group entities by type for the expected format
        # The endpoint expects: { entities: { person: [...], company: [...] } }
        entities_by_type: Dict[str, List[str]] = {}
        for ent in entities:
            if isinstance(ent, str):
                ent_type = "unknown"
                label = ent.strip()
            elif isinstance(ent, dict):
                ent_type = ent.get("typeName", ent.get("type", "unknown"))
                label = (
                    ent.get("label")
                    or ent.get("name")
                    or ent.get("value")
                    or ent.get("text")
                )
                label = label.strip() if isinstance(label, str) else ""
            else:
                continue

            if not label:
                continue
            if ent_type not in entities_by_type:
                entities_by_type[ent_type] = []
            entities_by_type[ent_type].append(label)

        payload = {
            "sourceNodeId": source_node_id,
            "entities": entities_by_type,
            "projectId": self.project_id
        }
        if source_url:
            payload["sourceUrl"] = source_url

        async with session.post(
            f"{BACKEND_URL}/api/graph/persist-entities",
            json=payload
        ) as resp:
            if resp.status >= 400:
                raise Exception(f"Failed to persist entities: {await resp.text()}")
            result = await resp.json()
            # Response may have entities nested by type
            all_ids = []
            persisted = result.get("entities", result.get("persisted", {}))
            if isinstance(persisted, dict):
                for type_entities in persisted.values():
                    if isinstance(type_entities, list):
                        all_ids.extend([e.get("id") for e in type_entities if e.get("id")])
            elif isinstance(persisted, list):
                all_ids = [e.get("id") for e in persisted if e.get("id")]
            return all_ids

    async def create_node(
        self,
        class_name: str,
        type_name: str,
        label: str,
        metadata: Optional[Dict[str, Any]] = None,
        value: Optional[str] = None
    ) -> Optional[str]:
        """Create a manual node via /api/graph/nodes."""
        session = await self._get_session()

        # Abacus canonical class names: subject/location/nexus/narrative.
        # Backwards compatibility: allow old callers using entity/source/query.
        normalized_class = (class_name or "").strip().lower()
        if normalized_class == "entity":
            normalized_class = "subject"
        elif normalized_class == "source":
            normalized_class = "location"
        elif normalized_class == "query":
            normalized_class = "nexus"
        elif normalized_class == "narrative":
            normalized_class = "narrative"
        class_name = normalized_class

        payload = {
            "className": class_name,
            "typeName": type_name,
            "label": label,
            "projectId": self.project_id,
            "metadata": metadata or {},
        }
        if value:
            payload["value"] = value

        async with session.post(
            f"{BACKEND_URL}/api/graph/nodes",
            json=payload
        ) as resp:
            if resp.status >= 400:
                logger.warning(f"Failed to create node: {await resp.text()}")
                return None
            result = await resp.json()
            return result.get("id")

    async def update_node_metadata(self, node_id: str, updates: Dict[str, Any]) -> bool:
        """
        Patch node metadata via /api/graph/nodes/:nodeId/metadata.

        This updates ONLY metadata fields (does not overwrite the whole node).
        """
        if not node_id or not isinstance(updates, dict) or not updates:
            return False
        session = await self._get_session()
        async with session.patch(
            f"{BACKEND_URL}/api/graph/nodes/{node_id}/metadata",
            json=updates,
        ) as resp:
            if resp.status >= 400:
                logger.warning(f"Failed to update node metadata {node_id}: {await resp.text()}")
                return False
            return True

    async def create_edge(
        self,
        from_node_id: str,
        to_node_id: str,
        relation: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Create an edge via /api/graph/edges."""
        session = await self._get_session()
        payload = {
            "fromNodeId": from_node_id,
            "toNodeId": to_node_id,
            "relation": relation,
            "projectId": self.project_id,
            "metadata": metadata or {},
        }

        async with session.post(
            f"{BACKEND_URL}/api/graph/edges",
            json=payload
        ) as resp:
            if resp.status >= 400:
                logger.warning(f"Failed to create edge: {await resp.text()}")
                return None
            result = await resp.json()
            return result.get("edgeId")

    async def create_goal(
        self,
        title: str,
        description: str = "",
        source_note_id: Optional[str] = None,
    ) -> Optional[str]:
        """Create a narrative goal node."""
        metadata = {
            "description": description,
            "investigation_id": self.investigation_id,
            "created": datetime.utcnow().isoformat(),
        }
        if source_note_id:
            metadata["source_note_id"] = source_note_id
        return await self.create_node("narrative", "goal", title, metadata=metadata)

    async def create_track(
        self,
        goal_id: str,
        title: str,
        description: str = "",
        source_note_id: Optional[str] = None,
        track_key: Optional[str] = None,
        topology_index: Optional[int] = None,
    ) -> Optional[str]:
        """Create a narrative track node and link to goal."""
        metadata = {
            "description": description,
            "goal_id": goal_id,
            "investigation_id": self.investigation_id,
            "created": datetime.utcnow().isoformat(),
        }
        if source_note_id:
            metadata["source_note_id"] = source_note_id
        if track_key:
            metadata["track_key"] = track_key
        if topology_index is not None:
            metadata["topology_index"] = int(topology_index)
        track_id = await self.create_node("narrative", "track", title, metadata=metadata)
        if track_id and goal_id:
            await self.create_edge(goal_id, track_id, "has_track")
        return track_id

    async def create_path(
        self,
        track_id: str,
        title: str,
        description: str = ""
    ) -> Optional[str]:
        """Create a narrative path node and link to track."""
        metadata = {
            "description": description,
            "track_id": track_id,
            "investigation_id": self.investigation_id,
            "created": datetime.utcnow().isoformat(),
        }
        path_id = await self.create_node("narrative", "path", title, metadata=metadata)
        if path_id and track_id:
            await self.create_edge(track_id, path_id, "has_path")
        return path_id

    async def link_goal_to_document(self, goal_id: str, document_id: str) -> Optional[str]:
        """Link a goal to its narrative document."""
        if not goal_id or not document_id:
            return None
        return await self.create_edge(goal_id, document_id, "has_narrative")

    async def link_path_to_query(self, path_id: str, query_id: str) -> Optional[str]:
        """Link a path to a query node."""
        if not path_id or not query_id:
            return None
        return await self.create_edge(path_id, query_id, "has_query")

    async def link_path_to_source(self, path_id: str, source_id: str) -> Optional[str]:
        """Link a path to a source node."""
        if not path_id or not source_id:
            return None
        return await self.create_edge(path_id, source_id, "has_source")

    async def link_path_to_entity(self, path_id: str, entity_id: str) -> Optional[str]:
        """Link a path to an entity node."""
        if not path_id or not entity_id:
            return None
        return await self.create_edge(path_id, entity_id, "has_entity")

    async def search_nodes(
        self,
        query: str,
        limit: int = 50,
        class_names: List[str] = None,
        type_names: List[str] = None
    ) -> List[Dict]:
        """
        Search nodes via /api/graph/search/nodes.

        VERIFIED: Uses 'term' (NOT 'q') and 'size' (NOT 'limit').
        """
        session = await self._get_session()

        # VERIFIED: param names are term, size, classNames, typeNames
        params = {
            "term": query,
            "projectId": self.project_id,
            "size": min(limit, 50)  # capped at 50 by backend
        }
        if class_names:
            params["classNames"] = ",".join(class_names)
        if type_names:
            params["typeNames"] = ",".join(type_names)

        async with session.get(
            f"{BACKEND_URL}/api/graph/search/nodes",
            params=params
        ) as resp:
            if resp.status >= 400:
                return []
            result = await resp.json()
            return result.get("nodes", [])

    # ─────────────────────────────────────────────────────────────
    # IO ROUTER (via tRPC: ioRouter.executeRoute)
    # ─────────────────────────────────────────────────────────────

    async def execute_io_route(
        self,
        route_id: str,
        input_value: str,
        route_type: str = "flow",
        motor_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute IO route via tRPC ioRouter.executeRoute.

        This calls the Matrix routing system to execute enrichment.
        """
        session = await self._get_session()

        # tRPC mutation call
        payload = {
            "0": {
                "json": {
                    "routeId": route_id,
                    "input": input_value,
                    "type": route_type,
                    "context": {
                        "projectId": self.project_id,
                        "investigationId": self.investigation_id,
                        "motorContext": motor_context
                    }
                }
            }
        }

        async with session.post(
            f"{BACKEND_URL}/api/trpc/ioRouter.executeRoute",
            params={"batch": "1"},
            json=payload
        ) as resp:
            if resp.status >= 400:
                return {"error": await resp.text()}
            result = await resp.json()
            # tRPC returns array of results
            if isinstance(result, list) and result:
                return result[0].get("result", {}).get("data", {})
            return result

    async def execute_query(self, query: str, motor_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute query - determines route from query prefix."""
        # Parse prefix to determine route
        if query.startswith("p:"):
            return await self.execute_io_route("person_osint", query[2:].strip(), motor_context=motor_context)
        elif query.startswith("c:"):
            return await self.execute_io_route("company_profile", query[2:].strip(), motor_context=motor_context)
        elif query.startswith("e:"):
            return await self.execute_io_route("email_osint", query[2:].strip(), motor_context=motor_context)
        elif query.startswith("d:"):
            return await self.execute_io_route("domain_intel", query[2:].strip(), motor_context=motor_context)
        else:
            # Default to person search
            return await self.execute_io_route("person_osint", query, motor_context=motor_context)

    # ─────────────────────────────────────────────────────────────
    # ENRICHMENT BUTTONS (tRPC: enrichment.getEnrichmentButtons)
    # ─────────────────────────────────────────────────────────────

    async def get_enrichment_buttons(
        self,
        entity_type: str,
        entity_value: str,
        jurisdiction: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        node_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetch dynamic enrichment buttons from the same config used by the UI."""
        session = await self._get_session()

        payload = {
            "0": {
                "json": {
                    "entityType": entity_type,
                    "entityValue": entity_value,
                    "jurisdiction": jurisdiction,
                    "metadata": metadata or {},
                    "nodeId": node_id,
                    "projectId": self.project_id,
                }
            }
        }

        async with session.get(
            f"{BACKEND_URL}/api/trpc/enrichment.getEnrichmentButtons",
            params={"batch": "1", "input": json.dumps(payload)}
        ) as resp:
            if resp.status >= 400:
                logger.warning(f"Failed to load enrichment buttons: {await resp.text()}")
                return []
            result = await resp.json()
            if isinstance(result, list) and result:
                data = result[0].get("result", {}).get("data", {})
                if isinstance(data, dict) and "json" in data:
                    return data.get("json", []) or []
                if isinstance(data, list):
                    return data
            return []

    async def execute_enrichment_button(self, button: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single enrichment button payload (mirrors UI behavior)."""
        endpoint = button.get("endpoint") or ""
        method = button.get("method", "GET")
        params = button.get("params", {}) or {}
        action = button.get("action", "api")

        if action == "link" or not endpoint:
            return {"skipped": True, "reason": "link_action"}

        session = await self._get_session()
        url = endpoint if endpoint.startswith("http") else f"{BACKEND_URL}{endpoint}"

        request_kwargs: Dict[str, Any] = {}
        if method == "POST":
            request_kwargs["json"] = params

        async with session.request(method, url, **request_kwargs) as resp:
            if resp.status >= 400:
                return {"error": await resp.text()}
            try:
                return await resp.json()
            except Exception:
                return {"status": "ok"}

    # ─────────────────────────────────────────────────────────────
    # WATCHERS (via tRPC: watchers.*)
    # ─────────────────────────────────────────────────────────────

    async def create_watcher(
        self,
        name: Optional[str] = None,
        parent_document_id: Optional[str] = None,
        label: Optional[str] = None,
        header_level: Optional[int] = None,
        header_index: Optional[int] = None
    ) -> str:
        """Create watcher via tRPC watchers.create (label/name compatible)."""
        session = await self._get_session()

        watcher_name = name or label or "Watcher"

        payload = {
            "0": {
                "json": {
                    "name": watcher_name,
                    "projectId": self.project_id,
                    "parentDocumentId": parent_document_id
                }
            }
        }

        async with session.post(
            f"{BACKEND_URL}/api/trpc/watchers.create",
            params={"batch": "1"},
            json=payload
        ) as resp:
            if resp.status < 400:
                result = await resp.json()
                if isinstance(result, list) and result:
                    data = result[0].get("result", {}).get("data", {})
                    return data.get("id", "")
                return ""

            error_text = await resp.text()
            logger.warning(f"Watcher create via tRPC failed: {error_text}")

        # Fallback: graph watcher creation (no auth)
        if parent_document_id:
            async with session.post(
                f"{BACKEND_URL}/api/graph/watchers/create-from-header",
                json={
                    "noteId": parent_document_id,
                    "headerText": watcher_name,
                    "projectId": self.project_id
                }
            ) as resp:
                if resp.status < 400:
                    result = await resp.json()
                    return result.get("watcherId", "") or result.get("id", "")
                logger.warning(f"Watcher create-from-header failed: {await resp.text()}")

        async with session.post(
            f"{BACKEND_URL}/api/graph/watchers/add-to-note",
            json={
                "headerText": watcher_name,
                "projectId": self.project_id
            }
        ) as resp:
            if resp.status < 400:
                result = await resp.json()
                return result.get("watcherId", "") or result.get("id", "")
            logger.warning(f"Watcher add-to-note failed: {await resp.text()}")

        return ""

    async def get_active_watchers(self) -> List[Dict]:
        """
        Get active watchers via tRPC watchers.listActive.

        VERIFIED: Procedure is 'listActive' (NOT 'getActive').
        """
        session = await self._get_session()

        async with session.get(
            f"{BACKEND_URL}/api/trpc/watchers.listActive",
            params={"batch": "1", "input": json.dumps({"0": {"json": {"projectId": self.project_id}}})}
        ) as resp:
            if resp.status >= 400:
                return []
            result = await resp.json()
            if isinstance(result, list) and result:
                # Response is array of watcher nodes
                return result[0].get("result", {}).get("data", [])
            return []

    # Alias for compatibility
    async def get_watchers(self) -> List[Dict]:
        return await self.get_active_watchers()

    # ─────────────────────────────────────────────────────────────
    # NARRATIVE DOCUMENTS
    # ─────────────────────────────────────────────────────────────

    async def create_narrative_document(self, title: str, markdown: str = "") -> str:
        """Create narrative document in the EDITh pipeline (graph + filesystem)."""
        session = await self._get_session()

        payload = {
            "label": title,
            "content": markdown,
            "projectId": self.project_id,
        }

        try:
            async with session.post(
                f"{BACKEND_URL}/api/graph/notes",
                json=payload
            ) as resp:
                if resp.status < 400:
                    result = await resp.json()
                    note_id = (
                        result.get("noteId")
                        or result.get("id")
                        or result.get("document", {}).get("id")
                    )
                    if note_id:
                        # Best-effort: attach investigation metadata for linking.
                        try:
                            await session.patch(
                                f"{BACKEND_URL}/api/graph/nodes/{note_id}/metadata",
                                json={
                                    "investigation_id": self.investigation_id,
                                    "created": datetime.utcnow().isoformat(),
                                }
                            )
                        except Exception:
                            pass
                        return note_id
                logger.warning(f"Create narrative via /api/graph/notes failed: {await resp.text()}")
        except Exception as exc:
            logger.warning(f"Create narrative via /api/graph/notes failed: {exc}")

        # Fallback: graph-only node (legacy path)
        metadata = {
            "markdown": markdown,
            "title": title,
            "investigation_id": self.investigation_id,
            "created": datetime.utcnow().isoformat(),
        }
        node_id = await self.create_node(
            class_name="narrative",
            type_name="note",
            label=title,
            metadata=metadata,
        )
        return node_id or ""

    async def get_narrative_document(self, document_id: str) -> Dict[str, Any]:
        """Get narrative document."""
        return await self.get_entity(document_id)

    # ─────────────────────────────────────────────────────────────
    # NODE MERGE (Disambiguation)
    # ─────────────────────────────────────────────────────────────

    async def merge_entities(
        self,
        keep_node_id: str,
        merge_node_id: str,
        new_label: str = None
    ) -> Dict:
        """
        Merge two entities via /api/graph/nodes/merge.

        VERIFIED: Uses keepNodeId/mergeNodeId (NOT sourceId/targetId).
        The keepNodeId's attributes are preserved, mergeNodeId is absorbed.
        """
        session = await self._get_session()

        payload = {
            "keepNodeId": keep_node_id,
            "mergeNodeId": merge_node_id,
            "overrideProjectId": self.project_id
        }
        if new_label:
            payload["newLabel"] = new_label

        async with session.post(
            f"{BACKEND_URL}/api/graph/nodes/merge",
            json=payload
        ) as resp:
            if resp.status >= 400:
                return {"error": await resp.text()}
            return await resp.json()

    # ─────────────────────────────────────────────────────────────
    # CORPUS SEARCH (Unknown Knowns)
    # ─────────────────────────────────────────────────────────────

    async def search_corpus(self, query: str, limit: int = 50) -> Dict[str, Any]:
        """Search existing corpus via /api/graph/search/nodes."""
        nodes = await self.search_nodes(query, limit)
        return {
            "results": nodes,
            "total": len(nodes)
        }

    async def get_recent_queries(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Fetch recent query nodes for duplicate prevention."""
        session = await self._get_session()

        async with session.get(
            f"{BACKEND_URL}/api/graph/queries/recent",
            params={"projectId": self.project_id, "limit": min(limit, 2000)}
        ) as resp:
            if resp.status >= 400:
                logger.warning(f"Failed to fetch recent queries: {await resp.text()}")
                return []
            result = await resp.json()
            return result.get("queries", [])

    # ─────────────────────────────────────────────────────────────
    # CONNECTIONS / EDGES
    # ─────────────────────────────────────────────────────────────

    async def get_connections(self, entity_id: str) -> List[Dict]:
        """Get entity connections from embedded_edges."""
        entity = await self.get_entity(entity_id)
        return entity.get("embedded_edges", [])

    # ─────────────────────────────────────────────────────────────
    # FINDINGS (from /api/graph/watchers/test-add-finding)
    # ─────────────────────────────────────────────────────────────

    async def add_finding_to_watcher(
        self,
        watcher_id: str,
        content: str,
        source_url: str = "",
        source_id: str = ""
    ) -> bool:
        """
        Add a finding/quote to a watcher via /api/graph/watchers/add-finding.
        """
        session = await self._get_session()

        payload = {
            "watcherId": watcher_id,
            "quote": content,
            "sourceUrl": source_url or "https://sastre.investigation/auto",
            "sourceId": source_id or f"sastre_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "explanation": "SASTRE autopilot finding"
        }

        async with session.post(
            f"{BACKEND_URL}/api/graph/watchers/add-finding",
            json=payload
        ) as resp:
            if resp.status >= 400:
                logger.warning(f"Failed to add finding to watcher: {await resp.text()}")
                return False
            return True

    # ─────────────────────────────────────────────────────────────
    # NARRATIVE DOCUMENT UPDATE
    # ─────────────────────────────────────────────────────────────

    async def update_narrative_markdown(self, document_id: str, markdown: str) -> bool:
        """
        Update narrative document markdown content.

        Prefer /api/graph/notes/:noteId to keep EDITh + graph in sync.
        """
        session = await self._get_session()

        # Try narrative update endpoint first.
        try:
            async with session.put(
                f"{BACKEND_URL}/api/graph/notes/{document_id}",
                json={"content": markdown}
            ) as resp:
                if resp.status < 400:
                    return True
                logger.warning(f"Failed to update narrative via /api/graph/notes: {await resp.text()}")
        except Exception as exc:
            logger.warning(f"Failed to update narrative via /api/graph/notes: {exc}")

        # Fallback: graph-only update via persist-entities.
        existing = await self.get_entity(document_id)
        if not existing:
            logger.warning(f"Document {document_id} not found for update")
            return False

        # Update via persist-entities with same ID
        payload = {
            "sourceNodeId": self.investigation_id or "sastre_auto",
            "entities": {
                "note": [{
                    "id": document_id,  # Existing ID triggers update
                    "className": "narrative",
                    "typeName": "note",
                    "label": existing.get("label", "Investigation Report"),
                    "content": markdown,
                    "metadata": {
                        **existing.get("metadata", {}),
                        "markdown": markdown,
                        "updatedAt": datetime.utcnow().isoformat(),
                        "updatedBy": "sastre_autopilot"
                    }
                }]
            },
            "projectId": self.project_id
        }

        async with session.post(
            f"{BACKEND_URL}/api/graph/persist-entities",
            json=payload
        ) as resp:
            if resp.status >= 400:
                logger.warning(f"Failed to update narrative: {await resp.text()}")
                return False
            return True

    # ─────────────────────────────────────────────────────────────
    # DISAMBIGUATION EDGE (mark entities as different)
    # ─────────────────────────────────────────────────────────────

    async def mark_different(
        self,
        entity_a_id: str,
        entity_b_id: str,
        reason: str = ""
    ) -> bool:
        """
        Mark two entities as DIFFERENT (not to be merged).

        Creates a DIFFERENT_FROM edge between entities.
        This is the REPEL outcome from disambiguation.
        """
        session = await self._get_session()

        # Create edge via persist-entities with edge specification
        # We create a "disambiguation" entity that links both with DIFFERENT_FROM edges
        disambiguation_node = {
            "className": "system",
            "typeName": "disambiguation",
            "label": f"REPEL: {entity_a_id[:8]} ≠ {entity_b_id[:8]}",
            "metadata": {
                "entity_a_id": entity_a_id,
                "entity_b_id": entity_b_id,
                "outcome": "REPEL",
                "reason": reason,
                "created": datetime.utcnow().isoformat(),
                "investigation_id": self.investigation_id
            }
        }

        payload = {
            "sourceNodeId": entity_a_id,  # Link from entity A
            "entities": {
                "disambiguation": [disambiguation_node]
            },
            "projectId": self.project_id
        }

        async with session.post(
            f"{BACKEND_URL}/api/graph/persist-entities",
            json=payload
        ) as resp:
            if resp.status >= 400:
                logger.warning(f"Failed to mark different: {await resp.text()}")
                return False

            logger.info(f"Marked DIFFERENT: {entity_a_id} ≠ {entity_b_id} ({reason})")
            return True

    async def park_binary_star(
        self,
        entity_a_id: str,
        entity_b_id: str,
        reason: str = "",
        confidence: Optional[float] = None
    ) -> bool:
        """
        Park an unresolved collision for human review (BINARY_STAR).

        Uses dedicated backend endpoint to persist disambiguation state.
        """
        session = await self._get_session()

        payload: Dict[str, Any] = {
            "entityAId": entity_a_id,
            "entityBId": entity_b_id,
            "reasoning": reason,
            "projectId": self.project_id,
        }
        # Binary-ratchet: confidence is optional legacy metadata; omit unless explicitly provided.
        if confidence is not None:
            payload["confidence"] = confidence

        async with session.post(
            f"{BACKEND_URL}/api/graph/disambiguation/park",
            json=payload
        ) as resp:
            if resp.status >= 400:
                logger.warning(f"Failed to park binary star: {await resp.text()}")
                return False
            return True

    # ─────────────────────────────────────────────────────────────
    # SUFFICIENCY CHECK
    # ─────────────────────────────────────────────────────────────

    async def check_sufficiency(
        self,
        document_id: Optional[str] = None,
        tasking: str = ""
    ) -> Dict[str, Any]:
        """Check if investigation is sufficient using constraint-based logic."""
        document = await self._build_document_snapshot(document_id, tasking)
        result = constraint_check(document)

        constraints = {
            "core_fields_populated": result.core_fields_populated,
            "tasking_headers_addressed": result.tasking_headers_addressed,
            "no_high_weight_absences": result.no_high_weight_absences,
            "disambiguation_resolved": result.disambiguation_resolved,
            "surprising_ands_processed": result.surprising_ands_processed,
        }

        return {
            "is_sufficient": result.is_complete,
            "overall_score": result.overall_score,
            "constraints": constraints,
            "collisions_pending": result.collisions_pending,
            "remaining_gaps": result.remaining_gaps,
            "recommendation": result.recommendation,
        }

    async def _build_document_snapshot(
        self,
        document_id: Optional[str] = None,
        tasking: str = ""
    ) -> Document:
        """Build a lightweight Document snapshot from Cymonides state."""
        markdown = ""
        if document_id:
            doc_node = await self.get_narrative_document(document_id)
            metadata = doc_node.get("metadata", {}) if doc_node else {}
            properties = doc_node.get("properties", {}) if doc_node else {}
            markdown = (
                metadata.get("markdown")
                or properties.get("markdown")
                or doc_node.get("content", "") if doc_node else ""
            )

        if markdown:
            document = DocumentInterface.from_markdown(markdown).document
        elif tasking:
            document = DocumentInterface.from_tasking(tasking).document
        else:
            document = Document()

        if document_id:
            document.id = document_id
        if tasking:
            document.tasking = tasking

        # Attach entities from grid rotation
        subject_mode = await self.get_grid_assessment("subject")
        document.known_entities = self._build_document_entities(subject_mode.rows)
        document.binary_stars = self._build_binary_stars(subject_mode.rows)

        # If no sections yet, seed from watchers
        if not document.sections:
            watchers = await self.get_watchers()
            document.sections = self._build_sections_from_watchers(watchers)

        return document

    def _build_document_entities(self, rows: List[Dict[str, Any]]) -> List[Entity]:
        """Convert grid subject rows into document entities."""
        entities: List[Entity] = []
        for row in rows:
            props = row.get("properties", {}) or {}
            entities.append(Entity(
                id=row.get("id", ""),
                name=row.get("label", ""),
                entity_type=row.get("type", "unknown"),
                attributes=EntityAttributes(
                    core=props.get("core", {}) or {},
                    shell=props.get("shell", {}) or {},
                    halo=props.get("halo", {}) or {},
                ),
            ))
        return entities

    def _build_sections_from_watchers(self, watchers: List[Dict[str, Any]]) -> List[Section]:
        """Convert watcher nodes into document sections."""
        sections: List[Section] = []
        for watcher in watchers:
            label = watcher.get("label") or watcher.get("name") or "Untitled"
            narrative = watcher.get("properties", {}).get("narrative", {}) if watcher else {}
            findings = narrative.get("findings", []) if isinstance(narrative, dict) else []
            content = narrative.get("summary", "") if isinstance(narrative, dict) else ""
            state = SectionState.COMPLETE if findings else SectionState.EMPTY
            sections.append(Section(
                header=label,
                state=state,
                content=content or "",
            ))
        return sections

    def _build_binary_stars(self, rows: List[Dict[str, Any]]) -> List[BinaryStar]:
        """Extract binary stars from node metadata."""
        stars: List[BinaryStar] = []
        seen = set()
        for row in rows:
            metadata = row.get("metadata", {}) or {}
            disambiguation = metadata.get("disambiguation", {}) if isinstance(metadata, dict) else {}
            if disambiguation.get("status") != "binary_star":
                continue
            entity_a = row.get("id", "")
            entity_b = disambiguation.get("relatedTo", "")
            if not entity_a or not entity_b:
                continue
            pair = tuple(sorted([entity_a, entity_b]))
            if pair in seen:
                continue
            seen.add(pair)
            stars.append(BinaryStar(
                entity_a_id=entity_a,
                entity_b_id=entity_b,
                similarity_score=disambiguation.get("confidence", 0.5),
            ))
        return stars


# =============================================================================
# FACTORY
# =============================================================================

async def create_investigation(project_id: str, tasking: str) -> CymonidesState:
    """Create a new investigation using the REAL backend."""
    state = CymonidesState(project_id)
    await state.create_investigation(tasking)
    return state


async def load_investigation(project_id: str, investigation_id: str) -> CymonidesState:
    """Load existing investigation."""
    state = CymonidesState(project_id, investigation_id)
    inv = await state.get_investigation()
    if not inv:
        raise ValueError(f"Investigation {investigation_id} not found")
    return state
