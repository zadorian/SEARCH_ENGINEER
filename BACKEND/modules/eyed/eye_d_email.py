#!/usr/bin/env python3
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from entity_search import EyeDSearchHandler


class EyeDEmailEngine:
    code = 'EDE'
    name = 'EYE-D Email'

    def __init__(self, keyword: str, event_emitter=None):
        self.keyword = keyword
        self.event_emitter = event_emitter
        self.handler = EyeDSearchHandler(event_emitter=event_emitter)

    def search(self) -> List[Dict[str, Any]]:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            results = loop.run_until_complete(self.handler.search_email(self.keyword))
            web_results: List[Dict[str, Any]] = []
            for i, r in enumerate(results.get('results', []), 1):
                data = r.get('data', {})
                snippet = ' | '.join([f"{k}: {str(v)[:80]}" for k, v in list(data.items())[:8]]) if isinstance(data, dict) else str(data)[:300]
                web_results.append({
                    'url': f"https://dehashed.com/search?query={self.keyword}",
                    'title': f"Email: {self.keyword} (from {r.get('source','unknown')})",
                    'snippet': snippet,
                    'engine': self.name,
                    'source': r.get('source','unknown').upper(),
                    'rank': i
                })
            return web_results
        finally:
            loop.close()


