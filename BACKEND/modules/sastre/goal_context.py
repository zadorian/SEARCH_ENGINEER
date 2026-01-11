"""
Goal Context (V4.2) — Narrative Notes as Programming
===================================================

Source of truth:
  - narrative class nodes, type "note"
  - metadata.investigation_id identifies which investigation the note belongs to
  - metadata.topology_role indicates its role: "goal" or "track" (etc.)

The Motor (intent derivation) must read strict metadata when available.
The note body can provide a minimal deterministic fallback via prefixes:

  GOAL: ...
  REQUIRES: ownership, directors, jurisdiction, adverse_media
  SUBJECT: Acme Ltd (HR)
  TRACK: Corporate Structure
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Set


@dataclass(frozen=True)
class GoalContext:
    note_id: str
    investigation_id: str
    title: str
    # Preserve explicit author ordering from metadata/body.
    requires_ordered: List[str]
    # Convenience set (normalized) for membership checks.
    requires: Set[str]
    subject_hint: Optional[str] = None
    track_hint: Optional[str] = None


def _read_note_content(note: Dict[str, Any]) -> str:
    # Notes are stored either in `content` or `metadata.content` (see graphRouter).
    content = note.get("content")
    if isinstance(content, str) and content.strip():
        return content
    meta = note.get("metadata") or {}
    if isinstance(meta, dict):
        mc = meta.get("content")
        if isinstance(mc, str) and mc.strip():
            return mc
    return ""


def parse_goal_context_from_note(note: Dict[str, Any]) -> Optional[GoalContext]:
    """
    Convert a Cymonides narrative note node into a GoalContext.

    Deterministic contract:
      - requires metadata.investigation_id
      - requires metadata.topology_role == "goal"
      - requires list is read from metadata.required_sections if present
        else from REQUIRES: line in body
    """
    if not isinstance(note, dict):
        return None

    note_id = note.get("id") or ""
    meta = note.get("metadata") or {}
    if not isinstance(meta, dict):
        meta = {}

    inv_id = meta.get("investigation_id") or meta.get("investigationId") or ""
    role = meta.get("topology_role") or meta.get("topologyRole") or meta.get("role") or ""
    if str(role).lower().strip() != "goal":
        return None
    if not inv_id or not note_id:
        return None

    title = (note.get("label") or note.get("name") or "Goal").strip()

    requires_ordered: List[str] = []
    requires: Set[str] = set()
    req_meta = meta.get("required_sections") or meta.get("requires") or meta.get("requiredSections")
    if isinstance(req_meta, list):
        for item in req_meta:
            s = str(item).strip().lower()
            if s:
                if s not in requires:
                    requires_ordered.append(s)
                    requires.add(s)
    elif isinstance(req_meta, str) and req_meta.strip():
        for part in req_meta.split(","):
            s = part.strip().lower()
            if s:
                if s not in requires:
                    requires_ordered.append(s)
                    requires.add(s)

    content = _read_note_content(note)
    subject_hint: Optional[str] = None
    track_hint: Optional[str] = None

    # Prefix parsing fallback
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        upper = line.upper()
        if upper.startswith("REQUIRES:") and not requires:
            rhs = line.split(":", 1)[1]
            for part in rhs.split(","):
                s = part.strip().lower()
                if s:
                    if s not in requires:
                        requires_ordered.append(s)
                        requires.add(s)
        elif upper.startswith("SUBJECT:") and not subject_hint:
            subject_hint = line.split(":", 1)[1].strip() or None
        elif upper.startswith("TRACK:") and not track_hint:
            track_hint = line.split(":", 1)[1].strip() or None

    return GoalContext(
        note_id=str(note_id),
        investigation_id=str(inv_id),
        title=title,
        requires_ordered=requires_ordered,
        requires=requires,
        subject_hint=subject_hint,
        track_hint=track_hint,
    )

@dataclass(frozen=True)
class TrackContext:
    note_id: str
    investigation_id: str
    track_key: str
    title: str
    order_index: int
    content: str


def parse_track_context_from_note(note: Dict[str, Any]) -> Optional[TrackContext]:
    """Parse narrative:note nodes with metadata.topology_role == 'track'."""
    if not isinstance(note, dict):
        return None

    note_id = note.get("id") or ""
    meta = note.get("metadata") or {}
    if not isinstance(meta, dict):
        meta = {}

    inv_id = meta.get("investigation_id") or meta.get("investigationId") or ""
    role = meta.get("topology_role") or meta.get("topologyRole") or meta.get("role") or ""
    if str(role).lower().strip() != "track":
        return None
    if not inv_id or not note_id:
        return None

    track_key = (meta.get("track_key") or meta.get("trackKey") or "").strip().lower()
    if not track_key:
        return None

    order_index_raw = meta.get("topology_index") or meta.get("topologyIndex") or meta.get("order") or 0
    try:
        order_index = int(order_index_raw)
    except Exception:
        order_index = 0

    title = (note.get("label") or note.get("name") or track_key).strip()
    content = _read_note_content(note)
    return TrackContext(
        note_id=str(note_id),
        investigation_id=str(inv_id),
        track_key=str(track_key),
        title=title,
        order_index=order_index,
        content=content,
    )


def tokenize_goal_requires(requires: Set[str]) -> Set[str]:
    """
    Normalize required section tokens into a stable set.
    Keeps "Naming is Programming": tokens are explicit, not inferred.
    """
    out: Set[str] = set()
    for r in requires or set():
        s = str(r).strip().lower()
        if not s:
            continue
        # Allow both "beneficial_ownership" and "beneficial ownership"
        out.add(s.replace(" ", "_"))
        out.add(s.replace("_", " "))
        out.add(s)
    return out