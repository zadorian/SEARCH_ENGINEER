from __future__ import annotations

from typing import Any, Dict, List

from ..base_searcher import BaseSearcher, SearchResult


class GASearcher(BaseSearcher):
    async def search(self, params: Dict[str, Any]) -> SearchResult:
        domain = (params.get('query') or '').strip().lower()
    items: List[Any] = []
    sources_used: List[str] = []
    errors: List[str] = []

        # Try to use the in-repo GA history engine (Wayback-based)
        try:
            import sys
            from pathlib import Path
            # Add Related tools path (handles spaces in directory names)
            sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'iii. OBJECT' / 'h. EXPANDING ' / 'LINKS' / 'Related'))
            from ga_search import run_ga_search  # type: ignore
            try:
                result = await run_ga_search(domain)
            except TypeError:
                # If signature differs, fallback to engine class
                from ga_search import GASearchEngine  # type: ignore
                engine = GASearchEngine()
                result = await engine.search(domain)

            if isinstance(result, dict):
                # Expose a compact items list (timeline entries) and include a summary payload
                timeline = result.get('timeline') or []
                items = timeline if isinstance(timeline, list) else []
                # Include a rolled-up summary item for convenience
                summary = {
                    'domain': result.get('domain'),
                    'current_codes': result.get('current_codes', {}),
                    'historical_codes': result.get('historical_codes', {}),
                    'historical_counts': {
                        'UA': len((result.get('historical_codes') or {}).get('UA', {})),
                        'GA': len((result.get('historical_codes') or {}).get('GA', {})),
                        'GTM': len((result.get('historical_codes') or {}).get('GTM', {})),
                    },
                    'snapshots_analyzed': len(items),
                }
                items.insert(0, {'type': 'ga_summary', **summary})
                sources_used.extend(['wayback', 'ga_history'])
        except Exception as e:
            # Keep resilient: report error for UI and telemetry
            errors.append(f"ga_history_unavailable: {e}")

        return SearchResult(
            type='ga',
            items=items,
            sources_used=sources_used,
            errors=errors,
            panel={'kind': 'domain', 'value': domain},
        )
