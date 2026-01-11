#!/usr/bin/env python3
"""
GRID-B - Native Python Grid Backend (no TypeScript dependency).

Implements:
- Grid rotation (/gridS, /gridX, /gridN, /gridL)
- Grid syntax parsing (filters, tags, watchers)
- Tagging and watcher creation (writes to cymonides-1-{project_id})

CYMONIDES MANDATE:
- Nodes live in cymonides-1-{project_id}
- Edges are embedded in nodes (embedded_edges)
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import md5
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from elasticsearch import Elasticsearch
except ImportError:  # pragma: no cover - handled by GridB init
    Elasticsearch = None


PROJECT_ROOT = Path(__file__).resolve().parents[3]
OPERATORS_PATH = Path(__file__).resolve().parent / "operators.json"


# -----------------------------------------------------------------------------
# Parse structures
# -----------------------------------------------------------------------------

@dataclass
class CellReference:
    kind: str  # cell, range, column, row
    column: Optional[str] = None  # A, B, C
    row: Optional[int] = None
    row_end: Optional[int] = None


@dataclass
class GridFilter:
    dimension: str
    value: str
    raw: str


@dataclass
class GridSyntaxParsed:
    raw: str
    is_grid_mode: bool
    rotation: Optional[str] = None  # subject, nexus, narrative, location
    class_filter: Optional[str] = None  # SUBJECT/NEXUS/NARRATIVE/LOCATION
    type_filter: Optional[str] = None  # person/company/etc
    node_refs: List[str] = field(default_factory=list)
    boolean_op: Optional[str] = None
    filters: List[GridFilter] = field(default_factory=list)
    cell_refs: List[CellReference] = field(default_factory=list)
    tag_to_apply: Optional[str] = None
    tag_to_remove: Optional[str] = None
    watcher_to_create: Optional[str] = None
    watcher_type_hint: Optional[str] = None
    action_chain: Optional[str] = None


# -----------------------------------------------------------------------------
# Constants (mirror gridSyntaxParser.ts)
# -----------------------------------------------------------------------------

CLASS_MAP = {
    "@subject": "SUBJECT",
    "@nexus": "NEXUS",
    "@narrative": "NARRATIVE",
    "@location": "LOCATION",
    "@s": "SUBJECT",
    "@x": "NEXUS",
    "@n": "NARRATIVE",
    "@l": "LOCATION",
}

TYPE_MAP = {
    "@person": "person",
    "@company": "company",
    "@p": "person",
    "@c": "company",
    "@query": "query",
    "@source": "source",
    "@q": "query",
    "@src": "source",
    "@email": "email",
    "@phone": "phone",
    "@username": "username",
    "@e": "email",
    "@t": "phone",
    "@u": "username",
    "@address": "address",
    "@jurisdiction": "jurisdiction",
    "@domain": "domain",
    "@addr": "address",
    "@dom": "domain",
    "@document": "document",
    "@note": "note",
    "@doc": "document",
}

ROTATION_MAP = {
    "S": "subject",
    "E": "subject",
    "X": "nexus",
    "N": "narrative",
    "L": "location",
}

CLASS_TO_TYPES = {
    "SUBJECT": ["person", "company", "email", "phone", "username"],
    "NEXUS": ["query", "source", "officer_of", "shareholder_of", "director_of", "beneficial_owner_of"],
    "NARRATIVE": ["document", "note", "narrative", "project", "watcher", "tag"],
    "LOCATION": ["address", "location", "jurisdiction", "domain", "url"],
}

WATCHER_SUFFIX_TO_TYPE = {
    "P": "person",
    "C": "company",
}


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify_tag(tag: str) -> str:
    return re.sub(r"[^a-z0-9\\-]+", "-", tag.strip().lower()).strip("-")


def _edge_id(from_id: str, to_id: str, relation: str) -> str:
    return md5(f"{from_id}:{to_id}:{relation}".encode("utf-8")).hexdigest()


def _get_project_index(project_id: str) -> str:
    return f"cymonides-1-{project_id}"


def _normalize_class_name(value: Optional[str]) -> str:
    raw = (value or "").strip().lower()
    if raw in ("source", "sources"):
        return "location"
    if raw in ("location", "locations"):
        return "location"
    if raw in ("entity", "entities"):
        return "subject"
    if raw in ("query", "queries"):
        return "nexus"
    return raw or "unknown"


def _legacy_class_name(value: Optional[str]) -> str:
    raw = (value or "").strip().lower()
    if raw == "subject":
        return "entity"
    if raw == "location":
        return "source"
    if raw == "nexus":
        return "query"
    return raw or "unknown"


def _pick_node_field(node: Dict[str, Any], *keys: str) -> Optional[Any]:
    for key in keys:
        value = node.get(key)
        if value is not None:
            return value
    return None


def _node_class(node: Dict[str, Any]) -> str:
    return (
        _pick_node_field(node, "node_class", "className", "class") or "unknown"
    )


def _node_type(node: Dict[str, Any]) -> str:
    return (
        _pick_node_field(node, "type", "typeName") or "unknown"
    )


def _node_label(node: Dict[str, Any]) -> str:
    return _pick_node_field(node, "label") or ""


def _node_metadata(node: Dict[str, Any]) -> Dict[str, Any]:
    metadata = node.get("metadata") or {}
    props = node.get("properties") or {}
    merged = dict(metadata)
    merged.update(props)
    if node.get("snippet") and merged.get("snippet") is None:
        merged["snippet"] = node.get("snippet")
    if node.get("content") and merged.get("content") is None:
        merged["content"] = node.get("content")
    if node.get("description") and merged.get("description") is None:
        merged["description"] = node.get("description")
    return merged


def _pick_target_properties(node: Dict[str, Any]) -> Dict[str, Any]:
    meta = node.get("metadata") or node.get("properties") or {}
    url = meta.get("url") or node.get("url") or node.get("canonicalValue")
    snippet = node.get("snippet") or meta.get("snippet") or meta.get("description")
    title = meta.get("title")
    domain = meta.get("domain")
    category = meta.get("category")
    filetype = meta.get("filetype") or meta.get("categoryAttributes", {}).get("filetype")
    country = meta.get("country") or meta.get("newsCountry")
    language = meta.get("language") or meta.get("newsLanguage")
    tag_color = meta.get("tagColor") or meta.get("color")

    props: Dict[str, Any] = {}
    if isinstance(url, str) and url.strip():
        props["url"] = url
    if isinstance(domain, str) and domain.strip():
        props["domain"] = domain
    if isinstance(title, str) and title.strip():
        props["title"] = title
    if isinstance(snippet, str) and snippet.strip():
        props["snippet"] = snippet[:500]
    if isinstance(category, str) and category.strip():
        props["category"] = category
    if isinstance(filetype, str) and filetype.strip():
        props["filetype"] = filetype.lower()
    if isinstance(country, str) and country.strip():
        props["country"] = country
    if isinstance(language, str) and language.strip():
        props["language"] = language
    if isinstance(tag_color, str) and tag_color.strip():
        props["color"] = tag_color
        props["tagColor"] = tag_color
    return props


# -----------------------------------------------------------------------------
# Operator registry
# -----------------------------------------------------------------------------

def load_operators(path: Optional[Path] = None) -> Dict[str, Any]:
    ops_path = path or OPERATORS_PATH
    if not ops_path.exists():
        return {"operators": [], "total": 0}
    data = json.loads(ops_path.read_text(encoding="utf-8"))
    ops = data.get("operators", data)
    if isinstance(ops, dict):
        ops = list(ops.values())
    return {"operators": ops, "total": len(ops)}


# -----------------------------------------------------------------------------
# Parser
# -----------------------------------------------------------------------------

def parse_grid_syntax(raw: str) -> GridSyntaxParsed:
    text = (raw or "").strip()
    if not text:
        return GridSyntaxParsed(raw=raw or "", is_grid_mode=False)

    parsed = GridSyntaxParsed(raw=text, is_grid_mode=False)

    # Split action chain
    if "=>" in text:
        selection, action = text.split("=>", 1)
        selection = selection.strip()
        action = action.strip()
    else:
        selection = text
        action = ""

    # /grid rotation
    grid_match = re.match(r"^/grid([A-Za-z])(?:\{([^}]*)\})?(.*)$", selection)
    if grid_match:
        parsed.is_grid_mode = True
        suffix = grid_match.group(1).upper()
        parsed.rotation = ROTATION_MAP.get(suffix)
        selection_body = (grid_match.group(2) or "").strip()
        tail = (grid_match.group(3) or "").strip()
        selection = " ".join([selection_body, tail]).strip()
    elif selection.startswith("#:"):
        parsed.is_grid_mode = True
        selection = selection[2:].strip()
    else:
        parsed.is_grid_mode = selection.startswith("#") or selection.startswith("@")

    # Action parsing (tag/watcher)
    if action:
        tag_add = re.match(r"^\+\#([A-Za-z0-9_:-]+)", action)
        tag_remove = re.match(r"^\-\#([A-Za-z0-9_:-]+)", action)
        watcher_match = re.match(
            r"^\+?(?:\#?watcher|w)([A-Za-z])?(?:\{([^}]+)\}|\[([^\]]+)\])",
            action,
            re.IGNORECASE,
        )
        if tag_add:
            parsed.tag_to_apply = tag_add.group(1)
        elif tag_remove:
            parsed.tag_to_remove = tag_remove.group(1)
        elif watcher_match:
            suffix = (watcher_match.group(1) or "").upper()
            header = (watcher_match.group(2) or watcher_match.group(3) or "").strip()
            parsed.watcher_to_create = header or None
            if suffix:
                parsed.watcher_type_hint = WATCHER_SUFFIX_TO_TYPE.get(suffix)
        else:
            parsed.action_chain = action

    # Cell references (inside braces - already merged into selection)
    cell_tokens = []
    for piece in re.split(r"[\s,]+", selection):
        if not piece:
            continue
        if re.match(r"^\d+-\d+[ABC]$", piece, re.IGNORECASE):
            cell_tokens.append(piece)
        elif re.match(r"^\d+[ABC]$", piece, re.IGNORECASE):
            cell_tokens.append(piece)
        elif re.match(r"^[ABC]$", piece, re.IGNORECASE):
            cell_tokens.append(piece)
        elif re.match(r"^\d+$", piece):
            cell_tokens.append(piece)
    for token in cell_tokens:
        ref = _parse_cell_ref(token)
        if ref:
            parsed.cell_refs.append(ref)

    # Tokenize remaining selection
    tokens = re.split(r"\s+", selection.strip())
    for token in tokens:
        if not token:
            continue
        upper = token.upper()
        lower = token.lower()

        if upper in ("AND", "OR"):
            parsed.boolean_op = upper
            continue
        if lower in CLASS_MAP:
            parsed.class_filter = CLASS_MAP[lower]
            continue
        if lower in TYPE_MAP:
            parsed.type_filter = TYPE_MAP[lower]
            continue
        if token.startswith("##"):
            filt = _parse_filter(token)
            if filt:
                parsed.filters.append(filt)
            continue
        if token.startswith("#") and not token.startswith("##"):
            parsed.node_refs.append(token[1:])
            continue
        if ":" in token:
            # Allow bare dimension:value tokens without ##
            filt = _parse_filter(f"##{token}")
            if filt:
                parsed.filters.append(filt)
            continue

    return parsed


def _parse_cell_ref(token: str) -> Optional[CellReference]:
    token = token.strip().upper()
    if not token:
        return None
    # Range like 1-5A
    match = re.match(r"^(\d+)-(\d+)([ABC])$", token)
    if match:
        return CellReference(
            kind="range",
            row=int(match.group(1)),
            row_end=int(match.group(2)),
            column=match.group(3),
        )
    # Cell like 1A
    match = re.match(r"^(\d+)([ABC])$", token)
    if match:
        return CellReference(
            kind="cell",
            row=int(match.group(1)),
            column=match.group(2),
        )
    # Column
    if token in ("A", "B", "C"):
        return CellReference(kind="column", column=token)
    # Row
    if token.isdigit():
        return CellReference(kind="row", row=int(token))
    return None


def _parse_filter(token: str) -> Optional[GridFilter]:
    raw = token.strip()
    value = raw.lstrip("#").strip()
    if not value:
        return None
    if ":" in value:
        dimension, val = value.split(":", 1)
        return GridFilter(dimension=dimension.strip(), value=val.strip(), raw=raw)
    return GridFilter(dimension=value.strip(), value="", raw=raw)


# -----------------------------------------------------------------------------
# GRID-B core
# -----------------------------------------------------------------------------

class GridB:
    def __init__(
        self,
        project_id: str,
        elastic_url: Optional[str] = None,
        operators_path: Optional[Path] = None,
    ) -> None:
        if Elasticsearch is None:
            raise RuntimeError("elasticsearch package is required for GridB execution")
        if not project_id:
            raise ValueError("project_id is required for GridB")
        self.project_id = project_id
        self.elastic_url = elastic_url or os.getenv(
            "ELASTICSEARCH_URL", os.getenv("ELASTIC_URL", "http://localhost:9200")
        )
        self.es = Elasticsearch([self.elastic_url])
        self.operators = load_operators(operators_path)

    # ------------------------------------------------------------------
    # Operators
    # ------------------------------------------------------------------

    def list_operators(self, category: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
        ops = self.operators.get("operators", [])
        if category:
            ops = [op for op in ops if str(op.get("category", "")).lower() == category.lower()]
        if status:
            ops = [op for op in ops if str(op.get("status", "")).lower() == status.lower()]
        return ops

    def get_operator(self, op_id: str) -> Optional[Dict[str, Any]]:
        for op in self.operators.get("operators", []):
            if op.get("id") == op_id:
                return op
        return None

    # ------------------------------------------------------------------
    # Node access
    # ------------------------------------------------------------------

    def get_nodes_by_ids(self, node_ids: List[str]) -> List[Dict[str, Any]]:
        if not node_ids:
            return []
        index_name = _get_project_index(self.project_id)
        resp = self.es.search(
            index=index_name,
            body={"query": {"terms": {"id": node_ids}}, "size": len(node_ids)},
        )
        return [hit.get("_source", {}) for hit in resp.get("hits", {}).get("hits", [])]

    # ------------------------------------------------------------------
    # Rotation
    # ------------------------------------------------------------------

    def rotate(
        self,
        primary_class: str,
        primary_type: Optional[str] = None,
        selected_node_ids: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        attributes: Optional[Dict[str, List[str]]] = None,
        temporal_filters: Optional[Dict[str, Any]] = None,
        search_keyword: Optional[str] = None,
        limit: int = 1000,
        cursor: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        index_name = _get_project_index(self.project_id)
        must: List[Any] = []

        canonical = _normalize_class_name(primary_class)
        class_alternates = (
            ["subject", "entity"] if canonical == "subject"
            else ["location", "source"] if canonical == "location"
            else ["nexus", "query"] if canonical == "nexus"
            else [canonical]
        )

        # Class filter
        if canonical:
            must.append({"terms": {"class": class_alternates}})

        # Type filter
        if primary_type:
            must.append({"term": {"type": primary_type}})

        # Search keyword
        if search_keyword:
            must.append({
                "bool": {
                    "should": [
                        {"match": {"label": search_keyword}},
                        {"match_phrase_prefix": {"label": search_keyword}},
                    ],
                    "minimum_should_match": 1,
                }
            })

        loci_filters_active = canonical in ("location", "source")

        # Category filter (location-only)
        if loci_filters_active and categories:
            cats = [c.strip().lower() for c in categories if str(c).strip()]
            if cats:
                must.append({
                    "bool": {
                        "should": [
                            {"terms": {"properties.category": cats}},
                            {"terms": {"metadata.category": cats}},
                        ],
                        "minimum_should_match": 1,
                    }
                })

        # Attribute filters (location-only)
        if loci_filters_active and attributes:
            for key, values in attributes.items():
                if not values:
                    continue
                terms = [str(v) for v in values if str(v).strip()]
                if not terms:
                    continue
                should = [
                    {"terms": {f"metadata.categoryAttributes.{key}": terms}},
                    {"terms": {f"metadata.{key}": terms}},
                    {"terms": {f"properties.{key}": terms}},
                ]
                if key == "dates":
                    should.append({"terms": {"metadata.year": terms}})
                    should.append({"terms": {"properties.year": terms}})
                must.append({"bool": {"should": should, "minimum_should_match": 1}})

        # Temporal filters (location-only)
        if loci_filters_active and temporal_filters:
            first_years = temporal_filters.get("firstSeenYears") or []
            last_years = temporal_filters.get("lastArchivedYears") or []
            age_min = temporal_filters.get("ageDaysMin")
            if first_years:
                must.append({"terms": {"metadata.temporal.first_seen_year": [str(v) for v in first_years]}})
            if last_years:
                must.append({"terms": {"metadata.temporal.last_archived_year": [str(v) for v in last_years]}})
            if isinstance(age_min, (int, float)):
                must.append({"range": {"metadata.temporal.age_days": {"gte": age_min}}})

        # Selected node pins (type pins + node pins)
        if selected_node_ids:
            type_pins = [nid for nid in selected_node_ids if str(nid).startswith("type:")]
            node_pins = [nid for nid in selected_node_ids if not str(nid).startswith("type:")]
            node_pins = [nid for nid in node_pins if nid != self.project_id]
            should: List[Any] = []
            if type_pins:
                types = [t.replace("type:", "") for t in type_pins if t.replace("type:", "")]
                if types:
                    should.append({"terms": {"type": types}})
            if node_pins:
                should.append({
                    "nested": {
                        "path": "embedded_edges",
                        "query": {"terms": {"embedded_edges.target_id": node_pins}},
                    }
                })
                should.append({"terms": {"embedded_edges.target_id": node_pins}})
                should.append({"terms": {"id": node_pins}})
            if should:
                must.append({"bool": {"should": should, "minimum_should_match": 1}})

        query_body: Dict[str, Any] = {
            "size": min(limit, 2000),
            "track_total_hits": True,
            "query": {"bool": {"must": must}} if must else {"match_all": {}},
            "sort": [{"metadata.updated_at": "desc"}, {"id": "desc"}],
        }
        if cursor and cursor.get("lastSeenAt") and cursor.get("lastNodeId"):
            query_body["search_after"] = [cursor["lastSeenAt"], cursor["lastNodeId"]]

        resp = self.es.search(index=index_name, body=query_body)
        hits = resp.get("hits", {}).get("hits", [])
        nodes = [h.get("_source", {}) for h in hits]
        total = resp.get("hits", {}).get("total", {}).get("value", len(nodes))

        rows = [self._map_node_to_row(node) for node in nodes]
        next_cursor = None
        if hits and len(hits) >= min(limit, 2000):
            last = nodes[-1]
            next_cursor = {
                "lastSeenAt": str((last.get("metadata") or {}).get("updated_at") or ""),
                "lastNodeId": str(last.get("id") or ""),
            }

        return {
            "rows": rows,
            "total": total,
            "nextCursor": next_cursor,
        }

    # ------------------------------------------------------------------
    # Tagging / watchers
    # ------------------------------------------------------------------

    def apply_tag(self, node_ids: List[str], tag: str) -> Dict[str, Any]:
        if not node_ids:
            return {"tagId": None, "tagLabel": tag, "count": 0}
        tag_id = f"tag:{_slugify_tag(tag)}"
        tag_node = self._ensure_tag_node(tag_id, tag)
        for node_id in node_ids:
            self._create_edge_bidirectional(node_id, tag_id, "tagged_with", {
                "tagLabel": tag,
                "tagColor": tag_node.get("metadata", {}).get("tagColor"),
                "color": tag_node.get("metadata", {}).get("tagColor"),
                "tagged_at": _now_iso(),
                "source": "grid_b",
            })
        return {"tagId": tag_id, "tagLabel": tag, "count": len(node_ids)}

    def remove_tag(self, node_ids: List[str], tag: str) -> Dict[str, Any]:
        if not node_ids:
            return {"tagId": None, "tagLabel": tag, "count": 0}
        tag_id = f"tag:{_slugify_tag(tag)}"
        for node_id in node_ids:
            self._remove_edge_bidirectional(node_id, tag_id, "tagged_with")
        return {"tagId": tag_id, "tagLabel": tag, "count": len(node_ids)}

    def create_watcher(self, label: str, node_ids: List[str], watcher_type_hint: Optional[str] = None) -> Dict[str, Any]:
        watcher_id = f"watcher_ent_{md5((label + _now_iso()).encode('utf-8')).hexdigest()[:12]}"
        monitored_types = [watcher_type_hint] if watcher_type_hint else None
        metadata = {
            "projectId": self.project_id,
            "createdBy": 0,
            "et3": {
                "watcherType": "entity",
                "monitoredTypes": monitored_types,
                "alertOnAnyMatch": True,
            },
            "narrative": {
                "parentDocumentId": "",
                "headerLevel": 0,
                "headerIndex": 0,
                "watcherStatus": "active",
                "extractionCount": 0,
                "lastCheckedAt": None,
                "findings": [],
            },
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        doc = self._index_node(
            node_id=watcher_id,
            class_name="narrative",
            type_name="watcher",
            label=label,
            metadata=metadata,
            content="",
            snippet=f"Entity watcher: {watcher_type_hint or 'all'}",
        )
        for node_id in node_ids:
            self._create_edge_bidirectional(
                watcher_id,
                node_id,
                "monitors",
                {"source": "grid_b", "matchedAt": _now_iso()},
            )
        return {"id": watcher_id, "label": label, "nodeCount": len(node_ids), "nodeIds": node_ids, "metadata": doc.get("metadata", {})}

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, syntax: str, limit: int = 1000) -> Dict[str, Any]:
        parsed = parse_grid_syntax(syntax)
        if not parsed.is_grid_mode:
            return {"error": "Not a grid syntax command", "syntax": syntax}

        view_class = parsed.rotation or (parsed.class_filter or "SUBJECT").lower()
        class_filter = parsed.class_filter or view_class.upper()
        primary_type = parsed.type_filter

        # Build filters from parsed filters
        categories: List[str] = []
        attributes: Dict[str, List[str]] = {}
        temporal_filters: Dict[str, Any] = {}
        selected_node_ids: List[str] = list(parsed.node_refs)

        for filt in parsed.filters:
            dim = filt.dimension
            val = filt.value
            if not dim:
                continue
            dim_lower = dim.lower()
            if dim_lower in ("entitytype", "topictype", "event", "theme"):
                if val:
                    primary_type = val
            elif dim_lower in ("project", "notes", "watchers", "goals", "tracks", "paths"):
                if val:
                    primary_type = val
            elif dim_lower == "tags":
                if val:
                    selected_node_ids.append(val)
            elif dim_lower in ("category",):
                if val:
                    categories.append(val)
            elif dim_lower in ("firstseen", "firstseenyear"):
                if val:
                    temporal_filters.setdefault("firstSeenYears", []).append(val)
            elif dim_lower in ("lastarchived", "lastarchivedyear"):
                if val:
                    temporal_filters.setdefault("lastArchivedYears", []).append(val)
            elif dim_lower == "agebucket":
                age_map = {"10y+": 3650, "5y+": 1825, "1y+": 365, "90d+": 90, "30d+": 30, "0-29d": 0}
                if val in age_map:
                    temporal_filters["ageDaysMin"] = max(
                        temporal_filters.get("ageDaysMin", 0),
                        age_map[val],
                    )
            else:
                if val:
                    attributes.setdefault(dim, []).append(val)

        rotation = self.rotate(
            primary_class=view_class,
            primary_type=primary_type,
            selected_node_ids=selected_node_ids or None,
            categories=categories or None,
            attributes=attributes or None,
            temporal_filters=temporal_filters or None,
            limit=limit,
        )

        rows = rotation.get("rows", [])
        selection = self._select_from_rows(rows, parsed.cell_refs)

        result: Dict[str, Any] = {
            "kind": "grid",
            "view": {
                "rotation": view_class,
                "classFilter": class_filter,
                "typeFilter": primary_type,
                "filters": [f.raw for f in parsed.filters],
            },
            "rows": rows,
            "total": len(rows),
            "selection": selection,
            "nextCursor": rotation.get("nextCursor"),
        }

        # Apply actions
        if parsed.tag_to_apply:
            tag_result = self.apply_tag(selection["nodeIds"], parsed.tag_to_apply)
            result["tagApplied"] = tag_result
        if parsed.tag_to_remove:
            tag_result = self.remove_tag(selection["nodeIds"], parsed.tag_to_remove)
            result["tagRemoved"] = tag_result
        if parsed.watcher_to_create:
            watcher = self.create_watcher(
                parsed.watcher_to_create,
                selection["nodeIds"],
                parsed.watcher_type_hint,
            )
            result["watcherCreated"] = watcher

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _index_node(
        self,
        node_id: str,
        class_name: str,
        type_name: str,
        label: str,
        metadata: Optional[Dict[str, Any]] = None,
        content: Optional[str] = None,
        snippet: Optional[str] = None,
    ) -> Dict[str, Any]:
        node_class = _normalize_class_name(class_name)
        legacy_class = _legacy_class_name(node_class)
        doc = {
            "id": node_id,
            "label": label,
            "node_class": node_class,
            "class": legacy_class,
            "className": node_class,
            "type": type_name,
            "typeName": type_name,
            "metadata": metadata or {},
            "content": content or "",
            "snippet": snippet or "",
            "createdAt": _now_iso(),
            "updatedAt": _now_iso(),
            "timestamp": _now_iso(),
            "projectId": self.project_id,
            "canonicalValue": (label or "").lower(),
            "url": label,
        }
        # Ensure metadata project_id timestamps
        doc["metadata"].setdefault("project_id", self.project_id)
        doc["metadata"].setdefault("created_at", _now_iso())
        doc["metadata"].setdefault("updated_at", _now_iso())
        self.es.index(index=_get_project_index(self.project_id), id=node_id, document=doc, refresh="wait_for")
        return doc

    def _ensure_tag_node(self, tag_id: str, tag_label: str) -> Dict[str, Any]:
        existing = self.get_nodes_by_ids([tag_id])
        if existing:
            return existing[0]
        metadata = {
            "project_id": self.project_id,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "tag_type": "grid_filter",
            "source": "grid_b",
        }
        return self._index_node(
            node_id=tag_id,
            class_name="narrative",
            type_name="tag",
            label=tag_label,
            metadata=metadata,
            content="",
            snippet="",
        )

    def _create_edge_bidirectional(self, from_id: str, to_id: str, relation: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        source_node = self.get_nodes_by_ids([from_id])
        target_node = self.get_nodes_by_ids([to_id])
        if not source_node or not target_node:
            return
        source = source_node[0]
        target = target_node[0]
        edge_id = _edge_id(from_id, to_id, relation)
        now = _now_iso()

        outgoing = {
            "edge_id": edge_id,
            "target_id": to_id,
            "target_label": _node_label(target),
            "target_class": _normalize_class_name(_node_class(target)),
            "target_type": _node_type(target),
            "relationship": relation,
            "direction": "outgoing",
            "confidence": None,
            "verified": None,
            "source_url": (metadata or {}).get("sourceUrl"),
            "timestamp": now,
            "target_properties": _pick_target_properties(target),
            "metadata": metadata or {},
            "created_at": now,
        }
        incoming = {
            "edge_id": edge_id,
            "target_id": from_id,
            "target_label": _node_label(source),
            "target_class": _normalize_class_name(_node_class(source)),
            "target_type": _node_type(source),
            "relationship": relation,
            "direction": "incoming",
            "confidence": None,
            "verified": None,
            "source_url": (metadata or {}).get("sourceUrl"),
            "timestamp": now,
            "target_properties": _pick_target_properties(source),
            "metadata": metadata or {},
            "created_at": now,
        }
        self._append_embedded_edge(from_id, outgoing)
        self._append_embedded_edge(to_id, incoming)

    def _append_embedded_edge(self, node_id: str, edge: Dict[str, Any]) -> None:
        index_name = _get_project_index(self.project_id)
        script = {
            "source": """
                if (ctx._source.embedded_edges == null || !(ctx._source.embedded_edges instanceof List)) {
                    ctx._source.embedded_edges = [];
                }
                boolean exists = false;
                for (e in ctx._source.embedded_edges) {
                    if (e.edge_id == params.edge.edge_id && e.direction == params.edge.direction) {
                        exists = true;
                        break;
                    }
                }
                if (!exists) { ctx._source.embedded_edges.add(params.edge); }
            """,
            "lang": "painless",
            "params": {"edge": edge},
        }
        self.es.update(index=index_name, id=node_id, body={"script": script}, refresh="wait_for")

    def _remove_edge_bidirectional(self, from_id: str, to_id: str, relation: str) -> None:
        edge_id = _edge_id(from_id, to_id, relation)
        self._remove_embedded_edge(from_id, edge_id)
        self._remove_embedded_edge(to_id, edge_id)

    def _remove_embedded_edge(self, node_id: str, edge_id: str) -> None:
        index_name = _get_project_index(self.project_id)
        script = {
            "source": """
                if (ctx._source.embedded_edges == null) { return; }
                ctx._source.embedded_edges.removeIf(e -> e.edge_id == params.edge_id);
            """,
            "lang": "painless",
            "params": {"edge_id": edge_id},
        }
        self.es.update(index=index_name, id=node_id, body={"script": script}, refresh="wait_for")

    def _map_node_to_row(self, node: Dict[str, Any]) -> Dict[str, Any]:
        merged_meta = _node_metadata(node)
        related = {
            "locations": [],
            "nexus": [],
            "subjects": [],
            "narratives": [],
            "sources": [],
            "queries": [],
            "entities": [],
        }
        tags: List[Dict[str, Any]] = []
        seen: set[str] = set()

        for edge in node.get("embedded_edges") or []:
            if edge.get("relationship") == "tagged_with" and edge.get("direction") == "outgoing":
                tags.append({
                    "id": edge.get("target_id"),
                    "name": edge.get("target_label"),
                    "color": (edge.get("metadata") or {}).get("color") or (edge.get("metadata") or {}).get("tagColor"),
                })

            target_id = edge.get("target_cluster_id") or edge.get("target_id")
            if not target_id or target_id in seen:
                continue
            seen.add(target_id)

            target_label = edge.get("target_cluster_label") or edge.get("target_label")
            target_class = edge.get("target_class")
            target_type = edge.get("target_type")
            edge_props = edge.get("target_properties") or {}
            edge_meta = edge.get("metadata") or {}
            meta = {**edge_props, **edge_meta}
            meta.update({
                "relationship": edge.get("relationship"),
                "direction": edge.get("direction"),
                "confidence": edge.get("confidence"),
                "verified": edge.get("verified"),
                "cluster_id": edge.get("target_cluster_id"),
                "cluster_label": edge.get("target_cluster_label"),
            })

            grid_node = {
                "id": target_id,
                "label": target_label,
                "class": {"name": target_class},
                "type": {"name": target_type},
                "metadata": meta,
                "lastSeen": edge.get("timestamp"),
            }

            if target_class in ("location", "source"):
                related["locations"].append(grid_node)
                related["sources"].append(grid_node)
            elif target_class in ("nexus", "query"):
                related["nexus"].append(grid_node)
                related["queries"].append(grid_node)
            elif target_class in ("subject", "entity"):
                related["subjects"].append(grid_node)
                related["entities"].append(grid_node)
            elif target_class == "narrative":
                related["narratives"].append(grid_node)

        # Inject project node as narrative if none found (skip if this IS project node)
        is_project_node = node.get("class") == "narrative" and node.get("type") == "project"
        if not related["narratives"] and self.project_id and not is_project_node:
            related["narratives"].append({
                "id": self.project_id,
                "label": "Project",
                "class": {"name": "narrative"},
                "type": {"name": "project"},
                "metadata": {},
                "lastSeen": _now_iso(),
            })

        return {
            "primaryNode": {
                "id": node.get("id"),
                "label": node.get("label"),
                "class": {"name": node.get("class") or node.get("className"), "displayLabel": node.get("class") or node.get("className")},
                "type": {"name": node.get("type") or node.get("typeName"), "displayLabel": node.get("type") or node.get("typeName")},
                "metadata": merged_meta,
                "lastSeen": (node.get("metadata") or {}).get("updated_at"),
                "updatedAt": (node.get("metadata") or {}).get("updated_at"),
                "tags": tags,
            },
            "relatedNodes": related,
            "tags": tags,
        }

    def _select_from_rows(self, rows: List[Dict[str, Any]], cell_refs: List[CellReference]) -> Dict[str, Any]:
        if not rows:
            return {"rowIndexes": [], "nodeIds": []}
        if not cell_refs:
            node_ids = [row.get("primaryNode", {}).get("id") for row in rows if row.get("primaryNode")]
            return {"rowIndexes": list(range(1, len(rows) + 1)), "nodeIds": [nid for nid in node_ids if nid]}

        row_indexes: set[int] = set()
        columns: set[str] = set()
        for ref in cell_refs:
            if ref.kind == "column" and ref.column:
                columns.add(ref.column)
            elif ref.kind == "row" and ref.row:
                row_indexes.add(ref.row)
            elif ref.kind == "cell" and ref.row and ref.column:
                row_indexes.add(ref.row)
                columns.add(ref.column)
            elif ref.kind == "range" and ref.row and ref.row_end and ref.column:
                for r in range(ref.row, ref.row_end + 1):
                    row_indexes.add(r)
                columns.add(ref.column)

        if not row_indexes:
            row_indexes = set(range(1, len(rows) + 1))
        if not columns:
            columns = {"A"}

        node_ids: List[str] = []
        for idx in sorted(row_indexes):
            if idx < 1 or idx > len(rows):
                continue
            row = rows[idx - 1]
            if "A" in columns or "B" in columns:
                primary = row.get("primaryNode", {})
                if primary.get("id"):
                    node_ids.append(primary["id"])
            if "C" in columns:
                related = row.get("relatedNodes", {})
                for bucket in ("locations", "nexus", "subjects", "narratives", "sources", "queries", "entities"):
                    for node in related.get(bucket, []) or []:
                        if node.get("id"):
                            node_ids.append(node["id"])

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_ids: List[str] = []
        for nid in node_ids:
            if nid in seen:
                continue
            seen.add(nid)
            unique_ids.append(nid)
        return {"rowIndexes": sorted(row_indexes), "nodeIds": unique_ids}
