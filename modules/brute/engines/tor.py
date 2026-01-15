from __future__ import annotations

import asyncio
import importlib.util
import logging
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote

try:
    from brute.base_searcher import BaseSearcher, SearchResult
except ImportError:
    from ..base_searcher import BaseSearcher, SearchResult

logger = logging.getLogger(__name__)


def _load_tor_module():
    module_path = Path(__file__).resolve().parents[2] / "iv. LOCATION" / "a. KNOWN_UNKNOWN" / "SOURCE_CATEGORY" / "TOR" / "tor.py"
    if not module_path.exists():
        return None
    spec = importlib.util.spec_from_file_location("tor_category", str(module_path))
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover - best effort shim
        logger.debug("Unable to load tor search module: %s", exc)
        return None
    return module


_TOR_MODULE = _load_tor_module()
_TOR_SEARCH_FN = getattr(_TOR_MODULE, "search", None) if _TOR_MODULE else None


def _tor_search_sync(query: str, max_results: int = 30) -> List[Dict[str, Any]]:
    if not callable(_TOR_SEARCH_FN):
        return []
    try:
        return _TOR_SEARCH_FN(query, max_results=max_results)  # type: ignore[call-arg]
    except Exception as exc:  # pragma: no cover - guard network errors
        logger.debug("Tor search aggregator failed: %s", exc)
        return []


TOR_PORTAL_CATALOG = [
    {
        "title": "Ahmia (clearnet gateway)",
        "source": "portal_ahmia",
        "requires_tor": False,
        "url_builder": lambda q: f"https://ahmia.fi/search/?q={quote(q)}" if q else "https://ahmia.fi/",
        "snippet": "Search Tor hidden services from the Ahmia index without Tor. Filters illegal content by design.",
    },
    {
        "title": "Ahmia (Tor onion)",
        "source": "portal_ahmia_onion",
        "requires_tor": True,
        "url_builder": lambda q: (
            f"http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion/search/?q={quote(q)}"
            if q
            else "http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion/"
        ),
        "snippet": "Native Ahmia access via Tor Browser for best coverage of hidden services.",
    },
    {
        "title": "DuckDuckGo Onion", 
        "source": "portal_ddg_onion",
        "requires_tor": True,
        "url_builder": lambda q: (
            f"https://duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion/html?q={quote(q)}"
            if q
            else "https://duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion/"
        ),
        "snippet": "Privacy-preserving searches with Tor Browser using DuckDuckGo's hidden service.",
    },
    {
        "title": "Torch (Tor search engine)",
        "source": "portal_torch",
        "requires_tor": True,
        "url_builder": lambda q: (
            f"http://torchdeedp3i2jigzjdmfpn5ttjhthh5wbmda2rr3jvqjg5p77c54dqd.onion/?q={quote(q)}"
            if q
            else "http://torchdeedp3i2jigzjdmfpn5ttjhthh5wbmda2rr3jvqjg5p77c54dqd.onion/"
        ),
        "snippet": "One of the oldest Tor indexes. Use within Tor Browser for best results.",
    },
    {
        "title": "Haystack (research-focused)",
        "source": "portal_haystack",
        "requires_tor": True,
        "url_builder": lambda q: (
            f"http://haystak5njsmn2hqkewecpaxetahtwhsbsa64jom2k22z5afxhnpxfid.onion/?q={quote(q)}"
            if q
            else "http://haystak5njsmn2hqkewecpaxetahtwhsbsa64jom2k22z5afxhnpxfid.onion/"
        ),
        "snippet": "Large archival index (3.5B+ pages). Ideal for investigative and historical research.",
    },
    {
        "title": "Not Evil", 
        "source": "portal_notevil",
        "requires_tor": True,
        "url_builder": lambda q: (
            f"http://hss3uro2hsxfogfq.onion/?q={quote(q)}" if q else "http://hss3uro2hsxfogfq.onion/"
        ),
        "snippet": "Community-driven Tor search engine popular with security researchers.",
    },
    {
        "title": "OnionLand Search (clearnet mirror)",
        "source": "portal_onionland",
        "requires_tor": False,
        "url_builder": lambda q: (
            f"https://onionlandsearchengine.com/search?q={quote(q)}" if q else "https://onionlandsearchengine.com/"
        ),
        "snippet": "Clearnet gateway for quickly previewing hidden services before switching to Tor.",
    },
    {
        "title": "YaCy local peer (Tor network)",
        "source": "portal_yacy_local",
        "requires_tor": False,
        "url_builder": lambda q: (
            f"http://localhost:8090/yacysearch.html?contentdom=all&query={quote(q)}" if q else "http://localhost:8090/yacysearch.html"
        ),
        "snippet": "Query your own YaCy node. Join the Tor peer network via yacy.conf to crawl hidden services collaboratively.",
    },
]


class TorSearcher(BaseSearcher):
    async def search(self, params: Dict[str, Any]) -> SearchResult:
        query = (params.get('query') or params.get('original') or '').strip()
        if query.lower().startswith('tor:'):
            query = query.split(':', 1)[1].strip()

        items: List[Dict[str, Any]] = []

        # Static portals (clearnet + onion) for quick pivoting
        for portal in TOR_PORTAL_CATALOG:
            url = portal["url_builder"](query)
            entry = {
                "title": portal["title"],
                "url": url,
                "snippet": portal["snippet"],
                "source": portal["source"],
            }
            if portal.get("requires_tor"):
                entry["requires_tor"] = True
            items.append(entry)

        # Aggregated recall via dispatcher-backed Tor search (GO/BI/.../YC)
        aggregated: List[Dict[str, Any]] = []
        if query:
            aggregated = await asyncio.to_thread(_tor_search_sync, query, params.get("max_results", 30))

        if aggregated:
            items.extend(aggregated)

        seen = set()
        unique_items: List[Dict[str, Any]] = []
        for item in items:
            key = str(item.get("url") or "").strip().lower()
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            unique_items.append(item)
        items = unique_items

        sources_used = [item.get("source") or item.get("engine_code") or "tor_portal" for item in items]
        sources_used = list(dict.fromkeys(str(src) for src in sources_used if src))

        panel = {}
        if not aggregated:
            panel["notice"] = (
                "Direct Tor search portals are listed first. Configure a local YaCy node or run brute search to enrich results."
            )

        return SearchResult(type='site', items=items, sources_used=sources_used, panel=panel)
