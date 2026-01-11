#!/usr/bin/env python3
"""
US Unified CLI - State-Aware Public Records Router
===================================================

Provides per-state operators that mirror the UK pattern:
    usca: <query>       - California unified search
    cusca: <company>    - California company search (state registry + OpenCorporates)
    pusca: <person>     - California person search (state regulatory/lit/asset sources)
    regusca: <query>    - California regulatory search
    litusca: <query>    - California litigation search
    assusca: <query>    - California asset/property search
    newsusca: <query>   - California news sources

Federal (US-wide) operators:
    us: <query>         - US unified search
    cus: <company>      - US company search
    pus: <person>       - US person search
    regus: <query>      - US regulatory search
    litus: <query>      - US litigation search
    assus: <query>      - US asset/property search
    newsus: <query>     - US news sources
"""

import argparse
import asyncio
import logging
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from .us_state_data import US_STATES, US_STATE_CODES
from .us_sources import get_state_sources, build_source_link
from .cr import USCompanyRegistry
from .reg import USRegulatory
from .lit import USLitigation
from .ass import USAssets

logger = logging.getLogger("us_unified_cli")

PROJECT_ROOT = Path(__file__).resolve().parents[4]
BACKEND_PATH = PROJECT_ROOT / "BACKEND" / "modules"
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

US_OPERATOR_PATTERN = re.compile(
    r"^(?P<prefix>us|cus|pus|regus|litus|assus|crus|newsus)(?P<state>[a-z]{2})?:\s*(?P<query>.*)$",
    re.IGNORECASE,
)


# =============================================================================
# OPERATOR DEFINITIONS
# =============================================================================

def build_us_operators() -> Dict[str, Dict[str, Any]]:
    operators: Dict[str, Dict[str, Any]] = {
        "us:": {
            "name": "US Unified Search",
            "entity_type": "all",
            "description": "Run US-wide searches across state sources",
        },
        "cus:": {
            "name": "US Company Search",
            "entity_type": "company",
            "description": "Search US company registries (federal + state sources)",
        },
        "pus:": {
            "name": "US Person Search",
            "entity_type": "person",
            "description": "Search US person-related sources (regulatory, litigation, assets)",
        },
        "regus:": {
            "name": "US Regulatory Search",
            "entity_type": "company",
            "description": "Search US regulatory sources",
        },
        "litus:": {
            "name": "US Litigation Search",
            "entity_type": "case",
            "description": "Search US litigation sources",
        },
        "assus:": {
            "name": "US Assets Search",
            "entity_type": "asset",
            "description": "Search US asset/property sources",
        },
        "newsus:": {
            "name": "US News Search",
            "entity_type": "article",
            "description": "Search US news sources",
        },
    }

    for code, name in sorted(US_STATES.items()):
        suffix = code.lower()
        operators[f"us{suffix}:"] = {
            "name": f"{name} Unified Search",
            "entity_type": "all",
            "description": f"Run all {name} searches (registry, regulatory, litigation, assets, news)",
        }
        operators[f"cus{suffix}:"] = {
            "name": f"{name} Company Search",
            "entity_type": "company",
            "description": f"Search {name} corporate registry sources",
        }
        operators[f"pus{suffix}:"] = {
            "name": f"{name} Person Search",
            "entity_type": "person",
            "description": f"Search {name} person-related sources",
        }
        operators[f"regus{suffix}:"] = {
            "name": f"{name} Regulatory Search",
            "entity_type": "company",
            "description": f"Search {name} regulatory sources",
        }
        operators[f"litus{suffix}:"] = {
            "name": f"{name} Litigation Search",
            "entity_type": "case",
            "description": f"Search {name} litigation sources",
        }
        operators[f"assus{suffix}:"] = {
            "name": f"{name} Assets Search",
            "entity_type": "asset",
            "description": f"Search {name} asset/property sources",
        }
        operators[f"newsus{suffix}:"] = {
            "name": f"{name} News Search",
            "entity_type": "article",
            "description": f"Search {name} news sources",
        }
        operators[f"crus{suffix}:"] = {
            "name": f"{name} Corporate Registry",
            "entity_type": "company",
            "description": f"Direct {name} corporate registry search",
        }

    return operators


US_OPERATORS = build_us_operators()


def get_us_operators() -> Dict[str, Dict[str, Any]]:
    return US_OPERATORS


def has_us_operator(query: str) -> bool:
    return bool(US_OPERATOR_PATTERN.match(query.strip().lower()))


def parse_us_query(query: str) -> Tuple[str, str, str, str, Optional[str]]:
    match = US_OPERATOR_PATTERN.match(query.strip())
    if not match:
        return "us:", query.strip(), "all", "all", None

    prefix = match.group("prefix").lower()
    raw_state = match.group("state")
    state_code = raw_state.upper() if raw_state else None
    value = match.group("query").strip()

    if state_code and state_code not in US_STATE_CODES:
        raise ValueError(f"Unsupported US state code: {state_code}")

    if prefix == "us":
        return f"us{raw_state or ''}:", value, "all", "all", state_code
    if prefix in {"cus", "crus"}:
        return f"{prefix}{raw_state or ''}:", value, "company", "cr", state_code
    if prefix == "pus":
        return f"pus{raw_state or ''}:", value, "person", "person", state_code
    if prefix == "regus":
        return f"regus{raw_state or ''}:", value, "company", "reg", state_code
    if prefix == "litus":
        return f"litus{raw_state or ''}:", value, "case", "lit", state_code
    if prefix == "assus":
        return f"assus{raw_state or ''}:", value, "asset", "ass", state_code
    if prefix == "newsus":
        return f"newsus{raw_state or ''}:", value, "article", "news", state_code

    return f"{prefix}{raw_state or ''}:", value, "all", "all", state_code


# =============================================================================
# RESULT DATACLASS
# =============================================================================

@dataclass
class USSearchResult:
    operator: str
    query: str
    entity_type: str
    jurisdiction: str = "US"
    state: Optional[str] = None

    results: Dict[str, Any] = field(default_factory=dict)

    companies: List[Dict] = field(default_factory=list)
    persons: List[Dict] = field(default_factory=list)

    registry_links: List[Dict] = field(default_factory=list)
    regulatory_links: List[Dict] = field(default_factory=list)
    litigation_links: List[Dict] = field(default_factory=list)
    asset_links: List[Dict] = field(default_factory=list)
    news_links: List[Dict] = field(default_factory=list)

    sources_queried: List[str] = field(default_factory=list)
    sources_succeeded: List[str] = field(default_factory=list)
    sources_failed: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    execution_time_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, [], {}, "")}


# =============================================================================
# US UNIFIED CLI
# =============================================================================

class USCLI:
    """Unified US public records CLI (state-aware)."""

    def __init__(self) -> None:
        self._cr = USCompanyRegistry()
        self._reg = USRegulatory()
        self._lit = USLitigation()
        self._ass = USAssets()

    async def execute(self, query: str) -> USSearchResult:
        operator, value, entity_type, section, state_code = parse_us_query(query)
        jurisdiction = f"US_{state_code}" if state_code else "US"

        result = USSearchResult(
            operator=operator,
            query=value,
            entity_type=entity_type,
            jurisdiction=jurisdiction,
            state=state_code,
        )

        start = time.time()

        try:
            if section in {"all", "cr"}:
                cr_result = await self._cr.search_company(value, state_code)
                result.results["corporate_registry"] = cr_result
                result.registry_links = cr_result.get("links", [])
                result.companies = cr_result.get("companies", [])

            if section in {"all", "person"}:
                reg_result = await self._reg.search(value, state_code)
                lit_result = await self._lit.search(value, state_code)
                ass_result = await self._ass.search(value, state_code)
                result.results["regulatory"] = reg_result
                result.results["litigation"] = lit_result
                result.results["assets"] = ass_result
                result.regulatory_links = reg_result.get("links", [])
                result.litigation_links = lit_result.get("links", [])
                result.asset_links = ass_result.get("links", [])

            if section == "reg":
                reg_result = await self._reg.search(value, state_code)
                result.results["regulatory"] = reg_result
                result.regulatory_links = reg_result.get("links", [])

            if section == "lit":
                lit_result = await self._lit.search(value, state_code)
                result.results["litigation"] = lit_result
                result.litigation_links = lit_result.get("links", [])

            if section == "ass":
                ass_result = await self._ass.search(value, state_code)
                result.results["assets"] = ass_result
                result.asset_links = ass_result.get("links", [])

            if section in {"all", "news"}:
                sources = get_state_sources(state_code, section="news")
                result.news_links = [build_source_link(s, value, jurisdiction, "news") for s in sources]
                result.results["news"] = {"links": result.news_links}

        except Exception as exc:
            result.errors.append(str(exc))

        all_links = (
            result.registry_links
            + result.regulatory_links
            + result.litigation_links
            + result.asset_links
            + result.news_links
        )
        result.sources_queried = [link.get("source_id") for link in all_links if link.get("source_id")]
        result.execution_time_ms = int((time.time() - start) * 1000)
        return result


# =============================================================================
# CLI ENTRYPOINT
# =============================================================================

async def execute_us_query(query: str) -> USSearchResult:
    cli = USCLI()
    return await cli.execute(query)


def main() -> None:
    parser = argparse.ArgumentParser(description="US Unified CLI (state-aware)")
    parser.add_argument("query", help="Query with US operator")
    args = parser.parse_args()

    result = asyncio.run(execute_us_query(args.query))
    print(result.to_dict())


if __name__ == "__main__":
    main()
