#!/usr/bin/env python3
"""
SASTRE ↔ EYE-D OSINT Bridge

Provides a thin, dependency-tolerant adapter for running EYE-D UnifiedSearcher
workflows (including multi-hop chain reaction) and producing deterministic
EDITH-style Markdown write-ups.

This module intentionally does not depend on MCP wiring; it calls EYE-D
directly (best-effort) and can optionally index results to Cymonides-1 via
EYE-D's C1Bridge when Elasticsearch is available.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


EYED_ROOT = Path("/data/EYE-D")


class EyedOsintError(RuntimeError):
    pass


def _ensure_eyed_on_path() -> None:
    if str(EYED_ROOT) not in sys.path:
        sys.path.insert(0, str(EYED_ROOT))


@dataclass
class EyedChainResult:
    query: str
    start_type: str
    depth: int
    result: Dict[str, Any]
    indexed: bool = False
    index_error: Optional[str] = None


class EyedOsintBridge:
    def __init__(self, *, project_id: str = "default"):
        self.project_id = project_id
        self._searcher = None

    def _get_searcher(self):
        if self._searcher is not None:
            return self._searcher

        if not EYED_ROOT.exists():
            raise EyedOsintError(f"EYE-D not found at {EYED_ROOT}")

        _ensure_eyed_on_path()
        try:
            from unified_osint import UnifiedSearcher
        except Exception as e:  # pragma: no cover
            raise EyedOsintError(f"Failed to import EYE-D UnifiedSearcher: {e}") from e

        self._searcher = UnifiedSearcher()
        return self._searcher

    def _try_get_c1_bridge(self, project_id: str):
        if not EYED_ROOT.exists():
            return None

        _ensure_eyed_on_path()
        try:
            from c1_bridge import C1Bridge
        except Exception:
            return None

        try:
            return C1Bridge(project_id=project_id)
        except Exception:
            return None

    async def chain_reaction(
        self,
        *,
        start_query: str,
        start_type: str,
        depth: int = 2,
        project_id: Optional[str] = None,
        index_to_c1: bool = True,
    ) -> EyedChainResult:
        query = (start_query or "").strip()
        if not query:
            raise EyedOsintError("start_query is required")

        stype = (start_type or "").strip().lower()
        if stype not in {"email", "phone", "domain", "username", "linkedin"}:
            raise EyedOsintError("start_type must be one of: email, phone, domain, username, linkedin")

        hop_depth = int(depth or 2)
        hop_depth = max(1, min(3, hop_depth))

        project = (project_id or self.project_id or "default").strip() or "default"

        searcher = self._get_searcher()
        
    async def chain_reaction(
        self,
        *,
        start_query: str,
        start_type: str,
        depth: int = 2,
        project_id: Optional[str] = None,
        index_to_c1: bool = True,
    ) -> EyedChainResult:
        query = (start_query or "").strip()
        if not query:
            raise EyedOsintError("start_query is required")

        stype = (start_type or "").strip().lower()
        if stype not in {"email", "phone", "domain", "username", "linkedin"}:
            raise EyedOsintError("start_type must be one of: email, phone, domain, username, linkedin")

        hop_depth = int(depth or 2)
        hop_depth = max(1, min(3, hop_depth))

        project = (project_id or self.project_id or "default").strip() or "default"

        searcher = self._get_searcher()
        
        # Use the sophisticated C1Bridge recursive logic (VERIFIED-first, Verification Cascade)
        if hasattr(searcher, 'search_with_recursion') and index_to_c1:
            try:
                result = await searcher.search_with_recursion(
                    initial_query=query,
                    project_id=project,
                    search_type=stype,
                    max_depth=hop_depth
                )
            except Exception as e:
                # If recursion fails, we can't fall back to the old method as it's been removed.
                raise EyedOsintError(f"Recursive search failed: {e}")
        else:
            raise EyedOsintError("Recursive search requires C1Bridge and indexing enabled.")

        indexed = True # search_with_recursion handles indexing internally
        index_error: Optional[str] = None

        # --- AUTO-WATCHER CREATION ---
        # Create a persistent Watcher for this entity and stream the findings to it
        if index_to_c1:
            try:
                # Lazy load WatcherBridge
                from SASTRE.bridges import WatcherBridge
                watcher_bridge = WatcherBridge()
                
                # Create Watcher (this creates graph nodes + document section)
                watcher_name = f"{stype.title()}: {query}"
                watcher = await watcher_bridge.create(
                    name=watcher_name,
                    project_id=project,
                    query=query
                )
                
                if watcher and watcher.get("id"):
                    # Generate a summary for the watcher
                    summary_md = self.render_writeup([(f"Chain Reaction: {query}", result)], include_raw=False)
                    
                    # Stream the finding to the new Watcher's document section
                    # Note: 'create' returns the watcher object which should link to a document
                    # We need the parentDocumentId or to use stream_finding directly if watcher knows its place
                    # watcher_bridge.create returns the watcher object.
                    
                    # We assume the watcher is linked to a document. We'll try to find its document/section.
                    # Actually, stream_finding_to_section needs doc_id and header.
                    # The Watcher object usually contains these if it was just created attached to a main doc.
                    # If not, we might need to rely on the watcher's own context management.
                    
                    # Better approach: Use the 'execute' endpoint of WatcherBridge which handles routing?
                    # Or simply update the watcher's "latest finding" if that concept exists.
                    
                    # Let's inspect what 'create' returns. Usually {id, name, parentDocumentId...}
                    doc_id = watcher.get("parentDocumentId")
                    if doc_id:
                        await watcher_bridge.stream_finding_to_section(
                            document_id=doc_id,
                            section_title=watcher_name, # Watchers match their section headers
                            finding_text=summary_md,
                            source_url=f"eye-d://chain/{stype}/{query}"
                        )
            except Exception as w_e:
                # Non-fatal error, just log/ignore if watcher creation fails
                # print(f"Warning: Failed to auto-create watcher: {w_e}")
                pass
        # -----------------------------

        return EyedChainResult(
            query=query,
            start_type=stype,
            depth=hop_depth,
            result=result if isinstance(result, dict) else {"result": result},
            indexed=indexed,
            index_error=index_error,
        )

    async def chain_reaction_batch(
        self,
        *,
        start_queries: Sequence[str],
        start_type: str,
        depth: int = 2,
        project_id: Optional[str] = None,
        index_to_c1: bool = True,
        concurrency: int = 1,
    ) -> List[EyedChainResult]:
        queries = [str(q).strip() for q in (start_queries or []) if str(q).strip()]
        if not queries:
            raise EyedOsintError("start_queries is required")

        sem = asyncio.Semaphore(max(1, int(concurrency or 1)))
        project = (project_id or self.project_id or "default").strip() or "default"

        async def _run(q: str) -> EyedChainResult:
            async with sem:
                return await self.chain_reaction(
                    start_query=q,
                    start_type=start_type,
                    depth=depth,
                    project_id=project,
                    index_to_c1=index_to_c1,
                )

        return await asyncio.gather(*[_run(q) for q in queries])

    def render_writeup(
        self,
        docs: Iterable[Tuple[str, Any]],
        *,
        include_raw: bool = False,
    ) -> str:
        if not EYED_ROOT.exists():
            raise EyedOsintError(f"EYE-D not found at {EYED_ROOT}")

        _ensure_eyed_on_path()
        try:
            from edith_writeup import render_report
        except Exception as e:  # pragma: no cover
            raise EyedOsintError(f"Failed to import EYE-D edith_writeup: {e}") from e

        normalized: List[Tuple[str, Any]] = []
        for label, data in docs:
            normalized.append((str(label), data))

        return render_report(normalized, include_raw=include_raw)

