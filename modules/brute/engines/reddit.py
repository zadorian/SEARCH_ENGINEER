from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import quote_plus


class RedditNavEngine:
    code = "RD"
    name = "reddit_nav"

    def is_available(self) -> bool:
        return True

    def search(self, query: str, num_results: int = 1) -> List[Dict[str, Any]]:
        q = (query or "").strip()
        url = f"https://www.reddit.com/search/?q={quote_plus(q)}"
        title = f"Reddit search: {q}" if q else "Reddit search"
        return [{
            "title": title,
            "url": url,
            "engine": self.name,
            "source": "reddit",
            "snippet": "Navigate to Reddit search results",
        }]
__all__ = ['RedditNavEngine']


