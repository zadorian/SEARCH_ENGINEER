from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional, Tuple
import requests


class HFUrlsEngine:
    code = "HFU"
    name = "hf_urls"

    DATASETS: List[Tuple[str, str, str]] = [
        ("nhagar/culturax_urls", "default", "url"),
        ("nhagar/c4_urls_multilingual", "default", "url"),
        ("nhagar/hplt-v1.2_urls", "default", "url"),
        ("nhagar/dolma_urls_v1.6", "default", "url"),
        # Domain-only pivots (emit homepage URLs)
        ("pkgforge-security/domains", "default", "domain"),
    ]

    API = "https://datasets-server.huggingface.co/search"

    def is_available(self) -> bool:
        return True

    def _extract_keyword(self, query: str) -> str:
        q = (query or "").strip()
        # Accept forms: site:domain, inurl:keyword, allinurl:..., or raw keyword
        # Prefer explicit domain when site: is present
        if "site:" in q:
            try:
                idx = q.index("site:") + len("site:")
                tail = q[idx:].strip()
                token = tail.split()[0]
                return token.strip('\"\'')
            except Exception:
                pass
        for prefix in ("inurl:", "allinurl:"):
            if prefix in q:
                try:
                    idx = q.index(prefix) + len(prefix)
                    # take token after prefix
                    tail = q[idx:].strip()
                    token = tail.split()[0]
                    return token.strip('\"\'')
                except Exception:
                    continue
        return q

    def _search_dataset(self, dataset: str, config: str, split: str, query: str, token: Optional[str], limit: int) -> List[Dict[str, Any]]:
        params = {
            "dataset": dataset,
            "config": config,
            "split": split,
            "query": query,
            "offset": 0,
            "length": max(1, min(limit, 50)),
        }
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            # Keep requests snappy to avoid upstream timeouts in orchestrator
            r = requests.get(self.API, params=params, headers=headers, timeout=6)
            if not r.ok:
                return []
            data = r.json()
        except Exception:
            return []
        rows = data.get("rows") or []
        out: List[Dict[str, Any]] = []
        for item in rows:
            row = (item or {}).get("row") or {}
            url = None
            homepage_url = None
            if isinstance(row, dict):
                # Prefer explicit URL-like fields
                url = row.get("url") or row.get("link") or None
                # Domain-only datasets: synthesize homepage URL variants
                domain = row.get("domain") or row.get("host") or row.get("site")
                if not url and domain:
                    d = str(domain).strip()
                    if d:
                        # default to https; callers can canonicalize
                        homepage_url = f"https://{d}"
                        url = homepage_url
            if not url:
                continue
            out.append({
                "title": f"HF URL: {url}",
                "url": url,
                "snippet": f"{dataset} hit for '{query}'",
                "engine": self.name,
                "source": dataset,
                "metadata": {"dataset": dataset, "query": query, "homepage": bool(homepage_url)},
            })
        return out

    def search(self, query: str, num_results: int = 25) -> List[Dict[str, Any]]:
        token = os.getenv("HF_TOKEN")
        kw = self._extract_keyword(query)
        results: List[Dict[str, Any]] = []
        per_ds = max(1, min(num_results, 25))
        # Prefer domain-only dataset when kw looks like a domain (contains dot)
        datasets: List[Tuple[str, str, str]]
        if "." in kw:
            datasets = [("pkgforge-security/domains", "default", "domain")]
        else:
            # Light sweep: try a small subset first for speed
            datasets = [
                ("nhagar/c4_urls_multilingual", "default", "url"),
                ("nhagar/culturax_urls", "default", "url"),
            ]
        for ds, cfg, col in datasets:
            hits = self._search_dataset(ds, cfg, "train", kw, token, per_ds)
            results.extend(hits)
            if len(results) >= num_results:
                break
            time.sleep(0.05)
        return results[:num_results]
__all__ = ['HFUrlsEngine']


