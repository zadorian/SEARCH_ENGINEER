#!/usr/bin/env python3
"""PublicWWW API engine using CSV export.

Note: Requires PUBLICWWW_API_KEY in environment.
"""

from __future__ import annotations

import os
import requests
from typing import Any, Dict, List, Optional
from urllib.parse import quote


def _key() -> str:
    return os.getenv("PUBLICWWW_API_KEY", "").strip()


class PublicWWWAPIEngine:
    code = "PW"
    name = "publicwww"

    def is_available(self) -> bool:
        return bool(_key())

    def search(
        self,
        query: str,
        *,
        max_results: int = 100,
        num_results: Optional[int] = None,
        **_: Any,
    ) -> List[Dict[str, Any]]:
        api_key = _key()
        if not api_key:
            return []

        limit = num_results or max_results
        if not query:
            return []

        # Enforce exact phrase (API matches best with quotes)
        q = query
        if not (q.startswith('"') and q.endswith('"')):
            q = f'"{q}"'

        url = f"https://publicwww.com/websites/{quote(q, safe='')}" \
              f"/?export=csv&key={api_key}"

        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            lines = (resp.text or "").strip().splitlines()
        except Exception:
            return []

        results: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for raw in lines[:limit]:
            entry = (raw or "").split(";")[0].strip()
            if not entry:
                continue
            if not entry.startswith(("http://", "https://")):
                entry = f"http://{entry}"
            if entry in seen:
                continue
            seen.add(entry)
            results.append({
                "title": entry,
                "url": entry,
                "snippet": "Found in source code",
                "engine": self.name,
                "engine_code": self.code,
                "source": "publicwww",
                "raw": {"entry": raw},
            })

        return results[:limit]


__all__ = ["PublicWWWAPIEngine"]


