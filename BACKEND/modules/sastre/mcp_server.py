#!/usr/bin/env python3
"""
SASTRE MCP Server - Full Operator Syntax Access

Claude writes operator syntax → SASTRE executes against all backends.

TOOLS:
    set_project     Set project context for all operations
    detect_context  Auto-detect genre/jurisdiction/entity_type from query
    execute         Execute ANY operator syntax (routes to appropriate backend)
    run             Execute full investigation loop (ThinOrchestrator + agents)

SYNTAX (exposed via resources/skills):
    Chain Operators:    chain: due_diligence c: Acme Corp :US
    IO Prefixes:        p: John Smith, c: Acme Corp :US, e: email@test.com
    Registry Operators: csr:, chr:, cuk:, cde: (Torpedo profiles)
    Link Analysis:      bl? :!domain.com, ol? :!domain.com
    Entity Extraction:  ent? :!domain.com, p? c? e? :!domain.com
    Historical:         ent? :2022! !domain.com
    Filetype:           pdf! :!domain.com, doc!, xls!
    Grid:               ent? :!#nodename, =? :!#node1 #node2
    Exact Phrase:       "John Smith" (40+ engines via BruteSearch)
    TLD Filters:        de!, uk!, news!, gov!

Usage:
    python -m SASTRE.mcp_server

Configure in Claude Desktop:
    {
        "sastre": {
            "command": "python3",
            "args": ["-m", "SASTRE.mcp_server"],
            "env": {
                "PYTHONPATH": "/path/to/BACKEND/modules"
            }
        }
    }
"""

import asyncio
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("sastre-mcp")

# Import MCP SDK
try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent, Resource, ResourceContents
    import mcp.server.stdio
except ImportError:
    logger.error("MCP SDK not installed. Run: pip install mcp")
    sys.exit(1)

# Add SASTRE module path
SASTRE_DIR = Path(__file__).parent
BACKEND_PATH = SASTRE_DIR.parent
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

# Import template loader for context detection
from .template_loader import (
    get_template_context,
    compose_report_template,
    get_writing_style,
    is_template_genre,
    COUNTRY_CODE_MAP,
    TEMPLATE_GENRES,
)

# Import WatcherBridge for direct watcher creation
from modules.sastre.bridges import WatcherBridge

# Import the unified executor for operator syntax routing (from SYNTAX module)
from modules.syntax.executor import UnifiedExecutor, execute as executor_execute

# Import PROJECT module for project management
sys.path.insert(0, "/data/CLASSES")
try:
    from NARRATIVE.PROJECT import (
        create_project, delete_project, reset_project,
        get_project, get_active_project, set_active_project,
        list_projects, get_node_count, ensure_default_project,
        get_project_index, list_project_indices,
    )
    PROJECT_AVAILABLE = True
except ImportError as e:
    logger.warning(f"PROJECT module not available: {e}")
    PROJECT_AVAILABLE = False

# Load operator registry (single source of truth)
OPERATOR_REGISTRY_PATH = SASTRE_DIR / "operators.json"
SYNTAX_REFERENCE_PATH = SASTRE_DIR / "docs" / "SYNTAX_REFERENCE.md"
_SYNTAX_REFERENCE_CACHE = None
_OPERATOR_REGISTRY_CACHE = None


def load_operator_registry() -> dict:
    """Load the operator registry JSON (single source of truth)."""
    global _OPERATOR_REGISTRY_CACHE
    if _OPERATOR_REGISTRY_CACHE is None:
        if OPERATOR_REGISTRY_PATH.exists():
            with open(OPERATOR_REGISTRY_PATH) as f:
                _OPERATOR_REGISTRY_CACHE = json.load(f)
        else:
            logger.warning(f"Operator registry not found at {OPERATOR_REGISTRY_PATH}")
            _OPERATOR_REGISTRY_CACHE = {"operators": [], "categories": {}}
    return _OPERATOR_REGISTRY_CACHE


def generate_syntax_reference_from_registry() -> str:
    """Generate syntax reference markdown from the operator registry."""
    registry = load_operator_registry()
    operators = registry.get("operators", [])
    categories = registry.get("categories", {})

    lines = ["# SASTRE Operator Syntax Reference", ""]
    lines.append("*Generated from operators.json - Single Source of Truth*")
    lines.append("")

    # Group operators by category
    by_category = {}
    for op in operators:
        cat = op.get("category", "other")
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(op)

    # Generate sections for each category
    for cat, cat_desc in categories.items():
        if cat not in by_category:
            continue

        ops = by_category[cat]
        lines.append(f"## {cat.replace('_', ' ').title()}")
        lines.append(f"*{cat_desc}*")
        lines.append("")
        lines.append("| Syntax | Description | Example |")
        lines.append("|--------|-------------|---------|")

        for op in ops:
            syntax = op.get("syntax", "")
            name = op.get("name", "")
            desc = op.get("description", "")
            examples = op.get("examples", [])
            example_str = examples[0]["query"] if examples else ""
            lines.append(f"| `{syntax}` | {desc[:60]}{'...' if len(desc) > 60 else ''} | `{example_str}` |")

        lines.append("")

    # Add routing summary
    lines.append("## Routing Summary")
    lines.append("```")
    lines.append("execute(query)")
    lines.append("    ├── x => y => z ──► Chain pipe (sequential operators)")
    lines.append("    ├── chain: ───────► IOPlanner (multi-step investigations)")
    lines.append("    ├── cuk: chr: ────► Torpedo (Registry profiles)")
    lines.append("    ├── p: c: e: ─────► IOExecutor (Entity investigation)")
    lines.append("    ├── :2022! :<- ───► Linklater (Historical/Archive)")
    lines.append("    ├── bl? ol? ent? ─► QueryExecutor (Link/Entity extraction)")
    lines.append("    └── \"phrase\" ─────► BruteSearch (40+ engines)")
    lines.append("```")

    return "\n".join(lines)


def get_syntax_reference() -> str:
    """Load the full operator syntax reference.

    Priority:
    1. Generate from operators.json (single source of truth)
    2. Fall back to SYNTAX_REFERENCE.md if it exists
    3. Fall back to embedded reference as last resort
    """
    global _SYNTAX_REFERENCE_CACHE
    if _SYNTAX_REFERENCE_CACHE is None:
        # Try to generate from registry first (preferred)
        if OPERATOR_REGISTRY_PATH.exists():
            _SYNTAX_REFERENCE_CACHE = generate_syntax_reference_from_registry()
            logger.info("Generated syntax reference from operators.json")
        elif SYNTAX_REFERENCE_PATH.exists():
            with open(SYNTAX_REFERENCE_PATH) as f:
                _SYNTAX_REFERENCE_CACHE = f.read()
            logger.info("Loaded syntax reference from SYNTAX_REFERENCE.md")
        else:
            _SYNTAX_REFERENCE_CACHE = _EMBEDDED_SYNTAX_REFERENCE
            logger.warning("Using embedded syntax reference (no registry found)")
    return _SYNTAX_REFERENCE_CACHE


# Embedded fallback syntax reference (in case file not found)
_EMBEDDED_SYNTAX_REFERENCE = """
# SASTRE Operator Syntax Reference

## Chain Operator (=>)
Chain pipes output from one operator to the next. Just regular operators chained.

| Syntax | Description |
|--------|-------------|
| `p: John Smith => c?` | Person search → extract companies from results |
| `bl? :!example.com => p?` | Backlinks → extract persons |
| `c: Acme Corp => ent?` | Company search → extract all entities |

**IF/THEN (conditional):** `IF {condition} THEN {operator}` - runs operator only if condition met.

## Chain Presets (Multi-Step Investigations)
| Syntax | Description |
|--------|-------------|
| `chain: due_diligence c: Acme Corp :US` | Full Due Diligence Report |
| `chain: ubo c: Siemens AG :DE` | Ultimate Beneficial Owners |
| `chain: officers c: Tesco PLC :UK` | Officers + Sanctions screening |
| `chain: pep p: John Smith` | Politically Exposed Person check |

## IO Prefixes (Entity Investigation)
| Prefix | Entity Type | Example |
|--------|-------------|---------|
| `p:` | Person | `p: John Smith` |
| `c:` | Company | `c: Acme Corp :US` |
| `e:` | Email | `e: john@example.com` |
| `d:` / `dom:` | Domain | `d: example.com` |
| `t:` | Phone | `t: +1-555-0123` |

## Jurisdiction-Qualified Prefixes
| Prefix | Entity + Jurisdiction | Example |
|--------|----------------------|---------|
| `cuk:` | Company UK | `cuk: Tesco PLC` |
| `puk:` | Person UK | `puk: John Smith` |
| `reguk:` | Regulatory UK | `reguk: FCA` |
| `lituk:` | Litigation UK | `lituk: Acme Corp` |
| `chr:` | Company Croatia | `chr: Podravka` |
| `chu:` | Company Hungary | `chu: OTP Bank` |
| `cde:` / `pde:` | Company/Person Germany | `cde: Siemens AG` |
| `cno:` / `pno:` | Company/Person Norway | `cno: Equinor` |
| `cfi:` / `pfi:` | Company/Person Finland | `cfi: Nokia` |
| `cch:` | Company Switzerland | `cch: Nestlé` |
| `cie:` | Company Ireland | `cie: Ryanair` |
| `ccz:` | Company Czech | `ccz: Skoda` |
| `cbe:` | Company Belgium | `cbe: AB InBev` |
| `lei:` | GLEIF LEI Lookup | `lei: 5493001KJTIIGC8Y1R12` |

## Link Analysis Operators (LINKLATER)
| Operator | Returns | Example |
|----------|---------|---------|
| `bl?` | Backlink pages | `bl? :!domain.com` |
| `?bl` | Backlink domains (fast) | `?bl :!domain.com` |
| `ol?` | Outlink pages | `ol? :!domain.com` |
| `?ol` | Outlink domains (fast) | `?ol :!domain.com` |
| `?rl` | Related/co-cited domains | `?rl :!domain.com` |
| `?ipl` | IP-linked domains | `?ipl :!domain.com` |
| `?owl` | Ownership-linked domains (WHOIS) | `?owl :!domain.com` |

## Entity Extraction Operators
| Operator | Extracts | Example |
|----------|----------|---------|
| `ent?` | All entities | `ent? :!company.com` |
| `p?` | Persons only | `p? :!company.com` |
| `c?` | Companies only | `c? :!company.com` |
| `e?` | Emails only | `e? :!company.com` |
| `t?` | Phone numbers | `t? :!company.com` |
| `a?` | Addresses | `a? :!company.com` |
| `u?` | Usernames | `u? :!company.com` |

## Filetype Discovery Operators
| Operator | Finds | Example |
|----------|-------|---------|
| `pdf!` | PDF files | `pdf! :!sebgroup.com` |
| `doc!` | All documents (pdf, doc, xls, ppt) | `doc! :!company.com` |
| `word!` | Word documents | `word! :!company.com` |
| `xls!` | Excel spreadsheets | `xls! :!company.com` |
| `ppt!` | PowerPoint | `ppt! :!company.com` |
| `file!` | All file types | `file! :!domain.com` |

## Historical/Archive Operators
| Modifier | Meaning | Example |
|----------|---------|---------|
| `2024!` | Single year | `ent? :2024! !domain.com` |
| `2020-2024!` | Year range | `ent? :2020-2024! !domain.com` |
| `<-2015!` | From now back to 2015 | `bl? :<-2015! !domain.com` |
| `<-!` | All historical archives | `ent? :<-! !domain.com` |
| `15.03.2019!` | Specific day (European) | `15.03.2019! :?domain.com` |
| `03.2019!` | Specific month | `03.2019! :?domain.com` |

## Keyword Search Operators
| Syntax | Description |
|--------|-------------|
| `keyword :?domain.com` | Live domain search |
| `keyword :domain.com/page?` | Live page search |
| `keyword :<-domain.com` | Archive search (backwards) |
| `keyword :->domain.com` | Archive search (forwards) |
| `keyword :-><-domain.com` | Bidirectional archive |

## Navigation Operators
| Syntax | Description |
|--------|-------------|
| `?domain.com` | Discover all URLs on domain |
| `domain.com/page/path?` | Scrape specific page |

## Tor/Onion Context
| Modifier | Meaning | Example |
|----------|---------|---------|
| `:tor` | Search via Tor engines | `"bitcoin" :tor` |
| `:onion` | Alias for :tor | `"marketplace" :onion` |

## Macro Operators (io_cli.py)
| Operator | Description | Example |
|----------|-------------|---------|
| `cdom?` | Find company website/domain | `cdom? Acme Corp` |
| `age?` | Find person age/DOB | `age? John Smith` |
| `alldom?` | Full domain analysis | `alldom? example.com` |
| `crel?` | Find related companies | `crel? Acme Corp` |
| `rep?` | Reputation analytics | `rep? example.com` |

## Matrix Exploration (io_cli.py)
| Pattern | Question | Example |
|---------|----------|---------|
| `TYPE=>[?]` | What outputs from this input? | `c=>[?]` |
| `[?]=>TYPE` | What produces this output? | `[?]=>e` |
| `TYPE=>TYPE` | Route between types | `c=>officers` |

## Domain Intelligence
| Operator | Description | Example |
|----------|-------------|---------|
| `whois:` | WHOIS registration | `whois:example.com` |
| `dns:` | DNS records | `dns:example.com` |
| `subdomains:` | Subdomain discovery | `subdomains:example.com` |
| `tech:` | Technology stack | `tech:example.com` |
| `similar?` | Similar pages (Exa) | `similar? :!domain.com` |
| `ga?` | Google Analytics detection | `ga? :!domain.com` |

## Corporate Intelligence
| Operator | Description | Example |
|----------|-------------|---------|
| `company:` | Company registry search | `company:company_name` |
| `officer:` | Corporate officer search | `officer:person_name` |
| `corpus:` | Deep scrape for corpus | `corpus:example.com` |

## Definitional Shorthands
| Code | Description | Example |
|------|-------------|---------|
| `[cde]` | German company patterns | `[cde] automotive` |
| `[cuk]` | UK company patterns | `[cuk] finance` |
| `[cus]` | US company patterns | `[cus] tech` |
| `[pde]` | German person patterns | `[pde] "board member"` |
| `[puk]` | British person patterns | `[puk] finance` |
| `[lde]` / `[luk]` / `[lus]` | Location patterns | `[lus] "tech startup"` |
| `[ogo]` | Government org | `[ogo] regulation` |
| `[ong]` | NGO/Non-profit | `[ong] climate` |

## Single Engine Operators
| Code | Engine |
|------|--------|
| `GO:` / `google:` | Google |
| `BI:` / `bing:` | Bing |
| `BR:` / `brave:` | Brave |
| `DD:` / `duckduckgo:` | DuckDuckGo |
| `YA:` / `yandex:` | Yandex |
| `FC:` / `firecrawl:` | Firecrawl |

## Target Scoping Syntax
| Syntax | Scope | Example |
|--------|-------|---------|
| `!domain.com` | Root domain (expanded) | `bl? :!domain.com` |
| `domain.com/page!` | Specific page (contracted) | `?bl :domain.com/path!` |
| `:?domain.com` | Live search scope | `keyword :?domain.com` |
| `:<-domain.com` | Archive scope | `keyword :<-domain.com` |

## Filters & Modifiers
| Modifier | Description |
|----------|-------------|
| `@CLASS` | Class filter (@PERSON, @COMPANY, @SOURCE) |
| `##jurisdiction:CY` | Dimension filter |
| `##unchecked` | Filter to unchecked items |
| `##confidence:>0.8` | Confidence filter |

## Tagging Operators (Grid Results)
| Syntax | Description | Example |
|--------|-------------|---------|
| `=> #tag` | Tag results | `ent? :!domain.com => #EXTRACTED` |
| `=> +#tag` | Add tag to results | `?bl :!domain.com => +#backlink_sources` |
| `=> -#tag` | Remove tag from results | `=> -#old_tag` |
| `=> #workstream` | Link to workstream | `=> #investigation_ws` |

## Bulk Selection Operators
| Syntax | Description | Example |
|--------|-------------|---------|
| `(#node1 AND #node2)` | Boolean selection | `(#john AND #acme) => brute!{de!}` |
| `(#a OR #b)` | OR selection | `(#suspects OR #pois) => ent?` |
| `@CLASS ##filter` | Class + dimension | `@COMPANY ##jurisdiction:CY => #OFFSHORE` |

## Grid Operators (Node Operations)
| Operator | Description |
|----------|-------------|
| `ent? :!#nodename` | Entities from node + edges |
| `ent? :#nodename!` | Entities from node only |
| `=? :!#node1 #node2` | Compare two nodes |

## Routing Summary
```
execute(query)
    ├── x => y => z ──► Chain pipe (sequential operators)
    ├── chain: ───────► IOPlanner (multi-step investigations)
    ├── cuk: chr: ────► Torpedo (Registry profiles)
    ├── p: c: e: ─────► IOExecutor (Entity investigation)
    ├── :2022! :<- ───► Linklater (Historical/Archive)
    ├── bl? ol? ent? ─► QueryExecutor (Link/Entity extraction)
    └── "phrase" ─────► BruteSearch (40+ engines)
```
"""


class SastreMCP:
    """
    SASTRE MCP Server with Full Operator Syntax Access.

    Claude writes operator syntax → SASTRE executes against all backends.

    4 tools:
    - set_project: Context management
    - detect_context: Auto-detect genre/jurisdiction/entity_type
    - execute: Execute ANY operator syntax (single query → appropriate backend)
    - run: Execute full investigation loop (ThinOrchestrator + agents)

    Resources:
    - sastre://syntax: Full operator syntax reference for Claude to learn
    """

    def __init__(self):
        self.server = Server("sastre")
        self.project_id = "default"
        self.context = {
            "genre": None,
            "jurisdiction": None,
            "entity_type": None,
            "is_template_mode": False,
        }
        # Unified executor for all operator syntax
        self._executor = UnifiedExecutor()
        self._register_handlers()

    def _detect_from_query(self, query: str) -> dict:
        """
        Auto-detect investigation context from query.

        Uses template_loader patterns + heuristics.
        """
        query_lower = query.lower()
        result = {
            "genre": None,
            "jurisdiction": None,
            "entity_type": None,
            "is_template_mode": False,
        }

        # Genre detection
        if any(x in query_lower for x in ["dd", "due diligence", "diligence"]):
            result["genre"] = "due_diligence"
        elif any(x in query_lower for x in ["asset trace", "asset tracing", "assets"]):
            result["genre"] = "asset_trace"
        elif any(x in query_lower for x in ["kyc", "know your customer"]):
            result["genre"] = "kyc"
        elif any(x in query_lower for x in ["background", "vetting"]):
            result["genre"] = "background_check"
        elif any(x in query_lower for x in ["pep", "politically exposed"]):
            result["genre"] = "pep_screening"
        elif any(x in query_lower for x in ["sanction", "ofac", "watchlist"]):
            result["genre"] = "sanctions_screening"
        elif any(x in query_lower for x in ["litigation", "lawsuit", "legal"]):
            result["genre"] = "litigation_support"
        elif any(x in query_lower for x in ["ubo", "beneficial owner"]):
            result["genre"] = "ubo_investigation"

        # Template mode check
        if result["genre"]:
            result["is_template_mode"] = is_template_genre(result["genre"])

        # Jurisdiction detection
        jur_keywords = {
            "uk": ["uk", "united kingdom", "britain", "england", "companies house", "london"],
            "us": ["usa", "united states", "delaware", "nevada", "sec", "new york"],
            "hu": ["hungary", "hungarian", "budapest", "cégbíróság"],
            "de": ["germany", "german", "gmbh", "berlin", "handelsregister"],
            "fr": ["france", "french", "paris", "sarl", "infogreffe"],
            "cy": ["cyprus", "cypriot", "limassol", "nicosia"],
            "bvi": ["bvi", "british virgin", "tortola"],
            "lu": ["luxembourg", "luxemburg", "s.a.r.l"],
            "ch": ["switzerland", "swiss", "zurich", "geneva"],
            "at": ["austria", "austrian", "vienna", "gmbh"],
            "nl": ["netherlands", "dutch", "amsterdam", "b.v."],
            "ie": ["ireland", "irish", "dublin"],
            "rs": ["serbia", "serbian", "belgrade", "apr.gov.rs"],
            "hr": ["croatia", "croatian", "zagreb"],
            "es": ["spain", "spanish", "madrid", "s.l."],
            "it": ["italy", "italian", "rome", "s.r.l."],
            "ae": ["uae", "dubai", "emirates", "abu dhabi"],
            "sg": ["singapore", "singaporean"],
            "hk": ["hong kong"],
            "ru": ["russia", "russian", "moscow"],
            "ua": ["ukraine", "ukrainian", "kyiv"],
        }

        for code, terms in jur_keywords.items():
            if any(term in query_lower for term in terms):
                result["jurisdiction"] = code.upper()
                break

        # Entity type detection
        if any(x in query_lower for x in ["person", "individual", "mr ", "ms ", "dr ", "director", "ceo", "officer"]):
            result["entity_type"] = "person"
        elif any(x in query_lower for x in ["company", "corp", "ltd", "llc", "gmbh", "limited", "inc", "s.a.", "plc"]):
            result["entity_type"] = "company"
        else:
            result["entity_type"] = "company"  # default

        return result

    def _register_handlers(self):
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="set_project",
                    description="Set the current project ID. All subsequent operations use this project.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_id": {
                                "type": "string",
                                "description": "Project ID (e.g., 'acme_dd_2025', 'smith_background')"
                            }
                        },
                        "required": ["project_id"]
                    }
                ),

                Tool(
                    name="detect_context",
                    description="""Auto-detect investigation context from query.

Returns:
    - genre: due_diligence, asset_trace, kyc, background_check, pep_screening, etc.
    - jurisdiction: 2-letter code (UK, HU, DE, CY, BVI, etc.)
    - entity_type: person or company
    - is_template_mode: True if genre requires structured templates

Template Mode (DD, asset trace, KYC, etc.):
    → Triggers EDITH templates (217 jurisdictions, 31 genres, 59 sections)
    → Structured report sections

Free-range Mode (open investigations):
    → No templates, just Sastre writing style
    → Flexible narrative structure

Examples:
    "DD on Acme Corp in Hungary" → genre=due_diligence, jurisdiction=HU, entity_type=company, template_mode=True
    "Who owns this Cyprus shell company?" → genre=None, jurisdiction=CY, entity_type=company, template_mode=False
    "Background check on John Smith" → genre=background_check, entity_type=person, template_mode=True""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Investigation query or tasking"
                            }
                        },
                        "required": ["query"]
                    }
                ),

                Tool(
                    name="run",
                    description="""Run SASTRE investigation.

Delegates to the full SASTRE system:
    - ThinOrchestrator: Agent coordination
    - 7 Agents: writer, disambiguator, io_executor, grid_assessor, query_lab, similarity_engine, orchestrator
    - Skills: EDITH templates when in template mode
    - Other CLIs: EYE-D, LINKLATER, alldom, country engines

Modes:
    - interactive: Full CLI with commands (help, status, pause, add, focus, findings, sections, export)
    - stream: JSON stream for frontend consumption
    - json: Single JSON result

The --review flag pauses after each section for approval.

Examples:
    run "Investigate John Smith's corporate connections"
    run --genre due_diligence --jurisdiction HU "DD on Acme Corp"
    run --depth comprehensive "Full asset trace"
    run --stream "Corporate intelligence on XYZ Ltd"  # For frontend""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "tasking": {
                                "type": "string",
                                "description": "Investigation tasking"
                            },
                            "genre": {
                                "type": "string",
                                "enum": ["due_diligence", "background_check", "asset_trace",
                                        "corporate_intelligence", "litigation_support", "kyc"],
                                "description": "Report genre (auto-detected if not specified)"
                            },
                            "jurisdiction": {
                                "type": "string",
                                "description": "2-letter country code (auto-detected if not specified)"
                            },
                            "depth": {
                                "type": "string",
                                "enum": ["basic", "enhanced", "comprehensive"],
                                "default": "enhanced",
                                "description": "Investigation depth"
                            },
                            "max_iterations": {
                                "type": "integer",
                                "default": 10,
                                "description": "Maximum agent iterations"
                            },
                            "stream": {
                                "type": "boolean",
                                "default": True,
                                "description": "Stream JSON events (for frontend)"
                            }
                        },
                        "required": ["tasking"]
                    }
                ),

                Tool(
                    name="activate_template",
                    description="""Activate a specific EDITH template (Genre + Jurisdiction) and auto-create watchers.

This "Activates Template Mode" by:
1. Loading the specific template (e.g., UK Due Diligence).
2. Parsing the template sections (e.g., "Corporate Affiliations", "Litigation").
3. Automatically creating Watchers for each section (via +#w:Header).
4. Returning the investigation plan.

Use this when you know exactly what investigation you are running.

Example:
    activate_template(genre="due_diligence", jurisdiction="UK", project_id="acme_dd")
    activate_template(genre="asset_trace", jurisdiction="DE", entity_type="person")""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "genre": {
                                "type": "string",
                                "description": "Investigation genre (e.g., due_diligence, asset_trace, background_check)",
                                "enum": ["due_diligence", "asset_trace", "background_check", "kyc", "litigation_support", "sanctions_screening"]
                            },
                            "jurisdiction": {
                                "type": "string",
                                "description": "2-letter country code (e.g., UK, US, DE, HU, CY)"
                            },
                            "subject": {
                                "type": "string",
                                "description": "Name of the entity/person to investigate (e.g., 'Acme Corp', 'John Smith'). Essential for contextual watchers."
                            },
                            "entity_type": {
                                "type": "string",
                                "enum": ["company", "person"],
                                "default": "company",
                                "description": "Subject type"
                            },
                            "project_id": {
                                "type": "string",
                                "description": "Project ID to attach watchers to (defaults to current set_project ID)"
                            },
                            "auto_create_watchers": {
                                "type": "boolean",
                                "default": True,
                                "description": "Automatically execute +#w: commands for each section"
                            }
                        },
                        "required": ["genre", "jurisdiction"]
                    }
                ),

                Tool(
                    name="execute",
                    description="""Execute ANY operator syntax query.

This is the POWER tool. Write operator syntax → SASTRE routes to the appropriate backend.

CHAIN (=> Operator):
    Takes output from one operator, feeds to next. Just regular operators piped together.

    p: John Smith => c?           → Person search → extract companies from results
    bl? example.com => p?         → Backlinks → extract persons from results
    c: Acme Corp => ent?          → Company search → extract all entities

    IF/THEN: Conditional execution based on results.

CHAIN PRESETS (Multi-Step Investigations):
    chain: due_diligence c: Acme Corp :US  → 33 steps, 8 sections
    chain: ubo c: Siemens AG :DE           → Ultimate Beneficial Owners
    chain: officers c: Tesco PLC :GB       → Officers + Sanctions
    chain: pep p: John Smith               → Politically Exposed Person

IO PREFIXES (Entity Investigation):
    p: John Smith              → Person investigation
    c: Acme Corp :US           → Company investigation (with jurisdiction)
    e: john@example.com        → Email investigation
    d: example.com             → Domain investigation
    t: +1-555-0123             → Phone investigation

JURISDICTION-QUALIFIED PREFIXES (Entity + Country):
    cuk: / puk: / reguk: / lituk:  → UK entities
    chr: / phr:                     → Croatian entities
    chu: / phu:                     → Hungarian entities
    cde: / pde:                     → German entities
    cno: / pno:                     → Norwegian entities
    cfi: / pfi:                     → Finnish entities
    cch: / cie: / ccz: / cbe:       → Swiss/Irish/Czech/Belgian
    lei:                            → GLEIF LEI lookup

LINK ANALYSIS (LINKLATER):
    bl? :!domain.com           → Backlink pages
    ?bl :!domain.com           → Backlink domains (fast)
    ol? :!domain.com           → Outlink pages
    ?ol :!domain.com           → Outlink domains (fast)
    ?rl :!domain.com           → Related/co-cited domains
    ?ipl :!domain.com          → IP-linked domains
    ?owl :!domain.com          → Ownership-linked domains (WHOIS)

ENTITY EXTRACTION:
    ent? :!domain.com          → All entities from domain
    p? c? e? :!domain.com      → Persons, companies, emails
    p? :!domain.com            → Persons only

HISTORICAL/ARCHIVE:
    ent? :2022! !domain.com    → Entities from 2022 archives
    ent? :2020-2024! !domain.com → Date range

FILETYPE:
    pdf! :!domain.com          → Find PDFs on domain
    doc! :!domain.com          → All documents
    word! / xls! / ppt!        → Word/Excel/PowerPoint

MACRO OPERATORS (io_cli.py):
    cdom? Acme Corp            → Find company website/domain
    age? John Smith            → Find person age/DOB
    alldom? example.com        → Full domain analysis
    crel? Acme Corp            → Find related companies
    rep? example.com           → Reputation analytics

MATRIX EXPLORATION (io_cli.py):
    c=>[?]                     → What outputs from company?
    [?]=>e                     → What produces email?
    c=>officers                → Route: company → officers

DOMAIN INTELLIGENCE:
    whois:example.com          → WHOIS registration
    dns:example.com            → DNS records
    subdomains:example.com     → Subdomain discovery
    tech:example.com           → Technology stack
    similar? :!domain.com      → Similar pages (Exa)
    ga? :!domain.com           → Google Analytics detection

KEYWORD SEARCH:
    keyword :?domain.com       → Live domain search
    keyword :<-domain.com      → Archive search (backwards)
    keyword :->domain.com      → Archive search (forwards)

NAVIGATION:
    ?domain.com                → Discover all URLs on domain
    domain.com/page?           → Scrape specific page

DEFINITIONAL SHORTHANDS:
    [cde] / [cuk] / [cus]      → Company patterns
    [pde] / [puk] / [pus]      → Person patterns
    [lde] / [luk] / [lus]      → Location patterns

SINGLE ENGINE:
    GO: query                  → Google only
    BI: / BR: / DD: / YA:      → Bing/Brave/DuckDuckGo/Yandex

TOR/ONION:
    "keyword" :tor             → Search via Tor engines
    ent? :!xyz.onion           → Extract from .onion

GRID (Node Operations):
    ent? :!#nodename           → Entities from node + edges
    =? :!#node1 #node2         → Compare two nodes

EXACT PHRASE (40+ engines via BruteSearch):
    "John Smith"               → Maximum recall search
    "Acme Corporation"         → Exact phrase across all engines

TLD FILTERS:
    de! "keyword"              → German TLD only
    uk! "keyword"              → UK TLD only
    news! "keyword"            → News engines only

TAGGING (Grid Results):
    => #tag                    → Tag results
    => +#tag                   → Add tag to results
    => -#tag                   → Remove tag from results
    => #workstream             → Link to workstream

BULK SELECTION:
    (#node1 AND #node2)        → Boolean AND selection
    (#a OR #b) => operator     → OR selection then run operator
    @CLASS ##filter => #tag    → Class + dimension filter then tag

MODIFIERS:
    :XX at end                 → Jurisdiction (e.g., :US, :DE, :UK)
    !target                    → Expanded scope (domain level)
    target!                    → Contracted scope (page only)
    @CLASS                     → Filter by class (@PERSON, @COMPANY)
    ##dimension:val            → Filter by dimension (##jurisdiction:CY)

Returns structured JSON with results from the appropriate backend.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Operator syntax query (see description for full syntax reference)"
                            }
                        },
                        "required": ["query"]
                    }
                ),

                Tool(
                    name="syntax",
                    description="Get the full SASTRE operator syntax reference. Use this to learn all available operators and their usage.",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                ),

                Tool(
                    name="operators",
                    description="""Get operators from the central registry.

Returns operators filtered by category, with full metadata including:
- syntax, name, description
- examples with queries and descriptions
- handler_module and handler_function
- input_type and output_type

Categories: chain, io_prefix, jurisdiction, link_analysis, entity_extraction,
filetype, historical, keyword_search, navigation, context, macro, matrix,
enrichment, tagging, bulk_selection, filter, comparison, pairwise,
target_scope, grid, definitional, single_engine, tld_filter, brute_search

Examples:
    operators()                  → All operators
    operators(category="chain")  → Chain operators only
    operators(category="link_analysis") → Link analysis operators""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "category": {
                                "type": "string",
                                "description": "Filter by category (optional). Leave empty for all operators."
                            }
                        },
                        "required": []
                    }
                ),

                # === PROJECT MANAGEMENT TOOLS ===
                Tool(
                    name="project_create",
                    description="Create a new investigation project. Creates cymonides-1-{projectId} index for storing nodes.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Project name (e.g., 'Alpha Investigation')"},
                            "user_id": {"type": "integer", "default": 1, "description": "User ID"}
                        },
                        "required": ["name"]
                    }
                ),
                Tool(
                    name="project_list",
                    description="List all projects for a user.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "user_id": {"type": "integer", "default": 1}
                        }
                    }
                ),
                Tool(
                    name="project_delete",
                    description="Delete a project and its ES index.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_id": {"type": "string", "description": "Project ID to delete"},
                            "user_id": {"type": "integer", "default": 1}
                        },
                        "required": ["project_id"]
                    }
                ),
                Tool(
                    name="project_reset",
                    description="Reset a project (delete all nodes but keep project).",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_id": {"type": "string"},
                            "user_id": {"type": "integer", "default": 1}
                        },
                        "required": ["project_id"]
                    }
                ),
                Tool(
                    name="project_info",
                    description="Get info about current or specified project.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_id": {"type": "string", "description": "Project ID (or uses current)"},
                            "user_id": {"type": "integer", "default": 1}
                        }
                    }
                ),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Any) -> list[TextContent]:
            try:
                if name == "set_project":
                    old_project = self.project_id
                    self.project_id = arguments["project_id"]
                    return [TextContent(type="text", text=json.dumps({
                        "old_project": old_project,
                        "new_project": self.project_id,
                        "message": f"Project set to: {self.project_id}",
                        "current_context": self.context
                    }, indent=2))]

                elif name == "detect_context":
                    query = arguments["query"]
                    detected = self._detect_from_query(query)

                    # Update stored context
                    self.context.update(detected)

                    # Get template info if in template mode
                    template_info = None
                    if detected["is_template_mode"] and detected["genre"]:
                        template_info = get_template_context(
                            query=query,
                            genre=detected["genre"],
                            jurisdiction=detected.get("jurisdiction"),
                            entity_type=detected.get("entity_type")
                        )
                        # Summarize, don't dump entire templates
                        template_info = {
                            "is_template_mode": template_info.get("is_template_mode"),
                            "genre": template_info.get("genre"),
                            "jurisdiction": template_info.get("jurisdiction"),
                            "entity_type": template_info.get("entity_type"),
                            "sections_available": [s.get("name") for s in template_info.get("sections", [])],
                            "has_genre_template": template_info.get("genre_template") is not None,
                            "has_jurisdiction_template": template_info.get("jurisdiction_template") is not None,
                        }

                    return [TextContent(type="text", text=json.dumps({
                        "query": query,
                        "detected": detected,
                        "template_info": template_info,
                        "writing_style_applies": True,  # Always
                        "next_step": "Use 'run' tool with this tasking to start investigation"
                    }, indent=2))]

                elif name == "run":
                    tasking = arguments["tasking"]

                    # Build CLI command
                    cmd = [
                        sys.executable, "-m", "SASTRE.cli",
                        tasking,
                        "--project", self.project_id,
                        "--iterations", str(arguments.get("max_iterations", 10)),
                        "--depth", arguments.get("depth", "enhanced"),
                    ]

                    # Add genre if specified
                    if arguments.get("genre"):
                        cmd.extend(["--genre", arguments["genre"]])
                    elif self.context.get("genre"):
                        cmd.extend(["--genre", self.context["genre"]])

                    # Stream mode for MCP (always use JSON output)
                    if arguments.get("stream", True):
                        cmd.append("--stream")
                    else:
                        cmd.append("--json")

                    logger.info(f"Running SASTRE CLI: {' '.join(cmd)}")

                    # Execute CLI and stream output
                    try:
                        process = await asyncio.create_subprocess_exec(
                            *cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                            cwd=str(BACKEND_PATH),
                            env={
                                **dict(__import__('os').environ),
                                "PYTHONPATH": str(BACKEND_PATH)
                            }
                        )

                        stdout, stderr = await asyncio.wait_for(
                            process.communicate(),
                            timeout=600  # 10 minute timeout
                        )

                        output = stdout.decode() if stdout else ""
                        errors = stderr.decode() if stderr else ""

                        # Parse JSON lines from stream mode
                        events = []
                        for line in output.strip().split('\n'):
                            if line:
                                try:
                                    events.append(json.loads(line))
                                except json.JSONDecodeError:
                                    events.append({"raw": line})

                        return [TextContent(type="text", text=json.dumps({
                            "status": "completed" if process.returncode == 0 else "error",
                            "return_code": process.returncode,
                            "events": events,
                            "event_count": len(events),
                            "errors": errors if errors else None,
                            "project": self.project_id,
                        }, indent=2, default=str))]

                    except asyncio.TimeoutError:
                        return [TextContent(type="text", text=json.dumps({
                            "status": "timeout",
                            "message": "Investigation timed out after 10 minutes",
                            "project": self.project_id,
                        }))]
                    except Exception as e:
                        return [TextContent(type="text", text=json.dumps({
                            "status": "error",
                            "error": str(e),
                            "project": self.project_id,
                        }))]

                elif name == "activate_template":
                    genre = arguments["genre"]
                    jurisdiction = arguments["jurisdiction"]
                    subject = arguments.get("subject", "")
                    entity_type = arguments.get("entity_type", "company")
                    project_id = arguments.get("project_id") or self.project_id
                    auto_create = arguments.get("auto_create_watchers", True)

                    # 1. Load Template
                    template_data = compose_report_template(
                        genre=genre,
                        jurisdiction=jurisdiction,
                        entity_type=entity_type
                    )

                    # 2. Extract Sections
                    sections = template_data.get("sections", [])
                    section_headers = []
                    for section in sections:
                        # Extract name and prettify
                        name = section.get("name", "Untitled")
                        pretty_name = name.replace("_", " ").title()
                        section_headers.append(pretty_name)

                    # 3. Auto-Create Watchers with Context
                    watchers_created = []
                    errors = []

                    if auto_create:
                        logger.info(f"Auto-creating {len(section_headers)} watchers for project {project_id}")
                        
                        # Initialize WatcherBridge
                        watcher_bridge = WatcherBridge()
                        
                        for header in section_headers:
                            try:
                                # Construct Contextual Query
                                # This is crucial: Watchers are evaluated in isolation, so they need
                                # to know WHO and WHERE they are looking for.
                                # Example: "Corporate Affiliations" -> "Corporate Affiliations for Acme Corp in UK"
                                
                                contextual_query = header
                                if subject:
                                    contextual_query = f"{header} for {subject}"
                                if jurisdiction:
                                    contextual_query += f" in {jurisdiction}"
                                
                                # Create Watcher via Bridge
                                # name = header (keeps link to section)
                                # query = contextual_query (gives AI context)
                                res = await watcher_bridge.create(
                                    name=header,
                                    project_id=project_id,
                                    query=contextual_query
                                )
                                
                                if res and not res.get("error"):
                                    watchers_created.append({
                                        "header": header,
                                        "query_used": contextual_query,
                                        "id": res.get("id") or res.get("watcherId")
                                    })
                                else:
                                    errors.append(f"{header}: {res.get('error', 'Unknown error')}")
                                    
                            except Exception as e:
                                errors.append(f"{header}: {str(e)}")
                        
                        # Close bridge
                        # await watcher_bridge.close() # WatcherBridge usually shares session, check implementation

                    # Update context
                    self.context.update({
                        "genre": genre,
                        "jurisdiction": jurisdiction,
                        "subject": subject,
                        "entity_type": entity_type,
                        "is_template_mode": True
                    })

                    return [TextContent(type="text", text=json.dumps({
                        "status": "success",
                        "mode": "template_mode_activated",
                        "project_id": project_id,
                        "context": {
                            "subject": subject,
                            "jurisdiction": jurisdiction
                        },
                        "template": {
                            "genre": genre,
                            "section_count": len(sections),
                            "sections": section_headers
                        },
                        "watchers": {
                            "attempted": len(section_headers),
                            "created": len(watchers_created),
                            "details": watchers_created,
                            "errors": errors
                        },
                        "next_steps": [
                            "Watchers are now active with contextual queries.",
                            "Use 'run' to start the investigation loop.",
                            "Or use 'execute' with specific queries to feed the watchers."
                        ]
                    }, indent=2, default=str))]

                elif name == "execute":
                    # Execute ANY operator syntax via UnifiedExecutor
                    query = arguments["query"]
                    logger.info(f"Executing operator syntax: {query}")

                    try:
                        # Route to appropriate backend via UnifiedExecutor
                        result = await self._executor.execute(query, self.project_id)

                        return [TextContent(type="text", text=json.dumps({
                            "query": query,
                            "project": self.project_id,
                            "executor": result.get("_executor", "unknown"),
                            "results": result,
                            "status": "error" if result.get("error") else "success",
                        }, indent=2, default=str))]

                    except Exception as e:
                        logger.exception(f"Execute error: {e}")
                        return [TextContent(type="text", text=json.dumps({
                            "query": query,
                            "project": self.project_id,
                            "status": "error",
                            "error": str(e),
                        }, indent=2))]

                elif name == "syntax":
                    # Return full syntax reference for Claude to learn
                    syntax_ref = get_syntax_reference()
                    return [TextContent(type="text", text=syntax_ref)]

                elif name == "operators":
                    # Return operators from the central registry
                    registry = load_operator_registry()
                    operators = registry.get("operators", [])
                    categories = registry.get("categories", {})

                    # Filter by category if specified
                    category_filter = arguments.get("category")
                    if category_filter:
                        operators = [op for op in operators if op.get("category") == category_filter]

                    return [TextContent(type="text", text=json.dumps({
                        "source": "operators.json",
                        "total_operators": len(registry.get("operators", [])),
                        "filtered_count": len(operators),
                        "category_filter": category_filter,
                        "categories": categories,
                        "operators": operators,
                    }, indent=2))]

                # === PROJECT MANAGEMENT HANDLERS ===
                elif name == "project_create":
                    if not PROJECT_AVAILABLE:
                        return [TextContent(type="text", text=json.dumps({"error": "PROJECT module not available"}))]
                    user_id = arguments.get("user_id", 1)
                    project = create_project(user_id, arguments["name"])
                    self.project_id = project.get("id", self.project_id)
                    return [TextContent(type="text", text=json.dumps({
                        "success": True,
                        "project": project,
                        "index": get_project_index(project.get("id")),
                        "message": f"Created project: {project.get('name')}"
                    }, indent=2))]

                elif name == "project_list":
                    if not PROJECT_AVAILABLE:
                        return [TextContent(type="text", text=json.dumps({"error": "PROJECT module not available"}))]
                    user_id = arguments.get("user_id", 1)
                    projects = list_projects(user_id)
                    active = get_active_project(user_id)
                    return [TextContent(type="text", text=json.dumps({
                        "projects": projects,
                        "active_project": active,
                        "total": len(projects)
                    }, indent=2))]

                elif name == "project_delete":
                    if not PROJECT_AVAILABLE:
                        return [TextContent(type="text", text=json.dumps({"error": "PROJECT module not available"}))]
                    user_id = arguments.get("user_id", 1)
                    delete_project(user_id, arguments["project_id"])
                    if self.project_id == arguments["project_id"]:
                        self.project_id = "default"
                    return [TextContent(type="text", text=json.dumps({
                        "success": True,
                        "deleted": arguments["project_id"],
                        "current_project": self.project_id
                    }, indent=2))]

                elif name == "project_reset":
                    if not PROJECT_AVAILABLE:
                        return [TextContent(type="text", text=json.dumps({"error": "PROJECT module not available"}))]
                    user_id = arguments.get("user_id", 1)
                    reset_project(user_id, arguments["project_id"])
                    return [TextContent(type="text", text=json.dumps({
                        "success": True,
                        "reset": arguments["project_id"],
                        "message": f"All nodes deleted from {arguments['project_id']}"
                    }, indent=2))]

                elif name == "project_info":
                    if not PROJECT_AVAILABLE:
                        return [TextContent(type="text", text=json.dumps({"error": "PROJECT module not available"}))]
                    user_id = arguments.get("user_id", 1)
                    project_id = arguments.get("project_id") or self.project_id
                    project = get_project(user_id, project_id)
                    node_count = get_node_count(project_id) if project else 0
                    return [TextContent(type="text", text=json.dumps({
                        "project": project,
                        "node_count": node_count,
                        "index": get_project_index(project_id) if project else None,
                        "is_current": project_id == self.project_id
                    }, indent=2))]

                else:
                    return [TextContent(type="text", text=f"Unknown tool: {name}")]

            except Exception as e:
                logger.exception(f"Error executing {name}")
                return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

        # Resource handlers - expose syntax reference as readable resource
        @self.server.list_resources()
        async def list_resources() -> list[Resource]:
            return [
                Resource(
                    uri="sastre://syntax",
                    name="SASTRE Operator Syntax Reference",
                    description="Full reference for all SASTRE operator syntax: chain, IO, registry, link analysis, entity extraction, historical, filetype, grid, exact phrase, TLD filters",
                    mimeType="text/markdown"
                ),
                Resource(
                    uri="sastre://operators",
                    name="SASTRE Operators Registry (JSON)",
                    description="Complete operators.json - 220 operators with syntax, handlers, examples, categories. Single source of truth.",
                    mimeType="application/json"
                ),
                Resource(
                    uri="sastre://writing-style",
                    name="Sastre Professional Writing Style",
                    description="Writing style guide for Sastre reports: certainty calibration, attribution, formatting",
                    mimeType="text/markdown"
                ),
            ]

        @self.server.read_resource()
        async def read_resource(uri: str) -> ResourceContents:
            if uri == "sastre://syntax":
                return ResourceContents(
                    uri=uri,
                    mimeType="text/markdown",
                    text=get_syntax_reference()
                )
            elif uri == "sastre://operators":
                # Return raw operators.json
                registry = load_operator_registry()
                return ResourceContents(
                    uri=uri,
                    mimeType="application/json",
                    text=json.dumps(registry, indent=2)
                )
            elif uri == "sastre://writing-style":
                return ResourceContents(
                    uri=uri,
                    mimeType="text/markdown",
                    text=get_writing_style()
                )
            else:
                raise ValueError(f"Unknown resource: {uri}")

    async def run(self):
        """Run the MCP server."""
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            logger.info("SASTRE MCP Server (Full Operator Syntax) running on stdio")
            logger.info("6 tools: set_project, detect_context, execute, run, syntax, operators")
            logger.info(f"Default project: {self.project_id}")
            logger.info("Operator registry: operators.json (single source of truth)")
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )


def main():
    """CLI entry point."""
    server = SastreMCP()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
