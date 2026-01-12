from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .snippets import first_snippet, snippet_for_span


DEFAULT_REGISTRY_PATH = Path(os.getenv("PACMAN_WATCHER_REGISTRY", "/data/.cache/pacman_watchers.json"))
DEFAULT_HAIKU_MAX_CALLS = int(os.getenv("PACMAN_HAIKU_MAX_CALLS", "25"))
DEFAULT_HAIKU_TEXT_LIMIT = int(os.getenv("PACMAN_HAIKU_TEXT_LIMIT", "20000"))
DEFAULT_HAIKU_DOMAIN_MAX = int(os.getenv("PACMAN_HAIKU_DOMAIN_MAX", "500"))

_HAIKU_CALLS: Dict[str, int] = {}


@dataclass(frozen=True)
class ExtractionTarget:
    """
    A single extraction target.

    mode:
      - builtin: use PACMAN built-ins (companies/persons/fast)
      - regex: run a regex and capture group 0 (or group N if group specified)
      - haiku: reserved for AI slot extraction (best-effort; optional)
    """

    name: str
    mode: str = "builtin"
    pattern: Optional[str] = None
    flags: str = "i"
    group: int = 0
    max_hits: int = 20
    instruction: Optional[str] = None  # haiku: describe what to extract
    trigger: Optional[str] = None      # pattern required to trigger execution


@dataclass
class WatcherSpec:
    watcher_id: str
    submarine_order: str
    domain_count: Optional[int] = None
    created_at: float = field(default_factory=lambda: time.time())
    ttl_seconds: int = 6 * 60 * 60  # 6h default
    targets: List[ExtractionTarget] = field(default_factory=list)

    def is_expired(self, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        return (now - self.created_at) > float(self.ttl_seconds)


def _ensure_parent(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def load_registry(path: Path = DEFAULT_REGISTRY_PATH) -> Dict[str, WatcherSpec]:
    """
    Load watcher specs from disk and prune expired entries.
    """
    if not path.exists():
        return {}

    try:
        raw = json.loads(path.read_text())
    except Exception:
        return {}

    now = time.time()
    registry: Dict[str, WatcherSpec] = {}
    for watcher_id, payload in (raw or {}).items():
        try:
            targets = [
                ExtractionTarget(**t) if isinstance(t, dict) else ExtractionTarget(name=str(t))
                for t in payload.get("targets", [])
            ]
            spec = WatcherSpec(
                watcher_id=str(payload.get("watcher_id") or watcher_id),
                submarine_order=str(payload.get("submarine_order") or ""),
                domain_count=payload.get("domain_count"),
                created_at=float(payload.get("created_at", now)),
                ttl_seconds=int(payload.get("ttl_seconds", 6 * 60 * 60)),
                targets=targets,
            )
            if spec.is_expired(now):
                continue
            registry[spec.watcher_id] = spec
        except Exception:
            continue

    # Best-effort rewrite to drop expired/invalid entries
    try:
        save_registry(registry, path)
    except Exception:
        pass

    return registry


def save_registry(registry: Dict[str, WatcherSpec], path: Path = DEFAULT_REGISTRY_PATH) -> None:
    _ensure_parent(path)
    payload = {k: asdict(v) for k, v in registry.items()}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str))
    tmp.replace(path)


def register_watcher(spec: WatcherSpec, path: Path = DEFAULT_REGISTRY_PATH) -> None:
    registry = load_registry(path)
    registry[spec.watcher_id] = spec
    save_registry(registry, path)


def unregister_watcher(watcher_id: str, path: Path = DEFAULT_REGISTRY_PATH) -> None:
    registry = load_registry(path)
    registry.pop(watcher_id, None)
    save_registry(registry, path)


def get_watcher(watcher_id: str, path: Path = DEFAULT_REGISTRY_PATH) -> Optional[WatcherSpec]:
    return load_registry(path).get(watcher_id)


def default_targets() -> List[ExtractionTarget]:
    return [
        ExtractionTarget(name="companies", mode="builtin"),
        ExtractionTarget(name="persons", mode="builtin"),
        ExtractionTarget(name="fast", mode="builtin"),
    ]


def _strip_html(html: str) -> str:
    if not html:
        return ""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


def extract_for_watcher(
    *,
    watcher: WatcherSpec,
    content: str,
    url: str = "",
    allow_ai: bool = True,
) -> List[Dict[str, Any]]:
    """
    Run extraction for a watcher spec and return normalized findings.

    Each finding includes a snippet with >=10 words of surrounding context when available.
    """
    if not content:
        return []

    text = _strip_html(content)
    findings: List[Dict[str, Any]] = []

    for target in watcher.targets:
        mode = (target.mode or "builtin").strip().lower()
        name = (target.name or "").strip()
        if not name:
            continue

        if mode == "builtin":
            findings.extend(_extract_builtin(name, text, url=url, max_hits=target.max_hits))
        elif mode == "regex":
            findings.extend(_extract_regex(target, text, url=url))
        elif mode == "haiku":
            if not allow_ai or not _haiku_allowed(watcher):
                continue
            findings.extend(_extract_haiku(target, watcher, text, url=url))

    return findings


def _gliner_enabled() -> bool:
    try:
        from .ai_backends.gliner import GLiNERBackend
        return GLiNERBackend().is_available()
    except ImportError:
        return False

def _extract_gliner(target_name: str, text: str, *, url: str) -> List[Dict[str, Any]]:
    """Run GLiNER extraction for a specific target type."""
    try:
        from .ai_backends.gliner import GLiNERBackend
        from .ai_backends.base import EntityType
    except ImportError:
        return []

    backend = GLiNERBackend()
    if not backend.is_available():
        return []

    # Map target string to EntityType
    etype = None
    target_lower = target_name.lower()
    if target_lower in {"company", "companies", "organization", "organizations"}:
        etype = EntityType.COMPANY
    elif target_lower in {"person", "persons", "people"}:
        etype = EntityType.PERSON
    elif target_lower in {"location", "locations", "address"}:
        etype = EntityType.ADDRESS
    
    # If we have a mapping, run specific extraction
    types = [etype] if etype else None
    
    # Run async extraction synchronously here (bridge gap)
    import asyncio
    try:
        results = asyncio.run(backend.extract(text, types))
    except Exception:
        # Fallback if loop is running
        return []

    findings = []
    for r in results:
        findings.append({
            "target": target_name,
            "value": r.value,
            "confidence": r.confidence,
            "snippet": r.context or first_snippet(text, r.value),
            "source_url": url,
            "source": "gliner",
        })
    return findings

def _extract_builtin(name: str, text: str, *, url: str, max_hits: int) -> List[Dict[str, Any]]:
    name_norm = name.strip().lower()
    
    # Try GLiNER first for complex types
    if name_norm in {"company", "companies", "person", "persons"} and _gliner_enabled():
        gliner_results = _extract_gliner(name_norm, text, url=url)
        if gliner_results:
            # Sort by confidence and limit
            gliner_results.sort(key=lambda x: x["confidence"], reverse=True)
            return gliner_results[:max_hits]

    results: List[Dict[str, Any]] = []

    if name_norm in {"company", "companies"}:
        try:
            from .entity_extractors.companies import extract_companies
        except Exception:
            return []

        for c in (extract_companies(text, max_results=max_hits) or [])[:max_hits]:
            value = c.get("name")
            if not value:
                continue
            snippet = first_snippet(text, value) or ""
            results.append(
                {
                    "target": "companies",
                    "value": value,
                    "confidence": float(c.get("confidence", 0.0) or 0.0),
                    "snippet": snippet,
                    "source_url": url,
                    "source": f"pacman_company_{c.get('source', 'unknown')}",
                }
            )
        return results

    if name_norm in {"person", "persons"}:
        try:
            from .entity_extractors.persons import extract_persons
        except Exception:
            return []

        for p in (extract_persons(text, max_results=max_hits) or [])[:max_hits]:
            value = p.get("name")
            if not value:
                continue
            snippet = first_snippet(text, value) or ""
            results.append(
                {
                    "target": "persons",
                    "value": value,
                    "confidence": float(p.get("confidence", 0.0) or 0.0),
                    "snippet": snippet,
                    "source_url": url,
                    "source": f"pacman_person_{p.get('source', 'unknown')}",
                }
            )
        return results

    if name_norm in {"fast", "identifiers", "contacts"}:
        try:
            from .entity_extractors.fast import extract_fast
        except Exception:
            return []

        fast = extract_fast(text) or {}
        # Cap total
        total = 0
        for etype, values in fast.items():
            for value in (values or [])[:max_hits]:
                snippet = first_snippet(text, value) or ""
                results.append(
                    {
                        "target": etype,
                        "value": value,
                        "confidence": 0.9,
                        "snippet": snippet,
                        "source_url": url,
                        "source": "pacman_fast",
                    }
                )
                total += 1
                if total >= max_hits:
                    return results
        return results

    return []


def _extract_regex(target: ExtractionTarget, text: str, *, url: str) -> List[Dict[str, Any]]:
    if not target.pattern:
        return []

    flags = 0
    if "i" in (target.flags or "").lower():
        flags |= re.IGNORECASE
    if "m" in (target.flags or "").lower():
        flags |= re.MULTILINE
    if "s" in (target.flags or "").lower():
        flags |= re.DOTALL

    try:
        pattern = re.compile(target.pattern, flags)
    except re.error:
        return []

    results: List[Dict[str, Any]] = []
    for match in pattern.finditer(text):
        try:
            value = match.group(int(target.group))
        except Exception:
            value = match.group(0)

        value = (value or "").strip()
        if not value:
            continue

        snippet = snippet_for_span(text, match.start(), match.end()) or ""
        results.append(
            {
                "target": target.name,
                "value": value,
                "confidence": 0.75,
                "snippet": snippet,
                "source_url": url,
                "source": "regex",
            }
        )
        if len(results) >= int(target.max_hits or 20):
            break

    return results


def _haiku_enabled() -> bool:
    # Never run paid/networked extraction inside pytest.
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    if os.getenv("PACMAN_DISABLE_HAIKU", "").strip().lower() in {"1", "true", "yes"}:
        return False
    return True


def _haiku_allowed(watcher: WatcherSpec) -> bool:
    """
    Guardrails for AI extraction:
    - If domain_count is unknown, treat as potentially large → prefer patterns.
    - If domain_count is large, skip Haiku.
    - Enforce a per-watcher call budget (best-effort, per-process).
    """
    if not _haiku_enabled():
        return False

    if watcher.domain_count is None:
        return False

    if int(watcher.domain_count) > DEFAULT_HAIKU_DOMAIN_MAX:
        return False

    used = _HAIKU_CALLS.get(watcher.watcher_id, 0)
    return used < DEFAULT_HAIKU_MAX_CALLS


def evaluate_trigger(trigger: str, text: str, url: str) -> bool:
    """
    Evaluate a trigger expression against text and metadata.
    Supports:
    - "string" or 'string': Regex match in text
    - land{code}: TLD check on URL (e.g. land{de} matches .de domains)
    - site{domain}: Domain check on URL
    - OR logic: "A OR B" matches if A or B is true
    """
    if not trigger:
        return True

    # Split by OR
    parts = [p.strip() for p in trigger.split(" OR ")]
    
    for part in parts:
        # Check for operators
        # land{code}
        land_match = re.match(r"land\{([a-z]{2})\}", part, re.IGNORECASE)
        if land_match:
            code = land_match.group(1).lower()
            # Simple TLD check
            from urllib.parse import urlparse
            try:
                domain = urlparse(url).netloc
                if domain.endswith(f".{code}") or f".{code}." in domain:
                    return True
            except Exception:
                pass
            continue

        # site{domain}
        site_match = re.match(r"site\{(.+?)\}", part, re.IGNORECASE)
        if site_match:
            target_domain = site_match.group(1).lower()
            try:
                domain = urlparse(url).netloc.lower()
                if target_domain in domain:
                    return True
            except Exception:
                pass
            continue

        # rank(topN) - STUB
        rank_match = re.match(r"rank\(top(\d+)\)", part, re.IGNORECASE)
        if rank_match:
            # We don't have rank data here yet, defaulting to False to be safe, 
            # or True if we assume high quality?
            # Let's return False effectively ignoring this condition unless ORed with others.
            continue

        # Regex/String pattern "..."
        # If wrapped in quotes, strip them. If not, treat as raw regex.
        pattern = part
        if (part.startswith('"') and part.endswith('"')) or (part.startswith("'") and part.endswith("'")):
            pattern = part[1:-1]
        
        try:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        except re.error:
            pass

    return False

def _extract_haiku(target: ExtractionTarget, watcher: WatcherSpec, text: str, *, url: str) -> List[Dict[str, Any]]:
    """
    Targeted Haiku extraction. Best-effort and safe-by-default.

    Requires ANTHROPIC_API_KEY. Returns [] on failure.
    """
    try:
        import anthropic  # type: ignore
    except Exception:
        return []

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return []

    # Check trigger pattern (pre-flight filter)
    if target.trigger:
        if not evaluate_trigger(target.trigger, text, url):
            return []

    instruction = (target.instruction or target.name or "").strip()
    if not instruction:
        return []

    model = os.getenv("PACMAN_HAIKU_MODEL", "claude-haiku-4-5-20251001").strip() or "claude-haiku-4-5-20251001"
    payload_text = text[:DEFAULT_HAIKU_TEXT_LIMIT]

    prompt = (
        "You are a forensic extractor.\n"
        "Extract the requested target(s) from the provided text.\n"
        "Rules:\n"
        "- Use ONLY the provided text.\n"
        "- Return ONLY valid JSON.\n"
        "- Return a JSON array of objects with keys: value, evidence.\n"
        "- evidence MUST be an exact quote copied verbatim from the text and MUST include the value.\n"
        "- If nothing is found, return [].\n\n"
        f"TARGET: {instruction}\n"
        f"URL: {url}\n\n"
        "TEXT:\n"
        f"{payload_text}\n"
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text if getattr(message, "content", None) else ""
    except Exception:
        return []

    raw = (raw or "").strip()
    if not raw:
        return []

    # Strip markdown fences
    if "```" in raw:
        parts = raw.split("```")
        for i in range(len(parts) - 1):
            if parts[i].strip().lower().endswith("json"):
                raw = parts[i + 1].strip()
                break
        else:
            raw = parts[1].strip() if len(parts) > 1 else raw

    # Best-effort: isolate JSON array
    start = raw.find("[")
    end = raw.rfind("]")
    raw_json = raw[start : end + 1] if start != -1 and end != -1 and end > start else raw

    try:
        items = json.loads(raw_json)
    except Exception:
        return []

    if not isinstance(items, list):
        return []

    _HAIKU_CALLS[watcher.watcher_id] = _HAIKU_CALLS.get(watcher.watcher_id, 0) + 1

    results: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        value = str(item.get("value") or "").strip()
        evidence = str(item.get("evidence") or "").strip()
        if not value:
            continue

        span_start = -1
        span_end = -1
        if evidence:
            span_start = text.find(evidence)
            if span_start != -1:
                span_end = span_start + len(evidence)

        if span_start != -1 and span_end != -1:
            snippet = snippet_for_span(text, span_start, span_end) or ""
        else:
            snippet = first_snippet(text, value) or ""

        results.append(
            {
                "target": target.name,
                "value": value,
                "confidence": float(item.get("confidence", 0.6) or 0.6),
                "snippet": snippet,
                "source_url": url,
                "source": "haiku",
            }
        )
        if len(results) >= int(target.max_hits or 20):
            break

    return results
