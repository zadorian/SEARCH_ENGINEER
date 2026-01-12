#!/usr/bin/env python3
"""
SUBMARINE ⇄ EDITh Targets Note

Stores and retrieves SUBMARINE exploration targets (domains, URLs, rules)
in the local EDITh-B note system (SQLite-backed).

The document is intended to be user-editable (bullet lists); SUBMARINE will
merge updates rather than overwrite unrelated sections.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


TARGETS_DOC_TITLE_DEFAULT = "SUBMARINE Exploration Targets"


@dataclass
class ExplorationTargets:
    domain_rules: list[str] = field(default_factory=list)  # substring rules (indom)
    url_rules: list[str] = field(default_factory=list)  # substring rules (inurl)
    target_domains: list[str] = field(default_factory=list)
    target_urls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain_rules": self.domain_rules,
            "url_rules": self.url_rules,
            "target_domains": self.target_domains,
            "target_urls": self.target_urls,
        }


def _dedupe_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        v = (item or "").strip()
        if not v:
            continue
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
    return out


def _normalize_domain(domain: str) -> str:
    d = (domain or "").strip().lower()
    if d.startswith("www."):
        d = d[4:]
    if ":" in d:
        d = d.split(":", 1)[0]
    return d


def _normalize_url(url: str) -> str:
    return (url or "").strip()


def _edith_service() -> Any:
    # EDITH isn't a top-level package; import via path.
    edith_root = Path(__file__).resolve().parents[2] / "EDITH"
    if edith_root.exists() and str(edith_root) not in sys.path:
        sys.path.insert(0, str(edith_root))

    from edith_b.service import EdithBService  # type: ignore

    return EdithBService()


def _parse_section_bullets(markdown: str, section_title: str) -> list[str]:
    lines = (markdown or "").splitlines()
    title_re = re.compile(rf"^\s*##\s+{re.escape(section_title)}\s*$", re.IGNORECASE)
    bullets: list[str] = []

    in_section = False
    for line in lines:
        if title_re.match(line):
            in_section = True
            continue
        if in_section:
            if re.match(r"^\s*##\s+", line):
                break
            m = re.match(r"^\s*[-*]\s+(.*)$", line)
            if m:
                bullets.append(m.group(1).strip())
    return _dedupe_preserve(bullets)


def _format_bullets(items: list[str]) -> str:
    items = [i.strip() for i in items if (i or "").strip()]
    if not items:
        return ""
    return "\n".join([f"- {i}" for i in items])


def ensure_targets_document(
    project_id: str,
    title: str = TARGETS_DOC_TITLE_DEFAULT,
) -> dict[str, Any]:
    service = _edith_service()

    # Find by metadata marker first, fall back to title match.
    for doc in service.list_documents(project_id=project_id):
        meta = doc.get("metadata") or {}
        submarine_meta = meta.get("submarine") if isinstance(meta, dict) else None
        if isinstance(submarine_meta, dict) and submarine_meta.get("doc_type") == "targets":
            return service.get_document(doc["id"]) or doc
        if (doc.get("title") or "").strip().lower() == title.strip().lower():
            return service.get_document(doc["id"]) or doc

    skeleton = f"""# {title}

This note is used by SUBMARINE to store exploration targets and rules.
You can edit the bullet lists below; SUBMARINE will merge in new targets.

## Domain Rules (indom)

## URL Rules (inurl)

## Target Domains

## Target URLs

## Notes
"""

    created = service.create_document(
        title=title,
        markdown=skeleton,
        project_id=project_id,
        doc_mode="markdown",
        metadata={"submarine": {"doc_type": "targets", "schema_version": 1}},
    )
    return created


def load_targets(project_id: str, title: str = TARGETS_DOC_TITLE_DEFAULT) -> tuple[dict[str, Any], ExplorationTargets]:
    doc = ensure_targets_document(project_id=project_id, title=title)
    markdown = doc.get("markdown") or ""

    targets = ExplorationTargets(
        domain_rules=_parse_section_bullets(markdown, "Domain Rules (indom)"),
        url_rules=_parse_section_bullets(markdown, "URL Rules (inurl)"),
        target_domains=[
            _normalize_domain(d) for d in _parse_section_bullets(markdown, "Target Domains")
        ],
        target_urls=[_normalize_url(u) for u in _parse_section_bullets(markdown, "Target URLs")],
    )

    targets.domain_rules = _dedupe_preserve(targets.domain_rules)
    targets.url_rules = _dedupe_preserve(targets.url_rules)
    targets.target_domains = _dedupe_preserve([d for d in targets.target_domains if d])
    targets.target_urls = _dedupe_preserve([u for u in targets.target_urls if u])

    return doc, targets


def update_targets(
    project_id: str,
    add_domains: Optional[list[str]] = None,
    add_urls: Optional[list[str]] = None,
    add_domain_rules: Optional[list[str]] = None,
    add_url_rules: Optional[list[str]] = None,
    title: str = TARGETS_DOC_TITLE_DEFAULT,
) -> tuple[dict[str, Any], ExplorationTargets]:
    service = _edith_service()
    doc, current = load_targets(project_id=project_id, title=title)

    domains = list(current.target_domains)
    urls = list(current.target_urls)
    domain_rules = list(current.domain_rules)
    url_rules = list(current.url_rules)

    for d in add_domains or []:
        nd = _normalize_domain(d)
        if nd:
            domains.append(nd)
    for u in add_urls or []:
        nu = _normalize_url(u)
        if nu:
            urls.append(nu)
    for r in add_domain_rules or []:
        rr = (r or "").strip()
        if rr:
            domain_rules.append(rr)
    for r in add_url_rules or []:
        rr = (r or "").strip()
        if rr:
            url_rules.append(rr)

    merged = ExplorationTargets(
        domain_rules=_dedupe_preserve(domain_rules),
        url_rules=_dedupe_preserve(url_rules),
        target_domains=_dedupe_preserve(domains),
        target_urls=_dedupe_preserve(urls),
    )

    doc_id = doc["id"]
    service.update_section_content(doc_id, "Domain Rules (indom)", _format_bullets(merged.domain_rules))
    service.update_section_content(doc_id, "URL Rules (inurl)", _format_bullets(merged.url_rules))
    service.update_section_content(doc_id, "Target Domains", _format_bullets(merged.target_domains))
    service.update_section_content(doc_id, "Target URLs", _format_bullets(merged.target_urls))

    service.update_document(
        doc_id,
        metadata_patch={
            "submarine": {
                "doc_type": "targets",
                "schema_version": 1,
                "updated_at": datetime.utcnow().isoformat(),
                "counts": {
                    "domain_rules": len(merged.domain_rules),
                    "url_rules": len(merged.url_rules),
                    "target_domains": len(merged.target_domains),
                    "target_urls": len(merged.target_urls),
                },
            }
        },
        auto_extract=False,
    )

    updated_doc = service.get_document(doc_id, sync_from_disk=False) or doc
    return updated_doc, merged

