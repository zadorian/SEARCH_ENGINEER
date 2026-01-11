"""
Abacus V4.2 — SUBJECT kinds (not "entity classes")
===================================================

Abacus has four *classes*:
  - SUBJECT, LOCATION, NEXUS, NARRATIVE

Within SUBJECT, we distinguish *kinds*:
  - entity: concrete people/companies/identifiers (traditional "entities")
  - concept: abstract topic/theme/industry (needs dimensions to become actionable)
  - topic: a stabilized concept used as an investigative anchor
  - event: a concretized concept bound to time + place + actors

This module defines the minimal deterministic contract used by SASTRE.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple


class SubjectKind(Enum):
    ENTITY = "entity"
    CONCEPT = "concept"
    TOPIC = "topic"
    EVENT = "event"


def infer_subject_kind(type_name: Optional[str], node: Optional[Dict[str, Any]] = None) -> SubjectKind:
    """
    Infer SUBJECT kind from node typeName/metadata. Deterministic, no probabilities.

    Current storage schema doesn't yet have dedicated topic/event types,
    so we use typeName and/or metadata.subject_kind if present.
    """
    if node and isinstance(node.get("metadata"), dict):
        sk = node["metadata"].get("subject_kind")
        if isinstance(sk, str):
            try:
                return SubjectKind(sk.strip().lower())
            except Exception:
                pass

    tn = (type_name or "").strip().lower()
    if tn in ("topic", "theme", "industry", "concept"):
        return SubjectKind.CONCEPT
    if tn in ("event", "ipo", "lawsuit", "data_breach"):
        return SubjectKind.EVENT
    return SubjectKind.ENTITY


@dataclass(frozen=True)
class HardeningSignal:
    """
    Deterministic "hardening" check: when a concept becomes event/topic.

    required_dimensions is the binary checklist.
    """
    has_time: bool
    has_place: bool
    has_actor: bool

    @property
    def is_event_ready(self) -> bool:
        return self.has_time and self.has_place and self.has_actor


def detect_hardening_signal(node: Dict[str, Any]) -> HardeningSignal:
    """
    Detect if a subject has enough dimensions to harden into an EVENT.

    We rely on existing property conventions and metadata keys:
      - time: date/date_range/timestamp/year
      - place: jurisdiction/country/location
      - actor: linked entity ids or explicit actor fields
    """
    props = node.get("properties") or {}
    meta = node.get("metadata") or {}
    if not isinstance(props, dict):
        props = {}
    if not isinstance(meta, dict):
        meta = {}

    has_time = any(k in props and props.get(k) for k in ("date", "timestamp", "year", "time_range", "date_range")) or any(
        k in meta and meta.get(k) for k in ("date", "timestamp", "year", "time_range", "date_range")
    )
    has_place = any(k in props and props.get(k) for k in ("jurisdiction", "country", "location")) or any(
        k in meta and meta.get(k) for k in ("jurisdiction", "country", "location")
    )
    # Actor can be represented as edges; we allow metadata.actor_ids as a deterministic bridge.
    actor_ids = meta.get("actor_ids") if isinstance(meta.get("actor_ids"), list) else []
    has_actor = bool(actor_ids) or any(k in props and props.get(k) for k in ("company", "person", "actors"))
    return HardeningSignal(has_time=bool(has_time), has_place=bool(has_place), has_actor=bool(has_actor))


