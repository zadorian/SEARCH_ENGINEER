#!/usr/bin/env python3
"""OpenLibrary API engine (books search).

API: https://openlibrary.org/dev/docs/api/search
"""

from __future__ import annotations

import requests
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode


class OpenLibraryAPIEngine:
    code = "OL"
    name = "openlibrary"

    def is_available(self) -> bool:
        # Public API
        return True

    def search(
        self,
        query: str,
        *,
        max_results: int = 20,
        num_results: Optional[int] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        limit = num_results or max_results
        if not query:
            return []

        try:
            params = {"q": query, "limit": min(limit, 50)}
            url = f"https://openlibrary.org/search.json?{urlencode(params)}"
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json() or {}
        except Exception:
            return []

        results: List[Dict[str, Any]] = []
        for doc in (data.get("docs") or [])[:limit]:
            key = doc.get("key") or ""
            url = f"https://openlibrary.org{key}" if key else None
            if not url:
                continue
            title = doc.get("title") or ""
            authors = ", ".join(doc.get("author_name") or [])
            year = doc.get("first_publish_year")
            snippet_parts = [p for p in [authors, str(year) if year else None] if p]
            snippet = " | ".join(snippet_parts)
            results.append({
                "title": title,
                "url": url,
                "snippet": snippet,
                "engine": self.name,
                "engine_code": self.code,
                "source": "openlibrary",
                "raw": doc,
            })
        return results


__all__ = ["OpenLibraryAPIEngine"]


