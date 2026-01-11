from typing import Dict, Any, List
from ..core.state import (
    InvestigationState, NarrativeItem, Query, SourceResult,
    Entity, Edge, EntityType, NarrativeState, QueryState, SourceState,
    NarrativeGoal, NarrativeTrack, NarrativePath, InvestigationPhase,
)
from ..contracts import KUQuadrant, Intent
from ..orchestrator import CymonidesClient

class InvestigationHydrator:
    """
    Hydrates InvestigationState from Cymonides (Elasticsearch) data.
    
    Bridges the gap between:
    1. The "Thin Wrapper" (CymonidesClient/Elasticsearch)
    2. The "Rich State" (InvestigationState for Agent reasoning)
    """
    
    def __init__(self, client: CymonidesClient):
        self.client = client
        
    async def hydrate(self, project_id: str, investigation_id: str) -> InvestigationState:
        """
        Build full InvestigationState from Cymonides graph.
        """
        # 1. Fetch Investigation Node
        inv_data = await self.client.get_node(project_id, investigation_id)
        if "error" in inv_data or not inv_data.get("nodes"):
            raise ValueError(f"Investigation {investigation_id} not found")
            
        root = inv_data["nodes"][0]
        tasking = root.get("properties", {}).get("tasking", "")
        
        state = InvestigationState.create(project_id, tasking)
        state.id = investigation_id
        phase_value = root.get("properties", {}).get("phase")
        if isinstance(phase_value, InvestigationPhase):
            state.phase = phase_value
        elif isinstance(phase_value, str):
            try:
                state.phase = InvestigationPhase(phase_value)
            except ValueError:
                state.phase = InvestigationPhase.INITIALIZING
        else:
            state.phase = InvestigationPhase.INITIALIZING
        
        # 2. Fetch all related nodes (Grid rotation across all modes)
        all_rows: List[Dict[str, Any]] = []
        for mode in ("narrative", "subject", "location", "nexus"):
            grid_data = await self.client.get_rotated_grid(project_id, mode=mode, limit=1000)
            if isinstance(grid_data, dict) and isinstance(grid_data.get("rows"), list):
                all_rows.extend(grid_data["rows"])

        # 3. Process Nodes
        seen_nodes = set()
        for row in all_rows:
            primary = row.get("primaryNode", {}) or {}
            node_id = primary.get("id")
            if not node_id or node_id in seen_nodes:
                continue
            node_class = self._normalize_node_class(primary)
            node_type = self._normalize_node_type(primary)

            if node_class == "narrative" and node_type != "investigation":
                if node_type == "goal":
                    self._add_goal(state, primary)
                elif node_type == "track":
                    self._add_track(state, primary)
                elif node_type == "path":
                    self._add_path(state, primary)
                else:
                    # Narrative Item (Document Section / Note / Watcher)
                    self._add_narrative_item(state, primary)

            elif node_class in ("query", "search"):
                self._add_query(state, primary)

            elif node_class in ("source", "domain", "jurisdiction"):
                self._add_source(state, primary)

            elif node_class == "entity":
                self._add_entity(state, primary)

            seen_nodes.add(node_id)

        # 4. Process Edges (Relationships)
        seen_edges = set()
        for row in all_rows:
            primary_id = row.get("primaryNode", {}).get("id")
            if not primary_id:
                continue
            for related in self._iter_related_nodes(row.get("relatedNodes")):
                related_id = related.get("id")
                rel_type = related.get("relationship") or related.get("relation") or "related_to"

                if not related_id:
                    continue
                edge_key = (primary_id, related_id, rel_type)
                if edge_key in seen_edges:
                    continue
                seen_edges.add(edge_key)

                state.add_edge(Edge.create(
                    source_id=primary_id,
                    target_id=related_id,
                    relationship=rel_type
                ))

                # Also link hierarchy if applicable
                if primary_id in state.narrative_items and related_id in state.queries:
                    state.narrative_items[primary_id].add_query(related_id)
                    state.narrative_to_queries[primary_id].append(related_id)

                if primary_id in state.queries and related_id in state.sources:
                    if related_id not in state.queries[primary_id].source_ids:
                        state.queries[primary_id].source_ids.append(related_id)

                if primary_id in state.goals and related_id in state.tracks:
                    state.add_track(state.tracks[related_id])

                if primary_id in state.tracks and related_id in state.paths:
                    state.add_path(state.paths[related_id])
        
        return state

    def _add_narrative_item(self, state: InvestigationState, node: Dict):
        """Map Cymonides narrative node to NarrativeItem."""
        item = NarrativeItem(
            id=node["id"],
            question=node.get("label", ""),
            intent=node.get("properties", {}).get("intent", "discover_subject"),
            priority=node.get("properties", {}).get("priority", "medium"),
            state=NarrativeState.ANSWERED if node.get("properties", {}).get("content") else NarrativeState.UNANSWERED
        )
        state.add_narrative_item(item)

    def _add_goal(self, state: InvestigationState, node: Dict):
        """Map Cymonides narrative goal node."""
        goal = NarrativeGoal(
            id=node["id"],
            title=node.get("label", ""),
            description=node.get("metadata", {}).get("description", ""),
            status=node.get("metadata", {}).get("status", "active"),
        )
        state.add_goal(goal)

    def _add_track(self, state: InvestigationState, node: Dict):
        """Map Cymonides narrative track node."""
        metadata = node.get("metadata", {}) or {}
        track = NarrativeTrack(
            id=node["id"],
            goal_id=metadata.get("goal_id", ""),
            title=node.get("label", ""),
            description=metadata.get("description", ""),
            status=metadata.get("status", "active"),
        )
        state.add_track(track)

    def _add_path(self, state: InvestigationState, node: Dict):
        """Map Cymonides narrative path node."""
        metadata = node.get("metadata", {}) or {}
        path = NarrativePath(
            id=node["id"],
            track_id=metadata.get("track_id", ""),
            title=node.get("label", ""),
            description=metadata.get("description", ""),
            status=metadata.get("status", "active"),
        )
        state.add_path(path)

    def _add_query(self, state: InvestigationState, node: Dict):
        """Map Cymonides query node to Query."""
        props = node.get("properties", {}) or {}
        macro = props.get("macro") or props.get("query") or node.get("label", "")
        quadrant_raw = props.get("quadrant") or props.get("ku_quadrant")
        intent_raw = props.get("intent")

        ku_quadrant = KUQuadrant.DISCOVER
        if isinstance(quadrant_raw, KUQuadrant):
            ku_quadrant = quadrant_raw
        elif isinstance(quadrant_raw, str):
            try:
                ku_quadrant = KUQuadrant(quadrant_raw)
            except ValueError:
                ku_quadrant = KUQuadrant.DISCOVER

        intent = Intent.DISCOVER_SUBJECT
        if isinstance(intent_raw, Intent):
            intent = intent_raw
        elif isinstance(intent_raw, str):
            try:
                intent = Intent(intent_raw)
            except ValueError:
                intent = Intent.DISCOVER_SUBJECT

        q = Query(
            id=node["id"],
            macro=macro or "",
            narrative_id="",  # Linked via edges later
            ku_quadrant=ku_quadrant,
            intent=intent,
            state=QueryState.COMPLETE
        )
        state.add_query(q)

    def _add_source(self, state: InvestigationState, node: Dict):
        """Map Cymonides source node to SourceResult."""
        metadata = node.get("metadata", {}) or {}
        props = node.get("properties", {}) or {}
        url = metadata.get("url") or props.get("url") or node.get("label", "")
        title = metadata.get("title") or props.get("title") or ""
        state_raw = props.get("state") or metadata.get("state")
        source_state = SourceState.CHECKED
        if isinstance(state_raw, SourceState):
            source_state = state_raw
        elif isinstance(state_raw, str):
            try:
                source_state = SourceState(state_raw)
            except ValueError:
                source_state = SourceState.CHECKED

        s = SourceResult(
            id=node["id"],
            url=url,
            source_name=node.get("label", "") or url,
            title=title,
            jurisdiction=props.get("jurisdiction", "unknown"),
            query_id="",  # Linked via edges later
            state=source_state,
        )
        state.add_source(s)

    def _add_entity(self, state: InvestigationState, node: Dict):
        """Map Cymonides entity node to Entity."""
        entity_type_raw = node.get("type") or node.get("typeName") or node.get("entityType")
        try:
            entity_type = EntityType(entity_type_raw)
        except Exception:
            entity_type = EntityType.UNKNOWN

        e = Entity.create(
            name=node.get("label", ""),
            entity_type=entity_type,
        )
        e.id = node["id"]
        
        # Hydrate properties
        props = node.get("properties", {})
        for k, v in props.items():
            e.add_core_attribute(k, v, "hydrated")
            
        state.add_entity(e, "hydrated")

    def _normalize_node_class(self, node: Dict[str, Any]) -> str:
        """Extract node class name from grid node."""
        class_value = node.get("class") or node.get("className")
        if isinstance(class_value, dict):
            class_value = class_value.get("name") or class_value.get("id")
        return (class_value or "").lower()

    def _normalize_node_type(self, node: Dict[str, Any]) -> str:
        """Extract node type name from grid node."""
        type_value = node.get("type") or node.get("typeName")
        if isinstance(type_value, dict):
            type_value = type_value.get("name") or type_value.get("id")
        return (type_value or "").lower()

    def _iter_related_nodes(self, related_nodes: Any) -> List[Dict[str, Any]]:
        """Yield related nodes from grid row shape."""
        if isinstance(related_nodes, list):
            return related_nodes
        if isinstance(related_nodes, dict):
            collected: List[Dict[str, Any]] = []
            for bucket_nodes in related_nodes.values():
                if isinstance(bucket_nodes, list):
                    collected.extend(bucket_nodes)
            return collected
        return []
